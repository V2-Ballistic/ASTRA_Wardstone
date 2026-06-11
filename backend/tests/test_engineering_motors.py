"""§5.2/§5.5 Motors API — endpoint tests with HAROLD mocked via respx
(same pattern as tests/test_harold_naming.py / test_harold_endpoints.py).

Proves: ingestCsv creates a motor whose WPN is HAROLD's ledger
response VERBATIM (never self-assigned), same-lineage re-upload bumps
the -REV but keeps the base index, persistence failure releases the
WPN (DELETE called), HAROLD-down ⇒ 503, revisions are immutable (no
mutation routes), and active-revision switching updates the catalog
entry's mass.
"""
from __future__ import annotations

import hashlib

import httpx
import pytest
import respx

from app.config import settings
from app.models.catalog import CatalogPart, Supplier
from app.models.engineering_motor import Motor, MotorRevision  # noqa: F401 — populates Base.metadata before create_all

_BASE = "http://host.docker.internal:8030"
_PREFIX = f"{_BASE}/api/tools/wardstone-harold"

MOTORS = "/api/v1/engineering/motors"


@pytest.fixture(autouse=True)
def _pin_settings(monkeypatch):
    monkeypatch.setattr(settings, "HAROLD_BASE_URL", _BASE)
    monkeypatch.setattr(settings, "HAROLD_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(settings, "HAROLD_INTEGRATION_ENABLED", True)


# ── HAROLD mock helpers ─────────────────────────────────────────────

def _ledger_entry(index: int, rev: str = "A") -> dict:
    return {
        "id": index,
        "wpn": f"WS-MTR-P{index:06d}-{rev}",
        "system_code": "MTR",
        "part_number_int": index,
        "revision": rev,
        "status": "active",
    }


def _mock_system_code() -> respx.Route:
    return respx.post(f"{_PREFIX}/system-codes").mock(
        return_value=httpx.Response(200, json={
            "code": "MTR", "name": "Solid Motors",
            "category": "engineering", "description": "x", "created": False,
        }),
    )


def _mock_issue(index: int = 1) -> respx.Route:
    return respx.post(f"{_PREFIX}/wpn/issue").mock(
        return_value=httpx.Response(201, json=_ledger_entry(index)),
    )


def _mock_precheck(stem: str = "WS01_curve") -> respx.Route:
    return respx.post(f"{_PREFIX}/filename-precheck").mock(
        return_value=httpx.Response(200, json={
            "filename": f"{stem}.csv",
            "astra_available": True,
            "is_collision": False,
            "iteration_stem": stem,
            "existing_iterations": [],
            "next_available_iteration": 1,
            "warnings": [],
            "errors": [],
        }),
    )


def _mock_record_use(wpn: str) -> respx.Route:
    return respx.patch(f"{_PREFIX}/wpn/{wpn}").mock(
        return_value=httpx.Response(200, json=_ledger_entry(1)),
    )


def _mock_revise(index: int, rev: str) -> respx.Route:
    base = f"WS-MTR-P{index:06d}-A"
    return respx.post(f"{_PREFIX}/wpn/{base}/revise").mock(
        return_value=httpx.Response(201, json=_ledger_entry(index, rev)),
    )


# ── Fixtures: CSV + design payloads ─────────────────────────────────

def _csv_bytes(grain_mass: float = 0.4) -> bytes:
    """Small consistent WS01-like 8-grain CSV."""
    lines = [f"# GrainMass_{i + 1}, {grain_mass}" for i in range(8)]
    lines.append("MotorTime_s,Thrust_N,PropMassRem_kg,Pchamber_Pa")
    m0 = 8 * grain_mass
    t_burn, dt, t_total = 1.0, 0.01, 1.2
    n = int(round(t_total / dt)) + 1
    for i in range(n):
        t = i * dt
        burning = t < t_burn
        f = 500.0 if burning else 0.0
        m = m0 * (1 - t / t_burn) if burning else 0.0
        p = 4.0e6 if burning else 0.0
        lines.append(f"{t:.4f},{f},{m:.9f},{p}")
    return "\n".join(lines).encode()


def _upload(client, headers, *, filename="WS01_curve.csv", grain_mass=0.4,
            path=f"{MOTORS}:ingestCsv"):
    return client.post(
        path,
        files={"file": (filename, _csv_bytes(grain_mass), "text/csv")},
        headers=headers,
    )


_DESIGN_INPUTS = {
    "propellant": {
        "density_kgpm3": 1750.0, "a": 6e-6, "n": 0.5, "k": 1.2,
        "cstar_mps": 900.0, "sigma_p": 0.0,
    },
    "grain": {
        "type": "BATES", "od_m": 0.05, "core_d_m": 0.02,
        "length_m": 0.12, "segment_count": 8, "inhibited_ends": 0,
    },
    "nozzle": {"throat_d_m": 0.01, "expansion_ratio": 4.0},
}


# ═════════════════════════════════════════════════════════════════
#  ingestCsv — creation with a HAROLD-issued WPN
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_ingest_csv_creates_motor_with_harold_wpn(client, auth_headers, db_session):
    _mock_system_code()
    issue_route = _mock_issue(1)
    _mock_precheck("WS01_curve")
    _mock_record_use("WS-MTR-P000001-A")

    r = _upload(client, auth_headers)
    assert r.status_code == 201, r.text
    body = r.json()

    # The WPN is HAROLD's ledger response VERBATIM — never self-assigned.
    assert body["wpn"] == "WS-MTR-P000001-A"
    assert body["motor"]["wpn"] == "WS-MTR-P000001-A"
    assert body["motor"]["base_index"] == 1
    assert body["rev_letter"] == "A"
    assert issue_route.call_count == 1
    # HAROLD decided the canonical name (precheck stem) — not the user.
    assert body["motor"]["name"] == "WS01_curve"
    assert body["precheck"]["iteration_stem"] == "WS01_curve"
    assert body["quality_tier"] == "excellent"
    assert body["recommended_fidelity"] == "HiFi"

    # DB state: motor + first revision + catalog entry on the in-house
    # supplier, active revision set.
    motor = db_session.query(Motor).one()
    assert motor.wpn == "WS-MTR-P000001-A"
    assert motor.base_index == 1
    assert motor.system_code == "MTR"
    assert motor.active_revision_id is not None
    rev = db_session.query(MotorRevision).one()
    assert rev.wpn == "WS-MTR-P000001-A"
    assert rev.origin == "csv"
    assert rev.source_csv_text is not None  # raw CSV retained
    part = db_session.query(CatalogPart).filter(
        CatalogPart.internal_part_number == "WS-MTR-P000001-A"
    ).one()
    assert part.part_number == "WS-MTR-P000001-A"
    assert float(part.mass_kg) == pytest.approx(3.2, rel=1e-6)
    supplier = db_session.query(Supplier).filter(
        Supplier.id == part.supplier_id
    ).one()
    assert supplier.is_in_house is True
    assert motor.catalog_part_id == part.id


@respx.mock
def test_ingest_same_lineage_issues_revision_keeps_index(client, auth_headers, db_session):
    _mock_system_code()
    issue_route = _mock_issue(1)
    _mock_precheck("WS01_curve")
    _mock_record_use("WS-MTR-P000001-A")
    assert _upload(client, auth_headers).status_code == 201

    revise_route = _mock_revise(1, "B")
    _mock_record_use("WS-MTR-P000001-B")
    r = _upload(client, auth_headers, grain_mass=0.5)
    assert r.status_code == 201, r.text
    body = r.json()

    # Same lineage ⇒ HAROLD revise, not a new index.
    assert body["wpn"] == "WS-MTR-P000001-B"
    assert body["rev_letter"] == "B"
    assert body["motor"]["wpn"] == "WS-MTR-P000001-A"  # base identity stable
    assert revise_route.called
    assert issue_route.call_count == 1  # no second allocation

    assert db_session.query(Motor).count() == 1
    revs = db_session.query(MotorRevision).order_by(MotorRevision.id).all()
    assert [x.rev_letter for x in revs] == ["A", "B"]
    assert {x.wpn for x in revs} == {"WS-MTR-P000001-A", "WS-MTR-P000001-B"}


@respx.mock
def test_revisions_from_csv_endpoint(client, auth_headers, db_session):
    _mock_system_code()
    _mock_issue(1)
    _mock_precheck("WS01_curve")
    _mock_record_use("WS-MTR-P000001-A")
    assert _upload(client, auth_headers).status_code == 201

    _mock_revise(1, "B")
    _mock_record_use("WS-MTR-P000001-B")
    r = _upload(
        client, auth_headers,
        path=f"{MOTORS}/WS-MTR-P000001-A/revisions:from-csv",
        grain_mass=0.5,
    )
    assert r.status_code == 201, r.text
    assert r.json()["wpn"] == "WS-MTR-P000001-B"
    assert db_session.query(MotorRevision).count() == 2


# ═════════════════════════════════════════════════════════════════
#  Failure semantics — gaplessness + 503
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_persistence_failure_releases_wpn(client, auth_headers, db_session, monkeypatch):
    _mock_system_code()
    _mock_issue(7)
    _mock_precheck("doomed_motor")
    delete_route = respx.delete(f"{_PREFIX}/wpn/WS-MTR-P000007-A").mock(
        return_value=httpx.Response(200, json={
            "deleted_wpn": "WS-MTR-P000007-A",
            "reclaimed": True, "new_next_index": 7,
        }),
    )

    import app.routers.engineering_motors as motors_router

    def _boom(*a, **kw):
        raise RuntimeError("catalog write exploded")

    monkeypatch.setattr(motors_router, "_ensure_catalog_entry", _boom)

    with pytest.raises(RuntimeError, match="catalog write exploded"):
        _upload(client, auth_headers, filename="doomed_motor.csv")

    # The freshly issued WPN was handed back — sequence stays gapless.
    assert delete_route.called
    assert db_session.query(Motor).count() == 0
    assert db_session.query(MotorRevision).count() == 0


@respx.mock
def test_harold_down_yields_503(client, auth_headers, db_session):
    respx.post(f"{_PREFIX}/filename-precheck").mock(
        side_effect=httpx.ConnectError("connection refused"),
    )
    r = _upload(client, auth_headers)
    assert r.status_code == 503
    assert "HAROLD" in r.json()["detail"]
    assert db_session.query(Motor).count() == 0


def test_harold_flag_off_yields_503(client, auth_headers, monkeypatch):
    monkeypatch.setattr(settings, "HAROLD_INTEGRATION_ENABLED", False)
    r = _upload(client, auth_headers)
    assert r.status_code == 503
    assert "HAROLD" in r.json()["detail"]


@respx.mock
def test_malformed_csv_422_before_any_harold_call(client, auth_headers):
    # No HAROLD routes mocked: any HTTP attempt would error loudly —
    # a bad CSV must 422 BEFORE touching the naming authority.
    r = client.post(
        f"{MOTORS}:ingestCsv",
        files={"file": ("junk.csv", b"this,is\nnot,a\nmotor,curve", "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 422
    assert "ingest failed" in r.json()["detail"]


# ═════════════════════════════════════════════════════════════════
#  Reads — list / detail / revisions / artifact / summary
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_read_endpoints_and_artifact_schema(client, auth_headers):
    _mock_system_code()
    _mock_issue(1)
    _mock_precheck("WS01_curve")
    _mock_record_use("WS-MTR-P000001-A")
    assert _upload(client, auth_headers).status_code == 201

    # List.
    r = client.get(MOTORS, headers=auth_headers)
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 1
    item = items[0]
    assert item["wpn"] == "WS-MTR-P000001-A"
    assert item["current_rev_letter"] == "A"
    assert item["quality_tier"] == "excellent"
    assert item["total_impulse_ns"] == pytest.approx(500.0 * 0.98, rel=0.02)
    assert item["motor_class"] == "I"   # ~490 N·s ⇒ I (320 < I ≤ 640)

    # Filter q.
    assert client.get(f"{MOTORS}?q=WS01", headers=auth_headers).json()
    assert client.get(f"{MOTORS}?q=nomatch", headers=auth_headers).json() == []

    # Detail.
    r = client.get(f"{MOTORS}/WS-MTR-P000001-A", headers=auth_headers)
    assert r.status_code == 200
    assert len(r.json()["revisions"]) == 1

    # Revision detail.
    r = client.get(f"{MOTORS}/WS-MTR-P000001-A/revisions/A", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["origin"] == "csv"
    assert r.json()["source_csv_sha256"]

    # Summary sheet.
    r = client.get(f"{MOTORS}/WS-MTR-P000001-A/summary", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["prop_mass_init_kg"] == pytest.approx(3.2, rel=1e-6)

    # Artifact — the §5.4 schema, field by field.
    r = client.get(
        f"{MOTORS}/WS-MTR-P000001-A/revisions/A/artifact", headers=auth_headers,
    )
    assert r.status_code == 200
    artifact = r.json()
    assert artifact["schema"] == "astra-motor-artifact/1.0"
    for fld in (
        "MotorTime_s", "Thrust_N", "Mdot_kgps", "PropMassRem_kg",
        "PropMassInit_kg", "Pchamber_Pa", "PropCGOffset_m_B",
        "PropInertiaAxial_kgm2", "PropInertiaTransverse_kgm2",
        "GrainStackLength_m", "BurnTime_s", "Ts_s", "AreaExit_m2",
        "AreaThroat_m2", "GrainTempGrid_K", "Thrust_N_byTgrain",
        "Mdot_kgps_byTgrain", "TotalImpulse_Ns", "PeakThrust_N",
        "Isp_s", "qualityTier", "defaultedFields", "provenance",
    ):
        assert fld in artifact, f"artifact missing {fld}"
    assert artifact["Ts_s"] == 0.001
    assert artifact["GrainTempGrid_K"] == [284.15, 294.15, 304.15]
    assert artifact["provenance"]["origin"] == "csv"
    assert artifact["provenance"]["wpn"] == "WS-MTR-P000001-A"
    assert artifact["provenance"]["csvSha256"]
    assert all(v <= 0 for v in artifact["Mdot_kgps"])

    # 404s.
    assert client.get(f"{MOTORS}/WS-MTR-P000099-A", headers=auth_headers).status_code == 404
    assert client.get(
        f"{MOTORS}/WS-MTR-P000001-A/revisions/Z", headers=auth_headers,
    ).status_code == 404


@respx.mock
def test_source_csv_stored_and_retrievable(client, auth_headers):
    """§5.2: the source CSV is stored with its hash AND retrievable —
    GET .../revisions/{rev}/source returns the uploaded bytes verbatim
    with text/csv + the original filename + the stored sha256."""
    _mock_system_code()
    _mock_issue(1)
    _mock_precheck("WS01_curve")
    _mock_record_use("WS-MTR-P000001-A")
    raw = _csv_bytes()
    r = client.post(
        f"{MOTORS}:ingestCsv",
        files={"file": ("WS01_curve.csv", raw, "text/csv")},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text

    r = client.get(
        f"{MOTORS}/WS-MTR-P000001-A/revisions/A/source", headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/csv")
    assert 'filename="WS01_curve.csv"' in r.headers["content-disposition"]
    assert r.content == raw  # byte-for-byte the uploaded source
    assert r.headers["x-source-sha256"] == hashlib.sha256(raw).hexdigest()

    # Base-WPN lookups resolve the same way as other sub-resources.
    r = client.get(
        f"{MOTORS}/WS-MTR-P000001/revisions/A/source", headers=auth_headers,
    )
    assert r.status_code == 200

    # Unknown revision → 404.
    assert client.get(
        f"{MOTORS}/WS-MTR-P000001-A/revisions/Z/source", headers=auth_headers,
    ).status_code == 404


@respx.mock
def test_source_csv_404_for_design_origin(client, auth_headers):
    """Design-origin revisions have no source CSV — /source is 404."""
    _mock_system_code()
    _mock_issue(3)
    _mock_record_use("WS-MTR-P000003-A")
    r = client.post(
        f"{MOTORS}:design",
        json={"name": "Mk1 8-grain", "inputs": _DESIGN_INPUTS},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text

    r = client.get(
        f"{MOTORS}/WS-MTR-P000003-A/revisions/A/source", headers=auth_headers,
    )
    assert r.status_code == 404
    assert "no stored source CSV" in r.json()["detail"]


@respx.mock
def test_motor_resolved_by_base_and_stale_rev_wpn(client, auth_headers):
    """Motor.wpn stores HAROLD's first-issued WPN verbatim
    (WS-MTR-P000001-A); path lookups must also resolve the base WPN
    (WS-MTR-P000001) and any-revision WPNs (e.g. a stale
    WS-MTR-P000001-C) to the same motor."""
    _mock_system_code()
    _mock_issue(1)
    _mock_precheck("WS01_curve")
    _mock_record_use("WS-MTR-P000001-A")
    assert _upload(client, auth_headers).status_code == 201

    # Base WPN (no revision letter).
    r = client.get(f"{MOTORS}/WS-MTR-P000001", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["wpn"] == "WS-MTR-P000001-A"  # stored value untouched

    # Stale / any-revision WPN sharing the same system code + index.
    r = client.get(f"{MOTORS}/WS-MTR-P000001-C", headers=auth_headers)
    assert r.status_code == 200, r.text
    assert r.json()["wpn"] == "WS-MTR-P000001-A"

    # Sub-resources resolve the same way.
    r = client.get(
        f"{MOTORS}/WS-MTR-P000001/revisions/A", headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["wpn"] == "WS-MTR-P000001-A"
    r = client.get(f"{MOTORS}/WS-MTR-P000001-C/summary", headers=auth_headers)
    assert r.status_code == 200
    assert r.json()["wpn"] == "WS-MTR-P000001-A"

    # PUT paths resolve too (no HAROLD call on selection).
    r = client.put(
        f"{MOTORS}/WS-MTR-P000001/active-revision",
        json={"rev_letter": "A"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["wpn"] == "WS-MTR-P000001-A"

    # True misses still 404 (different index, base or revved).
    assert client.get(
        f"{MOTORS}/WS-MTR-P000099", headers=auth_headers,
    ).status_code == 404
    assert client.get(
        f"{MOTORS}/WS-MTR-P000099-C", headers=auth_headers,
    ).status_code == 404


# ═════════════════════════════════════════════════════════════════
#  Immutability — no mutation routes on revisions
# ═════════════════════════════════════════════════════════════════


def test_revisions_have_no_mutation_routes():
    from app.main import app

    rev_read_routes = 0
    for route in app.routes:
        path = getattr(route, "path", "")
        if "/engineering/motors" not in path:
            continue
        methods = set(getattr(route, "methods", set()) or set())
        if "/revisions/{rev}" in path:
            rev_read_routes += 1
            assert methods <= {"GET", "HEAD"}, (
                f"published revisions are immutable — {path} exposes {methods}"
            )
        # No DELETE anywhere in the motors surface.
        assert "DELETE" not in methods, f"unexpected DELETE on {path}"
    assert rev_read_routes >= 2  # detail + artifact reads exist

    # The literal colon routes registered correctly.
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/v1/engineering/motors:ingestCsv" in paths
    assert "/api/v1/engineering/motors:design" in paths
    assert "/api/v1/engineering/motors:previewDesign" in paths
    assert "/api/v1/engineering/motors/{wpn}/revisions:from-csv" in paths
    assert "/api/v1/engineering/motors/{wpn}/revisions:from-design" in paths


# ═════════════════════════════════════════════════════════════════
#  Active-revision switch
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_active_revision_switch_updates_catalog_mass(client, auth_headers, db_session):
    _mock_system_code()
    _mock_issue(1)
    _mock_precheck("WS01_curve")
    _mock_record_use("WS-MTR-P000001-A")
    assert _upload(client, auth_headers, grain_mass=0.4).status_code == 201
    _mock_revise(1, "B")
    _mock_record_use("WS-MTR-P000001-B")
    assert _upload(client, auth_headers, grain_mass=0.5).status_code == 201

    motor = db_session.query(Motor).one()
    rev_a = db_session.query(MotorRevision).filter_by(rev_letter="A").one()
    rev_b = db_session.query(MotorRevision).filter_by(rev_letter="B").one()
    assert motor.active_revision_id == rev_a.id  # ingest does not auto-switch

    r = client.put(
        f"{MOTORS}/WS-MTR-P000001-A/active-revision",
        json={"rev_letter": "B"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    db_session.expire_all()
    motor = db_session.query(Motor).one()
    assert motor.active_revision_id == rev_b.id
    part = db_session.query(CatalogPart).filter(
        CatalogPart.internal_part_number == "WS-MTR-P000001-A"
    ).one()
    assert float(part.mass_kg) == pytest.approx(4.0, rel=1e-6)  # rev B grain sum

    # Unknown letter → 404.
    r = client.put(
        f"{MOTORS}/WS-MTR-P000001-A/active-revision",
        json={"rev_letter": "Q"},
        headers=auth_headers,
    )
    assert r.status_code == 404


# ═════════════════════════════════════════════════════════════════
#  Design endpoints
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_preview_design_never_calls_harold(client, auth_headers):
    # respx strict mode with ZERO routes: any HAROLD call would raise.
    r = client.post(
        f"{MOTORS}:previewDesign", json=_DESIGN_INPUTS, headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total_impulse_ns"] > 0
    assert body["peak_thrust_n"] > 0
    assert len(body["time_s"]) == len(body["thrust_n"]) == len(body["pchamber_pa"])
    assert body["motor_class"]
    assert all(v <= 0 for v in body["mdot_kgps"])


@respx.mock
def test_design_creates_motor_with_harold_wpn(client, auth_headers, db_session):
    _mock_system_code()
    issue_route = _mock_issue(3)
    _mock_record_use("WS-MTR-P000003-A")
    r = client.post(
        f"{MOTORS}:design",
        json={"name": "Mk1 8-grain", "inputs": _DESIGN_INPUTS},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["wpn"] == "WS-MTR-P000003-A"   # HAROLD's number, verbatim
    assert issue_route.call_count == 1
    assert body["quality_tier"] == "excellent"
    assert body["recommended_fidelity"] == "HiFi"

    motor = db_session.query(Motor).one()
    assert motor.name == "Mk1 8-grain"
    rev = db_session.query(MotorRevision).one()
    assert rev.origin == "design"
    assert rev.design_inputs["grain"]["segment_count"] == 8
    artifact = rev.artifact
    assert artifact["provenance"]["origin"] == "design"
    assert artifact["provenance"]["designInputs"]["grain"]["od_m"] == 0.05
    assert artifact["AreaThroat_m2"] > 0
    assert artifact["GrainStackLength_m"] == pytest.approx(8 * 0.12, rel=1e-9)
    # Design artifacts carry real geometry — no defaulted fields.
    assert artifact["defaultedFields"] == []


@respx.mock
def test_design_revision_endpoint(client, auth_headers, db_session):
    _mock_system_code()
    _mock_issue(3)
    _mock_record_use("WS-MTR-P000003-A")
    assert client.post(
        f"{MOTORS}:design",
        json={"name": "Mk1 8-grain", "inputs": _DESIGN_INPUTS},
        headers=auth_headers,
    ).status_code == 201

    _mock_revise(3, "B")
    _mock_record_use("WS-MTR-P000003-B")
    tweaked = {
        **_DESIGN_INPUTS,
        "grain": {**_DESIGN_INPUTS["grain"], "length_m": 0.10},
    }
    r = client.post(
        f"{MOTORS}/WS-MTR-P000003-A/revisions:from-design",
        json={"inputs": tweaked},
        headers=auth_headers,
    )
    assert r.status_code == 201, r.text
    assert r.json()["wpn"] == "WS-MTR-P000003-B"
    assert db_session.query(MotorRevision).count() == 2


def test_design_non_bates_is_422(client, auth_headers):
    bad = {**_DESIGN_INPUTS, "grain": {**_DESIGN_INPUTS["grain"], "type": "finocyl"}}
    r = client.post(
        f"{MOTORS}:previewDesign", json=bad, headers=auth_headers,
    )
    assert r.status_code == 422
    assert "not yet implemented" in r.json()["detail"]


# ═════════════════════════════════════════════════════════════════
#  RBAC
# ═════════════════════════════════════════════════════════════════


def test_writes_require_req_eng_plus(client, db_session):
    from tests.conftest import make_user

    _user, headers = make_user(db_session, "stakeholder")
    r = client.post(
        f"{MOTORS}:design",
        json={"name": "nope", "inputs": _DESIGN_INPUTS},
        headers=headers,
    )
    assert r.status_code == 403


def test_reads_require_auth(client):
    assert client.get(MOTORS).status_code in (401, 403)
