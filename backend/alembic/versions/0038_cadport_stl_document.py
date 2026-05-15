"""CADPORT-REBUILD-004: STL mesh document linkage

Revision ID: 0038
Revises: 0037
Create Date: 2026-05-15

TDD-4 adds real CAD geometry to the assembly viewer. The bridge
exports a binary STL per part during extraction; ASTRA stores it as
a supplier_documents row (document_type='stl') and points
catalog_parts.stl_document_id at it. The Three.js viewer + the
part-detail STL download fetch the mesh through the existing
/catalog/documents/{id}/file route.

Additive only:

  supplier_document_type enum — gains 'stl' (autocommit block per the
    0029/0036 pattern; ALTER TYPE ... ADD VALUE cannot run inside the
    migration transaction).

  catalog_parts.stl_document_id — nullable FK → supplier_documents,
    ON DELETE SET NULL. NULL is the legitimate state for parts whose
    SW STL export failed or that predate this feature (viewer falls
    back to a schematic box).

ADD COLUMN IF NOT EXISTS — safe on a populated DB, re-runnable. No
autogenerate (standing rule 2).
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0038"
down_revision: Union[str, None] = "0037"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── supplier_document_type enum: + 'stl' ────────────────────────
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE supplier_document_type ADD VALUE IF NOT EXISTS 'stl'"
        )

    # ── catalog_parts.stl_document_id ───────────────────────────────
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS stl_document_id INTEGER"
    )
    # Add the FK constraint separately + idempotently (ADD CONSTRAINT
    # has no IF NOT EXISTS; guard via the catalog).
    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_catalog_parts_stl_document_id'
            ) THEN
                ALTER TABLE catalog_parts
                    ADD CONSTRAINT fk_catalog_parts_stl_document_id
                    FOREIGN KEY (stl_document_id)
                    REFERENCES supplier_documents(id) ON DELETE SET NULL;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE catalog_parts "
        "DROP CONSTRAINT IF EXISTS fk_catalog_parts_stl_document_id"
    )
    op.execute(
        "ALTER TABLE catalog_parts DROP COLUMN IF EXISTS stl_document_id"
    )
    # The 'stl' enum value is intentionally NOT removed on downgrade —
    # PG cannot DROP an enum value, and leaving it is harmless.
