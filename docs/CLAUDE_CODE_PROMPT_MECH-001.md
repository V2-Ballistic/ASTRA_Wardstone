# Claude Code Execution Prompt — Mechanical Interfaces redesign + joints

> Rebuilds `/projects/[id]/mechanical-interfaces`. The current page is a stub at 5KB (per the build output). This adds proper joint CRUD with two catalog parts per joint, joint type/status filters, design parity with the Projects dashboard, and integration with `CatalogPartPicker` from SYSARCH-002.
>
> **Precondition:** SYSARCH-002 has shipped. `CatalogPartPicker` exists. Mechanical part_class values (`fastener_screw`, `bracket`, `housing`, etc.) exist in the catalog enum from CAT-002.
>
> **Investigation-first:** the prompt's Phase 0 is a discovery pass to find out what currently exists for mechanical joints — the current state may be a placeholder or it may have a partial backend already.

---

## Mission

Working in **`C:\Users\WardStone\Documents\ASTRA\`**. Build out the Mechanical Interfaces page for managing joints between mechanical parts in a project. A joint is a defined relationship between two catalog parts (e.g., bracket-to-chassis bolted joint, gasket-sealed flange) with type, status, torque/preload specs, and traceability. The goal is engineering rigor for mechanical interface control, paralleling what Electrical Interfaces does for connectors/harnesses.

Single source of architectural truth lives below.

Commit per phase. Use `phase-<n>(mech): <summary>`. **Verify each phase before committing** — same rule as SYSARCH.

---

## Pre-flight read — investigate FIRST, design SECOND

The current state of mechanical joints in the codebase is unknown. Investigate before designing.

### Schema discovery

```powershell
cd C:\Users\WardStone\Documents\ASTRA

# Look for any joint-related table
docker compose exec db psql -U astra -d astra -c "\dt" | findstr /i "joint mech"

# If a joints table exists, dump its schema
docker compose exec db psql -U astra -d astra -c "\d mechanical_joints" 2>$null
docker compose exec db psql -U astra -d astra -c "\d joints" 2>$null
```

### Backend discovery

```powershell
docker compose exec backend find /app/app/models -name "*.py" -exec grep -l -i "joint\|mechanical" {} \;
docker compose exec backend find /app/app/routers -name "*.py" -exec grep -l -i "joint\|mechanical" {} \;
docker compose exec backend find /app/app/schemas -name "*.py" -exec grep -l -i "joint\|mechanical" {} \;
```

### Frontend discovery

```powershell
docker compose exec frontend find /app/src -path "*/mechanical*" -type f
```

Read whatever shows up. Then read the existing page itself:

`frontend/src/app/projects/[id]/mechanical-interfaces/page.tsx` — the current stub.

Possible scenarios:

- **Scenario A — nothing exists.** No joint table, no models, no router. The current page is purely a UI stub. → Phase 1 adds migration + models + router + schemas. Phase 2+ does the frontend.
- **Scenario B — partial backend.** A `mechanical_joints` table exists with some columns. → Compare against the spec below; add missing columns via additive migration. Don't rebuild what's there.
- **Scenario C — full backend, weak frontend.** Joints CRUD works backend-side; the page is just visually off. → Skip Phase 1 entirely; go straight to frontend redesign.

**Surface which scenario you're in to the user before proceeding past Phase 0.** Don't assume.

### Standard refs

- `frontend/src/app/page.tsx` — design reference (stat strip, gradient buttons, card grid, empty state).
- `frontend/src/app/catalog/page.tsx` — table-vs-card patterns.
- `frontend/src/app/projects/[id]/system-architecture/page.tsx` — recently rebuilt; mirror the three-tab + stat strip + add-modal pattern.
- `frontend/src/components/catalog/CatalogPartPicker.tsx` — REUSED, with `allowedClasses` set to mechanical values (`fastener_screw`, `fastener_bolt`, `nut`, `washer`, `bracket`, `housing`, `enclosure`, `seal_o_ring`, `bearing`, `spring`, `structural_member`, `mechanical_other`).
- `frontend/src/lib/autosave.ts` — `useFormAutosave` hook for the Add Joint modal.

---

## Decisions — locked

| # | Decision | Rationale |
|---|----------|-----------|
| AD-1 | Each joint references **two** `catalog_parts` via FK columns `catalog_part_a_id` and `catalog_part_b_id`. The "A" part is conventionally the "primary" or "host" part; "B" is the "mating" part. | Most joints are pair-wise. Three-way joints are rare; can be modeled as two joints if needed. |
| AD-2 | Joint type enum: `bolted`, `screwed`, `riveted`, `welded`, `brazed`, `soldered`, `adhesive`, `press_fit`, `threaded`, `pinned`, `keyed`, `clamped`, `gasket_sealed`, `o_ring_sealed`, `tongue_groove`, `other`. | Covers aerospace mechanical joints. Add via `mechanical_joint_type` enum in the migration. |
| AD-3 | Joint status enum: `planned`, `designed`, `analyzed`, `qualified`, `installed`, `verified`, `failed`, `superseded`. | Mirrors lifecycle states. Add via `mechanical_joint_status` enum. |
| AD-4 | Joint specs are **optional** — store on the joint row directly: `torque_nominal_nm`, `torque_min_nm`, `torque_max_nm`, `preload_n`, `surface_treatment`, `gasket_type`, `gasket_compression_pct`, `fastener_count`, `fastener_part_id` (FK to catalog_parts when fastener is itself a catalog item). | Avoid a child table for spec attributes. Mechanical joints have a small fixed set of common attributes; nullable columns are fine. |
| AD-5 | Joint to project relationship: `project_id` FK on the joint. **Not** `system_id` — joints can cross system boundaries. Add an optional `system_id` for organizational filtering only. | Joints often span subsystems (a bracket bolted to a chassis crosses any "structures" / "avionics" boundary). |
| AD-6 | Hand-written migration. Number depends on current head — discover via `alembic current` in Phase 0 and chain accordingly. After SYSARCH ships clean, head is still likely `0029` (SYSARCH didn't add a migration); this would be `0030_mechanical_joints.py`. | Per project standing rule. Verify head before writing. |
| AD-7 | Frontend is a single page with three tabs (`overview` default, `joints`, `parts-with-joints`). No force graph (yet); reserved for future TDD. | Consistent with the three-tab pattern from SYSARCH and Catalog. |
| AD-8 | The "3D assembly upload" feature mentioned in the existing stub (image 5 from earliest screenshots: "Upload an assembly STEP file to auto-detect mating joints when pythonOCC is available") is **deferred**. Don't build it. Future TDD with pythonOCC properly installed. | Keeps scope tight. |

---

## Standing rules (subset)

1. **Drop-in file replacements only.** Whole-file output.
2. **No Alembic autogenerate.** Hand-write the migration.
3. **SQLAlchemy enum:** `.value` not `str()`.
4. **API list cap `limit=200`.**
5. **Backend in container:** `docker compose exec backend <cmd>`. Same for frontend.
6. **PowerShell:** `curl.exe`, no `$PID`.
7. **React hooks before any early `return`.** Optional chaining for null safety.
8. **TypeScript validates clean** post-changes.
9. **Python AST validation** on every Python file.
10. **Login during testing:** `mason` / `password123`. Project DEF-MOD1 (id=2) is the test target.
11. **Don't drop / don't touch** existing requirements (8), projects (1), users, audit_log, electronic_signatures, the catalog tables, the units table, or any work shipped by CAT-002 / SYSARCH-002.
12. **Don't run a verification command and silently move past a failure.** Stop on red.

---

## Phase 0 — Investigation report

Run the discovery commands above. Write a one-page summary to `docs/MECH_INVESTIGATION.md`:

- Which scenario (A/B/C) applies?
- If B: what columns/constraints already exist on `mechanical_joints` (or whatever the table is called)?
- What's the current `mechanical-interfaces/page.tsx` rendering?
- Are there any existing joint-related models, schemas, routers? Paths.
- What's the current alembic head? (Should be 0029 if SYSARCH ran clean.)
- Recommended phase plan based on findings.

**Do not proceed to Phase 1 without this report.** If Scenario C, the migration phase is skipped. If Scenario B, the migration is additive only.

Commit: `phase-0(mech): investigation report`

---

## Phase 1 — Migration (conditional on Phase 0)

**Skip this phase entirely if Scenario C (full backend exists).** Go to Phase 4.

### 1.1 Migration file

Number per current alembic head. Assuming 0029 is head, this is `0030_mechanical_joints.py`. **Verify and adjust** if head is something else.

```python
"""ASTRA-TDD-MECH-001: mechanical joints

Revision ID: 0030
Revises: 0029
Create Date: ...
"""

revision = "0030"
down_revision = "0029"  # confirm via `alembic current` first
branch_labels = None
depends_on = None


def upgrade():
    # Enums (must run outside transaction for ADD VALUE if extending later)
    op.execute("""
        CREATE TYPE mechanical_joint_type AS ENUM (
            'bolted', 'screwed', 'riveted', 'welded', 'brazed', 'soldered',
            'adhesive', 'press_fit', 'threaded', 'pinned', 'keyed', 'clamped',
            'gasket_sealed', 'o_ring_sealed', 'tongue_groove', 'other'
        )
    """)
    op.execute("""
        CREATE TYPE mechanical_joint_status AS ENUM (
            'planned', 'designed', 'analyzed', 'qualified',
            'installed', 'verified', 'failed', 'superseded'
        )
    """)

    op.execute("""
        CREATE TABLE mechanical_joints (
            id                       BIGSERIAL    PRIMARY KEY,
            project_id               INTEGER      NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
            system_id                INTEGER      REFERENCES systems(id) ON DELETE SET NULL,

            joint_id_tag             VARCHAR(64)  NOT NULL,  -- e.g. "MJ-001", project-unique
            name                     VARCHAR(255) NOT NULL,
            description              TEXT,

            joint_type               mechanical_joint_type   NOT NULL,
            status                   mechanical_joint_status NOT NULL DEFAULT 'planned',

            -- Two parts being joined
            catalog_part_a_id        INTEGER      NOT NULL REFERENCES catalog_parts(id) ON DELETE RESTRICT,
            catalog_part_b_id        INTEGER      NOT NULL REFERENCES catalog_parts(id) ON DELETE RESTRICT,
            part_a_role              VARCHAR(64),  -- 'host', 'primary', 'flange', etc. (free text guidance)
            part_b_role              VARCHAR(64),

            -- Optional fastener (when applicable)
            fastener_part_id         INTEGER      REFERENCES catalog_parts(id) ON DELETE SET NULL,
            fastener_count           INTEGER,

            -- Specs (all nullable — different joint types use different specs)
            torque_nominal_nm        NUMERIC(10,3),
            torque_min_nm            NUMERIC(10,3),
            torque_max_nm            NUMERIC(10,3),
            preload_n                NUMERIC(12,2),
            surface_treatment        VARCHAR(128),
            gasket_type              VARCHAR(128),
            gasket_compression_pct   NUMERIC(5,2),

            location_zone            VARCHAR(128),
            notes                    TEXT,

            created_at               TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            updated_at               TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            created_by_id            INTEGER      NOT NULL REFERENCES users(id),

            CONSTRAINT uq_mech_joint_project_tag UNIQUE (project_id, joint_id_tag),
            CONSTRAINT ck_mech_joint_distinct_parts CHECK (catalog_part_a_id <> catalog_part_b_id)
        )
    """)

    op.execute("CREATE INDEX ix_mech_joints_project ON mechanical_joints(project_id)")
    op.execute("CREATE INDEX ix_mech_joints_system ON mechanical_joints(system_id)")
    op.execute("CREATE INDEX ix_mech_joints_part_a ON mechanical_joints(catalog_part_a_id)")
    op.execute("CREATE INDEX ix_mech_joints_part_b ON mechanical_joints(catalog_part_b_id)")
    op.execute("CREATE INDEX ix_mech_joints_status ON mechanical_joints(status)")


def downgrade():
    op.execute("DROP TABLE IF EXISTS mechanical_joints CASCADE")
    op.execute("DROP TYPE IF EXISTS mechanical_joint_status")
    op.execute("DROP TYPE IF EXISTS mechanical_joint_type")
```

### 1.2 Verify

```powershell
docker compose exec backend alembic upgrade head
docker compose exec db psql -U astra -d astra -c "\d mechanical_joints"
docker compose exec db psql -U astra -d astra -c "SELECT enum_range(NULL::mechanical_joint_type)"
docker compose exec db psql -U astra -d astra -c "SELECT COUNT(*) FROM requirements"  # still 8
```

Commit: `phase-1(mech): migration <NNNN> — mechanical_joints table + enums`

---

## Phase 2 — Backend models, schemas, router

### 2.1 `backend/app/models/mechanical_joint.py` (NEW)

`MechanicalJoint` ORM model + `MechanicalJointType` and `MechanicalJointStatus` enums (Python-side, matching the PG enums). FK relationships to `Project`, `System`, `CatalogPart` (three: a, b, fastener), `User`. Add `back_populates` on the related models if they need to surface joints (probably skip for now — not needed for v1 UI).

Register in `app/models/__init__.py`.

### 2.2 `backend/app/schemas/mechanical_joint.py` (NEW)

Pydantic schemas:
- `MechanicalJointCreate` — required: `name`, `joint_type`, `catalog_part_a_id`, `catalog_part_b_id`. `joint_id_tag` auto-generated if not provided (`MJ-001`, `MJ-002`, ...).
- `MechanicalJointUpdate` — all optional.
- `MechanicalJointResponse` — full record + `catalog_part_a_summary` + `catalog_part_b_summary` + `fastener_summary` (all using the same `CatalogPartSummary` shape from SYSARCH-002 Phase 2).
- `MechanicalJointSummary` — list response, lighter (no full CatalogPartSummary, just IDs + names).

### 2.3 `backend/app/routers/mechanical_joint.py` (NEW)

Mount at `/api/v1/mechanical-joints`. Endpoints:

```
GET    /mechanical-joints?project_id=N         — list with filters: joint_type, status, system_id, search
POST   /mechanical-joints?project_id=N         — create
GET    /mechanical-joints/{id}                 — detail
PATCH  /mechanical-joints/{id}                 — update
DELETE /mechanical-joints/{id}                 — soft via status='superseded' OR hard delete (admin only)
GET    /mechanical-joints/{id}/audit           — joint history (use existing audit infrastructure)
```

RBAC: reuse the existing pattern from `app/routers/catalog.py` (req_eng+ for create/update; admin for hard delete; project_member for reads).

Auto-generate `joint_id_tag` if not provided: `MJ-NNN` where NNN is `(MAX(joint_id_tag suffix) + 1)` for the project, or `001` if first.

Audit emit on create/update/delete with `mech_joint.created`, `mech_joint.updated`, `mech_joint.deleted`.

Register in `app/main.py`:
```python
from app.routers import mechanical_joint
app.include_router(mechanical_joint.router, prefix="/api/v1")
```

### 2.4 Backend tests

`backend/tests/test_mechanical_joints.py`:
- `test_create_joint_with_two_catalog_parts` — picks two mechanical catalog parts, creates joint, asserts response includes both part summaries.
- `test_create_rejects_same_part_for_a_and_b` — DB CHECK constraint should prevent this; backend should return 422 with a clear message.
- `test_auto_generated_joint_id_tag` — first joint in project gets MJ-001, second gets MJ-002.
- `test_filter_by_joint_type_and_status` — list endpoint filters work.
- `test_patch_status_transitions` — planned → designed → qualified → installed → verified.
- `test_audit_emitted_on_create_update_delete`.
- `test_unauthorized_project_returns_403`.

### 2.5 Verify

```powershell
docker compose exec backend python -m pytest backend/tests/test_mechanical_joints.py -v
```

Commit: `phase-2(mech): models, schemas, router + tests`

---

## Phase 3 — Frontend types, API client

`frontend/src/lib/mech-types.ts`:
```typescript
export type MechanicalJointType =
  | 'bolted' | 'screwed' | 'riveted' | 'welded' | 'brazed' | 'soldered'
  | 'adhesive' | 'press_fit' | 'threaded' | 'pinned' | 'keyed' | 'clamped'
  | 'gasket_sealed' | 'o_ring_sealed' | 'tongue_groove' | 'other';

export type MechanicalJointStatus =
  | 'planned' | 'designed' | 'analyzed' | 'qualified'
  | 'installed' | 'verified' | 'failed' | 'superseded';

export interface MechanicalJoint {
  id: number;
  project_id: number;
  system_id?: number;
  joint_id_tag: string;
  name: string;
  description?: string;
  joint_type: MechanicalJointType;
  status: MechanicalJointStatus;
  catalog_part_a_id: number;
  catalog_part_b_id: number;
  catalog_part_a_summary?: CatalogPartSummary;  // reuse from sysarch-types
  catalog_part_b_summary?: CatalogPartSummary;
  part_a_role?: string;
  part_b_role?: string;
  fastener_part_id?: number;
  fastener_summary?: CatalogPartSummary;
  fastener_count?: number;
  torque_nominal_nm?: number;
  torque_min_nm?: number;
  torque_max_nm?: number;
  preload_n?: number;
  surface_treatment?: string;
  gasket_type?: string;
  gasket_compression_pct?: number;
  location_zone?: string;
  notes?: string;
  created_at: string;
  updated_at: string;
}
```

`frontend/src/lib/mech-api.ts`:
```typescript
export const mechAPI = {
  listJoints: (params: { project_id: number; joint_type?: string; status?: string; ... }) => ...,
  getJoint: (id: number) => ...,
  createJoint: (project_id: number, body: ...) => ...,
  updateJoint: (id: number, body: ...) => ...,
  deleteJoint: (id: number) => ...,
};
```

Verify: `docker compose exec frontend npx tsc --noEmit`.

Commit: `phase-3(mech): frontend types + API client`

---

## Phase 4 — Page rewrite

`frontend/src/app/projects/[id]/mechanical-interfaces/page.tsx` — full replacement.

Three tabs (`?tab=...`):
- `overview` (default) — dashboard view
- `joints` — joints list with filters
- `parts-with-joints` — view of catalog parts that participate in joints in this project

### Overview tab

Stat strip (matches Projects dashboard pattern):
- **Joints** total (`Wrench` icon, blue)
- **By status** breakdown chip row (Planned · Designed · Qualified · Installed · Verified)
- **Critical** (joints with `failed` status, `AlertTriangle` icon, red)
- **Avg torque spec** (median nominal torque across bolted joints, optional — skip if no data)

Below: a recent activity card showing the last 5 joints created/updated.

### Joints tab

Filter row:
- Search (joint_id_tag, name, part names)
- Joint type dropdown (16 values)
- Status dropdown (8 values)
- System dropdown (filter by parent system if set on joint)

Card grid (3-col xl, 2-col lg):
- Top: `joint_id_tag` (mono) + status pill (top-right)
- Title: `name`
- Joint type chip
- Sub-row: **Part A** chip (catalog WPN, name) → **Part B** chip
- Footer: torque spec if set ("18-22 Nm"), location_zone if set
- Click → opens edit modal (or detail page if you prefer; modal is simpler for v1)
- Hover: edit + delete icons

"Add Joint" gradient button top-right of the grid. Empty state: "No joints defined yet. Add your first joint to start tracking mechanical interfaces." with CTA.

### Parts-with-joints tab

Read-only cross-reference: list of catalog parts (mechanical class only) that appear as A, B, or fastener in any joint in this project. Each row shows:
- Part WPN + name + class chip
- Count of joints (e.g. "Used in 4 joints")
- Click → filters Joints tab to joints involving this part

This is just a different lens on the same data. Useful for "which parts have we already designed joints for" questions.

### AddJointModal

`frontend/src/components/mech/AddJointModal.tsx`:

Fields:
1. **Part A** — `CatalogPartPicker` with `allowedClasses` = mechanical values
2. **Part B** — same picker
3. `joint_type` (required dropdown — 16 values)
4. `name` (required, with auto-suggested format like "{part_a_name}-{part_b_name} {joint_type} joint")
5. `joint_id_tag` (auto-generated, override-able)
6. `status` (default `planned`)
7. `system_id` (optional dropdown of project systems)
8. **Fastener** — optional `CatalogPartPicker` with `allowedClasses` = `['fastener_screw', 'fastener_bolt', 'nut']`
9. `fastener_count` (number input, only shown if fastener picked)
10. `torque_nominal_nm`, `torque_min_nm`, `torque_max_nm` (visible only when joint_type ∈ {bolted, screwed, threaded})
11. `preload_n` (visible only for bolted/screwed)
12. `surface_treatment` (free text)
13. `gasket_type`, `gasket_compression_pct` (visible only when joint_type ∈ {gasket_sealed, o_ring_sealed})
14. `location_zone` (free text)
15. `notes` (textarea)

Use `useFormAutosave` with key `astra:autosave:mech-joint-new:project-${projectId}`.

POST to `/api/v1/mechanical-joints?project_id=N`. Close modal on success, refresh joint list, flash success toast.

EditJointModal is the same component with prefilled state — pass an optional `initialJoint` prop.

### Verify

```powershell
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Manual smoke (DEF-MOD1, id=2):

1. Navigate to `/projects/2/mechanical-interfaces`. Three tabs visible. Overview is default. Stat strip shows zeros.
2. Switch to Joints tab. Empty state with "Add your first joint" CTA.
3. Click "Add Joint". Modal opens. Part A picker shows mechanical catalog parts only (no electrical LRUs). Pick a bracket. Pick a chassis as Part B.
4. Set joint_type=bolted. Torque fields appear. Set 18 / 16 / 22 Nm.
5. Pick a fastener (a screw catalog part). Set fastener_count=4.
6. Submit. Modal closes, joint card appears in grid. `joint_id_tag` auto-generated as `MJ-001`.
7. Add a second joint, gasket_sealed type — confirm gasket fields appear and torque fields hide.
8. `joint_id_tag` auto-generates as `MJ-002`.
9. Filter by status=planned — both visible. Filter by joint_type=bolted — only first.
10. Click first joint card → edit modal opens with prefilled data. Change status to designed, save. Card updates.
11. Switch to "Parts with Joints" tab. The bracket and chassis show with "Used in 1 joint" / "Used in 2 joints" depending on overlap.
12. Form autosave: open Add Joint, partial fill, refresh — restore banner appears.

Commit: `phase-4(mech): page rewrite + Joints/Overview/Parts tabs + AddJointModal`

---

## Phase 5 — Tests + completion notes

### 5.1 Frontend tests

`frontend/src/tests/mech.test.tsx`:
- Stat strip computes from props.
- Tab switching updates URL.
- AddJointModal validates same-part-for-A-and-B → shows inline error.
- Conditional fields show/hide based on joint_type.

### 5.2 Completion notes

`docs/PHASE_MECH_COMPLETION_NOTES.md`:
- Per-phase commits + scenarios encountered in Phase 0.
- Manual smoke matrix results.
- Open follow-ups: 3D assembly STEP upload (deferred until pythonOCC), joint-to-requirement traceability, joint-to-baseline integration.

### 5.3 Final verify

```powershell
docker compose exec backend python -m pytest backend/tests/test_mechanical_joints.py -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Commit: `phase-5(mech): tests + completion notes`

---

## Out of scope — do NOT do these

1. **Don't build the 3D assembly STEP upload / auto-detect feature.** Deferred until pythonOCC is properly installed in the Docker image (separate operational task).
2. **Don't link joints to requirements yet.** Joint-to-requirement traceability is a future TDD.
3. **Don't link joints to baselines.** Future TDD.
4. **Don't extend `CatalogPartPicker`.** Use it as-is from SYSARCH-002.
5. **Don't refactor the Catalog or System Architecture pages.** Mechanical Interfaces is its own surface.
6. **Don't drop or modify the `/parts-library/*` legacy routes.** Out of scope.
7. **Don't add joint-to-joint relationships.** A joint is a pair of parts; no nesting.

---

## Common gotchas

1. **`catalog_part_a_id` and `catalog_part_b_id` referencing different parts.** The DB CHECK constraint enforces this. Backend should also validate and return a clean 422 with the message "Part A and Part B must be different catalog parts." Frontend should show this inline before submitting.
2. **Auto-generated `joint_id_tag` race condition.** Two simultaneous creates could pick the same `MJ-NNN`. Wrap the create in a transaction with a SELECT FOR UPDATE on the project row, or use `INSERT ... RETURNING` with retry on UNIQUE conflict. Simple version: catch `IntegrityError` and retry once with the next number.
3. **Conditional fields in AddJointModal.** Hooks discipline — `useState` for every field, including the conditionally-rendered ones, before any conditional rendering. The fields don't unmount, they just hide.
4. **Mechanical part_class values must exist in the `part_class` enum.** They were added in CAT-002 migration 0029. Confirm via `SELECT enum_range(NULL::part_class)` if the picker comes back empty.
5. **CatalogPartPicker `allowedClasses` prop.** Pass an array. The picker may need to make multiple parallel requests if the backend `/catalog/parts` only accepts a single `part_class` per request — that's how SYSARCH built it. Don't try to extend the backend; merge client-side.
6. **`fastener_part_id` is independent of `catalog_part_a_id` / `catalog_part_b_id`.** A bolted joint has Part A (the bracket) + Part B (the chassis) + fastener (the screw). Three distinct catalog references.
7. **Soft delete.** Setting status to `superseded` is the recommended "delete" path. Hard delete is admin-only and should be discouraged in the UI.
8. **Audit emit.** Use the existing `_audit` helper from `app/services/audit_service`. Pattern: `_audit(db, "mech_joint.created", "mechanical_joint", joint.id, current_user.id, {...details...}, project_id=joint.project_id, request=request)`.
9. **Join cardinality on list endpoint.** `GET /mechanical-joints?project_id=N` does 3 joins per row (part A, part B, fastener) plus supplier joins. Use `joinedload` to avoid N+1. For 200 joints that's ~600 part fetches; with joinedload it's one query with multiple JOINs — fine.

---

## Sign-off

```powershell
docker compose exec backend python -m pytest backend/tests/test_mechanical_joints.py -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

All green → all phase commits → write `docs/PHASE_MECH_COMPLETION_NOTES.md`. Done.

If anything in this prompt conflicts with what's in the actual code (especially Phase 0 findings), **stop and surface the conflict.** Don't refactor catalog work, SYSARCH work, or anything outside `/projects/[id]/mechanical-interfaces/*` and `/api/v1/mechanical-joints/*`.

---

*Prompt version 1.0.*
