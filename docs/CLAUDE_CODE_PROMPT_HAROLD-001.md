# Claude Code Execution Prompt — HAROLD nomenclature integration

> Wires ASTRA to the HAROLD nomenclature system (separate project at `http://localhost:8030/`) so users can suggest, validate, and reserve part numbers using the company's `WS-<SYS>-P<NNNN>-<REV>` CAD nomenclature standard with its 17 two-letter system codes.
>
> **Precondition:** SYSARCH-002, MECH-001, and PROJPARTS-001 have shipped. CAT-002 catalog work is solid. HAROLD must be running on the host at `http://localhost:8030/` for end-to-end testing — confirm with the user before kicking off Phase 4.

---

## Mission

Working in **`C:\Users\WardStone\Documents\ASTRA\`**. Add bidirectional HAROLD integration:

1. **Outbound (ASTRA → HAROLD):** when creating a new catalog part, optionally call HAROLD to suggest the next-available WPN for a given system code, or validate a manually-entered WPN against HAROLD's rules.
2. **Inbound (HAROLD → ASTRA):** expose `GET /api/v1/catalog/designators?system=AV` so HAROLD can see what part numbers ASTRA already issued and avoid collisions.
3. **Schema:** add `systems.system_code_2letter VARCHAR(2)` (deferred from SYSARCH-002) to capture the 2-letter code (`AV` = Avionics, `ST` = Structures, etc.). Optional, nullable. No enforcement against HAROLD's 17-value list — HAROLD owns that, ASTRA just passes through.
4. **Operability:** feature flag `HAROLD_INTEGRATION_ENABLED`, configurable URL/timeout, graceful degradation when HAROLD is unreachable.

Single source of architectural truth lives below. Commit per phase. Verify before each commit.

---

## Pre-flight read

### HAROLD API discovery

Confirm HAROLD is reachable from your dev workstation:

```powershell
curl.exe http://localhost:8030/api/tools/
```

If user has DESIGN.md or API docs for HAROLD locally, read them. Otherwise the assumed surface (per Mason's earlier description) is:

- `GET  /api/tools/_wardstone-harold-search?system=AV&part_class=...` → returns suggested next WPN(s)
- `POST /api/tools/_wardstone-harold-validate` with body `{wpn: "WS-AV-P0042-A"}` → returns validity + any collision info
- `GET  /api/tools/_wardstone-harold-data` → metadata about HAROLD (system code list, version, etc.)

If the actual HAROLD API differs from these, **stop and surface the difference** before proceeding. Don't guess endpoint shapes.

### ASTRA codebase

- `backend/app/routers/catalog.py` — the existing catalog router. You're adding a new `GET /catalog/designators` endpoint here.
- `frontend/src/app/catalog/parts/new/page.tsx` — the "New Part" flow. You're adding a "Suggest from HAROLD" button here.
- `frontend/src/app/projects/[id]/settings/page.tsx` — the project settings page (or check if there's a global `/settings` page; the existing structure may have one or the other).
- `backend/app/config.py` (or similar — find via `find /app -name "config.py"`) — where env vars are loaded.
- `backend/alembic/versions/` — to find current head and chain the migration.

---

## Network connectivity — critical

HAROLD lives on the **host machine** at `localhost:8030`. From inside the ASTRA backend Docker container, `localhost` refers to the container itself, not the host. Three options for connectivity:

| Option | Pros | Cons |
|--------|------|------|
| A — `host.docker.internal:8030` | Works on Windows/Mac Docker Desktop out of the box | Doesn't work on native Linux without `--add-host` |
| B — Bind ASTRA backend to host network | Simplest; `localhost` works | Loses Docker network isolation; conflicts on shared ports |
| C — Run HAROLD as a sibling Docker service | Cleanest long-term | Requires HAROLD's docker-compose adjustment, out of ASTRA's control |

**Default to Option A.** Mason is on Windows Docker Desktop (per session context), so `host.docker.internal` resolves correctly. The env var becomes:

```
HAROLD_BASE_URL=http://host.docker.internal:8030
```

Document Option C as a future improvement; don't implement it.

---

## Decisions — locked

| # | Decision | Rationale |
|---|----------|-----------|
| AD-1 | Feature flag `HAROLD_INTEGRATION_ENABLED` (default `false`). When false, ASTRA behaves as today — no HAROLD calls, no UI affordances. | Lets the integration ship dark and turn on per-deployment. |
| AD-2 | HAROLD client uses `httpx` (already in deps from earlier). Short timeout (3s). Failures degrade gracefully — UI shows "HAROLD unreachable, enter manually" rather than blocking. | Keeps ASTRA usable when HAROLD is down. |
| AD-3 | Add `systems.system_code_2letter VARCHAR(2)` (nullable) — deferred from SYSARCH-002. Stored uppercase. No DB-level enforcement of HAROLD's 17 values. | HAROLD owns the canonical list; ASTRA passes through. |
| AD-4 | The outbound `GET /api/v1/catalog/designators?system=AV` returns WPNs ASTRA has issued for a given 2-letter system code. Looks at `catalog_parts.part_number` filtering by pattern `WS-AV-P\d{4}-.*`. | HAROLD avoids collisions when suggesting next WPN. |
| AD-5 | "Suggest from HAROLD" button on New Part flow is **optional** — user can ignore and enter a WPN manually. We never auto-rewrite an existing WPN. | Soft integration; HAROLD is a tool, not a gate. |
| AD-6 | "Validate against HAROLD" runs on a small button (not on every keystroke) and on form submit. Result is informational; backend does NOT block save based on HAROLD validity. | Decouples ASTRA's data validity from HAROLD's availability. |
| AD-7 | Hand-written migration. Verify alembic head before writing. After SYSARCH/MECH/PROJPARTS run, head is likely 0030 or 0031. | Project standing rule. |
| AD-8 | All HAROLD calls run server-side (in the backend), not from the browser. Browser calls ASTRA's `/api/v1/harold/*` endpoints which proxy to HAROLD. | Avoids CORS issues; centralizes auth/timeout/retry; keeps the integration testable. |

---

## Standing rules (subset)

1. **Drop-in file replacements only.**
2. **No Alembic autogenerate.**
3. **SQLAlchemy enum:** `.value` not `str()`.
4. **API list cap `limit=200`.**
5. **Backend in container.** Frontend in container. PowerShell quirks per usual.
6. **React hooks before any early `return`.** Optional chaining throughout.
7. **TypeScript validates clean.**
8. **Python AST validation.**
9. **Login during testing:** `mason` / `password123`. Project DEF-MOD1 (id=2).
10. **Don't drop / don't touch** existing requirements (8), projects (1), users, audit_log, electronic_signatures, catalog work, SYSARCH work, MECH work, PROJPARTS work.
11. **Don't run a verification command and silently move past failure.**
12. **Don't make HAROLD a hard dependency.** ASTRA keeps working when `HAROLD_INTEGRATION_ENABLED=false` or HAROLD is down.

---

## Phase 1 — Migration + config

### 1.1 Migration

Verify alembic head first:
```powershell
docker compose exec backend alembic current
```

Number the migration accordingly. Assume `0032_harold_seam.py` if SYSARCH/MECH/PROJPARTS have all run; **adjust based on actual head**.

```python
"""ASTRA-TDD-HAROLD-001: HAROLD nomenclature seam — system_code_2letter

Revision ID: 0032
Revises: <prior head>
"""

revision = "0032"
down_revision = "0031"  # confirm via alembic current
branch_labels = None
depends_on = None


def upgrade():
    op.execute(
        "ALTER TABLE systems "
        "ADD COLUMN IF NOT EXISTS system_code_2letter VARCHAR(2)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS ix_systems_code_2letter "
        "ON systems(system_code_2letter)"
    )


def downgrade():
    op.execute("DROP INDEX IF EXISTS ix_systems_code_2letter")
    op.execute("ALTER TABLE systems DROP COLUMN IF EXISTS system_code_2letter")
```

### 1.2 Config

Add to `backend/app/config.py` (or wherever `Settings` / env loading lives):

```python
class Settings(BaseSettings):
    # ... existing settings ...
    harold_integration_enabled: bool = False
    harold_base_url: str = "http://host.docker.internal:8030"
    harold_timeout_seconds: float = 3.0
```

Add to `.env.example` (and document, don't auto-set in `.env`):

```
# HAROLD nomenclature integration (optional)
HAROLD_INTEGRATION_ENABLED=false
HAROLD_BASE_URL=http://host.docker.internal:8030
HAROLD_TIMEOUT_SECONDS=3.0
```

### 1.3 Verify

```powershell
docker compose exec backend alembic upgrade head
docker compose exec db psql -U astra -d astra -c "\d systems" | findstr system_code_2letter
docker compose exec db psql -U astra -d astra -c "SELECT COUNT(*) FROM requirements"  # still 8
```

Commit: `phase-1(harold): migration <NNNN> — system_code_2letter on systems + config flags`

---

## Phase 2 — Backend HAROLD client + service

### 2.1 `backend/app/services/harold/__init__.py` (NEW)

```python
"""HAROLD nomenclature integration — client + service helpers.

All calls to HAROLD originate here. The browser never talks to HAROLD directly;
it proxies through `/api/v1/harold/*` endpoints which use this module.

Behavior when HAROLD is disabled / unreachable:
  - All public functions raise `HaroldUnavailableError`.
  - Endpoints catch and return a structured 503-ish response so the UI
    shows "HAROLD unreachable, enter manually" gracefully.
"""
```

Files in `backend/app/services/harold/`:

- `client.py` — `HaroldClient` class with `httpx.AsyncClient`, methods for `search()`, `validate()`, `data()`, `heartbeat()`. Each wraps one HAROLD endpoint, applies the configured timeout, raises `HaroldUnavailableError` on network errors.
- `errors.py` — `HaroldUnavailableError`, `HaroldInvalidResponseError`.
- `service.py` — higher-level functions called by the router: `suggest_next_wpn(system_code, part_class)`, `validate_wpn(wpn)`, `is_enabled()`. Returns Pydantic models, not raw HTTP responses.

```python
# Example shape of service.py
async def suggest_next_wpn(
    system_code: str,
    part_class: Optional[str] = None,
    *,
    settings: Settings,
) -> WpnSuggestion:
    if not settings.harold_integration_enabled:
        raise HaroldUnavailableError("HAROLD integration disabled")
    async with HaroldClient(settings) as client:
        result = await client.search(system=system_code, part_class=part_class)
        return WpnSuggestion(
            suggested_wpn=result["suggested_wpn"],
            next_index=result["next_index"],
            existing_count=result["existing_count"],
            harold_version=result.get("version"),
        )
```

### 2.2 `backend/app/schemas/harold.py` (NEW)

Pydantic models for the proxy endpoints:
- `WpnSuggestion`
- `WpnValidationResult` — `{is_valid: bool, errors: list[str], warnings: list[str], suggested_correction: Optional[str]}`
- `HaroldHeartbeatResponse` — `{enabled: bool, reachable: bool, base_url: str, response_time_ms: Optional[int], version: Optional[str], system_codes: Optional[list[dict]]}`

### 2.3 Backend tests (mocked HAROLD)

`backend/tests/test_harold_service.py`:
- `test_suggest_next_wpn_returns_structured_result` — mock `httpx` with `respx`; assert client parses correctly.
- `test_suggest_next_wpn_raises_when_disabled` — settings.harold_integration_enabled=False → `HaroldUnavailableError`.
- `test_suggest_next_wpn_raises_on_timeout` — mock 5s response with 3s timeout → `HaroldUnavailableError`.
- `test_validate_wpn_passes_through_response` — happy path.
- `test_validate_wpn_handles_500_from_harold` — HAROLD returns 500 → `HaroldInvalidResponseError`.

If `respx` isn't installed: `pip install respx` in the running container or use `httpx-mock` / write a thin wrapper.

Verify:
```powershell
docker compose exec backend pip install respx
docker compose exec backend python -m pytest backend/tests/test_harold_service.py -v
```

Commit: `phase-2(harold): client + service + schemas + mocked tests`

---

## Phase 3 — Backend HAROLD router + outbound /designators

### 3.1 `backend/app/routers/harold.py` (NEW)

Mount at `/api/v1/harold`. Endpoints:

```
GET  /harold/heartbeat                                    — health check; returns enabled+reachable+latency
GET  /harold/suggest-wpn?system_code=AV&part_class=lru   — proxy to HAROLD search
POST /harold/validate-wpn { wpn: "WS-AV-P0042-A" }       — proxy to HAROLD validate
GET  /harold/system-codes                                — proxy to HAROLD data; returns the 17 codes for UI dropdowns
```

All endpoints require auth (existing `get_current_user` dependency). All endpoints catch `HaroldUnavailableError` and return:

```json
HTTP 200
{
  "harold_available": false,
  "reason": "HAROLD integration disabled" | "HAROLD unreachable: <error>" | ...
}
```

Returning 200 with a structured "unavailable" payload is intentional — the browser uses this to decide whether to show the "Suggest from HAROLD" button. A 503 would be less ergonomic for the UI.

For successful proxies, return the structured result with `harold_available: true`.

Register in `app/main.py`.

### 3.2 Outbound endpoint — `GET /api/v1/catalog/designators`

Add to `backend/app/routers/catalog.py` (drop-in replacement of the file with the new endpoint appended). This endpoint is consumed by HAROLD to know what WPNs ASTRA has issued.

```python
@router.get("/designators")
def list_catalog_designators(
    system: Optional[str] = Query(None, description="2-letter system code, e.g. AV"),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=200),
    db: Session = Depends(get_db),
    # No current_user requirement — this endpoint is consumed by HAROLD
    # which is a peer service, not a logged-in user. If you want auth,
    # use a dedicated API token (HAROLD_API_TOKEN env var) and check it here.
):
    """List part_numbers ASTRA has issued, for HAROLD collision-avoidance.
    Returns: {designators: list[str], total: int, system_filter: str | null}
    """
    query = db.query(CatalogPart.part_number).filter(CatalogPart.deleted_at.is_(None))
    if system:
        # Match WS-<SYSTEM>-P\d{4}-.* pattern
        query = query.filter(CatalogPart.part_number.like(f"WS-{system.upper()}-P%"))
    total = query.count()
    rows = query.offset(skip).limit(limit).all()
    return {
        "designators": [r[0] for r in rows],
        "total": total,
        "system_filter": system.upper() if system else None,
    }
```

**Auth note:** the endpoint is read-only and exposes only `part_number` (already public-ish data within the company network). Acceptable to leave it unauthenticated for v1. If the deployment is internet-exposed, add an `X-Harold-Token` header check using a shared secret env var.

### 3.3 Tests

`backend/tests/test_harold_router.py`:
- `test_heartbeat_returns_structured_response_when_enabled` — mock HAROLD reachable.
- `test_heartbeat_returns_unreachable_when_disabled` — `HAROLD_INTEGRATION_ENABLED=false`.
- `test_suggest_wpn_proxies_correctly` — mock HAROLD response, assert pass-through.
- `test_suggest_wpn_returns_unavailable_on_harold_500` — graceful degradation.
- `test_validate_wpn_proxies_correctly`.
- `test_designators_returns_only_matching_pattern` — seed catalog with mixed part_numbers, query `?system=AV`, assert only `WS-AV-*` returned.
- `test_designators_pagination_works`.

Verify:
```powershell
docker compose exec backend python -m pytest backend/tests/test_harold_service.py backend/tests/test_harold_router.py -v
```

Commit: `phase-3(harold): /api/v1/harold/* router + /api/v1/catalog/designators outbound`

---

## Phase 4 — Frontend integration

### 4.1 Types + API client

`frontend/src/lib/harold-types.ts`:
```typescript
export interface WpnSuggestion {
  suggested_wpn: string;
  next_index: number;
  existing_count: number;
  harold_version?: string;
}

export interface WpnValidationResult {
  is_valid: boolean;
  errors: string[];
  warnings: string[];
  suggested_correction?: string;
}

export interface HaroldHeartbeat {
  enabled: boolean;
  reachable: boolean;
  base_url: string;
  response_time_ms?: number;
  version?: string;
  system_codes?: { code: string; name: string }[];
}

// Discriminated wrapper used by every HAROLD call
export type HaroldResult<T> =
  | { harold_available: true; data: T }
  | { harold_available: false; reason: string };
```

`frontend/src/lib/harold-api.ts`:
```typescript
export const haroldAPI = {
  heartbeat: () => apiClient.get<HaroldHeartbeat>('/harold/heartbeat'),
  suggestWpn: (system_code: string, part_class?: string) =>
    apiClient.get<HaroldResult<WpnSuggestion>>(`/harold/suggest-wpn?system_code=${system_code}` + (part_class ? `&part_class=${part_class}` : '')),
  validateWpn: (wpn: string) =>
    apiClient.post<HaroldResult<WpnValidationResult>>('/harold/validate-wpn', { wpn }),
  systemCodes: () => apiClient.get<HaroldResult<{ codes: { code: string; name: string }[] }>>('/harold/system-codes'),
};
```

### 4.2 New Part flow integration

Modify `frontend/src/app/catalog/parts/new/page.tsx` — drop-in full replacement.

Above the `part_number` input, add a small affordance:

```tsx
{haroldAvailable && (
  <div className="mb-2 flex items-center gap-2">
    <select value={haroldSystemCode} onChange={...}
      className="rounded-lg border border-astra-border bg-astra-bg px-2 py-1 text-xs">
      <option value="">System code...</option>
      {haroldSystemCodes.map(c => <option key={c.code} value={c.code}>{c.code} — {c.name}</option>)}
    </select>
    <button onClick={handleSuggest}
      className="rounded-lg bg-violet-600 hover:bg-violet-500 px-3 py-1 text-xs font-semibold text-white flex items-center gap-1">
      <Sparkles className="h-3 w-3" /> Suggest from HAROLD
    </button>
    {suggestedWpn && (
      <span className="text-xs text-emerald-400 font-mono">{suggestedWpn}</span>
    )}
  </div>
)}
```

Behavior:
- On mount: call `haroldAPI.heartbeat()`. If `enabled && reachable`, set `haroldAvailable=true` and call `haroldAPI.systemCodes()` to populate the dropdown.
- "Suggest from HAROLD" button: requires system_code selected, calls `haroldAPI.suggestWpn(system_code, part_class)`, on success pre-fills `part_number` with `suggested_wpn` and shows the suggestion as an emerald hint.
- Below `part_number` input, add a small "Validate" button that calls `haroldAPI.validateWpn(part_number)` and shows the result inline (green check if valid, amber warning + suggested_correction if not).
- Form submit doesn't block on HAROLD validation — HAROLD is informational.

If HAROLD is unavailable (`harold_available: false`), the entire HAROLD UI block is hidden. Form behaves as today.

### 4.3 Settings page section

Modify `frontend/src/app/projects/[id]/settings/page.tsx` (or the global settings page if that's the structure). Add a new section:

```
HAROLD Integration
  Status: ✓ Connected / ✗ Disabled / ⚠ Unreachable
  URL: http://host.docker.internal:8030
  Version: 0.4.2 (if reachable)
  Last heartbeat: 12s ago
  [Test connection] button
```

Read-only — actual config lives in env vars. Just visualizes current state. Calls `haroldAPI.heartbeat()` on mount and when user clicks "Test connection."

### 4.4 Verify

```powershell
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Manual smoke (DEF-MOD1, id=2):

**With HAROLD reachable** (set `HAROLD_INTEGRATION_ENABLED=true` in `.env`, restart backend, confirm `host.docker.internal:8030` reachable from container):

1. Navigate to `/catalog/parts/new`. HAROLD section visible above part_number input. System code dropdown populated with HAROLD's 17 codes.
2. Pick "AV". Click "Suggest from HAROLD". `part_number` field pre-fills with something like `WS-AV-P0042-A`. Emerald hint shows the suggested WPN.
3. Modify the WPN to something invalid (e.g. `BAD-FORMAT`). Click "Validate". Inline error: "Format mismatch — expected WS-<SYS>-P<NNNN>-<REV>".
4. Settings page → HAROLD section shows "Connected", URL, version, latency.

**With HAROLD disabled** (set `HAROLD_INTEGRATION_ENABLED=false`, restart backend):

5. Navigate to `/catalog/parts/new`. No HAROLD section visible. Form works as today, manual WPN entry only.
6. Settings page → HAROLD section shows "Disabled".

**With HAROLD unreachable** (enabled but `host.docker.internal:8030` doesn't respond — stop HAROLD and retry):

7. New Part page: HAROLD heartbeat fails on mount, section is hidden. Form falls back to manual.
8. Settings page → HAROLD section shows "Unreachable" with the last error string.
9. ASTRA itself remains responsive — no UI hangs from HAROLD timeouts.

Commit: `phase-4(harold): frontend types + suggest/validate UI in new-part flow + settings status`

---

## Phase 5 — Tests + completion notes

### 5.1 Frontend tests

`frontend/src/tests/harold.test.tsx`:
- Heartbeat hook returns `enabled=false` when API responds with `harold_available=false`.
- Suggest button is hidden when HAROLD unavailable.
- Validate button shows green check on `is_valid=true`.
- Validate shows suggested_correction on `is_valid=false`.

### 5.2 Outbound endpoint contract test

`backend/tests/test_catalog_designators.py`:
- Seed catalog with `WS-AV-P0001-A`, `WS-ST-P0001-A`, `WS-AV-P0002-B`, plus a non-HAROLD-style `92196A196`.
- `GET /api/v1/catalog/designators?system=AV` returns 2 entries.
- `GET /api/v1/catalog/designators?system=ST` returns 1.
- `GET /api/v1/catalog/designators` (no filter) returns all 4.
- `?limit=200` cap respected.
- Soft-deleted parts (`deleted_at` not null) are excluded.

### 5.3 Completion notes

`docs/PHASE_HAROLD_COMPLETION_NOTES.md`:
- Per-phase commits.
- Manual smoke matrix results (3 scenarios: reachable, disabled, unreachable).
- Open follow-ups:
  - Bidirectional collision warning (HAROLD warns ASTRA when a manual WPN entry would collide with another project's WPN).
  - HAROLD as a sibling Docker service (Option C from the connectivity section).
  - HAROLD-driven catalog-wide WPN re-issuance for legacy parts that don't follow the standard.
  - Webhook from HAROLD to ASTRA on system-code list changes (today, ASTRA fetches on demand).
  - Auth between HAROLD and ASTRA's `/catalog/designators` (shared secret token).

### 5.4 Final verify

```powershell
docker compose exec backend python -m pytest backend/tests/test_harold_service.py backend/tests/test_harold_router.py backend/tests/test_catalog_designators.py -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Commit: `phase-5(harold): tests + completion notes`

---

## Out of scope — do NOT do these

1. **Don't make HAROLD a hard dependency.** Default flag is `false`; ASTRA must work without HAROLD installed.
2. **Don't auto-rewrite existing catalog WPNs** to match HAROLD's format. Existing parts (e.g. McMaster `92196A196`) keep their part_numbers.
3. **Don't enforce HAROLD validity at save time.** Validation result is informational. Backend never blocks `POST /catalog/parts` based on HAROLD's verdict.
4. **Don't build the bidirectional webhook flow.** ASTRA polls HAROLD when needed; HAROLD polls ASTRA's `/designators`. No webhooks v1.
5. **Don't refactor the existing catalog upload flow.** STEP upload ignores HAROLD — auto-detected manufacturer's MPN stays as the part_number.
6. **Don't refactor SYSARCH or MECH.** HAROLD slots in alongside the existing System.system_code_2letter (which we add in Phase 1) but doesn't change SYSARCH page behavior.
7. **Don't add HAROLD to the project-level Parts BOM page.** BOM line designations are project-internal; no HAROLD nomenclature there.
8. **Don't bundle HAROLD UI into the existing `/catalog/page.tsx`.** Keep the integration scoped to the New Part flow (`/catalog/parts/new`) and the Settings page.

---

## Common gotchas

1. **`localhost` from inside container.** From the backend container, `localhost:8030` is the container's own loopback. Use `host.docker.internal:8030` (Windows/Mac Docker Desktop). Document this in a comment in `config.py` for whoever next debugs.
2. **`httpx.AsyncClient` lifecycle.** Open it as an async context manager per-call OR maintain a module-level long-lived client. Per-call is simpler and adequate for low call volumes; long-lived is faster but adds shutdown complexity. Go per-call for v1.
3. **Timeout on the backend, not the frontend.** A 30s frontend timeout looks like a hung UI. Configure the backend to fail-fast at 3s and return a structured "unreachable" response; the frontend renders that gracefully.
4. **HAROLD endpoint shapes are assumed.** Your investigation in pre-flight read should confirm the actual HAROLD API. If different, surface and adjust before writing tests.
5. **Pattern matching in `/designators`.** PostgreSQL `LIKE` is case-sensitive; `WS-AV-P%` won't match `ws-av-p0042-a`. Either store WPNs uppercase (current convention seems to be uppercase) or use `ILIKE` in the query. Go with `LIKE` and uppercase the input; document in comments.
6. **`system_code_2letter` is uppercase.** Backend should `.upper()` on save and on query. Frontend dropdown values use uppercase.
7. **Settings page heartbeat polling.** Don't poll continuously — that hammers HAROLD. Heartbeat on mount + manual "Test connection" button. Maybe a 60s revalidation if you really want; not critical.
8. **Auth on the outbound `/catalog/designators` endpoint.** v1 leaves it unauthenticated for simplicity. Document this in the endpoint docstring as a security caveat. Future: shared-secret token via `X-Harold-Token` header.
9. **Don't catch generic `Exception` in the client.** Catch `httpx.HTTPError`, `httpx.TimeoutException`, `httpx.ConnectError` specifically. A bare `Exception` swallows real bugs (KeyError on response parsing, etc.).
10. **HAROLD enabled but base_url misconfigured.** If `HAROLD_BASE_URL` is wrong, every call times out. Heartbeat catches this — show "Unreachable: <connection refused>" in the settings UI rather than a generic "HAROLD unavailable."
11. **`respx` for tests.** Add to `backend/requirements-dev.txt` so it's part of the dev environment going forward, not just `pip install`-into-container.
12. **Don't expose HAROLD's internal errors to the user.** If HAROLD returns a 500 with internal stack trace, log it backend-side but show "HAROLD returned an error — try again or enter manually" to the user.

---

## Sign-off

```powershell
docker compose exec backend python -m pytest backend/tests/test_harold_service.py backend/tests/test_harold_router.py backend/tests/test_catalog_designators.py -v
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

All green → all phase commits → write `docs/PHASE_HAROLD_COMPLETION_NOTES.md`. Done.

If anything in this prompt conflicts with what's actually in the code or HAROLD's API, **stop and surface the conflict.** The HAROLD endpoint shapes especially — if `_wardstone-harold-search` doesn't accept `?system=` or returns a different structure, fix the assumption before writing the client.

---

*Prompt version 1.0.*
