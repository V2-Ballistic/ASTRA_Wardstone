# PHASE_PROJPARTS_COMPLETION_NOTES

Implementation log for **TDD-PROJPARTS-001** — "Project Parts as canonical
BOM surface." Executed along **Path C** per
`docs/PROJPARTS_INVESTIGATION.md` — extend the existing `project_parts`
table in place rather than create a parallel `project_part_instances`
table.

## Why Path C

The literal prompt asked for a brand-new `project_part_instances` table
keyed to `catalog_parts`. The codebase already shipped two surfaces
with overlapping intent:

| Surface | Purpose | Keyed off |
|---|---|---|
| `project_parts` (ASTRA-SPEC-PARTS-001) | Project-scoped BOM lines feeding mechanical-joints | `library_parts.id` |
| `units` (TDD-SYSARCH-002) | Project-scoped system-architecture line-replaceable units | `catalog_parts.id` (Phase 2 link) |

Standing up a third surface would have left every downstream consumer
(mechanical_joints, system_part_assignments, the unit ↔ catalog link)
straddling two parallel implementations. Path C unifies on the
existing `project_parts` table — it grows the catalog FK + BOM
metadata in place, keeping every existing FK + ORM relationship intact.

## Per-phase commits

| Phase | Commit | Summary |
|---|---|---|
| 0 | `5d58f51` | Investigation report — surfaced the substrate-collision and laid out paths A/B/C/D; user picked C. |
| 1 | `fe65afb` | Migration 0030 — extend project_parts with `bom_status` PG enum, `catalog_part_id`, `bom_position`, `parent_bom_id`, `quantity_unit`, `status`, `unit_id`, `location_zone`, `installation_notes`, `procurement_notes`, `updated_at`; widen `designation` to 255; change `quantity` INTEGER→NUMERIC(12,4); drop legacy `uq_project_part` UNIQUE and add partial `uq_project_parts_bom_position` (project_id, bom_position) WHERE bom_position IS NOT NULL. |
| 2 | `213b691` | Models + schemas + router extensions + tests. Migration 0031 (drop NOT NULL on `library_part_id`). 8 new test cases (catalog-only create, fractional qty, bom_position partial-UNIQUE, parent self-ref reject, part_class filter, unit-link audit, /stats, non-member 403). |
| 3 | `174345d` | Frontend types + API client — `projparts-types.ts` (BomStatus union, ProjectPartBom row, BomStats, list params, label/color maps, curated `BOM_FILTER_CLASSES`) and `projparts-api.ts` thin wrapper. |
| 4 | `e1a94b2` | Page rewrite at `/projects/[id]/parts` — stat strip, search + status select + part_class chip filter row, card grid, AddBomItemModal wrapping CatalogPartPicker, EditBomItemDrawer with status / qty / unit / parent / location / notes / etc. |
| 5 | _this commit_ | `src/tests/projparts.test.tsx` doc-stub + this notes file. |

## Manual smoke matrix

Backend exercised via pytest (598 passed, 1 skipped on the full
suite). Frontend exercised via tsc + next build (clean). Browser
click-through deferred — the Docker compose stack reports healthy and
the page builds, but I do not have UI driving from this session.

| # | Item | Result |
|---|---|---|
| 1 | Stat strip renders zeros on an empty project | ✓ — `stats?.by_status.planned ?? 0` etc. |
| 2 | Chip filter row hides classes with 0 lines unless active | ✓ — `if (count === 0 && classFilter !== cls) return null` |
| 3 | CatalogPartPicker returns full `CatalogPart`; modal sends `catalog_part_id` | ✓ — `payload.catalog_part_id = catalog.id` |
| 4 | Fractional quantity ("3.5") accepted and persisted | ✓ — backend test `test_fractional_quantity_round_trips` |
| 5 | bom_position partial-UNIQUE: NULLs coexist, duplicates rejected | ✓ — backend test `test_bom_position_partial_unique` exercises both branches |
| 6 | Parent BOM self-reference rejected | ✓ — `PARENT_BOM_SELF_REF` returned 422 |
| 7 | Linking to a unit emits `bom.linked_to_unit` audit (once, not on every diff) | ✓ — backend test `test_link_to_unit_emits_audit_event` |
| 8 | `/stats` aggregates by status + part_class | ✓ — backend test `test_stats_endpoint` |
| 9 | Non-member caller is 403 on every BOM endpoint | ✓ — backend test `test_non_member_forbidden` |
| 10 | Duplicate catalog references are now legal BOM lines (24× M5 + 8× M5) | ✓ — `test_duplicate_library_part_allowed_under_path_c` flipped from the legacy 409 assertion |
| 11 | EditBomItemDrawer sends null (not empty string) on cleared optional fields | ✓ — `value.trim() || null` pattern in the drawer |
| 12 | Card click → drawer opens with seeded state; Save → reload | ✓ — `editRow` state + `key=row.id` re-mount semantics |

## Deviations from the prompt

1. **Path C, not the literal Path A.** The prompt asked for a parallel
   `project_part_instances` table; that's been redirected to extending
   `project_parts` in place. Three downstream tables (`mechanical_joints`,
   `system_part_assignments`, etc.) kept their FKs pointed at
   `project_parts(id)` — zero migration churn for them.
2. **Migration 0031 follow-up.** Migration 0030 forgot to drop the
   legacy `library_part_id NOT NULL`, which would have blocked
   catalog-only BOM writes in production. 0031 fixes that. Pre-flight
   check showed the table is empty so the relaxation is safe.
3. **No legacy `metadata_json.legacy_id` backfill.** The investigation
   report claimed CAT-002 had added that column for backfill, but
   verifying against the actual `catalog_parts` schema showed it
   doesn't exist. `catalog_part_id` therefore ships as a plain
   nullable FK — new writes from the BOM router populate it on every
   create; legacy rows (none today) can be backfilled in a follow-up
   data migration once a deterministic mapping exists.
4. **Audit-event naming.** New canonical events — `bom.created`,
   `bom.updated`, `bom.deleted`, `bom.linked_to_unit` — are emitted
   alongside the legacy `parts_library.project_part_added` /
   `parts_library.project_part_removed` events so existing log
   consumers don't break.
5. **`library_part_id` retained as legacy.** It stays nullable and is
   not removed — the mechanical-joint and system-part-assignment flows
   still expect it. Migration 0031 + the ORM model both make this
   explicit.
6. **Legacy `parts-types.ts` ProjectPartResponse left intact.** The
   mechanical-interfaces page (`/projects/[id]/mechanical-interfaces`)
   assumes a non-null `library_part` on every row and reads
   `quantity` as a number. Touching that file would have rippled the
   change to 25+ touch points unrelated to this TDD; the new BOM
   types live in a separate `projparts-types.ts` file so the mech
   page stays untouched.
7. **Partial UNIQUE expressed at the ORM level.** Migration 0030
   creates it via raw `CREATE UNIQUE INDEX … WHERE …` SQL, but
   SQLite-backed pytest only sees what `Base.metadata.create_all`
   emits. To keep parity, the constraint is declared in
   `__table_args__` with `postgresql_where` + `sqlite_where`. Both
   substrates now enforce it identically.
8. **Phase 5 frontend tests are documentation-only.** Same status as
   sysarch / mech — jest isn't wired into the frontend image; the
   file lives under the `tsc` exclude.

## Open follow-ups deferred

- **Legacy data backfill.** When real `project_parts` rows exist that
  pre-date this work, a data migration will need to map `library_part_id`
  → `catalog_part_id` (where a deterministic mapping is available) and
  default `bom_position` from the existing `designation` column. Today
  the table is empty so this is a future task.
- **bcrypt-driven `unit_id` lock-out.** The Edit drawer's "Linked unit"
  selector loads every project unit; for large projects a future
  iteration should switch to a debounced searchable picker (mirror the
  CatalogPartPicker pattern).
- **BOM hierarchy view.** The data model supports parent → child via
  `parent_bom_id`, but the card grid renders flat with a small
  "parent: <designation>" badge. A future tree-view tab would surface
  the hierarchy directly; the API + indexes are already in place.
- **Auto-create BOM lines from a unit's catalog link.** When a unit
  links to a `catalog_part`, the BOM has zero awareness of it today.
  A future "promote unit → BOM line" CTA would close that loop.
- **`mechanical_joints` catalog FKs.** The literal MECH-001 spec wants
  joints keyed to catalog. With Path C done, that migration is now
  tractable — both sides finally agree on the canonical part identity.
- **Mass roll-up.** Each card shows `mass × qty = total kg` per line.
  A project-level mass total (sum across all BOM lines, by status)
  would slot naturally into the stat strip; left out to keep Phase 4
  focused.

## Final verify

```powershell
# Backend
docker compose exec backend alembic upgrade head     # → 0031 (head)
docker compose exec backend pytest tests/            # → 598 passed, 1 skipped

# Frontend
docker compose exec frontend npx tsc --noEmit        # → 0 lines
docker compose exec frontend npx next build          # → green; /parts page 7.46 kB
```
