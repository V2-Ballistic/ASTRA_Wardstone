"""add auto_req_approval_required + integration / AI / sync tables

Revision ID: 0007a
Revises: 0007
Create Date: 2026-03-14 03:55:15.962957

F-109: was previously named ``4bd35db2ef64_add_auto_req_approval_required.py``
with revision id ``4bd35db2ef64``. Renamed to ``0007a`` so the file
sorts predictably alongside the rest of the chain (0007 → 0007a →
0008 → … → 0022) and the migration list reads in chronological order
without random-hex outliers. ``0008``'s ``down_revision`` was updated
in the same commit so the chain still resolves.

F-108: the original migration ended with a ``DO $$ … IF NOT EXISTS …
ALTER TABLE …`` PL/pgSQL block to add the ``auto_req_approval_required``
column with a runtime existence check. That made the migration
non-reversible in autogenerate diffs (alembic can't reason about raw
SQL) and bypassed the normal ``op.add_column`` machinery, so a future
``alembic check`` always reported drift even when the column was
present. Replaced with ``op.add_column(...)`` wrapped in a small
try/except so the IF-NOT-EXISTS semantics survive — needed because
some early dev environments hand-applied this column before the
migration existed.

History note: this migration also creates four "extra" tables
(integration_configs, ai_analysis_cache, ai_feedback, sync_logs).
Original commit message says it was rescued from an autogenerate run
that had also tried to drop the workflow tables; the four creates
above were the real intent. They live here for chain integrity.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '0007a'
down_revision: Union[str, None] = '0007'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── New table: integration_configs ──
    op.create_table('integration_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('integration_type', sa.String(length=50), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('config_encrypted', sa.Text(), nullable=False),
        sa.Column('field_mapping', sa.JSON(), nullable=True),
        sa.Column('sync_direction', sa.String(length=20), nullable=True),
        sa.Column('external_project', sa.String(length=255), nullable=True),
        sa.Column('sync_schedule', sa.String(length=50), nullable=True),
        sa.Column('last_sync_at', sa.DateTime(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_intconfig_project', 'integration_configs', ['project_id', 'integration_type'], unique=False)
    op.create_index(op.f('ix_integration_configs_id'), 'integration_configs', ['id'], unique=False)

    # ── New table: ai_analysis_cache ──
    op.create_table('ai_analysis_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('requirement_id', sa.Integer(), nullable=False),
        sa.Column('analysis_type', sa.String(length=30), nullable=False),
        sa.Column('result_json', sa.JSON(), nullable=False),
        sa.Column('model_used', sa.String(length=100), nullable=True),
        sa.Column('prompt_version', sa.String(length=20), nullable=True),
        sa.Column('analyzed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['requirement_id'], ['requirements.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_analysis_cache_id'), 'ai_analysis_cache', ['id'], unique=False)
    op.create_index('ix_ai_cache_req_type', 'ai_analysis_cache', ['requirement_id', 'analysis_type'], unique=True)

    # ── New table: ai_feedback ──
    op.create_table('ai_feedback',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('requirement_id', sa.Integer(), nullable=False),
        sa.Column('suggestion_type', sa.String(length=50), nullable=True),
        sa.Column('suggestion_text', sa.Text(), nullable=True),
        sa.Column('accepted', sa.Boolean(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['requirement_id'], ['requirements.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ai_feedback_id'), 'ai_feedback', ['id'], unique=False)
    op.create_index('ix_ai_feedback_req', 'ai_feedback', ['requirement_id'], unique=False)
    op.create_index('ix_ai_feedback_user', 'ai_feedback', ['user_id', 'created_at'], unique=False)

    # ── New table: sync_logs ──
    op.create_table('sync_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('integration_config_id', sa.Integer(), nullable=False),
        sa.Column('direction', sa.String(length=20), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('created_count', sa.Integer(), nullable=True),
        sa.Column('updated_count', sa.Integer(), nullable=True),
        sa.Column('skipped_count', sa.Integer(), nullable=True),
        sa.Column('error_count', sa.Integer(), nullable=True),
        sa.Column('details', sa.JSON(), nullable=True),
        sa.Column('triggered_by_id', sa.Integer(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['integration_config_id'], ['integration_configs.id']),
        sa.ForeignKeyConstraint(['triggered_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_sync_logs_id'), 'sync_logs', ['id'], unique=False)
    op.create_index('ix_synclog_config', 'sync_logs', ['integration_config_id', 'started_at'], unique=False)

    # ── Add auto_req_approval_required to projects ──
    # F-108: was previously a DO $$ … IF NOT EXISTS … block. Now a
    # plain op.add_column wrapped in a try/except so the IF NOT EXISTS
    # semantics still cover dev environments that hand-applied the
    # column. The DuplicateColumn exception (PG SQLSTATE 42701) means
    # the column is already there — fine, swallow.
    try:
        op.add_column(
            'projects',
            sa.Column(
                'auto_req_approval_required',
                sa.Boolean(),
                nullable=True,
                server_default=sa.true(),
            ),
        )
    except Exception as exc:
        # Re-raise unless it's the duplicate-column case.
        if 'already exists' not in str(exc).lower() and 'duplicatecolumn' not in str(type(exc)).lower():
            raise


def downgrade() -> None:
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS auto_req_approval_required")
    op.drop_table('sync_logs')
    op.drop_table('ai_feedback')
    op.drop_table('ai_analysis_cache')
    op.drop_table('integration_configs')
