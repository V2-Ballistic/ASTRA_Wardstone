"""F-075: requirements uniqueness + (project_id, owner_id) index

Revision ID: 0017
Revises: 0016
Create Date: 2026-04-30

Pre-fix state of `requirements`:
  * Comment said "Each req_id must be unique within a project" but
    no constraint enforced it — duplicate (project_id, req_id) rows
    could be inserted.
  * Migration 0002 created `ix_req_project_reqid` as a non-unique
    composite — useful for lookups, useless for enforcing uniqueness.
  * Composite indexes (project_id, status) and (project_id, req_type)
    existed (also from 0002), but (project_id, owner_id) didn't —
    "show me all requirements owned by user X in project Y" did a
    full project scan.

This migration:
  1. Drops `ix_req_project_reqid` (non-unique).
  2. Creates `uq_req_per_project UNIQUE (project_id, req_id)` — the
    UNIQUE constraint also serves as the lookup index.
  3. Creates `ix_req_project_owner (project_id, owner_id)`.

If duplicates exist in production at upgrade time, the unique
constraint creation will fail. The audit's intent is that no such
duplicates SHOULD exist (the absence of the constraint was the bug,
not a feature). Operators with known dupes must dedupe before
upgrading.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0017"
down_revision: Union[str, None] = "0016"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the non-unique composite first; UNIQUE serves the same lookups.
    op.execute("DROP INDEX IF EXISTS ix_req_project_reqid")

    op.create_unique_constraint(
        "uq_req_per_project",
        "requirements",
        ["project_id", "req_id"],
    )

    # Owner-scoped lookup composite. IF NOT EXISTS via raw SQL because
    # alembic's create_index doesn't expose the flag in older versions
    # and operators may have hand-added this index already.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_req_project_owner "
        "ON requirements (project_id, owner_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_req_project_owner")
    op.drop_constraint(
        "uq_req_per_project", "requirements", type_="unique",
    )
    # Restore the legacy non-unique composite for parity with 0002.
    op.create_index(
        "ix_req_project_reqid",
        "requirements",
        ["project_id", "req_id"],
    )
