"""ASTRA — HAROLD V2 proxy router (TDD-HAROLD-INT-002 Phase 3).

Mounted at ``/api/v1/harold``. Every HAROLD HTTP call from the browser
goes through this router so the browser never crosses origins (AD-4)
and timeout / auth policy lives in one place.

Endpoint conventions:
  * Every endpoint always returns HTTP 200 with a discriminated payload —
    ``{harold_available: true, data: ...}`` on success or
    ``{harold_available: false, reason: ...}`` on failure. Returning
    503 for "HAROLD is off" would force the UI to parse status codes,
    which doesn't compose with axios interceptors.
  * Two exceptions to that pattern:
      - ``/heartbeat`` returns a flat shape (``enabled``,
        ``reachable``, ``base_url`` ...) because the UI reads those
        fields directly on mount.
      - ``/parts/{id}/reconcile`` can still return 404 if the part
        doesn't exist (a real client error, not "HAROLD is off").
  * Auth via ``get_current_user``. HAROLD itself has no auth — this
    router is the ASTRA-side gate.
"""
from __future__ import annotations

import logging
from typing import Union

from fastapi import APIRouter, Depends, HTTPException, Path
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.models.catalog import CatalogPart
from app.schemas.harold import (
    FilenameValidationAvailable,
    FilenameValidationResult,
    HaroldHeartbeatResponse,
    HaroldSuggestRequest,
    HaroldSystemCode,
    HaroldUnavailable,
    HaroldValidateFilenameRequest,
    HaroldValidateRequest,
    ReconcileAvailable,
    ReconcileResult,
    SystemCodesAvailable,
    SystemCodesPayload,
    WpnParsedFields,
    WpnSuggestion,
    WpnSuggestionAvailable,
    WpnValidationAvailable,
    WpnValidationResult,
)
from app.services.auth import get_current_user
from app.services.harold import (
    HaroldUnavailableError,
    heartbeat as svc_heartbeat,
    issue_wpn_for_catalog_part,  # noqa: F401 - re-exported for catalog router
    list_system_codes as svc_list_system_codes,
    reconcile_pending_sync as svc_reconcile,
    suggest_wpn_for_part as svc_suggest,
    validate_filename_wpn as svc_validate_filename,
    validate_wpn as svc_validate_wpn,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/harold", tags=["HAROLD"])


# ─────────────────────────────────────────────────────────────────
#  GET /heartbeat — flat response, always 200
# ─────────────────────────────────────────────────────────────────


@router.get("/heartbeat", response_model=HaroldHeartbeatResponse)
async def get_heartbeat(
    current_user: User = Depends(get_current_user),
):
    """Probe HAROLD V2's ``/health``. Always returns 200; the
    ``enabled`` + ``reachable`` fields drive UI behavior. Used on
    mount in the pending-import review and the catalog list."""
    result = await svc_heartbeat()
    return HaroldHeartbeatResponse(**result)


# ─────────────────────────────────────────────────────────────────
#  GET /system-codes
# ─────────────────────────────────────────────────────────────────


@router.get(
    "/system-codes",
    response_model=Union[SystemCodesAvailable, HaroldUnavailable],
)
async def get_system_codes(
    current_user: User = Depends(get_current_user),
):
    """Pass-through to V2's ``/api/v1/system-codes``. Returns the
    21-code list (17 project-system + 4 library-category) for
    operator-facing UI dropdowns. Off / unreachable → structured
    unavailable envelope."""
    try:
        body = await svc_list_system_codes()
    except HaroldUnavailableError as exc:
        return HaroldUnavailable(reason=str(exc))

    raw_codes = body.get("codes") or []
    codes = [HaroldSystemCode(**c) for c in raw_codes if isinstance(c, dict)]
    return SystemCodesAvailable(
        data=SystemCodesPayload(codes=codes, total=int(body.get("total") or len(codes))),
    )


# ─────────────────────────────────────────────────────────────────
#  POST /suggest — class → system → next-available WPN
# ─────────────────────────────────────────────────────────────────


@router.post(
    "/suggest",
    response_model=Union[WpnSuggestionAvailable, HaroldUnavailable],
)
async def post_suggest(
    body: HaroldSuggestRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Map ``part_class`` via the AD-6 table → ``system_code`` →
    next-available WPN from V2's ``suggest`` endpoint.

    The service falls back to the local allocator when V2 is
    unreachable, so this endpoint normally returns
    ``WpnSuggestionAvailable`` with ``source`` annotating which path
    served the request. Service raises only on a hard error (e.g.
    completely missing fallback row), which we translate to the
    unavailable envelope.
    """
    try:
        result = await svc_suggest(db, body.part_class, hint=body.hint)
    except (HaroldUnavailableError, ValueError, RuntimeError) as exc:
        return HaroldUnavailable(reason=str(exc))
    return WpnSuggestionAvailable(data=WpnSuggestion(**result))


# ─────────────────────────────────────────────────────────────────
#  POST /validate — direct V2 validate
# ─────────────────────────────────────────────────────────────────


@router.post(
    "/validate",
    response_model=Union[WpnValidationAvailable, HaroldUnavailable],
)
async def post_validate(
    body: HaroldValidateRequest,
    current_user: User = Depends(get_current_user),
):
    """Format + ledger lookup via V2's ``/api/v1/wpn/validate``.

    ``is_valid_format=false`` is a NORMAL result (not an error) —
    callers want to see the malformed-WPN message and offer to fix
    it. Only network-level / 5xx failures hit the unavailable path.
    """
    try:
        body_json = await svc_validate_wpn(body.wpn)
    except HaroldUnavailableError as exc:
        return HaroldUnavailable(reason=str(exc))

    parsed = body_json.get("parsed")
    return WpnValidationAvailable(
        data=WpnValidationResult(
            wpn             = body_json.get("wpn") or body.wpn,
            is_valid_format = bool(body_json.get("is_valid_format")),
            is_issued       = bool(body_json.get("is_issued")),
            errors          = list(body_json.get("errors") or []),
            warnings        = list(body_json.get("warnings") or []),
            parsed          = (WpnParsedFields(**parsed)
                               if isinstance(parsed, dict) else None),
            ledger_entry    = body_json.get("ledger_entry"),
        ),
    )


# ─────────────────────────────────────────────────────────────────
#  POST /validate-filename — filename parse + optional V2 validate
# ─────────────────────────────────────────────────────────────────


@router.post(
    "/validate-filename",
    response_model=FilenameValidationAvailable,
)
async def post_validate_filename(
    body: HaroldValidateFilenameRequest,
    current_user: User = Depends(get_current_user),
):
    """Always returns an envelope with the structural parse.

    When the filename contains a Wardstone-format WPN AND HAROLD is
    reachable, ``wpn_validation`` is populated with the result of
    calling V2's validate. When HAROLD is down or off, the parse
    still comes back — ``wpn_validation`` is just ``None``.
    """
    result = await svc_validate_filename(body.filename)
    wpn_val_raw = result.get("wpn_validation")
    wpn_val: WpnValidationResult | None = None
    if isinstance(wpn_val_raw, dict):
        parsed = wpn_val_raw.get("parsed")
        wpn_val = WpnValidationResult(
            wpn             = wpn_val_raw.get("wpn") or "",
            is_valid_format = bool(wpn_val_raw.get("is_valid_format")),
            is_issued       = bool(wpn_val_raw.get("is_issued")),
            errors          = list(wpn_val_raw.get("errors") or []),
            warnings        = list(wpn_val_raw.get("warnings") or []),
            parsed          = (WpnParsedFields(**parsed)
                               if isinstance(parsed, dict) else None),
            ledger_entry    = wpn_val_raw.get("ledger_entry"),
        )
    return FilenameValidationAvailable(
        data=FilenameValidationResult(
            filename            = result.get("filename") or "",
            base_name           = result.get("base_name") or "",
            extension           = result.get("extension") or "",
            is_wardstone_format = bool(result.get("is_wardstone_format")),
            extracted_wpn       = result.get("extracted_wpn"),
            wpn_validation      = wpn_val,
        ),
    )


# ─────────────────────────────────────────────────────────────────
#  POST /parts/{part_id}/reconcile — manual "Sync with HAROLD"
# ─────────────────────────────────────────────────────────────────


@router.post(
    "/parts/{part_id}/reconcile",
    response_model=Union[ReconcileAvailable, HaroldUnavailable],
)
async def post_reconcile(
    part_id: int = Path(..., ge=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Manual sync trigger for a part with ``wpn_pending_sync=True``.

    Service attempts to register the part's current
    ``internal_part_number`` with HAROLD via ``issue_specific``. On
    409 (collision), falls through to a fresh ``issue`` allocation
    and updates the part's ``internal_part_number`` in-place.

    Returns 404 if the part doesn't exist. Returns the unavailable
    envelope if HAROLD is unreachable (the user retries when HAROLD
    is back).
    """
    part = (
        db.query(CatalogPart)
        .filter(CatalogPart.id == part_id)
        .one_or_none()
    )
    if part is None:
        raise HTTPException(
            status_code=404,
            detail=f"CatalogPart {part_id} not found",
        )

    try:
        result = await svc_reconcile(db, part)
    except HaroldUnavailableError as exc:
        db.rollback()
        return HaroldUnavailable(reason=str(exc))
    except Exception as exc:  # noqa: BLE001 - unexpected; roll back and surface
        db.rollback()
        logger.exception(
            "reconcile_pending_sync crashed for part_id=%s", part_id,
        )
        return HaroldUnavailable(reason=f"Internal reconcile error: {exc!s}")

    # Service mutates ``part`` in-place when it reconciles; commit so
    # internal_part_number / wpn_pending_sync changes persist alongside
    # the audit row.
    if result.get("reconciled"):
        try:
            db.commit()
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.exception(
                "reconcile commit failed for part_id=%s", part_id,
            )
            return HaroldUnavailable(reason=f"DB commit failed: {exc!s}")

    return ReconcileAvailable(data=ReconcileResult(**result))
