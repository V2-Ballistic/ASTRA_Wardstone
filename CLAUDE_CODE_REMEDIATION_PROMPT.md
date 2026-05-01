# ASTRA Remediation Plan — Claude Code Prompt

**Source:** `AUDIT_FINDINGS.md` (121 findings: 6 Critical, 32 High, 53 Medium, 24 Low, 6 Info)
**Target codebase root:** `C:\Users\Mason\Documents\ASTRA`
**Branch strategy:** Create one branch per phase: `fix/phase-1-critical`, `fix/phase-2-security`, etc. Commit after each finding (or each tightly-coupled cluster) so the history is bisectable.
**Deliverable:** All fixes applied + a tracking document at `C:\Users\Mason\Documents\ASTRA\REMEDIATION_LOG.md` updated after every finding (template in §10).

---

## 1. Operating Rules (read before touching any file)

1. **Read `AUDIT_FINDINGS.md` first.** Every fix here references a finding ID (F-001 through F-141). Look the finding up before editing — the audit doc has line numbers, evidence, and impact.
2. **Order matters.** Phases are dependency-ordered. Do not skip ahead. F-007 cannot be fixed until F-002 is complete because F-007 patches a file that F-002 *relocates*. Several other pairs are similarly coupled — call-outs noted inline.
3. **Never run `alembic revision --autogenerate`.** The codebase has known schema drift (F-013 ad-hoc script). Autogenerate will emit `op.drop_table(...)` for tables it doesn't recognize. For all schema work in this remediation, write migrations by hand.
4. **For trivial column additions, prefer direct SQL** against `astra-db-1`: `ALTER TABLE … ADD COLUMN IF NOT EXISTS …` — but **also** capture the change in a hand-written Alembic migration so the schema is reproducible from `alembic upgrade head`.
5. **Syntax-validate every Python file** before saving: `python3 -c "import ast; ast.parse(open('path').read())"`. Mason has been bitten by paste-induced `SyntaxError` in this codebase before.
6. **Do not run `docker compose down -v`** under any circumstance — that wipes the dev DB and forces full user re-creation.
7. **Backend rate limit is 200**, not 1000. If any new code paginates, cap at 200.
8. **PostgreSQL enums require `values_callable`.** Whenever you add or modify a `SQLEnum(...)` column, include `values_callable=lambda x: [e.value for e in x]`.
9. **Deliver complete drop-in files.** Mason's standing preference. No patches, no partial diffs in chat — write the full file.
10. **Update `REMEDIATION_LOG.md` after every finding.** One row per finding: ID, status, files touched, commit SHA, verification result. Template in §10.
11. **Don't fix issues you weren't asked to.** If you spot something new while editing, add an entry to `REMEDIATION_LOG.md` under "New findings discovered during remediation" — do NOT silently fix it. Mason needs the audit trail.

---

## 2. Cross-Cutting Deliverables (build first, used throughout)

These are new shared modules that multiple findings depend on. Build all four before starting Phase 1, because Phase 1 fixes import them.

### 2.1 `backend/app/dependencies/project_access.py` — covers F-014 and unblocks F-046, F-051, F-052, F-058
A single FastAPI dependency that any router can apply. Loads the project, asserts the caller is owner OR a `ProjectMember` OR `role == ADMIN`. Two flavors:
- `project_member_required(project_id: int)` — for endpoints that take `project_id` directly (path/query/body).
- `entity_project_member_required(entity_loader)` — for endpoints whose project_id has to be resolved from an entity ID (e.g., `requirement_id` → `requirement.project_id`).

Both raise `HTTPException(403, "Not a project member")` on miss. Cache the membership lookup per-request via `request.state` so multiple deps in the same call don't re-query.

### 2.2 `backend/app/middleware/body_size_limit.py` — covers F-018
ASGI middleware enforcing a 50 MB request body cap (configurable via `MAX_UPLOAD_BYTES` env var, default `52428800`). Stream-aware — reject before the handler reads. Register in `main.py` ABOVE the routers. Returns 413 Payload Too Large.

### 2.3 `backend/app/services/quality/nasa_terms.py` — covers F-079
Single source of truth for `PROHIBITED_TERMS` (with deduplication — current "sufficient" duplicate gets removed). Both `services/quality_checker.py` and `services/reports/quality_report.py` must import from this module.

### 2.4 `backend/app/services/security/record_hash.py` — covers F-008
Helper that produces a canonical hash of a signed record's content. Signature: `compute_record_hash(entity_type: str, entity: Any) -> str`. For `requirement` it digests `req_id + version + statement + title`. Pluggable per-entity-type so workflow can add more later.

---

## 3. Phase 1 — Critical Foundation (Day 1, blocks everything else)

**Branch:** `fix/phase-1-critical`
**Ordering rationale:** F-002 must come first because it relocates the file F-007 patches. F-001 and F-003 are independent one-liners — do them next. F-014 is the largest single change — schedule it last in this phase but before any High-severity work because dozens of High/Medium findings simplify once the dependency exists.

### 3.1 F-002 — Workflow file-swap + naming **[CRITICAL]**
**Goal:** Make the workflow + e-signature subsystem actually load.

Steps:
1. The file at `backend/app/routers/workflow.py` contains MODELS. Move its contents to `backend/app/models/workflow.py` (singular). Verify no logic change, just relocation.
2. The file at `backend/app/models/workflows.py` contains the ROUTER. Move its contents to `backend/app/routers/workflows.py` (plural — match `main.py:37`).
3. Delete the two old files (`backend/app/routers/workflow.py` and `backend/app/models/workflows.py`).
4. Update three imports — they currently say `from app.models.workflow import …` and that path didn't exist before; after step 1 it does, so these now resolve correctly:
   - `backend/app/services/signature_service.py:18`
   - `backend/app/services/workflow_engine.py:22`
   - the moved router file's own internal imports (verify line ~37)
5. In `backend/app/models/__init__.py`, re-export workflow models so `from app.models import ApprovalWorkflow` works (covers F-138).
6. In `backend/app/main.py`, replace the silent `try/except (ImportError, AttributeError): pass` blocks (lines 33-51 and 62-79) with `logger.warning("Failed to load optional router %s: %s", path, exc)`. This addresses F-121 in the same edit.
7. Confirm with `python3 -c "from app.models.workflow import ApprovalWorkflow; from app.routers.workflows import router; print('OK')"` from `backend/`.

**Verification:**
- `docker exec astra-backend-1 python -c "from app.routers.workflows import router; print(len(router.routes))"` returns >0.
- `docker exec astra-backend-1 curl -s localhost:8000/openapi.json | python -c "import sys,json; d=json.load(sys.stdin); print([p for p in d['paths'] if '/workflows' in p])"` lists the workflow paths.

### 3.2 F-001 — JWT signed with SecretStr wrapper **[CRITICAL]**
**File:** `backend/app/services/auth_manager.py:54`

One-line change: `settings.SECRET_KEY` → `settings.SECRET_KEY.get_secret_value()`.

Add a unit test at `backend/tests/test_auth_manager_jwt.py` that issues a token via `create_access_token` and decodes it with the *intended* key — fails before the fix, passes after.

### 3.3 F-003, F-067 — Encryption fallback + production guard **[CRITICAL+HIGH, treat as one cluster]**
**Files:** `backend/app/services/encryption.py`, `backend/app/services/mfa.py`, `backend/app/config.py`

1. In `config.py:enforce_production_guards()`, add: refuse to start when `ENVIRONMENT=production` and `ENCRYPTION_KEY` is empty *or* equals `"dev-fallback-encryption-key"` *or* equals `"test-secret-key-not-for-production"`.
2. In `services/encryption.py:_get_fernet()`, remove the `"dev-fallback-encryption-key"` literal fallback. If both env vars are missing, raise `RuntimeError("ENCRYPTION_KEY not configured")` — the production guard catches prod, dev gets a loud crash that's easy to fix.
3. In `services/encryption.py:decrypt_field`, replace the silent `InvalidToken: return ciphertext` branch with `logger.warning(...)` gated on `os.getenv("ALLOW_PLAINTEXT_LEGACY", "false") == "true"`. Default behavior: re-raise.
4. In `services/mfa.py:22-24`, replace the byte-truncate-and-pad key derivation with a call to `services.encryption._derive_key(...)` — same PBKDF2 derivation as field encryption. Salt: `b"astra-mfa-v1"`.
5. Make `_SALT` in `encryption.py` configurable via `ENCRYPTION_KEY_SALT` env var; default to existing static value for backward compatibility.

### 3.4 F-004 — Lock down `/dev/seed-project/{id}` **[CRITICAL]**
**Files:** `backend/app/routers/seed_project.py:35,446`, `backend/app/main.py:30,164`

1. In `main.py`, move the `seed_project_router` registration into the `if not is_prod:` block at lines 55-60, alongside `dev_router`.
2. Add `current_user: User = Depends(require_permission("projects.create"))` to `seed_project_data` at `seed_project.py:446`.
3. Replace the `existing_count >= 20` idempotency check with a "seed marker" — add a `is_seed_data: bool` column to `Requirement` (Phase 2 migration), or for now check for a sentinel `Requirement(req_id="SEED-MARKER", ...)` and short-circuit if present.
4. Pair with F-120: change router prefix from `/dev` to `/admin/seed-project`.

### 3.5 F-005 — Audit log page params bug **[CRITICAL, frontend, 5-second fix]**
**File:** `frontend/src/app/projects/[id]/audit/page.tsx:49`

Change `{ params }` to `{ params: p }`. Verify by loading the audit log page in the dev environment — filters and pagination should now work.

### 3.6 F-006 — Binary `pg_dump` in repo root **[CRITICAL]**
**File:** repo root `4_24_2026_SQL_ASTRA.sql`

1. `cd C:\Users\Mason\Documents\ASTRA && git ls-files | grep 4_24_2026` — confirms tracking status.
2. If tracked: `git rm --cached 4_24_2026_SQL_ASTRA.sql && git commit -m "fix(security): untrack pg_dump per F-006"`. Then `git filter-repo --path 4_24_2026_SQL_ASTRA.sql --invert-paths` to scrub history. **Coordinate with Mason before force-push** — this rewrites history.
3. Move the file out of the repo entirely (e.g., `C:\Users\Mason\Documents\ASTRA-backups\`).
4. Append to `.gitignore`:
   ```
   *.sql.dump
   *.pgdump
   [0-9]*_SQL_*.sql
   *.bak
   ```
   (The `*.bak` line also handles F-023.)
5. Tell Mason to `pg_restore -l ../ASTRA-backups/4_24_2026_SQL_ASTRA.sql` and review what was in it; if it contains real user data, credential rotation is required.

### 3.7 F-014 — Project membership enforcement **[CRITICAL, large surface]**

Build `dependencies/project_access.py` per §2.1, then apply it to **every** function in this list. Each application is `current_user: User = Depends(get_current_user), _membership = Depends(project_member_required)` — the dep loads project_id from path/query/body. For entity-keyed endpoints, use `entity_project_member_required` and pass the entity loader.

Routers to modify (line ranges from audit doc F-014):
- `routers/projects.py:51-65, 84-106, 151-229, 367`
- `routers/requirements.py:117, 140, 303, 440, 464, 482, 553, 574, 604`
- `routers/baselines.py:99, 120, 149, 193`
- `routers/interface.py:142-202, 267, 306-575, 658-1019, 1358-1505, 1689-1889, 2035-2205, 2838-3016, 3398-3447`
- `routers/integrations.py:142-218`
- `routers/dashboard.py:15`
- `routers/impact.py:62, 209`
- `routers/reports.py:75-194, 201-215`

After this, F-046, F-051 (still also needs the project_id filter fix), F-052, F-058 are auto-covered — note the partial coverage in their entries below.

**Verification:** Add a single integration test that creates two projects (A and B) with different members. Caller is a member of A only. Assert: every endpoint that takes `project_id=B.id` returns 403 — paste the route list above, run them all programmatically.

---

## 4. Phase 2 — Security Hardening + Compliance (Days 2-3)

**Branch:** `fix/phase-2-security`
**Prereq:** Phase 1 merged.

### 4.1 F-015 — `/auth/register` accepts arbitrary role
**File:** `backend/app/routers/auth.py:33-52`

Choose option (b) from the audit recommendation: keep the route public but force `role = UserRole.DEVELOPER` server-side, ignoring any role in the request body. Add a separate admin-gated endpoint `POST /admin/users` (likely already exists — verify) for elevated-role creation.

### 4.2 F-016 + F-031 + F-124 — Account lockout + failed-login audit
**Files:** `backend/app/routers/auth.py:59-89`, `backend/app/services/account_lockout.py`

1. Wire `services/account_lockout.py` into the `login` path: call `lockout.check(username)` before password verification; call `lockout.register_failure(username)` on `verify_password` False; call `lockout.clear(username)` on success.
2. In the failure branch, emit `audit_service.record_event("auth.login_failed", actor=username, ip=request.client.host, ua=request.headers.get("user-agent"))`. **Do not** wrap in `try/except: pass`.
3. Remove the `try/except Exception: pass` around the success-side audit (covers F-124).
4. Add `MAX_LOGIN_ATTEMPTS` and `LOCKOUT_DURATION_MINUTES` to `.env.example` (covers part of F-010).

### 4.3 F-017 — Webhook signature verification
**File:** `backend/app/routers/integrations.py:359-381`

For Jira: validate the `x-atlassian-webhook-identifier` and (if configured) HMAC the body with the per-config webhook secret. Reject 401 on miss. For Azure DevOps: validate basic-auth header matches the per-config secret. Replace the hardcoded `integration_config_id=0` by resolving it from a path slug `/integrations/{slug}/jira/webhook`.

### 4.4 F-021 + F-104 — `.env` placeholders + Postgres host binding
**Files:** `.env`, `docker-compose.yml`

1. Generate real secrets: `openssl rand -hex 32` for `SECRET_KEY` and `ENCRYPTION_KEY`. Replace placeholders in `.env`.
2. In `docker-compose.yml:21-22` and `:36`, change `"5432:5432"` and pgAdmin port to `"127.0.0.1:5432:5432"` and `"127.0.0.1:5050:80"` respectively.

### 4.5 F-010 — `.env.example` parity
**File:** `.env.example`

Add every variable that any code path reads from `os.getenv` or `Settings` but isn't already in the example. From the audit: `ENCRYPTION_KEY`, `ENCRYPTION_KEY_SALT`, `MAX_LOGIN_ATTEMPTS`, `LOCKOUT_DURATION_MINUTES`, `RATE_LIMIT_DEFAULT/AUTH/IMPORT`, `ALLOWED_HOSTS`, `SESSION_TIMEOUT_MINUTES`, `AUTH_PROVIDER`, `AUTH_MFA_REQUIRED`, all `OIDC_*`, all `SAML_*`, `PIV_CA_BUNDLE_PATH`, `MAX_UPLOAD_BYTES`, `ALLOW_PLAINTEXT_LEGACY`. Group with comment headers (`# --- Auth ---`, `# --- Encryption ---`, etc.). For each, add a one-line comment indicating whether it's mandatory in production.

### 4.6 F-011 + F-012 — Dockerfile hardening
**Files:** `backend/Dockerfile`, `frontend/Dockerfile`

Backend: pin to `python:3.12.7-slim-bookworm@sha256:<digest>` (look up the digest from Docker Hub at fix time), add `RUN useradd --uid 1000 -m astra && mkdir -p /app/uploads && chown -R astra /app`, add `USER astra`, add `HEALTHCHECK CMD curl -fsS http://localhost:8000/health || exit 1`.

Frontend: convert to multi-stage `deps → build → run`. Run stage uses `USER 1000:1000`, `CMD ["npm","start"]`. Add a HEALTHCHECK on `/`.

### 4.7 F-013 — Convert ad-hoc enum script to Alembic migration
**Files:** `add_interface_enum_values.ps1` → `backend/alembic/versions/0008_extend_interface_enums.py` (or use the next sequential number after the chain renaming in F-109).

For each `ALTER TYPE ADD VALUE`, wrap in `with op.get_context().autocommit_block(): op.execute("ALTER TYPE … ADD VALUE IF NOT EXISTS '…'")`. After the migration is in, delete the `.ps1`.

### 4.8 F-009 — Audit-append-only triggers via Alembic
**File:** new `backend/alembic/versions/0009_audit_append_only_triggers.py`

`op.execute()` the contents of `database/migrations/audit_append_only.sql`. Downgrade drops the triggers. Run order: must be after `0001` (audit_log table exists). Verify with `psql astra -c "\d+ audit_log"` — should show the `prevent_audit_update`, `prevent_audit_delete`, `prevent_audit_truncate` triggers.

### 4.9 F-018 — File-upload size + zip-bomb defenses
**Files:** new `middleware/body_size_limit.py` (per §2.2), `routers/imports.py:246-276`, `routers/interface_import.py:589-606,786-802`

1. Register the middleware in `main.py` BEFORE the routers.
2. In each upload handler: validate `Content-Type` against an allowlist (`application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`, `text/csv`). Sniff with `python-magic` (add to requirements). Pass `read_only=True` to `openpyxl.load_workbook` (already done in some places — verify everywhere).
3. After parsing, cap row count at 50,000 and sheet count at 25; reject with 413 on overflow.
4. Strip cell values starting with `=`, `+`, `-`, `@` before re-export (formula injection defense).
5. Sanitize filenames in responses with `werkzeug.utils.secure_filename` (or equivalent — it's already a transitive dep).

### 4.10 F-019 + F-020 — Streaming reports + audit log export
**Files:** `routers/reports.py:75-194`, `routers/audit.py:120-171`, `routers/interface_import.py:1127-1695`

1. For audit-log CSV export: replace `db.query(AuditLog)…all()` with a server-side cursor. Return `StreamingResponse(generator, media_type="text/csv")`. JSON path: emit NDJSON one record per line.
2. For reports: introduce a job table (`report_jobs(id, project_id, status, format, file_path, created_at, finished_at)`). Each report POST kicks off a `BackgroundTask` that writes to disk under `/app/reports/`. Return `{"job_id": …}`. Add `GET /reports/jobs/{id}` for polling. Add `GET /reports/jobs/{id}/download` for the file (with project-membership auth).
3. Switch `openpyxl.Workbook(write_only=True)` for any report >100 rows.
4. Pre-fetch with `joinedload`/`selectinload` to eliminate the per-row `db.query` in `interface_import` exporters.

### 4.11 F-007 — Workflow enums missing `values_callable`
**File:** `backend/app/models/workflow.py` (post-F-002 location), lines ~71, ~123, ~175

Add `values_callable=lambda x: [e.value for e in x]` to the three `SQLEnum` declarations: `ApprovalWorkflow.status`, `WorkflowInstance.status`, `ElectronicSignature.signature_meaning`. Add a migration that ALTERs the existing Postgres enum types to lowercase if any data already exists in those tables (likely none, since the subsystem hasn't been reachable until F-002).

### 4.12 F-008 — E-signature record-content binding (21 CFR Part 11 §11.70)
**Files:** `backend/app/models/workflow.py`, `backend/app/services/signature_service.py`, new `services/security/record_hash.py` (per §2.4)

1. Add `record_hash: str` column to `ElectronicSignature`. Migration in same file as F-007's enum migration.
2. At sign time (`signature_service.request_signature`), compute `record_hash` via the new helper and persist on the signature row.
3. Update `ElectronicSignature.compute_hash` to include `record_hash` in the digest payload.
4. In `verify_signature`, recompute the entity's current `record_hash` and reject if it differs from the stored one.
5. Document the supported entity_types (start with `requirement`).

### 4.13 F-022 — Production guard on destructive downgrades
**Files:** `backend/alembic/versions/0001_initial_schema.py:404-435`, `backend/alembic/versions/0007_interface_module.py:958-992`

At the top of each `downgrade()`:
```python
import os
if os.getenv("ENVIRONMENT") == "production" and not os.getenv("ASTRA_ALLOW_DESTRUCTIVE_DOWNGRADE"):
    raise NotImplementedError("Refusing destructive downgrade in production. Set ASTRA_ALLOW_DESTRUCTIVE_DOWNGRADE=true to override.")
```

### 4.14 F-023 — Delete `.bak` files
Delete: `backend/app/routers/interface.py.bak`, `backend/app/routers/workflow.py.bak` (if it survived F-002), `backend/app/services/reports/change_history.py.bak`, `frontend/src/app/projects/[id]/verification/page.tsx.bak`, `frontend/src/app/projects/[id]/requirements/[reqId]/page.tsx.bak`. `.gitignore` already covers future ones (added in F-006 step).

### 4.15 F-024 + F-025 — Frontend auth module consolidation
**Files:** `frontend/src/lib/auth.ts`, `frontend/src/lib/auth.tsx`

1. Diff the two files. The richer one (auth.ts per the audit — has `is_active`, RBAC helpers, `PermissionGate`) is the keeper.
2. Delete `auth.tsx`.
3. Rename `auth.ts` → `auth.tsx` (it returns JSX).
4. Add `'use client';` as line 1.
5. Wrap the `localStorage.setItem` at line 167 in `if (typeof window !== 'undefined')`.

### 4.16 F-026 — Sidebar requirement count
**File:** `frontend/src/components/layout/Sidebar.tsx:136-140`

Switch to `dashboardAPI.stats(projectId)` and read `total_requirements`. Drop the `limit:1` call.

### 4.17 F-027 — Login flow uses `useAuth().login()`, not localStorage
**File:** `frontend/src/app/login/page.tsx`

All four success paths: replace `localStorage.setItem('astra_token', t); window.location.href='/'` with `await login(username, password); router.push('/')`. For SSO, use `router.replace('/')` to scrub `?token=` from the URL; validate via `/auth/me` before persisting.

### 4.18 F-028 — Delete legacy `[unitId]` route
Delete the entire `frontend/src/app/projects/[id]/interfaces/[unitId]/` folder. `[id]/interfaces/unit/[unitId]/` is the survivor.

### 4.19 F-029 — Add `system_id` to `UnitSummary`
**Files:** `backend/app/schemas/interface.py` (UnitSummary), `frontend/src/lib/interface-types.ts:225-236`, `frontend/src/app/projects/[id]/interfaces/page.tsx:570-586`

1. Backend: add `system_id: int` to `UnitSummary`.
2. Frontend: same field added to the TS type.
3. Replace the N-call `getSystem` fan-out with `Object.fromEntries(units.map(u => [u.id, u.system_id]))`.

### 4.20 F-030 — Drop `db_url` passthrough
**File:** `backend/app/routers/requirements.py:226-243, 285-296, 354-365`

Remove the `db_url` argument from `_run_background_ai` and from the three `BackgroundTask` invocations. The function imports `SessionLocal` directly — no URL needed.

### 4.21 F-032 — Persist report history
**Files:** `backend/app/routers/reports.py`, new model `ReportHistoryEntry` (or piggyback on the `report_jobs` table from F-019)

Replace the module-level `_report_history` list with DB persistence. Scope every query by project membership. This entry collapses naturally into F-019's job table — implement them together.

### 4.22 F-033 — Move audit emit to AFTER cascade commit
**File:** `backend/app/routers/interface.py`

For every delete handler listed in F-033 (`delete_system`, `delete_unit`, `delete_connector`, `delete_bus`, `delete_message`, `delete_harness`, `delete_endpoint`):
1. Wrap the cascade query/commit in `try/except` with `db.rollback()` on exception.
2. Move the `_audit(...)` call to AFTER `db.commit()` succeeds.
3. Re-raise after rollback so the caller still gets an error.

### 4.23 F-034 — Token-tied import preview
**File:** `backend/app/routers/interface_import.py:786-1120`

At preview time, store parsed-and-validated rows in a new `import_previews(token, project_id, payload_json, expires_at)` table (token = `secrets.token_urlsafe(32)`, expires in 30 minutes). Return token in preview response. Confirm endpoint accepts ONLY the token, not a re-uploaded file. Reject expired tokens.

### 4.24 F-035 — `TraceLink` integrity
**Files:** `backend/app/models/__init__.py:213-228`, new migration

1. Add ForeignKey constraints to `source_id` and `target_id` — but they're polymorphic, so use a CHECK constraint validated at the application layer instead. Add `project_id: int` (not nullable, FK to projects).
2. Add `Index("ix_trace_source", "source_type", "source_id")`, `Index("ix_trace_target", "target_type", "target_id")`.
3. Add `UniqueConstraint("source_type", "source_id", "target_type", "target_id", "link_type")`.
4. In `routers/projects.py:create_trace_link`: validate both endpoints exist, both belong to `current_user`'s project, and the project_ids match.
5. Migration handles existing data: for each existing trace_link, set project_id from source entity; drop rows where source/target no longer exists; report counts.

### 4.25 F-036 — External-IdP signature step-up
**Files:** `backend/app/services/auth_providers/__init__.py:38-50`, `backend/app/services/signature_service.py:51`

For users with `hashed_password == "EXTERNAL_IDP_NO_LOCAL_PASSWORD"`, route signature requests through an OIDC `prompt=login` step-up flow. New endpoint `POST /workflows/signatures/idp-step-up` that returns a one-time signature token after fresh IdP re-auth. `signature_service.request_signature` accepts either password+verify_password OR signature token.

### 4.26 F-037 — PIV cert chain validation
**File:** `backend/app/services/auth_providers/piv.py:109-137`

Use `cryptography.x509.verification` (cryptography ≥ 42) to walk the chain against the configured CA bundle. OCSP/CRL check when env demands it. Until implemented in production-ready form, refuse to register the PIV provider when `ENVIRONMENT=production`:

```python
if os.getenv("ENVIRONMENT") == "production" and not <full chain validation available>:
    raise RuntimeError("PIV provider requires full chain validation in production")
```

### 4.27 F-038 — Mutable defaults
Sweep every file in F-038. Pattern:
- `Column(JSON, default={})` → `Column(JSON, default=dict)`
- `Column(JSON, default=[])` → `Column(JSON, default=list)`
- Pydantic `: List[str] = []` → `: List[str] = Field(default_factory=list)`
- Pydantic `: Dict[…] = {}` → `: Dict[…] = Field(default_factory=dict)`

Files: `models/__init__.py`, `models/embedding.py`, `models/integration.py`, `models/interface.py`, `models/audit_log.py`, `models/ai_models.py`, `schemas/__init__.py`, `schemas/interface.py`, `schemas/impact.py`, `schemas/ai_embeddings.py`. Use `grep -rn "default=\[\]\|default={}" backend/app/` to find all occurrences and confirm none are missed.

---

## 5. Phase 3 — Medium Severity (Days 4-6)

**Branch:** `fix/phase-3-medium`
**Prereq:** Phase 2 merged.

Group these into focused commits — they're individually small but related sets touch the same files.

### 5.1 N+1 Query Sweep — F-039, F-040, F-041, F-042, F-043, F-044
For each finding, replace the per-row `db.query(...)` with a single eager-loaded query (`joinedload`/`selectinload`) or a GROUP BY aggregation. The audit doc lists exact line numbers per finding. Verification: log SQL with `SQLALCHEMY_ECHO=true`, confirm query count is constant (1-3 queries) regardless of N.

### 5.2 F-045 — pgvector for embeddings
**Files:** new migration `00XX_add_pgvector_embeddings.py`, `backend/app/services/ai/duplicate_detector.py`, `backend/app/services/ai/trace_suggester.py`

1. Migration: `with op.get_context().autocommit_block(): op.execute("CREATE EXTENSION IF NOT EXISTS vector")`. Then `ALTER COLUMN requirement_embeddings.embedding TYPE vector(1536) USING embedding::text::vector`. (Confirm the embedding dimension by checking your model output.)
2. `duplicate_detector` and `trace_suggester`: use Postgres `<=>` cosine-distance operator with index, replace pure-Python pairwise loop with one matmul or one SQL query.

### 5.3 F-046 — Auto-requirement approve/reject project ownership
**File:** `backend/app/routers/interface.py:2838-2957, 2960-3016`

After F-014 the dependency exists; here, additionally validate every `requirement_id` in the bulk payload belongs to the same project that the dep authorized. If mixed, reject 400. Use real `project_id` in audit event.

### 5.4 F-047, F-048 — DELETE preview/destructive separation
**File:** `backend/app/routers/interface.py`

For all six handlers in F-047: extract the preview logic into a new `GET /interfaces/{entity}/{id}/delete-impact` endpoint. The DELETE handler always deletes (with optional `force=true` for cascade). Include `delete_field` in this refactor so it gets the audit emit and confirm gate (covers F-048).

### 5.5 F-049, F-050 — Wire/Connection rollup + req_link audit
**File:** `backend/app/routers/interface.py`

F-049: in `update_wire`, if pin changes, call `maybe_delete_connection_for_wire` on old state then `_upsert_connection` on new. Emit audit.
F-050: add `_audit("interface_req_link.created"|".deleted", ...)` to create/delete handlers.

### 5.6 F-051 — Interface coverage project filter
**File:** `backend/app/routers/interface.py:3398-3447`

Add `project_id` filter to all four count queries. The simplest path: join through entity types that carry `project_id` (Interface/Unit/etc.). If frequent, consider adding a `project_id` column to `InterfaceRequirementLink` in a follow-up migration.

### 5.7 F-052 — `list_req_links` parameter validation
**File:** `backend/app/routers/interface.py:3349-3377`

Require `entity_type+entity_id` as a pair, OR `requirement_id` alone — reject if neither. Always filter by `project_id` (from the membership dep).

### 5.8 F-053 — `clone_requirement` transaction + audit
Single transaction (one `db.commit()` at the end) wrapped in try/except with rollback. Add `_audit("requirement.cloned", ...)`.

### 5.9 F-054 — `_run_background_ai` commit
**File:** `backend/app/routers/requirements.py:226-243`

`with SessionLocal() as db:` context manager, explicit `db.commit()` after `cache_analysis`.

### 5.10 F-055 — CSV import per-row savepoints
**File:** `backend/app/routers/imports.py:418-429`

Wrap each row in `db.begin_nested()`. Outer commit promotes only successful savepoints. Track per-row failures and return them in the response.

### 5.11 F-056 — Interface confirm uses validator
**File:** `backend/app/routers/interface_import.py:951`

Run the preview validator at confirm time too. Skip rows that fail validation (return them in the response). Stop fabricating `SPARE_{n}` names.

### 5.12 F-057 — `trigger_sync` partial-failure rollback
**File:** `backend/app/routers/integrations.py:294-327`

Wrap the connector call in `db.begin_nested()`. On exception, rollback the savepoint (drops the partial requirement inserts), then commit only the SyncLog entry.

### 5.13 F-058 — covered by F-014
Verify after Phase 1 merge.

### 5.14 F-059 — `create_baseline` transaction safety
**File:** `backend/app/routers/baselines.py:38-94`

Wrap snapshot loop in try/except with rollback. After commit, verify `count(BaselineRequirement where baseline_id=X) == expected_count`; if mismatch, log alarm and return 500.

### 5.15 F-060, F-061, F-062 — Seed bug cluster
**File:** `backend/app/routers/seed_project.py`

F-060: insert verification first, flush, then create the link with `verif.id`.
F-061: snapshot the actual requirement fields (not hardcoded "approved"). Match the `POST /baselines` schema.
F-062: replace `count >= 20` with a sentinel-marker check.

### 5.16 F-063 — Persistent JWT blacklist
**File:** `backend/app/services/auth_manager.py:106-114`

New table `revoked_tokens(jti, exp, revoked_at)`. Check on every request via the `get_current_user` dep. Periodic cleanup of expired entries.

### 5.17 F-064 — Redis-backed rate limiter
**File:** `backend/app/middleware/rate_limiter.py:60-117`

If Redis is acceptable, switch token bucket to Redis. Use exact `API_PREFIX + tier` matching, drop substring matching. If Redis is not yet in stack, document the worker-count multiplier prominently in the middleware docstring AND in `SECURITY.md` until Redis lands.

### 5.18 F-065 — Workflow timeout escalation
**File:** `backend/app/services/workflow_engine.py:280-335`

Either implement escalation (notification + role flag + DB record), or remove `auto_escalate_to_role` from the model and schema entirely. Don't ship a half-implemented field.

### 5.19 F-066 — `TrustedHostMiddleware`
**Files:** `backend/app/config.py:50-51`, `backend/app/main.py:142-148`

Register `TrustedHostMiddleware(allowed_hosts=settings.ALLOWED_HOSTS.split(","))`. Add to `enforce_production_guards()`: refuse to start in prod with `ALLOWED_HOSTS="*"`.

### 5.20 F-068 — Token lifetime + refresh + revocation
**Files:** `backend/app/config.py:39-40`, `backend/app/services/auth_manager.py`

1. Lower `ACCESS_TOKEN_EXPIRE_MINUTES` to 30.
2. Implement refresh token issue/rotate flow.
3. Wire revocation list (F-063) into the auth dep.
4. Either honor `SESSION_TIMEOUT_MINUTES` (idle timeout via last-activity tracking) or remove the unused config.

### 5.21 F-069 — Loud RBAC import
**File:** `backend/app/routers/admin.py:25-32` (and others — `grep -rn "from app.services.rbac"` to find all)

Replace silent fallback with `logger.critical("RBAC unavailable; refusing to start"); raise`. Or, if RBAC must remain optional, log CRITICAL at startup and expose a `/health/rbac` endpoint that returns the active strategy.

### 5.22 F-070 — `confirm_import` Request type
**File:** `backend/app/routers/interface_import.py:786-1118`

Add `request: Request` to the function signature (FastAPI `Request`). Pass through to `_audit`.

### 5.23 F-071, F-072 — `/imports/template` GET + auth
**Files:** `backend/app/routers/imports.py:457-464`, `backend/app/routers/interface_import.py:297-300`

Change `@router.post("/template")` to `@router.get("/template")`. Add `current_user: User = Depends(get_current_user)`. Update frontend callers in `lib/api.ts` and `lib/interface-api.ts` to use GET.

### 5.24 F-073 — `deactivate_user` semantics
**File:** `backend/app/routers/admin.py:139-154`

Rename to `POST /users/{id}/deactivate` (returns 200) AND cascade: set `ProjectMember(user_id=X)` rows to inactive (or delete them).

### 5.25 F-074 — `_next_id` race
**Files:** `backend/app/routers/interface.py:113-127`, `imports.py:362-367`, `projects.py:372-388`

Create a per-project sequence table `id_sequences(project_id, prefix, next_value)` with `SELECT … FOR UPDATE` semantics. Or use Postgres sequences (`CREATE SEQUENCE` per project at project-creation time). Update all three call sites.

### 5.26 F-075 — Requirement uniqueness + composite indexes
**File:** `backend/app/models/__init__.py:153-189` + new migration

`__table_args__ = (UniqueConstraint("project_id", "req_id", name="uq_req_per_project"), Index("ix_req_project_status", "project_id", "status"), Index("ix_req_project_type", "project_id", "req_type"), Index("ix_req_project_owner", "project_id", "owner_id"))`. Migration uses direct SQL via `op.execute` to add constraint, since autogenerate is forbidden.

### 5.27 F-076 — `ondelete` strategies
**File:** `backend/app/models/__init__.py:139, 203, 235, 254` + migration

`Project.owner_id` → `ondelete="SET NULL"` (preserve project history when user is deleted).
`SourceArtifact.project_id` → `ondelete="CASCADE"`.
`Verification.requirement_id` → `ondelete="CASCADE"`.
`RequirementHistory.requirement_id` → `ondelete="CASCADE"`.

Sweep `models/interface.py` and `models/audit_log.py` for similar gaps as long as you're in there.

### 5.28 F-077 — Numeric for engineering-unit math
**File:** `backend/app/models/interface.py:1452-1457`

Change `Float` → `Numeric(20, 9)` for `scale_factor`, `offset_value`, `lsb_value`, `min_value`, `max_value`, `resolution`, `accuracy`. Migration uses `ALTER COLUMN … TYPE NUMERIC(20,9)`.

### 5.29 F-078 — Drop `WireHarness` `(from_connector_id, to_connector_id)` UniqueConstraint
**File:** `backend/app/models/interface.py:1543-1545` + migration

Drop the constraint. `harness_endpoints.lru_connector_id` already has a UNIQUE constraint that does the right thing now that the endpoint model exists.

### 5.30 F-079 — covered by §2.3 deliverable

### 5.31 F-080 — Cron audit IP/UA marker
**File:** `backend/app/services/audit_service.py:79-83`

When `get_request_context()` returns `{}`, set `action_detail["context"] = "cron"` and `action_detail["host"] = socket.gethostname()`.

### 5.32 F-081 — AI quality issue logging
**File:** `backend/app/services/ai/quality_analyzer.py:82`

Replace `except Exception: continue` with `except Exception as exc: logger.debug("Skipping malformed issue: %s", exc); continue`.

### 5.33 F-082 — SAML cert/key context manager
**File:** `backend/app/services/auth_providers/saml.py:36-38`

`with open(cert_file) as f: cert = f.read()`. Same for key file.

### 5.34 F-083 — `_persist_report` transaction safety
**File:** `backend/app/services/ai/impact_analyzer.py:897-920`

Explicit `db.flush()` before commit. Truncate `report_json` to 1 MB. Cap captured-items count at 1000.

### 5.35 F-084 — Replace `require()` with normal imports
**Files:** All in F-084.

`let aiAPI: any = null; try { aiAPI = require('@/lib/ai-api').aiAPI; } catch {}` → `import { aiAPI } from '@/lib/ai-api'`. Gate runtime feature flag on `aiAPI.isAvailable`. The `require()` pattern bundles unconditionally anyway, so this is purely a type/cleanliness fix.

### 5.36 F-085, F-086, F-087 — Bulk frontend endpoints
Add three new backend endpoints (and matching frontend lib functions):
- `GET /verifications?project_id=X` — returns all verifications for project in one query (powers F-085).
- `GET /interfaces/req-links?project_id=X&auto_generated=true` — powers F-086.
- `POST /ai/trace-suggestions/project?project_id=X` — project-wide trace suggestions (powers F-087). Or, if expensive, paginate with explicit "Showing first N of M" UI.

Frontend pages then drop the batched-with-delay pattern.

### 5.37 F-088 — ForceGraph performance
**File:** `frontend/src/components/traceability/ForceGraph.tsx:117-210, 418-440`

Move force simulation to a Web Worker (preferred) OR split iterations across `requestAnimationFrame` so the main thread stays responsive. Key edges by stable id (e.g., `${edge.source}-${edge.target}-${edge.type}`), not array index.

### 5.38 F-089 — Surface fetch errors
**File:** `frontend/src/app/projects/[id]/interfaces/page.tsx:548-595`

Set an error state in the catch block; render an error banner above the page.

### 5.39 F-090 — Explicit toast severity
**Files:** F-090 list

Update `flash`/toast helper to take `severity: 'success'|'error'|'info'` explicitly. Audit all call sites and pass severity. Stop inferring from message text.

### 5.40 F-091 — Replace native confirm/alert
**Files:** F-091 list

Use the existing modal/`flash()` patterns from elsewhere in the codebase. No new dependency needed.

### 5.41 F-092 — Typed response interfaces
Define interfaces (`DashboardStats`, `CoverageReport`, `BaselineDetail`, `AISuggestion`) in `frontend/src/lib/types.ts` (or co-locate in respective lib files). Replace `useState<any>(null)` with typed state.

### 5.42 F-093 — `Wire.signal_type`
**File:** `frontend/src/app/projects/[id]/interfaces/harness/[harnessId]/page.tsx`, `frontend/src/lib/interface-types.ts`

Add `signal_type?: SignalType` to `Wire` interface. Drop the `(w as any).signal_type` casts.

### 5.43 F-094, F-095, F-096, F-097 — A11y sweep
F-094: add `aria-label` to every icon-only button in the audit list.
F-095: pair `<label htmlFor="x">` with `<input id="x">` everywhere — pervasive sweep.
F-096: requirements tree gets `role="tree"`, `role="treeitem"`, `aria-expanded`, `aria-level`, arrow-key navigation handler.
F-097: pin/wire color indicators get a small letter/glyph adjacent (e.g., "P" for power, "S" for signal).

### 5.44 F-098, F-099, F-100, F-101, F-102, F-103
F-098: add `react-window` or `@tanstack/react-virtual`. Use only when row count > 100.
F-099: replace fake progress with spinner; put `clearInterval` in `finally`.
F-100: track `levelManuallyChosen` in state; effect skips override when true.
F-101: `router.replace('/login?next=' + encodeURIComponent(pathname))`. Login flow honors `?next` and pushes there on success.
F-102: AbortController per the pattern in `requirements/page.tsx:380-432`.
F-103: `withStats.length === 0 ? 0 : sum/withStats.length`.

### 5.45 F-105, F-106, F-107
F-105: dev compose backend + frontend HEALTHCHECK mirroring prod.
F-106: nginx baseline CSP `default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self'; connect-src 'self'`.
F-107: delete `version: "3.9"` from both compose files.

### 5.46 F-108, F-109 — Migration cleanup
F-108: replace `DO $$ … IF NOT EXISTS` block with `op.add_column(...)`. The migration becomes a normal Alembic migration.
F-109: rename `4bd35db2ef64_add_auto_req_approval_required.py` → `0008_add_auto_req_approval.py` (or whatever sequential number the chain has reached after F-013 and F-009 add their own migrations). Update the `down_revision` of the next migration accordingly.

### 5.47 F-110, F-111 — Repo hygiene
F-110: delete `approval-toggle-patches.py`.
F-111: rewrite `test-astra-api.ps1` to read credentials from env vars (`ASTRA_TEST_USER`, `ASTRA_TEST_PASSWORD`). Refuse to run if `BASE` looks like prod (substring match `prod`, `production`).

---

## 6. Phase 4 — Low Severity & Cleanup (Day 7)

**Branch:** `fix/phase-4-cleanup`

Walk F-112 through F-135 individually — they're small. A few groupings:

- **Code hygiene** (F-112 delete `.ps1` migration scripts; F-113 `.is_(False)`; F-114 `STAKEHOLDER`/`DEVELOPER` empty sets; F-115 quality_report import warning; F-116 raise instead of empty obj; F-117 lazy-import reports; F-118 `BusProtocol.ONEWIRE` → `one_wire` value (with data migration); F-119 reorder `report_icd`; F-120 covered by F-004; F-121 covered by F-002; F-122 narrow `MeResponse` schema; F-123 drop `| string` from TS unions; F-124 covered by F-031; F-125 conditional import for qrcode).
- **Frontend cleanup** (F-126 delete `AddConnectionModal`; F-127 explicit recompute; F-128 refactor `AutoGrowAmbiguityModal`; F-129 virtualize PinMapSvg beyond 200 wires; F-130 always send `format`).
- **Style/awareness** (F-131, F-132 — comments only; no code change).
- **Schema/UX polish** (F-133 add `= None` to Optionals; F-134 extend `_populate_pin_mating`; F-135 persistable layout).

For F-118 specifically, since the value is in the database: the migration must `UPDATE bus … SET protocol='one_wire' WHERE protocol='oneWire'` AFTER the enum has both values, then drop the old value in a follow-up migration once data is migrated. Two-step migration is required by Postgres.

---

## 7. Phase 5 — Info-Severity & Follow-Ups (Day 7-8)

These are awareness items, not defects. Address as time allows:

- **F-136** — Optionally renumber the migration chain in a single cleanup commit (rename `0005` → `0003`, `0006` → `0004`, etc., and update `down_revision`). Cosmetic only; the chain works as-is.
- **F-137** — Document `init.sql` extensions in `SECURITY.md` and `README.md`. Add a startup guard that verifies `pg_extension` contains `uuid-ossp` and `pg_trgm`.
- **F-138** — covered by F-002.
- **F-139** — confirmation only, no action.
- **F-140** — design note, no action.
- **F-141** — Run a focused review of `services/interface/auto_requirements.py` to confirm NASA Appendix C SHALL pattern enforcement on auto-generated interface requirements. If gaps found, raise as new findings.

---

## 8. Verification Procedure (run after each phase)

Run this checklist before merging each phase branch.

**Backend smoke:**
```
docker exec astra-backend-1 python -c "from app.main import app; print(len(app.routes))"
docker exec astra-backend-1 alembic current
docker exec astra-backend-1 alembic check
docker exec astra-backend-1 pytest backend/tests -x -q
```

**Frontend smoke:**
```
cd frontend && npm run typecheck
cd frontend && npm run build
```

**Dependency-aware integration tests** (write these once, reuse each phase):
- `test_jwt_uses_real_secret` (F-001)
- `test_workflow_router_is_loaded` (F-002)
- `test_encryption_refuses_dev_fallback_in_prod` (F-003)
- `test_seed_project_requires_auth` (F-004)
- `test_audit_page_filters_work` (manual or e2e — F-005)
- `test_project_membership_blocks_cross_project_access` (F-014, biggest single test — covers ~30 endpoints)
- `test_register_ignores_role_field` (F-015)
- `test_login_lockout_after_max_attempts` (F-016)
- `test_failed_login_emits_audit_event` (F-031)
- `test_audit_log_immutability_triggers_installed` (F-009)
- `test_workflow_signature_binds_record_hash` (F-008)
- `test_upload_size_limit_returns_413` (F-018)

**Full audit re-run:** After Phase 4 merges, re-run the original audit prompt (`CLAUDE_CODE_AUDIT_PROMPT.md`) against the codebase and produce `AUDIT_FINDINGS_POST_REMEDIATION.md`. Compare. Open issues for any Critical/High findings that survived; Mediums/Lows that survived go on the backlog.

---

## 9. Safety Rails (read again before destructive ops)

- **Before any `git filter-repo`** (F-006), confirm with Mason. History rewrites require team coordination.
- **Before any `ALTER COLUMN … TYPE`** on a populated table, take a backup: `docker exec astra-db-1 pg_dump -U astra -d astra > /tmp/pre-migration-$(date +%s).sql` and `docker cp astra-db-1:/tmp/pre-migration-*.sql .` (move it OUT of the repo root so F-006's gitignore catches future ones).
- **Never run `alembic downgrade base`** during this remediation. Phase 2 adds a guard, but until then the down path destroys data.
- **Never `docker compose down -v`** — see operating rule #6.
- **For Phase 1 §3.7 (project membership)**, the test fixture must include a user who is in zero projects. Currently the seed user `mason` is admin of everything; create a new `dev_test_user` for negative tests.
- **F-118 (`BusProtocol.ONEWIRE` rename)** breaks any existing data with that value. Two-step migration required (see §6).

---

## 10. `REMEDIATION_LOG.md` Template

After every finding fix, append a row. Save to `C:\Users\Mason\Documents\ASTRA\REMEDIATION_LOG.md`.

```markdown
# ASTRA Remediation Log
**Started:** <YYYY-MM-DD>
**Source audit:** AUDIT_FINDINGS.md (commit <hash>)

## Progress

| Finding | Severity | Status | Files Touched | Commit | Verification | Notes |
|---|---|---|---|---|---|---|
| F-001 | Critical | ✅ Fixed | `backend/app/services/auth_manager.py`, `backend/tests/test_auth_manager_jwt.py` | `<sha>` | Test passes | — |
| F-002 | Critical | ✅ Fixed | (list moved/deleted/edited files) | `<sha>` | OpenAPI shows /workflows/* paths | Required pytest fixture update |
| F-014 | Critical | 🚧 In progress | `backend/app/dependencies/project_access.py`, 8 routers so far | — | — | reports.py + integrations.py remaining |
| ... | | | | | | |

## New findings discovered during remediation

| Date | Finding | Severity | Status |
|---|---|---|---|
| ... | ... | ... | ... |

## Phase status

- [ ] Phase 1 — Critical Foundation
- [ ] Phase 2 — Security Hardening + Compliance
- [ ] Phase 3 — Medium Severity
- [ ] Phase 4 — Low Severity & Cleanup
- [ ] Phase 5 — Info & Follow-ups
- [ ] Post-remediation audit re-run
```

---

## 11. Final Checks Before Declaring Remediation Complete

1. Every Critical and High finding has an entry in `REMEDIATION_LOG.md` marked ✅ or ⏸ Deferred (with explicit rationale and Mason's sign-off for any deferral).
2. `pytest` and `npm run build` both green.
3. `docker compose up` brings the stack up cleanly with the new `.env.example` filled in.
4. `alembic upgrade head` from a fresh DB produces a schema identical to the running dev DB (no drift).
5. The post-remediation audit re-run shows zero new Critical/High findings.
6. `git log --oneline` shows clean per-finding commits — bisectable.

When complete, print to stdout: `REMEDIATION COMPLETE — <N> findings resolved, <M> deferred, see REMEDIATION_LOG.md` and stop. Do not summarize in chat; the log is the deliverable.
