# ASTRA Codebase Audit — Claude Code Prompt

**Purpose:** Run a full-codebase static audit of ASTRA to identify bugs, errors, security issues, anti-patterns, and contract drift between the FastAPI backend and Next.js frontend. Produce a single consolidated findings document.

**Target codebase root:** `C:\Users\Mason\Documents\ASTRA`

**Deliverable:** A single markdown document at `C:\Users\Mason\Documents\ASTRA\AUDIT_FINDINGS.md` containing every finding using the structure defined in Section 6.

---

## 1. Operating Rules

1. **Read-only audit.** Do not modify any source files. Do not run migrations. Do not start, stop, or `docker compose` anything. Do not run tests that mutate the database.
2. **Cover the entire repo.** Walk every file under the root except: `node_modules/`, `.next/`, `__pycache__/`, `.venv/`, `venv/`, `dist/`, `build/`, `.git/`, `*.lock`, `*.log`, and any `*.sqlite` or `*.db` binaries.
3. **No speculation.** Every finding must cite a real file path and line range. If you cannot point to specific lines, do not include the finding.
4. **No fabrication.** If something looks suspicious but you can't confirm it from the code, mark it as `Needs Manual Review` rather than asserting a bug.
5. **Cross-reference before flagging.** Before claiming an endpoint is unused, grep the frontend. Before claiming a frontend call is broken, grep the backend router. API contract mismatches require evidence from both sides.
6. **Severity is conservative.** When in doubt, downgrade. A `Critical` finding must have a clear exploit, data-loss, or production-down path.

---

## 2. Project Context (do not re-derive)

- **Stack:** FastAPI + SQLAlchemy + PostgreSQL 16 backend; Next.js 14 (App Router) + TypeScript + Tailwind frontend; Alembic for migrations; Docker Compose runtime.
- **Containers:** `astra-backend-1`, `astra-frontend-1`, `astra-db-1`.
- **Active project:** SMDS, project_id=1. Default user: `mason` (admin).
- **Domain:** Aerospace/defense MBSE — requirements, traceability, ICDs, verification. Standards: NASA Appendix C SHALL patterns, MIL-STD-810H/461G/1553B/882E, INCOSE SE Handbook, 21 CFR Part 11, NIST SP 800-53, DO-178C, ISO 29148.
- **Most recently completed module:** Interface Module (Systems / Units / Connectors / Pins / Wire Harnesses / Bus Definitions / Messages / Auto-Generated Requirements). Pay extra attention here — it is the freshest code and most likely to harbor bugs.
- **AI generation pipeline:** Three-tier (OpenAI / Anthropic / regex fallback) for SHALL statement generation and auto-requirements. pgvector for embeddings.

---

## 3. Audit Phases

Execute in order. Do not skip phases.

### Phase 0 — Inventory
1. Walk the tree and produce a file-count summary by directory and language. Include this as an appendix in the final report.
2. Identify the canonical locations of:
   - FastAPI routers (`backend/app/routers/` or equivalent)
   - SQLAlchemy models
   - Pydantic schemas
   - Alembic migrations (`alembic/versions/`)
   - Next.js routes (`frontend/app/`)
   - Frontend API client(s) and TypeScript type definitions
   - Docker / compose / env files

### Phase 1 — Backend audit (Python / FastAPI / SQLAlchemy)

For every Python file, look for:

**Correctness**
- Missing `await` on async calls; sync DB sessions inside async endpoints.
- `Depends()` misuse; missing `Depends(get_db)` or `Depends(get_current_user)` on endpoints that mutate data.
- Endpoints that accept a `project_id` or resource ID but never check ownership/authorization.
- Routers that silently catch broad `Exception` and return 200.
- Endpoints that mutate state inside GET handlers.
- N+1 queries — relationship access inside loops without `selectinload`/`joinedload`.
- Missing `db.commit()` or `db.rollback()` in error paths.
- Float/decimal mixing in any pricing, tolerance, or measurement code.
- Off-by-one in pagination (`offset`, `limit`).

**Schema & ORM**
- `SQLEnum(...)` declarations missing `values_callable=lambda x: [e.value for e in x]` (known gotcha — PostgreSQL enums must be lowercase).
- Models with mutable defaults (`default=[]`, `default={}`).
- Foreign keys without `ondelete` strategy on parent-child relationships where cascade matters (trace links, audit log, generated requirements).
- Mismatch between SQLAlchemy column type and Pydantic schema field type.
- Indexes missing on frequently filtered columns (`project_id`, `status`, `created_at`, foreign keys used in joins).

**Migrations (Alembic)**
- Any migration containing `op.drop_table(...)` — flag every instance for manual review (autogenerate-drift hazard).
- Any migration that runs `CREATE EXTENSION` (specifically `pgvector`) — flag as a transaction-poisoning risk.
- Migrations that diverge from the 0001→0007 chain or have non-linear `down_revision` values.
- Data migrations mixed with DDL in the same revision without explicit transaction handling.

**Security**
- Hardcoded secrets, API keys, JWT secrets, or passwords in source.
- `password123` or similar dev credentials referenced outside seed/test files.
- SQL constructed via f-string or `.format()` (rather than parameterized).
- Missing CORS allowlist or `allow_origins=["*"]` in production paths.
- JWT decode without signature verification or with `verify=False`.
- Any endpoint returning password hashes, tokens, or full user objects with sensitive fields.
- File upload endpoints without size limits, MIME validation, or path traversal protection.

**Reliability**
- Endpoints that pass `limit=1000` or higher to internal pagination (backend rate limit is 200 — flag any limit > 200).
- Long-running synchronous calls (LLM, file generation, audit export) without background task offload.
- Unbounded result sets returned without pagination.
- Missing timeouts on outbound HTTP/LLM calls.
- AI generation code paths without the regex fallback wired in.

**Domain compliance**
- SHALL statement generation that doesn't enforce NASA Appendix C patterns (single SHALL per statement, active voice, testable verb).
- Audit log writes that miss any of: actor, timestamp, before/after state, reason — required for 21 CFR Part 11.
- Electronic signature flows that don't bind signature to specific record state (hash mismatch risk).
- Trace-link creation paths that don't update both endpoints' link counts atomically.

### Phase 2 — Frontend audit (Next.js 14 / TypeScript / Tailwind)

For every `.ts`/`.tsx` file, look for:

**Correctness**
- `useEffect` with missing dependencies or stale closures.
- `useEffect` with side effects that fire on every render (missing dep array entirely).
- Async state updates after unmount without cleanup.
- `key={index}` on lists where reorder/delete is possible.
- Conditional hooks (hook called inside `if`/early return).
- Form submission handlers that don't `preventDefault`.
- Optimistic UI updates without rollback on failure.

**API integration**
- Any axios/fetch call with `limit: 1000` or higher (backend max is 200 — must be ≤200).
- API calls without `try/catch` or `.catch()` and without surfacing errors to the user.
- Hardcoded API URLs that should come from env config.
- Calls that don't go through the central axios instance with the JWT interceptor.
- Frontend types that drift from backend Pydantic schemas — list every mismatched field.
- The known case: anywhere `UnitSummary` is treated as if it carried `system_id` (it doesn't — flag any such assumption).

**Type safety**
- `any` usage outside of clearly justified boundaries.
- `as` casts that hide a real type mismatch.
- Non-null assertions (`!`) on values that can plausibly be null/undefined.
- Optional chaining followed by an unguarded property access.

**Accessibility & UX**
- Buttons without accessible labels.
- Forms without labels associated to inputs.
- Color-only signaling (especially in the dark aerospace theme).
- Missing loading and empty states on async data views.
- Missing error boundaries on routes that render data-heavy widgets.

**Performance**
- Lists rendered without virtualization beyond ~500 rows.
- Heavy computations inside render without `useMemo`.
- New object/array literals passed as props on every render.
- Images without `next/image` where applicable.

### Phase 3 — Cross-cutting & integration

- **API contract drift:** for every backend route, confirm a frontend caller exists with matching method, path, request shape, and response handling. List orphaned endpoints (no caller) and orphaned frontend calls (no matching backend route).
- **Enum drift:** every TypeScript union/enum mirroring a backend enum must match exactly (lowercase values, identical members).
- **Status code consistency:** mutating endpoints should return 200/201/204 consistently; error paths should return appropriate 4xx with structured detail.
- **Auth flow:** confirm every non-public endpoint requires auth and that the frontend handles 401 by redirecting to login.
- **Docker / env:** flag missing entries in `.env.example`, secrets committed in `.env`, container names referenced in code that don't match `astra-{service}-1`.
- **Logging:** PII or secrets in log statements; missing structured logging on critical paths (auth, audit, signature, export).

### Phase 4 — Dead code, TODOs, and risk markers

- Every `TODO`, `FIXME`, `XXX`, `HACK`, `# noqa`, `// @ts-ignore`, `// @ts-expect-error` — list with file:line and surrounding context.
- Unused imports, unused exports, unreachable code blocks.
- Functions defined but never called within the project.
- Commented-out code blocks longer than 5 lines.

---

## 4. Severity Definitions

| Severity | Definition |
|---|---|
| **Critical** | Can cause data loss, auth bypass, secret exposure, or production outage. Must fix before next deploy. |
| **High** | Bug with clear user-visible impact, broken core flow, or compliance gap (21 CFR Part 11, audit trail integrity, signature binding). |
| **Medium** | Incorrect behavior in non-core paths, performance cliff under realistic load, type safety hole, accessibility blocker. |
| **Low** | Style, minor type imprecision, dead code, missing log field, cosmetic inconsistency. |
| **Info** | Observation worth noting; not a defect. Includes architectural smells, refactor opportunities. |

---

## 5. What NOT to Flag

- Stylistic preferences (single vs. double quotes, import ordering) unless inconsistent within the same file.
- Tailwind class ordering.
- Third-party code under `node_modules/`, `__pycache__/`, `.venv/`.
- Generated files (`*.generated.*`, OpenAPI client output).
- Anything inside `migrations/versions/` older than 0001 if it predates the current chain.
- Tests as "untested code" — testing is a separate concern, out of scope here.

---

## 6. Output Format

Write the final document to `C:\Users\Mason\Documents\ASTRA\AUDIT_FINDINGS.md` with this exact structure:

```markdown
# ASTRA Audit Findings
**Date:** <YYYY-MM-DD>
**Commit/branch:** <git rev-parse HEAD output, or "uncommitted">
**Files scanned:** <count>
**Total findings:** <count>

## Executive Summary
- Critical: N
- High: N
- Medium: N
- Low: N
- Info: N

<2-4 paragraph plain-English summary of the codebase's overall health, top three risk areas, and recommended priority order for remediation.>

## Findings

### CRITICAL

#### F-001 — <short title>
- **File:** `relative/path/to/file.py`
- **Lines:** 42–58
- **Category:** <Backend / Frontend / Migration / Security / Domain / Cross-cutting>
- **Description:** <what is wrong, in 1–3 sentences>
- **Impact:** <what breaks, who's affected>
- **Recommendation:** <concrete fix in 1–2 sentences>
- **Evidence:**
  ```python
  <minimal code excerpt showing the issue>
  ```

#### F-002 — ...

### HIGH
<same structure>

### MEDIUM
<same structure>

### LOW
<same structure>

### INFO
<same structure>

## Cross-Cutting Concerns

### API Contract Drift
| Backend Route | Frontend Caller | Mismatch |
|---|---|---|
| ... | ... | ... |

### Enum Drift
| Backend Enum | Frontend Mirror | Mismatch |
|---|---|---|
| ... | ... | ... |

### Orphaned Endpoints / Calls
- Backend routes with no frontend caller: ...
- Frontend calls with no backend route: ...

## TODO / FIXME / Risk-Marker Inventory
| File | Line | Marker | Context |
|---|---|---|---|
| ... | ... | ... | ... |

## Appendix A — File Inventory
<directory tree with file counts and line counts by language>

## Appendix B — Audit Methodology
<bulleted list of what was scanned, what was skipped, and any limitations encountered>
```

---

## 7. Numbering & Identifiers

- Findings are numbered globally `F-001`, `F-002`, ... in order of severity (Critical first), then in the order encountered within each severity bucket.
- Once written, IDs are stable. If you re-run this audit, append new findings with new IDs rather than renumbering.

---

## 8. Final Checks Before Writing the Report

1. Every `Critical` and `High` finding has a real file path and a line range that exists in the file.
2. No two findings describe the same root cause — consolidate duplicates.
3. The Executive Summary counts match the actual finding counts in each section.
4. The API Contract Drift table is filled out (or explicitly marked "no drift detected").
5. The TODO inventory is complete.
6. The file is saved to `C:\Users\Mason\Documents\ASTRA\AUDIT_FINDINGS.md` and nowhere else.

When the report is written, print to stdout: `AUDIT COMPLETE — <N> findings written to AUDIT_FINDINGS.md` and stop. Do not summarize the findings in chat; the document is the deliverable.
