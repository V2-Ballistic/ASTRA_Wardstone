# Claude Code Execution Prompt — ASTRA ↔ HAROLD V2 Integration

> Wires ASTRA to HAROLD V2 (now running at `http://localhost:8031/api/v1/*`) so STEP uploads validate filenames against HAROLD's pattern, request next-available WPNs, register issued WPNs back to HAROLD's ledger, and degrade gracefully when HAROLD is unreachable.
>
> **Replaces the stale `CLAUDE_CODE_PROMPT_HAROLD-INTEGRATION-001.md`** which was speculative pre-V2 and targeted a WRENCH-plugin architecture that no longer matches reality.
>
> **Precondition:** HAROLD V2 is shipped and verified per `C:\Tools\harold\docs\PHASE_HAROLD_V2_COMPLETION_NOTES.md`. V2 reachable from ASTRA's backend container at `http://host.docker.internal:8031`.
>
> **ASTRA-side only.** HAROLD V2 already exposes the REST API surface we need; no HAROLD modifications planned.

---

## Mission

Working in `C:\Users\WardStone\Documents\ASTRA\`. Integrate ASTRA with HAROLD V2 so:

1. **On STEP upload**, ASTRA's parser runs as today. If the filename matches HAROLD's WPN pattern (`WS-<XX>-P<NNNNNN>-<REV>` with 21 system codes), ASTRA calls `POST /api/v1/wpn/validate` to check format + issued status. If the filename is manufacturer-style (McMaster's `92196A196_..._Screw.STEP`), ASTRA calls `GET /api/v1/wpn/suggest?system_code=<class-mapped-code>` to get a proposed WPN.
2. **On pending import review**, ASTRA shows the suggested or detected WPN inline. User can accept the suggestion, edit it (validates on blur via HAROLD), or leave it blank for auto-assignment on approval.
3. **On approval**, ASTRA calls `POST /api/v1/wpn/issue` (for auto-allocation) or `POST /api/v1/wpn/issue-specific` (for caller-supplied WPN). Sets `catalog_parts.internal_part_number` from the response. Audit-emits the WPN assignment.
4. **HAROLD's `_wardstone-harold-search` tool** (via its V2 ledger) queries ASTRA's `GET /api/v1/catalog/designators` to know what's already issued. ASTRA must fix that endpoint to filter on the correct column (it currently filters on `part_number` — the manufacturer MPN — but should filter on `internal_part_number` — the WPN).
5. **Graceful degradation:** when HAROLD is unreachable, ASTRA falls back to a local allocator (`catalog_wpn_fallback_sequences`), marks affected parts `wpn_pending_sync=TRUE`, and provides a manual "Sync with HAROLD" action that reconciles when HAROLD is back.

Filetype scope: STEP files first. The filename-validator + WPN-suggestion seam is built filetype-agnostic so future formats (PDF datasheets, drawings) plug in without refactor.

Commit per phase. Use `phase-<n>(harold-int): <summary>`. **Verify each phase before commit. Phase 0 is a mandatory stop with reconciliation report.**

---

## Pre-flight read

### HAROLD V2 surface (authoritative)

Read `C:\Tools\harold\docs\PHASE_HAROLD_V2_COMPLETION_NOTES.md` and `C:\Tools\harold\docs\HAROLD_V2_DESIGN.md` for the exact API contract. Confirm V2 is reachable from ASTRA's backend container:

```powershell
docker compose exec backend curl -sS http://host.docker.internal:8031/health
docker compose exec backend curl -sS http://host.docker.internal:8031/openapi.json | head -c 500
```

Both should succeed.

Key V2 endpoints this integration calls:

```
GET  /health
GET  /api/v1/system-codes                       — 21 codes with category
POST /api/v1/wpn/validate                       — format + ledger lookup
POST /api/v1/wpn/validate-bulk                  — up to 200 names
GET  /api/v1/wpn/suggest?system_code=FH&hint=  — next available
POST /api/v1/wpn/issue                          — allocate + register
POST /api/v1/wpn/issue-specific                 — register caller-supplied
PATCH /api/v1/wpn/{wpn}                         — metadata patch
GET  /api/v1/ledger/{wpn}                       — get one
```

WPN format: `WS-<XX>-P<NNNNNN>-<REV>` where XX is one of 21 codes (17 project-system + 4 library-category: FH/MH/EH/SH), NNNNNN is 6 digits 1-999999, REV is ASME 20-letter (`ABCDEFGHJKLMNPRTUVWY` — excludes I/O/Q/S/X/Z).

### ASTRA prior partial work (must reconcile)

The HAROLD-001 prior session shipped a partial skeleton. Phase 0's first task is auditing what exists and deciding whether to refactor or rewrite:

```powershell
docker compose exec backend find /app/app/services/harold -type f -name "*.py" 2>$null
docker compose exec backend find /app/app/routers -name "*harold*" -o -name "*.py" -path "*harold*" 2>$null
docker compose exec backend find /app/app/schemas -name "*harold*" 2>$null
docker compose exec db psql -U astra -d astra -c "\d catalog_parts" | findstr -i "wpn internal_part_number pending_sync"
docker compose exec db psql -U astra -d astra -c "\d systems" | findstr -i "system_code_2letter"
docker compose exec db psql -U astra -d astra -c "SELECT version_num FROM alembic_version"
```

Specifically look for:
- `backend/app/services/harold/client.py`, `service.py`, `errors.py`, `fallback.py`, `filename_validator.py`
- `backend/app/routers/harold.py`
- `backend/app/schemas/harold.py`
- Migration 0032 adding `systems.system_code_2letter` (deferred from SYSARCH-002, likely shipped by prior HAROLD-001 session)
- The `/catalog/designators` endpoint in `backend/app/routers/catalog.py` and what column it filters on
- Any `catalog_parts.internal_part_number` column (probably NOT present yet)

The prior work targeted the WRONG api shape (it assumed `POST /api/tools/_wardstone-harold-*/runs` envelope). It needs to be rewritten against V2's REST endpoints. The migration 0032 is keepable (`systems.system_code_2letter` is useful regardless).

### ASTRA core refs

- `backend/app/routers/catalog.py` — existing STEP upload at `POST /catalog/upload-step`, existing `_approve_pending_import` flow.
- `backend/app/models/catalog.py` — `CatalogPart` model. Phase 1 adds columns.
- `backend/app/services/cad/step_parser.py` — parser produces the filename + extracted_data that drives suggestion.
- `backend/app/config.py` — env vars / settings.
- `frontend/src/components/parts/StepUploadModal.tsx` — upload entry point.
- `frontend/src/app/catalog/pending-imports/[id]/page.tsx` — review page; this is where WPN suggestion surfaces.
- `frontend/src/app/catalog/page.tsx` — Catalog parts list; internal WPN becomes the primary identifier.
- `frontend/src/lib/catalog-api.ts`, `frontend/src/lib/catalog-types.ts`, `frontend/src/lib/errors.ts` — type and client updates.

---

## Decisions — locked

| # | Decision | Rationale |
|---|----------|-----------|
| AD-1 | `HAROLD_INTEGRATION_ENABLED` env var; default **`false`** for the initial build. Mason flips to `true` after end-to-end smoke passes. | Per Mason's "build and test isolated, then integrate to primary" framing. |
| AD-2 | HAROLD reached at `http://host.docker.internal:8031` from inside the ASTRA backend container. | Standard Windows Docker Desktop bridge. |
| AD-3 | Short timeout (3s) on all HAROLD calls. Graceful degradation on timeout or unreachable. | Don't block ASTRA's request path on HAROLD's availability. |
| AD-4 | All HAROLD calls go server-side from ASTRA's backend. Browser never talks to HAROLD directly. | Avoids CORS dance, centralizes auth (future), keeps CSP simple. |
| AD-5 | ASTRA is the system of record for catalog parts. HAROLD's ledger is a search/browse layer over what ASTRA has issued, populated via `POST /api/v1/wpn/issue` notifications on approval. | Matches V2 design (Option B from earlier — HAROLD has a ledger, but ASTRA's `catalog_parts.internal_part_number` is the source of truth for the underlying part). |
| AD-6 | Class → system_code mapping: `fastener_*`, `nut`, `washer`, `bracket`, `housing`, `enclosure`, `seal_o_ring`, `bearing`, `spring`, `structural_member` → **MH** (Mechanical Hardware) for non-fasteners and **FH** (Fastener Hardware) for fasteners. Electrical part_classes → **EH** (Electrical Hardware). Sealing → **SH** (Soft/Sealing Hardware). `mechanical_other` → MH. | Library-category codes added in V2 are the canonical catalog-level destinations. Old "default everything to ST" idea is wrong — ST is a project-system code, not a catalog category. |
| AD-7 | Class → system mapping lives as a Python dict constant in `app/services/harold/class_to_system.py`, NOT in a config file. Editable in code, version-controlled. | Avoids "we need to ship a config to change a mapping" surprise. |
| AD-8 | New migration adds `catalog_parts.internal_part_number VARCHAR(32)` (nullable, unique partial index), `catalog_parts.wpn_pending_sync BOOLEAN NOT NULL DEFAULT FALSE`, and `catalog_wpn_fallback_sequences` table. Migration number per current alembic head. | Standard additive migration pattern. |
| AD-9 | `/api/v1/catalog/designators` is corrected to filter on `internal_part_number` (not `part_number`). Returns `[{wpn, part_id, part_class, system_code, created_at}, ...]`. | Currently filters wrong column per Phase 0 of HAROLD-V2 finding. |
| AD-10 | `/api/v1/catalog/designators` stays unauthenticated for v1 (LAN-only). Future TDD adds shared-token header. | Matches HAROLD V2's posture. |
| AD-11 | Approval flow: if user-supplied WPN is present in pending import metadata, call `issue-specific`. If absent, call `issue` (auto-allocate). If HAROLD unreachable, use local fallback allocator and set `wpn_pending_sync=TRUE`. | Three branches, all deterministic. |
| AD-12 | Frontend WPN regex for live validation is hardcoded to V2's pattern (`^WS-[A-Z]{2}-P[0-9]{6}-[ABCDEFGHJKLMNPRTUVWY]$`). Backend always re-validates via HAROLD. | Frontend hint for fast UX; HAROLD is the authority. |

---

## Standing rules (subset)

1. **Drop-in file replacements only.** Whole-file output.
2. **No Alembic autogenerate.** Hand-write the migration.
3. **SQLAlchemy enum:** `.value` not `str()`.
4. **API list cap `limit=200`.**
5. **Backend in container** (`docker compose exec backend`). Frontend in container.
6. **PowerShell:** `curl.exe`, no `$PID`. Use `Invoke-RestMethod` for JSON.
7. **React hooks before any early `return`.** Optional chaining for null safety.
8. **TypeScript validates clean** post-changes via `npx tsc --noEmit`.
9. **Python AST validation** on every Python file.
10. **Login during testing:** `mason` / `password123`. The CAT-002 lexicon fix and the McMaster part already in `catalog_parts` are the test substrate.
11. **Don't touch HAROLD V2.** No edits in `C:\Tools\harold`. The V2 API is the contract; if something seems missing on V2's side, surface it and stop.
12. **Don't run a verification command and silently move past failure.** Stop on red.

---

## Phase 0 — Reconciliation + design report

Mandatory stop with report.

Tasks:

1. **Audit prior HAROLD work in ASTRA.** Read every file the discovery commands surface. Document each file's purpose, what it currently does, what it assumes about HAROLD's API (which is wrong), and whether it's salvageable or needs rewrite.

2. **Confirm migration 0032 state.** Did the prior session land `systems.system_code_2letter`? If yes, keep it (useful for SYSTEM-level WPN context in the future). If no, plan to skip it from this round; it's not blocking.

3. **Confirm V2 reachability** from the backend container (the curl above). Confirm `host.docker.internal:8031` resolves and `/health` returns 200.

4. **Fetch V2's OpenAPI spec** and save it to `docs/HAROLD_V2_OPENAPI.json` for reference. Endpoints, request/response shapes, and any optional parameters we'll use.

5. **Confirm the McMaster part state.** The CAT-002 fixture catalog part (the McMaster screw at `catalog_parts` id=1 or wherever it landed) is the smoke target. Document its current `part_class`, `part_subtype` (should be `fastener_screw` / `socket_head_cap_screw` after the lexicon fix), and confirm `internal_part_number` is null.

6. **Confirm the four ASTRA bugs identified earlier are fixed or surface them:**
   - The Phase 0 lexicon fix ("Socket Head Screw" → `fastener_screw`) — confirmed shipped earlier.
   - The error-rendering fix (`formatApiError` in `frontend/src/lib/errors.ts`) — confirmed shipped earlier.
   - The STEP upload form-field-name fix (`Content-Type: multipart/form-data`) — confirmed shipped earlier.
   - The CORS / CSP `connect-src` fix for LAN deployment — confirmed shipped earlier.

7. **Plan reconciliation strategy** for prior HAROLD work. Three paths:
   - **A (recommended):** delete prior HAROLD code in ASTRA, rebuild fresh against V2's actual REST API. Migration 0032 stays.
   - **B:** salvage what's salvageable, rewrite call sites against V2 endpoints. Risk: drift between salvaged code and new code, partial rewrites.
   - **C:** keep prior code as-is, add new V2 client alongside. Two HAROLD clients — definitely not.

Default recommendation: **A**. Cleaner separation, no half-migrated code, prior work was speculative and short.

Deliverable: write `docs/HAROLD_INTEGRATION_DESIGN.md` (overwrite if Phase 0 of the earlier prompt already produced one) with:
- Inventory of prior HAROLD work in ASTRA, file by file.
- V2 reachability confirmation.
- McMaster part state.
- Reconciliation path choice (A/B/C) with rationale.
- Confirmed Phase 1-7 plan with adjustments based on what's found.

Commit: `phase-0(harold-int): reconciliation report + V2 API capture`. Push and **stop**. Do not proceed.

---

## Phase 1 — ASTRA migration

Verify alembic head, then write `backend/alembic/versions/<NNNN>_harold_wpn_columns.py`:

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
        "ON catalog_parts(internal_part_number) "
        "WHERE internal_part_number IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_catalog_parts_pending_sync "
        "ON catalog_parts(wpn_pending_sync) WHERE wpn_pending_sync = TRUE"
    )
    op.execute("""
        CREATE TABLE IF NOT EXISTS catalog_wpn_fallback_sequences (
            system_code     VARCHAR(2)   PRIMARY KEY,
            next_index      INTEGER      NOT NULL DEFAULT 1,
            updated_at      TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    # Seed sequences for all 21 codes
    for code in (
        "VH","AE","AS","AV","BT","CC","CG","EE","FC","GN","GS",
        "OR","PR","ST","TH","TS","WH",
        "FH","MH","EH","SH",
    ):
        op.execute(
            f"INSERT INTO catalog_wpn_fallback_sequences (system_code) "
            f"VALUES ('{code}') ON CONFLICT DO NOTHING"
        )
```

Update `backend/app/models/catalog.py` — add `internal_part_number` and `wpn_pending_sync` columns to `CatalogPart`.

Verify:
```powershell
docker compose exec backend alembic upgrade head
docker compose exec db psql -U astra -d astra -c "\d catalog_parts" | findstr -i "wpn pending_sync"
docker compose exec db psql -U astra -d astra -c "SELECT system_code FROM catalog_wpn_fallback_sequences"
# 21 rows
docker compose exec db psql -U astra -d astra -c "SELECT COUNT(*) FROM requirements"
# Still 8
```

Commit: `phase-1(harold-int): WPN columns + fallback sequences migration`.

---

## Phase 2 — ASTRA's HAROLD V2 client + service layer

Per the Phase 0 reconciliation choice. Assuming Path A (delete prior, rebuild fresh):

Delete:
```
backend/app/services/harold/  (all prior contents)
backend/app/schemas/harold.py
backend/app/routers/harold.py
```

Then create fresh, targeting V2's REST API:

`backend/app/services/harold/__init__.py`
`backend/app/services/harold/errors.py` — `HaroldUnavailableError`, `HaroldInvalidResponseError`, `HaroldValidationError`, `HaroldDuplicateError`.

`backend/app/services/harold/client.py` — `HaroldClient(httpx.AsyncClient)` with methods that map 1:1 to V2 endpoints:
```python
class HaroldClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.harold_base_url
        self.timeout = settings.harold_timeout_seconds

    async def __aenter__(self): ...
    async def __aexit__(self, *args): ...

    async def heartbeat(self) -> dict: ...
    async def system_codes(self) -> dict: ...
    async def validate(self, wpn: str) -> dict: ...
    async def validate_bulk(self, wpns: list[str]) -> dict: ...
    async def suggest(self, system_code: str, hint: str | None = None) -> dict: ...
    async def issue(self, system_code: str, origin_system: str, origin_record_id: str,
                    display_name: str, description: str | None = None,
                    metadata: dict | None = None) -> dict: ...
    async def issue_specific(self, wpn: str, origin_system: str, origin_record_id: str,
                              display_name: str, **kwargs) -> dict: ...
    async def get_ledger_entry(self, wpn: str) -> dict: ...
```

Each method:
- Builds the URL from `base_url + "/api/v1/..."`.
- Wraps in `httpx.AsyncClient.request(...)` with the timeout.
- Catches `httpx.ConnectError`, `httpx.TimeoutException`, `httpx.HTTPError` and raises `HaroldUnavailableError` with the underlying message.
- Catches 4xx responses and raises domain-specific exceptions (e.g. `HaroldDuplicateError` on 409 from `issue-specific`).
- Returns parsed JSON dict on success.

`backend/app/services/harold/class_to_system.py`:
```python
PART_CLASS_TO_SYSTEM_CODE = {
    # Mechanical fasteners → FH
    "fastener_screw": "FH",
    "fastener_bolt": "FH",
    "nut": "FH",
    "washer": "FH",
    # Mechanical non-fastener hardware → MH
    "bracket": "MH",
    "housing": "MH",
    "enclosure": "MH",
    "bearing": "MH",
    "spring": "MH",
    "structural_member": "MH",
    "mechanical_other": "MH",
    # Sealing → SH
    "seal_o_ring": "SH",
    # Electrical → EH
    "processor": "EH",
    "sensor": "EH",
    "power_supply": "EH",
    "radio": "EH",
    "antenna": "EH",
    "actuator": "EH",
    "display": "EH",
    "harness": "EH",
    "connector_only": "EH",
    "compute_module": "EH",
    "power_distribution": "EH",
    "interface_card": "EH",
}

DEFAULT_SYSTEM_CODE = "MH"  # fallback for unmapped classes

def map_class_to_system(part_class: str) -> str:
    return PART_CLASS_TO_SYSTEM_CODE.get(part_class, DEFAULT_SYSTEM_CODE)
```

`backend/app/services/harold/filename_validator.py` — filetype-agnostic helpers:
```python
WPN_PATTERN = re.compile(
    r"^WS-[A-Z]{2}-P[0-9]{6}-[ABCDEFGHJKLMNPRTUVWY]$"
)

@dataclass
class FilenameValidationResult:
    is_wardstone_format: bool
    extracted_wpn: str | None
    base_name: str
    extension: str

def validate_filename(filename: str) -> FilenameValidationResult: ...
def extract_wpn_from_filename(filename: str) -> str | None: ...
```

`backend/app/services/harold/fallback.py` — local sequence allocator used when HAROLD is unreachable:
```python
def allocate_fallback_wpn(db: Session, system_code: str) -> str:
    """Reserves next WPN from catalog_wpn_fallback_sequences. Atomic.
    Returns formatted WPN string. Caller is responsible for setting
    wpn_pending_sync=True on the resulting catalog_part."""
```

`backend/app/services/harold/service.py` — high-level service functions called by the router:
```python
async def suggest_wpn_for_part(db: Session, part_class: str,
                                hint: str | None = None,
                                settings: Settings = ...) -> dict:
    """Maps part_class to system_code, calls HAROLD's suggest, returns
    {suggested_wpn, system_code, source: 'harold'} or falls back to
    {suggested_wpn: <fallback_dry_run>, system_code, source: 'fallback',
     reason: 'HAROLD unavailable: <message>'}."""

async def validate_filename_wpn(filename: str, settings: Settings = ...) -> dict:
    """If filename contains a Wardstone-format WPN, calls HAROLD's
    validate to check format + issued status. Returns the structured
    result. If filename doesn't contain a WPN, returns
    {is_wardstone_format: False}."""

async def issue_wpn_for_catalog_part(db: Session, part: CatalogPart,
                                     supplied_wpn: str | None = None,
                                     settings: Settings = ...) -> str:
    """Three branches:
    1. supplied_wpn present → call issue_specific. On 409, raise.
    2. supplied_wpn absent + HAROLD up → call issue. Set internal_part_number.
    3. supplied_wpn absent + HAROLD down → fallback.allocate_fallback_wpn.
       Set wpn_pending_sync=True.
    Returns the assigned WPN string. Caller commits the transaction."""

async def reconcile_pending_sync(db: Session, part: CatalogPart,
                                  settings: Settings = ...) -> bool:
    """For a part with wpn_pending_sync=True, re-validate its WPN against
    HAROLD. If valid + unique: register via issue_specific, clear the flag.
    If duplicate: reallocate via issue, update internal_part_number, clear
    the flag. Returns True if reconciled, False if HAROLD still unreachable."""
```

`backend/app/schemas/harold.py` — Pydantic models matching V2's response shapes (copy from `docs/HAROLD_V2_OPENAPI.json` Phase 0 saved).

Add config to `backend/app/config.py`:
```python
class Settings(BaseSettings):
    # ... existing ...
    harold_integration_enabled: bool = False
    harold_base_url: str = "http://host.docker.internal:8031"
    harold_timeout_seconds: float = 3.0
```

Backend tests using `respx` to mock HAROLD V2's API:
- `test_harold_client.py` — every client method, happy path + timeout + 5xx + connect error.
- `test_class_to_system.py` — every part_class maps correctly, unmapped falls back to MH.
- `test_filename_validator.py` — WS-FH-P000042-A matches, lowercase doesn't, McMaster filenames don't match, edge cases.
- `test_fallback_allocator.py` — sequential, atomic via FOR UPDATE, independent per system_code.
- `test_service.py` — `suggest_wpn_for_part` HAROLD-up vs down; `issue_wpn_for_catalog_part` all three branches; `reconcile_pending_sync`.

Verify:
```powershell
docker compose exec backend python -m pytest backend/tests/test_harold_*.py -v
```

Commit: `phase-2(harold-int): HAROLD V2 client + service + fallback + filename validator`.

---

## Phase 3 — ASTRA endpoints

### 3.1 Fix `/api/v1/catalog/designators`

Currently filters on `part_number` (manufacturer MPN). Change to filter on `internal_part_number`. Update in `backend/app/routers/catalog.py`:

```python
@router.get("/designators")
def list_catalog_designators(
    system_code: str | None = Query(None, regex=r"^[A-Z]{2}$"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """List internal_part_numbers (WPNs) ASTRA has issued, for HAROLD
    collision-avoidance and browse. Filter optional by system_code
    (2-letter prefix of the WPN).
    Returns: {designators: [{wpn, part_id, part_class, system_code, created_at}, ...], total}
    """
    q = db.query(CatalogPart).filter(
        CatalogPart.internal_part_number.isnot(None),
        CatalogPart.deleted_at.is_(None),
    )
    if system_code:
        q = q.filter(CatalogPart.internal_part_number.like(f"WS-{system_code}-P%"))
    total = q.count()
    rows = q.offset(skip).limit(limit).all()
    return {
        "designators": [
            {
                "wpn": p.internal_part_number,
                "part_id": p.id,
                "part_class": p.part_class.value if p.part_class else None,
                "system_code": p.internal_part_number.split("-")[1] if p.internal_part_number else None,
                "created_at": p.created_at,
            }
            for p in rows
        ],
        "total": total,
        "filter": {"system_code": system_code},
    }
```

### 3.2 New `/api/v1/harold/*` proxy router

`backend/app/routers/harold.py`:

```
GET  /api/v1/harold/heartbeat                    — V2 reachability check
GET  /api/v1/harold/system-codes                 — proxy to V2
POST /api/v1/harold/suggest                      — body: {part_class, hint}
POST /api/v1/harold/validate                     — body: {wpn}
POST /api/v1/harold/validate-filename            — body: {filename}
POST /api/v1/harold/parts/{part_id}/reconcile    — manual sync trigger for pending-sync parts
```

Each endpoint catches `HaroldUnavailableError` and returns:
```json
HTTP 200
{"harold_available": false, "reason": "..."}
```

For successful proxies, returns the V2 result with `{"harold_available": true, ...}`.

### 3.3 Wire upload + approval hooks

Modify `POST /api/v1/catalog/upload-step` (in `backend/app/routers/catalog.py`):

After parser runs, before creating the pending import:

```python
# Attempt HAROLD-based suggestion
if settings.harold_integration_enabled:
    try:
        suggestion = await harold_service.suggest_wpn_for_part(
            db,
            parsed.part_class,
            hint=parsed.original_filename,
            settings=settings,
        )
        extracted_data["proposed_wpn"] = suggestion["suggested_wpn"]
        extracted_data["wpn_source"] = suggestion["source"]
        extracted_data["wpn_suggestion_reason"] = suggestion.get("reason")
    except Exception as e:
        log.warning(f"HAROLD suggestion failed: {e}")
        extracted_data["wpn_source"] = "unavailable"

# If filename itself looks like a Wardstone WPN, also validate it
filename_check = await harold_service.validate_filename_wpn(
    parsed.original_filename, settings=settings
)
if filename_check.get("is_wardstone_format"):
    extracted_data["filename_wpn"] = filename_check["extracted_wpn"]
    extracted_data["filename_wpn_status"] = filename_check.get("status")
    if filename_check.get("is_duplicate"):
        warnings.append(
            f"Filename WPN {filename_check['extracted_wpn']} already issued."
            f" Suggested next: {filename_check.get('suggested_correction')}"
        )
```

Modify `_approve_pending_import` to assign the WPN:

```python
# After CatalogPart row created, before commit
if settings.harold_integration_enabled:
    user_supplied = extracted_data.get("user_supplied_wpn")  # set if user overrode
    proposed = extracted_data.get("proposed_wpn")
    final_wpn = user_supplied or proposed

    try:
        assigned_wpn = await harold_service.issue_wpn_for_catalog_part(
            db, part, supplied_wpn=final_wpn, settings=settings
        )
        part.internal_part_number = assigned_wpn
        # wpn_pending_sync set inside the service when fallback is used
    except HaroldDuplicateError as e:
        # Caller-supplied WPN conflicts. Reject the approval.
        raise HTTPException(409, f"WPN {final_wpn} already issued: {e}")

# Audit
_audit(db, "catalog.part.wpn_assigned", "catalog_part", part.id,
       current_user.id, {
           "wpn": part.internal_part_number,
           "wpn_pending_sync": part.wpn_pending_sync,
       })
```

### 3.4 Tests

`backend/tests/test_harold_endpoints.py`:
- Heartbeat happy + V2 down → returns `harold_available: false` (200).
- Suggest happy + V2 down.
- Validate happy + V2 down + 409 duplicate.
- Designators endpoint filters on `internal_part_number` correctly.
- Designators returns paginated results with correct shape.

`backend/tests/test_upload_approval_flow.py`:
- Upload happy path with HAROLD up → pending_import has `proposed_wpn` in extracted_data.
- Upload with HAROLD down → pending_import has `wpn_source: 'unavailable'`.
- Approval with proposed WPN → catalog_part has `internal_part_number` set, `wpn_pending_sync=False`.
- Approval with HAROLD down → catalog_part has fallback WPN, `wpn_pending_sync=True`.
- Approval with caller-supplied duplicate WPN → 409.

Verify:
```powershell
docker compose exec backend python -m pytest backend/tests/test_harold_*.py backend/tests/test_upload_approval_flow.py -v
```

Commit: `phase-3(harold-int): /api/v1/harold/* + designators fix + upload-approval wiring`.

---

## Phase 4 — Frontend integration

### 4.1 Types + client

`frontend/src/lib/harold-types.ts`:

```typescript
export interface WpnSuggestion {
  suggested_wpn: string;
  system_code: string;
  source: 'harold' | 'fallback';
  reason?: string;
}

export interface WpnValidationResult {
  wpn: string;
  is_valid_format: boolean;
  is_issued: boolean;
  errors: string[];
  warnings: string[];
  parsed?: { sys: string; num: number; rev: string };
  ledger_entry?: { part_id?: number; display_name?: string };
}

export interface HaroldResult<T> {
  harold_available: boolean;
  reason?: string;
  data?: T;
}
```

`frontend/src/lib/harold-api.ts`:

```typescript
export const haroldAPI = {
  heartbeat: () => apiClient.get('/harold/heartbeat'),
  suggest: (part_class: string, hint?: string) =>
    apiClient.post<HaroldResult<WpnSuggestion>>('/harold/suggest',
      { part_class, hint }),
  validate: (wpn: string) =>
    apiClient.post<HaroldResult<WpnValidationResult>>('/harold/validate',
      { wpn }),
  reconcile: (part_id: number) =>
    apiClient.post(`/harold/parts/${part_id}/reconcile`),
};
```

Add `internal_part_number?: string` and `wpn_pending_sync?: boolean` to the `CatalogPart` type.

### 4.2 Pending Import review (`frontend/src/app/catalog/pending-imports/[id]/page.tsx`)

Drop-in replacement. Above the existing extracted-data form, add a WPN section:

```tsx
{wpnSection && (
  <div className="rounded-xl border border-astra-border bg-astra-surface p-4 mb-4">
    <div className="flex items-center gap-3 mb-2">
      <h3 className="text-sm font-semibold uppercase text-astra-muted">
        Wardstone Part Number
      </h3>
      {wpnSection.source === 'harold' && (
        <span className="rounded-full bg-emerald-500/15 text-emerald-300 px-2 py-0.5 text-xs">
          Suggested by HAROLD
        </span>
      )}
      {wpnSection.source === 'fallback' && (
        <span className="rounded-full bg-amber-500/15 text-amber-300 px-2 py-0.5 text-xs">
          Fallback (HAROLD unavailable)
        </span>
      )}
    </div>

    <div className="flex items-center gap-3">
      <input
        type="text"
        value={wpnInput}
        onChange={onWpnChange}
        onBlur={onWpnBlur}
        className="flex-1 rounded-lg border border-astra-border bg-astra-bg px-3 py-2 font-mono text-sm"
        placeholder="WS-FH-P000042-A"
        pattern="^WS-[A-Z]{2}-P[0-9]{6}-[ABCDEFGHJKLMNPRTUVWY]$"
      />
      {validationStatus === 'valid' && (
        <Check className="h-4 w-4 text-emerald-400" />
      )}
      {validationStatus === 'invalid' && (
        <X className="h-4 w-4 text-red-400" />
      )}
    </div>

    {validationFeedback && (
      <p className="mt-2 text-xs text-astra-muted">{validationFeedback}</p>
    )}
  </div>
)}
```

On blur, calls `haroldAPI.validate(wpnInput)` and shows inline feedback.

Approve button disabled while validation is pending or shows invalid. When HAROLD is unavailable, the fallback WPN is shown but the user can still proceed (with `wpn_pending_sync=True` on the resulting part).

### 4.3 Catalog parts list (`frontend/src/app/catalog/page.tsx`)

Show `internal_part_number` as the primary identifier (bold, monospace) with manufacturer `part_number` as secondary (smaller, muted). If `wpn_pending_sync === true`, show a small amber dot on the card.

### 4.4 Catalog part detail page (`frontend/src/app/catalog/parts/[id]/page.tsx`)

Likewise. Add a "Sync with HAROLD" admin button visible only when `wpn_pending_sync === true`. Calls `haroldAPI.reconcile(part_id)`.

Verify:
```powershell
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Commit: `phase-4(harold-int): frontend WPN section + catalog list + reconcile UI`.

---

## Phase 5 — End-to-end smoke + reconciliation

Flip the feature flag:
```powershell
# Edit .env or however settings come in
$env:HAROLD_INTEGRATION_ENABLED = "true"
docker compose restart backend
```

Smoke matrix against the McMaster fixture (the screw already in the catalog from CAT-002):

1. ASTRA backend reaches HAROLD: `docker compose exec backend curl http://host.docker.internal:8031/health` → 200.
2. ASTRA's `/api/v1/harold/heartbeat` returns `{harold_available: true, ...}`.
3. Upload a NEW McMaster STEP file (rename the fixture or grab another McMaster bolt). Pending import page shows the green "Suggested by HAROLD: WS-FH-P000001-A" chip (or similar — HAROLD's first FH allocation).
4. Click Approve. Catalog part created with `internal_part_number = WS-FH-P000001-A`, `wpn_pending_sync = false`.
5. Verify via `curl http://localhost:8031/api/v1/ledger/WS-FH-P000001-A` — HAROLD's ledger shows the entry with `origin_system: 'astra'`, `origin_record_id: '<part_id>'`.
6. Catalog parts list shows the new internal WPN prominently.
7. Upload a second STEP. Pending import shows `WS-FH-P000002-A`. Approve.
8. Upload a third STEP file with filename matching `WS-FH-P000001-A.STEP` (rename for testing). Pending import shows a RED duplicate warning with `WS-FH-P000003-A` as the suggested correction.
9. Stop HAROLD: `cd C:\Tools\harold && docker compose stop harold-backend`.
10. Upload another STEP. Pending import shows AMBER "HAROLD unavailable — fallback WPN" chip. Approve. Catalog list shows the part with the amber sync-pending dot.
11. Restart HAROLD: `docker compose start harold-backend`.
12. Open the pending-sync part's detail page. Click "Sync with HAROLD". Confirm WPN is reconciled — same WPN if no collision, new WPN if collision. `wpn_pending_sync` flips to false.
13. From another LAN machine (`http://192.168.1.74:3000`), log in, upload a STEP, confirm the full flow works.

If any step fails, surface and stop.

Commit (state-only, no code): `phase-5(harold-int): end-to-end smoke validated`.

---

## Phase 6 — Tests + completion notes

### 6.1 Final test pass

```powershell
docker compose exec backend python -m pytest backend/tests/ -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

All green.

### 6.2 Completion notes

`docs/PHASE_HAROLD_INTEGRATION_NOTES.md`:
- Per-phase commits.
- Reconciliation strategy chosen in Phase 0.
- End-to-end smoke results from Phase 5.
- Open follow-ups deferred:
  - **Extend filename validation to PDF datasheets** — same validator seam, different upload route.
  - **Webhook from HAROLD to ASTRA on ledger changes** — currently ASTRA pulls; push would close the gap on cross-system drift.
  - **Authenticated `/catalog/designators`** — shared-token header for non-LAN deployments.
  - **Reconciliation worker** — currently manual button; an automatic worker would clear `wpn_pending_sync` for parts where HAROLD has returned without user action.
  - **Bulk upload of pre-named files** — when a folder of `WS-FH-P*.STEP` files is dropped, recognize each WPN, validate against HAROLD, only create new ledger entries for unknowns.
  - **WPN format display preferences** — some operators may prefer the system-code expanded (`WS-Fastener Hardware-P000042-A`); option in settings if requested.

Commit: `phase-6(harold-int): tests + completion notes`.

---

## Out of scope — do NOT do these

1. **Don't modify HAROLD V2.** V2 is the contract; if something seems missing on V2's side, surface and stop.
2. **Don't extend to PDF datasheets or other file types.** Filename validator is built generic, but STEP-only wiring this round.
3. **Don't add auth to `/catalog/designators`.** Future TDD.
4. **Don't build a reconciliation worker.** Manual button is sufficient for v1.
5. **Don't touch SYSARCH, MECH, EI-CLEANUP, or the lexicon fix.** Those are independent.
6. **Don't drop the legacy `/parts-library/*` routes.** Out of scope as usual.
7. **Don't redesign the catalog parts list layout.** Just promote the internal WPN to primary identifier; everything else stays.
8. **Don't bake HAROLD calls into the frontend directly.** All calls go through ASTRA's backend proxies (`/api/v1/harold/*`).

---

## Common gotchas

1. **`host.docker.internal` is Windows/Mac Docker Desktop only.** Mason is on Windows so fine. Document the Linux equivalent for future deployment.
2. **3-second timeout** on the backend, NOT the frontend. Frontend timeout of 30s would hang the UI. Backend fails fast and returns the structured "unavailable" response so the frontend renders gracefully.
3. **Concurrent fallback allocation race.** Two simultaneous uploads when HAROLD is down both allocate fallback WPNs. The `SELECT FOR UPDATE` in the fallback allocator prevents same-WPN collisions. After HAROLD returns, both reconcile attempts could re-collide; the reconcile service uses `issue_specific` first and falls back to `issue` (new allocation) if the specific number is already taken in HAROLD's ledger.
4. **`notify_wpn_issued` failure.** If HAROLD is up for `suggest` but transiently fails during the final `issue` call at approval time, the catalog part has no WPN. Either retry once or fall back to local allocator + `wpn_pending_sync=True`. Recommend the fallback path; user reconciles manually.
5. **Regex consistency.** ASTRA's frontend validates `^WS-[A-Z]{2}-P[0-9]{6}-[ABCDEFGHJKLMNPRTUVWY]$` for instant UX. Backend always re-validates via HAROLD. Don't try to make them share a string at the linguistic level (hard to do across Python/TS); duplicate the regex and add a comment.
6. **`/catalog/designators` filter `system_code`.** Filters parts whose `internal_part_number` starts with `WS-<XX>-`. Doesn't filter by the catalog `part_class` directly. If the caller wants part_class filtering, that's a different endpoint.
7. **`reconcile_pending_sync` partial failure.** If reconcile partially succeeds (HAROLD accepts the `issue_specific` but the audit emit fails), state is inconsistent. Wrap in a transaction; rollback on any failure.
8. **Catalog parts without `internal_part_number`** (pre-integration parts) appear in the list with manufacturer MPN as their only identifier. Don't break the existing display — null `internal_part_number` is valid and renders as "—" or "Not assigned" in the UI.
9. **The McMaster part already in `catalog_parts`** doesn't have an `internal_part_number`. Don't backfill it automatically — let Mason decide whether to retroactively assign WPNs to existing parts via a future cleanup script.
10. **HAROLD's `/api/v1/wpn/issue-specific` returns 409 on duplicate.** ASTRA's catch should translate that to a clear user-facing message: "WPN already issued to another part. Pick a different one or use auto-allocate."
11. **Audit event names.** `catalog.part.wpn_assigned`, `catalog.part.wpn_reconciled`, `catalog.part.wpn_pending_sync`, `harold.unavailable`. Consistent prefix patterns help future searches.
12. **`harold_integration_enabled = false`** must mean ASTRA behaves exactly as it does today. No surprise side effects from the new code paths.

---

## Sign-off

```powershell
docker compose exec backend python -m pytest backend/tests/ -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

All green → all phase commits → write `docs/PHASE_HAROLD_INTEGRATION_NOTES.md` → done.

If anything in this prompt conflicts with HAROLD V2's actual API (per Phase 0's OpenAPI capture), **stop and surface the conflict.** Don't refactor V2; don't drift the design.

The Phase 0 stop is mandatory. Do not proceed past Phase 0 without my explicit approval of `docs/HAROLD_INTEGRATION_DESIGN.md`.

---

*Prompt version 2.0 — supersedes `CLAUDE_CODE_PROMPT_HAROLD-INTEGRATION-001.md` (speculative pre-V2 attempt). This one targets the real V2 REST surface.*
