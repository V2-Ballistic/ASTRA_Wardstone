"""ASTRA-TDD-HAROLD-INT-002 Phase 3 — upload + approval flow with HAROLD.

Exercises the catalog router's flag-gated HAROLD wiring:

  POST /catalog/upload-step:
    + flag-off → behaviour identical to today (gotcha #12).
    + flag-on, HAROLD up → pending_import.extracted_data has
      proposed_wpn, wpn_source="harold", wpn_system_code.
    + flag-on, HAROLD down → wpn_source="fallback".
    + flag-on, filename WPN present → filename_wpn key + duplicate
      warning when HAROLD says is_issued=True.

  POST /catalog/pending-imports/{id}/approve:
    + flag-off → catalog_part.internal_part_number stays NULL.
    + flag-on, user proposed WPN, HAROLD up → internal_part_number
      set from V2's issue response, wpn_pending_sync=False.
    + flag-on, HAROLD down → fallback WPN, wpn_pending_sync=True.
    + flag-on, user_supplied_wpn collides in HAROLD ledger → 409.

Uses the same synthetic STEP payload pattern as
``test_step_upload_flow.py``.
"""
from __future__ import annotations

import io
import textwrap

import httpx
import pytest
import respx

from app.config import settings
from app.models.catalog import (
    CatalogPart,
    PendingCatalogImport,
    Supplier,
    SupplierAlias,
    WpnFallbackSequence,
)
from app.services.harold.fallback import ALLOWED_SYSTEM_CODES


_BASE = "http://host.docker.internal:8031"


# Same synthetic McMaster STEP body used by test_step_upload_flow.py,
# trimmed to what the parser needs.
MCMASTER_SHCS_STEP = textwrap.dedent("""\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('STEP AP214'),'1');
FILE_NAME(
    '92196A196_18-8 Stainless Steel Socket Head Screw',
    '2026-05-01T12:00:00',
    ('Mason'),
    ('Wardstone'),
    'SwSTEP 2.0',
    'SolidWorks 2025',
    '');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1 = APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,#2);
#2 = APPLICATION_CONTEXT('automotive_design');
#10 = PRODUCT('92196A196','92196A196 18-8 Stainless Steel Socket Head Screw','',(#11));
#11 = PRODUCT_CONTEXT('',#2,'mechanical');
#20 = SI_UNIT(.MILLI.,.METRE.);
#30 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.001),#31);
#100 = CARTESIAN_POINT('NONE',(0,0,0));
#101 = CARTESIAN_POINT('NONE',(50,80,12));
ENDSEC;
END-ISO-10303-21;
""")


# ─────────────────────────────────────────────────────────────────
#  Fixtures
# ─────────────────────────────────────────────────────────────────


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
    """Seed the fallback-sequence table + the in-house Wardstone supplier
    (the upload-step path falls back to Wardstone for unknown vendors)."""
    for code in sorted(ALLOWED_SYSTEM_CODES):
        db_session.add(WpnFallbackSequence(system_code=code, next_index=1))
    sup = db_session.query(Supplier).filter(Supplier.name == "Wardstone").first()
    if sup is None:
        sup = Supplier(
            name="Wardstone", short_name="WS", country="US",
            is_active=True, is_in_house=True,
            created_by_id=1,
        )
        db_session.add(sup); db_session.flush()
        for alias in ("Wardstone", "WardStone", "WARDSTONE", "Ward Stone", "WS"):
            db_session.add(SupplierAlias(supplier_id=sup.id, alias=alias))
    db_session.commit()
    return db_session


def _upload(client, auth_headers, *, content: str, filename: str):
    files = {"file": (filename, io.BytesIO(content.encode("iso-8859-1")), "model/step")}
    return client.post(
        "/api/v1/catalog/upload-step", files=files, headers=auth_headers,
    )


def _upload_mcmaster(client, auth_headers):
    return _upload(
        client, auth_headers,
        content=MCMASTER_SHCS_STEP,
        filename="92196A196_18-8 Stainless Steel Socket Head Screw.STEP",
    )


# ═════════════════════════════════════════════════════════════════
#  Upload-step flag-off — byte-identical to today (gotcha #12)
# ═════════════════════════════════════════════════════════════════


def test_upload_flag_off_no_wpn_metadata(
    client, auth_headers, db_session, test_user, harold_off, seeded,
):
    r = _upload_mcmaster(client, auth_headers)
    assert r.status_code == 201, r.text

    pending = (
        db_session.query(PendingCatalogImport)
        .filter(PendingCatalogImport.id == r.json()["pending_import_id"])
        .first()
    )
    assert pending is not None
    ext = pending.extracted_data or {}
    # Flag is off — none of the new keys should appear.
    assert "proposed_wpn" not in ext
    assert "wpn_source" not in ext
    assert "wpn_system_code" not in ext
    assert "filename_wpn" not in ext


# ═════════════════════════════════════════════════════════════════
#  Upload-step flag-on
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_upload_flag_on_harold_up_stashes_proposed_wpn(
    client, auth_headers, db_session, test_user, harold_on, seeded,
):
    respx.get(f"{_BASE}/api/v1/wpn/suggest").mock(
        return_value=httpx.Response(200, json={
            "suggested_wpn":  "WS-FH-P000003-A",
            "system_code":    "FH",
            "next_index":     3,
            "existing_count": 2,
        }),
    )
    # validate-filename — the McMaster filename has no Wardstone WPN
    # in it, so the validate POST is never made. No respx route needed.
    r = _upload_mcmaster(client, auth_headers)
    assert r.status_code == 201, r.text

    pending = (
        db_session.query(PendingCatalogImport)
        .filter(PendingCatalogImport.id == r.json()["pending_import_id"])
        .first()
    )
    ext = pending.extracted_data
    assert ext["proposed_wpn"] == "WS-FH-P000003-A"
    assert ext["wpn_source"] == "harold"
    assert ext["wpn_system_code"] == "FH"
    # Filename has no WPN in it → no filename_wpn key
    assert "filename_wpn" not in ext


@respx.mock
def test_upload_flag_on_harold_down_marks_fallback(
    client, auth_headers, db_session, test_user, harold_on, seeded,
):
    respx.get(f"{_BASE}/api/v1/wpn/suggest").mock(
        side_effect=httpx.ConnectError("nope"),
    )
    r = _upload_mcmaster(client, auth_headers)
    assert r.status_code == 201, r.text
    pending = (
        db_session.query(PendingCatalogImport)
        .filter(PendingCatalogImport.id == r.json()["pending_import_id"])
        .first()
    )
    ext = pending.extracted_data
    # Service fell back to local allocator
    assert ext["wpn_source"] == "fallback"
    assert ext["proposed_wpn"].startswith("WS-FH-P")
    assert ext["wpn_system_code"] == "FH"
    assert "unavailable" in (ext.get("wpn_suggestion_reason") or "").lower()


@respx.mock
def test_upload_filename_wpn_already_issued_adds_warning(
    client, auth_headers, db_session, test_user, harold_on, seeded,
):
    """When the filename itself looks like a Wardstone WPN AND that
    WPN is already in HAROLD's ledger, the warning list grows."""
    respx.get(f"{_BASE}/api/v1/wpn/suggest").mock(
        return_value=httpx.Response(200, json={
            "suggested_wpn":  "WS-FH-P000003-A",
            "system_code":    "FH",
            "next_index":     3,
            "existing_count": 2,
        }),
    )
    respx.post(f"{_BASE}/api/v1/wpn/validate").mock(
        return_value=httpx.Response(200, json={
            "wpn": "WS-FH-P000001-A",
            "is_valid_format": True,
            "is_issued": True,
            "errors": [], "warnings": [],
            "parsed": {"sys": "FH", "num": 1, "rev": "A"},
        }),
    )
    # Rename the uploaded file so the filename contains a Wardstone WPN.
    r = _upload(
        client, auth_headers,
        content=MCMASTER_SHCS_STEP,
        filename="WS-FH-P000001-A.STEP",
    )
    assert r.status_code == 201, r.text

    pending = (
        db_session.query(PendingCatalogImport)
        .filter(PendingCatalogImport.id == r.json()["pending_import_id"])
        .first()
    )
    ext = pending.extracted_data
    assert ext["filename_wpn"] == "WS-FH-P000001-A"

    warnings = (pending.extraction_warnings or {}).get("warnings") or []
    assert any("already issued" in w for w in warnings)


# ═════════════════════════════════════════════════════════════════
#  Approval flag-off — internal_part_number stays NULL
# ═════════════════════════════════════════════════════════════════


def test_approval_flag_off_leaves_internal_pn_null(
    client, auth_headers, db_session, test_user, harold_off, seeded,
):
    r = _upload_mcmaster(client, auth_headers)
    pending_id = r.json()["pending_import_id"]

    r2 = client.post(
        f"/api/v1/catalog/pending-imports/{pending_id}/approve",
        headers=auth_headers,
    )
    assert r2.status_code == 201, r2.text
    part_id = r2.json()["id"]

    part = db_session.query(CatalogPart).filter(CatalogPart.id == part_id).first()
    assert part is not None
    assert part.internal_part_number is None
    assert part.wpn_pending_sync is False


# ═════════════════════════════════════════════════════════════════
#  Approval flag-on — three branches
# ═════════════════════════════════════════════════════════════════


@respx.mock
def test_approval_flag_on_harold_up_auto_allocate(
    client, auth_headers, db_session, test_user, harold_on, seeded,
):
    respx.get(f"{_BASE}/api/v1/wpn/suggest").mock(
        return_value=httpx.Response(200, json={
            "suggested_wpn":  "WS-FH-P000001-A",
            "system_code":    "FH",
            "next_index":     1,
            "existing_count": 0,
        }),
    )
    respx.post(f"{_BASE}/api/v1/wpn/issue").mock(
        return_value=httpx.Response(201, json={
            "id": 1, "wpn": "WS-FH-P000001-A", "system_code": "FH",
            "part_number_int": 1, "revision": "A", "status": "active",
        }),
    )
    r = _upload_mcmaster(client, auth_headers)
    pending_id = r.json()["pending_import_id"]

    r2 = client.post(
        f"/api/v1/catalog/pending-imports/{pending_id}/approve",
        headers=auth_headers,
    )
    assert r2.status_code == 201, r2.text
    part_id = r2.json()["id"]

    part = db_session.query(CatalogPart).filter(CatalogPart.id == part_id).first()
    assert part.internal_part_number == "WS-FH-P000001-A"
    assert part.wpn_pending_sync is False


@respx.mock
def test_approval_flag_on_harold_down_uses_fallback(
    client, auth_headers, db_session, test_user, harold_on, seeded,
):
    """HAROLD up for suggest at upload time, then down by approval
    time → fallback path; wpn_pending_sync=True."""
    respx.get(f"{_BASE}/api/v1/wpn/suggest").mock(
        return_value=httpx.Response(200, json={
            "suggested_wpn":  "WS-FH-P000001-A",
            "system_code":    "FH",
            "next_index":     1,
            "existing_count": 0,
        }),
    )
    respx.post(f"{_BASE}/api/v1/wpn/issue").mock(
        side_effect=httpx.ConnectError("nope"),
    )
    r = _upload_mcmaster(client, auth_headers)
    pending_id = r.json()["pending_import_id"]

    r2 = client.post(
        f"/api/v1/catalog/pending-imports/{pending_id}/approve",
        headers=auth_headers,
    )
    assert r2.status_code == 201, r2.text
    part_id = r2.json()["id"]

    part = db_session.query(CatalogPart).filter(CatalogPart.id == part_id).first()
    assert part.internal_part_number is not None
    assert part.internal_part_number.startswith("WS-FH-P")
    assert part.wpn_pending_sync is True


@respx.mock
def test_approval_user_supplied_duplicate_returns_409(
    client, auth_headers, db_session, test_user, harold_on, seeded,
):
    """If the operator types a WPN that's already in HAROLD's ledger,
    HAROLD returns 409 → the router rejects the approval with 409
    and rolls back the whole transaction."""
    respx.get(f"{_BASE}/api/v1/wpn/suggest").mock(
        return_value=httpx.Response(200, json={
            "suggested_wpn":  "WS-FH-P000001-A",
            "system_code":    "FH",
            "next_index":     1,
            "existing_count": 0,
        }),
    )
    respx.post(f"{_BASE}/api/v1/wpn/issue-specific").mock(
        return_value=httpx.Response(409, text="already issued"),
    )

    r = _upload_mcmaster(client, auth_headers)
    pending_id = r.json()["pending_import_id"]

    # Simulate the operator overriding the proposed WPN with one
    # that's already issued.
    pending = (
        db_session.query(PendingCatalogImport)
        .filter(PendingCatalogImport.id == pending_id)
        .first()
    )
    ext = dict(pending.extracted_data)
    ext["user_supplied_wpn"] = "WS-FH-P000050-A"
    pending.extracted_data = ext
    db_session.commit()

    r2 = client.post(
        f"/api/v1/catalog/pending-imports/{pending_id}/approve",
        headers=auth_headers,
    )
    assert r2.status_code == 409, r2.text
    assert "already issued" in r2.json()["detail"].lower()

    # Rollback worked: no CatalogPart row was created for the failed
    # approval.
    parts_after = (
        db_session.query(CatalogPart)
        .join(PendingCatalogImport,
              PendingCatalogImport.committed_catalog_part_id == CatalogPart.id)
        .filter(PendingCatalogImport.id == pending_id)
        .count()
    )
    assert parts_after == 0


@respx.mock
def test_approval_user_supplied_happy_path(
    client, auth_headers, db_session, test_user, harold_on, seeded,
):
    respx.get(f"{_BASE}/api/v1/wpn/suggest").mock(
        return_value=httpx.Response(200, json={
            "suggested_wpn":  "WS-FH-P000001-A",
            "system_code":    "FH",
            "next_index":     1,
            "existing_count": 0,
        }),
    )
    respx.post(f"{_BASE}/api/v1/wpn/issue-specific").mock(
        return_value=httpx.Response(201, json={
            "id": 1, "wpn": "WS-FH-P000050-A", "system_code": "FH",
            "part_number_int": 50, "revision": "A", "status": "active",
        }),
    )

    r = _upload_mcmaster(client, auth_headers)
    pending_id = r.json()["pending_import_id"]
    pending = (
        db_session.query(PendingCatalogImport)
        .filter(PendingCatalogImport.id == pending_id)
        .first()
    )
    ext = dict(pending.extracted_data)
    ext["user_supplied_wpn"] = "WS-FH-P000050-A"
    pending.extracted_data = ext
    db_session.commit()

    r2 = client.post(
        f"/api/v1/catalog/pending-imports/{pending_id}/approve",
        headers=auth_headers,
    )
    assert r2.status_code == 201, r2.text
    part = db_session.query(CatalogPart).filter(CatalogPart.id == r2.json()["id"]).first()
    assert part.internal_part_number == "WS-FH-P000050-A"
    assert part.wpn_pending_sync is False
