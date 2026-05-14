# MECH-001 Phase 0 — Investigation Report

> Discovery pass per the prompt's Phase 0 requirement. **Stop here and
> surface findings before proceeding** — the prompt itself mandates this.

## TL;DR

**Scenario:** the prompt's three-scenario taxonomy doesn't quite fit. It's
**closest to Scenario C (full backend, weak frontend)**, but with a
**material design conflict against the MECH-001 spec** that needs a
decision before any work proceeds.

- A full `mechanical_joints` table + ORM model + Pydantic schemas +
  716-line router + frontend page already exist, shipped under
  `ASTRA-SPEC-PARTS-001` (migration 0027).
- The MECH-001 prompt's `catalog_part_a_id` / `catalog_part_b_id`
  design **conflicts** with the actual schema, which keys joints off
  `project_parts` (the project-scoped instance of a `library_part`),
  not `catalog_parts`. There's also a `fastener_part_id` and a
  `seal_part_id` that FK to `library_parts` (the legacy parts library
  that CAT-002 backfilled into `catalog_parts` but did not retire).

The conflict is architectural, not cosmetic. **Recommendation: redesign
the frontend only (Scenario-C-style) and keep the existing backend.**
The literal MECH-001 catalog-keyed schema would require either a
parallel table or a destructive migration of working production code,
both out of scope per the prompt's own standing rules. Details below;
your call before I proceed.

---

## Alembic head

```
0029 (head)
```

Matches expectation — SYSARCH-002 didn't add a migration, so head is
unchanged from CAT-002. The MECH-001 prompt's "if scenario A or B,
write migration 0030" therefore lines up numerically.

---

## Existing tables

```
public | mechanical_joint_sequences  | table | astra
public | mechanical_joints           | table | astra
```

Both shipped by migration `0027_parts_library_and_mechanical.py`.

### `mechanical_joints` (32 columns, 11 indexes, 7 FKs, 11 CHECK constraints)

Authoritative schema dump:

| Column                        | Type                       | Notes                                                                 |
|-------------------------------|----------------------------|-----------------------------------------------------------------------|
| `id`                          | `integer` (BIGSERIAL)      | PK                                                                    |
| `joint_id`                    | `varchar(32)` UNIQUE       | Per-project tag like `MJ-001`, allocated from `mechanical_joint_sequences` |
| `project_id`                  | `integer` NOT NULL         | FK → `projects(id)` CASCADE                                           |
| `joint_type`                  | `joint_type` enum NOT NULL | `{bolted, riveted, press_fit, adhesive, weld, seal, alignment_pin, thermal_bond, spring_clip}` (9 values) |
| `part_a_id`                   | `integer` NOT NULL         | **FK → `project_parts(id)` RESTRICT** — NOT `catalog_parts`           |
| `part_b_id`                   | `integer` NOT NULL         | **FK → `project_parts(id)` RESTRICT** — NOT `catalog_parts`           |
| `fastener_part_id`            | `integer` nullable         | **FK → `library_parts(id)` SET NULL** — legacy, NOT `catalog_parts`    |
| `fastener_count`              | `integer`                  |                                                                       |
| `torque_nominal_nm`           | `numeric(10,4)`            |                                                                       |
| `torque_min_nm`               | `numeric(10,4)`            |                                                                       |
| `torque_max_nm`               | `numeric(10,4)`            |                                                                       |
| `engagement_length_mm`        | `numeric(10,4)`            | not in MECH-001 spec                                                  |
| `locking_feature`             | `locking_feature` enum     | not in MECH-001 spec                                                  |
| `hole_pattern_description`    | `varchar(300)`             | not in MECH-001 spec                                                  |
| `mating_surface_flatness_mm`  | `numeric(10,4)`            | not in MECH-001 spec                                                  |
| `mating_surface_finish_ra`    | `numeric(10,4)`            | not in MECH-001 spec                                                  |
| `seal_part_id`                | `integer`                  | **FK → `library_parts(id)` SET NULL**, not in MECH-001 spec           |
| `leak_rate_max_scc_s`         | `numeric(12,6)`            | not in MECH-001 spec                                                  |
| `test_pressure_bar`           | `numeric(10,3)`            | not in MECH-001 spec                                                  |
| `interface_drawing`           | `varchar(200)`             | not in MECH-001 spec                                                  |
| `source_step_file_id`         | `integer`                  | FK → `documents(id)` SET NULL — the deferred 3D STEP feature          |
| `source_step_entity`          | `text`                     | same                                                                  |
| `confidence`                  | `confidence_level` enum    | not in MECH-001 spec                                                  |
| `status`                      | `joint_status` enum NOT NULL DEFAULT `draft` | `{draft, active, superseded}` (3 values) |
| `notes`                       | `text`                     |                                                                       |
| `created_at` / `updated_at`   | `timestamptz`              |                                                                       |
| `created_by_id`               | `integer`                  | FK → `users(id)` SET NULL                                             |

**Missing vs MECH-001 spec:** `name` (top-level), `description`, `system_id`,
`part_a_role`, `part_b_role`, `preload_n`, `surface_treatment`,
`gasket_type`, `gasket_compression_pct`, `location_zone`.

Notable enum gaps (MECH-001 wants):

| Enum | Existing values | MECH-001 wants |
|------|----------------|----------------|
| `joint_type` | 9 (bolted, riveted, press_fit, adhesive, weld, seal, alignment_pin, thermal_bond, spring_clip) | 16 (adds `screwed`, `brazed`, `soldered`, `threaded`, `pinned`, `keyed`, `clamped`, `gasket_sealed`, `o_ring_sealed`, `tongue_groove`, `other`; renames `weld`→`welded`) |
| `joint_status` | 3 (draft, active, superseded) | 8 (planned, designed, analyzed, qualified, installed, verified, failed, superseded) |

CHECK constraints already in place: `part_a_id <> part_b_id`, torque
nonneg + min ≤ max, positive engagement/finish/flatness/leak rate/test
pressure/fastener count.

### `mechanical_joint_sequences`

One row per project; `next_val` allocator for `MJ-NNN` tags. The
prompt's "auto-generated `joint_id_tag` race condition" gotcha is
already solved by this table — no need to invent it.

---

## Backend files referencing mechanical joints

Existing code (do not rewrite — Scenario C):

- `backend/app/models/parts_library.py` — `MechanicalJoint` ORM, +
  the `JointType` / `JointStatus` / `LockingFeature` / `ConfidenceLevel`
  / `AssemblyParseJobStatus` Python enums, plus `MechanicalJointSequence`,
  `AssemblyParseJob`, `LibraryPart`, `ProjectPart`, etc.
- `backend/app/schemas/parts_library.py` — 630 lines including
  `MechanicalJointCreate`, `MechanicalJointResponse`, `MechanicalJointPatch`.
- `backend/app/routers/mechanical_joints.py` — 716 lines, 8 endpoints
  under `/api/v1/projects/{project_id}/mechanical-joints/`:
  - `GET /` — list with `joint_type` / `status` / `confidence` / `part_id`
    filters, eager-loads part A/B via `ProjectPart.library_part`, +
    fastener + seal `library_parts`.
  - `POST /` — create with `_assign_joint_id` (sequence allocator) and
    `_validate_joint_part_refs` (cross-project guard).
  - `GET /{joint_id}` — detail.
  - `PATCH /{joint_id}` — update.
  - `DELETE /{joint_id}` — soft (superseded) by default; force flag
    for active joints; auto-requirement cleanup on active deletion.
  - `POST /{joint_id}/approve` — transitions draft → active and
    generates auto-requirements via `mechanical_req_templates`.
  - `POST /assembly/parse` and `GET /assembly/parse/{job_id}` — the
    3D STEP feature (deferred per the prompt's AD-8).

Cross-references in other backend files (don't touch):

- `app/services/parts/mechanical_req_templates.py` — joint→req template engine
- `app/services/parts/__init__.py`, `wpn_service.py` — parts library service layer
- `app/services/cad/step_parser.py` — STEP parser (CAT-002)
- `app/services/req_sync/listener.py` — reactive sync hooks (likely listens to MechanicalJoint changes)
- `app/services/reports/icd_report.py` — ICD report generation

---

## Frontend file (the page itself)

`frontend/src/app/projects/[id]/mechanical-interfaces/page.tsx`:
**414 lines** of working code. NOT the 5 kB stub the prompt assumed
— the 5 kB figure was the compiled-bundle size, not source.

The page already:

- Lists joints in a table (Joint ID, Type, Part A, Part B, Fastener,
  Count, Torque, Status, actions).
- Has status + joint_type filters.
- Has an Add Joint button (disabled when `< 2` project parts exist).
- Has approve + delete actions.
- Routes joint detail / fastener links via `/parts-library/{id}`.
- Has the "3D assembly upload (Phase 4)" placeholder banner the
  prompt's AD-8 explicitly says to leave alone.

What's missing vs MECH-001's frontend spec:

- No tabs (the prompt wants `overview` / `joints` / `parts-with-joints`).
- No stat strip (the SYSARCH-style four-card row).
- No card grid (current is a table).
- No `CatalogPartPicker` integration — picker today is implicit via
  the inline create modal that comes from `parts-api`.
- The visual language is the older `bg-gray-50 dark:bg-gray-800/50`
  Tailwind palette, not the `astra-surface` / `astra-border` /
  gradient-button palette the prompt asks for.

---

## The core conflict — Part A/B keying

**Spec (MECH-001):** `catalog_part_a_id` / `catalog_part_b_id` FK
directly to `catalog_parts`. Frontend `AddJointModal` uses
`CatalogPartPicker` with `allowedClasses=['fastener_screw', ...]`
(the mechanical CAT-002 enum values).

**Reality:** existing `mechanical_joints.part_a_id` / `part_b_id` FK
to `project_parts`. A project part is a project-scoped row that
links one `library_part` (legacy parts library) into one project,
with quantity + designation + a `system_part_assignments` join to
systems. Joints reference these INSTANCES, not the catalog
recipes.

This is not a "missing column" fix. It's two different mental models:

| Question | MECH-001 model | Actual model |
|----------|----------------|--------------|
| Joint between… | two catalog parts (recipes) | two project parts (instances) |
| Same bracket in two projects | one shared joint definition? | each project has its own joint row |
| What does "Add Joint" need first? | catalog parts only | project parts (i.e. library_parts placed in this project) |
| Joint-to-system | optional `system_id` on the joint | derived via `project_parts → system_part_assignments → systems` |
| Fastener | catalog_parts FK | library_parts FK (legacy) |

CAT-002 backfilled every `library_part` into `catalog_parts` (each
catalog_parts row carries `metadata_json.legacy_id` back to its
source library_part), so library_parts and catalog_parts are
**parallel mirrors of the same mechanical-parts data** until
TDD-PROJPARTS-001 ships the consolidation. The project_parts table
hasn't migrated to catalog_parts yet — that's literally what
PROJPARTS-001 is for.

So the literal MECH-001 spec would force us to either:

1. **Build a parallel `mechanical_joints_v2` catalog-keyed table**
   (rejected: two parallel joint surfaces is worse than either one).
2. **Rip the FKs on `mechanical_joints.part_a_id/part_b_id` from
   `project_parts` to `catalog_parts`** (rejected: invalidates the
   approve / auto-requirements / req_sync chain; out of scope per
   prompt §11 — "Don't drop or modify… any work shipped by CAT-002
   / SYSARCH-002").
3. **Wait for PROJPARTS-001 to consolidate project_parts +
   catalog_parts, then revisit MECH-001 with a clean substrate.**

Option 3 is the cleanest and best matches the prompt queue's intent
(PROJPARTS-001 is the next queued prompt after MECH-001).

---

## Recommended phase plan

Two viable paths. Picking one is **your call before I proceed**.

### Path A (recommended) — Frontend-only redesign

Keep the existing backend as-is. Rebuild the frontend page to match
the SYSARCH/Catalog design language while still using the existing
`mechanicalJointsAPI.list/create/get/patch/delete/approve` and
`project_parts`-keyed model.

- **Phase 1: skipped** (no migration needed).
- **Phase 2: skipped** (backend already complete).
- **Phase 3: minimal types/api work** — the existing
  `mech-types` / `parts-api.ts` already exists; might need
  `MechanicalJointSummary` shaping for the card grid.
- **Phase 4: page rewrite** — three-tab layout (`overview`,
  `joints`, `parts-with-joints`), stat strip, card grid,
  AddJointModal using a `ProjectPartPicker` (mechanical class only,
  filtered via `library_part.material_class` or the
  catalog_part backfill that CAT-002 attached). Existing modal
  components could be lifted from `/parts` if any.
- **Phase 5: tests + completion notes.**

Pros: zero schema risk, leaves the working approve/auto-req chain
untouched, deliverable today.
Cons: doesn't match the literal MECH-001 spec (catalog_part FKs);
the visual lift is the real win, not the schema lift.

### Path B — Defer MECH-001 entirely until PROJPARTS-001

Don't run MECH-001 now. Run PROJPARTS-001 first (it's queued next).
That work will consolidate `project_parts` / `library_parts` /
`catalog_parts`, and then MECH-001 can ship per its literal spec
with `catalog_part_a_id` / `catalog_part_b_id` FKs cleanly.

Pros: ships MECH-001 to spec.
Cons: nothing changes on the mechanical-interfaces page in the
meantime; user has to wait through PROJPARTS-001.

### Path C — Run MECH-001 to the literal spec, accept the parallel table

Add migration 0030 with `mechanical_joints_v2` (catalog-keyed),
fresh router at `/api/v1/mechanical-joints` (no `/projects/` prefix),
new frontend. Old `mechanical_joints` keeps running until manually
migrated.

Pros: matches spec.
Cons: two parallel joint surfaces is a maintenance footgun. Approve
flow, auto-requirements, req-sync listeners, ICD report generation
— all stay wired to the old table. Real users will be confused
which page is canonical.

---

## What I need from you

Pick a path. My recommendation is **Path A** — it ships the visible
UX win (the new page) without touching the working backend, and
leaves the schema consolidation to PROJPARTS-001 where it belongs.

If you want **Path B**, I stop here and queue MECH-001 for after
PROJPARTS-001.

If you want **Path C**, I proceed with the migration + parallel
backend, but I want to flag again: this introduces two
`mechanical_joints` surfaces and someone has to clean it up later.

---

*Phase 0 complete. Awaiting direction.*
