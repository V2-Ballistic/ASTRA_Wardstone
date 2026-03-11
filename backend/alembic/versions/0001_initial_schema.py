"""initial_schema

Revision ID: 0001
Revises: None
Create Date: 2025-01-01 00:00:00.000000

Captures the complete ASTRA schema as of the initial codebase:
  - users, projects, requirements, source_artifacts, trace_links,
    verifications, requirement_history, baselines, baseline_requirements,
    comments
  - Plus Phase-1 addon tables (created only if they don't already exist):
    project_members, audit_log, mfa_configs, refresh_tokens,
    auth_sessions, account_lockouts, approval_workflows,
    workflow_stages, workflow_instances, workflow_stage_actions,
    electronic_signatures

For existing databases that were created via Base.metadata.create_all(),
run:  alembic stamp 0001
to mark this migration as "already applied" without re-running it.
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Enum types used by the models ──
# Alembic needs these for PostgreSQL enum columns

userrole = postgresql.ENUM(
    "admin", "project_manager", "requirements_engineer",
    "reviewer", "stakeholder", "developer",
    name="userrole", create_type=False,
)
requirementtype = postgresql.ENUM(
    "functional", "performance", "interface", "environmental",
    "constraint", "safety", "security", "reliability",
    "maintainability", "derived",
    name="requirementtype", create_type=False,
)
requirementpriority = postgresql.ENUM(
    "critical", "high", "medium", "low",
    name="requirementpriority", create_type=False,
)
requirementstatus = postgresql.ENUM(
    "draft", "under_review", "approved", "baselined",
    "implemented", "verified", "validated", "deferred", "deleted",
    name="requirementstatus", create_type=False,
)
requirementlevel = postgresql.ENUM(
    "L1", "L2", "L3", "L4", "L5",
    name="requirementlevel", create_type=False,
)
artifacttype = postgresql.ENUM(
    "interview", "meeting", "decision", "standard",
    "legacy", "email", "multimedia", "document",
    name="artifacttype", create_type=False,
)
tracelinktype = postgresql.ENUM(
    "satisfaction", "evolution", "dependency", "rationale",
    "contribution", "verification", "decomposition",
    name="tracelinktype", create_type=False,
)
verificationmethod = postgresql.ENUM(
    "test", "analysis", "inspection", "demonstration",
    name="verificationmethod", create_type=False,
)
verificationstatus = postgresql.ENUM(
    "planned", "in_progress", "pass", "fail",
    name="verificationstatus", create_type=False,
)


def upgrade() -> None:
    # ── Create enum types ──
    for enum in [
        userrole, requirementtype, requirementpriority, requirementstatus,
        requirementlevel, artifacttype, tracelinktype,
        verificationmethod, verificationstatus,
    ]:
        enum.create(op.get_bind(), checkfirst=True)

    # ══════════════════════════════════════
    #  Core tables
    # ══════════════════════════════════════

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False, index=True),
        sa.Column("email", sa.String(255), unique=True, nullable=False, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=False),
        sa.Column("role", userrole, nullable=False, server_default="developer"),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true"),
        sa.Column("last_login", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    op.create_table(
        "projects",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(20), unique=True, nullable=False, index=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(50), server_default="active"),
        sa.Column("config", sa.JSON(), server_default="{}"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    op.create_table(
        "requirements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("req_id", sa.String(50), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=True),
        sa.Column("req_type", requirementtype, nullable=False),
        sa.Column("priority", requirementpriority, nullable=False, server_default="medium"),
        sa.Column("status", requirementstatus, nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("quality_score", sa.Float(), server_default="0.0"),
        sa.Column("level", requirementlevel, nullable=False, server_default="L1"),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("requirements.id"), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    op.create_table(
        "source_artifacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("artifact_id", sa.String(50), nullable=False, index=True),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("artifact_type", artifacttype, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("source_date", sa.DateTime(), nullable=True),
        sa.Column("participants", sa.JSON(), server_default="[]"),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    op.create_table(
        "trace_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("target_type", sa.String(50), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("link_type", tracelinktype, nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default="active"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    op.create_table(
        "verifications",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("method", verificationmethod, nullable=False),
        sa.Column("status", verificationstatus, nullable=False, server_default="planned"),
        sa.Column("responsible_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("criteria", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    op.create_table(
        "requirement_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("field_changed", sa.String(100), nullable=False),
        sa.Column("old_value", sa.Text(), nullable=True),
        sa.Column("new_value", sa.Text(), nullable=True),
        sa.Column("change_description", sa.Text(), nullable=True),
        sa.Column("changed_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("changed_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    op.create_table(
        "baselines",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("requirements_count", sa.Integer(), server_default="0"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    op.create_table(
        "baseline_requirements",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("baseline_id", sa.Integer(), sa.ForeignKey("baselines.id"), nullable=False),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("req_id_snapshot", sa.String(50), nullable=False),
        sa.Column("title_snapshot", sa.String(500), nullable=False),
        sa.Column("statement_snapshot", sa.Text(), nullable=True),
        sa.Column("rationale_snapshot", sa.Text(), nullable=True),
        sa.Column("status_snapshot", sa.String(30), nullable=False),
        sa.Column("level_snapshot", sa.String(5), nullable=False),
        sa.Column("type_snapshot", sa.String(50), nullable=True),
        sa.Column("priority_snapshot", sa.String(20), nullable=True),
        sa.Column("quality_score_snapshot", sa.Float(), server_default="0.0"),
        sa.Column("version_snapshot", sa.Integer(), server_default="1"),
        sa.Column("parent_id_snapshot", sa.Integer(), nullable=True),
    )

    op.create_table(
        "comments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("author_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("comments.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    # ══════════════════════════════════════
    #  Phase-1 addon tables (RBAC, audit, auth, security, workflows)
    #  Created with checkfirst-equivalent using IF NOT EXISTS at SQL level
    # ══════════════════════════════════════

    # RBAC: project_members
    op.create_table(
        "project_members",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role_override", sa.String(50), nullable=True),
        sa.Column("added_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("added_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_user"),
    )

    # Audit log
    op.create_table(
        "audit_log",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("event_type", sa.String(50), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("user_ip", sa.String(45), server_default=""),
        sa.Column("user_agent", sa.String(500), server_default=""),
        sa.Column("action_detail", sa.JSON(), server_default="{}"),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("record_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("sequence_number", sa.BigInteger(), nullable=False, unique=True),
    )

    # Security: account lockout
    op.create_table(
        "account_lockouts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(100), unique=True, nullable=False),
        sa.Column("failed_attempts", sa.Integer(), server_default="0"),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("last_attempt_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("last_attempt_ip", sa.String(45), server_default=""),
    )

    # Multi-auth: MFA
    op.create_table(
        "mfa_configs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False),
        sa.Column("secret_encrypted", sa.Text(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("last_used_at", sa.DateTime(), nullable=True),
    )

    # Multi-auth: refresh tokens
    op.create_table(
        "refresh_tokens",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(128), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("revoked", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    # Multi-auth: sessions
    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("auth_provider", sa.String(50), nullable=False, server_default="local"),
        sa.Column("ip_address", sa.String(50), server_default=""),
        sa.Column("user_agent", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("last_active", sa.DateTime(), server_default=sa.text("now()")),
    )

    # Workflows
    _wf_status = postgresql.ENUM("active", "inactive", name="workflowstatus", create_type=False)
    _inst_status = postgresql.ENUM(
        "pending", "in_progress", "approved", "rejected", "cancelled", "timed_out",
        name="instancestatus", create_type=False,
    )
    _sig_meaning = postgresql.ENUM(
        "approved", "rejected", "reviewed", "witnessed",
        name="signaturemeaning", create_type=False,
    )
    _wf_status.create(op.get_bind(), checkfirst=True)
    _inst_status.create(op.get_bind(), checkfirst=True)
    _sig_meaning.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "approval_workflows",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("status", _wf_status, server_default="active"),
        sa.Column("entity_type", sa.String(50), server_default="requirement"),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    op.create_table(
        "workflow_stages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("approval_workflows.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_number", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("required_role", sa.String(50), nullable=True),
        sa.Column("required_count", sa.Integer(), server_default="1"),
        sa.Column("timeout_hours", sa.Integer(), server_default="0"),
        sa.Column("auto_escalate_to_role", sa.String(50), nullable=True),
        sa.Column("can_parallel", sa.Boolean(), server_default="false"),
        sa.Column("require_signature", sa.Boolean(), server_default="true"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()")),
    )

    op.create_table(
        "electronic_signatures",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("signature_meaning", _sig_meaning, nullable=False),
        sa.Column("statement", sa.Text(), nullable=False),
        sa.Column("password_verified", sa.Boolean(), server_default="false"),
        sa.Column("ip_address", sa.String(45), server_default=""),
        sa.Column("user_agent", sa.String(500), server_default=""),
        sa.Column("timestamp", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        sa.Column("signature_hash", sa.String(64), nullable=False, unique=True),
    )

    op.create_table(
        "workflow_instances",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("workflow_id", sa.Integer(), sa.ForeignKey("approval_workflows.id"), nullable=False),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("status", _inst_status, server_default="pending"),
        sa.Column("current_stage_number", sa.Integer(), server_default="1"),
        sa.Column("submitted_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(), server_default=sa.text("now()")),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "workflow_stage_actions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("instance_id", sa.Integer(), sa.ForeignKey("workflow_instances.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_number", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("comment", sa.Text(), server_default=""),
        sa.Column("signature_id", sa.Integer(), sa.ForeignKey("electronic_signatures.id"), nullable=True),
        sa.Column("acted_at", sa.DateTime(), server_default=sa.text("now()")),
    )


def downgrade() -> None:
    # Reverse order — drop dependents first
    op.drop_table("workflow_stage_actions")
    op.drop_table("workflow_instances")
    op.drop_table("electronic_signatures")
    op.drop_table("workflow_stages")
    op.drop_table("approval_workflows")
    op.drop_table("auth_sessions")
    op.drop_table("refresh_tokens")
    op.drop_table("mfa_configs")
    op.drop_table("account_lockouts")
    op.drop_table("audit_log")
    op.drop_table("project_members")
    op.drop_table("comments")
    op.drop_table("baseline_requirements")
    op.drop_table("baselines")
    op.drop_table("requirement_history")
    op.drop_table("verifications")
    op.drop_table("trace_links")
    op.drop_table("source_artifacts")
    op.drop_table("requirements")
    op.drop_table("projects")
    op.drop_table("users")

    # Drop enum types
    for name in [
        "signaturemeaning", "instancestatus", "workflowstatus",
        "verificationstatus", "verificationmethod", "tracelinktype",
        "artifacttype", "requirementlevel", "requirementstatus",
        "requirementpriority", "requirementtype", "userrole",
    ]:
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
