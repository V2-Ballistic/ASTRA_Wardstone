# ASTRA Backlog Remediation — Claude Code Prompt

**Source:** `BACKLOG.md` (23 findings: F-200 through F-222)
**Baseline commit:** `00b562a` on `main` (post-remediation re-audit 2026-05-01)
**Target codebase root:** `C:\Users\Mason\Documents\ASTRA`
**Branch strategy:** One branch per phase. Commit after each finding (or tightly-coupled cluster) so history is bisectable.
**Deliverable:** All fixes applied + `BACKLOG_REMEDIATION_LOG.md` updated after every finding. Template in §9.

---

## 1. Operating Rules (read before touching any file)

1. **Read `BACKLOG.md` before every fix.** Each finding has an exact file path and line range. Look it up, then edit.
2. **Phase order is dependency-ordered.** Do not skip ahead. F-200 → F-201 cluster → F-202/F-216 → the rest. Rationale is in the phase headers.
3. **Never run `alembic revision --autogenerate`.** The codebase has known schema drift. Write all migrations by hand.
4. **Syntax-validate every Python file you touch** before saving:
   ```
   python3 -c "import ast; ast.parse(open('path').read())"
   ```
5. **Never run `docker compose down -v`** — wipes the dev database.
6. **Backend pagination cap is 200.** Any new query that paginates must use `limit: int = Query(default=50, le=200)`.
7. **PostgreSQL enums require `values_callable`.** Any new or modified `SQLEnum(...)` column must include `values_callable=lambda x: [e.value for e in x]`.
8. **Deliver complete drop-in files.** No partial diffs in chat — write the full file when the file is the deliverable. For single-line fixes, show the before/after lines plus surrounding context.
9. **Update `BACKLOG_REMEDIATION_LOG.md` after every finding.** One row per finding: ID, status, files touched, commit SHA, verification result. Template in §9.
10. **Do not fix anything not listed here.** If you spot a new issue while editing, add it to `BACKLOG_REMEDIATION_LOG.md` under "New findings discovered" and stop. Mason needs the audit trail.
11. **After every phase**, run the verification block defined in §8 and paste the output into the log before starting the next phase.

---

## 2. Phase 1 — AUTH / TOKEN HARDENING (F-200, F-221)

**Branch:** `fix/backlog-phase-1-auth`
**Why first:** F-200 is the highest-impact single-line fix in the entire backlog. Non-local-login tokens (SAML/OIDC/PIV/MFA/refresh-rotation) currently bypass the JWT revocation list entirely. This must land before the membership sweep so any tokens minted during Phase 2 testing are fully revocable.

---

### 2.1 F-200 — `auth_manager.create_access_token` does not stamp `jti`

**Files:** `backend/app/services/auth_manager.py` (lines 40–54, 113, 204, 210, 236)

**Steps:**
1. Open `auth_manager.py`. In `create_access_token` (around line 40), add before the `jwt.encode` call:
   ```python
   import uuid  # add to top of file if not present
   to_encode.setdefault("jti", uuid.uuid4().hex)
   ```
2. Verify the same `to_encode.setdefault("jti", ...)` guard exists in `refresh_access_token` (line ~113), `authenticate` (line ~210), and `complete_mfa` (line ~236). If any of these call `create_access_token` internally, the fix propagates automatically — confirm by tracing the call chain before adding a duplicate.
3. Confirm that `get_current_user` in `backend/app/services/auth.py` already does `if jti: <revocation check>`. The fix makes `jti` always present, so the revocation branch now runs for all token paths.
4. Write a regression test at `backend/tests/test_auth_manager_jti.py`:
   - Issue a token via `auth_manager.create_access_token`
   - Decode it with `jwt.decode(token, key, algorithms=[...], options={"verify_exp": False})`
   - Assert `"jti" in payload` and `len(payload["jti"]) == 32`
   - Repeat for a token returned by `refresh_access_token`

**Verification:**
```
docker exec astra-backend-1 pytest tests/test_auth_manager_jti.py -v
```

**Commit message:** `fix(auth): stamp jti on auth_manager.create_access_token (F-200)`

---

### 2.2 F-221 — `revoke_access_token_jti` swallows all exceptions silently

**File:** `backend/app/services/auth.py:79–92`

**Steps:**
1. Locate the `except Exception` block in `revoke_access_token_jti`.
2. Replace with:
   ```python
   except Exception as exc:
       db.rollback()
       logger.warning("revoke_access_token_jti rolled back: %s", exc)
   ```
   The rollback stays; the silent swallow becomes a logged warning.

**Verification:** Manually inspect the change. No dedicated test needed — the warning is observable in logs.

**Commit message:** `fix(auth): log revoke_access_token_jti rollback exception (F-221)`

---

## 3. Phase 2 — PROJECT MEMBERSHIP SWEEP (F-201, F-208, F-210, F-211)

**Branch:** `fix/backlog-phase-2-membership`
**Why second:** These are all sub-cases of the same incomplete F-014 fix. One commit per router keeps the diffs reviewable. Fix them in this order: `audit.py` (F-208) → `seed_project.py` (F-210) → `imports.py` (F-211) → the full F-201 sweep across `workflows.py`, `ai.py`, `ai_writer.py`.

The fix pattern in all cases is:
- If the endpoint takes `project_id` as a path/query param: call `_check_membership(db, project_id, current_user)` immediately after the "project not found" guard.
- If the endpoint takes an entity ID (workflow_id, instance_id, etc.): load the row, read its `.project_id`, then call `_check_membership`.
- Mirror the negative test pattern from F-014: create a `dev_test_user` (not a member of any project), assert that a request from that user returns 403.

---

### 3.1 F-208 — `audit.py:get_audit_log` filters by `project_id` without `_check_membership`

**File:** `backend/app/routers/audit.py:43–72`

**Steps:**
1. Locate `get_audit_log` (the paginated `/audit/log` endpoint).
2. After the "no project_id" early-return/pass, add:
   ```python
   if project_id is not None:
       _check_membership(db, project_id, current_user)
   ```
3. The adjacent `/audit/export` endpoint (line ~217) is already gated — confirm it's still correct after your edit.
4. Add a test: non-member user + project_id → 403.

**Commit message:** `fix(audit): gate get_audit_log on project membership (F-208)`

---

### 3.2 F-210 — `seed_project.py:seed_project_data` has no membership check

**File:** `backend/app/routers/seed_project.py:465–491`

**Steps:**
1. Locate the "Project not found" guard (line ~484).
2. Immediately after it, add `_check_membership(db, project_id, current_user)`.
3. Import `_check_membership` from `app.dependencies.project_access` if not already imported in this file.
4. Add a test: non-member user calling the seed endpoint → 403.

**Commit message:** `fix(seed): gate seed_project_data on project membership (F-210)`

---

### 3.3 F-211 — `imports.py:confirm_import` re-validates project but skips membership

**File:** `backend/app/routers/imports.py:343–470`

**Steps:**
1. Locate `confirm_import`. It already checks the project exists — find that check.
2. Immediately after the "project not found" guard, add `_check_membership(db, project_id, current_user)`.
3. Check `preview_import` (lines 251–336) — apply the same guard if `project_id` is accepted there.
4. Add a test: non-member user confirming an import → 403.

**Commit message:** `fix(imports): gate confirm_import and preview_import on project membership (F-211)`

---

### 3.4 F-201 — Membership gaps in `workflows.py`, `ai.py`, `ai_writer.py`

**Files:**
- `backend/app/routers/workflows.py` (lines 116–227, 240–315) — ~14 project-scoped endpoints
- `backend/app/routers/ai.py` (lines 76–89, 92–111, 118–138, 277–331, 379–435)
- `backend/app/routers/ai_writer.py` — all 7 endpoints

**Steps (one commit per router):**

**Commit A — `workflows.py`:**
1. For every endpoint that accepts `project_id` (path or query): add `_check_membership(db, project_id, current_user)` after the project-exists guard.
2. For entity-keyed endpoints (workflow_id / instance_id / signature_id): load the entity, read `entity.project_id`, call `_check_membership(db, entity.project_id, current_user)`. Pattern is identical to `_assert_member_for_entity` in `interface.py` — copy that approach.
3. Add at minimum: one positive test (member can access) and one negative test (non-member gets 403) for the most write-heavy workflow endpoint.

**Commit B — `ai.py`:**
1. Apply the same `_check_membership` pattern to the 5 ungated endpoints: `get_project_duplicates`, `check_duplicate`, `get_trace_suggestions`, `reindex_embeddings`, `get_ai_stats`.
2. Confirm the already-gated `/trace-suggestions/by-project` endpoint is untouched.
3. Add a negative test for `get_ai_stats` (representative of the pattern).

**Commit C — `ai_writer.py`:**
1. All 7 endpoints need `_check_membership`. Apply the pattern.
2. Add one negative test.

**Commit message per router:**
```
fix(workflows): apply project membership gate to all project-scoped endpoints (F-201)
fix(ai): apply project membership gate to ungated endpoints (F-201)
fix(ai_writer): apply project membership gate to all endpoints (F-201)
```

---

## 4. Phase 3 — DEV ROUTER HARDENING (F-202, F-216)

**Branch:** `fix/backlog-phase-3-dev-router`
**Why its own branch:** Auth-gating `dev.py` is a policy decision that warrants a separate diff. Do not bundle with Phase 2.

---

### 4.1 F-202 — `POST /dev/reset` exposes unauthenticated table-drop

**File:** `backend/app/routers/dev.py:146–261`

**Steps:**
1. Add `current_user: User = Depends(require_any_role(UserRole.ADMIN))` to both `seed_database` (line ~147) and `reset_and_seed` (line ~257).
2. Add a required confirmation header to `/dev/reset`:
   ```python
   x_confirm: str = Header(None, alias="X-Dev-Reset-Confirm")
   if x_confirm != "I-mean-it":
       raise HTTPException(400, "Send X-Dev-Reset-Confirm: I-mean-it to proceed")
   ```
3. Emit an audit event before the `drop_all` call:
   ```python
   await audit_service.log(db, actor=current_user, action="dev.reset", detail={"trigger": "manual"})
   ```
   If `audit_service` is async, adapt accordingly.
4. Add a test: unauthenticated caller → 401; non-admin caller → 403; admin without header → 400.

**Commit message:** `fix(dev): require ADMIN auth + confirmation header on reset endpoints (F-202)`

---

### 4.2 F-216 — `reset_and_seed` drops tables without a service-unavailable shim

**File:** `backend/app/routers/dev.py:256–261`

**Steps:**
1. Immediately before `Base.metadata.drop_all(bind=engine)`, set a module-level flag (e.g., `_RESET_IN_PROGRESS = True`) and immediately after `seed_database` completes, clear it.
2. In a middleware (or near the top of the `reset_and_seed` handler), if `_RESET_IN_PROGRESS` is already `True`, return HTTP 503 Service Unavailable.
3. This is a best-effort shim for single-worker dev. Document in a comment that the proper fix for multi-worker is a Redis flag (deferred per BACKLOG.md).

**Commit message:** `fix(dev): add in-progress guard to reset_and_seed (F-216)`

---

## 5. Phase 4 — DATA INTEGRITY & CONTRACT (F-203, F-204, F-205)

**Branch:** `fix/backlog-phase-4-integrity`

---

### 5.1 F-203 — Requirements creation uses racy `count + 1` for req_id

**Files:** `backend/app/routers/requirements.py:314–318, 575–578`, `backend/app/routers/imports.py:393–397`

**Steps:**
1. Open `requirements.py`. In `create_requirement`, find the `count + 1` / `generate_requirement_id` call. Replace with:
   ```python
   from app.services.id_sequence import next_human_id
   req_id = next_human_id(db, project_id, prefix=<req_type_prefix>, source_model=Requirement, id_field="req_id")
   ```
   Use the same pattern already applied in `interface.py` and `projects.py:create_artifact` — look at those files first to get the exact call signature.
2. Apply the same replacement in `clone_requirement` (line ~575).
3. In `imports.py:confirm_import` (line ~393), apply the same replacement. Note: batch imports must resolve IDs sequentially within the transaction (each call to `next_human_id` locks the row and increments it atomically), so the loop order matters — process rows in the order they arrive, not in parallel.
4. Write a concurrency regression test in `backend/tests/test_requirement_id_race.py`:
   - Use `threading.Thread` (or `asyncio.gather` if the test client supports it) to fire two simultaneous `POST /requirements/` calls for the same project.
   - Assert both succeed (200) and return distinct `req_id` values.

**Verification:**
```
docker exec astra-backend-1 pytest tests/test_requirement_id_race.py -v
```

**Commit message:** `fix(requirements): replace count+1 req_id with next_human_id (F-203)`

---

### 5.2 F-204 — Frontend sends `confirm` param; backend expects `force` on 6 DELETE endpoints

**File:** `frontend/src/lib/interface-api.ts:76–77, 139–140, 167–168, 202–203, 239–240, 403–404`

**Steps:**
1. Open `interface-api.ts`. Find every occurrence of `confirm: true` or `confirm=true` in DELETE call params.
2. Rename to `force: true` / `force=true` in all 6 locations:
   - `deleteUnit`
   - `deleteBus`
   - `deleteMessage`
   - `deleteHarness`
   - `deleteWire`
   - `deleteHarnessEndpoint`
3. Confirm that `deleteSystem` and `deleteConnector` already use `force` (they were updated in Phase 3C) — leave those untouched.
4. Run `npm run typecheck` to confirm no TypeScript errors introduced.

**Verification:**
```
cd frontend && npm run typecheck
```

**Commit message:** `fix(frontend): rename confirm→force on interface DELETE params (F-204)`

---

### 5.3 F-205 — `Requirement` and `Baseline` FKs missing `ondelete` strategy

**File:** `backend/app/models/__init__.py:181 (Requirement), :333 (Baseline)`

**Steps:**
1. In the `Requirement` model, find the `project_id` ForeignKey definition. Change to:
   ```python
   project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
   ```
2. Apply the same change to `Baseline.project_id`.
3. Write a hand-authored Alembic migration (do NOT use `--autogenerate`):
   ```python
   # In upgrade():
   op.drop_constraint("requirements_project_id_fkey", "requirements", type_="foreignkey")
   op.create_foreign_key(
       "requirements_project_id_fkey", "requirements", "projects",
       ["project_id"], ["id"], ondelete="CASCADE"
   )
   # Repeat for baselines_project_id_fkey / baselines
   ```
4. Apply the migration: `docker exec astra-backend-1 alembic upgrade head`
5. Add a test that hard-deletes a project via raw SQL and asserts the associated requirements and baselines are gone (not a constraint violation).
   > Note: `AuditLog.project_id` was intentionally set to `SET NULL` in F-076 to preserve the audit trail (AU-9). Do not change it. Only `Requirement` and `Baseline` get `CASCADE` here.

**Verification:**
```
docker exec astra-backend-1 alembic upgrade head
docker exec astra-backend-1 alembic check
docker exec astra-backend-1 pytest tests/test_project_cascade_delete.py -v
```

**Commit message:** `fix(models): add ondelete=CASCADE to Requirement and Baseline project_id FKs (F-205)`

---

## 6. Phase 5 — MEDIUM SEVERITY (F-206 through F-215)

**Branch:** `fix/backlog-phase-5-medium`
Do these in order within the branch. Each is a small, isolated change — commit after each one.

---

### 6.1 F-206 — `get_current_user` swallows generic `Exception` in revoked-tokens lookup

**File:** `backend/app/services/auth.py:61–71`

Replace `except (ImportError, Exception)` with:
```python
except (ProgrammingError, OperationalError, NoSuchTableError) as exc:
    logger.warning("Revocation table check failed, allowing token: %s", exc)
```
Import `ProgrammingError`, `OperationalError`, `NoSuchTableError` from `sqlalchemy.exc`. A transient DB error should not silently grant authentication — the warning surfaces it.

**Commit message:** `fix(auth): narrow exception handling in revoked-token lookup (F-206)`

---

### 6.2 F-207 — Frontend RBAC matrix missing `interfaces.*` and `reports.export` actions

**File:** `frontend/src/lib/auth.tsx:30–79`

1. Open `auth.tsx`. Find the `PERMISSION_MATRIX` constant.
2. Add the following to the ADMIN and PROJECT_MANAGER entries (mirror `backend/app/services/rbac.py:23–92`):
   - `interfaces.create`
   - `interfaces.update`
   - `interfaces.delete`
3. Add `reports.export` to ADMIN, PROJECT_MANAGER, STAKEHOLDER, and DEVELOPER entries as the backend grants it.
4. Add a comment above the matrix:
   ```typescript
   // SYNC NOTE: This matrix must mirror backend/app/services/rbac.py.
   // If you change one, change the other.
   ```
5. Run `npm run typecheck`.

**Commit message:** `fix(frontend): sync PERMISSION_MATRIX with backend RBAC grants (F-207)`

---

### 6.3 F-209 — Integration catalog advertises stale webhook URLs (pre-F-017 paths)

**File:** `backend/app/routers/integrations.py:593, 605`

1. Find where `webhook_url` is constructed for Jira and Azure entries.
2. Change the static strings from `/integrations/jira/webhook` and `/integrations/azure/webhook` to templates that include `{config_id}` — or better, compute them per-config on the detail response using the request's base URL so the returned value is always a fully-resolved, copy-pasteable URL.
3. If the catalog endpoint returns a list before any configs are created (config_id is unknown), change the field name to `webhook_url_template` and return a pattern string like `/api/v1/integrations/{config_id}/jira/webhook`. Document the rename in the response schema.

**Commit message:** `fix(integrations): update catalog webhook URLs to post-F-017 paths (F-209)`

---

### 6.4 F-212 — `signature_service.get_signatures` issues N+1 user lookups

**File:** `backend/app/services/signature_service.py:349–377`

Replace the per-row `db.query(User).filter(User.id == s.user_id).first()` loop with a single LEFT JOIN:
```python
rows = (
    db.query(ElectronicSignature, User)
    .outerjoin(User, User.id == ElectronicSignature.user_id)
    .filter(ElectronicSignature.entity_type == entity_type, ElectronicSignature.entity_id == entity_id)
    .all()
)
return [build_signature_response(sig, user) for sig, user in rows]
```
Adjust `build_signature_response` (or equivalent) if needed.

**Commit message:** `fix(signatures): replace N+1 user lookup with LEFT JOIN (F-212)`

---

### 6.5 F-213 — `_resolve_project_for_baseline_create` is dead code that raises `NotImplementedError`

**File:** `backend/app/routers/baselines.py:43–52`

Delete the entire `_resolve_project_for_baseline_create` function. The working membership pattern is the inline `_check_membership` call in `create_baseline` at line ~66. Verify nothing calls `_resolve_project_for_baseline_create` before deleting: `grep -r "_resolve_project_for_baseline_create" backend/`.

**Commit message:** `fix(baselines): delete dead _resolve_project_for_baseline_create (F-213)`

---

### 6.6 F-214 — `audit.py` per-entity trail uses bare `get_current_user`

**File:** `backend/app/routers/audit.py:79–92`

The preferred fix (keep it accessible to engineers, not just admins):
1. Load the entity being queried to resolve its `project_id`.
2. Call `_check_membership(db, entity.project_id, current_user)`.
3. If the entity type doesn't have a `project_id` (e.g., global catalog entities), fall through without a membership check.

If entity-type resolution is too complex to do cleanly right now, fall back to: add `_audit_dep` (ADMIN/PM gate) consistent with sibling endpoints, and document the limitation.

**Commit message:** `fix(audit): apply consistent access control to per-entity audit trail (F-214)`

---

### 6.7 F-215 — Audit endpoints accept `limit` up to 500; platform standard is 200

**File:** `backend/app/routers/audit.py:53, 84`

Change the `limit` parameter declarations from `le=500` (or no ceiling) to `le=200` on both `/audit/log` and `/audit/log/entity/...`. If these were intentionally higher for ops tooling, add a comment documenting the exception and leave at 200 for now — an ops-team approval is needed to raise it formally.

**Commit message:** `fix(audit): cap audit endpoint limit params at 200 per platform standard (F-215)`

---

## 7. Phase 6 — LOW SEVERITY & CLEANUP (F-217 through F-220)

**Branch:** `fix/backlog-phase-6-cleanup`

---

### 7.1 F-217 — Four `.bak` files committed in working tree

**Files:** `backend/app/routers/interface.py.bak`, `backend/app/services/reports/change_history.py.bak`, `frontend/src/app/projects/[id]/requirements/[reqId]/page.tsx.bak`, `frontend/src/app/projects/[id]/verification/page.tsx.bak`

1. `git rm backend/app/routers/interface.py.bak`
2. `git rm backend/app/services/reports/change_history.py.bak`
3. `git rm "frontend/src/app/projects/[id]/requirements/[reqId]/page.tsx.bak"`
4. `git rm "frontend/src/app/projects/[id]/verification/page.tsx.bak"`
5. Confirm `.gitignore` already contains `*.bak` (added in original F-006 remediation). If not, add it now.

**Commit message:** `chore: remove committed .bak files (F-217)`

---

### 7.2 F-218 — `devAPI.seedProject` calls the pre-F-004 route path

**File:** `frontend/src/lib/api.ts:191–194`

1. First, `grep -r "devAPI.seedProject\|devAPI\.seedProject" frontend/src/` to confirm whether anything in the UI actually calls this function.
2. **If nothing calls it:** delete the `devAPI.seedProject` function entirely and the enclosing `devAPI` object if it's empty.
3. **If something does call it:** update the path to `/admin/seed-project/${projectId}` to match the F-004 relocation.
4. Run `npm run typecheck`.

**Commit message:** `fix(frontend): remove/update stale devAPI.seedProject path (F-218)`

---

### 7.3 F-219 — `.env.example` uses `admin@astra.local` which triggers pgAdmin restart loop

**File:** `.env.example:25`

Change `PGADMIN_DEFAULT_EMAIL=admin@astra.local` to `PGADMIN_DEFAULT_EMAIL=admin@example.com`. Also update the live `.env` file on the dev machine (not committed — add a note in the BACKLOG_REMEDIATION_LOG.md that Mason should update `.env` manually).

**Commit message:** `fix(config): replace .local TLD in .env.example PGADMIN_DEFAULT_EMAIL (F-219)`

---

### 7.4 F-220 — SAML `authenticate` honours IdP-provided `role` attribute verbatim

**File:** `backend/app/services/auth_providers/saml.py:148–162`

1. Find where the SAML `role` attribute flows into `find_or_create_user`.
2. For new user provisioning: always pass `role=UserRole.DEVELOPER` regardless of IdP-provided value.
3. Add a log warning when the IdP attribute is present and differs from `developer`:
   ```python
   idp_role = attributes.get("role")
   if idp_role and idp_role != "developer":
       logger.warning("SAML IdP provided role=%s for new user %s; ignoring, defaulting to developer", idp_role, username)
   ```
4. Check `auth_providers/oidc.py` for the parallel pattern — apply the same guard if found.

**Commit message:** `fix(saml): ignore IdP-provided role on new user provisioning (F-220)`

---

## 8. Verification Procedure

Run this full block at the end of **every phase** before opening a PR. Paste the output into `BACKLOG_REMEDIATION_LOG.md`.

**Backend health:**
```bash
docker exec astra-backend-1 python -c "from app.main import app; print(len(app.routes))"
docker exec astra-backend-1 alembic current
docker exec astra-backend-1 alembic check
```

**Full test suite (run after every phase — fix any failures before moving on):**
```bash
docker exec astra-backend-1 pytest tests/ -x -q -m "not performance"
```

**After Phase 4 only (migrations touched):**
```bash
docker exec astra-backend-1 alembic upgrade head
docker exec astra-backend-1 alembic check
docker exec astra-backend-1 pytest tests/test_project_cascade_delete.py -v
```

**Frontend checks (run after Phase 4 and Phase 5):**
```bash
cd frontend && npm run typecheck
cd frontend && npm run build
```

**Per-phase targeted test runs (run these in addition to the full suite):**

| Phase | Targeted command |
|---|---|
| Phase 1 | `pytest tests/test_auth_manager_jti.py -v` |
| Phase 2 | `pytest tests/ -k "membership or project_access" -v` |
| Phase 3 | `pytest tests/ -k "dev_router or reset" -v` |
| Phase 4 | `pytest tests/test_requirement_id_race.py tests/test_project_cascade_delete.py -v` |
| Phase 5 | `pytest tests/ -x -q -m "not performance"` (full suite) |
| Phase 6 | `npm run typecheck && npm run build` |

**Final gate before declaring complete:**
- `pytest tests/ -q -m "not performance"` is fully green (0 failures, 0 errors)
- `npm run typecheck` exits 0
- `npm run build` exits 0
- `alembic check` reports "No new upgrade operations detected"
- `git status` shows no untracked `.bak` files

---

## 9. `BACKLOG_REMEDIATION_LOG.md` Template

Write this file to `C:\Users\Mason\Documents\ASTRA\BACKLOG_REMEDIATION_LOG.md` and append a row after every finding.

```markdown
# ASTRA Backlog Remediation Log
**Started:** <YYYY-MM-DD>
**Source:** BACKLOG.md / AUDIT_FINDINGS_POST_REMEDIATION.md (baseline commit 00b562a)

## Progress

| Finding | Severity | Status | Files Touched | Commit | Verification | Notes |
|---|---|---|---|---|---|---|
| F-200 | High | ✅ Fixed | `backend/app/services/auth_manager.py`, `backend/tests/test_auth_manager_jti.py` | `<sha>` | `pytest tests/test_auth_manager_jti.py` → PASSED | — |
| F-221 | Low | ✅ Fixed | `backend/app/services/auth.py` | `<sha>` | Code review only | — |
| F-208 | Medium | ✅ Fixed | `backend/app/routers/audit.py` | `<sha>` | `pytest -k membership` → PASSED | — |
| ... | | | | | | |

## Phase Status

- [ ] Phase 1 — Auth / Token Hardening (F-200, F-221)
- [ ] Phase 2 — Project Membership Sweep (F-201, F-208, F-210, F-211)
- [ ] Phase 3 — Dev Router Hardening (F-202, F-216)
- [ ] Phase 4 — Data Integrity & Contract (F-203, F-204, F-205)
- [ ] Phase 5 — Medium Severity (F-206–F-215)
- [ ] Phase 6 — Low Severity & Cleanup (F-217–F-220)
- [ ] Final verification gate

## New findings discovered during remediation

| Date | Description | Severity | Action |
|---|---|---|---|
| ... | ... | ... | ... |
```

---

## 10. Safety Rails (re-read before any destructive operation)

- **Before any migration touching a populated table** (`ALTER COLUMN`, `DROP CONSTRAINT`, `CREATE FOREIGN KEY`):
  ```bash
  docker exec astra-db-1 pg_dump -U astra -d astra > /tmp/pre-migration-$(date +%s).sql
  docker cp astra-db-1:/tmp/pre-migration-*.sql .
  ```
  Move the file outside the repo root immediately so `.gitignore`'s `[0-9]*_SQL_*.sql` pattern catches it if it ends up there.
- **Never run `alembic downgrade base`** — Phase 2 of the original remediation added a production guard against destructive downgrades; respect it.
- **For Phase 2 negative tests**, you need a `dev_test_user` who is not a member of any project. The seed user `mason` is admin of everything. Create a fresh fixture user for the negative assertions — do not reuse `mason`.
- **F-203 batch import fix**: the `next_human_id` lock pattern is correct only within a single transaction. Confirm the `confirm_import` transaction boundary encloses all ID generations before committing.

---

## 11. Finding → Phase Quick Reference

| Finding | Severity | Phase | One-line description |
|---|---|---|---|
| F-200 | High | 1 | `auth_manager` missing `jti` on all non-local tokens |
| F-221 | Low | 1 | `revoke_access_token_jti` swallows exceptions silently |
| F-208 | Medium | 2 | `get_audit_log` missing membership check |
| F-210 | Medium | 2 | `seed_project_data` missing membership check |
| F-211 | Medium | 2 | `confirm_import` missing membership check |
| F-201 | High | 2 | ~14 endpoints across workflows/ai/ai_writer missing membership |
| F-202 | High | 3 | `POST /dev/reset` unauthenticated — drops all tables |
| F-216 | Medium | 3 | `reset_and_seed` no service-unavailable guard during drop |
| F-203 | High | 4 | Requirements req_id uses racy `count + 1` → 500 on collision |
| F-204 | High | 4 | Frontend sends `confirm`; backend expects `force` on 6 DELETEs |
| F-205 | High | 4 | `Requirement`/`Baseline` FK missing `ondelete` strategy |
| F-206 | Medium | 5 | `get_current_user` swallows all exceptions in revocation lookup |
| F-207 | Medium | 5 | Frontend RBAC matrix missing `interfaces.*` and `reports.export` |
| F-209 | Medium | 5 | Integration catalog advertises stale pre-F-017 webhook URLs |
| F-212 | Medium | 5 | `signature_service.get_signatures` N+1 user lookups |
| F-213 | Medium | 5 | `_resolve_project_for_baseline_create` dead code, raises NotImplementedError |
| F-214 | Medium | 5 | Per-entity audit trail uses bare `get_current_user` |
| F-215 | Medium | 5 | Audit endpoints allow `limit=500`; standard is 200 |
| F-217 | Low | 6 | Four `.bak` files committed to working tree |
| F-218 | Low | 6 | `devAPI.seedProject` calls the pre-F-004 route |
| F-219 | Low | 6 | `.env.example` pgAdmin email uses `.local` TLD → restart loop |
| F-220 | Low | 6 | SAML honours IdP-provided `role` verbatim on new users |
| F-222 | Info | — | Webhook URL architecture note — no code change required |

---

When `BACKLOG_REMEDIATION_LOG.md` shows all 22 actionable findings as ✅ Fixed (F-222 is Info/no-action), the final verification gate passes, and `pytest` + `npm run build` are both green, print to stdout:

```
BACKLOG REMEDIATION COMPLETE — 22 findings resolved, 1 deferred (F-222 Info/no-action), see BACKLOG_REMEDIATION_LOG.md
```

Then stop. Do not summarize in chat. The log is the deliverable.
