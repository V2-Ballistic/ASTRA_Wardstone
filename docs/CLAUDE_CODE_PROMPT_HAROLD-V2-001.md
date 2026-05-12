# Claude Code Execution Prompt — HAROLD V2 Rebuild

> Rebuilds HAROLD as a standalone FastAPI service replacing the current WRENCH plugin. Preserves the `WS-<XX>-P<NNNN>-<REV>` nomenclature pattern but adds 4 library-category codes (FH/MH/EH/SH), expands the part-number range to 6 digits (1-999999), adds a persistent ledger, and exposes a proper REST API for cross-service integration.
>
> Cross-repo: lives at `C:\Tools\harold` (replaces existing WRENCH plugin in-place). Sync to `C:\opt\wrench\tools-dev\wardstone-harold` via the existing `pwsh deploy.ps1` mirror.
>
> **Does NOT touch ASTRA.** Integration with ASTRA is a follow-up prompt (HAROLD-INTEGRATION-002) once V2 ships clean.

---

## Mission

Working in `C:\Tools\harold`. Replace the current WRENCH plugin (6 tool handlers, no persistence, pure-regex validation) with a proper FastAPI service. The new service:

1. Serves on port 8030 (preserves current integration point)
2. Persists all issued WPNs in a Postgres ledger
3. Validates WPN format against the expanded standard
4. Suggests next-available WPNs per system/library code
5. Exposes a clean REST API
6. Runs in Docker with `docker compose up`
7. Includes a minimal browse UI for HAROLD operators to see issued WPNs

The current 6 WRENCH tool handlers (validate, search, data, bulk-validate, add-project, delete-project) keep their behavior but route to the new REST endpoints internally — anywhere HAROLD is currently called as a WRENCH plugin continues to work transparently. This is the migration bridge.

Commit per phase. Use `phase-<n>(harold-v2): <summary>`. **Verify each phase before commit. Phase 0 is a hard stop with design report.**

---

## Pre-flight read

Read the current state thoroughly. The new build keeps the nomenclature contract; everything else changes.

1. `C:\Tools\harold\` — full repo walk:
   ```powershell
   Get-ChildItem C:\Tools\harold -Recurse -File -Include *.py,*.md,*.toml,*.cfg,*.yml,*.yaml,*.ps1,Dockerfile,docker-compose.yml | Select-Object FullName, Length, LastWriteTime
   ```
2. Every tool handler implementation — the regex rules, the validation logic, the system code list, error messages. Document each behavior exactly so the new service reproduces them.
3. `deploy.ps1` — the existing robocopy mirror to the wrench copy. Document its mechanics.
4. Any test files — preserve their assertions in the new test suite if applicable.

Also confirm in ASTRA's repo (read-only, don't modify):
- `C:\Users\WardStone\Documents\ASTRA\docs\HAROLD_INTEGRATION_DESIGN.md` — the Phase 0 discovery report from the previous integration attempt. It documents what HAROLD currently looks like.
- `C:\Users\WardStone\Documents\ASTRA\backend\app\services\harold\` — the partial HAROLD client skeleton from prior work. Don't touch it now (ASTRA integration is the follow-up prompt) but read it so you understand what API surface the future integration expects.

---

## Decisions — locked

| # | Decision | Rationale |
|---|----------|-----------|
| AD-1 | New FastAPI service. Replaces WRENCH plugin entry point. Same path (`C:\Tools\harold`), same git history. | WRENCH plugin model can't carry persistence cleanly. FastAPI is what ASTRA expects to talk to. |
| AD-2 | WRENCH tool handlers preserved as thin shims that call the new REST API via localhost. Existing WRENCH integrations continue working. | Migration bridge. No flag day for downstream WRENCH consumers. |
| AD-3 | WPN format: `WS-<XX>-P<NNNNNN>-<REV>` where XX is one of 21 codes (17 existing + FH/MH/EH/SH new), NNNNNN is 6 digits 1-999999, REV is single uppercase A-Z. | Mason's call: extended range for headroom, library codes for catalog-level parts. |
| AD-4 | Postgres for the ledger. New `harold_db` database in the same Postgres instance ASTRA uses. New container `harold-db-1` is overkill — reuse the existing `astra-db-1` instance with a separate `harold` database. | One Postgres instance, two databases, clean separation. |
| AD-5 | Port 8030 preserved. Backend container `harold-backend-1`. | Doesn't disturb ASTRA's port mappings; downstream services find HAROLD where they expect it. |
| AD-6 | Run as a sibling Docker service in ASTRA's `docker-compose.yml`, OR in HAROLD's own `docker-compose.yml`. Decision deferred to Phase 0 — choose whichever makes the dev loop simpler for Mason. | Practical, not architectural. |
| AD-7 | REST API only. No GraphQL, no gRPC. JSON over HTTP. | Standard, ASTRA already speaks HTTP. |
| AD-8 | Browse UI is minimal (server-rendered Jinja templates or a tiny single-file HTML page). Not a full SPA. | HAROLD is a utility service; rich UI is not the point. |
| AD-9 | Alembic for migrations. Pattern after ASTRA's setup (hand-written, no autogenerate). | Consistent with shop standards. |
| AD-10 | Validate-and-claim atomicity: when ASTRA registers a new WPN, HAROLD writes the ledger row inside a transaction with a uniqueness check. If the same WPN is registered twice concurrently, second registration returns 409 Conflict. | Prevents race conditions in cross-service WPN allocation. |
| AD-11 | Audit log on every ledger write (issued, retired, transferred). New table `harold_audit_log`. | Standard for naming services. |
| AD-12 | No auth in v1. LAN-only deployment assumption. Document as future TDD. | Matches ASTRA's `/catalog/designators` posture. |

---

## Standing rules

1. **Drop-in file replacements only.** Whole-file output.
2. **No Alembic autogenerate.** Hand-write migrations.
3. **Python AST validation** on every Python file before delivery.
4. **PowerShell:** `curl.exe`, no `$PID`, `Invoke-RestMethod` for JSON.
5. **TypeScript/React n/a here** (HAROLD has no React; minimal UI is server-rendered).
6. **Don't touch ASTRA.** The follow-up integration prompt does that.
7. **Don't edit the wrench copy directly.** All edits in `C:\Tools\harold`. Sync via deploy.ps1 — extend it if needed to handle the new structure.
8. **Don't run a verification command and silently move past failure.** Stop on red.
9. **Preserve git history** at `C:\Tools\harold`. New commits add on; don't rewrite history.
10. **No breaking changes to the WPN format** beyond what AD-3 specifies. The 17 existing system codes keep their meaning. Existing valid WPNs in the wild remain valid.

---

## System code reference

The 21 codes the new HAROLD recognizes:

**Existing project-system codes (17, preserved verbatim from current HAROLD):**
```
VH  AE  AS  AV  BT  CC  CG  EE  FC  GN  GS  OR  PR  ST  TH  TS  WH
```

**New library-category codes (4, added):**
```
FH  — Fastener Hardware
MH  — Mechanical Hardware (non-fastener)
EH  — Electrical Hardware (catalog-level)
SH  — Soft/Sealing Hardware
```

These categorize **catalog-level parts** (generic library items) that don't yet belong to a project system. When a part is later placed into a project, its project-system code may differ; the catalog WPN with the library code stays as the canonical reference.

Validation regex: `^WS-(VH|AE|AS|AV|BT|CC|CG|EE|FC|GN|GS|OR|PR|ST|TH|TS|WH|FH|MH|EH|SH)-P[0-9]{6}-[A-Z]$`

Number range: `P000001` through `P999999`. The `000001` is the first issued; the allocator initializes at 1. New users will see `WS-FH-P000001-A` as the first fastener hardware WPN issued, `WS-FH-P000002-A` as the second, etc. Each system/library code maintains its own counter.

Revision letters: A through Z. First revision is A. When a part is revised, the revision letter advances (B, C, …, Z). After Z, the next revision uses double letters (AA, AB, …) — but that's far enough out we punt on it; v1 supports A-Z only.

---

## Phase 0 — Design confirmation + deployment plan

Mandatory stop with report.

Tasks:

1. **Document the current HAROLD surface precisely** — every WRENCH tool, its inputs, its outputs, its error responses. The new service's WRENCH shims must produce identical behavior to existing callers. Save as `docs/CURRENT_HAROLD_SURFACE.md`.

2. **Decide deployment topology.** Two options:
   - **A** — Add `harold-backend` and (optionally) reuse `astra-db-1` in ASTRA's `docker-compose.yml`. Both services orchestrated from one compose file.
   - **B** — HAROLD has its own `docker-compose.yml`. ASTRA's compose stays untouched. Two separate `docker compose up` invocations.
   
   Recommend B for cleaner separation; the two services communicate via host networking. Document the choice and the rationale in `docs/HAROLD_V2_DEPLOYMENT.md`.

3. **Confirm Postgres approach.** Reuse `astra-db-1` with a separate `harold` database? Or run a dedicated `harold-db-1` container? Recommend separate database in same instance (one Postgres, two databases — minimum infrastructure, clean isolation).

4. **Confirm migration path for existing in-the-wild WPNs.** Currently there aren't any (ASTRA hasn't issued any yet per the audit query Mason ran earlier — `SELECT … FROM catalog_parts WHERE cad_step_path IS NOT NULL` returned zero rows). But document that any existing WPNs from prior HAROLD usage (if discovered) get loaded into the new ledger on first startup via a seed script. Phase 7 implements the seed script if needed.

5. **Confirm the deploy.ps1 changes.** New structure (Docker containers vs the current Python module mirror) means deploy.ps1 needs updating. Document what changes.

Deliverable: `docs/HAROLD_V2_DESIGN.md` in the HAROLD repo with:
- Current surface documented (point 1 above).
- Deployment topology choice (A or B).
- Database approach.
- Migration plan for existing WPNs.
- Updated deploy.ps1 plan.
- Confirmed sequence of Phases 1-8.

Commit: `phase-0(harold-v2): design confirmation + deployment plan`. Push and **stop**. Do not proceed.

---

## Phase 1 — Scaffolding

New directory structure:

```
C:\Tools\harold\
├── docker-compose.yml           (new — if deployment Option B)
├── Dockerfile                   (new — for the FastAPI service)
├── pyproject.toml               (new — Python project metadata)
├── alembic.ini                  (new)
├── deploy.ps1                   (updated for new structure)
├── app/
│   ├── __init__.py
│   ├── main.py                  (FastAPI entrypoint)
│   ├── config.py                (Settings)
│   ├── database.py              (SQLAlchemy session)
│   ├── models/
│   │   ├── __init__.py
│   │   ├── wpn_ledger.py
│   │   └── audit_log.py
│   ├── schemas/
│   │   ├── __init__.py
│   │   ├── wpn.py
│   │   └── audit.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── wpn_validator.py
│   │   ├── wpn_allocator.py
│   │   └── audit_service.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── wpn.py
│   │   ├── ledger.py
│   │   ├── system_codes.py
│   │   └── health.py
│   ├── wrench_shims/            (legacy WRENCH tool handlers, now thin shims)
│   │   ├── __init__.py
│   │   ├── validate.py
│   │   ├── search.py
│   │   ├── data.py
│   │   ├── bulk_validate.py
│   │   ├── add_project.py
│   │   └── delete_project.py
│   └── ui/                      (minimal browse UI)
│       ├── templates/
│       │   ├── base.html
│       │   ├── ledger.html
│       │   └── wpn_detail.html
│       └── static/
│           └── style.css
├── alembic/
│   ├── env.py
│   └── versions/
│       └── 0001_initial_schema.py
├── tests/
│   ├── conftest.py
│   ├── test_wpn_validator.py
│   ├── test_wpn_allocator.py
│   ├── test_ledger_api.py
│   ├── test_wrench_shims.py
│   └── test_browse_ui.py
└── docs/
    ├── README.md (updated)
    ├── CURRENT_HAROLD_SURFACE.md (from Phase 0)
    ├── HAROLD_V2_DEPLOYMENT.md (from Phase 0)
    └── HAROLD_V2_DESIGN.md (from Phase 0)
```

`config.py`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg2://harold:harold@localhost:5432/harold"
    api_port: int = 8030
    cors_origins: str = "http://localhost:3000,http://localhost:8000"
    environment: str = "development"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",")]

    class Config:
        env_prefix = "HAROLD_"
        env_file = ".env"
```

`main.py`:
```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import wpn, ledger, system_codes, health
from app.wrench_shims import router as wrench_router

app = FastAPI(title="HAROLD V2", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(wpn.router, prefix="/api/v1")
app.include_router(ledger.router, prefix="/api/v1")
app.include_router(system_codes.router, prefix="/api/v1")
app.include_router(wrench_router, prefix="/api/tools")  # legacy WRENCH compatibility
```

`Dockerfile`:
```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e .

COPY app/ ./app/
COPY alembic/ ./alembic/
COPY alembic.ini ./

EXPOSE 8030

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD curl -f http://localhost:8030/health || exit 1

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8030"]
```

`docker-compose.yml` (if Option B from Phase 0):
```yaml
version: '3.9'

services:
  harold-db:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: harold
      POSTGRES_PASSWORD: harold
      POSTGRES_DB: harold
    ports:
      - "127.0.0.1:5433:5432"  # different port from ASTRA's postgres
    volumes:
      - harold-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U harold"]
      interval: 5s
      timeout: 3s
      retries: 5

  harold-backend:
    build: .
    ports:
      - "0.0.0.0:8030:8030"
    environment:
      HAROLD_DATABASE_URL: postgresql+psycopg2://harold:harold@harold-db:5432/harold
      HAROLD_API_PORT: "8030"
      HAROLD_ENVIRONMENT: development
    depends_on:
      harold-db:
        condition: service_healthy

volumes:
  harold-db-data:
```

Verify Phase 1:
```powershell
cd C:\Tools\harold
docker compose build
docker compose up -d
docker compose ps  # both healthy
curl.exe http://localhost:8030/health  # {"status": "healthy"}
```

Commit: `phase-1(harold-v2): scaffolding — fastapi, docker, alembic`.

---

## Phase 2 — WPN validator + allocator services

### 2.1 `app/services/wpn_validator.py`

```python
import re
from dataclasses import dataclass

VALID_SYSTEM_CODES = {
    # Project-system codes (existing 17)
    "VH", "AE", "AS", "AV", "BT", "CC", "CG", "EE", "FC", "GN", "GS",
    "OR", "PR", "ST", "TH", "TS", "WH",
    # Library-category codes (new 4)
    "FH", "MH", "EH", "SH",
}

WPN_REGEX = re.compile(
    r"^WS-(?P<sys>[A-Z]{2})-P(?P<num>\d{6})-(?P<rev>[A-Z])$"
)

@dataclass
class WpnValidationResult:
    wpn: str
    is_valid: bool
    errors: list[str]
    parsed: dict | None  # {sys, num, rev} when valid

def validate_wpn_format(wpn: str) -> WpnValidationResult:
    """Pure format validation. Does NOT check the ledger.
    
    For ledger uniqueness, use ledger_service.is_wpn_issued()."""
    errors = []
    if not wpn or not isinstance(wpn, str):
        return WpnValidationResult(wpn, False, ["WPN must be a non-empty string"], None)

    m = WPN_REGEX.match(wpn)
    if not m:
        errors.append(
            "Format must match WS-<XX>-P<NNNNNN>-<REV> where "
            "XX is a 2-letter code, NNNNNN is 6 digits, REV is A-Z"
        )
        return WpnValidationResult(wpn, False, errors, None)

    sys_code = m.group("sys")
    num = int(m.group("num"))
    rev = m.group("rev")

    if sys_code not in VALID_SYSTEM_CODES:
        errors.append(
            f"System code '{sys_code}' is not in the allowed list. "
            f"Allowed: {', '.join(sorted(VALID_SYSTEM_CODES))}"
        )
    if not (1 <= num <= 999999):
        errors.append(f"Part number {num} out of range 1-999999")
    if not ("A" <= rev <= "Z"):
        errors.append(f"Revision '{rev}' must be A-Z")

    is_valid = len(errors) == 0
    return WpnValidationResult(
        wpn,
        is_valid,
        errors,
        {"sys": sys_code, "num": num, "rev": rev} if is_valid else None,
    )
```

### 2.2 `app/services/wpn_allocator.py`

Atomic allocation. Uses a sequence table per system code with row-level locking.

```python
from sqlalchemy.orm import Session
from app.models.wpn_ledger import WpnSequence, WpnLedgerEntry

def allocate_next_wpn(db: Session, system_code: str, *, dry_run: bool = False) -> str:
    """Allocates next available WPN for the given system code.
    
    Atomic: row-locks the sequence row, increments, formats, returns.
    If dry_run=True, returns the next number without incrementing.
    """
    if system_code not in VALID_SYSTEM_CODES:
        raise ValueError(f"Unknown system code: {system_code}")

    seq = (
        db.query(WpnSequence)
        .filter(WpnSequence.system_code == system_code)
        .with_for_update()
        .first()
    )
    if not seq:
        seq = WpnSequence(system_code=system_code, next_index=1)
        db.add(seq)
        db.flush()

    next_index = seq.next_index
    wpn = f"WS-{system_code}-P{next_index:06d}-A"

    if not dry_run:
        seq.next_index = next_index + 1

    return wpn

def reserve_wpn(db: Session, wpn: str) -> WpnLedgerEntry:
    """Records a WPN as issued. Idempotent: re-registering an existing
    WPN with the same metadata is a no-op; conflicting metadata is 409.
    """
    result = validate_wpn_format(wpn)
    if not result.is_valid:
        raise ValueError(f"Invalid WPN format: {result.errors}")
    # … implementation: insert into wpn_ledger with unique constraint on wpn
```

### 2.3 Tests

`tests/test_wpn_validator.py`:
- Valid: `WS-FH-P000001-A`, `WS-ST-P999999-Z`, every system code with a sample WPN.
- Invalid: lowercase, wrong number of digits, system code not in list, revision out of range, missing dashes, empty string.

`tests/test_wpn_allocator.py`:
- First allocation for unknown system: returns `WS-XX-P000001-A`, sequence row created.
- Sequential allocations increment: 000001, 000002, 000003.
- Different system codes have independent counters.
- Concurrent allocation simulated via pytest-asyncio: both succeed, no duplicate numbers.
- `dry_run=True` doesn't advance the sequence.

Verify:
```powershell
docker compose exec harold-backend python -m pytest tests/test_wpn_validator.py tests/test_wpn_allocator.py -v
```

Commit: `phase-2(harold-v2): wpn validator + allocator + tests`.

---

## Phase 3 — Persistence: ledger + audit + migration

### 3.1 Migration `alembic/versions/0001_initial_schema.py`

```python
"""Initial HAROLD V2 schema."""

revision = "0001"
down_revision = None

def upgrade():
    op.execute("""
        CREATE TABLE wpn_sequences (
            system_code     VARCHAR(2)  PRIMARY KEY,
            next_index      INTEGER     NOT NULL DEFAULT 1,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """)

    op.execute("""
        CREATE TABLE wpn_ledger (
            id                  BIGSERIAL    PRIMARY KEY,
            wpn                 VARCHAR(24)  NOT NULL UNIQUE,
            system_code         VARCHAR(2)   NOT NULL,
            part_number_int     INTEGER      NOT NULL,
            revision            CHAR(1)      NOT NULL,

            -- Cross-system metadata (e.g. ASTRA's catalog_part_id)
            origin_system       VARCHAR(32),     -- 'astra', 'manual', 'imported'
            origin_record_id    VARCHAR(64),     -- e.g. '42' for astra catalog_parts.id=42
            display_name        VARCHAR(255),    -- human-readable label
            description         TEXT,
            metadata_json       JSONB,           -- arbitrary attached data

            status              VARCHAR(32)  NOT NULL DEFAULT 'active',
                -- active, retired, superseded, reserved
            superseded_by       VARCHAR(24)  REFERENCES wpn_ledger(wpn),

            issued_at           TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
            retired_at          TIMESTAMPTZ,

            CONSTRAINT ck_wpn_format CHECK (
                wpn ~ '^WS-[A-Z]{2}-P[0-9]{6}-[A-Z]$'
            )
        )
    """)

    op.execute("CREATE INDEX ix_wpn_ledger_system ON wpn_ledger(system_code)")
    op.execute("CREATE INDEX ix_wpn_ledger_status ON wpn_ledger(status)")
    op.execute("CREATE INDEX ix_wpn_ledger_origin ON wpn_ledger(origin_system, origin_record_id)")
    op.execute("CREATE INDEX ix_wpn_ledger_issued_at ON wpn_ledger(issued_at)")

    op.execute("""
        CREATE TABLE harold_audit_log (
            id             BIGSERIAL    PRIMARY KEY,
            event_type     VARCHAR(64)  NOT NULL,
                -- wpn.issued, wpn.retired, wpn.superseded, wpn.metadata_updated,
                -- ledger.exported, system_code.queried
            wpn            VARCHAR(24),
            actor          VARCHAR(128),    -- 'astra', 'manual', user id, IP address
            details        JSONB,
            created_at     TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX ix_harold_audit_event ON harold_audit_log(event_type)")
    op.execute("CREATE INDEX ix_harold_audit_wpn ON harold_audit_log(wpn)")
    op.execute("CREATE INDEX ix_harold_audit_created ON harold_audit_log(created_at)")

    # Seed sequences with starting values (1) for all 21 codes
    for code in (
        "VH","AE","AS","AV","BT","CC","CG","EE","FC","GN","GS",
        "OR","PR","ST","TH","TS","WH",
        "FH","MH","EH","SH",
    ):
        op.execute(f"INSERT INTO wpn_sequences (system_code) VALUES ('{code}')")


def downgrade():
    op.execute("DROP TABLE IF EXISTS harold_audit_log CASCADE")
    op.execute("DROP TABLE IF EXISTS wpn_ledger CASCADE")
    op.execute("DROP TABLE IF EXISTS wpn_sequences CASCADE")
```

### 3.2 Models

`app/models/wpn_ledger.py` — SQLAlchemy ORM matching the migration.

`app/models/audit_log.py` — same.

### 3.3 Verify

```powershell
docker compose exec harold-backend alembic upgrade head
docker compose exec harold-db psql -U harold -d harold -c "\d wpn_ledger"
docker compose exec harold-db psql -U harold -d harold -c "SELECT system_code, next_index FROM wpn_sequences"
# All 21 codes present, next_index=1
```

Commit: `phase-3(harold-v2): ledger + audit migration + ORM models`.

---

## Phase 4 — REST API

### 4.1 `app/routers/health.py`

```
GET /health     → {"status": "healthy", "version": "2.0.0", "db": "ok"}
```

### 4.2 `app/routers/system_codes.py`

```
GET /api/v1/system-codes
  → {
      "codes": [
        {"code": "VH", "category": "project-system", "label": "Vehicle"},
        {"code": "FH", "category": "library-category", "label": "Fastener Hardware"},
        ...
      ]
    }
```

Categories: `project-system` for the original 17, `library-category` for FH/MH/EH/SH.

Labels are stored as a Python dict constant in code (no migration needed). Update as Wardstone's standard evolves.

### 4.3 `app/routers/wpn.py`

```
POST /api/v1/wpn/validate
  Body: {"wpn": "WS-FH-P000042-A"}
  Returns: {
    "wpn": "WS-FH-P000042-A",
    "is_valid_format": true,
    "is_issued": false,
    "errors": [],
    "warnings": [],
    "parsed": {"sys": "FH", "num": 42, "rev": "A"}
  }

POST /api/v1/wpn/validate-bulk
  Body: {"wpns": ["WS-FH-P000001-A", "WS-XX-P0001-A", ...]}
  Returns: list of WpnValidationResult

GET /api/v1/wpn/suggest?system_code=FH&hint=...
  Returns: {
    "suggested_wpn": "WS-FH-P000043-A",
    "system_code": "FH",
    "next_index": 43,
    "existing_count": 42
  }

POST /api/v1/wpn/issue
  Body: {
    "system_code": "FH",
    "origin_system": "astra",
    "origin_record_id": "42",
    "display_name": "McMaster 92196A196 socket head screw",
    "description": "...",
    "metadata": {...}
  }
  Returns: {
    "wpn": "WS-FH-P000043-A",
    "status": "active",
    "issued_at": "..."
  }
  Allocates next WPN, writes ledger row, returns. Atomic.

POST /api/v1/wpn/issue-specific
  Body: {"wpn": "WS-FH-P000042-A", "origin_system": "...", ...}
  Returns: same as above
  Used when caller already has a specific WPN in mind (e.g. ASTRA fallback
  allocation that needs to be registered after-the-fact). 409 if already issued.

PATCH /api/v1/wpn/{wpn}
  Body: {"display_name": "...", "description": "...", "metadata": {...}}
  Updates ledger metadata. WPN itself is immutable.

POST /api/v1/wpn/{wpn}/retire
  Body: {"reason": "..."}
  Marks status=retired. WPN is not deleted (audit trail preserved).

POST /api/v1/wpn/{wpn}/supersede
  Body: {"successor_wpn": "WS-FH-P000044-A", "reason": "..."}
  Marks status=superseded, sets superseded_by, audit emit.
```

### 4.4 `app/routers/ledger.py`

```
GET /api/v1/ledger?system_code=FH&status=active&q=...&skip=0&limit=200
  Returns: paginated list of ledger entries

GET /api/v1/ledger/{wpn}
  Returns: full ledger entry

GET /api/v1/ledger/export?format=csv
  Returns: CSV stream of all ledger entries
```

### 4.5 WRENCH compatibility shims

`app/wrench_shims/` — six tool handlers that match the existing tool surface but call the new REST API internally. From the perspective of WRENCH callers, behavior is identical. Document each shim's mapping in `docs/WRENCH_COMPATIBILITY.md`.

### 4.6 Backend tests

`tests/test_ledger_api.py`:
- Issue a WPN, see it in the ledger.
- Issue-specific with existing WPN → 409.
- Validate happy + sad path.
- Retire + supersede update status correctly.
- Audit log gets a row per write.
- List/filter/search.

`tests/test_wrench_shims.py`:
- Each WRENCH tool produces identical output to the documented current behavior on representative inputs.

Verify:
```powershell
docker compose exec harold-backend python -m pytest tests/ -v
# Manual smoke
curl.exe -X POST http://localhost:8030/api/v1/wpn/validate -H "Content-Type: application/json" -d '{\"wpn\":\"WS-FH-P000001-A\"}'
curl.exe http://localhost:8030/api/v1/system-codes
```

Commit: `phase-4(harold-v2): REST API + WRENCH shims + tests`.

---

## Phase 5 — Minimal browse UI

Jinja-rendered, server-side. Two views:

1. **Ledger list** at `GET /` — paginated table of all WPNs with filters (system code, status, search). Click a row → detail.
2. **WPN detail** at `GET /wpn/{wpn}` — full metadata, audit history, retire/supersede actions (links to API endpoints).

Templates in `app/ui/templates/`, static assets in `app/ui/static/`. Use the existing astra-surface dark aesthetic if you want to match Mason's design palette — but minimal UI is fine, the goal is "operators can see what's in the ledger," not "polished SPA."

CSS is small (~200 lines). No JS framework. Sprinkle of vanilla JS for the filter form.

Verify by visiting `http://localhost:8030/` in a browser, confirming the ledger view renders and filters work.

Commit: `phase-5(harold-v2): minimal browse UI`.

---

## Phase 6 — Deploy script update

Update `C:\Tools\harold\deploy.ps1` to:

1. Build the Docker image (`docker compose build`)
2. Push to a local registry if Mason has one, or skip if not (don't assume infrastructure that doesn't exist — surface and ask)
3. Mirror source files to `C:\opt\wrench\tools-dev\wardstone-harold` via robocopy `/MIR` (preserves existing pattern)
4. Restart the wrench HAROLD service (whatever mechanism wrench uses)

Document the manual sync workflow in `docs/DEPLOY_WORKFLOW.md`.

Commit: `phase-6(harold-v2): deploy.ps1 updated for docker structure`.

---

## Phase 7 — Migration of existing data (optional)

Per Phase 0 discovery, the current HAROLD has no persistent ledger — it's pure validation. So there are no existing WPNs to migrate. **Probably skip this phase entirely** unless Phase 0 reveals otherwise.

If WPNs exist in some form (e.g. issued in spreadsheets, in another system, hand-tracked), write a seed script `app/scripts/seed_existing_wpns.py` that reads them from a CSV and bulk-inserts into `wpn_ledger` with `origin_system='imported'`. Audit log emits a `ledger.bulk_imported` event.

Commit (if applicable): `phase-7(harold-v2): seed existing WPNs from CSV`.

---

## Phase 8 — Tests + completion notes

### 8.1 Final test pass

```powershell
docker compose exec harold-backend python -m pytest tests/ -v
# All green
```

### 8.2 End-to-end smoke

1. `docker compose up -d` brings both `harold-db` and `harold-backend` up healthy.
2. `curl http://localhost:8030/health` → 200.
3. `curl http://localhost:8030/api/v1/system-codes` lists 21 codes (17 project-system + 4 library-category).
4. `curl -X POST http://localhost:8030/api/v1/wpn/validate -d '{"wpn":"WS-FH-P000001-A"}'` returns `is_valid_format: true, is_issued: false`.
5. `curl -X POST http://localhost:8030/api/v1/wpn/issue -d '{"system_code":"FH","origin_system":"manual","display_name":"Test"}'` returns `WS-FH-P000001-A`.
6. Validate same WPN again → `is_issued: true`.
7. List ledger via `curl http://localhost:8030/api/v1/ledger?system_code=FH` → 1 entry.
8. Browse UI at `http://localhost:8030/` shows the entry.
9. Each WRENCH shim called with known-good input produces output matching the documented pre-V2 behavior.

### 8.3 Completion notes

`docs/PHASE_HAROLD_V2_COMPLETION_NOTES.md`:
- Per-phase commits.
- Phase 0 design choices and their rationale.
- End-to-end smoke results.
- Open follow-ups deferred:
  - **HAROLD-INTEGRATION-002** — the follow-up prompt that wires ASTRA into V2.
  - Auth on the REST API (currently LAN-only, no auth).
  - Replication / backup story for the `harold` database (currently local Docker volume only).
  - Webhook on WPN issuance (HAROLD → ASTRA push instead of pull) — future TDD.
  - Multi-revision support for WPNs beyond A-Z (currently A-Z only).
  - Reservation flow (reserve a WPN block for offline use; reconcile when reconnected).
  - Bulk operations UI in the browse interface.

Commit: `phase-8(harold-v2): tests + completion notes`.

---

## Out of scope — do NOT do these

1. **Don't touch ASTRA.** Integration is HAROLD-INTEGRATION-002, separate prompt.
2. **Don't keep the old WRENCH plugin entry point as the primary.** The new FastAPI service replaces it. WRENCH shims call the new API; they're not the service itself.
3. **Don't add auth.** v1 is LAN-only. Future TDD.
4. **Don't add a webhook system.** ASTRA polls HAROLD when needed; HAROLD polls ASTRA via the integration. No push-based system in v1.
5. **Don't build a rich SPA browse UI.** Minimal Jinja-rendered HTML is enough. The browse UI is a utility for HAROLD operators, not the main product.
6. **Don't add system codes beyond the 21 specified** (17 existing + FH/MH/EH/SH). If Wardstone wants more, that's a follow-up TDD with proper governance.
7. **Don't change the WPN format** beyond what AD-3 specifies.
8. **Don't refactor the deploy.ps1 mirror mechanism more than necessary.** Mason has it working; we just need to teach it the new Docker structure.

---

## Common gotchas

1. **Port 8030 conflicts.** If the current WRENCH plugin is running on 8030, the new container can't bind. Document the stop-old-start-new sequence in deploy.ps1.
2. **Postgres port collision.** ASTRA uses 5432; HAROLD's `harold-db` maps to host port 5433 to avoid clashing. Confirm this works with Mason's other tooling.
3. **Migration on every container start.** The Dockerfile CMD runs `alembic upgrade head` before starting uvicorn. Safe (Alembic is idempotent) but adds a few seconds to startup. If too slow, decouple via an init container.
4. **WPN regex special characters in CHECK constraint.** Postgres needs `~` for regex, escaping might bite. Test the CHECK constraint with a known-bad WPN insertion.
5. **Sequence allocator concurrency.** `SELECT ... FOR UPDATE` row-locks the sequence row. Two simultaneous allocators serialize correctly. Test with concurrent pytest-asyncio.
6. **WRENCH shim parity.** The current WRENCH plugin probably returns specific error message strings and JSON shapes that downstream callers depend on. Match them byte-for-byte. Document any unavoidable changes.
7. **Lowercase WPN inputs.** The regex requires uppercase. Decide policy: reject lowercase outright (strict), or `.upper()` then re-validate (lenient). Lenient is more forgiving but masks user errors. Go strict.
8. **Stale wrench copy.** `deploy.ps1` mirrors source files, but if the wrench copy is currently a running Python module, robocopy mirror doesn't restart it. Document the restart step.
9. **HAROLD_DATABASE_URL pointing to ASTRA's postgres.** If you go with shared-Postgres instead of separate `harold-db` container, the URL needs `?database=harold` and a separate role with limited privileges. Document the setup.
10. **CORS for the browse UI.** If anything outside the HAROLD container needs to call the UI's static assets, CORS applies. Default `cors_origins` covers `localhost:3000` and `:8000` so ASTRA-side iframes (future) work.
11. **JSONB metadata in `wpn_ledger.metadata_json`.** Don't store huge payloads. Cap at a few KB. If ASTRA wants to attach a big extracted_data dump, it can keep that on its side and just link by `origin_record_id`.

---

## Sign-off

```powershell
cd C:\Tools\harold
docker compose down
docker compose up -d --build
docker compose exec harold-backend python -m pytest tests/ -v

# All green → all phase commits → write docs/PHASE_HAROLD_V2_COMPLETION_NOTES.md
```

After Phase 8, HAROLD V2 is standalone-functional. ASTRA isn't wired in yet — that's HAROLD-INTEGRATION-002. Mason kicks off the follow-up prompt against the real V2 API after V2 ships clean.

If anything in this prompt conflicts with what's actually in the current HAROLD codebase (especially the WRENCH tool surfaces that Phase 0 documents), **stop and surface the conflict.** Don't refactor WRENCH itself; don't touch ASTRA; don't replace the deploy.ps1 mirror without preserving its existing destination structure.

---

*Prompt version 1.0 — supersedes the earlier `CLAUDE_CODE_PROMPT_HAROLD-001.md` and `CLAUDE_CODE_PROMPT_HAROLD-INTEGRATION-001.md` for the HAROLD-side work. The integration prompt will follow once V2 ships.*
