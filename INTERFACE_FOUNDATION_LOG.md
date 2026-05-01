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
| 2 — Catalog CRUD backend | ⏳ pending | — | — | — | — |
| 3 — Catalog UI | ⏳ pending | — | — | — | — |
| 4 — Connection Builder + auto-wire | ⏳ pending | — | — | — | — |
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

## Anomalies & Tangential Findings

| Date | Phase | Description | Severity | Disposition |
|---|---|---|---|---|
| 2026-04-30 | 1 | Spec §5.1 step 14 cites `pins.name`; actual column is `pins.signal_name`. Backfill sources `signal_name` instead — same intent. | INFO | Migrated as-is; documented above. |
| 2026-04-30 | 1 | Spec §4.6 cites "existing `interface.SignalDirection`" enum; no such enum exists in current code. Used the new catalog `SignalDirection`. | INFO | Tracked here; matches §11 auto-wire usage. |
| 2026-04-30 | 1 | Pre-existing `app.models.workflow` triggers a `PydanticDeprecatedSince20` warning (class-based Config). Pre-Phase-1, not Phase-1's regression. | INFO | Out of scope — leave for unrelated tidy-up. |

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
