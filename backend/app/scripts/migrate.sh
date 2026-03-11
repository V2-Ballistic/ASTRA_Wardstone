#!/usr/bin/env bash
# ══════════════════════════════════════════════════════
#  ASTRA — Run Pending Database Migrations
#  File: backend/scripts/migrate.sh   ← NEW
#
#  Usage:
#    ./scripts/migrate.sh              # upgrade to head
#    ./scripts/migrate.sh +1           # upgrade one revision
#    ./scripts/migrate.sh 0002         # upgrade to specific revision
# ══════════════════════════════════════════════════════

set -euo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:-head}"

echo "╔══════════════════════════════════════════╗"
echo "║  ASTRA — Database Migration              ║"
echo "╚══════════════════════════════════════════╝"
echo ""

# Show current state
echo "Current revision:"
alembic current 2>/dev/null || echo "  (no revision stamp found)"
echo ""

# Show pending
echo "Pending migrations:"
alembic history --indicate-current 2>/dev/null | head -20
echo ""

# Apply
echo "Upgrading to: ${TARGET}"
alembic upgrade "${TARGET}"

echo ""
echo "✓ Migration complete. New revision:"
alembic current
