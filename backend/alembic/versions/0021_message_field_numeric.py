"""F-077: MessageField scale/offset/range columns Float -> Numeric(20, 9).

Revision ID: 0021
Revises: 0020
Create Date: 2026-04-30

The seven engineering-unit math columns on `message_fields`
(scale_factor, offset_value, lsb_value, min_value, max_value,
resolution, accuracy) were stored as DOUBLE PRECISION (Postgres Float).
Float couldn't represent ICD-typical decimal constants exactly —
inserting `0.1` and reading it back returned `0.10000000149011612`,
which broke unit-conversion equality checks downstream.

NUMERIC(20, 9) preserves the source decimal exactly for any realistic
ICD value (12 integer digits + 9 decimals = ~10^12 range with 1 ppb
precision).

The cast `Float -> Numeric` is non-lossy for the values that fit; rows
that don't fit (extremely large powers of two like 2^65) would raise.
We accept the migration may surface such a row in `astra_dev` if one
exists; production should not have any.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0021"
down_revision: Union[str, None] = "0020"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMNS = (
    "scale_factor",
    "offset_value",
    "lsb_value",
    "min_value",
    "max_value",
    "resolution",
    "accuracy",
)


def upgrade() -> None:
    for col in _COLUMNS:
        op.alter_column(
            "message_fields",
            col,
            existing_type=sa.Float(),
            type_=sa.Numeric(20, 9),
            existing_nullable=True,
            postgresql_using=f"{col}::numeric(20, 9)",
        )


def downgrade() -> None:
    for col in _COLUMNS:
        op.alter_column(
            "message_fields",
            col,
            existing_type=sa.Numeric(20, 9),
            type_=sa.Float(),
            existing_nullable=True,
            postgresql_using=f"{col}::double precision",
        )
