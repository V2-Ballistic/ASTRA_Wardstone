"""CADPORT-REBUILD-002: catalog mass-property columns + cadport assemblies

Revision ID: 0036
Revises: 0035
Create Date: 2026-05-15

TDD-2 of the CADPORT rebuild program wires CADPORT extraction into
ASTRA's catalog. This migration is the schema half (additive only):

  catalog_parts — CAD mass-property columns (CITADEL body frame, SI
    units) parsed out of the §6 part YAML for column-level
    display/query without opening the blob, plus the linkage spine
    columns `cadport_part_id` (L4) and `content_hash` (dedup gate,
    AD-2). `mass_kg` already exists (Numeric(10,4) from INTF-002) so
    it is NOT re-added; the new physics columns are DOUBLE PRECISION
    to preserve full extraction precision.

  supplier_document_type enum — gains 'yaml' so the §6 YAMLs can be
    stored as `supplier_documents` rows with a truthful document_type
    (AD-5). Added in an autocommit block per the 0029 pattern
    (ALTER TYPE ... ADD VALUE cannot run inside the migration's
    transaction).

  cadport_assemblies + cadport_assembly_components — the assembly↔
    project linkage (L7) and the per-instance component map (AD-7).

All column adds use ADD COLUMN IF NOT EXISTS; all tables use
CREATE TABLE IF NOT EXISTS. Safe to run on a populated DB and
re-runnable. No autogenerate (standing rule 2).
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0036"
down_revision: Union[str, None] = "0035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Physics columns: DOUBLE PRECISION, nullable. Names match the §6 YAML
# mass_properties block (CITADEL body frame, SI). mass_kg intentionally
# excluded — it already exists as Numeric(10,4).
_PHYSICS_COLS = [
    "volume_m3",
    "surface_area_m2",
    "density_kg_m3",
    "center_of_mass_x",
    "center_of_mass_y",
    "center_of_mass_z",
    "ixx",
    "iyy",
    "izz",
    "ixy",
    "ixz",
    "iyz",
]


def upgrade() -> None:
    # ── catalog_parts: physics columns ──────────────────────────────
    for col in _PHYSICS_COLS:
        op.execute(
            f"ALTER TABLE catalog_parts "
            f"ADD COLUMN IF NOT EXISTS {col} DOUBLE PRECISION"
        )

    # ── catalog_parts: linkage spine ────────────────────────────────
    # cadport_part_id is the immutable §5 spine key (L4). UUID, nullable
    # (legitimate NULL for non-CADPORT parts), unique among non-NULLs.
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS cadport_part_id UUID"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_catalog_parts_cadport_part_id "
        "ON catalog_parts(cadport_part_id) "
        "WHERE cadport_part_id IS NOT NULL"
    )
    # content_hash drives the AD-2 dedup gate. sha256 hex is 64 chars
    # but the YAML carries the 'sha256:' prefix → VARCHAR(256) is
    # generous and matches the AD-1/AD-2 spec.
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS content_hash VARCHAR(256)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_catalog_parts_content_hash "
        "ON catalog_parts(content_hash)"
    )

    # ── supplier_document_type enum: + 'yaml' ───────────────────────
    # ALTER TYPE ... ADD VALUE cannot run inside the migration's
    # transaction (PG). autocommit_block per the 0029 pattern.
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE supplier_document_type ADD VALUE IF NOT EXISTS 'yaml'"
        )

    # ── cadport_assemblies (L7: assembly ↔ project) ─────────────────
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cadport_assemblies (
            id                        SERIAL PRIMARY KEY,
            assembly_id               UUID NOT NULL UNIQUE,
            project_id                INTEGER NOT NULL
                                        REFERENCES projects(id) ON DELETE CASCADE,
            display_name              VARCHAR(500) NOT NULL,
            source_file               VARCHAR(500) NOT NULL,
            content_hash              VARCHAR(256),
            total_mass_kg             DOUBLE PRECISION,
            center_of_mass_x          DOUBLE PRECISION,
            center_of_mass_y          DOUBLE PRECISION,
            center_of_mass_z          DOUBLE PRECISION,
            component_count           INTEGER NOT NULL DEFAULT 0,
            solidworks_version        VARCHAR(64),
            assembly_yaml_document_id INTEGER
                                        REFERENCES supplier_documents(id) ON DELETE SET NULL,
            created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at                TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cadport_assemblies_project_id "
        "ON cadport_assemblies(project_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cadport_assemblies_content_hash "
        "ON cadport_assemblies(content_hash)"
    )

    # ── cadport_assembly_components (the per-instance component map) ─
    op.execute(
        """
        CREATE TABLE IF NOT EXISTS cadport_assembly_components (
            id              SERIAL PRIMARY KEY,
            assembly_id     INTEGER NOT NULL
                              REFERENCES cadport_assemblies(id) ON DELETE CASCADE,
            catalog_part_id INTEGER
                              REFERENCES catalog_parts(id) ON DELETE SET NULL,
            cadport_part_id UUID,
            instance_name   VARCHAR(500) NOT NULL,
            quantity        INTEGER NOT NULL DEFAULT 1,
            transform_json  TEXT,
            suppressed      BOOLEAN NOT NULL DEFAULT FALSE
        )
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cadport_assembly_components_assembly_id "
        "ON cadport_assembly_components(assembly_id)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_cadport_assembly_components_catalog_part_id "
        "ON cadport_assembly_components(catalog_part_id)"
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS cadport_assembly_components")
    op.execute("DROP TABLE IF EXISTS cadport_assemblies")
    op.execute("DROP INDEX IF EXISTS ix_catalog_parts_content_hash")
    op.execute("ALTER TABLE catalog_parts DROP COLUMN IF EXISTS content_hash")
    op.execute("DROP INDEX IF EXISTS ix_catalog_parts_cadport_part_id")
    op.execute("ALTER TABLE catalog_parts DROP COLUMN IF EXISTS cadport_part_id")
    for col in _PHYSICS_COLS:
        op.execute(f"ALTER TABLE catalog_parts DROP COLUMN IF EXISTS {col}")
    # The 'yaml' enum value is intentionally NOT removed on downgrade —
    # PG cannot DROP an enum value, and leaving it is harmless.
