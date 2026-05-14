# Claude Code Execution Prompt — Phase 0 Quick Fixes

> Two user-reported bugs that block daily work. The catalog refactor (TDD-CAT-001, migration 0028) has already shipped — do **NOT** touch any of that work. This prompt is scoped tightly to the two fixes below.

---

## Mission

Working in **`C:\Users\Mason\Documents\ASTRA\`** (PowerShell, Docker Desktop, services in `docker-compose.yml`). Two fixes:

1. **Fix 0a** — User cannot change `req_type` from `functional` → `performance` after first save. Frontend-only fix.
2. **Fix 0b** — Session timeout silently kills unsaved form data (user lost an hour of work on a Source Artifact). Three-part fix: backend refresh tokens + frontend idle warning + form autosave.

Both fixes ship as a single phase. Commit when done with message `phase-0(quickfix): req_type editable + session refresh + form autosave`.

---

## Standing rules (subset, the ones that matter for this run)

1. **Drop-in file replacements only.** Whole-file edits, no partial patches.
2. **No Alembic autogenerate.** Hand-write migrations using `op.execute(text("..."))` or explicit `op.create_table()`.
3. **Backend commands inside the container:** `docker compose exec backend <cmd>`, `docker compose exec db psql -U astra -d astra`.
4. **PowerShell:** `curl` is an alias — use `curl.exe` or `Invoke-RestMethod`. `$PID` is reserved. Bcrypt operations stay inside the backend container.
5. **React hooks before any early `return`.** Optional chaining (`req?.field`) for null safety after hooks.
6. **TypeScript validates clean:** run `npx tsc --noEmit` from `frontend/` after changes.
7. **Python AST validation:** every Python file you create or modify must parse via `python3 -c "import ast; ast.parse(open('<f>').read())"`.
8. **Don't touch:** `users`, `projects`, `requirements`, `requirement_history`, `audit_log`, `electronic_signatures` table data. The 8 existing requirements must remain.
9. **Login during testing:** `mason` / `password123` (admin, user_id=1).

---

## Fix 0a — Requirement type lock after save

**Backend:** already correct. `RequirementUpdate` schema includes `req_type: Optional[str] = None`, and `update_requirement` in `backend/app/routers/requirements.py` runs `setattr(req, field, new_value)` for any field in `update_data`. The bug is frontend-only.

**Investigation step:** open `frontend/src/app/projects/[id]/requirements/[reqId]/page.tsx`. The metadata sidebar likely renders `req_type` as a static `<TypeBadge>` with no edit control, OR has a `disabled` predicate gated on `status !== 'draft'` (unjustified — there's no business rule that locks type after first save).

**Fix specification:**

- Render `req_type` as an inline-editable `<select>` matching the visual pattern of the existing `priority` / `level` controls in the same sidebar.
- Options: the 10 valid types from `frontend/src/lib/types.ts:RequirementType` (`functional`, `performance`, `interface`, `environmental`, `constraint`, `safety`, `security`, `reliability`, `maintainability`, `derived`).
- On change, call the existing `saveField('req_type', newValue)` helper. The backend `_record_history` will capture the change as a typed event automatically.
- **No status-based disabling.** Type changes are allowed at any status. The audit log captures the change for review.
- Add a small inline note next to the dropdown: "Changing type does not change the requirement ID." (because `req_id` like `FR-001` is already issued and we don't renumber.)

**Test to add — `backend/tests/test_requirement_type_change.py`:**

```python
def test_can_change_req_type_after_save(client, auth_headers, sample_req):
    # sample_req fixture creates a 'functional' requirement
    r = client.patch(
        f"/api/v1/requirements/{sample_req.id}",
        json={"req_type": "performance"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["req_type"] == "performance"

    # History records the change
    h = client.get(f"/api/v1/requirements/{sample_req.id}/history", headers=auth_headers)
    fields_changed = [entry["field_changed"] for entry in h.json()["history"]]
    assert "req_type" in fields_changed
```

**Verification:**

```powershell
docker compose exec backend pytest tests/test_requirement_type_change.py -v
```

Manual: edit a requirement in the UI, change type, save, refresh — type persists.

---

## Fix 0b — Session timeout eats unsaved form data

Three-part fix. All three ship together.

### Part 1 — Backend refresh-token mechanism

**Migration `backend/alembic/versions/0029_refresh_tokens.py`** (numbered 0029 because 0028 is the catalog migration that just landed):

```python
"""refresh tokens for sliding sessions

Revision ID: 0029
Revises: 0028
"""
from alembic import op
from sqlalchemy import text

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    op.execute(text("""
        CREATE TABLE refresh_tokens (
            id          BIGSERIAL    PRIMARY KEY,
            user_id     INTEGER      NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            token_hash  VARCHAR(255) NOT NULL UNIQUE,
            issued_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            expires_at  TIMESTAMPTZ  NOT NULL,
            revoked_at  TIMESTAMPTZ,
            user_agent  VARCHAR(512),
            ip_address  VARCHAR(64)
        );
        CREATE INDEX idx_refresh_tokens_user_id ON refresh_tokens(user_id);
        CREATE INDEX idx_refresh_tokens_expires ON refresh_tokens(expires_at);
    """))


def downgrade():
    op.execute(text("DROP TABLE IF EXISTS refresh_tokens CASCADE"))
```

**Model `backend/app/models/refresh_token.py`** — `RefreshToken` SQLAlchemy model. Add to `app/models/__init__.py` exports.

**Auth router** (`backend/app/routers/auth.py`) — modify and extend:

- **Modify** `POST /auth/login`: on success, also generate a refresh token (32-byte url-safe random via `secrets.token_urlsafe(32)`), store SHA-256 hash in `refresh_tokens` with 7-day `expires_at`, set as `httpOnly`, `samesite='lax'` cookie named `refresh_token`. Return access token in body as today.
- **Add** `POST /auth/refresh`: read the `refresh_token` cookie, hash it, look up by `token_hash`. Reject if not found, expired, or revoked. **Rotate**: revoke the old token (`revoked_at = NOW()`), issue a new one, set new cookie. Return `{ access_token, expires_at }` for the new access token (30 min TTL).
- **Add** `POST /auth/logout`: revoke ALL refresh tokens for the current user (set `revoked_at = NOW()` on every non-revoked row). Clear the cookie.

Use the existing JWT helpers in `backend/app/services/auth.py` for access tokens. Refresh tokens are opaque random strings, NOT JWTs.

**Test — `backend/tests/test_auth_refresh.py`:**

```python
def test_refresh_rotates_token(client):
    # Login
    r = client.post("/api/v1/auth/login",
                    json={"username": "mason", "password": "password123"})
    assert r.status_code == 200
    cookie = r.cookies.get("refresh_token")
    assert cookie

    # Refresh succeeds
    client.cookies.set("refresh_token", cookie)
    r2 = client.post("/api/v1/auth/refresh")
    assert r2.status_code == 200
    new_cookie = r2.cookies.get("refresh_token")
    assert new_cookie and new_cookie != cookie

    # Old refresh token is now revoked — replay must fail
    client.cookies.set("refresh_token", cookie)
    r3 = client.post("/api/v1/auth/refresh")
    assert r3.status_code == 401


def test_logout_revokes_all_tokens(client):
    r = client.post("/api/v1/auth/login",
                    json={"username": "mason", "password": "password123"})
    cookie = r.cookies.get("refresh_token")
    client.cookies.set("refresh_token", cookie)

    client.post("/api/v1/auth/logout")
    r2 = client.post("/api/v1/auth/refresh")
    assert r2.status_code == 401
```

### Part 2 — Frontend axios interceptor + SessionMonitor

**New file `frontend/src/lib/auth-refresh.ts`:**

- Wires into the existing axios instance in `frontend/src/lib/api.ts`.
- On any 401 from `/api/v1/*` (EXCEPT `/auth/login` and `/auth/refresh` themselves), trigger a single in-flight refresh: `POST /auth/refresh`. On success, retry the original request with the new access token. On failure, redirect to `/login`.
- **Recursion guard:** mark the refresh request itself with a flag (`config._isRefresh = true`) and skip the interceptor for those.
- **Concurrency guard:** if multiple 401s arrive simultaneously, all wait on the same in-flight refresh promise so we don't fire 5 refreshes at once.
- After every successful API response, dispatch a custom event `window.dispatchEvent(new Event('astra:api-call'))` that the SessionMonitor listens for.

**New file `frontend/src/components/SessionMonitor.tsx`:**

- Listens for activity events: `mousedown`, `keydown`, and the custom `astra:api-call`.
- Tracks `lastActivity` timestamp.
- At T-5 minutes of inactivity (i.e. `now - lastActivity > 25 minutes` if access TTL is 30), shows a modal: **"You'll be signed out in 5 minutes due to inactivity. Stay signed in?"** with a single primary button.
- Modal button calls `POST /auth/refresh` and resets the timer.
- At T-0 (full window elapsed, 30 min default), force-logout via `POST /auth/logout` and redirect to `/login`.
- Configurable: read TTL from a window-level constant or `process.env.NEXT_PUBLIC_SESSION_WARN_MIN` (default 25) / `_SESSION_TIMEOUT_MIN` (default 30).

**Modify `frontend/src/components/layout/AppShell.tsx`:** mount `<SessionMonitor />` inside the authenticated branch alongside `<Sidebar />`. Drop-in full file replacement.

### Part 3 — Form autosave to localStorage

**New file `frontend/src/lib/autosave.ts`:**

```typescript
export interface AutosaveOptions {
  debounceMs?: number;     // default 1500
  ttlMs?: number;          // default 7 days
}

export interface AutosaveResult<T> {
  hasDraft: boolean;
  draftAge: number | null;        // ms since draft saved, null if no draft
  restoreDraft: () => T | null;
  clearDraft: () => void;
}

/**
 * Debounced autosave of a form state object to localStorage.
 *
 * Storage shape: { value: T, savedAt: number }
 * Storage key convention: `astra:autosave:<form-name>:<scope>`
 *   - req-new:project-${projectId}
 *   - req-edit:${reqId}
 *   - source-new:project-${projectId}
 *   - source-edit:${sourceId}
 */
export function useFormAutosave<T extends object>(
  storageKey: string,
  state: T,
  options: AutosaveOptions = {}
): AutosaveResult<T>;
```

Implementation notes:
- On mount, read localStorage. If a draft exists and `Date.now() - savedAt < ttlMs`, set `hasDraft=true` and `draftAge`.
- If older than TTL, delete and `hasDraft=false`.
- On every state change, debounce-write `{ value: state, savedAt: Date.now() }` to localStorage after `debounceMs`.
- `restoreDraft()` returns the saved value (caller decides how to merge into form state).
- `clearDraft()` removes the localStorage entry. Form's onSubmit handler must call this on successful save.
- Skip writes when state is empty/initial (avoid prompting "restore?" on a blank form the user never typed in).

**New file `frontend/src/components/RestorePromptBanner.tsx`:**

Reusable banner component. Props: `{ ageMs: number; onRestore: () => void; onDiscard: () => void }`.

UI: amber banner with `Clock` icon, copy "Found unsaved changes from `<relative time>` ago", **Restore** button (gradient blue→violet) and **Discard** button (text-only).

Render at the top of the form, above the actual fields. Hide once user clicks either button.

**Wire autosave into these forms:**

| Form | File | Storage key |
|------|------|-------------|
| New requirement | `frontend/src/app/projects/[id]/requirements/new/page.tsx` | `astra:autosave:req-new:project-${projectId}` |
| Edit requirement | `frontend/src/app/projects/[id]/requirements/[reqId]/page.tsx` (the inline edit area; coexists with Fix 0a) | `astra:autosave:req-edit:${reqId}` |
| New source artifact | search the codebase for `SourceArtifactCreate` usage and the source artifact create page | `astra:autosave:source-new:project-${projectId}` |
| Edit source artifact | same area (likely a sibling page) | `astra:autosave:source-edit:${sourceId}` |

For each form:
1. Build a single `formState` object from the existing `useState` fields.
2. Call `useFormAutosave(storageKey, formState)` — receive `{ hasDraft, draftAge, restoreDraft, clearDraft }`.
3. Render `<RestorePromptBanner>` at the top when `hasDraft` is true. `onRestore` repopulates form state from `restoreDraft()`. `onDiscard` calls `clearDraft()`.
4. In the form's submit handler, call `clearDraft()` after successful save.

**Do NOT add autosave to:** any login form, any password-changing form, the auth/refresh flow.

### Verification (Fix 0b end-to-end)

```powershell
docker compose exec backend alembic upgrade head
docker compose exec backend alembic current  # should show 0029

docker compose exec backend pytest tests/test_auth_refresh.py -v

cd frontend
npx tsc --noEmit
npm run build
```

Manual smoke:

1. Log in. Open DevTools → Application → Cookies. Confirm `refresh_token` cookie is set, `httpOnly=true`, expiry ~7 days out.
2. Open New Requirement. Type a title and statement. Wait 2 seconds. Refresh the page. Banner should appear: "Found unsaved changes from a few seconds ago — Restore | Discard". Click Restore. Form repopulates.
3. Submit the requirement. Refresh New Requirement. No banner (autosave was cleared on submit).
4. Open New Requirement, type a few characters, **leave the tab idle for 26 minutes** (or temporarily set `NEXT_PUBLIC_SESSION_WARN_MIN=0.5` for testing). Modal should appear at the warning threshold: "You'll be signed out in 5 minutes…". Click Stay Signed In. Modal closes, session continues.
5. Repeat #4 but don't click. After full timeout, redirected to login. Log back in. Open New Requirement. Banner appears, content recoverable.

---

## Out of scope — do NOT do these

1. **Don't modify any of the catalog work** that just shipped: `catalog_parts`, `catalog_part_mechanical`, `catalog_part_electrical`, `pending_imports`, `supplier_aliases`, the Catalog page, the Pending Imports review page, the STEP parser, the seed JSON files, migration `0028`. All of that is committed (or about to be) — leave it alone.
2. **Don't drop or alter** any existing tables. The 8 requirements must remain. The 1 project must remain. Wardstone supplier seed must remain.
3. **Don't touch System Architecture, Mechanical Interfaces, Electrical Interfaces, or Project Parts pages.** Those are future TDDs.
4. **Don't refactor the existing auth code beyond what these fixes require.** The bcrypt + JWT login flow stays. We're adding a refresh-token layer on top, not replacing.

---

## Common gotchas

1. **CORS + cookies in dev:** the refresh cookie needs `samesite='lax'`. Without it, the cookie won't be sent on the SPA's POST. In dev (HTTP), use `secure=False`. In prod (HTTPS), `secure=True`.

2. **Axios interceptor recursion:** if `POST /auth/refresh` itself returns 401 (e.g. refresh token revoked), the interceptor must NOT loop. Mark refresh requests with `config._isRefresh = true` and short-circuit.

3. **Single in-flight refresh:** module-level promise variable. All concurrent 401s wait on the same promise. Reset to null after resolve/reject.

4. **localStorage SSR:** Next.js renders some components on the server where `window` is undefined. The autosave hook must guard: `if (typeof window === 'undefined') return;`. Don't use `localStorage` directly in render.

5. **Don't autosave password fields.** Defensive — there are no current login autosave use cases, but if you ever add a "change password" form, opt out.

6. **Cross-tab autosave conflicts:** if a user opens the same form in two tabs, both write to the same localStorage key. Last write wins, which is acceptable. The restore banner shows the timestamp so the user knows what they're getting.

7. **Form state object identity:** the autosave hook needs stable identity for the state object to debounce correctly. Use `useMemo` to derive a single `formState` object from individual `useState` values — don't pass an inline object literal.

8. **The req_type fix and the autosave fix overlap on the same file** (`requirements/[reqId]/page.tsx`). Apply both in a single drop-in replacement. Don't deliver two competing versions.

---

## Sign-off

When done:

```powershell
docker compose exec backend pytest tests/test_requirement_type_change.py tests/test_auth_refresh.py -v
cd frontend && npx tsc --noEmit && npm run build
```

Both green → commit:

```
phase-0(quickfix): req_type editable + session refresh + form autosave
```

If anything in this prompt conflicts with what you find in the code, **stop and surface the conflict** rather than guessing. The auth code in particular has been touched by multiple iterations; verify the current shape before extending.

---

*Prompt version 1.0 — companion to `CLAUDE_CODE_PROMPT_CAT-001.md`.*
