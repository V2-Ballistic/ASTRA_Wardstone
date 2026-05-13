"""ASTRA-TDD-HAROLD-INT-002 Phase 3 — /api/v1/harold/* + /designators tests.

Uses respx to mock HAROLD V2 + the FastAPI TestClient for the proxy
router. Covers happy / unavailable / 409 / 422 for each endpoint and
the `/catalog/designators` filter pivot per AD-9.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.config import settings
from app.models.catalog import (
    CatalogPart,
    LifecycleStatus,
    LRUClass,
    PartClass,
    Supplier,
    WpnFallbackSequence,
)
from app.services.harold.fallback import ALLOWED_SYSTEM_CODES


_BASE = "http://host.docker.internal:8031"


@pytest.fixture(autouse=True)
def _pin_settings(monkeypatch):
    monkeypatch.setattr(settings, "HAROLD_BASE_URL", _BASE)
    monkeypatch.setattr(settings, "HAROLD_TIMEOUT_SECONDS", 1.0)


@pytest.fixture
def harold_on(monkeypatch):
    monkeypatch.setattr(settings, "HAROLD_INTEGRATION_ENABLED", True)


@pytest.fixture
def harold_off(monkeypatch):
    monkeypatch.setattr(settings, "HAROLD_INTEGRATION_ENABLED", False)


@pytest.fixture
def seeded(db_session):
    for code in sorted(ALLOWED_SYSTEM_CODES):
        db_session.add(WpnFallbackSequence(system_code=code, next_index=1))
    db_session.commit()
    return db_session


def _make_part(db_session, supplier_id, user_id, **kw) -> CatalogPart:
    defaults = dict(
        supplier_id=supplier_id,
        part_number=kw.get("part_number", "TEST-PN-001"),
        name=kw.get("name", "Test part"),
        part_class=kw.get("part_class", PartClass.FASTENER_SCREW),
        lru_classification=LRUClass.LRU,
        lifecycle_status=LifecycleStatus.ACTIVE,
        created_by_id=user_id,
    )
    defaults.update({
        k: v for k, v in kw.items()
        if k not in ("part_number", "name", "part_class")
    })
    part = CatalogPart(**defaults)
    db_session.add(part)
    db_session.commit()
    db_session.refresh(part)
    return part


# ═════════════════════════════════════════════════════════════════
#  /api/v1/harold/heartbeat
# ═════════════════════════════════════════════════════════════════


def test_heartbeat_flag_off(client, auth_headers, harold_off):
    r = client.get("/api/v1/harold/heartbeat", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is False
    assert body["reachable"] is False
    assert "disabled" in (body["reason"] or "").lower()


@respx.mock
def test_heartbeat_flag_on_reachable(client, auth_headers, harold_on):
    respx.get(f"{_BASE}/health").mock(
        return_value=httpx.Response(200, json={
            "status": "healthy", "version": "2.0.0", "db": "ok",
        }),
    )
    r = client.get("/api/v1/harold/heartbeat", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"] is True
    assert body["reachable"] is True
    assert body["version"] == "2.0.0"


@respx.mock
def test_heartbeat_flag_on_harold_down(client, auth_headers, harold_on):
    respx.get(f"{_BASE}/health").mock(
        side_effect=httpx.ConnectError("no route"),
    )
    r = client.get("/api/v1/harold/heartbeat", headers=auth_headers)
    body = r.json()
    assert body["enabled"] is True
    assert body["reachable"] is False
    assert "unreachable" in body["reason"].lower()


def test_heartbeat_requires_auth(client):
    r = client.get("/api/v1/harold/heartbeat")
    assert r.status_code == 401


# ═════════════════════════════════════════════════════════════════
#  /api/v1/harold/system-codes
# ═════════════════════════════════════════════════════════════════


def test_system_codes_flag_off_returns_unavailable(client, auth_headers, harold_off):
    r = client.get("/api/v1/harold/system-codes", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["harold_available"] is False
    assert "disabled" in body["reason"].lower()


@respx.mock
def test_system_codes_happy_path(client, auth_headers, harold_on):
    respx.get(f"{_BASE}/api/v1/system-codes").mock(
        return_value=httpx.Response(200, json={
            "total": 21,
            "codes": [
                {"code": "FH", "category": "library-category",
                 "name": "Fastener Hardware", "description": "Catalog fasteners"},
                {"code": "ST", "category": "project-system",
                 "name": "Structures", "description": "Structural elements"},
            ],
        }),
    )
    r = client.get("/api/v1/harold/system-codes", headers=auth_headers)
    body = r.json()
    assert body["harold_available"] is True
    assert body["data"]["total"] == 21
    codes = {c["code"] for c in body["data"]["codes"]}
    assert codes == {"FH", "ST"}


@respx.mock
def test_system_codes_harold_500(client, auth_headers, harold_on):
    respx.get(f"{_BASE}/api/v1/system-codes").mock(
        return_value=httpx.Response(500, text="boom"),
    )
    r = client.get("/api/v1/harold/system-codes", headers=auth_headers)
    body = r.json()
    assert body["harold_available"] is False


# ═════════════════════════════════════════════════════════════════
#  /api/v1/harold/suggest
# ═════════════════════════════════════════════════════════════════


def test_suggest_flag_off_uses_fallback(client, auth_headers, harold_off, seeded):
    r = client.post(
        "/api/v1/harold/suggest",
        headers=auth_headers,
        json={"part_class": "fastener_screw"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["harold_available"] is True
    assert body["data"]["source"] == "fallback"
    assert body["data"]["system_code"] == "FH"


@respx.mock
def test_suggest_flag_on_routes_to_harold(client, auth_headers, harold_on, seeded):
    respx.get(f"{_BASE}/api/v1/wpn/suggest").mock(
        return_value=httpx.Response(200, json={
            "suggested_wpn":  "WS-FH-P000042-A",
            "system_code":    "FH",
            "next_index":     42,
            "existing_count": 41,
        }),
    )
    r = client.post(
        "/api/v1/harold/suggest",
        headers=auth_headers,
        json={"part_class": "fastener_screw"},
    )
    body = r.json()
    assert body["data"]["source"] == "harold"
    assert body["data"]["suggested_wpn"] == "WS-FH-P000042-A"
    assert body["data"]["existing_count"] == 41


@respx.mock
def test_suggest_harold_down_falls_back(client, auth_headers, harold_on, seeded):
    respx.get(f"{_BASE}/api/v1/wpn/suggest").mock(
        side_effect=httpx.ConnectError("no route"),
    )
    r = client.post(
        "/api/v1/harold/suggest",
        headers=auth_headers,
        json={"part_class": "bracket"},
    )
    body = r.json()
    assert body["data"]["source"] == "fallback"
    assert body["data"]["system_code"] == "MH"
    assert body["data"]["reason"]


def test_suggest_requires_part_class(client, auth_headers, harold_on):
    r = client.post("/api/v1/harold/suggest", headers=auth_headers, json={})
    assert r.status_code == 422


# ═════════════════════════════════════════════════════════════════
#  /api/v1/harold/validate
# ═════════════════════════════════════════════════════════════════


def test_validate_flag_off_returns_unavailable(client, auth_headers, harold_off):
    r = client.post(
        "/api/v1/harold/validate",
        headers=auth_headers,
        json={"wpn": "WS-FH-P000001-A"},
    )
    body = r.json()
    assert body["harold_available"] is False


@respx.mock
def test_validate_happy_path(client, auth_headers, harold_on):
    respx.post(f"{_BASE}/api/v1/wpn/validate").mock(
        return_value=httpx.Response(200, json={
            "wpn": "WS-FH-P000001-A",
            "is_valid_format": True,
            "is_issued": False,
            "errors": [], "warnings": [],
            "parsed": {"sys": "FH", "num": 1, "rev": "A"},
        }),
    )
    r = client.post(
        "/api/v1/harold/validate",
        headers=auth_headers,
        json={"wpn": "WS-FH-P000001-A"},
    )
    body = r.json()
    assert body["harold_available"] is True
    assert body["data"]["is_valid_format"] is True
    assert body["data"]["is_issued"] is False
    assert body["data"]["parsed"]["num"] == 1


@respx.mock
def test_validate_malformed_returns_body(client, auth_headers, harold_on):
    """is_valid_format=false is a normal result, NOT the unavailable
    branch."""
    respx.post(f"{_BASE}/api/v1/wpn/validate").mock(
        return_value=httpx.Response(200, json={
            "wpn": "ws-fh-p000001-a",
            "is_valid_format": False,
            "is_issued": False,
            "errors": ["lowercase rejected"],
            "warnings": [],
            "parsed": None,
        }),
    )
    r = client.post(
        "/api/v1/harold/validate",
        headers=auth_headers,
        json={"wpn": "ws-fh-p000001-a"},
    )
    body = r.json()
    assert body["harold_available"] is True
    assert body["data"]["is_valid_format"] is False
    assert body["data"]["errors"]


@respx.mock
def test_validate_harold_down_unavailable_envelope(client, auth_headers, harold_on):
    respx.post(f"{_BASE}/api/v1/wpn/validate").mock(
        side_effect=httpx.ConnectError("no route"),
    )
    r = client.post(
        "/api/v1/harold/validate",
        headers=auth_headers,
        json={"wpn": "WS-FH-P000001-A"},
    )
    body = r.json()
    assert body["harold_available"] is False


# ═════════════════════════════════════════════════════════════════
#  /api/v1/harold/validate-filename
# ═════════════════════════════════════════════════════════════════


def test_validate_filename_mcmaster_style(client, auth_headers, harold_off):
    r = client.post(
        "/api/v1/harold/validate-filename",
        headers=auth_headers,
        json={"filename": "92196A196_Screw.STEP"},
    )
    body = r.json()
    assert body["harold_available"] is True
    assert body["data"]["is_wardstone_format"] is False
    assert body["data"]["extracted_wpn"] is None
    assert body["data"]["extension"] == ".STEP"


@respx.mock
def test_validate_filename_with_wpn_flag_on(client, auth_headers, harold_on):
    respx.post(f"{_BASE}/api/v1/wpn/validate").mock(
        return_value=httpx.Response(200, json={
            "wpn": "WS-FH-P000001-A",
            "is_valid_format": True,
            "is_issued": True,
            "errors": [], "warnings": [],
            "parsed": {"sys": "FH", "num": 1, "rev": "A"},
        }),
    )
    r = client.post(
        "/api/v1/harold/validate-filename",
        headers=auth_headers,
        json={"filename": "WS-FH-P000001-A.STEP"},
    )
    body = r.json()
    assert body["data"]["is_wardstone_format"] is True
    assert body["data"]["extracted_wpn"] == "WS-FH-P000001-A"
    assert body["data"]["wpn_validation"]["is_issued"] is True


# ═════════════════════════════════════════════════════════════════
#  /api/v1/harold/parts/{part_id}/reconcile
# ═════════════════════════════════════════════════════════════════


def test_reconcile_unknown_part_returns_404(client, auth_headers, harold_on):
    r = client.post(
        "/api/v1/harold/parts/999999/reconcile",
        headers=auth_headers,
    )
    assert r.status_code == 404


@respx.mock
def test_reconcile_happy_path(
    client, auth_headers, harold_on, db_session, test_user, seeded,
):
    sup = Supplier(name="McMaster", created_by_id=test_user.id)
    db_session.add(sup); db_session.commit(); db_session.refresh(sup)
    part = _make_part(
        db_session, sup.id, test_user.id,
        internal_part_number="WS-FH-P000005-A",
        wpn_pending_sync=True,
    )

    respx.post(f"{_BASE}/api/v1/wpn/issue-specific").mock(
        return_value=httpx.Response(201, json={
            "id": 1, "wpn": "WS-FH-P000005-A", "system_code": "FH",
            "part_number_int": 5, "revision": "A", "status": "active",
        }),
    )
    r = client.post(
        f"/api/v1/harold/parts/{part.id}/reconcile",
        headers=auth_headers,
    )
    body = r.json()
    assert body["harold_available"] is True
    assert body["data"]["reconciled"] is True
    assert body["data"]["via"] == "issue_specific"


@respx.mock
def test_reconcile_collision_falls_through(
    client, auth_headers, harold_on, db_session, test_user, seeded,
):
    sup = Supplier(name="McMaster", created_by_id=test_user.id)
    db_session.add(sup); db_session.commit(); db_session.refresh(sup)
    part = _make_part(
        db_session, sup.id, test_user.id,
        internal_part_number="WS-FH-P000005-A",
        wpn_pending_sync=True,
    )

    respx.post(f"{_BASE}/api/v1/wpn/issue-specific").mock(
        return_value=httpx.Response(409, text="already issued"),
    )
    respx.post(f"{_BASE}/api/v1/wpn/issue").mock(
        return_value=httpx.Response(201, json={
            "id": 99, "wpn": "WS-FH-P000099-A", "system_code": "FH",
            "part_number_int": 99, "revision": "A", "status": "active",
        }),
    )
    r = client.post(
        f"/api/v1/harold/parts/{part.id}/reconcile",
        headers=auth_headers,
    )
    body = r.json()
    assert body["data"]["reconciled"] is True
    assert body["data"]["via"] == "issue"
    assert body["data"]["wpn"] == "WS-FH-P000099-A"


@respx.mock
def test_reconcile_harold_down(
    client, auth_headers, harold_on, db_session, test_user, seeded,
):
    sup = Supplier(name="McMaster", created_by_id=test_user.id)
    db_session.add(sup); db_session.commit(); db_session.refresh(sup)
    part = _make_part(
        db_session, sup.id, test_user.id,
        internal_part_number="WS-FH-P000005-A",
        wpn_pending_sync=True,
    )
    respx.post(f"{_BASE}/api/v1/wpn/issue-specific").mock(
        side_effect=httpx.ConnectError("nope"),
    )
    r = client.post(
        f"/api/v1/harold/parts/{part.id}/reconcile",
        headers=auth_headers,
    )
    body = r.json()
    assert body["data"]["reconciled"] is False


# ═════════════════════════════════════════════════════════════════
#  /api/v1/catalog/designators — AD-9 column pivot
# ═════════════════════════════════════════════════════════════════


def test_designators_empty(client):
    """No parts with internal_part_number → empty list, total 0."""
    r = client.get("/api/v1/catalog/designators")  # no auth required
    assert r.status_code == 200
    body = r.json()
    assert body["designators"] == []
    assert body["total"] == 0
    assert body["system_filter"] is None


def test_designators_excludes_parts_without_wpn(
    client, db_session, test_user,
):
    """The McMaster-style row with internal_part_number=NULL must NOT
    appear in the response."""
    sup = Supplier(name="McMaster", created_by_id=test_user.id)
    db_session.add(sup); db_session.commit(); db_session.refresh(sup)
    _make_part(
        db_session, sup.id, test_user.id,
        part_number="92196A196",
        internal_part_number=None,  # explicit
    )
    r = client.get("/api/v1/catalog/designators")
    assert r.json()["total"] == 0


def test_designators_returns_structured_rows(
    client, db_session, test_user,
):
    sup = Supplier(name="McMaster", created_by_id=test_user.id)
    db_session.add(sup); db_session.commit(); db_session.refresh(sup)
    _make_part(
        db_session, sup.id, test_user.id,
        part_number="92196A196",
        internal_part_number="WS-FH-P000001-A",
        part_class=PartClass.FASTENER_SCREW,
    )
    _make_part(
        db_session, sup.id, test_user.id,
        part_number="92196A197",
        internal_part_number="WS-MH-P000007-A",
        part_class=PartClass.BRACKET,
    )

    r = client.get("/api/v1/catalog/designators")
    body = r.json()
    assert body["total"] == 2
    by_wpn = {d["wpn"]: d for d in body["designators"]}
    assert by_wpn["WS-FH-P000001-A"]["system_code"] == "FH"
    assert by_wpn["WS-FH-P000001-A"]["part_class"] == "fastener_screw"
    assert by_wpn["WS-MH-P000007-A"]["system_code"] == "MH"
    assert by_wpn["WS-MH-P000007-A"]["part_class"] == "bracket"
    # part_id is set
    assert by_wpn["WS-FH-P000001-A"]["part_id"]
    assert by_wpn["WS-MH-P000007-A"]["part_id"]


def test_designators_filter_by_system(
    client, db_session, test_user,
):
    sup = Supplier(name="McMaster", created_by_id=test_user.id)
    db_session.add(sup); db_session.commit(); db_session.refresh(sup)
    _make_part(
        db_session, sup.id, test_user.id,
        part_number="A", internal_part_number="WS-FH-P000001-A",
    )
    _make_part(
        db_session, sup.id, test_user.id,
        part_number="B", internal_part_number="WS-MH-P000007-A",
    )
    r = client.get("/api/v1/catalog/designators?system=FH")
    body = r.json()
    assert body["total"] == 1
    assert body["system_filter"] == "FH"
    assert body["designators"][0]["wpn"] == "WS-FH-P000001-A"


def test_designators_system_filter_case_insensitive(
    client, db_session, test_user,
):
    sup = Supplier(name="McMaster", created_by_id=test_user.id)
    db_session.add(sup); db_session.commit(); db_session.refresh(sup)
    _make_part(
        db_session, sup.id, test_user.id,
        part_number="A", internal_part_number="WS-FH-P000001-A",
    )
    r = client.get("/api/v1/catalog/designators?system=fh")
    body = r.json()
    assert body["total"] == 1
    assert body["system_filter"] == "FH"


def test_designators_pagination(
    client, db_session, test_user,
):
    sup = Supplier(name="McMaster", created_by_id=test_user.id)
    db_session.add(sup); db_session.commit(); db_session.refresh(sup)
    for i in range(1, 6):
        _make_part(
            db_session, sup.id, test_user.id,
            part_number=f"P{i}",
            internal_part_number=f"WS-FH-P00000{i}-A",
        )
    r = client.get("/api/v1/catalog/designators?skip=0&limit=2")
    body = r.json()
    assert body["total"] == 5
    assert len(body["designators"]) == 2

    r2 = client.get("/api/v1/catalog/designators?skip=2&limit=2")
    body2 = r2.json()
    assert len(body2["designators"]) == 2
    # No overlap
    wpns1 = {d["wpn"] for d in body["designators"]}
    wpns2 = {d["wpn"] for d in body2["designators"]}
    assert wpns1.isdisjoint(wpns2)
