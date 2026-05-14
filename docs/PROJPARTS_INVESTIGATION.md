# PROJPARTS-001 Phase 0 — Investigation Report

> Discovery pass. **Stop and surface findings before proceeding** —
> mirrors the MECH-001 pattern (the PROJPARTS-001 prompt was written
> without knowledge of the existing `project_parts` surface, exactly
> like MECH-001 was written without knowledge of the existing
> `mechanical_joints` surface).

## TL;DR

The prompt's target table `project_part_instances` (new,
catalog-keyed) **conflicts** with the existing `project_parts` table
that's been shipping since `ASTRA-SPEC-PARTS-001` (migration 0027).
The existing table is the project-scoped BOM-equivalent today; it's
referenced by two live downstream consumers
(`mechanical_joints.part_a_id/b_id`, `system_part_assignments.project_part_id`)
and used by the just-rebuilt Mechanical Interfaces page (MECH-001 Path A)
plus the existing `/projects/[id]/parts` page.

Three (really four) viable paths. **Path C is the right engineering**
but is meaningfully more work than the prompt anticipated; Path A
mirrors how MECH-001 was resolved and ships the visible UX win
without schema risk. Your call before I proceed.

---

## Alembic head

```
0029 (head)
```

Matches expectation — MECH-001 was a frontend-only run, no migration added.

---

## Existing tables

```
public | project_parts | table | astra
```

(no `project_part_instances`, no `bom_line_items`, no `part_instance` tables)

### `project_parts` (8 columns, 4 indexes, 3 FKs, 1 CHECK, 1 UNIQUE)

Shipped by migration `0027_parts_library_and_mechanical.py`.

| Column            | Type                     | Notes                                                            |
|-------------------|--------------------------|------------------------------------------------------------------|
| `id`              | `integer` (BIGSERIAL)    | PK                                                               |
| `project_id`      | `integer` NOT NULL       | FK → `projects(id)` CASCADE                                      |
| `library_part_id` | `integer` NOT NULL       | **FK → `library_parts(id)` RESTRICT** — NOT `catalog_parts`      |
| `quantity`        | `integer` NOT NULL DEFAULT 1 | CHECK `quantity >= 1` — **integer**, not numeric(12,4)       |
| `designation`     | `varchar(64)`            |                                                                  |
| `notes`           | `text`                   |                                                                  |
| `added_by_id`     | `integer`                | FK → `users(id)` SET NULL                                        |
| `added_at`        | `timestamptz` NOT NULL   | DEFAULT NOW()                                                    |

Constraints:
- `UNIQUE (project_id, library_part_id)` — one row per (project, library_part) tuple.
- `CHECK quantity >= 1` — integer-only.

**Missing vs PROJPARTS-001 spec:** `catalog_part_id` (the whole point
of the new table), `bom_position`, `parent_bom_id`, `quantity_unit`,
`status` enum (`bom_status`), `unit_id`, `location_zone`,
`installation_notes`, `procurement_notes`, `created_at`, `updated_at`,
`created_by_id`. The existing `added_by_id`/`added_at` is the
project_parts equivalent of created_by/created_at.

Quantity column is **INTEGER**, not the spec's `NUMERIC(12,4)`. So
fractional quantities (3.5 m of cable) aren't supported today.

### Downstream consumers (the constraint)

```
mechanical_joints.part_a_id → project_parts(id) ON DELETE RESTRICT
mechanical_joints.part_b_id → project_parts(id) ON DELETE RESTRICT
system_part_assignments.project_part_id → project_parts(id) ON DELETE CASCADE
```

These tables actively use `project_parts.id`. Any path that drops
or renames `project_parts` breaks both the just-rebuilt Mechanical
Interfaces page (MECH-001) and the System Architecture system-detail
unit grid (the system_part_assignments join). **Neither can be
broken silently.**

---

## Backend already in place

- **Model:** `backend/app/models/parts_library.py` exposes
  `ProjectPart` ORM with `back_populates` to `LibraryPart`,
  `system_assignments` (1:N), `MechanicalJoint` joins through it.
- **Schemas:** `backend/app/schemas/parts_library.py` —
  `ProjectPartResponse`, `ProjectPartCreate`, etc.
- **Router:** `backend/app/routers/project_parts.py` — 8 endpoints
  already mounted (uses `prefix=""` so the actual paths are
  `/api/v1/projects/{project_id}/parts/...`, not the prompt's
  proposed `/api/v1/project-parts`). It already supports
  list / unassigned / create / patch / delete plus
  system-assignment subroutes:
  - `GET    /projects/{project_id}/parts/`
  - `GET    /projects/{project_id}/parts/unassigned`
  - `POST   /projects/{project_id}/parts/`
  - `PATCH  /projects/{project_id}/parts/{id}`
  - `DELETE /projects/{project_id}/parts/{id}`
  - `GET    /projects/{project_id}/systems/{system_id}/parts/`
  - `POST   /projects/{project_id}/systems/{system_id}/parts/`
  - `PATCH/DELETE` on assignments.

The prompt's `/api/v1/project-parts?project_id=N` route shape would
shadow this with a totally different table on a different prefix.

---

## Existing frontend page

`frontend/src/app/projects/[id]/parts/page.tsx` is **339 lines** of
working code (NOT a 4.73 kB stub — that figure was the compiled
bundle size). It already:

- Lists project parts with the linked `library_part` summary.
- Has a part-library picker modal (`partsLibraryAPI.list`).
- Supports add (via library_part_id + designation + quantity) and remove.
- Renders the library-part status pill, part_type chip, material_class chip, etc.
- Routes to `/parts-library/{library_part_id}` for the underlying part detail.

What's missing vs the PROJPARTS-001 vision:

- No SYSARCH-style stat strip.
- No chip filter row by part_class (`Mechanical / Electrical / ...`).
- No status filter (the schema has no status column anyway).
- No `bom_position` / hierarchical view (column doesn't exist).
- No fractional quantity (column is integer).
- Uses the `library_parts` mental model, not the catalog one.

---

## The core conflict — schema model

The prompt assumes a clean substrate: create `project_part_instances`
keyed on `catalog_parts`. The reality:

| Question | PROJPARTS-001 spec | Existing `project_parts` |
|----------|--------------------|--------------------------|
| BOM line FK target | `catalog_parts.id` | `library_parts.id` (legacy) |
| Quantity | `NUMERIC(12,4)` (fractional) | `INTEGER` |
| Status | `bom_status` enum (7 values) | _none_ |
| BOM position / tree | `bom_position` + `parent_bom_id` | _none_ |
| Optional Unit link | `unit_id` FK | _none_ |
| Created-by/at | `created_by_id`/`created_at` | `added_by_id`/`added_at` |
| Used by mech-joints | _new table not used_ | **part_a_id/b_id reference it** |
| Used by sys-parts | _new table not used_ | **project_part_id references it** |
| UNIQUE constraint | `(project_id, bom_position)` | `(project_id, library_part_id)` |

CAT-002 backfilled every `library_parts` row into `catalog_parts`
(catalog_parts row carries `metadata_json.legacy_id → library_parts.id`),
so every existing project_part transitively identifies a catalog_part
— it's just not surfaced via an FK column yet.

---

## Paths

### Path A (mirrors MECH-001 resolution) — Frontend-only redesign

Keep `project_parts` as-is. Don't add `project_part_instances`. Rebuild
the existing `/projects/[id]/parts/page.tsx` to match SYSARCH styling:
stat strip, chip filter row, card grid, AddBomItemModal using a
LibraryPartPicker (analogous to the FastenerPicker in MECH-001).

- **Phase 1 skipped.** No migration.
- **Phase 2 skipped.** Backend already exists.
- **Phase 3 absorbed.** Existing types/api/lib already exposes
  everything the page uses.
- **Phase 4 page rewrite.** SYSARCH visual language, single-page
  flat list, chip filters, autosave on Add modal.
- **Phase 5 tests + notes.**

Pros: zero schema risk; doesn't disturb MECH-001 or SYS-PART
assignments; ships fast.
Cons: no fractional quantity, no status lifecycle, no BOM hierarchy
column, no chip filter by `part_class` (chip filter would key on
the linked `library_part.part_type` instead — different enum, more
limited).

### Path B — Add `project_part_instances` alongside (literal prompt)

Net result: three parallel "parts in a project" surfaces:

1. `library_parts ↔ project_parts` (legacy, used by mech joints + sys parts)
2. `catalog_parts ↔ units` (electrical instances, SYSARCH)
3. `catalog_parts ↔ project_part_instances` (NEW: BOM)

Users see two separate "Parts" surfaces in the same project: one
called Parts (old project_parts) feeding mechanical joints, another
called Parts (new BOM) feeding the new page. Reconciling them is a
maintenance footgun. **Recommended against.**

### Path C (best engineering) — Extend `project_parts` in place

Add the BOM columns and the catalog FK to the existing table:

- ALTER TABLE `project_parts`
  - ADD COLUMN `catalog_part_id INTEGER REFERENCES catalog_parts(id)` (nullable initially)
  - ADD COLUMN `bom_position VARCHAR(64)`
  - ADD COLUMN `parent_bom_id BIGINT REFERENCES project_parts(id) ON DELETE SET NULL`
  - ADD COLUMN `quantity_unit VARCHAR(16) NOT NULL DEFAULT 'each'`
  - ADD COLUMN `status bom_status NOT NULL DEFAULT 'planned'` (new enum)
  - ADD COLUMN `unit_id INTEGER REFERENCES units(id) ON DELETE SET NULL`
  - ADD COLUMN `location_zone VARCHAR(128)`
  - ADD COLUMN `installation_notes TEXT`
  - ADD COLUMN `procurement_notes TEXT`
  - ALTER COLUMN `quantity` TYPE `NUMERIC(12,4)` USING quantity::numeric
  - ALTER COLUMN `designation` TYPE `VARCHAR(255)` (widen from 64)
  - DROP CONSTRAINT `chk_pp_quantity_positive`, ADD `CHECK (quantity > 0)`
  - DROP CONSTRAINT `uq_project_part`, ADD `UNIQUE (project_id, bom_position) WHERE bom_position IS NOT NULL`
- One-shot backfill: `UPDATE project_parts SET catalog_part_id = cp.id FROM catalog_parts cp WHERE cp.metadata_json->>'legacy_id' = project_parts.library_part_id::text` (the CAT-002 backfill marker).
- Extend `ProjectPart` ORM + `ProjectPartResponse` schema.
- Extend the existing `/api/v1/projects/{project_id}/parts/` router
  with new endpoints / fields (don't break the mech-joints or
  sys-parts callers).
- Rebuild the frontend page on top of the unified API.

Pros:
- One canonical project-parts surface that ARES the BOM.
- Mechanical Interfaces page keeps working (FK target unchanged).
- System part assignments keep working.
- Future Unit-reconciliation report has one source of truth.
- Removes the library_parts vs catalog_parts mental fork going forward
  (`catalog_part_id` is the canonical lookup; `library_part_id` is
  the transitional legacy column).

Cons:
- Migration is non-trivial (column ALTERs, type change with USING,
  partial-unique constraint replacement, backfill).
- More work than the prompt anticipated. Realistically 1-2 days of
  careful build + verify.

### Path D — Defer PROJPARTS-001 entirely

Same as MECH-001 Path B. Don't run. Wait for a consolidation TDD
that's scoped to the schema rewrite. Then MECH/PROJPARTS can both
ship cleanly on the new substrate.

---

## Recommendation

**Path C is the right engineering**, but it's bigger than the prompt
budgeted for. If you have the appetite for a careful 1–2 day
migration + extend + rewrite, Path C consolidates a mess of parallel
surfaces and unlocks future work cleanly.

If you want the **visible UX win this session** with zero schema
risk, **Path A** mirrors MECH-001 exactly and ships fast (a couple
hours of frontend rebuild).

I am NOT recommending **Path B** — three parallel "parts in a
project" surfaces is worse than what we have today.

**Path D** is reasonable if PROJPARTS-001 isn't a near-term priority
and you'd rather queue a "Project Parts Consolidation" TDD with a
fresh budget.

---

## What I need from you

Pick A, B, C, or D. My ranking is **C > A > D > B**.

If you pick C, I'll write the migration carefully and stop after it
runs cleanly on the live DB so you can sanity-check before I write
the new endpoints + page.

If you pick A, I rebuild the page on top of the existing API in one
phase, like MECH-001.

If you pick B, I proceed with the migration + parallel table, but
flagging again that this creates a long-term maintenance problem.

If you pick D, I stop here.

---

*Phase 0 complete. Awaiting direction.*
