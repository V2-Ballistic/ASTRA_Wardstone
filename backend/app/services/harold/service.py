"""HAROLD service layer — higher-level functions consumed by the router.

TDD-HAROLD-001 Phase 2 (Path A). The functions here wrap the raw client
calls in Pydantic-like dataclasses, enforce the feature flag, and
measure heartbeat latency.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Optional

from app.config import settings
from . import client as harold_client
from .errors import HaroldUnavailableError


# ── Dataclasses (router converts these into Pydantic responses) ──

@dataclass
class HeartbeatResult:
    enabled:           bool
    reachable:         bool
    base_url:          str
    response_time_ms:  Optional[int] = None
    version:           Optional[str] = None
    reason:            Optional[str] = None


@dataclass
class SystemCode:
    code:        str
    name:        str
    description: str


@dataclass
class WpnSuggestion:
    suggestion:        str
    pattern_id:        str
    pattern_label:     str
    confidence:        float
    reasoning:         str
    extracted_fields:  dict[str, str]
    candidates:        list[dict]
    notes:             list[str]
    llm_used:          Optional[str] = None


def is_enabled() -> bool:
    """Single source of truth for the feature flag."""
    return bool(settings.HAROLD_INTEGRATION_ENABLED)


# ── Public service functions ─────────────────────────────────────

async def heartbeat() -> HeartbeatResult:
    """Probe HAROLD's `/health` endpoint. Always returns a result —
    never raises. The structured result tells the router whether to
    expose HAROLD affordances in the UI."""
    base = settings.HAROLD_BASE_URL
    if not is_enabled():
        return HeartbeatResult(
            enabled=False, reachable=False, base_url=base,
            reason="HAROLD integration disabled (HAROLD_INTEGRATION_ENABLED=false)",
        )
    started = time.perf_counter()
    try:
        await harold_client.health()
    except HaroldUnavailableError as exc:
        return HeartbeatResult(
            enabled=True, reachable=False, base_url=base, reason=str(exc),
        )
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    # Extract the HAROLD plugin version from /api/tools (best effort —
    # not fatal if missing).
    version: Optional[str] = None
    try:
        tools = await harold_client.list_tools()
        for t in tools or []:
            slug = t.get("slug")
            if slug in ("wardstone-harold", "_wardstone-harold-data"):
                version = t.get("version")
                if slug == "wardstone-harold":
                    break
    except HaroldUnavailableError:
        # /health worked but /api/tools failed — still call us reachable
        pass

    return HeartbeatResult(
        enabled=True, reachable=True, base_url=base,
        response_time_ms=elapsed_ms, version=version,
    )


async def list_system_codes() -> list[SystemCode]:
    """Fetch HAROLD's 17 system codes. Raises HaroldUnavailableError
    when the flag is off — callers should treat that as soft
    unavailable, not a 500."""
    if not is_enabled():
        raise HaroldUnavailableError("HAROLD integration disabled")
    payload = await harold_client.data("systems")
    raw_list = payload.get("systems") or []
    result: list[SystemCode] = []
    for row in raw_list:
        if not isinstance(row, dict):
            continue
        code = (row.get("code") or "").upper()
        if not code:
            continue
        result.append(SystemCode(
            code=code,
            name=row.get("name") or "",
            description=row.get("description") or "",
        ))
    return result


async def suggest_wpn_from_text(
    query: str,
    allow_llm_refine: bool = True,
) -> WpnSuggestion:
    """Invoke HAROLD's NL search and pack into a typed result.

    The prompt's original "next-WPN allocator" model doesn't match
    HAROLD's real surface — Search is an NL pattern matcher. Callers
    pass a free-text description (e.g. catalog part's name + class)
    and get a single pattern-matched suggestion back.
    """
    if not is_enabled():
        raise HaroldUnavailableError("HAROLD integration disabled")
    raw = await harold_client.search(query=query, allow_llm_refine=allow_llm_refine)
    return WpnSuggestion(
        suggestion       = str(raw.get("suggestion") or ""),
        pattern_id       = str(raw.get("pattern_id") or ""),
        pattern_label    = str(raw.get("pattern_label") or ""),
        confidence       = float(raw.get("confidence") or 0.0),
        reasoning        = str(raw.get("reasoning") or ""),
        extracted_fields = dict(raw.get("extracted_fields") or {}),
        candidates       = list(raw.get("candidates") or []),
        notes            = list(raw.get("notes") or []),
        llm_used         = raw.get("llm_used"),
    )
