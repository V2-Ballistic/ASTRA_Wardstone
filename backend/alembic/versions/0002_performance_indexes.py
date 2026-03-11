"""performance_indexes

Revision ID: 0002
Revises: 0001
Create Date: 2025-01-01 00:01:00.000000

Adds composite indexes on the most frequently-queried columns.
These are additive-only — no data changes, safe to apply while
the application is running (PostgreSQL creates indexes concurrently
by default for non-unique indexes).
"""

from typing import Sequence, Union
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ══════════════════════════════════════
    #  Requirements — most-queried table
    # ══════════════════════════════════════

    # Filtering by project + status (dashboard, list page)
    op.create_index(
        "ix_req_project_status",
        "requirements",
        ["project_id", "status"],
    )

    # Filtering by project + type (type breakdown charts)
    op.create_index(
        "ix_req_project_type",
        "requirements",
        ["project_id", "req_type"],
    )

    # Looking up by project + req_id (detail page, search)
    op.create_index(
        "ix_req_project_reqid",
        "requirements",
        ["project_id", "req_id"],
    )

    # ══════════════════════════════════════
    #  Trace Links — polymorphic lookups
    # ══════════════════════════════════════

    # Source-side lookup (from a requirement → its outgoing links)
    op.create_index(
        "ix_tracelink_source",
        "trace_links",
        ["source_type", "source_id"],
    )

    # Target-side lookup (to a requirement → its incoming links)
    op.create_index(
        "ix_tracelink_target",
        "trace_links",
        ["target_type", "target_id"],
    )

    # Full-pair lookup (check if a specific link exists)
    op.create_index(
        "ix_tracelink_pair",
        "trace_links",
        ["source_type", "source_id", "target_type", "target_id"],
    )

    # ══════════════════════════════════════
    #  Requirement History — timeline queries
    # ══════════════════════════════════════

    op.create_index(
        "ix_reqhistory_req_time",
        "requirement_history",
        ["requirement_id", "changed_at"],
    )

    # ══════════════════════════════════════
    #  Baselines — project timeline
    # ══════════════════════════════════════

    op.create_index(
        "ix_baseline_project_time",
        "baselines",
        ["project_id", "created_at"],
    )

    # ══════════════════════════════════════
    #  Audit Log — compliance queries
    # ══════════════════════════════════════

    op.create_index(
        "ix_audit_project_time",
        "audit_log",
        ["project_id", "timestamp"],
    )

    op.create_index(
        "ix_audit_entity_lookup",
        "audit_log",
        ["entity_type", "entity_id"],
    )

    op.create_index(
        "ix_audit_user_time",
        "audit_log",
        ["user_id", "timestamp"],
    )

    op.create_index(
        "ix_audit_sequence",
        "audit_log",
        ["sequence_number"],
    )

    # ══════════════════════════════════════
    #  Comments — threaded display
    # ══════════════════════════════════════

    op.create_index(
        "ix_comment_req_created",
        "comments",
        ["requirement_id", "created_at"],
    )

    # ══════════════════════════════════════
    #  Workflow instances — status filtering
    # ══════════════════════════════════════

    op.create_index(
        "ix_wfinst_entity",
        "workflow_instances",
        ["entity_type", "entity_id"],
    )

    op.create_index(
        "ix_wfinst_project_status",
        "workflow_instances",
        ["project_id", "status"],
    )


def downgrade() -> None:
    # Drop in reverse order
    op.drop_index("ix_wfinst_project_status", table_name="workflow_instances")
    op.drop_index("ix_wfinst_entity", table_name="workflow_instances")
    op.drop_index("ix_comment_req_created", table_name="comments")
    op.drop_index("ix_audit_sequence", table_name="audit_log")
    op.drop_index("ix_audit_user_time", table_name="audit_log")
    op.drop_index("ix_audit_entity_lookup", table_name="audit_log")
    op.drop_index("ix_audit_project_time", table_name="audit_log")
    op.drop_index("ix_baseline_project_time", table_name="baselines")
    op.drop_index("ix_reqhistory_req_time", table_name="requirement_history")
    op.drop_index("ix_tracelink_pair", table_name="trace_links")
    op.drop_index("ix_tracelink_target", table_name="trace_links")
    op.drop_index("ix_tracelink_source", table_name="trace_links")
    op.drop_index("ix_req_project_reqid", table_name="requirements")
    op.drop_index("ix_req_project_type", table_name="requirements")
    op.drop_index("ix_req_project_status", table_name="requirements")
