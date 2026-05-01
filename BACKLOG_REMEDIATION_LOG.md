# ASTRA Backlog Remediation Log
**Started:** 2026-05-01
**Source:** BACKLOG.md / AUDIT_FINDINGS_POST_REMEDIATION.md (baseline commit 00b562a)

## Progress

| Finding | Severity | Status | Files Touched | Commit | Verification | Notes |
|---|---|---|---|---|---|---|
| F-200 | High | ✅ Fixed | `backend/app/services/auth_manager.py`, `backend/tests/test_auth_manager_jti.py` | `cf6e952` | `pytest tests/test_auth_manager_jti.py` → 4 passed | jti stamped via `to_encode.setdefault(...)`; refresh-rotated tokens now also get jti |
| F-221 | Low | ✅ Fixed | `backend/app/services/auth.py` | `1c832fe` | Code review only (warning observable in logs) | Logger added to module; rollback preserved |
| F-208 | Medium | ✅ Fixed | `backend/app/routers/audit.py`, `backend/tests/test_phase2_membership_sweep.py` | `e24a3ea` | `pytest -k F208` → 2 passed | Mirror of /audit/export gate |
| F-210 | Medium | ✅ Fixed | `backend/app/routers/seed_project.py`, tests | `fa3b86d` | `pytest -k F210` → 1 passed | — |
| F-211 | Medium | ✅ Fixed | `backend/app/routers/imports.py`, tests | `2e58456` | `pytest -k F211` → 1 passed | Both preview and confirm gated |
| F-201 | High | ✅ Fixed | `backend/app/routers/workflows.py` (`fdb1553`), `backend/app/routers/ai.py` (`c37e095`), `backend/app/routers/ai_writer.py` + schema (`2de8daa`), tests (`e5accca`) | three commits | `pytest -k F201` → 9 passed | ai_writer added optional `project_id` to each schema; gate is no-op when absent (backward-compatible) |
| F-202 | High | ✅ Fixed | `backend/app/routers/dev.py`, `backend/tests/test_phase3_dev_router.py` | `ef6e990` | `pytest tests/test_phase3_dev_router.py` → 7 passed | ADMIN auth + X-Dev-Reset-Confirm header + dev.reset audit emitted |
| F-216 | Medium | ✅ Fixed | `backend/app/routers/dev.py` | `ef6e990` | covered by reset test | `_RESET_IN_PROGRESS` shim returns 503 during drop/create window (single-worker only) |
| F-203 | High | ✅ Fixed | `backend/app/routers/requirements.py`, `backend/app/routers/imports.py`, `backend/tests/test_requirement_id_race.py` | `2961e31` | `pytest tests/test_requirement_id_race.py` → 2 passed | Now uses next_human_id with FOR-UPDATE lock |
| F-204 | High | ✅ Fixed | `frontend/src/lib/interface-api.ts` | `59e3931` | `npx tsc --noEmit` → no errors in interface-api.ts | 6 functions renamed; positional callers unaffected |
| F-205 | High | ✅ Fixed | `backend/app/models/__init__.py`, `backend/alembic/versions/0026_requirement_baseline_cascade.py`, `backend/tests/test_project_cascade_delete.py` | `b363df6` | `alembic upgrade head` (0026 applied), `pytest tests/test_project_cascade_delete.py` → 1 passed | DB backup taken at `/tmp/pre-0026-1777669474.sql` inside astra-db-1 |
| F-206 | Medium | ✅ Fixed | `backend/app/services/auth.py` | `1c6a616` | full suite green | Catches only ImportError + ProgrammingError + OperationalError; warns on swallow |
| F-207 | Medium | ✅ Fixed | `frontend/src/lib/auth.tsx` | `5d37f01` | `npx tsc --noEmit` clean | Adds interfaces.* + reports.export; SYNC NOTE comment |
| F-209 | Medium | ✅ Fixed | `backend/app/routers/integrations.py` | `f283873` | full suite green | Field renamed `webhook_url` → `webhook_url_template`; FE doesn't reference it |
| F-212 | Medium | ✅ Fixed | `backend/app/services/signature_service.py` | `698bd30` | full suite green | Single OUTER JOIN replaces per-row User lookup |
| F-213 | Medium | ✅ Fixed | `backend/app/routers/baselines.py` | `48fd9a0` | full suite green | Dead stub deleted; replaced with explanatory comment |
| F-214 | Medium | ✅ Fixed | `backend/app/routers/audit.py` | `4f8893b` | full suite green | Resolves entity → project → `_check_membership` |
| F-215 | Medium | ✅ Fixed | `backend/app/routers/audit.py` | `4f8893b` | full suite green | Both endpoints now `le=200` |
| F-217 | Low | ✅ Fixed | 4 `.bak` files removed | `1b498a1` | `git status` clean of `.bak` | `.gitignore` already had `*.bak` |
| F-218 | Low | ✅ Fixed | `frontend/src/lib/api.ts` | `ef7af1c` | TS clean | One UI caller exists in `[id]/page.tsx:417` — path now hits `/admin/seed-project/...` |
| F-219 | Low | ✅ Fixed | `.env.example` | `6949a2e` | n/a (config) | **ACTION FOR MASON:** update live `.env` on dev machine — change `PGADMIN_DEFAULT_EMAIL` from `admin@astra.local` → `admin@example.com` |
| F-220 | Low | ✅ Fixed | `backend/app/services/auth_providers/saml.py` | `d21dc79` | full suite green | OIDC + PIV providers verified to already default safely |
| F-222 | Info | — | — | — | — | No-action / architectural framing |

## Phase Status

- [x] Phase 1 — Auth / Token Hardening (F-200, F-221) — full suite: 295 passed, 0 failed (`pytest tests/ -x -q -m 'not performance'`, 178s). Backend route count: 332. `alembic check` reports pre-existing schema drift (per operating rule §3 — known and tolerated on this baseline; no migration introduced this phase).
- [x] Phase 2 — Project Membership Sweep (F-201, F-208, F-210, F-211) — full suite: 309 passed, 0 failed (was 295 before; +14 negative tests). 7 commits on `fix/backlog-phase-2-membership`.
- [x] Phase 3 — Dev Router Hardening (F-202, F-216) — full suite: 316 passed (+7).
- [x] Phase 4 — Data Integrity & Contract (F-203, F-204, F-205) — full suite: 319 passed (+3). Migration 0026 applied; db backup at `astra-db-1:/tmp/pre-0026-1777669474.sql`.
- [x] Phase 5 — Medium Severity (F-206–F-215) — full suite: 319 passed, 0 failed (no new tests; existing coverage protects the touched paths).
- [x] Phase 6 — Low Severity & Cleanup (F-217–F-220) — full suite: 319 passed; FE typecheck clean for touched files.
- [x] Final verification gate
  - `pytest tests/ -q -m 'not performance'` → **319 passed, 0 failed** (was 295 at baseline; +24 net new tests across phases 1–4).
  - Backend route count: 249.
  - `alembic current` → `0026 (head)`. Migration 0026 applied cleanly.
  - `alembic check` → reports the pre-existing baseline schema drift (account_lockouts / ai_suggestions / workflow_stages defaults + indexes). This drift was already present at baseline commit `00b562a` and is tolerated per operating rule §3 ("the codebase has known schema drift; never run `alembic revision --autogenerate`"). No drift was introduced by this remediation cycle.
  - Frontend `npx tsc --noEmit` → no errors in any file touched by this remediation (`interface-api.ts`, `auth.tsx`, `api.ts`). Pre-existing TS errors in `__tests__/`, `src/tests/`, and a handful of unrelated `interfaces/*` pages are out of scope.
  - `git status` → no untracked `.bak` files; only the un-tracked input prompt remains (intentional).

## New findings discovered during remediation

| Date | Description | Severity | Action |
|---|---|---|---|
| — | — | — | — |
