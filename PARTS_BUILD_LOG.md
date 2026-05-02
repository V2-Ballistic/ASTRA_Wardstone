# ASTRA Parts Library & Mechanical Module — Build Log
**Started:** 2026-05-01
**Spec:** ASTRA-SPEC-PARTS-001 v0.1
**Branch:** feat/parts-mechanical-module
**Pre-flight alembic revision:** 0026
**Pre-flight test count:** 319 passed (3m 8s)
**DB snapshot:** ../ASTRA-backups/pre_parts_1777690333.dump
**Pre-flight frontend baseline:** `next build` fails on jest.config.ts (pre-existing); `tsc --noEmit` reports ~24 non-test errors (pre-existing target=es5 Set/Map iteration). New code must not regress these counts.

## Phase Status

| Phase | Status | Commit | Alembic | Tests delta | Build | Notes |
|---|---|---|---|---|---|---|
| 1 — Models, migration, schemas | in-progress | | | | — | |
| 2 — Services, routers, tests | pending | | | | — | |
| 3 — Frontend | pending | | — | — | | |
| 4 — Assembly parser, 3D, integration | pending | | — | | | |

## Decisions / Adaptations

- **No `Document` model existed.** Created a minimal `Document` model in `backend/app/models/document.py` per addendum §A.4. Migration 0027 creates the `documents` table.
- **`audit_service.log` does not exist.** Codebase uses `audit_service.record_event(db, event_type, entity_type, entity_id, user_id, action_detail, project_id)` synchronously. All audit calls adapted to this signature.
- **`RequirementSourceLink` uses `template_id`+`template_inputs` (JSON), not `generation_template_id`+`project_id`.** Adapted joint approval to use the existing schema.
- **`CatalogPart` link on import approval deferred.** CatalogPart requires `supplier_id`, `part_number`, `name`, `part_class` (NOT NULL) and has no `library_part_id` column. Spec §4.5's CatalogPart creation block is non-trivial and out of scope for Phase 2; deferred to a follow-on task. Approval still works without `supplier_id`.
- **`typecheck` script added to `frontend/package.json`** as `tsc --noEmit` — script did not exist in baseline.

## New Issues Discovered

| Date | File:Line | Severity | Description | Action |
|---|---|---|---|---|

## Deferred Items

| Item | Reason | Spec ref |
|---|---|---|
| SolidWorks add-in | Separate spec | OQ-4 |
| Mass budget rollup | OQ-2 | §7 |
| ITAR role-gating | OQ-1 | §3.5.1 |
| Installation records | OQ-3 | §5.1.1 |
| LOD switching | OQ-7 | §6.3 |
| Full OCC mating-pair detection | Phase 5 | §5.2 stages 3-6 |
| Assembly GLTF with transforms | Stretch goal | §6.3 |
| CatalogPart auto-link on import approval | CatalogPart schema mismatch with spec | §4.5 |

## pythonOCC status
Available in container: TBD (will detect at parser import time)
Stub mode active: TBD
Stub mode impacts: STEP geometry extraction (bounding box, volume, surface area, thread detection from holes), assembly mating-pair / fastener pattern / seal groove detection. Metadata-only parsing (product name, MPN extraction via regex) always works.
