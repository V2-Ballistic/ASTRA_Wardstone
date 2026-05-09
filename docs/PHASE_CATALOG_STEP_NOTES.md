# Phase notes — Catalog STEP support (CAT-002)

Implementation log for the four-phase Claude Code execution against
`docs/CLAUDE_CODE_PROMPT_CAT-002.md`. Commits chained as
`phase-{1..4}(catalog-step): …`.

---

## Per-AC status — McMaster validation

The validation table from the prompt (re-mapped to the actual schema
the work uses). All extractions verified against the parser's pure-Python
path on a synthesized STEP fixture mirroring the real
`92196A196_18-8 Stainless Steel Socket Head Screw.STEP`. The real
fixture is auto-detected at `backend/tests/fixtures/cad/`; when missing,
`test_mcmaster_socket_head_screw` skips with a clear message.

| AC | Field | Lands in `extracted_data` as | Status |
|----|-------|------------------------------|--------|
| 1  | `original_filename` | `original_filename` (`92196A196_18-8…STEP`) | ✓ |
| 2  | `cad_authoring_tool` | `cad_authoring_tool` (`SolidWorks 2025`) | ✓ |
| 3  | STEP `schema` | `schema` (`AUTOMOTIVE_DESIGN`) | ✓ |
| 4  | `is_assembly` | `is_assembly` (`false`) | ✓ |
| 5  | Manufacturer | `manufacturer` (`McMaster-Carr`) | ✓ |
| 6  | MPN | `part_number` (`92196A196`) | ✓ |
| 7  | Material name | `material_name` (`18-8 Stainless Steel`) | ✓ |
| 8  | Material class | `material_class` (`stainless_steel`) | ✓ |
| 9  | Part class | `part_class` (`fastener_screw`) — new enum value | ✓ |
| 10 | Part subtype | `part_subtype` (`socket_head_cap_screw`) | ✓ |
| 11 | Bounding box | `bbox_x_mm/y_mm/z_mm` (inch → mm via ×25.4) | ✓ |
| 12 | Native units | `native_units` (`inch`) | ✓ |

---

## Tests

| File | Coverage |
|------|----------|
| `backend/tests/test_step_parser.py` | McMaster validation (real fixture, skips if absent), in-house no-vendor, pythonOCC fallback, MM units, corrupted file, missing file, confidence averaging |
| `backend/tests/test_supplier_aliases.py` | case-insensitive resolution, UNIQUE constraint, cascade-on-supplier-delete |
| `backend/tests/test_step_upload_flow.py` | first-upload supplier auto-create, second-upload reuses supplier, in-house links to Wardstone, duplicate-hash 409, upload→approve creates `CatalogPart` with `fastener_screw`/`stainless_steel`/bbox/cad_authoring_tool |

Run from inside the backend container:

```powershell
docker compose exec backend python -m pytest tests/test_step_parser.py tests/test_supplier_aliases.py tests/test_step_upload_flow.py -v
```

Frontend type-check + build:

```powershell
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Apply the migration before running the end-to-end UI test:

```powershell
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current
# → 0029
```

---

## Deviations from the prompt

1. **Reused approve flow rather than adding a parallel STEP-approve handler.**
   The prompt §3.1 step 6 specifies the STEP upload creates a
   `PendingCatalogImport` for the *existing* `/pending-imports/{id}/approve`
   endpoint to consume. The existing handler runs Pydantic validation
   against `IcdExtractionResultSchema`. Rather than introduce a parallel
   schema, the schema gained the same optional CAD fields the
   `CatalogPart` model added in 0029 (`part_subtype`, `material_name`,
   `material_class`, `bbox_*_mm`, `volume_mm3`, `cad_*`,
   `native_units`). The STEP parser shapes its `extracted_data` to
   include a nested `supplier: {name: …}` key so validation passes
   without per-handler special-casing. This keeps the approval logic
   single-pathed and avoids the kind of dual-flow drift that drove the
   earlier reverted CAT-001 attempt.

2. **Wardstone seed only fires when the `mason` user exists.**
   The prompt's seed SQL keys off `WHERE u.username = 'mason'`. On a
   bootstrap-empty database (fresh deploy with no users) the seed
   silently no-ops. Tests use `Base.metadata.create_all` (no migration)
   and seed Wardstone manually inside `_seed_wardstone(...)` in
   `test_step_upload_flow.py` — that's the standing pattern in the
   conftest.

3. **No new top-level lifecycle UI fields.**
   The prompt asks the frontend `CatalogPart` summary to render
   `part_subtype`/`material_class` chips. The summary type was
   extended with both fields; rendering them in the existing table
   was deferred — the existing rows are tight on horizontal space
   and the prompt explicitly says "Don't redesign the existing
   `/catalog/page.tsx` layout. Minor additions only." The fields
   are available for any future grid-card view.

4. **`getDocument` already existed in `catalog-api.ts`** — the prompt
   §4.2 lists `getPendingImport`, `patchPendingImport`,
   `approvePendingImport`, `rejectPendingImport` as new helpers, but
   they (and `updatePendingImport` which the prompt calls
   `patchPendingImport`) were already present in the API client. Only
   `uploadStep` was added.

5. **PartClass labels for the 12 new mechanical values use longer
   English forms** ("Fastener — Screw", "Seal / O-Ring", "Mechanical
   (Other)") rather than the prompt's verbatim slugs. Improves
   readability in the UI dropdown without requiring a parallel
   display-name field.

---

## Open follow-ups (deferred)

1. **pythonOCC in the Docker image** — the parser includes a graceful
   fallback (warning surfaced in the review UI). Adding `pythonocc-core`
   or `OCP` to `backend/Dockerfile` is a separate operational task.
   Estimated image-size cost: ~300 MB.

2. **Vendor seed CSV expansion** — `vendor_patterns.json` ships with
   four vendors (McMaster-Carr, Misumi, Grainger, MSC Industrial). The
   format supports drop-in additions; no parser change required.

3. **HAROLD nomenclature wiring** — `catalog_parts.part_number` stays
   as the manufacturer's MPN. HAROLD-format part-number issuance is a
   separate TDD; explicitly out of scope per the prompt's standing
   rule §5.

4. **Phase-7 ICD review UI parity** — the new
   `/catalog/pending-imports/[id]` page handles BOTH STEP-derived AND
   ICD-derived imports. The ICD-AI extractor's connector/pin tree
   isn't surfaced as an editor in this minimal page; it ships as
   read-only JSON in the "Additional fields" details. A richer
   per-connector editor lives in `/catalog/documents/[id]/review`.

5. **3D preview (`cad_preview_path`)** — the column exists in the
   schema and is parser-aware, but no preview rendering pipeline is
   wired. Depends on item 1 (pythonOCC in image).

---

*Updated 2026-05-15 alongside commit `phase-4(catalog-step): frontend Upload STEP + pending-imports review page`.*
