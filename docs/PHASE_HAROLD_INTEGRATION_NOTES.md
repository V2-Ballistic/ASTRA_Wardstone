# ASTRA ↔ HAROLD V2 Integration — Completion Notes

Phase scope: TDD-HAROLD-INTEGRATION-002.
Branch: `fix/frontend-healthcheck-ipv4`.
Date completed: 2026-05-12.

This is the post-mortem record of wiring ASTRA's catalog flow into
HAROLD V2's native REST API (port 8031, `/api/v1/*`) — superseding
the earlier speculative HAROLD-001 attempt that targeted a WRENCH
plugin shape that V2 doesn't use.

---

## 1. Per-phase commits

| Phase | Commit  | Subject |
|-------|---------|---------|
| 0     | `c6e3858` | reconciliation report + V2 API capture |
| 1     | `3a0a071` | WPN columns + fallback sequences migration (0033) |
| 2     | `9e5d489` | HAROLD V2 client + service + fallback + filename validator |
| 3     | `24c72a0` | `/api/v1/harold/*` router + designators fix + upload-approval wiring |
| 4     | `e416305` | frontend WPN section + catalog list + reconcile UI |
| fix   | `7399a74` | catch-up: HAROLD env-var declarations in docker-compose |
| 5     | `a980f9c` | end-to-end smoke validated (state-only) |
| 6     | _this commit_ | tests + completion notes |

The `fix(harold-int)` commit between Phase 4 and Phase 5 covered three
env-var passthroughs in `docker-compose.yml`
(`HAROLD_INTEGRATION_ENABLED`, `HAROLD_BASE_URL`,
`HAROLD_TIMEOUT_SECONDS`) that had been live in Mason's working tree
through Phases 1-4 but never staged. Caught during the Phase 5
pre-commit audit.

---

## 2. Reconciliation strategy (chosen in Phase 0)

The Phase 0 design report (`docs/HAROLD_INTEGRATION_DESIGN.md`) settled
on **Path A — delete and rebuild fresh against V2**. The prior
HAROLD-001 code (~660 lines across 7 files) spoke WRENCH's
`/api/tools/{slug}/runs` envelope, not V2's native REST. Salvage value
was low and rewrite cost was small, so:

* `git rm` of the speculative `backend/app/services/harold/`,
  `routers/harold.py`, the V1 `schemas/harold.py`, plus the frontend's
  `harold-api.ts` / `harold-types.ts`.
* Only the discriminated-union response pattern and the
  `HaroldUnavailableError` / `HaroldDuplicateError` exception classes
  survived; everything else was rebuilt against the OpenAPI capture in
  `docs/HAROLD_V2_OPENAPI.json`.
* Migration 0032 (`systems.system_code_2letter`, pre-integration)
  stayed in place — useful future context for system-level WPN scope.

The runtime reconciliation policy (Phase 3 service + Phase 4 UI):

1. **Upload time** (HAROLD up) — `suggest` is called with
   `part_class → system_code` via the AD-6 lookup table. Result lands
   in `extracted_data` as `proposed_wpn` (UI hint only, never an
   implicit commitment per AD-11).
2. **Upload time** (HAROLD down) — the same suggest call falls back
   to the local allocator (`catalog_wpn_fallback_sequences` table,
   `SELECT FOR UPDATE` per dialect, no-op on SQLite). Result is tagged
   `source: fallback` so the UI can render the amber chip.
3. **Approve time** (AD-11 strict three-branch):
   * `extracted_data.user_supplied_wpn` set → `issue_specific`. 409
     surfaces a clean 422 to the user; 5xx propagates as
     `HaroldUnavailableError`.
   * Else, HAROLD reachable → `issue` (fresh allocation, authoritative).
   * Else → fallback allocator + `wpn_pending_sync = True`.
4. **Manual reconcile** (`POST /api/v1/harold/parts/{id}/reconcile`):
   first try `issue_specific` with the fallback-allocated WPN; on 409
   (HAROLD already issued that number to someone else), allocate a
   fresh HAROLD WPN, update `internal_part_number` in place, and emit
   `wpn_changed_during_reconcile`. On success, `wpn_pending_sync`
   flips to False and the audit emits `catalog.part.wpn_reconciled`.

The whole reconcile step is wrapped in a transaction — partial
failure (HAROLD accepts but audit emit fails) rolls back so state stays
consistent. There is no automatic reconciliation worker; manual button
is sufficient for v1.

`HAROLD_INTEGRATION_ENABLED=false` is byte-identical to pre-integration
ASTRA. The flag-gated import in `backend/app/routers/catalog.py` skips
the entire `_harold_suggest` / `_harold_validate_filename` / issue path.

---

## 3. End-to-end smoke results (Phase 5)

Live run against HAROLD V2 at `host.docker.internal:8031` with the
flag flipped on. All 13 steps green:

```
 1. backend → V2 /health                                   200 / healthy
 2. /api/v1/harold/heartbeat                               enabled+reachable
 3. STEP upload → green "Suggested by HAROLD" chip         WS-FH-P000001-A
 4. Approve → catalog part with internal_part_number set   wpn_pending_sync=false
 5. V2 ledger shows origin_system=astra/origin_record_id   verified
 6. Catalog list promotes the WPN as primary identifier    no amber dot
 7. Second STEP allocates the next sequence number         WS-FH-P000002-A
 8. Renamed-collision STEP fall-through to fresh issue     reissued cleanly
 9. Stop HAROLD                                            harold-backend down
10. STEP upload → amber fallback chip + sync-pending dot   fallback allocator hit
11. Restart HAROLD                                         back up
12. Sync with HAROLD button → reconcile + flag cleared     verified
13. LAN access from 192.168.1.74:3000                      full flow works
```

## 4. Final test pass (Phase 6)

```
docker compose exec backend python -m pytest tests/ -q   →  788 passed, 1 skipped
docker compose exec frontend npx tsc --noEmit            →  exit 0
docker compose exec frontend npm run build               →  exit 0, 12/12 static pages
```

The single skipped test is the pre-existing F-127 skip; not
HAROLD-related. Backend pytest baseline was 788/1 at Phase 3 — Phase 4
was frontend-only and Phase 5/6 added no new backend tests, so the
count is unchanged.

> Note: `respx==0.22.0` was missing from the running backend image at
> Phase 6 even though it's pinned in `backend/requirements-dev.txt`.
> Installed it explicitly to unblock the test run. Worth a rebuild of
> the dev image at some point to bake it back in.

---

## 5. Open follow-ups (deferred — out of scope this round)

1. **Extend filename validation to PDF datasheets.** Same
   `validate_filename` seam, different upload route. A bulk-rename
   helper for legacy doc folders would lean on the same primitive.
2. **Webhook from HAROLD to ASTRA on ledger changes.** Today ASTRA
   pulls (heartbeat + manual reconcile). Push would close the gap on
   cross-system drift — e.g. someone editing HAROLD's ledger directly
   would silently invalidate `internal_part_number` until next sync.
3. **Authenticated `/catalog/designators`.** Currently open. Future
   TDD adds a shared-token header so non-LAN deployments can call it
   from outside the trust boundary.
4. **Reconciliation worker.** Manual "Sync with HAROLD" button is the
   only path today. An automatic worker could sweep
   `wpn_pending_sync=True` rows when HAROLD's heartbeat returns to
   `reachable=True`, without operator action.
5. **Bulk upload of pre-named files.** When a folder of `WS-FH-P*.STEP`
   files is dropped, recognise each WPN, validate against HAROLD, and
   only create new ledger entries for unknowns. Plays well with the
   existing filename validator.
6. **WPN format display preferences.** Some operators may prefer the
   system code expanded (`WS-Fastener Hardware-P000042-A`) rather than
   the two-letter prefix. Add as a setting if requested.

The McMaster part already in `catalog_parts` (id=1, MPN `92196A196`)
was intentionally not backfilled with a WPN — per gotcha #9 from the
spec, retroactive assignment is Mason's call via a future cleanup
script, not silent migration.

---

## 6. Sign-off

- Branch `fix/frontend-healthcheck-ipv4` ahead of `origin` by 14
  commits (8 from HAROLD-V2-001, 7 from HAROLD-INTEGRATION-002, plus
  the catch-up fix).
- Feature flag is **ON** in `.env` for the smoke environment. Flip to
  `false` and `docker compose up -d backend` (NOT `restart`) to return
  to pre-integration behaviour.
- HAROLD V2's stack is independent and runs out of `C:\Tools\harold`;
  no changes were made there.
