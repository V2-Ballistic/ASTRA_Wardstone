"""HAROLD naming-authority wrapper for the engineering domains.

Spec §2 ("HAROLD naming authority — mandatory, sequential, gapless"):
this is the thin, reused service every engineering-domain feature
(solid motors, aero decks, vehicle configurations, …) goes through to
obtain a WPN. The contract is strict:

  * HAROLD is the ONLY source of numbers. ASTRA never computes,
    guesses, or fabricates an index — every WPN returned by this
    module is HAROLD's response verbatim.
  * NO local fallback. The ``app.services.harold.fallback`` allocator
    used by the catalog is FORBIDDEN here. If HAROLD is unavailable
    (or the integration flag is off), every function raises
    ``HaroldUnavailableError`` and the caller surfaces 503.
  * NO silent re-allocation. If persistence fails after allocation,
    the WPN is released back to HAROLD (DELETE /wpn/{wpn}) so the
    sequence stays gapless. If THAT fails too, we log CRITICAL and
    raise ``HaroldOrphanWpnError`` — the ledger must never drift
    silently (spec §2.7).

Async story: every function here is an ``async def``, matching the
existing convention — ASTRA's FastAPI handlers that talk to HAROLD
are themselves ``async def`` and ``await`` the service directly (see
``app/routers/harold.py``); there is no sync→async bridge layer.
SQLAlchemy ``Session`` work inside ``allocate_and_persist`` is plain
synchronous calls made from the async function, exactly as
``app.services.harold.service`` already does.
"""
from __future__ import annotations

import inspect
import logging
from typing import Any, Callable, Optional

from sqlalchemy.orm import Session

from app.config import settings
from app.services.harold import client as harold_client
from app.services.harold.errors import HaroldUnavailableError

from .errors import HaroldOrphanWpnError

logger = logging.getLogger(__name__)


# ── Spec-mandated engineering system codes ─────────────────────────
#
# The CODES are fixed strings from spec §2 — but their numeric
# sequences live ONLY in HAROLD. Nothing in ASTRA may derive an index
# from these constants.

MTR_CODE: str = "MTR"
AER_CODE: str = "AER"
CFG_CODE: str = "CFG"

#: Registration name/description used when ``ensure_system_code`` is
#: called without explicit values for one of the known codes.
SYSTEM_CODE_REGISTRY: dict[str, dict[str, str]] = {
    MTR_CODE: {
        "name":        "Solid Motors",
        "description": "Solid rocket motor designs (engineering domain)",
    },
    AER_CODE: {
        "name":        "Aero Decks",
        "description": "Aerodynamic decks (engineering domain)",
    },
    CFG_CODE: {
        "name":        "Vehicle Configurations",
        "description": "Vehicle configuration definitions (engineering domain)",
    },
}


def _require_enabled() -> None:
    """Strictness gate. Unlike the catalog path, the engineering
    domains have NO degraded mode — flag off behaves exactly like
    HAROLD being down (callers surface 503)."""
    if not settings.HAROLD_INTEGRATION_ENABLED:
        raise HaroldUnavailableError(
            "HAROLD integration disabled (HAROLD_INTEGRATION_ENABLED=false) — "
            "engineering-domain naming has no local fallback"
        )


# ── System-code registration ───────────────────────────────────────


async def ensure_system_code(
    code: str,
    name: Optional[str] = None,
    description: Optional[str] = None,
) -> dict[str, Any]:
    """Register ``code`` with HAROLD if absent (idempotent).

    HAROLD's ``POST /system-codes`` answers 201 ``created: true`` for
    a new code and 200 ``created: false`` for an existing one — both
    are success here. ``name``/``description`` default from
    ``SYSTEM_CODE_REGISTRY`` for the spec-mandated codes; for any
    other code, ``name`` is required.
    """
    _require_enabled()
    defaults = SYSTEM_CODE_REGISTRY.get(code, {})
    resolved_name = name if name is not None else defaults.get("name")
    if not resolved_name:
        raise ValueError(
            f"ensure_system_code({code!r}): name is required for codes "
            "outside SYSTEM_CODE_REGISTRY"
        )
    resolved_description = (
        description if description is not None else defaults.get("description")
    )
    return await harold_client.register_system_code(
        code,
        resolved_name,
        category="engineering",
        description=resolved_description,
    )


# ── Allocation ─────────────────────────────────────────────────────


async def allocate_next(
    sys_code: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    origin_record_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Allocate the next sequential WPN for ``sys_code``.

    Ensures the system code exists, then calls HAROLD's
    ``POST /wpn/issue``. Returns the full ledger entry (incl. ``wpn``)
    verbatim — ASTRA NEVER computes or guesses a number. Raises
    ``HaroldUnavailableError`` when HAROLD is down; no fallback.
    """
    _require_enabled()
    await ensure_system_code(sys_code)
    return await harold_client.issue(
        sys_code,
        origin_system="astra",
        origin_record_id=origin_record_id,
        display_name=display_name,
        description=description,
        metadata=metadata,
    )


# ── Filename precheck ──────────────────────────────────────────────


async def precheck_filename(
    name: str,
    sys_code: Optional[str] = None,
) -> dict[str, Any]:
    """HAROLD's filename precheck — HAROLD decides the canonical name.
    Returns the precheck verdict verbatim."""
    _require_enabled()
    return await harold_client.filename_precheck(
        name, intended_part_class=sys_code,
    )


# ── Revisions ──────────────────────────────────────────────────────


async def issue_revision(
    wpn: str,
    *,
    display_name: Optional[str] = None,
    description: Optional[str] = None,
    origin_record_id: Optional[str] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Issue the next revision of ``wpn`` (same index, next revision
    letter A→B→C…) via ``POST /wpn/{wpn}/revise``. Returns the new
    ledger entry verbatim."""
    _require_enabled()
    return await harold_client.revise(
        wpn,
        origin_system="astra",
        origin_record_id=origin_record_id,
        display_name=display_name,
        description=description,
        metadata=metadata,
    )


# ── Ledger annotation ──────────────────────────────────────────────


async def record_use(
    wpn: str,
    kind: str,
    metadata: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    """Annotate ``wpn``'s ledger entry with how ASTRA is using it.

    Sends ``PATCH /wpn/{wpn}`` with ``{"metadata": {kind, ...}}``;
    HAROLD merges the metadata into the existing entry server-side.
    """
    _require_enabled()
    merged: dict[str, Any] = dict(metadata or {})
    merged["kind"] = kind
    return await harold_client.patch_wpn(wpn, metadata=merged)


# ── Release (failed-persistence reconciliation ONLY) ───────────────


async def release(wpn: str, *, reason: Optional[str] = None) -> dict[str, Any]:
    """Release ``wpn`` back to HAROLD (``DELETE /wpn/{wpn}``) so the
    index is reclaimed and the sequence stays gapless.

    ONLY for failed-persistence reconciliation — never for normal
    record deletion (issued names are permanent once persisted).
    """
    _require_enabled()
    return await harold_client.delete_wpn(
        wpn,
        actor="astra",
        reason=reason or "failed-persistence reconciliation",
    )


# ── Ledger query ───────────────────────────────────────────────────


async def ledger_query(
    system_code: Optional[str] = None,
    status: Optional[str] = None,
    q: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
) -> dict[str, Any]:
    """Filtered/paginated ledger listing — returns
    ``{items, total, skip, limit}`` verbatim."""
    _require_enabled()
    return await harold_client.list_ledger(
        system_code=system_code, status=status, q=q, skip=skip, limit=limit,
    )


# ── Transactional allocate-then-persist helper ─────────────────────


async def allocate_and_persist(
    db: Session,
    sys_code: str,
    persist_fn: Callable[[Session, dict[str, Any]], Any],
    *,
    alloc_kwargs: Optional[dict[str, Any]] = None,
) -> tuple[dict[str, Any], Any]:
    """Allocate a WPN, persist the local record, commit — gaplessly.

    Flow:
      1. ``allocate_next(sys_code, **alloc_kwargs)`` — HAROLD issues
         the ledger entry.
      2. ``persist_fn(db, ledger_entry)`` — the caller writes its ORM
         row(s). May be sync or return an awaitable.
      3. ``db.commit()``.

    On ANY persistence/commit failure: ``db.rollback()``, then
    ``release(wpn)`` so HAROLD reclaims the index (no gap). The
    original exception is re-raised. If the release itself fails, log
    CRITICAL with the orphan WPN and raise ``HaroldOrphanWpnError``
    (spec §2.7: the ledger must never drift; never silently
    re-allocate).

    Returns ``(ledger_entry, persist_fn_result)``.
    """
    entry = await allocate_next(sys_code, **(alloc_kwargs or {}))
    wpn = entry.get("wpn") or ""

    try:
        result = persist_fn(db, entry)
        if inspect.isawaitable(result):
            result = await result
        db.commit()
    except Exception as persist_exc:
        db.rollback()
        logger.warning(
            "allocate_and_persist: persistence failed for %s (%s); "
            "releasing back to HAROLD",
            wpn, persist_exc,
        )
        try:
            await release(wpn, reason=f"persistence failed: {persist_exc!s}")
        except Exception as release_exc:
            logger.critical(
                "ORPHAN WPN %s: persistence failed (%s) AND release "
                "failed (%s). HAROLD's ledger now holds an entry no "
                "ASTRA record references — manual reconciliation "
                "required. Do NOT re-allocate.",
                wpn, persist_exc, release_exc,
            )
            raise HaroldOrphanWpnError(
                f"WPN {wpn} is orphaned: persistence failed "
                f"({persist_exc!s}) and release failed ({release_exc!s})",
                wpn=wpn,
            ) from persist_exc
        raise

    return entry, result
