"""HAROLD-IN-WRENCH-001 Phase 6: original_filename on supplier_documents

Revision ID: 0034
Revises: 0033
Create Date: 2026-05-13

Phase 0 reconnaissance found ``supplier_documents`` has no column for
the original multipart upload filename — disk files are UUIDs and the
user-supplied ``title`` is what callers see. HAROLD's filename
precheck (Phase 5) needs to match a proposed CAD filename against
ASTRA's stored documents, which requires the actual filename to be
preserved.

Locked decision (Phase 0 §7 Q2) is option (a): add the column. Per
Phase 0 the column is nullable so existing rows don't need a forced
backfill — but we DO backfill from ``title`` on this same migration
because the STEP-upload path already sets ``title=original_filename``
in code, so most existing rows already have the filename in title and
we can recover it for free. Manual-supplier-doc uploads (which set
``title`` to a user-friendly string) get a NULL — HAROLD's precheck
ILIKE on original_filename naturally skips them.

This migration is additive + safe to run on a populated DB.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0034"
down_revision: Union[str, None] = "0033"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE supplier_documents "
        "ADD COLUMN IF NOT EXISTS original_filename VARCHAR(500)"
    )
    # Index because HAROLD's precheck queries via
    # `original_filename ILIKE '<stem>%'`. The trigram pattern would
    # need a GIN index for full ILIKE acceleration; a plain B-tree
    # works for the leading-anchored case the precheck actually uses.
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_supplier_documents_original_filename "
        "ON supplier_documents(original_filename)"
    )

    # Backfill from title on the STEP path (where title is already
    # the multipart filename per catalog.py:1997). Heuristic: only
    # backfill rows whose title looks like a filename (contains a
    # dot and no whitespace) so user-friendly titles on the
    # supplier-doc upload path keep their NULL — those weren't
    # filenames to begin with and shouldn't masquerade as ones.
    op.execute(
        "UPDATE supplier_documents "
        "SET original_filename = title "
        "WHERE original_filename IS NULL "
        "  AND title LIKE '%.%' "
        "  AND title NOT LIKE '% %'"
    )


def downgrade() -> None:
    op.execute(
        "DROP INDEX IF EXISTS ix_supplier_documents_original_filename"
    )
    op.execute(
        "ALTER TABLE supplier_documents "
        "DROP COLUMN IF EXISTS original_filename"
    )
