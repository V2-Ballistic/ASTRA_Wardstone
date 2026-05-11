"""ASTRA-TDD-HAROLD-001 Phase 2 — service-layer tests.

Uses `respx` to mock the WRENCH `/api/tools/{slug}/runs` and `/health`
endpoints. Tests verify:
  1. suggest_wpn_from_text() parses the real HAROLD-Search output shape.
  2. The feature flag short-circuits to HaroldUnavailableError when off.
  3. Timeouts surface as HaroldUnavailableError (NOT a generic Exception).
  4. list_system_codes() upper-cases codes and skips malformed rows.
  5. heartbeat() returns a structured "unavailable" payload instead of
     raising when HAROLD is down.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import settings
from app.services.harold import (
    HaroldUnavailableError,
    heartbeat,
    list_system_codes,
    suggest_wpn_from_text,
)


@pytest.fixture
def harold_on(monkeypatch):
    monkeypatch.setattr(settings, "HAROLD_INTEGRATION_ENABLED", True)
    monkeypatch.setattr(settings, "HAROLD_BASE_URL", "http://harold.test")
    monkeypatch.setattr(settings, "HAROLD_TIMEOUT_SECONDS", 1.0)


@pytest.fixture
def harold_off(monkeypatch):
    monkeypatch.setattr(settings, "HAROLD_INTEGRATION_ENABLED", False)
    monkeypatch.setattr(settings, "HAROLD_BASE_URL", "http://harold.test")


# ─────────────────────────────────────────────────────────────────
#  suggest_wpn_from_text
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_suggest_wpn_parses_real_harold_search_shape(harold_on):
    """Reflects an actual response captured during Phase-0 investigation."""
    real_output = {
        "suggestion":       "WS-AV-P1000-A",
        "pattern_id":       "cad_part",
        "pattern_label":    "CAD part",
        "confidence":       0.57,
        "reasoning":        "CAD part pattern: WS-AV-P1000-A.",
        "extracted_fields": {"SYS": "AV", "NNNN": "1000", "REV": "A"},
        "glossary_matches": [],
        "candidates":       [{"pattern_id": "cad_assembly", "label": "CAD assembly", "score": 0.99}],
        "notes":            ["No project code provided"],
        "llm_used":         "ollama:llama3.2",
    }
    with respx.mock(base_url="http://harold.test") as mock:
        mock.post("/api/tools/_wardstone-harold-search/runs").mock(
            return_value=httpx.Response(200, json={
                "runId": "x", "slug": "_wardstone-harold-search",
                "inputs": {"query": "avionics processor"},
                "output": real_output, "success": True, "elapsed_ms": 1234,
                "error": None, "created_at": "2026-05-11T20:00:00",
            }),
        )
        result = await suggest_wpn_from_text("avionics processor")

    assert result.suggestion    == "WS-AV-P1000-A"
    assert result.pattern_id    == "cad_part"
    assert result.confidence    == pytest.approx(0.57)
    assert result.extracted_fields["SYS"] == "AV"
    assert result.llm_used      == "ollama:llama3.2"
    assert len(result.candidates) == 1


@pytest.mark.asyncio
async def test_suggest_raises_when_flag_off(harold_off):
    with pytest.raises(HaroldUnavailableError, match="disabled"):
        await suggest_wpn_from_text("anything")


@pytest.mark.asyncio
async def test_suggest_raises_on_timeout(harold_on):
    """Per AD-2 — short timeout, graceful degradation."""
    with respx.mock(base_url="http://harold.test") as mock:
        mock.post("/api/tools/_wardstone-harold-search/runs").mock(
            side_effect=httpx.TimeoutException("simulated"),
        )
        with pytest.raises(HaroldUnavailableError, match="unreachable"):
            await suggest_wpn_from_text("query")


@pytest.mark.asyncio
async def test_suggest_raises_on_connect_error(harold_on):
    with respx.mock(base_url="http://harold.test") as mock:
        mock.post("/api/tools/_wardstone-harold-search/runs").mock(
            side_effect=httpx.ConnectError("ECONNREFUSED"),
        )
        with pytest.raises(HaroldUnavailableError, match="unreachable"):
            await suggest_wpn_from_text("query")


@pytest.mark.asyncio
async def test_suggest_raises_on_harold_500(harold_on):
    """WRENCH returning a 500 is graceful-degradation territory, not
    an ASTRA bug — surfaces as Unavailable (gotcha #12)."""
    with respx.mock(base_url="http://harold.test") as mock:
        mock.post("/api/tools/_wardstone-harold-search/runs").mock(
            return_value=httpx.Response(500, text="upstream error"),
        )
        with pytest.raises(HaroldUnavailableError, match="HTTP 500"):
            await suggest_wpn_from_text("query")


# ─────────────────────────────────────────────────────────────────
#  list_system_codes
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_system_codes_normalizes_uppercase(harold_on):
    """Real HAROLD returns codes uppercase; if a fixture / future
    upstream change downgraded them, we want the service to fix that
    rather than propagate."""
    real_payload = {
        "section": "systems",
        "payload": {
            "systems": [
                {"code": "av", "name": "Avionics - Hardware", "description": "Flight computers."},
                {"code": "ST", "name": "Structures",         "description": "Primary structure."},
                {"name": "Garbage row, no code"},
                "not-a-dict",
            ],
        },
    }
    with respx.mock(base_url="http://harold.test") as mock:
        mock.post("/api/tools/_wardstone-harold-data/runs").mock(
            return_value=httpx.Response(200, json={
                "runId": "x", "slug": "_wardstone-harold-data",
                "inputs": {"section": "systems"},
                "output": real_payload, "success": True, "elapsed_ms": 0,
                "error": None, "created_at": "2026-05-11T20:00:00",
            }),
        )
        codes = await list_system_codes()

    assert [c.code for c in codes] == ["AV", "ST"]
    assert codes[0].name == "Avionics - Hardware"


@pytest.mark.asyncio
async def test_list_system_codes_raises_when_disabled(harold_off):
    with pytest.raises(HaroldUnavailableError):
        await list_system_codes()


# ─────────────────────────────────────────────────────────────────
#  heartbeat
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_heartbeat_returns_unreachable_when_disabled(harold_off):
    """Must never raise — the heartbeat is the *signal* that drives
    the UI's hide-or-show logic."""
    result = await heartbeat()
    assert result.enabled   is False
    assert result.reachable is False
    assert result.reason    and "disabled" in result.reason


@pytest.mark.asyncio
async def test_heartbeat_returns_reachable_when_healthy(harold_on):
    with respx.mock(base_url="http://harold.test") as mock:
        mock.get("/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
        mock.get("/api/tools/").mock(return_value=httpx.Response(200, json=[
            {"slug": "wardstone-harold",       "name": "HAROLD",      "category": "Utility",
             "version": "0.1.0", "description": "HAROLD", "icon": "book-open"},
            {"slug": "_wardstone-harold-data", "name": "HAROLD-Data", "category": "Utility",
             "version": "0.1.0", "description": "", "icon": None},
        ]))
        result = await heartbeat()

    assert result.enabled   is True
    assert result.reachable is True
    assert result.version   == "0.1.0"
    assert result.response_time_ms is not None and result.response_time_ms >= 0


@pytest.mark.asyncio
async def test_heartbeat_returns_unreachable_on_connect_error(harold_on):
    with respx.mock(base_url="http://harold.test") as mock:
        mock.get("/health").mock(side_effect=httpx.ConnectError("ECONNREFUSED"))
        result = await heartbeat()

    assert result.enabled   is True
    assert result.reachable is False
    assert result.reason    and "unreachable" in result.reason.lower()
