"""F-035: TraceLink project_id + uniqueness + indexes

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-30

The trace_links table predates the project-scoping work and has:
  * no project_id column (polymorphic source, never tied back to project)
  * no UNIQUE constraint on the (src,tgt,link_type) tuple
  * no FK on source_id / target_id (impossible — polymorphic)
  * a non-unique ix_tracelink_pair index from migration 0002

This migration:
  1. ADD COLUMN project_id NULL.
  2. Backfill from the source entity:
       source_type='requirement'      → requirements.project_id
       source_type='source_artifact'  → source_artifacts.project_id
       source_type='verification'     → verifications.requirement_id
                                        → requirements.project_id
       any other source_type          → leave NULL (will fail step 3)
  3. SET NOT NULL + add FK projects(id) ON DELETE CASCADE.
  4. Add UniqueConstraint on (source_type, source_id, target_type,
     target_id, link_type) — `uq_trace_link_endpoints`. Rejects
     duplicates pre-emptively.
  5. Add `ix_trace_links_project (project_id)`.
  6. Drop the legacy non-unique pair index from 0002 if present
     (its replacement is the new UNIQUE).

If step 2 leaves NULLs we abort (5b raises) so the operator can
either fix the bad rows or extend this migration's resolver. We
will NOT silently drop unresolvable rows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0012"
down_revision: Union[str, None] = "0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Add nullable column
    op.add_column(
        "trace_links",
        sa.Column("project_id", sa.Integer(), nullable=True),
    )

    # 2. Backfill from source entity
    bind.execute(sa.text(
        """
        UPDATE trace_links tl
           SET project_id = r.project_id
          FROM requirements r
         WHERE tl.source_type = 'requirement'
           AND tl.source_id = r.id
           AND tl.project_id IS NULL
        """
    ))
    bind.execute(sa.text(
        """
        UPDATE trace_links tl
           SET project_id = sa.project_id
          FROM source_artifacts sa
         WHERE tl.source_type = 'source_artifact'
           AND tl.source_id = sa.id
           AND tl.project_id IS NULL
        """
    ))
    bind.execute(sa.text(
        """
        UPDATE trace_links tl
           SET project_id = r.project_id
          FROM verifications v
          JOIN requirements r ON r.id = v.requirement_id
         WHERE tl.source_type = 'verification'
           AND tl.source_id = v.id
           AND tl.project_id IS NULL
        """
    ))

    # 2b. Abort if anything is still unresolved.
    unresolved = bind.execute(sa.text(
        "SELECT COUNT(*) FROM trace_links WHERE project_id IS NULL"
    )).scalar()
    if unresolved:
        raise RuntimeError(
            f"F-035 migration aborted: {unresolved} trace_links rows could not "
            "be backfilled with a project_id. Inspect rows with "
            "project_id IS NULL and either fix the source reference, delete "
            "the row, or extend this migration's resolver."
        )

    # 3. SET NOT NULL + FK
    op.alter_column("trace_links", "project_id", nullable=False)
    op.create_foreign_key(
        "fk_trace_links_project_id",
        source_table="trace_links",
        referent_table="projects",
        local_cols=["project_id"],
        remote_cols=["id"],
        ondelete="CASCADE",
    )

    # 5. New project_id index
    op.create_index(
        "ix_trace_links_project", "trace_links", ["project_id"],
    )

    # 4. UniqueConstraint on the (src,tgt,link_type) tuple
    op.create_unique_constraint(
        "uq_trace_link_endpoints",
        "trace_links",
        ["source_type", "source_id", "target_type", "target_id", "link_type"],
    )

    # 6. Drop legacy non-unique pair index from 0002 (if present).
    # IF EXISTS keeps re-runs and partial DBs idempotent.
    op.execute(sa.text("DROP INDEX IF EXISTS ix_tracelink_pair"))


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS ix_trace_links_project"))
    op.drop_constraint(
        "uq_trace_link_endpoints", "trace_links", type_="unique",
    )
    op.drop_constraint(
        "fk_trace_links_project_id", "trace_links", type_="foreignkey",
    )
    op.drop_column("trace_links", "project_id")
    # Restore the legacy non-unique composite for parity with 0002.
    op.create_index(
        "ix_tracelink_pair",
        "trace_links",
        ["source_type", "source_id", "target_type", "target_id"],
    )
