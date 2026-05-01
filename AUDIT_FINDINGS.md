# ASTRA Audit Findings
**Date:** 2026-04-29
**Commit/branch:** `2b1e8f71dec3e7d642aee246c48560d73ddc15d2` (main)
**Files scanned:** 196 (Python: 105, TS/TSX: 55, SQL: 4, YAML/JSON/INI: 7, Dockerfiles: 2, scripts: 8, Markdown/env/other: 15)
**Total findings:** 121 (Critical 6 · High 32 · Medium 53 · Low 24 · Info 6)

## Executive Summary

- **Critical:** 6
- **High:** 32
- **Medium:** 53
- **Low:** 24
- **Info:** 6

ASTRA is structurally a solid systems-engineering platform with deep ICD modeling and a thoughtful tamper-evident audit design, but the codebase is currently sitting on **at least one fully broken subsystem** and **several authentication/authorization gaps** that a determined caller can exploit today. The headline failures: (1) the multi-stage workflow + electronic-signature subsystem is unreachable at runtime — the model file lives in `routers/`, the router file lives in `models/`, every consumer (`signature_service`, `workflow_engine`, `models/workflows`) imports `from app.models.workflow import …` (a module that does not exist), and `main.py` mounts `app.routers.workflows` (a module that also does not exist) — silently swallowed by `try/except ImportError`. The 21 CFR Part 11 e-signature flow advertised in `SECURITY.md` cannot fire. (2) `services/auth_manager.create_access_token` signs JWTs with the *SecretStr wrapper object* instead of `.get_secret_value()` — every token issued through the MFA / partial-token / refresh path is signed with a non-secret value, which is a complete forge-anyone's-token bypass on those code paths. (3) `services/encryption.py` and `services/mfa.py` both fall back to known literal strings when env vars are missing and `enforce_production_guards()` only checks `SECRET_KEY`, so a misconfigured prod box can transparently run with publicly-known encryption keys. (4) `audit/page.tsx` references an undefined identifier `params` in the `/audit/log` fetch — the audit log page is currently broken end-user-visible. (5) A binary `pg_dump` named `4_24_2026_SQL_ASTRA.sql` sits at the repo root and is not in `.gitignore`.

The three top risk areas are **(A) Workflow + e-signature compliance subsystem** (entire feature non-functional and not bound to record state), **(B) authn/authz layer** (auth_manager SecretStr bug, /auth/register accepts arbitrary `role`, no account lockout, /dev/seed-project loaded in core with no auth, no project-membership checks anywhere on read or mutate endpoints), and **(C) production-safety hygiene** (encryption fallback, audit triggers never installed, dev seeders + reset endpoint exposed when `ENVIRONMENT≠production`, ad-hoc `add_interface_enum_values.ps1` mutating schema outside Alembic, Dockerfiles running as root, dev pg dump committed).

**Recommended remediation order:** (1) Fix the workflow file-swap and the JWT SecretStr bug — these are import-time / sign-time defects with one-line fixes that unblock the e-signature compliance story. (2) Close the project-membership gap with a single shared dependency applied to every router that takes `project_id`. (3) Remove the binary SQL dump from the repo, add `.env.example` parity, install the audit-immutability triggers via Alembic. (4) Remove the dev seeder's hard-coded `password123` and the unauthenticated `/auth/register` role-passthrough. (5) Add streaming + size limits to file-upload and report endpoints. (6) Sweep Medium findings (N+1 queries, audit-before-commit pattern, cascade-delete races) in a focused interface-router refactor.

Frontend hygiene is broadly OK — most issues are perf cliffs (force-graph synchronous, fan-out N+1 against system endpoint) and a11y gaps (icon-only buttons, label/input association). The `interfaces/[unitId]` vs `interfaces/unit/[unitId]` route duplication and the duplicate `auth.ts`/`auth.tsx` modules are the remaining structural problems. Migration chain itself is structurally sound (single linear DAG `0001 → 0002 → 0005 → 0006 → 0007 → 4bd35db2ef64`); the missing 0003/0004 numeric labels are cosmetic only.

---

## Findings

### CRITICAL

#### F-001 — JWT signed with SecretStr wrapper, not the actual secret
- **File:** `backend/app/services/auth_manager.py`
- **Lines:** 54
- **Category:** Security / Backend
- **Description:** `jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)` passes the `SecretStr` *object*, not its value. python-jose coerces via `str()`, which on a Pydantic SecretStr yields `"**********"`. Every token issued through `auth_manager` (MFA-partial path, refresh path, provider-specific authenticate paths) is therefore signed with the literal mask string, not the configured key. Tokens issued by `services/auth.py:28` use `.get_secret_value()` correctly, so the two paths are mutually unverifiable, and any token issued through `auth_manager` has an effectively known signing key.
- **Impact:** Anyone can forge tokens that pass verification against any token issued through `auth_manager.create_access_token()`. Complete auth bypass for MFA / refresh / provider flows.
- **Recommendation:** Change to `settings.SECRET_KEY.get_secret_value()` exactly as `services/auth.py:28` does. Add a unit test that decodes a freshly-issued token with the intended key.
- **Evidence:**
  ```python
  return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)
  ```

#### F-002 — Workflow + e-signature subsystem broken at import time (file-swap + plural/singular naming)
- **File:** `backend/app/routers/workflow.py`, `backend/app/models/workflows.py`, `backend/app/services/signature_service.py`, `backend/app/services/workflow_engine.py`, `backend/app/main.py`
- **Lines:** `routers/workflow.py:1-199`; `models/workflows.py:1-410`; `signature_service.py:18`; `workflow_engine.py:22`; `main.py:37,69`
- **Category:** Backend / Domain (21 CFR Part 11 compliance)
- **Description:** The file at `routers/workflow.py` contains only SQLAlchemy MODEL definitions (5 tables: ApprovalWorkflow, WorkflowStage, WorkflowInstance, StageAction, ElectronicSignature) — no `APIRouter`, no endpoints. Its docstring even reads `File: backend/app/models/workflow.py`. Conversely, `models/workflows.py` (plural) contains the entire FastAPI APIRouter with all CRUD/approval/signature endpoints; its docstring reads `File: backend/app/routers/workflows.py`. The two files have been swapped. Three consumers (`signature_service.py:18`, `workflow_engine.py:22`, `models/workflows.py:37`) all `from app.models.workflow import …` — that module path does not exist (only `app.models.workflows` does). `main.py:37` tries `app.routers.workflows` (plural) — that path does not exist either (only `app.routers.workflow` does). Every failure is silenced by surrounding `try/except (ImportError, AttributeError): pass` blocks.
- **Impact:** Every workflow endpoint (POST `/workflows`, signature endpoints, approval action endpoints, `seed-default`, `check-timeouts`) is **unreachable**. `signature_service.request_signature` cannot be imported. `workflow_engine.start_workflow / perform_action / check_timeouts` cannot be imported. The 21 CFR Part 11 e-signature workflow advertised in `SECURITY.md` does not exist at runtime. Frontend approval flows have no backend.
- **Recommendation:** Move the model classes to `app/models/workflow.py`. Move the router to `app/routers/workflows.py` (matching `main.py`'s import). Update the three broken imports to the new paths. Replace the optional-router `try/except` in `main.py` with a logger.warning so the next mistake of this kind is loud.
- **Evidence:**
  ```python
  # routers/workflow.py:1-12  (this is actually a MODEL file)
  """
  ASTRA — Multi-Stage Approval Workflow Models
  File: backend/app/models/workflow.py   ← NEW
  ...
  """
  class ApprovalWorkflow(Base):
      __tablename__ = "approval_workflows"
  ```
  ```python
  # services/signature_service.py:18 — broken import
  from app.models.workflow import ElectronicSignature, SignatureMeaning
  # main.py:37 — broken router mount (silenced)
  ("app.routers.workflows", "router"),
  ```

#### F-003 — Field-encryption + MFA-secret encryption silently fall back to known literal keys
- **File:** `backend/app/services/encryption.py`, `backend/app/services/mfa.py`, `backend/app/config.py`
- **Lines:** `encryption.py:42-47`; `mfa.py:22-24`; `config.py:99-123`
- **Category:** Security
- **Description:** `_get_fernet()` reads `ENCRYPTION_KEY` and falls back to `SECRET_KEY` and finally to the hard-coded `"dev-fallback-encryption-key"` if both are unset. `services/mfa.py` does the same with `_raw_key = os.getenv("SECRET_KEY", "test-secret-key-not-for-production")` — and uses raw byte truncate-and-pad (`raw_key.encode()[:32].ljust(32, b"\0")`) instead of PBKDF2, so MFA TOTP secrets and field-level encrypted PII are protected by inconsistent key derivations. `enforce_production_guards()` checks only `SECRET_KEY` — `ENCRYPTION_KEY` default is `SecretStr("")` and is never enforced. Additionally, `decrypt_field` swallows `InvalidToken` and returns ciphertext as-is (line 69-72), so any wrong-key situation is masked.
- **Impact:** A misconfigured production deploy (no `ENCRYPTION_KEY`, dev `SECRET_KEY`) will transparently encrypt PII and MFA secrets with publicly known strings. The decrypt-fallback hides the misconfiguration. Any leak of `SECRET_KEY` (which is also the JWT signing key) immediately compromises every TOTP secret and every encrypted column. NIST SC-12 / SC-28 / IA-5 violation.
- **Recommendation:** (1) Add `ENCRYPTION_KEY` to `enforce_production_guards()` and refuse to start in prod with an empty value. (2) Use `services.encryption._derive_key()` (PBKDF2-SHA256, 480k iterations) inside `mfa.py` instead of byte truncation. (3) Replace the `InvalidToken: return ciphertext` branch with a logged warning behind an explicit `ALLOW_PLAINTEXT_LEGACY=true` flag. (4) Salt: `_SALT = b"astra-field-encryption-v1"` is static — derive per-installation salt from `ENCRYPTION_KEY_SALT` env var.
- **Evidence:**
  ```python
  # services/encryption.py:42-47
  def _get_fernet() -> Fernet:
      raw = os.getenv("ENCRYPTION_KEY", "")
      if not raw:
          raw = os.getenv("SECRET_KEY", "dev-fallback-encryption-key")
      return Fernet(_derive_key(raw))
  ```
  ```python
  # services/mfa.py:22-24
  _raw_key = os.getenv("SECRET_KEY", "test-secret-key-not-for-production")
  _fernet_key = base64.urlsafe_b64encode(_raw_key.encode()[:32].ljust(32, b"\0"))
  _fernet = Fernet(_fernet_key)
  ```

#### F-004 — `/dev/seed-project/{id}` is loaded in CORE routers with NO auth, NO env gate, can pollute any project
- **File:** `backend/app/routers/seed_project.py`, `backend/app/main.py`
- **Lines:** `seed_project.py:35,446`; `main.py:30,164`
- **Category:** Security
- **Description:** `seed_project_router` is added to the `/dev` prefix and is registered as a **core** router in `main.py:30,164` — *not* gated by `is_prod` like the regular `dev_router` (which is properly behind `if not is_prod` at `main.py:55-60`). The `POST /dev/seed-project/{project_id}` endpoint has no `Depends(get_current_user)`, no role check, and no environment gate. Idempotency check (`existing_count >= 20`) fires only when the target project already has ≥20 requirements, so any project with fewer requirements (including a brand-new real project) gets 48 fake "Satellite Missile Deployment System" requirements + 30 trace links + verifications + baselines silently appended.
- **Impact:** Any unauthenticated network caller can corrupt production project data. Idempotency does not protect a real partially-populated project from being seeded.
- **Recommendation:** Wrap with `current_user: User = Depends(require_permission("projects.create"))`, gate behind `is_prod` like `dev_router`, and use a proper "is-seed" marker (e.g., a project config flag) instead of count threshold.
- **Evidence:**
  ```python
  # main.py:30,164 — core router (always loaded)
  from app.routers.seed_project import router as seed_project_router
  ...
  app.include_router(seed_project_router, prefix=API_PREFIX)
  # seed_project.py:446 — no Depends
  @router.post("/seed-project/{project_id}")
  def seed_project_data(project_id: int, db: Session = Depends(get_db)):
  ```

#### F-005 — Audit log page is broken: undefined `params` variable passed to axios
- **File:** `frontend/src/app/projects/[id]/audit/page.tsx`
- **Lines:** 46-49
- **Category:** Frontend / API-Integration
- **Description:** A local query-params object is built into `const p: any = …` (line 46-48) but the axios call uses `{ params }` (an undefined identifier, not `p`). At runtime axios receives `undefined` and skips params entirely — the request hits `/audit/log` with NO `project_id`, NO `skip/limit`, and NO filters.
- **Impact:** The audit log page does not work for the user. Filters do nothing, pagination does nothing, project scoping is lost. Likely explains "audit log appears empty" reports.
- **Recommendation:** One-line fix on line 49: change `{ params }` to `{ params: p }`.
- **Evidence:**
  ```tsx
  const p: any = { skip: page * limit, limit, project_id: projectId };
  if (entityType) p.entity_type = entityType;
  if (eventType)  p.event_type  = eventType;
  const res = await api.get('/audit/log', { params });   // ← `params` is undefined
  ```

#### F-006 — Binary `pg_dump` of an `astra` database checked into repo root
- **File:** `4_24_2026_SQL_ASTRA.sql`
- **Lines:** entire file (~70 KB)
- **Category:** Security / Cross-cutting
- **Description:** The file is NOT a SQL script — it is a binary `pg_dump` custom-format dump (header `PGDMP\1\20…`, format v1.16-0, source database `astra`, server version 16.13). It contains COPY blocks for tables including `account_lockouts`, `ai_analysis_cache`, `ai_feedback`, `ai_suggestions`, etc. — meaning it likely contains real user data, hashed passwords, and audit records. `.gitignore` does not exclude this pattern, so future dumps can also be committed.
- **Impact:** Potential data leak (depends on the source environment). Credential rotation may be required if the dump came from any non-trivial environment. Repo bloat. Future leakage from re-runs of `pg_dump` at the repo root.
- **Recommendation:** (1) `git ls-files | grep 4_24` to confirm whether it's tracked. (2) `pg_restore -l 4_24_2026_SQL_ASTRA.sql` to inspect contents. (3) If it has real data: rotate any credentials it touches; rewrite git history with `git filter-repo --path 4_24_2026_SQL_ASTRA.sql --invert-paths`; force-push with team approval. (4) Add `*.sql.dump`, `*.pgdump`, `[0-9]*_SQL_*.sql` to `.gitignore`.
- **Evidence:**
  ```
  $ file 4_24_2026_SQL_ASTRA.sql
  → PostgreSQL custom database dump - v1.16-0
  Binary header: PGDMP\1\20...astra\016.13...
  ```

---

### HIGH

#### F-007 — Workflow models' `SQLEnum` declarations missing `values_callable` (PostgreSQL upper/lower-case mismatch)
- **File:** `backend/app/routers/workflow.py`
- **Lines:** 71, 123, 175
- **Category:** Schema / Migration
- **Description:** `ApprovalWorkflow.status`, `WorkflowInstance.status`, and `ElectronicSignature.signature_meaning` use `Column(SQLEnum(EnumType), …)` without `values_callable=lambda x: [e.value for e in x]`. With the `str, enum.Enum` pattern used throughout this file, the Postgres enum type is created using member NAMES (uppercase: `ACTIVE`, `PENDING`, `APPROVED`) but Python comparisons throughout the codebase use `.value` (lowercase). The result is `InvalidTextRepresentation` errors (or silent no-result filters) when these fields are queried or updated. Same anti-pattern that the rest of `models/__init__.py` and `models/interface.py` correctly avoid.
- **Impact:** Once the workflow router is unbroken (F-002), inserts/updates to these three enum columns will fail; status filters return empty.
- **Recommendation:** Add `values_callable=lambda x: [e.value for e in x]` to all three column declarations. Also write a migration that ALTERs the existing Postgres enum types to lowercase if any data already exists.
- **Evidence:**
  ```python
  status = Column(SQLEnum(WorkflowStatus), default=WorkflowStatus.ACTIVE)               # line 71
  status = Column(SQLEnum(InstanceStatus), default=InstanceStatus.PENDING)              # line 123
  signature_meaning = Column(SQLEnum(SignatureMeaning), nullable=False,)                # line 175
  ```

#### F-008 — Electronic signature hash does not bind the signed record's content (21 CFR Part 11 §11.70)
- **File:** `backend/app/routers/workflow.py`, `backend/app/services/signature_service.py`
- **Lines:** `routers/workflow.py:193-199`; `signature_service.py:55-72,100-106`
- **Category:** Domain (compliance)
- **Description:** `ElectronicSignature.compute_hash` digests only `user_id | entity_type | entity_id | meaning | timestamp_iso`. The signed record's content (statement, version, requirement hash) is NOT in the hash. After a requirement is signed, an editor can rewrite the statement and the signature still verifies. 21 CFR Part 11 §11.70 requires e-sigs to be linked to their respective electronic records so they cannot be excised, copied, or transferred.
- **Impact:** FDA-regulated deployments cannot meet §11.70. Signatures can stay "valid" while the underlying record changes silently. Audit-of-record-state has no cryptographic anchor.
- **Recommendation:** Add a `record_hash` column to `ElectronicSignature` populated at sign time from a canonical serialization of the signed entity (e.g., `sha256(req.req_id + req.version + req.statement + req.title)`). Include `record_hash` in `compute_hash`. On `verify_signature`, recompute the entity's current hash and fail the verification if changed.
- **Evidence:**
  ```python
  payload = f"{user_id}|{entity_type}|{entity_id}|{meaning}|{timestamp_iso}"
  return hashlib.sha256(payload.encode("utf-8")).hexdigest()
  ```

#### F-009 — `audit_append_only.sql` triggers are never auto-applied; audit immutability is opt-in by hand
- **File:** `database/migrations/audit_append_only.sql`, `docker-compose.yml`, `backend/alembic/versions/*`
- **Lines:** entire SQL file; not referenced anywhere in compose or migrations
- **Category:** Security (NIST AU-9)
- **Description:** The file defines BEFORE UPDATE/DELETE/TRUNCATE triggers on `audit_log` that raise exceptions to physically prevent tampering. However, this file is NOT mounted by `docker-compose`, NOT included via `init.sql`, NOT referenced in any Alembic migration, and not auto-installed by the backend at startup. `SECURITY.md:214` puts "Run audit_append_only.sql on the database" in a manual operator checklist — meaning in practice the trigger does not get installed in default deployments.
- **Impact:** The "tamper-evident audit log" advertised in `SECURITY.md` is in name only on default installs. Anyone with DB credentials (and the dev `astra_dev_password_change_me` is in `.env` plus the public 5432 port — see F-021) can silently `UPDATE` or `DELETE` audit rows. NIST AU-9 control is broken-by-default.
- **Recommendation:** Add an Alembic migration that runs the trigger DDL via `op.execute()`. Migration must run AFTER `audit_log` exists (i.e., after `0001`). Stamp the install in `alembic_version` so re-deploys always have it.
- **Evidence:**
  ```sql
  -- file is correct and complete; only the install path is missing.
  CREATE TRIGGER prevent_audit_update BEFORE UPDATE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_log_block_update();
  ```

#### F-010 — `.env.example` missing 18+ environment variables that the code reads (incl. `ENCRYPTION_KEY`)
- **File:** `.env.example` vs `backend/app/services/{encryption,mfa,account_lockout,auth_manager}.py`, `backend/app/services/auth_providers/{oidc,saml,piv}.py`, `backend/app/middleware/rate_limiter.py`, `backend/app/config.py`
- **Lines:** `.env.example:1-43`; example callers `encryption.py:43`, `account_lockout.py:26-27`, `oidc.py:25-28`, `saml.py:27-31`, `piv.py:117`
- **Category:** Cross-cutting / Security
- **Description:** Code calls `os.getenv(...)` for at least 18 variables not in `.env.example`: `ENCRYPTION_KEY`, `MAX_LOGIN_ATTEMPTS`, `LOCKOUT_DURATION_MINUTES`, `RATE_LIMIT_DEFAULT/AUTH/IMPORT`, `ALLOWED_HOSTS`, `SESSION_TIMEOUT_MINUTES`, `AUTH_PROVIDER`, `AUTH_MFA_REQUIRED`, OIDC_*, SAML_*, `PIV_CA_BUNDLE_PATH`. Most have insecure fallbacks (e.g., `ENCRYPTION_KEY` falls back to `SECRET_KEY` then to `"dev-fallback-encryption-key"`).
- **Impact:** New deployments are silently misconfigured with insecure defaults. Combined with F-003, encryption keys silently degrade to known constants.
- **Recommendation:** Add every missing variable to `.env.example` with empty values + one-line per-group comments. Add a security section listing the keys that gate `enforce_production_guards()` so the operator knows which are mandatory in prod.

#### F-011 — Backend Dockerfile runs as root; no pinned base image, no HEALTHCHECK on backend in dev compose
- **File:** `backend/Dockerfile`, `docker-compose.yml`, `docker-compose.prod.yml`
- **Lines:** `backend/Dockerfile:1-17`; `docker-compose.prod.yml:120,149`
- **Category:** Security / Reliability
- **Description:** Image is `python:3.12-slim` (no SHA, no minor pin). No `USER` directive, so the container runs as UID 0. Production compose declares `user: "1000:1000"` for backend and frontend, but the Dockerfile does not create that user and `/app/uploads` is created while running as root — UID 1000 cannot write to it at runtime. No HEALTHCHECK in dev compose for backend; only db has a healthcheck.
- **Impact:** Container escape gives root. Production uploads silently fail with PermissionError because the runtime UID does not own `/app/uploads`. Base-image drift between environments.
- **Recommendation:** Pin `FROM python:3.12.7-slim-bookworm@sha256:<digest>`. Add `RUN useradd --uid 1000 -m astra && chown -R astra /app && USER astra`. Add `HEALTHCHECK CMD curl -fsS http://localhost:8000/health || exit 1`. Same hardening for `frontend/Dockerfile` (also runs as root, also unpinned, also `npm run dev` as default).

#### F-012 — Frontend Dockerfile defaults to `npm run dev` as root, no multi-stage build, no HEALTHCHECK
- **File:** `frontend/Dockerfile`
- **Lines:** 1-11
- **Category:** Security / Reliability
- **Description:** Default CMD is `npm run dev`. Production compose overrides to `npm start`, but the same image is reused. No multi-stage build, so source + node_modules + dev deps ship in the runtime image. No `USER` directive (root). `npm install --legacy-peer-deps` masks dependency-resolution bugs.
- **Impact:** ~500MB image, root container, dependency surprises in prod, potential HMR endpoints reachable in production.
- **Recommendation:** Convert to multi-stage `deps → build → run` with `USER 1000:1000` and `CMD ["npm","start"]` in the run stage.

#### F-013 — `add_interface_enum_values.ps1` mutates production schema with ~50 `ALTER TYPE … ADD VALUE` outside Alembic
- **File:** `add_interface_enum_values.ps1`
- **Lines:** 22-103
- **Category:** Migration
- **Description:** Script runs ~50 `ALTER TYPE … ADD VALUE IF NOT EXISTS` statements via `docker exec astra-db-1 psql` against `connectortype`, `signaltype`, `pindirection`. None are captured in any Alembic migration — schema state drifts between environments that did vs did not run the script. DR rebuild from `alembic upgrade head` produces a different schema. Container name `astra-db-1` is hardcoded so the script breaks if the compose project name differs.
- **Impact:** Schema drift; prod DB doesn't match any migration in version control; `alembic check` will flag drift; `alembic autogenerate` will try to re-add the values.
- **Recommendation:** Convert to a numbered Alembic migration (e.g., `0008_extend_interface_enums.py`). Wrap each `ALTER TYPE ADD VALUE` in `with op.get_context().autocommit_block():` because Postgres forbids `ALTER TYPE ADD VALUE` inside a transaction.

#### F-014 — Backend doesn't enforce project membership on ANY endpoint that takes `project_id`
- **File:** Pervasive — `backend/app/routers/projects.py`, `requirements.py`, `baselines.py`, `interface.py`, `integrations.py`, `dashboard.py`, `impact.py`, `reports.py`
- **Lines:** `projects.py:51-65,84-106,151-229,367`; `requirements.py:117,140,303,440,464,482,553,574,604`; `baselines.py:99,120,149,193`; `interface.py:142-202,267,306-575,658-1019,1358-1505,1689-1889,2035-2205,2838-3016,3398-3447`; `integrations.py:142-218`; `dashboard.py:15`; `impact.py:62,209`; `reports.py:75-194,201-215`
- **Category:** Security / Domain
- **Description:** Every router accepts `project_id` as a path/query/body parameter without asserting `current_user` is the owner or a `ProjectMember`. `list_projects` returns *every* project to *any* authenticated user. `list_baselines`, `get_baseline`, `compare_baselines`, `list_artifacts`, `list_trace_links`, `get_dashboard_stats`, `get_project_risk`, `list_integrations`, every interface CRUD, and the entire reports surface either rely on a generic role check or on no check at all. `ProjectMember` exists but is referenced only by `admin.py` and `dev.py` (member management endpoints). The `_require_project()` helper in `interface.py:113-121` only checks the project exists.
- **Impact:** Cross-project information disclosure and write access. A user with `requirements.update` in project A can edit/delete requirements in project B. A PM can read/write integration credentials (Jira tokens, DOORS passwords) for projects they don't belong to. Any logged-in user can list and read all projects in the tenant.
- **Recommendation:** Centralize a `project_member_required(project_id)` FastAPI dependency that loads `Project`, asserts `current_user.id == owner_id OR exists(ProjectMember(project_id, user_id, current_user.id)) OR current_user.role == ADMIN`. Apply to every router function that takes `project_id` (path, query, or body). For functions that take an entity ID (e.g., `req_id`, `baseline_id`, `harness_id`), load the entity, then call the same helper with `entity.project_id`.

#### F-015 — `/auth/register` accepts arbitrary `role` from request body and is unauthenticated
- **File:** `backend/app/routers/auth.py`
- **Lines:** 33-52
- **Category:** Security
- **Description:** Public registration accepts arbitrary `role` from `UserCreate`. Any unauthenticated `POST /auth/register` can create an account with `role="admin"`. No invitation token, no email verification, no role restriction.
- **Impact:** Trivial privilege escalation — register as admin, then access every privileged endpoint.
- **Recommendation:** Either (a) remove `/register` entirely (registration via `/admin/users` only), or (b) ignore `role` from request body and force `UserRole.DEVELOPER` server-side. Add an admin-invitation flow for elevated roles.

#### F-016 — Login has no account lockout despite `MAX_LOGIN_ATTEMPTS` / `LOCKOUT_DURATION_MINUTES` config
- **File:** `backend/app/routers/auth.py`, `backend/app/config.py`
- **Lines:** `auth.py:59-89`; `config.py:53-55`
- **Category:** Security (NIST AC-7)
- **Description:** Router docstring says "Lockout Disabled for Dev". `login` does not increment a failed-attempt counter or check a lockout window. `config.py` defines `MAX_LOGIN_ATTEMPTS=5` and `LOCKOUT_DURATION_MINUTES=30` but they are unused. `services/account_lockout.py` exists but is never wired into the login path.
- **Impact:** Unlimited password guessing per account, mitigated only by the per-IP rate limit (10/min/IP on `/auth/`). A distributed credential-stuffing attack is unbounded.
- **Recommendation:** Add `failed_attempts` and `locked_until` columns to `User` (or use `services/account_lockout.py`); enforce on each login attempt; emit `auth.login_locked` audit event. Also emit `auth.login_failed` audit event in the failure branch (currently no audit on failure — F-031).

#### F-017 — Webhook receivers `/integrations/jira/webhook` and `/azure/webhook` accept any JSON, no auth, no signature verification
- **File:** `backend/app/routers/integrations.py`
- **Lines:** 359-381
- **Category:** Security
- **Description:** Both webhook endpoints have no `Depends(get_current_user)`, no Jira `x-atlassian-webhook-identifier` / signature check, no Azure HMAC verification, and no source-IP allowlist. Both accept arbitrary JSON, instantiate a connector with empty config, dispatch `receive_webhook(payload)`, and write a `SyncLog` row with `integration_config_id=0`.
- **Impact:** Any network caller can POST malicious payloads that mutate state or fill the `SyncLog` table. Constraint: only the per-IP rate limit (default bucket, 100/min). Information disclosure via `SyncLog` rows.
- **Recommendation:** Validate Jira/Azure signatures or shared-secret tokens. Resolve `integration_config_id` from a path parameter or a unique URL slug instead of hardcoding 0. Add `is_webhook_authentic` check before any DB writes.

#### F-018 — File-upload endpoints read entire file into memory with no size limit, no MIME validation, no zip-bomb defense
- **File:** `backend/app/routers/imports.py`, `backend/app/routers/interface_import.py`
- **Lines:** `imports.py:246-276`; `interface_import.py:589-606,786-802`
- **Category:** Reliability / Security
- **Description:** `await file.read()` is called with no max-size guard. Extension is derived from `filename.rsplit(".", 1)[-1].lower()` — trivial to spoof. The XLSX parser uses `openpyxl.load_workbook` on user-supplied bytes — XML zip-bomb or formula-injection (`=cmd|...`) is unmitigated. Filename is also echoed in response without sanitization.
- **Impact:** Memory-exhaustion DoS — a single attacker uploads a multi-GB file and OOMs the worker. XLSX zip bombs can amplify resource consumption. Formula injection if the rows are re-exported.
- **Recommendation:** Enforce a body-size limit at middleware level (e.g., 25-50 MB). Validate `Content-Type` and content-sniff with `python-magic`. Use `load_workbook(read_only=True)` (already done) plus row/sheet count caps. Strip cells starting with `=`/`+`/`-`/`@` before re-exporting. Sanitize filename for any output.

#### F-019 — Report generation endpoints synchronous; large projects time out the worker
- **File:** `backend/app/routers/reports.py`, `backend/app/routers/interface_import.py`
- **Lines:** `reports.py:75-194`; `interface_import.py:1127-1273,1280-1394,1401-1506,1513-1695`
- **Category:** Reliability
- **Description:** Six report endpoints (`traceability-matrix`, `requirements-spec`, `quality`, `compliance`, `status-dashboard`, `change-history`, `icd`) call `gen.generate(project_id, db, …)` inline. `interface_import` exports (`/io/export/units`, `harness/{id}`, `all-wiring`, `icd-data`) iterate units→connectors→pins with `db.query().first()` per row — thousands of round trips for a 100-unit project, full xlsx materialized in memory.
- **Impact:** Multi-second to multi-minute responses; load balancer timeouts; worker pool saturation under concurrency.
- **Recommendation:** For `format=pdf|docx` or large projects, kick off a `BackgroundTask`, persist result to disk/object store, return `job_id`; add `GET /reports/jobs/{id}` for poll/download. Use openpyxl's `write_only=True` mode for streaming xlsx generation. Pre-fetch via joinedload/selectinload to eliminate per-row queries.

#### F-020 — Audit log export loads ALL rows into memory before serialization
- **File:** `backend/app/routers/audit.py`
- **Lines:** 120-171
- **Category:** Reliability
- **Description:** `db.query(AuditLog)…all()` materializes every audit row. CSV is built in memory; JSON returns a single dict. No streaming, no pagination.
- **Impact:** A real audit log easily reaches 100k+ rows; the export OOMs the worker and times out the request. The compliance "export everything" use case is broken at scale.
- **Recommendation:** Stream rows from a server-side cursor; for CSV emit a generator-backed `StreamingResponse`; for JSON switch to NDJSON one-record-per-line streaming.

#### F-021 — `.env` ships with placeholder `ENCRYPTION_KEY=<openssl rand -hex 32>` (literal angle brackets) and dev `POSTGRES_PASSWORD`
- **File:** `.env`, `docker-compose.yml`
- **Lines:** `.env:8-10,17,28`; `docker-compose.yml:21-22`
- **Category:** Security
- **Description:** `.env` (correctly in `.gitignore` — verify with `git ls-files .env`) contains `POSTGRES_PASSWORD=astra_dev_password_change_me`, `DATABASE_URL` with the password embedded, `SECRET_KEY=replace-with-64-char-random-string-openssl-rand-hex-32` (which `config.py:25` correctly flags as a known weak secret), `PGADMIN_DEFAULT_PASSWORD=pgadmin_change_me`, and `ENCRYPTION_KEY=<openssl rand -hex 32>` — that's a literal placeholder with angle brackets, not a value, so encryption silently falls back to `SECRET_KEY` (and onward — see F-003). Postgres is exposed on `5432:5432` (host-wide, not localhost-bound), so anyone reachable on the host can connect with these credentials.
- **Impact:** Any leak of the `.env` (laptop loss, screen-share, accidental commit) yields full DB and JWT compromise. Combined with F-003, encryption is also compromised. Combined with the exposed 5432 port, network-adjacent compromise is sufficient.
- **Recommendation:** Bind Postgres to `127.0.0.1:5432:5432` in dev compose. Replace `.env` placeholders with real generated secrets even in dev (a commit hook can require non-placeholder values). Move shared dev secrets out of plain-text `.env` to `direnv`/`pass`/`sops`.

#### F-022 — `0001` and `0007` migration `downgrade()` blocks wipe the entire schema with no production guard
- **File:** `backend/alembic/versions/0001_initial_schema.py`, `backend/alembic/versions/0007_interface_module.py`
- **Lines:** `0001_initial_schema.py:404-435`; `0007_interface_module.py:958-992`
- **Category:** Migration
- **Description:** `0001` downgrade drops 21 core tables and 12 enum types. `0007` downgrade drops 15 ICD tables and 38 enum types. A single accidental `alembic downgrade base` (CI rollback test pointed at prod, manual mistake) wipes all data.
- **Impact:** Catastrophic data loss on accidental invocation.
- **Recommendation:** At the top of each `downgrade()` add `if os.getenv("ENVIRONMENT") == "production" and not os.getenv("ASTRA_ALLOW_DESTRUCTIVE_DOWNGRADE"): raise NotImplementedError("Refusing destructive downgrade in production")`.

#### F-023 — `routers/workflow.py.bak`, `frontend/.../verification/page.tsx.bak`, `frontend/.../requirements/[reqId]/page.tsx.bak`, `services/reports/change_history.py.bak`, `routers/interface.py.bak` left in source tree
- **File:** Five `.bak` files
- **Lines:** N/A (entire files)
- **Category:** Cross-cutting
- **Description:** Five stale `.bak` backup files exist alongside their live counterparts. They are not loaded by Python or Next.js at runtime, but they bloat the repo, confuse code review, and cause `grep`/Glob to match dead code.
- **Impact:** Code review noise; risk of grep-and-replace touching the wrong file; future drift.
- **Recommendation:** Delete all `*.bak` files. Add `*.bak` to `.gitignore`.
- **Evidence:**
  ```
  backend/app/routers/interface.py.bak             (~106 KB, mtime Mar 13)
  backend/app/services/reports/change_history.py.bak
  frontend/src/app/projects/[id]/verification/page.tsx.bak
  frontend/src/app/projects/[id]/requirements/[reqId]/page.tsx.bak
  ```

#### F-024 — Duplicate `auth.ts` + `auth.tsx` modules at `@/lib/auth` with diverging shapes
- **File:** `frontend/src/lib/auth.ts`, `frontend/src/lib/auth.tsx`
- **Lines:** entire files
- **Category:** Frontend / Cross-cutting
- **Description:** Two files export `AuthProvider` and `useAuth` at the same logical import path (`@/lib/auth`). Module resolution picks one (Next/TS prefers `.tsx`), but their `User` shapes differ (auth.ts adds `is_active`, auth.tsx doesn't), one has `refresh()` the other has `token`, and only auth.ts defines RBAC helpers (`hasPermission`, `PermissionGate`). auth.ts also returns JSX without the `'use client'` pragma.
- **Impact:** Whichever module wins decides whether refresh tokens work, whether the User type carries `is_active`, and whether RBAC helpers exist at runtime. Consumers that rely on RBAC will silently fail if `auth.tsx` wins.
- **Recommendation:** Delete `auth.tsx` (older, shorter). Rename `auth.ts` → `auth.tsx` (since it returns JSX). Add `'use client';` as line 1.

#### F-025 — `auth.ts` exports React components but lacks `'use client'`; calls `localStorage` unguarded
- **File:** `frontend/src/lib/auth.ts`
- **Lines:** 1, 167
- **Category:** Frontend
- **Description:** This module exports `AuthProvider`, `PermissionGate`, and `useAuth` — all client-side hooks/components — but has no `'use client'` directive. It also calls `localStorage.setItem('astra_token', …)` at line 167 without a `typeof window !== 'undefined'` guard.
- **Impact:** Production builds may degrade to server components. Any server component importing this module will throw at SSR.
- **Recommendation:** Add `'use client';` at the top of the file (and rename to `.tsx` per F-024).

#### F-026 — Sidebar requirement count uses `limit:1` then reads `r.data.length` — always 0 or 1
- **File:** `frontend/src/components/layout/Sidebar.tsx`
- **Lines:** 136-140
- **Category:** API-Integration
- **Description:** Fetches `requirementsAPI.list(projectId, { limit: 1 })` and stores `Array.isArray(r.data) ? r.data.length : 0` as the requirement count. The list endpoint returns an array (not a paginated envelope), so the count can only ever be 0 or 1.
- **Impact:** The sidebar requirements badge is structurally wrong on every project — never matches the dashboard count.
- **Recommendation:** Use `/dashboard/stats` (which returns `total_requirements`) or change the backend list endpoint to return `{items, total}`.

#### F-027 — Login bypasses `useAuth().login()`; sets localStorage directly + hard-reloads the page
- **File:** `frontend/src/app/login/page.tsx`
- **Lines:** 14, 18-26, 62-71, 87-99, 109-117
- **Category:** Frontend / Security
- **Description:** All four success paths (local login, MFA, PIV, SSO callback) call `localStorage.setItem('astra_token', …)` then `window.location.href = '/'`. The hook `const { login } = useAuth()` is destructured but never invoked. SSO callback at lines 18-26 reads `?token=` from URL — putting a JWT in the address bar leaks it into browser history and analytics dumps. No URL replacement, no token validation before persisting.
- **Impact:** Tokens in browser history; AuthProvider state can drift from localStorage; full-page reload defeats SPA UX; failed validation is undetectable.
- **Recommendation:** `await login(username, password)` then `router.push('/')`. For SSO, use `router.replace('/')` to scrub the URL, validate via `/auth/me` first, persist only on success. Better: cookie-based SSO handshake.

#### F-028 — Two unit-detail pages at conflicting Next.js dynamic routes
- **File:** `frontend/src/app/projects/[id]/interfaces/unit/[unitId]/page.tsx`, `frontend/src/app/projects/[id]/interfaces/[unitId]/page.tsx`
- **Lines:** entire files
- **Category:** Frontend / Route-Structure
- **Description:** Both routes exist. Next.js routes `/interfaces/unit/123` to the new page (more specific), but `/interfaces/123` (any old bookmark) hits the legacy page. Worse, `/interfaces/whatever` (non-numeric) also hits the legacy page and calls `getUnit(NaN)`.
- **Impact:** Two sources of truth — bug fixes don't propagate; old bookmarks render stale UI.
- **Recommendation:** Delete the legacy `[unitId]/` folder.

#### F-029 — Interface page issues N getSystem() calls per system load to backfill `unit→system` map
- **File:** `frontend/src/app/projects/[id]/interfaces/page.tsx`, `frontend/src/lib/interface-types.ts`
- **Lines:** `interfaces/page.tsx:570-586`; `interface-types.ts:225-236`
- **Category:** Performance / API-Integration
- **Description:** `UnitSummary` (the lighter type returned by `listUnits`) does not include `system_id` (it is only on the heavier `Unit`). To build a unit→system map for harness grouping, the page issues N parallel `getSystem(s.id)` calls — one per system, every page load.
- **Impact:** Linear API call amplification. On a project with 30 systems, the Interfaces tab fires 30 extra round-trips every load.
- **Recommendation:** Add `system_id` to the backend `UnitSummary` schema and the frontend type. Drop the `SystemDetail` fan-out: `unitSystemMap = Object.fromEntries(units.map(u => [u.id, u.system_id]))`.

#### F-030 — `_run_background_ai` receives DB URL with secret; risk of secret-in-traceback
- **File:** `backend/app/routers/requirements.py`
- **Lines:** 226-243, 285-296, 354-365
- **Category:** Security
- **Description:** Two endpoints unwrap `settings.DATABASE_URL` with `.get_secret_value()` and then pass the raw URL (including password) as a positional argument to a `BackgroundTask`. The argument is unused inside `_run_background_ai` (which imports `SessionLocal` directly). On any task exception, the URL appears in the traceback / logger context.
- **Impact:** DB password disclosure in error logs and tracebacks.
- **Recommendation:** Drop the `db_url` argument; rely on the imported `SessionLocal`.

#### F-031 — Auth login emits no audit event on failure; success-path audit is silenced by `except Exception: pass`
- **File:** `backend/app/routers/auth.py`
- **Lines:** 83-87
- **Category:** Reliability (NIST AU-2)
- **Description:** Successful-login audit is wrapped in `try/except Exception: pass`. There is no audit emission for the `verify_password` failure branch. NIST 800-53 AU-2 requires both successful and failed authentication attempts to be auditable.
- **Impact:** Compliance gap; failed-login attempts cannot be reconstructed; intrusion analysis impossible.
- **Recommendation:** Emit `auth.login_failed` audit event in the failure branch with username + IP + UA. Don't swallow the success-side failure — `audit_service.record_event` already has its own retry semantics.

#### F-032 — Reports history is process-local in-memory; lost on restart, not shared between workers
- **File:** `backend/app/routers/reports.py`
- **Lines:** 38-39, 201-215
- **Category:** Reliability
- **Description:** `_report_history: list[dict] = []` is a module-level Python list. Each worker has its own copy; restart wipes it. `GET /reports/history` returns only the local worker's slice. Also no auth scoping — any user sees every project's history.
- **Impact:** Compliance gap (advertised as audit-grade history but is non-durable). Information disclosure across projects (orthogonal to F-014). Inconsistent results depending on which worker handles the request.
- **Recommendation:** Persist to a `report_history` DB table (or piggyback on `audit_log`). Always scope by project membership.

#### F-033 — `delete_*` cascade handlers emit audit BEFORE the destructive commit
- **File:** `backend/app/routers/interface.py`
- **Lines:** delete_system 267-299; delete_unit 524-575; delete_connector 880-1019; delete_bus 1505-1555; delete_message 1856-1889; delete_harness 2172-2205; delete_endpoint 3994-4051
- **Category:** Reliability / Domain
- **Description:** Each cascade-delete handler calls `_audit(db, "X.deleted", …)` BEFORE the multi-step `db.query(...).delete()` cascade and final `db.delete(parent); db.commit()`. `record_event` does its own commit, so the audit row is durable even if the cascade rolls back. There is also no `try/except` around the cascade.
- **Impact:** Tamper-evident audit log gets ahead of reality. "User X deleted entity Y" is recorded even when the deletion silently failed. Investigation follows a false lead.
- **Recommendation:** Move every `_audit(...)` call to AFTER `db.commit()` succeeds. Wrap the cascade in `try/except` with explicit `db.rollback()`.

#### F-034 — `confirm_import` (interface) re-uploads the file with no token tying preview to confirm
- **File:** `backend/app/routers/interface_import.py`
- **Lines:** 786-1120
- **Category:** Reliability / Security
- **Description:** Frontend uploads the same xlsx twice — once for `/preview`, once for `/confirm`. There is no token linking a validated preview to a specific confirm call. A user (or attacker) could approve preview A and upload modified file B to confirm.
- **Impact:** Validation TOCTOU — what was previewed is not what gets imported. User-side or attacker-side modifications slip past quality checks.
- **Recommendation:** At preview time, store the parsed-and-validated rows in a temporary table (or signed cache) keyed by a token. Confirm endpoint accepts only that token, not a re-uploaded file.

#### F-035 — `TraceLink` has no FKs on source/target, no project_id, no uniqueness; silent dangling references
- **File:** `backend/app/models/__init__.py`, `backend/app/routers/projects.py`
- **Lines:** `models/__init__.py:213-228`; `projects.py:109-129`
- **Category:** Schema / Domain
- **Description:** `TraceLink.source_id` and `target_id` are `Column(Integer, nullable=False)` with NO `ForeignKey` constraint. `source_type`/`target_type` are free-form strings. No `project_id`. No unique constraint on `(source_type, source_id, target_type, target_id, link_type)`. `create_trace_link` accepts arbitrary IDs and inserts without validating the referenced entities exist or that source and target belong to the same project.
- **Impact:** Trace integrity is not enforced. Coverage reports, impact analysis, and the orphan detector silently drift. Cross-project link injection is possible. Compliance reports become misleading (NASA NPR 7150.2 / DO-178C bidirectional traceability required).
- **Recommendation:** Add validation in `create_trace_link` (entities exist, same project, not deleted). Add `Index("ix_trace_source", "source_type","source_id")`, `Index("ix_trace_target", "target_type","target_id")`, and `UniqueConstraint("source_type","source_id","target_type","target_id","link_type")`. Application-level cleanup hook on entity deletion.

#### F-036 — External-IdP users get fake bcrypt hash → `verify_password` fails → cannot e-sign
- **File:** `backend/app/services/auth_providers/__init__.py`
- **Lines:** 38-50
- **Category:** Security / Domain
- **Description:** When SAML/OIDC/PIV creates a local `User` row, `hashed_password` is set to the literal string `"EXTERNAL_IDP_NO_LOCAL_PASSWORD"`. That is not a bcrypt hash. `signature_service.request_signature():51` calls `verify_password(password, user.hashed_password)` which will return `False` (or raise) for these users.
- **Impact:** SAML/OIDC/PIV users CANNOT sign approvals. Stages requiring `require_signature=True` are blocked indefinitely for these users — directly contradicts the multi-IdP support advertised in `docs/PIV_SETUP.md`.
- **Recommendation:** For external-IdP users, implement a "sign with IdP step-up" path that doesn't go through `verify_password` (e.g., fresh OIDC `prompt=login` re-auth + return a step-up token used as the signature evidence). Document the chosen approach.

#### F-037 — PIV cert-chain validation does not actually validate the chain
- **File:** `backend/app/services/auth_providers/piv.py`
- **Lines:** 109-137
- **Category:** Security
- **Description:** `validate_cert_chain` only checks the cert's expiry. The signature chain is NOT verified against the CA bundle. Comment at line 134 admits "real chain validation needs pyOpenSSL or certvalidator." In dev (no CA bundle), the function returns True. In prod, it returns True if the cert is unexpired regardless of issuer.
- **Impact:** PIV/CAC auth accepts ANY parseable, unexpired cert — complete CAC auth bypass for any environment using the PIV provider.
- **Recommendation:** Use `cryptography`'s X509 verification (>= 42) or `certvalidator` to walk the chain. Check OCSP/CRL when env vars demand it. Until implemented, raise `NotImplementedError` or refuse to register the PIV provider when `ENVIRONMENT=production`.

#### F-038 — Mutable defaults on dozens of SQLAlchemy + Pydantic fields
- **File:** `backend/app/models/__init__.py`, `models/embedding.py`, `models/integration.py`, `models/interface.py`, `models/audit_log.py`, `models/ai_models.py`, `schemas/__init__.py`, `schemas/interface.py`, `schemas/impact.py`, `schemas/ai_embeddings.py`
- **Lines:** `models/__init__.py:141,202`; `models/embedding.py:44,87`; `models/integration.py:74`; `models/interface.py:1198,1351,1420,1621`; `models/audit_log.py:40`; `models/ai_models.py:26`; `schemas/__init__.py:120`; `schemas/impact.py:65,168`; `schemas/ai_embeddings.py:154` (representative)
- **Category:** Schema
- **Description:** Pattern `Column(JSON, default={})` and `Column(JSON, default=[])` is repeated across many models. SQLAlchemy mostly tolerates it for column defaults (deepcopy on each insert) but the value is shared by reference at the Python level if `model.field` is read before flush. Pydantic input schemas (`SourceArtifactCreate.participants: List[str] = []` and friends) have the same problem and Pydantic v2 still does not protect against it.
- **Impact:** Subtle action-at-a-distance bugs when a not-yet-committed instance has its mutable default modified — the change is visible on every subsequent new instance until restart.
- **Recommendation:** Use callables: `default=dict`, `default=list` for SQLAlchemy. `Field(default_factory=list)` / `Field(default_factory=dict)` for Pydantic.

---

### MEDIUM

#### F-039 — N+1 queries in interface detail endpoints (per-row `db.query` in tight loops)
- **File:** `backend/app/routers/interface.py`
- **Lines:** 209-231, 386-474, 755-783, 1425-1467, 2118-2139, 3835-3891; `services/ai/impact_analyzer.py:610-660`; `services/signature_service.py:130`; `services/workflow_engine.py:379,444`
- **Category:** Backend / Reliability
- **Description:** `get_system`, `get_unit`, `get_connector`, `get_bus`, `get_harness`, `get_connection` each issue per-iteration `db.query(...).first()` for related entities (Connector per pin, Unit per connector, Pin per assignment, mating). Same N+1 in `_find_affected_verifications`, `signature_service.get_signatures`, `workflow_engine.get_instance_detail / list_instances`.
- **Impact:** Page latency scales O(units × connectors × pins). Multi-second responses on projects with hundreds of pins per unit; connection pool fills with short queries.
- **Recommendation:** Use `joinedload`/`selectinload` across the relationship chain, or single SQL query with explicit joins.

#### F-040 — Dashboard stats loads all requirements + history into Python and joins per-row
- **File:** `backend/app/routers/dashboard.py`
- **Lines:** 15-138
- **Category:** Backend
- **Description:** `get_dashboard_stats` calls `.all()` on requirements (no limit), iterates in Python, and for each `RequirementHistory` row issues a fresh `db.query(User)…first()` to look up the changer.
- **Impact:** Project with thousands of requirements + history rows produces thousands of round-trip user lookups; multi-second dashboard.
- **Recommendation:** Single User join, GROUP BY aggregations in SQL.

#### F-041 — `get_project_risk` issues 3N DB queries per requirement
- **File:** `backend/app/routers/impact.py`
- **Lines:** 209-285
- **Category:** Backend
- **Description:** Loops through every requirement and runs three counts (outbound, inbound, child_count). Project with 500 requirements = 1500 queries. Not bounded by `limit`.
- **Impact:** 3-5 second response on a moderate project; CPU-blocking.
- **Recommendation:** Two GROUP BY queries; combine in Python; add server-enforced item limit.

#### F-042 — `list_project_members` runs 2N user lookups inside the response builder
- **File:** `backend/app/routers/admin.py`
- **Lines:** 196-208
- **Category:** Backend
- **Description:** For each `ProjectMember`, the response builder issues `db.query(User).filter(User.id == m.user_id).first()` TWICE plus a `or User(...)` fallback that constructs throwaway User objects.
- **Impact:** 2N unnecessary queries; messy fallback.
- **Recommendation:** Single join (`db.query(ProjectMember, User).join(User)…`) or eager-load via relationship.

#### F-043 — `list_baselines` runs N user-lookup queries inside the response comprehension
- **File:** `backend/app/routers/baselines.py`
- **Lines:** 115
- **Category:** Backend
- **Description:** `for b in baselines: creator = db.query(User).filter(User.id == b.created_by_id).first()`.
- **Impact:** O(N) round-trips for the baselines list.
- **Recommendation:** Eager-load via relationship or single User-IN-list query.

#### F-044 — `list_trace_links` materializes IN-clauses of all req_ids + artifact_ids
- **File:** `backend/app/routers/projects.py`
- **Lines:** 84-106
- **Category:** Backend
- **Description:** Fetches all `Requirement.id` and `SourceArtifact.id` for the project, then queries TraceLink with two `IN(req_ids)` plus two `IN(art_ids)` joined by OR. Approaches Postgres' parameter limit and is slow at scale. No `limit/offset` on the result.
- **Impact:** O(N) row scan + return-everything; potential `max_locks_per_transaction` issues; unbounded response.
- **Recommendation:** Drive from TraceLink with a subquery on `Requirement.project_id == X`. Add `skip`/`limit` query params.

#### F-045 — Embedding storage uses JSON column, not pgvector — cosine similarity in pure Python at O(N²)
- **File:** `backend/alembic/versions/0005_add_embedding_tables.py`, `backend/app/services/ai/duplicate_detector.py`, `backend/app/services/ai/trace_suggester.py`
- **Lines:** `0005:35`; `duplicate_detector.py:64-69,113-124`; `trace_suggester.py:39-89`
- **Category:** Reliability / Performance
- **Description:** `requirement_embeddings.embedding` is `Column(JSON, server_default="[]")`. No `CREATE EXTENSION pgvector` anywhere in the repo. `find_duplicates` does pairwise similarity in pure Python (N² cosine), then recomputes per-pair similarity inside group-build (O(N²) again). For 1000 requirements that's 500k cosine ops per call. `suggest_trace_links` reloads all project embeddings into memory on every call.
- **Impact:** Multi-second latency; CPU-bound; blocks the event loop in async context. UI-perceived AI latency proportional to project size.
- **Recommendation:** Adopt pgvector (proper migration with `with op.get_context().autocommit_block(): op.execute("CREATE EXTENSION IF NOT EXISTS vector")` then ALTER COLUMN). For now, use numpy: `np.dot(M, M.T) / norms` is one matmul. Memoize `get_project_embeddings` per `(project_id, latest_mtime)`.

#### F-046 — Auto-requirement approve/reject doesn't verify the requirement_ids belong to the caller's project
- **File:** `backend/app/routers/interface.py`
- **Lines:** approve 2838-2957; reject 2960-3016
- **Category:** Domain / Security
- **Description:** Caller-supplied `requirement_ids` are loaded and mutated without per-requirement project ownership/membership checks; no consistency check that all IDs belong to the same project. Bulk audit event uses `entity_id=0`.
- **Impact:** A user with `interfaces.update` on project A could submit requirement_ids from project B and bulk-approve them. Audit event has no entity_id anchor for investigation.
- **Recommendation:** Validate every requirement belongs to a project the caller is a member of. Use the actual `project_id` in the audit event (or one event per project_id).

#### F-047 — DELETE handlers conflate "preview" with destructive verb (return 200 with no deletion when `confirm=false`)
- **File:** `backend/app/routers/interface.py`
- **Lines:** delete_unit 524-575; delete_bus 1505-1555; delete_message 1856-1889; delete_harness 2172-2205; delete_wire 3040-3075; delete_endpoint 3994-4051
- **Category:** Reliability
- **Description:** HTTP DELETE returns `{"status":"preview", …}` with status_code 200 when `confirm` is falsy. Naive clients can't distinguish a preview from a real delete.
- **Recommendation:** Move "preview" to a dedicated `GET /unit/{id}/delete-impact`. DELETE always destructive (with optional `force=true` for cascade).

#### F-048 — `delete_field` skips the confirm gate, mutates linked link statuses without preview, no audit
- **File:** `backend/app/routers/interface.py`
- **Lines:** 1953-1971
- **Category:** Reliability / Domain
- **Description:** Unlike the other DELETE handlers, `delete_field` immediately deletes and bulk-updates linked `InterfaceRequirementLink` rows to "pending_review" with no preview path and no `_audit(...)` emission.
- **Recommendation:** Add `confirm` gate; emit audit.

#### F-049 — `update_wire` mutates fields freely without rebuilding `Connection` rollup; no audit
- **File:** `backend/app/routers/interface.py`
- **Lines:** 3018-3037
- **Category:** Reliability
- **Description:** If `from_pin_id`/`to_pin_id` change (rerouting the wire to a different LRU pair), the Connection rollup is not rebuilt. Stale Connection persists. No `_audit` event.
- **Recommendation:** Run `maybe_delete_connection_for_wire` on old state, then `_upsert_connection` on new. Emit audit.

#### F-050 — `delete_req_link` and `create_req_link` emit no audit event
- **File:** `backend/app/routers/interface.py`
- **Lines:** create 3323-3346; delete 3380-3391
- **Category:** Domain (compliance)
- **Description:** No `_audit(...)` call. Trace-link create/delete is part of traceability evidence and must be audited per 21 CFR Part 11 / DO-178C.
- **Recommendation:** Add `_audit(db, "interface_req_link.created"|".deleted", ...)`.

#### F-051 — `get_interface_coverage` queries `InterfaceRequirementLink` with no `project_id` filter
- **File:** `backend/app/routers/interface.py`
- **Lines:** 3398-3447
- **Category:** Backend / Domain
- **Description:** `linked_ifaces`, `auto_total`, `auto_approved`, `auto_pending` count globally — no project scoping (the model has no `project_id`). The reported coverage for project_id=X mixes counts from ALL projects.
- **Recommendation:** Either add `project_id` to `InterfaceRequirementLink`, or constrain via a join to the entity types (Interface/Unit/etc.) that DO carry `project_id`.

#### F-052 — `list_req_links` allows queries without `entity_id` — table scan
- **File:** `backend/app/routers/interface.py`
- **Lines:** 3349-3377
- **Category:** Backend / Security
- **Description:** Caller can pass only `entity_type="requirement"` (no `entity_id`) and pull every link with that type across all projects.
- **Recommendation:** Require `entity_type+entity_id` as a pair, or `requirement_id` alone. Add `project_id` filter.

#### F-053 — `clone_requirement` runs two commits with no rollback path; no `_audit` call
- **File:** `backend/app/routers/requirements.py`
- **Lines:** 482-512
- **Category:** Reliability / Domain
- **Description:** Commits the clone insert, then commits the history insert. If the second fails, the clone exists with no audit history. No `_audit("requirement.cloned", ...)`.
- **Recommendation:** Single transaction with try/except; add audit emission.

#### F-054 — `_run_background_ai` opens SessionLocal but never commits (relies on `cache_analysis` to commit)
- **File:** `backend/app/routers/requirements.py`
- **Lines:** 226-243
- **Category:** Reliability
- **Description:** `db = SessionLocal(); ... cache_analysis(db, ...); db.close()` — no `db.commit()`. `cache_analysis` must be committing internally; if it doesn't, the cached result silently rolls back.
- **Recommendation:** Use `with SessionLocal() as db: ... db.commit()`.

#### F-055 — `confirm_import` (CSV) catches per-row exceptions but commits everything in one transaction
- **File:** `backend/app/routers/imports.py`
- **Lines:** 418-429
- **Category:** Reliability
- **Description:** Each row's create+flush is wrapped in try/except, but the parent commit happens after the loop. A row that raised after `db.add` may have left orphan objects in the session, tainting subsequent rows.
- **Recommendation:** Use `db.begin_nested()` per row; outer commit promotes only successful savepoints.

#### F-056 — `confirm_import` (interface) fabricates fake `signal_name="SPARE_{n}"` when user omits it
- **File:** `backend/app/routers/interface_import.py`
- **Lines:** 951
- **Category:** Domain
- **Description:** Preview validation flags missing signal_name (line 692) but confirm fabricates `SPARE_{pin_num}` instead of skipping. Preview/confirm semantic mismatch.
- **Recommendation:** Skip rows whose preview marked invalid; or run validator inline at confirm.

#### F-057 — `trigger_sync` swallows connector exceptions, commits "failed" log + last_sync_at without rollback of partial inserts
- **File:** `backend/app/routers/integrations.py`
- **Lines:** 294-327
- **Category:** Reliability
- **Description:** Connector that creates 50 requirements then fails on the 51st leaves 50 stray requirements + a "failed" SyncLog. No `db.rollback()` for partial inserts.
- **Recommendation:** Run connector inside `db.begin_nested()`; rollback savepoint on exception; commit only the SyncLog in the outer transaction.

#### F-058 — `create_/update_integration` accept `project_id` but only check role, not membership
- **File:** `backend/app/routers/integrations.py`
- **Lines:** 154-182, 197-215
- **Category:** Security
- **Description:** Any global PM can create/edit integration configs (with stored API tokens) for any project, including projects they have no other access to.
- **Recommendation:** Add project membership assertion (covered globally by F-014).

#### F-059 — `create_baseline` commits parent + many children in one transaction with no try/except
- **File:** `backend/app/routers/baselines.py`
- **Lines:** 38-94
- **Category:** Reliability
- **Description:** No try/except wrapping the snapshot loop. If the loop fails mid-way, the parent Baseline row + some snapshots may persist in a partial state if a downstream layer catches the exception.
- **Recommendation:** Wrap in try/except with rollback; verify count after commit and emit alarm if mismatch.

#### F-060 — Seed creates `TraceLink` with `target_id=0`, then patches after flush
- **File:** `backend/app/routers/seed_project.py`
- **Lines:** 670-685
- **Category:** Reliability
- **Description:** `db.add(link); db.add(verif); db.flush(); link.target_id = verif.id`. Relies on flush ordering. Constraint violation between flush and final commit could leave a committed link with `target_id=0`.
- **Recommendation:** Insert verification first, flush, then create the link with `verif.id`.

#### F-061 — Seed BaselineRequirement uses hardcoded `status_snapshot="approved"` and omits half the snapshot fields
- **File:** `backend/app/routers/seed_project.py`
- **Lines:** 706-743
- **Category:** Reliability / Domain
- **Description:** All BaselineRequirement rows written with `status_snapshot="approved"` regardless of the requirement's actual status. Fields `type_snapshot`, `priority_snapshot`, `quality_score_snapshot`, `version_snapshot`, `parent_id_snapshot` are missing.
- **Recommendation:** Snapshot the requirement's actual fields; match the schema used by the legitimate `POST /baselines` endpoint.

#### F-062 — Seed idempotency uses `count >= 20` threshold; partially-populated project gets re-seeded
- **File:** `backend/app/routers/seed_project.py`
- **Lines:** 446-475
- **Category:** Backend
- **Description:** A project with 1-19 existing requirements will silently get 48 more appended, with possible req_id collisions (`FR-001` etc.).
- **Recommendation:** Check for an existing seed-marker requirement ID and short-circuit if present.

#### F-063 — In-memory JWT blacklist; lost on restart, not multi-process safe
- **File:** `backend/app/services/auth_manager.py`
- **Lines:** 106-114
- **Category:** Security
- **Description:** `_BLACKLIST: set[str] = set()` is module-local. Each worker has its own. After restart, all "logged out" tokens are valid again until exp.
- **Recommendation:** Persist revocations in a small DB table (or Redis) keyed by JWT `jti` + `exp`; check on every request.

#### F-064 — Rate limiter is per-worker in-memory; effective limit multiplies by worker count
- **File:** `backend/app/middleware/rate_limiter.py`
- **Lines:** 60-117
- **Category:** Reliability / Security
- **Description:** `_TokenBucket` is per `RateLimiterMiddleware` instance per worker process. With N workers, an attacker effectively gets `N × default_rpm` per IP. Stated rate limits (100/10/5) are misleading. Also `_select_bucket` uses substring matching on path (`if "/auth/" in path`) which is fragile and can mis-tier paths.
- **Recommendation:** Move to Redis-backed token bucket so all workers share state. Document the worker-count multiplier until then. Match exact `API_PREFIX + tier`.

#### F-065 — Workflow timeout escalation does not actually escalate or notify
- **File:** `backend/app/services/workflow_engine.py`
- **Lines:** 280-335
- **Category:** Reliability
- **Description:** Escalation branch only appends a dict to a return list. No notification, no role change, no DB record. The `auto_escalate_to_role` field is read here but consumed nowhere.
- **Recommendation:** Implement escalation (notification, role flag, DB record) or remove the field to avoid implying it works.

#### F-066 — `ALLOWED_HOSTS` defaults to "*" and `TrustedHostMiddleware` is never registered
- **File:** `backend/app/config.py`, `backend/app/main.py`
- **Lines:** `config.py:50-51`; `main.py:142-148`
- **Category:** Security
- **Description:** Config sets `ALLOWED_HOSTS: str = "*"`. `enforce_production_guards()` doesn't check it. `TrustedHostMiddleware` is not registered in `main.py` (only CORS is).
- **Impact:** Host-header attacks (cache-poisoning, password-reset poisoning) are possible. The intent of `ALLOWED_HOSTS` is unenforced.
- **Recommendation:** Either remove the unused config or wire `TrustedHostMiddleware` and refuse "*" in production guard.

#### F-067 — `ENCRYPTION_KEY` not in `enforce_production_guards`
- **File:** `backend/app/config.py`
- **Lines:** 43, 99-123
- **Category:** Security
- **Description:** `ENCRYPTION_KEY: SecretStr = SecretStr("")`. Production guard only checks SECRET_KEY.
- **Recommendation:** Add ENCRYPTION_KEY to the guard; refuse to start in prod with empty value. (Companion to F-003.)

#### F-068 — `ACCESS_TOKEN_EXPIRE_MINUTES = 480` (8 hours), `SESSION_TIMEOUT_MINUTES = 60` is unused
- **File:** `backend/app/config.py`
- **Lines:** 39-40
- **Category:** Security (NIST AC-12)
- **Description:** 8-hour JWT lifetime with no refresh, no revocation list, no idle timeout enforcement. SESSION_TIMEOUT_MINUTES is defined but unused.
- **Recommendation:** Lower access token to ≤30 minutes; implement refresh + revocation list.

#### F-069 — RBAC import fallback silently degrades to `get_current_user` (no warning)
- **File:** `backend/app/routers/admin.py`, several others
- **Lines:** `admin.py:25-32`
- **Category:** Security
- **Description:** `try/except ImportError: def require_permission(action): return get_current_user`. A future broken import silently drops ALL role-based access controls.
- **Recommendation:** Either make RBAC a hard dependency, or log a CRITICAL warning at startup when the fallback is active.

#### F-070 — `interface_import.confirm_import` audit emit uses `request=None` then forwards to `record_event`
- **File:** `backend/app/routers/interface_import.py`
- **Lines:** 786-1118
- **Category:** Reliability
- **Description:** `request=None` is the bare default (no `Request` type). `_audit(..., request=request)` forwards None; `record_event` tries `request.client.host if request.client else ""` and may crash (silently swallowed) — the IP/UA fields will be empty.
- **Recommendation:** Declare `request: Request` properly.

#### F-071 — `POST /imports/template` should be `GET`
- **File:** `backend/app/routers/imports.py`
- **Lines:** 457-464; also `interface_import.py:297-300`
- **Category:** Backend
- **Description:** Template-download endpoints generate a deterministic xlsx with no input parameters except `current_user`. POST is wrong verb; breaks caching; CSRF-exempt-GET protections won't apply.
- **Recommendation:** Change to `@router.get("/template")`.

#### F-072 — `GET /imports/template` lacks authentication
- **File:** `backend/app/routers/imports.py`
- **Lines:** 457-464
- **Category:** Security
- **Description:** No `Depends(get_current_user)`. Reconnaissance leak that the API exists.
- **Recommendation:** Add `current_user: User = Depends(get_current_user)`.

#### F-073 — `deactivate_user` mapped to DELETE but does soft-delete; doesn't deactivate ProjectMember rows
- **File:** `backend/app/routers/admin.py`
- **Lines:** 139-154
- **Category:** Domain / Backend
- **Description:** HTTP DELETE returning 200 with body and just flipping `is_active=False`. ProjectMember rows are not touched — deactivated user remains "in" projects.
- **Recommendation:** Either rename to `POST /users/{id}/deactivate`, or implement true deletion + cascade ProjectMember.

#### F-074 — `_next_id` race condition for all interface entity IDs
- **File:** `backend/app/routers/interface.py`, `imports.py`, `projects.py`
- **Lines:** `interface.py:113-127`; `imports.py:362-367`; `projects.py:372-388`
- **Category:** Reliability
- **Description:** `count + 1` pattern (or `max + 1`) for human-readable IDs (FR-001, FR-002, ART-001, IFC-XXX). Two concurrent creates produce identical IDs → unique-constraint failure.
- **Recommendation:** Per-project sequence or `SELECT FOR UPDATE` on a counter.

#### F-075 — `Requirement` table has no `(project_id, req_id)` uniqueness; missing composite indexes
- **File:** `backend/app/models/__init__.py`
- **Lines:** 153-189
- **Category:** Schema
- **Description:** `__table_args__` is empty; comment says "Each req_id must be unique within a project" but no constraint backs it. No composite index on `(project_id, status)`, `(project_id, req_type)`, `(project_id, owner_id)`.
- **Recommendation:** Add `UniqueConstraint("project_id","req_id", name="uq_req_per_project")` and supporting indexes.

#### F-076 — Most parent-child FKs lack `ondelete` strategy
- **File:** `backend/app/models/__init__.py`
- **Lines:** 139, 203, 235, 254
- **Category:** Schema
- **Description:** `Project.owner_id`, `SourceArtifact.project_id`, `Verification.requirement_id`, `RequirementHistory.requirement_id` have no `ondelete`. Cascading deletes are inconsistent between ORM-managed and DB-managed paths.
- **Recommendation:** `requirement_id → CASCADE`, `owner/created_by → SET NULL` (preserve history of deleted users).

#### F-077 — `MessageField` uses Float for engineering-unit conversions (DO-178C / MIL-STD-882E concern)
- **File:** `backend/app/models/interface.py`
- **Lines:** 1452-1457
- **Category:** Domain
- **Description:** `scale_factor`, `offset_value`, `lsb_value`, `min_value`, `max_value`, `resolution`, `accuracy` use `Float`. For ICD message field encodings (BAM16, scaled-int → engineering units), this introduces float round-trip error that matters for verification.
- **Recommendation:** `Numeric(20, 9)` (Postgres NUMERIC) for fields that participate in engineering-unit math.

#### F-078 — `WireHarness` UniqueConstraint `(from_connector_id, to_connector_id)` blocks multi-endpoint design
- **File:** `backend/app/models/interface.py`
- **Lines:** 1543-1545
- **Category:** Schema
- **Description:** Predates the HarnessEndpoint model. Forces a single from/to pair per harness; rejects two harnesses between the same two LRUs (e.g., redundant power + signal).
- **Recommendation:** Drop the constraint; rely on `harness_endpoints.lru_connector_id` UNIQUE.

#### F-079 — `quality_checker.PROHIBITED_TERMS` has duplicate "sufficient"; second source-of-truth in reports
- **File:** `backend/app/services/quality_checker.py`, `backend/app/services/reports/quality_report.py`
- **Lines:** `quality_checker.py:12-21`; `quality_report.py:35-40`
- **Category:** Domain
- **Description:** "sufficient" appears twice in `PROHIBITED_TERMS`. The list also diverges from a similar list in `quality_report.py`. Reports and live checks disagree on what's prohibited.
- **Recommendation:** Single module (e.g., `services/quality/nasa_terms.py`); import from both.

#### F-080 — Audit log writes from cron (workflow timeouts) record empty IP/UA
- **File:** `backend/app/services/audit_service.py`
- **Lines:** 79-83
- **Category:** Reliability (compliance)
- **Description:** `get_request_context()` returns `{}` for non-request invocations. Cron-triggered actions audit with no IP/UA — minor 21 CFR Part 11 hit.
- **Recommendation:** Pass `system="cron"` marker into `action_detail`; document.

#### F-081 — `ai/quality_analyzer` swallows malformed AI issue parses silently
- **File:** `backend/app/services/ai/quality_analyzer.py`
- **Lines:** 82
- **Category:** Reliability
- **Description:** `except Exception: continue` — drops issues with no log. If LLM returns malformed JSON for one issue out of ten, nine appear and the user has no signal.
- **Recommendation:** `logger.debug("Skipping malformed issue: %s", exc)` at minimum.

#### F-082 — SAML provider opens cert/key files without context manager
- **File:** `backend/app/services/auth_providers/saml.py`
- **Lines:** 36-38
- **Category:** Security
- **Description:** `open(cert_file).read()` leaks file handles on exception.
- **Recommendation:** `with open(...) as f:`.

#### F-083 — `ai/impact_analyzer._persist_report` writes inside the request session with no transaction isolation
- **File:** `backend/app/services/ai/impact_analyzer.py`
- **Lines:** 897-920
- **Category:** Reliability
- **Description:** Same db session as caller; if caller already committed and is mid-rollback, the report write either races with cascade deletes or commits orphan rows. `report_json` has no size limit.
- **Recommendation:** Explicit `db.flush()` before commit; truncate `report_json`; bound the captured-items count.

#### F-084 — Multiple frontend pages use `require('@/lib/ai-api')` inside React components
- **File:** `frontend/src/app/projects/[id]/page.tsx`, `requirements/page.tsx`, `requirements/new/page.tsx`, `requirements/[reqId]/page.tsx`, `traceability/page.tsx`
- **Lines:** representative: `page.tsx:32-33,378-382`; `requirements/[reqId]/page.tsx:328-335`
- **Category:** Frontend / Type-Safety
- **Description:** `let aiAPI: any = null; try { aiAPI = require('@/lib/ai-api').aiAPI; } catch {}`. Webpack/turbopack bundles unconditionally; the catch never fires; types are `any`.
- **Recommendation:** Normal `import { aiAPI } from '@/lib/ai-api'`. Gate on `aiAPI.isAvailable` for runtime feature flag.

#### F-085 — `verification/page.tsx` issues N requirement-by-requirement verification fetches batched 5 with 100ms delay
- **File:** `frontend/src/app/projects/[id]/verification/page.tsx`
- **Lines:** 64-94
- **Category:** Performance / API-Integration
- **Description:** No bulk endpoint exists. For 100 reqs that's 20 batches × ~100ms = ~2s minimum.
- **Recommendation:** Add `GET /verifications?project_id=X` returning all in one query.

#### F-086 — `auto-requirements/page.tsx` has the same N+1 batched-with-delay pattern
- **File:** `frontend/src/app/projects/[id]/interfaces/auto-requirements/page.tsx`
- **Lines:** 251-267
- **Category:** Performance / API-Integration
- **Description:** Same anti-pattern.
- **Recommendation:** Backend endpoint `GET /interfaces/req-links?project_id=X&auto_generated=true`.

#### F-087 — Traceability AI suggestions silently truncates to first 20 requirements
- **File:** `frontend/src/app/projects/[id]/traceability/page.tsx`
- **Lines:** 144-167
- **Category:** Performance / API-Integration
- **Description:** `batch = reqs.slice(0, 20)`. Suggestions for requirements 21+ are dropped with no UI signal.
- **Recommendation:** Project-wide trace-suggestions endpoint, or paginate with explicit "Showing first 20" indicator.

#### F-088 — `ForceGraph` runs 60-iteration O(N²) force simulation synchronously in useEffect
- **File:** `frontend/src/components/traceability/ForceGraph.tsx`
- **Lines:** 117-210, 418-440
- **Category:** Performance / Frontend
- **Description:** 60 × N² ops on mount. For 200 nodes ≈ 2.4M ops blocks main thread. Edges keyed by index (`key={`edge-${i}`}`) — reorders cause wrong-styled lines.
- **Recommendation:** Web Worker or split iterations across `requestAnimationFrame`. Key edges by stable id.

#### F-089 — `interfaces/page.tsx` swallows all fetch errors with empty catch
- **File:** `frontend/src/app/projects/[id]/interfaces/page.tsx`
- **Lines:** 548-595
- **Category:** API-Integration
- **Description:** `try { ... } catch { } setLoading(false);` — silent failure shows blank page with no error.
- **Recommendation:** Surface via state + error banner.

#### F-090 — Toast severity inferred from substring match on message text
- **File:** `frontend/src/app/projects/[id]/interfaces/auto-requirements/page.tsx`, `settings/page.tsx`, `system/[systemId]/page.tsx`, `unit/[unitId]/page.tsx`
- **Lines:** 441-444 (auto-requirements)
- **Category:** Frontend
- **Description:** `toast.includes('fail') ? red : green`. A success message containing "fail" (e.g., "0 failed") will be styled red.
- **Recommendation:** Pass severity explicitly: `flash(message, 'success'|'error')`.

#### F-091 — Native `confirm()` / `alert()` for destructive actions and error reporting
- **File:** `requirements/[reqId]/page.tsx:553`, `baselines/page.tsx:71`, `interfaces/[unitId]/page.tsx:86,97`
- **Category:** A11y / UX
- **Description:** Native dialogs block the JS thread, can't be styled, and have poor screen-reader support.
- **Recommendation:** Use the existing modal / `flash()` patterns.

#### F-092 — Pervasive `useState<any>(null)` instead of typed response interfaces
- **File:** `frontend/src/app/projects/[id]/page.tsx`, `audit/page.tsx`, `impact/page.tsx`, `baselines/page.tsx`, `traceability/page.tsx`
- **Category:** Type-Safety
- **Description:** Backend contract drift goes undetected. Concrete types exist for some (e.g., `ImpactReport` in `impact-api.ts`) but are not used as state types.
- **Recommendation:** Define / reuse `DashboardStats`, `CoverageReport`, `BaselineDetail`, `AISuggestion` interfaces.

#### F-093 — `Wire` interface stale: `(w as any).signal_type` cast in PinMapSvg
- **File:** `frontend/src/app/projects/[id]/interfaces/harness/[harnessId]/page.tsx`
- **Lines:** 130, 191, 204, 230
- **Category:** Type-Safety
- **Description:** Real wire payload has `signal_type`; TS interface doesn't.
- **Recommendation:** Add `signal_type?: SignalType` to `Wire`.

#### F-094 — Many icon-only buttons missing aria-label
- **File:** Multiple — `audit/page.tsx:163`, `baselines/page.tsx:93,123`, `traceability/page.tsx:229`, `requirements/page.tsx:594`, `interfaces/page.tsx:799`
- **Category:** A11y (WCAG 4.1.2)
- **Description:** Refresh, expand, trash, X-close buttons render only an icon.
- **Recommendation:** Add `aria-label` to every `<button>` with no text child.

#### F-095 — Many form inputs not associated with their label
- **File:** Pervasive across `projects/new`, `requirements/new`, `settings`, modal pages
- **Category:** A11y (WCAG 1.3.1, 4.1.2)
- **Description:** `<label>Name</label><input ...>` without `htmlFor`/`id` pairing.
- **Recommendation:** Wrap input in `<label>` or use `htmlFor`/`id`.

#### F-096 — Requirements tree built with `<div>` nodes instead of `role="tree"`
- **File:** `frontend/src/app/projects/[id]/requirements/page.tsx`
- **Lines:** 140-191
- **Category:** A11y
- **Description:** No `role="tree"`/`treeitem`, no `aria-expanded`/`aria-level`, no arrow-key navigation.
- **Recommendation:** Add ARIA tree roles or use a third-party tree component.

#### F-097 — Color-only signaling on pin/wire colors and signal-type indicators
- **File:** `harness/[harnessId]/page.tsx` (PinMapSvg), `connection/[connectionId]/page.tsx` (ConnectorPairPinMap)
- **Category:** A11y (WCAG 1.4.1)
- **Description:** Hover-only tooltip is the only way to read signal type from the dot color.
- **Recommendation:** Add a small letter/glyph code adjacent to the color indicator.

#### F-098 — Requirements list/tree renders all 200 rows without virtualization
- **File:** `frontend/src/app/projects/[id]/requirements/page.tsx`
- **Category:** Performance
- **Description:** Every keystroke in the search box re-renders all rows; sluggish on large projects.
- **Recommendation:** react-window/virtuoso for >100 rows.

#### F-099 — Import wizard fake progress bar
- **File:** `frontend/src/app/projects/[id]/import/page.tsx`
- **Lines:** 151-153, 151-168
- **Category:** Frontend
- **Description:** `setInterval` ticks progress to 90% regardless of server-side progress; `clearInterval` is not in `finally`.
- **Recommendation:** Replace with a spinner or implement SSE/WebSocket progress.

#### F-100 — Auto-suggest level overrides user's explicit level selection on parent change
- **File:** `frontend/src/app/projects/[id]/requirements/new/page.tsx`
- **Lines:** 163-171
- **Category:** Frontend / UX
- **Description:** Effect re-runs and overwrites manually chosen level.
- **Recommendation:** Track whether user manually touched `level`.

#### F-101 — `AppShell` renders `<LoginPage />` in-place instead of redirecting to `/login`
- **File:** `frontend/src/components/layout/AppShell.tsx`
- **Lines:** 48-54
- **Category:** Frontend
- **Description:** URL doesn't reflect login state; deep-link UX broken; no `?next=` honoring.
- **Recommendation:** `router.replace('/login?next=' + currentPath)`; login flow honors `?next`.

#### F-102 — `aiStats` fetched without AbortController; setState on unmounted component
- **File:** `frontend/src/app/projects/[id]/page.tsx`
- **Lines:** 378-382
- **Category:** Frontend
- **Recommendation:** Use AbortController pattern as in `requirements/page.tsx:380-432`.

#### F-103 — `divide-by-zero hazard` on `avgQuality` when no project has stats
- **File:** `frontend/src/app/page.tsx`
- **Lines:** 198-200
- **Category:** Frontend
- **Recommendation:** Guard against `withStats.length === 0`.

#### F-104 — Postgres port 5432 exposed to host in dev compose
- **File:** `docker-compose.yml`
- **Lines:** 21-22
- **Category:** Security
- **Description:** `ports: "5432:5432"` allows any host process (or anything reachable on the host) to connect with the dev password.
- **Recommendation:** `127.0.0.1:5432:5432`. Same for pgAdmin (line 36).

#### F-105 — No HEALTHCHECK on backend/frontend in dev compose
- **File:** `docker-compose.yml`
- **Lines:** 5-103
- **Category:** Reliability
- **Recommendation:** Mirror prod healthchecks.

#### F-106 — `nginx.conf` HTTPS server lacks `Content-Security-Policy` header
- **File:** `nginx/nginx.conf`
- **Lines:** 84-90
- **Category:** Security
- **Description:** App-level CSP is set by SecurityHeadersMiddleware, but nginx fallback is missing.
- **Recommendation:** Add a baseline CSP header at the nginx layer.

#### F-107 — Compose files use deprecated `version: "3.9"` key
- **File:** `docker-compose.yml`, `docker-compose.prod.yml`
- **Category:** Reliability
- **Recommendation:** Delete the `version:` line.

#### F-108 — Mixed DDL + DO-block in `4bd35db2ef64` migration
- **File:** `backend/alembic/versions/4bd35db2ef64_add_auto_req_approval_required.py`
- **Lines:** 102-112
- **Category:** Migration
- **Description:** Combines `op.create_table` calls with `DO $$ … IF NOT EXISTS` block. The IF-NOT-EXISTS guard makes the migration silently no-op on partially-applied databases — masks drift.
- **Recommendation:** Replace with `op.add_column(...)` and rely on Alembic's tracking.

#### F-109 — Hash-named migration `4bd35db2ef64` deviates from `000N` convention
- **File:** `backend/alembic/versions/4bd35db2ef64_add_auto_req_approval_required.py`
- **Category:** Migration
- **Recommendation:** Rename to `0008_add_auto_req_approval.py`.

#### F-110 — `approval-toggle-patches.py` is a "patch" file containing inert string blobs
- **File:** `approval-toggle-patches.py`
- **Lines:** 1-122
- **Category:** Cross-cutting
- **Description:** Despite `.py` extension, contains only triple-quoted strings of hand-written diffs; no executable code. The matching Alembic migration is already in place.
- **Recommendation:** Delete or move to `docs/archive/`.

#### F-111 — Test smoke script `test-astra-api.ps1` has hard-coded `mason / Admin123!` and `password123`
- **File:** `test-astra-api.ps1`
- **Lines:** 81-91
- **Category:** Security
- **Description:** Reveals the seed user's likely password; if BASE points at any reachable env, the script silently authenticates and creates artifacts.
- **Recommendation:** Read credentials from env vars; refuse to run if BASE points at a "prod" hostname.

---

### LOW

#### F-112 — `fix-routes.ps1`, `wire-forcegraph.ps1` are one-shot string-replace migration scripts left at repo root
- **File:** `fix-routes.ps1`, `wire-forcegraph.ps1`
- **Category:** Cross-cutting
- **Description:** Idempotent, not destructive, but dead code once the changes are merged.
- **Recommendation:** Delete or move to `scripts/archive/`.

#### F-113 — `RefreshToken.revoked == False  # noqa: E712` should use `.is_(False)`
- **File:** `backend/app/services/auth_manager.py`
- **Lines:** 79
- **Category:** Backend
- **Recommendation:** `.is_(False)`.

#### F-114 — `STAKEHOLDER` and `DEVELOPER` permission sets are empty dict literals
- **File:** `backend/app/services/rbac.py`
- **Lines:** 75-79
- **Recommendation:** Use `set()` with explicit comment, or remove from matrix.

#### F-115 — `quality_report` fallback returns score 0 without warning when import fails
- **File:** `backend/app/services/reports/quality_report.py`
- **Lines:** 26-31
- **Recommendation:** Log a warning at module-import time.

#### F-116 — `impact_analyzer` returns ImpactReport with empty req object on missing requirement
- **File:** `backend/app/services/ai/impact_analyzer.py`
- **Lines:** 286-296
- **Recommendation:** Return None or raise ValueError; let router translate to 404.

#### F-117 — `services/reports/__init__.py` eager-imports openpyxl/reportlab/python-docx
- **File:** `backend/app/services/reports/__init__.py`
- **Lines:** 1-32
- **Recommendation:** Lazy-import inside the registry.

#### F-118 — `BusProtocol.ONEWIRE = "oneWire"` is camelCase; rest of enum is snake_case
- **File:** `backend/app/models/interface.py`
- **Lines:** 526
- **Recommendation:** Normalize to `"one_wire"`.

#### F-119 — `report_icd` defined out of order in `reports.py` without the section banner
- **File:** `backend/app/routers/reports.py`
- **Lines:** 217-228
- **Recommendation:** Group with other report-generators; add the matching banner.

#### F-120 — `seed_project` router prefix `/dev` collides with `dev_router` (different gating)
- **File:** `backend/app/routers/seed_project.py`
- **Lines:** 35
- **Recommendation:** Move to `/admin/seed-project` and add proper auth (paired with F-004).

#### F-121 — Optional-routers / models loop in `main.py` silently swallows ImportError
- **File:** `backend/app/main.py`
- **Lines:** 33-51, 62-79
- **Description:** A typo in any module path silently skips the router/model with no log line. This is what is currently masking F-002.
- **Recommendation:** Log a warning on import failure; consider failing-startup for "core-but-optional" routers in production.

#### F-122 — `GET /auth/me` returns full UserResponse (drift risk for future fields)
- **File:** `backend/app/routers/auth.py`
- **Lines:** 96-98
- **Recommendation:** Use a narrower `MeResponse` schema explicitly listing safe fields.

#### F-123 — `ConnectorType` / `BusProtocol` TS unions end with `| string` (defeats the union)
- **File:** `frontend/src/lib/interface-types.ts`
- **Lines:** 43-57, 122
- **Description:** Adding `string` to a union of literals collapses to `string`.
- **Recommendation:** Drop `| string`; use a separate `*_custom?: string` field (already exists on Connector).

#### F-124 — `services/audit_service` swallows audit-failure in `requirements.py:83-87` (auth.login_success)
- **File:** `backend/app/routers/auth.py`
- **Lines:** 83-87
- **Description:** Audit-failure on successful login is silently dropped. Combined with F-031 — should not be swallowed.
- **Recommendation:** Let `record_event` raise; it has its own retry semantics.

#### F-125 — `mfa.py` qrcode optional import uses `# type: ignore`
- **File:** `backend/app/services/mfa.py`
- **Lines:** 69
- **Category:** Style
- **Description:** Acceptable but worth a real conditional-import pattern.

#### F-126 — `AddConnectionModal` is a fully-implemented unused modal (~5KB dead code)
- **File:** `frontend/src/app/projects/[id]/interfaces/page.tsx`
- **Lines:** 217-291
- **Description:** Comment at line 1192-1195 explicitly says it was "removed in Phase 3a".
- **Recommendation:** Delete.

#### F-127 — `byLevel` mutation aliases the API object
- **File:** `frontend/src/app/projects/[id]/page.tsx`
- **Lines:** 410-416
- **Recommendation:** Be explicit about whether to recompute.

#### F-128 — `AutoGrowAmbiguityModal.resolveCurrent` has tangled state-machine workaround
- **File:** `frontend/src/components/AutoGrowAmbiguityModal.tsx`
- **Lines:** 131-220
- **Description:** Self-described as "paranoia-level workaround"; uses `setTimeout(0)` to flush.
- **Recommendation:** Refactor to compute next state from current render state, not via closure variables inside setState callbacks.

#### F-129 — `PinMapSvg` renders N×N SVG nodes inline for harnesses with hundreds of wires
- **File:** `frontend/src/app/projects/[id]/interfaces/harness/[harnessId]/page.tsx`, `connection/[connectionId]/page.tsx`
- **Lines:** 166-194 (harness)
- **Recommendation:** Virtualize beyond ~200 wires, or render via single `<canvas>`.

#### F-130 — `status-dashboard` reports omit `format` query param
- **File:** `frontend/src/app/projects/[id]/reports/page.tsx`
- **Lines:** 158-160
- **Description:** Special-cased to skip `format` for status-dashboard.
- **Recommendation:** Always send the user-clicked format.

#### F-131 — `report_history` placement, comment-block separator inconsistency in `reports.py`
- **File:** `backend/app/routers/reports.py`
- **Category:** Style
- **Description:** Cosmetic-only.

#### F-132 — `AISuggestion.metadata_json` shadows-by-name SA reserved attribute
- **File:** `backend/app/models/embedding.py`
- **Lines:** 87
- **Description:** SA tolerates `metadata_json` (only `metadata` is reserved on Declarative Base) — flagged for awareness.

#### F-133 — `Optional[str]` schemas without `= None`
- **File:** `backend/app/schemas/interface.py`
- **Description:** Pydantic v2 brittle pattern; `from_attributes=True` saves it most of the time.
- **Recommendation:** Add `= None`.

#### F-134 — `_populate_pin_mating` resolves only mating UNIT, not mating PIN
- **File:** `backend/app/routers/interface.py`
- **Lines:** 3585-3601
- **Description:** Frontend has to issue extra lookups to render full mating info.
- **Recommendation:** Extend helper to return `mating_connector_designator` + `mating_pin_number`.

#### F-135 — `get_block_diagram` positions are hardcoded; user layout cannot persist
- **File:** `backend/app/routers/interface.py`
- **Lines:** 3266-3316
- **Recommendation:** Allow `layout` query param or persist `layout_x/y` on System.

---

### INFO

#### F-136 — Migration chain has cosmetic 0003/0004 numeric gap (chain itself is sound)
- **File:** `backend/alembic/versions/0005_add_embedding_tables.py`
- **Lines:** 18
- **Description:** `0005` declares `down_revision="0002"`, skipping numeric labels 0003/0004. The chain is a valid linear DAG: `0001 → 0002 → 0005 → 0006 → 0007 → 4bd35db2ef64`.
- **Recommendation:** Add a brief docstring note in `0005`, or renumber in a single cleanup commit.

#### F-137 — `init.sql` installs `uuid-ossp` and `pg_trgm` outside Alembic
- **File:** `database/init.sql`
- **Lines:** 8-9
- **Description:** Correct location for `CREATE EXTENSION` (Postgres can't run it inside a transaction with other DDL), but Alembic has no record. A fresh DB created without docker-entrypoint (RDS, manual `pg_create`) will lack the extensions.
- **Recommendation:** Document in SECURITY.md/README. Optionally add a startup guard checking `pg_extension`.

#### F-138 — `models/__init__.py` does not re-export workflow models
- **File:** `backend/app/models/__init__.py`
- **Lines:** 10-15
- **Description:** Only interface symbols are re-exported. `from app.models import ApprovalWorkflow` would fail. Tied to F-002.

#### F-139 — `requirements.list_requirements` cap is exactly 200, matching the documented backend ceiling
- **File:** `backend/app/routers/requirements.py`
- **Lines:** 117-136
- **Description:** Confirmation that no rule-of-200 violation exists. All frontend `limit:` values are ≤200.

#### F-140 — Existing `_audit` tamper-evident chain in `audit_service` is well-designed (note for posterity)
- **File:** `backend/app/services/audit_service.py`
- **Description:** Hash-chain implementation is sound; the gap is the missing DB-level append-only triggers (F-009).

#### F-141 — SHALL-statement Appendix-C enforcement lives in `services/quality_checker` only
- **File:** `backend/app/services/quality_checker.py`
- **Description:** AutoRequirementGenerator at `services/interface/auto_requirements.py` was not deeply audited from the router-side. A focused review of that file would confirm whether NASA Appendix C patterns are enforced when interface auto-requirements are generated.

---

## Cross-Cutting Concerns

### API Contract Drift

The frontend uses 14 logical endpoint groups via `lib/{api,ai-api,ai-writer-api,impact-api,interface-api,auth}.ts` plus inline calls in pages. Cross-checked against the 100+ backend routes inventoried by the routers agent; **no method/path/shape mismatches found** beyond the items already captured as findings (F-005 audit-page params bug, F-026 sidebar limit:1 misuse, F-029 unit_summary missing system_id).

| Backend Route | Frontend Caller | Mismatch |
|---|---|---|
| `GET /workflows/*`, `POST /workflows/*` (all) | none | **Backend missing entirely** (F-002). Router never registered. |
| `GET /workflows/signatures/*` | none | Same — entire signature subsystem absent. |
| `POST /workflows/seed-default/{project_id}` | none | Same. |
| `GET /audit/log` | `audit/page.tsx:49` | Frontend passes `params` (undefined) → backend gets no filters (F-005). |
| `GET /interfaces/units` (returns `UnitSummary[]`) | `interface-api.ts:65`, `interfaces/page.tsx:570-586` | Frontend expects `system_id` on each unit; `UnitSummary` doesn't include it; page issues N getSystem() calls to backfill (F-029). |
| `GET /requirements/?limit=1` | `Sidebar.tsx:138` | Frontend reads `r.data.length` (always 0/1) as the project's total — wrong contract (F-026). |
| `POST /imports/template` | `import/page.tsx:174` (via `api.ts:135` likely uses GET) | Backend declares POST but the operation is read-only (F-071). |
| `POST /interfaces/io/import/template` | `interface-api.ts:298` | Same as above. |
| `POST /audit/verify`, `GET /audit/export`, `GET /audit/package` | `audit/page.tsx:61,72,89,106` | Endpoints exist on both sides; consistent. |
| All `/interfaces/*` CRUD | `interface-api.ts` | Method/path matches; field-level drift exists in `Wire.signal_type` (F-093) and other detail responses but no method/path mismatch. |

### Enum Drift

| Backend Enum | Frontend Mirror | Mismatch |
|---|---|---|
| `WorkflowStatus`, `InstanceStatus`, `SignatureMeaning` | none | Backend declares Postgres enum with **upper-case** member names due to missing `values_callable` (F-007); even if the frontend tried to mirror, it would have to use UPPER-CASE strings, mismatching the `.value` lower-case used everywhere else. |
| `ConnectorType` (`models/interface.py`) | `ConnectorType` (`interface-types.ts:43-57`) | TS union ends with `\| string` (F-123) — defeats the literal union for type safety. |
| `BusProtocol` (`models/interface.py:526`) | `BusProtocol` (`interface-types.ts:122`) | Backend has `ONEWIRE="oneWire"` (camelCase outlier) while every other value is snake_case (F-118). TS union also ends with `\| string`. |
| `RequirementStatus`, `RequirementType`, `RequirementPriority`, `UserRole`, `RequirementLevel`, `VerificationMethod`, `VerificationStatus` | (no explicit TS mirrors found beyond loose strings) | Frontend uses literal strings; should mirror the backend enums for type safety (companion to F-092). |
| All other interface-module enums | `interface-types.ts:1-194` | Mirror correctly (lowercase values match backend's `values_callable`). |

### Status Code Consistency

| Pattern | Files | Issue |
|---|---|---|
| DELETE returns 200 with `{"status":"preview"}` body when `confirm=false` | `interface.py` delete_unit/bus/message/harness/wire/endpoint | F-047 — conflates verb semantics. |
| DELETE returns 200 with body (not 204) for soft-delete | `admin.py:139` deactivate_user | F-073 — verb/contract mismatch. |
| Bulk operations return 200 with mixed success/error in body | `interface.py:2785-2836` generate_harness_requirements (also auto_wire `auto_result["error"]`) | F-072 — silent partial-success on 200. |
| 4xx vs 5xx distinction generally clean | rest of routers | OK. |

### Auth Flow

- Frontend `lib/api.ts` axios interceptor attaches `Authorization: Bearer <token>` from `localStorage.astra_token` and redirects to `/login` on 401.
- Backend uses `Depends(get_current_user)` consistently for normal endpoints.
- **Gaps:** F-004 (seed-project unauthenticated), F-072 (template download unauthenticated), F-017 (webhooks unauthenticated by design but no signature check), F-014 (no project membership check anywhere), F-015 (register accepts arbitrary role), F-016 (no lockout), F-031 (no failed-login audit).

### Docker / Env

- Container names `astra-{service}-1` match the convention. Hardcoded reference in `add_interface_enum_values.ps1` (F-013) breaks if compose project name differs.
- `.env` correctly gitignored.
- `.env.example` missing 18+ vars (F-010).
- `.env` has placeholder ENCRYPTION_KEY (F-021).
- Postgres exposed on host 5432 (F-104).
- Dockerfiles run as root (F-011, F-012).
- Dev compose lacks healthchecks for backend/frontend (F-105).
- nginx CSP missing (F-106).

### Logging

- No PII or secrets logged that I could find — but `_run_background_ai` (F-030) passes the DB URL with embedded password as a positional arg, which would appear in tracebacks.
- Several `except Exception: pass` swallows mute legitimate errors (F-031, F-081, multiple in `routers/interface.py`).
- Optional-router import-failures in `main.py` are silent (F-121) — this is what is currently hiding F-002.

### Orphaned Endpoints / Calls

**Backend routes with no obvious frontend caller** (verified by searching `frontend/src/lib/*.ts` and `app/**/*.tsx`):

- `POST /auth/register` — no frontend register page exists; the API client exposes it (`api.ts:41`) but no UI calls it. **Possibly intentional** (admin-only registration).
- `GET /audit/verify`, `GET /audit/package` — only `/audit/log` and `/audit/export` are called from `audit/page.tsx`. Other two are inventoried in api.ts but unused.
- `GET /requirements/ai/stats` and `GET /ai/stats` — duplicate functionality. Only `/ai/stats` is called by frontend; `/requirements/ai/stats` is orphaned.
- `GET /interfaces/buses/{bus_pk}/utilization` — no frontend caller surfaces this.
- `GET /interfaces/messages/{msg_pk}/byte-map` — no frontend caller.
- `POST /interfaces/connectors/{conn_pk}/pins/auto-generate` — no frontend caller (`interface-api.ts` exposes it but pages don't call it).
- `POST /interfaces/impact/preview`, `POST /interfaces/impact/execute` — exposed in interface-api.ts but no UI flow visible.
- `GET /interfaces/io/export/{units,harness,all-wiring,icd-data}` — exposed but no obvious "Export" button surface in audited pages.
- `POST /workflows/*` and `GET /workflows/*` — backend doesn't even exist (F-002); irrelevant orphan.

**Frontend calls with no backend route:** none found beyond F-002 (workflows endpoints).

---

## TODO / FIXME / Risk-Marker Inventory

Surprisingly clean codebase — only a handful of risk markers across 196 files.

| File | Line | Marker | Context |
|---|---|---|---|
| `frontend/src/components/AutoGrowAmbiguityModal.tsx` | 183 | comment "paranoia-level workaround" | "the `latestXXX` closure variables above are the actual source of truth for the call" — see F-128. |
| `backend/tests/test_interface.py` | 448 | `# noqa` | "handled by fixture chain". |
| `backend/tests/conftest.py` | 34, 45-86 (≈14 instances) | `# noqa: E402,F401,F403` | Intentional import-ordering suppressions. |
| `backend/alembic/env.py` | 24 | `# noqa: F401` | Model imports for autogenerate. |
| `backend/app/main.py` | 63 | `# noqa: F401,F403` | `from app.models import *` — pulls workflows.py side effects (see F-002). |
| `backend/app/services/auth_manager.py` | 79 | `# noqa: E712` | `RefreshToken.revoked == False` — see F-113. |
| `backend/app/services/auth_providers/__init__.py` | 78-81 | `# noqa: F401, E402` | Provider self-registration. |
| `backend/app/services/mfa.py` | 69 | `# type: ignore` | Optional qrcode import — F-125. |
| `backend/alembic/versions/4bd35db2ef64_*.py` | 7-9 | docstring "FIXED: Removed autogenerate DROP TABLE" | Self-documents that autogenerate-drift was happening — supports F-002 diagnosis. |

No `TODO` / `FIXME` / `HACK` / `XXX` strings in shipping code (the "XXX" hit in `AutoGrowAmbiguityModal.tsx:183` is part of a variable-name pattern `latestXXX`, not a risk marker). No `// @ts-ignore` / `// @ts-expect-error` in frontend.

---

## Appendix A — File Inventory

Total files scanned: **196** (excluding `node_modules/`, `.next/`, `__pycache__/`, `.venv/`, `dist/`, `build/`, `.git/`, lock files, log files, sqlite/db binaries).

| Directory | Files | Notes |
|---|---|---|
| `backend/app/routers/` | 19 (+ 1 `.bak`) | `interface.py` is the dominant file at 4051 lines; `interface_import.py` 1700 lines |
| `backend/app/models/` | 11 | `interface.py` 1796 lines; `__init__.py` defines core domain |
| `backend/app/schemas/` | 6 | |
| `backend/app/services/` | 16 (top-level) + sub-packages | `ai/` (10), `auth_providers/` (5), `integrations/` (5), `interface/` (4), `reports/` (8 + 1 `.bak`) |
| `backend/app/middleware/` | 4 | |
| `backend/alembic/versions/` | 6 (active migrations) | 0001, 0002, 0005, 0006, 0007, 4bd35db2ef64 |
| `backend/app/scripts/` | 3 | shell scripts for migrate/rollback |
| `backend/tests/` | 7 | |
| `frontend/src/app/` | 28 page.tsx files (+ 2 `.bak`) | `interfaces/` is the biggest module (10 sub-routes) |
| `frontend/src/components/` | 11 .tsx files | a11y, ai, impact, layout, traceability, AutoGrowAmbiguityModal |
| `frontend/src/lib/` | 10 .ts/.tsx files | including duplicate `auth.ts` + `auth.tsx` (F-024) |
| `frontend/src/hooks/` | 1 | `useAnnounce.ts` |
| `frontend/__tests__/`, `frontend/src/tests/` | 3 | |
| Root (`docker-compose*.yml`, `Dockerfile`s, `nginx/nginx.conf`, `database/init.sql`, `database/migrations/audit_append_only.sql`, `.env`, `.env.example`, `.gitignore`, `SECURITY.md`, ad-hoc `.ps1`/`.py`/`.sh`/`.sql`) | ~25 | including the binary `4_24_2026_SQL_ASTRA.sql` (F-006) |

Approximate LOC by language: Python ~38k, TS/TSX ~22k, SQL ~3k, YAML/conf ~0.5k.

---

## Appendix B — Audit Methodology

**Scanned:**
- All Python source under `backend/app/` (every router, model, schema, service, middleware) and `backend/tests/` (read-only review for security smells; not as "missing tests" — testing is out of scope).
- All Python source in `backend/alembic/` (env.py and every active version file).
- All TypeScript / TSX under `frontend/src/`.
- Root-level Dockerfiles, compose files, nginx config, `.env*`, `.gitignore`, `SECURITY.md`, `database/init.sql`, `database/migrations/audit_append_only.sql`, ad-hoc `.ps1`/`.py`/`.sh` scripts.
- Binary file `4_24_2026_SQL_ASTRA.sql` was identified by header inspection (not parsed).

**Skipped (per audit prompt):**
- `node_modules/`, `.next/`, `__pycache__/`, `.venv/`, `venv/`, `dist/`, `build/`, `.git/`, `*.lock`, `*.log`, `*.sqlite`, `*.db`.
- Generated files (`*.generated.*`, OpenAPI client output) — none observed.
- Migrations older than 0001 — N/A (0001 is the first revision).
- Stylistic preferences and Tailwind class ordering.
- Test coverage gaps ("untested code") — explicitly out of scope.

**Tooling:**
- Direct file reads via the harness's `Read` tool.
- `Grep` for cross-codebase patterns (SQLEnum without `values_callable`, mutable defaults, `except Exception:`, `await file.read()`, `password`, `from app.models.workflow`, etc.).
- Four parallel sub-agents covering: (1) backend routers + main + middleware + config; (2) backend services + models + schemas; (3) Alembic + Docker + env + nginx + root scripts; (4) Next.js frontend (lib + components + pages).

**Limitations / Items Not Verified:**
- Did not run any code, did not start containers, did not connect to a DB.
- Did not verify whether the `4_24_2026_SQL_ASTRA.sql` dump is git-tracked (recommended: `git ls-files | grep 4_24`).
- Did not deeply audit `services/interface/auto_requirements.py` for Appendix C SHALL-pattern enforcement (F-141).
- Did not deeply audit `services/integrations/{jira,doors,azure_devops}.py` connector implementations beyond top-level structure.
- Frontend behavior not validated in a browser — UI-affecting findings (F-005, F-026, F-027, F-028, F-029, F-088, F-094, F-095, F-096, F-097) are based on static reading.

`AUDIT COMPLETE — 121 findings written to AUDIT_FINDINGS.md`
