"""ASTRA-TDD-HAROLD-001 Phase 3 — router tests.

Verifies the discriminated `{harold_available: …}` envelope on every
endpoint and the graceful-degradation path (HAROLD off / 500 / connect
error). HAROLD itself is fully mocked via respx.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.config import settings


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
#  /heartbeat — always 200, never raises
# ─────────────────────────────────────────────────────────────────

def test_heartbeat_disabled_returns_structured_payload(
    client, auth_headers, harold_off,
):
    r = client.get("/api/v1/harold/heartbeat", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["enabled"]   is False
    assert body["reachable"] is False
    assert body["base_url"]  == "http://harold.test"
    assert body["reason"]    and "disabled" in body["reason"]


def test_heartbeat_reachable_returns_version_and_latency(
    client, auth_headers, harold_on,
):
    with respx.mock(base_url="http://harold.test") as mock:
        mock.get("/health").mock(return_value=httpx.Response(200, json={"status": "ok"}))
        mock.get("/api/tools/").mock(return_value=httpx.Response(200, json=[
            {"slug": "wardstone-harold", "name": "HAROLD", "category": "Utility",
             "version": "0.1.0", "description": "HAROLD", "icon": "book-open"},
        ]))
        r = client.get("/api/v1/harold/heartbeat", headers=auth_headers)

    assert r.status_code == 200
    body = r.json()
    assert body["enabled"]   is True
    assert body["reachable"] is True
    assert body["version"]   == "0.1.0"
    assert body["response_time_ms"] is not None


def test_heartbeat_unreachable_returns_structured_payload(
    client, auth_headers, harold_on,
):
    with respx.mock(base_url="http://harold.test") as mock:
        mock.get("/health").mock(side_effect=httpx.ConnectError("ECONNREFUSED"))
        r = client.get("/api/v1/harold/heartbeat", headers=auth_headers)

    assert r.status_code == 200
    body = r.json()
    assert body["enabled"]   is True
    assert body["reachable"] is False
    assert body["reason"]    and "unreachable" in body["reason"].lower()


# ─────────────────────────────────────────────────────────────────
#  /system-codes
# ─────────────────────────────────────────────────────────────────

def test_system_codes_off_returns_unavailable_envelope(
    client, auth_headers, harold_off,
):
    r = client.get("/api/v1/harold/system-codes", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    assert body["harold_available"] is False
    assert "disabled" in body["reason"]


def test_system_codes_proxies_payload_on_success(
    client, auth_headers, harold_on,
):
    with respx.mock(base_url="http://harold.test") as mock:
        mock.post("/api/tools/_wardstone-harold-data/runs").mock(
            return_value=httpx.Response(200, json={
                "runId": "x", "slug": "_wardstone-harold-data",
                "inputs": {"section": "systems"},
                "output": {
                    "section": "systems",
                    "payload": {"systems": [
                        {"code": "AV", "name": "Avionics - Hardware",
                         "description": "Flight computers."},
                        {"code": "ST", "name": "Structures",
                         "description": "Primary structure."},
                    ]},
                },
                "success": True, "elapsed_ms": 0, "error": None,
                "created_at": "2026-05-11T20:00:00",
            }),
        )
        r = client.get("/api/v1/harold/system-codes", headers=auth_headers)

    assert r.status_code == 200
    body = r.json()
    assert body["harold_available"] is True
    codes = body["data"]["codes"]
    assert {c["code"] for c in codes} == {"AV", "ST"}


def test_system_codes_degrades_on_harold_500(
    client, auth_headers, harold_on,
):
    with respx.mock(base_url="http://harold.test") as mock:
        mock.post("/api/tools/_wardstone-harold-data/runs").mock(
            return_value=httpx.Response(500, text="upstream"),
        )
        r = client.get("/api/v1/harold/system-codes", headers=auth_headers)

    assert r.status_code == 200
    body = r.json()
    assert body["harold_available"] is False
    assert "HTTP 500" in body["reason"]


# ─────────────────────────────────────────────────────────────────
#  /suggest-wpn
# ─────────────────────────────────────────────────────────────────

def test_suggest_wpn_proxies_correctly(client, auth_headers, harold_on):
    with respx.mock(base_url="http://harold.test") as mock:
        mock.post("/api/tools/_wardstone-harold-search/runs").mock(
            return_value=httpx.Response(200, json={
                "runId": "x", "slug": "_wardstone-harold-search",
                "inputs": {"query": "avionics processor", "allow_llm_refine": True},
                "output": {
                    "suggestion":       "WS-AV-P1000-A",
                    "pattern_id":       "cad_part",
                    "pattern_label":    "CAD part",
                    "confidence":       0.57,
                    "reasoning":        "CAD part pattern…",
                    "extracted_fields": {"SYS": "AV"},
                    "glossary_matches": [],
                    "candidates":       [],
                    "notes":            [],
                    "llm_used":         "ollama:llama3.2",
                },
                "success": True, "elapsed_ms": 1234, "error": None,
                "created_at": "2026-05-11T20:00:00",
            }),
        )
        r = client.get(
            "/api/v1/harold/suggest-wpn?query=avionics+processor",
            headers=auth_headers,
        )

    assert r.status_code == 200
    body = r.json()
    assert body["harold_available"] is True
    assert body["data"]["suggestion"] == "WS-AV-P1000-A"
    assert body["data"]["confidence"] == pytest.approx(0.57)
    assert body["data"]["llm_used"]   == "ollama:llama3.2"


def test_suggest_wpn_requires_query(client, auth_headers, harold_on):
    r = client.get("/api/v1/harold/suggest-wpn", headers=auth_headers)
    # FastAPI validation — missing required query param.
    assert r.status_code == 422


def test_suggest_wpn_degrades_when_disabled(
    client, auth_headers, harold_off,
):
    r = client.get(
        "/api/v1/harold/suggest-wpn?query=something", headers=auth_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["harold_available"] is False


def test_endpoints_require_auth(client, harold_on):
    """The three /harold/* endpoints all sit behind get_current_user."""
    assert client.get("/api/v1/harold/heartbeat").status_code         == 401
    assert client.get("/api/v1/harold/system-codes").status_code      == 401
    assert client.get(
        "/api/v1/harold/suggest-wpn?query=anything",
    ).status_code == 401
