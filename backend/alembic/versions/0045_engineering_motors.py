"""ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §5 — engineering motors tables.

Revision ID: 0045
Revises: 0044
Create Date: 2026-06-10

Creates the Motors engineering domain:

  motors           — stable identity, one row per HAROLD MTR base
                     index. ``wpn`` is the HAROLD-issued base WPN
                     verbatim; ``base_index`` mirrors the ledger's
                     ``part_number_int`` (never derived locally).
  motor_revisions  — IMMUTABLE history. Every CSV ingest / design run
                     is a new row with HAROLD's next -REV letter.
                     UNIQUE(motor_id, rev_letter); never updated in
                     place (no UPDATE endpoints exist on revisions).

The motors.active_revision_id ↔ motor_revisions.motor_id FK cycle is
broken by adding the active-revision FK with a separate ALTER after
both tables exist.

Hand-written per Mason's standing rule.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0045"
down_revision: Union[str, None] = "0044"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS motors (
            id                  SERIAL PRIMARY KEY,
            wpn                 VARCHAR(32) NOT NULL UNIQUE,
            base_index          INTEGER NOT NULL,
            system_code         VARCHAR(8) NOT NULL DEFAULT 'MTR',
            name                VARCHAR(255) NOT NULL,
            motor_class         VARCHAR(8),
            active_revision_id  INTEGER,
            catalog_part_id     INTEGER REFERENCES catalog_parts(id) ON DELETE SET NULL,
            created_by_id       INTEGER NOT NULL REFERENCES users(id),
            created_at          TIMESTAMPTZ DEFAULT now(),
            updated_at          TIMESTAMPTZ DEFAULT now()
        )
        """
    )
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS motor_revisions (
            id                   SERIAL PRIMARY KEY,
            motor_id             INTEGER NOT NULL REFERENCES motors(id) ON DELETE CASCADE,
            wpn                  VARCHAR(32) NOT NULL UNIQUE,
            rev_letter           VARCHAR(4) NOT NULL,
            origin               VARCHAR(16) NOT NULL,
            design_inputs        JSONB,
            source_csv_filename  VARCHAR(500),
            source_csv_sha256    VARCHAR(64),
            source_csv_text      TEXT,
            artifact             JSONB NOT NULL,
            artifact_sha256      VARCHAR(64) NOT NULL,
            total_impulse_ns     DOUBLE PRECISION,
            peak_thrust_n        DOUBLE PRECISION,
            burn_time_s          DOUBLE PRECISION,
            isp_s                DOUBLE PRECISION,
            quality_tier         VARCHAR(16) NOT NULL,
            defaulted_fields     JSONB,
            warnings             JSONB,
            notes                TEXT,
            created_by_id        INTEGER NOT NULL REFERENCES users(id),
            created_utc          TIMESTAMPTZ DEFAULT now(),
            CONSTRAINT uq_motor_revision_letter UNIQUE (motor_id, rev_letter)
        )
        """
    )
    # Close the FK cycle after both tables exist.
    op.execute(
        """
        ALTER TABLE motors
        ADD CONSTRAINT fk_motors_active_revision
        FOREIGN KEY (active_revision_id)
        REFERENCES motor_revisions(id) ON DELETE SET NULL
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_motors_wpn ON motors (wpn)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_motors_base_index ON motors (base_index)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_motors_name ON motors (name)")
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_motor_revisions_motor "
        "ON motor_revisions (motor_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_motor_revisions_wpn "
        "ON motor_revisions (wpn)"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE motors DROP CONSTRAINT IF EXISTS fk_motors_active_revision"
    )
    op.execute("DROP TABLE IF EXISTS motor_revisions")
    op.execute("DROP TABLE IF EXISTS motors")
