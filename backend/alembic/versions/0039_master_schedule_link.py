"""Master Schedule project link table

Revision ID: 0039
Revises: 0038
Create Date: 2026-05-21

ASTRA <-> WRENCH master-schedule integration. Each ASTRA project can be
linked to exactly one master-schedule program (by program code, e.g.
"WS"). The link table is the join key the ASTRA project's "Master
Schedule" tab uses to proxy reads to the plugin's REST endpoints.

Additive only — no existing row touched.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0039"
down_revision: Union[str, None] = "0038"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_project_links (
            id SERIAL PRIMARY KEY,
            astra_project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            schedule_program_code VARCHAR(16) NOT NULL,
            linked_at TIMESTAMP NOT NULL DEFAULT NOW(),
            UNIQUE (astra_project_id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_schedule_project_links_program_code "
        "ON schedule_project_links (schedule_program_code)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS schedule_project_links")
