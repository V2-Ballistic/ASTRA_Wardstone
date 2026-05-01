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
| F-203 | High | ⏳ Pending | — | — | — | Phase 4 |
| F-204 | High | ⏳ Pending | — | — | — | Phase 4 |
| F-205 | High | ⏳ Pending | — | — | — | Phase 4 |
| F-206 | Medium | ⏳ Pending | — | — | — | Phase 5 |
| F-207 | Medium | ⏳ Pending | — | — | — | Phase 5 |
| F-209 | Medium | ⏳ Pending | — | — | — | Phase 5 |
| F-212 | Medium | ⏳ Pending | — | — | — | Phase 5 |
| F-213 | Medium | ⏳ Pending | — | — | — | Phase 5 |
| F-214 | Medium | ⏳ Pending | — | — | — | Phase 5 |
| F-215 | Medium | ⏳ Pending | — | — | — | Phase 5 |
| F-217 | Low | ⏳ Pending | — | — | — | Phase 6 |
| F-218 | Low | ⏳ Pending | — | — | — | Phase 6 |
| F-219 | Low | ⏳ Pending | — | — | — | Phase 6 |
| F-220 | Low | ⏳ Pending | — | — | — | Phase 6 |
| F-222 | Info | — | — | — | — | No-action / architectural framing |

## Phase Status

- [x] Phase 1 — Auth / Token Hardening (F-200, F-221) — full suite: 295 passed, 0 failed (`pytest tests/ -x -q -m 'not performance'`, 178s). Backend route count: 332. `alembic check` reports pre-existing schema drift (per operating rule §3 — known and tolerated on this baseline; no migration introduced this phase).
- [x] Phase 2 — Project Membership Sweep (F-201, F-208, F-210, F-211) — full suite: 309 passed, 0 failed (was 295 before; +14 negative tests). 7 commits on `fix/backlog-phase-2-membership`.
- [x] Phase 3 — Dev Router Hardening (F-202, F-216) — full suite: 316 passed (+7).
- [ ] Phase 4 — Data Integrity & Contract (F-203, F-204, F-205)
- [ ] Phase 5 — Medium Severity (F-206–F-215)
- [ ] Phase 6 — Low Severity & Cleanup (F-217–F-220)
- [ ] Final verification gate

## New findings discovered during remediation

| Date | Description | Severity | Action |
|---|---|---|---|
| — | — | — | — |
