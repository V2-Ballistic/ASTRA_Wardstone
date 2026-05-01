# ASTRA Backlog — Post-Remediation Findings

**Source:** `AUDIT_FINDINGS_POST_REMEDIATION.md` (committed to main on 2026-05-01 as `00b562a`)
**Status:** 23 unresolved as of 2026-05-01 (0 CRITICAL, 6 HIGH, 11 MEDIUM, 5 LOW, 1 INFO)
**Original audit baseline:** `AUDIT_FINDINGS.md` (121 findings; 116 fixed + 7 verified-closed + 5 deferred per `REMEDIATION_LOG.md`).

Next remediation cycle should address the 6 HIGH first; **F-201 is the highest priority** (it leaves a class of pre-existing F-014 cross-project leak paths open, and pairs with F-208 / F-210 / F-211 to make the audit / seed / import surfaces unscoped).

---

## HIGH severity (6) — schedule next cycle

### F-200 — `auth_manager.create_access_token` does not stamp `jti`
**File:** `backend/app/services/auth_manager.py:40-54` (also touches `refresh_access_token` line 113, `authenticate` line 210, `complete_mfa` line 236, partial-MFA line 204).
**Summary:** `services/auth.py:create_access_token` (line 36) correctly sets `jti = uuid.uuid4().hex` on every JWT. The parallel `auth_manager.create_access_token` does NOT. Tokens minted by SAML / OIDC / PIV / MFA / refresh-rotation paths all lack `jti`, and `get_current_user`'s revocation check is gated by `if jti:` — so any non-local-login token skips the F-063 revocation list entirely. Logout is a no-op for these tokens.
**Recommended fix:** Add `to_encode.setdefault("jti", uuid.uuid4().hex)` (and `import uuid`) to `auth_manager.create_access_token` before the `jwt.encode` call. One-line fix. Add a regression test that decodes a refresh-rotated token and asserts `payload["jti"]` is present.

### F-201 — `_check_membership` gaps in legacy routers (workflows / audit / seed / ai / ai_writer)
**Files:** `backend/app/routers/workflows.py` (lines 116-227, 240-315), `backend/app/routers/audit.py` (lines 43-72 `get_audit_log`, 79-92 `get_entity_audit_trail`), `backend/app/routers/imports.py` (lines 251-336 `preview_import`, 343-470 `confirm_import`), `backend/app/routers/ai.py` (lines 76-89 `get_project_duplicates`, 92-111 `check_duplicate`, 118-138 `get_trace_suggestions`, 277-331 `reindex_embeddings`, 379-435 `get_ai_stats`), `backend/app/routers/seed_project.py:465-491`, `backend/app/routers/ai_writer.py` (all 7 endpoints).
**Summary:** F-014 audit work (Phase 1) added `project_member_required` to enumerated routers but missed these. Verified by direct grep on 2026-05-01:
- `workflows.py`: 0 of ~14 project-scoped endpoints gated
- `audit.py`: 1 of 3 project_id endpoints gated (only `/audit/export`)
- `seed_project.py`: 0 of 1 gated (env guard only — see F-210)
- `ai.py`: 1 of 7+ gated (only `/trace-suggestions/by-project`)
- `ai_writer.py`: 0 of 7 gated
- `impact.py`: well-covered (5 inline calls — not in this gap)
A `PROJECT_MANAGER` can read/write workflows for projects they're not a member of; any authenticated user can read any project's audit trail via `/audit/log/entity/{type}/{id}`; any user with `requirements.create` can confirm-import into any project.
**Recommended fix:** Apply `Depends(project_member_required)` per endpoint, or `_check_membership(db, project_id, current_user)` inline. For entity-keyed routes (workflow_id / instance_id / signature_id), walk the row to its `project_id` first (analogous to `_assert_member_for_entity` in `interface.py`). Mirror the F-014 negative test pattern.

### F-202 — `dev` router has no authentication; `POST /dev/reset` drops all tables for any unauthenticated caller
**File:** `backend/app/routers/dev.py:146-261` (`seed_database` line 147, `reset_and_seed` line 257).
**Summary:** Neither endpoint includes `Depends(get_current_user)`. They rely entirely on the env-gate in `main.py:101` (`if not is_prod`). Any non-production environment (development / staging / qa / test) exposes `POST /api/v1/dev/reset` to drop all tables and re-seed. A port-scan or CSRF (no creds required, so SameSite doesn't help) wipes the database.
**Recommended fix:** Wrap both endpoints with `Depends(require_any_role(UserRole.ADMIN))` and require an `X-Dev-Reset-Confirm: I-mean-it` header on `/reset`. Emit `dev.reset` audit entry before the drop runs.

### F-203 — `requirements.py` create / clone / import paths use racy `count + 1` for req_id; surfaces as 500 with F-075's UNIQUE
**Files:** `backend/app/routers/requirements.py:314-318` (`create_requirement`), `:575-578` (`clone_requirement`), `backend/app/routers/imports.py:393-397` (`confirm_import`).
**Summary:** F-074 introduced `services.id_sequence.next_human_id` with `SELECT … FOR UPDATE`. It's wired into `interface.py` and `projects.py:create_artifact` but the requirement-creation paths were missed. With F-075's `uq_req_per_project (project_id, req_id)` constraint now active, two concurrent `POST /requirements/?project_id=X` calls of the same `req_type` both compute the same `count + 1` → same `req_id` → IntegrityError → 500. The original race (silent ID reuse) is fixed by the constraint, but the user-visible behaviour is now a 500 with no actionable detail. CSV bulk imports also have wrong count basis (in-flight rows in same transaction not visible).
**Recommended fix:** Replace `count + 1` + `generate_requirement_id` with `next_human_id(db, project_id, prefix=…, source_model=Requirement, id_field="req_id")` in all three call sites. The `imports.py` confirm path additionally needs to handle in-batch parent-resolution so children don't reuse sibling numbers.

### F-204 — Frontend `interface-api.ts` sends `confirm` query param on six DELETE endpoints; backend now expects `force` (F-047 contract change)
**File:** `frontend/src/lib/interface-api.ts:76-77, 139-140, 167-168, 202-203, 239-240, 403-404`.
**Summary:** Phase 3C F-047 standardised every interface DELETE on `force=true` to bypass the cascade-safety gate. `deleteSystem` and `deleteConnector` were updated; `deleteUnit`, `deleteBus`, `deleteMessage`, `deleteHarness`, `deleteWire`, `deleteHarnessEndpoint` still send `confirm`. FastAPI silently ignores unknown query params, so the backend reads `force=False` regardless of what the user clicked, returns 409, and the user is stuck.
**Recommended fix:** Rename the param to `force` in all six lines.

### F-205 — `Requirement.project_id` and `Baseline.project_id` foreign keys have no `ondelete` strategy
**File:** `backend/app/models/__init__.py:181` (Requirement), `:333` (Baseline).
**Summary:** F-076 swept ondelete strategies on most FKs but missed the largest tables. Both default to PG's `NO ACTION`. The relationship-side `Project.requirements = relationship(..., cascade="all, delete-orphan")` only fires on ORM-mediated delete; raw SQL `DELETE FROM projects WHERE id=…` (admin tooling, future hard-delete endpoint, retention sweep) raises a constraint violation.
**Recommended fix:** Migration adding `ondelete="CASCADE"` on both columns. Note: `AuditLog.project_id` was set to `SET NULL` in F-076 specifically to preserve the trail (AU-9), so cascading a project delete will leave orphan audit rows — that's correct.

---

## MEDIUM severity (11) — opportunistic

### F-206 — `services/auth.py:get_current_user` swallows generic `Exception` in revoked-tokens lookup
**File:** `backend/app/services/auth.py:61-71`.
**Summary:** `try: ... except (ImportError, Exception)` is too broad. A transient DB error during the revocation lookup silently lets a revoked token authenticate. Also masks legitimate SQL errors that should bubble as 500.
**Recommended fix:** Catch only `ProgrammingError` / `OperationalError` / `NoSuchTableError`. Log WARNING on the swallowed case.

### F-207 — Backend RBAC `interfaces.*` actions missing from frontend `auth.tsx:PERMISSION_MATRIX`
**File:** `frontend/src/lib/auth.tsx:30-79`.
**Summary:** Backend `services/rbac.py:23-92` grants `interfaces.create/update/delete` to ADMIN and PROJECT_MANAGER. Frontend mirror lists none. `<PermissionGate action="interfaces.create">` always returns false. Same applies to `reports.export` for STAKEHOLDER/DEVELOPER (granted backend-side per F-114; missing frontend-side).
**Recommended fix:** Sync the frontend matrix to the backend list. Add a comment on both sides: "If you change one, change the other."

### F-208 — `audit.py:get_audit_log` accepts `project_id` query without `_check_membership`
**File:** `backend/app/routers/audit.py:43-72`.
**Summary:** Sub-case of F-201. `/audit/log` filters by project_id but does not validate caller's membership. `/audit/export` (line 217) is gated; `/audit/log` is not. Inconsistent.
**Recommended fix:** Mirror the export gate — `if project_id is not None: _check_membership(db, project_id, current_user)`.

### F-209 — `integrations.py:get_integration_catalog` advertises webhook URLs missing the `{config_id}` segment
**File:** `backend/app/routers/integrations.py:593, 605`.
**Summary:** F-017 moved Jira/Azure webhooks to `/integrations/{config_id}/jira/webhook`. The catalog still publishes the pre-F-017 `/integrations/jira/webhook` (and `…/azure/webhook`). Operators copy the catalog URL into Jira/Azure DevOps Service Hooks → events bounce back as 404s.
**Recommended fix:** Make `webhook_url` a template like `/api/v1/integrations/{config_id}/jira/webhook`, have the frontend interpolate; OR compute server-side per-config and return resolved URL on detail response.

### F-210 — `seed_project.py:seed_project_data` requires `projects.create` but does NOT call `_check_membership`
**File:** `backend/app/routers/seed_project.py:465-491`.
**Summary:** Sub-case of F-201, called out separately because the seeded payload is a 48-requirement firehose (3 baselines, 5 artifacts, ~30 trace links, 20 verifications). A non-member admin or PM can flood any project's data and audit trail.
**Recommended fix:** Add `_check_membership(db, project_id, current_user)` after the "Project not found" check at line 484.

### F-211 — `confirm_import` re-validates project but does NOT call `_check_membership`
**File:** `backend/app/routers/imports.py:343-470`.
**Summary:** Sub-case of F-201. Import surface is an attractive privilege-escalation target — single call writes N requirements + N history rows + an audit row, all attributed to caller's `current_user.id`. Should be membership-gated.

### F-212 — `services/signature_service.py:get_signatures` issues N+1 user lookups
**File:** `backend/app/services/signature_service.py:349-377`.
**Summary:** Loops over each signature row issuing `db.query(User).filter(User.id == s.user_id).first()`. N+1 for entities with many signatures. Same fix pattern as F-042 / F-043.
**Recommended fix:** Single LEFT JOIN — `db.query(ElectronicSignature, User).outerjoin(User, User.id == ElectronicSignature.user_id).filter(...)`.

### F-213 — `_resolve_project_for_baseline_create` raises `NotImplementedError` and is never invoked
**File:** `backend/app/routers/baselines.py:43-52`.
**Summary:** Dead code with misleading docstring. `create_baseline` (line 55) does the membership check inline at line 66. Future readers may try to "fix" by wiring it into `entity_project_member_required(_resolve_project_for_baseline_create)` — which would crash the endpoint.
**Recommended fix:** Delete `_resolve_project_for_baseline_create`. Inline `_check_membership` is the working pattern.

### F-214 — `audit.py` per-entity trail uses bare `get_current_user` while sibling endpoints gate on ADMIN/PM
**File:** `backend/app/routers/audit.py:30-34, 79-92`.
**Summary:** Three different security postures across four endpoints in the same router: paginated log + verify + export use `_audit_dep` (ADMIN/PM); per-entity trail (line 79) uses bare `get_current_user`. Combined with F-208's project_id gap, the audit surface has no consistent posture.
**Recommended fix:** Either gate per-entity trail to ADMIN/PM, OR resolve entity → project_id and `_check_membership` it (preferred — engineers should read their own project's audit trails).

### F-215 — `/audit/log` and `/audit/log/entity/...` accept `limit` up to 500; platform standard is 200
**File:** `backend/app/routers/audit.py:53, 84`.
**Summary:** Probably intentional for ops work but worth tracking. Inconsistent with the 200 cap enforced everywhere else.
**Recommended fix:** Drop to 200, OR add a documented exception with audit-team approval.

### F-216 — `dev.py:reset_and_seed` calls `Base.metadata.drop_all` without holding any lock
**File:** `backend/app/routers/dev.py:256-261`.
**Summary:** Subordinate to F-202. Beyond F-202's auth gap, the implementation drops tables while other workers may be mid-query. Browser tabs polling for stats during reset hit transient `relation does not exist` errors instead of clean "service unavailable".
**Recommended fix:** Pair with F-202's auth gate. Add a brief table-lock or "service unavailable" middleware shim during the drop window.

---

## LOW (5)

### F-217 — Four `.bak` files committed in working tree
**Files:** `backend/app/routers/interface.py.bak`, `backend/app/services/reports/change_history.py.bak`, `frontend/src/app/projects/[id]/requirements/[reqId]/page.tsx.bak`, `frontend/src/app/projects/[id]/verification/page.tsx.bak`.
**Summary:** Stale snapshots from refactors. Imported by nothing, but scanned by linters/search tools, bloats build context.
**Recommended fix:** `git rm` all four. Add `*.bak` to `.gitignore`.

### F-218 — `devAPI.seedProject` calls `/dev/seed-project/${projectId}` which moved to `/admin/seed-project/...` per F-004
**File:** `frontend/src/lib/api.ts:191-194`.
**Summary:** Documented in REMEDIATION_LOG line 14 ("Frontend callers will need a follow-up — no frontend caller for this endpoint currently exists per the audit's orphan list"). The `devAPI.seedProject` definition is the orphan; export remains, would 404 if anyone wired it up.
**Recommended fix:** Update path to `/admin/seed-project/${projectId}`. Or delete `devAPI` block if no UI consumes it.

### F-219 — `PGADMIN_DEFAULT_EMAIL=admin@astra.local` in `.env.example` triggers pgAdmin restart loop
**File:** `.env.example:25`.
**Summary:** RFC-6762 reserves `.local` TLD; pgAdmin rejects it. Fresh checkouts that copy `.env.example → .env` and run `docker compose up` see pgadmin restart-loop.
**Recommended fix:** Change to `admin@example.com` in `.env.example` (and update `.env` per the rotation runbook).

### F-220 — `auth_providers/saml.py:authenticate` accepts IdP-provided `role` attribute verbatim
**File:** `backend/app/services/auth_providers/saml.py:148-162`.
**Summary:** SAML "role" attribute flows directly into `find_or_create_user`. If a misconfigured IdP exposes the attribute as user-controllable (some Azure AD self-service profile editing setups), an unprivileged user could push `role=admin`. Mostly the IdP's job, but the SP defaults to "developer" only when the attribute is absent — present-but-malicious flows through. Parallel OIDC code path likely has the same issue.
**Recommended fix:** Don't honour IdP-provided `role` for new-user provisioning. Always create as `developer`; require admin elevation via `/admin/users/{id}` (matching F-015's posture for `/auth/register`). Log a warning when IdP attribute is present.

### F-221 — `revoke_access_token_jti` swallows all exceptions on duplicate insert without logging
**File:** `backend/app/services/auth.py:79-92`.
**Summary:** `except Exception` masks the legitimate UNIQUE-violation case (correct) but also DB connectivity errors and FK integrity errors (e.g. user deleted). No log emitted.
**Recommended fix:** Add `logger.warning("revoke_access_token_jti rolled back: %s", exc)` so the legitimately-swallowed cases are visible.

---

## INFO (1)

### F-222 — Catalog `webhook_url` strings could be templated client-side
**File:** `backend/app/routers/integrations.py:593, 605`.
**Summary:** Repeats F-209 from a different angle — the "right" architecture is a per-config method that returns the fully-resolved URL after creation (since the path includes `config_id` that doesn't exist at catalog-time). Tracked separately as the architectural framing.

---

## Notes for the F-201 cleanup PR (next session)

The bulk of the value is in F-201. Suggested approach:
1. Branch `fix/post-remediation-membership` off `main`.
2. One commit per router being fixed (workflows, audit, seed, ai, ai_writer, imports). Keep the diffs small — each is a `Depends` change + a per-endpoint test.
3. Bundle F-208 + F-210 + F-211 with F-201 (all sub-cases of the same gap; same fix pattern).
4. F-200 is one line — could go in the same PR or its own (one-liner is uncontroversial).
5. F-202 is its own PR — auth-gating dev.py warrants discussion of the dev-only auth shape.
6. Save F-203, F-204, F-205, F-206, and the MEDIUM/LOW backlog for a separate sweep.

Conservative scope estimate for the F-200 + F-201 cluster + sub-cases: ~half a day of focused work + tests.
