"""Assembly mass / CG / inertia re-rollup.

CADPORT-TDD-STEP-001 §7.1.3. Triggered after a part-mass edit when the
edited part is a component of one or more ``cadport_assemblies``.
Re-aggregates the assembly's rollup fields from the CURRENT state of
its components — i.e. ``cadport_assembly_components`` joined to
``catalog_parts`` with the per-instance transforms applied.

Math (standard rigid-body composition, CITADEL body frame):

  * **Mass**       — M = Σ qᵢ · mᵢ for each non-suppressed component.
  * **CG**         — body-frame CG = mass-weighted average of the
                     component CGs (in the assembly frame).
                     cg = (Σ qᵢ · mᵢ · (R_i · cg_i + t_i)) / M.
  * **Inertia**    — about the assembly's CG, in the assembly frame:
                     I_assembly = Σ qᵢ · (R_i · I_i · R_iᵀ
                                          + mᵢ · skew(d_i)ᵀ · skew(d_i))
                     where d_i = (R_i · cg_i + t_i) − cg_assembly
                     (vector from assembly CG to the component CG in
                     the assembly frame). The first term rotates the
                     component's inertia tensor about its own CG into
                     the assembly frame; the second is the parallel-
                     axis displacement term.

The transform_json on each component is a 4×4 homogeneous matrix
in the same convention CADPORT's §6 components[].transform_m field
uses (rotation 3×3 in the top-left, translation 3×1 in the right
column). When transform_json is NULL the identity is assumed.

Flag propagation: the assembly's
``inertia_revised_via_uniform_scaling`` flag is set to True iff ANY
constituent part has its flag set OR the caller passes
``triggered_by_scaling=True`` (the part-mass-edit pathway).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.models.catalog import (
    CadportAssembly,
    CadportAssemblyComponent,
    CatalogPart,
)

logger = logging.getLogger(__name__)


@dataclass
class AssemblyRollupResult:
    assembly_pk: int
    total_mass_kg: float
    center_of_mass: tuple[float, float, float]
    inertia: dict[str, float]  # ixx/iyy/izz/ixy/ixz/iyz, kg·m²
    inertia_revised_via_uniform_scaling: bool
    component_count: int
    skipped: list[str]  # one-line reasons for any components that were skipped


def _parse_transform(transform_json: Optional[str]) -> tuple[np.ndarray, np.ndarray]:
    """Return (R, t) in assembly frame. NULL / parse failure → identity."""
    if not transform_json:
        return np.eye(3), np.zeros(3)
    try:
        matrix = json.loads(transform_json)
    except Exception:  # noqa: BLE001 — non-fatal
        return np.eye(3), np.zeros(3)
    if not isinstance(matrix, list) or len(matrix) < 3:
        return np.eye(3), np.zeros(3)
    try:
        M = np.array([[float(v) for v in row] for row in matrix], dtype=float)
    except (TypeError, ValueError):
        return np.eye(3), np.zeros(3)
    if M.shape == (4, 4):
        return M[:3, :3], M[:3, 3]
    if M.shape == (3, 4):
        return M[:3, :3], M[:3, 3]
    if M.shape == (3, 3):
        return M, np.zeros(3)
    return np.eye(3), np.zeros(3)


def _component_inertia_matrix(part: CatalogPart) -> Optional[np.ndarray]:
    """Build the symmetric 3×3 inertia tensor for a part, in its own
    body frame. Returns None when any required component is NULL."""
    parts = (part.ixx, part.iyy, part.izz, part.ixy, part.ixz, part.iyz)
    if any(p is None for p in parts):
        return None
    ixx, iyy, izz, ixy, ixz, iyz = (float(p) for p in parts)
    return np.array(
        [
            [ixx, ixy, ixz],
            [ixy, iyy, iyz],
            [ixz, iyz, izz],
        ],
        dtype=float,
    )


def _skew(v: np.ndarray) -> np.ndarray:
    """Skew-symmetric matrix [v]× such that [v]× · w = v × w."""
    return np.array(
        [
            [0.0, -v[2], v[1]],
            [v[2], 0.0, -v[0]],
            [-v[1], v[0], 0.0],
        ],
        dtype=float,
    )


def _component_cg(part: CatalogPart) -> Optional[np.ndarray]:
    parts = (part.center_of_mass_x, part.center_of_mass_y, part.center_of_mass_z)
    if any(p is None for p in parts):
        return None
    return np.array([float(p) for p in parts], dtype=float)


def rollup_assembly(
    db: Session,
    *,
    assembly: CadportAssembly,
    triggered_by_scaling: bool = False,
) -> AssemblyRollupResult:
    """Re-aggregate this assembly's rollup fields and persist them.

    Returns the new totals so the caller can include them in a response
    or log line. Skipped components (NULL part, NULL mass, NULL CG,
    NULL inertia) are noted in ``skipped`` — their contribution is
    treated as zero rather than blocking the rollup.
    """
    components = (
        db.query(CadportAssemblyComponent)
        .filter(CadportAssemblyComponent.assembly_id == assembly.id)
        .all()
    )

    total_mass = 0.0
    weighted_cg = np.zeros(3)
    contributing: list[tuple[float, np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = []
    # Each entry: (m_i_total, R_i, cg_world_i (vector), I_i_world (3x3), t_i (vector))

    skipped: list[str] = []
    flag_inherited = False

    for c in components:
        if c.suppressed:
            continue
        if c.catalog_part_id is None or c.catalog_part is None:
            skipped.append(f"component {c.instance_name!r}: no catalog_part link")
            continue
        part = c.catalog_part
        if part.deleted_at is not None:
            skipped.append(f"component {c.instance_name!r}: part soft-deleted")
            continue
        if part.mass_kg is None:
            skipped.append(f"component {c.instance_name!r}: part has no mass")
            continue
        cg_local = _component_cg(part)
        if cg_local is None:
            skipped.append(f"component {c.instance_name!r}: part has no CG")
            continue
        I_local = _component_inertia_matrix(part)
        if I_local is None:
            skipped.append(f"component {c.instance_name!r}: part has no inertia")
            continue
        R, t = _parse_transform(c.transform_json)
        # CG in the assembly frame.
        cg_world = R @ cg_local + t
        # Inertia about the component's CG, rotated into the assembly frame.
        I_world = R @ I_local @ R.T
        m_each = float(part.mass_kg)
        qty = max(1, int(c.quantity or 1))
        m_total_for_instance = m_each * qty
        total_mass += m_total_for_instance
        weighted_cg += m_total_for_instance * cg_world
        contributing.append((m_total_for_instance, R, cg_world, I_world, t))
        if bool(part.inertia_revised_via_uniform_scaling):
            flag_inherited = True

    if total_mass > 0.0:
        cg_assembly = weighted_cg / total_mass
        I_assembly = np.zeros((3, 3))
        for m, _R, cg_world, I_world, _t in contributing:
            d = cg_world - cg_assembly
            # Parallel-axis displacement term: m * (||d||² · I_3 - d·d^T)
            # which equals m · [d]×^T · [d]× for the standard convention.
            d_outer = np.outer(d, d)
            d_squared = float(np.dot(d, d))
            parallel = m * (d_squared * np.eye(3) - d_outer)
            I_assembly += I_world + parallel
    else:
        cg_assembly = np.zeros(3)
        I_assembly = np.zeros((3, 3))

    assembly.total_mass_kg = float(total_mass)
    assembly.center_of_mass_x = float(cg_assembly[0])
    assembly.center_of_mass_y = float(cg_assembly[1])
    assembly.center_of_mass_z = float(cg_assembly[2])
    assembly.ixx = float(I_assembly[0, 0])
    assembly.iyy = float(I_assembly[1, 1])
    assembly.izz = float(I_assembly[2, 2])
    assembly.ixy = float(I_assembly[0, 1])
    assembly.ixz = float(I_assembly[0, 2])
    assembly.iyz = float(I_assembly[1, 2])
    flag = flag_inherited or bool(triggered_by_scaling)
    assembly.inertia_revised_via_uniform_scaling = flag

    db.add(assembly)

    return AssemblyRollupResult(
        assembly_pk=int(assembly.id),
        total_mass_kg=float(total_mass),
        center_of_mass=(
            float(cg_assembly[0]),
            float(cg_assembly[1]),
            float(cg_assembly[2]),
        ),
        inertia={
            "ixx": float(I_assembly[0, 0]),
            "iyy": float(I_assembly[1, 1]),
            "izz": float(I_assembly[2, 2]),
            "ixy": float(I_assembly[0, 1]),
            "ixz": float(I_assembly[0, 2]),
            "iyz": float(I_assembly[1, 2]),
        },
        inertia_revised_via_uniform_scaling=flag,
        component_count=len(contributing),
        skipped=skipped,
    )


def rerollup_assemblies_containing_part(
    db: Session,
    *,
    catalog_part_id: int,
    triggered_by_scaling: bool = True,
) -> list[AssemblyRollupResult]:
    """For every assembly that lists ``catalog_part_id`` as a non-
    suppressed component, re-roll up its mass / CG / inertia. Returns
    one result per assembly touched. Caller owns the commit."""
    assembly_pks = (
        db.query(CadportAssemblyComponent.assembly_id)
        .filter(CadportAssemblyComponent.catalog_part_id == catalog_part_id)
        .distinct()
        .all()
    )
    out: list[AssemblyRollupResult] = []
    for (pk,) in assembly_pks:
        assembly = (
            db.query(CadportAssembly).filter(CadportAssembly.id == pk).first()
        )
        if assembly is None:
            continue
        try:
            out.append(
                rollup_assembly(
                    db, assembly=assembly, triggered_by_scaling=triggered_by_scaling
                )
            )
        except Exception:  # noqa: BLE001 - one bad assembly doesn't fail the rest
            logger.exception(
                "assembly rollup failed for assembly_pk=%s after part %s edit",
                pk,
                catalog_part_id,
            )
    return out
