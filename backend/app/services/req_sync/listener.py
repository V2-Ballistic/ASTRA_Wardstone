"""
ASTRA — Reactive Requirement Sync — SQLAlchemy event listeners
===============================================================
File: backend/app/services/req_sync/listener.py    ← NEW (Phase 5)

Hooks ``after_update`` / ``after_delete`` on every entity tracked by the
fan-out engine. Each listener runs the fan-out service inside the same
session as the source edit, so users see proposals before they navigate
away.

Safety guarantees
-----------------
1. **Re-entrant guard.** ``fan_out_for_entity`` may auto-apply a proposal
   that updates a Requirement, which itself can have source links. Without
   a depth cap, that would re-trigger the listener and loop. We use a
   :class:`contextvars.ContextVar` so the depth count is safe across
   concurrent FastAPI requests.
2. **Listener errors never abort the original commit.** SQLAlchemy fires
   ``after_*`` events *after* the row is written. If the fan-out service
   raises, we log loudly and continue — the source edit is already
   persisted, and the next listener firing (or a manual trigger) will pick
   up the missed work.
3. **Idempotent registration.** ``register_sync_listeners`` can be called
   multiple times; re-registration is suppressed by SQLAlchemy's existing-
   listener check (``event.contains``).
"""

from __future__ import annotations

import contextvars
import logging
from typing import Tuple

from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.req_sync import SourceEntityType
from app.services.req_sync.fan_out import fan_out_for_entity

logger = logging.getLogger("astra.req_sync.listener")


# ══════════════════════════════════════════════════════════════
#  Re-entrant guard
# ══════════════════════════════════════════════════════════════

_fan_out_depth: contextvars.ContextVar[int] = contextvars.ContextVar(
    "req_sync_fan_out_depth", default=0,
)


def _enter_fan_out() -> bool:
    """Increment depth. Returns ``False`` when fan-out is already running
    in this context (= caller should bail to prevent recursion)."""
    depth = _fan_out_depth.get()
    if depth > 0:
        return False
    _fan_out_depth.set(depth + 1)
    return True


def _exit_fan_out() -> None:
    _fan_out_depth.set(max(0, _fan_out_depth.get() - 1))


def _current_depth() -> int:
    """Test helper."""
    return _fan_out_depth.get()


# ══════════════════════════════════════════════════════════════
#  Watched models — populated lazily so import order doesn't matter
# ══════════════════════════════════════════════════════════════

def _watched_models() -> list[Tuple[type, SourceEntityType]]:
    """Return ``[(model_class, source_entity_type), ...]``. Imports are
    inlined so listener.py stays importable before models are loaded."""
    from app.models.interface import (
        System, Unit, Connector, Pin, Interface,
        WireHarness, Wire, BusDefinition,
        MessageDefinition, MessageField,
        UnitEnvironmentalSpec,
    )
    pairs: list[Tuple[type, SourceEntityType]] = [
        (System,                SourceEntityType.SYSTEM),
        (Unit,                  SourceEntityType.UNIT),
        (Connector,             SourceEntityType.CONNECTOR),
        (Pin,                   SourceEntityType.PIN),
        (Interface,             SourceEntityType.INTERFACE),
        (WireHarness,           SourceEntityType.WIRE_HARNESS),
        (Wire,                  SourceEntityType.WIRE),
        (BusDefinition,         SourceEntityType.BUS_DEFINITION),
        (MessageDefinition,     SourceEntityType.MESSAGE),
        (MessageField,          SourceEntityType.MESSAGE_FIELD),
        (UnitEnvironmentalSpec, SourceEntityType.UNIT_ENV_SPEC),
    ]
    # CatalogPart is optional — wired only if the model is loaded.
    try:
        from app.models.catalog import CatalogPart
        pairs.append((CatalogPart, SourceEntityType.CATALOG_PART))
    except ImportError:  # pragma: no cover
        pass
    # MechanicalJoint — Parts module (ASTRA-SPEC-PARTS-001)
    try:
        from app.models.parts_library import MechanicalJoint
        pairs.append((MechanicalJoint, SourceEntityType.MECHANICAL_JOINT))
    except ImportError:  # pragma: no cover
        pass
    return pairs


# ══════════════════════════════════════════════════════════════
#  Listener factory
# ══════════════════════════════════════════════════════════════

def _make_listener(entity_type: SourceEntityType, trigger_event: str):
    """Build a closure suitable for ``event.listen``.

    Listener body:
        - bail-out if re-entrancy guard says we're already in a fan-out
        - resolve the Session (via ``Session.object_session``) so we share
          the in-flight transaction
        - run :func:`fan_out_for_entity`
        - log + swallow any exception (post-commit listener errors must
          NEVER abort the original transaction)
    """
    def _listener(mapper, connection, target):
        if not _enter_fan_out():
            logger.debug(
                "req_sync: skip recursive fan-out for %s.%s (depth=%d)",
                entity_type.value, getattr(target, "id", "?"),
                _current_depth(),
            )
            return
        try:
            # Some events (after_delete) deliver the target with id set.
            entity_id = getattr(target, "id", None)
            if entity_id is None:
                logger.warning(
                    "req_sync: %s listener fired with no entity id, skipping",
                    entity_type.value,
                )
                return
            session = Session.object_session(target)
            if session is None:
                logger.warning(
                    "req_sync: cannot resolve session for %s.%d, skipping",
                    entity_type.value, entity_id,
                )
                return
            try:
                fan_out_for_entity(
                    session, entity_type, entity_id, trigger_event,
                )
            except Exception as exc:
                # CRITICAL: do NOT re-raise. The original commit has already
                # happened by the time after_update / after_delete fires.
                logger.exception(
                    "req_sync: fan_out_for_entity raised for %s.%d (%s): %s",
                    entity_type.value, entity_id, trigger_event, exc,
                )
        finally:
            _exit_fan_out()
    return _listener


# ══════════════════════════════════════════════════════════════
#  Public registration
# ══════════════════════════════════════════════════════════════

_REGISTERED = False


def register_sync_listeners() -> None:
    """Wire ``after_update`` and ``after_delete`` listeners to every model
    in :func:`_watched_models`. Idempotent — safe to call repeatedly."""
    global _REGISTERED
    if _REGISTERED:
        return

    for model, source_type in _watched_models():
        for sa_event, trigger in (
            ("after_update", "update"),
            ("after_delete", "delete"),
        ):
            listener = _make_listener(source_type, trigger)
            # Use a unique propagation key so duplicate calls (e.g. dev
            # reload) silently no-op.
            try:
                event.listen(model, sa_event, listener, propagate=True)
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "req_sync: failed to wire %s.%s — %s",
                    model.__name__, sa_event, exc,
                )

    _REGISTERED = True
    logger.info(
        "req_sync: listeners registered for %d models",
        len(_watched_models()),
    )


def _reset_for_tests() -> None:
    """Allow the test suite to re-register listeners after model reload."""
    global _REGISTERED
    _REGISTERED = False
