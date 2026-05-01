"""F-118: bus_protocol enum value 'oneWire' -> 'one_wire'.

Revision ID: 0022
Revises: 0021
Create Date: 2026-04-30

The enum had one camelCase outlier ('oneWire') in an otherwise
snake_case enum (mil_std_1553b, can_2b, spacewire, …). That broke
partial-string filters in the requirements / interface analytics
panes (`LIKE '%one_%'` would miss it) and was a perpetual editor
trap.

This migration is a two-step rename. Step 3 — dropping the old
'oneWire' value from the enum — is deliberately deferred:
PostgreSQL has no clean way to remove an enum value (you have to
recreate the type, rebuild every dependent column, and gate the
window during which writes might still hit the old value). We pay
the cost of the orphan-but-unreachable enum value to keep this
migration reversible and atomic. Step 3 lands when (a) we audit
that no row has used 'oneWire' for at least one full release, and
(b) we have a downtime window large enough for the type-recreate.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0022"
down_revision: Union[str, None] = "0021"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: add the new value to the enum type so future writes can
    # use it. PostgreSQL requires the ADD VALUE to be COMMITTED before
    # the new value can appear in another statement (otherwise:
    # ERROR: unsafe use of new value "one_wire" of enum type busprotocol).
    # `autocommit_block` runs the inner statements outside the
    # migration's wrapping transaction so the commit happens between
    # step 1 and step 2.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE busprotocol ADD VALUE IF NOT EXISTS 'one_wire'")

    # Step 2: rewrite existing rows from the old value to the new.
    op.execute(
        "UPDATE bus_definitions SET protocol = 'one_wire'::busprotocol "
        "WHERE protocol::text = 'oneWire'"
    )


def downgrade() -> None:
    # Reverse step 2; step 1 (the ADD VALUE) cannot be cleanly undone
    # without recreating the enum type, which is the same reason the
    # old value still lingers after the upgrade.
    op.execute(
        "UPDATE bus_definitions SET protocol = 'oneWire'::busprotocol "
        "WHERE protocol::text = 'one_wire'"
    )
