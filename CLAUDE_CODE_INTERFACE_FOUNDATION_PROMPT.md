# ASTRA Interface Foundation Refactor — Claude Code Execution Prompt

**Source spec:** `ASTRA_INTERFACE_FOUNDATION_REFACTOR.md` (ASTRA-TDD-INTF-002 v1.1)
**Target codebase root:** `C:\Users\Mason\Documents\ASTRA`
**Branch:** create `feat/interface-foundation` from current `main`
**Deliverable:** Spec executed in 8 phases, with `INTERFACE_FOUNDATION_LOG.md` updated per phase (template in §11)

---

## 1. Operating Rules (read before touching any file)

1. **Read the spec first.** Every phase below references sections of `ASTRA_INTERFACE_FOUNDATION_REFACTOR.md`. The spec is the source of truth — if anything in this prompt conflicts with the spec, the spec wins.
2. **The audit-remediation pacing rules carry forward.** Run continuously within a phase. Stop only for: (a) the phase verification gate, (b) genuinely destructive operations, (c) novel issues outside the spec, (d) plan ambiguity that affects later phases, (e) failures you can't resolve in 2-3 attempts. No routine check-ins.
3. **One commit per logical unit, not per file.** Schema models in one commit, migration in another, CRUD endpoints in another. Phase boundaries always commit + push.
4. **Never `alembic revision --autogenerate`.** Hand-write migration 0008 per spec §5. The codebase has known autogenerate-drift hazards.
5. **Syntax-validate every Python file** before committing: `python3 -c "import ast; ast.parse(open('path').read())"`. Mason has been bitten by paste-induced `SyntaxError` in this codebase before.
6. **Backend pagination cap is 200.** Every list endpoint enforces this.
7. **Every `SQLEnum(...)` includes `values_callable=lambda x: [e.value for e in x]`.** No exceptions.
8. **Project-membership dep stays applied.** All new project-scoped endpoints (catalog placement, sync proposals, coverage) get `Depends(project_member_required)` per the Phase 1 audit work in `dependencies/project_access.py`.
9. **Update `INTERFACE_FOUNDATION_LOG.md` per phase.** One entry per phase: status, files touched, commits, verification result, anomalies. Template in §11.
10. **Don't touch unrelated audit-remediation work.** F-045 (pgvector) stays deferred. Frontend test-infra cleanup stays deferred. The two follow-ups (delete-impact UI, /auth/refresh interceptor) stay deferred.
11. **Phases are independently safe rollback points.** If anything goes wrong mid-phase, you should be able to `git reset --hard` to the previous phase's tail commit without leaving the dev DB in a broken state. The hand-written migration's `down()` block is the safety net for Phase 1.

---

## 2. Pre-Flight Checks (run before Phase 1, do not skip)

Before creating the branch:

1. **Confirm clean working tree** on `main`:
   ```
   git status                # should be clean
   git log --oneline -5      # confirm Phase 4 audit work is the most recent merge
   ```

2. **Confirm DB is healthy:**
   ```
   docker compose ps                    # all services running
   docker exec astra-backend-1 alembic current   # should be at 0022 (or whatever Phase 4 left it at)
   docker exec astra-backend-1 pytest backend/tests/ -q   # should pass (modulo any deferred tests)
   ```

3. **Snapshot the dev DB** before any schema work:
   ```
   docker exec astra-db-1 pg_dump -U astra -d astra -F c -f /tmp/pre_intf002_$(date +%s).dump
   docker cp astra-db-1:/tmp/pre_intf002_*.dump ../ASTRA-backups/
   ```
   The dump goes OUTSIDE the repo (per F-006's `.gitignore` rule). This is the rollback floor for Phase 1.

4. **Branch from main:**
   ```
   git checkout main
   git pull origin main
   git checkout -b feat/interface-foundation
   git push -u origin feat/interface-foundation
   ```

5. **Initialize the log:**
   Create `INTERFACE_FOUNDATION_LOG.md` per the template in §11. Commit and push.

Stop after pre-flight. Report DB snapshot location, current alembic revision, and the new branch SHA. Wait for go before Phase 1.

---

## 3. Phase 1 — Schema & Migration (foundation)

**Spec:** §4 (full schema), §5 (migration), §8.4 (connection pool)
**Risk:** Highest of all phases. If migration is wrong, the dev DB needs the snapshot from §2.
**Rollback floor:** Pre-flight snapshot.

Execution order:

1. **Create new model files** per spec §4:
   - `backend/app/models/catalog.py` — Supplier, SupplierDocument, CatalogPart, CatalogConnector, CatalogPin, PendingCatalogImport, plus all enums (PartClass, LRUClass, LifecycleStatus, ConnectorGender, SignalType, SignalDirection, SupplierDocumentType, ExtractionStatus, PendingImportStatus).
   - `backend/app/models/req_sync.py` — RequirementSourceLink, RequirementSyncProposal, plus enums (SourceEntityType, SyncProposalType, SyncProposalStatus).
   - `backend/app/models/coverage_exception.py` — CoverageException model only (per §13.6).

2. **Modify existing files:**
   - `backend/app/models/interface.py` — add `Pin` columns per §4.6, add `Unit` columns per §4.7. Do NOT drop the existing `Pin.name` column (deprecated in 0008, dropped in 0009 only after grep confirms zero readers).
   - `backend/app/models/__init__.py` — re-export all new models so `from app.models import CatalogPart` works.
   - `backend/app/models/__init__.py` (Requirement) — add `sync_locked`, `sync_locked_reason`, `sync_locked_by_id`, `sync_locked_at`, `generation_template_id` per §4.9.

3. **Create Pydantic schemas** in `backend/app/schemas/catalog.py`, `backend/app/schemas/req_sync.py`, `backend/app/schemas/coverage.py`. Use `Field(default_factory=...)` for any list/dict defaults — F-038 from the audit work. Every `Optional[...]` field gets `= None` (F-133).

4. **Hand-write migration** `backend/alembic/versions/0023_supplier_catalog_layer.py` (note: spec calls it 0008 but the actual next number after audit Phase 4 is 0023 — verify with `alembic current` and use the correct sequential number; update the spec reference in commit message).

   Follow §5.1 ordering exactly:
   - Create all enum types FIRST. PostgreSQL doesn't allow forward references to enums.
   - Create tables in dependency order: suppliers → supplier_documents → catalog_parts (defer self-FK on parent_part_id) → catalog_connectors → catalog_pins → pending_catalog_imports → requirement_source_links → requirement_sync_proposals → coverage_exceptions.
   - ALTER TABLE for additions to units, pins, requirements.
   - Create indexes per §8.2 (GIN on JSONB, search indexes, etc.). Use direct `op.execute(...)` for GIN since they're not in Alembic's standard helper set.
   - Backfill steps 14-16 from §5.1 in that exact order.
   - **Migration must be reversible.** The `down()` block reverses every step. Test the down path on a snapshot before declaring the migration done.

5. **Update connection pool** per §8.4 — `backend/app/database.py` gets `pool_size=20`, `max_overflow=30`, `pool_pre_ping=True`, `pool_recycle=1800`.

6. **Run audit-immutability check.** Phase 2B of the audit installed `prevent_audit_update`/`delete`/`truncate` triggers on `audit_log`. Confirm migration 0023 doesn't try to mutate audit_log rows. If it does, stop — surface to me.

**Phase 1 verification gate:**

```
docker exec astra-backend-1 alembic upgrade head
docker exec astra-backend-1 alembic current      # should show 0023 (or whichever number)
docker exec astra-db-1 psql -U astra -d astra -c "\d suppliers"
docker exec astra-db-1 psql -U astra -d astra -c "\d catalog_parts"
docker exec astra-db-1 psql -U astra -d astra -c "\d requirement_source_links"
docker exec astra-db-1 psql -U astra -d astra -c "SELECT COUNT(*) FROM pins WHERE internal_signal_name IS NULL;"  # should be 0
docker exec astra-db-1 psql -U astra -d astra -c "SELECT COUNT(*) FROM requirement_source_links;"  # should equal old InterfaceRequirementLink count
docker exec astra-backend-1 pytest backend/tests/ -v
```

Plus a manual down/up test on a throwaway DB (the snapshot makes this safe):
```
docker exec astra-backend-1 alembic downgrade -1
docker exec astra-backend-1 alembic upgrade head
```

The full test suite must still pass. If green: stop, report, await go for Phase 2.

---

## 4. Phase 2 — Catalog CRUD Backend

**Spec:** §6 (RBAC), §9.1-9.4 (endpoints), §14 (placement service)
**Prereq:** Phase 1 merged-clean to the branch. Verification gate green.

Execution:

1. **Build `backend/app/services/catalog/placement.py`** per §14. The placement service is the heart of "Brand New" vs "Existing from catalog" — get it right and the UI work in Phase 3 falls into place.

2. **Build `backend/app/routers/catalog.py`** with endpoints from §9.1, §9.2 (except `/extract` and ingestion routes — those are Phase 7), §9.3, §9.4 (list/detail/edit only — approve/reject is Phase 7).

   Every endpoint:
   - Has the appropriate RBAC dep per §6 table. Use existing `require_permission(...)` from the auth layer.
   - Project-scoped endpoints additionally use `Depends(project_member_required)`.
   - Lists are capped at `limit=200` (422 above).
   - Mutations emit audit events using existing `audit_service.record_event(...)`.
   - The `DELETE /catalog/parts/{id}` endpoint refuses with 409 if the part is placed anywhere, unless `?admin_force=true` AND caller is admin.

3. **Register router** in `backend/app/main.py` `_optional_routers` list. The existing pattern logs a warning on import failure (per F-002 audit fix) — use that.

4. **Tests** in `backend/tests/test_catalog_crud.py`:
   - Create supplier, edit, delete (admin-only check).
   - Create catalog part with connectors and pins; verify cascades.
   - Place catalog part in project — confirm Unit + Connectors + Pins created with correct catalog linkage, mfr_pin_name copied, internal_signal_name defaulted to mfr_pin_name.
   - "Brand new" placement creates a global catalog entry (not project-local).
   - RBAC: stakeholder cannot create supplier (403), reviewer cannot edit catalog part (403), admin overrides part-in-use deletion check.
   - Project membership: a user not in project A cannot place a catalog part in project A.

   Use the enum-import pattern from Phase 1 audit work (`SystemType.SUBSYSTEM`, never `"subsystem"`).

5. **Tangential observation:** if any audit-Phase finding's remediation is touched while editing existing routers (e.g., interface.py for placement integration), do NOT re-fix it. Note in commit message.

**Phase 2 verification gate:**

```
docker exec astra-backend-1 pytest backend/tests/test_catalog_crud.py -v
docker exec astra-backend-1 pytest backend/tests/ -v       # full suite — zero regressions
```

Manual smoke per §17 Phase 2 acceptance: create Supplier → create CatalogPart with 2 connectors and 10 pins → place in SMDS → verify Unit + Pins created with correct catalog linkage.

If green: stop, report, await go for Phase 3.

---

## 5. Phase 3 — Catalog UI (no ingestion)

**Spec:** §14 (placement UX), §16 (frontend pages), dark theme convention
**Prereq:** Phase 2 merged-clean.

Execution:

1. **New pages** per §16:
   - `/catalog` — landing with three tabs (Suppliers / Parts / Pending Imports). Pending Imports tab shows empty-state until Phase 7.
   - `/catalog/suppliers/[id]` — supplier detail with documents + parts.
   - `/catalog/suppliers/new` — create form.
   - `/catalog/parts/[id]` — part detail (specs, connectors+pins, where-used, variants).
   - `/catalog/parts/new` — manual create catalog part.

2. **Build `<PlaceLruModal>`** per §14 with three tabs: "Catalog" (working in this phase), "Brand New" (working), "Upload ICD" (disabled with tooltip until Phase 7).

3. **Modify existing pages** per §16:
   - `/projects/[id]/interfaces/unit/[unitId]` — add catalog badge + variants link. The "sync proposal indicator" piece is Phase 5 — add a placeholder hook.
   - `/projects/[id]/interfaces/connector/[connectorId]` — dual-name pin table. Mfr column locked (read-only). Internal column editable. Bulk actions (rename pattern, copy mfr → internal).
   - `/projects/[id]/interfaces/page.tsx` — "Add Unit" CTA opens `<PlaceLruModal>`. "Connect Two Units" launches builder (Phase 4 — placeholder for now).
   - `/projects/[id]/interfaces/harness/[harnessId]` — wire rows show internal name primary + mfr name secondary.

4. **Type definitions** in `frontend/src/lib/catalog-types.ts` mirroring backend Pydantic schemas. Avoid the `| string` anti-pattern (F-123 audit fix).

5. **API client** in `frontend/src/lib/catalog-api.ts` using the central axios instance (auth interceptor, JWT attachment).

6. **ASTRA dark theme conformance** per Mason's standing pattern: `bg-astra-surface`, `border-astra-border`, `bg-astra-surface-alt`, blue accents on interactive, `rounded-xl` cards.

7. **A11y carry-forwards from Phase 3B audit work.** Icon-only buttons get `aria-label`. Form inputs paired with `<label htmlFor>`/`id`. No new color-only signaling.

**Phase 3 verification gate:**

```
cd frontend && npm run typecheck            # zero new errors
cd frontend && npm run build                # ✓ Compiled successfully
docker exec astra-backend-1 pytest backend/tests/ -v
```

Manual smoke per §17 Phase 3 acceptance: create supplier → create catalog part → place in SMDS → see dual-name pin table.

If green: stop, report, await go for Phase 4.

---

## 6. Phase 4 — Connection Builder + Three-Way Auto-Wire

**Spec:** §11 (algorithm), §15 (UX), §9.5 (endpoints)
**Prereq:** Phase 3 merged-clean.
**Risk:** Moderate. The auto-wire algorithm is invoked on user action, not on every commit, so a bug here doesn't poison the DB. But the three-way validation matrix (§11.3) is subtle — table-driven test it exhaustively.

Execution:

1. **Build `backend/app/services/interface/auto_wire.py`** per §11.2 algorithm. The three checks (name + direction + LRU endpoint) are each independently togglable for development but `enforce_lru_endpoints` defaults to True and "never off in prod." Document this in the docstring.

2. **Build `backend/app/services/interface/wire_heuristics.py`** — gauge/color suggestions based on signal type, current limits, etc. (§11 inputs).

3. **Direction compatibility matrix** per §11.3. Implement as a function, not a literal dict — the `*` wildcards in the spec are illustrative. Cover every pair of `SignalDirection` enum members explicitly. Unit-test every cell.

4. **Connection Builder backend endpoints** per §9.5:
   - `POST /interfaces/connection-builder/start`
   - `POST /interfaces/connection-builder/{interface_id}/auto-suggest-wires`
   - `POST /interfaces/connection-builder/{interface_id}/commit`

   All three under `req_eng+` RBAC + project-membership dep.

5. **Frontend components:**
   - `frontend/src/components/connection-builder/ConnectionBuilder.tsx` (wizard shell)
   - `frontend/src/components/connection-builder/PinPairingMatrix.tsx`
   - `frontend/src/components/connection-builder/HarnessAssignmentForm.tsx`
   - `/projects/[id]/interfaces/connect` page hosting the wizard

6. **Direction conflict UI** per §15.1. Red badge, plain-language explanation, three actions (Override admin / Mark target as input / Skip). LRU validation banner per §15.2.

7. **Tests** in `backend/tests/test_auto_wire.py`:
   - All three checks pass → wire proposed.
   - Name match fails → unmatched_source.
   - Name match ambiguous → ambiguous list, never auto-paired.
   - Direction conflict → direction_conflicts list.
   - LRU endpoint validation fails (cross-project) → lru_validation_errors.
   - Wildcard direction (UNKNOWN) → permissive but flagged.
   - Power↔Ground rejected.
   - Bidirectional pairs handled correctly.

**Phase 4 verification gate:**

```
docker exec astra-backend-1 pytest backend/tests/test_auto_wire.py -v
docker exec astra-backend-1 pytest backend/tests/ -v
cd frontend && npm run typecheck && npm run build
```

Manual smoke per §17 Phase 4 acceptance: connect Radar to C2 in SMDS in under 60 seconds, with a deliberate direction conflict caught.

If green: stop, report, await go for Phase 5.

---

## 7. Phase 5 — Reactive Requirement Sync Engine

**Spec:** §12 (full sync engine), §9.6 (endpoints)
**Prereq:** Phase 4 merged-clean.
**Risk:** Highest after Phase 1. SQLAlchemy event listeners fire on every commit. A bug can recursively trigger more proposals, hammer the DB, or silently corrupt requirements. Phase this very carefully.

Execution:

1. **Build the renderer first.** `backend/app/services/req_sync/renderer.py` reuses the existing template engine in `services/interface/auto_requirements.py`. Test it standalone before wiring listeners. Given a template_id and a list of source links, it produces a `RenderedRequirement` deterministically.

2. **Build the fan-out service.** `backend/app/services/req_sync/fan_out.py` per §12.2. Pay close attention to:
   - The "skip if sync_locked" branch.
   - The auto-apply policy table per §12.5 — every status × edit cell explicitly.
   - The "supersede prior PENDING proposals" logic in step 4.
   - Bulk-load requirements via `id IN (...)`. No N+1 (§8.3).

3. **Build the listeners.** `backend/app/services/req_sync/listener.py` per §12.1. Critical safety constraints:
   - Listeners run AFTER commit, never before. If a listener raises, the original transaction is already committed — log loudly and surface as a sync proposal of type=REGENERATE rather than crashing.
   - Listeners must be re-entrant safe. If applying a sync proposal triggers another listener (e.g., updating a requirement that has its own source links), the second-level fan-out must be detected and either skipped (preferred) or capped at depth=1.
   - Test in isolation: a unit test that fires the listener manually, asserts the proposal row, and confirms no infinite loop.

4. **Endpoints** per §9.6 in `backend/app/routers/req_sync.py`. Bulk accept must be transactional — all-or-none, atomic.

5. **Frontend:**
   - `/projects/[id]/req-sync` page per §12.6 three-pane layout.
   - sync_locked toggle on requirement detail page.
   - "X proposals pending" badge on project nav.

6. **Tests** in `backend/tests/test_req_sync.py` covering every case in §12.7. Add explicitly:
   - Listener doesn't fire when `sync_locked=True`.
   - Listener doesn't fire when status in (`cancelled`, `superseded`).
   - Recursive trigger is bounded (don't spin forever).
   - `pending_review` requirement is auto-applied silently AND emits an audit event so the change isn't invisible.
   - `approved` requirement creates a proposal, never auto-applies.

7. **Performance check:** §17 Phase 5 acceptance says "within 1 second." Time the fan-out on a project with 100+ source links. If >1s, profile and add an index or batch.

**Phase 5 verification gate:**

```
docker exec astra-backend-1 alembic check        # no schema drift introduced
docker exec astra-backend-1 pytest backend/tests/test_req_sync.py -v
docker exec astra-backend-1 pytest backend/tests/ -v
cd frontend && npm run typecheck && npm run build
```

Manual smoke per §17 Phase 5 acceptance: edit a wire data rate in SMDS → within 1 second the related auto-generated requirement appears in the sync proposals queue with correct old/new diff.

If green: stop, report, await go for Phase 6.

---

## 8. Phase 6 — Source Coverage Validator

**Spec:** §13 (full validator), §9.7 (endpoints)
**Prereq:** Phase 5 merged-clean.

Execution:

1. **Build `backend/app/services/coverage/source_validator.py`** per §13.3.

2. **Materialized view migration.** Per §13.4, create `mv_requirement_source_coverage`. Spec calls this "0008.5 (or fold into 0008)" — fold it into a separate sequential migration `0024_coverage_materialized_view.py` (or whatever the next number is). MVs can't be created inside the main migration because Alembic's autogenerate doesn't know about MVs anyway.

3. **Refresh service.** `backend/app/services/coverage/refresh.py`:
   - Triggered after batch source-link writes (the bulk-accept endpoint in Phase 5 should call this once per batch, not per row).
   - Scheduled refresh every 10 minutes via APScheduler or whatever cron-style mechanism the project uses.
   - Use `REFRESH MATERIALIZED VIEW CONCURRENTLY` to avoid locking reads.

4. **Coverage Exception model.** Already in `models/coverage_exception.py` from Phase 1. Verify the migration created the table.

5. **Endpoints** per §9.7 in `backend/app/routers/coverage.py`. Filing an exception requires `proj_mgr+`. Admin co-sign required for the exception to count toward coverage (per §13.6).

6. **Suggestion engine** per §13.5. Pattern-matching on requirement statement text. Keep this simple — it's a UX hint, not a contract.

7. **Frontend:**
   - `/projects/[id]/coverage` page per §13.7 — traffic light per level, sortable orphan table, suggested source type per row, link-to-source picker, exception filing flow with admin co-sign prompt.
   - Coverage badge in project nav.

8. **Tests** in `backend/tests/test_coverage.py`:
   - L1 orphan → severity ok.
   - L2 orphan → severity warning.
   - L3 orphan → severity error.
   - L4 with parent-trace to traced L3 → counted as covered.
   - L5 with active exception (admin-cosigned) → counted as covered.
   - L5 with exception but no admin co-sign → severity warning.
   - MV refresh after batch write picks up new links.

**Phase 6 verification gate:**

```
docker exec astra-backend-1 alembic upgrade head
docker exec astra-db-1 psql -U astra -d astra -c "SELECT * FROM mv_requirement_source_coverage LIMIT 5;"
docker exec astra-backend-1 pytest backend/tests/test_coverage.py -v
docker exec astra-backend-1 pytest backend/tests/ -v
cd frontend && npm run typecheck && npm run build
```

Manual smoke per §17 Phase 6 acceptance: SMDS coverage page shows green for L1/L2, accurate orphan counts, suggested source types, working exception flow.

If green: stop, report, await go for Phase 7.

---

## 9. Phase 7 — ICD Ingestion Pipeline

**Spec:** §10 (pipeline), §9.2/§9.4 (endpoints)
**Prereq:** Phase 6 merged-clean.
**Risk:** Calls real Anthropic API. Costs real tokens. **Tests must mock the API call — no live API in CI.**

Execution:

1. **Add dependencies** to `backend/requirements.txt`:
   ```
   PyMuPDF==1.24.5
   camelot-py[cv]==0.11.0
   python-docx==1.1.2
   ```
   Rebuild backend image: `docker compose build backend && docker compose up -d backend`.

2. **Build `backend/app/services/catalog/document_extractor.py`** — the pre-extraction pass. PyMuPDF for PDF (text + 200 DPI page images, capped at 50 pages), python-docx for DOCX, openpyxl for XLSX (already in requirements), camelot-py for table extraction. Returns a normalized intermediate representation.

3. **Build `backend/app/services/catalog/prompts.py`** with the strict-JSON-schema prompt for Anthropic. Schema validates against `IcdExtractionResultSchema` Pydantic model.

4. **Build `backend/app/services/catalog/icd_extractor.py`** — orchestrates document_extractor → Anthropic call → schema validation → PendingCatalogImport row. Use the existing `ai_service` abstraction so the regex fallback (per Mason's three-tier AI pipeline pattern) handles API failures.

5. **Endpoints:**
   - `POST /catalog/suppliers/{id}/documents/upload` — multipart upload, SHA-256 hash, store under `/data/supplier_docs/{uuid}.{ext}`. **Apply F-018 protections from audit Phase 2C** — the BodySizeLimitMiddleware and content-type validation are already in place; verify they cover this new endpoint.
   - `POST /catalog/documents/{doc_id}/extract` — trigger extraction (background task, not synchronous). Returns 202 Accepted with `{job_id}`. Use the `report_jobs` table pattern from F-019 audit work, OR create a dedicated `extraction_jobs` table — pick one and stick with it.
   - `POST /catalog/pending-imports/{id}/approve` — transactional commit creating Supplier (if new), CatalogPart, CatalogConnectors, CatalogPins. All-or-none.
   - `POST /catalog/pending-imports/{id}/reject` — sets status, no data created.

6. **Review UI page** at `/catalog/documents/[id]/review` per §10. Side-by-side: original document preview (PDF.js for PDF, raw download for others) on the left, extracted form on the right with every field editable. Approve button transitions to Phase 7 commit flow.

7. **Enable Tab 3 (Upload ICD)** in `<PlaceLruModal>` from Phase 3.

8. **Tests** in `backend/tests/test_icd_extraction.py`:
   - **Mock the Anthropic API** — no live calls. Use a fixture JSON response that matches the schema.
   - Synthetic ICD fixture: a simple PDF with known content that the mock returns matching extraction for.
   - Schema validation rejects malformed extractions.
   - Approve creates Supplier + CatalogPart + Connectors + Pins atomically.
   - Reject creates no data.
   - Re-uploading the same SHA-256 doesn't create duplicate documents.

**Phase 7 verification gate:**

```
docker exec astra-backend-1 pytest backend/tests/test_icd_extraction.py -v
docker exec astra-backend-1 pytest backend/tests/ -v
cd frontend && npm run typecheck && npm run build
```

Manual smoke per §17 Phase 7 acceptance: upload a real Glenair Mil-DTL-38999 datasheet → in <60 seconds it's in pending review → engineer approves → catalog has the part → place in SMDS → connect.

**This manual smoke uses real Anthropic API tokens. Estimate cost: a single 50-page datasheet extraction ~$0.10-0.50. Don't loop on this — one successful E2E run is the acceptance.**

If green: stop, report, await go for Phase 8.

---

## 10. Phase 8 — Polish, RBAC Verification, Robustness

**Spec:** §17 Phase 8, §22 (acceptance)
**Prereq:** Phase 7 merged-clean.

Execution:

1. **README update.** Add catalog and sync architecture sections at the top of the existing README. Diagram from spec §3 included as ASCII.

2. **Seed script** for starter suppliers: Raytheon, BAE, TE Connectivity, Glenair, Amphenol. Each with one or two representative catalog parts. Idempotent — re-run does not duplicate. Place under `backend/app/scripts/seed_catalog.py`.

3. **Audit log events.** Verify every catalog mutation, import approval, sync proposal acceptance, coverage exception emits an audit event with the correct event type. Grep:
   ```
   grep -rn "audit_service.record_event\|_audit(" backend/app/routers/catalog.py backend/app/routers/req_sync.py backend/app/routers/coverage.py
   ```
   Every state-changing endpoint should appear. Missing events get added.

4. **Admin override paths.** Test end-to-end:
   - Admin force-approves a sync proposal that the policy says shouldn't auto-apply.
   - Admin force-deletes a CatalogPart that has placed Units (`?admin_force=true`).
   - Admin overrides a locked requirement.
   - Admin places a `RESTRICTED` lifecycle catalog part.
   
   Each path emits a special audit event tagged `admin_override=true` so the audit log distinguishes overrides from normal mutations.

5. **Performance test** per §18: `backend/tests/test_perf_catalog_scale.py`. Target thresholds from §18:
   - Catalog list paginated: <200ms
   - Catalog part detail: <300ms
   - Auto-wire on 100-pin units: <500ms
   - Coverage report: <1s
   - Sync proposal fan-out on CatalogPart edit affecting 50 placed units: <2s
   
   Test fails the build if any threshold is blown.

6. **Full regression test.** Run the entire pytest suite. Target: zero regressions on existing SMDS data and audit-Phase tests.

7. **E2E test** per §17 Phase 8 acceptance: fresh DB → seed → upload → approve → place → connect → auto-wire → generate reqs → edit source → review proposal → accept → coverage report green.

**Phase 8 verification gate (final):**

```
docker exec astra-backend-1 alembic upgrade head
docker exec astra-backend-1 alembic check
docker exec astra-backend-1 pytest backend/tests/ -v --tb=short
docker exec astra-backend-1 pytest backend/tests/test_perf_catalog_scale.py -v
cd frontend && npm run typecheck
cd frontend && npm run build
```

Plus the §22 Definition of Done checklist — walk every item and confirm ✅.

If green: stop, report, await merge instruction.

After Phase 8 closes and is merged to main:

1. The branch becomes the new baseline for the Test Integration Module (ASTRA-TDD-TEST-001) and Phase 2 Communication Module — those are out of scope for this refactor but explicitly named as downstream consumers in spec §0.
2. The deferred F-045 (pgvector) becomes more attractive because the catalog layer adds vector-search opportunities (similar parts by spec). Don't pull it in here, but flag in `INTERFACE_FOUNDATION_LOG.md` that the use case is now stronger.

---

## 11. `INTERFACE_FOUNDATION_LOG.md` Template

Initialize at pre-flight. Update at every phase verification gate.

```markdown
# ASTRA Interface Foundation Refactor — Execution Log
**Started:** <YYYY-MM-DD>
**Source spec:** ASTRA-TDD-INTF-002 v1.1 (`ASTRA_INTERFACE_FOUNDATION_REFACTOR.md`)
**Branch:** feat/interface-foundation
**Pre-flight DB snapshot:** `../ASTRA-backups/pre_intf002_<timestamp>.dump`

## Pre-flight
- Working tree clean: ✅
- alembic current at start: 0022 (post-audit Phase 4)
- Test suite at start: <count> passed
- Branch SHA: <sha>

## Phase Status

| Phase | Status | Commit Range | Tests Added | Verification Gate | Notes |
|---|---|---|---|---|---|
| 1 — Schema & migration | ⏳ in progress / ✅ complete / ⏸ deferred | a1b2c3d..e4f5g6h | N | green/red | — |
| 2 — Catalog CRUD backend | … | … | … | … | … |
| 3 — Catalog UI | … | … | … | … | … |
| 4 — Connection Builder + auto-wire | … | … | … | … | … |
| 5 — Reactive Requirement Sync | … | … | … | … | … |
| 6 — Source Coverage Validator | … | … | … | … | … |
| 7 — ICD Ingestion | … | … | … | … | … |
| 8 — Polish & robustness | … | … | … | … | … |

## Per-Phase Detail

### Phase 1 — Schema & migration
**Files touched:** (list)
**Migration revision:** 0023 (or actual)
**Backfill counts:**
- requirement_source_links migrated from interface_requirement_links: <count>
- pins.internal_signal_name populated: <count>
**Verification gate output:** (paste relevant lines)
**Anomalies / observations:** (anything tangential — log here, do not silently fix)

### Phase 2 — Catalog CRUD backend
…

(Continue for each phase as it lands.)

## Anomalies & Tangential Findings

(Per the audit-remediation pattern — anything noticed but not silently fixed goes here.)

| Date | Phase | Description | Severity | Disposition |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

## Out of Scope (explicitly deferred)

- F-045 pgvector (deferred from audit, separate prep PR).
- Frontend test-infra cleanup (deferred from audit Phase 3B).
- delete-impact UI integration (deferred from audit Phase 3C).
- /auth/refresh frontend interceptor (deferred from audit Phase 3C).
- Test Integration Module (ASTRA-TDD-TEST-001 — separate spec).
- Phase 2 Communication Module (separate spec).
- Vendor revision diff/upgrade UI (per spec §20).
- Image extraction from ICDs (text + tables only in v1).
- Catalog-to-Catalog mating constraints.
- Cross-project full-graph where-used.
- Archival job for old sync proposals.
- Signal entity abstraction.
```

---

## 12. Final Acceptance — Definition of Done

Walk spec §22 verbatim. All 18 boxes ticked. Plus:

1. `INTERFACE_FOUNDATION_LOG.md` complete with per-phase entries.
2. `feat/interface-foundation` merged to main with `--no-ff`.
3. No deferred items added beyond the explicit list in §11 of this prompt.
4. `git log --oneline main..HEAD` (before merge) shows clean per-phase commits — bisectable.

When complete, print to stdout: `INTERFACE FOUNDATION REFACTOR COMPLETE — 8 phases, <N> commits, see INTERFACE_FOUNDATION_LOG.md` and stop. Don't summarize in chat; the log is the deliverable.
