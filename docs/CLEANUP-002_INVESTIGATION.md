# ASTRA-CLEANUP-002 — Phase 0 Investigation (raw outputs)

Captured 2026-05-13 against the running stack. Companion to
`CLEANUP-002_DESIGN.md`, which synthesises findings into AD
revisions and an adjusted Phase 1–5 plan.

---

## 1. CORS / CSP state

### .env (line 61)

```
BACKEND_CORS_ORIGINS=http://localhost:3000,http://ASTRA:3000,http://ASTRA.local:3000,http://192.168.1.74:3000
```

The LAN origin `http://192.168.1.74:3000` is **already present**.

### Running backend's parsed cors_origins

```
docker compose exec backend python -c "from app.config import settings; print(settings.cors_origins)"
['http://localhost:3000', 'http://ASTRA:3000', 'http://ASTRA.local:3000', 'http://192.168.1.74:3000']
```

Container is 16 hours old and already picked up the LAN origin.

### CSP header on /health

```
curl.exe -sI http://localhost:8000/health
content-security-policy: default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline';
  style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:;
  connect-src 'self' ws: wss: http://localhost:*
```

**`connect-src` does NOT include the LAN origin.** It is hardcoded
in `backend/app/middleware/security_headers.py:51` (dev branch). It
is **not** derived from `settings.cors_origins` as AD-1 assumes.

### OPTIONS preflight against the LAN host

```
curl.exe -X OPTIONS "http://192.168.1.74:8000/api/v1/interfaces/connections?project_id=1" \
  -H "Origin: http://192.168.1.74:3000" -H "Access-Control-Request-Method: GET"

HTTP/1.1 200 OK
access-control-allow-methods: DELETE, GET, HEAD, OPTIONS, PATCH, POST, PUT
access-control-max-age: 600
access-control-allow-credentials: true
access-control-allow-origin: http://192.168.1.74:3000
content-security-policy: default-src 'self'; script-src 'self' 'unsafe-eval' 'unsafe-inline';
  style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:;
  connect-src 'self' ws: wss: http://localhost:*
```

CORS itself **already works** — the right `access-control-allow-origin`
header is returned for the LAN origin. The user-reported CORS error
is most plausibly a CSP-induced `connect-src` violation that
manifests in dev-tools as a similar-looking "Refused to connect"
message, OR the report predates the `.env` line that already added
the origin. Either way, the present blocker is CSP, not CORS.

---

## 2. STEP dedup — current code

### `backend/app/routers/catalog.py:1577-1591` (STEP upload)

```python
# Global hash dedup — STEP geometry hash collisions across vendors
# are essentially impossible; if we've seen this hash already, the
# caller is re-uploading.
dup = (
    db.query(SupplierDocument.id, SupplierDocument.supplier_id)
    .filter(SupplierDocument.sha256 == sha256)
    .first()
)
if dup is not None:
    raise HTTPException(
        409,
        f"STEP file with sha256={sha256[:12]}… already uploaded "
        f"(supplier_document_id={dup[0]}, supplier_id={dup[1]}). "
        "Open the existing pending import instead.",
    )
```

Only filters on `sha256`. Error body is the opaque ID dump the
user complained about. No reference to pending-import or
catalog-part state in the filter or response.

### `backend/app/routers/catalog.py:471-484` (per-supplier doc upload)

```python
# Per-supplier dedup: reject if the SAME hash already exists for this supplier.
dup = (
    db.query(SupplierDocument.id)
    .filter(
        SupplierDocument.supplier_id == supplier_id,
        SupplierDocument.sha256 == sha256,
    )
    .first()
)
if dup is not None:
    raise HTTPException(
        409,
        f"Document with sha256={sha256[:12]}… already exists for supplier {supplier_id}",
    )
```

A separate dedup path for non-STEP documents. Same shape; same gap.

---

## 3. Schemas — soft-delete columns

```
\d supplier_documents   → NO deleted_at column
\d pending_catalog_imports → NO deleted_at column
\d catalog_parts        → deleted_at column present (line 401 of models/catalog.py)
\d mechanical_joints    → NO deleted_at column
```

Only `catalog_parts` has soft-delete. `supplier_documents` and
`pending_catalog_imports` are hard-delete entities; their lifecycle
is governed by FK cascade and status enum respectively.

---

## 4. FK graph rooted at catalog_parts

```sql
SELECT conname, conrelid::regclass FROM pg_constraint
WHERE confrelid = 'catalog_parts'::regclass AND contype = 'f';

 fk_catalog_parts_parent_part                           | catalog_parts
 catalog_connectors_catalog_part_id_fkey                | catalog_connectors
 pending_catalog_imports_committed_catalog_part_id_fkey | pending_catalog_imports
 units_catalog_part_id_fkey                             | units
 project_parts_catalog_part_id_fkey                     | project_parts
```

Five referencing tables — including the self-reference via
`parent_part_id` (variant relationships). Notably absent:
`mechanical_joints` (transitive via `project_parts` only) and
`catalog_assembly_components` (table does not exist).

### mechanical_joints FKs (the transitive path)

```sql
SELECT conname, pg_get_constraintdef(oid) FROM pg_constraint
WHERE conrelid = 'mechanical_joints'::regclass AND contype = 'f';

 part_a_id           → project_parts(id)  ON DELETE RESTRICT
 part_b_id           → project_parts(id)  ON DELETE RESTRICT
 fastener_part_id    → library_parts(id)  ON DELETE SET NULL   ← NOT catalog_parts
 seal_part_id        → library_parts(id)  ON DELETE SET NULL   ← NOT catalog_parts
 source_step_file_id → documents(id)      ON DELETE SET NULL   ← NOT supplier_documents
```

Joints reach `catalog_parts` only transitively, via `project_parts`.
The fastener/seal FK paths point at the legacy `library_parts` table
— a separate row store with no direct relationship to catalog.

---

## 5. McMaster fixture (catalog_part_id=1) — deletion-safety

```sql
SELECT 'project_parts (direct)'              , COUNT(*) FROM project_parts WHERE catalog_part_id = 1
UNION ALL SELECT 'mechanical_joints (via pp)', COUNT(*) FROM mechanical_joints
                                                WHERE part_a_id IN (SELECT id FROM project_parts WHERE catalog_part_id = 1)
                                                   OR part_b_id IN (SELECT id FROM project_parts WHERE catalog_part_id = 1)
UNION ALL SELECT 'catalog_connectors'        , COUNT(*) FROM catalog_connectors WHERE catalog_part_id = 1
UNION ALL SELECT 'units'                     , COUNT(*) FROM units WHERE catalog_part_id = 1
UNION ALL SELECT 'catalog_parts (self)'      , COUNT(*) FROM catalog_parts WHERE parent_part_id = 1
UNION ALL SELECT 'pending_catalog_imports'   , COUNT(*) FROM pending_catalog_imports WHERE committed_catalog_part_id = 1;

 project_parts (direct)                |     0
 mechanical_joints (transitive via pp) |     0
 catalog_connectors                    |     0
 units                                 |     0
 catalog_parts (self parent)           |     0
 pending_catalog_imports               |     0
```

Zero references across all six paths. `deletable: true`. McMaster
is safe to use as the delete-flow smoke target.

---

## 6. Row counts on key tables

```sql
SELECT 'catalog_parts'          , COUNT(*) FROM catalog_parts
UNION ALL SELECT 'project_parts'           , COUNT(*) FROM project_parts
UNION ALL SELECT 'pending_catalog_imports' , COUNT(*) FROM pending_catalog_imports
UNION ALL SELECT 'supplier_documents'      , COUNT(*) FROM supplier_documents
UNION ALL SELECT 'library_parts'           , COUNT(*) FROM library_parts
UNION ALL SELECT 'documents'               , COUNT(*) FROM documents;

 catalog_parts            | 1
 project_parts            | 0
 pending_catalog_imports  | 2
 supplier_documents       | 2
 library_parts            | 1
 documents                | 2
```

Two leftover pending imports; two supplier_documents. `library_parts`
and `documents` (the legacy Parts Library tables) hold 1 and 2 rows
respectively — they are not empty; sunsetting them entirely is a
separate concern.

---

## 7. Frontend route trees

### `frontend/src/app/parts-library/` (four pages)

```
parts-library/page.tsx
parts-library/[id]/page.tsx
parts-library/pending-imports/page.tsx
parts-library/pending-imports/[id]/page.tsx
```

### `frontend/src/app/catalog/` (page.tsx inventory)

```
catalog/page.tsx
catalog/documents/[id]/review/page.tsx
catalog/parts/new/page.tsx
catalog/parts/[id]/page.tsx
catalog/pending-imports/[id]/page.tsx
catalog/suppliers/new/page.tsx
catalog/suppliers/[id]/page.tsx
```

Note the absence of `catalog/pending-imports/page.tsx` — there is
**no list page** at `/catalog/pending-imports`. AD-4's redirect
`/parts-library/pending-imports → /catalog/pending-imports` would
currently 404.

---

## 8. Sidebar nav config

`frontend/src/components/layout/Sidebar.tsx:60-66`:

```tsx
const GLOBAL_NAV: NavItem[] = [
  { href: '/',              label: 'Projects',      icon: Home  },
  { href: '/catalog',       label: 'Catalog',       icon: Package },
  { href: '/parts-library', label: 'Parts Library', icon: Boxes },   // ← line 65
];
```

The Parts Library entry is a single line in a 3-item array. The
`Boxes` icon is also used for the per-project Parts entry at line
81, so the icon import stays.

---

## 9. Existing Next.js redirects

`frontend/next.config.js:10-29` currently has three redirects (all
the `/projects/:id/interfaces/system/...` →
`/projects/:id/system-architecture/...` rewrites from TDD-SYSARCH-002).
The Phase 3 redirects can be appended to the same `redirects()`
async function.

---

## 10. Container state at investigation time

```
NAME              SERVICE   STATUS
astra-backend-1   backend   Up 16 hours (healthy)
astra-db-1        db        Up 16 hours (healthy)
astra-frontend-1  frontend  Up 16 hours (healthy)
astra-pgadmin-1   pgadmin   Up 16 hours
```

Working copy is dirty: `docker-compose.yml` has an uncommitted
change flipping the frontend service `command` from `npm run dev`
to `sh -c "npm run build && npm start"` — relevant to gotcha #5
(Next.js redirects need rebuild in production mode). Mason has
elected to leave this untouched during Phase 0.
