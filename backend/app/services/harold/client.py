"""HAROLD HTTP client — now targeting WRENCH at :8030.

HAROLD-IN-WRENCH-001 Phase 6: V2 standalone at :8031 is on its way
out (Phase 7 decommission). HAROLD now lives inside the WRENCH
chassis at :8030 as a plugin and exposes its REST surface under
``/api/tools/wardstone-harold/*``. This client cut over from the
old V2-native URLs (``/api/v1/<thing>``) to the new chassis-mounted
URLs (``/api/tools/wardstone-harold/<thing>``). Request/response
shapes are byte-for-byte identical — only the URL prefix changed.

One method per endpoint we call. Each method:

  1. Builds the URL from ``settings.HAROLD_BASE_URL`` (default now
     ``http://host.docker.internal:8030``, WRENCH's api port).
  2. Uses ``httpx.AsyncClient`` opened per-call (low volume; not
     worth the long-lived-client shutdown complexity).
  3. Catches only the SPECIFIC httpx exceptions
     (``ConnectError``, ``TimeoutException``, ``HTTPError``) and
     re-raises as ``HaroldUnavailableError``. A bare ``Exception``
     would swallow real bugs in response parsing — see the
     historic gotcha #9 carried over from HAROLD-001.
  4. Maps 4xx responses to domain-specific exceptions
     (``HaroldDuplicateError`` on 409, ``HaroldValidationError`` on 422).
  5. Returns the parsed JSON dict on success.
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
    return await _request("GET", "/api/tools/wardstone-harold/system-codes")


async def register_system_code(
    code: str,
    name: str,
    category: str = "engineering",
    description: Optional[str] = None,
) -> dict[str, Any]:
    """``POST /api/tools/wardstone-harold/system-codes``. Idempotent
    registration: HAROLD answers 201 ``{..., created: true}`` for a
    brand-new code and 200 ``{..., created: false}`` when the code
    already exists — both land here as the parsed body. 422 (codes
    must be 2–3 uppercase letters) maps to ``HaroldValidationError``.
    """
    body: dict[str, Any] = {"code": code, "name": name, "category": category}
    if description is not None:
        body["description"] = description
    return await _request(
        "POST", "/api/tools/wardstone-harold/system-codes", json=body,
    )


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
    return await _request("GET", "/api/tools/wardstone-harold/wpn/suggest", params=params)


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
    return await _request("POST", "/api/tools/wardstone-harold/wpn/validate", json={"wpn": wpn})


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
    return await _request("POST", "/api/tools/wardstone-harold/wpn/issue", json=body)


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
    return await _request("POST", "/api/tools/wardstone-harold/wpn/issue-specific", json=body)


# ── Revise ──────────────────────────────────────────────────────────


async def revise(
    wpn: str,
    *,
    origin_system: Optional[str] = None,
    origin_record_id: Optional[str] = None,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """``POST /api/tools/wardstone-harold/wpn/{wpn}/revise``. Issues a
    new ledger entry for the SAME index with the next revision letter
    (A→B→C…). 404 (unknown base WPN) maps to
    ``HaroldInvalidResponseError``; 409 (revision letters exhausted)
    maps to ``HaroldDuplicateError``."""
    body: dict[str, Any] = {}
    if origin_system is not None:    body["origin_system"]    = origin_system
    if origin_record_id is not None: body["origin_record_id"] = origin_record_id
    if display_name is not None:     body["display_name"]     = display_name
    if description is not None:      body["description"]      = description
    if metadata is not None:         body["metadata"]         = metadata
    return await _request(
        "POST", f"/api/tools/wardstone-harold/wpn/{wpn}/revise", json=body,
    )


# ── Patch (annotate ledger entry) ───────────────────────────────────


async def patch_wpn(
    wpn: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """``PATCH /api/tools/wardstone-harold/wpn/{wpn}``. Partial update
    of a ledger entry; HAROLD merges ``metadata`` into the existing
    entry's metadata server-side. Returns the updated entry."""
    body: dict[str, Any] = {}
    if display_name is not None: body["display_name"] = display_name
    if description is not None:  body["description"]  = description
    if metadata is not None:     body["metadata"]     = metadata
    return await _request(
        "PATCH", f"/api/tools/wardstone-harold/wpn/{wpn}", json=body,
    )


# ── Delete (release a WPN) ──────────────────────────────────────────


async def delete_wpn(
    wpn: str,
    *,
    actor: Optional[str] = None,
    reason: Optional[str] = None,
) -> dict[str, Any]:
    """``DELETE /api/tools/wardstone-harold/wpn/{wpn}``. The release
    path for failed persistence — HAROLD reclaims the index so the
    sequence stays gapless. Returns
    ``{deleted_wpn, reclaimed, new_next_index}``."""
    params: dict[str, Any] = {}
    if actor is not None:  params["actor"]  = actor
    if reason is not None: params["reason"] = reason
    return await _request(
        "DELETE", f"/api/tools/wardstone-harold/wpn/{wpn}",
        params=params or None,
    )


# ── Ledger lookup ───────────────────────────────────────────────────


async def get_ledger_entry(wpn: str) -> dict[str, Any]:
    """``GET /api/v1/ledger/{wpn}``. 404 propagates as
    ``HaroldInvalidResponseError`` — callers map to "not found" in
    their own domain language."""
    return await _request("GET", f"/api/tools/wardstone-harold/ledger/{wpn}")


async def list_ledger(
    system_code: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
) -> dict[str, Any]:
    """``GET /api/tools/wardstone-harold/ledger``. Filtered, paginated
    ledger listing. Returns ``{items, total, skip, limit}``."""
    params: dict[str, Any] = {"skip": skip, "limit": limit}
    if system_code is not None: params["system_code"] = system_code
    if status is not None:      params["status"]      = status
    if q is not None:           params["q"]           = q
    return await _request(
        "GET", "/api/tools/wardstone-harold/ledger", params=params,
    )


# ── Filename precheck ───────────────────────────────────────────────


async def filename_precheck(
    filename: str,
    intended_part_class: Optional[str] = None,
) -> dict[str, Any]:
    """``POST /api/tools/wardstone-harold/filename-precheck``. HAROLD
    decides the canonical name for a candidate filename. Returns the
    precheck verdict body verbatim."""
    body: dict[str, Any] = {"filename": filename}
    if intended_part_class is not None:
        body["intended_part_class"] = intended_part_class
    return await _request(
        "POST", "/api/tools/wardstone-harold/filename-precheck", json=body,
    )
