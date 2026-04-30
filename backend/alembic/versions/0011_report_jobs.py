"""F-019 + F-032: persistent report_jobs table

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-30

Replaces the in-process `_report_history` list in routers/reports.py
with a durable, project-scoped table that also serves as the substrate
for the async report generation pattern (POST returns job_id, the
generator runs in BackgroundTasks, GET polls + downloads).

The result blob is stored inline (LargeBinary). For very large
outputs you may later swap in S3 / object store; the API contract
(job_id + download endpoint) stays stable.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "0011"
down_revision: Union[str, None] = "0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use a postgres-native enum so values are first-class. values_callable on
    # the SQLAlchemy side will hand the python str-Enum's `.value` to PG.
    reportjobstatus = postgresql.ENUM(
        "pending", "running", "completed", "failed",
        name="reportjobstatus",
        create_type=False,
    )
    reportjobstatus.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "report_jobs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("report_type", sa.String(length=64), nullable=False),
        sa.Column("format", sa.String(length=16), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM(name="reportjobstatus", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "requested_by_id",
            sa.Integer(),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column(
            "options",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column("result_blob", sa.LargeBinary(), nullable=True),
        sa.Column("result_filename", sa.String(length=255), nullable=True),
        sa.Column("result_content_type", sa.String(length=128), nullable=True),
        sa.Column(
            "result_metadata",
            postgresql.JSON(astext_type=sa.Text()),
            nullable=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_report_jobs_project_id", "report_jobs", ["project_id"],
    )
    op.create_index(
        "ix_report_jobs_status", "report_jobs", ["status"],
    )
    op.create_index(
        "ix_report_jobs_requested_by_id", "report_jobs", ["requested_by_id"],
    )
    op.create_index(
        "ix_report_jobs_project_created",
        "report_jobs",
        ["project_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_report_jobs_project_created", table_name="report_jobs")
    op.drop_index("ix_report_jobs_requested_by_id", table_name="report_jobs")
    op.drop_index("ix_report_jobs_status", table_name="report_jobs")
    op.drop_index("ix_report_jobs_project_id", table_name="report_jobs")
    op.drop_table("report_jobs")
    sa.Enum(name="reportjobstatus").drop(op.get_bind(), checkfirst=True)
