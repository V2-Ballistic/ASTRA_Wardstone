# ASTRA Backlog Remediation Log
**Started:** 2026-05-01
**Source:** BACKLOG.md / AUDIT_FINDINGS_POST_REMEDIATION.md (baseline commit 00b562a)

## Progress

| Finding | Severity | Status | Files Touched | Commit | Verification | Notes |
|---|---|---|---|---|---|---|
| F-200 | High | ✅ Fixed | `backend/app/services/auth_manager.py`, `backend/tests/test_auth_manager_jti.py` | `cf6e952` | `pytest tests/test_auth_manager_jti.py` → 4 passed | jti stamped via `to_encode.setdefault(...)`; refresh-rotated tokens now also get jti |
| F-221 | Low | ✅ Fixed | `backend/app/services/auth.py` | `1c832fe` | Code review only (warning observable in logs) | Logger added to module; rollback preserved |
| F-208 | Medium | ⏳ Pending | — | — | — | Phase 2 |
| F-210 | Medium | ⏳ Pending | — | — | — | Phase 2 |
| F-211 | Medium | ⏳ Pending | — | — | — | Phase 2 |
| F-201 | High | ⏳ Pending | — | — | — | Phase 2 |
| F-202 | High | ⏳ Pending | — | — | — | Phase 3 |
| F-216 | Medium | ⏳ Pending | — | — | — | Phase 3 |
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
- [ ] Phase 2 — Project Membership Sweep (F-201, F-208, F-210, F-211)
- [ ] Phase 3 — Dev Router Hardening (F-202, F-216)
- [ ] Phase 4 — Data Integrity & Contract (F-203, F-204, F-205)
- [ ] Phase 5 — Medium Severity (F-206–F-215)
- [ ] Phase 6 — Low Severity & Cleanup (F-217–F-220)
- [ ] Final verification gate

## New findings discovered during remediation

| Date | Description | Severity | Action |
|---|---|---|---|
| — | — | — | — |
