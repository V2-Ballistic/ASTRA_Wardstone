# ASTRA-CLEANUP-002 — Completion Notes

Status: **Shipped** on branch `fix/frontend-healthcheck-ipv4`.
Date: 2026-05-13.

Four user-visible cleanups landed across six commits. All four issues
from the original TDD prompt are resolved.

---

## 1. Commits

| Phase | SHA       | Subject |
|------:|-----------|---------|
| 0     | `2abdcf3` | discovery + design report |
| 1     | `47dfaea` | CSP connect-src derives from CORS origins |
| 2     | `4017fe2` | STEP dedup respects soft-delete + actionable 409 |
| 3     | `f64cdb8` | remove Parts Library from sidebar + 308 redirects |
| 4     | `be477c5` | pending import + catalog part deletion with usage check |
| —     | `7221eb5` | fix(compose): frontend production mode for stable LAN access |
| 5     | (this commit) | tests + completion notes |

The `fix(compose)` commit was an unrelated working-tree edit
surfaced during Phase 4. Sequenced before Phase 5 by decision.

---

## 2. What changed, by issue

### Issue 1 — LAN access fix (Phase 1, AD-1)

The original TDD framing was "CORS allow-list missing LAN origin."
Phase 0 found `.env`'s `BACKEND_CORS_ORIGINS` already listed
`http://192.168.1.74:3000` and the backend already returned the
right `Access-Control-Allow-Origin` header on preflight. The actual
LAN-browser block was **CSP**: `SecurityHeadersMiddleware.dispatch`
hardcoded `connect-src 'self' ws: wss: http://localhost:*`, which
refused the cross-origin XHR before CORS got a chance.

Fix at `backend/app/middleware/security_headers.py`:
- New `_connect_src()` returns
  `"'self' ws: wss: <origin1> <origin2> …"`, derived from
  `settings.cors_origins`.
- Both dev and prod CSP branches use the derived value, so adding a
  host to `BACKEND_CORS_ORIGINS` in `.env` auto-propagates to CSP.
- `uvicorn --reload` picked up the code change without container
  recreation (no env change involved).

### Issue 2 — STEP dedup respects soft-delete (Phase 2, AD-2 + AD-3)

Re-uploading a STEP after soft-deleting its catalog_part used to
409 with an opaque "soft-deleted supplier_document" message. Phase 0
found `supplier_documents` has no `deleted_at` column at all — the
soft-delete actually lives on `catalog_parts.deleted_at`.

Fix at `backend/app/routers/catalog.py:1577-1591` (STEP upload):
- Rewrote the dedup query as an `outerjoin` through `CatalogPart`
  and `PendingCatalogImport`. A supplier_document with the same
  sha256 blocks re-upload only if it still has live downstream
  state — a non-soft-deleted catalog_part, or a `PENDING`
  pending_import.
- 409 detail body is now structured (AD-3):
  ```json
  {
    "code": "step_already_uploaded",
    "message": "…",
    "existing_supplier_document_id": 42,
    "existing_pending_import_id": 19,
    "existing_pending_import_url": "/catalog/pending-imports/19"
  }
  ```
- Frontend (`frontend/src/lib/errors.ts`,
  `frontend/src/app/catalog/page.tsx`) recognises the code and
  routes the user directly to the existing pending import instead
  of surfacing the raw error.

**AD-2 refinement that surfaced during implementation**: the
design report sketched the pending-import liveness condition as
`status != REJECTED`. The shipped code uses the stricter
`status == PENDING`. Rationale: APPROVED and REVIEWED imports
have already produced catalog_parts that own the supplier_document's
liveness through the `CatalogPart.source_document_id` FK. Counting
them on the pending leg would double-block. Mason confirmed the
tighter check is the right semantics.

### Issue 3 — Parts Library removal (Phase 3, AD-4 + AD-5)

Sunset the legacy module without breaking old bookmarks.

- `frontend/src/components/layout/Sidebar.tsx` — dropped the
  Parts Library entry from `GLOBAL_NAV`.
- `frontend/next.config.js` — appended four 308 redirects, ordered
  after SYSARCH-002's existing redirects:
    - `/parts-library` → `/catalog`
    - `/parts-library/pending-imports` → `/catalog/pending-imports`
    - `/parts-library/pending-imports/:id` → `/catalog/pending-imports/:id`
    - `/parts-library/:id` → `/catalog/parts/:id`
- `frontend/src/app/catalog/pending-imports/page.tsx` (new) —
  Phase 0 found `/catalog/pending-imports` had no list page
  (only `[id]/page.tsx`), so the second redirect would 404.
  Minimal port from the legacy parts-library list, swapped to
  read `catalogAPI.listPendingImports()`.

The `frontend/src/app/parts-library/` route tree was kept in
place per AD-4 + out-of-scope rule #1. Next.js redirects
intercept before route resolution.

### Issue 4 — Easy deletion with usage warnings (Phase 4, AD-6 / AD-7 / AD-8 / AD-9)

Two distinct flows landed:

**Pending-import hard delete (AD-6 + AD-9)** — new
`DELETE /api/v1/catalog/pending-imports/{id}` at
`backend/app/routers/catalog.py`. Hard-deletes the row. The linked
`supplier_document` is also deleted iff no other pending import
references it AND no non-soft-deleted catalog_part was sourced from
it. The response carries `supplier_document_deleted: bool` so the
UI toast can reflect whether the cascade fired.

Audit event: `pending_import.deleted` with
`{prior_status, source_document_id, supplier_document_deleted}`.

Frontend surfaces:
- `frontend/src/app/catalog/pending-imports/page.tsx` — per-row
  trash icon + `ConfirmDialog` + green-success toast.
- `frontend/src/app/catalog/pending-imports/[id]/page.tsx` —
  Delete button in the header bar alongside Reject + Approve.

**Catalog-part safe-delete with usage check (AD-7 + AD-8 + AD-9)**:

- New `_build_catalog_part_usage_report()` helper walks the three
  downstream-consumer FKs into `catalog_parts`:
  - `project_parts.catalog_part_id` (direct BOM)
  - `mechanical_joints.part_a_id / part_b_id` (transitive via
    `project_parts`, exactly per Phase 0's schema sweep)
  - `units.catalog_part_id` (project placements)
- New `GET /api/v1/catalog/parts/{id}/usage-report` returns the
  structured `CatalogPartUsageReport`:
  ```json
  {
    "part_id": 42,
    "part_number": "RSP-100",
    "internal_part_number": "WS-EL-P000042-A",
    "total_references": 3,
    "deletable": false,
    "projects": [
      {
        "project_id": 7,
        "project_name": "DART",
        "project_code": "DART",
        "project_part_count": 2,
        "mechanical_joint_count": 1,
        "unit_count": 0
      }
    ]
  }
  ```
- `DELETE /api/v1/catalog/parts/{id}` default path:
  - Soft-deletes (`deleted_at = utcnow()`) when the report is
    clean (`deletable: true`). Audit `catalog.part.deleted`.
  - 409s with `{ code: "part_in_use", usage: <report> }` when
    not. Audit `catalog.part.deletion_blocked`.
- `?admin_force=true` preserves the legacy hard-delete cascade for
  admin tooling. `test_create_part_with_connectors_and_pins`
  updated to call this path since the cascade is no longer the
  default.

**AD-7 refinement that surfaced during implementation**: Phase 0's
FK sweep also flagged `catalog_connectors.catalog_part_id` and
`catalog_parts.parent_part_id` for inclusion in the usage check.
Both were excluded after writing the first cut against the existing
test suite:
- Connectors are *owned* by the part — they're part of its own
  pin definition and cascade with it on hard-delete. Counting them
  as "usage" 409'd the pre-Phase-4 flow that creates a part with
  connectors and immediately deletes it.
- `parent_part_id` is `ON DELETE SET NULL`, so variant children
  survive parent deletion with the link nulled. Not a block.

Shipped usage report keeps these two FKs out of `total_references`
and `deletable`. The helper docstring captures the rationale.

Frontend surfaces:
- `frontend/src/components/catalog/CatalogPartDeleteModal.tsx`
  (new) — self-contained "delete with usage report" modal used by
  list-page surfaces. Owns the report fetch + the 409 re-render path.
- `frontend/src/app/catalog/parts/[id]/page.tsx` — usage-report
  fetch on mount, a "Used in N projects" / "Unused" badge in the
  header, inline modal that reuses already-fetched state.
- `frontend/src/app/catalog/page.tsx` (PartsTab) — per-row trash
  icon (admin only), `stopPropagation` on row click,
  `CatalogPartDeleteModal`-driven flow.

---

## 3. Audit events introduced

| Event                              | Resource                  | When |
|------------------------------------|---------------------------|------|
| `pending_import.deleted`           | `pending_catalog_import`  | Hard delete from list or detail page. |
| `catalog.part.deleted`             | `catalog_part`            | Default soft-delete path succeeds. |
| `catalog.part.deletion_blocked`    | `catalog_part`            | 409 returned because usage > 0. |

The pre-existing `catalog_part.deleted` event (singular `_`, used
by the legacy `admin_force=true` path) is retained for backward
compatibility. New event names use the dotted form
(`catalog.part.deleted`) so log filters can distinguish soft vs
hard deletes by namespace.

---

## 4. Structured 409 response shape

Two endpoints now return structured `detail` objects, both keyed by
a string `code` so the frontend's `parseStructuredApiError` helper
can branch on the typed shape:

```ts
// POST /api/v1/catalog/upload-step
{
  code: "step_already_uploaded",
  message: string,
  existing_supplier_document_id: number,
  existing_pending_import_id: number | null,
  existing_pending_import_url: string | null,
}

// DELETE /api/v1/catalog/parts/{id}
{
  code: "part_in_use",
  message: string,
  usage: CatalogPartUsageReport,
}
```

Future structured errors should follow the same pattern: an opaque
`code` for branching, a human-readable `message` for fallback
rendering, and any actionable IDs or sub-payloads alongside.

---

## 5. Phase 0 AD revisions, consolidated

Phase 0 surfaced five deviations from the locked ADs. Final
decisions (Mason in chat, confirmed by the shipped commits):

| Open question (§7 of design report)             | Decision | Where |
|-------------------------------------------------|----------|-------|
| Q1 CSP fix shape                                | Derive from `settings.cors_origins` | Phase 1 (`47dfaea`) |
| Q2 STEP dedup shape                             | Option B — outerjoin form (no schema change) | Phase 2 (`4017fe2`) |
| Q3 `/catalog/pending-imports/page.tsx`          | Option A — port the legacy list page | Phase 3 (`f64cdb8`) |
| Q4 Per-supplier doc dedup at `catalog.py:471-484` | Defer to follow-up TDD | (see §6) |
| Q5 Mechanical-joints fixture                    | Option (a) — real Project + ProjectPart + MechanicalJoint chain | Phase 4 (`be477c5`) |

The two refinements that emerged during implementation (Phase 2's
stricter `status == PENDING` check; Phase 4's connectors + variant
children exclusion) are documented in §2 above.

---

## 6. Deferred follow-ups

Surfaced during this TDD; intentionally out of scope:

1. **Apply the soft-delete-aware dedup pattern to the per-supplier
   doc upload** at `backend/app/routers/catalog.py:471-484`. Same
   shape gap as the STEP path, just lower traffic. Mason deferred
   the decision (open question Q4).
2. **Sunset the `frontend/src/app/parts-library/` route tree entirely.**
   Currently kept in place behind the 308 redirects (rule #1). Future
   TDD removes the files once we're confident no bookmarks survive.
3. **Sunset the `library_parts` table.** Phase 0 noted 1 row still in
   it, plus `mechanical_joints.fastener_part_id` / `seal_part_id` and
   `project_parts.library_part_id` keying into it. Migration off the
   legacy table is its own TDD.
4. **Bulk-delete for catalog parts.** One-at-a-time only this round.
5. **"Cascade override" admin path that auto-removes project_parts
   before deleting the catalog_part.** Currently the operator must
   manually clear the references first. Riskier flow that warrants
   its own TDD with its own audit story.
6. **Apply the "delete with usage check" pattern to other entities**
   — suppliers (used by parts), systems (used by units), units
   (used by connectors + interfaces).
7. **Browser smoke walkthrough on the LAN machine** at
   `http://192.168.1.74:3000` (TDD §5.2 step 1 + step 4-7).
   Automated tests cover the backend deletion flows end-to-end and
   the build artifact ships without TypeScript errors; the manual
   browser walkthrough is operator-side and is not gated by this
   TDD's success criteria.

---

## 7. Verification snapshot

| Check                            | Result |
|----------------------------------|--------|
| `pytest backend/tests/` (ex. e2e) | **797 passed, 1 skipped, 0 failed** |
| `npx tsc --noEmit`                | clean |
| `npm run build`                   | clean (Next.js validates redirects + types) |
| `python -c "import ast; ast.parse(...)"` | clean for every modified backend file |
