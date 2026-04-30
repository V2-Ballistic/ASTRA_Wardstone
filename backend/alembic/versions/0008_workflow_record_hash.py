"""F-007 + F-008: workflow enum values_callable + e-signature record_hash

Revision ID: 0008
Revises: 4bd35db2ef64
Create Date: 2026-04-30

F-007 (workflow SQLEnum values_callable): the SQLAlchemy column
declarations on `models/workflow.py` now pass values_callable so the
ORM uses lowercase enum values (.value) when reading/writing. The
Postgres enum types `workflowstatus`, `instancestatus`, and
`signaturemeaning` were ALREADY created with lowercase labels by
migration 0001 (see 0001_initial_schema.py:320-327, which used
`postgresql.ENUM("active", "inactive", …)` with literal lowercase
strings). pg_enum was inspected pre-migration and confirmed lowercase
across all twelve labels. So no `ALTER TYPE … RENAME VALUE` is
necessary — the in-DB state already matches what the ORM now emits.

F-008 (21 CFR Part 11 §11.70 record-binding): adds a nullable
`record_hash` column to electronic_signatures so the signature can be
bound to the signed entity's content at sign time. signature_service
populates it on every new sign and verifies it on read; rows from
before this migration (none expected — F-002 had the entire workflow
subsystem unreachable until commit d495747) stay null and are treated
as "unbound legacy" by the verifier.

This migration is idempotent for the column add via IF NOT EXISTS.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "0008"
down_revision: Union[str, None] = "4bd35db2ef64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent: safe to re-apply on a partially-stamped database.
    op.execute("""
        ALTER TABLE electronic_signatures
        ADD COLUMN IF NOT EXISTS record_hash VARCHAR(64);
    """)


def downgrade() -> None:
    op.execute("""
        ALTER TABLE electronic_signatures
        DROP COLUMN IF EXISTS record_hash;
    """)
