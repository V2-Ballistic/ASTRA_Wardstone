"""CADPORT-TDD-STEP-001: catalog_parts STEP / mass-source provenance

Revision ID: 0040
Revises: 0039
Create Date: 2026-06-02

The CADPORT plugin can now ingest STEP files in addition to the
SolidWorks COM bridge path. Both paths land in the same ``catalog_parts``
table, but they differ in *how* mass was determined for the row, and
STEP-imported rows must be re-mass-editable from ASTRA (PATCH
/api/v1/catalog/parts/{id}/mass) while SolidWorks-imported rows must
not (their mass is owned upstream by SW).

This migration adds three text columns and one boolean — all additive,
default-backfilled so the SolidWorks rows in production read as the
historical "carries SW-side mass" shape:

  source_format VARCHAR(16) NOT NULL DEFAULT 'sldprt'
    -- 'sldprt' | 'step'

  step_material_key VARCHAR(64) NULL
    -- When mass_source = 'material', the materials.json key the
    -- density came from. NULL otherwise.

  mass_source VARCHAR(16) NOT NULL DEFAULT 'cad'
    -- 'cad'            : SW-bridge-derived mass (or geometric-only STEP
    --                    that has no mass yet); the historical behaviour
    -- 'material'       : computed at upload from a CADPORT material
    --                    pick (STEP path)
    -- 'user_override'  : explicit number from CADPORT upload OR from
    --                    the ASTRA Edit-mass affordance

  inertia_revised_via_uniform_scaling BOOLEAN NOT NULL DEFAULT FALSE
    -- True iff this row's inertia tensor was produced by linear
    -- mass-scaling (CADPORT-TDD-STEP-001 §7.1.4) rather than being
    -- re-derived from geometry. Per the standing-rule addition Mason
    -- called for, downstream consumers want this on the row so
    -- round-trips preserve the fact.

Also extends ``cadport_assemblies`` with the same boolean — assembly
rollups inherit "involved a scaling step somewhere" from any constituent
part or from a triggering edit.

CHECK constraints on the enums are deliberately omitted: ALTER TYPE-style
CHECK migrations are painful and the application-layer Pydantic schema
already enforces the value space.

Hand-written per Mason's standing rule (no autogenerate). Mirrors the
additive ALTER TABLE IF NOT EXISTS / CREATE INDEX IF NOT EXISTS pattern
from 0036_cadport_integration.py so a partially-applied or already-
present state is safe.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "0040"
down_revision: Union[str, None] = "0039"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── catalog_parts ──────────────────────────────────────────────────
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS source_format VARCHAR(16) "
        "NOT NULL DEFAULT 'sldprt'"
    )
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS step_material_key VARCHAR(64)"
    )
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS mass_source VARCHAR(16) "
        "NOT NULL DEFAULT 'cad'"
    )
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS inertia_revised_via_uniform_scaling "
        "BOOLEAN NOT NULL DEFAULT FALSE"
    )

    # ── cadport_assemblies ─────────────────────────────────────────────
    op.execute(
        "ALTER TABLE cadport_assemblies "
        "ADD COLUMN IF NOT EXISTS inertia_revised_via_uniform_scaling "
        "BOOLEAN NOT NULL DEFAULT FALSE"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE cadport_assemblies "
        "DROP COLUMN IF EXISTS inertia_revised_via_uniform_scaling"
    )
    op.execute(
        "ALTER TABLE catalog_parts "
        "DROP COLUMN IF EXISTS inertia_revised_via_uniform_scaling"
    )
    op.execute("ALTER TABLE catalog_parts DROP COLUMN IF EXISTS mass_source")
    op.execute("ALTER TABLE catalog_parts DROP COLUMN IF EXISTS step_material_key")
    op.execute("ALTER TABLE catalog_parts DROP COLUMN IF EXISTS source_format")
