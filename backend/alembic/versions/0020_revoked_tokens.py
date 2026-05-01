"""F-063: revoked_tokens table for cross-worker access-token revocation.

Revision ID: 0020
Revises: 0019
Create Date: 2026-04-30

The pre-fix `auth_manager._BLACKLIST` was a process-local `set()` —
logging out on worker A did nothing for worker B. This migration adds
the durable backing table that `get_current_user` now consults on every
authenticated request.

Companion change: `create_access_token` now stamps a `jti` claim on
every issued token, and `get_current_user` rejects tokens whose jti
appears here.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0020"
down_revision: Union[str, None] = "0019"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "revoked_tokens",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("jti", sa.String(length=64), nullable=False),
        sa.Column("exp", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("reason", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("jti", name="revoked_tokens_jti_key"),
    )
    op.create_index("ix_revoked_tokens_jti", "revoked_tokens", ["jti"])
    op.create_index("ix_revoked_tokens_exp", "revoked_tokens", ["exp"])
    op.create_index("ix_revoked_tokens_id", "revoked_tokens", ["id"])


def downgrade() -> None:
    op.drop_index("ix_revoked_tokens_id", table_name="revoked_tokens")
    op.drop_index("ix_revoked_tokens_exp", table_name="revoked_tokens")
    op.drop_index("ix_revoked_tokens_jti", table_name="revoked_tokens")
    op.drop_table("revoked_tokens")
