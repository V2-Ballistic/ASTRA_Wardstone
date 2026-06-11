"""Mass-recompute parity guard — config-ecosystem deltas (spec §7.4).

ASTRA's ``app/services/cadport/mass_recompute.py`` is a deliberate
line-for-line mirror of CADPORT's ``cadport/services/mass_recompute.py``
(the plugin-side copy is the source of truth). Parity between the two
was manually verified identical; this golden-vector test is the cheap
drift guard that keeps it that way.

THE IDENTICAL GOLDEN VECTORS LIVE IN CADPORT's
``tests/unit/test_mass_recompute_parity.py`` (C:\\Tools\\CADPORT). If
you change the identity here, change it there AND update both copies
of the vectors in the same change — a mismatch means the two systems
would disagree about the same §6 YAML blob.

Vectors: mass 2.7 kg -> 5.4 kg (ratio exactly 2.0): every inertia
component x2, principal moments x2, density recomputed from the new
mass and the unchanged volume, CG untouched, provenance flips to
user_override + uniform-scaling. ``clear`` returns the blob to the
geometric-only state.
"""

from __future__ import annotations

import copy

import pytest

from app.services.cadport.mass_recompute import (
    clear_mass_dependent_fields,
    recompute_mass_dependent_fields,
)

# ── Golden input (fixed §6 YAML blob) ──────────────────────────────────
# Keep byte-identical with the CADPORT copy.

GOLDEN_INPUT = {
    "schema_version": "1.0",
    "kind": "part",
    "part_id": "00000000-0000-4000-8000-000000000001",
    "mass_properties": {
        "units": "SI",
        "coordinate_system": "body_frame",
        "mass_kg": 2.7,
        "volume_m3": 0.001,
        "surface_area_m2": 0.06,
        "density_kg_m3": 2700.0,
        "center_of_mass_m": {"x": 0.01, "y": -0.02, "z": 0.03},
        "inertia_tensor_kg_m2": {
            "ixx": 0.011,
            "iyy": 0.022,
            "izz": 0.033,
            "ixy": 0.0012,
            "ixz": -0.0013,
            "iyz": 0.0014,
        },
        "principal_moments_kg_m2": [0.010, 0.021, 0.035],
    },
    "provenance": {
        "source": "step",
        "mass_source": "computed_from_material",
        "material_assumed": "al_6061_t6",
        "inertia_revised_via_uniform_scaling": False,
    },
}

NEW_MASS_KG = 5.4  # exactly 2x -> ratio 2.0, no float slop in expectations

# ── Golden expected outputs ────────────────────────────────────────────

EXPECTED_RECOMPUTED_MP = {
    "units": "SI",
    "coordinate_system": "body_frame",
    "mass_kg": 5.4,
    "volume_m3": 0.001,
    "surface_area_m2": 0.06,
    "density_kg_m3": 5400.0,  # 5.4 / 0.001
    "center_of_mass_m": {"x": 0.01, "y": -0.02, "z": 0.03},  # geometric — unchanged
    "inertia_tensor_kg_m2": {
        "ixx": 0.022,
        "iyy": 0.044,
        "izz": 0.066,
        "ixy": 0.0024,
        "ixz": -0.0026,
        "iyz": 0.0028,
    },
    "principal_moments_kg_m2": [0.020, 0.042, 0.070],
}

EXPECTED_CLEARED_MP = {
    "units": "SI",
    "coordinate_system": "body_frame",
    "mass_kg": 0.0,
    "volume_m3": 0.001,
    "surface_area_m2": 0.06,
    "density_kg_m3": 0.0,
    "center_of_mass_m": {"x": 0.01, "y": -0.02, "z": 0.03},
    "inertia_tensor_kg_m2": {
        "ixx": 0.0, "iyy": 0.0, "izz": 0.0,
        "ixy": 0.0, "ixz": 0.0, "iyz": 0.0,
    },
    "principal_moments_kg_m2": [0.0, 0.0, 0.0],
}


def test_recompute_golden_vector():
    blob = copy.deepcopy(GOLDEN_INPUT)
    out = recompute_mass_dependent_fields(blob, new_mass_kg=NEW_MASS_KG)

    # Input not mutated.
    assert blob == GOLDEN_INPUT

    mp = out["mass_properties"]
    for key, expected in EXPECTED_RECOMPUTED_MP.items():
        if key == "inertia_tensor_kg_m2":
            for comp, val in expected.items():
                assert mp[key][comp] == pytest.approx(val, rel=1e-12), comp
        elif key == "principal_moments_kg_m2":
            assert mp[key] == pytest.approx(expected, rel=1e-12)
        elif isinstance(expected, float):
            assert mp[key] == pytest.approx(expected, rel=1e-12), key
        else:
            assert mp[key] == expected, key

    prov = out["provenance"]
    assert prov["inertia_revised_via_uniform_scaling"] is True
    assert prov["mass_source"] == "user_override"
    assert "material_assumed" not in prov
    assert prov["source"] == "step"  # passthrough keys preserved

    # Non-mass top-level keys ride through unchanged.
    assert out["part_id"] == GOLDEN_INPUT["part_id"]
    assert out["kind"] == "part"


def test_clear_golden_vector():
    blob = copy.deepcopy(GOLDEN_INPUT)
    out = clear_mass_dependent_fields(blob)

    assert blob == GOLDEN_INPUT  # input not mutated

    mp = out["mass_properties"]
    for key, expected in EXPECTED_CLEARED_MP.items():
        assert mp[key] == expected, key

    prov = out["provenance"]
    assert prov["inertia_revised_via_uniform_scaling"] is False
    assert prov["mass_source"] is None
    assert "material_assumed" not in prov


def test_recompute_rejects_non_positive_mass():
    for bad in (0.0, -1.0, None):
        with pytest.raises(ValueError):
            recompute_mass_dependent_fields(
                copy.deepcopy(GOLDEN_INPUT), new_mass_kg=bad
            )


def test_recompute_then_clear_round_trip_is_geometric_only():
    """recompute -> clear lands on the same cleared state as clear alone
    (the identity has no path-dependence)."""
    a = clear_mass_dependent_fields(copy.deepcopy(GOLDEN_INPUT))
    b = clear_mass_dependent_fields(
        recompute_mass_dependent_fields(
            copy.deepcopy(GOLDEN_INPUT), new_mass_kg=NEW_MASS_KG
        )
    )
    assert a == b
