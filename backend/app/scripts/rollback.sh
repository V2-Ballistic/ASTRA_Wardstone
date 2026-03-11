#!/usr/bin/env bash
# ══════════════════════════════════════════════════════
#  ASTRA — Rollback Database Migration
#  File: backend/scripts/rollback.sh   ← NEW
#
#  Usage:
#    ./scripts/rollback.sh             # rollback one step
#    ./scripts/rollback.sh -2          # rollback two steps
#    ./scripts/rollback.sh 0001        # downgrade to specific revision
# ══════════════════════════════════════════════════════

set -euo pipefail
cd "$(dirname "$0")/.."

TARGET="${1:--1}"

echo "╔══════════════════════════════════════════╗"
echo "║  ASTRA — Database Rollback               ║"
echo "╚══════════════════════════════════════════╝"
echo ""

echo "Current revision:"
alembic current
echo ""

echo "⚠  Rolling back to: ${TARGET}"
read -r -p "Are you sure? (y/N) " confirm
if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
    echo "Aborted."
    exit 0
fi

alembic downgrade "${TARGET}"

echo ""
echo "✓ Rollback complete. New revision:"
alembic current
