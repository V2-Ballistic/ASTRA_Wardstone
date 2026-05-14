# Claude Code Execution Prompt — Electrical Interfaces Systems-Tab Cleanup

> Companion follow-up to SYSARCH-002. Removes the deprecated Systems tab from `/projects/[id]/interfaces` now that System Architecture owns systems/units management.
>
> **Precondition:** SYSARCH-002 has shipped, soak is complete, and the team has confirmed nobody is using the deprecation banner anymore. Don't run this until SYSARCH is solid.

---

## Mission

Working in **`C:\Users\WardStone\Documents\ASTRA\`**. Drop the Systems tab from `/projects/[id]/interfaces/page.tsx`. The page becomes Connections + N² Matrix only. Default tab becomes `connections`. The Systems-tab deprecation banner from SYSARCH Phase 6.5 also goes — it's no longer needed.

This is the smallest TDD in the queue. One commit, one phase, ~15-30 minutes.

---

## Pre-flight read

1. `frontend/src/app/projects/[id]/interfaces/page.tsx` — the page you're trimming. Read end-to-end. Identify:
   - The `Tab` type union (currently `'systems' | 'connections' | 'n2matrix'`).
   - The `useState<Tab>('systems')` default.
   - The Systems tab button in the tab bar.
   - The Systems tab body content (cards, search, the deprecation banner from SYSARCH 6.5, "Add System" button).
   - Any state/data fetching exclusive to the Systems tab (the `systems` array, related fetches, `setSystems`, etc.).
   - Whether `systems` data is used by Connections / N² Matrix tabs (it likely IS — N² Matrix needs the system list to label rows/columns). If so, keep the fetch but drop the tab UI only.

2. `frontend/src/components/layout/Sidebar.tsx` — confirm "System Architecture" is now in ENGINEERING (it should be from SYSARCH-002 Phase 6.4). If somehow missing, surface and stop — don't proceed without it.

3. `frontend/next.config.js` — confirm the `redirects()` for old `/interfaces/system/[id]` and `/interfaces/unit/[id]` routes exist (from SYSARCH-002 Phase 6.3). They should.

---

## Standing rules (subset)

1. **Drop-in file replacement.** Whole `interfaces/page.tsx` file delivered.
2. **Don't touch the backend.** `/api/v1/interfaces/systems/*` endpoints stay — System Architecture uses them. This is purely a frontend trim.
3. **Don't remove the `systems` data fetch** if Connections or N² Matrix consume it. Only the Systems tab UI goes.
4. **TypeScript validates clean** after the change: `docker compose exec frontend npx tsc --noEmit`.
5. **React hooks before any early `return`.** Optional chaining for null safety.
6. **Login during testing:** `mason` / `password123`. Test against project DEF-MOD1 (id=2).

---

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| AD-1 | Default tab is `connections`, not `n2matrix`. | Connections is the most-used view. N² Matrix is a specialty view. |
| AD-2 | URL `?tab=systems` (legacy bookmarks) silently falls back to `connections`. No redirect, no error. | The deprecation banner had a soak release; anyone bookmarking `?tab=systems` after that gets graceful fallback. |
| AD-3 | Page-level state for the `systems` array stays IF the N² Matrix or Connections views consume it. | They almost certainly do — N² rows/cols are systems. Don't break those. |
| AD-4 | No backend changes. | Systems endpoints are still used by `/system-architecture`. |

---

## Execution

### Single phase — drop the Systems tab

**File:** `frontend/src/app/projects/[id]/interfaces/page.tsx` (whole-file replacement)

Changes:

1. **Type narrowing:**
   ```typescript
   type Tab = 'connections' | 'n2matrix';
   ```
   Drop `'systems'` from the union.

2. **Default state:**
   ```typescript
   const [tab, setTab] = useState<Tab>('connections');
   ```

3. **URL param parsing:** wherever the page reads `?tab=...` from `useSearchParams`, coerce unknown values (including `'systems'`) to `'connections'`:
   ```typescript
   const rawTab = searchParams.get('tab');
   const initialTab: Tab = (rawTab === 'connections' || rawTab === 'n2matrix') ? rawTab : 'connections';
   ```

4. **Tab bar:** remove the Systems button (the `{ key: 'systems', ... }` entry from the tabs array). Connections and N² Matrix remain.

5. **Tab body:** remove the entire `{tab === 'systems' && (...)}` block, including the deprecation banner from SYSARCH 6.5, the search input that filtered systems, the system card grid, the "Add System" button. All of that gets deleted.

6. **`systems` data fetch:** **KEEP IT** if any other tab uses it (N² Matrix definitely does — it needs the system list to render axes). The `setSystems` and the fetch effect stay. Just the Systems tab UI goes.

7. **Imports cleanup:** remove unused imports if the Systems tab pulled in components/icons that no other tab uses (e.g. an `AddSystemModal` import, system-card-only icons). Keep imports that are still used by Connections/N² Matrix.

8. **Page header subtitle:** update to reflect the trimmed scope. From whatever it was to something like:
   ```
   Connections, harnesses, and N² interface matrix
   ```
   No more "Systems / Units / Harnesses" framing.

### Verify

```powershell
cd C:\Users\WardStone\Documents\ASTRA

docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Manual smoke (project DEF-MOD1, id=2):

1. Navigate to `/projects/2/interfaces`. Tab bar shows **Connections** | **N² Matrix** only. Connections is selected by default.
2. Direct URL `/projects/2/interfaces?tab=systems` → lands on Connections (graceful fallback). No error in console.
3. Direct URL `/projects/2/interfaces?tab=n2matrix` → lands on N² Matrix.
4. N² Matrix still renders with its full system axes — confirms the `systems` fetch is still working.
5. Direct URL `/projects/2/interfaces?tab=connections` → lands on Connections.
6. Sidebar nav still has "System Architecture" entry. Click it → `/projects/2/system-architecture` works.

Commit:

```
phase-1(ei-cleanup): remove Systems tab from /interfaces, keep systems fetch for N² Matrix
```

---

## Out of scope — do NOT do these

1. **Don't touch the backend `/api/v1/interfaces/systems/*` endpoints.** System Architecture page uses them.
2. **Don't remove the `next.config.js` redirects** that were added in SYSARCH-002 Phase 6.3. They serve old bookmarks.
3. **Don't refactor Connections or N² Matrix.** Pure deletion of the Systems tab.
4. **Don't drop the page-level `systems` state if other tabs consume it.** Verify via grep before deleting.
5. **Don't change the page route or filename.** Same path: `/projects/[id]/interfaces`.

---

## Common gotchas

1. **`systems` array consumed by N² Matrix.** Almost certainly yes. Grep `setSystems` and `systems\.` usage in the page before deciding to drop the fetch.
2. **The deprecation banner.** From SYSARCH-002 Phase 6.5. The whole `{tab === 'systems' && (<div>...</div>)}` deprecation block goes with the tab.
3. **TypeScript error if `Tab` union narrows but `setTab('systems')` lurks somewhere.** After narrowing, search for any string literal `'systems'` left as a tab argument and remove.
4. **`useSearchParams` on the App Router.** Reading happens on mount; if the page mounts with `?tab=systems`, the fallback in step 3 kicks in. If the URL is changed via `router.push`, also push to `?tab=connections` or remove the param entirely — don't re-introduce `?tab=systems` in any internal nav.
5. **Stale router pushes.** If any "Add System" button in this page used `router.push('?tab=systems')` to scroll to the tab after creating a system, those code paths are gone now. Should already be gone with the tab removal.

---

## Sign-off

```powershell
docker compose exec frontend npx tsc --noEmit
docker compose exec frontend npm run build
```

Both green → manual smoke passes → commit. Done.

If anything in this prompt conflicts with what's actually in `interfaces/page.tsx`, **stop and surface the conflict.** Don't refactor Connections, N² Matrix, harness logic, or any other interfaces functionality.

---

*Prompt version 1.0.*
