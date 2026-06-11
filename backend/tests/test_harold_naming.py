"""harold_naming — strict HAROLD naming-authority service tests.

Mocks HAROLD's HTTP surface via respx, same pattern as
``test_harold_client.py`` / ``test_harold_service.py``. Spec §2
properties under test:

  * sequentiality — WPNs come back from HAROLD verbatim, in order;
    ASTRA never fabricates an index.
  * idempotent system-code registration (created: true/false).
  * revision bump — index stable, revision letter A→B.
  * allocate_and_persist commits on success and does NOT release.
  * allocate_and_persist releases (gaplessness) on persistence
    failure, after rollback.
  * release failure → HaroldOrphanWpnError + CRITICAL log.
  * HAROLD down → HaroldUnavailableError propagates; NO fallback.
  * record_use patches merged metadata onto the ledger entry.
"""
from __future__ import annotations

import json as _json
import logging

import httpx
import pytest
import respx

from app.config import settings
from app.services import harold_naming
from app.services.harold_naming import (
    MTR_CODE,
    HaroldOrphanWpnError,
    HaroldUnavailableError,
    allocate_and_persist,
    allocate_next,
    ensure_system_code,
    issue_revision,
    ledger_query,
    record_use,
)

_BASE = "http://host.docker.internal:8030"
_PREFIX = f"{_BASE}/api/tools/wardstone-harold"


@pytest.fixture(autouse=True)
def _pin_settings(monkeypatch):
    """Pin base URL/timeout and enable the integration — the
    engineering domains require HAROLD, so the flag is on for every
    test except the explicit flag-off test."""
    monkeypatch.setattr(settings, "HAROLD_BASE_URL", _BASE)
    monkeypatch.setattr(settings, "HAROLD_TIMEOUT_SECONDS", 1.0)
    monkeypatch.setattr(settings, "HAROLD_INTEGRATION_ENABLED", True)


def _ledger_entry(index: int, rev: str = "A", code: str = "MTR") -> dict:
    return {
        "id": index,
        "wpn": f"WS-{code}-P{index:06d}-{rev}",
        "system_code": code,
        "part_number_int": index,
        "revision": rev,
        "status": "active",
    }


def _mock_system_code_exists(code: str = "MTR") -> respx.Route:
    """System code already registered → 200 created:false."""
    return respx.post(f"{_PREFIX}/system-codes").mock(
        return_value=httpx.Response(200, json={
            "code": code, "name": "Solid Motors",
            "category": "engineering", "description": "x",
            "created": False,
        }),
    )


class FakeDb:
    """Stand-in Session exposing exactly what allocate_and_persist
    touches — lets the tests assert commit/rollback ordering."""

    def __init__(self):
        self.committed = False
        self.rolled_back = False

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True


# ── Sequentiality: HAROLD's numbers verbatim, never fabricated ─────


@pytest.mark.asyncio
@respx.mock
async def test_allocate_next_surfaces_harold_sequence_verbatim():
    _mock_system_code_exists()
    issue_route = respx.post(f"{_PREFIX}/wpn/issue").mock(
        side_effect=[
            httpx.Response(201, json=_ledger_entry(1)),
            httpx.Response(201, json=_ledger_entry(2)),
            httpx.Response(201, json=_ledger_entry(3)),
        ],
    )
    wpns = []
    for _ in range(3):
        entry = await allocate_next(MTR_CODE, display_name="Motor design")
        wpns.append(entry["wpn"])
    assert wpns == [
        "WS-MTR-P000001-A",
        "WS-MTR-P000002-A",
        "WS-MTR-P000003-A",
    ]
    assert issue_route.call_count == 3  # one HAROLD issue per WPN — no local math


@pytest.mark.asyncio
@respx.mock
async def test_allocate_next_sends_system_code_and_origin():
    _mock_system_code_exists()
    captured: dict = {}

    def _handler(request):
        captured.update(_json.loads(request.content))
        return httpx.Response(201, json=_ledger_entry(7))

    respx.post(f"{_PREFIX}/wpn/issue").mock(side_effect=_handler)
    await allocate_next(
        MTR_CODE,
        display_name="Mk2 motor",
        origin_record_id="42",
        metadata={"domain": "solid_motor"},
    )
    assert captured["system_code"] == "MTR"
    assert captured["origin_system"] == "astra"
    assert captured["origin_record_id"] == "42"
    assert captured["display_name"] == "Mk2 motor"
    assert captured["metadata"] == {"domain": "solid_motor"}


# ── ensure_system_code idempotency ─────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_ensure_system_code_first_registration_created_true():
    captured: dict = {}

    def _handler(request):
        captured.update(_json.loads(request.content))
        return httpx.Response(201, json={
            "code": "MTR", "name": "Solid Motors",
            "category": "engineering",
            "description": captured.get("description"),
            "created": True,
        })

    respx.post(f"{_PREFIX}/system-codes").mock(side_effect=_handler)
    body = await ensure_system_code(MTR_CODE)
    assert body["created"] is True
    # Registry defaults flow onto the wire.
    assert captured["code"] == "MTR"
    assert captured["name"] == "Solid Motors"
    assert captured["category"] == "engineering"


@pytest.mark.asyncio
@respx.mock
async def test_ensure_system_code_idempotent_created_false():
    route = _mock_system_code_exists()
    first = await ensure_system_code(MTR_CODE)
    second = await ensure_system_code(MTR_CODE)
    assert first["created"] is False
    assert second["created"] is False
    assert route.call_count == 2  # both calls hit HAROLD; HAROLD dedupes


@pytest.mark.asyncio
async def test_ensure_system_code_unknown_code_requires_name():
    with pytest.raises(ValueError, match="name is required"):
        await ensure_system_code("ZZ")


# ── issue_revision: index stable, revision letter bumps ────────────


@pytest.mark.asyncio
@respx.mock
async def test_issue_revision_bumps_letter_keeps_index():
    respx.post(f"{_PREFIX}/wpn/WS-MTR-P000007-A/revise").mock(
        return_value=httpx.Response(201, json=_ledger_entry(7, rev="B")),
    )
    entry = await issue_revision(
        "WS-MTR-P000007-A", description="thrust curve rev",
    )
    assert entry["wpn"] == "WS-MTR-P000007-B"
    assert entry["part_number_int"] == 7   # index stable
    assert entry["revision"] == "B"        # A → B


# ── allocate_and_persist: success path ─────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_allocate_and_persist_success_commits_and_never_releases():
    _mock_system_code_exists()
    respx.post(f"{_PREFIX}/wpn/issue").mock(
        return_value=httpx.Response(201, json=_ledger_entry(1)),
    )
    delete_route = respx.delete(f"{_PREFIX}/wpn/WS-MTR-P000001-A").mock(
        return_value=httpx.Response(200, json={
            "deleted_wpn": "WS-MTR-P000001-A",
            "reclaimed": True, "new_next_index": 1,
        }),
    )
    db = FakeDb()
    persisted: list[dict] = []

    def persist_fn(session, entry):
        assert session is db
        persisted.append(entry)
        return "row-1"

    entry, result = await allocate_and_persist(
        db, MTR_CODE, persist_fn,
        alloc_kwargs={"display_name": "Motor design"},
    )
    assert entry["wpn"] == "WS-MTR-P000001-A"
    assert result == "row-1"
    assert persisted == [entry]
    assert db.committed is True
    assert db.rolled_back is False
    assert not delete_route.called  # success never releases


# ── allocate_and_persist: failure path = rollback + release ───────


@pytest.mark.asyncio
@respx.mock
async def test_allocate_and_persist_failure_rolls_back_and_releases():
    _mock_system_code_exists()
    respx.post(f"{_PREFIX}/wpn/issue").mock(
        return_value=httpx.Response(201, json=_ledger_entry(5)),
    )
    delete_route = respx.delete(f"{_PREFIX}/wpn/WS-MTR-P000005-A").mock(
        return_value=httpx.Response(200, json={
            "deleted_wpn": "WS-MTR-P000005-A",
            "reclaimed": True, "new_next_index": 5,
        }),
    )
    db = FakeDb()

    def persist_fn(session, entry):
        raise RuntimeError("disk full")

    with pytest.raises(RuntimeError, match="disk full"):
        await allocate_and_persist(db, MTR_CODE, persist_fn)

    assert db.rolled_back is True
    assert db.committed is False
    assert delete_route.called  # WPN handed back — sequence stays gapless


@pytest.mark.asyncio
@respx.mock
async def test_allocate_and_persist_commit_failure_also_releases():
    """Failure at commit (not just persist_fn) must release too."""
    _mock_system_code_exists()
    respx.post(f"{_PREFIX}/wpn/issue").mock(
        return_value=httpx.Response(201, json=_ledger_entry(6)),
    )
    delete_route = respx.delete(f"{_PREFIX}/wpn/WS-MTR-P000006-A").mock(
        return_value=httpx.Response(200, json={
            "deleted_wpn": "WS-MTR-P000006-A",
            "reclaimed": True, "new_next_index": 6,
        }),
    )

    class CommitExplodesDb(FakeDb):
        def commit(self):
            raise RuntimeError("constraint violated at commit")

    db = CommitExplodesDb()
    with pytest.raises(RuntimeError, match="constraint violated"):
        await allocate_and_persist(db, MTR_CODE, lambda s, e: None)
    assert db.rolled_back is True
    assert delete_route.called


# ── allocate_and_persist: release failure = orphan + CRITICAL ─────


@pytest.mark.asyncio
@respx.mock
async def test_release_failure_raises_orphan_error_and_logs_critical(caplog):
    _mock_system_code_exists()
    respx.post(f"{_PREFIX}/wpn/issue").mock(
        return_value=httpx.Response(201, json=_ledger_entry(9)),
    )
    # Release path is down → orphan.
    respx.delete(f"{_PREFIX}/wpn/WS-MTR-P000009-A").mock(
        side_effect=httpx.ConnectError("harold went away"),
    )
    db = FakeDb()

    def persist_fn(session, entry):
        raise RuntimeError("persistence exploded")

    with caplog.at_level(logging.CRITICAL, logger="app.services.harold_naming.service"):
        with pytest.raises(HaroldOrphanWpnError) as excinfo:
            await allocate_and_persist(db, MTR_CODE, persist_fn)

    assert excinfo.value.wpn == "WS-MTR-P000009-A"
    assert db.rolled_back is True
    critical = [r for r in caplog.records if r.levelno == logging.CRITICAL]
    assert critical, "expected a CRITICAL log record for the orphan WPN"
    assert "WS-MTR-P000009-A" in critical[0].getMessage()


# ── HAROLD down: no fallback, ever ─────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_harold_down_raises_unavailable_no_fallback():
    respx.post(f"{_PREFIX}/system-codes").mock(
        side_effect=httpx.ConnectError("connection refused"),
    )
    with pytest.raises(HaroldUnavailableError):
        await allocate_next(MTR_CODE)


@pytest.mark.asyncio
@respx.mock
async def test_harold_500_raises_unavailable_no_fallback():
    _mock_system_code_exists()
    respx.post(f"{_PREFIX}/wpn/issue").mock(
        return_value=httpx.Response(500, text="boom"),
    )
    with pytest.raises(HaroldUnavailableError):
        await allocate_next(MTR_CODE)


@pytest.mark.asyncio
async def test_flag_off_raises_unavailable(monkeypatch):
    monkeypatch.setattr(settings, "HAROLD_INTEGRATION_ENABLED", False)
    with pytest.raises(HaroldUnavailableError, match="no local fallback"):
        await allocate_next(MTR_CODE)


@pytest.mark.asyncio
@respx.mock
async def test_allocate_and_persist_harold_down_never_touches_db():
    respx.post(f"{_PREFIX}/system-codes").mock(
        side_effect=httpx.ConnectError("nope"),
    )
    db = FakeDb()
    with pytest.raises(HaroldUnavailableError):
        await allocate_and_persist(db, MTR_CODE, lambda s, e: None)
    assert db.committed is False
    assert db.rolled_back is False


# ── record_use: metadata annotation via PATCH ──────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_record_use_patches_metadata_with_kind():
    captured: dict = {}

    def _handler(request):
        captured.update(_json.loads(request.content))
        entry = _ledger_entry(3)
        entry["metadata"] = captured.get("metadata")
        return httpx.Response(200, json=entry)

    respx.patch(f"{_PREFIX}/wpn/WS-MTR-P000003-A").mock(side_effect=_handler)
    body = await record_use(
        "WS-MTR-P000003-A", "solid_motor", {"design_id": 12},
    )
    assert captured == {
        "metadata": {"design_id": 12, "kind": "solid_motor"},
    }
    assert body["wpn"] == "WS-MTR-P000003-A"


# ── ledger_query passthrough ───────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_ledger_query_passes_filters_and_returns_page():
    route = respx.get(
        f"{_PREFIX}/ledger",
        params={"system_code": "MTR", "status": "active",
                "q": "motor", "skip": "0", "limit": "50"},
    ).mock(
        return_value=httpx.Response(200, json={
            "items": [_ledger_entry(1)], "total": 1, "skip": 0, "limit": 50,
        }),
    )
    body = await ledger_query(
        system_code="MTR", status="active", q="motor", limit=50,
    )
    assert route.called
    assert body["total"] == 1
    assert body["items"][0]["wpn"] == "WS-MTR-P000001-A"


# ── Module hygiene: the forbidden fallback is not imported ─────────


def test_harold_naming_never_imports_fallback_allocator():
    """Spec §2: NO local fallback for engineering domains. Guard
    against future regressions wiring the catalog fallback in."""
    import app.services.harold_naming.service as svc
    assert not hasattr(svc, "fallback")
    src_attrs = vars(svc)
    assert "allocate_for_part_class" not in src_attrs


def test_spec_mandated_codes():
    assert harold_naming.MTR_CODE == "MTR"
    assert harold_naming.AER_CODE == "AER"
    assert harold_naming.CFG_CODE == "CFG"
    assert harold_naming.SYSTEM_CODE_REGISTRY["MTR"]["name"] == "Solid Motors"
    assert harold_naming.SYSTEM_CODE_REGISTRY["AER"]["name"] == "Aero Decks"
    assert harold_naming.SYSTEM_CODE_REGISTRY["CFG"]["name"] == "Vehicle Configurations"
