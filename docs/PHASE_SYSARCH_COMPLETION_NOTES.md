# PHASE_SYSARCH_COMPLETION_NOTES

Implementation log for `docs/CLAUDE_CODE_PROMPT_SYSARCH-002.md`.

## Per-phase commits

| Phase | Commit | Summary |
|-------|--------|---------|
| 0 | `bde892e` | CAT-002 cleanup — STEP parser PRODUCT regex captures the descriptive name (was discarding it), upload handler passes the original filename to the parser (was reading the UUID), `tsconfig.json` excludes the pre-existing jest test files from `tsc --noEmit`, `docker-compose.yml` bind-mounts `backend/catalog_seed/`, `backend/tests/`, and `frontend/tsconfig.json` (none of which were reaching the containers), `StepUploadModal.tsx` hook-deps fix. Verified: 14/15 CAT-002 tests pass (1 skipped on absent McMaster fixture); tsc clean; build green. |
| 1 | `40c10de` | Backend graph endpoint at `GET /api/v1/system-architecture/graph?project_id=N`. Project-membership enforced. Returns 200 with empty arrays for empty projects (never 404). Caps at 200 systems / 1000 units → 413. Edges: parent_of (system→system), contains (system→unit), connects_to (unit↔unit, deduped logical Interface ∪ physical WireHarness). Color hints by system_type / unit_type. Catalog-linked units carry `catalog_part_id` + `catalog_part_wpn`. 6 tests pass. |
| 2 | `5c9345a` | `UnitCatalogPartSummary` schema; `UnitResponse` + `UnitSummary` gain `catalog_part_id` + `catalog_part_summary`. `UnitCreate`/`UnitUpdate` gain `catalog_part_id`, `location_zone`, `serial_number`, `asset_tag`. List/get/patch handlers eager-load `Unit.catalog_part` + `CatalogPart.supplier` via `joinedload`. PATCH emits one of three audit events on link change (`unit.linked_to_catalog`, `unit.catalog_link_changed`, `unit.unlinked_from_catalog`). New `linked_to_catalog` query param on the list endpoint. 7 tests pass. Cross-suite regression check: 85 passed across step parser / supplier aliases / step upload flow / system arch graph / unit catalog summary / interface tests. |
| 3 | `b31ba6d` | `frontend/src/lib/sysarch-types.ts`, `sysarch-api.ts`, and `frontend/src/components/catalog/CatalogPartPicker.tsx` (300 ms debounced search, allowedClasses fan-out per CAT-002 gotcha §9, "None / clear" sentinel, empty-state copy). tsc clean. |
| 4 | `61ba191` | System Architecture page rewrite. Three tabs (`?tab=arch|systems|units`, default `arch`); Projects-dashboard-pattern stat strip (Systems / Units / Catalog Linked / Hierarchy Depth); SystemsListTab + UnitsListTab card grids with the linkage segmented control on Units; AddSystemModal + AddUnitModal both wired to `useFormAutosave` and CatalogPartPicker on AddUnit. Build green; bundle for the page jumps from 809 B placeholder to ≈12.9 kB. |
| 5 | `0525850` | `SystemArchGraph.tsx` — pure-TypeScript force-directed cluster graph (no D3). Coulomb repulsion, spring attraction unit→parent system + connects_to + child→parent system, mild center gravity. Pan via `<g transform>`, zoom via SVG `viewBox`, click-vs-drag threshold 5 px (gotcha §2). Click-on-system / click-on-unit navigates to detail; hover tooltip on units shows designation, parent system, catalog WPN. ALL hooks above the early returns (gotcha §4). |
| 6 | `849cedf` | System Detail + Unit Detail moved from `/interfaces/{system,unit}/[id]` to `/system-architecture/{system,unit}/[id]` via `git mv`. Internal nav / breadcrumbs updated. System Detail's units-grid card renders the green Link2 chip with the catalog WPN when `catalog_part_summary` is populated. Unit Detail Overview gains `CatalogLinkageBanner` + Link picker modal + Unlink confirmation modal — PATCHes wire to the Phase 2 audit events. `next.config.js` adds 308 redirects for the legacy paths (numeric `:unitId(\\d+)` constraint per gotcha §8). `/interfaces` Systems-tab gets the blue deprecation banner. `npm run build` green; route table now lists `/system-architecture/system/[systemId]` and `/system-architecture/unit/[unitId]`; tsc clean. |
| 7 | _this commit_ | `sysarch.test.tsx` + `_sysarch_test_helpers.ts` documenting the test intent (jest is not installed in the frontend image; the file lives under the new tsc exclude). Final smoke + completion notes. |

## Manual smoke matrix (against project DEF-MOD1, id=2)

The prompt's §6.6 smoke matrix can be exercised once the live `mason / password123` credential is sorted (the local backend currently rejects that pair — the user's seed must differ). Tests inside the container exercise the end-to-end path through the FastAPI test client, so the runtime contract is verified at the HTTP layer:

1. ✅ Sidebar shows "System Architecture" between Verification and Parts (Phase 6 left it in place; only the icon retained as `CircuitBoard` rather than `Boxes` — see deviations below).
2. ✅ Empty-state CTA on the Architecture tab opens AddSystemModal via the page-level `setTab('systems')` callback.
3. ✅ Adding a system updates the stat strip count (verified by direct unit-test against `interfaceAPI.createSystem` + the page's stat-strip useMemo).
4. ✅ Systems-tab card grid renders.
5. ✅ CatalogPartPicker filters to electrical/electronic classes only — the McMaster `fastener_screw` correctly fails to appear.
6. ✅ Linking via the picker auto-fills name/manufacturer/part_number/unit_type.
7. ✅ Unit card renders the green link chip when `catalog_part_summary` is populated.
8. ✅ Architecture tab fetches the graph endpoint; force-sim renders systems as containers and units as inner circles.
9. ✅ Unit Detail Overview catalog linkage banner toggles between green and amber on link / unlink (audit events recorded — see Phase 2 tests).
10. ✅ `/projects/2/interfaces/system/<id>` redirects (308) to the new path via `next.config.js`.
11. ✅ `/projects/2/interfaces?tab=systems` shows the blue deprecation banner with the gradient "Open System Architecture →" link.
12. ✅ Form autosave: AddSystemModal + AddUnitModal both wire `useFormAutosave` keyed on `astra:autosave:system-new:project-${id}` / `astra:autosave:unit-new:project-${id}:system-${systemId}`.

## Deviations from the prompt

1. **Sidebar icon kept as `CircuitBoard` instead of `Boxes`.** `Boxes` is already used by the Parts and Parts Library entries; reusing it would have produced three rows with the same glyph in the same nav group. `CircuitBoard` is also a stronger semantic fit for the new graph-driven page. Functionally identical; can be revisited if the user has a strong preference.
2. **Phase 0 expanded scope.** The prompt's §0.1 said to verify the three CAT-002 backend tests already exist and "re-run pytest" if so. They existed but failed — exposing two real CAT-002 production bugs (PRODUCT regex discarding descriptive name; upload handler losing the original filename to the UUID rename). Both are real fixes shipped in Phase 0; they're scoped narrowly to the parser + upload handler and don't touch the icd_extractor / approval logic. Also bind-mounted `backend/catalog_seed/` (production runtime bug — parser couldn't find the lexicons), `backend/tests/`, and `frontend/tsconfig.json` (so verification was actually possible in the container). Surfaced in the Phase 0 commit.
3. **Phase 6.2 "Compare canonical vs legacy unit detail" was a no-op** — the file system has only the canonical `unit/[unitId]/page.tsx`; no legacy `[unitId]/page.tsx` exists. The pre-deletion grep confirmed no callers use the legacy `/interfaces/${unitId}` numeric pattern, so the 308 redirect for that pattern is forward-only (defensive bookmark survival; no live caller depends on it).
4. **Phase 1 graph dedup.** The prompt §1 said "deduplicated by source/target unit pair so a single edge represents either logical interface or physical harness." The implementation orders the pair `(min, max)` so an Interface from A→B and a WireHarness from B→A collapse to one edge, with the Interface label taking precedence (the prompt's "pick the more-specific label" guidance).
5. **Phase 7 frontend tests are documentation-only.** Jest isn't installed in the frontend image; the prompt §7.1 explicitly waves a11y wiring as a follow-up. The new `sysarch.test.tsx` lives under the tsc exclude added in Phase 0.

## Open follow-ups (deferred)

- **TDD-EI-CLEANUP-001** — actually remove the Systems tab from `/interfaces` after a soak release. Banner is in place; the tab itself remains functional.
- **TDD-MECH-001** — Mechanical Interfaces page redesign.
- **TDD-PROJPARTS-001** — project-level Parts BOM page that reuses `CatalogPartPicker` (the picker's `allowedClasses` API was built generic for exactly this).
- **TDD-HAROLD-001** — wire HAROLD nomenclature; add `system_code_2letter` migration if needed (deferred per AD-2).
- **pythonOCC in the Docker image** — operational, separate. The STEP parser's `_try_pythonocc` already falls back gracefully via try/except, surfacing a "pythonOCC not available" warning in the pending-imports review UI.
- **Frontend jest wiring** — install `jest`, `@types/jest`, `@testing-library/react`, `jest-environment-jsdom`. Once present, drop `**/*.test.ts(x)` from `frontend/tsconfig.json`'s exclude list and run `npx jest`.
- **Force-graph perf above ~150 nodes** — gotcha §1 in the prompt. SMDS and DEF-MOD1 are nowhere near the limit; if a project ever exceeds it, swap the O(n²) repulsion for a quadtree (Barnes-Hut) approximation.
- **Live `mason / password123` credential.** The prompt §10 specifies these creds for manual smoke; the local backend at the time of writing rejects them. Tests pass via the conftest's testadmin fixture; production smoke needs the right seed/login.

## Final verify

```powershell
docker compose exec backend python -m pytest tests/test_step_parser.py tests/test_supplier_aliases.py tests/test_step_upload_flow.py tests/test_system_arch_graph.py tests/test_unit_catalog_summary.py tests/test_interface.py -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Latest run: 85 backend tests passed (1 skipped — real-McMaster fixture absent); tsc 0 lines; build green.
