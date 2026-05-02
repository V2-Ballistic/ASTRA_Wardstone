# ASTRA Parts & Mechanical — Maximum Detail Addendum
# Supplements CLAUDE_CODE_PARTS_MECHANICAL_BUILD_PROMPT_DETAILED.md
# Read this file ALONGSIDE the primary prompt. Where this file and the primary conflict, this file wins.

---

## A. Exact Codebase Integration Reference

Before writing any code, read these existing files to understand the exact patterns already in use.
This addendum gives you the patterns extracted from those files so you do not have to re-read them.

### A.1 How existing routers are structured

All routers follow this exact skeleton (from `backend/app/routers/catalog.py`):

```python
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.dependencies.auth import get_current_user, require_any_role
from app.dependencies.project_access import project_member_required
from app.models.user import User, UserRole
from app.services.audit import audit_service

router = APIRouter()

# Every project-scoped endpoint:
@router.get("/", response_model=list[SomeResponse])
async def list_things(
    project_id: int,                              # from path
    limit: int = Query(default=50, le=200),       # always
    offset: int = Query(default=0, ge=0),         # always
    db: Session = Depends(get_db),
    current_user: User = Depends(project_member_required),  # project-scoped
):
    ...
```

`project_member_required` is in `backend/app/dependencies/project_access.py`. It reads `project_id` from the path parameter automatically. You do not pass it — it is extracted from the path. Look at how it is implemented before wiring new routers.

`require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)` is in `backend/app/dependencies/auth.py`. It returns a `User` object.

### A.2 How audit_service.log is called

Look at `backend/app/services/audit.py`. The `log` method signature is:

```python
await audit_service.log(
    db=db,
    actor=current_user,        # User object
    action="module.verb",      # dot-separated string
    entity_type="snake_case",  # matches table name convention
    entity_id=object.id,
    before_state=None,         # dict or None — serialized to JSON
    after_state=None,          # dict or None
)
```

Audit log is async — use `await`. If you are in a non-async context (background task), use `asyncio.run(audit_service.log(...))` or the sync variant if one exists. Check the existing code for the sync pattern.

### A.3 How background tasks use DB sessions

From `backend/app/services/` patterns:

```python
async def my_background_task(id: int):
    """Background tasks must create their own DB session."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        obj = db.query(MyModel).get(id)
        # ... do work ...
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
```

Never use the request-scoped `get_db()` session in a background task. It will be closed before the task runs.

### A.4 How existing documents are stored

Look at how `SupplierDocument` stores files in `backend/app/routers/catalog.py` (Phase 3 of INTF-002 work). The pattern is:

```python
import os, uuid

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/tmp/astra_uploads")

def _save_document_file(content: bytes, filename: str, checksum: str) -> str:
    """Save binary content to disk. Returns the file_path."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(filename)[1].lower()
    dest_filename = f"{checksum}{ext}"
    dest_path = os.path.join(UPLOAD_DIR, dest_filename)
    if not os.path.exists(dest_path):   # idempotent — same checksum = same file
        with open(dest_path, 'wb') as f:
            f.write(content)
    return dest_path
```

If a `Document` model already exists in the codebase (from ICD ingestion work in Phase 7 of INTF-002), use it. Check `backend/app/models/` for a `Document` or `SupplierDocument` model. If the existing model uses different field names than what is specified in this prompt, use the existing model's field names.

If no `Document` model exists, create a minimal one:

```python
class Document(Base):
    __tablename__ = "documents"
    id            = Column(Integer, primary_key=True)
    filename      = Column(String(500), nullable=False)
    file_path     = Column(String(1000), nullable=False)
    file_size_bytes = Column(BigInteger, nullable=False)
    sha256        = Column(String(64), nullable=False, index=True)
    mime_type     = Column(String(100), nullable=False)
    document_type = Column(String(100), nullable=True)
    uploaded_by_id= Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    uploaded_at   = Column(DateTime(timezone=True), server_default=func.now())
```

And add its table to the migration before `library_parts` (which references it).

### A.5 How AI services are called

The three-tier AI pattern is in `backend/app/services/ai/`. Look at how it is called in `backend/app/services/icd_extractor.py` (from Phase 7). The pattern:

```python
from app.services.ai import get_ai_service

async def my_ai_function(prompt: str) -> str:
    ai = get_ai_service()
    response = await ai.complete(
        system="Your system prompt here.",
        user=prompt,
        max_tokens=1000,
    )
    return response
```

If `get_ai_service()` does not exist, look for however the ICD extractor calls the AI API. Use the exact same calling convention. If no AI service exists at all, skip the AI interpretation pass and use only `_rules_fallback()` in the STEP parser — log a warning in the `extraction_log`.

### A.6 How the req_sync engine works (read carefully before Phase 2)

From `backend/app/services/req_sync/fan_out.py` and `listener.py` (Phase 5 of INTF-002):

The fan-out system works like this:
1. A SQLAlchemy `after_update` event fires when a source entity (Interface, WireHarness, etc.) is updated.
2. The listener calls `fan_out_to_source_links(connection, source_entity_type, source_entity_id)`.
3. `fan_out_to_source_links` queries `requirement_source_links` for all links with that entity type/id.
4. For each link, it calls `decide_action()` to determine whether to UPDATE, OBSOLETE, or SKIP.
5. If UPDATE or OBSOLETE: creates a `RequirementSyncProposal` record.
6. The user reviews proposals in the `/req-sync` UI page.

For `MechanicalJoint`, the pattern is identical. The `after_update` listener fires when a joint's fields change after it is ACTIVE. The `after_delete` listener marks sourced requirements as needing review.

The `contextvar` re-entrancy guard (`_get_listener_depth()`, `_increment_depth()`, `_decrement_depth()`) prevents infinite loops when the listener itself modifies data that would trigger another listener. Copy this pattern exactly.

Look at the exact function signatures in `fan_out.py` before writing the `_mj_after_update` listener. The function name and parameters may differ slightly from what is in the primary prompt.

### A.7 How `next_human_id` works

Used for generating requirement IDs like `SMDS-MECH-001`. Look at how it is implemented for existing requirement generation. It is likely in `backend/app/services/interface/auto_requirements.py` or similar. Find it and use the same function. The pattern generates the next sequential ID with a given prefix, checking existing `req_id` values to avoid collisions.

If the function signature is different from what is used in the `approve_joint` implementation in the primary prompt, use the actual function signature from the codebase.

### A.8 Existing `SQLEnum` import

```python
from sqlalchemy import Enum as SQLEnum
```

This is the import used throughout the codebase. The alias `SQLEnum` avoids collision with Python's `enum.Enum`. Confirm this is the pattern in the existing models before writing new ones.

---

## B. Complete Migration with Inline SQL Comments

This section provides the exact `upgrade()` function with every decision explained as a SQL comment. Use this to hand-write the migration precisely.

```sql
-- WHY: PostgreSQL cannot forward-reference enum types.
-- All enum types MUST be created before any table that uses them.
-- We use CREATE TYPE ... AS ENUM rather than inline column types
-- so that SQLAlchemy can reference them by name.

-- WHY: We prefix nothing on these enums because they do not collide with
-- existing ASTRA enum type names. Verify with:
-- SELECT typname FROM pg_type WHERE typtype = 'e';
-- before creating each one. If a collision exists, prefix with 'parts_'.

CREATE TYPE part_type AS ENUM (
    'fastener', 'washer', 'insert', 'bracket', 'enclosure', 'seal',
    'bearing', 'hinge_latch', 'thermal_interface', 'pcb_mechanical', 'custom'
);

CREATE TYPE part_status AS ENUM (
    'draft', 'under_review', 'approved', 'superseded', 'obsolete'
);

-- WHY: material_class is separate from part_type because a bracket can be
-- aluminum OR titanium. Separating them avoids a combinatorial explosion.
CREATE TYPE material_class AS ENUM (
    'aluminum', 'titanium', 'steel', 'stainless_steel', 'nickel_alloy',
    'polymer', 'composite', 'ceramic', 'other'
);

CREATE TYPE thread_standard AS ENUM (
    'iso_metric', 'unc', 'unf', 'npt', 'bspp', 'an_nas_ms', 'custom'
);

CREATE TYPE head_type AS ENUM (
    'socket', 'hex', 'pan', 'flat', 'button', 'torx', 'fillister', 'truss'
);

CREATE TYPE drive_type AS ENUM (
    'hex_key', 'torx', 'phillips', 'slotted', 'spanner', 'custom'
);

-- WHY: locking_feature is on both LibraryPart (what the part provides)
-- and MechanicalJoint (what the joint uses). They share this type.
CREATE TYPE locking_feature AS ENUM (
    'none', 'nylok', 'prevailing_torque', 'safety_wire', 'loctite',
    'castellated', 'lockwire_hole'
);

CREATE TYPE qualification_status AS ENUM (
    'unqualified', 'qual_testing', 'qualified', 'flight_proven', 'demanufactured'
);

CREATE TYPE pending_parts_status AS ENUM (
    'pending', 'under_review', 'approved', 'rejected'
);

-- WHY: confidence_level is shared by the parts import pipeline AND
-- the assembly parser. Centralizing it prevents drift.
CREATE TYPE confidence_level AS ENUM ('high', 'medium', 'low');

CREATE TYPE joint_type AS ENUM (
    'bolted', 'riveted', 'press_fit', 'adhesive', 'weld', 'seal',
    'alignment_pin', 'thermal_bond', 'spring_clip'
);

CREATE TYPE joint_status AS ENUM ('draft', 'active', 'superseded');

CREATE TYPE assembly_parse_job_status AS ENUM (
    'queued', 'running', 'complete', 'failed'
);

-- WHY: wpn_sequences is a simple counter table, one row per part type code.
-- SELECT FOR UPDATE on this table is the atomic WPN assignment mechanism.
-- No autoincrement — we need the prefix format "WS-FAST-000001-00".
CREATE TABLE wpn_sequences (
    part_type_code VARCHAR(8) PRIMARY KEY,
    next_val       INTEGER NOT NULL DEFAULT 1
        CHECK (next_val >= 1)
);

-- Seed immediately — all 11 part type codes.
-- If a row is missing at runtime, assign_wpn() creates it, but pre-seeding
-- avoids the INSERT on the hot path.
INSERT INTO wpn_sequences (part_type_code, next_val) VALUES
    ('FAST', 1), ('WASH', 1), ('INSR', 1), ('BRKT', 1), ('ENCL', 1),
    ('SEAL', 1), ('BEAR', 1), ('HNGL', 1), ('THIF', 1), ('PCBM', 1),
    ('CUST', 1);

-- WHY: library_parts uses Numeric(12,4) for ALL measurement fields.
-- Float is banned (F-031 from original audit). 12 digits total, 4 decimal places
-- is sufficient for fastener dimensions in mm (e.g. 999.9999 mm) and torques
-- in N·m (e.g. 9999.9999 N·m).
-- Exception: volume uses Numeric(18,4) because large enclosures can have
-- volumes in the millions of mm³.
CREATE TABLE library_parts (
    id                        SERIAL PRIMARY KEY,
    wardstone_part_number     VARCHAR(32)  NOT NULL UNIQUE,
    revision                  VARCHAR(2)   NOT NULL DEFAULT '00'
                                  CHECK (revision ~ '^[0-9]{2}$'),
    part_type                 part_type    NOT NULL,
    name                      VARCHAR(500) NOT NULL,
    description               TEXT,
    manufacturer_part_number  VARCHAR(200),
    manufacturer_name         VARCHAR(200),
    cage_code                 VARCHAR(10),
    nsn                       VARCHAR(20),
    drawing_number            VARCHAR(200),
    drawing_revision          VARCHAR(20),
    heritage                  TEXT,
    status                    part_status  NOT NULL DEFAULT 'draft',

    -- Supersession chain. Self-FK deferred to avoid chicken-and-egg on same-table insert.
    superseded_by_id          INTEGER REFERENCES library_parts(id) ON DELETE SET NULL
                                  DEFERRABLE INITIALLY DEFERRED,

    -- Dimensional — all Numeric, all nullable (extracted by parser)
    bounding_box_x_mm         NUMERIC(12,4),
    bounding_box_y_mm         NUMERIC(12,4),
    bounding_box_z_mm         NUMERIC(12,4),
    volume_mm3                NUMERIC(18,4),  -- larger precision for enclosures
    surface_area_mm2          NUMERIC(18,4),
    thread_size               VARCHAR(50),
    thread_standard           thread_standard,
    nominal_diameter_mm       NUMERIC(12,4),
    nominal_length_mm         NUMERIC(12,4),
    head_type                 head_type,
    drive_type                drive_type,
    nominal_bore_mm           NUMERIC(12,4),
    cross_section_dia_mm      NUMERIC(12,4),
    flange_diameter_mm        NUMERIC(12,4),
    hole_pattern_count        INTEGER CHECK (hole_pattern_count > 0),
    hole_pattern_dia_mm       NUMERIC(12,4),
    hole_pattern_pcd_mm       NUMERIC(12,4),

    -- Material
    material_name             VARCHAR(200),
    material_standard         VARCHAR(200),
    material_class            material_class,
    density_g_cm3             NUMERIC(10,4) CHECK (density_g_cm3 > 0),
    yield_strength_mpa        NUMERIC(10,2) CHECK (yield_strength_mpa >= 0),
    ultimate_strength_mpa     NUMERIC(10,2) CHECK (ultimate_strength_mpa >= 0),
    elastic_modulus_gpa       NUMERIC(10,2) CHECK (elastic_modulus_gpa > 0),
    hardness                  VARCHAR(50),
    thermal_conductivity_wm   NUMERIC(10,4) CHECK (thermal_conductivity_wm >= 0),
    cte_um_m_c                NUMERIC(10,4),  -- can be negative for some composites
    corrosion_protection      VARCHAR(200),
    flammability_class        VARCHAR(100),
    outgassing_tml_pct        NUMERIC(8,4) CHECK (outgassing_tml_pct >= 0),
    outgassing_cvcm_pct       NUMERIC(8,4) CHECK (outgassing_cvcm_pct >= 0),

    -- Performance
    mass_nominal_g            NUMERIC(12,4) CHECK (mass_nominal_g >= 0),
    mass_max_g                NUMERIC(12,4) CHECK (mass_max_g >= 0),
    proof_load_n              NUMERIC(12,2) CHECK (proof_load_n >= 0),
    clamp_load_n              NUMERIC(12,2) CHECK (clamp_load_n >= 0),
    torque_nominal_nm         NUMERIC(10,4) CHECK (torque_nominal_nm >= 0),
    torque_min_nm             NUMERIC(10,4) CHECK (torque_min_nm >= 0),
    torque_max_nm             NUMERIC(10,4) CHECK (torque_max_nm >= 0),
    torque_lubricated_nm      NUMERIC(10,4) CHECK (torque_lubricated_nm >= 0),
    locking_feature           locking_feature DEFAULT 'none',
    safety_wire_holes         BOOLEAN,
    shear_strength_n          NUMERIC(12,2) CHECK (shear_strength_n >= 0),
    bearing_load_n            NUMERIC(12,2) CHECK (bearing_load_n >= 0),
    compression_set_pct       NUMERIC(8,2)  CHECK (compression_set_pct BETWEEN 0 AND 100),
    sealing_pressure_max_bar  NUMERIC(10,3) CHECK (sealing_pressure_max_bar >= 0),
    temperature_min_c         NUMERIC(8,2),
    temperature_max_c         NUMERIC(8,2),
    -- CHECK: temperature range is valid
    CONSTRAINT chk_temp_range CHECK (
        temperature_min_c IS NULL OR temperature_max_c IS NULL OR
        temperature_min_c < temperature_max_c
    ),
    -- CHECK: torque range is valid
    CONSTRAINT chk_torque_range CHECK (
        torque_min_nm IS NULL OR torque_max_nm IS NULL OR
        torque_min_nm <= torque_max_nm
    ),
    -- CHECK: mass_max >= mass_nominal
    CONSTRAINT chk_mass_range CHECK (
        mass_nominal_g IS NULL OR mass_max_g IS NULL OR
        mass_max_g >= mass_nominal_g
    ),

    -- Procurement
    unit_cost_usd             NUMERIC(12,4) CHECK (unit_cost_usd >= 0),
    lead_time_weeks           INTEGER       CHECK (lead_time_weeks >= 0),
    min_order_qty             INTEGER       CHECK (min_order_qty >= 1),
    preferred_supplier_id     INTEGER       REFERENCES suppliers(id) ON DELETE SET NULL,
    supplier_part_number      VARCHAR(200),
    qualification_status      qualification_status DEFAULT 'unqualified',
    qualification_basis       TEXT,
    shelf_life_months         INTEGER       CHECK (shelf_life_months > 0),
    date_of_manufacture       DATE,
    restricted_use            BOOLEAN       NOT NULL DEFAULT FALSE,
    restriction_notes         TEXT,

    -- STEP traceability
    step_file_id              INTEGER       REFERENCES documents(id) ON DELETE SET NULL,
    step_file_checksum        VARCHAR(64),  -- SHA-256 hex
    step_entity_id            VARCHAR(200), -- '#PRODUCT_DEFINITION:42' format

    -- Approval chain
    approved_by_id            INTEGER       REFERENCES users(id) ON DELETE SET NULL,
    approved_at               TIMESTAMPTZ,
    CONSTRAINT chk_approved_fields CHECK (
        -- If status=approved, approved_by and approved_at must be set
        status != 'approved' OR (approved_by_id IS NOT NULL AND approved_at IS NOT NULL)
    ),

    -- Audit
    created_at                TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ   NOT NULL DEFAULT NOW(),
    created_by_id             INTEGER       REFERENCES users(id) ON DELETE SET NULL
);

-- WHY: The (part_type, status) composite index is for the default list query:
-- WHERE status = 'approved' AND part_type = ? 
-- This covers most of the query load on the list endpoint.
CREATE INDEX ix_library_part_type_status ON library_parts (part_type, status);

-- WHY: STEP checksum index is for the duplicate-detection query on upload:
-- WHERE step_file_checksum = ?
CREATE INDEX ix_library_part_step_checksum ON library_parts (step_file_checksum)
    WHERE step_file_checksum IS NOT NULL;

-- WHY: MPN index is for the picker modal search:
-- WHERE manufacturer_part_number ILIKE ?
-- ILIKE cannot use a standard B-tree index on the full value, but on short strings
-- (< 200 chars) it is fast enough. A GIN trigram index would be better for substring
-- search but requires pg_trgm extension — avoid unless confirmed available.
CREATE INDEX ix_library_part_mpn ON library_parts (manufacturer_part_number)
    WHERE manufacturer_part_number IS NOT NULL;


-- WHY: pending_parts_imports stores the raw extraction output from the STEP parser.
-- proposed_data is JSONB (not JSON) for GIN-indexable queries on field names.
-- low_confidence_fields is a PostgreSQL ARRAY(TEXT) for fast ANY() queries.
CREATE TABLE pending_parts_imports (
    id                    SERIAL PRIMARY KEY,
    document_id           INTEGER      NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    status                pending_parts_status NOT NULL DEFAULT 'pending',
    proposed_data         JSONB        NOT NULL DEFAULT '{}',
    confidence_scores     JSONB        NOT NULL DEFAULT '{}',
    low_confidence_fields TEXT[]       NOT NULL DEFAULT '{}',
    extraction_log        TEXT,
    parser_version        VARCHAR(32),
    reviewed_by_id        INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    reviewed_at           TIMESTAMPTZ,
    rejection_reason      TEXT,
    library_part_id       INTEGER      REFERENCES library_parts(id) ON DELETE SET NULL,
    created_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at            TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    created_by_id         INTEGER      REFERENCES users(id) ON DELETE SET NULL
);

CREATE INDEX ix_pending_parts_status ON pending_parts_imports (status);
CREATE INDEX ix_pending_parts_document ON pending_parts_imports (document_id);


-- WHY: project_parts is a pure join table with extra fields (quantity, designation).
-- ondelete=CASCADE on project_id: deleting a project removes all its part associations.
-- ondelete=RESTRICT on library_part_id: you cannot delete a library part that is in use.
-- The UNIQUE constraint prevents adding the same part twice to the same project.
CREATE TABLE project_parts (
    id               SERIAL      PRIMARY KEY,
    project_id       INTEGER     NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    library_part_id  INTEGER     NOT NULL REFERENCES library_parts(id) ON DELETE RESTRICT,
    quantity         INTEGER     NOT NULL DEFAULT 1 CHECK (quantity >= 1),
    designation      VARCHAR(64),
    notes            TEXT,
    added_by_id      INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    added_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (project_id, library_part_id)
);

CREATE INDEX ix_project_parts_project ON project_parts (project_id);
CREATE INDEX ix_project_parts_library ON project_parts (library_part_id);


-- WHY: system_part_assignments links a system to a project_part (not directly to a
-- library_part). This is correct: the same bolt (library_part) might be used in
-- both the primary structure (system A) and the payload adapter (system B) as two
-- distinct ProjectPart records.
CREATE TABLE system_part_assignments (
    id               SERIAL      PRIMARY KEY,
    system_id        INTEGER     NOT NULL REFERENCES systems(id) ON DELETE CASCADE,
    project_part_id  INTEGER     NOT NULL REFERENCES project_parts(id) ON DELETE CASCADE,
    position_order   INTEGER     NOT NULL DEFAULT 0,
    assigned_by_id   INTEGER     REFERENCES users(id) ON DELETE SET NULL,
    assigned_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (system_id, project_part_id)
);

CREATE INDEX ix_spa_system ON system_part_assignments (system_id);
CREATE INDEX ix_spa_ppart  ON system_part_assignments (project_part_id);


-- WHY: mechanical_joint_sequences is one row per project, tracking the next
-- sequential number for that project's joint IDs (MJ-0001-NNNNNN).
-- SELECT FOR UPDATE on this row prevents duplicate joint IDs under concurrent load.
CREATE TABLE mechanical_joint_sequences (
    project_id  INTEGER PRIMARY KEY,
    next_val    INTEGER NOT NULL DEFAULT 1 CHECK (next_val >= 1)
);


-- WHY: assembly_parse_jobs is a lightweight job tracking table.
-- progress_log is TEXT (not JSONB) so it can be appended to incrementally
-- without deserializing the whole document on every write.
-- result is JSONB to allow structured queries on the parse output.
CREATE TABLE assembly_parse_jobs (
    id           SERIAL      PRIMARY KEY,
    project_id   INTEGER     NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id  INTEGER     REFERENCES documents(id) ON DELETE SET NULL,
    status       assembly_parse_job_status NOT NULL DEFAULT 'queued',
    progress_log TEXT,
    result       JSONB,
    error        TEXT,
    created_by_id INTEGER    REFERENCES users(id) ON DELETE SET NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ
);

CREATE INDEX ix_apj_project ON assembly_parse_jobs (project_id);
CREATE INDEX ix_apj_status  ON assembly_parse_jobs (status) WHERE status IN ('queued','running');


-- WHY: mechanical_joints carries all joint configuration including torque
-- tolerances, engagement length, sealing requirements, and locking features.
-- All measurement fields: Numeric(10,4) for torque/length, Numeric(12,6) for
-- leak rate (very small numbers, e.g. 1.5e-6 scc/s).
-- joint_id is a VARCHAR(32) human-readable identifier, not the PK.
-- The PK (id) is used internally; joint_id is used in the UI and documents.
-- ondelete=RESTRICT on part_a_id and part_b_id: you cannot remove a project part
-- that is referenced by a joint. This protects data integrity at the DB level.
CREATE TABLE mechanical_joints (
    id                        SERIAL       PRIMARY KEY,
    joint_id                  VARCHAR(32)  NOT NULL UNIQUE,
    project_id                INTEGER      NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    joint_type                joint_type   NOT NULL,
    part_a_id                 INTEGER      NOT NULL
                                  REFERENCES project_parts(id) ON DELETE RESTRICT,
    part_b_id                 INTEGER      NOT NULL
                                  REFERENCES project_parts(id) ON DELETE RESTRICT,
    CONSTRAINT chk_parts_different CHECK (part_a_id != part_b_id),
    fastener_part_id          INTEGER      REFERENCES library_parts(id) ON DELETE SET NULL,
    fastener_count            INTEGER      CHECK (fastener_count > 0),
    torque_nominal_nm         NUMERIC(10,4) CHECK (torque_nominal_nm >= 0),
    torque_min_nm             NUMERIC(10,4) CHECK (torque_min_nm >= 0),
    torque_max_nm             NUMERIC(10,4) CHECK (torque_max_nm >= 0),
    engagement_length_mm      NUMERIC(10,4) CHECK (engagement_length_mm > 0),
    locking_feature           locking_feature,
    hole_pattern_description  VARCHAR(300),
    mating_surface_flatness_mm NUMERIC(10,4) CHECK (mating_surface_flatness_mm > 0),
    mating_surface_finish_ra  NUMERIC(10,4) CHECK (mating_surface_finish_ra > 0),
    seal_part_id              INTEGER      REFERENCES library_parts(id) ON DELETE SET NULL,
    leak_rate_max_scc_s       NUMERIC(12,6) CHECK (leak_rate_max_scc_s > 0),
    test_pressure_bar         NUMERIC(10,3) CHECK (test_pressure_bar > 0),
    interface_drawing         VARCHAR(200),
    source_step_file_id       INTEGER      REFERENCES documents(id) ON DELETE SET NULL,
    source_step_entity        TEXT,
    confidence                confidence_level,
    status                    joint_status NOT NULL DEFAULT 'draft',
    notes                     TEXT,
    created_at                TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at                TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    created_by_id             INTEGER      REFERENCES users(id) ON DELETE SET NULL,
    -- Cross-field constraints
    CONSTRAINT chk_torque_range CHECK (
        torque_min_nm IS NULL OR torque_max_nm IS NULL OR
        torque_min_nm <= torque_max_nm
    ),
    CONSTRAINT chk_bolted_has_fastener CHECK (
        joint_type != 'bolted' OR fastener_part_id IS NOT NULL OR
        status = 'draft'  -- allow draft bolted joints without fastener (fill in later)
    )
);

CREATE INDEX ix_mj_project_status ON mechanical_joints (project_id, status);
CREATE INDEX ix_mj_parts          ON mechanical_joints (part_a_id, part_b_id);
CREATE INDEX ix_mj_joint_id       ON mechanical_joints (joint_id);

-- WHY: Add library_part_id to units so that when a Unit is instantiated from
-- a CatalogPart AND the CatalogPart is linked to a LibraryPart (e.g. a mechanical
-- enclosure that has both an electrical catalog entry and a physical library entry),
-- the connection can be made. This is a nullable convenience FK.
ALTER TABLE units ADD COLUMN IF NOT EXISTS
    library_part_id INTEGER REFERENCES library_parts(id) ON DELETE SET NULL;

-- WHY: Extend the source_entity_type enum for the req_sync engine.
-- ADD VALUE IF NOT EXISTS is safe to run multiple times.
ALTER TYPE source_entity_type ADD VALUE IF NOT EXISTS 'mechanical_joint';
```

---

## C. Complete Pydantic Validators

Add these validators to `LibraryPartCreate` in `backend/app/schemas/parts_library.py`:

```python
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from decimal import Decimal, InvalidOperation
from typing import Optional, Any

class LibraryPartCreate(BaseModel):
    # ... (all fields from primary prompt) ...

    @field_validator(
        'bounding_box_x_mm', 'bounding_box_y_mm', 'bounding_box_z_mm',
        'volume_mm3', 'surface_area_mm2', 'nominal_diameter_mm',
        'nominal_length_mm', 'mass_nominal_g', 'mass_max_g',
        'torque_nominal_nm', 'torque_min_nm', 'torque_max_nm',
        'torque_lubricated_nm', 'density_g_cm3', 'yield_strength_mpa',
        'ultimate_strength_mpa', 'elastic_modulus_gpa',
        'thermal_conductivity_wm', 'unit_cost_usd',
        'hole_pattern_dia_mm', 'hole_pattern_pcd_mm',
        'shear_strength_n', 'bearing_load_n', 'sealing_pressure_max_bar',
        mode='before'
    )
    @classmethod
    def coerce_to_decimal(cls, v: Any) -> Optional[Decimal]:
        """Accept string or numeric input; convert to Decimal. Reject negatives."""
        if v is None or v == '':
            return None
        try:
            d = Decimal(str(v))
        except InvalidOperation:
            raise ValueError(f"Invalid numeric value: {v!r}")
        if d < 0:
            raise ValueError(f"Value must be non-negative, got {d}")
        return d

    @field_validator('temperature_min_c', 'temperature_max_c',
                     'cte_um_m_c', 'outgassing_tml_pct', 'outgassing_cvcm_pct',
                     'compression_set_pct', mode='before')
    @classmethod
    def coerce_to_decimal_allow_negative(cls, v: Any) -> Optional[Decimal]:
        """Temperature and CTE can be negative."""
        if v is None or v == '':
            return None
        try:
            return Decimal(str(v))
        except InvalidOperation:
            raise ValueError(f"Invalid numeric value: {v!r}")

    @field_validator('revision', mode='before')
    @classmethod
    def validate_revision(cls, v: Any) -> str:
        if v is None:
            return '00'
        s = str(v)
        if not s.isdigit() or len(s) != 2:
            raise ValueError("Revision must be two digits, e.g. '00', '01', '09'")
        return s

    @field_validator('cage_code', mode='before')
    @classmethod
    def validate_cage_code(cls, v: Any) -> Optional[str]:
        if v is None or v == '':
            return None
        code = str(v).upper().strip()
        if len(code) != 5:
            raise ValueError("CAGE code must be exactly 5 characters")
        return code

    @model_validator(mode='after')
    def validate_torque_range(self) -> 'LibraryPartCreate':
        if (self.torque_min_nm is not None and
                self.torque_max_nm is not None and
                self.torque_min_nm > self.torque_max_nm):
            raise ValueError(
                f"torque_min_nm ({self.torque_min_nm}) must be ≤ "
                f"torque_max_nm ({self.torque_max_nm})"
            )
        return self

    @model_validator(mode='after')
    def validate_temperature_range(self) -> 'LibraryPartCreate':
        if (self.temperature_min_c is not None and
                self.temperature_max_c is not None and
                self.temperature_min_c >= self.temperature_max_c):
            raise ValueError(
                f"temperature_min_c ({self.temperature_min_c}) must be < "
                f"temperature_max_c ({self.temperature_max_c})"
            )
        return self

    @model_validator(mode='after')
    def validate_mass_range(self) -> 'LibraryPartCreate':
        if (self.mass_nominal_g is not None and
                self.mass_max_g is not None and
                self.mass_max_g < self.mass_nominal_g):
            raise ValueError(
                f"mass_max_g ({self.mass_max_g}) must be ≥ "
                f"mass_nominal_g ({self.mass_nominal_g})"
            )
        return self


class MechanicalJointCreate(BaseModel):
    # ... (all fields from primary prompt) ...

    @model_validator(mode='after')
    def validate_parts_different(self) -> 'MechanicalJointCreate':
        if self.part_a_id == self.part_b_id:
            raise ValueError("part_a_id and part_b_id must be different parts")
        return self

    @model_validator(mode='after')
    def validate_torque_range(self) -> 'MechanicalJointCreate':
        if (self.torque_min_nm is not None and
                self.torque_max_nm is not None):
            t_min = Decimal(str(self.torque_min_nm))
            t_max = Decimal(str(self.torque_max_nm))
            if t_min > t_max:
                raise ValueError(
                    f"torque_min_nm ({t_min}) must be ≤ torque_max_nm ({t_max})"
                )
        return self

    @model_validator(mode='after')
    def validate_bolted_joint(self) -> 'MechanicalJointCreate':
        """A BOLTED joint without fastener_part_id is allowed (DRAFT filling in later)
        but must have fastener_count if fastener_part_id is set."""
        if (self.fastener_part_id is not None and
                self.fastener_count is not None and
                self.fastener_count < 1):
            raise ValueError("fastener_count must be ≥ 1")
        return self
```

---

## D. Complete Router Implementation Details

### D.1 `assign_joint_id` — exact implementation

```python
def _assign_joint_id(db: Session, project_id: int) -> str:
    """
    Thread-safe joint ID assignment using SELECT FOR UPDATE.
    Format: MJ-{project_id:04d}-{seq:06d}
    Example: MJ-0001-000042
    """
    seq = (
        db.query(MechanicalJointSequence)
        .filter(MechanicalJointSequence.project_id == project_id)
        .with_for_update()
        .first()
    )
    if seq is None:
        seq = MechanicalJointSequence(project_id=project_id, next_val=1)
        db.add(seq)
        db.flush()
    joint_id = f"MJ-{project_id:04d}-{seq.next_val:06d}"
    seq.next_val += 1
    return joint_id
```

### D.2 `_resolve_project_part` — exact implementation

```python
def _resolve_project_part(
    db: Session,
    project_id: int,
    step_entity_id: str,
    project_parts: list,
) -> Optional[ProjectPart]:
    """
    Match a STEP entity ID to a ProjectPart record.
    Matching order:
    1. Exact match on library_part.step_entity_id
    2. Fuzzy match on library_part.name vs the step_entity product name
    Returns the first match or None.
    """
    # Extract product name from step_entity_id if it contains it
    # Format: "#PRODUCT:42" or "product_name_string"
    for pp in project_parts:
        lp = pp.library_part
        if lp.step_entity_id and lp.step_entity_id == step_entity_id:
            return pp
        # Fuzzy: normalize both names and check containment
        entity_lower = step_entity_id.lower()
        part_name_lower = (lp.name or '').lower()
        if part_name_lower and part_name_lower in entity_lower:
            return pp
        if entity_lower in part_name_lower:
            return pp
    return None
```

### D.3 Complete `create_joint` endpoint

```python
@router.post("/", response_model=MechanicalJointResponse, status_code=201)
async def create_joint(
    project_id: int,
    data: MechanicalJointCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(project_member_required),
):
    """
    Create a mechanical joint manually. Status = DRAFT.
    Validates:
    - part_a and part_b belong to this project
    - fastener_part_id (if set) is an APPROVED FASTENER
    - seal_part_id (if set) is an APPROVED SEAL
    - part_a_id != part_b_id (Pydantic validator catches this, but double-check)
    """
    # Validate part_a belongs to this project
    part_a = db.query(ProjectPart).filter(
        ProjectPart.id == data.part_a_id,
        ProjectPart.project_id == project_id,
    ).first()
    if not part_a:
        raise HTTPException(
            422,
            {"detail": "part_a_id does not belong to this project",
             "code": "PART_NOT_IN_PROJECT"}
        )

    # Validate part_b belongs to this project
    part_b = db.query(ProjectPart).filter(
        ProjectPart.id == data.part_b_id,
        ProjectPart.project_id == project_id,
    ).first()
    if not part_b:
        raise HTTPException(
            422,
            {"detail": "part_b_id does not belong to this project",
             "code": "PART_NOT_IN_PROJECT"}
        )

    # Validate fastener part type and approval status
    if data.fastener_part_id:
        fastener = db.query(LibraryPart).get(data.fastener_part_id)
        if not fastener:
            raise HTTPException(422, {"detail": "fastener_part_id not found",
                                       "code": "PART_NOT_FOUND"})
        if fastener.part_type != PartType.FASTENER:
            raise HTTPException(
                422,
                {"detail": f"fastener_part_id references a {fastener.part_type.value}, "
                           f"not a fastener",
                 "code": "INVALID_FASTENER_TYPE"}
            )
        if fastener.status != PartStatus.APPROVED:
            raise HTTPException(
                422,
                {"detail": "Fastener must be APPROVED before use in a joint",
                 "code": "PART_NOT_APPROVED"}
            )

    # Validate seal part
    if data.seal_part_id:
        seal = db.query(LibraryPart).get(data.seal_part_id)
        if not seal:
            raise HTTPException(422, {"detail": "seal_part_id not found",
                                       "code": "PART_NOT_FOUND"})
        if seal.part_type != PartType.SEAL:
            raise HTTPException(
                422,
                {"detail": f"seal_part_id references a {seal.part_type.value}, not a seal",
                 "code": "INVALID_SEAL_TYPE"}
            )
        if seal.status != PartStatus.APPROVED:
            raise HTTPException(
                422,
                {"detail": "Seal must be APPROVED before use in a joint",
                 "code": "PART_NOT_APPROVED"}
            )

    # Assign joint ID
    joint_id = _assign_joint_id(db, project_id)

    # Create joint
    joint = MechanicalJoint(
        **data.model_dump(exclude_none=True),
        joint_id=joint_id,
        project_id=project_id,
        status=JointStatus.DRAFT,
        created_by_id=current_user.id,
    )
    db.add(joint)
    db.commit()
    db.refresh(joint)

    # Eager-load relationships for response serialization
    db.refresh(joint)
    if joint.fastener_part_id:
        _ = joint.fastener_part
    if joint.seal_part_id:
        _ = joint.seal_part

    await audit_service.log(
        db=db, actor=current_user,
        action="mechanical_joints.joint_created",
        entity_type="mechanical_joint", entity_id=joint.id,
        after_state={
            "joint_id": joint.joint_id,
            "joint_type": joint.joint_type.value,
            "part_a_id": joint.part_a_id,
            "part_b_id": joint.part_b_id,
        },
    )
    return joint
```

### D.4 `list_joints` endpoint with full selectinload

```python
@router.get("/", response_model=list[MechanicalJointResponse])
async def list_joints(
    project_id: int,
    joint_type: Optional[JointType] = Query(None),
    status: Optional[JointStatus] = Query(None),
    confidence: Optional[ConfidenceLevel] = Query(None),
    part_id: Optional[int] = Query(None, description="Filter by part_a_id or part_b_id"),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(project_member_required),
):
    from sqlalchemy.orm import selectinload

    query = (
        db.query(MechanicalJoint)
        .options(
            selectinload(MechanicalJoint.part_a)
                .selectinload(ProjectPart.library_part),
            selectinload(MechanicalJoint.part_b)
                .selectinload(ProjectPart.library_part),
            selectinload(MechanicalJoint.fastener_part),
            selectinload(MechanicalJoint.seal_part),
        )
        .filter(MechanicalJoint.project_id == project_id)
    )

    if joint_type:
        query = query.filter(MechanicalJoint.joint_type == joint_type)
    if status:
        query = query.filter(MechanicalJoint.status == status)
    else:
        # Default: exclude superseded
        query = query.filter(MechanicalJoint.status != JointStatus.SUPERSEDED)
    if confidence:
        query = query.filter(MechanicalJoint.confidence == confidence)
    if part_id:
        query = query.filter(
            or_(
                MechanicalJoint.part_a_id == part_id,
                MechanicalJoint.part_b_id == part_id,
            )
        )

    query = query.order_by(MechanicalJoint.created_at.desc())
    return query.offset(offset).limit(limit).all()
```

### D.5 `delete_joint` endpoint with soft-delete logic

```python
@router.delete("/{joint_id}", status_code=204)
async def delete_joint(
    project_id: int,
    joint_id: str,
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: User = Depends(project_member_required),
):
    joint = db.query(MechanicalJoint).filter(
        MechanicalJoint.joint_id == joint_id,
        MechanicalJoint.project_id == project_id,
    ).first()
    if not joint:
        raise HTTPException(404, "Joint not found")

    if joint.status == JointStatus.SUPERSEDED:
        raise HTTPException(
            409,
            {"detail": "Joint is already superseded", "code": "WRONG_STATE"}
        )

    if joint.status == JointStatus.DRAFT:
        # Hard delete DRAFT joints — no requirements linked to them
        db.delete(joint)
        db.commit()
        await audit_service.log(
            db=db, actor=current_user,
            action="mechanical_joints.joint_deleted",
            entity_type="mechanical_joint", entity_id=joint.id,
            before_state={"joint_id": joint_id, "status": "draft"},
        )
        return

    # ACTIVE joint
    if not force:
        raise HTTPException(
            409,
            {
                "detail": (
                    "Active joints cannot be deleted without force=true. "
                    "This joint has auto-generated requirements linked to it. "
                    "Deleting it will mark those requirements for review."
                ),
                "code": "ACTIVE_JOINT_REQUIRES_FORCE",
            }
        )

    # force=True: only admin can force-delete active joints
    if not current_user.is_admin:
        raise HTTPException(
            403,
            {"detail": "Only admins can force-delete active joints",
             "code": "INSUFFICIENT_ROLE"}
        )

    # Soft delete: set status = SUPERSEDED (triggers after_update listener
    # which will mark sourced requirements for review)
    before_state = {"joint_id": joint_id, "status": "active"}
    joint.status = JointStatus.SUPERSEDED
    db.commit()

    await audit_service.log(
        db=db, actor=current_user,
        action="mechanical_joints.joint_deleted",
        entity_type="mechanical_joint", entity_id=joint.id,
        before_state=before_state,
        after_state={"joint_id": joint_id, "status": "superseded", "force": True},
    )
```

---

## E. Complete Test Implementations

Every test function below is a complete implementation. Replace the stub names in the primary prompt with these.

```python
# backend/tests/test_parts_library.py

import pytest
import threading
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.main import app
from app.models.parts_library import (
    LibraryPart, WPNSequence, PendingPartsImport, PartType, PartStatus,
    PendingPartsStatus
)
from app.services.parts.wpn_service import assign_wpn, bump_revision
from app.services.parts.step_parser import (
    parse_step_file, match_thread, _rules_fallback, StepParserResult,
    THREAD_TABLE
)
from app.models.parts_library import ThreadStandard, ConfidenceLevel
from tests.conftest import auth_headers, admin_headers, pm_headers, dev_headers


# ── WPN Tests ─────────────────────────────────────────────────────────────────

def test_wpn_assignment_unique_sequential(db: Session):
    """Five sequential FASTENER WPNs must be WS-FAST-000001-00 through 000005-00."""
    # Reset sequence for test isolation
    seq = db.query(WPNSequence).filter_by(part_type_code="FAST").with_for_update().first()
    if seq:
        seq.next_val = 1
    db.commit()

    wpns = [assign_wpn(db, PartType.FASTENER) for _ in range(5)]
    db.commit()

    assert wpns[0] == "WS-FAST-000001-00"
    assert wpns[1] == "WS-FAST-000002-00"
    assert wpns[4] == "WS-FAST-000005-00"
    # All unique
    assert len(set(wpns)) == 5


def test_wpn_bump_revision():
    """bump_revision must increment the RR suffix correctly."""
    assert bump_revision("WS-FAST-000042-00") == "WS-FAST-000042-01"
    assert bump_revision("WS-FAST-000042-09") == "WS-FAST-000042-10"
    assert bump_revision("WS-BRKT-000001-05") == "WS-BRKT-000001-06"


def test_wpn_type_codes_cover_all_part_types():
    """Every PartType member must have a corresponding WPN type code."""
    from app.services.parts.wpn_service import WPN_TYPE_CODES
    for pt in PartType:
        assert pt in WPN_TYPE_CODES, f"Missing WPN type code for {pt}"
        code = WPN_TYPE_CODES[pt]
        assert len(code) == 4, f"WPN type code must be 4 chars, got '{code}' for {pt}"


def test_wpn_assignment_race_condition(db_factory):
    """
    Two concurrent threads must not produce duplicate WPNs.
    Uses db_factory to get two independent DB sessions.
    """
    results = []
    errors = []

    def assign_one():
        db = db_factory()
        try:
            wpn = assign_wpn(db, PartType.WASHER)
            db.commit()
            results.append(wpn)
        except Exception as e:
            errors.append(e)
        finally:
            db.close()

    # Reset WASH sequence
    db = db_factory()
    seq = db.query(WPNSequence).filter_by(part_type_code="WASH").with_for_update().first()
    if seq:
        seq.next_val = 1
    db.commit()
    db.close()

    t1 = threading.Thread(target=assign_one)
    t2 = threading.Thread(target=assign_one)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert not errors, f"Thread errors: {errors}"
    assert len(results) == 2
    assert results[0] != results[1], "Duplicate WPNs produced under concurrent load"
    assert len(set(results)) == 2


# ── API Tests — Parts Library CRUD ──────────────────────────────────────────

def test_create_part_manually_assigns_wpn(client: TestClient, pm_headers: dict):
    """POST /parts-library/ creates a DRAFT part with an assigned WPN."""
    resp = client.post(
        "/api/v1/parts-library/",
        json={
            "part_type": "washer",
            "name": "M6 Flat Washer",
            "nominal_diameter_mm": "6.5",
            "material_name": "A2 Stainless Steel",
            "material_class": "stainless_steel",
        },
        headers=pm_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["wardstone_part_number"].startswith("WS-WASH-")
    assert data["wardstone_part_number"].endswith("-00")
    assert data["status"] == "draft"
    assert data["part_type"] == "washer"
    assert data["name"] == "M6 Flat Washer"
    assert data["approved_at"] is None  # DRAFT — not yet approved


def test_approved_part_requires_pm_or_admin(client: TestClient, dev_headers: dict):
    """Developer role cannot create library parts."""
    resp = client.post(
        "/api/v1/parts-library/",
        json={"part_type": "fastener", "name": "Test"},
        headers=dev_headers,
    )
    assert resp.status_code == 403


def test_list_parts_returns_approved_only_by_default(
    client: TestClient, admin_headers: dict, db: Session
):
    """Default list returns only APPROVED parts."""
    # Create parts in different statuses
    from app.services.parts.wpn_service import assign_wpn
    for status, ptype in [
        (PartStatus.APPROVED, PartType.FASTENER),
        (PartStatus.APPROVED, PartType.WASHER),
        (PartStatus.DRAFT, PartType.BRACKET),
        (PartStatus.SUPERSEDED, PartType.SEAL),
    ]:
        wpn = assign_wpn(db, ptype)
        db.add(LibraryPart(
            wardstone_part_number=wpn, revision="00",
            part_type=ptype, name=f"Test {ptype.value}",
            status=status,
            approved_by_id=1 if status == PartStatus.APPROVED else None,
            approved_at=func.now() if status == PartStatus.APPROVED else None,
        ))
    db.commit()

    resp = client.get("/api/v1/parts-library/", headers=admin_headers)
    assert resp.status_code == 200
    parts = resp.json()
    # All returned parts must be APPROVED
    for p in parts:
        assert p["status"] == "approved", f"Non-approved part in default list: {p}"


def test_list_parts_filter_by_type(
    client: TestClient, admin_headers: dict, db: Session
):
    """Filter by part_type=fastener returns only fasteners."""
    resp = client.get(
        "/api/v1/parts-library/",
        params={"part_type": "fastener", "status": "approved"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    for p in resp.json():
        assert p["part_type"] == "fastener"


def test_search_by_name_ilike(client: TestClient, admin_headers: dict, db: Session):
    """Search finds parts by name substring (case-insensitive)."""
    from app.services.parts.wpn_service import assign_wpn
    wpn = assign_wpn(db, PartType.FASTENER)
    db.add(LibraryPart(
        wardstone_part_number=wpn, revision="00",
        part_type=PartType.FASTENER,
        name="TITANIUM HEX BOLT M5",
        manufacturer_part_number="TI-M5-HB-001",
        status=PartStatus.APPROVED,
        approved_by_id=1, approved_at=func.now(),
    ))
    db.commit()

    resp = client.get(
        "/api/v1/parts-library/",
        params={"search": "titanium hex", "status": "approved"},
        headers=admin_headers,
    )
    assert resp.status_code == 200
    assert any("TITANIUM HEX BOLT" in p["name"] for p in resp.json())

    # Also finds by MPN
    resp2 = client.get(
        "/api/v1/parts-library/",
        params={"search": "TI-M5", "status": "approved"},
        headers=admin_headers,
    )
    assert resp2.status_code == 200
    assert any("TI-M5-HB-001" in p.get("manufacturer_part_number", "") for p in resp2.json())


def test_update_draft_part_in_place(
    client: TestClient, pm_headers: dict, db: Session
):
    """Patching a DRAFT part updates it in-place — no new revision row."""
    from app.services.parts.wpn_service import assign_wpn
    wpn = assign_wpn(db, PartType.FASTENER)
    part = LibraryPart(
        wardstone_part_number=wpn, revision="00",
        part_type=PartType.FASTENER, name="Old Name",
        status=PartStatus.DRAFT,
    )
    db.add(part)
    db.commit()
    original_id = part.id

    resp = client.patch(
        f"/api/v1/parts-library/{original_id}",
        json={"name": "New Name", "torque_nominal_nm": "9.8"},
        headers=pm_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == original_id       # same row
    assert data["name"] == "New Name"
    assert data["wardstone_part_number"] == wpn   # WPN unchanged
    # No new rows
    count = db.query(LibraryPart).filter(
        LibraryPart.wardstone_part_number.like(wpn.rsplit("-",1)[0] + "%")
    ).count()
    assert count == 1


def test_update_approved_part_dimensional_creates_revision(
    client: TestClient, pm_headers: dict, db: Session
):
    """Patching a dimensional field on APPROVED part creates a new revision row."""
    from app.services.parts.wpn_service import assign_wpn
    wpn = assign_wpn(db, PartType.FASTENER)
    part = LibraryPart(
        wardstone_part_number=wpn, revision="00",
        part_type=PartType.FASTENER, name="Socket Head Screw M4",
        status=PartStatus.APPROVED,
        approved_by_id=1, approved_at=func.now(),
        torque_nominal_nm=Decimal("2.9"),
    )
    db.add(part)
    db.commit()

    resp = client.patch(
        f"/api/v1/parts-library/{part.id}",
        json={"torque_nominal_nm": "3.2"},  # dimensional change → new revision
        headers=pm_headers,
    )
    assert resp.status_code == 200
    data = resp.json()

    # New revision row created
    new_wpn = data["wardstone_part_number"]
    assert new_wpn.endswith("-01"), f"Expected -01 revision, got {new_wpn}"
    assert data["status"] == "draft"   # new revision must be re-approved
    assert data["torque_nominal_nm"] == "3.2"

    # Old row is now SUPERSEDED
    db.refresh(part)
    assert part.status == PartStatus.SUPERSEDED
    assert part.superseded_by_id == data["id"]


# ── STEP Upload Tests ─────────────────────────────────────────────────────────

MINIMAL_STEP = b"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Test part'),'2;1');
FILE_NAME('test.step','2024-01-01T00:00:00',('ASTRA'),('Test'),'','','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1=PRODUCT('M4-SCREW','Socket Head Cap Screw','',(#2));
#2=PRODUCT_CONTEXT('MECHANICAL',#3,'mechanical');
#3=APPLICATION_CONTEXT('automotive design');
ENDSEC;
END-ISO-10303-21;
"""


def test_upload_step_creates_pending_import(
    client: TestClient, pm_headers: dict
):
    """Valid STEP file upload returns pending_import_id."""
    import io
    resp = client.post(
        "/api/v1/parts-library/upload-step",
        files={"file": ("test_part.step", io.BytesIO(MINIMAL_STEP), "application/step")},
        headers=pm_headers,
    )
    assert resp.status_code == 202, resp.text
    data = resp.json()
    assert data["duplicate"] is False
    assert "pending_import_id" in data
    assert isinstance(data["pending_import_id"], int)


def test_upload_non_step_rejected(client: TestClient, pm_headers: dict):
    """Non-STEP files are rejected with INVALID_FILE_TYPE."""
    import io
    resp = client.post(
        "/api/v1/parts-library/upload-step",
        files={"file": ("drawing.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
        headers=pm_headers,
    )
    assert resp.status_code == 400
    assert resp.json()["code"] == "INVALID_FILE_TYPE"


def test_upload_duplicate_step_returns_existing(
    client: TestClient, pm_headers: dict, db: Session
):
    """Uploading the same file twice returns duplicate=True."""
    import io, hashlib
    checksum = hashlib.sha256(MINIMAL_STEP).hexdigest()

    # First upload
    r1 = client.post(
        "/api/v1/parts-library/upload-step",
        files={"file": ("part.step", io.BytesIO(MINIMAL_STEP), "application/step")},
        headers=pm_headers,
    )
    assert r1.status_code == 202

    # Second upload — same file
    r2 = client.post(
        "/api/v1/parts-library/upload-step",
        files={"file": ("part_copy.step", io.BytesIO(MINIMAL_STEP), "application/step")},
        headers=pm_headers,
    )
    assert r2.status_code in (200, 202)
    assert r2.json()["duplicate"] is True


def test_approve_import_assigns_wpn(
    client: TestClient, pm_headers: dict, db: Session
):
    """Approving a pending import creates a LibraryPart with WPN assigned."""
    from app.models.parts_library import PendingPartsImport, PendingPartsStatus
    # Create a pending import directly in DB (simulates completed parser)
    doc = _create_test_document(db)
    pending = PendingPartsImport(
        document_id=doc.id,
        status=PendingPartsStatus.PENDING,
        proposed_data={
            "name": "M6 Socket Head Screw",
            "part_type": "fastener",
            "manufacturer_part_number": "SHC-M6-16-SS",
            "thread_size": "M6×1.0",
            "thread_standard": "iso_metric",
            "torque_nominal_nm": "9.8",
        },
        confidence_scores={
            "name": "high",
            "part_type": "high",
            "thread_size": "high",
            "torque_nominal_nm": "medium",
        },
        low_confidence_fields=[],
        created_by_id=1,
    )
    db.add(pending)
    db.commit()

    resp = client.post(
        f"/api/v1/parts-library/pending-imports/{pending.id}/approve",
        json={"overrides": {}},
        headers=pm_headers,
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["wardstone_part_number"].startswith("WS-FAST-")
    assert data["wardstone_part_number"].endswith("-00")
    assert data["status"] == "approved"
    assert data["approved_by_id"] is not None
    assert data["name"] == "M6 Socket Head Screw"
    assert data["torque_nominal_nm"] == "9.8"

    # Verify pending import status updated
    db.refresh(pending)
    assert pending.status == PendingPartsStatus.APPROVED
    assert pending.library_part_id == data["id"]


def test_approve_import_with_overrides_uses_overrides(
    client: TestClient, pm_headers: dict, db: Session
):
    """Override values take precedence over proposed_data."""
    doc = _create_test_document(db)
    pending = PendingPartsImport(
        document_id=doc.id,
        status=PendingPartsStatus.PENDING,
        proposed_data={"name": "Wrong Name", "part_type": "fastener"},
        confidence_scores={},
        low_confidence_fields=[],
        created_by_id=1,
    )
    db.add(pending)
    db.commit()

    resp = client.post(
        f"/api/v1/parts-library/pending-imports/{pending.id}/approve",
        json={"overrides": {"name": "Correct Override Name", "torque_nominal_nm": "12.5"}},
        headers=pm_headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Correct Override Name"
    assert Decimal(data["torque_nominal_nm"]) == Decimal("12.5")


def test_approve_import_idempotent(
    client: TestClient, pm_headers: dict, db: Session
):
    """Approving an already-approved import returns the existing part."""
    doc = _create_test_document(db)
    pending = PendingPartsImport(
        document_id=doc.id,
        status=PendingPartsStatus.PENDING,
        proposed_data={"name": "Part X", "part_type": "bracket"},
        confidence_scores={}, low_confidence_fields=[], created_by_id=1,
    )
    db.add(pending)
    db.commit()

    # First approve
    r1 = client.post(
        f"/api/v1/parts-library/pending-imports/{pending.id}/approve",
        json={"overrides": {}}, headers=pm_headers,
    )
    assert r1.status_code == 200
    first_id = r1.json()["id"]
    first_wpn = r1.json()["wardstone_part_number"]

    # Second approve — must return the same part
    r2 = client.post(
        f"/api/v1/parts-library/pending-imports/{pending.id}/approve",
        json={"overrides": {}}, headers=pm_headers,
    )
    assert r2.status_code == 200
    assert r2.json()["id"] == first_id
    assert r2.json()["wardstone_part_number"] == first_wpn


def test_reject_import(client: TestClient, pm_headers: dict, db: Session):
    """Rejection sets status=rejected and stores reason."""
    doc = _create_test_document(db)
    pending = PendingPartsImport(
        document_id=doc.id,
        status=PendingPartsStatus.PENDING,
        proposed_data={"name": "Reject Me", "part_type": "washer"},
        confidence_scores={}, low_confidence_fields=[], created_by_id=1,
    )
    db.add(pending)
    db.commit()

    resp = client.post(
        f"/api/v1/parts-library/pending-imports/{pending.id}/reject",
        json={"reason": "Incorrect part geometry — does not match drawing"},
        headers=pm_headers,
    )
    assert resp.status_code == 200 or resp.status_code == 204

    db.refresh(pending)
    assert pending.status == PendingPartsStatus.REJECTED
    assert "Incorrect part geometry" in pending.rejection_reason


def test_approve_import_missing_name_fails(
    client: TestClient, pm_headers: dict, db: Session
):
    """Approving without a name field raises 422 MISSING_REQUIRED_FIELD."""
    doc = _create_test_document(db)
    pending = PendingPartsImport(
        document_id=doc.id,
        status=PendingPartsStatus.PENDING,
        proposed_data={"part_type": "fastener"},  # no name
        confidence_scores={}, low_confidence_fields=[], created_by_id=1,
    )
    db.add(pending)
    db.commit()

    resp = client.post(
        f"/api/v1/parts-library/pending-imports/{pending.id}/approve",
        json={"overrides": {}}, headers=pm_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "MISSING_REQUIRED_FIELD"


# ── STEP Parser Unit Tests ────────────────────────────────────────────────────

def test_thread_table_m6_match():
    """6.55mm clearance hole maps to M6×1.0 with torque 9.8 N·m."""
    result = match_thread(Decimal("6.55"))
    assert result is not None
    size, standard, torque = result
    assert size == "M6×1.0"
    assert standard == ThreadStandard.ISO_METRIC
    assert torque == Decimal("9.8")


def test_thread_table_unf_match():
    """6.47mm clearance hole maps to 1/4-28 UNF."""
    result = match_thread(Decimal("6.47"))
    assert result is not None
    size, standard, torque = result
    assert "1/4-28" in size
    assert standard == ThreadStandard.UNF


def test_thread_table_no_match():
    """99mm clearance hole does not match any thread."""
    assert match_thread(Decimal("99.0")) is None
    assert match_thread(Decimal("0.5")) is None
    assert match_thread(Decimal("50.0")) is None


def test_thread_table_all_within_bounds():
    """All entries in THREAD_TABLE have valid dia ranges and positive torque."""
    for lo, hi, size, std, torque in THREAD_TABLE:
        assert lo < hi, f"Invalid range [{lo}, {hi}] for {size}"
        assert torque > 0, f"Non-positive torque {torque} for {size}"
        assert std in ThreadStandard


def test_parse_step_metadata_only():
    """parse_step_file extracts product name from STEP text even without OCC."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.step', delete=False,
                                     mode='wb') as f:
        f.write(MINIMAL_STEP)
        path = f.name
    try:
        result = parse_step_file(path)
        assert result.product_name is not None
        assert "M4-SCREW" in result.product_name or "M4" in (result.product_name or "")
    finally:
        os.unlink(path)


def test_parse_step_marks_geometry_low_confidence_without_occ():
    """Without OCC, all geometry fields have LOW confidence."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(suffix='.step', delete=False, mode='wb') as f:
        f.write(MINIMAL_STEP)
        path = f.name
    try:
        result = parse_step_file(path)
        if not result.occ_available:
            for geo_field in ["bounding_box_x_mm", "volume_mm3", "thread_size"]:
                assert result.confidence_scores.get(geo_field) == "low" or \
                       geo_field in result.low_confidence_fields
    finally:
        os.unlink(path)


# ── AI Rules Fallback Tests ───────────────────────────────────────────────────

def test_rules_fallback_classifies_screw_as_fastener():
    r = StepParserResult(product_name="M6 Socket Head Cap Screw")
    result = _rules_fallback(r)
    assert result["part_type"] == "fastener"


def test_rules_fallback_classifies_washer():
    r = StepParserResult(product_name="M6 Flat Washer ISO 7089")
    result = _rules_fallback(r)
    assert result["part_type"] == "washer"


def test_rules_fallback_classifies_bearing():
    r = StepParserResult(product_name="6002-2Z Deep Groove Ball Bearing")
    result = _rules_fallback(r)
    assert result["part_type"] == "bearing"


def test_rules_fallback_detects_nylok():
    r = StepParserResult(product_name="M4 Nylok Hex Screw")
    result = _rules_fallback(r)
    assert result["locking_feature"] == "nylok"


def test_rules_fallback_detects_prevailing_torque():
    r = StepParserResult(product_name="M5 Prevailing Torque Nut ISO 7042")
    result = _rules_fallback(r)
    assert result["locking_feature"] == "prevailing_torque"


def test_rules_fallback_ti_6al_4v_material():
    r = StepParserResult(product_name="M5 Ti-6Al-4V Socket Head Screw")
    result = _rules_fallback(r)
    assert result["material_class"] == "titanium"
    assert "Ti-6Al-4V" in (result["material_name"] or "")


def test_rules_fallback_propagates_torque_from_thread_match():
    r = StepParserResult(
        product_name="M6 Screw",
        torque_nominal_nm=Decimal("9.8")
    )
    result = _rules_fallback(r)
    assert result["torque_nominal_nm"] == float(Decimal("9.8"))
    assert result["torque_min_nm"] == pytest.approx(float(Decimal("9.8")) * 0.85, abs=0.01)
    assert result["torque_max_nm"] == pytest.approx(float(Decimal("9.8")) * 1.10, abs=0.01)


def test_rules_fallback_unknown_part_defaults_to_custom():
    r = StepParserResult(product_name="XJ-9000 Undefined Component")
    result = _rules_fallback(r)
    assert result["part_type"] == "custom"
    assert result["confidence_overrides"].get("part_type") == "low"
    assert len(result["flags"]) > 0


# ── Template Rendering Tests ──────────────────────────────────────────────────

def test_render_mech_bolt_001_full_context():
    from app.services.parts.mechanical_req_templates import render_template

    context = {
        "part_a_name": "Main Structure Panel",
        "part_b_name": "Avionics Bay Cover",
        "fastener_description": "M6×16 Socket Head Cap Screw A286",
        "fastener_count": 4,
        "torque_nominal_nm": "9.8",
        "torque_tolerance_nm": "0.8",
    }
    result = render_template("MECH-BOLT-001", context)
    assert result is not None
    assert "Main Structure Panel" in result
    assert "Avionics Bay Cover" in result
    assert "4×" in result
    assert "9.8 N·m" in result
    assert "{" not in result, "Unresolved template tokens in rendered string"
    assert "}" not in result


def test_render_template_missing_context_substitutes_tbd():
    from app.services.parts.mechanical_req_templates import render_template
    result = render_template("MECH-BOLT-001", {})
    assert result is not None
    assert "TBD" in result
    # No KeyError should be raised
    assert "{" not in result


def test_render_unknown_template_returns_none():
    from app.services.parts.mechanical_req_templates import render_template
    assert render_template("MECH-NONEXISTENT-999", {}) is None


def test_all_templates_render_with_tbd_context():
    """Every template ID must render without error when context is empty."""
    from app.services.parts.mechanical_req_templates import TEMPLATES, render_template
    for template_id in TEMPLATES:
        result = render_template(template_id, {})
        assert result is not None, f"Template {template_id} returned None"
        assert "{" not in result, \
            f"Template {template_id} has unresolved tokens: {result}"


def test_joint_type_templates_map_all_joint_types():
    """Every JointType must have a (possibly empty) list in JOINT_TYPE_TEMPLATES."""
    from app.services.parts.mechanical_req_templates import JOINT_TYPE_TEMPLATES
    from app.models.parts_library import JointType
    for jt in JointType:
        assert jt in JOINT_TYPE_TEMPLATES, f"Missing template map for {jt}"
```

---

```python
# backend/tests/test_project_parts.py

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.parts_library import (
    ProjectPart, LibraryPart, SystemPartAssignment,
    MechanicalJoint, JointStatus, JointType, PartType, PartStatus
)
from tests.conftest import pm_headers, dev_headers, make_approved_library_part


def test_add_approved_part_to_project_creates_join(
    client: TestClient, pm_headers: dict, db: Session, project_id: int
):
    """Adding an APPROVED library part creates a ProjectPart join record."""
    lp = make_approved_library_part(db, PartType.FASTENER, "M4 Screw")

    resp = client.post(
        f"/api/v1/projects/{project_id}/parts/",
        json={"library_part_id": lp.id, "quantity": 8, "designation": "HW-J1"},
        headers=pm_headers,
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["library_part_id"] == lp.id
    assert data["quantity"] == 8
    assert data["designation"] == "HW-J1"
    # Critical: library part fields NOT duplicated on ProjectPart
    assert "torque_nominal_nm" not in data  # only on library_part nested object
    assert data["library_part"]["id"] == lp.id
    assert data["library_part"]["name"] == "M4 Screw"


def test_add_draft_part_to_project_rejected(
    client: TestClient, pm_headers: dict, db: Session, project_id: int
):
    """DRAFT library parts cannot be added to projects."""
    from app.services.parts.wpn_service import assign_wpn
    wpn = assign_wpn(db, PartType.BRACKET)
    draft = LibraryPart(
        wardstone_part_number=wpn, revision="00",
        part_type=PartType.BRACKET, name="Draft Bracket",
        status=PartStatus.DRAFT,
    )
    db.add(draft); db.commit()

    resp = client.post(
        f"/api/v1/projects/{project_id}/parts/",
        json={"library_part_id": draft.id},
        headers=pm_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "PART_NOT_APPROVED"


def test_add_same_part_twice_returns_409(
    client: TestClient, pm_headers: dict, db: Session, project_id: int
):
    """Adding the same library part to a project twice returns 409."""
    lp = make_approved_library_part(db, PartType.WASHER, "M6 Washer")

    r1 = client.post(f"/api/v1/projects/{project_id}/parts/",
                     json={"library_part_id": lp.id}, headers=pm_headers)
    assert r1.status_code == 201

    r2 = client.post(f"/api/v1/projects/{project_id}/parts/",
                     json={"library_part_id": lp.id}, headers=pm_headers)
    assert r2.status_code == 409
    assert r2.json()["code"] == "DUPLICATE_PROJECT_PART"


def test_non_member_cannot_add_part(
    client: TestClient, dev_headers: dict, db: Session,
    project_id: int
):
    """A user who is not a member of the project gets 403."""
    # dev_headers is for a user not in this project
    lp = make_approved_library_part(db, PartType.SEAL, "O-Ring")
    resp = client.post(
        f"/api/v1/projects/{project_id}/parts/",
        json={"library_part_id": lp.id},
        headers=dev_headers,  # non-member
    )
    assert resp.status_code == 403


def test_remove_part_does_not_delete_library_record(
    client: TestClient, pm_headers: dict, db: Session, project_id: int
):
    """Removing a ProjectPart does NOT delete the LibraryPart."""
    lp = make_approved_library_part(db, PartType.BEARING, "6002-2Z Bearing")

    add_resp = client.post(
        f"/api/v1/projects/{project_id}/parts/",
        json={"library_part_id": lp.id}, headers=pm_headers,
    )
    assert add_resp.status_code == 201
    pp_id = add_resp.json()["id"]

    del_resp = client.delete(
        f"/api/v1/projects/{project_id}/parts/{pp_id}",
        headers=pm_headers,
    )
    assert del_resp.status_code == 204

    # Library part still exists
    still_exists = db.query(LibraryPart).get(lp.id)
    assert still_exists is not None
    assert still_exists.status == PartStatus.APPROVED


def test_remove_part_with_active_joint_blocked(
    client: TestClient, pm_headers: dict, db: Session, project_id: int
):
    """Cannot remove a project part that has an active mechanical joint."""
    lp_a = make_approved_library_part(db, PartType.BRACKET, "Bracket A")
    lp_b = make_approved_library_part(db, PartType.ENCLOSURE, "Enclosure B")

    r_a = client.post(f"/api/v1/projects/{project_id}/parts/",
                      json={"library_part_id": lp_a.id}, headers=pm_headers)
    r_b = client.post(f"/api/v1/projects/{project_id}/parts/",
                      json={"library_part_id": lp_b.id}, headers=pm_headers)
    pp_a_id = r_a.json()["id"]
    pp_b_id = r_b.json()["id"]

    # Create and approve a joint
    joint_resp = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/",
        json={
            "joint_type": "bolted",
            "part_a_id": pp_a_id,
            "part_b_id": pp_b_id,
            "fastener_count": 4,
        },
        headers=pm_headers,
    )
    assert joint_resp.status_code == 201
    joint_jid = joint_resp.json()["joint_id"]

    approve_resp = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/{joint_jid}/approve",
        headers=pm_headers,
    )
    assert approve_resp.status_code == 200

    # Now try to remove part_a
    del_resp = client.delete(
        f"/api/v1/projects/{project_id}/parts/{pp_a_id}",
        headers=pm_headers,
    )
    assert del_resp.status_code == 409
    assert del_resp.json()["code"] == "HAS_ACTIVE_JOINTS"

    # With force=true (admin only)
    admin_hdrs = pm_headers  # use admin fixture in actual test setup
    force_del = client.delete(
        f"/api/v1/projects/{project_id}/parts/{pp_a_id}",
        params={"force": True},
        headers=admin_hdrs,
    )
    # Either 204 (deleted) or 403 (insufficient role) depending on pm vs admin
    assert force_del.status_code in (204, 403)


def test_list_unassigned_parts(
    client: TestClient, pm_headers: dict, db: Session, project_id: int
):
    """Unassigned endpoint returns only parts with no SystemPartAssignment."""
    lp1 = make_approved_library_part(db, PartType.FASTENER, "Bolt 1")
    lp2 = make_approved_library_part(db, PartType.FASTENER, "Bolt 2")
    lp3 = make_approved_library_part(db, PartType.WASHER, "Washer 1")

    r1 = client.post(f"/api/v1/projects/{project_id}/parts/",
                     json={"library_part_id": lp1.id}, headers=pm_headers)
    r2 = client.post(f"/api/v1/projects/{project_id}/parts/",
                     json={"library_part_id": lp2.id}, headers=pm_headers)
    r3 = client.post(f"/api/v1/projects/{project_id}/parts/",
                     json={"library_part_id": lp3.id}, headers=pm_headers)
    pp1_id = r1.json()["id"]

    # Assign part 1 to a system (assumes system_id=1 exists in test DB)
    client.post(
        f"/api/v1/projects/{project_id}/systems/1/parts/",
        json={"project_part_id": pp1_id}, headers=pm_headers,
    )

    unassigned_resp = client.get(
        f"/api/v1/projects/{project_id}/parts/unassigned",
        headers=pm_headers,
    )
    assert unassigned_resp.status_code == 200
    ids = [p["id"] for p in unassigned_resp.json()]
    assert r2.json()["id"] in ids
    assert r3.json()["id"] in ids
    assert pp1_id not in ids  # assigned, must not appear
```

---

```python
# backend/tests/test_mechanical_joints.py

import pytest
from decimal import Decimal
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from app.models.parts_library import (
    MechanicalJoint, MechanicalJointSequence, JointStatus, JointType,
    PartType, PartStatus
)
from app.models.req_sync import RequirementSourceLink, SourceEntityType
from app.models.requirements import Requirement
from tests.conftest import pm_headers, admin_headers, make_approved_library_part


def test_joint_id_format(
    client: TestClient, pm_headers: dict, db: Session, project_id: int,
    pp_a_id: int, pp_b_id: int
):
    """joint_id must match format MJ-{project_id:04d}-{seq:06d}."""
    resp = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/",
        json={"joint_type": "bolted", "part_a_id": pp_a_id, "part_b_id": pp_b_id},
        headers=pm_headers,
    )
    assert resp.status_code == 201
    joint_id = resp.json()["joint_id"]
    import re
    assert re.match(r"MJ-\d{4}-\d{6}$", joint_id), \
        f"joint_id format mismatch: {joint_id}"
    assert joint_id.startswith(f"MJ-{project_id:04d}-")


def test_joint_id_race_condition(
    db_factory, project_id: int, pp_a_id: int, pp_b_id: int
):
    """Two concurrent joint creates must produce distinct IDs."""
    import threading
    from app.services.parts.mechanical_joints import _assign_joint_id

    results = []
    def create_one():
        db = db_factory()
        try:
            jid = _assign_joint_id(db, project_id)
            db.commit()
            results.append(jid)
        finally:
            db.close()

    t1 = threading.Thread(target=create_one)
    t2 = threading.Thread(target=create_one)
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert len(results) == 2
    assert results[0] != results[1], f"Duplicate joint IDs: {results}"


def test_create_joint_validates_part_ownership(
    client: TestClient, pm_headers: dict, db: Session,
    project_id: int, other_project_id: int
):
    """A part from another project cannot be used in a joint."""
    # Create a part in another project
    lp = make_approved_library_part(db, PartType.FASTENER, "Cross-Project Bolt")
    from app.models.parts_library import ProjectPart
    other_pp = ProjectPart(
        project_id=other_project_id, library_part_id=lp.id, quantity=1
    )
    db.add(other_pp); db.commit()

    # Get a valid part from the current project
    from tests.conftest import get_any_project_part
    good_pp = get_any_project_part(db, project_id)

    resp = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/",
        json={
            "joint_type": "bolted",
            "part_a_id": good_pp.id,
            "part_b_id": other_pp.id,  # wrong project
        },
        headers=pm_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "PART_NOT_IN_PROJECT"


def test_fastener_type_validation(
    client: TestClient, pm_headers: dict, db: Session,
    project_id: int, pp_a_id: int, pp_b_id: int
):
    """Using a WASHER as a fastener_part is rejected."""
    washer = make_approved_library_part(db, PartType.WASHER, "M6 Washer")
    from app.models.parts_library import ProjectPart
    washer_pp = ProjectPart(project_id=project_id, library_part_id=washer.id, quantity=1)
    db.add(washer_pp); db.commit()

    resp = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/",
        json={
            "joint_type": "bolted",
            "part_a_id": pp_a_id,
            "part_b_id": pp_b_id,
            "fastener_part_id": washer.id,  # wrong type
        },
        headers=pm_headers,
    )
    assert resp.status_code == 422
    assert resp.json()["code"] == "INVALID_FASTENER_TYPE"


def test_same_part_both_sides_rejected(
    client: TestClient, pm_headers: dict, db: Session,
    project_id: int, pp_a_id: int
):
    """part_a_id == part_b_id must be rejected."""
    resp = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/",
        json={
            "joint_type": "bolted",
            "part_a_id": pp_a_id,
            "part_b_id": pp_a_id,   # same part on both sides
        },
        headers=pm_headers,
    )
    assert resp.status_code == 422


def test_approve_joint_generates_requirements(
    client: TestClient, pm_headers: dict, db: Session,
    project_id: int
):
    """Approving a BOLTED joint creates MECH-BOLT-* requirements."""
    fastener_lp = make_approved_library_part(
        db, PartType.FASTENER, "M6×16 SHCS A286",
        extra={"torque_nominal_nm": Decimal("9.8"),
               "torque_min_nm": Decimal("8.3"),
               "torque_max_nm": Decimal("10.8")}
    )
    lp_a = make_approved_library_part(db, PartType.BRACKET, "Primary Frame")
    lp_b = make_approved_library_part(db, PartType.ENCLOSURE, "Avionics Box")

    from app.models.parts_library import ProjectPart
    pp_fast = ProjectPart(project_id=project_id, library_part_id=fastener_lp.id, quantity=10)
    pp_a    = ProjectPart(project_id=project_id, library_part_id=lp_a.id, quantity=1)
    pp_b    = ProjectPart(project_id=project_id, library_part_id=lp_b.id, quantity=1)
    db.add_all([pp_fast, pp_a, pp_b]); db.commit()

    # Create joint
    create_resp = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/",
        json={
            "joint_type": "bolted",
            "part_a_id": pp_a.id,
            "part_b_id": pp_b.id,
            "fastener_part_id": fastener_lp.id,
            "fastener_count": 4,
            "torque_nominal_nm": "9.8",
            "torque_min_nm": "8.3",
            "torque_max_nm": "10.8",
            "locking_feature": "nylok",
        },
        headers=pm_headers,
    )
    assert create_resp.status_code == 201
    joint_jid = create_resp.json()["joint_id"]

    # Approve
    approve_resp = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/{joint_jid}/approve",
        headers=pm_headers,
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "active"

    # Verify requirements created
    joint = db.query(MechanicalJoint).filter(
        MechanicalJoint.joint_id == joint_jid
    ).first()
    source_links = db.query(RequirementSourceLink).filter(
        RequirementSourceLink.source_entity_type == SourceEntityType.MECHANICAL_JOINT,
        RequirementSourceLink.source_entity_id == joint.id,
    ).all()
    # BOLTED joint should generate MECH-BOLT-001, -002, -003, -004, MECH-SURF-001
    assert len(source_links) >= 3, \
        f"Expected ≥3 source links for BOLTED joint, got {len(source_links)}"

    # Verify requirement content
    req_ids = [sl.requirement_id for sl in source_links]
    reqs = db.query(Requirement).filter(Requirement.id.in_(req_ids)).all()
    statements = [r.statement for r in reqs]

    # MECH-BOLT-001 must mention the fastener name and torque
    bolt_001 = next((s for s in statements if "9.8 N·m" in s), None)
    assert bolt_001 is not None, \
        f"MECH-BOLT-001 with torque 9.8 not found in: {statements}"
    assert "Primary Frame" in bolt_001 or "Avionics Box" in bolt_001
    assert "4×" in bolt_001

    # No unresolved template tokens
    for stmt in statements:
        assert "{" not in stmt, f"Unresolved token in: {stmt}"


def test_approve_joint_fires_req_sync_on_update(
    client: TestClient, pm_headers: dict, db: Session, project_id: int
):
    """Updating a joint's torque after approval creates sync proposals."""
    from app.models.req_sync import RequirementSyncProposal

    # Create and approve a bolted joint (minimal)
    lp_a = make_approved_library_part(db, PartType.BRACKET, "Bracket X")
    lp_b = make_approved_library_part(db, PartType.ENCLOSURE, "Enclosure Y")
    from app.models.parts_library import ProjectPart
    pp_a = ProjectPart(project_id=project_id, library_part_id=lp_a.id, quantity=1)
    pp_b = ProjectPart(project_id=project_id, library_part_id=lp_b.id, quantity=1)
    db.add_all([pp_a, pp_b]); db.commit()

    cjr = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/",
        json={"joint_type": "bolted", "part_a_id": pp_a.id, "part_b_id": pp_b.id,
              "fastener_count": 2, "torque_nominal_nm": "9.8"},
        headers=pm_headers,
    )
    jid = cjr.json()["joint_id"]
    client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/{jid}/approve",
        headers=pm_headers,
    )

    initial_proposals = db.query(RequirementSyncProposal).count()

    # Update torque — should trigger sync
    client.patch(
        f"/api/v1/projects/{project_id}/mechanical-joints/{jid}",
        json={"torque_nominal_nm": "12.5"},
        headers=pm_headers,
    )

    final_proposals = db.query(RequirementSyncProposal).count()
    assert final_proposals > initial_proposals, \
        "Updating torque on active joint must create sync proposals"


def test_delete_draft_joint_hard_deletes(
    client: TestClient, pm_headers: dict, db: Session,
    project_id: int, pp_a_id: int, pp_b_id: int
):
    """DRAFT joints are hard-deleted."""
    cr = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/",
        json={"joint_type": "bolted", "part_a_id": pp_a_id, "part_b_id": pp_b_id},
        headers=pm_headers,
    )
    jid = cr.json()["joint_id"]
    db_id = cr.json()["id"]

    dr = client.delete(
        f"/api/v1/projects/{project_id}/mechanical-joints/{jid}",
        headers=pm_headers,
    )
    assert dr.status_code == 204

    assert db.query(MechanicalJoint).get(db_id) is None


def test_delete_active_joint_without_force_blocked(
    client: TestClient, pm_headers: dict, db: Session,
    project_id: int, pp_a_id: int, pp_b_id: int
):
    """Active joints require force=true to delete."""
    cr = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/",
        json={"joint_type": "bolted", "part_a_id": pp_a_id, "part_b_id": pp_b_id},
        headers=pm_headers,
    )
    jid = cr.json()["joint_id"]
    client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/{jid}/approve",
        headers=pm_headers,
    )

    dr = client.delete(
        f"/api/v1/projects/{project_id}/mechanical-joints/{jid}",
        headers=pm_headers,  # no force
    )
    assert dr.status_code == 409
    assert dr.json()["code"] == "ACTIVE_JOINT_REQUIRES_FORCE"


def test_delete_active_joint_with_force_soft_deletes(
    client: TestClient, admin_headers: dict, db: Session,
    project_id: int, pp_a_id: int, pp_b_id: int
):
    """force=true on active joint sets status=superseded (not hard delete)."""
    cr = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/",
        json={"joint_type": "bolted", "part_a_id": pp_a_id, "part_b_id": pp_b_id},
        headers=admin_headers,
    )
    jid = cr.json()["joint_id"]
    db_id = cr.json()["id"]
    client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/{jid}/approve",
        headers=admin_headers,
    )

    dr = client.delete(
        f"/api/v1/projects/{project_id}/mechanical-joints/{jid}",
        params={"force": True},
        headers=admin_headers,
    )
    assert dr.status_code == 204

    # Row still exists but status = superseded
    joint = db.query(MechanicalJoint).get(db_id)
    assert joint is not None
    assert joint.status == JointStatus.SUPERSEDED


def test_non_member_cannot_create_joint(
    client: TestClient, dev_headers: dict,
    project_id: int, pp_a_id: int, pp_b_id: int
):
    """Non-project-member gets 403."""
    resp = client.post(
        f"/api/v1/projects/{project_id}/mechanical-joints/",
        json={"joint_type": "bolted", "part_a_id": pp_a_id, "part_b_id": pp_b_id},
        headers=dev_headers,
    )
    assert resp.status_code == 403
```

---

## F. Complete Frontend Page Implementations

### F.1 `StepUploadModal` — complete TSX

```tsx
// frontend/src/components/parts/StepUploadModal.tsx
'use client';
import { useState, useCallback, useRef } from 'react';
import { partsLibraryAPI } from '@/lib/api';

interface StepUploadModalProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (pendingImportId: number) => void;
}

const MAX_FILE_SIZE_MB = 50;
const ACCEPTED_EXTENSIONS = ['.step', '.stp'];

export function StepUploadModal({ open, onClose, onSuccess }: StepUploadModalProps) {
  const [file, setFile] = useState<File | null>(null);
  const [progress, setProgress] = useState(0);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const validateFile = (f: File): string | null => {
    const ext = '.' + f.name.split('.').pop()?.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      return `Invalid file type "${ext}". Only .step and .stp files are accepted.`;
    }
    if (f.size > MAX_FILE_SIZE_MB * 1024 * 1024) {
      return `File size ${(f.size / 1024 / 1024).toFixed(1)} MB exceeds ${MAX_FILE_SIZE_MB} MB limit.`;
    }
    if (f.size === 0) {
      return 'File is empty.';
    }
    return null;
  };

  const handleFileSelect = (f: File) => {
    const err = validateFile(f);
    if (err) { setError(err); return; }
    setFile(f);
    setError(null);
  };

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const dropped = e.dataTransfer.files[0];
    if (dropped) handleFileSelect(dropped);
  }, []);

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const res = await partsLibraryAPI.uploadStep(file, setProgress);
      if (res.data.duplicate) {
        if (res.data.pending_import_id) {
          setError(null);
          onSuccess(res.data.pending_import_id);
        } else if (res.data.existing_part_id) {
          setError(
            `This file is already in the library as ${res.data.existing_wpn}. ` +
            `Redirecting to the existing part.`
          );
          setTimeout(() => {
            window.location.href = `/parts-library/${res.data.existing_part_id}`;
          }, 2000);
        }
      } else {
        onSuccess(res.data.pending_import_id!);
      }
    } catch (err: unknown) {
      const axErr = err as { response?: { data?: { detail?: string; code?: string } } };
      setError(axErr.response?.data?.detail || 'Upload failed. Please try again.');
    } finally {
      setUploading(false);
    }
  };

  const handleReset = () => {
    setFile(null);
    setProgress(0);
    setError(null);
    if (inputRef.current) inputRef.current.value = '';
  };

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
      <div className="bg-white dark:bg-gray-900 rounded-xl shadow-2xl w-full max-w-lg mx-4 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Upload STEP File
          </h2>
          <button
            onClick={onClose}
            disabled={uploading}
            className="text-gray-400 hover:text-gray-600 dark:hover:text-gray-200 disabled:opacity-50"
          >
            ✕
          </button>
        </div>

        {/* Drop zone */}
        {!file && (
          <div
            onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => inputRef.current?.click()}
            className={`
              border-2 border-dashed rounded-lg p-8 text-center cursor-pointer
              transition-colors duration-150
              ${dragOver
                ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20'
                : 'border-gray-300 dark:border-gray-600 hover:border-blue-400 hover:bg-gray-50 dark:hover:bg-gray-800'}
            `}
          >
            <div className="text-4xl mb-2">📦</div>
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">
              Drop a STEP file here or click to browse
            </p>
            <p className="text-xs text-gray-500 dark:text-gray-400 mt-1">
              .step or .stp — max {MAX_FILE_SIZE_MB} MB
            </p>
            <input
              ref={inputRef}
              type="file"
              accept=".step,.stp"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFileSelect(f);
              }}
            />
          </div>
        )}

        {/* Selected file info */}
        {file && (
          <div className="flex items-center gap-3 p-3 bg-gray-50 dark:bg-gray-800 rounded-lg">
            <div className="text-2xl">📄</div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-gray-900 dark:text-white truncate">
                {file.name}
              </p>
              <p className="text-xs text-gray-500">
                {(file.size / 1024).toFixed(1)} KB
              </p>
            </div>
            {!uploading && (
              <button
                onClick={handleReset}
                className="text-gray-400 hover:text-red-500 text-sm"
              >
                Remove
              </button>
            )}
          </div>
        )}

        {/* Upload progress */}
        {uploading && (
          <div className="mt-4">
            <div className="flex justify-between text-xs text-gray-500 mb-1">
              <span>Uploading...</span>
              <span>{progress}%</span>
            </div>
            <div className="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
              <div
                className="bg-blue-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="mt-3 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200
                          dark:border-red-800 rounded-lg text-sm text-red-700 dark:text-red-300">
            {error}
          </div>
        )}

        {/* Actions */}
        <div className="mt-5 flex gap-3 justify-end">
          <button
            onClick={onClose}
            disabled={uploading}
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300
                       border border-gray-300 dark:border-gray-600 rounded-lg
                       hover:bg-gray-50 dark:hover:bg-gray-800 disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={handleUpload}
            disabled={!file || uploading}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600
                       rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed
                       flex items-center gap-2"
          >
            {uploading ? (
              <>
                <svg className="animate-spin w-4 h-4" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10"
                          stroke="currentColor" strokeWidth="4"/>
                  <path className="opacity-75" fill="currentColor"
                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"/>
                </svg>
                Uploading...
              </>
            ) : 'Upload & Parse'}
          </button>
        </div>
      </div>
    </div>
  );
}
```

### F.2 `ConfidenceBadge` — reusable component

```tsx
// frontend/src/components/parts/ConfidenceBadge.tsx
import type { ConfidenceLevel } from '@/types/parts-library';

interface ConfidenceBadgeProps {
  level: ConfidenceLevel;
  showLabel?: boolean;
}

const CONFIG: Record<ConfidenceLevel, { bg: string; text: string; label: string; icon: string }> = {
  high:   { bg: 'bg-green-100 dark:bg-green-900/30',
            text: 'text-green-800 dark:text-green-300',
            label: 'High',  icon: '✓' },
  medium: { bg: 'bg-amber-100 dark:bg-amber-900/30',
            text: 'text-amber-800 dark:text-amber-300',
            label: 'Medium', icon: '~' },
  low:    { bg: 'bg-red-100 dark:bg-red-900/30',
            text: 'text-red-800 dark:text-red-300',
            label: 'Low', icon: '!' },
};

export function ConfidenceBadge({ level, showLabel = true }: ConfidenceBadgeProps) {
  const c = CONFIG[level];
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${c.bg} ${c.text}`}
          title={`${c.label} confidence`}>
      <span aria-hidden="true">{c.icon}</span>
      {showLabel && c.label}
    </span>
  );
}
```

### F.3 `WPNBadge` — reusable WPN display component

```tsx
// frontend/src/components/parts/WPNBadge.tsx
'use client';
import { useState } from 'react';

interface WPNBadgeProps {
  wpn: string;
  size?: 'sm' | 'md' | 'lg';
}

export function WPNBadge({ wpn, size = 'md' }: WPNBadgeProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = () => {
    navigator.clipboard.writeText(wpn).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };

  const sizeClass = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-sm px-3 py-1',
    lg: 'text-base px-4 py-1.5',
  }[size];

  return (
    <button
      onClick={handleCopy}
      title={copied ? 'Copied!' : 'Click to copy WPN'}
      className={`
        inline-flex items-center gap-2 font-mono font-medium rounded
        bg-gray-900 dark:bg-gray-800 text-green-400 dark:text-green-300
        border border-gray-700 dark:border-gray-600
        hover:bg-gray-800 dark:hover:bg-gray-700
        transition-colors duration-100 ${sizeClass}
      `}
    >
      {wpn}
      <span className="text-gray-500 dark:text-gray-400 text-xs">
        {copied ? '✓' : '⧉'}
      </span>
    </button>
  );
}
```

### F.4 `PartTypeBadge` — colored part type chip

```tsx
// frontend/src/components/parts/PartTypeBadge.tsx
import type { PartType } from '@/types/parts-library';

const COLORS: Record<PartType, string> = {
  fastener:          'bg-blue-100   dark:bg-blue-900/30   text-blue-800   dark:text-blue-200',
  washer:            'bg-gray-100   dark:bg-gray-800       text-gray-800   dark:text-gray-200',
  insert:            'bg-purple-100 dark:bg-purple-900/30 text-purple-800 dark:text-purple-200',
  bracket:           'bg-teal-100   dark:bg-teal-900/30   text-teal-800   dark:text-teal-200',
  enclosure:         'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-200',
  seal:              'bg-green-100  dark:bg-green-900/30  text-green-800  dark:text-green-200',
  bearing:           'bg-amber-100  dark:bg-amber-900/30  text-amber-800  dark:text-amber-200',
  hinge_latch:       'bg-pink-100   dark:bg-pink-900/30   text-pink-800   dark:text-pink-200',
  thermal_interface: 'bg-red-100    dark:bg-red-900/30    text-red-800    dark:text-red-200',
  pcb_mechanical:    'bg-indigo-100 dark:bg-indigo-900/30 text-indigo-800 dark:text-indigo-200',
  custom:            'bg-gray-100   dark:bg-gray-800       text-gray-600   dark:text-gray-400',
};

const LABELS: Record<PartType, string> = {
  fastener:          'Fastener',
  washer:            'Washer',
  insert:            'Insert',
  bracket:           'Bracket',
  enclosure:         'Enclosure',
  seal:              'Seal',
  bearing:           'Bearing',
  hinge_latch:       'Hinge/Latch',
  thermal_interface: 'Thermal IF',
  pcb_mechanical:    'PCB Mech',
  custom:            'Custom',
};

export function PartTypeBadge({ type }: { type: PartType }) {
  return (
    <span className={`
      inline-flex px-2 py-0.5 rounded text-xs font-medium
      ${COLORS[type]}
    `}>
      {LABELS[type]}
    </span>
  );
}
```

### F.5 Complete `parts-library/page.tsx` with all states

```tsx
// frontend/src/app/(parts-library)/parts-library/page.tsx
'use client';
import { useState, useEffect } from 'react';
import Link from 'next/link';
import { partsLibraryAPI } from '@/lib/api';
import type { LibraryPartSummary, PartType, PartStatus } from '@/types/parts-library';
import { WPNBadge } from '@/components/parts/WPNBadge';
import { PartTypeBadge } from '@/components/parts/PartTypeBadge';
import { StepUploadModal } from '@/components/parts/StepUploadModal';
import { useRouter } from 'next/navigation';
import { useDebounce } from '@/hooks/useDebounce';

// ── Skeleton ──────────────────────────────────────────────────────────────────
function TableSkeleton() {
  return (
    <div className="animate-pulse">
      {[...Array(6)].map((_, i) => (
        <div key={i} className="flex gap-4 py-3 border-b border-gray-100 dark:border-gray-800">
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-36" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded flex-1" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-20" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-28" />
          <div className="h-4 bg-gray-200 dark:bg-gray-700 rounded w-24" />
        </div>
      ))}
    </div>
  );
}

// ── Status badge ──────────────────────────────────────────────────────────────
const STATUS_STYLES: Record<string, string> = {
  draft:        'bg-gray-100   dark:bg-gray-800 text-gray-600   dark:text-gray-400',
  under_review: 'bg-amber-100  dark:bg-amber-900/30 text-amber-800 dark:text-amber-200',
  approved:     'bg-green-100  dark:bg-green-900/30 text-green-800 dark:text-green-200',
  superseded:   'bg-orange-100 dark:bg-orange-900/30 text-orange-800 dark:text-orange-200',
  obsolete:     'bg-red-100    dark:bg-red-900/30 text-red-800 dark:text-red-200',
};

function StatusBadge({ status }: { status: string }) {
  const style = STATUS_STYLES[status] ?? STATUS_STYLES.draft;
  return (
    <span className={`inline-flex px-2 py-0.5 rounded text-xs font-medium capitalize ${style}`}>
      {status.replace('_', ' ')}
    </span>
  );
}

// ── Part type filter chips ────────────────────────────────────────────────────
const PART_TYPES: PartType[] = [
  'fastener', 'washer', 'insert', 'bracket', 'enclosure',
  'seal', 'bearing', 'hinge_latch', 'thermal_interface', 'pcb_mechanical', 'custom'
];

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function PartsLibraryPage() {
  const router = useRouter();
  const [parts, setParts] = useState<LibraryPartSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<PartType | ''>('');
  const [statusFilter, setStatusFilter] = useState<PartStatus | ''>('');
  const [uploadOpen, setUploadOpen] = useState(false);

  const debouncedSearch = useDebounce(search, 300);

  const fetchParts = () => {
    setLoading(true);
    setError(null);
    partsLibraryAPI.list({
      search: debouncedSearch || undefined,
      part_type: typeFilter || undefined,
      status: statusFilter || undefined,
    })
      .then(res => setParts(res.data))
      .catch(err => {
        const msg = err?.response?.data?.detail || 'Failed to load parts library';
        setError(msg);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => { fetchParts(); },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [debouncedSearch, typeFilter, statusFilter]);

  const handleUploadSuccess = (pendingImportId: number) => {
    setUploadOpen(false);
    router.push(`/parts-library/pending-imports/${pendingImportId}`);
  };

  const hasFilters = !!search || !!typeFilter || !!statusFilter;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Page header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
            Parts Library
          </h1>
          <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
            Global cross-project mechanical parts database
          </p>
        </div>
        <div className="flex gap-3">
          <Link
            href="/parts-library/pending-imports"
            className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300
                       border border-gray-300 dark:border-gray-600 rounded-lg
                       hover:bg-gray-50 dark:hover:bg-gray-800"
          >
            Review Queue
          </Link>
          <button
            onClick={() => setUploadOpen(true)}
            className="px-4 py-2 text-sm font-medium text-white bg-blue-600
                       rounded-lg hover:bg-blue-700"
          >
            Upload STEP File
          </button>
          <Link
            href="/parts-library/new"
            className="px-4 py-2 text-sm font-medium text-white bg-green-600
                       rounded-lg hover:bg-green-700"
          >
            New Part
          </Link>
        </div>
      </div>

      {/* Search + filters */}
      <div className="flex flex-wrap gap-3 mb-6">
        {/* Search */}
        <div className="flex-1 min-w-64">
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search by name, WPN, MPN, manufacturer..."
            className="w-full px-4 py-2 text-sm border border-gray-300 dark:border-gray-600
                       rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white
                       focus:ring-2 focus:ring-blue-500 focus:border-transparent"
          />
        </div>
        {/* Type filter */}
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value as PartType | '')}
          className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600
                     rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
        >
          <option value="">All Types</option>
          {PART_TYPES.map(t => (
            <option key={t} value={t}>
              {t.replace('_', ' ').replace(/\b\w/g, c => c.toUpperCase())}
            </option>
          ))}
        </select>
        {/* Status filter */}
        <select
          value={statusFilter}
          onChange={e => setStatusFilter(e.target.value as PartStatus | '')}
          className="px-3 py-2 text-sm border border-gray-300 dark:border-gray-600
                     rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-white"
        >
          <option value="">Approved Only</option>
          <option value="draft">Draft</option>
          <option value="under_review">Under Review</option>
          <option value="approved">Approved</option>
          <option value="superseded">Superseded</option>
          <option value="obsolete">Obsolete</option>
        </select>
        {hasFilters && (
          <button
            onClick={() => { setSearch(''); setTypeFilter(''); setStatusFilter(''); }}
            className="px-3 py-2 text-sm text-gray-500 hover:text-gray-700
                       dark:text-gray-400 dark:hover:text-gray-200"
          >
            Clear filters
          </button>
        )}
      </div>

      {/* Content */}
      {loading ? (
        <TableSkeleton />
      ) : error ? (
        <div className="rounded-lg bg-red-50 dark:bg-red-900/20 border border-red-200
                         dark:border-red-800 p-4 flex items-center justify-between">
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          <button
            onClick={fetchParts}
            className="text-sm text-red-600 dark:text-red-400 underline hover:no-underline"
          >
            Retry
          </button>
        </div>
      ) : parts.length === 0 ? (
        hasFilters ? (
          <div className="text-center py-16">
            <p className="text-gray-500 dark:text-gray-400">
              No parts match your filters.
            </p>
            <button
              onClick={() => { setSearch(''); setTypeFilter(''); setStatusFilter(''); }}
              className="mt-2 text-sm text-blue-600 dark:text-blue-400 underline"
            >
              Clear filters
            </button>
          </div>
        ) : (
          <div className="text-center py-16">
            <div className="text-6xl mb-4">🔩</div>
            <h3 className="text-lg font-medium text-gray-900 dark:text-white">
              No parts in the library yet
            </h3>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Upload a STEP file or create a part manually to get started.
            </p>
            <div className="flex gap-3 justify-center mt-4">
              <button
                onClick={() => setUploadOpen(true)}
                className="px-4 py-2 text-sm font-medium text-white bg-blue-600
                           rounded-lg hover:bg-blue-700"
              >
                Upload STEP File
              </button>
              <Link
                href="/parts-library/new"
                className="px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300
                           border border-gray-300 dark:border-gray-600 rounded-lg
                           hover:bg-gray-50 dark:hover:bg-gray-800"
              >
                Create Manually
              </Link>
            </div>
          </div>
        )
      ) : (
        <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700">
          <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
            <thead className="bg-gray-50 dark:bg-gray-800">
              <tr>
                {[
                  'WPN', 'Name', 'Type', 'Material', 'Manufacturer', 'MPN',
                  'Status', 'Approved'
                ].map(col => (
                  <th
                    key={col}
                    className="px-4 py-3 text-left text-xs font-medium text-gray-500
                               dark:text-gray-400 uppercase tracking-wider"
                  >
                    {col}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-100 dark:divide-gray-800">
              {parts.map(part => (
                <tr
                  key={part.id}
                  onClick={() => router.push(`/parts-library/${part.id}`)}
                  className="hover:bg-gray-50 dark:hover:bg-gray-800 cursor-pointer"
                >
                  <td className="px-4 py-3 whitespace-nowrap">
                    <WPNBadge wpn={part.wardstone_part_number} size="sm" />
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                      {part.name}
                    </span>
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <PartTypeBadge type={part.part_type} />
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                    {part.material_name || (
                      <span className="text-gray-300 dark:text-gray-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-500 dark:text-gray-400">
                    {part.manufacturer_name || (
                      <span className="text-gray-300 dark:text-gray-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 text-sm font-mono text-gray-500 dark:text-gray-400">
                    {part.manufacturer_part_number || (
                      <span className="text-gray-300 dark:text-gray-600">—</span>
                    )}
                  </td>
                  <td className="px-4 py-3 whitespace-nowrap">
                    <StatusBadge status={part.status} />
                  </td>
                  <td className="px-4 py-3 text-sm text-gray-400 dark:text-gray-500 whitespace-nowrap">
                    {part.approved_at
                      ? new Date(part.approved_at).toLocaleDateString()
                      : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <StepUploadModal
        open={uploadOpen}
        onClose={() => setUploadOpen(false)}
        onSuccess={handleUploadSuccess}
      />
    </div>
  );
}
```

---

## G. Exact Wiring into `main.py`

Add these lines in `backend/app/main.py` after the existing router registrations:

```python
# Parts Library (Phase 2)
from app.routers import parts_library as parts_library_router
from app.routers import project_parts as project_parts_router
from app.routers import mechanical_joints as mechanical_joints_router

app.include_router(
    parts_library_router.router,
    prefix="/api/v1/parts-library",
    tags=["parts-library"],
)
app.include_router(
    project_parts_router.router,
    prefix="/api/v1/projects/{project_id}/parts",
    tags=["project-parts"],
)
app.include_router(
    mechanical_joints_router.router,
    prefix="/api/v1/projects/{project_id}/mechanical-joints",
    tags=["mechanical-joints"],
)

# Register mechanical joint req_sync listeners (Phase 2)
# Must happen AFTER models are imported so SQLAlchemy events can attach.
from app.services.req_sync import listener as req_sync_listener  # noqa: F401
# The import is sufficient — the @event.listens_for decorators fire on import.
```

Also add to the model import block in `main.py` (the block that ensures all models are imported before `Base.metadata.create_all`):

```python
import app.models.parts_library  # noqa: F401 — register parts models with Base
```

---

## H. Exact `useDebounce` Hook

If this hook does not exist in the codebase, create it:

```typescript
// frontend/src/hooks/useDebounce.ts
import { useState, useEffect } from 'react';

export function useDebounce<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState<T>(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);

  return debounced;
}
```

If a `useDebounce` hook already exists at a different path, use that one. Do not create a duplicate.

---

## I. API Response JSON Examples

For every endpoint, this section gives the exact JSON shape of a successful response. Use these to confirm your implementations are serializing correctly.

### `GET /api/v1/parts-library/` (list)

```json
[
  {
    "id": 1,
    "wardstone_part_number": "WS-FAST-000001-00",
    "revision": "00",
    "part_type": "fastener",
    "name": "M6×16 Socket Head Cap Screw A286",
    "status": "approved",
    "manufacturer_name": "Bossard",
    "manufacturer_part_number": "1253427",
    "material_name": "A286",
    "material_class": "stainless_steel",
    "mass_nominal_g": "4.2000",
    "approved_at": "2025-03-15T14:22:00Z"
  }
]
```

**Important:** `mass_nominal_g` is a `string`, not a number. This is because FastAPI serializes Python `Decimal` to string in JSON. The frontend TypeScript types reflect this.

### `POST /api/v1/parts-library/` (create)

Request body:
```json
{
  "part_type": "washer",
  "name": "M6 Flat Washer ISO 7089",
  "nominal_diameter_mm": "6.5",
  "material_name": "A2 Stainless Steel",
  "material_class": "stainless_steel",
  "mass_nominal_g": "1.4"
}
```

Response (201):
```json
{
  "id": 5,
  "wardstone_part_number": "WS-WASH-000001-00",
  "revision": "00",
  "part_type": "washer",
  "name": "M6 Flat Washer ISO 7089",
  "status": "draft",
  "manufacturer_name": null,
  "manufacturer_part_number": null,
  "material_name": "A2 Stainless Steel",
  "material_class": "stainless_steel",
  "nominal_diameter_mm": "6.5000",
  "mass_nominal_g": "1.4000",
  "torque_nominal_nm": null,
  "approved_at": null,
  "approved_by_id": null,
  "created_at": "2025-05-01T10:15:00Z",
  "updated_at": "2025-05-01T10:15:00Z"
}
```

### `POST /api/v1/parts-library/upload-step` (success)

Response (202):
```json
{
  "duplicate": false,
  "pending_import_id": 3,
  "message": "STEP file accepted. Parsing in progress."
}
```

Response when duplicate (200):
```json
{
  "duplicate": true,
  "existing_part_id": 1,
  "existing_wpn": "WS-FAST-000001-00",
  "message": "This exact STEP file is already in the Parts Library."
}
```

### `POST /api/v1/parts-library/pending-imports/{id}/approve` (success)

Request body:
```json
{
  "overrides": {
    "name": "M6×16 SHCS A286 (Corrected)",
    "torque_nominal_nm": "9.8",
    "torque_min_nm": "8.3",
    "torque_max_nm": "10.8"
  },
  "supplier_id": null
}
```

Response (200): Full `LibraryPartResponse` schema — all fields including WPN, revision, status=approved.

### `POST /api/v1/projects/{project_id}/parts/` (success)

Request:
```json
{
  "library_part_id": 1,
  "quantity": 4,
  "designation": "HW-J1",
  "notes": "Primary panel attachment"
}
```

Response (201):
```json
{
  "id": 10,
  "project_id": 1,
  "library_part_id": 1,
  "quantity": 4,
  "designation": "HW-J1",
  "notes": "Primary panel attachment",
  "added_at": "2025-05-01T10:30:00Z",
  "library_part": {
    "id": 1,
    "wardstone_part_number": "WS-FAST-000001-00",
    "revision": "00",
    "part_type": "fastener",
    "name": "M6×16 Socket Head Cap Screw A286",
    "status": "approved",
    "manufacturer_name": "Bossard",
    "manufacturer_part_number": "1253427",
    "material_name": "A286",
    "material_class": "stainless_steel",
    "mass_nominal_g": "4.2000",
    "approved_at": "2025-03-15T14:22:00Z"
  },
  "system_id": null
}
```

### `POST /api/v1/projects/{project_id}/mechanical-joints/` (success)

Request:
```json
{
  "joint_type": "bolted",
  "part_a_id": 10,
  "part_b_id": 11,
  "fastener_part_id": 1,
  "fastener_count": 4,
  "torque_nominal_nm": "9.8",
  "torque_min_nm": "8.3",
  "torque_max_nm": "10.8",
  "locking_feature": "nylok",
  "notes": "Primary structure to avionics bay"
}
```

Response (201):
```json
{
  "id": 1,
  "joint_id": "MJ-0001-000001",
  "project_id": 1,
  "joint_type": "bolted",
  "part_a_id": 10,
  "part_b_id": 11,
  "fastener_part_id": 1,
  "fastener_count": 4,
  "torque_nominal_nm": "9.8000",
  "torque_min_nm": "8.3000",
  "torque_max_nm": "10.8000",
  "engagement_length_mm": null,
  "locking_feature": "nylok",
  "hole_pattern_description": null,
  "mating_surface_flatness_mm": null,
  "mating_surface_finish_ra": null,
  "seal_part_id": null,
  "leak_rate_max_scc_s": null,
  "test_pressure_bar": null,
  "interface_drawing": null,
  "notes": "Primary structure to avionics bay",
  "status": "draft",
  "confidence": null,
  "source_step_file_id": null,
  "created_at": "2025-05-01T10:35:00Z",
  "updated_at": "2025-05-01T10:35:00Z",
  "fastener_part": {
    "id": 1,
    "wardstone_part_number": "WS-FAST-000001-00",
    "part_type": "fastener",
    "name": "M6×16 Socket Head Cap Screw A286",
    "status": "approved"
    // ... other LibraryPartSummary fields
  },
  "seal_part": null
}
```

### `POST /api/v1/parts-library/pending-imports/{id}/approve` — error responses

Missing name (422):
```json
{"detail": "Field 'name' is required before approval", "code": "MISSING_REQUIRED_FIELD"}
```

Wrong state (409):
```json
{"detail": "Import is rejected and cannot be approved", "code": "WRONG_STATE"}
```

### `DELETE /api/v1/projects/{project_id}/mechanical-joints/{joint_id}` — active without force (409)

```json
{
  "detail": "Active joints cannot be deleted without force=true. This joint has auto-generated requirements linked to it. Deleting it will mark those requirements for review.",
  "code": "ACTIVE_JOINT_REQUIRES_FORCE"
}
```

---

## J. Database Performance Constraints

### J.1 Query performance requirements for list endpoints

The following list endpoints must complete within these time bounds under the test dataset (project with 500 parts, 200 joints, 50 systems):

| Endpoint | Max response time | Key index that enables this |
|---|---|---|
| `GET /parts-library/` (default) | 200ms | `ix_library_part_type_status` |
| `GET /parts-library/?search=M6` | 500ms | `ix_library_part_mpn` + text scan |
| `GET /projects/1/parts/` | 150ms | `ix_project_parts_project` + selectinload |
| `GET /projects/1/mechanical-joints/` | 200ms | `ix_mj_project_status` + selectinload |
| `GET /projects/1/parts/unassigned` | 250ms | `ix_spa_ppart` (LEFT JOIN exclusion) |

Add a `@pytest.mark.performance` test for each:

```python
@pytest.mark.performance
def test_list_parts_performance(client, admin_headers, db_with_500_parts):
    import time
    start = time.monotonic()
    resp = client.get("/api/v1/parts-library/", headers=admin_headers)
    elapsed = time.monotonic() - start
    assert resp.status_code == 200
    assert elapsed < 0.200, f"List parts took {elapsed:.3f}s (>200ms)"
```

### J.2 `updated_at` trigger

PostgreSQL does not auto-update `updated_at` on UPDATE unless a trigger is set. The existing codebase uses `onupdate=func.now()` in SQLAlchemy, which works when updates go through SQLAlchemy ORM. However, if any raw SQL updates are run (in tests or migrations), this will not fire.

For the `library_parts` and `mechanical_joints` tables, add a PostgreSQL trigger in the migration for production safety:

```sql
-- Add to upgrade() after table creation:
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

-- Only create if not already exists (from previous migrations)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_library_parts_updated_at'
    ) THEN
        CREATE TRIGGER trg_library_parts_updated_at
            BEFORE UPDATE ON library_parts
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_trigger
        WHERE tgname = 'trg_mechanical_joints_updated_at'
    ) THEN
        CREATE TRIGGER trg_mechanical_joints_updated_at
            BEFORE UPDATE ON mechanical_joints
            FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
    END IF;
END $$;
```

If `update_updated_at_column()` function already exists in the DB (from a previous migration), the `CREATE OR REPLACE` will update it safely.

In `downgrade()`, drop these triggers:
```sql
DROP TRIGGER IF EXISTS trg_library_parts_updated_at ON library_parts;
DROP TRIGGER IF EXISTS trg_mechanical_joints_updated_at ON mechanical_joints;
-- Do NOT drop the function — it may be shared with other tables
```

---

## K. `conftest.py` Fixtures Required by Tests

If these fixtures do not already exist in `backend/tests/conftest.py`, add them:

```python
# backend/tests/conftest.py (additions)
import pytest
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.parts_library import (
    LibraryPart, WPNSequence, ProjectPart,
    PartType, PartStatus
)

def make_approved_library_part(
    db: Session,
    part_type: PartType,
    name: str,
    extra: dict | None = None,
) -> LibraryPart:
    """
    Test helper: create and commit an APPROVED library part.
    Assigns a WPN using the WPN service (safe to call in tests).
    """
    from app.services.parts.wpn_service import assign_wpn
    wpn = assign_wpn(db, part_type)
    fields = {
        "wardstone_part_number": wpn,
        "revision": "00",
        "part_type": part_type,
        "name": name,
        "status": PartStatus.APPROVED,
        "approved_by_id": 1,
        "approved_at": "2025-01-01T00:00:00Z",
    }
    if extra:
        fields.update(extra)
    part = LibraryPart(**fields)
    db.add(part)
    db.commit()
    db.refresh(part)
    return part

def get_any_project_part(db: Session, project_id: int) -> ProjectPart:
    """Return any ProjectPart for the given project, or raise."""
    pp = db.query(ProjectPart).filter(
        ProjectPart.project_id == project_id
    ).first()
    if not pp:
        raise ValueError(
            f"No ProjectPart found for project_id={project_id}. "
            "Add a part to the project before running this test."
        )
    return pp

def _create_test_document(db: Session):
    """Create a minimal Document record for tests."""
    from app.models import Document  # use whatever Document model exists
    doc = Document(
        filename="test_part.step",
        file_path="/tmp/test_part.step",
        file_size_bytes=1024,
        sha256="a" * 64,
        mime_type="application/step",
        document_type="step_cad",
        uploaded_by_id=1,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc

@pytest.fixture
def pp_a_id(db: Session, project_id: int) -> int:
    """Fixture providing a ProjectPart ID for part A in mechanical joint tests."""
    lp = make_approved_library_part(db, PartType.BRACKET, "Fixture Bracket A")
    pp = ProjectPart(project_id=project_id, library_part_id=lp.id, quantity=1)
    db.add(pp); db.commit()
    return pp.id

@pytest.fixture
def pp_b_id(db: Session, project_id: int) -> int:
    """Fixture providing a ProjectPart ID for part B in mechanical joint tests."""
    lp = make_approved_library_part(db, PartType.ENCLOSURE, "Fixture Enclosure B")
    pp = ProjectPart(project_id=project_id, library_part_id=lp.id, quantity=1)
    db.add(pp); db.commit()
    return pp.id
```

---

## L. Final End-to-End Smoke Test Sequence

After all 4 phases complete, run this exact manual verification sequence and record results in `PARTS_BUILD_LOG.md`:

```
1. Navigate to http://localhost:3000/parts-library
   Expected: Page loads, shows "No parts in the library yet" empty state
   or existing parts if the dev DB already has some.

2. Click "Upload STEP File". Drop in a valid .step file.
   Expected: Upload completes, redirect to /parts-library/pending-imports/[id].
   Pending review page shows extracted fields with confidence badges.

3. Review the import. Edit the name if needed. Click "Approve".
   Expected: Toast "Part WS-[TYPE]-000001-00 approved". Redirect to part detail.

4. Part detail page:
   Expected: WPN badge (monospace, dark background), 5 tabs visible,
   3D viewer shows GLTF or "Upload STEP file to enable 3D preview" placeholder.

5. Navigate to a project: http://localhost:3000/projects/1/parts
   Expected: Engineering nav shows SYSTEM ARCHITECTURE, PARTS, ELECTRICAL INTERFACES,
   MECHANICAL INTERFACES in that order.

6. Click "Add Part". LibraryPartPickerModal opens.
   Expected: The approved part from step 3 appears in the list.
   Select it, set quantity=4, designation="HW-J1", click Add.

7. PARTS tab refreshes.
   Expected: New row with amber "Unassigned" badge.

8. Navigate to /projects/1/mechanical-interfaces.
   Expected: Empty joints list, "Add Joint" and "Upload Assembly" buttons.

9. Click "Add Joint". Select Part A and Part B from dropdowns.
   Set joint_type=bolted, fastener_count=4, torque_nominal=9.8.
   Click Save.
   Expected: Joint appears with status=DRAFT, confidence=LOW (no STEP source).

10. Click "Approve" on the joint.
    Expected: Status → ACTIVE, confidence badge shown.
    Navigate to Requirements for the project.
    Expected: MECH-BOLT-001 through MECH-BOLT-004 auto-generated requirements visible.
    Each requirement text contains the part names and torque values.

11. Navigate to /projects/1/system-architecture.
    Expected: Systems accordion with any assigned parts listed.
    Overview graph renders (may be empty if no electrical interfaces exist).

12. Navigate to /projects/1/interfaces.
    Expected: Label reads "ELECTRICAL INTERFACES" (not "INTERFACES").
    Yellow info banner about Systems management.
    All existing interface functionality works unchanged.
```

---

## M. Environment Variables Reference

Add these to `.env.example` in the project root:

```bash
# STEP file storage
UPLOAD_DIR=/tmp/astra_uploads
# e.g. for production: /var/astra/uploads

# GLTF cache (generated 3D views)
GLTF_CACHE_DIR=/tmp/astra_gltf_cache
# e.g. for production: /var/astra/gltf_cache

# pythonOCC availability (auto-detected — set to "false" to force stub mode)
# ASTRA_OCC_DISABLED=false
```

These must be read in the relevant service files via `os.environ.get(...)` with the `/tmp/...` defaults shown.

---

## N. Precise Tab Component Specification for Part Detail Page

The 5-tab layout in `parts-library/[id]/page.tsx` must use this exact Tailwind implementation pattern (matching the existing project tab style):

```tsx
// Tab navigation bar
<div className="border-b border-gray-200 dark:border-gray-700">
  <nav className="-mb-px flex space-x-8 overflow-x-auto" aria-label="Tabs">
    {TABS.map((tab) => (
      <button
        key={tab.id}
        onClick={() => setActiveTab(tab.id)}
        className={`
          whitespace-nowrap py-4 px-1 border-b-2 font-medium text-sm
          ${activeTab === tab.id
            ? 'border-blue-500 text-blue-600 dark:text-blue-400'
            : 'border-transparent text-gray-500 hover:text-gray-700 hover:border-gray-300 dark:text-gray-400 dark:hover:text-gray-200'}
        `}
        aria-current={activeTab === tab.id ? 'page' : undefined}
      >
        {tab.label}
      </button>
    ))}
  </nav>
</div>
```

Tab definitions:
```tsx
const TABS = [
  { id: 'overview',     label: 'Overview' },
  { id: 'dimensions',   label: 'Dimensions' },
  { id: 'material',     label: 'Material' },
  { id: 'performance',  label: 'Performance' },
  { id: 'procurement',  label: 'Procurement' },
] as const;

type TabId = typeof TABS[number]['id'];
```

---

## O. `PARTS_BUILD_LOG.md` — Pre-Populated Phase 0 Entry

After pre-flight, write this exact structure as the Phase 0 entry:

```markdown
### Phase 0 — Pre-flight
**Date:** <YYYY-MM-DD>
**Pre-flight alembic revision:** <value from `alembic current`>
**Pre-flight test count:** <N> passed (from pytest -q output)
**pythonOCC in container:** <run: docker exec astra-backend-1 python3 -c "from OCC.Core.STEPControl import STEPControl_Reader; print('OCC available')" and record result>
**DB snapshot:** ..\ASTRA-backups\pre_parts_<timestamp>.dump (<size> bytes)
**Branch SHA:** <git rev-parse HEAD>

**Environment check:**
- AI service configured: <check .env for AI_PROVIDER and AI_API_KEY>
- Document storage path: <UPLOAD_DIR value or default /tmp/astra_uploads>
- Existing document model: <yes (class name) / no — will create>
- `source_entity_type` current values: <SELECT enum_range(NULL::source_entity_type)>
- `suppliers` table exists: <yes/no — needed for optional CatalogPart link on approve>

**Anomalies / carry-forwards:**
<any issues found during pre-flight>
```
