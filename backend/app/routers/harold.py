"""ASTRA — HAROLD proxy router (TDD-HAROLD-001 Phase 3, Path A)
=================================================================

Mounted at `/api/v1/harold`. All HTTP traffic to HAROLD originates
here so the browser never crosses origins (gotcha #3 — keep CORS out
of HAROLD's problem space) and all auth / timeout / retry policy
lives in one place (AD-8).

Endpoint conventions:
  * Every endpoint always returns HTTP 200 with a discriminated
    payload — `{harold_available: true, data: …}` on success or
    `{harold_available: false, reason: …}` on failure. Returning 503
    for "HAROLD is off" would force the UI to parse status codes,
    which doesn't compose with axios interceptors (gotcha-driven
    decision; see prompt §3.1 + AD-2).
  * Auth via the standard `get_current_user` dependency. HAROLD itself
    has no auth — this router is the ASTRA-side gate.
"""

from __future__ import annotations

import logging
from typing import Union

from fastapi import APIRouter, Depends, Query

from app.models import User
from app.schemas.harold import (
    HaroldHeartbeatResponse, HaroldUnavailable,
    HaroldSystemCode, SystemCodesAvailable, SystemCodesPayload,
    WpnSuggestion, WpnSuggestionAvailable,
)
from app.services.auth import get_current_user
from app.services.harold import (
    HaroldUnavailableError,
    heartbeat as svc_heartbeat,
    list_system_codes as svc_list_system_codes,
    suggest_wpn_from_text as svc_suggest_wpn,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/harold", tags=["HAROLD"])


# ─────────────────────────────────────────────────────────────────
#  /heartbeat
# ─────────────────────────────────────────────────────────────────

@router.get("/heartbeat", response_model=HaroldHeartbeatResponse)
async def get_heartbeat(
    current_user: User = Depends(get_current_user),
):
    """Always 200. `enabled` + `reachable` + `response_time_ms` tell the
    UI whether to render HAROLD affordances. Used on mount in the new
    part page and the project settings page."""
    result = await svc_heartbeat()
    return HaroldHeartbeatResponse(
        enabled          = result.enabled,
        reachable        = result.reachable,
        base_url         = result.base_url,
        response_time_ms = result.response_time_ms,
        version          = result.version,
        reason           = result.reason,
    )


# ─────────────────────────────────────────────────────────────────
#  /system-codes
# ─────────────────────────────────────────────────────────────────

@router.get(
    "/system-codes",
    response_model=Union[SystemCodesAvailable, HaroldUnavailable],
)
async def get_system_codes(
    current_user: User = Depends(get_current_user),
):
    """Returns HAROLD's 17 system codes (AV / ST / TH / …) for the
    catalog-new-part dropdown. Off → structured-unavailable."""
    try:
        codes = await svc_list_system_codes()
    except HaroldUnavailableError as exc:
        return HaroldUnavailable(reason=str(exc))

    return SystemCodesAvailable(
        data=SystemCodesPayload(
            codes=[
                HaroldSystemCode(
                    code=c.code, name=c.name, description=c.description,
                ) for c in codes
            ],
        ),
    )


# ─────────────────────────────────────────────────────────────────
#  /suggest-wpn
# ─────────────────────────────────────────────────────────────────

@router.get(
    "/suggest-wpn",
    response_model=Union[WpnSuggestionAvailable, HaroldUnavailable],
)
async def suggest_wpn(
    query: str = Query(
        ..., min_length=1, max_length=2000,
        description=(
            "Free-text description of the part (name + class label) "
            "fed to HAROLD's NL pattern matcher. NOT a system code."
        ),
    ),
    allow_llm_refine: bool = Query(
        True,
        description="Allow HAROLD to refine via its LLM (slower, higher quality).",
    ),
    current_user: User = Depends(get_current_user),
):
    """Proxy to `_wardstone-harold-search`. Returns a single
    pattern-matched WPN suggestion + confidence + reasoning. The UI
    pre-fills the part_number field on accept."""
    try:
        result = await svc_suggest_wpn(query=query, allow_llm_refine=allow_llm_refine)
    except HaroldUnavailableError as exc:
        return HaroldUnavailable(reason=str(exc))

    return WpnSuggestionAvailable(
        data=WpnSuggestion(
            suggestion       = result.suggestion,
            pattern_id       = result.pattern_id,
            pattern_label    = result.pattern_label,
            confidence       = result.confidence,
            reasoning        = result.reasoning,
            extracted_fields = result.extracted_fields,
            candidates       = result.candidates,
            notes            = result.notes,
            llm_used         = result.llm_used,
        ),
    )
