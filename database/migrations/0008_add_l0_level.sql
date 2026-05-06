-- ══════════════════════════════════════════════════════════════
--  ASTRA — Migration 0008 — Add L0 Customer/Contractual Level
--  File: database/migrations/0008_add_l0_level.sql
--
--  Adds 'L0' value to the requirementlevel PostgreSQL enum,
--  inserted BEFORE 'L1' to preserve sort ordering.
--
--  Also adds the source_artifact_id column on requirements so L0
--  rows can carry a hard FK to their originating MRD/SOW/contract
--  document. Nullable so L1–L5 remain unaffected.
--
--  Idempotent: safe to re-run.
-- ══════════════════════════════════════════════════════════════

-- Postgres 12+ allows ALTER TYPE ... ADD VALUE outside transactions.
-- Use IF NOT EXISTS for idempotency.

ALTER TYPE requirementlevel ADD VALUE IF NOT EXISTS 'L0' BEFORE 'L1';

-- Add source_artifact_id column (nullable; ON DELETE SET NULL so a
-- removed artifact does not cascade-delete the requirement).
ALTER TABLE requirements
    ADD COLUMN IF NOT EXISTS source_artifact_id INTEGER
        REFERENCES source_artifacts(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS ix_requirements_source_artifact_id
    ON requirements(source_artifact_id);

-- Verification queries (run manually after migration):
-- SELECT unnest(enum_range(NULL::requirementlevel)) AS level;
-- Expected output: L0, L1, L2, L3, L4, L5
--
-- \d requirements
-- Expected: source_artifact_id column present, FK to source_artifacts.
