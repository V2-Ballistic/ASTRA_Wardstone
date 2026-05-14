"""Interface module schema-drift backfill

Revision ID: 0035
Revises: 0034
Create Date: 2026-05-14

Three pieces of model-vs-DB drift the HAROLD-IN-WRENCH cleanup
TRUNCATE surfaced (the /interfaces/* endpoints started 500-ing
because they project the full ORM column list / select from
declared tables, and these had silently never been migrated):

  1. wire_harnesses — 9 columns the "Phase 1: Harness Overview
     editable attributes" feature added to the model (see
     models/interface.py:1601). All nullable.

  2. connections — the LRU-pair rollup table the model declares at
     interface.py:1890 with the comment "Schema-drift sync:
     created by 0007". 0007 doesn't actually create it. The
     /interfaces/connections endpoint SELECTs from this table.

  3. harness_endpoints — same situation. Model at
     interface.py:1860 comments "created by 0007"; 0007 doesn't.

All three were masked while no live UI exercised the harness-loading
endpoints; the post-truncate state exposed all three at once.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0035"
down_revision: Union[str, None] = "0034"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_NEW_COLUMNS: tuple[str, ...] = (
    # name              type
    "shielding_class      VARCHAR(50)",
    "sleeve_type          VARCHAR(50)",
    "operating_temp_min_c DOUBLE PRECISION",
    "operating_temp_max_c DOUBLE PRECISION",
    "min_bend_radius_mm   DOUBLE PRECISION",
    "weight_g_per_m       DOUBLE PRECISION",
    "drain_wire_spec      VARCHAR(100)",
    "service_loop_m       DOUBLE PRECISION",
    "mil_spec             VARCHAR(100)",
)


def upgrade() -> None:
    # ── (1) wire_harnesses Harness Overview columns ──
    for col in _NEW_COLUMNS:
        op.execute(
            f"ALTER TABLE wire_harnesses ADD COLUMN IF NOT EXISTS {col}"
        )

    # ── (2) connections — LRU-pair rollup ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS connections (
            id          SERIAL       PRIMARY KEY,
            project_id  INTEGER      NOT NULL
                          REFERENCES projects(id) ON DELETE CASCADE,
            lru_a_id    INTEGER      NOT NULL
                          REFERENCES units(id) ON DELETE CASCADE,
            lru_b_id    INTEGER      NOT NULL
                          REFERENCES units(id) ON DELETE CASCADE,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_connection_pair UNIQUE (lru_a_id, lru_b_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_connections_project ON connections(project_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_connections_lru_a   ON connections(lru_a_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_connections_lru_b   ON connections(lru_b_id)")

    # ── (3) harness_endpoints — per-end mating connector record ──
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS harness_endpoints (
            id                   SERIAL       PRIMARY KEY,
            harness_id           INTEGER      NOT NULL
                                   REFERENCES wire_harnesses(id) ON DELETE CASCADE,
            mating_connector_id  INTEGER      NOT NULL
                                   REFERENCES connectors(id) ON DELETE CASCADE,
            lru_connector_id     INTEGER      NULL
                                   REFERENCES connectors(id) ON DELETE SET NULL,
            label                VARCHAR(40)  NULL,
            tail_length_m        DOUBLE PRECISION NULL,
            notes                TEXT         NULL,
            created_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            CONSTRAINT uq_lru_connector_once UNIQUE (lru_connector_id)
        )
        """
    )
    op.execute("CREATE INDEX IF NOT EXISTS ix_harness_endpoints_harness ON harness_endpoints(harness_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_harness_endpoints_lru     ON harness_endpoints(lru_connector_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_harness_endpoints_mating  ON harness_endpoints(mating_connector_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS harness_endpoints CASCADE")
    op.execute("DROP TABLE IF EXISTS connections CASCADE")
    for col in _NEW_COLUMNS:
        name = col.split()[0]
        op.execute(
            f"ALTER TABLE wire_harnesses DROP COLUMN IF EXISTS {name}"
        )
