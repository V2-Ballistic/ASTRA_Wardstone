"""§9 CITADEL bundle export — endpoint tests with HAROLD mocked via
respx.

Proves: the exported manifest validates against
``bundle_schema.Manifest``, dependencies pin EVERY artifact
(components + aero + motors), artifact files exist on disk with
content-matching sha256 names, identical YAML bytes used by two
components are stored ONCE (dedup), **export twice ⇒ same
bundle_hash** (volatile fields normalized out of the hash) with the
recorded row idempotently reused per the
UNIQUE(config_wpn, rev_letter, bundle_hash) constraint, the zip is
downloadable and history is retrievable WITHOUT re-export, a missing
§6 YAML 422s naming the part, and HAROLD-down only degrades
provenance (never fails the export).
"""
from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile

import httpx
import pytest
import respx

from app.config import settings
from app.models.engineering_config import (
    ConfigBundleExport, VehicleConfig, VehicleConfigRevision,  # noqa: F401
)
from app.services.engineering.bundle_export import (
    compute_deterministic_bundle_hash,
)
from app.services.engineering.bundle_schema import Manifest

from tests.test_engineering_configs import (
    OML_WPN,
    PART_X,
    PART_Y,
    _ledger_entry,
    make_aero_deck,
    make_motor,
    make_part,
)
from app.models.catalog import Supplier

_BASE = "http://host.docker.internal:8030"
_PREFIX = f"{_BASE}/api/tools/wardstone-harold"

CONFIGS = "/api/v1/engineering/configs"
CFG_BASE = "WS-CFG-P000001"

#: Two components share these EXACT bytes → one content-addressed file.
_SHARED_YAML = "# CITADEL mass props\nshared: true\nmass_kg: 2.0\n"


@pytest.fixture(autouse=True)
def _pin_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "HAROLD_BASE_URL", _BASE)
    monkeypatch.setattr(settings, "HAROLD_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(settings, "HAROLD_INTEGRATION_ENABLED", True)
    monkeypatch.setenv("CITADEL_BUNDLE_DIR", str(tmp_path / "bundles"))


@pytest.fixture()
def supplier(db_session, test_user) -> Supplier:
    s = Supplier(
        name="Wardstone (test)", is_in_house=True,
        created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture()
def seeded_world(db_session, supplier, test_user, tmp_path):
    """Catalog parts (X/Y share identical YAML bytes; OML distinct),
    an aero deck bound to the OML, and an 'excellent' motor."""
    px = make_part(
        db_session, supplier, test_user, tmp_path,
        wpn=PART_X, name="Mass +x", mass=2.0, cg=(1.0, 0.0, 0.0),
        yaml_text=_SHARED_YAML,
    )
    py = make_part(
        db_session, supplier, test_user, tmp_path,
        wpn=PART_Y, name="Mass -x", mass=2.0, cg=(-1.0, 0.0, 0.0),
        yaml_text=_SHARED_YAML,
    )
    poml = make_part(
        db_session, supplier, test_user, tmp_path,
        wpn=OML_WPN, name="OML shell", mass=1.0, cg=(0.5, 0.0, 0.0),
    )
    deck_rev = make_aero_deck(db_session, test_user, oml_wpn=OML_WPN)
    motor_rev = make_motor(db_session, test_user, quality="excellent")
    return {"parts": (px, py, poml), "deck_rev": deck_rev,
            "motor_rev": motor_rev}


def _full_body() -> dict:
    return {
        "name": "Flight Vehicle 1",
        "description": "full export test config",
        "components": [
            {"role": "structure", "wpn": PART_X},
            {"role": "ballast", "wpn": PART_Y},
            {"role": "oml", "wpn": OML_WPN},
        ],
        "aero_binding": {"wpn": "WS-AER-P000001", "rev_letter": "A"},
        "stage_map": [{
            "stageNum": 1,
            "motorWpn": "WS-MTR-P000001-A",
            "motorRevLetter": "A",
            "ignitionTime_s": 0.0,
            "thrustAxis_B": [1.0, 0.0, 0.0],
        }],
        "astra_baseline_id": None,
    }


def _mock_harold_create():
    respx.post(f"{_PREFIX}/system-codes").mock(
        return_value=httpx.Response(200, json={
            "code": "CFG", "name": "Vehicle Configurations",
            "category": "engineering", "description": "x", "created": False,
        }),
    )
    respx.post(f"{_PREFIX}/wpn/issue").mock(
        return_value=httpx.Response(201, json=_ledger_entry(1)),
    )
    respx.patch(f"{_PREFIX}/wpn/WS-CFG-P000001-A").mock(
        return_value=httpx.Response(200, json=_ledger_entry(1)),
    )


def _mock_ledger():
    return respx.get(url__regex=r".*/wardstone-harold/ledger.*").mock(
        return_value=httpx.Response(200, json={
            "items": [_ledger_entry(1)], "total": 1, "skip": 0, "limit": 200,
        }),
    )


def _create_config(client, auth_headers):
    r = client.post(CONFIGS, json=_full_body(), headers=auth_headers)
    assert r.status_code == 201, r.text
    return r.json()


def _export(client, auth_headers, rev="A"):
    return client.post(
        f"{CONFIGS}/{CFG_BASE}/{rev}:exportBundle", headers=auth_headers,
    )


# ═════════════════════════════════════════════════════════════════
#  Manifest + artifacts + dedup
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_export_manifest_artifacts_and_dedup(client, auth_headers,
                                             db_session, seeded_world,
                                             tmp_path):
    _mock_harold_create()
    _mock_ledger()
    _create_config(client, auth_headers)

    r = _export(client, auth_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["bundle_hash"]) == 64
    assert body["reused"] is False

    # Artifact count: X+Y share identical YAML bytes (stored ONCE),
    # OML YAML, aero deck JSON, motor curve JSON ⇒ 4 unique artifacts.
    assert body["artifact_count"] == 4

    manifest = body["manifest"]
    # The manifest validates against THE shared schema contract.
    parsed = Manifest.model_validate(manifest)
    assert parsed.schema_ == "citadel-config-bundle/1.0"
    assert manifest["bundle"]["bundleHash"] == body["bundle_hash"]

    # Config / frame blocks.
    assert manifest["config"]["wpn"] == CFG_BASE
    assert manifest["config"]["rev"] == "A"
    assert manifest["frame"]["icdId"] == "citadel-vehicle-body-frame"
    assert manifest["frame"]["icdRev"] == 1
    assert manifest["frame"]["datum"] == "OML_nose_tip"

    # massProperties == the revision's STORED rollup.
    rev_row = db_session.query(VehicleConfigRevision).one()
    assert manifest["massProperties"]["totalMass_kg"] == \
        rev_row.rollup["totalMass_kg"]
    assert manifest["massProperties"]["cg_m_B"] == rev_row.rollup["cg_m_B"]

    # Components carry catalog mass/cg + artifact refs (CADPORT YAML).
    comps = {c["wpn"]: c for c in manifest["components"]}
    assert set(comps) == {PART_X, PART_Y, OML_WPN}
    assert comps[PART_X]["mass_kg"] == 2.0
    assert comps[PART_X]["cg_m_B"] == [1.0, 0.0, 0.0]
    assert comps[PART_X]["artifact"]["type"] == "mass_props_yaml"
    assert comps[PART_X]["artifact"]["sourceSystem"] == "CADPORT"
    # Dedup: X and Y reference the SAME content-addressed file.
    assert comps[PART_X]["artifact"]["file"] == comps[PART_Y]["artifact"]["file"]

    # Aero + propulsion blocks.
    assert manifest["aero"]["omlWpn"] == OML_WPN
    assert manifest["aero"]["artifact"]["sourceSystem"] == "AstraAero"
    assert manifest["propulsion"][0]["motorWpn"] == "WS-MTR-P000001-A"
    assert manifest["propulsion"][0]["artifact"]["type"] == "motor_curve"
    assert manifest["propulsion"][0]["artifact"]["qualityTier"] == "excellent"
    assert manifest["propulsion"][0]["artifact"]["origin"] == "design"
    # All motors excellent ⇒ HiFi.
    assert manifest["recommendedFidelity"] == "HiFi"

    # Dependencies pin EVERY artifact: 3 components + aero + motor.
    deps = {(d["wpn"], d["rev"]): d["sha256"] for d in manifest["dependencies"]}
    assert set(deps) == {
        (PART_X, "A"), (PART_Y, "A"), (OML_WPN, "A"),
        ("WS-AER-P000001", "A"), ("WS-MTR-P000001-A", "A"),
    }
    # X and Y pin the same sha (identical bytes), distinct WPNs.
    assert deps[(PART_X, "A")] == deps[(PART_Y, "A")]

    # provenance: HAROLD ledger summary + astra exporter stamp.
    assert manifest["provenance"]["harold"]["total"] == 1
    assert manifest["provenance"]["astra"]["exportedBy"] == "testadmin"

    # On-disk bundle: manifest.json + content-addressed artifacts whose
    # sha256 matches their bytes.
    bundle_dir = tmp_path / "bundles" / body["bundle_dirname"]
    assert (bundle_dir / "manifest.json").is_file()
    artifact_files = sorted((bundle_dir / "artifacts").iterdir())
    assert len(artifact_files) == 4  # dedup on disk too
    for f in artifact_files:
        claimed = f.name.split(".", 1)[0]
        assert hashlib.sha256(f.read_bytes()).hexdigest() == claimed
    # Every manifest artifact ref resolves to a file on disk.
    refs = [c["artifact"]["file"] for c in manifest["components"]]
    refs.append(manifest["aero"]["artifact"]["file"])
    refs.append(manifest["propulsion"][0]["artifact"]["file"])
    for ref in refs:
        assert (bundle_dir / ref).is_file(), f"missing artifact {ref}"


# ═════════════════════════════════════════════════════════════════
#  Determinism — the load-bearing property
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_export_twice_same_bundle_hash(client, auth_headers, db_session,
                                       seeded_world):
    _mock_harold_create()
    _mock_ledger()
    _create_config(client, auth_headers)

    r1 = _export(client, auth_headers)
    r2 = _export(client, auth_headers)
    assert r1.status_code == 201 and r2.status_code == 201

    # Same revision ⇒ SAME bundleHash, even though createdUtc /
    # provenance differ between the two export attempts (those fields
    # are normalized out of the hash).
    assert r1.json()["bundle_hash"] == r2.json()["bundle_hash"]
    assert r1.json()["reused"] is False
    assert r2.json()["reused"] is True

    # UNIQUE(config_wpn, rev_letter, bundle_hash): identical content
    # is recorded once — the second export idempotently reuses the
    # row, keeping lookup-by-hash unambiguous for retrieval.
    exports = db_session.query(ConfigBundleExport).all()
    assert len(exports) == 1
    assert exports[0].bundle_hash == r1.json()["bundle_hash"]


@respx.mock
def test_deterministic_hash_normalization_rule(client, auth_headers,
                                               seeded_world):
    _mock_harold_create()
    _mock_ledger()
    _create_config(client, auth_headers)
    manifest = _export(client, auth_headers).json()["manifest"]
    stored_hash = manifest["bundle"]["bundleHash"]

    # The recorded hash is reproducible from the stored manifest.
    assert compute_deterministic_bundle_hash(manifest) == stored_hash

    # Volatile fields do NOT affect the hash …
    volatile = copy.deepcopy(manifest)
    volatile["bundle"]["id"] = "something-else"
    volatile["bundle"]["createdUtc"] = "1999-01-01T00:00:00+00:00"
    volatile["bundle"]["createdBy"] = "someone-else"
    volatile["provenance"] = {"harold": {}, "astra": {
        "baselineId": None, "exportedBy": "x", "exportedUtc": "y",
    }}
    assert compute_deterministic_bundle_hash(volatile) == stored_hash

    # … but the covered content DOES.
    for mutate in (
        lambda m: m["massProperties"].__setitem__("totalMass_kg", 99.0),
        lambda m: m["config"].__setitem__("rev", "Z"),
        lambda m: m["dependencies"][0].__setitem__("sha256", "f" * 64),
        lambda m: m["frame"].__setitem__("icdRev", 2),
    ):
        mutated = copy.deepcopy(manifest)
        mutate(mutated)
        assert compute_deterministic_bundle_hash(mutated) != stored_hash


# ═════════════════════════════════════════════════════════════════
#  History / manifest / download — WITHOUT re-export
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_history_manifest_and_zip_download(client, auth_headers,
                                           seeded_world):
    _mock_harold_create()
    _mock_ledger()
    _create_config(client, auth_headers)
    exported = _export(client, auth_headers).json()
    bundle_hash = exported["bundle_hash"]

    # History (no re-export involved).
    r = client.get(f"{CONFIGS}/{CFG_BASE}/A/bundles", headers=auth_headers)
    assert r.status_code == 200
    history = r.json()
    assert len(history) == 1
    assert history[0]["bundle_hash"] == bundle_hash
    assert history[0]["artifact_count"] == 4

    # Stored manifest, served from the DB row.
    r = client.get(
        f"{CONFIGS}/{CFG_BASE}/A/bundles/{bundle_hash}/manifest",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json() == exported["manifest"]

    # Zip download (FileResponse).
    r = client.get(
        f"{CONFIGS}/{CFG_BASE}/A/bundles/{bundle_hash}/download",
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = zf.namelist()
    assert "manifest.json" in names
    assert sum(1 for n in names if n.startswith("artifacts/")) == 4
    # Deterministic zip: fixed 1980 timestamps on every entry.
    assert all(i.date_time == (1980, 1, 1, 0, 0, 0) for i in zf.infolist())
    # The zipped manifest is the stored manifest, hash included.
    zipped = json.loads(zf.read("manifest.json"))
    assert zipped == exported["manifest"]
    assert zipped["bundle"]["bundleHash"] == bundle_hash

    # Unknown hash → 404.
    assert client.get(
        f"{CONFIGS}/{CFG_BASE}/A/bundles/{'0' * 64}/manifest",
        headers=auth_headers,
    ).status_code == 404


# ═════════════════════════════════════════════════════════════════
#  Failure paths
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_missing_yaml_file_422_names_part(client, auth_headers, db_session,
                                          seeded_world, tmp_path):
    _mock_harold_create()
    _create_config(client, auth_headers)

    # Pull part X's YAML out from under the export.
    (tmp_path / f"{PART_X}.yaml").unlink()

    r = _export(client, auth_headers)
    assert r.status_code == 422, r.text
    detail = r.json()["detail"]
    assert detail["wpn"] == PART_X
    assert PART_X in detail["message"]
    assert db_session.query(ConfigBundleExport).count() == 0


@respx.mock
def test_harold_down_export_succeeds_with_degraded_provenance(
    client, auth_headers, seeded_world,
):
    _mock_harold_create()
    _create_config(client, auth_headers)

    # Ledger unreachable at export time — provenance.harold is omitted
    # with a warning; the export itself MUST still succeed.
    respx.get(url__regex=r".*/wardstone-harold/ledger.*").mock(
        side_effect=httpx.ConnectError("connection refused"),
    )
    r = _export(client, auth_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["manifest"]["provenance"]["harold"] == {}
    assert any("HAROLD" in w for w in body["warnings"])


@respx.mock
def test_nominal_fidelity_when_motor_not_excellent(client, auth_headers,
                                                   db_session, supplier,
                                                   test_user, tmp_path):
    make_part(
        db_session, supplier, test_user, tmp_path,
        wpn=PART_X, name="Mass +x", mass=2.0, cg=(1.0, 0.0, 0.0),
    )
    make_motor(db_session, test_user, quality="workable")
    _mock_harold_create()
    _mock_ledger()
    body = {
        "name": "Nominal Vehicle",
        "components": [{"role": "structure", "wpn": PART_X}],
        "stage_map": [{
            "stageNum": 1,
            "motorWpn": "WS-MTR-P000001-A",
            "motorRevLetter": "A",
            "ignitionTime_s": 0.0,
            "thrustAxis_B": [1.0, 0.0, 0.0],
        }],
    }
    assert client.post(
        CONFIGS, json=body, headers=auth_headers).status_code == 201
    r = _export(client, auth_headers)
    assert r.status_code == 201, r.text
    assert r.json()["manifest"]["recommendedFidelity"] == "Nominal"


def test_export_requires_write_role(client, db_session, seeded_world):
    from tests.conftest import make_user

    _user, headers = make_user(db_session, "stakeholder")
    r = client.post(
        f"{CONFIGS}/{CFG_BASE}/A:exportBundle", headers=headers,
    )
    # Role gate fires before the config lookup.
    assert r.status_code == 403
