"""ASTRA-TDD-HAROLD-INT-002 Phase 2 — service-layer tests.

Combines respx-mocked HAROLD calls with the SQLite test DB so the
three approval branches in ``issue_wpn_for_catalog_part`` and the
reconcile flow are exercised end-to-end.

Replaces the prior HAROLD-001 test file of the same name.
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.config import settings
from app.models.catalog import (
    CatalogPart,
    PartClass,
    Supplier,
    WpnFallbackSequence,
    LifecycleStatus,
    LRUClass,
)
from app.services.harold import (
    HaroldDuplicateError,
    HaroldUnavailableError,
    heartbeat,
    issue_wpn_for_catalog_part,
    list_system_codes,
    reconcile_pending_sync,
    suggest_wpn_for_part,
    validate_filename_wpn,
    validate_wpn,
)
from app.services.harold.fallback import ALLOWED_SYSTEM_CODES


_BASE = "http://host.docker.internal:8030"


@pytest.fixture(autouse=True)
def _pin_base_url(monkeypatch):
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
    """Seed fallback-sequence table with all 21 codes."""
    for code in sorted(ALLOWED_SYSTEM_CODES):
        db_session.add(WpnFallbackSequence(system_code=code, next_index=1))
    db_session.commit()
    return db_session


@pytest.fixture
def supplier(db_session, test_user):
    s = Supplier(name="McMaster-Carr", created_by_id=test_user.id)
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _make_part(db_session, supplier, test_user, **overrides) -> CatalogPart:
    defaults = dict(
        supplier_id=supplier.id,
        part_number="92196A196",
        name="Test fastener part",
        part_class=PartClass.FASTENER_SCREW,
        lru_classification=LRUClass.LRU,
        lifecycle_status=LifecycleStatus.ACTIVE,
        created_by_id=test_user.id,
    )
    defaults.update(overrides)
    part = CatalogPart(**defaults)
    db_session.add(part)
    db_session.commit()
    db_session.refresh(part)
    return part


# ── heartbeat ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heartbeat_flag_off_short_circuits(harold_off):
    r = await heartbeat()
    assert r["enabled"] is False
    assert r["reachable"] is False
    assert "disabled" in r["reason"].lower()


@pytest.mark.asyncio
@respx.mock
async def test_heartbeat_flag_on_reachable(harold_on):
    respx.get(f"{_BASE}/health").mock(
        return_value=httpx.Response(200, json={
            "status": "healthy", "version": "2.0.0", "db": "ok",
        }),
    )
    r = await heartbeat()
    assert r["enabled"] is True
    assert r["reachable"] is True
    assert r["version"] == "2.0.0"
    assert r["response_time_ms"] is not None


@pytest.mark.asyncio
@respx.mock
async def test_heartbeat_flag_on_harold_down(harold_on):
    respx.get(f"{_BASE}/health").mock(
        side_effect=httpx.ConnectError("no route"),
    )
    r = await heartbeat()
    assert r["enabled"] is True
    assert r["reachable"] is False
    assert "unreachable" in r["reason"].lower()


# ── suggest_wpn_for_part ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_suggest_flag_off_uses_fallback(harold_off, seeded):
    r = await suggest_wpn_for_part(seeded, "fastener_screw")
    assert r["source"] == "fallback"
    assert r["system_code"] == "FH"
    assert r["suggested_wpn"] == "WS-FH-P000001-A"


@pytest.mark.asyncio
@respx.mock
async def test_suggest_flag_on_routes_to_harold(harold_on, seeded):
    respx.get(f"{_BASE}/api/tools/wardstone-harold/wpn/suggest").mock(
        return_value=httpx.Response(200, json={
            "suggested_wpn":  "WS-FH-P000007-A",
            "system_code":    "FH",
            "next_index":     7,
            "existing_count": 6,
        }),
    )
    r = await suggest_wpn_for_part(seeded, "fastener_screw")
    assert r["source"] == "harold"
    assert r["suggested_wpn"] == "WS-FH-P000007-A"
    assert r["existing_count"] == 6


@pytest.mark.asyncio
@respx.mock
async def test_suggest_harold_down_falls_back(harold_on, seeded):
    respx.get(f"{_BASE}/api/tools/wardstone-harold/wpn/suggest").mock(
        side_effect=httpx.ConnectError("no route"),
    )
    r = await suggest_wpn_for_part(seeded, "bracket")
    assert r["source"] == "fallback"
    assert r["system_code"] == "MH"
    assert "unavailable" in r["reason"].lower()


@pytest.mark.asyncio
@respx.mock
async def test_suggest_unmapped_class_routes_to_mh(harold_on, seeded):
    respx.get(f"{_BASE}/api/tools/wardstone-harold/wpn/suggest").mock(
        return_value=httpx.Response(200, json={
            "suggested_wpn": "WS-MH-P000001-A",
            "system_code":    "MH",
            "next_index":     1,
            "existing_count": 0,
        }),
    )
    r = await suggest_wpn_for_part(seeded, "not_a_class")
    assert r["source"] == "harold"
    assert r["system_code"] == "MH"


# ── validate_wpn (direct passthrough) ──────────────────────────────


@pytest.mark.asyncio
async def test_validate_flag_off_raises(harold_off):
    with pytest.raises(HaroldUnavailableError):
        await validate_wpn("WS-FH-P000001-A")


@pytest.mark.asyncio
@respx.mock
async def test_validate_passthrough(harold_on):
    respx.post(f"{_BASE}/api/tools/wardstone-harold/wpn/validate").mock(
        return_value=httpx.Response(200, json={
            "wpn": "WS-FH-P000001-A",
            "is_valid_format": True,
            "is_issued": False,
            "errors": [], "warnings": [],
            "parsed": {"sys": "FH", "num": 1, "rev": "A"},
        }),
    )
    r = await validate_wpn("WS-FH-P000001-A")
    assert r["is_valid_format"] is True
    assert r["is_issued"] is False


# ── validate_filename_wpn ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_validate_filename_no_wpn_in_filename(harold_off):
    r = await validate_filename_wpn("92196A196_Screw.STEP")
    assert r["is_wardstone_format"] is False
    assert r["extracted_wpn"] is None
    assert r["wpn_validation"] is None


@pytest.mark.asyncio
async def test_validate_filename_wpn_present_flag_off(harold_off):
    """Filename has a WPN but flag is off → skip the HAROLD call."""
    r = await validate_filename_wpn("WS-FH-P000001-A.STEP")
    assert r["is_wardstone_format"] is True
    assert r["extracted_wpn"] == "WS-FH-P000001-A"
    assert r["wpn_validation"] is None  # flag-off: HAROLD not called


@pytest.mark.asyncio
@respx.mock
async def test_validate_filename_wpn_present_flag_on(harold_on):
    respx.post(f"{_BASE}/api/tools/wardstone-harold/wpn/validate").mock(
        return_value=httpx.Response(200, json={
            "wpn": "WS-FH-P000001-A",
            "is_valid_format": True,
            "is_issued": True,
            "errors": [], "warnings": [],
            "parsed": {"sys": "FH", "num": 1, "rev": "A"},
        }),
    )
    r = await validate_filename_wpn("WS-FH-P000001-A.STEP")
    assert r["is_wardstone_format"] is True
    assert r["wpn_validation"]["is_issued"] is True


@pytest.mark.asyncio
@respx.mock
async def test_validate_filename_harold_down_returns_partial(harold_on):
    respx.post(f"{_BASE}/api/tools/wardstone-harold/wpn/validate").mock(
        side_effect=httpx.ConnectError("nope"),
    )
    r = await validate_filename_wpn("WS-FH-P000001-A.STEP")
    assert r["is_wardstone_format"] is True
    assert r["extracted_wpn"] == "WS-FH-P000001-A"
    assert r["wpn_validation"] is None  # HAROLD down — partial result


# ── issue_wpn_for_catalog_part (3 branches per AD-11) ─────────────


@pytest.mark.asyncio
async def test_issue_branch1_caller_supplied_flag_off_marks_pending(
    harold_off, db_session, supplier, test_user, seeded,
):
    """Flag off but caller supplied a WPN: apply locally, flag pending."""
    part = _make_part(db_session, supplier, test_user)
    wpn, source, pending = await issue_wpn_for_catalog_part(
        seeded, part, supplied_wpn="WS-FH-P000050-A",
    )
    assert wpn == "WS-FH-P000050-A"
    assert source == "fallback"
    assert pending is True


@pytest.mark.asyncio
@respx.mock
async def test_issue_branch1_caller_supplied_harold_up(
    harold_on, db_session, supplier, test_user, seeded,
):
    respx.post(f"{_BASE}/api/tools/wardstone-harold/wpn/issue-specific").mock(
        return_value=httpx.Response(201, json={
            "id": 1, "wpn": "WS-FH-P000050-A", "system_code": "FH",
            "status": "active", "part_number_int": 50, "revision": "A",
        }),
    )
    part = _make_part(db_session, supplier, test_user)
    wpn, source, pending = await issue_wpn_for_catalog_part(
        seeded, part, supplied_wpn="WS-FH-P000050-A",
    )
    assert wpn == "WS-FH-P000050-A"
    assert source == "harold-specific"
    assert pending is False


@pytest.mark.asyncio
@respx.mock
async def test_issue_branch1_caller_supplied_duplicate_propagates(
    harold_on, db_session, supplier, test_user, seeded,
):
    """HAROLD 409 must propagate as HaroldDuplicateError so the router
    can map it to HTTP 409."""
    respx.post(f"{_BASE}/api/tools/wardstone-harold/wpn/issue-specific").mock(
        return_value=httpx.Response(409, text="already issued"),
    )
    part = _make_part(db_session, supplier, test_user)
    with pytest.raises(HaroldDuplicateError):
        await issue_wpn_for_catalog_part(
            seeded, part, supplied_wpn="WS-FH-P000050-A",
        )


@pytest.mark.asyncio
@respx.mock
async def test_issue_branch2_auto_allocate_harold_up(
    harold_on, db_session, supplier, test_user, seeded,
):
    respx.post(f"{_BASE}/api/tools/wardstone-harold/wpn/issue").mock(
        return_value=httpx.Response(201, json={
            "id": 1, "wpn": "WS-FH-P000001-A", "system_code": "FH",
            "status": "active", "part_number_int": 1, "revision": "A",
        }),
    )
    part = _make_part(db_session, supplier, test_user)
    wpn, source, pending = await issue_wpn_for_catalog_part(seeded, part)
    assert wpn == "WS-FH-P000001-A"
    assert source == "harold-auto"
    assert pending is False


@pytest.mark.asyncio
@respx.mock
async def test_issue_branch3_auto_allocate_harold_down(
    harold_on, db_session, supplier, test_user, seeded,
):
    respx.post(f"{_BASE}/api/tools/wardstone-harold/wpn/issue").mock(
        side_effect=httpx.ConnectError("nope"),
    )
    part = _make_part(db_session, supplier, test_user)
    wpn, source, pending = await issue_wpn_for_catalog_part(seeded, part)
    assert wpn == "WS-FH-P000001-A"  # fallback for part_class fastener_screw → FH
    assert source == "fallback"
    assert pending is True


@pytest.mark.asyncio
async def test_issue_flag_off_auto_uses_fallback(
    harold_off, db_session, supplier, test_user, seeded,
):
    part = _make_part(db_session, supplier, test_user,
                       part_class=PartClass.NUT)
    wpn, source, pending = await issue_wpn_for_catalog_part(seeded, part)
    assert wpn == "WS-FH-P000001-A"  # nut → FH
    assert source == "fallback"
    assert pending is True


# ── reconcile_pending_sync ────────────────────────────────────────


@pytest.mark.asyncio
async def test_reconcile_flag_off_noop(
    harold_off, db_session, supplier, test_user, seeded,
):
    part = _make_part(
        db_session, supplier, test_user,
        internal_part_number="WS-FH-P000001-A",
        wpn_pending_sync=True,
    )
    r = await reconcile_pending_sync(seeded, part)
    assert r["reconciled"] is False
    assert "disabled" in r["reason"].lower()


@pytest.mark.asyncio
async def test_reconcile_not_pending_noop(
    harold_on, db_session, supplier, test_user, seeded,
):
    part = _make_part(
        db_session, supplier, test_user,
        internal_part_number="WS-FH-P000001-A",
        wpn_pending_sync=False,
    )
    r = await reconcile_pending_sync(seeded, part)
    assert r["reconciled"] is False
    assert r["via"] == "noop"


@pytest.mark.asyncio
@respx.mock
async def test_reconcile_happy_path(
    harold_on, db_session, supplier, test_user, seeded,
):
    respx.post(f"{_BASE}/api/tools/wardstone-harold/wpn/issue-specific").mock(
        return_value=httpx.Response(201, json={
            "id": 1, "wpn": "WS-FH-P000005-A", "system_code": "FH",
            "status": "active", "part_number_int": 5, "revision": "A",
        }),
    )
    part = _make_part(
        db_session, supplier, test_user,
        internal_part_number="WS-FH-P000005-A",
        wpn_pending_sync=True,
    )
    r = await reconcile_pending_sync(seeded, part)
    assert r["reconciled"] is True
    assert r["via"] == "issue_specific"
    assert part.wpn_pending_sync is False


@pytest.mark.asyncio
@respx.mock
async def test_reconcile_collision_falls_through_to_new_wpn(
    harold_on, db_session, supplier, test_user, seeded,
):
    """409 from issue_specific → call issue → new WPN, flag cleared."""
    respx.post(f"{_BASE}/api/tools/wardstone-harold/wpn/issue-specific").mock(
        return_value=httpx.Response(409, text="already issued"),
    )
    respx.post(f"{_BASE}/api/tools/wardstone-harold/wpn/issue").mock(
        return_value=httpx.Response(201, json={
            "id": 99, "wpn": "WS-FH-P000099-A", "system_code": "FH",
            "status": "active", "part_number_int": 99, "revision": "A",
        }),
    )
    part = _make_part(
        db_session, supplier, test_user,
        internal_part_number="WS-FH-P000005-A",
        wpn_pending_sync=True,
    )
    r = await reconcile_pending_sync(seeded, part)
    assert r["reconciled"] is True
    assert r["via"] == "issue"
    assert r["wpn"] == "WS-FH-P000099-A"
    assert part.internal_part_number == "WS-FH-P000099-A"
    assert part.wpn_pending_sync is False


@pytest.mark.asyncio
@respx.mock
async def test_reconcile_harold_down_returns_unreconciled(
    harold_on, db_session, supplier, test_user, seeded,
):
    respx.post(f"{_BASE}/api/tools/wardstone-harold/wpn/issue-specific").mock(
        side_effect=httpx.ConnectError("nope"),
    )
    part = _make_part(
        db_session, supplier, test_user,
        internal_part_number="WS-FH-P000005-A",
        wpn_pending_sync=True,
    )
    r = await reconcile_pending_sync(seeded, part)
    assert r["reconciled"] is False
    assert part.wpn_pending_sync is True  # flag preserved


# ── list_system_codes ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_list_system_codes_flag_off_raises(harold_off):
    with pytest.raises(HaroldUnavailableError):
        await list_system_codes()


@pytest.mark.asyncio
@respx.mock
async def test_list_system_codes_passthrough(harold_on):
    respx.get(f"{_BASE}/api/tools/wardstone-harold/system-codes").mock(
        return_value=httpx.Response(200, json={
            "total": 21,
            "codes": [{"code": "FH", "category": "library-category",
                       "name": "Fastener Hardware", "description": "..."}],
        }),
    )
    r = await list_system_codes()
    assert r["total"] == 21
