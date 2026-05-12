"""ASTRA-TDD-HAROLD-INT-002 Phase 2 — HTTP client tests.

Mocks HAROLD V2's REST endpoints via respx. Verifies every client
method (happy path, timeout, ConnectError, 5xx, 4xx mapping to
domain-specific exceptions).
"""
from __future__ import annotations

import httpx
import pytest
import respx

from app.config import settings
from app.services.harold import client as harold_client
from app.services.harold.errors import (
    HaroldDuplicateError,
    HaroldInvalidResponseError,
    HaroldUnavailableError,
    HaroldValidationError,
)


_BASE = "http://host.docker.internal:8031"


@pytest.fixture(autouse=True)
def _pin_base_url(monkeypatch):
    """Make sure every test uses the same base URL regardless of
    .env / env-var drift."""
    monkeypatch.setattr(settings, "HAROLD_BASE_URL", _BASE)
    monkeypatch.setattr(settings, "HAROLD_TIMEOUT_SECONDS", 1.0)


# ── /health ────────────────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_health_happy_path():
    respx.get(f"{_BASE}/health").mock(
        return_value=httpx.Response(200, json={
            "status": "healthy", "version": "2.0.0", "db": "ok",
        }),
    )
    body = await harold_client.health()
    assert body["status"] == "healthy"
    assert body["version"] == "2.0.0"


@pytest.mark.asyncio
@respx.mock
async def test_health_500_raises_unavailable():
    respx.get(f"{_BASE}/health").mock(return_value=httpx.Response(500))
    with pytest.raises(HaroldUnavailableError):
        await harold_client.health()


@pytest.mark.asyncio
@respx.mock
async def test_health_connect_error_raises_unavailable():
    respx.get(f"{_BASE}/health").mock(side_effect=httpx.ConnectError("nope"))
    with pytest.raises(HaroldUnavailableError, match="unreachable"):
        await harold_client.health()


@pytest.mark.asyncio
@respx.mock
async def test_health_timeout_raises_unavailable():
    respx.get(f"{_BASE}/health").mock(side_effect=httpx.TimeoutException("slow"))
    with pytest.raises(HaroldUnavailableError, match="unreachable"):
        await harold_client.health()


# ── /api/v1/system-codes ──────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_list_system_codes_happy_path():
    respx.get(f"{_BASE}/api/v1/system-codes").mock(
        return_value=httpx.Response(200, json={
            "total": 21,
            "codes": [{"code": "FH", "category": "library-category",
                       "name": "Fastener Hardware", "description": "..."}],
        }),
    )
    body = await harold_client.list_system_codes()
    assert body["total"] == 21
    assert body["codes"][0]["code"] == "FH"


# ── /api/v1/wpn/suggest ───────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_suggest_happy_path():
    respx.get(f"{_BASE}/api/v1/wpn/suggest").mock(
        return_value=httpx.Response(200, json={
            "suggested_wpn": "WS-FH-P000001-A",
            "system_code":    "FH",
            "next_index":     1,
            "existing_count": 0,
        }),
    )
    body = await harold_client.suggest("FH")
    assert body["suggested_wpn"] == "WS-FH-P000001-A"


@pytest.mark.asyncio
@respx.mock
async def test_suggest_passes_system_code_query_param():
    """Verify the URL the client emits — the route matcher catches
    the system_code param explicitly."""
    route = respx.get(
        f"{_BASE}/api/v1/wpn/suggest",
        params={"system_code": "MH"},
    ).mock(return_value=httpx.Response(200, json={
        "suggested_wpn": "WS-MH-P000003-A",
        "system_code":   "MH",
        "next_index":    3,
        "existing_count": 2,
    }))
    body = await harold_client.suggest("MH", hint="some hint string")
    assert route.called
    assert body["suggested_wpn"] == "WS-MH-P000003-A"


@pytest.mark.asyncio
@respx.mock
async def test_suggest_422_validation_error():
    respx.get(f"{_BASE}/api/v1/wpn/suggest").mock(
        return_value=httpx.Response(422, text="invalid system code"),
    )
    with pytest.raises(HaroldValidationError):
        await harold_client.suggest("XX")


# ── /api/v1/wpn/validate ──────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_validate_returns_body_even_when_is_valid_false():
    """is_valid_format=false is a normal result, not an exception."""
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
    body = await harold_client.validate("ws-fh-p000001-a")
    assert body["is_valid_format"] is False
    assert body["errors"]


@pytest.mark.asyncio
@respx.mock
async def test_validate_422_raises_validation_error():
    respx.post(f"{_BASE}/api/v1/wpn/validate").mock(
        return_value=httpx.Response(422, text="body must include wpn"),
    )
    with pytest.raises(HaroldValidationError):
        await harold_client.validate("")


# ── /api/v1/wpn/issue ─────────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_issue_happy_path():
    respx.post(f"{_BASE}/api/v1/wpn/issue").mock(
        return_value=httpx.Response(201, json={
            "id": 1, "wpn": "WS-FH-P000001-A", "system_code": "FH",
            "status": "active", "part_number_int": 1, "revision": "A",
        }),
    )
    body = await harold_client.issue(
        "FH",
        origin_system="astra",
        origin_record_id="42",
        display_name="Test",
    )
    assert body["wpn"] == "WS-FH-P000001-A"


@pytest.mark.asyncio
@respx.mock
async def test_issue_body_omits_none_fields():
    """Optional fields with None values shouldn't appear in the POST
    body — V2 would reject them as type errors."""
    captured = {}

    def _handler(request):
        import json as _json
        captured.update(_json.loads(request.content))
        return httpx.Response(201, json={
            "id": 2, "wpn": "WS-FH-P000002-A", "system_code": "FH",
            "status": "active", "part_number_int": 2, "revision": "A",
        })

    respx.post(f"{_BASE}/api/v1/wpn/issue").mock(side_effect=_handler)
    await harold_client.issue("FH")  # no optional fields supplied
    assert captured == {"system_code": "FH"}


# ── /api/v1/wpn/issue-specific ────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_issue_specific_happy_path():
    respx.post(f"{_BASE}/api/v1/wpn/issue-specific").mock(
        return_value=httpx.Response(201, json={
            "id": 5, "wpn": "WS-FH-P000050-A", "system_code": "FH",
            "status": "active", "part_number_int": 50, "revision": "A",
        }),
    )
    body = await harold_client.issue_specific(
        "WS-FH-P000050-A",
        origin_system="astra",
        origin_record_id="99",
        display_name="Reconciled fallback",
    )
    assert body["wpn"] == "WS-FH-P000050-A"


@pytest.mark.asyncio
@respx.mock
async def test_issue_specific_409_raises_duplicate():
    respx.post(f"{_BASE}/api/v1/wpn/issue-specific").mock(
        return_value=httpx.Response(409, text="already issued"),
    )
    with pytest.raises(HaroldDuplicateError):
        await harold_client.issue_specific("WS-FH-P000050-A")


@pytest.mark.asyncio
@respx.mock
async def test_issue_specific_422_raises_validation():
    respx.post(f"{_BASE}/api/v1/wpn/issue-specific").mock(
        return_value=httpx.Response(422, text="malformed wpn"),
    )
    with pytest.raises(HaroldValidationError):
        await harold_client.issue_specific("ws-fh-p000001-a")


# ── /api/v1/ledger/{wpn} ──────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_get_ledger_entry_happy_path():
    respx.get(f"{_BASE}/api/v1/ledger/WS-FH-P000001-A").mock(
        return_value=httpx.Response(200, json={
            "wpn": "WS-FH-P000001-A", "system_code": "FH",
            "part_number_int": 1, "revision": "A", "status": "active",
        }),
    )
    body = await harold_client.get_ledger_entry("WS-FH-P000001-A")
    assert body["status"] == "active"


@pytest.mark.asyncio
@respx.mock
async def test_get_ledger_entry_404_raises_invalid_response():
    respx.get(f"{_BASE}/api/v1/ledger/WS-FH-P999999-A").mock(
        return_value=httpx.Response(404, text="not found"),
    )
    with pytest.raises(HaroldInvalidResponseError):
        await harold_client.get_ledger_entry("WS-FH-P999999-A")


# ── JSON parsing failures ─────────────────────────────────────────


@pytest.mark.asyncio
@respx.mock
async def test_non_json_body_raises_invalid_response():
    respx.get(f"{_BASE}/health").mock(
        return_value=httpx.Response(200, text="not json at all"),
    )
    with pytest.raises(HaroldInvalidResponseError):
        await harold_client.health()


@pytest.mark.asyncio
@respx.mock
async def test_non_object_body_raises_invalid_response():
    respx.get(f"{_BASE}/health").mock(
        return_value=httpx.Response(200, json=["not", "an", "object"]),
    )
    with pytest.raises(HaroldInvalidResponseError):
        await harold_client.health()
