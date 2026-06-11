"""Config-ecosystem deltas (spec §7.2): catalog part role taxonomy.

Revision ID: 0049
Revises: 0048
Create Date: 2026-06-10

Adds one column on ``catalog_parts``:

  catalog_parts.role TEXT NULL

``role`` is the vehicle role taxonomy value carried over from CADPORT
(oml | structure | avionics | payload | propulsion | recovery |
ballast | other — see ``app/models/catalog.py::
CATALOG_PART_ROLE_TAXONOMY``, the mirror of CADPORT's
``cadport/services/roles.py::ROLE_TAXONOMY``). ``role='oml'`` flags
the airframe part. NULL on legacy rows / non-CADPORT parts. Values
are validated at the API boundary (from-cadport import + PATCH
/catalog/parts/{id}/role), not by a DB constraint — keeping the
column free-text TEXT matches the source_format/mass_source pattern
from migration 0040.

Hand-written per Mason's standing rule.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0049"
down_revision: Union[str, None] = "0048"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS role TEXT"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE catalog_parts DROP COLUMN IF EXISTS role")
