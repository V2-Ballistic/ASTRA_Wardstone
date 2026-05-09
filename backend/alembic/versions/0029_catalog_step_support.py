"""ASTRA-TDD-CAT-002: catalog STEP support — CAD columns, mechanical part_class
values, supplier_aliases, Wardstone seed.

Revision ID: 0029
Revises: 0028
Create Date: 2026-05-15

Additive migration. Does NOT alter existing column shapes; only adds:
  * suppliers.is_in_house  (BOOLEAN NOT NULL DEFAULT FALSE)
  * supplier_aliases       (new table — for vendor auto-detect dedup)
  * 12 new mechanical values on the part_class PG enum
  * 12 nullable CAD columns on catalog_parts
  * Wardstone supplier seed + 5 aliases

All operations use IF NOT EXISTS / IF EXISTS so the migration is safely
re-runnable. ALTER TYPE ... ADD VALUE runs inside
``op.get_context().autocommit_block()`` per the pattern in
0028_add_l0_level.py — PostgreSQL forbids those inside a transaction.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0029"
down_revision: Union[str, None] = "0028"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Twelve mechanical / structural values introduced on the existing
# part_class PG enum. Lowercase string values; SQLAlchemy enum extraction
# uses .value, not str() — Python enum names like "FASTENER_SCREW" do not
# round-trip through PG. (Standing rule §3.)
_NEW_PART_CLASS_VALUES = (
    "fastener_screw",
    "fastener_bolt",
    "nut",
    "washer",
    "bracket",
    "housing",
    "enclosure",
    "seal_o_ring",
    "bearing",
    "spring",
    "structural_member",
    "mechanical_other",
)


def upgrade() -> None:
    # ─────────────────────────────────────────────────────────────
    # 1. suppliers.is_in_house
    # ─────────────────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE suppliers "
        "ADD COLUMN IF NOT EXISTS is_in_house BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # ─────────────────────────────────────────────────────────────
    # 2. supplier_aliases — vendor-name dedup map for auto-detect
    # ─────────────────────────────────────────────────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS supplier_aliases (
            id          BIGSERIAL    PRIMARY KEY,
            supplier_id INTEGER      NOT NULL REFERENCES suppliers(id) ON DELETE CASCADE,
            alias       VARCHAR(255) NOT NULL UNIQUE,
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_supplier_aliases_supplier "
        "ON supplier_aliases(supplier_id)"
    )

    # ─────────────────────────────────────────────────────────────
    # 3. Extend part_class enum with mechanical values
    #    Must run OUTSIDE the migration's enclosing transaction.
    # ─────────────────────────────────────────────────────────────
    with op.get_context().autocommit_block():
        for v in _NEW_PART_CLASS_VALUES:
            op.execute(
                f"ALTER TYPE part_class ADD VALUE IF NOT EXISTS '{v}'"
            )

    # ─────────────────────────────────────────────────────────────
    # 4. CAD columns on catalog_parts (all nullable, additive)
    # ─────────────────────────────────────────────────────────────
    for col_sql in [
        "ADD COLUMN IF NOT EXISTS part_subtype          VARCHAR(64)",
        "ADD COLUMN IF NOT EXISTS material_name         VARCHAR(128)",
        "ADD COLUMN IF NOT EXISTS material_class        VARCHAR(64)",
        "ADD COLUMN IF NOT EXISTS bbox_x_mm             NUMERIC(10,3)",
        "ADD COLUMN IF NOT EXISTS bbox_y_mm             NUMERIC(10,3)",
        "ADD COLUMN IF NOT EXISTS bbox_z_mm             NUMERIC(10,3)",
        "ADD COLUMN IF NOT EXISTS volume_mm3            NUMERIC(14,4)",
        "ADD COLUMN IF NOT EXISTS cad_step_path         TEXT",
        "ADD COLUMN IF NOT EXISTS cad_preview_path      TEXT",
        "ADD COLUMN IF NOT EXISTS cad_authoring_tool    VARCHAR(64)",
        "ADD COLUMN IF NOT EXISTS native_units          VARCHAR(16)",
        "ADD COLUMN IF NOT EXISTS deleted_at            TIMESTAMPTZ",
    ]:
        op.execute(f"ALTER TABLE catalog_parts {col_sql}")

    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_catalog_parts_material_class "
        "ON catalog_parts(material_class)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_catalog_parts_part_subtype "
        "ON catalog_parts(part_subtype)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_catalog_parts_deleted_at "
        "ON catalog_parts(deleted_at)"
    )

    # ─────────────────────────────────────────────────────────────
    # 5. Seed Wardstone in-house supplier + aliases
    #    Idempotent via ON CONFLICT. The seed only fires when 'mason'
    #    exists (the standing dev login). Test environments use
    #    Base.metadata.create_all + per-test fixture seeding instead
    #    of running this migration.
    # ─────────────────────────────────────────────────────────────
    op.execute(
        """
        INSERT INTO suppliers (
            name, short_name, country, is_active, is_in_house,
            created_by_id, created_at, updated_at
        )
        SELECT 'Wardstone', 'WS', 'US', TRUE, TRUE, u.id, NOW(), NOW()
        FROM users u
        WHERE u.username = 'mason'
        ON CONFLICT (name) DO UPDATE SET is_in_house = TRUE
        """
    )

    op.execute(
        """
        INSERT INTO supplier_aliases (supplier_id, alias)
        SELECT s.id, a.alias
        FROM suppliers s
        CROSS JOIN (VALUES
            ('Wardstone'),
            ('WardStone'),
            ('WARDSTONE'),
            ('Ward Stone'),
            ('WS')
        ) AS a(alias)
        WHERE s.name = 'Wardstone'
        ON CONFLICT (alias) DO NOTHING
        """
    )


def downgrade() -> None:
    """Reverse 0029. Forward-only on enum values — PG can't drop them
    cleanly. Indexes, columns, table, and Wardstone seed all reverse."""
    op.execute("DROP INDEX IF EXISTS ix_catalog_parts_material_class")
    op.execute("DROP INDEX IF EXISTS ix_catalog_parts_part_subtype")
    op.execute("DROP INDEX IF EXISTS ix_catalog_parts_deleted_at")

    for col in (
        "part_subtype", "material_name", "material_class",
        "bbox_x_mm", "bbox_y_mm", "bbox_z_mm",
        "volume_mm3",
        "cad_step_path", "cad_preview_path", "cad_authoring_tool",
        "native_units", "deleted_at",
    ):
        op.execute(f"ALTER TABLE catalog_parts DROP COLUMN IF EXISTS {col}")

    op.execute("DROP INDEX IF EXISTS ix_supplier_aliases_supplier")
    op.execute("DROP TABLE IF EXISTS supplier_aliases CASCADE")

    # Remove the Wardstone seed but keep any hand-edited rows linked to it.
    op.execute(
        "DELETE FROM suppliers WHERE name = 'Wardstone' AND is_in_house = TRUE"
    )
    op.execute("ALTER TABLE suppliers DROP COLUMN IF EXISTS is_in_house")

    # Note: PartClass enum values stay (PG can't drop them cleanly
    # without recreating the type). Harmless if unused.
