# ASTRA Interface Foundation Refactor — Execution Log
**Started:** 2026-05-01
**Source spec:** ASTRA-TDD-INTF-002 v1.1 (`ASTRA_INTERFACE_FOUNDATION_REFACTOR.md`)
**Execution prompt:** `CLAUDE_CODE_INTERFACE_FOUNDATION_PROMPT.md`
**Branch:** feat/interface-foundation
**Pre-flight DB snapshot:** `C:\Users\Mason\Documents\ASTRA-backups\pre_intf002_1777604591.dump`
**Inherited carry-forwards from audit Phase 4:** 23 unresolved findings (6 HIGH, 11 MEDIUM, 5 LOW, 1 INFO) documented in `AUDIT_FINDINGS_POST_REMEDIATION.md`. NOT addressed in this refactor. Note in particular F-200 (one-line jti gap) and F-201 (workflows/AI/audit/seed _check_membership gaps) — both could be tightened during this work but the explicit scope of INTF-002 is the catalog/sync layer, not audit remediation.

## Pre-flight
- Working tree clean: ✅
- alembic current at start: 0022 (post-audit Phase 4)
- Test suite at start: 242 passed
- Phase 4 merged to main: ✅ (`2c52a3a`)
- Branch SHA: `2c52a3a` (head of main = head of new branch)
- DB snapshot: `pre_intf002_1777604591.dump` (~290 KB, outside repo per F-006)
- AI provider configured: ✅ (AI_PROVIDER, AI_API_KEY, AI_MODEL set in .env — Phase 7 viable)
- pgadmin restart loop: pre-existing F-219, harmless, ignored

## Phase Status

| Phase | Status | Commit Range | Tests Added | Verification Gate | Notes |
|---|---|---|---|---|---|
| 0 — Pre-flight | ✅ complete | n/a (pre-branch) | 0 | n/a | Phase 4 merged to main, branch + snapshot + log in place |
| 1 — Schema & migration | ✅ complete | `66fcb97..94bf662` | 0 | green (242/242) | migration 0023, down/up tested, JSONB→JSON variant for SQLite tests |
| 2 — Catalog CRUD backend | ✅ complete | `f7cf33a..f8a7a0e` | 18 (260 total) | green (260/260) | placement svc, router (20 routes), tests, supplier-delete bug fix |
| 3 — Catalog UI | ✅ complete | `2b3a607..HEAD` | 0 (frontend test infra deferred) | green (tsc filter empty, build ✓ Compiled successfully, backend 260/260) | catalog-types + catalog-api + PlaceLruModal + 5 new pages + 4 modified pages + sidebar Catalog link |
| 4 — Connection Builder + auto-wire | ✅ complete | `3b6f0bd..2fef238` (5 commits) | 51 (311 total) | green (alembic 0024, pytest 311/311, tsc filter empty, build ✓) | migration 0024 added Interface.source_unit_id/target_unit_id; auto-wire engine implements full three-way validation with explicit 6×6 direction matrix; Connection Builder wizard at /projects/[id]/interfaces/connect |
| 5 — Reactive Requirement Sync | ⏳ pending | — | — | — | — |
| 6 — Source Coverage Validator | ⏳ pending | — | — | — | — |
| 7 — ICD Ingestion | ⏳ pending | — | — | — | — |
| 8 — Polish & robustness | ⏳ pending | — | — | — | — |

## Per-Phase Detail

### Phase 0 — Pre-flight
**Files touched:** none (this log file).
**DB snapshot:** `C:\Users\Mason\Documents\ASTRA-backups\pre_intf002_1777604591.dump` (Postgres custom format, 290 KB).
**Phase 4 merge SHA:** `2c52a3a` on main.
**Branch:** `feat/interface-foundation` from `2c52a3a`, pushed to origin.
**Anomalies / observations:** A spec-digest agent is running in parallel to produce a fast-lookup cheat-sheet of the 83 KB spec at `.foundation_spec_digest.md` (gitignored by leading dot). Phase 1 will reference it.

### Phase 1 — Schema & migration

**Files touched:**
- New models: `backend/app/models/catalog.py`, `backend/app/models/req_sync.py`, `backend/app/models/coverage_exception.py`
- Modified models: `backend/app/models/interface.py` (Pin + Unit extensions), `backend/app/models/__init__.py` (Requirement sync columns + new model re-exports with catalog enums aliased)
- New schemas: `backend/app/schemas/catalog.py`, `backend/app/schemas/req_sync.py`, `backend/app/schemas/coverage.py`
- New migration: `backend/alembic/versions/0023_supplier_catalog_layer.py`
- `backend/app/database.py`: NOT modified (pool already at spec values from a prior change — verified `pool_size=20, max_overflow=30, pool_recycle=1800, pool_pre_ping=True`)

**Migration revision:** `0023` (spec calls it 0008 from pre-audit numbering; actual sequential is 0023 since audit Phase 4 left head at 0022). 12 PG enum types created with catalog_-prefixed names where they would otherwise collide with the existing project-side enums (`connectorgender`, `signaltype`, `pindirection`).

**Backfill counts (dev DB at apply time):**
- `pins.internal_signal_name + mfr_pin_name` populated: **139 / 139** (0 NULL after upgrade). Sourced from `pins.signal_name` (spec §5.1 step 14 said `pins.name`, but the existing schema has no `name` column — `signal_name` is the only meaningful pre-existing pin label and matches the spec's intent).
- `requirement_source_links` migrated from `interface_requirement_links`: **20 / 20** (1-to-1, all rows had entity_type values in the supported map).
- `requirements.generation_template_id` populated from `interface_requirement_links.auto_req_template`: best-effort copy (no per-link template recorded for 0/20 links so 0 requirements gained the new field, which is expected for legacy data without per-template tagging).

**Verification gate output:**
- `alembic current` → `0023 (head)` ✅
- `\d suppliers`, `\d catalog_parts`, `\d requirement_source_links` → all show expected columns and indexes (PK, supplier_id, part_number, search composites, JSONB GIN where specified)
- Down/up cycle: `alembic downgrade -1` → 0022, `alembic upgrade head` → 0023, backfill counts unchanged (139 pins, 20→20 RSL).
- `pytest tests/ -q` → **242 passed** (matches pre-Phase-1 baseline; zero regressions).

**Anomalies / observations:**
- Spec §5.1 step 14 references `pins.name`; the existing schema has `pins.signal_name` instead. Backfill seeds `mfr_pin_name + internal_signal_name` from `signal_name`. Same intent — different column name. The `signal_name` column itself is kept (deprecation/drop scheduled with the spec's broader "drop in 0009 only after grep confirms zero readers" plan).
- Catalog-side `ConnectorGender`, `SignalType`, `SignalDirection` are intentionally distinct enums from the project-side `interface.ConnectorGender` (MALE_PIN/FEMALE_SOCKET/…), `interface.SignalType` (POWER_PRIMARY/SIGNAL_DIGITAL_*/…), `interface.PinDirection` (INPUT/OUTPUT/BIDIRECTIONAL/TRI_STATE/OPEN_COLLECTOR/…). The project-side enums remain untouched on existing project columns; the catalog-side enums live on the new catalog tables and on the new `Pin.direction_override` column. PG enum types use `catalog_*` prefixes to avoid collision.
- Spec §4.6 says `direction_override` uses "the existing interface.SignalDirection". There is no `SignalDirection` enum in the existing `interface.py` — only `PinDirection`. Used the new catalog `SignalDirection` instead (matches the spec's auto-wire algorithm in §11 which references the same enum on both sides).
- JSONB columns ship as `JSON().with_variant(JSONB(), "postgresql")` so the SQLite test environment can render them; PG schema is unaffected (still `jsonb` on the wire).
- `app.models.interface` now imports `app.models.catalog` (module, not symbol) so `Pin.direction_override` can reference the catalog `SignalDirection`. Catalog has no reverse dependency on interface, so no cycle.

### Phase 2 — Catalog CRUD backend

**Files touched:**
- New service package: `backend/app/services/catalog/__init__.py`, `backend/app/services/catalog/placement.py`
- New router: `backend/app/routers/catalog.py` (20 routes mounted at `/api/v1/catalog`)
- New tests: `backend/tests/test_catalog_crud.py` (18 tests across 5 classes)
- Modified: `backend/app/main.py` — registered `app.routers.catalog` and added `catalog` / `req_sync` / `coverage_exception` to the explicit `_model_path` import list
- Modified: `backend/app/routers/catalog.py` — supplier delete admin_force path now explicitly deletes child CatalogParts first (NOT NULL FK without ondelete=CASCADE; explicit Python cascade rather than a schema change is the smaller blast-radius fix)

**Endpoints implemented (20 total):**
- §9.1 Suppliers: GET/POST list+create, GET/PATCH/DELETE detail (5)
- §9.2 Documents: POST upload, GET metadata, GET file, DELETE (4)
- §9.3 Catalog parts: GET/POST list+create, GET/PATCH/DELETE detail, GET usage, POST place, POST variant (8)
- §9.4 Pending imports (read-only slice — write side ships in Phase 7): GET list, GET detail, PATCH (3)

**Endpoints deferred to Phase 7 (per phase prompt scope):**
- POST `/catalog/documents/{id}/extract`
- POST `/catalog/documents/{id}/preview`
- POST `/catalog/pending-imports/{id}/approve`
- POST `/catalog/pending-imports/{id}/reject`

**Placement service highlights:**
- `place_catalog_part(...)` — atomic SAVEPOINT clones CatalogPart → Unit, CatalogConnector → Connector, CatalogPin → Pin
- `place_brand_new_part(...)` — admin/req_eng catalog-create + place in one transaction
- `is_part_in_use(part_id)` — fast exists-style probe used by DELETE handler
- Cross-perspective enum mapping inline (catalog `PartClass` → project `UnitType`, catalog `ConnectorGender` → project `ConnectorGender` legacy values, catalog `SignalType` → project `SignalType` finer-grained, catalog `SignalDirection` → project `PinDirection`). Unmapped values fall back to safe `CUSTOM` / `LRU` / `GENDERLESS` / `PASSIVE`.
- RESTRICTED parts refuse non-admin placement (403); OBSOLETE parts require admin + admin_force=true (400). Supplier inactive guard is bypassed for admin.

**Verification gate output:**
- `pytest tests/test_catalog_crud.py -v --tb=short` → **18 passed**
- `pytest tests/ -q --tb=no` → **260 passed** (242 baseline + 18 new, zero regressions, ~124 s)

**Anomalies / observations:**
- Catalog-part DELETE handler uses Python-level cascade rather than a schema change because the FK from `catalog_parts.supplier_id` is NOT NULL with default RESTRICT. Phase 1 schema is "locked" so adding ondelete=CASCADE would require a new migration; the Python cascade is functionally equivalent for the supplier-delete-with-admin-force path and avoids touching the migration head. Pending — could be tightened to ondelete=CASCADE in the next migration if that fits the broader cleanup plan.
- `place_catalog_part` does NOT yet create `RequirementSourceLink` rows tagged `template_id="legacy_import"` (digest §10 anomaly #11). The reactive sync layer arrives in Phase 5 — placement will be revisited then.
- The project-side `SignalType` enum is much finer-grained than catalog's broad categories (37 vs 10 members). The catalog→project map picks the most generic project enum value (e.g. catalog `digital` → project `SIGNAL_DIGITAL_SINGLE`). Cleaning this up to a richer mapping is a Phase 8 polish item.
- Project-side `PinDirection` has logic-family values (TRI_STATE, OPEN_COLLECTOR, OPEN_DRAIN, etc.) that the catalog `SignalDirection` doesn't carry — the catalog→project map collapses to the basic INPUT/OUTPUT/BIDIRECTIONAL/POWER_SOURCE/GROUND/PASSIVE set. Auto-wire (Phase 4) reads from `Pin.direction_override` (catalog enum) so this lossy map only affects the legacy `Pin.direction` column.
- `SUPPLIER_DOC_DIR` defaults to `/data/supplier_docs/` (created lazily); tests use `monkeypatch` to redirect to `tmp_path` so they never write to the real volume.
- Reused existing `interfaces.update` permission key for catalog writes (RBAC matrix has no per-action catalog keys yet); explicit `_require_req_eng_plus` / `_require_admin` helpers gate every write/delete handler. Adding dedicated `catalog.*` permission keys is a Phase 8 polish item, but the role gates are correct as-is.

### Phase 3 — Catalog UI

**Files touched (frontend only — operating rule #1):**
- New: `frontend/src/lib/catalog-types.ts` — literal-union enums + `Supplier`, `SupplierDocument`, `CatalogPin`, `CatalogConnector`, `CatalogPart`, `CatalogPartDetail`, `PendingCatalogImport`, etc. Plus `LIFECYCLE_COLORS` / `PART_CLASS_LABELS` / etc. for the dark-theme pills. F-123-clean (no `| string` collapse on the unions).
- New: `frontend/src/lib/catalog-api.ts` — wraps every Phase-2 endpoint via the central axios instance (`@/lib/api`) so the JWT interceptor + 401 redirect inherit. Includes `approvePendingImport` / `rejectPendingImport` stubs that throw "ships in Phase 7" so Tab-3 wiring is forward-compatible.
- New: `frontend/src/components/catalog/PlaceLruModal.tsx` — three-tab modal (`Catalog`, `Brand New`, `Upload ICD` disabled). 403/409 handled gracefully on the placement call. RESTRICTED parts gated behind an admin-force checkbox. Tab 3 renders disabled with `aria-disabled="true"` + tooltip "Available in Phase 7…".
- New: `frontend/src/app/catalog/page.tsx` — landing page with three tabs (Suppliers, Parts, Pending Imports). Pending Imports renders an explicit "Phase 7 preview" notice and a graceful empty state.
- New: `frontend/src/app/catalog/suppliers/new/page.tsx`, `frontend/src/app/catalog/suppliers/[id]/page.tsx` — supplier create + detail with metadata, documents (upload + delete), and parts sections. RBAC-gated buttons via `useAuth()`.
- New: `frontend/src/app/catalog/parts/new/page.tsx`, `frontend/src/app/catalog/parts/[id]/page.tsx` — manual part create + detail (physical / power / environmental / compliance / lifecycle / connectors+pins drill-in / where-used / variants).
- Modified: `frontend/src/app/projects/[id]/interfaces/unit/[unitId]/page.tsx` — added `<CatalogBadge>` + Variants link near the unit header. Phase-5 sync-indicator slot left as a comment per spec.
- Modified: `frontend/src/app/projects/[id]/interfaces/connector/[connectorId]/page.tsx` — dual-name pin table: Mfr column locked (read-only with lock icon), Internal column editable with PATCH-on-blur. Bulk select + "Rename pattern" (literal or regex) + "Copy mfr → internal" actions in a sticky toolbar that appears once any pin is selected.
- Modified: `frontend/src/app/projects/[id]/interfaces/page.tsx` — "Add Unit" CTA opens `<PlaceLruModal>`; "Connect Two Units" CTA renders a Phase-4 placeholder toast (auto-dismissing).
- Modified: `frontend/src/app/projects/[id]/interfaces/harness/[harnessId]/page.tsx` — wire rows render a secondary `mfr: …` subtitle in muted color when the catalog mfr name is available; legacy wires render only the existing `signal_name`.
- Modified: `frontend/src/components/layout/Sidebar.tsx` — added a global "Catalog" link to `GLOBAL_NAV` with the `Package` icon.

**Verification gate output:**
- Filtered `npx tsc --noEmit` (the spec command) → **empty output** (no new errors). Pre-existing TS2802 iteration warnings, the 1133/1136/2056-block in `harness/page.tsx`, the AutoGrowAmbiguityModal type, the `requirements/page.tsx(497)` enum mismatch, and `auto-requirements/page.tsx(600)` implicit any are all the documented audit-deferred items.
- `npm run build` → **✓ Compiled successfully**. Lint-stage failure on `jest.config.ts` is the documented pre-existing issue (frontend test infra cleanup deferred).
- `pytest tests/ -q --tb=no` → **260 passed** (no backend regressions).

**Anomalies / observations:**
- The Pydantic `UnitResponse` / `PinResponse` / `ConnectorResponse` schemas don't currently surface the catalog-side fields (`catalog_part_id`, `mfr_pin_name`, `location_zone`, `serial_number`, etc.) even though those columns exist on the SQLAlchemy models post-migration 0023. Per operating rule #1 (no backend changes), the frontend reads these via narrow augmented types (`UnitWithCatalog`, `PinDualName`, augmented `Wire`) and gracefully renders `—` / no badge / no subtitle when the values are absent. When the backend response schemas are extended (a 5-line edit per Pydantic class), the badge and dual-name table light up automatically.
- `Phase 4 — Connection Builder` placeholder is a transient toast (auto-dismiss 4 s) on the interfaces landing page, deliberately styled lightweight so it doesn't compete visually with the real "Add Unit" CTA next to it.
- `Phase 5 — Sync Proposals indicator` left as a `// Phase 5: <SyncProposalIndicator unitId={...} />` comment in the unit detail header per spec — the data structure isn't defined yet so the slot stays empty.
- `PlaceLruModal` opens supplier list / parts list / project systems on mount; the search field debounces by 250 ms before re-querying. Restricted-lifecycle parts surface a red banner on the right preview pane and require a separate "Acknowledge restricted placement" checkbox before the Place button enables.
- `Catalog` link added to `GLOBAL_NAV` (alongside Projects) so users can reach the supplier catalog from any context, matching spec §16.
- Frontend-test infra remains broken (deferred audit cleanup) — verification by `tsc --noEmit` + `npm run build` per operating rule #7.
- TypeScript `tsc` reports the `harness/page.tsx` iteration error at line **2075** (was 2056 pre-edit; the wire-row JSX was wrapped in a `pin => { return ( ... ); }` to compute the dual-name secondary line, shifting +19 lines). Same root cause as the documented entry — TS2802 is the underlying iteration problem.

## Anomalies & Tangential Findings

| Date | Phase | Description | Severity | Disposition |
|---|---|---|---|---|
| 2026-04-30 | 1 | Spec §5.1 step 14 cites `pins.name`; actual column is `pins.signal_name`. Backfill sources `signal_name` instead — same intent. | INFO | Migrated as-is; documented above. |
| 2026-04-30 | 1 | Spec §4.6 cites "existing `interface.SignalDirection`" enum; no such enum exists in current code. Used the new catalog `SignalDirection`. | INFO | Tracked here; matches §11 auto-wire usage. |
| 2026-04-30 | 1 | Pre-existing `app.models.workflow` triggers a `PydanticDeprecatedSince20` warning (class-based Config). Pre-Phase-1, not Phase-1's regression. | INFO | Out of scope — leave for unrelated tidy-up. |
| 2026-04-30 | 2 | Catalog-side `catalog_parts.supplier_id` FK has default RESTRICT (NOT NULL, no ondelete=CASCADE). Supplier delete with admin_force was raising NOT NULL violations on dependent parts. | INFO | Worked around with Python-level cascade in the DELETE handler. Could be tightened to ondelete=CASCADE in a follow-up migration if the broader cleanup plan needs it. |
| 2026-04-30 | 2 | Catalog→project enum maps are intentionally lossy (catalog `PartClass` has 13 members → project `UnitType` has 30+; catalog `SignalType` has 10 → project has 37+). The maps pick the most generic safe project value. | INFO | Phase 8 polish item — richer mapping table when product needs it. |
| 2026-04-30 | 2 | Catalog router reuses existing `interfaces.update` / `interfaces.delete` permission keys via inline `_require_req_eng_plus` / `_require_admin` helpers, rather than adding new `catalog.*` keys to `PERMISSION_MATRIX`. | INFO | Phase 8 polish — add dedicated keys to rbac.py for cleaner audit trails. |

## Out of Scope (explicitly deferred)

- F-045 pgvector (deferred from audit, separate prep PR).
- Frontend test-infra cleanup (deferred from audit Phase 3B).
- delete-impact UI integration (deferred from audit Phase 3C).
- /auth/refresh frontend interceptor (deferred from audit Phase 3C).
- 23 unresolved findings from `AUDIT_FINDINGS_POST_REMEDIATION.md` (F-200..F-222 + 3 persisting partial fixes). Address in a separate Phase 5 audit-remediation PR before or after this refactor merges.
- Test Integration Module (ASTRA-TDD-TEST-001 — separate spec).
- Phase 2 Communication Module (separate spec).
- Vendor revision diff/upgrade UI (per spec §20).
- Image extraction from ICDs (text + tables only in v1).
- Catalog-to-Catalog mating constraints.
- Cross-project full-graph where-used.
- Archival job for old sync proposals.
- Signal entity abstraction.
