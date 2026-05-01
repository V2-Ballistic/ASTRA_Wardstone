# ASTRA — Aerospace Systems Traceability & Requirements Application

ASTRA is a requirements/traceability/interface-control platform for complex
aerospace electronic systems: it tracks the supplier catalog, places parts into
project assemblies, captures connector + wire harness designs, auto-generates
traceable interface requirements, and reactively syncs those requirements when
the underlying source data changes.

---

## Quick start

```bash
# From the repository root
docker compose up -d

# Backend  → http://localhost:8000  (API, FastAPI docs at /docs)
# Frontend → http://localhost:3000  (Next.js)
# DB       → postgres @ localhost:5432  (user astra, db astra)
```

Apply the latest migrations once the containers are up:

```bash
docker exec astra-backend-1 alembic upgrade head
```

To populate a fresh database with starter suppliers + catalog parts:

```bash
docker exec astra-backend-1 python -m app.scripts.seed_catalog
```

Run the test suite (default markers exclude perf tests):

```bash
docker exec astra-backend-1 pytest tests/ -q -m 'not performance'
docker exec astra-backend-1 pytest tests/ -q -m performance
```

---

## Architecture overview

ASTRA splits its data into two layers: a **GLOBAL catalog** that's shared
across every project, and a **PROJECT layer** that holds the per-project
instances of catalog parts plus the wires, requirements, and traceability
that flow from them.

```
┌─────────────────────── GLOBAL LAYER (cross-project, master) ──────────────────────┐
│                                                                                    │
│   Supplier ◄──── SupplierDocument                                                  │
│      │                  │                                                          │
│      │                  │ (chain of custody — SHA-256 + audit)                     │
│      ▼                  ▼                                                          │
│   CatalogPart ──── CatalogConnector ──── CatalogPin                                │
│      (LRU master spec, env envelope, lifecycle)            (mfr_pin_name + signal) │
│                                                                                    │
│   PendingCatalogImport ◄── ICD ingestion pipeline (PyMuPDF + camelot + AI)         │
│                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────┘
                                     ▲
                                     │ instantiated_from (catalog_part_id)
                                     │
┌────────────────────── PROJECT LAYER (per-project, instance) ──────────────────────┐
│                                                                                    │
│   Project ── System ── Unit (instance of CatalogPart) ── Connector ── Pin          │
│                          │                                              │          │
│                          │                                  internal_signal_name   │
│                          │                                  (editable, auto-wire   │
│                          │                                   join key)             │
│                          ▼                                                         │
│                    Interface ◄── WireHarness ── Wire                               │
│                          │                                                         │
│                          │ generates                                               │
│                          ▼                                                         │
│                    Requirement ◄── RequirementSourceLink (provenance)              │
│                          │                                                         │
│                          ▼                                                         │
│                    RequirementSyncProposal (raised when source changes)            │
│                          │                                                         │
│                          ▼                                                         │
│                    CoverageException (admin-cosigned waiver)                       │
│                                                                                    │
└────────────────────────────────────────────────────────────────────────────────────┘
```

**Key idea:** Suppliers and LRUs are master data. Projects subscribe to them.
When source data changes — at either layer — derived requirements track the
change and ask for re-approval rather than going stale.

### Reactive requirement sync

SQLAlchemy `after_update` / `after_delete` listeners watch every source-side
entity (System, Unit, Connector, Pin, Interface, WireHarness, Wire,
BusDefinition, MessageDefinition, MessageField, UnitEnvironmentalSpec,
CatalogPart). When any of those mutate, the engine fans out to the
`RequirementSourceLink` index, re-renders each affected requirement against the
canonical template, and either:

- silently auto-applies the change for `pending_review` / `auto_generated`
  requirements (with audit trail), or
- raises a `RequirementSyncProposal` for human review on `approved` /
  `baselined` requirements.

`sync_locked` requirements never receive proposals; admins can override with
`admin_force=true`. Re-entrancy is guarded by a contextvar depth cap (=1) so
apply → listener → apply loops cannot recurse.

### Source coverage validator

The `mv_requirement_source_coverage` materialized view (migration 0025) precomputes
per-requirement coverage severity using the spec §13 rules (L1/L2 ok by default,
L3 needs a direct source, L4 needs traceable parent or source, L5 needs admin
co-signed exception). The `/coverage/source/{project_id}` endpoint serves the MV
in <1s for projects with hundreds of requirements; live recomputation is
available via `?live=true` for paranoid reads.

### ICD ingestion pipeline

`/catalog/documents/{id}/extract` queues a background task that:

1. extracts text + tables + page images via PyMuPDF + camelot[cv]
2. prompts the configured AI provider with a strict JSON schema
3. validates the response against `IcdExtractionResultSchema`
4. persists a `PendingCatalogImport` for human review
5. `/pending-imports/{id}/approve` atomically commits Supplier + CatalogPart +
   CatalogConnector + CatalogPin rows.

---

## Module map

### Backend (`backend/app`)

```
app/
├── routers/
│   ├── catalog.py        ← Suppliers, parts, documents, pending imports (§9.1-9.4)
│   ├── req_sync.py       ← Sync proposals, lock/unlock, source links (§9.6)
│   ├── coverage.py       ← Coverage report, exceptions, cosign (§9.7)
│   ├── interfaces.py     ← Units, connectors, pins, harnesses
│   ├── requirements.py   ← CRUD + history + traceability
│   ├── auth.py           ← JWT login, refresh, MFA, SAML
│   └── ...
├── services/
│   ├── catalog/
│   │   ├── placement.py       ← place_catalog_part / place_brand_new_part
│   │   ├── document_extractor.py   ← PDF/DOCX/XLSX → text/tables/images
│   │   ├── prompts.py         ← LLM prompt templates + JSON schema embed
│   │   └── icd_extractor.py   ← Orchestrator: extract → validate → persist
│   ├── req_sync/
│   │   ├── renderer.py        ← Re-render a requirement from its template
│   │   ├── fan_out.py         ← Source-link walker + auto-apply policy table
│   │   └── listener.py        ← SQLAlchemy event listener wiring
│   ├── coverage/
│   │   ├── source_validator.py    ← MV-backed + live coverage compute
│   │   ├── suggestions.py     ← Pattern-match orphan → suggested source type
│   │   └── refresh.py         ← REFRESH MATERIALIZED VIEW [CONCURRENTLY]
│   ├── interface/
│   │   ├── auto_wire.py       ← Three-way validation engine (§11)
│   │   └── wire_heuristics.py ← Bus/protocol detection from pin names
│   ├── audit_service.py       ← Tamper-evident audit chain
│   └── ai/                    ← LLM client abstraction (Anthropic/OpenAI/local)
├── models/                    ← SQLAlchemy ORM (catalog.py, req_sync.py, ...)
├── schemas/                   ← Pydantic request/response schemas
├── scripts/
│   └── seed_catalog.py        ← Idempotent starter-supplier loader
└── alembic/versions/          ← Migrations 0001 → 0025
```

### Frontend (`frontend/src/app`)

Next.js 14 App Router — every route is a page in `src/app/<path>/page.tsx`:

```
app/
├── (catalog)/
│   ├── catalog/                     ← Suppliers/Parts/Pending tabs
│   ├── catalog/suppliers/[id]/      ← Supplier detail + documents + parts
│   ├── catalog/parts/[id]/          ← Part detail + connectors + pins + variants
│   └── catalog/documents/[id]/review/  ← Side-by-side ICD review
├── projects/[id]/
│   ├── interfaces/                  ← Units list + Connection Builder entry
│   ├── interfaces/connect/          ← Three-step Connection Builder wizard
│   ├── interfaces/unit/[unitId]/    ← Unit detail + connectors + sync panel
│   ├── interfaces/connector/[id]/   ← Dual-name pin table (mfr / internal)
│   ├── interfaces/harness/[id]/     ← Wire list + commit
│   ├── requirements/                ← Virtualized list + sync indicator
│   ├── requirements/[id]/           ← Detail + RequirementSyncPanel
│   ├── auto-requirements/           ← Template-driven auto-gen
│   ├── req-sync/                    ← Pending proposals, three-pane diff
│   └── coverage/                    ← Traffic-light per level + orphan filing
└── components/
    ├── catalog/PlaceLruModal.tsx    ← Tabbed: Catalog / Brand New / Upload ICD
    ├── req-sync/RequirementSyncPanel.tsx
    └── layout/Sidebar.tsx           ← Global nav + project nav + counts
```

### Key services to know

- `app.services.catalog.placement` — instantiating a global CatalogPart into a
  project as a Unit + Connectors + Pins (§14)
- `app.services.req_sync.fan_out` — `decide_action(req_status, proposal_type)`
  policy table; the heart of the sync engine (§12.5)
- `app.services.coverage.source_validator` — orphan detection + severity rules
  per requirement level (§13)
- `app.services.interface.auto_wire` — three-way name/direction/LRU-endpoint
  pin matcher used by the Connection Builder (§11)

---

## Where to find things

| Need | File |
|---|---|
| Spec | `ASTRA_INTERFACE_FOUNDATION_REFACTOR.md` |
| Spec digest (cheat-sheet) | `.foundation_spec_digest.md` (gitignored) |
| Phase-by-phase execution log | `INTERFACE_FOUNDATION_LOG.md` |
| Audit findings + dispositions | `AUDIT_FINDINGS_POST_REMEDIATION.md` |
| Audit remediation phase log | `REMEDIATION_LOG.md` |
| Security policy + threat model | `SECURITY.md` |
| Operator notes (Windows/PowerShell) | `ASTRA_INTERFACE_FOUNDATION_REFACTOR.md` §21 |
| API docs (live) | `http://localhost:8000/docs` (Swagger) |

---

## Known deferred items

The Interface Foundation Refactor (ASTRA-TDD-INTF-002) explicitly defers the
following to follow-up work:

- **F-045 pgvector** — vector index migration + cosine queries (separate prep PR).
- **Frontend test infrastructure** — broken since pre-Phase-3B; deferred from
  audit Phase 3B. Verification today is by `tsc --noEmit` + `npm run build`.
- **Delete-impact UI integration** — backend hooks shipped in audit 3C; UI
  surfacing deferred from audit Phase 3C.
- **/auth/refresh frontend interceptor** — backend supports it; the interceptor
  hook still needs to be added.
- **23 unresolved findings** from `AUDIT_FINDINGS_POST_REMEDIATION.md`
  (F-200..F-222 + 3 partial fixes). Address in a separate audit-remediation PR.
- **Test Integration Module** (ASTRA-TDD-TEST-001 — separate spec).
- **Phase 2 Communication Module** (separate spec).
- **Vendor revision diff/upgrade UI** (per spec §20).
- **Image extraction from ICDs** (text + tables only in v1).
- **Catalog-to-Catalog mating constraints**.
- **Cross-project full-graph where-used**.
- **Archival job for old sync proposals**.
- **Signal entity abstraction** (three-way auto-wire mitigates the immediate need).
- **Vendor-side ICD smoke** — Mason runs the manual real-PDF + real-AI smoke
  before merging Phase 7 + 8 to main; the mocked-LLM tests cover all 10
  acceptance scenarios from the phase prompt.

---

## License & contributing

Internal R&D use only. See `SECURITY.md` for vulnerability reporting and the
phase logs for the change-management trail.
