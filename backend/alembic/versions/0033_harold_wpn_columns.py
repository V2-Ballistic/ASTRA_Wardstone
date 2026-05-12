"""ASTRA-TDD-HAROLD-INT-002 Phase 1: WPN columns + fallback sequences

Revision ID: 0033
Revises: 0032
Create Date: 2026-05-12

Lands the schema additions needed to integrate ASTRA with HAROLD V2:

  catalog_parts
    internal_part_number  VARCHAR(32) NULL UNIQUE (partial, where NOT NULL)
      The Wardstone Part Number assigned by HAROLD on approval — the
      canonical Wardstone identity for the part. Manufacturer's
      `part_number` (MPN) remains the supplier-side identity.

    wpn_pending_sync      BOOLEAN NOT NULL DEFAULT FALSE
      TRUE when ASTRA assigned a fallback WPN (HAROLD was unreachable
      at approval time). Cleared by the manual "Sync with HAROLD"
      action or the (future) reconciliation worker.

  catalog_wpn_fallback_sequences
    Local per-system counters used when HAROLD is unreachable. Mirror
    of HAROLD's own `wpn_sequences` table; reconciles via the
    manual-sync flow described in HAROLD-INTEGRATION-002 §Phase 3.
    Seeded with all 21 codes (17 V1 project-system + 4 V2 library)
    at next_index=1.

Lock #8 of the integration prompt. McMaster row (catalog_parts.id=1)
gets internal_part_number=NULL by default; no backfill — per prompt
gotcha #9 Mason decides whether to retroactively assign WPNs.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0033"
down_revision: Union[str, None] = "0032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_FALLBACK_SEED_CODES: tuple[str, ...] = (
    # Project-system codes (HAROLD V1, 17)
    "VH", "AE", "AS", "AV", "BT", "CC", "CG", "EE", "FC", "GN", "GS",
    "OR", "PR", "ST", "TH", "TS", "WH",
    # Library-category codes (HAROLD V2 additions per AD-3)
    "FH", "MH", "EH", "SH",
)


def upgrade() -> None:
    # catalog_parts.internal_part_number — the Wardstone WPN. Unique
    # only where set; a NULL means "no WPN assigned yet" (legitimate
    # state for parts uploaded before integration enabled, or while
    # HAROLD is unreachable and approval hasn't happened yet).
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS internal_part_number VARCHAR(32)"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_catalog_parts_internal_wpn "
        "ON catalog_parts(internal_part_number) "
        "WHERE internal_part_number IS NOT NULL"
    )

    # catalog_parts.wpn_pending_sync — fallback-allocator marker.
    # Filtered index because the column is FALSE on the overwhelming
    # majority of rows; only the TRUE rows are interesting (reconcile
    # candidates).
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS wpn_pending_sync BOOLEAN "
        "NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_catalog_parts_pending_sync "
        "ON catalog_parts(wpn_pending_sync) WHERE wpn_pending_sync = TRUE"
    )

    # catalog_wpn_fallback_sequences — local allocator counters. One
    # row per system code in the 21-code set. The allocator service
    # (Phase 2 fallback.py) row-locks with FOR UPDATE.
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS catalog_wpn_fallback_sequences (
            system_code  VARCHAR(2)   PRIMARY KEY,
            next_index   INTEGER      NOT NULL DEFAULT 1,
            updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            CONSTRAINT ck_fallback_next_index_positive CHECK (next_index >= 1),
            CONSTRAINT ck_fallback_next_index_max      CHECK (next_index <= 1000000)
        )
        """
    )

    # Seed all 21 codes at next_index=1. ON CONFLICT DO NOTHING so
    # re-running this migration on a previously-seeded DB is safe.
    for code in _FALLBACK_SEED_CODES:
        op.execute(
            f"INSERT INTO catalog_wpn_fallback_sequences (system_code) "
            f"VALUES ('{code}') ON CONFLICT (system_code) DO NOTHING"
        )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS catalog_wpn_fallback_sequences CASCADE")
    op.execute("DROP INDEX IF EXISTS ix_catalog_parts_pending_sync")
    op.execute("DROP INDEX IF EXISTS ix_catalog_parts_internal_wpn")
    op.execute(
        "ALTER TABLE catalog_parts DROP COLUMN IF EXISTS wpn_pending_sync"
    )
    op.execute(
        "ALTER TABLE catalog_parts DROP COLUMN IF EXISTS internal_part_number"
    )
