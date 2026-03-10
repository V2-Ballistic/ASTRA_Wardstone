-- ══════════════════════════════════════════════════════
--  ASTRA — Database Initialization
--  This runs automatically when the PostgreSQL container
--  starts for the first time.
-- ══════════════════════════════════════════════════════

-- Enable useful extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";  -- For fuzzy text search

-- Note: Tables are created by SQLAlchemy / Alembic.
-- This file is for extensions and optional seed data only.

-- Seed data will be inserted via the /api/v1/auth/register endpoint
-- or via Alembic seed migrations.
