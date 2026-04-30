"""Schema-drift cleanup — add the few genuinely-useful indexes
that models declared but past migrations never created.

Revision ID: 0019
Revises: 0018
Create Date: 2026-04-30

Companion to the model-side reconciliation done in the same Phase 2D
sweep. After this migration `alembic check` reports only:

  * ``ix_<table>_id`` redundant indexes — `Column(..., primary_key=True,
    index=True)` declarations in ~22 models. Postgres already creates
    a btree index for the PK constraint, so adding `index=True` is
    redundant. We do NOT create these in production — they'd waste
    disk + write throughput. Removing the model declarations is
    invasive (touches every model file) and tracked separately as a
    follow-up; the alembic check noise is benign.
  * ``server default`` deltas — application-level Python defaults
    (e.g. ``default="active"``) vs DB-level ``server_default`` are
    semantically equivalent on insert but show up as drift to
    autogenerate. Cosmetic.

The indexes added here genuinely DO improve query performance for
the existing access patterns:

  * ``ix_audit_entity`` (entity_type, entity_id) — for the per-entity
    audit-trail endpoint at /audit/log/entity/{type}/{id}.
  * ``ix_audit_project`` (project_id, timestamp) — for project audit
    list paged by time.
  * ``ix_audit_user`` (user_id, timestamp) — for the "show me what
    user X did" view.
  * ``ix_audit_seq`` (sequence_number) — single-row hash-chain walks.
  * ``ix_esig_entity`` (entity_type, entity_id) — workflow signature
    list endpoint.
  * ``ix_wf_instance_entity`` (entity_type, entity_id) — "what
    workflows are open on this requirement?" lookup.

All `CREATE INDEX IF NOT EXISTS` so this migration is idempotent
against partially-migrated environments.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0019"
down_revision: Union[str, None] = "0018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES = [
    ("ix_audit_entity", "audit_log", "(entity_type, entity_id)"),
    ("ix_audit_project", "audit_log", "(project_id, timestamp)"),
    ("ix_audit_user", "audit_log", "(user_id, timestamp)"),
    ("ix_audit_seq", "audit_log", "(sequence_number)"),
    ("ix_esig_entity", "electronic_signatures", "(entity_type, entity_id)"),
    ("ix_wf_instance_entity", "workflow_instances", "(entity_type, entity_id)"),
]


def upgrade() -> None:
    for name, table, cols in _INDEXES:
        op.execute(f"CREATE INDEX IF NOT EXISTS {name} ON {table} {cols}")


def downgrade() -> None:
    for name, _table, _cols in reversed(_INDEXES):
        op.execute(f"DROP INDEX IF EXISTS {name}")
