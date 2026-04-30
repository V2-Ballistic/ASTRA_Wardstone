"""F-065: drop never-honoured WorkflowStage.auto_escalate_to_role column

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-30

The column was a forward-looking placeholder for "on stage timeout,
notify this role". The actual escalation code in
``workflow_engine.check_timeouts`` only appended a dict to a return
list — no notification was sent, no role flag was set, no DB record
was written. Half-implemented columns are footguns: they imply a
behaviour the system doesn't have. Drop the column entirely; when a
real escalation feature lands it should bring its own column with a
defined contract.

Downgrade restores the column as nullable VARCHAR(50) so a rollback
keeps existing seed data round-trippable.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0015"
down_revision: Union[str, None] = "0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("workflow_stages", "auto_escalate_to_role")


def downgrade() -> None:
    op.add_column(
        "workflow_stages",
        sa.Column("auto_escalate_to_role", sa.String(length=50), nullable=True),
    )
