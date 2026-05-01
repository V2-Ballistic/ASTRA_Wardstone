# ASTRA Audit Findings — Post-Remediation Re-Audit
**Date:** 2026-04-30
**Commit/branch:** `4ece3e4` on `fix/phase-4-cleanup`
**Files scanned:** ~208 (.py + .ts + .tsx + .yml + .sql)
**Total findings:** 23 (3 persisting + 20 new at F-200+)

## Executive Summary
- Critical: 0
- High: 6
- Medium: 11
- Low: 5
- Info: 1

The ASTRA codebase has materially improved since the original 121-finding
audit. All five Critical findings (auth-bypass, secrets-in-repo,
encryption-key fallback, seed-router auth, project-membership leak) and
every High-severity compliance gap (audit log triggers, signature
record-binding, PIV chain validation, IdP step-up) have been remediated
with both code changes and regression tests. The hash-chained audit log,
durable refresh-token rotation, append-only triggers, FOR-UPDATE-locked
ID sequences, and TrustedHost / scram-sha-256 hardening are all in
place and verified in the codebase.

The post-remediation findings cluster around **three remaining themes**:

1. **F-014 was incomplete in non-`interface.py` routers.** The
   workflow router, integrations webhook catalog, AI router, imports
   router, seed-project handler, and parts of the audit router still
   gate on role only (or on bare authentication) without consulting
   project membership. A PROJECT_MANAGER can read/write workflows for
   projects they don't belong to; any authenticated user can fetch any
   entity's audit trail; a user with `requirements.create` can import
   into any project.

2. **F-074 was incomplete for the requirements router.** The race-free
   `next_human_id` helper covers `interface.py` and `projects.py:create_artifact`,
   but `requirements.py:create_requirement`, `clone_requirement`, and
   `imports.py:confirm_import` still derive new req_ids from
   `count + 1`. With F-075's UNIQUE constraint now in place, this
   produces 500-IntegrityError instead of the silent collision it used
   to — but the race remains.

3. **`auth_manager.create_access_token` does not stamp a `jti`.** The
   F-063 revocation mechanism only protects tokens issued via
   `services.auth.create_access_token`. Tokens minted by the SAML / OIDC
   / PIV / MFA / refresh-rotation paths in `auth_manager.py` carry no
   `jti`, so logout/admin-revoke is a no-op for the entire non-local
   auth surface — including the new `/auth/refresh` rotation path.
   This is the single highest-impact post-remediation finding.

Several smaller gaps round out the list: dev router has no auth
(`POST /dev/reset` will drop all tables for any unauthenticated caller
in dev environments); the frontend-backend `confirm` vs `force` query
param drift on six interface DELETE endpoints means UI cascade-delete
clicks silently fail with 409; the `devAPI.seedProject` frontend caller
still hits `/dev/seed-project/...` (dead since F-004 moved the route);
two committed `.bak` files (`interface.py.bak`,
`change_history.py.bak`) plus two frontend `.bak` files leak old code
into the build context.

Recommended priority: (1) stamp `jti` on `auth_manager.create_access_token`
(F-200, single line); (2) audit `_check_membership` coverage on
workflows/imports/AI/audit/seed routers (F-201, ~10 endpoints); (3)
fix the `confirm` vs `force` drift on interface deletes (F-202,
6 frontend lines); (4) remove the four `.bak` files.

## Remediation Comparison

| Original audit | Count |
|---|---:|
| Total findings (121 original + 5 discovered) | 126 |
| ✅ Resolved (fixed or verified-closed) | 123 |
| ⏸ Deferred (with rationale) | 5 |
| Persisting in current code (re-flagged below) | 3 |
| **NEW findings introduced or missed by original audit** | 20 |

## Persisting Findings (from original audit, not yet resolved)

These findings from `AUDIT_FINDINGS.md` were marked "Fixed" in the
remediation log but the underlying issue still exists in some code path
the original fix did not touch.

### F-014 (PARTIAL — workflows / imports / AI / audit / seed)
- **Status:** marked Fixed in REMEDIATION_LOG (per-router cluster
  commits). Several non-`interface.py` endpoints still bypass
  `_check_membership`. See **F-201** below for full enumeration.
- **Why this is a persistence note rather than a new finding:** the
  original audit framed F-014 as "every project-id-aware endpoint
  must check membership." The remediation closed the largest groups
  but the workflow, AI, and audit routers were skipped or only
  partially covered.

### F-074 (PARTIAL — requirements router)
- **Status:** marked Fixed for `interface.py` + `projects.py:create_artifact`.
  `requirements.py:create_requirement` (line 314-318), `clone_requirement`
  (line 575-578), and `imports.py:confirm_import` (line 393-397) still
  derive `req_id` from `count + 1`. See **F-203** below.

### F-077 (PARTIAL — Float on engineering-unit columns)
- **Status:** marked Fixed for the seven `MessageField` scale/offset
  columns (migration 0021). Other engineering-physical columns on
  `Unit` (`mass_kg`, `voltage_input_min`, `temp_operating_min_c`,
  etc. at `models/interface.py:1124-1169`) remain `Float`. These
  participate in environmental margin checks; whether `Float` rounding
  matters for them is a domain call the original audit didn't make
  explicit. **Status: Needs Manual Review** — likely fine for physical
  dimensions, less fine for tolerance arithmetic.

## New Findings (post-remediation discoveries)

20 new findings, F-200..F-219, listed below in their severity sections.

## Findings

### CRITICAL

*(none)*

### HIGH

#### F-200 — `auth_manager.create_access_token` does not stamp `jti`; F-063 revocation list cannot block tokens issued by SAML / OIDC / PIV / MFA / refresh-rotation
- **File:** `backend/app/services/auth_manager.py`
- **Lines:** 40-54 (also: 113 `refresh_access_token`, 204/210/236 `authenticate` + `complete_mfa`)
- **Category:** Backend / Security
- **Description:** `services.auth.create_access_token` (line 36 of `services/auth.py`) correctly calls `to_encode.setdefault("jti", uuid.uuid4().hex)` so every issued JWT carries a unique jti claim. The parallel implementation at `services/auth_manager.py:40-54` does NOT. Tokens minted by `authenticate()` (the SAML / OIDC / PIV path, line 210), `complete_mfa()` (line 236), `refresh_access_token()` (line 113), and partial-MFA tokens (line 204) all lack `jti`. `get_current_user` reads `jti = payload.get("jti")` (`services/auth.py:49`) and the revocation check at line 61 is gated by `if jti:` — so any non-local-login token simply skips the revocation list entirely.
- **Impact:** F-063 (the entire durable revocation infrastructure built in Phase 3C, including the `revoked_tokens` table and `POST /auth/logout`) is a **no-op for every token issued through `auth_manager.py`**. With AUTH_PROVIDER=saml/oidc/piv this is every token in the deployment. Even with AUTH_PROVIDER=local, every token returned by `/auth/refresh` (the new F-068 rotation endpoint) is unrevocable. Logout silently succeeds at the frontend but the JWT remains valid until natural expiry. Defeats the entire stated goal of F-063.
- **Recommendation:** Add `to_encode.setdefault("jti", uuid.uuid4().hex)` (and `import uuid`) to `auth_manager.create_access_token` before the `jwt.encode` call at line 54. Add a regression test that decodes the token issued by `refresh_access_token` and asserts `payload["jti"]` is present.
- **Evidence:**
  ```python
  # services/auth_manager.py:47-54
  def create_access_token(data: dict, ...) -> str:
      to_encode = data.copy()
      expire = datetime.utcnow() + (...)
      to_encode.update({"exp": expire})
      if partial:
          to_encode["mfa_pending"] = True
      return jwt.encode(to_encode, settings.SECRET_KEY.get_secret_value(),
                        algorithm=settings.ALGORITHM)
      # NO jti stamp — F-063 cannot revoke this
  ```

#### F-201 — F-014 incomplete: workflows / AI / audit / seed-project / imports endpoints accept project_id (or operate on project-scoped entities) without `_check_membership`
- **File:** `backend/app/routers/workflows.py` (lines 116-227, 240-315 — every workflow endpoint), `backend/app/routers/audit.py` (lines 43-72 `get_audit_log`, 79-92 `get_entity_audit_trail`), `backend/app/routers/imports.py` (lines 251-336 `preview_import`, 343-470 `confirm_import`), `backend/app/routers/ai.py` (lines 76-89 `get_project_duplicates`, 92-111 `check_duplicate`, 118-138 `get_trace_suggestions`, 277-331 `reindex_embeddings`, 379-435 `get_ai_stats`), `backend/app/routers/seed_project.py:465-491`
- **Lines:** as above
- **Category:** Backend / Security
- **Description:** Each of these endpoints either takes a project_id or loads a project-scoped entity but enforces only role (`require_any_role(ADMIN, PROJECT_MANAGER)`) or permission (`require_permission(...)`) — not membership. The original F-014 fix wired `_check_membership` through `interface.py`, `projects.py`, `requirements.py`, etc., but skipped these. Concrete consequences:
  - Any `PROJECT_MANAGER` can list / create / update / delete approval workflows and stages for projects they're not assigned to.
  - Any authenticated user can call `GET /audit/log/entity/{type}/{id}` and read the entire audit trail of any requirement, baseline, or signature anywhere in the system.
  - Any user with `requirements.create` permission can preview-import or confirm-import requirements into any project.
  - Any user with `ai.reindex` can re-embed any project. Any authenticated user can list duplicates, check duplicates, fetch trace suggestions, and view AI stats for any project.
  - Any user with `projects.create` (admin or PM) can fully seed any project's data via `POST /admin/seed-project/{project_id}` without being a member.
- **Impact:** Cross-project data leak / write paths matching the same threat model F-014 was designed to close.
- **Recommendation:** Add `_check_membership(db, project_id, current_user)` (or the `project_member_required` dependency) to every endpoint listed. For workflow endpoints keyed by workflow_id / stage_id / instance_id, walk the row to its `project_id` first (analogous to `_assert_member_for_entity` in `interface.py`).
- **Evidence:**
  ```python
  # routers/workflows.py:116-130
  @router.post("/", status_code=201)
  def create_workflow(
      data: WorkflowCreate,
      db: Session = Depends(get_db),
      current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
  ):
      wf = ApprovalWorkflow(
          name=data.name, ...,
          project_id=data.project_id, ...,  # data.project_id never validated
      )
      db.add(wf); db.commit(); db.refresh(wf)
      return _wf_to_dict(wf)
  ```

#### F-202 — `dev` router has no authentication; `POST /dev/reset` drops all tables for any unauthenticated caller in dev environments
- **File:** `backend/app/routers/dev.py:146-261`
- **Lines:** 147 (`seed_database`), 257 (`reset_and_seed`)
- **Category:** Backend / Security
- **Description:** Neither endpoint includes `Depends(get_current_user)` or any auth dep. They rely entirely on the env-gate in `main.py:101` (`if not is_prod: from app.routers.dev import router as dev_router`). If `ENVIRONMENT` is anything other than `production` (the default is `development`, plus `staging` / `qa` / `test`), `POST /api/v1/dev/reset` will `Base.metadata.drop_all(bind=engine)` then re-seed. Any port-scan that finds the dev backend can wipe the database.
- **Impact:** Data destruction in any non-production environment from an unauthenticated network-reachable attacker. Even on the developer's laptop a misbehaving browser tab on a malicious site (CSRF — credentials are not required so SameSite doesn't help) could submit the reset. Production is gated, so this is "only" dev/staging.
- **Recommendation:** Wrap both endpoints with `current_user: User = Depends(require_any_role(UserRole.ADMIN))` and require an additional `X-Dev-Reset-Confirm: I-mean-it` header on `/reset`. The audit trail entry `dev.reset` should be emitted before the drop runs.
- **Evidence:**
  ```python
  # routers/dev.py:256-261
  @router.post("/reset")
  def reset_and_seed(db: Session = Depends(get_db)):
      """Drop all tables, recreate, and seed. DEV ONLY."""
      Base.metadata.drop_all(bind=engine)   # no auth, no audit
      Base.metadata.create_all(bind=engine)
      return seed_database(db)
  ```

#### F-203 — `requirements.py` create / clone / import paths still use racy `count + 1` for req_id generation; with F-075's UNIQUE constraint this surfaces as 500
- **File:** `backend/app/routers/requirements.py:314-318` (`create_requirement`), `:575-578` (`clone_requirement`), `backend/app/routers/imports.py:393-397` (`confirm_import`)
- **Category:** Backend / Correctness / Reliability
- **Description:** F-074 introduced `services.id_sequence.next_human_id` with `SELECT … FOR UPDATE` to serialise concurrent generators. The remediation log says the helper is wired into `interface.py` and `projects.py:create_artifact`. The requirement-creation paths were missed. With F-075 now enforcing `uq_req_per_project (project_id, req_id)`, two concurrent `POST /requirements/?project_id=X` calls of the same `req_type` will both compute `count + 1`, both build the same `req_id`, and the second commit will raise IntegrityError → FastAPI 500. The original F-074 race (silent ID reuse) is fixed by the constraint, but the user-visible behaviour is now a 500 instead of a duplicate.
- **Impact:** Concurrent imports / quick-fire UI creates produce 500 errors with no actionable detail. CSV bulk imports with parent-child requirements within a single batch also have the wrong count basis (the `req_id_to_pk` map is updated but the `db.query(func.count(...))` is not aware of the in-flight rows in the same transaction).
- **Recommendation:** Replace `count + 1` + `generate_requirement_id` with `next_human_id(db, project_id, prefix=…, source_model=Requirement, id_field="req_id")` in all three call sites. The `imports.py` confirm path also needs to handle the in-batch parent-resolution case so children don't reuse the same number as siblings.
- **Evidence:**
  ```python
  # routers/requirements.py:314-318
  count = db.query(func.count(Requirement.id)).filter(
      Requirement.project_id == project_id,
      Requirement.req_type == req_data.req_type,
  ).scalar()
  req_id = generate_requirement_id(project.code, req_data.req_type, count + 1)
  # racy — concurrent calls compute the same count → same req_id → IntegrityError
  ```

#### F-204 — Frontend `interface-api.ts` sends `confirm` query parameter on six DELETE endpoints; backend now expects `force` (F-047 contract change)
- **File:** `frontend/src/lib/interface-api.ts:76-77, 139-140, 167-168, 202-203, 239-240, 403-404`
- **Lines:** as above
- **Category:** Cross-cutting / API Contract Drift
- **Description:** Phase 3C F-047 standardised every interface DELETE on a `force=true` query param to bypass the cascade-safety gate. The backend now consistently uses `force: bool = Query(False)` (e.g. `interface.py:785, 1126, 1785, 2154, 2279, 2547, 3577, 4735`). The frontend client was only partly updated: `deleteSystem` and `deleteConnector` use `force`, but `deleteUnit`, `deleteBus`, `deleteMessage`, `deleteHarness`, `deleteWire`, and `deleteHarnessEndpoint` still send `confirm`. FastAPI silently ignores unknown query params, so the backend reads `force=False` regardless of what the user clicked, returns the 409 cascade-warning, and the user is stuck.
- **Impact:** Force-delete UI buttons silently fail for six entity types. Users see "the system has dependent entities" and have no way to override from the UI.
- **Recommendation:** Rename the param to `force` in all six lines.
- **Evidence:**
  ```typescript
  // frontend/src/lib/interface-api.ts:76-77
  deleteUnit: (id: number, confirm = false) =>
    api.delete(`${BASE}/units/${id}`, { params: { confirm } }),
  // backend wants `force`, not `confirm`
  ```

#### F-205 — `Requirement.project_id` foreign key has no `ondelete` strategy; ORM-side `cascade="all, delete-orphan"` only fires when the parent is deleted via SQLAlchemy
- **File:** `backend/app/models/__init__.py:181`
- **Lines:** 181 (`Requirement.project_id`), also 333 (`Baseline.project_id`)
- **Category:** Backend / Schema
- **Description:** F-076 swept the FK ondelete strategies on `Project.owner_id`, `SourceArtifact.project_id`, `Verification.requirement_id`, `RequirementHistory.requirement_id`, etc. The largest table — `requirements` — was missed. `Requirement.project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)` defaults to PG's `NO ACTION`. The relationship-side `Project.requirements = relationship(..., cascade="all, delete-orphan")` only fires on ORM-mediated delete; a SQL `DELETE FROM projects WHERE id=…` (or a future cascade-from-elsewhere) raises a constraint violation. `Baseline.project_id` has the same gap. Schema-drift cleanup did not catch this because the column didn't change between dev DB and the model — both are `NO ACTION`.
- **Impact:** Inconsistent cascade semantics between SQL-side and ORM-side. If a project is force-deleted via raw SQL (admin tooling, future hard-delete endpoint, audit-log retention sweep), all its requirements + baselines block the delete instead of cascading. Less critical day-to-day; matters for any future "delete project" feature.
- **Recommendation:** Migration to add `ondelete="CASCADE"` on `Requirement.project_id` and `Baseline.project_id`. Be cautious: cascading a project delete also wipes its hash-chained audit trail relationships — `AuditLog.project_id` was set to `SET NULL` in F-076 specifically to preserve the trail, so the project delete will leave orphan audit rows (correct per AU-9).
- **Evidence:**
  ```python
  # models/__init__.py:181
  project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
  # F-076 missed this — should be ForeignKey("projects.id", ondelete="CASCADE")
  ```

### MEDIUM

#### F-206 — `services/auth.py:get_current_user` swallows generic `Exception` in the revoked-tokens lookup, including HTTPException
- **File:** `backend/app/services/auth.py:61-71`
- **Category:** Backend / Security
- **Description:** The try/except at line 61-71 catches `(ImportError, Exception)`. The intent is to handle the table-missing case gracefully when the 0020 migration hasn't run; the code re-raises HTTPException via the `isinstance` check. But because `Exception` is the catch-all, every non-HTTPException path (including DB errors during the revocation lookup, OperationalError on connection drop, etc.) is silently swallowed. The function then falls through to the user query — meaning a transient DB error during the revocation check will let a revoked token authenticate.
- **Impact:** Race window: a revoked token can pass authentication if the DB is temporarily unreachable for the revocation lookup but recovers in time for the user lookup. Also masks legitimate SQL errors that should bubble up as 500.
- **Recommendation:** Catch only `ProgrammingError` / `OperationalError` (and perhaps `NoSuchTableError`); let everything else propagate. Log a WARNING on the swallowed case so operators see "revocation table missing" loudly.
- **Evidence:**
  ```python
  # services/auth.py:61-71
  if jti:
      try:
          from app.models.auth_models import RevokedToken
          if db.query(RevokedToken).filter(RevokedToken.jti == jti).first():
              raise credentials_exception
      except (ImportError, Exception) as exc:
          if isinstance(exc, HTTPException):
              raise
          # Otherwise the table is missing — log and fall through.
          # ↑ comment says "log and fall through" but no log emitted
  ```

#### F-207 — Backend `rbac.PERMISSION_MATRIX` includes `interfaces.create` / `interfaces.update` / `interfaces.delete` but frontend `auth.tsx:PERMISSION_MATRIX` does not — `<PermissionGate action="interfaces.create">` always returns false
- **File:** `frontend/src/lib/auth.tsx:30-79`
- **Category:** Cross-cutting / Enum Drift
- **Description:** Backend `services/rbac.py:23-92` grants `interfaces.create/update/delete` to ADMIN and PROJECT_MANAGER. The frontend mirror at `auth.tsx:30-79` lists no `interfaces.*` actions. Any UI guard like `<PermissionGate action="interfaces.create">` evaluates to false for everyone. Backend also grants `reports.export` to STAKEHOLDER and DEVELOPER (F-114 fix); frontend has empty permission sets for those two roles, so stakeholders/developers can't see the export button despite the backend permitting it.
- **Impact:** UI hides controls users are entitled to. Functional bug, not security — backend re-checks server-side.
- **Recommendation:** Sync the frontend matrix to the backend list. Add a comment on both sides: "If you change one, change the other."

#### F-208 — `audit.py:get_audit_log` accepts `project_id` query param without `_check_membership`
- **File:** `backend/app/routers/audit.py:43-72`
- **Category:** Backend / Security
- **Description:** `/audit/log` accepts `project_id` and filters by it but does not validate the caller's membership. Only `/audit/export` (line 192-237) gained the `_check_membership(db, project_id, current_user)` check in F-020. A PM with cross-project view sees /audit/export blocked but /audit/log open — inconsistent.
- **Impact:** Cross-project read of the paginated audit log when filtered by project_id. Pairs with F-201's `get_entity_audit_trail` gap to make the entire audit-read surface unscoped.
- **Recommendation:** Mirror the export gate: `if project_id is not None: _check_membership(db, project_id, current_user)`.

#### F-209 — `integrations.py:get_integration_catalog` advertises webhook URLs without the `{config_id}` path segment
- **File:** `backend/app/routers/integrations.py:593, 605`
- **Category:** Backend / API Contract Drift
- **Description:** F-017 moved Jira/Azure webhook routes from the hardcoded `/integrations/jira/webhook` to `/integrations/{config_id}/jira/webhook`. The catalog still publishes `webhook_url: "/api/v1/integrations/jira/webhook"` and `…/azure/webhook` — wrong by one path segment. Any frontend that displays the catalog value as the webhook URL gives users a 404 endpoint to configure at the upstream provider.
- **Impact:** Operators copy the catalog URL into Jira/Azure DevOps Service Hooks → events bounce back as 404s.
- **Recommendation:** Make webhook_url a template like `/api/v1/integrations/{config_id}/jira/webhook` and have the frontend interpolate, or compute it server-side per-config and return the resolved URL on the integration detail response.

#### F-210 — `seed_project.py:seed_project_data` requires `projects.create` but does NOT call `_check_membership`
- **File:** `backend/app/routers/seed_project.py:465-491`
- **Category:** Backend / Security
- **Description:** Sub-case of F-201 noted separately because the seeded payload is a 48-requirement firehose (3 baselines, 5 artifacts, ~30 trace links, 20 verifications). A non-member admin or PM can flood any project's data and audit trail.
- **Recommendation:** Add `_check_membership(db, project_id, current_user)` after the `Project not found` check at line 484.

#### F-211 — `confirm_import` re-validates project but does NOT call `_check_membership`; same pattern as F-201 but worth calling out for the import surface
- **File:** `backend/app/routers/imports.py:343-470`
- **Category:** Backend / Security
- **Description:** Sub-case of F-201, listed separately because the import surface is an attractive privilege-escalation target — a single call writes N requirements + N history rows + an audit row, all attributed to the caller's `current_user.id`. Should be membership-gated.

#### F-212 — `services/signature_service.py:get_signatures` issues N+1 user lookups
- **File:** `backend/app/services/signature_service.py:349-377`
- **Category:** Backend / Performance
- **Description:** Loops over each signature row and issues `db.query(User).filter(User.id == s.user_id).first()` per iteration. For an entity with N signatures (workflows can have many), this is N+1. Pattern matches F-042 / F-043 fixes elsewhere — same fix pattern (single LEFT JOIN).
- **Recommendation:** Replace with `db.query(ElectronicSignature, User).outerjoin(User, User.id == ElectronicSignature.user_id).filter(...)`.

#### F-213 — `_resolve_project_for_baseline_create` raises `NotImplementedError` and is never invoked; create_baseline relies on inline `_check_membership` instead
- **File:** `backend/app/routers/baselines.py:43-52`
- **Category:** Backend / Code Quality
- **Description:** Dead code with a misleading docstring: defines a resolver that always raises NotImplementedError, then `create_baseline` (line 55) does the membership check inline anyway. The function should be deleted; its presence suggests an incomplete refactor that future readers may try to "fix" by wiring it into `entity_project_member_required(_resolve_project_for_baseline_create)` — which would crash the endpoint.
- **Recommendation:** Delete `_resolve_project_for_baseline_create`. The inline `_check_membership` at line 66 is the working pattern.

#### F-214 — `audit.py:_audit_dep` permission gate accepts ADMIN or PROJECT_MANAGER for the global audit surface; per-entity trail at `/audit/log/entity/{type}/{id}` uses bare `get_current_user`
- **File:** `backend/app/routers/audit.py:30-34, 79-92`
- **Category:** Backend / Security
- **Description:** Two different auth gates on the same router. The paginated log (line 43) and verify (line 99) and export (line 192) all use `_audit_dep` (ADMIN/PM). The per-entity trail (line 79) uses bare `get_current_user`. This is a deliberate-looking choice (the docstring says "any authenticated user") but it conflicts with the membership-scoping the rest of the surface enforces. Combined with F-208's project_id gap, the audit surface has three different security postures across four endpoints.
- **Recommendation:** Either gate per-entity trail to ADMIN/PM as well, or resolve the entity → project_id and `_check_membership` it (preferred — engineers should be able to read their own project's audit trails).

#### F-215 — `/audit/log` and `/audit/log/entity/...` accept `limit` up to 500; platform standard documented as 200
- **File:** `backend/app/routers/audit.py:53, 84`
- **Category:** Backend / Performance
- **Description:** The original audit prompt notes the backend rate limit / pagination ceiling is 200; audit endpoints allow 500. Probably intentional for operations work but worth tracking.

#### F-216 — `dev.py:reset_and_seed` calls `Base.metadata.drop_all` without holding any lock; concurrent in-flight requests during a reset get `relation does not exist` errors
- **File:** `backend/app/routers/dev.py:256-261`
- **Category:** Backend / Reliability (subordinate to F-202)
- **Description:** Beyond F-202's auth gap, the implementation drops tables while other workers may be mid-query. Even within a single dev session, an open browser tab polling for stats during the reset will hit transient errors instead of a clean "service unavailable". Pair with F-202's auth gate.

### LOW

#### F-217 — Two backend `.bak` files committed; two frontend `.bak` files committed
- **File:** `backend/app/routers/interface.py.bak`, `backend/app/services/reports/change_history.py.bak`, `frontend/src/app/projects/[id]/requirements/[reqId]/page.tsx.bak`, `frontend/src/app/projects/[id]/verification/page.tsx.bak`
- **Category:** Code Quality
- **Description:** Stale snapshots left over from refactors. They are imported by nothing, but they're scanned by linters and search tools, and they bloat the build context. The frontend ones may also confuse Next.js's app-router (depends on whether the `.bak` extension excludes them from the route table — it does, but TS/ESLint will still load them).
- **Recommendation:** `git rm` all four. Add `*.bak` to `.gitignore`.

#### F-218 — `devAPI.seedProject` in frontend `lib/api.ts:193` calls `/dev/seed-project/${projectId}` which no longer exists (moved to `/admin/seed-project/${projectId}` per F-004)
- **File:** `frontend/src/lib/api.ts:191-194`
- **Category:** Cross-cutting / API Contract Drift
- **Description:** Documented in REMEDIATION_LOG line 14 as "Frontend callers will need a follow-up to use the new path — no frontend caller for this endpoint currently exists per the audit's orphan list." The `devAPI.seedProject` definition is the orphan — there's no UI button bound to it, but the export remains and would 404 if anyone wired it up.
- **Recommendation:** Update path to `/admin/seed-project/${projectId}`. Or delete `devAPI` block entirely if no UI consumes it.

#### F-219 — `PGADMIN_DEFAULT_EMAIL=admin@astra.local` in `.env.example` will trigger pgAdmin's restart loop on a fresh checkout
- **File:** `.env.example:25`
- **Category:** Infra / Documentation
- **Description:** Documented in REMEDIATION_LOG (one of the new-findings during remediation, "Low" severity, fix deferred). The `.local` TLD is RFC-6762 reserved and pgAdmin rejects it. Anyone copying `.env.example → .env` and running `docker compose up` will see pgadmin restart-loop.
- **Recommendation:** Change to `admin@example.com` in `.env.example` (and update `.env` too, per the rotation runbook).

#### F-220 — `auth_providers/saml.py:authenticate` accepts the IdP-provided `role` attribute verbatim and passes it to `find_or_create_user`
- **File:** `backend/app/services/auth_providers/saml.py:148-162`
- **Category:** Backend / Security (defense-in-depth)
- **Description:** SAML attribute "role" is a string from the IdP. If a misconfigured IdP exposes the attribute as user-controllable (e.g. self-service profile editing in some Azure AD setups), an unprivileged user could push `role=admin`. This is mostly the IdP's job to control, but the SP defaults to "developer" only when the attribute is absent — present-but-malicious flows through. Severity Low because (a) trusted IdPs typically lock role attributes, (b) the parallel OIDC code path likely has the same issue (would need separate review).
- **Recommendation:** Do not honour IdP-provided `role` for new-user provisioning. Always create as `developer`; require an admin to elevate via `/admin/users/{id}` (matching F-015's posture for `/auth/register`). Log a warning when the IdP attribute is present so operators can debug missing role mappings.

#### F-221 — `services/auth.py:revoke_access_token_jti` swallows all exceptions on duplicate insert without logging
- **File:** `backend/app/services/auth.py:79-92`
- **Category:** Backend / Code Quality
- **Description:** The except-Exception block treats every error as "already revoked — fine." That's correct for the UNIQUE-violation case but masks DB connectivity errors, integrity errors on the FK to `users.id` (if a user was deleted), etc. Add a `logger.warning` so the legitimately-swallowed cases are visible.

### INFO

#### F-222 — Docs `webhook_url` strings in catalog could be replaced with a templated client-side approach
- **File:** `backend/app/routers/integrations.py:593, 605`
- **Category:** Architecture
- **Description:** Repeats F-209 from a different angle — the catalog publishes a "webhook_url" the frontend will likely show in the integration setup UI. The right architecture is a per-config method that returns the fully-resolved URL after creation (since the path includes the config_id that doesn't exist at catalog-time).

## Cross-Cutting Concerns

### API Contract Drift
| Backend Route | Frontend Caller | Mismatch |
|---|---|---|
| `DELETE /interfaces/units/{pk}?force=true` | `interface-api.ts:76 deleteUnit(.., confirm)` | Frontend sends `confirm`; backend reads `force`. (F-204) |
| `DELETE /interfaces/buses/{pk}?force=true` | `interface-api.ts:139 deleteBus(.., confirm)` | Same as above. (F-204) |
| `DELETE /interfaces/messages/{pk}?force=true` | `interface-api.ts:167 deleteMessage(.., confirm)` | Same. (F-204) |
| `DELETE /interfaces/harnesses/{pk}?force=true` | `interface-api.ts:202 deleteHarness(.., confirm)` | Same. (F-204) |
| `DELETE /interfaces/wires/{pk}?force=true` | `interface-api.ts:239 deleteWire(.., confirm)` | Same. (F-204) |
| `DELETE /interfaces/endpoints/{pk}?force=true` | `interface-api.ts:403 deleteHarnessEndpoint(.., confirm)` | Same. (F-204) |
| `POST /admin/seed-project/{project_id}` (F-004 path) | `api.ts:193 devAPI.seedProject` posts `/dev/seed-project/{id}` | 404 / orphan caller. (F-218) |
| Catalog `webhook_url: /api/v1/integrations/jira/webhook` | Frontend integration setup UI uses catalog URL | Backend route requires `{config_id}` segment. (F-209) |
| `/auth/me` returns `MeResponse{role: str, full_name, ...}` | `frontend/src/lib/auth.tsx:120-128 AuthUser` | Includes `is_active` field; `MeResponse` does NOT — frontend's `is_active` will be undefined. Minor. |

### Enum Drift
| Backend Enum | Frontend Mirror | Mismatch |
|---|---|---|
| `services/rbac.py PERMISSION_MATRIX` (includes `interfaces.create/update/delete` for ADMIN+PM, `reports.export` for STAKEHOLDER+DEVELOPER) | `frontend/src/lib/auth.tsx:30-79 PERMISSION_MATRIX` | Frontend missing `interfaces.*` for ADMIN+PM; missing `reports.export` for STAKEHOLDER+DEVELOPER. (F-207) |

### Orphaned Endpoints / Calls
- Backend routes with no frontend caller (post-Phase-3C):
  - `POST /auth/refresh` — listed as deferred (frontend axios interceptor not wired). Documented.
  - `POST /auth/logout` — listed as deferred. Documented.
  - `POST /admin/users/{id}/deactivate` — frontend `adminAPI.deactivateUser` exists in `lib/api.ts:176`, but I found no UI page that calls it. **Status: Needs Manual Review** — likely consumed by a not-yet-built admin UI.
  - `POST /workflows/signatures/idp-step-up` — F-036 endpoint; no frontend caller (IdP integration is forward-looking).
  - All seven `/interfaces/{entity}/{id}/delete-impact` endpoints — frontend doesn't consume them yet (documented as deferred).
- Frontend calls with no backend route:
  - `devAPI.seedProject` → `/dev/seed-project/{id}` (404 — moved to `/admin/seed-project/{id}`). (F-218)

## TODO / FIXME / Risk-Marker Inventory
| File | Line | Marker | Context |
|---|---|---|---|
| `frontend/src/components/AutoGrowAmbiguityModal.tsx` | 113 | `XXX` | Comment string `latestXXX` (placeholder in a discussion of closure capture, not a real risk marker). |
| `backend/app/main.py` | 45 | `# noqa: F401` | Intentional — RBAC import-for-side-effect probe. |
| `backend/app/main.py` | 112 | `# noqa: F401,F403` | Intentional — `from app.models import *` for SQLAlchemy metadata population. |
| `backend/app/routers/baselines.py` | 65, 220 | `# noqa: WPS437` | Intentional — `_check_membership` is a private helper accessed for the inline body-project case. |
| `backend/app/services/auth_providers/__init__.py` | 78-81 | `# noqa: F401, E402` | Intentional — provider modules imported for `register_provider` decorator side-effects. |
| `backend/app/services/reports/jobs.py` | 151 | `# noqa: BLE001` | Intentional — broad except in a background job runner. |
| `backend/app/services/auth_manager.py` | 96 | comment about prior `# noqa` | Comment only; the `# noqa` is gone. |

No `TODO`, `FIXME`, `HACK`, `// @ts-ignore`, or `// @ts-expect-error` markers found in scope.

## Appendix A — File Inventory

| Area | Count |
|---|---:|
| Python (`backend/**/*.py`, excluding `__pycache__`) | 153 |
| TypeScript / TSX (`frontend/src/**/*.{ts,tsx}`, excluding node_modules / .next) | 59 |
| Alembic migrations (`backend/alembic/versions/*.py`) | 21 |
| Docker / compose YAML | 2 (`docker-compose.yml`, `docker-compose.prod.yml`) |
| Database SQL fixtures | 1 (`database/init.sql`) |
| pg_hba | 1 (`database/pg_hba.conf`) |
| .env.example | 1 |
| Total scannable files | ~208 |

### Backend module breakdown
- Routers: `admin`, `ai`, `ai_writer`, `audit`, `auth`, `baselines`, `dashboard`, `dev`, `impact`, `imports`, `integrations`, `interface`, `interface_import`, `projects`, `reports`, `requirements`, `seed_project`, `workflows` (18 routers + 4 sub-routers from `projects.py`).
- Models: 14 model files (incl. new in Phase 2/3: `report_job`, `step_up_token`, `id_sequence`).
- Services: `account_lockout`, `audit_service`, `auth`, `auth_manager`, `encryption`, `id_sequence`, `mfa`, `quality_checker`, `rbac`, `signature_service`, `workflow_engine`, plus subdirs `ai/`, `auth_providers/`, `integrations/`, `interface/`, `quality/`, `reports/`, `security/`.
- Migrations: `0001` → `0007` → `0007a` → `0008` → … → `0022` (linear chain, no forks observed).
- Middleware: `audit_middleware`, `body_size_limit`, `rate_limiter`, `security_headers` (all 4 mounted in `main.py`).

### Frontend module breakdown
- App routes: 23 page files under `frontend/src/app/projects/[id]/...` plus `login/`, `traceability/`, `projects/new/`. Two `.bak` files in the route tree (F-217).
- Components: 17 component files spread across `a11y/`, `ai/`, `impact/`, `layout/`, `traceability/` plus shared components.
- API clients: `api.ts`, `interface-api.ts`, `ai-api.ts`, `ai-writer-api.ts`, `impact-api.ts`.
- Types: `types.ts`, `interface-types.ts`.

## Appendix B — Audit Methodology

### What was scanned
- All Python files under `backend/app/` and `backend/alembic/versions/`.
- All TypeScript / TSX files under `frontend/src/`.
- `docker-compose.yml`, `docker-compose.prod.yml`, `.env.example`, `database/init.sql`, `database/pg_hba.conf`.
- `REMEDIATION_LOG.md` (read in full to filter out resolved findings).
- Original `AUDIT_FINDINGS.md` (referenced for finding-ID continuity).

### What was skipped
- `__pycache__/`, `node_modules/`, `.next/`, `.venv/`, `.git/`.
- Tests (`backend/tests/`) — out of scope per the operating rules.
- Generated files, lockfiles.
- The five deferred items (F-045, delete-impact UI, /auth/refresh interceptor, frontend test-infra, F-134) — surfaced via REMEDIATION_LOG and excluded from new findings per the prompt's instructions.

### Methodology
1. Read `CLAUDE_CODE_AUDIT_PROMPT.md` and `REMEDIATION_LOG.md` end-to-end.
2. Inventoried directory structure with `Glob` / `ls` to map current code locations against the documented post-remediation state.
3. Read every router file (18) end-to-end. Diffed each handler against the F-014 / F-074 fix patterns to find places where the remediation was incomplete.
4. Targeted Grep sweeps for known anti-patterns: `count + 1`, `# noqa`, `confirm.*Query` vs `force.*Query` drift, `_check_membership` coverage, `Float` columns, `TODO/FIXME`.
5. Cross-referenced every backend route signature against `frontend/src/lib/*-api.ts` to find frontend-backend drift.
6. Spot-checked services (`auth.py`, `auth_manager.py`, `signature_service.py`, `audit_service.py`, `workflow_engine.py`) for the remaining gaps in the F-063 / F-068 / F-008 mechanisms.
7. Read the new migrations (0007a, 0020, 0021, 0022) for transaction-boundary correctness.

### Limitations
- Did not run any code, tests, or migrations (read-only constraint).
- Did not start docker, did not connect to the running DB.
- Did not exhaustively read every interface.py handler (the file is 4,792 lines; focused on the new delete-impact + F-014 / F-142 / F-143 areas plus the auth-adjacent handlers).
- Did not re-verify the original audit's frontend a11y / type-safety findings — REMEDIATION_LOG marks them complete, so they're trusted.
- Workflow engine and auto-grow service code paths spot-checked rather than exhaustively reviewed.
- pgvector / embedding similarity code (F-045) intentionally skipped — deferred per remediation log.

AUDIT COMPLETE — 23 findings written to AUDIT_FINDINGS_POST_REMEDIATION.md
