"""ASTRA-TDD-PROJPARTS-001 (Path C, follow-up): drop NOT NULL on project_parts.library_part_id

Revision ID: 0031
Revises: 0030
Create Date: 2026-05-11

Migration 0030 added `catalog_part_id` as the canonical Path C BOM
link but did not relax the legacy `library_part_id NOT NULL`.
Catalog-only BOM lines (the dominant case under Path C) therefore
still fail at the DB layer. This migration finishes the job by
dropping the NOT NULL — `library_part_id` stays as an optional
legacy reference for fastener-class workflows and mechanical-joint
back-compat.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0031"
down_revision: Union[str, None] = "0030"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE project_parts ALTER COLUMN library_part_id DROP NOT NULL"
    )


def downgrade() -> None:
    # Restoring NOT NULL after Path C is in production-use will fail if
    # any rows have a NULL library_part_id (the expected steady state).
    # We therefore re-add NOT NULL only when the column is empty-free;
    # callers downgrading must clean catalog-only rows first.
    op.execute(
        "ALTER TABLE project_parts ALTER COLUMN library_part_id SET NOT NULL"
    )
