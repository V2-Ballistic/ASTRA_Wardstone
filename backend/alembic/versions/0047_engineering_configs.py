"""ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §8 — vehicle configurations.

Revision ID: 0047
Revises: 0046
Create Date: 2026-06-10

Creates the Configurations tracker:

  vehicle_configs           — stable identity, one row per HAROLD CFG
                              base index. ``wpn`` is HAROLD's issued
                              base WPN verbatim; ``base_index`` mirrors
                              the ledger's ``part_number_int``.
  vehicle_config_revisions  — IMMUTABLE history. Every BOM / aero /
                              stage-map change is a new row with
                              HAROLD's next -REV letter.
                              UNIQUE(vehicle_config_id, rev_letter);
                              no UPDATE endpoints exist on revisions.

The vehicle_configs.active_revision_id ↔
vehicle_config_revisions.vehicle_config_id FK cycle is broken by
adding the active-revision FK with a separate ALTER after both tables
exist (same pattern as 0045/0046).

All DDL uses IF NOT EXISTS — safe to run on a populated DB and
re-runnable. Hand-written per Mason's standing rule (no autogenerate).
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0047"
down_revision: Union[str, None] = "0046"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vehicle_configs (
            id                  SERIAL PRIMARY KEY,
            wpn                 VARCHAR(64)  NOT NULL UNIQUE,
            base_index          INTEGER,
            system_code         VARCHAR(8)   NOT NULL DEFAULT 'CFG',
            name                VARCHAR(500) NOT NULL,
            active_revision_id  INTEGER,
            created_by_id       INTEGER NOT NULL REFERENCES users(id),
            created_at          TIMESTAMPTZ DEFAULT now(),
            updated_at          TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vehicle_configs_wpn "
        "ON vehicle_configs (wpn)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vehicle_configs_base_index "
        "ON vehicle_configs (base_index)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vehicle_configs_name "
        "ON vehicle_configs (name)"
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS vehicle_config_revisions (
            id                 SERIAL PRIMARY KEY,
            vehicle_config_id  INTEGER NOT NULL
                                   REFERENCES vehicle_configs(id)
                                   ON DELETE CASCADE,
            wpn                VARCHAR(64) NOT NULL UNIQUE,
            rev_letter         VARCHAR(8)  NOT NULL,
            description        TEXT,
            top_assembly_wpn   VARCHAR(64),
            frame_icd_id       INTEGER NOT NULL REFERENCES frame_icds(id),
            frame_icd_rev      INTEGER NOT NULL,
            astra_baseline_id  INTEGER REFERENCES baselines(id)
                                   ON DELETE SET NULL,
            components         JSONB NOT NULL,
            aero_binding       JSONB,
            stage_map          JSONB NOT NULL DEFAULT '[]'::jsonb,
            rollup             JSONB NOT NULL,
            validation         JSONB NOT NULL DEFAULT '{}'::jsonb,
            notes              TEXT,
            created_by_id      INTEGER NOT NULL REFERENCES users(id),
            created_utc        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_vehicle_config_revision_letter
                UNIQUE (vehicle_config_id, rev_letter)
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vehicle_config_revisions_config "
        "ON vehicle_config_revisions (vehicle_config_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_vehicle_config_revisions_wpn "
        "ON vehicle_config_revisions (wpn)"
    )

    # FK half of the deliberate cycle — added after both tables exist.
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_vehicle_configs_active_revision'
            ) THEN
                ALTER TABLE vehicle_configs
                    ADD CONSTRAINT fk_vehicle_configs_active_revision
                    FOREIGN KEY (active_revision_id)
                    REFERENCES vehicle_config_revisions(id)
                    ON DELETE SET NULL;
            END IF;
        END $$
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE vehicle_configs "
        "DROP CONSTRAINT IF EXISTS fk_vehicle_configs_active_revision"
    )
    op.execute("DROP TABLE IF EXISTS vehicle_config_revisions")
    op.execute("DROP TABLE IF EXISTS vehicle_configs")
