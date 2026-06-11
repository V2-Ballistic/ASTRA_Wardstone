"""ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §6: aero decks (HAROLD-named, AER).

Revision ID: 0046
Revises: 0045
Create Date: 2026-06-10

Creates the engineering-hub aero-deck tables:

  aero_decks           — deck identity (BASE WPN, no revision letter)
  aero_deck_revisions  — immutable revisions; each row carries the
                         FULL HAROLD-issued WPN, the raw source text,
                         and the normalized astra-aero-deck/1.0 deck
                         (JSONB) plus its canonical-JSON sha256 and a
                         denormalized mach/alpha envelope for the
                         list view.

aero_decks.active_revision_id ↔ aero_deck_revisions.aero_deck_id is a
deliberate FK cycle; the active-revision FK is added AFTER both tables
exist (NOT VALID-free since both are empty at migration time).

All DDL uses IF NOT EXISTS — safe to run on a populated DB and
re-runnable. Hand-written per Mason's standing rule (no autogenerate).
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0046"
down_revision: Union[str, None] = "0045"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS aero_decks (
            id                  SERIAL PRIMARY KEY,
            wpn                 VARCHAR(64)  NOT NULL,
            base_index          INTEGER,
            system_code         VARCHAR(8)   NOT NULL DEFAULT 'AER',
            name                VARCHAR(500) NOT NULL,
            oml_wpn             VARCHAR(64),
            active_revision_id  INTEGER,
            created_by_id       INTEGER REFERENCES users(id)
                                    ON DELETE SET NULL,
            created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_aero_decks_wpn UNIQUE (wpn)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_aero_decks_wpn ON aero_decks(wpn)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS aero_deck_revisions (
            id                SERIAL PRIMARY KEY,
            aero_deck_id      INTEGER NOT NULL
                                  REFERENCES aero_decks(id)
                                  ON DELETE CASCADE,
            wpn               VARCHAR(64) NOT NULL,
            rev_letter        VARCHAR(8)  NOT NULL,
            source_filenames  JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_sha256s    JSONB NOT NULL DEFAULT '[]'::jsonb,
            source_text       TEXT,
            deck              JSONB NOT NULL,
            deck_sha256       VARCHAR(64) NOT NULL,
            mach_min          DOUBLE PRECISION,
            mach_max          DOUBLE PRECISION,
            alpha_min_deg     DOUBLE PRECISION,
            alpha_max_deg     DOUBLE PRECISION,
            sref_m2           DOUBLE PRECISION,
            lref_m            DOUBLE PRECISION,
            defaulted_fields  JSONB NOT NULL DEFAULT '[]'::jsonb,
            warnings          JSONB NOT NULL DEFAULT '[]'::jsonb,
            notes             TEXT,
            created_by_id     INTEGER REFERENCES users(id)
                                  ON DELETE SET NULL,
            created_utc       TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_aero_deck_revisions_wpn UNIQUE (wpn),
            CONSTRAINT uq_aero_deck_revisions_deck_rev
                UNIQUE (aero_deck_id, rev_letter)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_aero_deck_revisions_aero_deck_id "
        "ON aero_deck_revisions(aero_deck_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_aero_deck_revisions_wpn "
        "ON aero_deck_revisions(wpn)"
    )

    # FK half of the deliberate cycle — added after both tables exist.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_aero_decks_active_revision_id'
            ) THEN
                ALTER TABLE aero_decks
                    ADD CONSTRAINT fk_aero_decks_active_revision_id
                    FOREIGN KEY (active_revision_id)
                    REFERENCES aero_deck_revisions(id)
                    ON DELETE SET NULL;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE aero_decks "
        "DROP CONSTRAINT IF EXISTS fk_aero_decks_active_revision_id"
    )
    op.execute("DROP TABLE IF EXISTS aero_deck_revisions")
    op.execute("DROP TABLE IF EXISTS aero_decks")
