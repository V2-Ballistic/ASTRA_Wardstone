"""add_impact_reports_table

Revision ID: 0006
Revises: 0005
Create Date: 2025-06-15 00:00:00.000000

Adds:
  - impact_reports: persisted impact analysis reports
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "impact_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "requirement_id",
            sa.Integer(),
            sa.ForeignKey("requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("change_description", sa.Text(), server_default=""),
        sa.Column("action_type", sa.String(20), server_default="modify"),
        sa.Column("report_json", JSON, nullable=False, server_default="{}"),
        sa.Column("risk_level", sa.String(20), nullable=False, server_default="low"),
        sa.Column("total_affected", sa.Integer(), server_default="0"),
        sa.Column("dependency_depth", sa.Integer(), server_default="0"),
        sa.Column("ai_summary", sa.Text(), server_default=""),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_impact_req_date", "impact_reports", ["requirement_id", "created_at"])
    op.create_index("ix_impact_risk", "impact_reports", ["risk_level"])


def downgrade() -> None:
    op.drop_table("impact_reports")
