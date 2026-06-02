"""Mass-scaling identity — mirror of the CADPORT plugin's helper.

CADPORT-TDD-STEP-001 §7.1.4. The ASTRA PATCH /api/v1/catalog/parts/
{id}/mass endpoint applies this identity to keep the inertia tensor +
density consistent with the new mass while leaving CG (a geometric
quantity) untouched.

Implementation note: deliberately mirrors ``cadport/services/
mass_recompute.py`` line-for-line where the YAML schema is concerned.
Both layers operate on the §6 YAML dict directly, so a §6 blob
round-tripped through either layer (or both) yields the same result.
The plugin-side copy is the source of truth — if you change one,
mirror the change here.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any


def _inertia_scaled(
    inertia: dict[str, Any], ratio: float
) -> dict[str, Any]:
    if not inertia:
        return {}
    out: dict[str, Any] = {}
    for k, v in inertia.items():
        if k in ("ixx", "iyy", "izz", "ixy", "ixz", "iyz"):
            try:
                out[k] = float(v) * float(ratio)
            except (TypeError, ValueError):
                out[k] = v
        else:
            out[k] = v
    return out


def _principal_moments_scaled(values: Any, ratio: float) -> list[float] | Any:
    if not isinstance(values, list):
        return values
    out: list[float] = []
    for v in values:
        try:
            out.append(float(v) * float(ratio))
        except (TypeError, ValueError):
            out.append(v)
    return out


def recompute_mass_dependent_fields(
    yaml_blob: dict[str, Any],
    *,
    new_mass_kg: float,
) -> dict[str, Any]:
    """Return a new §6 YAML blob with mass + inertia rescaled."""
    if new_mass_kg is None or float(new_mass_kg) <= 0.0:
        raise ValueError("new_mass_kg must be a positive float")
    out = deepcopy(yaml_blob)
    mp = out.get("mass_properties")
    if not isinstance(mp, dict):
        mp = {}
        out["mass_properties"] = mp
    old_mass = float(mp.get("mass_kg") or 0.0)
    new_mass = float(new_mass_kg)
    mp["mass_kg"] = new_mass
    if old_mass > 0.0:
        ratio = new_mass / old_mass
        mp["inertia_tensor_kg_m2"] = _inertia_scaled(
            mp.get("inertia_tensor_kg_m2") or {}, ratio
        )
        if "principal_moments_kg_m2" in mp:
            mp["principal_moments_kg_m2"] = _principal_moments_scaled(
                mp.get("principal_moments_kg_m2"), ratio
            )
    volume_m3 = float(mp.get("volume_m3") or 0.0)
    if volume_m3 > 0.0:
        mp["density_kg_m3"] = new_mass / volume_m3
    prov = out.get("provenance")
    if not isinstance(prov, dict):
        prov = {}
        out["provenance"] = prov
    prov["inertia_revised_via_uniform_scaling"] = True
    prov["mass_source"] = "user_override"
    prov.pop("material_assumed", None)
    return out


def clear_mass_dependent_fields(yaml_blob: dict[str, Any]) -> dict[str, Any]:
    """Drop mass + inertia; preserve geometry + CG (returns to 'cad' source)."""
    out = deepcopy(yaml_blob)
    mp = out.get("mass_properties")
    if isinstance(mp, dict):
        mp["mass_kg"] = 0.0
        mp["inertia_tensor_kg_m2"] = {
            k: 0.0 for k in ("ixx", "iyy", "izz", "ixy", "ixz", "iyz")
        }
        if "principal_moments_kg_m2" in mp:
            mp["principal_moments_kg_m2"] = [0.0, 0.0, 0.0]
        if float(mp.get("volume_m3") or 0.0) > 0.0:
            mp["density_kg_m3"] = 0.0
    prov = out.get("provenance")
    if isinstance(prov, dict):
        prov["inertia_revised_via_uniform_scaling"] = False
        prov["mass_source"] = None
        prov.pop("material_assumed", None)
    return out


def scaled_inertia_components(
    *,
    old_mass_kg: float,
    new_mass_kg: float,
    ixx: float | None,
    iyy: float | None,
    izz: float | None,
    ixy: float | None,
    ixz: float | None,
    iyz: float | None,
) -> dict[str, float | None]:
    """Scale a six-component inertia tensor in place. Returns a dict of
    the new values. NULL components stay NULL. When ``old_mass_kg`` is
    not positive the new components are returned as ``None`` (the caller
    is expected to re-derive from geometry in that case)."""
    if old_mass_kg is None or float(old_mass_kg) <= 0.0:
        return {"ixx": None, "iyy": None, "izz": None, "ixy": None, "ixz": None, "iyz": None}
    ratio = float(new_mass_kg) / float(old_mass_kg)

    def s(v: float | None) -> float | None:
        return None if v is None else float(v) * ratio

    return {
        "ixx": s(ixx), "iyy": s(iyy), "izz": s(izz),
        "ixy": s(ixy), "ixz": s(ixz), "iyz": s(iyz),
    }
