"""§8 Configurations tracker — endpoint tests with HAROLD mocked via
respx (same pattern as tests/test_engineering_motors.py).

Proves: create validates BEFORE touching HAROLD (unknown WPN /
missing mass / OML↔aero mismatch / two-OML ⇒ 422 with structured
errors and no HAROLD call), the parallel-axis roll-up matches a
hand-computed two-mass case exactly, revision bump keeps the base
index and never mutates prior revisions, clone allocates a NEW CFG
WPN, the diff is structured, persistence failure releases the WPN,
HAROLD down ⇒ 503.
"""
from __future__ import annotations

import hashlib

import httpx
import pytest
import respx

from app.config import settings
from app.models.catalog import (
    CatalogPart, PartClass, Supplier, SupplierDocument, SupplierDocumentType,
)
from app.models.engineering_aero import AeroDeck, AeroDeckRevision
from app.models.engineering_config import (  # noqa: F401 — populates Base.metadata
    ConfigBundleExport, VehicleConfig, VehicleConfigRevision,
)
from app.models.engineering_frame import FrameIcd  # noqa: F401 — populates Base.metadata before create_all
from app.models.engineering_motor import Motor, MotorRevision

_BASE = "http://host.docker.internal:8030"
_PREFIX = f"{_BASE}/api/tools/wardstone-harold"

CONFIGS = "/api/v1/engineering/configs"

OML_WPN = "WS-FH-P000010-A"
PART_X = "WS-FH-P000011-A"
PART_Y = "WS-FH-P000012-A"


@pytest.fixture(autouse=True)
def _pin_settings(monkeypatch):
    monkeypatch.setattr(settings, "HAROLD_BASE_URL", _BASE)
    monkeypatch.setattr(settings, "HAROLD_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(settings, "HAROLD_INTEGRATION_ENABLED", True)


# ── HAROLD mock helpers ─────────────────────────────────────────────

def _ledger_entry(index: int, rev: str = "A") -> dict:
    return {
        "id": index,
        "wpn": f"WS-CFG-P{index:06d}-{rev}",
        "system_code": "CFG",
        "part_number_int": index,
        "revision": rev,
        "status": "active",
    }


def _mock_system_code() -> respx.Route:
    return respx.post(f"{_PREFIX}/system-codes").mock(
        return_value=httpx.Response(200, json={
            "code": "CFG", "name": "Vehicle Configurations",
            "category": "engineering", "description": "x", "created": False,
        }),
    )


def _mock_issue(index: int = 1) -> respx.Route:
    return respx.post(f"{_PREFIX}/wpn/issue").mock(
        return_value=httpx.Response(201, json=_ledger_entry(index)),
    )


def _mock_record_use(wpn: str) -> respx.Route:
    return respx.patch(f"{_PREFIX}/wpn/{wpn}").mock(
        return_value=httpx.Response(200, json=_ledger_entry(1)),
    )


def _mock_revise(index: int, rev: str) -> respx.Route:
    base = f"WS-CFG-P{index:06d}-A"
    return respx.post(f"{_PREFIX}/wpn/{base}/revise").mock(
        return_value=httpx.Response(201, json=_ledger_entry(index, rev)),
    )


# ── Catalog / engineering fixtures ──────────────────────────────────

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


def make_part(
    db_session, supplier, user, tmp_path, *,
    wpn: str,
    name: str,
    mass: float | None,
    cg: tuple | None = (0.0, 0.0, 0.0),
    inertia: tuple = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0),
    yaml_text: str | None = None,
) -> CatalogPart:
    """Catalog part with a §6 YAML supplier document on disk."""
    text = yaml_text or f"# CITADEL mass props\nwpn: {wpn}\nmass_kg: {mass}\n"
    content = text.encode("utf-8")
    path = tmp_path / f"{wpn}.yaml"
    path.write_bytes(content)
    doc = SupplierDocument(
        supplier_id=supplier.id,
        title=f"{wpn} mass props",
        original_filename=f"{wpn}.yaml",
        document_type=SupplierDocumentType.YAML,
        file_path=str(path),
        file_size_bytes=len(content),
        sha256=hashlib.sha256(content).hexdigest(),
        mime_type="application/yaml",
        uploaded_by_id=user.id,
    )
    db_session.add(doc)
    db_session.flush()
    cx, cy, cz = cg if cg is not None else (None, None, None)
    ixx, iyy, izz, ixy, ixz, iyz = inertia
    part = CatalogPart(
        supplier_id=supplier.id,
        part_number=wpn,
        name=name,
        part_class=PartClass.STRUCTURAL_MEMBER,
        internal_part_number=wpn,
        mass_kg=mass,
        center_of_mass_x=cx, center_of_mass_y=cy, center_of_mass_z=cz,
        ixx=ixx, iyy=iyy, izz=izz, ixy=ixy, ixz=ixz, iyz=iyz,
        source_document_id=doc.id,
        created_by_id=user.id,
    )
    db_session.add(part)
    db_session.commit()
    db_session.refresh(part)
    return part


@pytest.fixture()
def two_mass_parts(db_session, supplier, test_user, tmp_path):
    """Hand-computable BOM: 2 kg at +x and 2 kg at −x, zero local
    inertia. Total 4 kg, CG (0,0,0), Iyy = Izz = Σ m·d² = 4, Ixx = 0."""
    px = make_part(
        db_session, supplier, test_user, tmp_path,
        wpn=PART_X, name="Mass +x", mass=2.0, cg=(1.0, 0.0, 0.0),
    )
    py = make_part(
        db_session, supplier, test_user, tmp_path,
        wpn=PART_Y, name="Mass -x", mass=2.0, cg=(-1.0, 0.0, 0.0),
    )
    return px, py


@pytest.fixture()
def oml_part(db_session, supplier, test_user, tmp_path) -> CatalogPart:
    return make_part(
        db_session, supplier, test_user, tmp_path,
        wpn=OML_WPN, name="OML shell", mass=1.0, cg=(0.5, 0.0, 0.0),
    )


def make_motor(db_session, user, *, index=1, quality="excellent") -> MotorRevision:
    wpn = f"WS-MTR-P{index:06d}-A"
    artifact = {
        "schema": "astra-motor-artifact/1.0",
        "MotorTime_s": [0.0, 1.0],
        "Thrust_N": [500.0, 0.0],
        "TotalImpulse_Ns": 490.0,
        "qualityTier": quality,
        "provenance": {"origin": "design", "wpn": wpn},
    }
    import json
    sha = hashlib.sha256(
        json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    motor = Motor(
        wpn=wpn, base_index=index, name=f"TestMotor{index}",
        created_by_id=user.id,
    )
    rev = MotorRevision(
        motor=motor, wpn=wpn, rev_letter="A", origin="design",
        artifact=artifact, artifact_sha256=sha, quality_tier=quality,
        created_by_id=user.id,
    )
    db_session_add_commit(db_session, motor, rev)
    return rev


def make_aero_deck(db_session, user, *, oml_wpn=OML_WPN, index=1) -> AeroDeckRevision:
    wpn_full = f"WS-AER-P{index:06d}-A"
    base = f"WS-AER-P{index:06d}"
    deck = {
        "schema": "astra-aero-deck/1.0",
        "omlWpn": oml_wpn,
        "Sref_m2": 0.01,
        "Lref_m": 0.1,
        "refPoint_m_B": [0.0, 0.0, 0.0],
        "validityEnvelope": {
            "machRange": [0.1, 2.0],
            "alphaRange_deg": [-10.0, 10.0],
            "betaRange_deg": [-5.0, 5.0],
        },
    }
    import json
    sha = hashlib.sha256(
        json.dumps(deck, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    deck_row = AeroDeck(
        wpn=base, base_index=index, name=f"TestDeck{index}",
        oml_wpn=oml_wpn, created_by_id=user.id,
    )
    rev = AeroDeckRevision(
        deck_parent=deck_row, wpn=wpn_full, rev_letter="A",
        source_filenames=[], source_sha256s=[],
        deck=deck, deck_sha256=sha, sref_m2=0.01, lref_m=0.1,
        defaulted_fields=[], warnings=[], created_by_id=user.id,
    )
    db_session_add_commit(db_session, deck_row, rev)
    return rev


def db_session_add_commit(db_session, *rows):
    for r in rows:
        db_session.add(r)
    db_session.commit()
    for r in rows:
        db_session.refresh(r)


def _two_mass_body(**overrides) -> dict:
    body = {
        "name": "Test Vehicle",
        "description": "two-mass test config",
        "components": [
            {"role": "structure", "wpn": PART_X},
            {"role": "ballast", "wpn": PART_Y},
        ],
    }
    body.update(overrides)
    return body


# ═════════════════════════════════════════════════════════════════
#  Create — HAROLD WPN verbatim + roll-up correctness
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_create_config_with_harold_wpn(client, auth_headers, db_session,
                                       two_mass_parts):
    issue_route = _mock_issue(1)
    _mock_system_code()
    _mock_record_use("WS-CFG-P000001-A")
    r = client.post(CONFIGS, json=_two_mass_body(), headers=auth_headers)
    assert r.status_code == 201, r.text
    body = r.json()

    # WPN is HAROLD's ledger response VERBATIM — never self-assigned.
    assert body["wpn"] == "WS-CFG-P000001-A"
    assert body["config_wpn"] == "WS-CFG-P000001"
    assert body["rev_letter"] == "A"
    assert issue_route.call_count == 1

    # Hand-computed parallel-axis roll-up: 2 kg at ±x, zero local
    # inertia ⇒ M = 4, CG = origin, Iyy = Izz = 2·1² + 2·1² = 4, Ixx = 0.
    rollup = body["rollup"]
    assert rollup["totalMass_kg"] == 4.0
    assert rollup["cg_m_B"] == [0.0, 0.0, 0.0]
    inertia = rollup["inertia_kgm2_B"]
    assert inertia[0][0] == 0.0   # Ixx
    assert inertia[1][1] == 4.0   # Iyy — exact parallel-axis value
    assert inertia[2][2] == 4.0   # Izz
    assert inertia[0][1] == 0.0 and inertia[0][2] == 0.0
    assert rollup["referencePoint_m_B"] == [0.0, 0.0, 0.0]
    assert rollup["method"] == "parallel_axis"

    cfg = db_session.query(VehicleConfig).one()
    assert cfg.wpn == "WS-CFG-P000001"
    assert cfg.base_index == 1
    assert cfg.system_code == "CFG"
    assert cfg.active_revision_id is not None
    rev = db_session.query(VehicleConfigRevision).one()
    assert rev.wpn == "WS-CFG-P000001-A"
    assert rev.frame_icd_id is not None and rev.frame_icd_rev == 1
    # Component names defaulted from the catalog.
    assert {c["name"] for c in rev.components} == {"Mass +x", "Mass -x"}


# ═════════════════════════════════════════════════════════════════
#  Save-time validation — 422 BEFORE any HAROLD call
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_create_unknown_wpn_422_before_harold(client, auth_headers,
                                              db_session, two_mass_parts):
    # No HAROLD routes mocked: any HTTP attempt would error loudly.
    body = _two_mass_body()
    body["components"].append({"role": "other", "wpn": "WS-FH-P999999-A"})
    r = client.post(CONFIGS, json=body, headers=auth_headers)
    assert r.status_code == 422, r.text
    errors = r.json()["detail"]["errors"]
    assert any(
        e["code"] == "unknown_component_wpn"
        and e["wpn"] == "WS-FH-P999999-A"
        for e in errors
    )
    assert db_session.query(VehicleConfig).count() == 0


@respx.mock
def test_create_missing_mass_422_names_part(client, auth_headers,
                                            db_session, supplier, test_user,
                                            tmp_path):
    make_part(
        db_session, supplier, test_user, tmp_path,
        wpn=PART_X, name="No-mass part", mass=None, cg=(0.0, 0.0, 0.0),
    )
    r = client.post(CONFIGS, json={
        "name": "Bad",
        "components": [{"role": "structure", "wpn": PART_X}],
    }, headers=auth_headers)
    assert r.status_code == 422, r.text
    errors = r.json()["detail"]["errors"]
    match = [e for e in errors if e["code"] == "rollup_not_computable"]
    assert match and match[0]["wpn"] == PART_X
    assert PART_X in match[0]["message"]


@respx.mock
def test_oml_aero_mismatch_422_lists_both(client, auth_headers, db_session,
                                          two_mass_parts, oml_part, test_user):
    # Deck is for a DIFFERENT OML than the config's 'oml' component.
    make_aero_deck(db_session, test_user, oml_wpn="WS-FH-P000099-A")
    body = _two_mass_body()
    body["components"].append({"role": "oml", "wpn": OML_WPN})
    body["aero_binding"] = {"wpn": "WS-AER-P000001", "rev_letter": "A"}
    r = client.post(CONFIGS, json=body, headers=auth_headers)
    assert r.status_code == 422, r.text
    errors = r.json()["detail"]["errors"]
    match = [e for e in errors if e["code"] == "oml_aero_mismatch"]
    assert match
    assert match[0]["deck_oml_wpn"] == "WS-FH-P000099-A"
    assert match[0]["component_oml_wpn"] == OML_WPN


@respx.mock
def test_two_oml_components_422(client, auth_headers, db_session,
                                two_mass_parts, oml_part, test_user):
    make_aero_deck(db_session, test_user)
    body = _two_mass_body()
    # Both X and the OML part claim role 'oml'.
    body["components"] = [
        {"role": "oml", "wpn": PART_X},
        {"role": "oml", "wpn": OML_WPN},
        {"role": "ballast", "wpn": PART_Y},
    ]
    body["aero_binding"] = {"wpn": "WS-AER-P000001", "rev_letter": "A"}
    r = client.post(CONFIGS, json=body, headers=auth_headers)
    assert r.status_code == 422, r.text
    errors = r.json()["detail"]["errors"]
    assert any(e["code"] == "multiple_oml_components" for e in errors)


@respx.mock
def test_unknown_motor_in_stage_map_422(client, auth_headers, db_session,
                                        two_mass_parts):
    body = _two_mass_body(stage_map=[{
        "stageNum": 1, "motorWpn": "WS-MTR-P000042-A",
        "motorRevLetter": "A", "ignitionTime_s": 0.0,
        "thrustAxis_B": [1.0, 0.0, 0.0],
    }])
    r = client.post(CONFIGS, json=body, headers=auth_headers)
    assert r.status_code == 422, r.text
    errors = r.json()["detail"]["errors"]
    assert any(e["code"] == "unknown_motor" for e in errors)


def test_role_is_required_and_closed_set(client, auth_headers, two_mass_parts):
    body = _two_mass_body()
    body["components"][0].pop("role")
    assert client.post(
        CONFIGS, json=body, headers=auth_headers).status_code == 422
    body = _two_mass_body()
    body["components"][0]["role"] = "warp_core"
    assert client.post(
        CONFIGS, json=body, headers=auth_headers).status_code == 422


# ═════════════════════════════════════════════════════════════════
#  Revisions — immutable, index stable
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_revision_bump_immutable_index_stable(client, auth_headers,
                                              db_session, two_mass_parts):
    issue_route = _mock_issue(1)
    _mock_system_code()
    _mock_record_use("WS-CFG-P000001-A")
    assert client.post(
        CONFIGS, json=_two_mass_body(), headers=auth_headers,
    ).status_code == 201

    revise_route = _mock_revise(1, "B")
    _mock_record_use("WS-CFG-P000001-B")
    body = _two_mass_body()
    # Move part X to a new placement (translation +0.5 in x).
    body["components"][0]["placement"] = [
        [1.0, 0.0, 0.0, 0.5],
        [0.0, 1.0, 0.0, 0.0],
        [0.0, 0.0, 1.0, 0.0],
        [0.0, 0.0, 0.0, 1.0],
    ]
    r = client.post(
        f"{CONFIGS}/WS-CFG-P000001/revisions", json=body,
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["wpn"] == "WS-CFG-P000001-B"
    assert r.json()["rev_letter"] == "B"
    assert revise_route.called
    assert issue_route.call_count == 1  # no second allocation — index stable

    assert db_session.query(VehicleConfig).count() == 1
    revs = db_session.query(VehicleConfigRevision).order_by(
        VehicleConfigRevision.id).all()
    assert [x.rev_letter for x in revs] == ["A", "B"]
    # Rev A is IMMUTABLE — its components are untouched by the bump.
    rev_a = revs[0]
    assert all(c.get("placement") is None for c in rev_a.components)
    # New rollup reflects the moved mass: CG x = (2·1.5 + 2·(−1)) / 4.
    assert r.json()["rollup"]["cg_m_B"][0] == pytest.approx(0.25)


def test_revisions_have_no_mutation_routes():
    from app.main import app

    for route in app.routes:
        path = getattr(route, "path", "")
        if "/engineering/configs" not in path:
            continue
        methods = set(getattr(route, "methods", set()) or set())
        if "/revisions/{rev}" in path:
            assert methods <= {"GET", "HEAD"}, (
                f"persisted revisions are immutable — {path} exposes {methods}"
            )
        assert "DELETE" not in methods, f"unexpected DELETE on {path}"

    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/v1/engineering/configs" in paths
    assert "/api/v1/engineering/configs/{wpn}:clone" in paths
    assert "/api/v1/engineering/configs/{wpn}/{rev}:exportBundle" in paths
    assert "/api/v1/engineering/configs/{wpn}/{rev}/bundles" in paths


# ═════════════════════════════════════════════════════════════════
#  Clone — NEW identity
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_clone_allocates_new_wpn(client, auth_headers, db_session,
                                 two_mass_parts):
    _mock_system_code()
    issue_route = _mock_issue(1)
    _mock_record_use("WS-CFG-P000001-A")
    assert client.post(
        CONFIGS, json=_two_mass_body(), headers=auth_headers,
    ).status_code == 201

    issue_route.mock(
        return_value=httpx.Response(201, json=_ledger_entry(2)),
    )
    _mock_record_use("WS-CFG-P000002-A")
    r = client.post(
        f"{CONFIGS}/WS-CFG-P000001:clone",
        json={"name": "Cloned Vehicle"},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["wpn"] == "WS-CFG-P000002-A"   # fresh allocation
    assert body["config_wpn"] == "WS-CFG-P000002"
    assert body["name"] == "Cloned Vehicle"
    assert issue_route.call_count == 2

    clones = db_session.query(VehicleConfig).order_by(VehicleConfig.id).all()
    assert [c.wpn for c in clones] == ["WS-CFG-P000001", "WS-CFG-P000002"]
    src_rev = clones[0].revisions[-1]
    new_rev = clones[1].revisions[-1]
    assert new_rev.components == src_rev.components
    assert new_rev.rollup == src_rev.rollup


# ═════════════════════════════════════════════════════════════════
#  Diff
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_diff_detects_add_remove_and_change(client, auth_headers, db_session,
                                            two_mass_parts, oml_part):
    _mock_system_code()
    _mock_issue(1)
    _mock_record_use("WS-CFG-P000001-A")
    assert client.post(
        CONFIGS, json=_two_mass_body(), headers=auth_headers,
    ).status_code == 201

    _mock_revise(1, "B")
    _mock_record_use("WS-CFG-P000001-B")
    body = {
        "name": "ignored",
        "components": [
            # X kept but placement changed; Y removed; OML added.
            {"role": "structure", "wpn": PART_X, "placement": [
                [1.0, 0.0, 0.0, 0.1],
                [0.0, 1.0, 0.0, 0.0],
                [0.0, 0.0, 1.0, 0.0],
                [0.0, 0.0, 0.0, 1.0],
            ]},
            {"role": "oml", "wpn": OML_WPN},
        ],
    }
    assert client.post(
        f"{CONFIGS}/WS-CFG-P000001/revisions", json=body,
        headers=auth_headers,
    ).status_code == 201, "revision B failed"

    r = client.get(
        f"{CONFIGS}/WS-CFG-P000001/diff?from=A&to=B", headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    diff = r.json()
    assert diff["from_rev"] == "A" and diff["to_rev"] == "B"
    assert [c["wpn"] for c in diff["components"]["added"]] == [OML_WPN]
    assert [c["wpn"] for c in diff["components"]["removed"]] == [PART_Y]
    changed = diff["components"]["changed"]
    assert len(changed) == 1 and changed[0]["wpn"] == PART_X
    assert "placement" in changed[0]["fields"]
    assert diff["aero_binding"] is None
    # Mass dropped by 2 kg (Y removed) and rose 1 kg (OML) ⇒ −1 kg.
    assert diff["rollup_delta"]["totalMass_kg"] == pytest.approx(-1.0)


# ═════════════════════════════════════════════════════════════════
#  Active revision
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_active_revision_switch(client, auth_headers, db_session,
                                two_mass_parts):
    _mock_system_code()
    _mock_issue(1)
    _mock_record_use("WS-CFG-P000001-A")
    assert client.post(
        CONFIGS, json=_two_mass_body(), headers=auth_headers,
    ).status_code == 201
    _mock_revise(1, "B")
    _mock_record_use("WS-CFG-P000001-B")
    assert client.post(
        f"{CONFIGS}/WS-CFG-P000001/revisions", json=_two_mass_body(),
        headers=auth_headers,
    ).status_code == 201

    r = client.put(
        f"{CONFIGS}/WS-CFG-P000001/active-revision",
        json={"rev_letter": "A"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["current_rev"] == "A"

    # Unknown letter → 404.
    assert client.put(
        f"{CONFIGS}/WS-CFG-P000001/active-revision",
        json={"rev_letter": "Q"},
        headers=auth_headers,
    ).status_code == 404


# ═════════════════════════════════════════════════════════════════
#  List / detail / revision detail
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_list_and_detail_endpoints(client, auth_headers, two_mass_parts):
    _mock_system_code()
    _mock_issue(1)
    _mock_record_use("WS-CFG-P000001-A")
    assert client.post(
        CONFIGS, json=_two_mass_body(), headers=auth_headers,
    ).status_code == 201

    r = client.get(CONFIGS, headers=auth_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    item = items[0]
    assert item["wpn"] == "WS-CFG-P000001"
    assert item["current_rev"] == "A"
    assert item["revision_count"] == 1
    assert item["total_mass_kg"] == 4.0
    assert item["component_count"] == 2

    assert client.get(
        f"{CONFIGS}?q=Vehicle", headers=auth_headers).json()
    assert client.get(
        f"{CONFIGS}?q=nomatch", headers=auth_headers).json() == []

    r = client.get(f"{CONFIGS}/WS-CFG-P000001", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()["revisions"]) == 1

    # Flight card: full resolved revision incl. rollup.
    r = client.get(
        f"{CONFIGS}/WS-CFG-P000001/revisions/A", headers=auth_headers,
    )
    assert r.status_code == 200
    card = r.json()
    assert card["wpn"] == "WS-CFG-P000001-A"
    assert card["rollup"]["totalMass_kg"] == 4.0
    assert card["frame_icd_rev"] == 1
    assert len(card["components"]) == 2

    assert client.get(
        f"{CONFIGS}/WS-CFG-P000099", headers=auth_headers,
    ).status_code == 404
    assert client.get(
        f"{CONFIGS}/WS-CFG-P000001/revisions/Z", headers=auth_headers,
    ).status_code == 404


# ═════════════════════════════════════════════════════════════════
#  Failure semantics — gaplessness + 503
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_persistence_failure_releases_wpn(client, auth_headers, db_session,
                                          two_mass_parts, monkeypatch):
    _mock_system_code()
    _mock_issue(7)
    delete_route = respx.delete(f"{_PREFIX}/wpn/WS-CFG-P000007-A").mock(
        return_value=httpx.Response(200, json={
            "deleted_wpn": "WS-CFG-P000007-A",
            "reclaimed": True, "new_next_index": 7,
        }),
    )

    import app.routers.engineering_configs as configs_router

    def _boom(*a, **kw):
        raise RuntimeError("revision write exploded")

    monkeypatch.setattr(configs_router, "_make_revision_row", _boom)

    with pytest.raises(RuntimeError, match="revision write exploded"):
        client.post(CONFIGS, json=_two_mass_body(), headers=auth_headers)

    # The freshly issued WPN was handed back — sequence stays gapless.
    assert delete_route.called
    assert db_session.query(VehicleConfig).count() == 0
    assert db_session.query(VehicleConfigRevision).count() == 0


@respx.mock
def test_harold_down_yields_503_on_create(client, auth_headers, db_session,
                                          two_mass_parts):
    respx.post(f"{_PREFIX}/system-codes").mock(
        side_effect=httpx.ConnectError("connection refused"),
    )
    r = client.post(CONFIGS, json=_two_mass_body(), headers=auth_headers)
    assert r.status_code == 503
    assert "HAROLD" in r.json()["detail"]
    assert db_session.query(VehicleConfig).count() == 0


def test_harold_flag_off_yields_503(client, auth_headers, two_mass_parts,
                                    monkeypatch):
    monkeypatch.setattr(settings, "HAROLD_INTEGRATION_ENABLED", False)
    r = client.post(CONFIGS, json=_two_mass_body(), headers=auth_headers)
    assert r.status_code == 503
    assert "HAROLD" in r.json()["detail"]


# ═════════════════════════════════════════════════════════════════
#  RBAC
# ═════════════════════════════════════════════════════════════════


def test_writes_require_req_eng_plus(client, db_session, two_mass_parts):
    from tests.conftest import make_user

    _user, headers = make_user(db_session, "stakeholder")
    r = client.post(CONFIGS, json=_two_mass_body(), headers=headers)
    assert r.status_code == 403


def test_reads_require_auth(client):
    assert client.get(CONFIGS).status_code in (401, 403)
