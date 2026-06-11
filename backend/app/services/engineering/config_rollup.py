"""
ASTRA — Config BOM mass-properties roll-up (spec §8)
====================================================
File: backend/app/services/engineering/config_rollup.py   ← NEW

Parallel-axis roll-up of a config's BOM components to the frame datum.
The math is EXACTLY the authoritative CADPORT assembly roll-up
(``app.services.cadport.assembly_rerollup``):

  * cg_world  = R · cg_local + t           (placement applied)
  * I_world   = R · I_local · Rᵀ           (tensor rotated, about own CG)
  * I_total   = Σ [ I_world + m·(‖d‖²·I₃ − d⊗d) ],  d = cg_world − cg_total
  * cg_total  = (Σ m · cg_world) / Σ m

Component mass / CG / inertia come from the catalog columns
(``CatalogPart`` resolved by WPN = ``internal_part_number``). The
``placement`` is a 4×4 row-major homogeneous matrix (rotation 3×3 in
the top-left, translation in the right column — CADPORT §6
``transform_m`` convention); a missing placement means identity.

Strictness differs from the CADPORT assembly path on purpose: there a
component with missing data is SKIPPED (contribution zero); here a
component without mass or CG makes the roll-up NOT COMPUTABLE — the
caller surfaces a 422 naming the offending parts (spec §8). A missing
inertia tensor is tolerated as a zero tensor + warning (point-mass
treatment) because CADPORT YAMLs can legitimately omit it.

``referencePoint_m_B`` is fixed at [0,0,0] — the frame datum itself.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

from app.models.catalog import CatalogPart

#: The roll-up reference point: the frame datum (spec §3 — one datum).
REFERENCE_POINT_M_B: List[float] = [0.0, 0.0, 0.0]


@dataclass
class RollupOutcome:
    """Result of :func:`rollup_components`. ``rollup`` is None iff
    ``errors`` is non-empty (roll-up not computable)."""
    rollup: Optional[Dict[str, Any]]
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


def parse_placement(
    placement: Optional[List[List[float]]],
) -> Tuple[np.ndarray, np.ndarray]:
    """4×4 nested list → (R, t). None ⇒ identity. Mirrors
    ``assembly_rerollup._parse_transform`` (minus the JSON-string
    decode — config placements are already lists)."""
    if placement is None:
        return np.eye(3), np.zeros(3)
    M = np.array([[float(v) for v in row] for row in placement], dtype=float)
    if M.shape == (4, 4) or M.shape == (3, 4):
        return M[:3, :3], M[:3, 3]
    if M.shape == (3, 3):
        return M, np.zeros(3)
    raise ValueError(f"placement must be a 4x4 matrix, got shape {M.shape}")


def _part_cg(part: CatalogPart) -> Optional[np.ndarray]:
    vals = (part.center_of_mass_x, part.center_of_mass_y, part.center_of_mass_z)
    if any(v is None for v in vals):
        return None
    return np.array([float(v) for v in vals], dtype=float)


def part_inertia_matrix(part: CatalogPart) -> Optional[np.ndarray]:
    """Symmetric 3×3 inertia tensor about the part's own CG, in its
    own frame. None when any component is NULL."""
    vals = (part.ixx, part.iyy, part.izz, part.ixy, part.ixz, part.iyz)
    if any(v is None for v in vals):
        return None
    ixx, iyy, izz, ixy, ixz, iyz = (float(v) for v in vals)
    return np.array(
        [
            [ixx, ixy, ixz],
            [ixy, iyy, iyz],
            [ixz, iyz, izz],
        ],
        dtype=float,
    )


def rollup_components(
    components: List[Dict[str, Any]],
    parts_by_wpn: Dict[str, CatalogPart],
) -> RollupOutcome:
    """Roll up *components* (the persisted component dicts) using the
    already-resolved catalog parts.

    Returns errors (one per offending component) instead of a rollup
    when any component lacks mass or CG, or has an unparseable
    placement — the save-time validator turns those into a 422.
    """
    errors: List[Dict[str, Any]] = []
    warnings: List[str] = []
    contributing: List[Tuple[float, np.ndarray, np.ndarray]] = []
    # (mass, cg_world, I_world)

    if not components:
        errors.append({
            "code": "empty_bom",
            "message": "config has no components — roll-up not computable",
        })
        return RollupOutcome(rollup=None, errors=errors)

    for comp in components:
        wpn = comp.get("wpn")
        part = parts_by_wpn.get(wpn)
        if part is None:
            # The validator reports unknown WPNs separately; skip here.
            continue

        missing = []
        if part.mass_kg is None:
            missing.append("mass")
        cg_local = _part_cg(part)
        if cg_local is None:
            missing.append("CG")
        if missing:
            errors.append({
                "code": "rollup_not_computable",
                "wpn": wpn,
                "message": (
                    f"component {wpn} ({part.name}) has no "
                    f"{' or '.join(missing)} in the catalog — "
                    "roll-up not computable"
                ),
            })
            continue

        I_local = part_inertia_matrix(part)
        if I_local is None:
            I_local = np.zeros((3, 3))
            warnings.append(
                f"component {wpn} has no inertia tensor in the catalog; "
                "treated as a point mass (zero local inertia)"
            )

        try:
            R, t = parse_placement(comp.get("placement"))
        except (ValueError, TypeError) as exc:
            errors.append({
                "code": "bad_placement",
                "wpn": wpn,
                "message": f"component {wpn}: invalid placement matrix: {exc}",
            })
            continue

        cg_world = R @ cg_local + t
        I_world = R @ I_local @ R.T
        contributing.append((float(part.mass_kg), cg_world, I_world))

    if errors:
        return RollupOutcome(rollup=None, errors=errors, warnings=warnings)

    total_mass = sum(m for m, _cg, _I in contributing)
    if total_mass <= 0.0:
        return RollupOutcome(
            rollup=None,
            errors=[{
                "code": "rollup_not_computable",
                "message": "total mass is zero — roll-up not computable",
            }],
            warnings=warnings,
        )

    cg_total = sum((m * cg for m, cg, _I in contributing), np.zeros(3))
    cg_total = cg_total / total_mass

    I_total = np.zeros((3, 3))
    for m, cg_world, I_world in contributing:
        d = cg_world - cg_total
        # Parallel-axis displacement: m · (‖d‖²·I₃ − d⊗d) — identical
        # to assembly_rerollup.rollup_assembly.
        I_total += I_world + m * (float(np.dot(d, d)) * np.eye(3)
                                  - np.outer(d, d))

    rollup = {
        "totalMass_kg": float(total_mass),
        "cg_m_B": [float(x) for x in cg_total],
        "inertia_kgm2_B": [[float(v) for v in row] for row in I_total],
        "referencePoint_m_B": list(REFERENCE_POINT_M_B),
        "method": "parallel_axis",
    }
    return RollupOutcome(rollup=rollup, errors=[], warnings=warnings)
