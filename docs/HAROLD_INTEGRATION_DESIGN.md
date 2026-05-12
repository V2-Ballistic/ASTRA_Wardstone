# HAROLD ↔ ASTRA Integration — Phase 0 Discovery Report

Author: Phase 0 agent (HAROLD-INTEGRATION-001).
Date: 2026-05-12.
Status: **Stops here for Mason's review.** No Phase 1 work has started.

This document supersedes `docs/HAROLD_INVESTIGATION.md` (Phase 0 of the
older HAROLD-001 prompt, kept on disk for diff). The TL;DR at the top is
the part most likely to change your mind about the next phase plan.

---

## TL;DR — what changes vs the prompt's assumptions

1. **HAROLD is a WRENCH plugin, not a standalone service.** Endpoints live
   under WRENCH's framework at `POST /api/tools/{slug}/runs`. HAROLD itself
   registers six `@register`-decorated tool functions. There is no
   `/validate`, no `/suggest-wpn`, no `/data` at the top level — those slugs
   are all accessed via the runs API.
2. **HAROLD does not issue WPNs and does not track issuance.** It validates
   format against the standard (`WS-<SYS>-P<NNNN>-<REV>` etc.) and offers
   an NL-driven *pattern transformer* (`_wardstone-harold-search`) — but
   there is no sequence allocator, no datastore of issued numbers, no
   "next available" endpoint. So the prompt's AD-5 ("HAROLD is the
   authoritative WPN issuer") is impossible as stated. We pivot to
   **Phase 5 Option C**: HAROLD = spec/validator only, ASTRA = issuer.
3. **HAROLD's "class code" is a SYSTEM code, not a part_class.** Valid
   codes: `VH AE AS AV BT CC CG EE FC GN GS OR PR ST TH TS WH` (17
   2-letter codes from `wardstone_harold.data.SYSTEMS`). The prompt's
   running example `WS-FS-P0042-A` is invalid on two counts: `FS` is
   not a real system code, and sequence `0042` is below the part range
   (1000–9999). McMaster fasteners map to `ST` (Structures — explicitly
   covers "Primary/secondary structure, brackets, fasteners").
4. **A previous session already shipped phase-0/1/2/3 of the older
   HAROLD-001 prompt** (commits `3054f96`, `4eee030`, `33f4f9b`,
   `03895f7`). We have a partial HAROLD client, service, router, and
   the `/catalog/designators` endpoint. They need extension, not
   rewrite. The migration that landed (`0032_harold_seam.py`) adds
   `systems.system_code_2letter`, **NOT** the
   `catalog_parts.internal_part_number` column the new prompt wants.
   Phase 1 of the new prompt still applies.
5. **The existing `/catalog/designators` filters on the manufacturer
   `part_number` column**, which for the one McMaster row currently
   reads `92196A196`. That's the wrong column to expose to HAROLD for
   collision avoidance once we have internal WPNs. Phase 3 needs to
   pivot the filter to `internal_part_number` once Phase 1 lands.
6. **AD-1 default is currently `False` in code.** The new prompt wants
   `true`. We need your call before flipping it.

If any of points 1–4 contradict what you thought you were getting, please
say so before we proceed — they shape the whole rest of the plan.

---

## 1. HAROLD's real surface

### 1.1 Runtime

- **Plugin** at `C:\Tools\harold\wardstone-harold\` (`pyproject.toml`,
  `src/wardstone_harold/`). Entry point:
  `wardstone_harold = "wardstone_harold.wrench_integration"` registered
  under `[project.entry-points."wrench.tools"]`.
- **Host** is the WRENCH api container at `C:\opt\wrench\deploy\docker-compose.yml`.
  WRENCH is a FastAPI app that auto-discovers plugins via entry points
  and exposes them under `/api/tools/{slug}/runs`.
- **Running copy** is at `C:\opt\wrench\tools-dev\wardstone-harold\` (a
  robocopy `/MIR` destination — never edited directly). Sync is
  one-shot via `pwsh C:\Tools\harold\deploy.ps1`, which restarts the
  api/web containers.
- **Diff main vs wrench copy:** identical except for build artifacts
  (`.pytest_cache`, `wardstone_harold.egg-info`). Confirmed via
  `diff -r --brief`.

### 1.2 WRENCH HTTP surface (port 8030)

Captured from `GET http://localhost:8030/openapi.json` and saved to
`docs/harold_openapi.json` (7.8 KB).

| Method | Path | Use |
|---|---|---|
| GET  | `/health`                       | Liveness. Returns `{status, tools, sdk_version}`. |
| GET  | `/api/tools`                    | List all registered tools across plugins. |
| GET  | `/api/tools/_status`            | Per-tool status. |
| GET  | `/api/tools/{slug}`             | Tool metadata + input/output JSON schema. |
| POST | `/api/tools/{slug}/runs`        | Invoke a tool. Body: `{"inputs": {...}}`. |
| GET  | `/api/runs`                     | List recent runs. |
| GET  | `/api/runs/{run_id}`            | One run's record. |
| GET  | `/api/recents`                  | UI recent-activity feed. |

The run envelope: `{runId, slug, inputs, output, success, elapsed_ms, error, created_at}`.

### 1.3 HAROLD's six registered tools

From `wrench_integration.py`:

| Slug                              | Visibility | Timeout | Purpose |
|-----------------------------------|-----------|---------|--------|
| `wardstone-harold`                | public  | 10 s | Catalog shell. UI launches `/wardstone-harold`. |
| `_wardstone-harold-data`          | hidden  | 10 s | Returns one of 13 sections of the standard (`SYSTEMS`, `PROJECTS`, `ARTIFACT_TYPES`, …). |
| `_wardstone-harold-search`        | hidden  | 30 s | NL → pattern transformer. Calls Ollama (`run_search`). |
| `_wardstone-harold-validate`      | hidden  | 10 s | Validate one name against the standard. Pure regex + tables, no LLM. |
| `_wardstone-harold-bulk-validate` | hidden  | 20 s | Up to 200 names per call. |
| `_wardstone-harold-add-project`   | hidden  | 10 s | Add a runtime project code (3-letter). |
| `_wardstone-harold-delete-project`| hidden  | 10 s | Remove a user-added project code. |

**Validate output** (what ASTRA's `validate_wpn` would consume):

```json
{
  "name": "WS-ST-P1014-A",
  "is_valid": true,
  "pattern_id": "cad_part",
  "pattern_label": "CAD part",
  "pattern": "WS-<SYS>-P<NNNN>-<REV>",
  "issues": [],
  "parsed_fields": {"SYS": "ST", "NNNN": "1014", "REV": "A"},
  "canonical_form": "WS-ST-P1014-A"
}
```

When invalid, `issues` contains `{severity, field, message, suggestion?}`
entries. Tested live:

```
POST /api/tools/_wardstone-harold-validate/runs {"inputs":{"name":"WS-ST-P0042-A"}}
→ is_valid=false, issues=[{severity:error, field:sequence,
   message:"Part sequence 0042 is out of range; expected 1000-9999
   (detail 1000-8999; library 9000-9799; coupon 9800-9899;
   hot-fix 9900-9999)."}]
```

### 1.4 The standard (canonical WPN patterns)

From `wardstone_harold/data.py:ARTIFACT_TYPES` and `validate.py` regexes:

| Pattern id          | Format                                | Example                  | Sequence range |
|---------------------|---------------------------------------|--------------------------|----------------|
| `cad_part`          | `WS-<SYS>-P<NNNN>-<REV>`              | `WS-ST-P1014-A`          | 1000–9999 (subranges: 1000-8999 detail, 9000-9799 library, 9800-9899 coupon, 9900-9999 hot-fix) |
| `cad_assembly`      | `WS-<SYS>-A<NNNN>-<REV>`              | `WS-AV-A0150-B`          | 0100–0999 |
| `vehicle_assembly`  | `WS-<PRJ>-VH-A<NNNN>-<REV>`           | `WS-DRT-VH-A0001-A`      | 0001–0099 |
| `cad_drawing`       | `WS-<SYS>-D<NNNN>-<REV>`              | `WS-AV-D0107-B`          | matches parent |
| `vehicle_drawing`   | `WS-<PRJ>-VH-D<NNNN>-<REV>`           | `WS-DRT-VH-D0001-A`      | matches parent |
| `cfd_run`           | `<vehCN>-<CFG>-<METHOD>-<COND>-G<n>-r<n>` | `DRT-B1M0-Crucif-FUN3D-M2.5-A05.0-B00.0-H010km-G2-r0` | — |
| `wt_test`           | `WT-<vehCN>-<facility>-T<n>-R<n>-P<n>` | `WT-DRT-B1M0-AEDC9-T217-R045-P012` | — |
| `fea_model`         | `<parentId>-FEA-<disc>-<seq>-<rev>`   | `WS-ST-P1014-FEA-STR-001-A` | — |
| `motor`             | `WS-MOT-<CLASS>-<SUB>-<seq>-<rev>`    | `WS-MOT-CG-RCS-002-A`    | — |
| `document`          | `WS-<PRJ>-DOC-<TYPE>-<seq>-<rev>`     | `WS-DRT-DOC-TRP-0001-A`  | — |
| `release_tag`       | `<vehCN>-<cfg>-<art>-vX.Y.Z`          | `DRT-B1M0-Crucif-aero-v0.4.1` | — |

Sub-cases for `load_case`, `hil_config`, `test_campaign`, `test_point`,
`log_file`, `harness` also exist but are out of scope for STEP-file
WPN assignment.

Detail parts and sub-assemblies have **no project segment** (the 2026
restructure). Vehicle-level artifacts (assemblies, drawings) keep a
3-letter project code (`DRT`, `CTL`, …).

REV letters (ASME Y14.35): `A B C D E F G H J K L M N P R T U V W Y`
— skips `I O Q S X Z`.

System codes (17, 2 letters): `VH AE AS AV BT CC CG EE FC GN GS OR PR ST TH TS WH`.

Project codes are dynamic (built-in + `add_project`-runtime). Built-in
ones include `DRT`, `CTL`, more in `data.PROJECTS`.

### 1.5 HAROLD's data model

- **Static reference data** only — `SYSTEMS`, `PROJECTS`, `ARTICLE_CLASSES`,
  `CAD_CLASSES`, `REV_LETTERS`, `ARTIFACT_TYPES`, `DISCIPLINES`,
  `REFERENCE_FRAMES`, `SYMBOLS`, `ABBREVIATIONS`, `RESERVED_PREFIXES`,
  `SUBSCRIPTS`, `VEHICLE_PROJECT_RULES`. All hard-coded in
  `wardstone_harold/data.py`.
- **One runtime mutation surface**: `add_project` / `delete_project`
  write to a JSON extras store (see `extras.py`). This is the only state
  HAROLD persists. No WPN issuance is tracked.
- **No SQL, no SQLite, no in-memory issued-WPN map.** Confirmed by
  reading every module (`__init__.py`, `data.py`, `extras.py`,
  `frames.py`, `search.py`, `validate.py`, `wrench_integration.py`).

### 1.6 HAROLD's existing collision-avoidance

**None.** `validate_name` does not consult anything to know whether a
WPN is already in use. The `_wardstone-harold-search` tool transforms
NL → pattern (e.g. "drawing for WS-AV-A0107-B" → "WS-AV-D0107-B"), it
does not allocate sequences.

This is the central design pivot: ASTRA must own the issuance counter.
HAROLD answers "is this name valid?" only.

### 1.7 Reachability from inside ASTRA's backend container

Confirmed via:
```
docker compose exec backend python -c \
  "import urllib.request; r=urllib.request.urlopen('http://host.docker.internal:8030/health', timeout=5); print(r.status, r.read().decode())"
→ 200 {"status":"ok","tools":64,"sdk_version":"1.0.0"}
```

`host.docker.internal:8030` resolves cleanly. WRENCH listens on
`0.0.0.0:8030` per the wrench `docker-compose.yml` port mapping; the
ASTRA backend container sees it via Docker Desktop's host-gateway DNS.

### 1.8 Main vs wrench copy

| Path | Role | Edited directly? |
|---|---|---|
| `C:\Tools\harold\wardstone-harold\` | Source of truth. Plugin source. | yes |
| `C:\opt\wrench\tools-dev\wardstone-harold\` | Runtime copy (robocopy /MIR destination). | **no** — wiped on each `deploy.ps1` |
| `C:\Tools\harold\web-workspace\apps\web\src\workspaces\wardstone-harold\` | Workspace stub (Next.js) source. | yes |
| `C:\Tools\harold\web-workspace\apps\web\src\app\(fullscreen)\wardstone-harold\` | Full-page app source. | yes |

Deploy command (sync + rebuild + smoke-test): `pwsh C:\Tools\harold\deploy.ps1`.

---

## 2. What's already shipped on the ASTRA side

From the older HAROLD-001 prompt's phase-0..3 commits:

- **Migration `0032_harold_seam.py`** — adds `systems.system_code_2letter VARCHAR(2)`.
  This is on the **`systems`** (SYSARCH) table, NOT on `catalog_parts`.
  It lets a project's system row reference a HAROLD code (e.g. project
  system "Avionics" → `AV`). The new prompt's Phase 1 is still needed
  to add `catalog_parts.internal_part_number` + `wpn_pending_sync`.
- **`backend/app/config.py`** — three settings:
  - `HAROLD_INTEGRATION_ENABLED: bool = False` (new prompt wants `True`).
  - `HAROLD_BASE_URL: str = "http://host.docker.internal:8030"` ✓.
  - `HAROLD_TIMEOUT_SECONDS: float = 3.0` ✓.
- **`backend/app/services/harold/`** — `client.py`, `errors.py`,
  `service.py`. Wraps `httpx.AsyncClient`, opens per-call (gotcha #2),
  catches only specific httpx exceptions (gotcha #9). Errors:
  `HaroldUnavailableError`, `HaroldInvalidResponseError`.
  Service functions today: `heartbeat()`, `list_system_codes()`,
  `suggest_wpn_from_text(query, allow_llm_refine)`.
  **Missing for the new prompt**: `validate_wpn`, `notify_wpn_issued`,
  `fallback.allocate_wpn`, `filename_validator.*`.
- **`backend/app/routers/harold.py`** — `/api/v1/harold/heartbeat`,
  `/system-codes`, `/suggest-wpn`. All under JWT auth.
  **Missing**: `/validate-wpn`, `/validate-filename`.
- **`backend/app/routers/catalog.py`** — `/api/v1/catalog/designators?system=AV&skip=0&limit=200`,
  unauthenticated (per AD-8). **Pivot needed**: filter currently runs
  against `catalog_parts.part_number` (the manufacturer MPN, e.g.
  `92196A196`), which is wrong for HAROLD collision-avoidance. After
  Phase 1 adds `internal_part_number`, the filter should target that
  column instead.
- **`frontend/src/lib/harold-api.ts` + `harold-types.ts`** — typed
  client and types for the three existing endpoints.

The lexicon fix that shipped this morning (commit `65e4cb3`) is
independent and stays.

---

## 3. Revised decision register (AD-1 … AD-9 + new)

| # | Original | Revised against reality | Action |
|---|---|---|---|
| **AD-1** | Feature flag default `true`. | Currently `False` in code. | **Need Mason's call.** Recommendation: flip to `True` once Phase 4 frontend lands so a half-shipped backend doesn't render WPN UI against nothing. |
| **AD-2** | `host.docker.internal:8030`. | Confirmed reachable. | ✓ keep. |
| **AD-3** | 3 s timeout. | Currently 3 s. | ✓ keep. NB: `_wardstone-harold-search` has a 30 s server-side timeout; if we ever call it, we'll need a path-specific override. |
| **AD-4** | WPN = `WS-<XX>-P<NNNN>-<REV>`, XX is class code. | XX is a **2-letter SYSTEM code** (17 values). Sequence `NNNN` is 1000–9999 with subranges. REV from a 20-letter alphabet (ASME Y14.35). | **Update prompt's running example** from `WS-FS-P0042-A` to `WS-ST-P1014-A`. McMaster fasteners → `ST`. |
| **AD-5** | HAROLD is authoritative WPN issuer; ASTRA falls back. | HAROLD does NOT issue WPNs. It validates format only. | **Revised:** ASTRA owns issuance via `catalog_wpn_fallback_sequences` (which becomes the **primary** allocator, not the fallback — rename). HAROLD is consulted to validate the resulting WPN before commit. `wpn_pending_sync` flag still useful as a "HAROLD was unreachable at validate-time; we issued anyway" marker. |
| **AD-6** | `/catalog/designators` (no auth, LAN-only). | Exists. Filters on `part_number` (MPN); needs pivot to `internal_part_number` after Phase 1. | Update Phase 3 to switch the column once the new column exists. Keep `?system=AV` query name. |
| **AD-7** | All HAROLD calls server-side. | ✓ already structured this way. | keep. |
| **AD-8** | Filetype-agnostic filename validation, STEP first. | Sound. STEP filename → MPN-style or WPN-style detection lives in a new `filename_validator.py`. | keep. |
| **AD-9** | Migration adds `internal_part_number`, `wpn_pending_sync`, fallback sequence table. | Not yet in migration head (0032 added a different column). Phase 1 still needed. | keep — but consider naming the table `catalog_wpn_sequences` (primary allocator, per AD-5 revision) rather than `*_fallback_*`. |

### New decisions to discuss

| # | Proposed | Rationale |
|---|---|---|
| **AD-10** | Class-to-system mapping lives on ASTRA side as a static dict (initially): `{fastener_screw, fastener_bolt, nut, washer, bearing, bracket, spring, structural_member → ST; processor, sensor, compute_module → AV; …}`. | HAROLD has no `part_class` concept. We translate at upload time and embed the chosen system code in `proposed_wpn`. User can override. |
| **AD-11** | Sequence allocation strategy: per-system, monotonically increasing, with a `SELECT … FOR UPDATE` lock on `catalog_wpn_sequences[system_code]` inside a transaction. Initial start at `1000`. Skip ranges 9000+ for v1 (library/coupon/hotfix categories require manual flags). | Avoids concurrent-upload races. Library/coupon/hotfix is a follow-on. |
| **AD-12** | `notify_wpn_issued` is **a no-op** in v1. HAROLD does not store issued WPNs. Audit emit stays ASTRA-side. | Phase 5 "Option C" — smallest viable change. Reconsider if Mason wants HAROLD to grow a SQLite ledger so other tools can query it. |
| **AD-13** | The `extract_wpn_candidate(filename)` regex matches HAROLD's actual patterns (cad_part, cad_assembly, vehicle_assembly, vehicle_drawing, cad_drawing) — not a single-format regex. Calls HAROLD's `validate-name` for the final ruling. | HAROLD owns the rules; ASTRA's regex is just a pre-filter for "looks like a Wardstone name at all". |
| **AD-14** | HAROLD's `add_project` runtime mutation is **not used** from ASTRA. Project codes for vehicle artifacts come from HAROLD's static `PROJECTS` list. | Adding projects is an out-of-band admin action via HAROLD's UI. ASTRA doesn't need write access. |

---

## 4. Sequence diagram — upload → approve → WPN assignment

```
User           ASTRA frontend          ASTRA backend                      HAROLD
 │                  │                        │                                │
 │ pick STEP file   │                        │                                │
 │─────────────────▶│                        │                                │
 │                  │ POST /catalog/upload-step (multipart)                   │
 │                  │───────────────────────▶│                                │
 │                  │                        │ step_parser.parse_step_file()  │
 │                  │                        │  → parsed.part_class, name,    │
 │                  │                        │    mfr part_number             │
 │                  │                        │                                │
 │                  │                        │ filename_validator.extract_…   │
 │                  │                        │  → looks_like_wpn? class_hint? │
 │                  │                        │                                │
 │                  │                        │ map part_class → system_code   │
 │                  │                        │  (AD-10, ASTRA-side dict)      │
 │                  │                        │                                │
 │                  │                        │ wpn_sequences.peek(system)     │
 │                  │                        │  → next candidate WS-ST-P1014  │
 │                  │                        │                                │
 │                  │                        │ POST /api/tools/_wardstone-    │
 │                  │                        │   harold-validate/runs         │
 │                  │                        │   {name: "WS-ST-P1014-A"}      │
 │                  │                        │───────────────────────────────▶│
 │                  │                        │                                │ pure regex + tables
 │                  │                        │◀───────────────────────────────│ {is_valid, issues[]}
 │                  │                        │                                │
 │                  │                        │ pending_imports.create(        │
 │                  │                        │   extracted_data + proposed_wpn│
 │                  │                        │   + wpn_source="harold")       │
 │                  │                        │                                │
 │                  │◀────── 201 {pending_import_id}                         │
 │                  │                        │                                │
 │ review page      │ GET /pending-imports/{id}                              │
 │─────────────────▶│───────────────────────▶│                                │
 │                  │                        │                                │
 │                  │◀── extracted_data + proposed_wpn + warnings            │
 │                  │ render WPN section (green / amber / red)                │
 │                  │                        │                                │
 │ edit WPN?        │ POST /harold/validate-wpn {wpn} (debounced on blur)    │
 │                  │───────────────────────▶│ HAROLD validate run            │
 │                  │                        │───────────────────────────────▶│
 │                  │                        │◀───────────────────────────────│
 │                  │◀── valid / errors / dup hint                            │
 │                  │                        │                                │
 │ click approve    │ POST /pending-imports/{id}/approve                     │
 │─────────────────▶│───────────────────────▶│                                │
 │                  │                        │ final validate (idempotent)    │
 │                  │                        │───────────────────────────────▶│
 │                  │                        │◀───────────────────────────────│
 │                  │                        │                                │
 │                  │                        │ wpn_sequences.claim(sys, rev)  │
 │                  │                        │  → row-locked increment        │
 │                  │                        │                                │
 │                  │                        │ duplicate check on             │
 │                  │                        │  catalog_parts.internal_part_  │
 │                  │                        │  number (UNIQUE constraint)    │
 │                  │                        │                                │
 │                  │                        │ catalog_parts.insert(          │
 │                  │                        │   internal_part_number=wpn,    │
 │                  │                        │   wpn_pending_sync=False)      │
 │                  │                        │                                │
 │                  │                        │ audit catalog.part.wpn_assigned│
 │                  │                        │                                │
 │                  │◀── 201 {catalog_part}                                   │
 │                  │ navigate to /catalog/parts/{id}                         │
```

Degraded path (HAROLD unreachable):
- Upload: skip validate call, proposed WPN gets `wpn_source="local"`,
  `wpn_validation_notes=["HAROLD unavailable at upload — local format check only"]`.
- Approve: skip final validate call, set `wpn_pending_sync=True`.
  Manual "Sync with HAROLD" button on the part page re-validates later.

Concurrency: `wpn_sequences.claim()` opens a transaction and does
`SELECT next_index FROM catalog_wpn_sequences WHERE system_code=:sys
FOR UPDATE`, increments, commits inside the same tx as the
`catalog_parts.insert`. Two parallel uploads on the same system can't
race; one waits.

---

## 5. Blocking concerns / questions for Mason

These need an answer before Phase 1 starts:

1. **AD-1 default — `true` or stay `false`?** If `true`, the first
   deploy after Phase 1 enables the integration before Phase 4 frontend
   lands; the upload flow still works but with no WPN UI. If `false`,
   we ship Phase 1-3 dark and flip the switch at Phase 4.
2. **AD-5 pivot OK?** HAROLD really doesn't issue WPNs. Confirming this
   means: ASTRA is the source of truth for issued WPN numbers, the
   `wpn_sequences` table is the primary (not fallback) allocator, and
   HAROLD is consulted only to validate format. If you wanted HAROLD
   to grow a SQLite ledger of issued numbers (so other Wardstone tools
   could ask HAROLD "is `WS-ST-P1014-A` taken?"), that's a real
   feature add on the HAROLD side and we should plan it explicitly.
3. **AD-10 class→system mapping** — proposed initial dict:

   | ASTRA part_class | HAROLD system code |
   |---|---|
   | fastener_screw, fastener_bolt, nut, washer | ST |
   | bracket, bearing, spring, structural_member, housing, enclosure | ST |
   | seal_o_ring | ST |
   | processor, sensor, compute_module, interface_card, radio, antenna | AV |
   | power_supply, power_distribution | EE |
   | actuator, connector_only, harness | WH |
   | display | AV |
   | other / mechanical_other | ST |

   Object if any of these feel wrong. Defaults are easy to change in
   one file later; getting the initial dict right saves manual
   overrides at upload time.

4. **Sequence start point.** Initial `next_index=1000` per system?
   Or pick higher numbers per system to leave gaps for known-existing
   parts you may import later? (1014 in the example was inherited
   from HAROLD's own example value — it's not currently in ASTRA.)

5. **Migration numbering.** Current head is `0032_harold_seam.py`.
   New Phase 1 migration would be `0033_catalog_wpn.py`. OK?

6. **HAROLD-side changes — yes/no?** Phase 5 in the prompt asks for
   cross-repo work. Under AD-5/AD-12 (Option C), Phase 5 becomes a
   **no-op on HAROLD**: ASTRA does all the lifting, HAROLD only
   validates. We'd document the "no HAROLD-side change" decision in
   `C:\Tools\harold\docs\ASTRA_INTEGRATION.md` (new file in the HAROLD
   repo) and stop there. Confirm this is acceptable; if you want a
   ledger in HAROLD, that's a substantial expansion.

7. **The /catalog/designators column pivot.** Currently the endpoint
   exposes the manufacturer `part_number` column. HAROLD doesn't
   actually consume `/catalog/designators` (it has no client for it),
   so we can change the column underneath without breaking anyone.
   Confirm the pivot to `internal_part_number` in Phase 3 is OK.

8. **WPN at upload-time vs approval-time.** The prompt phrases it as
   "approval issues the WPN". Should the **proposed** WPN at upload
   also be persisted (so two simultaneous uploads see different
   numbers), or should the sequence only advance at approval? My
   recommendation: only advance at approval, peek at upload. Two
   uploads might see the same proposed number; whichever approves
   first claims it; the second gets re-proposed at approval. This is
   simpler and matches HAROLD's "rev letters are aspirational until
   release" philosophy.

---

## 6. Revised phase plan

Subject to your answers above. The numbering matches the prompt for
diff-ability, but several phases shrink under AD-5/AD-12.

### Phase 1 — migration (largely unchanged from prompt)

Write `backend/alembic/versions/0033_catalog_wpn.py`:
- `catalog_parts.internal_part_number VARCHAR(32) NULL` + unique partial index.
- `catalog_parts.wpn_pending_sync BOOLEAN NOT NULL DEFAULT FALSE` + filtered index.
- `catalog_wpn_sequences (system_code VARCHAR(2) PK, next_index INT NOT NULL DEFAULT 1000, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW())`.

Naming change from prompt: `catalog_wpn_fallback_sequences` → `catalog_wpn_sequences` (primary, not fallback, per AD-5).

### Phase 2 — service layer (extension, not rewrite)

Files to **add** under `backend/app/services/harold/`:
- `validate.py` — `async def validate_wpn(wpn: str) -> WpnValidationResult`.
  Calls `_wardstone-harold-validate` via existing client.
- `filename_validator.py` — `extract_wpn_candidate(filename)`,
  `looks_like_wardstone_wpn(filename)`, `derive_class_hint(filename, parsed)`,
  `FilenameValidationResult` Pydantic model. **Filetype-agnostic** (AD-8).
- `sequences.py` — `async def peek_next_wpn(system_code, db) -> str`,
  `async def claim_wpn(system_code, db) -> str`. SQLAlchemy `with_for_update()`.
- `class_to_system.py` — the AD-10 mapping, single source.

Files to **extend**:
- `service.py` — add `notify_wpn_issued(wpn, part_id, db)` as an audit
  emit (per AD-12 it's a no-op WRT HAROLD, but emits the audit event
  ASTRA-side).
- `errors.py` — add `HaroldValidationError`, `HaroldDuplicateError`.

Files **untouched**: `client.py` (already wraps the runs endpoint correctly).

New schemas in `backend/app/schemas/harold.py`:
- `WpnValidationResult` (per the prompt's spec).
- `WpnSuggestion` extension to include `system_code` + `wpn_source`
  (`'harold'`, `'local'`, `'fallback'`).

`respx`-mocked tests cover happy path, 404, 500, timeout, unknown
system, McMaster-style names, Wardstone-style names, fallback path.

### Phase 3 — endpoints

**Outbound** (`backend/app/routers/harold.py` extension):
- `POST /harold/validate-wpn`        — proxy to validate tool.
- `POST /harold/validate-filename`   — runs `extract_wpn_candidate` +
  optional `validate_wpn` call. Returns `FilenameValidationResult`.

**Inbound** (`backend/app/routers/catalog.py` modification):
- `GET /catalog/designators` — pivot filter column from `part_number`
  to `internal_part_number`. Same `?system=AV` API. Same `limit=200`.
  Same no-auth (AD-6, AD-8).

**Upload + approval hooks** (`backend/app/routers/catalog.py`):
- `POST /catalog/upload-step` — after parsing, peek a proposed WPN,
  call `validate_wpn` if HAROLD is up, persist `proposed_wpn` +
  `wpn_source` + `wpn_validation_notes` into pending_import.
- `_approve_pending_import` — final validate, claim WPN, set on
  `CatalogPart.internal_part_number`, audit emit, handle duplicate
  (422) and HAROLD-down (proceed with `wpn_pending_sync=True`).

### Phase 4 — frontend

Drop-in replacement for `frontend/src/app/catalog/pending-imports/[id]/page.tsx`:
- WPN section with green/amber/red chip and editable monospace input.
- On-blur live validate via `POST /api/v1/harold/validate-wpn`.
- Approve button gated on WPN being valid (or user-acknowledged fallback).

Drop-in replacement for `frontend/src/app/catalog/page.tsx`:
- Parts tab cards/rows show `internal_part_number` primary,
  manufacturer `part_number` secondary. Amber dot if `wpn_pending_sync`.

`frontend/src/lib/harold-api.ts` extension: `validateWpn`,
`validateFilename`.

TypeScript clean, `npm run build` green.

### Phase 5 — HAROLD-side (**no-op under AD-12**)

Create `C:\Tools\harold\docs\ASTRA_INTEGRATION.md` documenting:
- HAROLD has no WPN issuance responsibility.
- ASTRA queries HAROLD's `_wardstone-harold-validate` tool.
- If a future revision wants HAROLD to track issued WPNs, the change is:
  (1) add a `db.py` with a SQLite store under wrench's data dir,
  (2) add `_wardstone-harold-claim-wpn` and `_wardstone-harold-list-issued` tools,
  (3) restart via `pwsh deploy.ps1`.
- Tests on the HAROLD side: none new in this round.

Commit in `C:\Tools\harold`: `feat(astra-integration): document
read-only validator role`.

### Phase 6 — end-to-end testing

Per the prompt's manual smoke matrix, adjusted for the AD-5 reality:
no "HAROLD-side WPN registry" step; instead, after each ASTRA approval,
verify ASTRA's `internal_part_number` is set and the sequence row in
`catalog_wpn_sequences` advanced. Verify HAROLD's validate-name
response continues to return `is_valid=true` for those numbers.

The "HAROLD down" leg: `pwsh -Command "docker stop wrench-api-1"` (or
the wrench-side equivalent — discover the actual container name in
Phase 6 prep). Upload + approve, observe `wpn_pending_sync=True`,
restart, click manual sync.

### Phase 7 — tests + completion notes

Standard test consolidation and `docs/PHASE_HAROLD_INTEGRATION_NOTES.md`.

---

## 7. Risks and gotchas

1. **A WRENCH-API restart wipes the wrench copy.** `deploy.ps1` uses
   `robocopy /MIR`, which **deletes** files in the destination not
   present in the source. If anyone edits `C:\opt\wrench\tools-dev\wardstone-harold`
   directly, the next deploy nukes those edits. The HAROLD README is
   explicit but worth re-stating in the cross-repo notes.
2. **HAROLD's `_wardstone-harold-search` is Ollama-backed and 30 s
   timeout.** We are NOT going to use it on the upload path — only the
   10 s `validate` tool. Phase 2 must make the per-call timeout
   path-specific so a future use of `search` doesn't block the upload.
3. **HAROLD's input schema for validate is `{name: str}`** with
   1 ≤ len ≤ 300. Tracking this so the ASTRA proxy enforces the same
   bounds and returns the right 422 before the HAROLD call.
4. **The `runs` API is single-shot.** No streaming, no long-poll. Fine
   for our use case.
5. **WRENCH may renumber slugs.** Treat slugs as configuration — the
   `TOOL_HAROLD_*` constants in `client.py` are the seam.
6. **HAROLD's revision rules are dense.** The valid REV set excludes
   `I O Q S X Z`. Sequence subranges are tight. The "X1, X2, …
   pre-release rev" rule means our v1 WPN allocator only issues
   `A`-suffix names; X-pre-release is out of scope for v1 STEP uploads.
7. **Pattern matching order matters.** `validate_name` tries
   `vehicle_*` before `cad_part` so a vehicle-prefix name doesn't get
   parsed as a part. Our ASTRA-side `extract_wpn_candidate` regex must
   follow the same precedence.
8. **The 2026 nomenclature restructure dropped project codes from
   parts.** Anything Mason has in older filenames carrying a project
   code (`WS-DRT-ST-P1014-A`) will fail HAROLD's validator and need
   manual remap.
9. **An older `docs/CLAUDE_CODE_PROMPT_HAROLD-001.md`** is still in
   the repo. The current prompt explicitly supersedes it; the older
   one's AD-9 mismatches reality (it assumed HAROLD endpoints
   `_wardstone-harold-search/validate/data` paths that work but aren't
   used the way it described). Recommend deleting it post-merge or
   marking it `SUPERSEDED-BY-HAROLD-INTEGRATION-001.md`.
10. **CSP & CORS.** All HAROLD calls are server-side per AD-7; no CSP
    work needed in Phase 4.

---

## 8. Files saved during Phase 0

- `docs/HAROLD_INTEGRATION_DESIGN.md` (this file).
- `docs/harold_openapi.json` — captured live from `GET http://localhost:8030/openapi.json`.
- Older artifacts (from earlier session, untouched):
  - `docs/HAROLD_INVESTIGATION.md`
  - `docs/CLAUDE_CODE_PROMPT_HAROLD-001.md`
  - `.harold_openapi.json` (orphan from prior run; consider deletion)
  - `C:UsersWardStone…harold_openapi.json` (one-character-encoded-as-string
    path-collision artifact in the repo root; **deletion-safe**, not
    referenced by anything).

---

## 9. What I did NOT do (per the stop instruction)

- No Phase 1 migration written.
- No client/service/router extensions.
- No frontend changes.
- No HAROLD-side commits.
- No code edits to anything under `backend/app/` or `frontend/`.
- No deletion of orphan files in the repo root.
- No flip of `HAROLD_INTEGRATION_ENABLED`.

**Waiting for your go-ahead on the questions in §5 before proceeding.**
