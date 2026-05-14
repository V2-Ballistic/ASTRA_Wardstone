"""ASTRA-TDD-PROJPARTS-001 (Path C): extend project_parts with BOM columns

Revision ID: 0030
Revises: 0029
Create Date: 2026-05-11

Path C per docs/PROJPARTS_INVESTIGATION.md — extend the existing
`project_parts` table in place rather than introduce a parallel
`project_part_instances` table. Adds the catalog_part_id link, the
BOM hierarchy / status / unit-linkage columns, widens designation,
changes quantity from INTEGER to NUMERIC(12,4) for fractional units,
drops the (project_id, library_part_id) uniqueness so the same
catalog part can appear as multiple BOM lines, and adds a partial
UNIQUE on (project_id, bom_position) WHERE bom_position IS NOT NULL.

Pre-flight data check (run via psql before writing this) showed
**zero rows** in project_parts, mechanical_joints, and
system_part_assignments, so the quantity type change and the
constraint swap have no migration risk on the current install.

The investigation report mentioned a CAT-002 `metadata_json.legacy_id`
backfill marker; that column does not actually exist on the
committed `catalog_parts` schema (the originally-drafted CAT-001
unified migration was reverted and CAT-002 / 0029 shipped only
additive CAD columns). `project_parts.catalog_part_id` therefore
ships as a plain nullable FK — Phase 2 backend logic will populate
it on every new write, and any legacy rows (none today) can be
backfilled in a follow-up data migration once a deterministic
library_parts ↔ catalog_parts mapping exists.

Downstream consumers (`mechanical_joints.part_a_id/b_id`,
`system_part_assignments.project_part_id`) keep their FKs to
`project_parts(id)` — no changes there. They keep working.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0030"
down_revision: Union[str, None] = "0029"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ─────────────────────────────────────────────────────────────
    # 1. bom_status enum
    # ─────────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TYPE bom_status AS ENUM (
            'planned', 'released', 'procured', 'received',
            'installed', 'verified', 'obsolete'
        )
        """
    )

    # ─────────────────────────────────────────────────────────────
    # 2. Add BOM columns to project_parts (all nullable except the
    #    enums/defaults — backwards compatible with existing rows
    #    even though the table is empty today).
    # ─────────────────────────────────────────────────────────────
    op.execute(
        """
        ALTER TABLE project_parts
            ADD COLUMN IF NOT EXISTS catalog_part_id INTEGER
                REFERENCES catalog_parts(id) ON DELETE RESTRICT,
            ADD COLUMN IF NOT EXISTS bom_position VARCHAR(64),
            ADD COLUMN IF NOT EXISTS parent_bom_id BIGINT
                REFERENCES project_parts(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS quantity_unit VARCHAR(16)
                NOT NULL DEFAULT 'each',
            ADD COLUMN IF NOT EXISTS status bom_status
                NOT NULL DEFAULT 'planned',
            ADD COLUMN IF NOT EXISTS unit_id INTEGER
                REFERENCES units(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS location_zone VARCHAR(128),
            ADD COLUMN IF NOT EXISTS installation_notes TEXT,
            ADD COLUMN IF NOT EXISTS procurement_notes TEXT,
            ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ
                NOT NULL DEFAULT NOW()
        """
    )

    # ─────────────────────────────────────────────────────────────
    # 3. Widen `designation` 64 → 255 chars. The original 64 was a
    #    tight cap for free-text BOM-line names ("M5×16 SHCS, chassis
    #    bay 2, primary mount" easily exceeds 64). The cast is
    #    automatic when the new type is wider than the old one.
    # ─────────────────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE project_parts ALTER COLUMN designation TYPE VARCHAR(255)"
    )

    # ─────────────────────────────────────────────────────────────
    # 4. Change `quantity` from INTEGER → NUMERIC(12,4) so fractional
    #    quantities (3.5 m of cable, 0.25 L of adhesive) are usable.
    #    The default 1 carries forward as 1.0000; zero rows today so
    #    the USING cast has nothing to fail on.
    #
    #    The existing CHECK (quantity >= 1) is dropped and replaced
    #    with CHECK (quantity > 0) — fractional quantities below 1
    #    are now legal, but zero / negative are not.
    # ─────────────────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE project_parts ALTER COLUMN quantity "
        "TYPE NUMERIC(12,4) USING quantity::numeric"
    )
    op.execute(
        "ALTER TABLE project_parts ALTER COLUMN quantity SET DEFAULT 1.0"
    )
    op.execute(
        "ALTER TABLE project_parts DROP CONSTRAINT IF EXISTS chk_pp_quantity_positive"
    )
    op.execute(
        "ALTER TABLE project_parts "
        "ADD CONSTRAINT chk_pp_quantity_positive CHECK (quantity > 0)"
    )

    # ─────────────────────────────────────────────────────────────
    # 5. Replace the legacy UNIQUE (project_id, library_part_id) with
    #    a partial UNIQUE on (project_id, bom_position) WHERE
    #    bom_position IS NOT NULL.
    #
    #    Rationale: BOM lines legitimately have the same catalog
    #    part appearing multiple times under different positions
    #    (24× M5 bolts in chassis assembly + 8× M5 bolts in radio
    #    bay = two BOM lines, same library_part). The position-based
    #    uniqueness preserves "no two lines share the same BOM
    #    position" without blocking duplicate part references.
    # ─────────────────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE project_parts DROP CONSTRAINT IF EXISTS uq_project_part"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_project_parts_bom_position "
        "ON project_parts (project_id, bom_position) "
        "WHERE bom_position IS NOT NULL"
    )

    # ─────────────────────────────────────────────────────────────
    # 6. Indexes on the new FK / filter columns
    # ─────────────────────────────────────────────────────────────
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_project_parts_catalog_part "
        "ON project_parts(catalog_part_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_project_parts_parent_bom "
        "ON project_parts(parent_bom_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_project_parts_unit "
        "ON project_parts(unit_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_project_parts_status "
        "ON project_parts(status)"
    )


def downgrade() -> None:
    """Reverse the BOM extension. The library_part_id FK + the
    integer-quantity world is restored, with one caveat: rows that
    accumulated fractional quantities or duplicate library_part
    references between upgrade and downgrade will FAIL to satisfy
    the original constraints — caller must clean those up first.
    """
    op.execute("DROP INDEX IF EXISTS ix_project_parts_status")
    op.execute("DROP INDEX IF EXISTS ix_project_parts_unit")
    op.execute("DROP INDEX IF EXISTS ix_project_parts_parent_bom")
    op.execute("DROP INDEX IF EXISTS ix_project_parts_catalog_part")
    op.execute("DROP INDEX IF EXISTS uq_project_parts_bom_position")

    op.execute(
        "ALTER TABLE project_parts ADD CONSTRAINT uq_project_part "
        "UNIQUE (project_id, library_part_id)"
    )

    op.execute(
        "ALTER TABLE project_parts DROP CONSTRAINT IF EXISTS chk_pp_quantity_positive"
    )
    op.execute(
        "ALTER TABLE project_parts "
        "ADD CONSTRAINT chk_pp_quantity_positive CHECK (quantity >= 1)"
    )
    op.execute(
        "ALTER TABLE project_parts ALTER COLUMN quantity "
        "TYPE INTEGER USING quantity::integer"
    )
    op.execute(
        "ALTER TABLE project_parts ALTER COLUMN quantity SET DEFAULT 1"
    )

    op.execute(
        "ALTER TABLE project_parts ALTER COLUMN designation TYPE VARCHAR(64)"
    )

    op.execute(
        """
        ALTER TABLE project_parts
            DROP COLUMN IF EXISTS updated_at,
            DROP COLUMN IF EXISTS procurement_notes,
            DROP COLUMN IF EXISTS installation_notes,
            DROP COLUMN IF EXISTS location_zone,
            DROP COLUMN IF EXISTS unit_id,
            DROP COLUMN IF EXISTS status,
            DROP COLUMN IF EXISTS quantity_unit,
            DROP COLUMN IF EXISTS parent_bom_id,
            DROP COLUMN IF EXISTS bom_position,
            DROP COLUMN IF EXISTS catalog_part_id
        """
    )

    op.execute("DROP TYPE IF EXISTS bom_status")
