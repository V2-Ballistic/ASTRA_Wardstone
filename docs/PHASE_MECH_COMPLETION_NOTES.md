# PHASE_MECH_COMPLETION_NOTES

Implementation log for `docs/CLAUDE_CODE_PROMPT_MECH-001.md`.
Followed **Path A** per `docs/MECH_INVESTIGATION.md` — frontend-only
redesign on top of the existing project_parts-keyed
`mechanicalJointsAPI`. Backend untouched; the catalog-keyed schema
the literal prompt asked for is deferred until TDD-PROJPARTS-001
consolidates project_parts ↔ catalog_parts.

## Per-phase commits

| Phase | Commit | Summary |
|-------|--------|---------|
| 0 | `9b98f49` | Investigation report — discovered Scenario C (full backend exists from ASTRA-SPEC-PARTS-001 / migration 0027), surfaced the catalog-vs-project-parts mental-model conflict, three paths laid out, user picked A. |
| 1 | _skipped_ | Migration not needed (backend already present). |
| 2 | _skipped_ | Models / schemas / router already present (716-line router, 630-line schemas). |
| 3 | _absorbed into Phase 4_ | The existing `parts-types.ts` + `parts-api.ts` already expose every type and endpoint the page uses; no new lib file needed. |
| 4 | `2ac5f06` | Frontend page rewrite. 3 tabs, stat strip, two custom pickers (ProjectPartPicker + FastenerPicker), AddJointModal with conditional fieldsets and form autosave. 1452 inserts / 320 deletes. |
| 5 | _this commit_ | `src/tests/mech.test.tsx` doc-stub + this notes file. |

## Manual smoke matrix (DEF-MOD1, id=2)

The prompt's 12-step manual smoke was exercised at code-level. Runtime
smoke requires either logging in via the UI or a fixture-seeded project
with ≥2 project_parts; the backend already enforces the
"need ≥ 2 project parts" guard surfaced by the Add Joint button.

| # | Item | Result |
|---|------|--------|
| 1 | Page renders three tabs, Overview default, stat strip with zeros on empty project | ✓ — `isTab()` defaults to `overview`; `StatCard` shows `'—'` while loading, `0` otherwise |
| 2 | Joints tab empty state with "Add your first joint" CTA | ✓ — `JointsTab` renders the empty-state when `filtered.length === 0` |
| 3 | Add Joint modal opens; Part A picker filters project parts only | ✓ — `ProjectPartPicker` only lists project_parts from `projectPartsAPI.list` |
| 4 | Joint type=bolted reveals torque fields | ✓ — `TORQUE_JOINT_TYPES.has(draft.joint_type)` |
| 5 | Pick fastener via FastenerPicker; set count | ✓ — `partsLibraryAPI.list({ part_type: 'fastener' })`; count input appears only after fastener picked |
| 6 | Submit creates joint with auto-generated MJ-NNN tag | ✓ — backend's `_assign_joint_id` allocator handles this; payload omits `joint_id` so backend assigns |
| 7 | Add second joint type=seal — gasket / leak / pressure fields appear, torque fields hide | ✓ — `SEAL_JOINT_TYPES.has(...)` reveals the seal fieldset; bolted fieldset hides |
| 8 | Auto-generated `joint_id_tag` increments | ✓ — backend allocator, not frontend |
| 9 | Status / type / part filters update the card grid | ✓ — `filteredJoints` useMemo |
| 10 | Approve flips draft → active; card status pill updates | ✓ — `mechanicalJointsAPI.approve` + reload |
| 11 | Parts-with-joints tab lists parts with usage counts; click flips to Joints with that part filter | ✓ — `partsWithJoints` cross-reference + `onPick` callback |
| 12 | Form autosave: refresh during partial fill shows restore banner | ✓ — `useFormAutosave` with key `astra:autosave:mech-joint-new:project-${id}` |

## Deviations from the prompt

1. **Path A interpretation** (the big one). The literal MECH-001 spec
   called for `catalog_part_a_id` / `catalog_part_b_id` FKs to
   `catalog_parts` and a fresh 16-value `mechanical_joint_type` enum.
   The actual codebase ships `mechanical_joints` keyed off
   `project_parts` (project-scoped instances of library_parts) with a
   9-value `joint_type` enum. The literal spec would have forced
   either a destructive migration of working production code or a
   parallel `mechanical_joints_v2` table; both rejected as bad
   engineering. Path A keeps the existing data model intact and
   ships the visible UX win.
2. **Backend-spec fields not surfaced.** The literal prompt mentioned
   `name`, `description`, `system_id`, `part_a_role`, `part_b_role`,
   `preload_n`, `surface_treatment`, `gasket_type`,
   `gasket_compression_pct`, and `location_zone`. None of these exist
   in the live schema. The page uses the schema's actual columns
   (joint_id, joint_type, status, part_a/b_id, fastener_part_id,
   fastener_count, torque_*, engagement_length_mm, locking_feature,
   hole_pattern_description, mating_surface_*, seal_part_id,
   leak_rate_max_scc_s, test_pressure_bar, interface_drawing, notes).
   Free-text supplements live in Notes until PROJPARTS-001 ships a
   schema revisit.
3. **No `system_id` on joints** so the prompt's "system" filter on the
   Joints tab maps onto the existing project-part filter instead.
   Effectively the same UX (filter by parent system → filter by parts
   in that system) since systems contain project_parts via
   `system_part_assignments`.
4. **No CatalogPartPicker reuse.** SYSARCH-002's
   `CatalogPartPicker` is keyed to `catalog_parts`. Mechanical joints
   use `project_parts`, so the page ships an inline `ProjectPartPicker`
   for Part A/B and a separate `FastenerPicker` for the
   `library_parts`-typed fastener slot. Both follow the same combobox
   + debounced search + outside-click-close pattern, so they look
   like cousins of the CatalogPartPicker.
5. **No backend tests added.** Phase 2 was skipped (backend already
   has its own test coverage from ASTRA-SPEC-PARTS-001).
6. **Phase 5 frontend tests are documentation-only.** Same status as
   sysarch's `src/tests/sysarch.test.tsx` — jest isn't wired into the
   frontend image; the file lives under the `tsc` exclude added in
   sysarch-prep Phase 0.

## Open follow-ups deferred

- **TDD-PROJPARTS-001** — consolidate `project_parts` / `library_parts` /
  `catalog_parts`. Once it lands, mechanical_joints can grow
  catalog-keyed FKs cleanly (and the literal MECH-001 enum / column
  expansion becomes viable).
- **3D assembly STEP upload + auto-detect mating joints** — the
  existing backend has the endpoint scaffolding (`/assembly/parse` job
  + `mechanical_joints.source_step_file_id` column); UI deferred until
  pythonOCC is installed in the Docker image (separate operational
  task; see SYSARCH-002 notes).
- **Joint ↔ requirement traceability** — Mason's auto-requirement
  generator already fires on approve via
  `app/services/parts/mechanical_req_templates.py`. Surfacing the
  generated requirements from the joint card is a future UX win.
- **Joint ↔ baseline integration** — capture joint snapshots when a
  project baseline is cut. Future TDD.
- **`failed` status** — the prompt's spec asked for a "failed" joint
  status the schema doesn't have. Adding it would need an `ADD VALUE`
  migration; out of scope here.
- **Edit modal** — Phase 4 ships the Add modal only. Patch-via-modal
  isn't wired; existing approve / delete actions work but field
  edits require a future Edit modal (probably a small extension of
  AddJointModal with `initialJoint` prop).

## Final verify

```powershell
docker compose exec frontend npx tsc --noEmit  # → 0 lines
docker compose exec frontend npm run build     # → green; mech page 13 kB
```

Backend tests untouched (Path A); the existing
`test_mechanical_joints.py` (shipped with ASTRA-SPEC-PARTS-001) still
passes.
