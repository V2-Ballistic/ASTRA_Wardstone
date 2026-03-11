"""add_embedding_and_suggestion_tables

Revision ID: 0005
Revises: 0002
Create Date: 2025-06-01 00:00:00.000000

Adds tables for AI embedding-based semantic analysis:
  - requirement_embeddings: cached vector embeddings per requirement
  - ai_suggestions: persisted AI suggestions (duplicates, trace links, verification)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers
revision = "0005"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── requirement_embeddings ──
    op.create_table(
        "requirement_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "requirement_id",
            sa.Integer(),
            sa.ForeignKey("requirements.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("embedding", JSON, nullable=False, server_default="[]"),
        sa.Column("dimensions", sa.Integer(), nullable=False, server_default="384"),
        sa.Column("model_version", sa.String(100), nullable=False, server_default="all-MiniLM-L6-v2"),
        sa.Column("statement_hash", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_req_embed_req_id", "requirement_embeddings", ["requirement_id"])
    op.create_index("ix_req_embed_model", "requirement_embeddings", ["model_version"])

    # ── ai_suggestions ──
    op.create_table(
        "ai_suggestions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "project_id",
            sa.Integer(),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "requirement_id",
            sa.Integer(),
            sa.ForeignKey("requirements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("suggestion_type", sa.String(30), nullable=False),
        sa.Column("target_type", sa.String(50), server_default=""),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False, server_default="0.0"),
        sa.Column("explanation", sa.Text(), server_default=""),
        sa.Column("metadata_json", JSON, server_default="{}"),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("resolved_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_sugg_project", "ai_suggestions", ["project_id"])
    op.create_index("ix_ai_sugg_req", "ai_suggestions", ["requirement_id"])
    op.create_index("ix_ai_sugg_status", "ai_suggestions", ["status"])
    op.create_index("ix_ai_sugg_type", "ai_suggestions", ["suggestion_type"])


def downgrade() -> None:
    op.drop_table("ai_suggestions")
    op.drop_table("requirement_embeddings")
