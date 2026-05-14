# ASTRA-CLEANUP-002 — Phase 0 Design Report

Author: Phase 0 (Cleanup-002) discovery agent.
Date: 2026-05-13.
Status: **Stops here for Mason's review.** No Phase 1 work begun.

Companion file: `CLEANUP-002_INVESTIGATION.md` (raw outputs).

Phase 0 surfaced five deviations from the locked ADs in the TDD
prompt that need decisions before Phase 1 starts. None are scope
explosions; all are local code/schema realities that the prompt
under-described. The Phase 1–5 plan below incorporates the
recommended fixes.

---

## TL;DR

1. **CORS is already fine.** `.env` has the LAN origin, the running
   backend parses it, and preflight returns the right header. The
   real LAN-access blocker is **CSP `connect-src`**, which is
   hardcoded in `SecurityHeadersMiddleware` to `'self' ws: wss:
   http://localhost:*` and is NOT derived from `settings.cors_origins`
   as AD-1 claims. Phase 1 needs a code change, not just `.env`.
2. **AD-2's `supplier_documents.deleted_at` doesn't exist.** That
   column is not on the table. The "soft-deleted supplier_document"
   in the user's complaint is really a still-active supplier_document
   whose parent `catalog_part` was soft-deleted. The fix has to be
   about catalog_part state, not supplier_document state.
3. **AD-6's `PendingCatalogImport.deleted_at` doesn't exist either.**
   Pending imports use a `status` enum; "soft-delete" is via
   `status='rejected'` or hard-delete per AD-6's intent. The
   prescribed `deleted_at.is_(None)` filter won't compile.
4. **AD-7's FK list is partially wrong.** `catalog_assembly_components`
   doesn't exist. `mechanical_joints` reaches catalog_parts only
   transitively via `project_parts`. There are two additional direct
   FKs the AD missed: `catalog_connectors` and `units`. Plus the
   self-FK via `parent_part_id` for variant relationships.
5. **AD-4's redirect target `/catalog/pending-imports` doesn't exist.**
   The directory has only `[id]/page.tsx`, no `page.tsx` for the
   list. The redirect would 404. Two recovery options below.

The full plan and revised ADs follow.

---

## 1. Issue 1 — CORS / CSP for LAN access

**State today**

- `.env:61` already lists `http://192.168.1.74:3000`. ✓
- The running backend parses
  `['http://localhost:3000', 'http://ASTRA:3000',
    'http://ASTRA.local:3000', 'http://192.168.1.74:3000']`. ✓
- OPTIONS preflight from the LAN origin returns
  `access-control-allow-origin: http://192.168.1.74:3000` and
  `access-control-allow-credentials: true`. ✓
- CSP `connect-src` is `'self' ws: wss: http://localhost:*`. ✗
  Hardcoded at `backend/app/middleware/security_headers.py:51`.

**Where AD-1 is wrong**

AD-1 says: "CSP `connect-src` is already derived from
`settings.cors_origins`, so it auto-aligns." It isn't. It is a
hardcoded string literal in `SecurityHeadersMiddleware.dispatch`.
The dev-mode branch (line 44-52) builds CSP with no reference to
the settings object.

**Why the user saw `No 'Access-Control-Allow-Origin' header`**

Most likely the user's snapshot predates the `.env` line addition.
If repro is needed today the relevant browser-side block is a CSP
violation, not a CORS violation — the wording in browser dev tools
can look similar but the underlying mechanism is different.

**Proposed fix (revised AD-1)**

- Add `http://192.168.1.74:*` to the dev-mode `connect-src` string
  in `SecurityHeadersMiddleware` (smallest, surgical).
  - Better: derive `connect-src` from `settings.cors_origins` so
    future hostname additions to `.env` automatically propagate to
    CSP. This is the AD-1 claim — make it true.
- The `.env` line is already correct; no env change needed.
- Phase 1 commits the `security_headers.py` change only. The
  backend container is recreated to pick up the code change (a
  plain `restart` works for code; `up -d` only matters for env).
- After the fix, both CORS (already passing) and CSP (newly
  passing) align for `http://192.168.1.74:3000`.

---

## 2. Issue 2 — STEP dedup vs soft-deleted parents

**Dedup query location**

`backend/app/routers/catalog.py:1577-1591`. Only filters on
`SupplierDocument.sha256 == sha256`. Error body lists raw IDs.

A second dedup at lines 471-484 (per-supplier document upload, not
STEP-specific) has the same shape.

**Where AD-2 is wrong**

`supplier_documents` has no `deleted_at` column (verified via `\d`
and `models/catalog.py`). The user's "soft-deleted supplier_document"
is the supplier_document attached to a soft-deleted `catalog_part`.
The supplier_document row itself is still active.

**Proposed fix (revised AD-2)**

Two viable approaches. Recommendation: **B**.

**A. Add `deleted_at` to `supplier_documents`** and cascade on
catalog_part soft-delete. Pro: matches AD-2 literally. Con: schema
change (out-of-scope rule #8 forbids new columns); also requires a
migration and a write path that updates supplier_documents whenever
a catalog_part is soft-deleted; affects the second dedup query too.

**B. Filter the STEP dedup so it ignores supplier_documents whose
only live downstream references are dead**, where "dead" means:

- the associated catalog_part exists but has `deleted_at IS NOT NULL`,
  AND
- the associated pending_catalog_import (if any) is `rejected` (a
  terminal pending status) or has been hard-deleted by Phase 4.

In code:

```python
dup = (
    db.query(SupplierDocument.id, SupplierDocument.supplier_id)
    .filter(SupplierDocument.sha256 == sha256)
    .outerjoin(CatalogPart, CatalogPart.source_document_id == SupplierDocument.id)
    .outerjoin(PendingCatalogImport, PendingCatalogImport.source_document_id == SupplierDocument.id)
    .filter(
        or_(
            # A live catalog_part exists
            and_(CatalogPart.id.isnot(None), CatalogPart.deleted_at.is_(None)),
            # A non-rejected pending import exists
            and_(PendingCatalogImport.id.isnot(None),
                 PendingCatalogImport.status != PendingImportStatus.REJECTED),
        )
    )
    .first()
)
```

This treats a SupplierDocument as "live" iff it still has a non-
deleted catalog_part *or* a non-rejected pending import. Re-upload
of a STEP after the catalog_part is soft-deleted (and any associated
pending import is approved-then-soft-deleted-too) succeeds cleanly.

When a true conflict exists (active document), the 409 body
includes the actionable IDs per AD-3 — adopt that wording as
written.

---

## 3. Issue 3 — Parts Library removal

**Current state**

- Sidebar entry at `Sidebar.tsx:65`: a single line in the
  3-item `GLOBAL_NAV` array.
- Frontend routes under `frontend/src/app/parts-library/`:
  `page.tsx`, `[id]/page.tsx`, `pending-imports/page.tsx`,
  `pending-imports/[id]/page.tsx`.
- Catalog page.tsx inventory: `/catalog`, `/catalog/parts/[id]`,
  `/catalog/parts/new`, `/catalog/pending-imports/[id]`,
  `/catalog/suppliers/[id]`, `/catalog/suppliers/new`,
  `/catalog/documents/[id]/review`.
- `frontend/next.config.js` already has a `redirects()` async
  function with three SYSARCH-002 redirects; new redirects can be
  appended.

**Where AD-4 is wrong (subtle)**

AD-4's redirect target `/catalog/pending-imports` doesn't have a
list `page.tsx` — only `[id]/page.tsx`. Hitting
`/parts-library/pending-imports` then 308-redirecting to
`/catalog/pending-imports` would land on a 404.

**Proposed fix (revised AD-4)**

Three options for the `/parts-library/pending-imports` redirect:

**A. Create a new `/catalog/pending-imports/page.tsx`** that
mirrors the legacy `/parts-library/pending-imports/page.tsx`
(read what it does, port it minimally). Extends Phase 3 scope by
one frontend file.

**B. Redirect `/parts-library/pending-imports` → `/catalog`**
(the catalog landing). Lossy but cheap.

**C. Keep `/parts-library/pending-imports/page.tsx` in place**
and only redirect the *other* three paths. The list keeps working
at the old URL until a future TDD ports it. Inconsistent.

Recommendation: **A**, with a thin port (the page is unlikely to
be large, given the catalog UI is the dominant surface now).

**Also note: `library_parts` DB table is non-empty (1 row) and
`documents` is non-empty (2 rows).** Mechanical joints'
`fastener_part_id`/`seal_part_id` FK into `library_parts`. The
table sunset is explicitly out-of-scope (rule #1: don't delete the
route tree); the table sunset is doubly out-of-scope. Surface for
follow-up.

**Other parts-library references**

Two pages reference `parts-library` indirectly:
- `frontend/src/app/projects/[id]/mechanical-interfaces/page.tsx`
- `frontend/src/app/projects/[id]/parts/page.tsx`

Plus shared modules:
- `frontend/src/components/parts/StepUploadModal.tsx`
- `frontend/src/lib/parts-api.ts`
- `frontend/src/lib/parts-types.ts`

Phase 3 verifies these continue to work after the redirects (most
likely they reference paths or API endpoints, not just labels —
audit during Phase 3 implementation).

---

## 4. Issue 4 — Easy deletion with usage warnings

**The real FK graph from `catalog_parts`** (verified via pg_constraint):

| Referencing table | Column | ON DELETE | Phase-4 usage relevance |
|---|---|---|---|
| `catalog_parts`             | `parent_part_id`             | SET NULL  | Yes — variants point at parents |
| `catalog_connectors`        | `catalog_part_id`            | (likely RESTRICT) | Yes — direct |
| `pending_catalog_imports`   | `committed_catalog_part_id`  | SET NULL  | No — already cascades to NULL |
| `units`                     | `catalog_part_id`            | (likely RESTRICT) | Yes — direct |
| `project_parts`             | `catalog_part_id`            | (likely RESTRICT) | Yes — direct + transitive |
| `mechanical_joints`         | (transitive via project_parts) | — | Yes — transitive |
| `catalog_assembly_components` | — | — | **Table does not exist** |

AD-7 needs to be expanded to:

- `project_parts` (direct, primary)
- `catalog_connectors` (direct, new)
- `units` (direct, new)
- `catalog_parts.parent_part_id` (self-reference, new)
- `mechanical_joints` (transitive via project_parts, as AD-7 already says)
- Skip `catalog_assembly_components` (table absent — gotcha #8 anticipated this)
- Skip `pending_catalog_imports.committed_catalog_part_id` (FK is ON
  DELETE SET NULL, so it doesn't actually block deletion; it auto-detaches
  on hard-delete and is irrelevant for soft-delete)

The usage-check endpoint and the delete-blocking response should
list every category that has > 0 references. The McMaster fixture
(catalog_part_id=1) has 0 references on every category and is a
safe smoke target (AD-10 — still correct).

**Also note: `mechanical_joints` has no `deleted_at` column.**
AD-7's example code uses `MechanicalJoint.deleted_at.is_(None)` —
drop that filter (joints are hard-deleted, not soft-deleted).

**AD-6 fix for pending-import deletion** — `pending_catalog_imports`
has no `deleted_at` column. The lifecycle column is `status` (enum:
pending, reviewed, approved, rejected). For Phase 4.1's hard-delete
flow, the `.filter(PendingCatalogImport.deleted_at.is_(None))` clauses
in AD-6's example code should be removed — they would be a syntax
error. Replace with `.filter(PendingCatalogImport.id == id)` only.

**Audit events** are correctly identified by AD-9; no revision.

---

## 5. McMaster fixture state

Single catalog_part row (id=1). Zero references across all six
relevant paths (project_parts, mechanical_joints via project_parts,
catalog_connectors, units, catalog_parts.parent_part_id,
pending_catalog_imports.committed_catalog_part_id). Safe deletion
target for the Phase 5 smoke walkthrough.

Per AD-10, the test will exercise the flow without auto-deleting —
that is, the smoke step that "tries to delete McMaster, succeeds"
should be operator-initiated, not asserted in an automated test
that runs on every CI cycle.

---

## 6. Adjusted Phase 1–5 plan

### Phase 1 — LAN access fix (CSP, not just CORS)

Files modified:
- `backend/app/middleware/security_headers.py` — dev-mode CSP
  derives `connect-src` from `settings.cors_origins` (the smaller
  surgical alternative is to add `http://192.168.1.74:*` to the
  literal, but the derive-from-settings option matches AD-1's claim
  and prevents future drift).

Verify:
- `curl.exe -sI http://localhost:8000/health` shows LAN origin in
  CSP `connect-src`.
- OPTIONS preflight from LAN origin still returns 200 + the right
  CORS headers (already does — regression check).
- Browser smoke from `http://192.168.1.74:3000` per the TDD prompt.

Commit: `phase-1(cleanup-002): CSP connect-src derives from CORS origins`.

### Phase 2 — STEP dedup respects soft-delete

Files modified:
- `backend/app/routers/catalog.py` — replace the STEP dedup query at
  lines 1577-1591 with the `outerjoin` form (§2 of this report).
  Also enrich the 409 body per AD-3 unchanged.
- (Optional, recommended): the per-supplier doc dedup at lines
  471-484 — same gap, same fix. Mason can opt-in or defer.
- `frontend/src/lib/errors.ts` (or equivalent) — render the new
  structured 409 response with the "View existing import" link
  per AD-3.

Tests at `backend/tests/test_step_dedup.py` per the TDD prompt.

Commit: `phase-2(cleanup-002): STEP dedup respects soft-delete + actionable 409`.

### Phase 3 — Parts Library removal

Files modified:
- `frontend/src/components/layout/Sidebar.tsx` — delete line 65.
  Audit imports; `Boxes` icon stays (still used on line 81).
- `frontend/next.config.js` — append four redirects to the existing
  `redirects()` async function (don't replace it — SYSARCH-002's
  three redirects must survive).
- **NEW** `frontend/src/app/catalog/pending-imports/page.tsx` —
  minimal port of `parts-library/pending-imports/page.tsx` so the
  redirect target exists. Alternatively, redirect the list path to
  `/catalog`; Mason decides.

Verify:
- `npx tsc --noEmit` clean.
- `npm run build` clean (Next.js validates redirects at build time).
- Hit `/parts-library` → ends up on `/catalog`. Same for the three
  deeper paths.

Commit: `phase-3(cleanup-002): remove Parts Library from sidebar + 308 redirects`.

### Phase 4 — Easy deletion with usage warnings

Files modified (backend):
- `backend/app/routers/catalog.py`:
  - `DELETE /pending-imports/{id}` per AD-6 — hard delete the row,
    cascade-delete the supplier_document only if no other live
    refs. Drop the `deleted_at.is_(None)` clauses (column absent).
  - `GET /parts/{id}/usage` per AD-8 — new endpoint; usage query
    covers the expanded reference set from §4 above.
  - `DELETE /parts/{id}` per AD-7 — block with structured 409 when
    usage > 0; soft-delete (`deleted_at = utcnow()`) when clear.
- `backend/app/routers/_audit.py` (or wherever `_audit` lives) — no
  changes; reuse the helper for the three new audit events.

Files modified (frontend):
- `frontend/src/app/catalog/parts/[id]/page.tsx` — usage badge,
  delete button, confirmation modal with project list.
- `frontend/src/app/catalog/page.tsx` — per-card delete button (admin only).
- `frontend/src/app/catalog/pending-imports/[id]/page.tsx` —
  delete action in header.
- `frontend/src/app/catalog/pending-imports/page.tsx` (created in
  Phase 3) — per-row delete action.

Tests at `backend/tests/test_catalog_deletion.py` per the TDD prompt,
with the test for `mechanical_joints` transitive usage adjusted to
use `part_a_id`/`part_b_id` (not `project_part_id`).

Commit: `phase-4(cleanup-002): pending import + catalog part deletion with usage check`.

### Phase 5 — Tests + completion notes

Per TDD prompt §5 unchanged. The notes doc captures:
- The five AD revisions surfaced in Phase 0.
- The new `/catalog/pending-imports` list page that Phase 3 created
  (if Mason picks option A in §3).
- The deferred follow-ups (sunset library_parts table, sunset
  parts-library route tree entirely, bulk-delete, cascade override).

Commit: `phase-5(cleanup-002): tests + completion notes`.

---

## 7. Open questions for Mason (decisions Phase 0 cannot make)

1. **CSP fix shape** (Phase 1): derive `connect-src` from
   `settings.cors_origins` (matches AD-1's claim, future-proof), or
   just hardcode `http://192.168.1.74:*` (smaller, faster).
2. **STEP dedup fix shape** (Phase 2): the outerjoin form (option
   B), or add a real `deleted_at` to `supplier_documents` with a
   schema migration (option A — out-of-scope per rule #8 unless
   relaxed).
3. **Phase 3 `/catalog/pending-imports/page.tsx`** decision: port
   the legacy page (option A, recommended), redirect to `/catalog`
   (option B), or skip that one redirect entirely (option C).
4. **Per-supplier doc dedup** (Phase 2 sideways): apply the same
   soft-delete-aware filter to the per-supplier dedup at lines
   471-484, or leave it for a future TDD.
5. **Test coverage for transitive `mechanical_joints` usage**: the
   existing schema has zero rows in `project_parts` and
   `mechanical_joints`. The Phase 4 test must seed both before
   asserting the 409. Confirm the test fixture approach is
   acceptable (a real project + a real project_part + a real
   joint, all created in the test, all torn down via the existing
   pytest fixture teardown).

Phase 1 starts immediately on green-light. None of the open
questions block discovery itself — they shape the Phase 1+
implementations.

---

## Appendix A — Files referenced

Backend:
- `backend/.env:61` (CORS line)
- `backend/app/config.py:69-104` (Settings + cors_origins property)
- `backend/app/main.py:241-260` (CORS + middleware registration)
- `backend/app/middleware/security_headers.py:44-52` (dev CSP literal)
- `backend/app/routers/catalog.py:471-484` (per-supplier doc dedup)
- `backend/app/routers/catalog.py:1577-1591` (STEP dedup)
- `backend/app/models/catalog.py:228, 280, 401, 556` (CatalogPart.deleted_at; SupplierDocument and PendingCatalogImport — no deleted_at)

Frontend:
- `frontend/src/components/layout/Sidebar.tsx:60-66` (GLOBAL_NAV)
- `frontend/src/app/parts-library/` (4 pages to redirect)
- `frontend/src/app/catalog/` (page.tsx inventory; missing pending-imports list)
- `frontend/next.config.js:10-29` (existing redirects)

Schema:
- `supplier_documents`: no `deleted_at`
- `pending_catalog_imports`: no `deleted_at`; has `status` enum
- `catalog_parts`: has `deleted_at` (the only soft-delete column)
- `mechanical_joints`: no `deleted_at`; `part_a_id`/`part_b_id` →
  `project_parts`, `fastener_part_id`/`seal_part_id` →
  `library_parts`, `source_step_file_id` → `documents`
- 5 direct FKs into `catalog_parts`: `project_parts`,
  `catalog_connectors`, `units`, `catalog_parts.parent_part_id`,
  `pending_catalog_imports.committed_catalog_part_id`
