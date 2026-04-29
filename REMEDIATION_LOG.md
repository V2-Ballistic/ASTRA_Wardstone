# ASTRA Remediation Log
**Started:** 2026-04-29
**Source audit:** `AUDIT_FINDINGS.md` (commit `2b1e8f71`)
**Branch strategy:** One branch per phase: `fix/phase-1-critical`, `fix/phase-2-security`, `fix/phase-3-medium`, `fix/phase-4-cleanup`.

## Progress

| Finding | Severity | Status | Files Touched | Commit | Verification | Notes |
|---|---|---|---|---|---|---|
| §2.1–2.4 cross-cutting | — | ✅ Built | `backend/app/dependencies/{__init__,project_access}.py`, `backend/app/middleware/body_size_limit.py`, `backend/app/services/quality/{__init__,nasa_terms}.py`, `backend/app/services/security/{__init__,record_hash}.py` | `09510cd` | `python -m ast` parse OK | New modules — used by Phase 1+ findings. Body-size middleware not yet registered (Phase 2 §4.9). |
| F-002 | Critical | ✅ Fixed | `backend/app/routers/workflow.py` → `backend/app/models/workflow.py` (moved); `backend/app/models/workflows.py` → `backend/app/routers/workflows.py` (moved); `backend/app/main.py` (logger.warning replaces silent excepts — also covers F-121); `backend/app/models/__init__.py` (re-export workflow models — also covers F-138) | `d495747` | `python -m ast` parse OK on all 4 touched files; runtime verification needs `docker exec astra-backend-1 python -c "from app.routers.workflows import router; print(len(router.routes))"` | `services/signature_service.py:18`, `services/workflow_engine.py:22`, and `routers/workflows.py:37` all import `from app.models.workflow import …` — that path NOW exists. No code change needed in those three files. F-138 + F-121 collapsed into the same commit per the plan. |
| F-001 | Critical | ✅ Fixed | `backend/app/services/auth_manager.py:54`; `backend/tests/test_auth_manager_jwt.py` (new regression test — both standard and MFA-partial paths) | `0cb1b96` | `python -m ast` parse OK; `pytest backend/tests/test_auth_manager_jwt.py` requires Docker container | One-line change: `settings.SECRET_KEY` → `settings.SECRET_KEY.get_secret_value()`. |
| F-003 + F-067 | Critical+High | ✅ Fixed | `backend/app/services/encryption.py` (full rewrite — drop literal fallback, expose `derive_key`, salt configurable via `ENCRYPTION_KEY_SALT`, `decrypt_field` re-raises by default with `ALLOW_PLAINTEXT_LEGACY=true` opt-in); `backend/app/services/mfa.py` (use `derive_key` with separate salt `b"astra-mfa-v1"`, drop byte-truncate-and-pad); `backend/app/config.py` (`enforce_production_guards` checks ENCRYPTION_KEY too, refuses empty / known-weak / <32-char in prod) | `38d6382` | `python -m ast` parse OK; runtime needs `pytest backend/tests` after Phase 2 unit tests added | Behaviour change: dev environments without ENCRYPTION_KEY *or* SECRET_KEY now raise RuntimeError on first encrypt — this is intentional per the plan ("loud crash that's easy to fix"). MFA secrets use a distinct salt so the MFA Fernet key != field-encryption Fernet key derived from the same input. |
| F-004 + F-120 + F-062 | Critical+Low+Medium | ✅ Fixed | `backend/app/routers/seed_project.py` (prefix `/dev` → `/admin/seed-project`; route `/seed-project/{project_id}` → `/{project_id}`; `Depends(require_permission("projects.create"))`; SEED-MARKER sentinel idempotency replacing `count >= 20`); `backend/app/main.py` (move import + mount inside `if not is_prod:` block) | `ad5a5b9` | `python -m ast` parse OK; full path becomes `/api/v1/admin/seed-project/{project_id}` (was `/api/v1/dev/seed-project/{project_id}`) — frontend callers via `dev/seed-project/...` need the path update tracked in cross-cutting orphan list | Defence-in-depth: env gate + auth dep + sentinel idempotency. F-120 (router prefix collision with `dev_router`) handled in the same edit. F-062 (count threshold idempotency) replaced with sentinel. Frontend callers will need a follow-up to use the new path — no frontend caller for this endpoint currently exists per the audit's orphan list. |
| F-005 | Critical | ✅ Fixed | `frontend/src/app/projects/[id]/audit/page.tsx:49` | `3a50373` | Manual: load /projects/X/audit and confirm filters + pagination return scoped data | One-character fix: `{ params }` → `{ params: p }`. |
| F-006 | Critical | ⏸ Partial — history rewrite deferred | Moved `4_24_2026_SQL_ASTRA.sql` (binary 71,630 bytes pg_dump) to `C:/Users/Mason/Documents/ASTRA-backups/`; `.gitignore` adds `*.sql.dump`, `*.pgdump`, `[0-9]*_SQL_*.sql`, `*.bak` patterns | _next_ | `git ls-files \| grep 4_24` returns empty after commit; future pg_dump output at repo root is now `.gitignore`d | History rewrite (`git filter-repo --path 4_24_2026_SQL_ASTRA.sql --invert-paths`) is **deferred** per safety-rail §9 — needs Mason's explicit approval before force-push to origin/main. The dump file remains at `../ASTRA-backups/4_24_2026_SQL_ASTRA.sql` for inspection: `pg_restore -l ../ASTRA-backups/4_24_2026_SQL_ASTRA.sql` to see what tables it contains; if real user data is present, rotate credentials and run the filter-repo. *.bak gitignore line also covers F-023 (stale .bak files — actual delete in next commit). |
| F-121 | Low | ✅ Fixed | (folded into F-002 commit `d495747`) | `d495747` | n/a | Replaced silent `except: pass` in main.py optional-router/model/middleware loops with `logger.warning`. |
| F-138 | Info | ✅ Fixed | (folded into F-002 commit `d495747`) | `d495747` | n/a | `from app.models import ApprovalWorkflow` etc. now resolves. |

## New findings discovered during remediation

| Date | Finding | Severity | Status |
|---|---|---|---|

## Phase status

- [ ] Phase 1 — Critical Foundation
- [ ] Phase 2 — Security Hardening + Compliance
- [ ] Phase 3 — Medium Severity
- [ ] Phase 4 — Low Severity & Cleanup
- [ ] Phase 5 — Info & Follow-ups
- [ ] Post-remediation audit re-run

## Deferred items requiring user coordination

| Finding | Reason | Action required from Mason |
|---|---|---|
| F-006 (history rewrite) | Safety-rail §9: `git filter-repo` rewrites history — requires team coordination before force-push. The file is removed from current state (commit on this branch) but remains in git history. | (1) `pg_restore -l ../ASTRA-backups/4_24_2026_SQL_ASTRA.sql` to inspect contents; (2) if it contains real user data, rotate any credentials it touches; (3) run `git filter-repo --path 4_24_2026_SQL_ASTRA.sql --invert-paths` and force-push **only after team buy-in**; (4) confirm origin/main is clean with `git log --all -- 4_24_2026_SQL_ASTRA.sql`. |
