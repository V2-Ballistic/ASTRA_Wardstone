"""Engineering Frame ICD tables (CITADEL Vehicle Body Frame)

Revision ID: 0044
Revises: 0043
Create Date: 2026-06-10

ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §3 — the versioned frame ICD that
every engineering-domain surface (motors, aero decks, vehicle
configurations, config bundles) references for its coordinate frame:

  frame_icds            identity rows (stable key, e.g.
                        'citadel-vehicle-body-frame')
  frame_icd_revisions   immutable content rows (datum / axes / units /
                        rules), rev starts at 1, UNIQUE(frame_icd_id, rev).
                        "Current" = highest rev — no mutable pointer.

Additive only — no existing row touched.

Hand-written per Mason's standing rule.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0044"
down_revision: Union[str, None] = "0043"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS frame_icds (
            id SERIAL PRIMARY KEY,
            key VARCHAR(100) NOT NULL UNIQUE,
            name VARCHAR(255) NOT NULL,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            created_by_id INTEGER NOT NULL REFERENCES users(id)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_frame_icds_key ON frame_icds (key)"
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS frame_icd_revisions (
            id SERIAL PRIMARY KEY,
            frame_icd_id INTEGER NOT NULL
                REFERENCES frame_icds(id) ON DELETE CASCADE,
            rev INTEGER NOT NULL,
            datum VARCHAR(100) NOT NULL,
            axes VARCHAR(100) NOT NULL,
            units VARCHAR(20) NOT NULL,
            rules TEXT NOT NULL,
            notes TEXT,
            created_at TIMESTAMPTZ DEFAULT NOW(),
            created_by_id INTEGER NOT NULL REFERENCES users(id),
            CONSTRAINT uq_frame_icd_rev UNIQUE (frame_icd_id, rev)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_frame_icd_revisions_frame_icd_id "
        "ON frame_icd_revisions (frame_icd_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS frame_icd_revisions")
    op.execute("DROP TABLE IF EXISTS frame_icds")
