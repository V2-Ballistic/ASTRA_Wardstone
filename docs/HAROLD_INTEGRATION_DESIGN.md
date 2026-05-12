# ASTRA ↔ HAROLD V2 Integration — Phase 0 Reconciliation Report

Author: Phase 0 agent (HAROLD-INTEGRATION-002).
Date: 2026-05-12.
Status: **Stops here for Mason's review.** No Phase 1 work has begun.

This document supersedes the earlier Phase 0 report from
`HAROLD-INTEGRATION-001` (the pre-V2 speculative attempt). Saved
companion: `docs/HAROLD_V2_OPENAPI.json` — V2's OpenAPI spec, captured
live for reference.

---

## TL;DR

1. **V2 is reachable from ASTRA's backend container** at
   `http://host.docker.internal:8031`. `/health` returns 200
   `{"status":"healthy","version":"2.0.0","db":"ok"}`. Confirmed live.
2. **Prior ASTRA-side HAROLD code targets the wrong API shape**
   throughout — it speaks WRENCH's `/api/tools/{slug}/runs` envelope,
   not V2's native REST. ~660 lines across 7 files. **Recommend
   Path A: delete and rebuild fresh against V2.** Salvage value is
   low; rewrite cost is small; the migration 0032 stays.
3. **Migration 0032** (`systems.system_code_2letter`) is present at
   alembic head. Keep it — useful for future SYSTEM-level WPN context.
4. **`catalog_parts`** has neither `internal_part_number` nor
   `wpn_pending_sync` yet. Phase 1 lands them in migration 0033.
   `catalog_wpn_fallback_sequences` table also doesn't exist yet.
5. **`HAROLD_BASE_URL` default is `:8030`** in `backend/app/config.py`
   — points at the WRENCH api, not V2 on `:8031`. Phase 2 must flip
   this. Three HAROLD settings exist (enabled flag, base URL,
   timeout); all three are kept but the URL changes.
6. **`/api/v1/catalog/designators`** filters on
   `catalog_parts.part_number` (manufacturer MPN) — wrong column.
   Phase 3 changes it to `internal_part_number`. Confirmed visually
   in `backend/app/routers/catalog.py:1638`.
7. **The McMaster part** (`catalog_parts.id=1`, MPN `92196A196`) is
   the smoke target. Current state: `part_class=fastener_screw`,
   `part_subtype=socket_head_cap_screw` (lexicon fix landed at
   commit `65e4cb3`), `internal_part_number` is null (column doesn't
   exist yet).
8. **All four prior ASTRA fixes confirmed shipped**: lexicon
   broadening, `formatApiError` helper, STEP upload Content-Type,
   CORS + CSP for LAN. None blocking.

If point 2 (Path A) is right, Phase 1 starts with `git rm` on the
prior `backend/app/services/harold/`, `routers/harold.py`,
`schemas/harold.py`, plus the frontend's `harold-api.ts` /
`harold-types.ts`. If you'd rather salvage (Path B), say so before
Phase 1 — the rewrite would be smaller but messier.

---

## 1. V2 reachability

```
$ docker compose exec -T backend python -c \
  "import urllib.request; r=urllib.request.urlopen( \
   'http://host.docker.internal:8031/health', timeout=3); \
   print('health:', r.status, r.read().decode())"
health: 200 {"status":"healthy","version":"2.0.0","db":"ok"}
```

`host.docker.internal:8031` resolves cleanly from inside the
backend container; Windows Docker Desktop's host-gateway DNS works
as expected.

## 2. V2 surface captured

Saved to `docs/HAROLD_V2_OPENAPI.json` (19.6 KB), captured live from
`GET http://localhost:8031/openapi.json`. Paths the integration will
use:

| Method | Path | Phase that calls it |
|---|---|---|
| GET  | `/health`                             | Phase 2 (HaroldClient.heartbeat) |
| GET  | `/api/v1/system-codes`                | Phase 3 (`/harold/system-codes` proxy, optional) |
| POST | `/api/v1/wpn/validate`                | Phase 3 (`/harold/validate` proxy + filename validator) |
| POST | `/api/v1/wpn/validate-bulk`           | reserved — no Phase 1-6 caller |
| GET  | `/api/v1/wpn/suggest?system_code=...` | Phase 3 (suggest_wpn_for_part) |
| POST | `/api/v1/wpn/issue`                   | Phase 3 (issue_wpn_for_catalog_part, auto-allocate branch) |
| POST | `/api/v1/wpn/issue-specific`          | Phase 3 (issue_wpn_for_catalog_part, caller-supplied branch); Phase 3 reconcile |
| PATCH | `/api/v1/wpn/{wpn}`                  | reserved — no Phase 1-6 caller |
| GET  | `/api/v1/ledger/{wpn}`                | reserved — useful for the manual reconcile path |

Also exposed by V2 but not used in this integration: `/wpn/{wpn}`
and `/` (browse UI), `/api/v1/ledger`, `/api/v1/ledger/export`,
`/api/v1/wpn/{wpn}/retire`, `/supersede`, the `/api/tools/*` V1
compat surface.

## 3. Existing migration + DB state

```
alembic_version → 0032
\d systems
  system_code_2letter | character varying(2)  | …
  "ix_systems_code_2letter" btree (system_code_2letter)
\d catalog_parts
  internal_part_number    →  NOT PRESENT
  wpn_pending_sync        →  NOT PRESENT
catalog_wpn_fallback_sequences  →  TABLE DOES NOT EXIST
```

Migration 0032 (`0032_harold_seam.py`, shipped by the prior
HAROLD-001 session) lands `systems.system_code_2letter`. That column
is a SYSARCH-level annotation — it lets a project's `systems` row
reference a HAROLD 2-letter code (e.g. "Avionics" system → AV). Not
load-bearing for the integration directly, but harmless and useful
later. **Keep.**

Phase 1's new migration 0033 adds:
- `catalog_parts.internal_part_number VARCHAR(32)` + partial unique index
- `catalog_parts.wpn_pending_sync BOOLEAN NOT NULL DEFAULT FALSE` + filtered index
- `catalog_wpn_fallback_sequences` table + 21 seeded codes

## 4. McMaster part state

```
catalog_parts:
  id           | 1
  part_number  | 92196A196
  name         | 92196A196_18-8 Stainless Steel Socket Head Screw
  part_class   | fastener_screw
  part_subtype | socket_head_cap_screw
```

The lexicon broadening (commit `65e4cb3`) landed `socket head screw`
on the existing `socket_head_cap_screw` entry plus four plain-fallback
tokens (`screw`, `bolt`, `nut`, `washer`). This row was reclassified
in-place from `mechanical_other` to `fastener_screw` at the same
commit.

For the Phase 5 smoke this part is the natural fixture: it's already
in the catalog as a fastener, so AD-6's class→system mapping routes
it to `FH` (Fastener Hardware). Phase 5 should NOT backfill its
`internal_part_number` automatically (gotcha #9 in the prompt) —
Mason decides whether to retroactively assign WPNs.

## 5. Prior HAROLD work in ASTRA — file-by-file audit

Every file targets the V1 WRENCH-plugin shape from the speculative
HAROLD-INTEGRATION-001 era. Bytes (committed at `33f4f9b`,
`03895f7`):

| File | Lines | Targets | Salvage? |
|---|---:|---|---|
| `backend/app/services/harold/__init__.py`        |  34 | exports | rewrite |
| `backend/app/services/harold/errors.py`          |  15 | `HaroldUnavailableError`, `HaroldInvalidResponseError` | **keep** (extend) |
| `backend/app/services/harold/client.py`          | 150 | WRENCH `POST /api/tools/{slug}/runs` envelope; hardcoded slugs for `_wardstone-harold-data` and `_wardstone-harold-search` | **rewrite** |
| `backend/app/services/harold/service.py`         | 145 | `heartbeat`, `list_system_codes` (via WRENCH data tool), `suggest_wpn_from_text` (NL search) | **rewrite** |
| `backend/app/routers/harold.py`                  | 138 | `/heartbeat`, `/system-codes`, `/suggest-wpn` (NL-based) | **rewrite** |
| `backend/app/schemas/harold.py`                  |  83 | V1 search-output shape; `HaroldUnavailable` discriminated-union pattern is reusable | **rewrite** (keep pattern) |
| `frontend/src/lib/harold-api.ts`                 |  31 | three calls to wrong endpoints | **rewrite** |
| `frontend/src/lib/harold-types.ts`               |  67 | `WPN_PATTERN = /^WS-[A-Z]{2}-P\d{4}-[A-Z]$/` (V1 4-digit, full A-Z rev) — **wrong on both axes** | **rewrite** |
| **TOTAL** | **663** | | |

### What's specifically wrong

1. **Client envelope.** `client._post_run(slug, inputs)` POSTs
   `{"inputs": inputs}` to `/api/tools/{slug}/runs` and expects a V1
   run envelope back (`{runId, slug, inputs, output, success, ...}`).
   V2 exposes that shape only on its **compat surface**
   (`/api/tools/*`), which mirrors but doesn't match the native
   `/api/v1/*` REST endpoints we want to use. Talking to the compat
   surface would work but is the long way around.
2. **`suggest_wpn_from_text` model is wrong.** It treats HAROLD's
   "search" as an allocator ("give me an NL-described WPN") whereas
   the integration needs a per-system allocator
   (`GET /api/v1/wpn/suggest?system_code=FH` → returns
   `WS-FH-P000001-A` next available). The NL search even
   exists in V2's compat surface but returns `success=false`
   because Ollama isn't bundled.
3. **`/api/v1/harold/suggest-wpn`** signature takes free-text
   `query`, not `part_class`. The new design takes a class → maps to
   a system code → asks HAROLD for the next available WPN.
4. **Missing endpoints.** No `/validate`, no `/validate-filename`,
   no `/parts/{id}/reconcile`. All three are needed.
5. **`harold-types.ts` WPN regex** is V1's 4-digit form
   (`\d{4}`) with full `[A-Z]` rev (includes the ASME-forbidden
   `I/O/Q/S/X/Z`). V2's regex is `\d{6}` with the 20-letter ASME
   set. Lock #12 in the new prompt is explicit:
   `^WS-[A-Z]{2}-P[0-9]{6}-[ABCDEFGHJKLMNPRTUVWY]$`.
6. **`HAROLD_BASE_URL` defaults to `:8030`** in `config.py:93`.
   That's WRENCH's port; V2 lives at `:8031`. Phase 2 must flip the
   default.

### What's salvageable

- **`errors.py`** — `HaroldUnavailableError` and
  `HaroldInvalidResponseError` are reusable. Phase 2 extends with
  `HaroldDuplicateError` and `HaroldValidationError`.
- **The discriminated-union pattern** in `schemas/harold.py`
  (`HaroldUnavailable` vs `*Available` with `harold_available: bool`
  discriminator) survives the rewrite — it's the right shape for
  an optional dependency where the frontend wants
  always-200-with-structured-payload semantics.
- **Logging style** + **httpx exception-specificity** (catch
  `TimeoutException`, `ConnectError`, `HTTPError` separately) is
  carry-over-able verbatim into the new client.

### Reconciliation path recommendation

**Path A — delete and rebuild fresh against V2.**

| | Path A (recommend) | Path B (salvage) | Path C (parallel clients) |
|---|---|---|---|
| Cleanliness | High | Mid (drift risk) | Low (two clients) |
| Code volume change | -663 / +900 | -200 / +700 | -0 / +900 |
| Mental load (Phase 2 author) | Low | High | High |
| Drift risk | None | Real | Significant |
| Reviewer load (Mason) | Smaller diffs | Bigger, harder-to-read diffs | Hardest to review |

Path A wins on every axis. The prior code was speculative and never
exercised end-to-end (the previous Phase 0 acknowledged this); there
are no callers depending on its existing surface; the rewrite is a
mechanical port of patterns into the new endpoint shape. Phase 2's
new files mirror the prior file layout 1:1, just with V2-correct
contents.

## 6. Four prior ASTRA fixes — confirmed shipped

| Fix | Commit | Verified |
|---|---|---|
| Lexicon broadening (`screw`/`bolt`/`nut`/`washer` fallbacks; "Socket Head Screw" → `fastener_screw`/`socket_head_cap_screw`) | `65e4cb3` | grep shows the four fallback rows in `backend/catalog_seed/part_type_lexicon.json`; McMaster row 1 is correctly classified. |
| `formatApiError` helper for safe Pydantic-array error rendering | `acada97` | `frontend/src/lib/errors.ts` exists; `export function formatApiError` declared. |
| STEP upload `Content-Type: multipart/form-data` override (axios was inheriting the JSON default) | `acada97` | `frontend/src/lib/catalog-api.ts:uploadStep` passes the header explicitly. |
| CORS + CSP for LAN deployment | inherited (CORSMiddleware in `main.py`; CSP middleware in `app/middleware/security_headers.py` includes `connect-src 'self' ws: wss: http://localhost:*` in dev mode) | grep confirms middleware present; `BACKEND_CORS_ORIGINS` env var lists LAN hosts. |

None block the integration.

## 7. Revised decision register (AD-1 … AD-12)

Mason's locked register from the prompt's "Decisions — locked"
section is consistent with reality post-V2. No adjustments needed.
Three settings live in `backend/app/config.py` already; Phase 2
updates `HAROLD_BASE_URL` from `:8030` to `:8031` to match AD-2.

| # | Lock | Status |
|---|---|---|
| AD-1  | `HAROLD_INTEGRATION_ENABLED` default `false` | ✓ already `False` in config.py |
| AD-2  | `host.docker.internal:8031` | ⚠ Phase 2 must update — current default is `:8030` |
| AD-3  | 3-second timeout | ✓ already 3.0 in config.py |
| AD-4  | Server-side calls only | ✓ enforced by router structure |
| AD-5  | ASTRA = system of record; HAROLD = ledger | ✓ matches V2 design |
| AD-6  | Class → system: fasteners FH, mechanical MH, electrical EH, sealing SH | ✓ — implementation in Phase 2 `class_to_system.py` |
| AD-7  | Mapping is a Python dict constant | ✓ |
| AD-8  | Add `internal_part_number`, `wpn_pending_sync`, `catalog_wpn_fallback_sequences` | ✓ Phase 1 migration 0033 |
| AD-9  | `/catalog/designators` → filter on `internal_part_number` | ✓ Phase 3 |
| AD-10 | `/catalog/designators` unauthenticated for v1 | ✓ matches today's posture |
| AD-11 | Three approval branches | ✓ Phase 3 |
| AD-12 | Frontend WPN regex `^WS-[A-Z]{2}-P[0-9]{6}-[ABCDEFGHJKLMNPRTUVWY]$` | ⚠ current frontend regex is V1; Phase 4 updates |

## 8. Revised phase plan

The prompt's six phases are correct against current state. Below is
the order with reconciled file lists.

### Phase 1 — migration

```
backend/alembic/versions/0033_harold_wpn_columns.py  (NEW)
backend/app/models/catalog.py                        (extend CatalogPart)
```

Adds `internal_part_number`, `wpn_pending_sync`,
`catalog_wpn_fallback_sequences` (21 seeded). Verify
`alembic_version → 0033`, `\d catalog_parts` shows the two new
columns, fallback sequences table populated.

Commit: `phase-1(harold-int): WPN columns + fallback sequences migration`.

### Phase 2 — V2 client + service + filename validator + fallback (Path A)

Delete (one commit step):
```
backend/app/services/harold/__init__.py
backend/app/services/harold/client.py
backend/app/services/harold/service.py
backend/app/routers/harold.py
backend/app/schemas/harold.py
frontend/src/lib/harold-api.ts
frontend/src/lib/harold-types.ts
```

`errors.py` is the only file kept verbatim from the prior tree
(extended with two new exception classes).

Write fresh:
```
backend/app/services/harold/__init__.py            (re-exports)
backend/app/services/harold/errors.py              (extend: add HaroldDuplicate / HaroldValidation)
backend/app/services/harold/client.py              (HaroldClient with V2 REST methods)
backend/app/services/harold/class_to_system.py     (AD-6 mapping dict)
backend/app/services/harold/filename_validator.py  (filetype-agnostic seam)
backend/app/services/harold/fallback.py            (local allocator over catalog_wpn_fallback_sequences)
backend/app/services/harold/service.py             (high-level: suggest_wpn_for_part / validate_filename_wpn / issue_wpn_for_catalog_part / reconcile_pending_sync)
backend/app/schemas/harold.py                      (V2-correct shapes; keep the *Available / Unavailable union pattern)
backend/app/config.py                              (HAROLD_BASE_URL default → :8031)
```

Tests (respx-mocked HAROLD V2):
```
backend/tests/test_harold_client.py
backend/tests/test_class_to_system.py
backend/tests/test_filename_validator.py
backend/tests/test_fallback_allocator.py
backend/tests/test_harold_service.py
```

Verify pytest green.

Commit: `phase-2(harold-int): HAROLD V2 client + service + fallback + filename validator`.

### Phase 3 — ASTRA endpoints

```
backend/app/routers/catalog.py     (fix /designators column; wire upload + approval to HAROLD)
backend/app/routers/harold.py      (NEW: /heartbeat, /system-codes proxy, /suggest, /validate, /validate-filename, /parts/{id}/reconcile)
backend/app/services/audit_service (if not already there: catalog.part.wpn_assigned, .wpn_reconciled events)
```

Test:
```
backend/tests/test_harold_endpoints.py     (each /harold/* endpoint, HAROLD-up vs down)
backend/tests/test_upload_approval_flow.py (three approval branches, audit emission, designators filter)
```

Commit: `phase-3(harold-int): /api/v1/harold/* + designators fix + upload-approval wiring`.

### Phase 4 — frontend

```
frontend/src/lib/harold-types.ts   (V2 shapes; WPN_PATTERN = ^WS-[A-Z]{2}-P[0-9]{6}-[ABCDEFGHJKLMNPRTUVWY]$)
frontend/src/lib/harold-api.ts     (heartbeat / suggest / validate / reconcile)
frontend/src/lib/catalog-types.ts  (extend CatalogPart with internal_part_number, wpn_pending_sync)
frontend/src/app/catalog/pending-imports/[id]/page.tsx  (WPN section above extracted-data form)
frontend/src/app/catalog/page.tsx                       (promote internal WPN to primary identifier)
frontend/src/app/catalog/parts/[id]/page.tsx            ("Sync with HAROLD" button when wpn_pending_sync)
```

Verify `npx tsc --noEmit` clean; `npm run build` green.

Commit: `phase-4(harold-int): frontend WPN section + catalog list + reconcile UI`.

### Phase 5 — end-to-end smoke + reconciliation

Flip `HAROLD_INTEGRATION_ENABLED=true`, restart backend, run the
prompt's 13-step smoke matrix against the McMaster fixture. Document
each step's result.

Commit: `phase-5(harold-int): end-to-end smoke validated` (state-only).

### Phase 6 — final tests + completion notes

```
docs/PHASE_HAROLD_INTEGRATION_NOTES.md  (NEW)
```

Final `pytest -v`, `tsc --noEmit`, `npm run build` all green. Notes
capture per-phase commits, smoke results, open follow-ups.

Commit: `phase-6(harold-int): tests + completion notes`.

---

## 9. Risks / gotchas surfaced during audit

1. **Pre-existing `docs/HAROLD_INTEGRATION_DESIGN.md`** is the Phase 0
   report from the older HAROLD-INTEGRATION-001 prompt (the one whose
   architecture we're now replacing). This commit overwrites that
   file with the new V2-reconciled content. The pre-V2 file's value
   was largely captured in the prompt's "Pre-flight read" section.
2. **`HAROLD_BASE_URL` change is a config edit that affects all
   developers.** Phase 2 updates the default; anyone with a
   `.env` overriding to `:8030` needs to drop the override. Document
   in the Phase 2 commit message.
3. **The McMaster part (id=1)** stays unmodified through Phase 1;
   `internal_part_number` defaults NULL on the new column. Phase 5's
   smoke uploads a SECOND McMaster STEP to exercise the full flow,
   leaving the original row as a pre-integration artifact. Don't
   backfill (per prompt gotcha #9).
4. **Fallback allocator race.** Two concurrent uploads during a
   HAROLD outage both reserve fallback WPNs. The `SELECT FOR UPDATE`
   in `fallback.allocate_fallback_wpn` (Phase 2) prevents
   same-WPN collisions. Reconcile-time collisions with HAROLD's own
   issued numbers are handled in `service.reconcile_pending_sync`:
   first try `issue_specific` (use the fallback WPN as-is); on 409,
   fall through to `issue` (allocate a fresh HAROLD WPN, update
   `internal_part_number`, audit-emit a `wpn_changed_during_reconcile`
   event).
5. **Audit event proliferation.** Prompt §Common gotcha #11 lists
   four event names: `catalog.part.wpn_assigned`,
   `catalog.part.wpn_reconciled`, `catalog.part.wpn_pending_sync`,
   `harold.unavailable`. Phase 3 emits them all. Existing
   `app.services.audit_service.record_event` is reused (no new
   service code).
6. **`/api/v1/catalog/designators` is currently unauthenticated** and
   `CatalogDesignatorsResponse` schema returns
   `{designators: list[str], total, system_filter}` — a flat list of
   manufacturer MPNs. Phase 3 changes both the shape and the column:
   new response is
   `{designators: [{wpn, part_id, part_class, system_code, created_at}, ...], total, filter}`.
   This is a **breaking change** for any caller that consumes the
   current shape. Confirmed via grep that **no caller exists yet**
   (the endpoint was added speculatively in commit `03895f7` and the
   only consumer was meant to be HAROLD, which doesn't poll ASTRA).
   Safe to break.
7. **Migration 0033 numbering.** Current head is 0032. Phase 1's
   migration goes 0033. If any other phase is in flight that
   intends migration 0033 also, surface and renumber.
8. **`reconcile_pending_sync` audit on partial failure.** Prompt
   §Common gotcha #7: wrap the reconcile in a transaction so a
   partial success (HAROLD accepts `issue_specific`, audit emit
   fails) rolls back. Phase 2's service function must take the
   transaction boundary explicitly.

## 10. Questions for Mason

None blocking — all twelve AD-* decisions are clear and self-consistent
with the V2 surface captured in `docs/HAROLD_V2_OPENAPI.json`. A few
soft prompts:

1. **Path A vs B vs C** for the prior HAROLD-code reconciliation:
   I'm recommending A (delete, rebuild). Sign off or override.
2. **Phase 5 smoke fixture:** the prompt suggests "rename the
   fixture or grab another McMaster bolt". Have a candidate file
   ready, or should I pick another McMaster part number for the
   smoke? Picking one is fine if you don't have a preference.
3. **`/api/v1/catalog/designators` breaking change** (point 9.6
   above). Implicit-OK per prompt scope. Flag it loudly here in
   case there's a non-obvious consumer.
4. **`docs/HAROLD_INTEGRATION_DESIGN.md` was previously written by
   the HAROLD-INTEGRATION-001 Phase 0** — this report overwrites it.
   If you wanted to keep the original for diff purposes, say so
   before this Phase 0 commit and I'll save it to
   `docs/HAROLD_INTEGRATION_DESIGN_V1.md` first.

## 11. Files saved during Phase 0

```
docs/HAROLD_INTEGRATION_DESIGN.md   (this file — overwrites prior)
docs/HAROLD_V2_OPENAPI.json         (NEW — 19.6 KB)
```

No code touched. No migration created. No HAROLD V2 modifications.
ASTRA frontend and backend unchanged from `HEAD`.

## 12. What I did NOT do (per the stop instruction)

- No Phase 1 migration written.
- No deletion of prior HAROLD code.
- No HAROLD V2 modifications.
- No code edits to `backend/`, `frontend/`, or `C:\Tools\harold`.
- No flip of `HAROLD_INTEGRATION_ENABLED`.

**Waiting for your go-ahead before proceeding to Phase 1.**
