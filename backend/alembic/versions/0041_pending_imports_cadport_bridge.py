"""CADPORT-TDD-ASTRA-BRIDGE-001 Phase 1: pending-imports CADPORT bridge.

Revision ID: 0041
Revises: 0040
Create Date: 2026-06-10

Three additive changes on ``pending_catalog_imports`` so CADPORT
uploads can land here for review before committing to ``catalog_parts``:

  ALTER TABLE pending_catalog_imports
    ALTER COLUMN supplier_id DROP NOT NULL;

  ALTER TABLE pending_catalog_imports
    ADD COLUMN proposed_supplier_name VARCHAR(200);

  ALTER TABLE pending_catalog_imports
    ADD COLUMN source_kind VARCHAR(32) NOT NULL DEFAULT 'pdf';

The discriminator ``source_kind`` lets the existing approve handler
keep its PDF-extraction path unchanged while a new branch handles
``'cadport'`` rows. ``proposed_supplier_name`` captures the
'create-on-approval' choice from the supplier picker — the supplier
row itself is materialized at approve time via TDD-SUPPLIER-001's
``get_or_create_supplier``.

Hand-written per Mason's standing rule.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0041"
down_revision: Union[str, None] = "0040"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Make supplier_id nullable. CADPORT uploads that propose a NEW
    # supplier name leave supplier_id NULL until the operator approves.
    op.execute(
        "ALTER TABLE pending_catalog_imports "
        "ALTER COLUMN supplier_id DROP NOT NULL"
    )
    op.execute(
        "ALTER TABLE pending_catalog_imports "
        "ADD COLUMN IF NOT EXISTS proposed_supplier_name VARCHAR(200)"
    )
    op.execute(
        "ALTER TABLE pending_catalog_imports "
        "ADD COLUMN IF NOT EXISTS source_kind VARCHAR(32) "
        "NOT NULL DEFAULT 'pdf'"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE pending_catalog_imports "
        "DROP COLUMN IF EXISTS source_kind"
    )
    op.execute(
        "ALTER TABLE pending_catalog_imports "
        "DROP COLUMN IF EXISTS proposed_supplier_name"
    )
    # Note: setting supplier_id back to NOT NULL would fail on any
    # cadport rows that have it NULL. Skip on downgrade — the looser
    # constraint is forward-compatible with the pre-0041 PDF path
    # (every PDF upload still writes supplier_id explicitly).
