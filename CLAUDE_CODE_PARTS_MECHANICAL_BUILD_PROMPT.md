# ASTRA — Parts Library & Mechanical Interfaces Build Prompt

**Source spec:** `ASTRA_PARTS_MECHANICAL_SPEC.docx` (ASTRA-SPEC-PARTS-001 v0.1)
**Target codebase root:** `C:\Users\Mason\Documents\ASTRA`
**Branch:** `feat/parts-mechanical-module` from current `main`
**Deliverable:** Full spec executed across 4 phases. `PARTS_BUILD_LOG.md` updated after every phase. Template in §12.

---

## 1. Operating Rules (read before touching any file)

1. **Run fully autonomously.** Do not ask for confirmation between steps. Do not check in between commits. Do not pause for approval on routine decisions. The only reasons to stop and surface an issue are:
   - A test that was passing is now broken and you cannot fix it within 3 attempts
   - A migration would destroy data that cannot be reconstructed
   - A spec ambiguity that will cause the wrong thing to be built for ALL downstream phases (not just the current one — use your judgment and proceed if the ambiguity is local)
   - A dependency is missing from the environment that you cannot install
   - Something that contradicts a Critical or High finding in `AUDIT_FINDINGS_POST_REMEDIATION.md` or `BACKLOG.md`

2. **Read the spec document before each phase.** The docx is at `C:\Users\Mason\Documents\ASTRA\ASTRA_PARTS_MECHANICAL_SPEC.docx`. The sections referenced in each phase below correspond to the numbered sections in that document. Spec beats this prompt if they conflict.

3. **Never run `alembic revision --autogenerate`.** The codebase has known autogenerate-drift hazards (tracked in original audit). Hand-write every migration.

4. **Syntax-validate every Python file before committing:**
   ```
   python3 -c "import ast; ast.parse(open('path').read())"
   ```

5. **Run `npm run typecheck` after every frontend file change.** Fix type errors before moving on.

6. **One commit per logical unit.** Models in one commit, migration in the next, router in the next. Phase boundary commits are always tagged `phase-N-complete`. History must be bisectable.

7. **Backend pagination cap is 200.** Every new list endpoint uses `limit: int = Query(default=50, le=200)`.

8. **Every `SQLEnum(...)` includes `values_callable=lambda x: [e.value for e in x]`.** No exceptions — this is a PostgreSQL enum requirement in this codebase.

9. **Every new project-scoped endpoint gets `Depends(project_member_required)`.** This was the fix for F-014/F-201. Do not regress it.

10. **No data duplication in the schema.** `ProjectPart` holds a FK to `LibraryPart`. It never copies fields. `SystemPartAssignment` holds a FK to `ProjectPart`. Read the spec §4.2 and §4.3 before writing any join model.

11. **The existing `/interfaces` backend route is NOT renamed.** The frontend tab rename to "Electrical Interfaces" is a label change only. The API path stays `/api/v1/interfaces/...` — zero API contract change.

12. **Write tests as you go.** Each new router gets a test file at `backend/tests/test_<router_name>.py`. Minimum: one test per endpoint, one negative membership test per project-scoped router. Tests run in the phase verification gate — do not defer them.

13. **Update `PARTS_BUILD_LOG.md` after every phase.** One entry per phase: status, files touched, commits, alembic revision, test count delta, verification output, anomalies found. Template in §12.

14. **Safety: never `docker compose down -v`.** That wipes the dev DB.

15. **Safety: before any migration that alters existing tables** (units, pins, requirements), snapshot the DB:
    ```
    docker exec astra-db-1 pg_dump -U astra -d astra -F c -f /tmp/pre_phase_N_$(date +%s).dump
    docker cp astra-db-1:/tmp/pre_phase_N_*.dump ..\ASTRA-backups\
    ```

---

## 2. Pre-Flight Checks (run once before Phase 1)

Run these in order. Fix anything that's broken before proceeding. Do not start Phase 1 until all pass.

```bash
# 1. Confirm clean main
git status
git log --oneline -5

# 2. Confirm stack is healthy
docker compose ps
docker exec astra-backend-1 alembic current
docker exec astra-backend-1 alembic check

# 3. Full test suite must be green before touching anything
docker exec astra-backend-1 pytest tests/ -q -m "not performance"
cd frontend && npm run typecheck && npm run build

# 4. DB snapshot (outside repo root)
docker exec astra-db-1 pg_dump -U astra -d astra -F c -f /tmp/pre_parts_module_$(date +%s).dump
docker cp "astra-db-1:/tmp/pre_parts_module_*.dump" ..\ASTRA-backups\

# 5. Create branch
git checkout main
git pull origin main
git checkout -b feat/parts-mechanical-module
git push -u origin feat/parts-mechanical-module
```

Record the pre-flight alembic revision (call it `HEAD_BEFORE`). Every migration in this build chains from that. Initialize `PARTS_BUILD_LOG.md` using the template in §12. Commit and push. Then proceed immediately to Phase 1 — no stop needed.

---

## 3. Phase 1 — Backend Data Model & Migrations

**Branch:** `feat/parts-mechanical-module`
**Spec sections:** §3.5 (data model), §3.2 (WPN scheme), §5.1 (MechanicalJoint), §4.2 (ProjectPart), §4.3 (SystemPartAssignment)
**Risk:** High — adds 6 new tables, modifies 1 existing table (units). DB snapshot from pre-flight is the rollback floor.
**Autonomy:** Run all of Phase 1 continuously. Only stop if a migration fails and you cannot resolve it.

---

### 3.1 New Python enums

Create `backend/app/models/parts_library.py`. Define these enums first (before any model), with `values_callable` on every `SQLEnum`:

```python
class PartType(str, Enum):
    FASTENER = "fastener"
    WASHER = "washer"
    INSERT = "insert"
    BRACKET = "bracket"
    ENCLOSURE = "enclosure"
    SEAL = "seal"
    BEARING = "bearing"
    HINGE_LATCH = "hinge_latch"
    THERMAL_INTERFACE = "thermal_interface"
    PCB_MECHANICAL = "pcb_mechanical"
    CUSTOM = "custom"

class PartStatus(str, Enum):
    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    SUPERSEDED = "superseded"
    OBSOLETE = "obsolete"

class MaterialClass(str, Enum):
    ALUMINUM = "aluminum"
    TITANIUM = "titanium"
    STEEL = "steel"
    STAINLESS_STEEL = "stainless_steel"
    NICKEL_ALLOY = "nickel_alloy"
    POLYMER = "polymer"
    COMPOSITE = "composite"
    CERAMIC = "ceramic"
    OTHER = "other"

class ThreadStandard(str, Enum):
    ISO_METRIC = "iso_metric"
    UNC = "unc"
    UNF = "unf"
    NPT = "npt"
    BSPP = "bspp"
    AN_NAS_MS = "an_nas_ms"
    CUSTOM = "custom"

class HeadType(str, Enum):
    SOCKET = "socket"
    HEX = "hex"
    PAN = "pan"
    FLAT = "flat"
    BUTTON = "button"
    TORX = "torx"
    FILLISTER = "fillister"
    TRUSS = "truss"

class LockingFeature(str, Enum):
    NONE = "none"
    NYLOK = "nylok"
    PREVAILING_TORQUE = "prevailing_torque"
    SAFETY_WIRE = "safety_wire"
    LOCTITE = "loctite"
    CASTELLATED = "castellated"
    LOCKWIRE_HOLE = "lockwire_hole"

class QualificationStatus(str, Enum):
    UNQUALIFIED = "unqualified"
    QUAL_TESTING = "qual_testing"
    QUALIFIED = "qualified"
    FLIGHT_PROVEN = "flight_proven"
    DEMANUFACTURED = "demanufactured"

class PendingPartsImportStatus(str, Enum):
    PENDING = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"

class ConfidenceLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class JointType(str, Enum):
    BOLTED = "bolted"
    RIVETED = "riveted"
    PRESS_FIT = "press_fit"
    ADHESIVE = "adhesive"
    WELD = "weld"
    SEAL = "seal"
    ALIGNMENT_PIN = "alignment_pin"
    THERMAL_BOND = "thermal_bond"
    SPRING_CLIP = "spring_clip"

class JointStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    SUPERSEDED = "superseded"
```

---

### 3.2 `LibraryPart` model

In the same file `backend/app/models/parts_library.py`, create the `LibraryPart` SQLAlchemy model with ALL fields from spec §3.5. Key implementation notes:

- `wardstone_part_number` — `Column(String(32), unique=True, nullable=False, index=True)`. Never user-settable via API — always generated server-side.
- `revision` — `Column(String(2), nullable=False, default="00")`. Two-digit zero-padded string.
- All decimal/float measurement fields (`mass_nominal`, `torque_nominal`, etc.) use `Column(Numeric(12, 4))` — NOT `Float`. Engineering-unit math precision is mandatory (learned from F-031 in original audit).
- `material_class` — `Column(SQLEnum(MaterialClass, values_callable=...), nullable=True)`
- `step_file_checksum` — `Column(String(64), nullable=True)` — SHA-256 hex string
- `step_file_id` — `Column(Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True)`
- `superseded_by_id` — `Column(Integer, ForeignKey("library_parts.id", ondelete="SET NULL"), nullable=True)` — self-referential
- `approved_by_id` — `Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)`
- `approved_at` — `Column(DateTime(timezone=True), nullable=True)`
- `project_id` — NOT on `LibraryPart`. This is a global record. No project scope.
- Audit columns: `created_at`, `updated_at`, `created_by_id` (FK users) — standard pattern matching other models.
- Index: composite index on `(part_type, status)` for filtered list queries.
- Index: `step_file_checksum` for dedup checks on upload.

Full field list comes from spec §3.5.1 through §3.5.5. Implement all of them. Use `nullable=True` for every optional field. Do not skip fields — the frontend detail view needs them all.

---

### 3.3 `WPNSequence` model

```python
class WPNSequence(Base):
    __tablename__ = "wpn_sequences"
    part_type_code = Column(String(8), primary_key=True)  # FAST, WASH, etc.
    next_val = Column(Integer, nullable=False, default=1)
```

This is the atomic counter for WPN assignment. The assignment function (in a service, not a model) does:
```python
def assign_wpn(db: Session, part_type: PartType) -> str:
    code = WPN_TYPE_CODES[part_type]  # dict: PartType -> 4-char code
    seq = db.query(WPNSequence).filter_by(part_type_code=code).with_for_update().first()
    if not seq:
        seq = WPNSequence(part_type_code=code, next_val=1)
        db.add(seq)
    wpn = f"WS-{code}-{seq.next_val:06d}-00"
    seq.next_val += 1
    return wpn
```

`with_for_update()` is mandatory — this is the race-condition fix for F-203's pattern applied to WPNs.

WPN_TYPE_CODES mapping:
```
FASTENER → FAST, WASHER → WASH, INSERT → INSR, BRACKET → BRKT,
ENCLOSURE → ENCL, SEAL → SEAL, BEARING → BEAR, HINGE_LATCH → HNGL,
THERMAL_INTERFACE → THIF, PCB_MECHANICAL → PCBM, CUSTOM → CUST
```

---

### 3.4 `PendingPartsImport` model

```python
class PendingPartsImport(Base):
    __tablename__ = "pending_parts_imports"
    id: int (PK)
    document_id: FK → documents.id (the uploaded STEP file)
    status: SQLEnum(PendingPartsImportStatus)
    proposed_data: Column(JSON)          # full proposed LibraryPart field dict
    confidence_scores: Column(JSON)      # field_name -> "high"/"medium"/"low"
    low_confidence_fields: Column(ARRAY(String))  # field names needing reviewer attention
    extraction_log: Column(Text)         # raw parser output for debugging
    parser_version: Column(String(32))   # semantic version of the STEP parser
    reviewed_by_id: FK → users.id (nullable)
    reviewed_at: DateTime (nullable)
    rejection_reason: Text (nullable)
    created_at, updated_at: standard audit columns
```

---

### 3.5 `ProjectPart` model

```python
class ProjectPart(Base):
    __tablename__ = "project_parts"
    id: int (PK)
    project_id: FK → projects.id (ondelete="CASCADE"), index=True
    library_part_id: FK → library_parts.id (ondelete="RESTRICT")  # never auto-delete a library part that's in use
    quantity: Column(Integer, nullable=False, default=1)
    designation: Column(String(64), nullable=True)   # e.g. HW-J1
    notes: Column(Text, nullable=True)
    added_by_id: FK → users.id (ondelete="SET NULL")
    added_at: DateTime(timezone=True)
    UniqueConstraint("project_id", "library_part_id", name="uq_project_part")
```

Relationship: `project_part.library_part` → `LibraryPart` (lazy loaded, selectinload in list queries)

---

### 3.6 `SystemPartAssignment` model

```python
class SystemPartAssignment(Base):
    __tablename__ = "system_part_assignments"
    id: int (PK)
    system_id: FK → systems.id (ondelete="CASCADE"), index=True
    project_part_id: FK → project_parts.id (ondelete="CASCADE"), index=True
    position_order: Column(Integer, nullable=False, default=0)  # display ordering
    assigned_by_id: FK → users.id (ondelete="SET NULL")
    assigned_at: DateTime(timezone=True)
    UniqueConstraint("system_id", "project_part_id", name="uq_system_part_assignment")
```

---

### 3.7 `MechanicalJoint` model

Full model per spec §5.1.1. Key implementation notes:

- `joint_id` — `Column(String(32), unique=True, nullable=False, index=True)` — format `MJ-{project_id:04d}-{seq:06d}`. Assigned by the same `with_for_update()` sequence pattern as WPN.
- `part_a_id` and `part_b_id` — both `FK → project_parts.id (ondelete="RESTRICT")`. These are the two project parts being joined.
- `fastener_part_id` — `FK → library_parts.id (ondelete="SET NULL"), nullable=True`
- `seal_part_id` — `FK → library_parts.id (ondelete="SET NULL"), nullable=True`
- All measurement fields (`torque_nominal`, `torque_min`, `torque_max`, `engagement_length`, `mating_surface_flatness`, `leak_rate_max`, `test_pressure`) — `Numeric(12, 4)`.
- `source_step_file_id` — `FK → documents.id (ondelete="SET NULL"), nullable=True`
- `source_step_entity` — `Column(Text, nullable=True)` — stores JSON array of STEP entity IDs
- `confidence` — `SQLEnum(ConfidenceLevel, values_callable=...)`
- `status` — `SQLEnum(JointStatus, values_callable=...)`
- `project_id` — `FK → projects.id (ondelete="CASCADE"), index=True` — for fast project-scoped queries
- Composite index: `(project_id, status)`, `(part_a_id, part_b_id)`
- RequirementSourceLink wiring: `MechanicalJoint` must be added to the `SourceEntityType` enum in `backend/app/models/req_sync.py`. Add `MECHANICAL_JOINT = "mechanical_joint"`. Add the SQLAlchemy `after_update` / `after_delete` event listener for `MechanicalJoint` in `backend/app/services/req_sync/listener.py` — follow the exact same pattern as the existing listeners for `Interface`, `WireHarness`, etc.

---

### 3.8 `MechanicalJointSequence` model

Same pattern as `WPNSequence` but keyed by `project_id` (integer). One row per project, `with_for_update()` on assignment.

---

### 3.9 Update `__init__.py`

In `backend/app/models/__init__.py`, re-export all new models:
```python
from app.models.parts_library import (
    LibraryPart, WPNSequence, PendingPartsImport,
    ProjectPart, SystemPartAssignment, MechanicalJoint,
    MechanicalJointSequence, PartType, PartStatus, MaterialClass,
    ThreadStandard, HeadType, LockingFeature, QualificationStatus,
    PendingPartsImportStatus, ConfidenceLevel, JointType, JointStatus
)
```

---

### 3.10 Pydantic schemas

Create `backend/app/schemas/parts_library.py`. Define schemas for:

- `LibraryPartCreate` — all user-settable fields. Exclude: `wardstone_part_number`, `revision`, `status`, `approved_by_id`, `approved_at`, `step_file_checksum`, `created_at`, `updated_at`.
- `LibraryPartUpdate` — same as Create but all fields Optional. Used for PATCH.
- `LibraryPartResponse` — all fields including computed ones. Include: `wardstone_part_number`, `status`, `approved_by`, `supplier_name` (from joined Supplier if linked).
- `LibraryPartSummary` — condensed for list views: `id`, `wardstone_part_number`, `name`, `part_type`, `status`, `manufacturer_name`, `manufacturer_part_number`, `material_name`, `approved_at`.
- `ProjectPartCreate` — `library_part_id`, `quantity`, `designation`, `notes`.
- `ProjectPartResponse` — includes nested `LibraryPartSummary`.
- `SystemPartAssignmentCreate` — `project_part_id`, `position_order`.
- `SystemPartAssignmentResponse` — includes nested `ProjectPartResponse`.
- `MechanicalJointCreate` — all user-settable fields.
- `MechanicalJointUpdate` — all Optional.
- `MechanicalJointResponse` — all fields + nested `LibraryPartSummary` for fastener and seal.
- `PendingPartsImportResponse` — full import record including `proposed_data`, `confidence_scores`, `low_confidence_fields`.
- `PendingPartsImportApprove` — `overrides: dict[str, Any]` (reviewer's field overrides before approval).

Use `model_config = ConfigDict(from_attributes=True)` (Pydantic v2 pattern matching the rest of the codebase). Every `Optional[X]` field has `= None`. No mutable defaults.

---

### 3.11 Alembic migration

Hand-write migration `backend/alembic/versions/NNNN_parts_library_and_mechanical.py` where `NNNN` is the next number after the current `alembic current` head. Set `down_revision` to that head.

Migration `upgrade()` order:
1. Create all new enum types: `part_type`, `part_status`, `material_class`, `thread_standard`, `head_type`, `locking_feature`, `qualification_status`, `pending_parts_import_status`, `confidence_level`, `joint_type`, `joint_status`
2. Create `wpn_sequences` table
3. Create `library_parts` table (all columns from §3.2 above — do not skip any)
4. Create `pending_parts_imports` table
5. Create `project_parts` table
6. Create `system_part_assignments` table
7. Create `mechanical_joint_sequences` table
8. Create `mechanical_joints` table
9. `ALTER TABLE units ADD COLUMN IF NOT EXISTS library_part_id INTEGER REFERENCES library_parts(id) ON DELETE SET NULL` — nullable, new FK for catalog-placed units
10. Seed `wpn_sequences` rows for all 11 part type codes with `next_val=1`
11. Add `MECHANICAL_JOINT` to the `source_entity_type` PostgreSQL enum: `op.execute("ALTER TYPE source_entity_type ADD VALUE IF NOT EXISTS 'mechanical_joint'")`
12. Create all indexes: `(library_parts.part_type, library_parts.status)`, `library_parts.step_file_checksum`, `project_parts.project_id`, `system_part_assignments.system_id`, `mechanical_joints.(project_id, status)`, `mechanical_joints.(part_a_id, part_b_id)`

Migration `downgrade()` — full reversal in exact reverse order. Drop indexes first, then tables, then enum values (note: PostgreSQL cannot remove enum values without recreating the type — handle this with `op.execute("ALTER TYPE source_entity_type RENAME TO source_entity_type_old")` + recreate without the value + update column + drop old).

**Test the down path on a throwaway connection before declaring the migration done.**

---

### 3.12 Phase 1 verification gate

Run all of these. All must pass before proceeding to Phase 2.

```bash
docker exec astra-backend-1 alembic upgrade head
docker exec astra-backend-1 alembic check
docker exec astra-db-1 psql -U astra -d astra -c "\d library_parts"
docker exec astra-db-1 psql -U astra -d astra -c "\d project_parts"
docker exec astra-db-1 psql -U astra -d astra -c "\d mechanical_joints"
docker exec astra-db-1 psql -U astra -d astra -c "SELECT * FROM wpn_sequences;"
docker exec astra-db-1 psql -U astra -d astra -c "SELECT enum_range(NULL::part_type);"
docker exec astra-backend-1 python3 -c "from app.models.parts_library import LibraryPart, MechanicalJoint; print('models OK')"
docker exec astra-backend-1 python3 -c "from app.schemas.parts_library import LibraryPartCreate, MechanicalJointCreate; print('schemas OK')"
docker exec astra-backend-1 pytest tests/ -q -m "not performance"
```

Full test suite must still pass (no regression). Commit with message `feat(parts): Phase 1 complete — data model, migrations, schemas`.

---

## 4. Phase 2 — Parts Library Backend (CRUD + STEP Parser + WPN Service)

**Spec sections:** §3.1 (part types), §3.2 (WPN), §3.3 (MPN), §3.4 (supplier linkage), §3.6 (STEP parser), §3.7 (review queue)
**Risk:** Medium — new endpoints only, no modification of existing routes.
**Autonomy:** Run all of Phase 2 continuously.

---

### 4.1 Install STEP parser dependency

```bash
docker exec astra-backend-1 pip install pythonOCC-core --break-system-packages
```

If `pythonOCC-core` is not available on the container's pip index (it has unusual packaging), install via conda or use the `pip install pythonocc-core` alternative. If neither is available in the Docker environment, implement a **stub parser** that:
- Reads the STEP file header to confirm it's a valid STEP file
- Extracts the PRODUCT entity names and descriptions via regex on the raw text
- Returns a `ParserResult` with all geometric fields as `None` and `confidence=LOW`
- Logs a warning: `"pythonOCC not available — geometric extraction disabled, metadata extraction only"`

The stub allows the full pipeline to function (manual entry + review queue) even without the geometry library. Flag this in `PARTS_BUILD_LOG.md` as a known gap to resolve when the Docker image is updated.

---

### 4.2 WPN service

Create `backend/app/services/parts/wpn_service.py`:

```python
WPN_TYPE_CODES = {
    PartType.FASTENER: "FAST",
    PartType.WASHER: "WASH",
    PartType.INSERT: "INSR",
    PartType.BRACKET: "BRKT",
    PartType.ENCLOSURE: "ENCL",
    PartType.SEAL: "SEAL",
    PartType.BEARING: "BEAR",
    PartType.HINGE_LATCH: "HNGL",
    PartType.THERMAL_INTERFACE: "THIF",
    PartType.PCB_MECHANICAL: "PCBM",
    PartType.CUSTOM: "CUST",
}

def assign_wpn(db: Session, part_type: PartType) -> str:
    """Thread-safe WPN assignment using SELECT FOR UPDATE."""
    code = WPN_TYPE_CODES[part_type]
    seq = (
        db.query(WPNSequence)
        .filter_by(part_type_code=code)
        .with_for_update()
        .first()
    )
    if not seq:
        seq = WPNSequence(part_type_code=code, next_val=1)
        db.add(seq)
        db.flush()
    wpn = f"WS-{code}-{seq.next_val:06d}-00"
    seq.next_val += 1
    return wpn

def bump_wpn_revision(wpn: str) -> str:
    """Increment the revision suffix: WS-FAST-000001-00 → WS-FAST-000001-01."""
    parts = wpn.rsplit("-", 1)
    new_rev = int(parts[1]) + 1
    return f"{parts[0]}-{new_rev:02d}"
```

---

### 4.3 STEP parser service

Create `backend/app/services/parts/step_parser.py`. Structure:

```python
@dataclass
class StepParserResult:
    # Metadata
    product_name: str | None
    product_description: str | None
    manufacturer_part_number: str | None
    # Geometry (None if pythonOCC unavailable)
    bounding_box_x: Decimal | None
    bounding_box_y: Decimal | None
    bounding_box_z: Decimal | None
    volume: Decimal | None
    surface_area: Decimal | None
    nominal_diameter: Decimal | None
    nominal_length: Decimal | None
    thread_size: str | None
    thread_standard: ThreadStandard | None
    hole_pattern_count: int | None
    hole_pattern_diameter: Decimal | None
    hole_pattern_pcd: Decimal | None
    # Confidence
    confidence_scores: dict[str, ConfidenceLevel]
    low_confidence_fields: list[str]
    parser_version: str
    extraction_log: str

def parse_step_file(file_path: str) -> StepParserResult:
    """Main entry point. Tries full pythonOCC extraction, falls back to metadata-only."""
    log = []
    try:
        from OCC.Core.STEPControl import STEPControl_Reader
        return _parse_with_occ(file_path, log)
    except ImportError:
        log.append("pythonOCC not available — metadata extraction only")
        return _parse_metadata_only(file_path, log)

def _parse_metadata_only(file_path: str, log: list) -> StepParserResult:
    """Regex-based STEP text extraction. No geometry."""
    with open(file_path, 'r', errors='replace') as f:
        content = f.read()
    # Extract PRODUCT( 'name', 'description', ... ) entities
    # Extract PRODUCT_DEFINITION_CONTEXT for CAD origin
    # Attempt MPN extraction from filename and PRODUCT name
    ...

def _parse_with_occ(file_path: str, log: list) -> StepParserResult:
    """Full B-rep extraction using OpenCASCADE."""
    # Read STEP file
    # Compute bounding box via BRep_Builder
    # Compute volume + surface area via BRepGProp
    # Extract hole features via BRep_Tool face iteration
    # Match hole diameters to thread table (THREAD_RECOGNITION_TABLE below)
    # Detect bolt circles via clustering of hole center points
    ...

# Thread recognition table from spec §3.6.1
THREAD_RECOGNITION_TABLE = [
    (3.3, 3.5, "M3×0.5", ThreadStandard.ISO_METRIC, Decimal("1.2")),
    (4.4, 4.6, "M4×0.7", ThreadStandard.ISO_METRIC, Decimal("2.9")),
    (5.4, 5.6, "M5×0.8", ThreadStandard.ISO_METRIC, Decimal("5.7")),
    (6.5, 6.7, "M6×1.0", ThreadStandard.ISO_METRIC, Decimal("9.8")),
    (8.5, 8.7, "M8×1.25", ThreadStandard.ISO_METRIC, Decimal("23.0")),
    (10.5, 10.7, "M10×1.5", ThreadStandard.ISO_METRIC, Decimal("45.0")),
    (3.28, 3.32, "#6-32 UNC", ThreadStandard.UNC, Decimal("0.9")),
    (4.19, 4.22, "#8-32 UNC", ThreadStandard.UNC, Decimal("1.5")),
    (5.16, 5.18, "#10-32 UNF", ThreadStandard.UNF, Decimal("2.4")),
    (6.45, 6.50, "1/4-28 UNF", ThreadStandard.UNF, Decimal("6.8")),
]
```

---

### 4.4 AI interpretation service

Create `backend/app/services/parts/ai_interpreter.py`. Uses the existing three-tier AI pattern (`services/ai/`). 

System prompt:
```
You are an aerospace mechanical engineering AI. Given a structured description of a mechanical part extracted from a STEP file, you will:
1. Confirm or correct the part type classification
2. Infer the material and material class from the part name, description, and geometry
3. Look up nominal torque specs for identified fastener threads if not already populated
4. Flag any unusual joint configurations
5. Identify the locking feature type if discernible from the part name

Respond ONLY with a JSON object. No prose. Schema:
{
  "part_type": "fastener|washer|...",
  "material_name": "string or null",
  "material_class": "aluminum|titanium|...|null",
  "torque_nominal": number_or_null,
  "locking_feature": "none|nylok|...|null",
  "confidence_overrides": {"field_name": "high|medium|low"},
  "flags": ["string"]
}
```

Input to the AI: structured JSON of the `StepParserResult` plus the raw product name and description. Output parsed with the regex fallback from `services/ai/` if JSON parse fails.

---

### 4.5 Parts Library router

Create `backend/app/routers/parts_library.py`. This is the GLOBAL (non-project-scoped) router. Register it in `main.py` with prefix `/api/v1/parts-library`.

Endpoints:

```
GET    /parts-library/                    List all parts (filterable: part_type, status, material_class, search)
POST   /parts-library/                    Create part manually (assigns WPN server-side)
GET    /parts-library/{part_id}           Get part detail
PATCH  /parts-library/{part_id}           Update part (bumps revision if dimensional fields change)
GET    /parts-library/{part_id}/history   Revision history
POST   /parts-library/upload-step         Upload STEP file → triggers background parser → returns pending_import_id
GET    /parts-library/pending-imports/    List pending imports
GET    /parts-library/pending-imports/{id} Get pending import detail
POST   /parts-library/pending-imports/{id}/approve  Approve with optional field overrides → commits LibraryPart
POST   /parts-library/pending-imports/{id}/reject   Reject with reason
GET    /parts-library/search?q=...        Full-text search across name, WPN, MPN, manufacturer
```

Auth requirements:
- All GET endpoints: `Depends(get_current_user)` — any authenticated user can browse
- POST / PATCH / approve / reject: `Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER))`
- Audit log emission: every create/approve/reject/update emits an audit event via `audit_service`

`POST /parts-library/upload-step`:
1. Validate file extension is `.step` or `.stp`
2. Validate file size ≤ 50MB (the body size limit middleware handles this but double-check)
3. Compute SHA-256 of the file content — check for duplicate (if `library_parts` already has this checksum, return the existing part ID with a 200 and a `duplicate: true` flag rather than re-parsing)
4. Save file to the documents system (existing `Document` model)
5. Enqueue background task: `BackgroundTasks.add_task(run_step_parser_pipeline, document_id, current_user.id)`
6. Return immediately with `{"pending_import_id": ..., "message": "Parsing in progress"}`

`run_step_parser_pipeline(document_id, user_id)` (background task):
1. Load the document file from storage
2. Call `parse_step_file(path)` → `StepParserResult`
3. Call `ai_interpreter.interpret(result)` → merged result with AI overrides
4. Compute `confidence_scores` and `low_confidence_fields`
5. Create `PendingPartsImport` record with `proposed_data` = full field dict, `status=PENDING`
6. Emit audit event: `parts_library.import_pending`

`POST /parts-library/pending-imports/{id}/approve`:
1. Load `PendingPartsImport`, verify `status == PENDING or UNDER_REVIEW`
2. Merge `proposed_data` with any `overrides` from the request body
3. Assign WPN via `wpn_service.assign_wpn(db, part_type)` inside the transaction
4. Create `LibraryPart` with all merged fields, `status=APPROVED`, `approved_by_id=current_user.id`, `approved_at=now()`
5. If `supplier_id` is set: create or link `CatalogPart` entry (per spec §3.4). Use existing `catalog.py` model.
6. Mark `PendingPartsImport.status = APPROVED`
7. Emit audit event: `parts_library.part_approved`
8. Return `LibraryPartResponse`

---

### 4.6 Project Parts router

Create `backend/app/routers/project_parts.py`. Register in `main.py` with prefix `/api/v1/projects/{project_id}/parts`. All endpoints get `Depends(project_member_required)`.

```
GET    /projects/{project_id}/parts/                 List project parts (with nested LibraryPartSummary)
POST   /projects/{project_id}/parts/                 Add part to project (creates ProjectPart)
DELETE /projects/{project_id}/parts/{project_part_id} Remove from project (destroys ProjectPart join record only)
PATCH  /projects/{project_id}/parts/{project_part_id} Update quantity, designation, notes
GET    /projects/{project_id}/parts/unassigned        Parts not yet assigned to any system
```

N+1 prevention: the list endpoint must `selectinload(ProjectPart.library_part)` — do not lazy-load inside a loop.

---

### 4.7 System Part Assignment router

Add to `backend/app/routers/systems.py` (existing file):

```
POST   /projects/{project_id}/systems/{system_id}/parts/              Assign a ProjectPart to a system
DELETE /projects/{project_id}/systems/{system_id}/parts/{assignment_id} Remove assignment
GET    /projects/{project_id}/systems/{system_id}/parts/              List parts assigned to a system
PATCH  /projects/{project_id}/systems/{system_id}/parts/{assignment_id} Update position_order
```

All get `Depends(project_member_required)`. No data duplication — this writes to `system_part_assignments` only.

---

### 4.8 Mechanical Joints router

Create `backend/app/routers/mechanical_joints.py`. Register with prefix `/api/v1/projects/{project_id}/mechanical-joints`. All endpoints `Depends(project_member_required)`.

```
GET    /mechanical-joints/                    List joints (filter: joint_type, status, part_id, confidence)
POST   /mechanical-joints/                    Create joint manually
GET    /mechanical-joints/{joint_id}          Joint detail
PATCH  /mechanical-joints/{joint_id}          Update joint
DELETE /mechanical-joints/{joint_id}          Delete joint (if DRAFT only — ACTIVE joints require admin force=true)
POST   /mechanical-joints/{joint_id}/approve  Change status DRAFT → ACTIVE (emits auto-req trigger)
POST   /upload-assembly                       Upload assembly STEP → triggers assembly parser (returns job_id)
GET    /assembly-parse-status/{job_id}        Poll parser status
```

`POST /{project_id}/mechanical-joints/{joint_id}/approve`:
1. Set `status = ACTIVE`
2. Emit `after_update`-equivalent event to trigger the req_sync listener for `MECHANICAL_JOINT`
3. The listener fans out to any RequirementSourceLinks on this joint and creates/applies sync proposals per the existing `fan_out.py` policy
4. Emit audit event

---

### 4.9 Auto-requirement templates

Create `backend/app/services/parts/mechanical_req_templates.py`. Define the 10 templates from spec §5.4 as a Python dict mapping template ID → template string with `{field_name}` placeholders. Wire these into the existing `auto_requirements.py` service (in `services/interface/` or equivalent) as a new source type.

The template renderer resolves `{field_name}` tokens by:
1. Looking up the `MechanicalJoint` record
2. Looking up the linked `LibraryPart` records (fastener, seal)
3. Building a context dict
4. Doing string `.format_map(context)` — no eval, no Jinja

For `MECH-BOLT-001`, the context dict includes:
```python
{
    "part_a_name": joint.part_a.library_part.name,
    "part_b_name": joint.part_b.library_part.name,
    "fastener_count": joint.fastener_count,
    "fastener_description": joint.fastener_part.name if joint.fastener_part else "fasteners",
    "torque_nominal": joint.torque_nominal,
    "torque_tolerance": (joint.torque_max - joint.torque_min) / 2 if joint.torque_max and joint.torque_min else "TBD",
}
```

---

### 4.10 Tests

Create `backend/tests/test_parts_library.py`, `test_project_parts.py`, `test_mechanical_joints.py`. Minimum test coverage:

- `test_wpn_assignment_is_unique`: concurrent requests cannot produce duplicate WPNs (use threading)
- `test_create_part_manually`: POST → 201, WPN is assigned, status=DRAFT
- `test_approve_import_assigns_wpn`: approve pending import → WPN is set, status=APPROVED
- `test_approve_creates_catalog_part_when_supplier_set`: supplier_id in overrides → CatalogPart created
- `test_add_part_to_project`: ProjectPart join created, library data not duplicated
- `test_remove_part_from_project_doesnt_delete_library`: library_part still exists after removal
- `test_assign_part_to_system`: SystemPartAssignment created
- `test_mechanical_joint_create`: joint created in DRAFT status
- `test_mechanical_joint_approve_triggers_req`: approving a joint with a req template fires auto-req creation
- `test_non_member_cannot_add_project_part`: 403 for non-member user (negative membership test)
- `test_step_upload_returns_pending_import`: upload a minimal valid STEP file (fixture) → pending import created
- `test_duplicate_step_checksum_returns_existing`: re-upload same file → 200 with `duplicate: true`

---

### 4.11 Phase 2 verification gate

```bash
docker exec astra-backend-1 pytest tests/test_parts_library.py tests/test_project_parts.py tests/test_mechanical_joints.py -v
docker exec astra-backend-1 pytest tests/ -q -m "not performance"
docker exec astra-backend-1 python -c "from app.main import app; print([r.path for r in app.routes if 'parts' in r.path])"
```

Commit: `feat(parts): Phase 2 complete — Parts Library CRUD, STEP parser, WPN service, mechanical joints router`.

---

## 5. Phase 3 — Frontend: Parts Library Global UI + Engineering Nav Restructure

**Spec sections:** §3.7 (Parts Library UI), §4.1 (tab order), §4.2 (PARTS tab), §4.3 (System Architecture)
**Risk:** Medium — routing changes affect existing navigation. Run `npm run typecheck` and `npm run build` after every file.
**Autonomy:** Run continuously. The only stop condition is a broken build you cannot fix in 3 attempts.

---

### 5.1 API client additions

Add to `frontend/src/lib/api.ts` (or the appropriate api client file for the codebase):

```typescript
// Parts Library (global)
export const partsLibraryAPI = {
  list: (params: PartsLibraryListParams) => axios.get('/parts-library/', { params }),
  get: (id: number) => axios.get(`/parts-library/${id}`),
  create: (data: LibraryPartCreate) => axios.post('/parts-library/', data),
  update: (id: number, data: LibraryPartUpdate) => axios.patch(`/parts-library/${id}`, data),
  uploadStep: (file: File) => { /* FormData upload */ },
  getPendingImports: () => axios.get('/parts-library/pending-imports/'),
  getPendingImport: (id: number) => axios.get(`/parts-library/pending-imports/${id}`),
  approveImport: (id: number, overrides: Record<string, unknown>) =>
    axios.post(`/parts-library/pending-imports/${id}/approve`, { overrides }),
  rejectImport: (id: number, reason: string) =>
    axios.post(`/parts-library/pending-imports/${id}/reject`, { reason }),
  search: (q: string) => axios.get('/parts-library/search', { params: { q } }),
};

// Project Parts
export const projectPartsAPI = {
  list: (projectId: number) => axios.get(`/projects/${projectId}/parts/`),
  add: (projectId: number, data: ProjectPartCreate) => axios.post(`/projects/${projectId}/parts/`, data),
  remove: (projectId: number, projectPartId: number) =>
    axios.delete(`/projects/${projectId}/parts/${projectPartId}`),
  update: (projectId: number, projectPartId: number, data: Partial<ProjectPartCreate>) =>
    axios.patch(`/projects/${projectId}/parts/${projectPartId}`, data),
  listUnassigned: (projectId: number) => axios.get(`/projects/${projectId}/parts/unassigned`),
};

// System Part Assignments
export const systemPartsAPI = {
  list: (projectId: number, systemId: number) =>
    axios.get(`/projects/${projectId}/systems/${systemId}/parts/`),
  assign: (projectId: number, systemId: number, data: SystemPartAssignmentCreate) =>
    axios.post(`/projects/${projectId}/systems/${systemId}/parts/`, data),
  remove: (projectId: number, systemId: number, assignmentId: number) =>
    axios.delete(`/projects/${projectId}/systems/${systemId}/parts/${assignmentId}`),
};

// Mechanical Joints
export const mechanicalJointsAPI = {
  list: (projectId: number, params?: MechanicalJointsListParams) =>
    axios.get(`/projects/${projectId}/mechanical-joints/`, { params }),
  get: (projectId: number, jointId: string) =>
    axios.get(`/projects/${projectId}/mechanical-joints/${jointId}`),
  create: (projectId: number, data: MechanicalJointCreate) =>
    axios.post(`/projects/${projectId}/mechanical-joints/`, data),
  update: (projectId: number, jointId: string, data: MechanicalJointUpdate) =>
    axios.patch(`/projects/${projectId}/mechanical-joints/${jointId}`, data),
  approve: (projectId: number, jointId: string) =>
    axios.post(`/projects/${projectId}/mechanical-joints/${jointId}/approve`),
  delete: (projectId: number, jointId: string, force = false) =>
    axios.delete(`/projects/${projectId}/mechanical-joints/${jointId}`, { params: { force } }),
  uploadAssembly: (projectId: number, file: File) => { /* FormData */ },
};
```

Add TypeScript interfaces for all request/response types. These must exactly mirror the Pydantic schemas from Phase 2 — no drift. Use `Decimal` as `string` on the frontend (JSON serialization of Decimal comes as string from FastAPI).

---

### 5.2 Global nav — Parts Library entry

In `frontend/src/components/layout/Sidebar.tsx` (or the equivalent global nav component):

Add a "Parts Library" nav entry at the global level, alongside the existing "Catalog" entry. Use the same nav item component pattern. Icon: wrench or cog (whichever is available in the project's icon set — check existing usage). Route: `/parts-library`.

Do NOT remove or modify the existing "Catalog" entry.

---

### 5.3 Parts Library pages

Create the following Next.js App Router pages:

**`frontend/src/app/(parts-library)/parts-library/page.tsx`** — List view
- Filter bar: Part Type (multi-select chips), Status (multi-select), search input (debounced, calls `/parts-library/search`)
- Table with columns: WPN, Name, Type badge, Material, Manufacturer, MPN, Status badge, Approved date
- "Upload STEP File" button → opens `StepUploadModal`
- "New Part" button → navigates to `/parts-library/new`
- Loading skeleton (not spinner) while data loads
- Empty state: "No parts in the library yet. Upload a STEP file or create a part manually."

**`frontend/src/app/(parts-library)/parts-library/new/page.tsx`** — Manual create form
- Five-tab form layout matching spec §3.7.2: Identification, Dimensions, Material, Performance, Procurement
- All fields from spec §3.5 groups. Required fields marked with *.
- WPN is shown as "Will be auto-assigned" — not an input.
- Save → POST /parts-library/ → on success navigate to the new part's detail page.

**`frontend/src/app/(parts-library)/parts-library/[id]/page.tsx`** — Part detail
- Five-tab layout: Overview, Dimensions, Material, Performance, Procurement
- Read mode by default. Edit button → inline edit mode (same tabs, now editable).
- Overview tab: WPN badge (monospace, distinct style), name, part type chip, status badge, description, manufacturer, MPN.
- Right panel (collapsed on mobile): "3D Preview" — renders the part's STEP as a three.js viewer (see §7 below). If no STEP file, shows placeholder with upload link.
- "Linked Projects" section: list of projects using this part.
- "Requirements" section: list of auto-requirements sourced from this part (read-only links).
- Breadcrumb: Parts Library → [Part Name]

**`frontend/src/app/(parts-library)/parts-library/pending-imports/page.tsx`** — Review queue
- List of `PendingPartsImport` records with status badges.
- Click a row → navigate to `pending-imports/[id]`.

**`frontend/src/app/(parts-library)/parts-library/pending-imports/[id]/page.tsx`** — Review detail
- Two-panel layout: left = 3D preview of the parsed STEP geometry; right = proposed fields with confidence indicators.
- LOW confidence fields rendered with amber background and a warning icon.
- Each field is editable inline before approving.
- Approve button (confirm dialog) → calls `approveImport` with any edited values as overrides.
- Reject button → modal with required reason text.

**`StepUploadModal` component** (`frontend/src/components/parts/StepUploadModal.tsx`):
- Drag-and-drop area accepting `.step` and `.stp` files only.
- File size validation: max 50MB client-side before upload.
- Upload progress bar.
- On success: "Parsing in progress. You'll be redirected to the review queue." → navigate to pending-imports list.
- On duplicate checksum: "This exact file is already in the Parts Library: [link to existing part]."

---

### 5.4 Engineering nav restructure

In the project-level left navigation (the Engineering section sidebar — likely `frontend/src/app/projects/[id]/` layout or sidebar component):

**Changes to make:**
1. Find the existing "Interfaces" tab entry. Rename label to "ELECTRICAL INTERFACES". Route stays the same (`/projects/[id]/interfaces`). No functional change.
2. Add "PARTS" tab. Route: `/projects/[id]/parts`. Position: second in Engineering section.
3. Add "MECHANICAL INTERFACES" tab. Route: `/projects/[id]/mechanical-interfaces`. Position: third.
4. Add "SYSTEM ARCHITECTURE" tab. Route: `/projects/[id]/system-architecture`. Position: first (before PARTS).

Final Engineering section tab order:
```
1. SYSTEM ARCHITECTURE   /projects/[id]/system-architecture
2. PARTS                 /projects/[id]/parts
3. ELECTRICAL INTERFACES /projects/[id]/interfaces       ← renamed label only
4. MECHANICAL INTERFACES /projects/[id]/mechanical-interfaces
```

---

### 5.5 PARTS tab page

**`frontend/src/app/projects/[id]/parts/page.tsx`**
- "Add Part from Library" button → opens `LibraryPartPickerModal` (search/filter dialog over the global Parts Library).
- Table: Designation, WPN (link to library detail), Name, Type, Material, Quantity, System (badge or "Unassigned" in amber), Actions.
- Unassigned badge on rows where no `SystemPartAssignment` exists.
- Row click → opens a read-only slide-over panel showing the full library part detail (same data as the global detail page, but in a panel — no navigation away).
- Remove button (trash icon) → confirmation → DELETE project part.

**`LibraryPartPickerModal` component** (`frontend/src/components/parts/LibraryPartPickerModal.tsx`):
- Searchable, filterable list of all `APPROVED` `LibraryPart` records.
- Shows: WPN, Name, Type, Material, Manufacturer.
- "Add to Project" button on each row. Quantity input (default 1). Optional designation field.
- Multi-select supported (add multiple parts in one modal session).

---

### 5.6 SYSTEM ARCHITECTURE tab page

**`frontend/src/app/projects/[id]/system-architecture/page.tsx`**

Two subtabs: Overview and Systems.

**Overview subtab:**
- Force-directed graph (reuse the existing `ForceGraph` component pattern from the project). Nodes: Systems (large, colored by system type) and Parts (small, colored by part type). Edges: electrical interface (blue), mechanical joint (amber), both (split).
- Filter toggles: Electrical edges, Mechanical edges, Unconnected parts.
- Clicking a System node → opens system detail side panel.
- Clicking a Part node → opens part detail side panel (library data).
- Empty state: "No systems yet. Create a system to start building your architecture."

**Systems subtab:**
- List of systems in this project (existing data — Systems were previously in Interfaces).
- Each system row expandable to show its assigned parts.
- "Assign Part" button per system → opens `LibraryPartPickerModal` in assignment mode (already-added parts only).
- Drag-and-drop reordering of parts within a system (updates `position_order`).
- "Create System" button — opens the same system create flow that was previously in Interfaces. This is a **UI relocation only** — the backend route `/projects/{id}/systems/` is unchanged.

**Important:** The existing system/unit creation UI in Interfaces tab must still work. The System Architecture tab adds a second entry point to the same backend routes. Do not remove the existing Interfaces tab's system management — defer that cleanup to a follow-up to avoid breaking existing user workflows. Add a banner to the Interfaces tab: "Systems and Units can now also be managed in System Architecture."

---

### 5.7 MECHANICAL INTERFACES tab page (shell)

**`frontend/src/app/projects/[id]/mechanical-interfaces/page.tsx`**

Phase 3 ships a functional shell. The assembly parser and 3D viewer come in Phase 4. Phase 3 delivers:

- Joints list view: table of `MechanicalJoint` records (ID, Type, Part A, Part B, Fastener, Count, Torque, Status, Confidence badge).
- "Add Joint Manually" button → modal form with all `MechanicalJoint` fields. Parts A and B are selected from the project's `ProjectPart` records. Fastener and Seal picked from `LibraryPart` (filtered by type).
- "Upload Assembly File" button → visible but shows "Coming in Phase 4" tooltip. Not wired yet.
- Row click → joint detail side panel with all fields, editable, plus approve/reject buttons.
- Filter: joint type, status, confidence.
- Empty state with clear call to action.

---

### 5.8 Phase 3 verification gate

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
docker exec astra-backend-1 pytest tests/ -q -m "not performance"
```

Manually navigate (or verify via build output) that all new routes resolve:
- `/parts-library`
- `/parts-library/new`
- `/parts-library/pending-imports`
- `/projects/1/parts`
- `/projects/1/system-architecture`
- `/projects/1/mechanical-interfaces`
- `/projects/1/interfaces` (renamed label, still works)

Commit: `feat(parts): Phase 3 complete — Parts Library UI, Engineering nav restructure, PARTS tab, System Architecture tab, Mechanical Interfaces shell`.

---

## 6. Phase 4 — Assembly Parser, 3D Viewer, Auto-Requirements, Full Integration

**Spec sections:** §5.2 (assembly parser), §6 (3D viewer), §7 (auto-requirements), §3.7.3 (review queue for parts)
**Risk:** Medium-High — three.js and pythonOCC integration. pythonOCC stub fallback from Phase 2 means the parser can run even if OCC is not available.
**Autonomy:** Run continuously. Stop only on broken tests or unresolvable dependency issues.

---

### 6.1 Assembly STEP parser service

Create `backend/app/services/parts/assembly_parser.py`.

```python
@dataclass
class AssemblyParseResult:
    parts: list[AssemblyPartResult]         # detected part instances
    joints: list[AssemblyJointResult]       # detected joints
    unmatched_instances: list[str]          # STEP entity names not matched to LibraryPart
    extraction_log: str
    parser_version: str

@dataclass
class AssemblyPartResult:
    step_entity_id: str
    step_product_name: str
    matched_library_part_id: int | None     # None = unmatched
    transform_matrix: list[float]           # 4×4 homogeneous transform for 3D positioning
    confidence: ConfidenceLevel

@dataclass
class AssemblyJointResult:
    part_a_step_entity: str
    part_b_step_entity: str
    joint_type: JointType
    fastener_thread_size: str | None
    fastener_count: int | None
    torque_nominal: Decimal | None
    mating_face_entity_ids: list[str]
    confidence: ConfidenceLevel

def parse_assembly_step(
    file_path: str,
    db: Session,
    project_id: int
) -> AssemblyParseResult:
    """
    Parse an assembly STEP file and match instances to project's LibraryParts.
    Falls back to metadata-only if pythonOCC unavailable.
    """
```

Assembly parser stages per spec §5.2 (all 7 stages). For each stage, emit a progress log line so the job status endpoint can report progress.

Matching logic for stage 2 (match assembly instances to project parts):
1. Try exact match on `PRODUCT` name → `LibraryPart.manufacturer_part_number`
2. Try match on `PRODUCT` name → `LibraryPart.name` (case-insensitive)
3. Try match on WPN extracted from `PRODUCT` description
4. If no match: `matched_library_part_id = None` → appears as a gap in 3D view

---

### 6.2 Assembly parse background job

Add to the mechanical joints router:

`POST /projects/{project_id}/mechanical-joints/upload-assembly`:
1. Validate file is `.step` or `.stp`, ≤ 100MB (assembly files are larger)
2. Save file to documents system
3. Create a `JobStatus` record (use existing job/status pattern from reports if available, otherwise create `assembly_parse_jobs` table with: `id`, `project_id`, `document_id`, `status` enum (queued/running/complete/failed), `result` JSON, `error` text, `created_at`, `completed_at`)
4. Enqueue `BackgroundTasks.add_task(run_assembly_parser, job_id, project_id, document_id, current_user.id)`
5. Return `{"job_id": ..., "status": "queued"}`

`GET /projects/{project_id}/mechanical-joints/assembly-parse-status/{job_id}`:
- Returns job status + progress log + partial results if available

`run_assembly_parser(job_id, project_id, document_id, user_id)` background task:
1. Update job status = running
2. Call `parse_assembly_step(file_path, db, project_id)`
3. For each `AssemblyJointResult`: create a `MechanicalJoint` record with `status=DRAFT`, confidence from result
4. Update job status = complete, store result JSON
5. Emit audit event: `mechanical_joints.assembly_parsed`

---

### 6.3 GLTF export service

Create `backend/app/services/parts/gltf_export.py`:

```python
def step_to_gltf(
    step_file_path: str,
    output_path: str,
    deflection: float = 0.5,
    max_triangles: int = 500_000
) -> bool:
    """
    Convert a STEP file to GLTF using pythonOCC tessellation.
    Returns True on success, False if pythonOCC unavailable.
    Caps at max_triangles — if exceeded, simplifies by increasing deflection.
    GLTF is cached: output_path is keyed on SHA-256 of the STEP file.
    """
    try:
        from OCC.Core.BRep import BRep_Builder
        # tessellate → export GLTF via pythonocc-utils or manual GLTF construction
        ...
        return True
    except ImportError:
        return False
```

GLTF caching: The output path is `{GLTF_CACHE_DIR}/{step_file_checksum}.gltf`. If the file exists, skip re-generation. Cache dir configured via `GLTF_CACHE_DIR` env var (default: `/tmp/astra_gltf_cache`).

Add a backend endpoint:

```
GET /parts-library/{part_id}/gltf     Returns the GLTF file for a part's STEP geometry
GET /projects/{project_id}/mechanical-interfaces/assembly-gltf   Returns combined assembly GLTF
```

The assembly GLTF endpoint applies each part's `transform_matrix` (from the assembly parse result) to position parts correctly in world space. Parts without a STEP file are included as bounding-box placeholder geometry with a distinct material (gray, 50% transparent).

---

### 6.4 3D Viewer frontend component

Create `frontend/src/components/parts/StepViewer.tsx`:

```tsx
interface StepViewerProps {
  gltfUrl: string | null;           // null = no STEP file uploaded
  missingParts?: MissingPartInfo[]; // parts with no STEP file (for assembly view)
  highlightJointId?: string;        // highlights mating faces for selected joint
  mode: 'part' | 'assembly';
}
```

Implementation using three.js (already a project dependency per README ForceGraph work):
- `OrthographicCamera` at true isometric angles (45° azimuth, 35.26° elevation)
- `GLTFLoader` to load the GLTF from the backend endpoint
- `OrbitControls` for orbit/pan/zoom
- Isometric preset button: resets camera to default angle
- If `gltfUrl` is null: show placeholder SVG with "Upload STEP file to enable 3D preview" text
- Missing parts: render bounding boxes in gray, semi-transparent. Each shows a label with the part name.
- Warning banner below viewer: lists missing part names with links to their Parts Library entries to upload STEP files
- `highlightJointId`: applies a colored overlay (`MeshBasicMaterial`, orange, 30% opacity) to mating face meshes for the selected joint
- Export PNG button: `renderer.domElement.toDataURL('image/png')` at 2× size
- Performance: use `<Suspense>` lazy load. Do not load three.js until the component is in the viewport (IntersectionObserver).
- If `gltfUrl` returns 404 (GLTF not yet generated): show a "Generating 3D preview…" spinner and poll every 3 seconds.

---

### 6.5 Wire 3D viewer into UI

**Parts Library part detail** (`parts-library/[id]/page.tsx`):
- Add `StepViewer` to the right panel of the Overview tab. Loads from `/parts-library/{id}/gltf`.
- If the part has no STEP file: show the placeholder with an "Upload STEP File" button that opens `StepUploadModal`.

**Mechanical Interfaces tab** (`projects/[id]/mechanical-interfaces/page.tsx`):
- Add a full-width `StepViewer` in assembly mode at the top of the page. Loads from `/projects/{projectId}/mechanical-interfaces/assembly-gltf`.
- Below the viewer: the joints list table (already in Phase 3 shell).
- Clicking a joint row sets `highlightJointId` on the viewer.
- Missing parts warning banner (from `StepViewer`'s `missingParts` prop) sits between viewer and joints table.

---

### 6.6 Assembly parse status UI

Update `projects/[id]/mechanical-interfaces/page.tsx`:

- "Upload Assembly File" button (was placeholder in Phase 3) → now wired to `mechanicalJointsAPI.uploadAssembly`
- After upload: shows a progress banner with the job status (polling `assembly-parse-status/{jobId}` every 2 seconds)
- On completion: shows "N joints detected. Review them below." — joints list refreshes automatically
- On failure: shows error message with extraction log (collapsible)

---

### 6.7 System Architecture Overview graph — wire mechanical edges

Update `projects/[id]/system-architecture/page.tsx` Overview subtab:

- Fetch mechanical joints via `mechanicalJointsAPI.list(projectId, { status: 'active' })`
- For each active joint, add an amber-colored edge between the two systems that contain `part_a` and `part_b`
- If both parts are in the same system: draw a self-loop on that system node with a wrench label
- Edge thickness scales with `fastener_count` (1–4 bolts = thin, 5–8 = medium, 9+ = thick)

---

### 6.8 Auto-requirement reactive sync — wire MechanicalJoint

In `backend/app/services/req_sync/listener.py`, add the `MechanicalJoint` after_update and after_delete listeners. Follow the exact same pattern as the existing `Interface` and `WireHarness` listeners:

```python
@event.listens_for(MechanicalJoint, "after_update")
def mechanical_joint_after_update(mapper, connection, target):
    if _depth_guard():
        return
    # Fan out to all RequirementSourceLinks where
    # source_entity_type = MECHANICAL_JOINT and source_entity_id = target.id
    # Apply the same decide_action() policy table from fan_out.py
    ...

@event.listens_for(MechanicalJoint, "after_delete")
def mechanical_joint_after_delete(mapper, connection, target):
    # Mark all sourced requirements as needing review
    ...
```

Add `RequirementSourceLink` creation in the joint approve endpoint: when a `MechanicalJoint` is approved, create one `RequirementSourceLink` per applicable template (based on `joint_type`). This is how the reactive sync knows which requirements are affected when the joint later changes.

---

### 6.9 Phase 4 verification gate

```bash
# Backend
docker exec astra-backend-1 pytest tests/ -q -m "not performance"
docker exec astra-backend-1 pytest tests/test_mechanical_joints.py -v  # all tests including auto-req
docker exec astra-backend-1 pytest tests/test_parts_library.py -v

# Frontend
cd frontend && npm run typecheck
cd frontend && npm run build

# Integration smoke (manual steps, verify outputs):
# 1. Upload a STEP file to Parts Library → verify pending import created, WPN assigned on approve
# 2. Add part to project → verify no data duplication (library_part unchanged)
# 3. Assign part to system → verify SystemPartAssignment created
# 4. Create mechanical joint manually → approve → verify auto-requirement generated
# 5. Navigate to /projects/1/mechanical-interfaces → verify 3D viewer renders (or placeholder if no STEP)
# 6. Navigate to /projects/1/system-architecture → verify Overview graph shows electrical + mechanical edges
# 7. Navigate to /projects/1/interfaces → verify label now reads "ELECTRICAL INTERFACES", all existing flows work

# Final health check
docker exec astra-backend-1 alembic current
docker exec astra-backend-1 alembic check
```

Full test suite must pass. `npm run build` must exit 0. Commit: `feat(parts): Phase 4 complete — assembly parser, 3D viewer, auto-requirements, full integration`.

---

## 7. Cross-Cutting Requirements (apply throughout all phases)

These apply to every file touched in this build. No exceptions.

### 7.1 Audit trail
Every create, update, delete, approve, and reject on `LibraryPart`, `PendingPartsImport`, `ProjectPart`, `SystemPartAssignment`, and `MechanicalJoint` emits an audit event via `audit_service`. Events must include:
- `actor_id` (current_user.id)
- `action` (e.g. `"parts_library.part_approved"`)
- `entity_type` and `entity_id`
- `before_state` and `after_state` (for updates — serialize to JSON)
- `timestamp`

This is required for 21 CFR Part 11 compliance (same standard as e-signatures and requirement approvals).

### 7.2 Error handling
Every API endpoint returns structured errors:
```json
{"detail": "Human-readable message", "code": "MACHINE_READABLE_CODE"}
```
Never return Python stack traces. Follow the existing error pattern in the codebase.

### 7.3 No `any` in TypeScript
Use proper types everywhere. If the backend schema is not yet known, use `unknown` and narrow with type guards — not `any`.

### 7.4 Loading and empty states
Every data-fetching component must have:
- A loading skeleton (not a spinner — use the skeleton pattern consistent with the existing UI)
- An empty state with a clear message and call to action
- An error state with a message and a retry button

### 7.5 Accessibility
All new form fields must have `<label>` elements associated via `htmlFor`. All interactive elements must have accessible names. Color-only status indicators must have a secondary indicator (icon or text).

### 7.6 Mobile responsiveness
The Parts Library list and the Engineering tabs must be usable on a 768px viewport. The 3D viewer can require desktop (show a "3D view requires a larger screen" message on mobile).

---

## 8. Deferred Items (do not build, track in log)

The following are out of scope for this build. If you encounter them, note them in `PARTS_BUILD_LOG.md` under "Deferred" and continue:

- **SolidWorks add-in** — separate spec, separate build. The `/mechanical-joints/upload-assembly` endpoint is designed to accept data from the add-in (same format as the STEP parser output) but the add-in itself is out of scope.
- **Mass budget rollup** — System-level mass budget tracking and rollup auto-requirements (spec OQ-2). Defer to next phase.
- **ITAR access controls** — LibraryPart `itar_controlled` flag and role-gating (spec OQ-1). Defer.
- **Installation records** — MechanicalJoint torque verification records (spec OQ-3). Defer.
- **LOD switching** for large assemblies (spec OQ-7). The 500k triangle cap and bounding-box fallback from spec §6.3 are sufficient for Phase 4.
- **Vendor revision diff/upgrade UI** — already deferred in the existing README.
- **Frontend test infrastructure** — already deferred per existing README. Verify with `tsc --noEmit` + `npm run build`.

---

## 9. New Issues Discovered During Build

If you discover something broken or wrong that is not in `BACKLOG.md` or `AUDIT_FINDINGS_POST_REMEDIATION.md`, do the following:

1. **Do NOT silently fix it** unless it is directly blocking your current phase and the fix is trivial (< 5 lines).
2. Add an entry to `PARTS_BUILD_LOG.md` under "New Issues Discovered" with: date, description, severity (Critical/High/Medium/Low), file and line, and recommended fix.
3. If it is Critical or High and it will actively break this build: stop and surface it. Otherwise continue.

This preserves the audit trail Mason depends on.

---

## 10. Final Delivery Checklist

Before opening the PR for this branch, verify every item:

```
[ ] All 4 phases committed with phase-N-complete tags
[ ] docker exec astra-backend-1 pytest tests/ -q -m "not performance" → 0 failures
[ ] cd frontend && npm run typecheck → exit 0
[ ] cd frontend && npm run build → exit 0
[ ] docker exec astra-backend-1 alembic check → "No new upgrade operations detected"
[ ] All new endpoints appear in /docs (Swagger) with correct schemas
[ ] PARTS_BUILD_LOG.md is complete — all phases documented
[ ] No .bak files created
[ ] No secrets or credentials in any new file
[ ] No hardcoded API URLs — all go through env config
[ ] No any types in TypeScript (eslint --max-warnings 0 on new files)
[ ] All new project-scoped endpoints tested with a non-member user → 403
[ ] Audit events emitted for all create/approve/reject/delete operations
[ ] WPN assignment tested for uniqueness under concurrent load
[ ] STEP file duplicate detection tested (same file twice → returns existing, no double-parse)
[ ] 3D viewer renders or shows appropriate placeholder/error state
[ ] /projects/1/interfaces still works with renamed label
[ ] git log --oneline shows clean, bisectable per-feature commits
```

When all items are checked and the test suite is green, print to stdout:

```
PARTS & MECHANICAL MODULE BUILD COMPLETE
Phases completed: 4/4
New tests: <count>
New migrations: <count>
Final alembic revision: <sha>
See PARTS_BUILD_LOG.md for full details.
```

Then stop. Do not summarize in chat. The log is the deliverable.

---

## 11. Safety Rails

Read these before any destructive operation. Non-negotiable.

- **Before any migration that ALTERs an existing table** (units in Phase 1): snapshot the DB per the pre-flight procedure.
- **Never `docker compose down -v`** — wipes the dev DB.
- **Never `alembic downgrade base`** — the production downgrade guard from original remediation Phase 2 will refuse this, but don't try.
- **WPN assignment MUST use `with_for_update()`** — two simultaneous part approvals from the review queue must not produce the same WPN. This was explicitly designed to prevent the F-203 race condition pattern.
- **`LibraryPart` records are IMMUTABLE once approved.** If you need to change a dimensional field, the service must bump the revision (increment RR suffix), not update the existing row in place. Implement this as: create a new row with the same base NNNNNN but incremented RR, set the old row's `superseded_by_id` to the new row.
- **Do not modify any existing migration file** in `alembic/versions/`. Only add new migration files.
- **The `/interfaces` backend route prefix stays as-is.** The frontend label rename is purely cosmetic.

---

## 12. `PARTS_BUILD_LOG.md` Template

Write to `C:\Users\Mason\Documents\ASTRA\PARTS_BUILD_LOG.md`. Update after every phase.

```markdown
# ASTRA Parts Library & Mechanical Module Build Log
**Started:** <YYYY-MM-DD>
**Spec:** ASTRA-SPEC-PARTS-001 v0.1
**Branch:** feat/parts-mechanical-module
**Pre-flight alembic revision:** <HEAD_BEFORE>
**Pre-flight test count:** <N>

## Phase Status

| Phase | Status | Commits | Alembic revision | Tests | Build |
|---|---|---|---|---|---|
| Phase 1 — Data model & migrations | ✅ / 🚧 / ⏸ | `<sha>` | `<rev>` | +N | — |
| Phase 2 — Parts Library backend | ✅ / 🚧 / ⏸ | `<sha>` | `<rev>` | +N | — |
| Phase 3 — Frontend + nav restructure | ✅ / 🚧 / ⏸ | `<sha>` | — | — | ✅/❌ |
| Phase 4 — Assembly parser + 3D + auto-reqs | ✅ / 🚧 / ⏸ | `<sha>` | — | +N | ✅/❌ |

## Phase Notes

### Phase 1
- Files touched: ...
- Anomalies: ...
- Verification output: ...

### Phase 2
- pythonOCC available: yes/no (stub used: yes/no)
- Files touched: ...
- Anomalies: ...

### Phase 3
- Frontend routes verified: ...
- typecheck: pass/fail
- build: pass/fail

### Phase 4
- 3D viewer: working/stub (pythonOCC available: yes/no)
- Assembly parser: working/stub
- Auto-requirements wired: yes/no

## New Issues Discovered

| Date | Description | Severity | File:Line | Action taken |
|---|---|---|---|---|
| ... | ... | ... | ... | ... |

## Deferred Items

| Item | Reason | Spec reference |
|---|---|---|
| SolidWorks add-in | Separate spec | OQ-4 |
| Mass budget rollup | OQ-2 | §7 |
| ITAR access controls | OQ-1 | §3.5.1 |
| Installation records | OQ-3 | §5.1.1 |
| LOD switching | OQ-7 | §6.3 |
```
