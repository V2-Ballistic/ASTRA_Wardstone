# Claude Code Execution Prompt — Project Parts BOM page

> Builds out `/projects/[id]/parts` as the project-level BOM (Bill of Materials) view. Distinct from `/projects/[id]/system-architecture/units` — Units are LRU instances with electrical pinouts; **BOM line items** are catalog parts placed into a project with quantity, designation, and BOM position. Same `catalog_parts` source, different relationship cardinality.
>
> **Precondition:** SYSARCH-002 has shipped. `CatalogPartPicker` exists. CAT-002 mechanical part_class values are in the catalog enum.

---

## Mission

Working in **`C:\Users\WardStone\Documents\ASTRA\`**. Replace the current minimal `/projects/[id]/parts` page with a proper BOM management interface. The BOM tracks every part instance in a project: structural fasteners (qty 24), gaskets (qty 4), brackets (qty 1), processors (qty 1), connectors (qty 8), etc. Each line item references a `catalog_parts` row.

This is **the BOM**. Not the unit list. Units (electrical instances) live in System Architecture; BOM (everything in the build) lives here.

Single source of architectural truth lives below. Commit per phase. Verify before each commit.

---

## Pre-flight read

### Schema discovery

```powershell
cd C:\Users\WardStone\Documents\ASTRA

# Check if a BOM-like table already exists
docker compose exec db psql -U astra -d astra -c "\dt" | findstr /i "bom part_instance project_part"

docker compose exec db psql -U astra -d astra -c "\d project_part_instances" 2>$null
docker compose exec db psql -U astra -d astra -c "\d project_parts" 2>$null
docker compose exec db psql -U astra -d astra -c "\d bom_line_items" 2>$null
```

If any of those exist, read the schema. Surface findings before designing.

### Backend / frontend discovery

```powershell
docker compose exec backend find /app/app -name "*.py" -exec grep -l "project_part\|BomLineItem\|bom_line" {} \;
docker compose exec frontend find /app/src/app -path "*/parts*" -type f
```

Read whatever shows up.

### Standard refs

- `frontend/src/app/projects/[id]/parts/page.tsx` — the current page (per build output it's 4.73 kB; likely a stub or minimal listing).
- `frontend/src/app/page.tsx` — design reference.
- `frontend/src/app/catalog/page.tsx` — table-vs-card patterns.
- `frontend/src/app/projects/[id]/system-architecture/page.tsx` — three-tab + stat strip + add-modal pattern.
- `frontend/src/components/catalog/CatalogPartPicker.tsx` — REUSED with broad `allowedClasses` (mechanical + electrical + electromechanical + cots) since BOM holds everything.
- `frontend/src/lib/autosave.ts` — `useFormAutosave`.
- `backend/app/models/catalog.py` — CatalogPart relationship side. `project_units = relationship("Unit", back_populates="catalog_part")` exists; we'll add a parallel `project_part_instances` relationship.

### Conceptual clarity

The relationship between Units (electrical, in `units` table) and BOM Line Items (in the new `project_part_instances` table):

| Concept | Storage | Cardinality vs catalog | Examples |
|---------|---------|------------------------|----------|
| **Unit** | `units` table (87 cols) | 1 unit per physical box | RSP-100 (one specific Radar Signal Processor with serial number 1234) |
| **BOM line item** | `project_part_instances` (NEW) | quantity per BOM position | "M5×16 socket head screw — qty 24 in chassis assembly" |

A unit may also be tracked as a BOM line item (qty=1, with serial). For now, keep them separate — the Unit row is canonical for electrical things; the BOM row is canonical for everything you'd see on a parts list. Reconciliation between the two surfaces is an Integration Validator job (future).

---

## Decisions — locked

| # | Decision | Rationale |
|---|----------|-----------|
| AD-1 | New table `project_part_instances` separate from `units`. | Cardinality differs (BOM has quantity; Unit is singular). Future integrity checks can reconcile. |
| AD-2 | BOM row has: project FK, catalog_part FK, quantity, designation (free text, e.g. "Bolt set 12"), bom_position (e.g. "1.2.3.4" hierarchical), location_zone, status, notes, parent_bom_id (for BOM tree structure). | Standard MBSE BOM shape. The hierarchical `parent_bom_id` enables nested assembly views later. |
| AD-3 | Quantity is numeric (not integer) — `NUMERIC(12,4)` — to support fractional units (3.5 meters of cable, 0.25L of adhesive). | Real BOMs have non-integer quantities for materials. |
| AD-4 | `unit_id` optional FK — if a BOM line item corresponds to a tracked Unit, link them. Most BOM items won't have this. | Optional reconciliation between BOM and Units. |
| AD-5 | BOM status enum: `planned`, `released`, `procured`, `received`, `installed`, `verified`, `obsolete`. | Tracks the BOM lifecycle. |
| AD-6 | Hand-written migration. Number per current alembic head. After SYSARCH ships clean head is 0029; if MECH-001 ran first it might be 0030. **Verify head before writing.** | Project standing rule. |
| AD-7 | Page is single tab (no sub-tabs) with strong filtering: by part class chip row, by status, by parent assembly. The chip filter row is the primary affordance. | BOM is a long flat list; tabs would be over-engineering. |
| AD-8 | Add BOM Item modal uses `CatalogPartPicker` with broad `allowedClasses` (all classes — mechanical and electrical alike). | BOM holds everything. |
| AD-9 | **Hierarchical view** is a future TDD. v1 ships flat. Display `bom_position` as text only ("1.2.3.4"). The `parent_bom_id` column is in the schema for forward compatibility but not surfaced in the UI yet. | Tree views with drag-reorder are a 2-week feature on their own. Ship the flat version first; iterate. |

---

## Standing rules (subset)

1. **Drop-in file replacements only.** Whole-file output.
2. **No Alembic autogenerate.**
3. **SQLAlchemy enum:** `.value` not `str()`.
4. **API list cap `limit=200`.**
5. **Backend in container.** Frontend in container.
6. **PowerShell:** `curl.exe`, no `$PID`.
7. **React hooks before any early `return`.**
8. **TypeScript validates clean** post-changes.
9. **Python AST validation** on every Python file.
10. **Login during testing:** `mason` / `password123`. Project DEF-MOD1 (id=2).
11. **Don't drop / don't touch** existing requirements (8), projects (1), units, catalog work, SYSARCH work.
12. **Don't run a verification command and silently move past failure.**

---

## Phase 1 — Migration

`backend/alembic/versions/<NNNN>_project_part_instances.py`. Verify head first via `alembic current`.

```python
def upgrade():
    op.execute("""
        CREATE TYPE bom_status AS ENUM (
            'planned', 'released', 'procured', 'received',
            'installed', 'verified', 'obsolete'
        )
    """)

    op.execute("""
        CREATE TABLE project_part_instances (
            id                  BIGSERIAL    PRIMARY KEY,
            project_id          INTEGER      NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            catalog_part_id     INTEGER      NOT NULL REFERENCES catalog_parts(id) ON DELETE RESTRICT,

            -- BOM identity
            designation         VARCHAR(255) NOT NULL,
            bom_position        VARCHAR(64),                     -- "1.2.3.4" hierarchical position
            parent_bom_id       BIGINT       REFERENCES project_part_instances(id) ON DELETE SET NULL,

            -- Cardinality
            quantity            NUMERIC(12,4) NOT NULL DEFAULT 1.0,
            quantity_unit       VARCHAR(16)  NOT NULL DEFAULT 'each',  -- each, m, L, kg, etc.

            -- Lifecycle
            status              bom_status   NOT NULL DEFAULT 'planned',

            -- Optional unit linkage
            unit_id             INTEGER      REFERENCES units(id) ON DELETE SET NULL,

            -- Free-form attributes
            location_zone       VARCHAR(128),
            installation_notes  TEXT,
            procurement_notes   TEXT,

            created_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at          TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            created_by_id       INTEGER      NOT NULL REFERENCES users(id),

            CONSTRAINT uq_project_bom_position UNIQUE (project_id, bom_position)
        )
    """)

    op.execute("CREATE INDEX ix_ppi_project ON project_part_instances(project_id)")
    op.execute("CREATE INDEX ix_ppi_catalog_part ON project_part_instances(catalog_part_id)")
    op.execute("CREATE INDEX ix_ppi_unit ON project_part_instances(unit_id)")
    op.execute("CREATE INDEX ix_ppi_parent ON project_part_instances(parent_bom_id)")
    op.execute("CREATE INDEX ix_ppi_status ON project_part_instances(status)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS project_part_instances CASCADE")
    op.execute("DROP TYPE IF EXISTS bom_status")
```

Verify:
```powershell
docker compose exec backend alembic upgrade head
docker compose exec db psql -U astra -d astra -c "\d project_part_instances"
docker compose exec db psql -U astra -d astra -c "SELECT COUNT(*) FROM requirements"  # still 8
```

Commit: `phase-1(projparts): migration <NNNN> — project_part_instances table + bom_status enum`

---

## Phase 2 — Backend models, schemas, router

### 2.1 `backend/app/models/project_part_instance.py` (NEW)

`ProjectPartInstance` ORM with:
- FKs to Project, CatalogPart (joined load), Unit (optional, joined), parent (self-ref)
- `BomStatus` Python enum matching the PG enum
- `back_populates` on `CatalogPart.project_part_instances` (add this side too)

Register in `app/models/__init__.py`.

Add to `app/models/catalog.py:CatalogPart`:
```python
project_part_instances = relationship("ProjectPartInstance", back_populates="catalog_part")
```

### 2.2 Schemas: `backend/app/schemas/project_part_instance.py` (NEW)

- `ProjectPartInstanceCreate` — required: `catalog_part_id`, `designation`, `quantity`. Defaults: `quantity_unit='each'`, `status='planned'`.
- `ProjectPartInstanceUpdate` — all optional.
- `ProjectPartInstanceResponse` — full record + `catalog_part_summary` (reuse from sysarch-types) + optional `unit_summary` + optional `parent_designation`.
- `ProjectPartInstanceListItem` — lighter list response.
- `BomStatsResponse` — for the stat strip: counts by status + by part class.

### 2.3 Router: `backend/app/routers/project_parts.py` (NEW)

Mount at `/api/v1/project-parts`. Endpoints:

```
GET    /project-parts?project_id=N           — list with filters (part_class, status, search, parent_bom_id)
GET    /project-parts/stats?project_id=N     — for the stat strip
POST   /project-parts?project_id=N           — create
GET    /project-parts/{id}                   — detail
PATCH  /project-parts/{id}                   — update
DELETE /project-parts/{id}                   — soft (status=obsolete) by default; admin can hard delete
GET    /project-parts/{id}/audit             — history
```

`part_class` filter on list endpoint queries through the catalog FK: `JOIN catalog_parts ON catalog_part_id WHERE part_class = $1`.

RBAC: req_eng+ for create/update; admin for hard delete; project_member for reads. Reuse the pattern from `app/routers/catalog.py`.

Audit emit on create/update/delete: `bom.created`, `bom.updated`, `bom.deleted`, plus `bom.linked_to_unit` when `unit_id` transitions from null to set.

Register in `app/main.py`.

### 2.4 Backend tests

`backend/tests/test_project_part_instances.py`:
- `test_create_bom_line_with_catalog_part` — picks a catalog part, sets quantity=24, designation="M5×16 chassis bolts", asserts response includes catalog_part_summary.
- `test_quantity_supports_fractional` — quantity=3.5, quantity_unit="m" works.
- `test_bom_position_unique_per_project` — same `bom_position` in same project → 422; same `bom_position` in different project → fine.
- `test_parent_bom_id_self_reference_works` — child's parent points to a sibling line; assert response includes parent_designation.
- `test_filter_by_part_class` — list endpoint filters by part_class via catalog join.
- `test_link_to_unit` — patch unit_id; assert `bom.linked_to_unit` audit event.
- `test_stats_endpoint` — returns counts by status and by part class.
- `test_unauthorized_returns_403`.

Verify:
```powershell
docker compose exec backend python -m pytest backend/tests/test_project_part_instances.py -v
```

Commit: `phase-2(projparts): models, schemas, router + tests`

---

## Phase 3 — Frontend types + API client

`frontend/src/lib/projparts-types.ts`:
```typescript
export type BomStatus =
  | 'planned' | 'released' | 'procured' | 'received'
  | 'installed' | 'verified' | 'obsolete';

export interface ProjectPartInstance {
  id: number;
  project_id: number;
  catalog_part_id: number;
  catalog_part_summary?: CatalogPartSummary;
  designation: string;
  bom_position?: string;
  parent_bom_id?: number;
  parent_designation?: string;
  quantity: number;
  quantity_unit: string;
  status: BomStatus;
  unit_id?: number;
  unit_summary?: { id: number; designation: string; system_id: number };
  location_zone?: string;
  installation_notes?: string;
  procurement_notes?: string;
  created_at: string;
  updated_at: string;
}

export interface BomStats {
  total: number;
  by_status: Record<BomStatus, number>;
  by_part_class: Record<string, number>;
}
```

`frontend/src/lib/projparts-api.ts`:
```typescript
export const projPartsAPI = {
  listBom: (params: { project_id: number; part_class?: string; status?: BomStatus; search?: string }) => ...,
  getStats: (project_id: number) => ...,
  getItem: (id: number) => ...,
  createItem: (project_id: number, body: ...) => ...,
  updateItem: (id: number, body: ...) => ...,
  deleteItem: (id: number) => ...,
};
```

Verify: `docker compose exec frontend npx tsc --noEmit`.

Commit: `phase-3(projparts): types + API client`

---

## Phase 4 — Page rewrite

`frontend/src/app/projects/[id]/parts/page.tsx` — full replacement.

Single page (no tabs). Layout top to bottom:

### Header
- Title: "Parts" (or "Bill of Materials" if you want to be explicit — `Parts` matches the sidebar/route, simpler).
- Subtitle: "All parts placed in this project — fasteners, brackets, electronics, materials."

### Stat strip (4 cards)
- **Total Items** (`Package` icon, blue) — sum of rows
- **By Status** breakdown chips (Planned · Released · Procured · Installed · Verified)
- **Distinct Catalog Parts** (`Library` icon, violet) — `count(distinct catalog_part_id)`
- **Quantity Sum** (`Sigma` icon, emerald) — sum of `quantity` for `quantity_unit='each'` items only (free-form units like meters/liters don't aggregate sensibly; show "+ N other units" hint)

### Filter row
- **Part class chip row** (top-level): All · Mechanical · Electrical · Electromechanical · Structural · COTS · S/F · Software (chips matching CAT-002 part_class enum groupings)
- Search input (designation, catalog WPN, catalog name, location_zone)
- Status dropdown (8 values)
- "Add Item" gradient button (top-right, blue→violet)

### Card grid
3-col xl, 2-col lg, 1-col mobile. Each card:
- Top: gradient avatar (initials of part_class), `bom_position` (mono if set, else "—"), status pill (top-right)
- Title: `designation` (bold, truncate)
- Sub-row: catalog WPN chip (mono) + `quantity` × `quantity_unit` chip (e.g. "24 each" or "3.5 m")
- Linked catalog name (smaller text)
- Location zone (if set)
- Hover: edit + delete icons

Click → opens edit modal (modal is enough for v1; full detail page can be a future iteration).

Empty state (matches Projects dashboard pattern): large `Package` icon, copy "No parts in this project yet. Add your first BOM item to start tracking your build.", primary CTA button "Add Item" (gradient).

### AddBomItemModal

`frontend/src/components/projparts/AddBomItemModal.tsx`:

Fields:
1. **Catalog part** — `CatalogPartPicker`, broad `allowedClasses` (mechanical + electrical + electromechanical + structural + cots + software_firmware values; basically everything except connector_only at the catalog level — adjust based on what's actually in the catalog enum). Required.
2. `designation` (required) — auto-suggested from catalog name + position counter, e.g. "M5×16 SHCS – Item 12"
3. `bom_position` (optional, auto-suggested incrementally if empty: "12", "13", ...)
4. `quantity` (required, default 1)
5. `quantity_unit` (dropdown: each / m / cm / mm / kg / g / L / mL / m² / m³ / set / pair, default `each`)
6. `status` (default `planned`)
7. **Parent BOM item** (optional dropdown of existing BOM items in this project) — for hierarchy
8. **Linked unit** (optional dropdown of project units) — surfaces only when catalog part_class is electrical-flavored
9. `location_zone` (free text)
10. `installation_notes`, `procurement_notes` (optional textareas)

`useFormAutosave` with key `astra:autosave:bom-item-new:project-${projectId}`.

POST to `/api/v1/project-parts?project_id=N`. Close on success, refresh list + stats, flash toast.

Edit reuses the same component with prefilled state.

### Delete handling

Default delete is soft (PATCH status=obsolete). Hard delete is admin-only and behind a confirmation modal that says "Permanently remove this BOM line. Audit log will retain the action."

### Verify

```powershell
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Manual smoke (DEF-MOD1, id=2):

1. Navigate to `/projects/2/parts`. Page renders. Empty state visible. Stats all zero.
2. Click "Add Item". Modal opens. CatalogPartPicker shows catalog parts (broad — mechanical and electrical mixed).
3. Pick a McMaster screw catalog part. Designation auto-suggests "92196A196 – Item 1". Set quantity=24. Submit.
4. Card appears. Stats: Total=1, Distinct Catalog=1, Quantity Sum=24.
5. Click "Add Item" again. Pick a bracket. Designation auto-suggests "...Item 2". Set quantity=4. Set parent BOM = first item. Submit.
6. Card appears with parent reference visible (small "in: 92196A196 – Item 1" subtext). Stats: Total=2, Distinct=2, Quantity Sum=28.
7. Filter chips: click "Mechanical" — both visible. Click "Electrical" — empty. Reset.
8. Search "screw" — first card shows.
9. Click first card → edit modal opens. Change status to "released". Save. Card pill updates.
10. Soft delete (just change status to obsolete via the edit modal). Stats update.
11. Form autosave: open Add Item, partial fill, refresh — restore banner.
12. Confirm broad CatalogPartPicker DOESN'T break the System Architecture AddUnitModal — that one filters to electrical classes only. (Quick check: open `/system-architecture` AddUnitModal, picker still shows electrical only.)

Commit: `phase-4(projparts): page rewrite + AddBomItemModal + stat strip + chip filters`

---

## Phase 5 — Tests + completion notes

### 5.1 Frontend tests

`frontend/src/tests/projparts.test.tsx`:
- Stat strip computes from props.
- Chip filter narrows the visible cards.
- AddBomItemModal validates required fields.
- Auto-suggested designation works.
- CatalogPartPicker accepts broad `allowedClasses` (smoke test).

### 5.2 Completion notes

`docs/PHASE_PROJPARTS_COMPLETION_NOTES.md`:
- Per-phase commits.
- Manual smoke matrix.
- Open follow-ups deferred:
  - Hierarchical BOM tree view (drag/drop reorder, expand/collapse parents).
  - BOM-to-Unit reconciliation report (find Units not represented in BOM, BOM line items that should map to Units).
  - BOM cost rollup (when supplier prices land in catalog).
  - BOM export to CSV / Excel.
  - BOM diff between baselines.

### 5.3 Final verify

```powershell
docker compose exec backend python -m pytest backend/tests/test_project_part_instances.py -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Commit: `phase-5(projparts): tests + completion notes`

---

## Out of scope — do NOT do these

1. **Don't build the hierarchical tree view.** v1 ships flat. The `parent_bom_id` column is a forward-compat hook.
2. **Don't auto-generate BOM lines from Units.** Reconciliation is a future Integration Validator job.
3. **Don't touch System Architecture's Units list.** They're separate surfaces; both query catalog_parts but in different ways.
4. **Don't refactor `CatalogPartPicker`.** Use it with a broader `allowedClasses` prop. If the picker's behavior with multi-class doesn't work cleanly, it's an upstream bug and a separate fix — surface it, don't paper over.
5. **Don't add a `parts/[id]` detail route.** Edit modal is enough for v1.
6. **Don't add cost / pricing / procurement integration.** Future TDD.
7. **Don't add BOM diff between baselines.** Future TDD.
8. **Don't drop the legacy `/parts-library/*` routes.** Out of scope.

---

## Common gotchas

1. **`CatalogPartPicker` with broad `allowedClasses`.** SYSARCH built it to send parallel requests per class and merge. With ~25 enum values that's ~25 parallel HTTP calls. If perf hurts, switch to no class filter (`?part_class=` omitted) for "all classes" and filter client-side. Surface this if you hit a noticeable lag.
2. **Quantity numeric precision.** `NUMERIC(12,4)` allows 99,999,999.9999. More than enough. Frontend should show 4 decimals max but trim trailing zeros for readability ("3.5" not "3.5000").
3. **`bom_position` UNIQUE per project.** Two BOM items can't share the same `bom_position`. The frontend auto-suggester picks the next available integer; users can override to hierarchical strings like "1.2.3" — those won't collide unless the user picks an existing one. Show inline error on collision.
4. **Stat strip math.** `Quantity Sum` only sums `quantity_unit='each'` rows. Other units don't aggregate. Show a small hint in the card: "+ N items in other units (m, kg, …)".
5. **Soft vs hard delete.** Default DELETE button = soft (status='obsolete'). Hard delete behind admin-force flag with explicit confirmation modal.
6. **`unit_id` linkage.** Optional. When set on an electrical-class catalog part, this is the BOM line that corresponds to a tracked Unit. Useful for reconciliation. Don't enforce — most BOM items won't have unit linkage.
7. **Audit emit.** `bom.created`, `bom.updated`, `bom.deleted`, `bom.linked_to_unit`. Use the existing `_audit` helper, pass `project_id` for project-scoped audits.
8. **Don't fetch the full catalog on page mount.** Only when the user opens AddBomItemModal. The picker handles its own debounced search.
9. **Flat list with 200+ rows.** With realistic projects this could grow to 1000s of BOM lines. Pagination via `?skip=N&limit=200`. Frontend should show "Showing 200 of 847 — load more" rather than infinite scroll for v1 (simpler, lets user see total upfront).

---

## Sign-off

```powershell
docker compose exec backend python -m pytest backend/tests/test_project_part_instances.py -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

All green → all phase commits → write `docs/PHASE_PROJPARTS_COMPLETION_NOTES.md`. Done.

If anything in this prompt conflicts with what's actually in the code, **stop and surface the conflict.** Don't refactor catalog work, SYSARCH work, MECH work, or anything outside `/projects/[id]/parts/*` and `/api/v1/project-parts/*`.

---

*Prompt version 1.0.*
