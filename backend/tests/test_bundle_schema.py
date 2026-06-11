"""
ASTRA — CITADEL Config Bundle v1 schema tests
==============================================
File: backend/tests/test_bundle_schema.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §1)

Determinism is the load-bearing property: same config rev ⇒ same
canonical bytes ⇒ same bundleHash. Covers:

  * example manifest fixture validating against the schema
  * manifest round-trip (validate → dump → validate → identical dump)
  * canonical_json determinism across dict insertion orders
  * compute_bundle_hash: bundleHash-exclusion, sensitivity to any
    field change, input not mutated
  * NaN rejection
  * bundle_dirname / artifact_filename / sha256_bytes helpers
  * strict contract: unknown keys + bad role rejected
"""

from __future__ import annotations

import copy
import json

import pytest
from pydantic import ValidationError

from app.services.engineering.bundle_schema import (
    ARTIFACT_SUFFIXES,
    SCHEMA_ID,
    ArtifactRef,
    Manifest,
    artifact_filename,
    bundle_dirname,
    canonical_json,
    compute_bundle_hash,
    manifest_to_dict,
    sha256_bytes,
)

_SHA_A = "a" * 64
_SHA_B = "b" * 64
_SHA_C = "c" * 64


def _example_manifest_dict() -> dict:
    """A complete, valid citadel-config-bundle/1.0 manifest."""
    return {
        "schema": SCHEMA_ID,
        "bundle": {
            "id": "7f3a1c2e-0000-4000-8000-000000000001",
            "createdUtc": "2026-06-10T12:00:00Z",
            "createdBy": "masongawler5@gmail.com",
            "astraBaselineId": 12,
            "astraBaselineRev": "1",
            "bundleHash": None,
        },
        "config": {
            "wpn": "WS-CFG-P000001-A",
            "name": "CITADEL Block 1",
            "rev": "A",
            "description": "First flight configuration",
            "topAssemblyWpn": "WS-FH-P000042-A",
        },
        "frame": {
            "icdId": "citadel-vehicle-body-frame",
            "icdRev": 1,
            "datum": "OML_nose_tip",
            "axes": "x_fwd_y_right_z_down",
            "units": "SI",
        },
        "massProperties": {
            "totalMass_kg": 42.5,
            "cg_m_B": [1.2, 0.0, 0.01],
            "inertia_kgm2_B": [
                [0.8, 0.0, 0.0],
                [0.0, 12.4, 0.0],
                [0.0, 0.0, 12.4],
            ],
            "referencePoint_m_B": [0.0, 0.0, 0.0],
            "method": "parallel_axis",
        },
        "components": [
            {
                "role": "structure",
                "wpn": "WS-FH-P000042-A",
                "rev": "A",
                "name": "Airframe",
                "mass_kg": 18.0,
                "cg_m_B": [1.5, 0.0, 0.0],
                "inertia_kgm2_B": [
                    [0.5, 0.0, 0.0],
                    [0.0, 6.0, 0.0],
                    [0.0, 0.0, 6.0],
                ],
                "placement": None,
                "artifact": {
                    "type": "massprops",
                    "file": f"{_SHA_A}.massprops.yaml",
                    "sha256": _SHA_A,
                    "sourceSystem": "cadport",
                    "ingestUtc": "2026-06-09T08:00:00Z",
                    "qualityTier": "measured",
                    "origin": "solidworks",
                    "designProvenanceId": "dp-001",
                },
            },
        ],
        "aero": {
            "wpn": "WS-AER-P000003-A",
            "rev": "A",
            "omlWpn": "WS-FH-P000042-A",
            "Sref_m2": 0.0182,
            "Lref_m": 0.152,
            "refPoint_m_B": [0.0, 0.0, 0.0],
            "validityEnvelope": {
                "machRange": [0.0, 2.5],
                "alphaRange_deg": [-10.0, 10.0],
                "betaRange_deg": [-5.0, 5.0],
            },
            "artifact": {
                "type": "aero",
                "file": f"{_SHA_B}.aero.json",
                "sha256": _SHA_B,
                "sourceSystem": "astra",
                "ingestUtc": "2026-06-09T09:00:00Z",
                "qualityTier": None,
                "origin": None,
                "designProvenanceId": None,
            },
        },
        "propulsion": [
            {
                "stageNum": 1,
                "motorWpn": "WS-MTR-P000007-B",
                "motorRev": "B",
                "ignitionTime_s": 0.0,
                "thrustAxis_B": [1.0, 0.0, 0.0],
                "mcTrialId": "mc-2026-06-01",
                "artifact": {
                    "type": "motor",
                    "file": f"{_SHA_C}.motor.json",
                    "sha256": _SHA_C,
                    "sourceSystem": "astra",
                    "ingestUtc": "2026-06-09T10:00:00Z",
                    "qualityTier": None,
                    "origin": None,
                    "designProvenanceId": None,
                },
            },
        ],
        "recommendedFidelity": "6dof",
        "dependencies": [
            {"wpn": "WS-MTR-P000007-B", "rev": "B", "sha256": _SHA_C},
        ],
        "provenance": {
            "harold": {"ledgerIds": [7, 42]},
            "astra": {
                "baselineId": 12,
                "exportedBy": "masongawler5@gmail.com",
                "exportedUtc": "2026-06-10T12:00:00Z",
            },
        },
    }


@pytest.fixture()
def example_manifest() -> dict:
    return _example_manifest_dict()


# ── Validation / round-trip ─────────────────────────────────────────

class TestManifestValidation:
    def test_example_validates(self, example_manifest):
        m = Manifest.model_validate(example_manifest)
        assert m.schema_ == SCHEMA_ID
        assert m.config.wpn == "WS-CFG-P000001-A"
        assert m.frame.icdId == "citadel-vehicle-body-frame"
        assert m.massProperties.method == "parallel_axis"
        assert m.components[0].role == "structure"
        assert m.propulsion[0].motorWpn == "WS-MTR-P000007-B"

    def test_round_trip_is_stable(self, example_manifest):
        m1 = Manifest.model_validate(example_manifest)
        d1 = manifest_to_dict(m1)
        m2 = Manifest.model_validate(d1)
        d2 = manifest_to_dict(m2)
        assert d1 == d2
        assert d1["schema"] == SCHEMA_ID  # wire key, not 'schema_'
        # Round-trip of the complete fixture reproduces it exactly.
        assert d1 == example_manifest

    def test_minimal_manifest_optional_blocks_absent(self, example_manifest):
        minimal = copy.deepcopy(example_manifest)
        del minimal["aero"]
        del minimal["propulsion"]
        del minimal["recommendedFidelity"]
        m = Manifest.model_validate(minimal)
        assert m.aero is None
        assert m.propulsion is None
        assert m.recommendedFidelity is None

    def test_unknown_key_rejected(self, example_manifest):
        bad = copy.deepcopy(example_manifest)
        bad["surpriseField"] = True
        with pytest.raises(ValidationError):
            Manifest.model_validate(bad)

    def test_bad_role_rejected(self, example_manifest):
        bad = copy.deepcopy(example_manifest)
        bad["components"][0]["role"] = "warp_core"
        with pytest.raises(ValidationError):
            Manifest.model_validate(bad)

    def test_bad_sha256_rejected(self):
        with pytest.raises(ValidationError):
            ArtifactRef(
                type="motor",
                file="x.motor.json",
                sha256="not-a-sha",
                sourceSystem="astra",
                ingestUtc="2026-06-10T12:00:00Z",
            )

    def test_wrong_vector_length_rejected(self, example_manifest):
        bad = copy.deepcopy(example_manifest)
        bad["massProperties"]["cg_m_B"] = [1.0, 2.0]
        with pytest.raises(ValidationError):
            Manifest.model_validate(bad)


# ── Determinism ─────────────────────────────────────────────────────

def _reorder_keys(obj):
    """Deep-copy *obj* with every dict's insertion order reversed —
    structurally equal, byte-different under naive json.dumps."""
    if isinstance(obj, dict):
        return {k: _reorder_keys(obj[k]) for k in reversed(list(obj))}
    if isinstance(obj, list):
        return [_reorder_keys(v) for v in obj]
    return obj


class TestDeterminism:
    def test_canonical_json_ignores_insertion_order(self, example_manifest):
        reordered = _reorder_keys(example_manifest)
        assert reordered == example_manifest  # structurally equal
        assert (
            json.dumps(reordered) != json.dumps(example_manifest)
        )  # naive dumps differ → reorder actually did something
        assert canonical_json(reordered) == canonical_json(example_manifest)

    def test_bundle_hash_identical_across_orderings(self, example_manifest):
        reordered = _reorder_keys(example_manifest)
        assert compute_bundle_hash(reordered) == compute_bundle_hash(
            example_manifest
        )

    def test_any_field_change_changes_hash(self, example_manifest):
        base = compute_bundle_hash(example_manifest)
        for mutate in (
            lambda d: d["config"].__setitem__("rev", "B"),
            lambda d: d["massProperties"].__setitem__("totalMass_kg", 42.6),
            lambda d: d["components"][0]["cg_m_B"].__setitem__(0, 1.6),
            lambda d: d["frame"].__setitem__("icdRev", 2),
            lambda d: d["propulsion"][0].__setitem__("ignitionTime_s", 0.1),
        ):
            changed = copy.deepcopy(example_manifest)
            mutate(changed)
            assert compute_bundle_hash(changed) != base

    def test_bundle_hash_excludes_bundle_hash_field(self, example_manifest):
        base = compute_bundle_hash(example_manifest)
        stamped = copy.deepcopy(example_manifest)
        stamped["bundle"]["bundleHash"] = base
        # Hash is computed over the manifest with bundleHash nulled, so
        # stamping the hash into the manifest doesn't change the hash —
        # that's what makes verification possible.
        assert compute_bundle_hash(stamped) == base

    def test_compute_bundle_hash_does_not_mutate_input(self, example_manifest):
        stamped = copy.deepcopy(example_manifest)
        stamped["bundle"]["bundleHash"] = _SHA_A
        before = copy.deepcopy(stamped)
        compute_bundle_hash(stamped)
        assert stamped == before

    def test_canonical_json_rejects_nan(self):
        with pytest.raises(ValueError):
            canonical_json({"x": float("nan")})

    def test_hash_stable_through_model_round_trip(self, example_manifest):
        """Validate → dump must hash identically to the raw dict —
        otherwise ASTRA and CITADEL (which mirrors the models) would
        disagree on the bundleHash of the same manifest."""
        m = Manifest.model_validate(example_manifest)
        assert compute_bundle_hash(manifest_to_dict(m)) == compute_bundle_hash(
            example_manifest
        )


# ── Naming helpers ──────────────────────────────────────────────────

class TestNamingHelpers:
    def test_sha256_bytes_known_vector(self):
        assert sha256_bytes(b"") == (
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        )

    def test_bundle_dirname_format(self):
        h = sha256_bytes(b"bundle")
        name = bundle_dirname("WS-CFG-P000001-A", "A", h)
        assert name == f"WS-CFG-P000001-A_A_{h[:8]}"

    def test_artifact_filename_all_suffixes(self):
        for suffix in ARTIFACT_SUFFIXES:
            assert artifact_filename(_SHA_A, suffix) == f"{_SHA_A}.{suffix}"
        assert ARTIFACT_SUFFIXES == (
            "massprops.yaml", "motor.json", "aero.json", "mesh.glb",
        )

    def test_artifact_filename_rejects_unknown_suffix(self):
        with pytest.raises(ValueError):
            artifact_filename(_SHA_A, "thrust.csv")
