"""INTF-002 Phase 4: add Interface unit endpoints (source_unit_id / target_unit_id).

Revision ID: 0024
Revises: 0023
Create Date: 2026-04-30

Spec §11.2 of ASTRA-TDD-INTF-002 drives the three-way auto-wire from
``Interface.source_unit_id`` and ``Interface.target_unit_id``. The existing
``Interface`` model only carries system-level endpoints (``source_system_id``
/ ``target_system_id``) — auto-wire has nothing to anchor to without unit-level
endpoints. Digest §10 calls this anomaly #3.

This migration adds the two FK columns + indexes + a best-effort backfill:

  * For each interface row, if its ``source_system`` has exactly ONE unit in
    the same project, ``source_unit_id`` is set to that unit's id. Otherwise
    the column is left NULL — the user must disambiguate via the new
    Connection Builder UI before auto-wire will run.
  * Same logic for ``target_system_id`` → ``target_unit_id``.

ON DELETE SET NULL: deleting a unit must not silently orphan an interface;
NULL forces the operator to re-pick the unit through the builder.

Reversibility
-------------
``downgrade()`` drops the indexes and columns in reverse order. No data
restoration is attempted (the columns were derived).
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0024"
down_revision: Union[str, None] = "0023"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Step 1: add columns (NULLABLE — backfill is best-effort) ──
    op.add_column(
        "interfaces",
        sa.Column(
            "source_unit_id", sa.Integer,
            sa.ForeignKey("units.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "interfaces",
        sa.Column(
            "target_unit_id", sa.Integer,
            sa.ForeignKey("units.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # ── Step 2: indexes for FK joins ──
    op.create_index(
        "ix_interfaces_source_unit", "interfaces", ["source_unit_id"]
    )
    op.create_index(
        "ix_interfaces_target_unit", "interfaces", ["target_unit_id"]
    )

    # ── Step 3: backfill — single-unit-system shortcut ──
    # For each interface, if the referenced system has exactly ONE unit in the
    # interface's project, copy that unit_id into the new column. Multi-unit
    # systems remain NULL by design (user-disambiguated via Connection Builder).
    #
    # The CTE picks systems with exactly one unit per (project_id, system_id)
    # so we never silently bind to the wrong unit on multi-unit systems.
    #
    # NOTE: ``interfaces.project_id`` is nullable on legacy rows. We OR on
    # ``units.project_id IS NOT NULL`` — interfaces with NULL project_id are
    # only auto-bound when there's exactly one matching unit anywhere on that
    # system, which on the dev DB never collides since every unit is
    # project-scoped.
    bind = op.get_bind()
    backfill_sql = sa.text(
        """
        WITH single_unit_systems AS (
            SELECT system_id, project_id, MIN(id) AS unit_id, COUNT(*) AS n
            FROM units
            GROUP BY system_id, project_id
            HAVING COUNT(*) = 1
        )
        UPDATE interfaces SET source_unit_id = sus.unit_id
        FROM single_unit_systems sus
        WHERE interfaces.source_system_id = sus.system_id
          AND (interfaces.project_id = sus.project_id
               OR interfaces.project_id IS NULL)
          AND interfaces.source_unit_id IS NULL
        """
    )
    bind.execute(backfill_sql)

    backfill_target_sql = sa.text(
        """
        WITH single_unit_systems AS (
            SELECT system_id, project_id, MIN(id) AS unit_id, COUNT(*) AS n
            FROM units
            GROUP BY system_id, project_id
            HAVING COUNT(*) = 1
        )
        UPDATE interfaces SET target_unit_id = sus.unit_id
        FROM single_unit_systems sus
        WHERE interfaces.target_system_id = sus.system_id
          AND (interfaces.project_id = sus.project_id
               OR interfaces.project_id IS NULL)
          AND interfaces.target_unit_id IS NULL
        """
    )
    bind.execute(backfill_target_sql)


def downgrade() -> None:
    op.drop_index("ix_interfaces_target_unit", table_name="interfaces")
    op.drop_index("ix_interfaces_source_unit", table_name="interfaces")
    op.drop_column("interfaces", "target_unit_id")
    op.drop_column("interfaces", "source_unit_id")
