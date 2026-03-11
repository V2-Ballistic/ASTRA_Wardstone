#!/usr/bin/env bash
# ══════════════════════════════════════════════════════
#  ASTRA — Create New Migration (Autogenerate)
#  File: backend/scripts/create_migration.sh   ← NEW
#
#  Compares the current SQLAlchemy models against the database
#  and generates a migration file with the diff.
#
#  Usage:
#    ./scripts/create_migration.sh "add_priority_column"
#    ./scripts/create_migration.sh "rename_status_field"
#
#  Always review the generated file before running it!
# ══════════════════════════════════════════════════════

set -euo pipefail
cd "$(dirname "$0")/.."

if [ -z "${1:-}" ]; then
    echo "Usage: $0 <migration_description>"
    echo "Example: $0 \"add_priority_column_to_baselines\""
    exit 1
fi

MESSAGE="$1"

echo "╔══════════════════════════════════════════╗"
echo "║  ASTRA — Autogenerate Migration          ║"
echo "╚══════════════════════════════════════════╝"
echo ""
echo "Description: ${MESSAGE}"
echo ""

alembic revision --autogenerate -m "${MESSAGE}"

echo ""
echo "✓ Migration file created in alembic/versions/"
echo ""
echo "IMPORTANT: Review the generated file before running:"
echo "  1. Open the new file in alembic/versions/"
echo "  2. Verify the upgrade() and downgrade() are correct"
echo "  3. Run:  alembic upgrade head"
