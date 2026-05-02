#!/bin/bash
# Quick HTTP-level sweep of every frontend route. Catches SSR runtime
# errors (which surface as 500), missing pages (404), and the
# use(params) class of bugs (which crash on render).
#
# Pages that are gated by AuthGate still SSR successfully (the redirect
# is client-side). So 200 here means the route resolves AND renders
# without crashing.

ROUTES=(
  "/"
  "/login"
  "/traceability"
  "/catalog"
  "/catalog/parts/new"
  "/catalog/suppliers/new"
  "/parts-library"
  "/parts-library/pending-imports"
  "/projects/new"
  "/projects/1"
  "/projects/1/ai"
  "/projects/1/audit"
  "/projects/1/baselines"
  "/projects/1/coverage"
  "/projects/1/impact"
  "/projects/1/import"
  "/projects/1/interfaces"
  "/projects/1/interfaces/auto-requirements"
  "/projects/1/interfaces/connect"
  "/projects/1/interfaces/import"
  "/projects/1/mechanical-interfaces"
  "/projects/1/parts"
  "/projects/1/reports"
  "/projects/1/req-sync"
  "/projects/1/requirements"
  "/projects/1/requirements/new"
  "/projects/1/settings"
  "/projects/1/system-architecture"
  "/projects/1/traceability"
  "/projects/1/verification"
)

BASE="${BASE:-http://localhost:3000}"
PASS=0
FAIL=0
FAILED_ROUTES=()

for route in "${ROUTES[@]}"; do
  url="${BASE}${route}"
  status=$(curl -s -o /tmp/route_body -w "%{http_code}" "$url")
  if [[ "$status" == "200" ]]; then
    if grep -q "__NEXT_DATA__\|<html" /tmp/route_body 2>/dev/null; then
      printf "  PASS   %3s   %s\n" "$status" "$route"
      PASS=$((PASS + 1))
    else
      printf "  FAIL   %3s   %s   (no HTML)\n" "$status" "$route"
      FAIL=$((FAIL + 1))
      FAILED_ROUTES+=("$route")
    fi
  else
    printf "  FAIL   %3s   %s\n" "$status" "$route"
    FAIL=$((FAIL + 1))
    FAILED_ROUTES+=("$route ($status)")
  fi
done

echo ""
echo "Summary: ${PASS} passed, ${FAIL} failed"
if (( FAIL > 0 )); then
  echo "Failed:"
  printf '  - %s\n' "${FAILED_ROUTES[@]}"
fi
