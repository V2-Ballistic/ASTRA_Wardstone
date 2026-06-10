"""CADPORT-TDD-ASTRA-BRIDGE-001 Phase 3: bidirectional sync metadata.

Revision ID: 0043
Revises: 0042
Create Date: 2026-06-10

Adds two columns on ``catalog_parts`` to drive the Phase 3
bidirectional mass/material sync:

  catalog_parts.last_sync_origin TEXT NULL
  catalog_parts.last_sync_at     TIMESTAMPTZ NULL

``last_sync_origin`` records who last wrote to the row:
  - 'astra'   : edit landed via the public ASTRA mass/material PATCH
                (the request handler then propagates to CADPORT)
  - 'cadport' : edit landed via the internal /sync-from-cadport
                endpoint (propagation came from CADPORT — no
                outgoing call back, to prevent loops)

The internal /sync-from-* endpoints are the loop-breakers: they
update the row + stamp ``last_sync_origin`` without re-firing
propagation. Symmetric column on the CADPORT side (added via the
SQLite startup shim, not Alembic — CADPORT runs on SQLite).

Hand-written per Mason's standing rule.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0043"
down_revision: Union[str, None] = "0042"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS last_sync_origin TEXT"
    )
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS last_sync_at TIMESTAMPTZ"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE catalog_parts DROP COLUMN IF EXISTS last_sync_at")
    op.execute("ALTER TABLE catalog_parts DROP COLUMN IF EXISTS last_sync_origin")
