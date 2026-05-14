# HAROLD-001 — Investigation Report (Phase 0)

Per the prompt's "stop and surface" rule (Pre-flight read §3, Common gotcha #4),
I probed HAROLD before writing the client to verify the assumed endpoint
surface. **The actual API differs substantially from the prompt's
assumptions.** This report enumerates the gaps and the chosen path (A).

## What HAROLD actually is

The host service at `localhost:8030/` self-identifies as **WRENCH** v0.2.0
— a generic tool-hosting framework. HAROLD is one of three plugins it
loads (the others are `cadport-extract-project` and `it-hub`). WRENCH
exposes a uniform invocation API; HAROLD's "endpoints" are tool slugs
inside that framework, not standalone REST routes.

### Available HAROLD tools

```
GET /api/tools/          → [
  {slug: "wardstone-harold",         name: "HAROLD",         category: "Utility"},
  {slug: "_wardstone-harold-data",   name: "HAROLD - Data",   category: "Utility"},
  {slug: "_wardstone-harold-search", name: "HAROLD - Search", category: "Utility"},
  ... (non-HAROLD tools)
]
```

### Invocation pattern

```
POST /api/tools/{slug}/runs
Content-Type: application/json
Body: {"inputs": { … tool-specific fields … }}

→ 200 {runId, slug, inputs, output, success, elapsed_ms, error, created_at}
```

Direct `GET /api/tools/{slug}` returns the *tool descriptor* (input/output
schema, fields). It is not an invocation entry point.

### `_wardstone-harold-data`

Reference-data lookup.

| Input              | Output |
|--------------------|--------|
| `{section: "systems"}` | List of 17 system codes — VH/AE/AS/AV/BT/CC/CG/EE/FC/GN/GS/OR/PR/ST/TH/TS/WH plus name + description for each. **Matches the prompt's claim of 17 codes** ✓ |
| `{section: "projects" \| "article_classes" \| "cad_classes" \| "rev_letters" \| "disciplines" \| "artifact_types" \| "reference_frames" \| "vehicle_project_rules" \| "symbols" \| "reserved_prefixes" \| "subscripts" \| "abbreviations" \| "meta" \| "all"}` | Other reference-data sections. |

### `_wardstone-harold-search`

NL-driven naming-pattern matcher with optional LLM refinement.

| Input | Output |
|-------|--------|
| `{query: str, allow_llm_refine: bool}` | `{suggestion, pattern_id, pattern_label, confidence (0-1), reasoning, extracted_fields, glossary_matches[], candidates[], notes[], llm_used}` |

Smoke probe — `query="avionics processor card"` →
`suggestion="WS-AV-P1000-A"`, `pattern_id="cad_part"`, `confidence=0.57`,
`reasoning="CAD part pattern: WS-AV-P1000-A. Parts have no project
segment because they're reusable across vehicles."`,
`llm_used="ollama:llama3.2"`, elapsed ~6.7s.

### `/health`

`GET /health` returns 200 + JSON. Suitable as a fast heartbeat probe.

### `/openapi.json`

Full WRENCH OpenAPI is exposed. Saved to `.harold_openapi.json` during
investigation (not committed). Confirms there is no `runs`-based
allocator surface beyond what's listed above.

## Mismatches with the literal prompt

| Prompt assumption | Reality | Resolution under Path A |
|---|---|---|
| `GET /api/tools/_wardstone-harold-search?system=AV&part_class=lru` returns next available WPN | Search is NL-driven, returns a single pattern-matched suggestion. No `system` / `part_class` query args. | Pass `query` = description (e.g. catalog part's `name` + class label); display `suggestion` with `confidence` and `reasoning` hint. |
| `POST /api/tools/_wardstone-harold-validate {wpn}` | **No validate tool exists.** | Drop HAROLD-side validate; use client-side regex `^WS-[A-Z]{2}-P\d{4}-[A-Z]$` for soft format check. Document in completion notes. |
| `GET /api/tools/_wardstone-harold-data` returns metadata | Returns *tool descriptor* on GET; actual data requires `POST /runs` with `{section: …}`. | Use `POST /runs` everywhere. |
| `harold_version` per response | `version` lives on the `/api/tools` *listing* per slug (today: `0.1.0`). | Cache it on heartbeat. |
| "Next-WPN allocator" — HAROLD tracks who's issued what | HAROLD provides format reference + NL suggestion only. ASTRA's `/designators` is the *only* allocation record. | Confirms the outbound `/designators` endpoint is the right shape. |

## Path chosen — A

Backend seam + frontend UI, adapted to WRENCH's real surface:

1. **Schema** — `systems.system_code_2letter VARCHAR(2)` (migration 0032),
   nullable, uppercase-on-save, no DB enforcement of HAROLD's 17 values.
2. **Config** — three env vars; default-off feature flag.
3. **Services** — `harold/client.py` (httpx, hits WRENCH `/api/tools/{slug}/runs`),
   `service.py` (`list_system_codes`, `suggest_wpn_from_text`, `heartbeat`),
   `errors.py` (`HaroldUnavailableError`, `HaroldInvalidResponseError`).
4. **Router** — `/api/v1/harold/heartbeat`, `/suggest-wpn`,
   `/system-codes`. **No `/validate-wpn` endpoint** — surfaced as a deviation.
5. **Outbound** — `GET /api/v1/catalog/designators` for HAROLD to pull
   what's issued.
6. **Frontend** — `harold-types.ts` + `harold-api.ts`, New-Part page gets
   a system-code dropdown + "Suggest from HAROLD" button (NL search from
   part name + description), and a soft client-side WPN regex check on
   blur. Settings page gets a HAROLD status card with heartbeat result.

## Discovery confirmations

- Alembic head: `0031` (migration 0032 is correct).
- `httpx==0.28.1` already in `backend/requirements-dev.txt`; `respx`
  must be added for mocked tests.
- `backend/app/config.py` uses pydantic-settings `BaseSettings` with
  ALL-CAPS field names. Match that convention.
- `frontend/src/app/projects/[id]/settings/page.tsx` exists with three
  sections (General / Interface Module / Danger Zone). The HAROLD card
  slots in between Interface Module and Danger Zone.
- `frontend/src/app/catalog/parts/new/page.tsx` has a clear
  `partNumber` state + `<Input id="np-pn">` insertion point near
  line 188 for the suggest affordance.

## Open questions deferred until later phases

- Whether to expose HAROLD's `pattern_id` / `pattern_label` /
  `reasoning` / `confidence` in the suggest UI or just the bare
  `suggestion` string. → Phase 4 will show all of them; they're cheap
  to render and useful when confidence is low.
- Whether to authenticate `/catalog/designators` with a shared secret.
  Prompt's AD-text leans toward unauthenticated for v1 → Phase 3 ships
  it open with a docstring caveat; auth becomes a follow-up.
- Whether `list_system_codes` should cache. Single dropdown population,
  one-call-on-mount → no cache needed.
