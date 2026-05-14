"""HAROLD V2 high-level service layer.

Phase 2 entry points called by Phase 3's ``/api/v1/harold/*`` proxy
router and by the catalog upload/approval handlers:

  heartbeat                      — / health probe; never raises.
  suggest_wpn_for_part           — class-aware suggest, falls back to
                                    local allocator when HAROLD is down.
  validate_filename_wpn          — pure-regex filename inspection +
                                    optional HAROLD validate when a
                                    Wardstone-style WPN is extracted.
  validate_wpn                   — direct HAROLD validate of a string.
  issue_wpn_for_catalog_part     — three-branch approval (AD-11):
                                    1. caller-supplied → issue_specific
                                    2. auto, HAROLD up → issue
                                    3. auto, HAROLD down → fallback +
                                       wpn_pending_sync=True
  reconcile_pending_sync         — manual "Sync with HAROLD" path for
                                    a part with wpn_pending_sync=True.

All functions are best-effort wrt HAROLD availability — they either
return a structured "unavailable" result or fall through to the local
allocator. The router never needs to interpret HTTP status codes from
HAROLD; the service translates them all into typed exceptions and
domain dicts.
"""
from __future__ import annotations

import logging
import time
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.models.catalog import CatalogPart

from . import client as harold_client
from . import fallback
from .class_to_system import (
    PART_CLASS_TO_SYSTEM_CODE,
    SYSTEM_CODE_LABELS,
    map_class_to_system,
)
from .errors import (
    HaroldDuplicateError,
    HaroldInvalidResponseError,
    HaroldUnavailableError,
    HaroldValidationError,
)
from .filename_validator import (
    FilenameValidationResult,
    extract_wpn_from_filename,
    validate_filename,
)

logger = logging.getLogger(__name__)


# ── Feature-flag gate ──────────────────────────────────────────────


def is_enabled() -> bool:
    """Single source of truth for ``HAROLD_INTEGRATION_ENABLED``."""
    return bool(settings.HAROLD_INTEGRATION_ENABLED)


# ── Heartbeat ──────────────────────────────────────────────────────


async def heartbeat() -> dict[str, Any]:
    """Probe V2's ``/health``. Always returns a dict — never raises.

    Result shape (matches ``schemas.harold.HaroldHeartbeatResponse``):
      {enabled, reachable, base_url, response_time_ms?, version?, reason?}
    """
    base = settings.HAROLD_BASE_URL
    if not is_enabled():
        return {
            "enabled":          False,
            "reachable":        False,
            "base_url":         base,
            "response_time_ms": None,
            "version":          None,
            "reason":           "HAROLD integration disabled "
                                "(HAROLD_INTEGRATION_ENABLED=false)",
        }
    started = time.perf_counter()
    try:
        body = await harold_client.health()
    except HaroldUnavailableError as exc:
        return {
            "enabled":          True,
            "reachable":        False,
            "base_url":         base,
            "response_time_ms": None,
            "version":          None,
            "reason":           str(exc),
        }
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return {
        "enabled":          True,
        "reachable":        True,
        "base_url":         base,
        "response_time_ms": elapsed_ms,
        "version":          body.get("version"),
        "reason":           None,
    }


# ── Suggest ────────────────────────────────────────────────────────


async def suggest_wpn_for_part(
    db: Session,
    part_class: str,
    *,
    hint: Optional[str] = None,
) -> dict[str, Any]:
    """Class → system_code → next-available WPN.

    Three paths:

      1. HAROLD off (flag false) → fallback-dry-run, source=fallback.
      2. HAROLD up → V2's ``GET /api/v1/wpn/suggest``, source=harold.
      3. HAROLD down → fallback-dry-run, source=fallback,
         reason populated.

    The result is always a dict with the same keys (matches
    ``schemas.harold.WpnSuggestion``).
    ``dry_run`` semantics: the suggest call never advances any counter
    in either system — the caller commits on approval, not on suggest.
    """
    system_code = map_class_to_system(part_class)

    if not is_enabled():
        wpn, _ = fallback.allocate_for_part_class(db, part_class, dry_run=True)
        return {
            "suggested_wpn":  wpn,
            "system_code":    system_code,
            "next_index":     int(wpn.split("-P")[1].split("-")[0]),
            "existing_count": 0,
            "source":         "fallback",
            "reason":         "HAROLD integration disabled",
        }

    try:
        body = await harold_client.suggest(system_code, hint=hint)
    except HaroldUnavailableError as exc:
        logger.warning("suggest: HAROLD unavailable: %s", exc)
        wpn, _ = fallback.allocate_for_part_class(db, part_class, dry_run=True)
        return {
            "suggested_wpn":  wpn,
            "system_code":    system_code,
            "next_index":     int(wpn.split("-P")[1].split("-")[0]),
            "existing_count": 0,
            "source":         "fallback",
            "reason":         f"HAROLD unavailable: {exc!s}",
        }
    except (HaroldInvalidResponseError, HaroldValidationError) as exc:
        logger.error("suggest: HAROLD returned malformed response: %s", exc)
        wpn, _ = fallback.allocate_for_part_class(db, part_class, dry_run=True)
        return {
            "suggested_wpn":  wpn,
            "system_code":    system_code,
            "next_index":     int(wpn.split("-P")[1].split("-")[0]),
            "existing_count": 0,
            "source":         "fallback",
            "reason":         f"HAROLD response malformed: {exc!s}",
        }

    return {
        "suggested_wpn":  body.get("suggested_wpn") or "",
        "system_code":    body.get("system_code") or system_code,
        "next_index":     int(body.get("next_index") or 0),
        "existing_count": int(body.get("existing_count") or 0),
        "source":         "harold",
        "reason":         None,
    }


# ── Validate (raw WPN string) ──────────────────────────────────────


async def validate_wpn(wpn: str) -> dict[str, Any]:
    """Direct HAROLD validate. Returns the parsed body verbatim plus
    a ``source`` annotation. Raises ``HaroldUnavailableError`` only
    when HAROLD itself is unreachable — a body with
    ``is_valid_format=false`` is a normal "no, that's not a valid
    WPN" result and comes back to the caller as-is.
    """
    if not is_enabled():
        raise HaroldUnavailableError("HAROLD integration disabled")
    return await harold_client.validate(wpn)


# ── Validate filename ──────────────────────────────────────────────


async def validate_filename_wpn(filename: str) -> dict[str, Any]:
    """Pure-regex parse + optional HAROLD validate on the extracted
    WPN. Returns a dict matching ``schemas.harold.FilenameValidationResult``.

    Two cases:
      1. Filename doesn't contain a Wardstone-format WPN →
         ``is_wardstone_format=False`` and no HAROLD call.
      2. Filename contains a WPN → call HAROLD's validate on it; the
         result lands under ``wpn_validation``.

    HAROLD unavailability in case 2 is non-fatal — we return the
    structural parse with ``wpn_validation=None`` so the caller can
    decide what to do.
    """
    parsed: FilenameValidationResult = validate_filename(filename)
    out: dict[str, Any] = {
        "filename":            parsed.filename,
        "base_name":           parsed.base_name,
        "extension":           parsed.extension,
        "is_wardstone_format": parsed.is_wardstone_format,
        "extracted_wpn":       parsed.extracted_wpn,
        "wpn_validation":      None,
    }
    if not parsed.is_wardstone_format or not parsed.extracted_wpn:
        return out
    if not is_enabled():
        return out

    try:
        out["wpn_validation"] = await harold_client.validate(parsed.extracted_wpn)
    except HaroldUnavailableError as exc:
        logger.info(
            "validate_filename_wpn: HAROLD unavailable for %s: %s",
            parsed.extracted_wpn, exc,
        )
    except (HaroldInvalidResponseError, HaroldValidationError) as exc:
        logger.warning(
            "validate_filename_wpn: HAROLD response malformed for %s: %s",
            parsed.extracted_wpn, exc,
        )
    return out


# ── Issue (the approval-time call) ─────────────────────────────────


async def issue_wpn_for_catalog_part(
    db: Session,
    part: CatalogPart,
    *,
    supplied_wpn: Optional[str] = None,
    actor: Optional[str] = None,
) -> tuple[str, str, bool]:
    """Assign a WPN to ``part``. Three-branch implementation per AD-11.

    Returns ``(wpn, source, pending_sync)``:
      - ``wpn``           the assigned WPN string
      - ``source``        ``"harold-specific"``, ``"harold-auto"``, or ``"fallback"``
      - ``pending_sync``  ``True`` iff the WPN came from the local
                          fallback allocator and needs reconciliation
                          when HAROLD comes back

    The caller MUST set ``part.internal_part_number = wpn`` and, if
    ``pending_sync`` is True, ``part.wpn_pending_sync = True``. Caller
    owns the transaction (commit happens at the boundary).

    Raises:
      - ``HaroldDuplicateError`` when supplied_wpn collides in HAROLD's
        ledger (409 from issue-specific).
      - ``HaroldValidationError`` when supplied_wpn is malformed
        (422 from issue-specific).
      - ``ValueError`` when supplied_wpn is empty/whitespace but the
        caller asked for issue-specific.
    """
    origin_record_id = str(part.id) if part.id is not None else None
    display_name = part.name or part.part_number or "(unnamed)"
    description = part.description

    # ── Branch 1: caller supplied a WPN ──
    if supplied_wpn:
        if not is_enabled():
            # Special case: the flag is off, but the caller asked
            # for a specific WPN. We can't register with HAROLD —
            # apply the value locally and mark pending_sync so a
            # later reconcile will register it.
            return (supplied_wpn, "fallback", True)
        try:
            await harold_client.issue_specific(
                supplied_wpn,
                origin_system="astra",
                origin_record_id=origin_record_id,
                display_name=display_name,
                description=description,
            )
            return (supplied_wpn, "harold-specific", False)
        except HaroldUnavailableError as exc:
            logger.warning(
                "issue_specific: HAROLD unavailable for %s; applying "
                "locally with pending_sync=true: %s",
                supplied_wpn, exc,
            )
            return (supplied_wpn, "fallback", True)

    # ── Branch 2: auto-allocate, HAROLD up ──
    if is_enabled():
        try:
            body = await harold_client.issue(
                map_class_to_system(part.part_class.value if part.part_class else ""),
                origin_system="astra",
                origin_record_id=origin_record_id,
                display_name=display_name,
                description=description,
            )
            wpn = body.get("wpn") or ""
            if not wpn:
                raise HaroldInvalidResponseError(
                    "HAROLD issue returned empty wpn"
                )
            return (wpn, "harold-auto", False)
        except HaroldUnavailableError as exc:
            logger.warning(
                "issue: HAROLD unavailable; falling back to local "
                "allocator: %s", exc,
            )
        except (HaroldInvalidResponseError, HaroldValidationError) as exc:
            logger.error("issue: HAROLD response malformed: %s", exc)

    # ── Branch 3: auto-allocate, HAROLD down (or flag off) ──
    pc = part.part_class.value if part.part_class else ""
    wpn, _ = fallback.allocate_for_part_class(db, pc, dry_run=False)
    return (wpn, "fallback", True)


# ── Reconcile (manual sync button) ─────────────────────────────────


async def reconcile_pending_sync(
    db: Session,
    part: CatalogPart,
) -> dict[str, Any]:
    """For a part with ``wpn_pending_sync=True``, try to register its
    current WPN with HAROLD.

    Strategy:
      - If HAROLD is down → return ``{reconciled: False, reason: ...}``.
      - Try ``issue_specific(part.internal_part_number)``. On success,
        clear the flag and return ``{reconciled: True, via:
        "issue_specific"}``.
      - On 409 (someone else got there first) → call ``issue`` to get
        a fresh WPN, update ``internal_part_number``, clear the flag,
        return ``{reconciled: True, wpn: <new>, via: "issue",
        reason: "collision"}``.

    The caller commits.
    """
    if not is_enabled():
        return {
            "reconciled": False,
            "wpn":        part.internal_part_number,
            "via":        None,
            "reason":     "HAROLD integration disabled",
        }
    if not part.wpn_pending_sync:
        return {
            "reconciled": False,
            "wpn":        part.internal_part_number,
            "via":        "noop",
            "reason":     "Part is not flagged wpn_pending_sync",
        }
    if not part.internal_part_number:
        return {
            "reconciled": False,
            "wpn":        None,
            "via":        None,
            "reason":     "Part has no internal_part_number to reconcile",
        }

    origin_record_id = str(part.id) if part.id is not None else None
    display_name = part.name or part.part_number or "(unnamed)"

    # First try: register the fallback WPN as-is.
    try:
        await harold_client.issue_specific(
            part.internal_part_number,
            origin_system="astra",
            origin_record_id=origin_record_id,
            display_name=display_name,
            description=part.description,
        )
        part.wpn_pending_sync = False
        return {
            "reconciled": True,
            "wpn":        part.internal_part_number,
            "via":        "issue_specific",
            "reason":     None,
        }
    except HaroldUnavailableError as exc:
        return {
            "reconciled": False,
            "wpn":        part.internal_part_number,
            "via":        None,
            "reason":     f"HAROLD unavailable: {exc!s}",
        }
    except HaroldDuplicateError:
        # Collision — fallback WPN already issued by someone else.
        # Drop our fallback number and ask HAROLD for a fresh one.
        pass

    # Fall-through: allocate fresh.
    try:
        pc = part.part_class.value if part.part_class else ""
        body = await harold_client.issue(
            map_class_to_system(pc),
            origin_system="astra",
            origin_record_id=origin_record_id,
            display_name=display_name,
            description=part.description,
        )
        new_wpn = body.get("wpn") or ""
        if not new_wpn:
            raise HaroldInvalidResponseError(
                "HAROLD issue returned empty wpn during reconcile"
            )
        old_wpn = part.internal_part_number
        part.internal_part_number = new_wpn
        part.wpn_pending_sync = False
        return {
            "reconciled": True,
            "wpn":        new_wpn,
            "via":        "issue",
            "reason":     f"Fallback {old_wpn!r} was already issued; "
                          f"reassigned to {new_wpn!r}",
        }
    except HaroldUnavailableError as exc:
        return {
            "reconciled": False,
            "wpn":        part.internal_part_number,
            "via":        None,
            "reason":     f"HAROLD unavailable during reissue: {exc!s}",
        }
    except (HaroldInvalidResponseError, HaroldValidationError) as exc:
        return {
            "reconciled": False,
            "wpn":        part.internal_part_number,
            "via":        None,
            "reason":     f"HAROLD response malformed: {exc!s}",
        }


# ── System codes proxy ─────────────────────────────────────────────


async def list_system_codes() -> dict[str, Any]:
    """Pass through to V2's ``/api/v1/system-codes``. Raises
    ``HaroldUnavailableError`` when off or unreachable; router maps
    to the discriminated-union ``HaroldUnavailable`` response."""
    if not is_enabled():
        raise HaroldUnavailableError("HAROLD integration disabled")
    return await harold_client.list_system_codes()
