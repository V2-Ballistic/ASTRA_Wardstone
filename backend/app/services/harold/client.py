"""HAROLD HTTP client — wraps WRENCH's tool-runs API.

TDD-HAROLD-001 Phase 2. Per the investigation report, HAROLD is hosted
inside the WRENCH framework at `HAROLD_BASE_URL`. Invocation is

    POST /api/tools/{slug}/runs   {"inputs": {...}}

Per Common Gotcha #2, `httpx.AsyncClient` opens per-call here — low
call volumes don't justify the long-lived-client shutdown complexity.

Per Common Gotcha #9, we catch the *specific* httpx exceptions only
(`HTTPError`, `TimeoutException`, `ConnectError`) and re-raise as
`HaroldUnavailableError`. A bare `Exception` would swallow real bugs
in response parsing.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings
from .errors import HaroldInvalidResponseError, HaroldUnavailableError

logger = logging.getLogger(__name__)


# WRENCH tool slugs (per `/api/tools` listing).
TOOL_HAROLD_DATA   = "_wardstone-harold-data"
TOOL_HAROLD_SEARCH = "_wardstone-harold-search"


def _base_url() -> str:
    return settings.HAROLD_BASE_URL.rstrip("/")


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(settings.HAROLD_TIMEOUT_SECONDS)


async def _post_run(slug: str, inputs: dict[str, Any]) -> dict[str, Any]:
    """POST /api/tools/{slug}/runs with {"inputs": inputs}. Returns
    the parsed RunResponse JSON. Raises HaroldUnavailableError on any
    network failure; HaroldInvalidResponseError on a malformed reply.
    """
    url = f"{_base_url()}/api/tools/{slug}/runs"
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as http:
            resp = await http.post(url, json={"inputs": inputs})
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        raise HaroldUnavailableError(f"HAROLD unreachable: {exc!s}") from exc
    except httpx.HTTPError as exc:
        raise HaroldUnavailableError(f"HAROLD HTTP error: {exc!s}") from exc

    if resp.status_code >= 500:
        # Server-side error inside WRENCH/HAROLD — log it but return
        # the structured "unreachable" to the UI per gotcha #12.
        logger.warning("HAROLD %s returned %d: %s", slug, resp.status_code, resp.text[:500])
        raise HaroldUnavailableError(
            f"HAROLD returned HTTP {resp.status_code}",
        )
    if resp.status_code >= 400:
        raise HaroldInvalidResponseError(
            f"HAROLD rejected request to {slug}: HTTP {resp.status_code}: {resp.text[:300]}",
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        raise HaroldInvalidResponseError(f"HAROLD returned non-JSON body: {exc!s}") from exc

    if not isinstance(payload, dict):
        raise HaroldInvalidResponseError("HAROLD run response is not a JSON object")
    if payload.get("success") is False:
        raise HaroldInvalidResponseError(
            f"HAROLD run reported failure: {payload.get('error') or 'unknown'}",
        )
    return payload


async def health() -> dict[str, Any]:
    """GET /health. Fast probe used by the heartbeat path. Raises
    HaroldUnavailableError if HAROLD doesn't respond."""
    url = f"{_base_url()}/health"
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as http:
            resp = await http.get(url)
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        raise HaroldUnavailableError(f"HAROLD unreachable: {exc!s}") from exc
    except httpx.HTTPError as exc:
        raise HaroldUnavailableError(f"HAROLD HTTP error: {exc!s}") from exc

    if resp.status_code != 200:
        raise HaroldUnavailableError(
            f"HAROLD /health returned HTTP {resp.status_code}",
        )
    try:
        return resp.json() if resp.content else {}
    except ValueError:
        return {}


async def list_tools() -> list[dict[str, Any]]:
    """GET /api/tools/. Used by the heartbeat path to extract the
    HAROLD plugin's `version`. Returns the raw list verbatim."""
    url = f"{_base_url()}/api/tools/"
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as http:
            resp = await http.get(url, follow_redirects=True)
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        raise HaroldUnavailableError(f"HAROLD unreachable: {exc!s}") from exc
    except httpx.HTTPError as exc:
        raise HaroldUnavailableError(f"HAROLD HTTP error: {exc!s}") from exc

    if resp.status_code != 200:
        raise HaroldUnavailableError(
            f"HAROLD /api/tools returned HTTP {resp.status_code}",
        )
    try:
        return resp.json() or []
    except ValueError:
        return []


async def search(query: str, allow_llm_refine: bool = True) -> dict[str, Any]:
    """Invoke `_wardstone-harold-search`. Returns the `output` block
    of the run response."""
    payload = await _post_run(TOOL_HAROLD_SEARCH, {
        "query": query,
        "allow_llm_refine": allow_llm_refine,
    })
    output = payload.get("output")
    if not isinstance(output, dict):
        raise HaroldInvalidResponseError("HAROLD search returned no output object")
    return output


async def data(section: str) -> dict[str, Any]:
    """Invoke `_wardstone-harold-data`. Returns the `payload` sub-block
    of the output (i.e. the actual reference-data dict for that section)."""
    raw = await _post_run(TOOL_HAROLD_DATA, {"section": section})
    output = raw.get("output")
    if not isinstance(output, dict):
        raise HaroldInvalidResponseError("HAROLD data returned no output object")
    payload = output.get("payload")
    if not isinstance(payload, dict):
        raise HaroldInvalidResponseError("HAROLD data output missing 'payload'")
    return payload
