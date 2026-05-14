# Claude Code Execution Prompt — System Architecture page rebuild + CAT-002 cleanup

> Replaces the earlier `CLAUDE_CODE_PROMPT_SYSARCH-001.md` which was based on assumptions about the schema that turned out to be wrong. The actual catalog/units schema verified in the DB is much further along than that prompt assumed: `units.catalog_part_id` already exists, the `CatalogPart`↔`Unit` relationship is wired, `units.location_zone` exists, etc. The migration shrinks to nearly nothing.
>
> Includes a small Phase 0 to close out CAT-002's loose ends (missing tests + pre-existing TypeScript errors in old test files) before the SYSARCH work begins.

---

## Mission

Working in **`C:\Users\WardStone\Documents\ASTRA\`** (PowerShell, Docker Desktop). Two pieces of work:

1. **Phase 0 — Close CAT-002's loose ends.** Verify (or write) the three Phase-3 backend tests for the STEP upload flow, silence the pre-existing TypeScript errors that block clean `tsc --noEmit`, and fix the trivial React hooks warning in the new `StepUploadModal.tsx`.

2. **Phases 1-6 — Build out System Architecture.** Replace the 809-byte placeholder page at `/projects/[id]/system-architecture/page.tsx` with a fully-functional three-tab interface (Architecture force graph / Systems / Units). Relocate the existing System Detail and Unit Detail pages out of `/interfaces/...` into `/system-architecture/...`, with server-side redirects so old bookmarks survive. Add a deprecation banner on `/interfaces` Systems tab pointing to the new home (don't remove the tab — that's a separate later TDD).

Single source of architectural truth lives below. There is no separate TDD doc for this run; the spec is here.

Commit per phase. Use commit messages of form `phase-<n>(sysarch): <summary>`. **Do not commit a phase until its verification block passes.** CAT-002 went in unverified twice in a row; we're not doing that again.

---

## Pre-flight — read these REAL files first, before writing anything

The previous SYSARCH attempt failed because it assumed the schema. This time, read what's actually there.

**Backend:**
1. `backend/app/models/interface.py` — the `Unit` model (87 columns, including `catalog_part_id` FK and `library_part_id` legacy FK), the `System` model with `parent_system_id` hierarchy, the `Interface` and `WireHarness` linkages between units. Confirms what already exists.
2. `backend/app/routers/interface.py` — existing `/api/v1/interfaces/systems/*`, `/units/*`, `/block-diagram` endpoints. You're NOT replacing any of these. You're adding a new sibling router.
3. `backend/app/schemas/interface.py` — `UnitResponse`, `SystemResponse`, etc. You'll extend `UnitResponse` to include `catalog_part_summary`.
4. `backend/app/models/catalog.py` — confirms the `project_units = relationship("Unit", back_populates="catalog_part")` line on `CatalogPart`. Means the back-relationship on `Unit` already exists.

**Frontend:**
5. `frontend/src/app/projects/[id]/system-architecture/page.tsx` — the placeholder you're replacing.
6. `frontend/src/app/projects/[id]/interfaces/page.tsx` — has the Systems tab. You're adding a deprecation banner here, NOT removing the tab.
7. `frontend/src/app/projects/[id]/interfaces/system/[systemId]/page.tsx` — System Detail. You're moving this. Read it first.
8. `frontend/src/app/projects/[id]/interfaces/unit/[unitId]/page.tsx` — the canonical Unit Detail.
9. `frontend/src/app/projects/[id]/interfaces/[unitId]/page.tsx` — the legacy variant of Unit Detail. **Compare against #8 carefully** — confirm nothing functional is unique to this variant before you delete it.
10. `frontend/src/components/layout/Sidebar.tsx` — adding a "System Architecture" entry between Verification and Interfaces in the ENGINEERING group.
11. `frontend/src/app/page.tsx` — the **design reference**. Match the stat strip, gradient buttons (`from-blue-500 to-violet-500`), card grid, empty state patterns from this page.
12. `frontend/src/components/traceability/ForceGraph.tsx` — read for force-simulation style only. The cluster layout you need is different (units gravitate toward parent system) so this is a starting point, not a port.
13. `frontend/next.config.js` — adding `redirects()` here.

**Component already in this repo from CAT-002:**
14. `frontend/src/components/parts/StepUploadModal.tsx` — has a React hooks warning to fix (Phase 0).
15. `frontend/src/lib/autosave.ts` — `useFormAutosave` hook from Phase 0; you'll wire it into AddSystemModal and AddUnitModal.

---

## Decisions — locked

| # | Decision | Rationale |
|---|----------|-----------|
| AD-1 | No new migration. The actual schema already has `units.catalog_part_id` (FK to `catalog_parts`), `units.location_zone`, the `Unit.catalog_part` relationship, the `systems.parent_system_id` hierarchy, and `units` has its 87-column override surface for environmental/EMI/etc. That's everything we need. | Verified against live DB. The earlier SYSARCH TDD's migration was unnecessary. |
| AD-2 | Skip `redundancy_role` and `system_code_2letter` columns from the earlier TDD. They're nice-to-have but not blocking the page rebuild. Add them in a future TDD if you need them (HAROLD wiring will likely add `system_code_2letter`). | Don't introduce a migration just to support a future feature. |
| AD-3 | Single page with three tabs at `/projects/[id]/system-architecture` controlled by `?tab=...`. Default tab = `arch` (the force graph). | Consistent with `/interfaces` and `/catalog`. Linkable views. The page is *named* System Architecture — leading with the graph reinforces purpose. |
| AD-4 | Detail pages move under `/system-architecture/system/[id]` and `/system-architecture/unit/[id]`. Old paths get **307 redirects via `next.config.js`**. | Clean URL space. Bookmarks survive. |
| AD-5 | Architecture Graph is custom SVG with a pure-TypeScript cluster force simulation. No D3. Reuse repulsion/gravity ideas from `ForceGraph.tsx`, cluster by parent system. | No new heavy dep. Existing pattern works. |
| AD-6 | Backend graph endpoint is new and dedicated: `GET /api/v1/system-architecture/graph?project_id=N`. Single round-trip return of `{systems, units, edges}` with all data the graph needs. The existing `/interfaces/block-diagram` (system-level) stays unchanged for back-compat. | One round-trip. Doesn't disturb the existing block-diagram which other views use. |
| AD-7 | The `/interfaces` Systems tab stays functional with a deprecation banner. The tab is removed in a future cleanup TDD after a soak release. | Migration safety. Bookmarks survive. |
| AD-8 | Detail pages are moved, not rewritten. Only path/breadcrumb/internal-nav changes plus the catalog-linkage UI additions. | Minimizes risk. The existing pages work today. |
| AD-9 | `CatalogPartPicker` is built generic (accepts `allowedClasses` prop) so a future Project Parts BOM page (TDD-PROJPARTS-001) can reuse it. | Avoid building it twice. |

---

## Standing rules (subset that matters here)

1. **Drop-in file replacements only.** Whole-file output. No partial edits.
2. **No Alembic autogenerate.** This run doesn't need a migration at all (per AD-1), but if you DO end up needing one, hand-write it using `op.execute(text(...))` — don't run `alembic revision --autogenerate`.
3. **SQLAlchemy enum extraction:** `.value` not `str()`.
4. **API list endpoints cap at `limit=200`.**
5. **Backend commands inside the container:** `docker compose exec backend <cmd>`, `docker compose exec db psql -U astra -d astra`. Windows host has no Node or pytest; use `docker compose exec frontend npm <cmd>` and `docker compose exec backend python -m pytest`.
6. **PowerShell:** `curl` is an alias — use `curl.exe`. Avoid `$PID`.
7. **React hooks before any early `return`.** Optional chaining (`unit?.catalog_part_summary`) for null safety.
8. **TypeScript validates clean.** After your changes, `docker compose exec frontend npx tsc --noEmit` must come back clean. Phase 0 is what makes this possible by handling the pre-existing test-file errors.
9. **Python AST validation:** `python3 -c "import ast; ast.parse(open('<f>').read())"` on every Python file before delivery.
10. **Login during testing:** `mason` / `password123` (admin, user_id=1). Project IDs: SMDS=1, DEF-MOD1 (Micro EKV)=2.
11. **Don't drop / don't touch** the 8 existing requirements, the 1 project, `users`, `audit_log`, `electronic_signatures`, the catalog tables (`suppliers`, `supplier_aliases`, `supplier_documents`, `catalog_parts`, `catalog_connectors`, `catalog_pins`, `pending_catalog_imports`), or the new STEP upload code from CAT-002.
12. **Don't run a verification command and silently move past a failure.** If `pytest` fails or `tsc` returns errors that aren't pre-existing test-file issues, surface them and stop. CAT-002 went in untested twice and we got lucky. Don't rely on luck.

---

## Phase 0 — CAT-002 cleanup (do this BEFORE Phase 1)

### 0.1 — Verify the three Phase-3 backend tests exist

```powershell
docker compose exec backend find /app -name "test_step_parser.py" -o -name "test_supplier_aliases.py" -o -name "test_step_upload_flow.py" 2>$null
```

**If all three are found:** re-run pytest with whatever the actual path is. They likely exist; the previous run from `cd C:\Users\WardStone\Documents\ASTRA` may have had a working-dir mismatch.

**If any are missing:** write them per the spec below. They were promised in the CAT-002 Phase 3 commit message but may not have been included in the actual commit. Add them and amend or create a follow-up commit.

Test specs (write only the missing ones):

- `backend/tests/test_step_parser.py` — `test_mcmaster_socket_head_screw` parses the McMaster fixture (mark `pytest.skip` if `backend/tests/fixtures/cad/92196A196_*.STEP` is absent), asserts manufacturer="McMaster-Carr", part_number="92196A196", material_class="stainless_steel", part_class="fastener_screw", part_subtype="socket_head_cap_screw", bbox populated, native_units="inch". Plus `test_inhouse_no_vendor_pattern`, `test_pythonocc_unavailable_fallback` (monkeypatch the OCC import to raise), `test_corrupted_step_returns_useful_error`.
- `backend/tests/test_supplier_aliases.py` — `test_alias_resolution_case_insensitive` (resolves "MCMASTER", "mcmaster", "McMaster" to one row), `test_unique_alias_constraint` (duplicate insert raises IntegrityError), `test_alias_cascade_on_supplier_delete`.
- `backend/tests/test_step_upload_flow.py` — `test_upload_mcmaster_creates_supplier_first_time`, `test_upload_mcmaster_reuses_supplier_second_time`, `test_upload_inhouse_links_to_wardstone`, `test_upload_dedup_rejects_duplicate_hash`, `test_upload_then_approve_creates_catalog_part`.

### 0.2 — Silence the pre-existing TypeScript errors

These 122 errors live in pre-existing test files that have no jest dev deps installed. They are NOT regressions from any of our work. Two options; **go with Option B** unless the user explicitly wants jest wired up.

**Option B (default):** edit `frontend/tsconfig.json` and append to the `exclude` array:

```json
"exclude": [
  "node_modules",
  "**/*.test.ts",
  "**/*.test.tsx",
  "__tests__/**",
  "src/tests/**"
]
```

Verify clean afterwards:

```powershell
docker compose exec frontend npx tsc --noEmit
```

Should come back with no errors.

### 0.3 — Fix the React hooks warning in `StepUploadModal.tsx`

The Phase 4 build flagged: *"React Hook useCallback has a missing dependency: 'handleFileSelect'."* Fix the dependency array. Don't change behavior — just the dep array.

### 0.4 — Phase 0 verify and commit

```powershell
docker compose exec backend python -m pytest backend/tests/test_step_parser.py backend/tests/test_supplier_aliases.py backend/tests/test_step_upload_flow.py -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

All three green → commit:

```
phase-0(sysarch-prep): verify CAT-002 tests, exclude legacy jest files from tsc, fix StepUploadModal hook deps
```

---

## Phase 1 — Backend graph endpoint

**File:** `backend/app/routers/system_architecture.py` (NEW)

Mount at `/api/v1/system-architecture`. One endpoint:

```python
GET /api/v1/system-architecture/graph?project_id=N
```

Response shape:

```python
class SystemArchGraphNode(BaseModel):
    id: int
    type: Literal['system', 'unit']
    label: str                      # for unit: designation; for system: name
    parent_id: Optional[int] = None # system_id for units; parent_system_id for systems
    badge: Optional[str] = None     # 2-letter code or unit_type
    status: Optional[str] = None
    color_hint: Optional[str] = None  # hex
    catalog_part_id: Optional[int] = None
    catalog_part_wpn: Optional[str] = None  # for units, the linked catalog part_number

class SystemArchGraphEdge(BaseModel):
    source: int
    target: int
    source_type: Literal['system', 'unit']
    target_type: Literal['system', 'unit']
    edge_type: Literal['contains', 'parent_of', 'connects_to']
    label: Optional[str] = None
    color_hint: Optional[str] = None

class SystemArchGraphResponse(BaseModel):
    systems: list[SystemArchGraphNode]
    units: list[SystemArchGraphNode]
    edges: list[SystemArchGraphEdge]
```

**Implementation:**
- Project-membership check via `project_member_required` dependency.
- Three queries (or fewer with joins): all systems for project, all units for project, all interfaces (unit↔unit) for project's units, plus all wire_harnesses (unit↔unit) for project's units.
- Edges from three sources:
  - `systems.parent_system_id` → `parent_of` edges (system→system)
  - `units.system_id` → `contains` edges (system→unit)
  - `interfaces` rows that link two units in this project → `connects_to` edges
  - `wire_harnesses` rows that link two units → also `connects_to` (deduplicated by source/target unit pair so a single edge represents either logical interface or physical harness; pick the more-specific label).
- Color hints: derive from system_type / unit_type / signal_type using whatever color maps already exist in the existing `/interfaces` views — extract them into a small constants module if not already.
- Returns empty arrays (status 200) for projects with no systems. Don't return 404.
- Cap result size at 200 systems + 1000 units total. Past that, return 413 Request Entity Too Large with a hint to filter.

**Register in `backend/app/main.py`:**

```python
from app.routers import system_architecture
app.include_router(system_architecture.router, prefix="/api/v1")
```

### Tests

`backend/tests/test_system_arch_graph.py`:
- `test_empty_project_returns_empty_graph` — project with 0 systems → `{systems: [], units: [], edges: []}`, status 200.
- `test_two_systems_three_units_renders_correctly` — assert all 5 nodes present, the 3 containment edges present.
- `test_unit_to_unit_interface_renders_as_connects_to_edge` — fixture an Interface row linking two units; assert the edge appears with type `connects_to`.
- `test_unauthorized_project_returns_403` — non-member request returns 403.
- `test_unit_with_catalog_link_includes_wpn_in_node` — link a unit to a catalog_part; assert `catalog_part_wpn` populated.

### Verify

```powershell
docker compose exec backend python -m pytest backend/tests/test_system_arch_graph.py -v
curl.exe -H "Authorization: Bearer <token>" "http://localhost:8000/api/v1/system-architecture/graph?project_id=2"
```

Commit: `phase-1(sysarch): graph endpoint`

---

## Phase 2 — Backend: catalog_part_summary on Unit responses

The `Unit` model already has a `catalog_part` relationship (the back-side of `CatalogPart.project_units`). Confirm it works; if not, add it explicitly:

```python
# backend/app/models/interface.py:Unit
catalog_part = relationship("CatalogPart", back_populates="project_units", lazy="joined")
```

**Update `backend/app/schemas/interface.py`:**

Add to `UnitResponse`:

```python
class CatalogPartSummary(BaseModel):
    id: int
    part_number: str          # the manufacturer's MPN; this is what the existing schema uses (NOT 'wpn')
    name: str
    part_class: str           # e.g. 'fastener_screw', 'processor', etc. (extended enum from CAT-002)
    part_subtype: Optional[str] = None  # NEW from CAT-002 migration 0029
    mass_kg: Optional[Decimal] = None
    cad_step_path: Optional[str] = None
    cad_preview_path: Optional[str] = None
    icd_doc_path: Optional[str] = None  # if present in schema; otherwise omit
    supplier_name: Optional[str] = None  # joined from supplier
    supplier_is_in_house: Optional[bool] = None  # NEW from CAT-002

class UnitResponse(BaseModel):
    # ... existing fields ...
    catalog_part_summary: Optional[CatalogPartSummary] = None
```

When `unit.catalog_part_id` is null, `catalog_part_summary` must serialize as `null`, not `{}`.

**Update `backend/app/routers/interface.py`:**

In the `GET /interfaces/units/{id}` and `GET /interfaces/units` handlers, populate `catalog_part_summary` from the joined `catalog_part` if present. The existing `Unit` queries don't need to change much — adding `joinedload(Unit.catalog_part).joinedload(CatalogPart.supplier)` to existing queries is enough.

Add `linked_to_catalog: Optional[bool]` query param to `GET /interfaces/units` so the new Units tab in System Architecture can filter "All / Linked / Not Linked." Also add `system_id` filter (probably already exists; verify) for filtering by parent system.

**Audit events on link change:** when `catalog_part_id` changes via PATCH, emit one of three events:
- `unit.linked_to_catalog` (was null, now set)
- `unit.catalog_link_changed` (was X, now Y, both non-null)
- `unit.unlinked_from_catalog` (was set, now null)

Each with `{unit_id, old_catalog_part_id, new_catalog_part_id, project_id}` in the audit details.

### Tests

`backend/tests/test_unit_catalog_summary.py`:
- `test_unit_response_includes_catalog_summary_when_linked` — create unit with catalog_part_id, GET it, assert `catalog_part_summary` populated with WPN, name, mass, supplier info.
- `test_unit_response_summary_is_null_when_unlinked` — unit without catalog_part_id, assert `catalog_part_summary is None` (not empty dict).
- `test_audit_emits_link_event_on_first_link` — patch a unit to add catalog_part_id, assert `unit.linked_to_catalog` audit row.
- `test_audit_emits_change_event_on_relink` — patch from one catalog_part_id to another, assert `unit.catalog_link_changed`.
- `test_audit_emits_unlink_event_on_clear` — patch to set catalog_part_id=null, assert `unit.unlinked_from_catalog`.
- `test_units_list_filter_linked_to_catalog_true` — assert filter returns only linked units.
- `test_units_list_filter_linked_to_catalog_false` — assert filter returns only unlinked units.

### Verify

```powershell
docker compose exec backend python -m pytest backend/tests/test_unit_catalog_summary.py -v
```

Commit: `phase-2(sysarch): UnitResponse.catalog_part_summary + audit events on link changes`

---

## Phase 3 — Frontend types, API client, CatalogPartPicker

**File:** `frontend/src/lib/sysarch-types.ts` (NEW)

```typescript
export interface SystemArchGraphNode {
  id: number;
  type: 'system' | 'unit';
  label: string;
  parent_id?: number;
  badge?: string;
  status?: string;
  color_hint?: string;
  catalog_part_id?: number;
  catalog_part_wpn?: string;
}

export interface SystemArchGraphEdge {
  source: number;
  target: number;
  source_type: 'system' | 'unit';
  target_type: 'system' | 'unit';
  edge_type: 'contains' | 'parent_of' | 'connects_to';
  label?: string;
  color_hint?: string;
}

export interface SystemArchGraphResponse {
  systems: SystemArchGraphNode[];
  units: SystemArchGraphNode[];
  edges: SystemArchGraphEdge[];
}
```

**File:** `frontend/src/lib/sysarch-api.ts` (NEW)

```typescript
export const sysarchAPI = {
  async getGraph(projectId: number) {
    return apiClient.get<SystemArchGraphResponse>(`/system-architecture/graph?project_id=${projectId}`);
  },
};
```

**File:** `frontend/src/components/catalog/CatalogPartPicker.tsx` (NEW)

Reusable searchable picker. Accepts `allowedClasses` prop (e.g. `['processor', 'sensor', 'compute_module', 'lru', ...]`). Calls `/api/v1/catalog/parts?part_class=<allowed>&q=<query>&limit=20` (the existing endpoint accepts a single `part_class` per request — for multiple, send parallel requests and merge client-side, OR extend the backend later; for v1 just accept a single `part_class` prop and let the parent component swap if needed).

Behavior:
- Combobox: input + dropdown.
- Type to search, debounce 300ms.
- Each result: WPN (mono), name, manufacturer chip, part_class chip, mass.
- "None / clear" option at top to deselect.
- Empty state: "No catalog parts match. Upload a STEP file in the Catalog or add manually."
- onChange callback receives the full `CatalogPart` object (or null on clear).

Match the visual language of the existing `/catalog` page list (small text, monospace WPN, astra-surface backgrounds).

### Verify

```powershell
docker compose exec frontend npx tsc --noEmit
```

Should remain clean (Phase 0 made it so). Commit: `phase-3(sysarch): types, api client, CatalogPartPicker`

---

## Phase 4 — System Architecture page rewrite

**File:** `frontend/src/app/projects/[id]/system-architecture/page.tsx` (full replacement of the placeholder)

Three tabs controlled by `?tab=...`:
- `arch` (default) — Architecture force graph
- `systems` — list of systems
- `units` — flat project-wide unit list

**Stat strip** (above tabs, always visible) — four cards matching the Projects dashboard pattern (`frontend/src/app/page.tsx`):

| Card | Icon | Source |
|------|------|--------|
| Systems | `Boxes` (lucide) | count of `systems` rows for project |
| Units | `Cpu` | count of `units` rows for project |
| Catalog Linked | `Link2` | count of `units` rows where `catalog_part_id IS NOT NULL` |
| Hierarchy Depth | `Layers3` | max parent-chain depth across systems (computed client-side from the systems list) |

Each card: `rounded-xl border border-astra-border bg-astra-surface p-4`. Icon top-left tinted, tiny uppercase label, large number, optional sub-text ("3 of 5 linked").

### Tab 2 — Systems list

`frontend/src/components/sysarch/SystemsListTab.tsx` — relocated logic from current `/interfaces` Systems tab.

- Filter row: search input (name/abbreviation/system_id), system_type dropdown, status dropdown.
- Card grid 2-col on `lg`, 1-col on mobile. Each card:
  - Top: gradient avatar (initials of system_type), system name, abbreviation badge, status pill (top-right).
  - Sub-row: system_type chip · WBS number · responsible org.
  - Footer: unit count · interface count · child-system count.
  - Click → navigate to `/system-architecture/system/[id]`.
  - Hover: edit / delete icons appear top-right.
- "Add System" gradient button (top-right).
- Empty state: "No systems defined yet. Add your first system to begin decomposing the architecture." with primary CTA opening AddSystemModal.

### Tab 3 — Units list (NEW project-wide flat view)

`frontend/src/components/sysarch/UnitsListTab.tsx`.

- Filter row:
  - Search (designation, name, manufacturer, part_number, MPN of linked catalog part).
  - System dropdown (filter by parent system).
  - Type dropdown (LRU/SRU/WRU/CCA/PCB/connector/...).
  - Status dropdown.
  - Catalog linkage segmented control: All · Linked · Not linked.
- Card grid 3-col on `xl`, 2-col on `lg`. Each card:
  - Top: gradient avatar (initials of unit_type), designation (mono), name, status pill.
  - Sub-row: parent system chip + unit_type chip + redundancy chip if set.
  - Linkage indicator: if `catalog_part_summary` set → green `Link2` chip with WPN. If null → muted "Not linked to catalog" with a small "Link" action.
  - Metadata: manufacturer · part_number · mass_kg.
  - Click → `/system-architecture/unit/[id]`.
- "Add Unit" gradient button (top-right).
- Empty state: "No units defined. Add a unit to start populating systems." with CTA.

### AddSystemModal

`frontend/src/components/sysarch/AddSystemModal.tsx`. Fields:
- `name` (required)
- `abbreviation` (optional, max 16 chars)
- `system_type` (existing enum dropdown)
- `status` (existing enum, default `concept`)
- `parent_system_id` (optional dropdown of existing systems)
- `wbs_number` (optional)
- `responsible_org` (optional)
- `description` (optional textarea)

POST `/api/v1/interfaces/systems?project_id=N`. Wire `useFormAutosave` with key `astra:autosave:system-new:project-${projectId}`.

### AddUnitModal

`frontend/src/components/sysarch/AddUnitModal.tsx`. Centerpiece is the `CatalogPartPicker` at the top.

Fields, in order:
1. **Catalog part** (`CatalogPartPicker`, optional) — `allowedClasses` prop set to electrical-side values (`processor`, `sensor`, `power_supply`, `radio`, `antenna`, `actuator`, `display`, `harness`, `connector_only`, `compute_module`, `power_distribution`, `interface_card`). When selected, auto-fill items 4-7 below; user can override each.
2. **System** (required dropdown — existing systems in project)
3. **Designation** (required, e.g. `RSP-100`) — uniqueness validated within project (existing validation).
4. `name` (required; pre-fills from catalog)
5. `unit_type` (dropdown; pre-fills based on catalog `part_class` mapping)
6. `manufacturer` (pre-fills from catalog supplier name)
7. `part_number` (pre-fills from catalog `part_number`)
8. `location_zone` (optional)
9. `status` (default `concept`)

POST `/api/v1/interfaces/units?project_id=N` with `catalog_part_id` if a catalog part was picked. Wire `useFormAutosave` with key `astra:autosave:unit-new:project-${projectId}:system-${systemId}`.

### Verify

```powershell
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Manual: navigate to `/projects/2/system-architecture`. Three tabs render. Stat strip computes correctly. Add System and Add Unit modals open and submit. Catalog picker filters and auto-fills.

Commit: `phase-4(sysarch): page rewrite + Systems/Units tabs + modals`

---

## Phase 5 — Architecture force graph

**File:** `frontend/src/components/sysarch/SystemArchGraph.tsx` (NEW)

Custom SVG force-directed cluster graph. Pure-TypeScript force simulation (no D3 dep).

**Layout:**
- Systems = rounded-rect container nodes, ~220×120 px. Title = system name + abbreviation badge. Border tinted by system_type.
- Units = circle nodes (radius 18), positioned inside their parent system's container.
- Edges:
  - Containment (system→unit): faint grey line.
  - Connection (unit→unit, from `connects_to` edges): solid colored line, color by signal_type if known else `#3B82F6`.
  - Hierarchy (system→child system): thick colored line.

**Behavior:**
- Pan & zoom (mouse-wheel + drag). Reset button.
- Click on a system → navigate to `/system-architecture/system/[id]`.
- Click on a unit → navigate to `/system-architecture/unit/[id]`.
- Hover on a unit shows tooltip: designation, system, catalog WPN (if linked), mass.
- Top-right legend: system-type colors + connection-type colors.
- Empty state when no systems: large icon, "Define your first system to start building the architecture", primary CTA opening AddSystemModal.

**Implementation notes:**
- Force simulation in pure TS — gravity toward center, repulsion between nodes, attractive force toward parent system center for units.
- Initial layout: lay out systems in a horizontal grid, run sim ~150 iterations to settle.
- SVG `viewBox="0 0 1280 720"`, responsive width.
- Click vs drag detection: track mousedown position, if mouseup within 5px treat as click; else as pan completion.
- All `useState`/`useEffect`/`useMemo`/`useCallback` calls before any early `return`. Optional chaining for null safety on graph data.
- Reuse the `clsx` import pattern from elsewhere in the codebase.

Data source: `sysarchAPI.getGraph(projectId)` (Phase 3 client). Fetch on mount. Handle loading / error / empty states cleanly.

### Verify

Manual: with 2+ systems and 3+ units, graph renders, pan/zoom works, click navigates, tooltip on hover.

Commit: `phase-5(sysarch): architecture force graph`

---

## Phase 6 — Detail page relocations + sidebar + redirects + deprecation banner

### 6.1 — Move System Detail

**Move:** `frontend/src/app/projects/[id]/interfaces/system/[systemId]/page.tsx` → `frontend/src/app/projects/[id]/system-architecture/system/[systemId]/page.tsx`.

Edits in the moved file:
- Breadcrumb: `${p}/system-architecture` instead of `${p}/interfaces`.
- Back arrow target: same change.
- "Back to Interface Management" copy → "Back to System Architecture".
- All internal navigation pointing into `/interfaces/system/...` or `/interfaces/unit/...` updates to `/system-architecture/...`.
- In the units grid: when a unit has `catalog_part_summary`, show a small `Link2` icon + the catalog WPN as a chip on the card. If null, no chip.

### 6.2 — Consolidate and move Unit Detail

**Two source files** — pick the right base and verify the legacy doesn't carry unique functionality:

- Canonical: `frontend/src/app/projects/[id]/interfaces/unit/[unitId]/page.tsx`
- Legacy: `frontend/src/app/projects/[id]/interfaces/[unitId]/page.tsx`

Compare line-by-line. Use the canonical version as the base. **Before deleting the legacy file**, grep across the frontend for any `router.push` / `Link href` that uses the legacy pattern `/interfaces/${unitId}` (numeric, no `unit/` prefix). Update those callers FIRST. Then delete.

```powershell
# Before deleting, find callers
docker compose exec frontend sh -c "grep -rn '/interfaces/' /app/src --include='*.tsx' --include='*.ts' | grep -v '/interfaces/unit/' | grep -v '/interfaces/system/' | grep -v '/interfaces/auto-requirements' | grep -v '/interfaces/connect' | grep -v '/interfaces/connection' | grep -v '/interfaces/connector' | grep -v '/interfaces/harness' | grep -v '/interfaces/import'"
```

Move target: `frontend/src/app/projects/[id]/system-architecture/unit/[unitId]/page.tsx`.

Edits:
- Breadcrumb / back nav as in 6.1.
- **Catalog linkage banner at top of Overview tab.** When `unit.catalog_part_summary` is set → green banner: "Linked to **<part_number>** · <name>" with mass, CAD-attached badge if `cad_step_path` set, ICD-attached badge if `icd_doc_path` set, supplier chip with "in-house" indicator if `supplier_is_in_house` true. Action buttons: "Edit Link" (re-open CatalogPartPicker), "Unlink" (PATCH catalog_part_id=null with confirmation modal).
- When `catalog_part_summary` is null → amber banner: "Not linked to catalog" with a "Link to Catalog" CTA opening CatalogPartPicker in a modal.
- Catalog-sourced fields (manufacturer, part_number, mass_kg) get a small "from catalog" badge next to them and become read-only when the unit is linked. Unlink to edit.

### 6.3 — Old paths become redirects

**File:** `frontend/next.config.js` — add a `redirects()` async function (or extend if one exists):

```javascript
async redirects() {
  return [
    {
      source: '/projects/:id/interfaces/system/:systemId',
      destination: '/projects/:id/system-architecture/system/:systemId',
      permanent: true,
    },
    {
      source: '/projects/:id/interfaces/unit/:unitId',
      destination: '/projects/:id/system-architecture/unit/:unitId',
      permanent: true,
    },
    // Legacy variant (numeric only — don't catch /interfaces/auto-requirements etc.)
    {
      source: '/projects/:id/interfaces/:unitId(\\d+)',
      destination: '/projects/:id/system-architecture/unit/:unitId',
      permanent: true,
    },
  ];
},
```

The `(\\d+)` regex constraint requires a NUMERIC `unitId`. Without it, the redirect would catch `/interfaces/import`, `/interfaces/connect`, etc. and break those routes.

### 6.4 — Sidebar update

**File:** `frontend/src/components/layout/Sidebar.tsx` — full replacement.

In `getProjectNav(projectId)`, ENGINEERING group, add **between** `Verification` and `Interfaces`:

```typescript
{ href: `${p}/system-architecture`, label: 'System Architecture', icon: Boxes },
```

`Boxes` from `lucide-react`. Don't change anything else in the sidebar.

### 6.5 — Deprecation banner on `/interfaces` Systems tab

**File:** `frontend/src/app/projects/[id]/interfaces/page.tsx` — small modification.

When `tab === 'systems'`, render a banner at the top of the tab body:

```tsx
{tab === 'systems' && (
  <div className="mb-4 flex items-center gap-2 rounded-xl border border-blue-500/30 bg-blue-500/10 px-4 py-3">
    <Info className="h-4 w-4 text-blue-400 flex-shrink-0" aria-hidden="true" />
    <span className="text-sm text-blue-200 flex-1">
      Systems and Units are now managed in <strong>System Architecture</strong>. This tab will be removed in a future release.
    </span>
    <Link href={`${p}/system-architecture?tab=systems`}
      className="rounded-lg bg-gradient-to-br from-blue-500 to-violet-500 px-3 py-1.5 text-xs font-semibold text-white hover:shadow-lg transition">
      Open System Architecture →
    </Link>
  </div>
)}
```

Don't remove the Systems tab itself. Keep its full functionality.

### 6.6 — Phase 6 verify

```powershell
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Manual smoke matrix (run against project DEF-MOD1, id=2):

1. Sidebar shows "System Architecture" between Verification and Interfaces. Click → lands on `/projects/2/system-architecture?tab=arch`.
2. With no systems yet, Architecture tab shows empty-state CTA. Click → AddSystemModal.
3. Add a system "Avionics" with abbreviation "AVN". Stat strip Systems = 1.
4. Add another system "Structures". Switch to Systems tab. Two cards.
5. Switch to Units tab. Click Add Unit. CatalogPartPicker shows electrical catalog parts only. Search the McMaster screw — it should NOT appear (it's a `fastener_screw` not in the electrical-allowed list). Good.
6. To test catalog linkage you need an electrical catalog part. Manually create one via the Catalog → Parts → New Part flow, or use a seed if one exists. Then return to Add Unit, pick it. Fields auto-fill. Submit.
7. Unit card shows green link chip with the catalog WPN.
8. Switch to Architecture tab. Both systems render as containers. The unit appears inside Avionics. Click unit → navigates to `/system-architecture/unit/<id>`.
9. Unit Detail Overview shows green linkage banner. Click "Unlink" → confirm → flips to amber. Click "Link to Catalog" → picker → re-link → green again.
10. Open `/projects/2/interfaces/system/<systemId>` directly — silently redirects to `/projects/2/system-architecture/system/<systemId>`. Same for `/interfaces/unit/<id>`.
11. Open `/projects/2/interfaces?tab=systems` — blue deprecation banner visible. Click banner link → System Architecture loads with Systems tab active.
12. Form autosave: open Add Unit, type a designation, refresh page, restore banner appears at top of modal.

Commit: `phase-6(sysarch): detail page relocations, sidebar, deprecation banner, redirects`

---

## Phase 7 — Tests + completion notes

### 7.1 — Frontend tests

`frontend/src/tests/sysarch.test.tsx`:
- Stat strip computes correct counts from props.
- Tab switching updates URL search param.
- `CatalogPartPicker` debounces search and renders results.
- Empty state on Architecture tab shows the "Add System" CTA when systems list is empty.

(Skip a11y axe additions for now — Phase 0 excluded `src/tests/**` from typecheck. If you want a11y back, that's a follow-up to wire jest-axe properly.)

### 7.2 — Completion notes

Write `docs/PHASE_SYSARCH_COMPLETION_NOTES.md` documenting:
- Per-phase commit hashes and what shipped.
- Manual smoke matrix results against DEF-MOD1.
- Any deviations from this prompt with justification.
- Open follow-ups deferred:
  - **TDD-EI-CLEANUP-001** — actually remove the Systems tab from `/interfaces` after a soak release.
  - **TDD-MECH-001** — Mechanical Interfaces page redesign.
  - **TDD-PROJPARTS-001** — project-level Parts BOM page that reuses `CatalogPartPicker`.
  - **TDD-HAROLD-001** — wire HAROLD nomenclature, add `system_code_2letter` migration if needed.
  - pythonOCC Docker image install (operational, separate).

### 7.3 — Final verify

```powershell
docker compose exec backend python -m pytest backend/tests/ -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

All green → commit: `phase-7(sysarch): tests + completion notes`

---

## Out of scope — do NOT do these

1. **Don't remove the Systems tab from `/interfaces`.** Banner only. TDD-EI-CLEANUP-001 ships the removal after soak.
2. **Don't redesign Mechanical Interfaces.** TDD-MECH-001.
3. **Don't build a project-level Parts BOM page.** TDD-PROJPARTS-001.
4. **Don't wire HAROLD outbound calls.** TDD-HAROLD-001.
5. **Don't add `redundancy_role` or `system_code_2letter` columns.** Per AD-2.
6. **Don't refactor the catalog code.** CAT-002 just shipped.
7. **Don't change the existing `/interfaces/block-diagram` endpoint** — it's used elsewhere. Add a new endpoint for the new graph view.
8. **Don't drop the legacy unit detail file** without first updating its callers (per the grep step in 6.2).
9. **Don't delete the `/parts-library/*` legacy routes.** They link to `library_parts` and `pending_parts_imports` (the old pre-catalog system being phased out). Out of scope.
10. **Don't change the existing System Detail or Unit Detail page structure** beyond breadcrumbs/nav and adding the catalog linkage banner.

---

## Common gotchas

1. **Force simulation perf.** With ~50 nodes the naive O(n²) repulsion is fine. Past ~150 it gets sluggish — leave a TODO. Don't optimize prematurely; SMDS and DEF-MOD1 are nowhere near the limit.
2. **Click vs drag.** Clicking a node should navigate; dragging the canvas should pan. Track `mousedown` position vs `mouseup`; if delta < 5px treat as click.
3. **Pan/zoom math.** SVG `viewBox` updates handle zoom; `transform="translate(x,y)"` on a `<g>` handles pan. Don't combine — they have different invertibility behavior under click handlers.
4. **Hooks before returns.** Many conditional renders in the page component (loading/error/empty/populated). Put ALL `useState`/`useEffect`/`useMemo`/`useCallback` at the top, then early returns. React will throw "rendered fewer hooks than expected" otherwise.
5. **Optional chaining everywhere.** `unit?.catalog_part_summary?.part_number` not chained property access without `?.`. Same for `graph?.systems?.length`.
6. **Modal focus traps.** Both modals must trap focus per WCAG. Use the existing `frontend/src/components/a11y/FocusTrap.tsx` if it exists; if not, the modals can be rendered without one for now (we're already excluding a11y tests from typecheck so this won't fail CI).
7. **Legacy unit detail callers.** Section 6.2 has a grep step. Skipping it creates dead links — silent failure that surfaces only when a user clicks an old bookmark. Do the grep.
8. **`next.config.js` redirect regex.** The `:unitId(\\d+)` requires double-backslash in the JS string literal. Without it, the regex is `:unitId(d+)` which matches nothing.
9. **Catalog filter `part_class` is single-value in the existing `/api/v1/catalog/parts` endpoint.** The `CatalogPartPicker` accepts an array prop — implement it by either (a) sending one request per allowed class and merging client-side, or (b) extending the backend to accept comma-separated. (a) is simpler and in scope; (b) is cleaner but a backend change. Go with (a).
10. **`lazy="joined"` on `Unit.catalog_part`.** Outer-joins on every Unit fetch. Fine for typical cases. If you ever query 1000+ units, switch to `lazy="select"` and batch. Leave a comment, don't optimize now.
11. **The Unit model already has 87 columns and many of them duplicate catalog_parts (mass, voltage, EMI, etc.).** The override pattern is: catalog defines defaults, unit overrides per-instance. The `CatalogPartSummary` we return shows what the catalog says; the unit's own column values are what actually applies. Don't try to reconcile — just expose both.
12. **Don't try to hide the legacy `library_part_id` linkage on Unit.** It's there because the codebase is mid-migration from `library_parts` to `catalog_parts`. Leave it alone. The new code uses `catalog_part_id`.

---

## Sign-off

After Phase 7:

```powershell
docker compose exec backend python -m pytest backend/tests/ -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

All three green → all 7 phase commits in place → write `docs/PHASE_SYSARCH_COMPLETION_NOTES.md` and you're done.

**Critical:** if any phase's verification fails, stop and surface the failure. Don't commit and move on. The pattern of "tests/build not run" leading to compounding undetected bugs has happened twice in this codebase already; this prompt explicitly demands verification at each phase boundary.

If anything in this prompt conflicts with what you find in the actual code, **stop and surface the conflict** with a recommended resolution. Don't refactor existing code outside the scope of this prompt — particularly `app/services/catalog/icd_extractor.py`, the existing CatalogPart approval logic, the `/parts-library/*` legacy routes, the existing `/interfaces` Connections / N² Matrix tabs, or anything in the Phase 0 CAT-002 cleanup beyond what 0.1-0.3 specify.

---

*Prompt version 2.0 — companion to (and supersedes) the earlier `CLAUDE_CODE_PROMPT_SYSARCH-001.md` which was based on incorrect schema assumptions.*
