"""HAROLD V2 HTTP client.

Wraps V2's native REST surface at ``/api/v1/*``. One method per
endpoint we call. Each method:

  1. Builds the URL from ``settings.HAROLD_BASE_URL``.
  2. Uses ``httpx.AsyncClient`` opened per-call (low volume; not worth
     the long-lived-client shutdown complexity).
  3. Catches only the SPECIFIC httpx exceptions
     (``ConnectError``, ``TimeoutException``, ``HTTPError``) and
     re-raises as ``HaroldUnavailableError``. A bare ``Exception``
     would swallow real bugs in response parsing — see the
     historic gotcha #9 carried over from HAROLD-001.
  4. Maps 4xx responses to domain-specific exceptions
     (``HaroldDuplicateError`` on 409, ``HaroldValidationError`` on 422).
  5. Returns the parsed JSON dict on success.

V2's compat surface (``/api/tools/*``) is NOT used here — Phase 0
discovery confirmed V2's native REST is what we want. The prior
HAROLD-001 client targeted the WRENCH envelope and is gone.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

import httpx

from app.config import settings

from .errors import (
    HaroldDuplicateError,
    HaroldInvalidResponseError,
    HaroldUnavailableError,
    HaroldValidationError,
)

logger = logging.getLogger(__name__)


def _base_url() -> str:
    return settings.HAROLD_BASE_URL.rstrip("/")


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(settings.HAROLD_TIMEOUT_SECONDS)


async def _request(
    method: str,
    path: str,
    *,
    json: Optional[dict[str, Any]] = None,
    params: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Shared request helper. Returns parsed JSON on 2xx; raises the
    domain-specific exception otherwise."""
    url = f"{_base_url()}{path}"
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as http:
            resp = await http.request(method, url, json=json, params=params)
    except (httpx.TimeoutException, httpx.ConnectError) as exc:
        raise HaroldUnavailableError(f"HAROLD unreachable: {exc!s}") from exc
    except httpx.HTTPError as exc:
        # Other httpx errors (e.g. unexpected protocol failures) —
        # still surface as unavailable so the frontend renders the
        # graceful degradation path.
        raise HaroldUnavailableError(f"HAROLD HTTP error: {exc!s}") from exc

    if resp.status_code >= 500:
        logger.warning(
            "HAROLD %s %s returned %d: %s",
            method, path, resp.status_code, resp.text[:300],
        )
        raise HaroldUnavailableError(
            f"HAROLD returned HTTP {resp.status_code}",
        )
    if resp.status_code == 409:
        raise HaroldDuplicateError(
            f"HAROLD rejected duplicate: HTTP 409: {resp.text[:300]}",
        )
    if resp.status_code == 422:
        raise HaroldValidationError(
            f"HAROLD validation failed: HTTP 422: {resp.text[:300]}",
        )
    if resp.status_code >= 400:
        raise HaroldInvalidResponseError(
            f"HAROLD rejected request to {path}: HTTP {resp.status_code}: {resp.text[:300]}",
        )

    try:
        payload = resp.json()
    except ValueError as exc:
        raise HaroldInvalidResponseError(
            f"HAROLD returned non-JSON body for {path}: {exc!s}",
        ) from exc

    if not isinstance(payload, dict):
        raise HaroldInvalidResponseError(
            f"HAROLD response to {path} is not a JSON object",
        )
    return payload


# ── Heartbeat ───────────────────────────────────────────────────────


async def health() -> dict[str, Any]:
    """``GET /health``. Returns the parsed body
    ``{status, version, db}``."""
    return await _request("GET", "/health")


# ── System codes ────────────────────────────────────────────────────


async def list_system_codes() -> dict[str, Any]:
    """``GET /api/v1/system-codes``. Returns ``{codes: [...], total}``.

    21 codes (17 project-system + 4 library-category). The shape
    matches V2's ``SystemCodesResponse``.
    """
    return await _request("GET", "/api/v1/system-codes")


# ── Suggest ─────────────────────────────────────────────────────────


async def suggest(
    system_code: str,
    hint: Optional[str] = None,   # accepted for forward-compat; V2 ignores it
) -> dict[str, Any]:
    """``GET /api/v1/wpn/suggest?system_code=XX``.

    Returns ``{suggested_wpn, system_code, next_index, existing_count}``.
    V2 only consumes ``system_code`` today; ``hint`` is reserved for a
    future NL-aware variant.
    """
    params = {"system_code": system_code}
    # V2's current ``suggest`` doesn't accept ``hint`` — sending it
    # would return 422. Drop it on the wire but accept it in our
    # signature so callers in service.py don't have to special-case.
    _ = hint  # noqa: F841 - reserved for forward compatibility
    return await _request("GET", "/api/v1/wpn/suggest", params=params)


# ── Validate ────────────────────────────────────────────────────────


async def validate(wpn: str) -> dict[str, Any]:
    """``POST /api/v1/wpn/validate``. Returns
    ``{wpn, is_valid_format, is_issued, errors, warnings, parsed?}``.

    NB: this method does NOT raise ``HaroldValidationError`` when the
    body comes back with ``is_valid_format=false`` — that's a normal
    "no, this WPN is malformed" result the caller wants to see. The
    ``HaroldValidationError`` path triggers only on HTTP 422 (Pydantic
    rejected the request body itself).
    """
    return await _request("POST", "/api/v1/wpn/validate", json={"wpn": wpn})


# ── Issue ───────────────────────────────────────────────────────────


async def issue(
    system_code: str,
    *,
    origin_system: Optional[str] = None,
    origin_record_id: Optional[str] = None,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """``POST /api/v1/wpn/issue``. Auto-allocates the next WPN for
    ``system_code``, writes V2's ledger row, returns the row."""
    body: dict[str, Any] = {"system_code": system_code}
    if origin_system is not None:    body["origin_system"]    = origin_system
    if origin_record_id is not None: body["origin_record_id"] = origin_record_id
    if display_name is not None:     body["display_name"]     = display_name
    if description is not None:      body["description"]      = description
    if metadata is not None:         body["metadata"]         = metadata
    return await _request("POST", "/api/v1/wpn/issue", json=body)


async def issue_specific(
    wpn: str,
    *,
    origin_system: Optional[str] = None,
    origin_record_id: Optional[str] = None,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """``POST /api/v1/wpn/issue-specific``. Registers a caller-supplied
    WPN. Raises ``HaroldDuplicateError`` on 409 (WPN already issued).
    """
    body: dict[str, Any] = {"wpn": wpn}
    if origin_system is not None:    body["origin_system"]    = origin_system
    if origin_record_id is not None: body["origin_record_id"] = origin_record_id
    if display_name is not None:     body["display_name"]     = display_name
    if description is not None:      body["description"]      = description
    if metadata is not None:         body["metadata"]         = metadata
    return await _request("POST", "/api/v1/wpn/issue-specific", json=body)


# ── Ledger lookup ───────────────────────────────────────────────────


async def get_ledger_entry(wpn: str) -> dict[str, Any]:
    """``GET /api/v1/ledger/{wpn}``. 404 propagates as
    ``HaroldInvalidResponseError`` — callers map to "not found" in
    their own domain language."""
    return await _request("GET", f"/api/v1/ledger/{wpn}")
