# Claude Code Execution Prompt — ASTRA-CLEANUP-002

> Four discrete cleanup items found during live ASTRA use:
>
> 1. **CORS fix for LAN access:** browser at `http://192.168.1.74:3000` is CORS-blocked on every backend call. Console shows `No 'Access-Control-Allow-Origin' header is present` on the interfaces, harnesses, connections, and N² matrix endpoints. `BACKEND_CORS_ORIGINS` doesn't include the LAN origin.
> 2. **STEP dedup soft-delete handling:** delete a catalog part with an uploaded STEP, re-upload the same STEP, get opaque dedup error pointing to the soft-deleted supplier_document. Dedup should respect soft-delete.
> 3. **Parts Library removal:** legacy `/parts-library` module from pre-CAT-002 era is still in the sidebar. Superseded by Catalog Parts. Get rid of it.
> 4. **Easy deletion with usage warnings:** pending imports should be deletable directly from the list (not just approve/reject). Catalog parts should be deletable with a clear warning when the part is referenced by a project. Same for any other entity with downstream usage.
>
> All four are localized; none require new architectural decisions. Single cleanup TDD, six phases (Phase 0 investigation + four fix phases + Phase 5 tests + notes), ship.

---

## Mission

Working in `C:\Users\WardStone\Documents\ASTRA\`. Resolve all four issues so:

- LAN access from `192.168.1.74:3000` works on every backend route, not just auth.
- Re-uploading a STEP after deleting the catalog part it belonged to succeeds cleanly — dedup ignores soft-deleted rows.
- Parts Library is removed from the sidebar; routes either deleted or 308-redirected to `/catalog`.
- Pending imports have a "Delete" action in the list. Catalog parts have a "Delete" action that checks downstream usage (`project_parts`, `mechanical_joints` via project_parts FK, `catalog_assembly_components`) and either warns clearly with usage details or blocks with the usage list.

Commit per phase. Use `phase-<n>(cleanup-002): <summary>`. **Verify each phase before commit. Phase 0 is a mandatory stop with a discovery report.**

---

## Pre-flight reads

Mandatory in Phase 0:

- `.env` (`BACKEND_CORS_ORIGINS` line)
- `docker-compose.yml` (backend `environment:` block — how CORS flows through to the container)
- `backend/app/config.py` (`cors_origins` parsing)
- `backend/app/main.py` (CORSMiddleware registration + SecurityHeaders/CSP middleware)
- `backend/app/routers/catalog.py` (STEP upload, dedup check, delete endpoint, list/detail for pending imports)
- `backend/app/services/cad/step_parser.py` (SHA-256 computation, where dedup query lives if not in the router)
- `backend/app/models/catalog.py` (CatalogPart, SupplierDocument, PendingCatalogImport — soft-delete columns, FK relationships)
- `backend/app/models/project.py` (project_parts — FKs into catalog_parts)
- `backend/app/models/mechanical.py` (or wherever mechanical_joints lives — key to project_parts per existing schema)
- `frontend/src/components/layout/Sidebar.tsx` (or wherever the sidebar nav lives)
- `frontend/src/app/parts-library/` (the legacy route tree)
- `frontend/src/app/catalog/pending-imports/page.tsx` (the pending imports list page)
- `frontend/src/app/catalog/parts/[id]/page.tsx` (catalog part detail — where the delete button lives)
- `frontend/next.config.js` (existing redirects)

State check before designing fixes:

```powershell
# CORS — what does .env have and what does the backend parse?
Get-Content .env | findstr -i CORS
docker compose exec backend python -c "from app.config import settings; print(settings.cors_origins)"

# CSP — what origins does the running backend emit?
curl.exe -sI http://localhost:8000/health 2>&1 | findstr -i "content-security-policy"

# Confirm the OPTIONS preflight failure reproduces
curl.exe -v -X OPTIONS "http://192.168.1.74:8000/api/v1/interfaces/connections?project_id=1" `
  -H "Origin: http://192.168.1.74:3000" `
  -H "Access-Control-Request-Method: GET" 2>&1 | findstr "HTTP/ Access-Control"

# SupplierDocument soft-delete columns
docker compose exec db psql -U astra -d astra -c "\d supplier_documents" | findstr "deleted_at"

# CatalogPart soft-delete + FK references
docker compose exec db psql -U astra -d astra -c "\d catalog_parts" | findstr "deleted_at"
docker compose exec db psql -U astra -d astra -c "
  SELECT conname, conrelid::regclass AS referencing_table
  FROM pg_constraint
  WHERE confrelid = 'catalog_parts'::regclass AND contype = 'f'
"

# Sidebar nav items and parts-library route inventory
docker compose exec frontend grep -rn "Parts Library\|parts-library" /app/src --include="*.tsx" 2>&1 | head -30
docker compose exec frontend ls /app/src/app/parts-library 2>&1

# How many catalog_parts vs project_parts vs pending_imports right now?
docker compose exec db psql -U astra -d astra -c "
  SELECT 'catalog_parts' AS table, COUNT(*) FROM catalog_parts
  UNION ALL SELECT 'project_parts', COUNT(*) FROM project_parts
  UNION ALL SELECT 'pending_catalog_imports', COUNT(*) FROM pending_catalog_imports
  UNION ALL SELECT 'supplier_documents', COUNT(*) FROM supplier_documents
"
```

---

## Decisions — locked

| # | Decision | Rationale |
|---|----------|-----------|
| AD-1 | `BACKEND_CORS_ORIGINS` in `.env` includes both `http://localhost:3000` AND `http://192.168.1.74:3000`. Backend container must be recreated (`docker compose up -d backend`, NOT `restart`) to pick up the env change. CSP `connect-src` is already derived from `settings.cors_origins`, so it auto-aligns. | The earlier CSP-from-CORS wiring was correct; the gap is `.env` not listing the LAN origin. Standard env-var hygiene. |
| AD-2 | STEP dedup query filters on `supplier_documents.deleted_at IS NULL`. Soft-deleted documents do NOT block re-upload of the same SHA-256. | Soft-delete semantically means "doesn't exist" for new operations; the row stays for audit but isn't a dedup target. Same logic applies to any other dedup-by-hash query in the codebase. |
| AD-3 | When dedup hits a NON-deleted supplier_document, the 409 response body includes `existing_supplier_document_id`, `existing_pending_import_id` (when an active pending import exists for this document), and `existing_pending_import_url`. Frontend renders a "View existing import" link instead of a wall-of-text error. | Actionable error UX. The current opaque dump-of-internal-IDs error is hostile. |
| AD-4 | Parts Library is **removed from the sidebar**. The `/parts-library/*` routes are **kept** with `308 Permanent Redirect` rules to `/catalog/*` equivalents added in `next.config.js`. Old bookmarks survive; new traffic goes to Catalog. | Discoverable removal without breaking existing deep-links. Sunsetting the routes entirely is a future TDD if Mason wants. |
| AD-5 | Sidebar nav config is data-driven (likely an array of nav items in the Sidebar component). The Parts Library entry is removed from that array; no other layout changes. | Minimal surgery on the navigation; no need to refactor the sidebar component itself. |
| AD-6 | Pending imports get a **Delete** action both inline in the list and on the detail page. Deletion is hard-delete (not soft-delete) because pending imports are pre-catalog ephemeral state — once rejected, no audit value in keeping the row. Cascades to delete the associated `supplier_document` ONLY if no other pending import or approved catalog_part references it. | Pending imports aren't system-of-record; aggressive cleanup is appropriate. The supplier_document cascade prevents orphaned blobs. |
| AD-7 | Catalog part deletion checks downstream usage across `project_parts`, `mechanical_joints`, and `catalog_assembly_components` (parent or child references). Returns a usage report. **If usage exists, the delete is blocked with HTTP 409** and the response body lists every project + entity that references the part. User must remove usage first. | Hard-block, not warn-then-proceed. A part on an active project shouldn't be silently severable; that's exactly the data drift the system is supposed to prevent. |
| AD-8 | NEW endpoint `GET /api/v1/catalog/parts/{id}/usage` returns the usage report (projects + entities) without requiring a delete attempt. Frontend pre-flights this on the delete button hover to show a "Used in 3 projects" badge proactively. | Lets users discover usage before attempting destructive actions. Good UX, cheap endpoint. |
| AD-9 | Pending import delete and catalog part delete each emit audit events: `pending_import.deleted`, `catalog.part.deletion_blocked` (when usage prevents), `catalog.part.deleted` (when successful). | Audit trail for destructive actions; standard practice. |
| AD-10 | The McMaster fixture (`catalog_part_id=1` per memory) has no project usage and is safely deletable. Don't auto-delete it during this TDD; just confirm the flow works against it. | Don't modify fixture data unexpectedly. |

---

## Standing rules

1. **Drop-in file replacements only.** Whole-file output for any modified file.
2. **No Alembic autogenerate.** No new migrations needed for this TDD; if any field-level change emerges, hand-write the migration.
3. **`docker compose up -d backend`** (not `restart`) when `.env` or `docker-compose.yml` changes.
4. **TypeScript validates clean** post-changes: `docker compose exec frontend npx tsc --noEmit` and `docker compose exec frontend npm run build`.
5. **Python AST validation** on every backend Python file: `python -c "import ast; ast.parse(open('path').read())"`.
6. **Stop on red.** Phase 0 is a mandatory stop; subsequent phases verify before commit.
7. **PowerShell** for any host-side commands. `curl.exe` not the alias. Avoid `$PID`.
8. **The McMaster fixture stays put.** No auto-cleanup of `catalog_parts` rows beyond what the test explicitly creates.
9. **Login credentials for browser testing:** `mason` / `password123`.
10. **Don't touch HAROLD** at `C:\Tools\harold` and don't touch its WRENCH-mirrored shim at `C:\opt\wrench\tools-dev\wardstone-harold`. Separate concern.

---

## Phase 0 — Discovery + design report

Mandatory stop.

Tasks:

1. **Capture current state** by running every command in the pre-flight `State check` block. Save raw outputs to `docs/CLEANUP-002_INVESTIGATION.md`.

2. **Identify the exact dedup query** that produces the user-facing error. Likely in `routers/catalog.py` upload-step handler or `services/cad/step_parser.py`. Quote the line numbers.

3. **Map the FK graph** rooted at `catalog_parts`:
   - Direct FKs from `project_parts` (instance layer)
   - Direct FKs from `mechanical_joints` if any (per memory, mechanical_joints key to `project_parts`, but verify)
   - Direct FKs from `catalog_assembly_components` (parent or child)
   - Any other table referencing `catalog_parts.id` — the pre-flight pg_constraint query enumerates this

4. **Inventory the sidebar entries** — list every nav item by label, what route it links to, and which component file defines it. Confirms which exact entry to remove.

5. **Inventory the parts-library routes** — list every page under `frontend/src/app/parts-library/`. Each needs a redirect target in `next.config.js`.

6. **Confirm the McMaster fixture's deletion-safety** — does `catalog_part_id=1` have any rows in `project_parts`, `mechanical_joints`, or `catalog_assembly_components`?
   ```sql
   SELECT 'project_parts' AS source, COUNT(*) FROM project_parts WHERE catalog_part_id = 1
   UNION ALL SELECT 'mechanical_joints', COUNT(*) FROM mechanical_joints WHERE catalog_part_id = 1
   UNION ALL SELECT 'catalog_assembly_components_parent', COUNT(*) FROM catalog_assembly_components WHERE parent_part_id = 1
   UNION ALL SELECT 'catalog_assembly_components_child', COUNT(*) FROM catalog_assembly_components WHERE child_part_id = 1;
   ```
   Document the result.

7. **Confirm `mechanical_joints` ↔ `catalog_parts` relationship** per memory: "Joints key to `project_parts`, NOT `catalog_parts`. `project_parts` table exists as the instance layer." If this is right, then mechanical_joints usage of a catalog_part is *transitive* via project_parts, not direct. Document this — it affects AD-7's usage query.

8. **Plan the parts-library route redirects.** For each existing route, identify the closest catalog equivalent:
   - `/parts-library` → `/catalog`
   - `/parts-library/pending-imports` → `/catalog/pending-imports`
   - `/parts-library/pending-imports/[id]` → `/catalog/pending-imports/[id]`
   - `/parts-library/[id]` → `/catalog/parts/[id]`
   Confirm each redirect target actually exists. If any doesn't, surface it.

Deliver `docs/CLEANUP-002_DESIGN.md` with:
- Investigation outputs.
- Dedup query location + proposed change.
- FK graph rooted at catalog_parts.
- Sidebar entry to remove (line numbers in source).
- Parts-library route → catalog redirect map.
- McMaster fixture deletion-safety state.
- Phase 1-5 plan with any adjustments.

Commit: `phase-0(cleanup-002): discovery + design report`. **Stop.**

---

## Phase 1 — CORS fix for LAN access

After Phase 0 approval:

1. **Update `.env`:**
   ```
   BACKEND_CORS_ORIGINS=http://localhost:3000,http://192.168.1.74:3000
   ```
   If the line already has `http://localhost:3000` only, append the LAN origin separated by comma (no space).

2. **Recreate the backend container** so it picks up the new env value:
   ```powershell
   docker compose up -d backend
   Start-Sleep -Seconds 6
   ```
   Recreation, not restart, is required for env changes to flow into Pydantic Settings.

3. **Verify the running backend sees the new origins:**
   ```powershell
   docker compose exec backend python -c "from app.config import settings; print(settings.cors_origins)"
   # Expected: ['http://localhost:3000', 'http://192.168.1.74:3000']
   ```

4. **Verify the OPTIONS preflight passes:**
   ```powershell
   curl.exe -v -X OPTIONS "http://192.168.1.74:8000/api/v1/interfaces/connections?project_id=1" `
     -H "Origin: http://192.168.1.74:3000" `
     -H "Access-Control-Request-Method: GET" 2>&1 | findstr "HTTP/ Access-Control"
   # Expected: HTTP/1.1 200 OK + Access-Control-Allow-Origin: http://192.168.1.74:3000
   ```

5. **Verify CSP `connect-src` includes the LAN origin** (since CSP derives from `settings.cors_origins`):
   ```powershell
   curl.exe -sI http://localhost:8000/health 2>&1 | findstr -i "content-security-policy"
   # Look for 192.168.1.74 in the connect-src directive
   ```

6. **Browser smoke from the LAN machine.** Open `http://192.168.1.74:3000` from another machine on the network, log in as mason. Navigate to a project's Interface Management page. Confirm the data loads (no CORS console errors).

No code changes in this phase — only `.env`. Commit: `phase-1(cleanup-002): CORS allow-list includes LAN origin`.

---

## Phase 2 — STEP dedup soft-delete handling

Files modified per Phase 0's investigation; the typical locations are:

1. **Backend dedup query** (in `routers/catalog.py` or `services/cad/step_parser.py`):
   ```python
   # BEFORE — finds ANY supplier_document with this hash
   existing = db.query(SupplierDocument).filter(
       SupplierDocument.sha256 == file_hash
   ).first()

   # AFTER — ignores soft-deleted rows per AD-2
   existing = db.query(SupplierDocument).filter(
       SupplierDocument.sha256 == file_hash,
       SupplierDocument.deleted_at.is_(None),
   ).first()
   ```

2. **Enrich the 409 response per AD-3.** When dedup hits a non-deleted document, look up any active pending import for it and include the actionable fields:
   ```python
   if existing:
       active_import = db.query(PendingCatalogImport).filter(
           PendingCatalogImport.supplier_document_id == existing.id,
           PendingCatalogImport.status.in_(["pending_review", "in_review"]),
           PendingCatalogImport.deleted_at.is_(None),
       ).first()
       raise HTTPException(
           status_code=409,
           detail={
               "code": "step_already_uploaded",
               "message": f"This STEP file (sha256={file_hash[:8]}...) was already uploaded.",
               "existing_supplier_document_id": existing.id,
               "existing_pending_import_id": active_import.id if active_import else None,
               "existing_pending_import_url": (
                   f"/catalog/pending-imports/{active_import.id}"
                   if active_import else None
               ),
           },
       )
   ```

3. **Frontend error handling.** Update `frontend/src/lib/errors.ts`' `formatApiError` (or equivalent) to recognize the structured 409 and render the "View existing import" link when `existing_pending_import_url` is present.

4. **Tests:**
   - `backend/tests/test_step_dedup.py` (new or extend):
     - Test: upload STEP, soft-delete the supplier_document, re-upload same STEP → succeeds with new supplier_document row.
     - Test: upload STEP, leave it active, re-upload same STEP → 409 with `existing_pending_import_url` populated.
     - Test: upload STEP, approve the pending import (becomes catalog_part), re-upload same STEP → 409 with `existing_supplier_document_id` but `existing_pending_import_id` is null (no active pending import remaining).
   - Frontend: update upload component test (if one exists) to assert the link renders on a 409 with `existing_pending_import_url`.

5. **Verify:**
   ```powershell
   docker compose exec backend python -m pytest backend/tests/test_step_dedup.py -v
   ```

Commit: `phase-2(cleanup-002): STEP dedup respects soft-delete + actionable 409`.

---

## Phase 3 — Parts Library removal

1. **Sidebar:** edit the nav config component identified in Phase 0. Remove the Parts Library entry. Confirm no orphaned imports or unused icon imports remain.

2. **Next.js redirects:** add to `frontend/next.config.js`:
   ```javascript
   module.exports = {
     // ... existing config ...
     async redirects() {
       return [
         // Parts Library → Catalog (legacy module sunset)
         {
           source: '/parts-library',
           destination: '/catalog',
           permanent: true,
         },
         {
           source: '/parts-library/pending-imports',
           destination: '/catalog/pending-imports',
           permanent: true,
         },
         {
           source: '/parts-library/pending-imports/:id',
           destination: '/catalog/pending-imports/:id',
           permanent: true,
         },
         {
           source: '/parts-library/:id',
           destination: '/catalog/parts/:id',
           permanent: true,
         },
       ];
     },
   };
   ```

3. **The `frontend/src/app/parts-library/` route tree** stays in place for now. Next.js redirects intercept before the routes resolve. (If you want to delete the route tree entirely, that's a follow-up TDD — leaving the files in place is the safer first step.)

4. **Tests:**
   - `npx tsc --noEmit` clean
   - `npm run build` clean (Next.js validates the redirect config at build time)
   - Manual smoke: hit `http://localhost:3000/parts-library` → browser ends up on `/catalog`. Same for the deeper routes.

Commit: `phase-3(cleanup-002): remove Parts Library from sidebar + 308 redirects`.

---

## Phase 4 — Easy deletion with usage warnings

### 4.1 Pending imports deletion

Backend `DELETE /api/v1/catalog/pending-imports/{id}`:

```python
@router.delete("/pending-imports/{id}")
def delete_pending_import(id: int, db: Session = Depends(get_db),
                          current_user: User = Depends(require_auth)):
    pi = db.query(PendingCatalogImport).filter(
        PendingCatalogImport.id == id,
        PendingCatalogImport.deleted_at.is_(None),
    ).first()
    if not pi:
        raise HTTPException(404, "Pending import not found")

    supplier_doc_id = pi.supplier_document_id

    # Hard-delete the pending import row per AD-6
    db.delete(pi)

    # Cascade: delete the supplier_document if no other active reference exists
    if supplier_doc_id:
        other_refs = db.query(PendingCatalogImport).filter(
            PendingCatalogImport.supplier_document_id == supplier_doc_id,
            PendingCatalogImport.id != id,
            PendingCatalogImport.deleted_at.is_(None),
        ).count()
        approved_refs = db.query(CatalogPart).filter(
            CatalogPart.source_document_id == supplier_doc_id,
            CatalogPart.deleted_at.is_(None),
        ).count()
        if other_refs == 0 and approved_refs == 0:
            db.query(SupplierDocument).filter(
                SupplierDocument.id == supplier_doc_id
            ).delete()

    _audit(db, "pending_import.deleted", "pending_catalog_import", id,
           current_user.id, {})
    db.commit()
    return {"deleted": True}
```

Frontend: pending imports list page gets a "Delete" button per row with confirm modal. Pending import detail page also gets the Delete action in the header.

### 4.2 Catalog part deletion with usage check

NEW endpoint `GET /api/v1/catalog/parts/{id}/usage` per AD-8:

```python
@router.get("/parts/{id}/usage")
def get_catalog_part_usage(id: int, db: Session = Depends(get_db),
                            current_user: User = Depends(require_auth)):
    part = db.query(CatalogPart).filter(
        CatalogPart.id == id, CatalogPart.deleted_at.is_(None)
    ).first()
    if not part:
        raise HTTPException(404, "Catalog part not found")

    # Direct: project_parts
    project_parts = db.query(ProjectPart).filter(
        ProjectPart.catalog_part_id == id,
        ProjectPart.deleted_at.is_(None),
    ).all()

    # Transitive: mechanical_joints via project_parts (per memory)
    project_part_ids = [pp.id for pp in project_parts]
    mech_joints = []
    if project_part_ids:
        mech_joints = db.query(MechanicalJoint).filter(
            MechanicalJoint.project_part_id.in_(project_part_ids),
            MechanicalJoint.deleted_at.is_(None),
        ).all()

    # Direct: catalog_assembly_components (parent or child references)
    assembly_refs = db.query(CatalogAssemblyComponent).filter(
        or_(
            CatalogAssemblyComponent.parent_part_id == id,
            CatalogAssemblyComponent.child_part_id == id,
        )
    ).all()

    # Aggregate by project for the UI
    projects_using = {}
    for pp in project_parts:
        proj_id = pp.project_id
        if proj_id not in projects_using:
            project = db.query(Project).filter(Project.id == proj_id).first()
            projects_using[proj_id] = {
                "project_id": proj_id,
                "project_name": project.name if project else "(unknown)",
                "project_code": project.code if project else "?",
                "project_part_count": 0,
                "mechanical_joint_count": 0,
            }
        projects_using[proj_id]["project_part_count"] += 1

    for mj in mech_joints:
        # Find which project this joint's project_part belongs to
        pp = next((pp for pp in project_parts if pp.id == mj.project_part_id), None)
        if pp and pp.project_id in projects_using:
            projects_using[pp.project_id]["mechanical_joint_count"] += 1

    return {
        "part_id": id,
        "part_number": part.part_number,
        "internal_part_number": part.internal_part_number,
        "total_references": len(project_parts) + len(mech_joints) + len(assembly_refs),
        "projects": list(projects_using.values()),
        "assembly_parent_count": sum(1 for a in assembly_refs if a.parent_part_id == id),
        "assembly_child_count": sum(1 for a in assembly_refs if a.child_part_id == id),
        "deletable": len(project_parts) == 0 and len(assembly_refs) == 0,
    }
```

UPDATE `DELETE /api/v1/catalog/parts/{id}` per AD-7:

```python
@router.delete("/parts/{id}")
def delete_catalog_part(id: int, db: Session = Depends(get_db),
                         current_user: User = Depends(require_auth)):
    # Reuse the usage logic
    usage = get_catalog_part_usage(id, db, current_user)

    if not usage["deletable"]:
        _audit(db, "catalog.part.deletion_blocked", "catalog_part", id,
               current_user.id, {"usage": usage})
        db.commit()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "part_in_use",
                "message": f"Cannot delete part. It is used by "
                           f"{usage['total_references']} entit{'y' if usage['total_references']==1 else 'ies'} "
                           f"across {len(usage['projects'])} project(s).",
                "usage": usage,
            },
        )

    part = db.query(CatalogPart).filter(
        CatalogPart.id == id, CatalogPart.deleted_at.is_(None)
    ).first()
    part.deleted_at = datetime.utcnow()
    _audit(db, "catalog.part.deleted", "catalog_part", id,
           current_user.id, {"part_number": part.part_number,
                              "internal_part_number": part.internal_part_number})
    db.commit()
    return {"deleted": True}
```

### 4.3 Frontend usage UI

Catalog part detail page (`frontend/src/app/catalog/parts/[id]/page.tsx`):

- On mount, call `GET /catalog/parts/{id}/usage`. Show a small badge near the Delete button: "Used in 3 projects" or "Not in use".
- Delete button click → confirmation modal. If `usage.deletable === false`, modal shows the project list and the Delete button is disabled with explanation: "Remove this part from N projects before deleting."
- If `deletable === true`, modal asks for confirmation, then calls `DELETE /catalog/parts/{id}`, refreshes the parts list.
- Use the existing `formatApiError` helper for the 409 case — backend's structured response is rendered as a project usage table inline.

Catalog parts list page: each card gets a Delete button (admin only). Same modal flow.

### 4.4 Tests

`backend/tests/test_catalog_deletion.py`:
- Test: delete pending import with no other references → succeeds + supplier_document also deleted.
- Test: delete pending import when supplier_document is referenced by an approved catalog_part → succeeds + supplier_document preserved.
- Test: get usage on a part with 0 references → `deletable: true`, `total_references: 0`.
- Test: get usage on a part with project_parts → `deletable: false`, projects list populated.
- Test: delete a part with no references → succeeds.
- Test: delete a part with project_parts → 409 with structured usage in detail.
- Test: delete a part with mechanical_joints (via project_parts transitively) → 409.
- Test: delete a part used as parent in catalog_assembly_components → 409.

Verify:
```powershell
docker compose exec backend python -m pytest backend/tests/test_catalog_deletion.py -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Commit: `phase-4(cleanup-002): pending import + catalog part deletion with usage check`.

---

## Phase 5 — Tests + completion notes

### 5.1 Final test pass

```powershell
docker compose exec backend python -m pytest backend/tests/ -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

All green.

### 5.2 Smoke walkthrough

Manual browser check:

1. From LAN machine (`http://192.168.1.74:3000`), log in. Navigate to project → Interfaces page. Data loads (Phase 1 verification).
2. Upload a STEP. Approve it. Delete the catalog part. Re-upload the same STEP file. Succeeds with new pending import (Phase 2 verification).
3. Click sidebar — no "Parts Library" entry visible (Phase 3a). Type `/parts-library` directly in the URL bar — browser redirects to `/catalog` (Phase 3b).
4. On a pending imports list, click Delete on a row. Confirm. Row vanishes (Phase 4a verification).
5. On a catalog part detail page that has no project usage, click Delete. Confirm. Part is soft-deleted (Phase 4b).
6. On the McMaster catalog_part, add it to a project as a project_part. Try to delete the catalog_part. Modal shows "Used in 1 project (...)", Delete button disabled (Phase 4b verification).
7. Remove the project_part. Try again. Delete succeeds.

### 5.3 Completion notes

`docs/PHASE_CLEANUP-002_NOTES.md`:
- Per-phase commits.
- The four cleanups, each summarized with the fix location.
- The structured 409 response shape introduced in Phase 2 (callers should consume `existing_pending_import_url`).
- The new usage-check endpoint (Phase 4) and the deletion-blocking pattern.
- Audit events introduced: `pending_import.deleted`, `catalog.part.deletion_blocked`, `catalog.part.deleted`.
- Open follow-ups:
  - Sunset the `frontend/src/app/parts-library/` route tree entirely (separate TDD).
  - Apply the same "delete with usage check" pattern to other entities: suppliers (used by parts), systems (used by units), units (used by connectors and interfaces), etc.
  - Bulk-delete for catalog parts (currently one-at-a-time).
  - "Auto-remove from projects then delete the catalog_part" cascade option for admins (currently hard-blocked, user must manually remove first).

Commit: `phase-5(cleanup-002): tests + completion notes`.

---

## Out of scope — do NOT do these

1. **Don't delete the `frontend/src/app/parts-library/` route tree.** AD-4 keeps the files in place; Next.js redirects handle the traffic. Future TDD removes them entirely.
2. **Don't add bulk-delete UI.** One-at-a-time deletion this round. Bulk is a separate TDD.
3. **Don't add "cascade delete" admin override.** Hard-block when usage exists; admin must manually remove project_parts first. Cascade is a separate, riskier TDD.
4. **Don't change the SHA-256 dedup algorithm itself.** Only change which rows count as "existing" (filter on `deleted_at`). The hash + the column unchanged.
5. **Don't touch HAROLD** at `C:\Tools\harold` or its WRENCH mirror at `C:\opt\wrench\tools-dev\wardstone-harold`. Out of scope.
6. **Don't touch the system-architecture or interfaces modules** beyond what CORS unblocks. Those have their own active development streams.
7. **Don't redesign the sidebar.** Remove one entry; everything else stays as-is.
8. **Don't add new database columns.** All four phases work with the existing schema (Phase 0 confirms `deleted_at` exists on the relevant tables).

---

## Common gotchas

1. **`.env` changes need container recreation** (`docker compose up -d backend`), not restart. Mason has hit this gotcha multiple times in the past — be explicit in Phase 1.
2. **CSP-from-CORS** wiring relies on `settings.cors_origins` being parsed correctly. If it's a string in some places and a list in others, Phase 0 surfaces the mismatch.
3. **`existing.deleted_at.is_(None)`** — SQLAlchemy ORM syntax. NOT `existing.deleted_at == None` (works but lints worse) or `existing.deleted_at is None` (does Python-side comparison, doesn't generate SQL).
4. **`PendingCatalogImport` status values** — check the actual enum/status string set. The dedup-active-check filter (`status.in_(["pending_review", "in_review"])`) needs the real values per the model.
5. **Frontend redirects need rebuild** in Next.js production mode. `next start` reads the config at startup; changes need container recreation or a fresh `npm run build`.
6. **The McMaster fixture has `internal_part_number=NULL`** per memory. Deletion test against it should account for the null in the part_number message formatting.
7. **`MechanicalJoint.project_part_id`** is the FK per memory. Confirm in Phase 0 — if the schema actually points to `catalog_part_id` directly, AD-7's transitive logic simplifies.
8. **`CatalogAssemblyComponent`** might not exist yet — it was defined in the SolidWorks integration design but never landed. If absent, drop that branch from the usage check; if present, include it.
9. **The 308 redirect** is a permanent redirect that browsers cache aggressively. If you change a target later, users with cached redirects keep hitting the old target. Verify the redirect map in Phase 0 covers every parts-library subpath that has a catalog equivalent.
10. **Audit events** use the existing `_audit(db, action, resource_type, resource_id, user_id, payload)` helper. Don't invent new audit infrastructure; reuse what's in `routers/_audit.py` or wherever the pattern is established.
11. **Frontend tsc + build** must both pass before any phase commits. Phase 4 introduces new types for the usage response — get them right or the build fails.
12. **Browser cache and 308s.** When Phase 3 lands and you visit `/parts-library`, hard-refresh (Ctrl+Shift+R) the first time to bypass any cached non-redirect response.

---

## Sign-off

```powershell
# Full test pass
docker compose exec backend python -m pytest backend/tests/ -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build

# All four manual smoke steps pass (per §5.2)
```

All green → all phase commits → write `docs/PHASE_CLEANUP-002_NOTES.md` → done.

If anything in Phase 0 surfaces schema differences from what the prompt assumes (e.g., `mechanical_joints` keys directly to `catalog_parts` rather than via `project_parts`), adjust the AD-7 usage query and surface the change in the design report.

The Phase 0 stop is mandatory. Do not proceed past Phase 0 without my explicit approval of `docs/CLEANUP-002_DESIGN.md`.

---

*Prompt version 1.0 — cleanup TDD covering live-use issues from LAN access, STEP re-upload, sidebar bloat, and easy deletion with safe usage guards.*
