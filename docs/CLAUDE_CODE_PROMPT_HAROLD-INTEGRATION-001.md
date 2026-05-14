# Claude Code Execution Prompt — HAROLD ↔ ASTRA Bidirectional Integration

> Wires the Wardstone HAROLD nomenclature service to ASTRA. HAROLD becomes the authoritative source for Wardstone Part Numbers (WPNs). ASTRA validates uploaded filenames against HAROLD's pattern, requests next-available WPNs on approval, surfaces duplicate warnings inline, and exposes its own catalog to HAROLD so HAROLD's WPN suggestions account for parts ASTRA has already created.
>
> Starting filetype scope: **STEP files** (CAD parts). The validation/naming seam is built filetype-agnostic so future file types (PDF datasheets, drawings, ICDs) plug in without refactor.
>
> Cross-repo work. Affects both:
> - ASTRA: `C:\Users\WardStone\Documents\ASTRA`
> - HAROLD main: `C:\Tools\harold`
> - HAROLD wrench copy (the running instance): `C:\opt\wrench\tools-dev\wardstone-harold`

---

## Mission

Build the full bidirectional integration so:

1. **ASTRA on STEP upload** parses the filename. If it matches HAROLD's WPN pattern, ASTRA asks HAROLD to validate (format + uniqueness). If the filename doesn't match the pattern (manufacturer-style names like `92196A196_..._Screw.STEP`), ASTRA asks HAROLD what WPN to suggest based on the inferred part class.
2. **ASTRA on approval** assigns the suggested WPN (or the user's override) to `catalog_parts.internal_part_number`, stamps the file, and notifies HAROLD that the WPN is now in use.
3. **HAROLD before suggesting any next WPN** queries ASTRA for existing WPNs so it doesn't collide.
4. **ASTRA's UI** shows the suggested WPN inline during the pending-import review, with one-click accept or manual override. Duplicate or malformed names get an amber warning with the suggested fix.
5. **All flows degrade gracefully** when HAROLD is unreachable — ASTRA falls back to its own sequence allocator with a "WPN pending HAROLD sync" flag on the part.

Investigation-first. Phase 0 surfaces HAROLD's actual API, naming rules, data model, and running configuration. **Do not proceed past Phase 0 without explicit user approval of the discovered design.**

---

## Pre-flight read

### HAROLD discovery (the main task of Phase 0)

```powershell
# Main HAROLD repo
Get-ChildItem C:\Tools\harold -Recurse -File -Include *.py,*.md,*.toml,*.cfg,*.yml,*.yaml,Dockerfile | Select-Object FullName, Length, LastWriteTime
Get-Content C:\Tools\harold\README.md -ErrorAction SilentlyContinue
Get-Content C:\Tools\harold\pyproject.toml -ErrorAction SilentlyContinue
Get-Content C:\Tools\harold\docker-compose.yml -ErrorAction SilentlyContinue

# Wrench copy (the running one)
Get-ChildItem C:\opt\wrench\tools-dev\wardstone-harold -Recurse -File -Include *.py,*.md,*.toml | Select-Object FullName, Length

# Is HAROLD currently running?
Test-NetConnection -ComputerName localhost -Port 8030 -InformationLevel Detailed
curl.exe http://localhost:8030/ 2>&1
curl.exe http://localhost:8030/docs 2>&1
curl.exe http://localhost:8030/openapi.json 2>&1
curl.exe http://localhost:8030/api/tools/ 2>&1
```

Output everything you find. The integration design depends entirely on what HAROLD actually exposes.

### ASTRA-side refs

- `backend/app/routers/catalog.py` — existing STEP upload at `POST /catalog/upload-step`, existing `_approve_pending_import` flow.
- `backend/app/models/catalog.py` — `CatalogPart` model. We'll add `internal_part_number` column (similar to what the deferred HAROLD-001 prompt and the just-discussed WPN prompt described).
- `backend/app/services/cad/step_parser.py` — existing parser. The filename-already-parsed signal is here.
- `backend/app/config.py` — env vars / settings live here.
- `frontend/src/components/parts/StepUploadModal.tsx`, `frontend/src/app/catalog/pending-imports/[id]/page.tsx` — UI integration points.
- `frontend/src/lib/catalog-api.ts`, `frontend/src/lib/errors.ts` — client and error formatting (the latter was just shipped via the formatApiError fix).

### Two prior prompts to consult, NOT execute as-is

These were written speculatively before discovery; **read them for direction but do not follow them literally**:

- `docs/CLAUDE_CODE_PROMPT_HAROLD-001.md` (the deferred queue entry) — assumed HAROLD endpoints `_wardstone-harold-search`, `_wardstone-harold-validate`, `_wardstone-harold-data` on port 8030. Confirm or correct against reality.
- The conversation context describes a planned WPN allocator at `WS-<XX>-P<NNNN>-<REV>` format. Confirm or correct against HAROLD's actual pattern.

If the actual HAROLD differs from these assumptions in any material way, your Phase 0 report flags the conflicts and waits for direction.

---

## Decisions to confirm or revise during Phase 0

These were locked under the older HAROLD-001 prompt. Revisit each against what you actually find:

| # | Decision (provisional) | Verify against reality |
|---|------------------------|------------------------|
| AD-1 | Feature flag `HAROLD_INTEGRATION_ENABLED` (default `true` now that the integration is real, not optional). | Confirm Mason wants this default. |
| AD-2 | HAROLD reached via HTTP at `http://host.docker.internal:8030` from inside the ASTRA backend container. | Verify HAROLD listens on 8030 and accepts external connections. |
| AD-3 | Short timeout (3s) on all HAROLD calls. ASTRA degrades gracefully. | Tunable via env. |
| AD-4 | WPN format is `WS-<XX>-P<NNNN>-<REV>` where XX is HAROLD's class/system code. | Confirm in HAROLD source. |
| AD-5 | HAROLD is the authoritative WPN issuer. ASTRA's sequence allocator (if it exists) becomes a fallback only when HAROLD is unreachable, with the resulting part marked `wpn_pending_sync=true` for later reconciliation. | Confirm Mason agrees. |
| AD-6 | ASTRA exposes `GET /api/v1/catalog/designators` (no auth for v1, behind LAN only) for HAROLD to query existing WPNs. | OK as v1. |
| AD-7 | All HAROLD calls go server-side from ASTRA's backend. Browser never talks to HAROLD directly. | Avoids CORS, centralizes the policy. |
| AD-8 | Filename validation is filetype-agnostic — extract WPN candidate via regex, validate, suggest. STEP files first, but the validator is generic. | Future PDFs/drawings reuse the same code. |
| AD-9 | Migration adds `internal_part_number VARCHAR(32)` + a unique index + a `wpn_pending_sync BOOLEAN` flag on `catalog_parts`. Catalog WPN sequence table for fallback only. | Numbering per alembic head. |

---

## Standing rules (subset)

1. **Drop-in file replacements only.** Whole-file output.
2. **No Alembic autogenerate.** Hand-write the migration.
3. **SQLAlchemy enum:** `.value` not `str()`.
4. **API list cap `limit=200`.**
5. **Backend in container** (`docker compose exec backend`). Frontend in container.
6. **PowerShell:** `curl.exe`, no `$PID`. Use `Invoke-RestMethod` for JSON post bodies.
7. **React hooks before any early `return`.** Optional chaining for null safety.
8. **TypeScript validates clean** post-changes.
9. **Python AST validation** on every Python file.
10. **Login during testing:** `mason` / `password123`.
11. **Don't drop / don't touch** existing requirements (8), projects (1), users, audit_log, electronic_signatures, the catalog tables shipped under CAT-002, SYSARCH-002, EI-CLEANUP-001 work. The lexicon fix that just shipped stays.
12. **Don't run a verification command and silently move past failure.** Stop on red.
13. **Cross-repo discipline:** all ASTRA changes commit to the ASTRA repo. All HAROLD changes commit to `C:\Tools\harold` (the main, not the wrench copy). The wrench copy is the running instance; if HAROLD-side changes require restarting it, document the sync step in the completion notes.

---

## Phase 0 — Discovery and design report

Goal: understand HAROLD well enough to design the integration without guessing.

Tasks:

1. **Map HAROLD's runtime.** Is it FastAPI, Flask, something else? What process runs it? Is it Docker-containerized? Read pyproject.toml / requirements.txt / Dockerfile. Identify the actual entry point.

2. **Map HAROLD's API surface.** Hit `/`, `/docs`, `/openapi.json`, `/api/`, `/api/tools/` if they exist. Save the OpenAPI spec to `docs/harold_openapi.json` in the ASTRA repo for reference. Read the actual route definitions in HAROLD's Python source. Document every endpoint with method, path, params, expected request/response shape.

3. **Map HAROLD's WPN format and rules.** Find the validation regex, the allowed class/system codes, the revision letter rules, any reserved patterns. Document with examples (valid AND invalid).

4. **Map HAROLD's data model.** Where does HAROLD store the WPNs it has issued? SQLite? JSON files? Postgres? Memory only? If it has persistence, what's the schema? If it doesn't, how does it know what's been issued (does it expect to query everything from ASTRA each time)?

5. **Map HAROLD's existing collision-avoidance, if any.** Does it currently query anything to know what WPNs are taken? Is it just incrementing a counter? Does it have a duplicate-detection function we can reuse?

6. **Confirm HAROLD is running on port 8030 right now** and that requests from inside the ASTRA Docker network can reach it via `host.docker.internal:8030`:

   ```powershell
   docker compose exec backend curl -sS http://host.docker.internal:8030/ 2>&1
   ```

7. **Compare main vs wrench copy.** Diff `C:\Tools\harold` vs `C:\opt\wrench\tools-dev\wardstone-harold`. Are they in sync? Which one should we modify? Mason has indicated main is the source of truth and wrench is "a copy running." Confirm this and document the sync mechanism (manual copy? symlink? CI? git submodule?).

Deliverable: write `docs/HAROLD_INTEGRATION_DESIGN.md` in the ASTRA repo with:

- HAROLD's real surface (endpoints, formats, data model).
- A revised set of design decisions matching reality (where AD-1 through AD-9 above need adjustment).
- A sequence diagram (ASCII or markdown) of the upload-to-WPN-assignment flow, showing every call between ASTRA, HAROLD, and back.
- Any blocking concerns (e.g., HAROLD doesn't have a `/validate` endpoint, or its WPN format is incompatible with what we'd need).
- A confirmed phase plan for Phases 1-7 below, with adjustments.

Commit: `phase-0(harold-integration): discovery report`. Push and **stop**. Do not proceed.

---

## Phase 1 — ASTRA migration: internal_part_number + sync flag

Skip this phase if Phase 0 reveals it was already done by an earlier session. Otherwise:

Verify alembic head, then write `backend/alembic/versions/<NNNN>_internal_wpn.py`:

```python
def upgrade():
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS internal_part_number VARCHAR(32)"
    )
    op.execute(
        "ALTER TABLE catalog_parts "
        "ADD COLUMN IF NOT EXISTS wpn_pending_sync BOOLEAN NOT NULL DEFAULT FALSE"
    )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_catalog_parts_internal_wpn "
        "ON catalog_parts(internal_part_number) WHERE internal_part_number IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_catalog_parts_pending_sync "
        "ON catalog_parts(wpn_pending_sync) WHERE wpn_pending_sync = TRUE"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS catalog_wpn_fallback_sequences (
            class_code VARCHAR(8) PRIMARY KEY,
            next_index INTEGER NOT NULL DEFAULT 1,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)
```

`wpn_pending_sync = TRUE` marks parts that got a fallback WPN (HAROLD was down at approval time) and need reconciliation when HAROLD is back.

Verify migration applies, requirements count unchanged, etc. Commit: `phase-1(harold-integration): WPN columns + fallback sequence table`.

---

## Phase 2 — ASTRA's HAROLD client + service layer

Files under `backend/app/services/harold/`:

- `client.py` — `HaroldClient` using `httpx.AsyncClient`, methods per HAROLD's actual endpoints (use Phase 0 discovery). Wraps connection, timeout, retry, error.
- `errors.py` — `HaroldUnavailableError`, `HaroldInvalidResponseError`, `HaroldValidationError`, `HaroldDuplicateError`.
- `service.py` — high-level service functions: `validate_wpn(wpn)`, `suggest_wpn(class_code, hint)`, `notify_wpn_issued(wpn, part_id)`, `heartbeat()`. These are what the routers call.
- `fallback.py` — local sequence allocator used when HAROLD is unreachable. Pulls from `catalog_wpn_fallback_sequences`, sets `wpn_pending_sync=True` on parts assigned this way.
- `filename_validator.py` — filetype-agnostic. Functions: `extract_wpn_candidate(filename)`, `looks_like_wardstone_wpn(filename)`, `derive_class_hint(filename, parsed_metadata)`. Returns structured `FilenameValidationResult` Pydantic model.

Pydantic schemas in `backend/app/schemas/harold.py`:
- `WpnSuggestion` with `suggested_wpn`, `class_code`, `confidence`, `harold_available`.
- `WpnValidationResult` with `is_valid`, `is_duplicate`, `existing_part_id` (if duplicate), `errors`, `warnings`, `suggested_correction`.
- `HaroldHeartbeat` with `enabled`, `reachable`, `base_url`, `response_time_ms`, `version`.

Backend tests with `respx` mocking HAROLD:
- Validate happy path / 404 / 500 / timeout.
- Suggest happy path / unknown class / HAROLD down.
- Filename validator on real McMaster-style names and real Wardstone-style names.
- Fallback allocator on HAROLD-down condition; resulting part marked `wpn_pending_sync=True`.

Verify with `pytest`. Commit: `phase-2(harold-integration): client, service, fallback, filename validator`.

---

## Phase 3 — ASTRA endpoints

### Outbound proxy (under `/api/v1/harold`)

New router `backend/app/routers/harold.py`:

```
GET  /harold/heartbeat
GET  /harold/suggest-wpn?class_code=FS&hint=...
POST /harold/validate-wpn { wpn: "WS-FS-P0042-A" }
POST /harold/validate-filename { filename: "92196A196_..._Screw.STEP", parsed_metadata: {...} }
```

Each catches `HaroldUnavailableError` and returns 200 with `{"harold_available": false, "reason": "..."}`. The frontend uses `harold_available` to decide UI behavior.

### Inbound (for HAROLD to query us)

Extend `backend/app/routers/catalog.py`:

```
GET /api/v1/catalog/designators?class_code=FS&skip=0&limit=200
```

Returns `{designators: [{wpn, part_id, part_class, created_at}, ...], total, class_filter}`. Filters by `class_code` (the XX in WS-XX-P0042-A) by parsing `internal_part_number`. Unauthenticated for v1 (LAN-only assumption) but documented as such; future TDD adds a shared-token header.

### Upload + approval hooks

Modify the existing `POST /catalog/upload-step`:
1. Run parser as before.
2. Call `service.suggest_wpn(class_code, hint=parsed.original_filename)` to get a proposed WPN.
3. Embed `proposed_wpn` and `wpn_source` (`'harold'` or `'fallback'`) and any `wpn_validation_notes` into the pending import's `extracted_data`.
4. If filename already looks like a Wardstone WPN, also call `service.validate_wpn` and surface duplicate/format warnings in `extraction_warnings`.

Modify `_approve_pending_import`:
1. After CatalogPart row created and before commit:
   - Take the WPN from the user's review-page input (or the proposed WPN from `extracted_data` if user didn't change it).
   - Call `service.validate_wpn` one final time (in case state changed between upload and approval).
   - If valid + unique: set `part.internal_part_number = wpn`, `wpn_pending_sync = False`. Call `service.notify_wpn_issued`.
   - If duplicate or invalid: 422 to user with the conflict; require resolution before approval.
   - If HAROLD unavailable: use `fallback.allocate_wpn(class_code)`, set `wpn_pending_sync = True`. Log a warning.
2. Audit: `catalog.part.wpn_assigned` with full details.

Tests:
- Upload + approve happy path with HAROLD up: catalog_part has internal_part_number, `wpn_pending_sync=False`.
- Upload + approve with HAROLD down: catalog_part has fallback WPN, `wpn_pending_sync=True`.
- Approve attempt with WPN already in use → 422.
- Approve attempt with malformed WPN → 422.
- HAROLD calls `/catalog/designators?class_code=FS` → gets back the issued WPN.

Commit: `phase-3(harold-integration): outbound/inbound endpoints + upload-approval wiring`.

---

## Phase 4 — Frontend integration

### StepUploadModal (`frontend/src/components/parts/StepUploadModal.tsx`)

On submit: after the upload returns successfully (with the pending_import_id), no UI change here. The interesting UI is on the next page.

### Pending Import review (`frontend/src/app/catalog/pending-imports/[id]/page.tsx`)

Drop-in replacement with these additions:

- **WPN section, prominent, near the top of the form** — shows the suggested WPN from `extracted_data.proposed_wpn`:
  - If `wpn_source === 'harold'` and no validation issues: green chip "Suggested by HAROLD: **WS-FS-P0042-A**" with a "Use suggestion" toggle (on by default) and an "Edit" button to manually override.
  - If `wpn_source === 'fallback'` (HAROLD was down): amber chip "HAROLD unavailable — fallback WPN **WS-FS-P0042-A**. Will reconcile on approval if HAROLD returns."
  - If `extraction_warnings` contains a duplicate or format warning from HAROLD: red chip with the warning text and the corrected suggestion.
- **Manual override input** — text field, monospace, regex-validated client-side (`^WS-[A-Z]{2,3}-P\d{4}-[A-Z]$` or whatever HAROLD's actual regex is, copied from Phase 0 discovery). On blur, calls `POST /api/v1/harold/validate-wpn` and shows inline green/red feedback.
- **Approve button behavior** — disabled while WPN validation pending or showing red status. Enabled when WPN is valid + unique (or when HAROLD is down and user explicitly opts into fallback).

### Catalog parts list (`frontend/src/app/catalog/page.tsx`)

Parts tab cards/rows show `internal_part_number` as the primary identifier (bold, monospace) with the manufacturer's `part_number` as secondary (smaller, muted). A small amber dot on the card if `wpn_pending_sync = true`.

### Catalog part detail page

Likewise, internal WPN is the headline; manufacturer MPN is secondary. Add a small "Sync with HAROLD" admin action visible only when `wpn_pending_sync = true`.

### TypeScript types and API client

- Add `internal_part_number`, `wpn_pending_sync` to `CatalogPart` type.
- Add `haroldAPI.heartbeat()`, `validateWpn(wpn)`, `validateFilename(filename, metadata)` to `frontend/src/lib/harold-api.ts`.

Verify `tsc --noEmit` and `npm run build`. Commit: `phase-4(harold-integration): pending-imports WPN section + catalog list redesign + harold-api client`.

---

## Phase 5 — HAROLD-side modifications (cross-repo, `C:\Tools\harold`)

Smallest viable change. Based on what Phase 0 reveals about HAROLD's current structure, do whichever fits:

**Option A — HAROLD already has a WPN suggester.** Modify its "next available WPN" function to first call `GET http://host.docker.internal:8000/api/v1/catalog/designators?class_code=<XX>` (or whatever URL ASTRA is reachable at from HAROLD's perspective — they're likely both on the same host so `localhost:8000` from HAROLD-side). Merge ASTRA's list with HAROLD's local list, take the max, return max+1.

**Option B — HAROLD doesn't track WPNs itself.** Add a small SQLite or JSON-backed table to HAROLD that mirrors ASTRA's `catalog_parts.internal_part_number`. ASTRA's `notify_wpn_issued` call writes here. The suggester reads from here + queries ASTRA as backup.

**Option C — HAROLD is read-only / specification-only.** It just knows the format rules, doesn't track issuance. Then ASTRA's `notify_wpn_issued` is a no-op and `suggest_wpn` becomes "give me the rules, I'll find next available by querying my own designators."

Phase 0 tells you which is the case. Pick the smallest change and document the choice in `C:\Tools\harold\docs\ASTRA_INTEGRATION.md` (new file).

Config for ASTRA endpoint URL goes in HAROLD's config:
```
ASTRA_BASE_URL=http://host.docker.internal:8000
ASTRA_DESIGNATORS_TIMEOUT_SECONDS=2.0
```

After committing changes to `C:\Tools\harold`, document the sync step to the wrench copy at `C:\opt\wrench\tools-dev\wardstone-harold` in the completion notes. If the sync is manual, surface that to Mason — he may want to automate it.

Tests in the HAROLD repo (whatever testing framework HAROLD uses, discovered in Phase 0):
- Suggester queries ASTRA's `/catalog/designators`, merges, returns max+1.
- Suggester gracefully handles ASTRA being down (returns from HAROLD's local state only).
- `notify_wpn_issued` writes to HAROLD's local state.

Commit in HAROLD: `feat(astra-integration): query ASTRA designators + accept notify_wpn_issued`.

Restart the wrench HAROLD copy:

```powershell
# Whatever HAROLD's restart procedure is. Often:
Stop-Process -Name "harold" -Force -ErrorAction SilentlyContinue
# Then re-run the entrypoint as documented in HAROLD's README
```

---

## Phase 6 — End-to-end testing

Both services running. Walk this sequence in the browser and document each step in the completion notes.

1. Log into ASTRA at `http://localhost:3000`.
2. Catalog → Upload STEP. Pick a McMaster .STEP file with a long manufacturer-style name (e.g. the existing fixture or another McMaster part).
3. Pending Import page loads. Verify:
   - Extracted data populated.
   - **Suggested WPN section visible** with green "Suggested by HAROLD: WS-FS-P0042-A" chip (or similar).
   - "Use suggestion" toggle on by default.
4. Click Approve.
5. Catalog parts list shows the new part. Internal WPN prominent, manufacturer MPN secondary.
6. From a shell, query HAROLD directly:
   ```powershell
   curl.exe http://localhost:8030/api/tools/_wardstone-harold-search?class_code=FS  # or whatever endpoint Phase 0 documented
   ```
   Verify the new WPN appears in HAROLD's view.
7. Upload a second McMaster STEP. Pending import shows suggested `WS-FS-P0043-A` (incremented). Approve.
8. Upload a third STEP file with a filename matching `WS-FS-P0042-A.STEP` (rename the file for testing). Pending import shows a **red duplicate warning** with `WS-FS-P0044-A` as the suggested correction.
9. Stop HAROLD: `Stop-Process -Name "harold" -Force`.
10. Upload another STEP. Pending import shows **amber "HAROLD unavailable — fallback WPN"** chip. Approve. Catalog list shows the part with the amber sync-pending dot.
11. Restart HAROLD.
12. Open the pending-sync part's detail page. Click "Sync with HAROLD". Confirm WPN is reconciled (no change if the fallback WPN was correct; new WPN assigned if there was a collision with what HAROLD had issued in the meantime).
13. `ipconfig` to confirm LAN IP, then from another machine on the LAN: open `http://192.168.1.74:3000`, log in, upload a STEP, confirm the same HAROLD-suggested WPN flow works.

If any step fails, surface and stop.

---

## Phase 7 — Tests + completion notes

### Backend test consolidation

Make sure `pytest -v` passes the full suite. New tests added in Phases 2-3 must coexist with the existing 85+ tests.

### Frontend tests

`frontend/src/tests/harold-integration.test.tsx`:
- Suggested WPN chip renders for each `wpn_source` value.
- Manual override input validates against the regex.
- Approve button disabled while validation pending.

### Completion notes

`docs/PHASE_HAROLD_INTEGRATION_NOTES.md`:
- Final commit hashes per phase across both repos.
- The Phase 0 discovery findings — what HAROLD actually looks like vs what was assumed.
- Manual smoke matrix from Phase 6 with results.
- Open follow-ups deferred to future TDDs:
  - **Extend filename validation to PDF datasheets** (the next filetype Mason wants supported).
  - **Bidirectional webhook from HAROLD on rule changes** (currently ASTRA polls HAROLD's `/data` endpoint on demand).
  - **Authenticated `/catalog/designators` endpoint** with shared-token header for non-LAN deployments.
  - **Reconciliation worker** that periodically reattempts WPN sync for `wpn_pending_sync=true` parts without manual intervention.
  - **Multi-project WPN spaces** — if Wardstone ever wants different namespaces per project, the schema needs `wpn_namespace` and HAROLD needs to be aware.
- Sync step from `C:\Tools\harold` to `C:\opt\wrench\tools-dev\wardstone-harold` documented.

### Final verify

```powershell
docker compose exec backend python -m pytest backend/tests/ -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build

# HAROLD-side tests (command discovered in Phase 0)
cd C:\Tools\harold
# e.g.: python -m pytest tests/ -v   OR   poetry run pytest

# Both services running, the manual smoke from Phase 6 passes.
```

Commit: `phase-7(harold-integration): tests + completion notes`.

---

## Out of scope — do NOT do these

1. **Don't extend to file types beyond STEP yet.** The validator is built filetype-agnostic, but only STEP is wired through the upload flow this round. PDFs/drawings are a follow-on TDD.
2. **Don't redesign HAROLD.** Smallest viable change for the integration. If HAROLD's architecture needs broader work, surface it and defer.
3. **Don't authenticate the `/catalog/designators` endpoint.** v1 is LAN-only. Future TDD adds auth.
4. **Don't build a reconciliation worker.** Manual "Sync with HAROLD" button on pending-sync parts is enough for v1.
5. **Don't bundle this into a webhook system.** HAROLD-to-ASTRA notifications stay HTTP-pull for now.
6. **Don't add a HAROLD admin UI inside ASTRA.** Settings page surface is just a status indicator + manual heartbeat refresh.
7. **Don't touch SYSARCH, MECH, the pending PROJPARTS work, or the recently-shipped lexicon fix.** Those are independent.
8. **Don't drop the legacy `/parts-library/*` routes.** Untouched per usual.
9. **Don't add ASTRA-side validation that duplicates HAROLD's regex.** HAROLD owns the rules. ASTRA copies the regex into the frontend only for instant feedback; backend always re-validates via HAROLD.

---

## Common gotchas

1. **HAROLD's actual endpoint paths may differ from the assumptions.** Phase 0 must surface this. Don't assume `/api/tools/_wardstone-harold-search` — verify.
2. **`host.docker.internal` only works on Windows/Mac Docker Desktop.** Mason is on Windows, so fine. Document the Linux equivalent (`--add-host=host.docker.internal:host-gateway` in compose) as a footnote.
3. **HAROLD-side calling ASTRA at `localhost:8000`** — HAROLD runs on the host directly (not in Docker), so `localhost` from HAROLD's perspective is the host. ASTRA's backend port mapping `0.0.0.0:8000->8000` makes this work.
4. **Reconciliation race conditions.** Two concurrent uploads when HAROLD is down both allocate fallback WPNs. When HAROLD comes back, both reconcile attempts could pick the same WPN. Solve with a transaction + SELECT FOR UPDATE on the fallback sequence row, plus a final HAROLD validate-and-claim call.
5. **`notify_wpn_issued` failure on approval.** If HAROLD is up for `suggest_wpn` but transiently fails during `notify_wpn_issued`, the catalog_part has the WPN but HAROLD doesn't know. Mark `wpn_pending_sync=True` in this case and let the manual sync button handle it.
6. **Regex format consistency.** The validation regex must be IDENTICAL in HAROLD (authoritative), ASTRA backend (re-validation), and ASTRA frontend (live feedback). Centralize it in a single source. Recommended: HAROLD exposes `GET /api/rules/regex` returning the canonical regex; ASTRA fetches and caches at startup, refreshes daily.
7. **WPN format collisions on extension.** If HAROLD's actual format has 3 or more letters in the class code (e.g., `WS-FAS-P0042-A`), the existing 2-letter map needs to expand. Surface in Phase 0.
8. **Don't catch generic `Exception` in the HAROLD client.** Specific `httpx.HTTPError`, `httpx.TimeoutException`, `httpx.ConnectError`. Generic Exception swallows real bugs.
9. **Audit emit on every WPN transition.** Approval-time assignment, manual override, reconciliation, fallback allocation — all four emit distinct audit event types.
10. **CSP `connect-src`.** The frontend's CSP was just updated to align with CORS for LAN access. If you add new frontend endpoints under a different origin (e.g., direct calls to HAROLD's port 8030 — which AD-7 says NOT to do), the CSP would block them. Sticking to backend proxy keeps CSP simple.

---

## Sign-off

After Phase 7:

```powershell
docker compose exec backend python -m pytest backend/tests/ -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
cd C:\Tools\harold
# HAROLD's test command from Phase 0
```

All green → all commits across both repos → write `docs/PHASE_HAROLD_INTEGRATION_NOTES.md` → done.

If anything in this prompt conflicts with what's actually in either codebase, **stop and surface the conflict.** Especially: don't refactor HAROLD's architecture, don't change the existing CAT-002 STEP upload flow beyond the new WPN integration points, don't touch SYSARCH-002 or MECH-001 work, don't break the just-shipped lexicon expansion.

The Phase 0 stop is mandatory. Do not proceed to Phase 1 without the user reviewing `docs/HAROLD_INTEGRATION_DESIGN.md` and confirming the discovered design matches their intent.

---

*Prompt version 1.0 — supersedes the earlier `CLAUDE_CODE_PROMPT_HAROLD-001.md` (which was speculative; this one is grounded in real discovery).*
