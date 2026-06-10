"""CADPORT-TDD-ASTRA-BRIDGE-001 Phase 2: source-file document types.

Revision ID: 0042
Revises: 0041
Create Date: 2026-06-10

Adds the source-CAD-file document types (``sldprt``, ``sldasm``,
``step``) to the existing ``supplier_document_type`` enum and three
new FK columns on ``catalog_parts`` to link each kind back to its
``supplier_documents`` row:

  catalog_parts.sldprt_document_id INTEGER NULL  REFERENCES supplier_documents(id) ON DELETE SET NULL
  catalog_parts.sldasm_document_id INTEGER NULL  REFERENCES supplier_documents(id) ON DELETE SET NULL
  catalog_parts.step_document_id   INTEGER NULL  REFERENCES supplier_documents(id) ON DELETE SET NULL

Mirrors the existing ``stl_document_id`` column shape (CADPORT-REBUILD-004
migration 0038). The new enum values pair with the spec §2.4 payload:

  source_files: [
    {kind: 'sldprt'|'sldasm'|'step', filename, sha256, content_base64}
  ]

ALTER TYPE ADD VALUE cannot run inside the migration's transaction
(PG limitation), same dance as 0029 / 0036.

Hand-written per Mason's standing rule.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0042"
down_revision: Union[str, None] = "0041"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # supplier_document_type enum — add the three CAD source kinds.
    # autocommit_block because ALTER TYPE ADD VALUE cannot run in
    # the migration transaction.
    with op.get_context().autocommit_block():
        for kind in ("sldprt", "sldasm", "step"):
            op.execute(
                f"ALTER TYPE supplier_document_type ADD VALUE IF NOT EXISTS '{kind}'"
            )

    # catalog_parts — three new nullable FK columns.
    for col in ("sldprt_document_id", "sldasm_document_id", "step_document_id"):
        op.execute(
            f"ALTER TABLE catalog_parts "
            f"ADD COLUMN IF NOT EXISTS {col} INTEGER"
        )
        op.execute(
            f"ALTER TABLE catalog_parts "
            f"ADD CONSTRAINT fk_catalog_parts_{col} "
            f"FOREIGN KEY ({col}) REFERENCES supplier_documents(id) "
            f"ON DELETE SET NULL"
        )


def downgrade() -> None:
    for col in ("sldprt_document_id", "sldasm_document_id", "step_document_id"):
        op.execute(
            f"ALTER TABLE catalog_parts DROP CONSTRAINT IF EXISTS fk_catalog_parts_{col}"
        )
        op.execute(f"ALTER TABLE catalog_parts DROP COLUMN IF EXISTS {col}")
    # ALTER TYPE DROP VALUE is not supported in Postgres — leave the
    # enum values in place on downgrade (matches the 0036 pattern).
