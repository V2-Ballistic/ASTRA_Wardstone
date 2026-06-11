# ASTRA Config Ecosystem — As-Found Note (pre-build survey)

Date: 2026-06-10 · Spec: `C:\Tools\CADPORT\docs\ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC.md`

## Repos / runtime
- **ASTRA** `C:\Users\WardStone\Documents\ASTRA` — FastAPI + Postgres 16 (SQLite in tests) + Alembic (43 hand-written migrations, latest `0043_catalog_parts_sync_origin.py`), Next.js 14 app-router frontend. Clean on `main`.
- **HAROLD** `C:\Tools\harold\wardstone-harold` — WRENCH plugin, **running** at `:8030` under `/api/tools/wardstone-harold`. SQLite ledger. Clean on `main`.
- **CADPORT** `C:\Tools\CADPORT` — WRENCH plugin at `/api/tools/cadport`. SQLite + additive-column shim (no Alembic). Clean on `main`.
- **CITADEL** — *not on this machine*. The `ingestMotorCSV` reference implementation is unavailable; the port (§5.2) is built to the spec's behavioral contract, not line-by-line from CITADEL source. Flagged per §12 spirit.

## HAROLD as-found vs §2 requirements
- Endpoints present: `GET /wpn/suggest`, `POST /wpn/validate(+bulk)`, `POST /wpn/issue`, `POST /wpn/issue-specific`, `POST /wpn/{wpn}/retire|supersede`, `DELETE /wpn/{wpn}` (hard delete; counter rolls back if highest — usable as the §2.7 release path), `PATCH /wpn/{wpn}`, `GET /ledger…`, `POST /filename-precheck`, `GET /system-codes`.
- Allocation is per-system-code `SELECT … FOR UPDATE` on `wpn_sequences` — sequential, gapless, transactional. ✔
- **Gaps:** (a) no `MTR`/`AER`/`CFG` codes — 21 hardcoded 2-letter codes only; (b) **no system-code allocator endpoint** (codes are in-code reference data); (c) validators/format enforce exactly 2-char codes, spec needs 3-char; (d) no "issue next revision of existing WPN" endpoint (§2.5).
- Resolution (in lieu of §12 stall — HAROLD is local source we own): extend HAROLD additively — DB-backed dynamic system codes + `POST /system-codes` registrar, 2–3 char code support, `POST /wpn/{wpn}/revise`. ASTRA *requests* MTR/AER/CFG through the registrar (no hardcoded numbers).

## ASTRA as-found
- HAROLD client at `backend/app/services/harold/client.py` (+ `service.py` with 3-branch issue & local fallback for catalog parts). Engineering domains will use a new strict `harold_naming` service (no silent fallback — §2/§12).
- Catalog: `catalog_parts` rich model; `POST /api/v1/catalog/parts/from-cadport` idempotent on `content_hash`. **No `role` column** (needed by §7).
- Baselines: project-scoped snapshot tables. Interfaces module: systems/units/connectors/buses (electrical ICD focus) — Frame ICD will register here.
- `app/services/cadport/mass_recompute.py` = uniform mass-scaling identity only (no parallel-axis). The §9 roll-up (parallel-axis to frame datum) does **not** yet exist on the ASTRA side; CADPORT computes assembly roll-ups at extract time. Parity verification of the mirrored scaling code is part of Phase 0.
- Tests: pytest, in-memory SQLite per test, `client`/`auth_headers`/`test_project` fixtures. Migrations are hand-written raw-SQL style ("Mason's standing rule").
- No existing engineering/motor/aero/config modules. Migration numbers reserved: 0044 frame-ICD, 0045 motors, 0046 aero, 0047 configs, 0048 bundle-export, 0049 catalog role.

## Frontend as-found
- Sidebar `NavGroup`s incl. an `ENGINEERING` group (`src/components/layout/Sidebar.tsx`); catalog tab pattern is the reference for the new tabs. axios client `src/lib/api.ts` (Bearer from localStorage, refresh interceptor). `d3@7` and `three` present; **no** chart lib, **no** drag-drop yet. Dark `astra-*` Tailwind theme, lucide icons, no component library.

## CADPORT as-found vs §7
- §6 YAML: `coordinate_system: body_frame`, SI; **no explicit frame-ICD datum/axes/referencePoint fields**; **no role taxonomy** anywhere in models/YAML/payload.
- Naming: WPNs always issued by HAROLD (`wpn_issue` at import step 3; filename precheck on upload) — already routes through the authority. ✔
- Mass sync: `mass_recompute.py` mirrored ASTRA↔CADPORT (uniform scaling, loop-breaker via `last_sync_origin`). Drift check scheduled.

## Frame datum
- Spec default **OML nose tip**, axes x-fwd/y-right/z-down, SI — *unconfirmed by stakeholder*; proceeding parameterized per §12.
