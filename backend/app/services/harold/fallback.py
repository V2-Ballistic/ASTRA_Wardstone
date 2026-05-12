"""Local fallback WPN allocator.

Used when HAROLD is unreachable at approval time. Atomic via
``SELECT ... FOR UPDATE`` on ``catalog_wpn_fallback_sequences``;
concurrent allocators on the same system code serialise on the row
lock. Concurrent allocators on different system codes proceed in
parallel (independent rows).

The allocator is the "primary" path when HAROLD is down — Phase 0
lock #11 of HAROLD-INT-002 makes the three approval branches
deterministic. Parts allocated via this path get
``wpn_pending_sync=True`` set by the caller; a future reconcile run
either confirms the same WPN against HAROLD's ledger or assigns a
new HAROLD-issued WPN (the manual sync button on the part detail
page triggers this).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterator

from sqlalchemy.orm import Session

from app.models.catalog import WpnFallbackSequence

from .class_to_system import DEFAULT_SYSTEM_CODE, PART_CLASS_TO_SYSTEM_CODE


# The 21 codes that the migration seeded. Imported as a set for
# fast membership checks. Mirrors HAROLD V2's wpn_sequences seed.
ALLOWED_SYSTEM_CODES: frozenset[str] = frozenset({
    "VH", "AE", "AS", "AV", "BT", "CC", "CG", "EE", "FC", "GN", "GS",
    "OR", "PR", "ST", "TH", "TS", "WH",
    "FH", "MH", "EH", "SH",
})


def format_wpn(system_code: str, num: int, rev: str = "A") -> str:
    """Compose the canonical 6-digit WPN string. Inverse of
    ``filename_validator.WPN_PATTERN``."""
    return f"WS-{system_code}-P{num:06d}-{rev}"


def _systems_seed_iter() -> Iterator[str]:
    """All 21 codes, deterministic order. Used by the migration's
    ON CONFLICT DO NOTHING seed; exposed here for any caller that
    needs to enumerate the universe of fallback-capable codes."""
    yield from sorted(ALLOWED_SYSTEM_CODES)


def allocate_fallback_wpn(
    db: Session,
    system_code: str,
    *,
    dry_run: bool = False,
) -> str:
    """Return the next available fallback WPN for ``system_code``.

    Atomicity: opens a ``SELECT ... FOR UPDATE`` on the matching row,
    increments ``next_index``, formats the result, and flushes.
    Caller owns the transaction (commit is NOT issued here) so the
    sequence advance, the catalog_parts row mutation, and any audit
    emission land or roll back together.

    ``dry_run=True`` peeks without advancing — useful for the
    pending-import UI to show "if you approve now, the fallback would
    be WS-FH-P000042-A".

    Raises ``ValueError`` for an unknown ``system_code``.
    Raises ``RuntimeError`` if the seeded row is missing (migration
    0033 should have created all 21).
    """
    if system_code not in ALLOWED_SYSTEM_CODES:
        raise ValueError(
            f"Unknown system code {system_code!r}. "
            f"Allowed: {', '.join(sorted(ALLOWED_SYSTEM_CODES))}."
        )

    # ORM ``.with_for_update()`` is dialect-aware: emits FOR UPDATE on
    # Postgres (production lock), suppressed silently on SQLite (test
    # env). Concurrent-allocator semantics are only meaningful against
    # Postgres anyway — Phase 5's end-to-end smoke against the real
    # container exercises the lock.
    row = (
        db.query(WpnFallbackSequence)
        .filter(WpnFallbackSequence.system_code == system_code)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        raise RuntimeError(
            f"catalog_wpn_fallback_sequences row missing for "
            f"{system_code!r}; migration 0033 should have seeded all "
            "21 codes. Re-run `alembic upgrade head` and verify."
        )

    next_index = int(row.next_index)
    wpn = format_wpn(system_code, next_index, rev="A")

    if not dry_run:
        row.next_index = next_index + 1
        row.updated_at = datetime.now(timezone.utc)
        db.flush()

    return wpn


def allocate_for_part_class(
    db: Session,
    part_class: str,
    *,
    dry_run: bool = False,
) -> tuple[str, str]:
    """Convenience: map a part_class via AD-6 → fallback-allocate.

    Returns ``(wpn, system_code)``. Useful from
    ``service.suggest_wpn_for_part`` when HAROLD is unreachable and
    we still need a deterministic suggestion to show the operator.
    """
    sys_code = PART_CLASS_TO_SYSTEM_CODE.get(part_class, DEFAULT_SYSTEM_CODE)
    return allocate_fallback_wpn(db, sys_code, dry_run=dry_run), sys_code
