"""F-074: per-project id_sequences table

Revision ID: 0016
Revises: 0015
Create Date: 2026-04-30

The new table holds one row per (project_id, prefix) and serves as
the lock target for the FOR UPDATE-based ``next_human_id`` helper.
Existing data is NOT seeded — `next_human_id` lazily inserts a row
for any (project_id, prefix) pair on first use, starting at the
maximum existing trailing-digit value + 1 (computed from the source
table). That backfill happens at first call, in the same transaction,
so there's no separate one-shot job to run.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0016"
down_revision: Union[str, None] = "0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "id_sequences",
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("prefix", sa.String(length=64), nullable=False),
        sa.Column("next_value", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"], ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint(
            "project_id", "prefix", name="pk_id_sequences",
        ),
    )


def downgrade() -> None:
    op.drop_table("id_sequences")
