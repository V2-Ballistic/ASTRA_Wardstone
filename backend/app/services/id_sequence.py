"""
ASTRA — ID-sequence service (F-074)
=====================================
File: backend/app/services/id_sequence.py

`next_human_id` is the only safe way to mint a per-project,
human-readable ID like ``SYS-007`` or ``ART-PROJ-042``. It uses a
``SELECT … FOR UPDATE`` on the ``id_sequences`` row for the
(project_id, prefix) pair, so two concurrent transactions serialize
on the lock and one of them sees the incremented value. On SQLite,
``with_for_update()`` is a no-op but our test suite is single-
connection (StaticPool) so the same correctness property holds in
test runs.

Migration backwards compat: pre-0016 rows in the source tables
(`systems`, `units`, ...) have IDs the new sequence doesn't yet
know about. The lazy initialiser scans the source table on first
call for a (project_id, prefix) and seeds ``next_value`` to
``MAX(trailing_digits) + 1``, then increments from there.
"""

from __future__ import annotations

import re
from typing import Optional, Type

from sqlalchemy.orm import Session

from app.models.id_sequence import IdSequence


_TRAILING_DIGITS = re.compile(r"(\d+)$")


def _scan_existing_max(
    db: Session, *, source_model: Optional[Type], project_id: int,
    prefix: str, id_field: str,
) -> int:
    """
    On first call for a (project_id, prefix) pair, look at the source
    table for any pre-existing rows and return the highest trailing
    integer found in their `id_field` values whose ID starts with
    `prefix`. Returns 0 if none.
    """
    if source_model is None:
        return 0
    rows = (
        db.query(getattr(source_model, id_field))
        .filter(source_model.project_id == project_id)
        .all()
    )
    highest = 0
    for (existing_id,) in rows:
        if not existing_id or not isinstance(existing_id, str):
            continue
        if not existing_id.startswith(prefix):
            continue
        m = _TRAILING_DIGITS.search(existing_id)
        if m:
            highest = max(highest, int(m.group(1)))
    return highest


def next_human_id(
    db: Session,
    *,
    project_id: int,
    prefix: str,
    fmt: str = "{prefix}-{n:03d}",
    source_model: Optional[Type] = None,
    id_field: str = "",
) -> str:
    """
    Return the next ID for (project_id, prefix). The helper:
      1. SELECTs the IdSequence row FOR UPDATE.
      2. If the row doesn't exist, creates it — seeding ``next_value``
         from the maximum trailing digit found in
         ``source_model.id_field`` (so existing data isn't overwritten).
      3. Reads ``next_value``, increments it on the row, returns the
         formatted ID.

    The caller MUST be inside a transaction that commits the INSERT
    using this ID. If the caller's transaction rolls back, the
    sequence row's increment also rolls back — no IDs are leaked.

    Args:
        project_id: scope of the sequence.
        prefix: e.g. "SYS", "UNIT", "ART-PROJ-ALPHA". Sequence rows
            are keyed by (project_id, prefix).
        fmt: format string with ``{prefix}`` and ``{n}`` substitutions.
            Defaults to zero-padded 3-digit suffix.
        source_model: ORM class used to seed next_value on first
            call. Pass None for new prefixes that have no legacy data.
        id_field: name of the human-id column on ``source_model``.
    """
    row = (
        db.query(IdSequence)
        .filter(
            IdSequence.project_id == project_id,
            IdSequence.prefix == prefix,
        )
        .with_for_update()
        .first()
    )
    if row is None:
        seed = _scan_existing_max(
            db,
            source_model=source_model,
            project_id=project_id,
            prefix=prefix,
            id_field=id_field,
        )
        row = IdSequence(
            project_id=project_id,
            prefix=prefix,
            next_value=seed + 1,
        )
        db.add(row)
        db.flush()

    n = row.next_value
    row.next_value = n + 1
    db.flush()
    return fmt.format(prefix=prefix, n=n)
