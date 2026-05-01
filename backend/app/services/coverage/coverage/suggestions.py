"""
ASTRA — Source-type Suggestion Engine (per spec §13.5)
=========================================================
File: backend/app/services/coverage/suggestions.py
                                              ← NEW (Phase 6, ASTRA-TDD-INTF-002)

UX hint: given a Requirement whose statement mentions e.g. "voltage" or
"shall transmit", return the most likely architectural source-entity type to
link it to. The intent is to short-circuit the picker modal — when a user
clicks "Link to source" on an orphan, the modal opens pre-filtered to the
suggested type.

Returning ``None`` means "no idea, let the user pick freely". Pattern misses
are silent — the suggestion engine is best-effort and never blocks.

The patterns are roughly ordered most-specific-first; the first match wins.
Keep them simple — these are case-insensitive substring lookups, not full
regex (the actual NLP-grade matching belongs in the Phase 7 catalog work).
"""

from __future__ import annotations

from typing import Optional

from app.models import Requirement
from app.models.req_sync import SourceEntityType


# Ordered list of (substring, source-entity type). First match wins. Patterns
# are case-insensitive, applied to (statement || " " || title || " " || rationale).
_PATTERNS: list[tuple[str, SourceEntityType]] = [
    # Power / electrical pin-level — shall be powered, voltage, current.
    ("shall be powered", SourceEntityType.PIN),
    ("voltage", SourceEntityType.PIN),
    ("current draw", SourceEntityType.PIN),
    ("amperage", SourceEntityType.PIN),
    # Pin allocation / assignment is always a pin-level source.
    ("pin allocation", SourceEntityType.PIN),
    ("pin assignment", SourceEntityType.PIN),
    # Signal / data transmit — wire-level (the wire carries the signal),
    # falling back to the bus definition if "bus" is mentioned.
    ("data rate", SourceEntityType.WIRE),
    ("shall transmit", SourceEntityType.WIRE),
    ("shall receive", SourceEntityType.WIRE),
    # Bus / message-level — picked over the more generic wire match below by
    # virtue of being earlier in the list.
    ("bus protocol", SourceEntityType.BUS_DEFINITION),
    ("can bus", SourceEntityType.BUS_DEFINITION),
    ("ethernet bus", SourceEntityType.BUS_DEFINITION),
    # Environmental — temperature, thermal, vibration, shock, acceleration.
    ("temperature", SourceEntityType.UNIT_ENV_SPEC),
    ("thermal", SourceEntityType.UNIT_ENV_SPEC),
    ("vibration", SourceEntityType.UNIT_ENV_SPEC),
    ("shock", SourceEntityType.UNIT_ENV_SPEC),
    ("acceleration", SourceEntityType.UNIT_ENV_SPEC),
    # Cabling / harness.
    ("harness", SourceEntityType.WIRE_HARNESS),
    ("cable", SourceEntityType.WIRE_HARNESS),
    # Connector / interface — fall through to connector last so signal /
    # cable patterns above win when both terms are present.
    ("connector", SourceEntityType.CONNECTOR),
    ("interface", SourceEntityType.INTERFACE),
    # Generic wire mention — last so e.g. "shall transmit" hits the more
    # specific WIRE rule above first (still WIRE, but explicit).
    ("wire", SourceEntityType.WIRE),
]


def suggest_source_type(req: Requirement) -> Optional[SourceEntityType]:
    """Return the best-guess source-entity type for *req*.

    UX-only — caller treats ``None`` as "let the user pick from any type".
    Match order matters: the most specific patterns appear first in the
    table above so generic terms never preempt them.
    """
    haystack_parts = []
    if getattr(req, "statement", None):
        haystack_parts.append(req.statement)
    if getattr(req, "title", None):
        haystack_parts.append(req.title)
    if getattr(req, "rationale", None):
        haystack_parts.append(req.rationale)
    if not haystack_parts:
        return None
    haystack = " ".join(haystack_parts).lower()
    for pattern, entity_type in _PATTERNS:
        if pattern in haystack:
            return entity_type
    return None
