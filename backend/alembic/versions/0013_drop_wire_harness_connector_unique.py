"""F-078 / F-143: drop legacy uq_harness_connectors UniqueConstraint

Revision ID: 0013
Revises: 0012
Create Date: 2026-04-30

The 2-endpoint era of WireHarness used
    UNIQUE(from_connector_id, to_connector_id)
to enforce "this LRU pair already has a harness — don't create another."
Once HarnessEndpoint landed (migration 0007) with its own UNIQUE on
``harness_endpoints.lru_connector_id``, the old constraint became:

  * Wrong, because the multi-endpoint design wants TWO harnesses
    between the same LRUs (e.g. one power, one signal).
  * The proximate cause of F-143 — every auto-grow call that tried to
    re-create a harness for an already-bridged LRU pair raised
    `IntegrityError`, which the router mapped to a 500 and the
    auto-wire tests mistook for a generator bug.

Drop only the constraint. Leave the four NOT NULL columns
(`from_unit_id`, `from_connector_id`, `to_unit_id`, `to_connector_id`)
in place — relaxing those is a separate concern for whenever a true
multi-endpoint harness without "primary" from/to lands.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0013"
down_revision: Union[str, None] = "0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Use IF EXISTS via raw SQL because alembic's drop_constraint doesn't
    # have an `if_exists` flag in the version pinned here, and we want the
    # migration to be safe to re-run on a partially-migrated DB.
    op.execute(
        "ALTER TABLE wire_harnesses DROP CONSTRAINT IF EXISTS uq_harness_connectors"
    )


def downgrade() -> None:
    # Recreate the constraint. Will fail on any existing duplicate
    # (from_connector_id, to_connector_id) — which is intentional: a
    # downgrade should surface the data that the upgrade made possible.
    op.create_unique_constraint(
        "uq_harness_connectors",
        "wire_harnesses",
        ["from_connector_id", "to_connector_id"],
    )
