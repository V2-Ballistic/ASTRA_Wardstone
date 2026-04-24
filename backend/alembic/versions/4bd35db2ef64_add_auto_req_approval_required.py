"""add auto_req_approval_required

Revision ID: 4bd35db2ef64
Revises: 0007
Create Date: 2026-03-14 03:55:15.962957

FIXED: Removed autogenerate DROP TABLE statements for workflow tables
       and hundreds of unnecessary alter_column/index changes.
       Only keeps legitimate new table creation + column addition.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4bd35db2ef64'
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

    # ── Add auto_req_approval_required to projects (if not already present) ──
    # Using raw SQL with IF NOT EXISTS to be safe on re-runs
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'projects' AND column_name = 'auto_req_approval_required'
            ) THEN
                ALTER TABLE projects ADD COLUMN auto_req_approval_required BOOLEAN DEFAULT TRUE;
            END IF;
        END $$;
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE projects DROP COLUMN IF EXISTS auto_req_approval_required")
    op.drop_table('sync_logs')
    op.drop_table('ai_feedback')
    op.drop_table('ai_analysis_cache')
    op.drop_table('integration_configs')
