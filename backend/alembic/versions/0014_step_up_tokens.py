"""F-036: step_up_tokens table for external-IdP signature path

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-30

External-IdP users (SAML / OIDC / PIV) carry the literal sentinel
``hashed_password = "EXTERNAL_IDP_NO_LOCAL_PASSWORD"`` and therefore
fail the password check in ``signature_service.request_signature``.
Phase 2D adds an alternative one-time-token path issued via
``POST /workflows/signatures/idp-step-up``. This migration creates
the persistence layer for those tokens.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0014"
down_revision: Union[str, None] = "0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "step_up_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column(
            "issued_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("consumed_at", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_step_up_tokens_user_id", "step_up_tokens", ["user_id"],
    )
    op.create_index(
        "ix_step_up_tokens_user_unconsumed",
        "step_up_tokens",
        ["user_id", "consumed_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_step_up_tokens_user_unconsumed", table_name="step_up_tokens")
    op.drop_index("ix_step_up_tokens_user_id", table_name="step_up_tokens")
    op.drop_table("step_up_tokens")
