"""ASTRA-TDD-LEVELS-001: add L0 (Customer/Contractual) requirement level

Revision ID: 0028
Revises: 0027
Create Date: 2026-05-05

Changes:
  * Adds 'L0' value to the requirementlevel PG enum, BEFORE 'L1' so the
    natural ordering of enum values is preserved (L0 < L1 < L2 ...).
  * Adds requirements.source_artifact_id (nullable FK to source_artifacts)
    so L0 rows can link to the originating MRD / SOW / contract document.

Mirrors database/migrations/0008_add_l0_level.sql for direct-psql workflows.
Both routes are idempotent; pick one.

Postgres note: ALTER TYPE ... ADD VALUE cannot run inside a transaction in
PG <12. We disable the transactional wrapper for the upgrade so it runs in
its own statement on PG 16+.

Down-migration: PG does NOT support removing an enum value cleanly. The
downgrade only drops the column and leaves 'L0' in the enum (harmless if
no rows reference it).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0028"
down_revision: Union[str, None] = "0027"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ALTER TYPE ... ADD VALUE must run outside a transaction.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE requirementlevel ADD VALUE IF NOT EXISTS 'L0' BEFORE 'L1'"
        )

    # Use raw IF NOT EXISTS SQL so this migration is safe to re-run after
    # the equivalent statement has been applied via the standalone SQL file
    # at database/migrations/0008_add_l0_level.sql.
    op.execute(
        "ALTER TABLE requirements "
        "ADD COLUMN IF NOT EXISTS source_artifact_id INTEGER "
        "REFERENCES source_artifacts(id) ON DELETE SET NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_requirements_source_artifact_id "
        "ON requirements(source_artifact_id)"
    )


def downgrade() -> None:
    op.drop_index(
        "ix_requirements_source_artifact_id",
        table_name="requirements",
    )
    op.drop_column("requirements", "source_artifact_id")
    # Note: 'L0' stays in the requirementlevel enum — PG cannot drop an
    # enum value without recreating the type. Harmless if unused.
