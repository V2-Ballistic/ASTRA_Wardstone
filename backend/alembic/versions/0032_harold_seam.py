"""ASTRA-TDD-HAROLD-001: HAROLD nomenclature seam — system_code_2letter

Revision ID: 0032
Revises: 0031
Create Date: 2026-05-11

Adds the 2-letter system code column deferred from SYSARCH-002, used by
HAROLD's `WS-<SYS>-P<NNNN>-<REV>` CAD nomenclature standard. Column is
optional/nullable — ASTRA passes the value through to HAROLD but does
not enforce membership in HAROLD's canonical 17-value list (HAROLD
owns that list and may add codes faster than ASTRA can re-migrate).

Convention: stored uppercase. The value gets `.upper()`-ed at the
service / router boundary; no DB-level CHECK constraint here.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0032"
down_revision: Union[str, None] = "0031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE systems "
        "ADD COLUMN IF NOT EXISTS system_code_2letter VARCHAR(2)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_systems_code_2letter "
        "ON systems(system_code_2letter)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_systems_code_2letter")
    op.execute(
        "ALTER TABLE systems DROP COLUMN IF EXISTS system_code_2letter"
    )
