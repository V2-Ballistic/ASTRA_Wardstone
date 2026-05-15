"""CADPORT-REBUILD-003: assembly rollup inertia columns

Revision ID: 0037
Revises: 0036
Create Date: 2026-05-15

The assembly detail UI needs the rollup moment-of-inertia tensor
alongside the CG that 0036 already stores. The §6 assembly YAML
carries rollup.inertia_tensor_kg_m2; rather than parse the blob on
every request, store the six components as queryable columns on
cadport_assemblies (same shape/pattern as the catalog_parts
physics columns from 0036).

Additive, ADD COLUMN IF NOT EXISTS, safe on the populated DB,
re-runnable. No autogenerate.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0037"
down_revision: Union[str, None] = "0036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_COLS = ["ixx", "iyy", "izz", "ixy", "ixz", "iyz"]


def upgrade() -> None:
    for c in _COLS:
        op.execute(
            f"ALTER TABLE cadport_assemblies "
            f"ADD COLUMN IF NOT EXISTS {c} DOUBLE PRECISION"
        )


def downgrade() -> None:
    for c in _COLS:
        op.execute(f"ALTER TABLE cadport_assemblies DROP COLUMN IF EXISTS {c}")
