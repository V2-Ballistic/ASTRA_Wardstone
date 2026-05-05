# ASTRA — Parts Library & Mechanical Interfaces Module
# Claude Code Execution Prompt — ASTRA-SPEC-PARTS-001 v0.1
# Maximum Detail Edition

**Source spec:** `ASTRA_PARTS_MECHANICAL_SPEC.docx`
**Codebase root:** `C:\Users\Mason\Documents\ASTRA`
**Branch:** `feat/parts-mechanical-module` off current `main`
**Active project for smoke tests:** SMDS (project_id=1), user: mason (user_id=1, admin)
**Deliverable:** All 4 phases executed. `PARTS_BUILD_LOG.md` updated after every phase. Template §13.

---

## 1. Operating Rules

1. **Fully autonomous.** No check-ins between steps. No confirmations on routine decisions. The ONLY reasons to stop and surface an issue:
   - A test that was passing is now broken and you cannot fix it within 3 attempts.
   - A migration would destroy data that cannot be reconstructed from the snapshot.
   - A spec ambiguity whose resolution affects ALL downstream phases (local ambiguities: use judgment and proceed).
   - A pip/npm dependency is unavailable in the container and no alternative exists.
   - A new finding that would be Critical or High in the existing audit framework.

2. **Every Python file syntax-validated before committing:**
   ```bash
   python3 -c "import ast; ast.parse(open('path').read())"
   ```

3. **`npm run typecheck` after every frontend file change.** Fix type errors immediately.

4. **Never `alembic revision --autogenerate`.** Hand-write every migration. The codebase has autogenerate-drift hazards.

5. **Every `SQLEnum(...)` includes `values_callable=lambda x: [e.value for e in x]`.** PostgreSQL requires lowercase enum values. This is a hard rule from original audit F-016.

6. **All decimal/float measurement fields use `Column(Numeric(precision, scale))` — never `Float`.** Engineering-unit math requires exact decimal arithmetic. This rule came from F-031 (`MessageField` scale/offset precision fix).

7. **Every new project-scoped endpoint gets `Depends(project_member_required)`.** F-014/F-201 regression prevention. No exceptions.

8. **Backend pagination cap is 200.** Every list endpoint: `limit: int = Query(default=50, le=200)`.

9. **One commit per logical unit.** Models → migration → schemas → service → router → tests. Phase boundaries always tagged `phase-N-complete`.

10. **`PARTS_BUILD_LOG.md` updated after every phase.** Template in §13.

11. **Never `docker compose down -v`.** Wipes dev DB.

12. **Before any migration touching existing tables:** DB snapshot first.
    ```bash
    docker exec astra-db-1 pg_dump -U astra -d astra -F c -f /tmp/pre_phaseN_$(date +%s).dump
    docker cp "astra-db-1:/tmp/pre_phaseN_*.dump" ..\ASTRA-backups\
    ```

13. **`LibraryPart` records are immutable once `status=approved`.** Updates to dimensional fields after approval must bump the `revision` suffix (RR increment) and set `superseded_by_id` on the old row — never overwrite in place.

14. **WPN assignment must use `SELECT FOR UPDATE`.** Two simultaneous approvals must not produce the same WPN. This is the F-203 lesson applied to this module.

15. **The `/interfaces` backend route prefix is NOT renamed.** The "ELECTRICAL INTERFACES" tab rename is a frontend label change only. Zero API contract changes.

---

## 2. Pre-Flight

```bash
git status                                          # must be clean
git log --oneline -5                                # confirm backlog remediation is latest
docker compose ps                                   # all 3 containers running
docker exec astra-backend-1 alembic current         # record as HEAD_BEFORE
docker exec astra-backend-1 alembic check           # no pending autogenerate
docker exec astra-backend-1 pytest tests/ -q -m "not performance"   # record count as TESTS_BEFORE
cd frontend && npm run typecheck && npm run build   # must be clean

# DB snapshot
docker exec astra-db-1 pg_dump -U astra -d astra -F c -f /tmp/pre_parts_$(date +%s).dump
docker cp "astra-db-1:/tmp/pre_parts_*.dump" ..\ASTRA-backups\

# Branch
git checkout main && git pull origin main
git checkout -b feat/parts-mechanical-module
git push -u origin feat/parts-mechanical-module
```

Initialize `PARTS_BUILD_LOG.md` (template §13). Commit. Then proceed to Phase 1 immediately — no pause.

---

## 3. Phase 1 — Data Model, Enums, Migration, Schemas

**Risk:** High — 6 new tables, modifies 1 existing table.
**Rollback floor:** Pre-flight snapshot.

---

### 3.1 File: `backend/app/models/parts_library.py` — Enums

Create this file. All enums defined BEFORE any SQLAlchemy models (PostgreSQL requires enum types to exist before columns reference them).

```python
import enum

class PartType(str, enum.Enum):
    FASTENER          = "fastener"
    WASHER            = "washer"
    INSERT            = "insert"
    BRACKET           = "bracket"
    ENCLOSURE         = "enclosure"
    SEAL              = "seal"
    BEARING           = "bearing"
    HINGE_LATCH       = "hinge_latch"
    THERMAL_INTERFACE = "thermal_interface"
    PCB_MECHANICAL    = "pcb_mechanical"
    CUSTOM            = "custom"

class PartStatus(str, enum.Enum):
    DRAFT         = "draft"
    UNDER_REVIEW  = "under_review"
    APPROVED      = "approved"
    SUPERSEDED    = "superseded"
    OBSOLETE      = "obsolete"

class MaterialClass(str, enum.Enum):
    ALUMINUM       = "aluminum"
    TITANIUM       = "titanium"
    STEEL          = "steel"
    STAINLESS_STEEL= "stainless_steel"
    NICKEL_ALLOY   = "nickel_alloy"
    POLYMER        = "polymer"
    COMPOSITE      = "composite"
    CERAMIC        = "ceramic"
    OTHER          = "other"

class ThreadStandard(str, enum.Enum):
    ISO_METRIC = "iso_metric"
    UNC        = "unc"
    UNF        = "unf"
    NPT        = "npt"
    BSPP       = "bspp"
    AN_NAS_MS  = "an_nas_ms"
    CUSTOM     = "custom"

class HeadType(str, enum.Enum):
    SOCKET    = "socket"
    HEX       = "hex"
    PAN       = "pan"
    FLAT      = "flat"
    BUTTON    = "button"
    TORX      = "torx"
    FILLISTER = "fillister"
    TRUSS     = "truss"

class DriveType(str, enum.Enum):
    HEX_KEY  = "hex_key"
    TORX     = "torx"
    PHILLIPS = "phillips"
    SLOTTED  = "slotted"
    SPANNER  = "spanner"
    CUSTOM   = "custom"

class LockingFeature(str, enum.Enum):
    NONE              = "none"
    NYLOK             = "nylok"
    PREVAILING_TORQUE = "prevailing_torque"
    SAFETY_WIRE       = "safety_wire"
    LOCTITE           = "loctite"
    CASTELLATED       = "castellated"
    LOCKWIRE_HOLE     = "lockwire_hole"

class QualificationStatus(str, enum.Enum):
    UNQUALIFIED    = "unqualified"
    QUAL_TESTING   = "qual_testing"
    QUALIFIED      = "qualified"
    FLIGHT_PROVEN  = "flight_proven"
    DEMANUFACTURED = "demanufactured"

class PendingPartsStatus(str, enum.Enum):
    PENDING      = "pending"
    UNDER_REVIEW = "under_review"
    APPROVED     = "approved"
    REJECTED     = "rejected"

class ConfidenceLevel(str, enum.Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"

class JointType(str, enum.Enum):
    BOLTED       = "bolted"
    RIVETED      = "riveted"
    PRESS_FIT    = "press_fit"
    ADHESIVE     = "adhesive"
    WELD         = "weld"
    SEAL         = "seal"
    ALIGNMENT_PIN= "alignment_pin"
    THERMAL_BOND = "thermal_bond"
    SPRING_CLIP  = "spring_clip"

class JointStatus(str, enum.Enum):
    DRAFT     = "draft"
    ACTIVE    = "active"
    SUPERSEDED= "superseded"
```

---

### 3.2 File: `backend/app/models/parts_library.py` — Models

Append to the same file after the enums. Use the exact column definitions below. Do not deviate from `Numeric(precision, scale)` on any measurement field.

```python
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    Numeric, ForeignKey, UniqueConstraint, Index, BigInteger,
    ARRAY
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base

# ─── WPN Sequence ────────────────────────────────────────────────────────────

class WPNSequence(Base):
    __tablename__ = "wpn_sequences"
    part_type_code = Column(String(8), primary_key=True)   # "FAST", "WASH" etc.
    next_val       = Column(Integer, nullable=False, default=1)

# ─── Library Part ─────────────────────────────────────────────────────────────

class LibraryPart(Base):
    __tablename__ = "library_parts"
    __table_args__ = (
        UniqueConstraint("wardstone_part_number", name="uq_library_part_wpn"),
        Index("ix_library_part_type_status", "part_type", "status"),
        Index("ix_library_part_step_checksum", "step_file_checksum"),
        Index("ix_library_part_mpn", "manufacturer_part_number"),
    )

    id                      = Column(Integer, primary_key=True, index=True)

    # ── Identification ──────────────────────────────────────────────────────
    wardstone_part_number   = Column(String(32),  nullable=False, unique=True)
    revision                = Column(String(2),   nullable=False, default="00")
    part_type               = Column(SQLEnum(PartType,
                                  values_callable=lambda x: [e.value for e in x]),
                                  nullable=False, index=True)
    name                    = Column(String(500),  nullable=False)
    description             = Column(Text,         nullable=True)
    manufacturer_part_number= Column(String(200),  nullable=True, index=True)
    manufacturer_name       = Column(String(200),  nullable=True)
    cage_code               = Column(String(10),   nullable=True)
    nsn                     = Column(String(20),   nullable=True)
    drawing_number          = Column(String(200),  nullable=True)
    drawing_revision        = Column(String(20),   nullable=True)
    heritage                = Column(Text,         nullable=True)
    status                  = Column(SQLEnum(PartStatus,
                                  values_callable=lambda x: [e.value for e in x]),
                                  nullable=False, default=PartStatus.DRAFT, index=True)
    superseded_by_id        = Column(Integer,
                                  ForeignKey("library_parts.id", ondelete="SET NULL"),
                                  nullable=True)

    # ── Dimensional — AUTO from STEP ────────────────────────────────────────
    bounding_box_x_mm       = Column(Numeric(12, 4), nullable=True)
    bounding_box_y_mm       = Column(Numeric(12, 4), nullable=True)
    bounding_box_z_mm       = Column(Numeric(12, 4), nullable=True)
    volume_mm3              = Column(Numeric(18, 4), nullable=True)
    surface_area_mm2        = Column(Numeric(18, 4), nullable=True)
    thread_size             = Column(String(50),  nullable=True)
    thread_standard         = Column(SQLEnum(ThreadStandard,
                                  values_callable=lambda x: [e.value for e in x]),
                                  nullable=True)
    nominal_diameter_mm     = Column(Numeric(12, 4), nullable=True)
    nominal_length_mm       = Column(Numeric(12, 4), nullable=True)
    head_type               = Column(SQLEnum(HeadType,
                                  values_callable=lambda x: [e.value for e in x]),
                                  nullable=True)
    drive_type              = Column(SQLEnum(DriveType,
                                  values_callable=lambda x: [e.value for e in x]),
                                  nullable=True)
    nominal_bore_mm         = Column(Numeric(12, 4), nullable=True)
    cross_section_dia_mm    = Column(Numeric(12, 4), nullable=True)
    flange_diameter_mm      = Column(Numeric(12, 4), nullable=True)
    hole_pattern_count      = Column(Integer,       nullable=True)
    hole_pattern_dia_mm     = Column(Numeric(12, 4), nullable=True)
    hole_pattern_pcd_mm     = Column(Numeric(12, 4), nullable=True)

    # ── Material ────────────────────────────────────────────────────────────
    material_name           = Column(String(200),  nullable=True)
    material_standard       = Column(String(200),  nullable=True)
    material_class          = Column(SQLEnum(MaterialClass,
                                  values_callable=lambda x: [e.value for e in x]),
                                  nullable=True)
    density_g_cm3           = Column(Numeric(10, 4), nullable=True)
    yield_strength_mpa      = Column(Numeric(10, 2), nullable=True)
    ultimate_strength_mpa   = Column(Numeric(10, 2), nullable=True)
    elastic_modulus_gpa     = Column(Numeric(10, 2), nullable=True)
    hardness                = Column(String(50),  nullable=True)
    thermal_conductivity_wm = Column(Numeric(10, 4), nullable=True)
    cte_um_m_c              = Column(Numeric(10, 4), nullable=True)
    corrosion_protection    = Column(String(200),  nullable=True)
    flammability_class      = Column(String(100),  nullable=True)
    outgassing_tml_pct      = Column(Numeric(8, 4),  nullable=True)
    outgassing_cvcm_pct     = Column(Numeric(8, 4),  nullable=True)

    # ── Mechanical Performance ───────────────────────────────────────────────
    mass_nominal_g          = Column(Numeric(12, 4), nullable=True)
    mass_max_g              = Column(Numeric(12, 4), nullable=True)
    proof_load_n            = Column(Numeric(12, 2), nullable=True)
    clamp_load_n            = Column(Numeric(12, 2), nullable=True)
    torque_nominal_nm       = Column(Numeric(10, 4), nullable=True)
    torque_min_nm           = Column(Numeric(10, 4), nullable=True)
    torque_max_nm           = Column(Numeric(10, 4), nullable=True)
    torque_lubricated_nm    = Column(Numeric(10, 4), nullable=True)
    locking_feature         = Column(SQLEnum(LockingFeature,
                                  values_callable=lambda x: [e.value for e in x]),
                                  nullable=True, default=LockingFeature.NONE)
    safety_wire_holes       = Column(Boolean,       nullable=True)
    shear_strength_n        = Column(Numeric(12, 2), nullable=True)
    bearing_load_n          = Column(Numeric(12, 2), nullable=True)
    compression_set_pct     = Column(Numeric(8, 2),  nullable=True)
    sealing_pressure_max_bar= Column(Numeric(10, 3), nullable=True)
    temperature_min_c       = Column(Numeric(8, 2),  nullable=True)
    temperature_max_c       = Column(Numeric(8, 2),  nullable=True)

    # ── Procurement & Lifecycle ──────────────────────────────────────────────
    unit_cost_usd           = Column(Numeric(12, 4), nullable=True)
    lead_time_weeks         = Column(Integer,       nullable=True)
    min_order_qty           = Column(Integer,       nullable=True)
    preferred_supplier_id   = Column(Integer,
                                  ForeignKey("suppliers.id", ondelete="SET NULL"),
                                  nullable=True, index=True)
    supplier_part_number    = Column(String(200),  nullable=True)
    qualification_status    = Column(SQLEnum(QualificationStatus,
                                  values_callable=lambda x: [e.value for e in x]),
                                  nullable=True, default=QualificationStatus.UNQUALIFIED)
    qualification_basis     = Column(Text,         nullable=True)
    shelf_life_months       = Column(Integer,       nullable=True)
    date_of_manufacture     = Column(Date,          nullable=True)
    restricted_use          = Column(Boolean,       nullable=False, default=False)
    restriction_notes       = Column(Text,         nullable=True)

    # ── STEP File Traceability ───────────────────────────────────────────────
    step_file_id            = Column(Integer,
                                  ForeignKey("documents.id", ondelete="SET NULL"),
                                  nullable=True)
    step_file_checksum      = Column(String(64),  nullable=True)
    step_entity_id          = Column(String(200), nullable=True)

    # ── Audit ────────────────────────────────────────────────────────────────
    approved_by_id          = Column(Integer,
                                  ForeignKey("users.id", ondelete="SET NULL"),
                                  nullable=True)
    approved_at             = Column(DateTime(timezone=True), nullable=True)
    created_at              = Column(DateTime(timezone=True),
                                  server_default=func.now(), nullable=False)
    updated_at              = Column(DateTime(timezone=True),
                                  server_default=func.now(), onupdate=func.now(),
                                  nullable=False)
    created_by_id           = Column(Integer,
                                  ForeignKey("users.id", ondelete="SET NULL"),
                                  nullable=True)

    # ── Relationships ────────────────────────────────────────────────────────
    superseded_by           = relationship("LibraryPart", remote_side=[id],
                                  foreign_keys=[superseded_by_id])
    preferred_supplier      = relationship("Supplier", foreign_keys=[preferred_supplier_id])
    approved_by             = relationship("User", foreign_keys=[approved_by_id])
    created_by              = relationship("User", foreign_keys=[created_by_id])
    project_parts           = relationship("ProjectPart", back_populates="library_part")
    fastener_joints         = relationship("MechanicalJoint",
                                  foreign_keys="MechanicalJoint.fastener_part_id",
                                  back_populates="fastener_part")
    seal_joints             = relationship("MechanicalJoint",
                                  foreign_keys="MechanicalJoint.seal_part_id",
                                  back_populates="seal_part")


# ─── Pending Parts Import ──────────────────────────────────────────────────────

class PendingPartsImport(Base):
    __tablename__ = "pending_parts_imports"

    id                   = Column(Integer, primary_key=True, index=True)
    document_id          = Column(Integer,
                              ForeignKey("documents.id", ondelete="CASCADE"),
                              nullable=False, index=True)
    status               = Column(SQLEnum(PendingPartsStatus,
                              values_callable=lambda x: [e.value for e in x]),
                              nullable=False, default=PendingPartsStatus.PENDING,
                              index=True)
    proposed_data        = Column(JSONB().with_variant(JSON(), "sqlite"), nullable=False)
    confidence_scores    = Column(JSONB().with_variant(JSON(), "sqlite"), nullable=False,
                              default=dict)
    low_confidence_fields= Column(ARRAY(String), nullable=False, default=list)
    extraction_log       = Column(Text, nullable=True)
    parser_version       = Column(String(32), nullable=True)
    reviewed_by_id       = Column(Integer,
                              ForeignKey("users.id", ondelete="SET NULL"),
                              nullable=True)
    reviewed_at          = Column(DateTime(timezone=True), nullable=True)
    rejection_reason     = Column(Text, nullable=True)
    library_part_id      = Column(Integer,
                              ForeignKey("library_parts.id", ondelete="SET NULL"),
                              nullable=True)  # set on approval
    created_at           = Column(DateTime(timezone=True),
                              server_default=func.now(), nullable=False)
    updated_at           = Column(DateTime(timezone=True),
                              server_default=func.now(), onupdate=func.now(),
                              nullable=False)
    created_by_id        = Column(Integer,
                              ForeignKey("users.id", ondelete="SET NULL"),
                              nullable=True)

    document             = relationship("Document")
    reviewed_by          = relationship("User", foreign_keys=[reviewed_by_id])
    library_part         = relationship("LibraryPart")


# ─── Project Part (join: project ↔ library_part) ──────────────────────────────

class ProjectPart(Base):
    __tablename__ = "project_parts"
    __table_args__ = (
        UniqueConstraint("project_id", "library_part_id",
                         name="uq_project_part"),
    )

    id               = Column(Integer, primary_key=True, index=True)
    project_id       = Column(Integer,
                          ForeignKey("projects.id", ondelete="CASCADE"),
                          nullable=False, index=True)
    library_part_id  = Column(Integer,
                          ForeignKey("library_parts.id", ondelete="RESTRICT"),
                          nullable=False, index=True)
    quantity         = Column(Integer, nullable=False, default=1)
    designation      = Column(String(64), nullable=True)
    notes            = Column(Text, nullable=True)
    added_by_id      = Column(Integer,
                          ForeignKey("users.id", ondelete="SET NULL"),
                          nullable=True)
    added_at         = Column(DateTime(timezone=True),
                          server_default=func.now(), nullable=False)

    project          = relationship("Project")
    library_part     = relationship("LibraryPart", back_populates="project_parts")
    added_by         = relationship("User")
    system_assignments = relationship("SystemPartAssignment",
                           back_populates="project_part",
                           cascade="all, delete-orphan")


# ─── System Part Assignment (join: system ↔ project_part) ────────────────────

class SystemPartAssignment(Base):
    __tablename__ = "system_part_assignments"
    __table_args__ = (
        UniqueConstraint("system_id", "project_part_id",
                         name="uq_system_part_assignment"),
    )

    id              = Column(Integer, primary_key=True, index=True)
    system_id       = Column(Integer,
                         ForeignKey("systems.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    project_part_id = Column(Integer,
                         ForeignKey("project_parts.id", ondelete="CASCADE"),
                         nullable=False, index=True)
    position_order  = Column(Integer, nullable=False, default=0)
    assigned_by_id  = Column(Integer,
                         ForeignKey("users.id", ondelete="SET NULL"),
                         nullable=True)
    assigned_at     = Column(DateTime(timezone=True),
                         server_default=func.now(), nullable=False)

    system          = relationship("System")
    project_part    = relationship("ProjectPart", back_populates="system_assignments")
    assigned_by     = relationship("User")


# ─── Mechanical Joint Sequence ────────────────────────────────────────────────

class MechanicalJointSequence(Base):
    __tablename__ = "mechanical_joint_sequences"
    project_id = Column(Integer, primary_key=True)
    next_val   = Column(Integer, nullable=False, default=1)


# ─── Assembly Parse Job ───────────────────────────────────────────────────────

class AssemblyParseJobStatus(str, enum.Enum):
    QUEUED   = "queued"
    RUNNING  = "running"
    COMPLETE = "complete"
    FAILED   = "failed"

class AssemblyParseJob(Base):
    __tablename__ = "assembly_parse_jobs"

    id          = Column(Integer, primary_key=True, index=True)
    project_id  = Column(Integer,
                     ForeignKey("projects.id", ondelete="CASCADE"),
                     nullable=False, index=True)
    document_id = Column(Integer,
                     ForeignKey("documents.id", ondelete="SET NULL"),
                     nullable=True)
    status      = Column(SQLEnum(AssemblyParseJobStatus,
                     values_callable=lambda x: [e.value for e in x]),
                     nullable=False, default=AssemblyParseJobStatus.QUEUED,
                     index=True)
    progress_log= Column(Text, nullable=True)
    result      = Column(JSONB().with_variant(JSON(), "sqlite"), nullable=True)
    error       = Column(Text, nullable=True)
    created_by_id= Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())
    completed_at= Column(DateTime(timezone=True), nullable=True)

    project     = relationship("Project")
    document    = relationship("Document")


# ─── Mechanical Joint ─────────────────────────────────────────────────────────

class MechanicalJoint(Base):
    __tablename__ = "mechanical_joints"
    __table_args__ = (
        Index("ix_mj_project_status", "project_id", "status"),
        Index("ix_mj_parts", "part_a_id", "part_b_id"),
    )

    id                       = Column(Integer, primary_key=True, index=True)
    joint_id                 = Column(String(32), unique=True, nullable=False, index=True)
    project_id               = Column(Integer,
                                   ForeignKey("projects.id", ondelete="CASCADE"),
                                   nullable=False, index=True)
    joint_type               = Column(SQLEnum(JointType,
                                   values_callable=lambda x: [e.value for e in x]),
                                   nullable=False)
    part_a_id                = Column(Integer,
                                   ForeignKey("project_parts.id", ondelete="RESTRICT"),
                                   nullable=False, index=True)
    part_b_id                = Column(Integer,
                                   ForeignKey("project_parts.id", ondelete="RESTRICT"),
                                   nullable=False, index=True)
    fastener_part_id         = Column(Integer,
                                   ForeignKey("library_parts.id", ondelete="SET NULL"),
                                   nullable=True)
    fastener_count           = Column(Integer, nullable=True)
    torque_nominal_nm        = Column(Numeric(10, 4), nullable=True)
    torque_min_nm            = Column(Numeric(10, 4), nullable=True)
    torque_max_nm            = Column(Numeric(10, 4), nullable=True)
    engagement_length_mm     = Column(Numeric(10, 4), nullable=True)
    locking_feature          = Column(SQLEnum(LockingFeature,
                                   values_callable=lambda x: [e.value for e in x]),
                                   nullable=True)
    hole_pattern_description = Column(String(300), nullable=True)
    mating_surface_flatness_mm= Column(Numeric(10, 4), nullable=True)
    mating_surface_finish_ra = Column(Numeric(10, 4), nullable=True)
    seal_part_id             = Column(Integer,
                                   ForeignKey("library_parts.id", ondelete="SET NULL"),
                                   nullable=True)
    leak_rate_max_scc_s      = Column(Numeric(12, 6), nullable=True)
    test_pressure_bar        = Column(Numeric(10, 3), nullable=True)
    interface_drawing        = Column(String(200), nullable=True)
    source_step_file_id      = Column(Integer,
                                   ForeignKey("documents.id", ondelete="SET NULL"),
                                   nullable=True)
    source_step_entity       = Column(Text, nullable=True)
    confidence               = Column(SQLEnum(ConfidenceLevel,
                                   values_callable=lambda x: [e.value for e in x]),
                                   nullable=True)
    status                   = Column(SQLEnum(JointStatus,
                                   values_callable=lambda x: [e.value for e in x]),
                                   nullable=False, default=JointStatus.DRAFT, index=True)
    notes                    = Column(Text, nullable=True)
    created_at               = Column(DateTime(timezone=True),
                                   server_default=func.now(), nullable=False)
    updated_at               = Column(DateTime(timezone=True),
                                   server_default=func.now(), onupdate=func.now(),
                                   nullable=False)
    created_by_id            = Column(Integer,
                                   ForeignKey("users.id", ondelete="SET NULL"),
                                   nullable=True)

    project     = relationship("Project")
    part_a      = relationship("ProjectPart", foreign_keys=[part_a_id])
    part_b      = relationship("ProjectPart", foreign_keys=[part_b_id])
    fastener_part = relationship("LibraryPart", foreign_keys=[fastener_part_id],
                                  back_populates="fastener_joints")
    seal_part   = relationship("LibraryPart", foreign_keys=[seal_part_id],
                                  back_populates="seal_joints")
    source_file = relationship("Document", foreign_keys=[source_step_file_id])
    created_by  = relationship("User")
```

---

### 3.3 Update `backend/app/models/__init__.py`

Add these imports so `from app.models import LibraryPart` works everywhere:

```python
from app.models.parts_library import (
    PartType, PartStatus, MaterialClass, ThreadStandard, HeadType,
    DriveType, LockingFeature, QualificationStatus, PendingPartsStatus,
    ConfidenceLevel, JointType, JointStatus, AssemblyParseJobStatus,
    WPNSequence, LibraryPart, PendingPartsImport,
    ProjectPart, SystemPartAssignment,
    MechanicalJointSequence, AssemblyParseJob, MechanicalJoint,
)
```

---

### 3.4 Update `backend/app/models/req_sync.py` — Add MECHANICAL_JOINT enum value

Find the `SourceEntityType` enum and add:
```python
MECHANICAL_JOINT = "mechanical_joint"
```
This allows `RequirementSourceLink` records to reference `MechanicalJoint` as a source.

---

### 3.5 Pydantic schemas: `backend/app/schemas/parts_library.py`

```python
from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Any
from decimal import Decimal
from datetime import datetime, date
from app.models.parts_library import (
    PartType, PartStatus, MaterialClass, ThreadStandard, HeadType,
    DriveType, LockingFeature, QualificationStatus, PendingPartsStatus,
    ConfidenceLevel, JointType, JointStatus
)

# ── LibraryPart ───────────────────────────────────────────────────────────────

class LibraryPartCreate(BaseModel):
    part_type:                PartType
    name:                     str
    description:              Optional[str] = None
    manufacturer_part_number: Optional[str] = None
    manufacturer_name:        Optional[str] = None
    cage_code:                Optional[str] = None
    nsn:                      Optional[str] = None
    drawing_number:           Optional[str] = None
    drawing_revision:         Optional[str] = None
    heritage:                 Optional[str] = None
    # Dimensional
    bounding_box_x_mm:        Optional[Decimal] = None
    bounding_box_y_mm:        Optional[Decimal] = None
    bounding_box_z_mm:        Optional[Decimal] = None
    volume_mm3:               Optional[Decimal] = None
    surface_area_mm2:         Optional[Decimal] = None
    thread_size:              Optional[str] = None
    thread_standard:          Optional[ThreadStandard] = None
    nominal_diameter_mm:      Optional[Decimal] = None
    nominal_length_mm:        Optional[Decimal] = None
    head_type:                Optional[HeadType] = None
    drive_type:               Optional[DriveType] = None
    nominal_bore_mm:          Optional[Decimal] = None
    cross_section_dia_mm:     Optional[Decimal] = None
    flange_diameter_mm:       Optional[Decimal] = None
    hole_pattern_count:       Optional[int] = None
    hole_pattern_dia_mm:      Optional[Decimal] = None
    hole_pattern_pcd_mm:      Optional[Decimal] = None
    # Material
    material_name:            Optional[str] = None
    material_standard:        Optional[str] = None
    material_class:           Optional[MaterialClass] = None
    density_g_cm3:            Optional[Decimal] = None
    yield_strength_mpa:       Optional[Decimal] = None
    ultimate_strength_mpa:    Optional[Decimal] = None
    elastic_modulus_gpa:      Optional[Decimal] = None
    hardness:                 Optional[str] = None
    thermal_conductivity_wm:  Optional[Decimal] = None
    cte_um_m_c:               Optional[Decimal] = None
    corrosion_protection:     Optional[str] = None
    flammability_class:       Optional[str] = None
    outgassing_tml_pct:       Optional[Decimal] = None
    outgassing_cvcm_pct:      Optional[Decimal] = None
    # Performance
    mass_nominal_g:           Optional[Decimal] = None
    mass_max_g:               Optional[Decimal] = None
    proof_load_n:             Optional[Decimal] = None
    clamp_load_n:             Optional[Decimal] = None
    torque_nominal_nm:        Optional[Decimal] = None
    torque_min_nm:            Optional[Decimal] = None
    torque_max_nm:            Optional[Decimal] = None
    torque_lubricated_nm:     Optional[Decimal] = None
    locking_feature:          Optional[LockingFeature] = LockingFeature.NONE
    safety_wire_holes:        Optional[bool] = None
    shear_strength_n:         Optional[Decimal] = None
    bearing_load_n:           Optional[Decimal] = None
    compression_set_pct:      Optional[Decimal] = None
    sealing_pressure_max_bar: Optional[Decimal] = None
    temperature_min_c:        Optional[Decimal] = None
    temperature_max_c:        Optional[Decimal] = None
    # Procurement
    unit_cost_usd:            Optional[Decimal] = None
    lead_time_weeks:          Optional[int] = None
    min_order_qty:            Optional[int] = None
    preferred_supplier_id:    Optional[int] = None
    supplier_part_number:     Optional[str] = None
    qualification_status:     Optional[QualificationStatus] = QualificationStatus.UNQUALIFIED
    qualification_basis:      Optional[str] = None
    shelf_life_months:        Optional[int] = None
    date_of_manufacture:      Optional[date] = None
    restricted_use:           bool = False
    restriction_notes:        Optional[str] = None

class LibraryPartUpdate(LibraryPartCreate):
    part_type: Optional[PartType] = None
    name: Optional[str] = None

class LibraryPartSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                       int
    wardstone_part_number:    str
    revision:                 str
    part_type:                PartType
    name:                     str
    status:                   PartStatus
    manufacturer_name:        Optional[str] = None
    manufacturer_part_number: Optional[str] = None
    material_name:            Optional[str] = None
    material_class:           Optional[MaterialClass] = None
    mass_nominal_g:           Optional[Decimal] = None
    approved_at:              Optional[datetime] = None

class LibraryPartResponse(LibraryPartCreate):
    model_config = ConfigDict(from_attributes=True)
    id:                    int
    wardstone_part_number: str
    revision:              str
    status:                PartStatus
    approved_at:           Optional[datetime] = None
    approved_by_id:        Optional[int] = None
    step_file_checksum:    Optional[str] = None
    created_at:            datetime
    updated_at:            datetime
    created_by_id:         Optional[int] = None
    superseded_by_id:      Optional[int] = None

# ── Project Part ──────────────────────────────────────────────────────────────

class ProjectPartCreate(BaseModel):
    library_part_id: int
    quantity:        int = Field(default=1, ge=1)
    designation:     Optional[str] = None
    notes:           Optional[str] = None

class ProjectPartUpdate(BaseModel):
    quantity:    Optional[int] = Field(default=None, ge=1)
    designation: Optional[str] = None
    notes:       Optional[str] = None

class ProjectPartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    project_id:      int
    library_part_id: int
    quantity:        int
    designation:     Optional[str] = None
    notes:           Optional[str] = None
    added_at:        datetime
    library_part:    LibraryPartSummary
    system_id:       Optional[int] = None  # resolved from SystemPartAssignment if exists

# ── System Part Assignment ────────────────────────────────────────────────────

class SystemPartAssignmentCreate(BaseModel):
    project_part_id: int
    position_order:  int = 0

class SystemPartAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:              int
    system_id:       int
    project_part_id: int
    position_order:  int
    assigned_at:     datetime
    project_part:    ProjectPartResponse

# ── Mechanical Joint ──────────────────────────────────────────────────────────

class MechanicalJointCreate(BaseModel):
    joint_type:               JointType
    part_a_id:                int
    part_b_id:                int
    fastener_part_id:         Optional[int] = None
    fastener_count:           Optional[int] = None
    torque_nominal_nm:        Optional[Decimal] = None
    torque_min_nm:            Optional[Decimal] = None
    torque_max_nm:            Optional[Decimal] = None
    engagement_length_mm:     Optional[Decimal] = None
    locking_feature:          Optional[LockingFeature] = None
    hole_pattern_description: Optional[str] = None
    mating_surface_flatness_mm: Optional[Decimal] = None
    mating_surface_finish_ra: Optional[Decimal] = None
    seal_part_id:             Optional[int] = None
    leak_rate_max_scc_s:      Optional[Decimal] = None
    test_pressure_bar:        Optional[Decimal] = None
    interface_drawing:        Optional[str] = None
    notes:                    Optional[str] = None

class MechanicalJointUpdate(MechanicalJointCreate):
    joint_type:  Optional[JointType] = None
    part_a_id:   Optional[int] = None
    part_b_id:   Optional[int] = None

class MechanicalJointResponse(MechanicalJointCreate):
    model_config = ConfigDict(from_attributes=True)
    id:                  int
    joint_id:            str
    project_id:          int
    status:              JointStatus
    confidence:          Optional[ConfidenceLevel] = None
    source_step_file_id: Optional[int] = None
    source_step_entity:  Optional[str] = None
    created_at:          datetime
    updated_at:          datetime
    fastener_part:       Optional[LibraryPartSummary] = None
    seal_part:           Optional[LibraryPartSummary] = None

# ── Pending Parts Import ──────────────────────────────────────────────────────

class PendingPartsImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:                    int
    document_id:           int
    status:                PendingPartsStatus
    proposed_data:         dict[str, Any]
    confidence_scores:     dict[str, str]
    low_confidence_fields: list[str]
    extraction_log:        Optional[str] = None
    parser_version:        Optional[str] = None
    library_part_id:       Optional[int] = None
    created_at:            datetime

class PendingPartsImportApprove(BaseModel):
    overrides: dict[str, Any] = Field(default_factory=dict)
    supplier_id: Optional[int] = None   # if set, creates CatalogPart link

# ── Assembly Parse ────────────────────────────────────────────────────────────

class AssemblyParseJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id:           int
    project_id:   int
    status:       str
    progress_log: Optional[str] = None
    result:       Optional[dict] = None
    error:        Optional[str] = None
    created_at:   datetime
    completed_at: Optional[datetime] = None
```

---

### 3.6 Alembic migration

Hand-write `backend/alembic/versions/NNNN_parts_library_and_mechanical.py` where NNNN = next sequential number. Check with `alembic current` first.

```python
"""Parts Library, Project Parts, Mechanical Joints

Revision ID: <generate>
Revises: <HEAD_BEFORE>
Create Date: <today>
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '<generate>'
down_revision = '<HEAD_BEFORE>'
branch_labels = None
depends_on = None

def upgrade():
    # ── 1. Enum types ─────────────────────────────────────────────────────────
    # Create each as a real PostgreSQL ENUM type
    part_type_enum = postgresql.ENUM(
        'fastener','washer','insert','bracket','enclosure','seal','bearing',
        'hinge_latch','thermal_interface','pcb_mechanical','custom',
        name='part_type', create_type=True
    )
    part_status_enum = postgresql.ENUM(
        'draft','under_review','approved','superseded','obsolete',
        name='part_status', create_type=True
    )
    material_class_enum = postgresql.ENUM(
        'aluminum','titanium','steel','stainless_steel','nickel_alloy',
        'polymer','composite','ceramic','other',
        name='material_class', create_type=True
    )
    thread_standard_enum = postgresql.ENUM(
        'iso_metric','unc','unf','npt','bspp','an_nas_ms','custom',
        name='thread_standard', create_type=True
    )
    head_type_enum = postgresql.ENUM(
        'socket','hex','pan','flat','button','torx','fillister','truss',
        name='head_type', create_type=True
    )
    drive_type_enum = postgresql.ENUM(
        'hex_key','torx','phillips','slotted','spanner','custom',
        name='drive_type', create_type=True
    )
    locking_feature_enum = postgresql.ENUM(
        'none','nylok','prevailing_torque','safety_wire','loctite',
        'castellated','lockwire_hole',
        name='locking_feature', create_type=True
    )
    qualification_status_enum = postgresql.ENUM(
        'unqualified','qual_testing','qualified','flight_proven','demanufactured',
        name='qualification_status', create_type=True
    )
    pending_parts_status_enum = postgresql.ENUM(
        'pending','under_review','approved','rejected',
        name='pending_parts_status', create_type=True
    )
    confidence_level_enum = postgresql.ENUM(
        'high','medium','low',
        name='confidence_level', create_type=True
    )
    joint_type_enum = postgresql.ENUM(
        'bolted','riveted','press_fit','adhesive','weld','seal',
        'alignment_pin','thermal_bond','spring_clip',
        name='joint_type', create_type=True
    )
    joint_status_enum = postgresql.ENUM(
        'draft','active','superseded',
        name='joint_status', create_type=True
    )
    assembly_job_status_enum = postgresql.ENUM(
        'queued','running','complete','failed',
        name='assembly_parse_job_status', create_type=True
    )

    for e in [
        part_type_enum, part_status_enum, material_class_enum,
        thread_standard_enum, head_type_enum, drive_type_enum,
        locking_feature_enum, qualification_status_enum,
        pending_parts_status_enum, confidence_level_enum,
        joint_type_enum, joint_status_enum, assembly_job_status_enum,
    ]:
        e.create(op.get_bind(), checkfirst=True)

    # ── 2. wpn_sequences ──────────────────────────────────────────────────────
    op.create_table('wpn_sequences',
        sa.Column('part_type_code', sa.String(8), primary_key=True),
        sa.Column('next_val', sa.Integer, nullable=False, server_default='1'),
    )

    # ── 3. library_parts ──────────────────────────────────────────────────────
    op.create_table('library_parts',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('wardstone_part_number', sa.String(32), nullable=False, unique=True),
        sa.Column('revision', sa.String(2), nullable=False, server_default='00'),
        sa.Column('part_type', sa.Enum('fastener','washer','insert','bracket','enclosure',
            'seal','bearing','hinge_latch','thermal_interface','pcb_mechanical','custom',
            name='part_type', create_type=False), nullable=False),
        sa.Column('name', sa.String(500), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('manufacturer_part_number', sa.String(200), nullable=True),
        sa.Column('manufacturer_name', sa.String(200), nullable=True),
        sa.Column('cage_code', sa.String(10), nullable=True),
        sa.Column('nsn', sa.String(20), nullable=True),
        sa.Column('drawing_number', sa.String(200), nullable=True),
        sa.Column('drawing_revision', sa.String(20), nullable=True),
        sa.Column('heritage', sa.Text, nullable=True),
        sa.Column('status', sa.Enum('draft','under_review','approved','superseded','obsolete',
            name='part_status', create_type=False), nullable=False, server_default='draft'),
        sa.Column('superseded_by_id', sa.Integer,
            sa.ForeignKey('library_parts.id', ondelete='SET NULL'), nullable=True),
        # Dimensional
        sa.Column('bounding_box_x_mm', sa.Numeric(12,4), nullable=True),
        sa.Column('bounding_box_y_mm', sa.Numeric(12,4), nullable=True),
        sa.Column('bounding_box_z_mm', sa.Numeric(12,4), nullable=True),
        sa.Column('volume_mm3', sa.Numeric(18,4), nullable=True),
        sa.Column('surface_area_mm2', sa.Numeric(18,4), nullable=True),
        sa.Column('thread_size', sa.String(50), nullable=True),
        sa.Column('thread_standard', sa.Enum('iso_metric','unc','unf','npt','bspp',
            'an_nas_ms','custom', name='thread_standard', create_type=False), nullable=True),
        sa.Column('nominal_diameter_mm', sa.Numeric(12,4), nullable=True),
        sa.Column('nominal_length_mm', sa.Numeric(12,4), nullable=True),
        sa.Column('head_type', sa.Enum('socket','hex','pan','flat','button','torx',
            'fillister','truss', name='head_type', create_type=False), nullable=True),
        sa.Column('drive_type', sa.Enum('hex_key','torx','phillips','slotted','spanner',
            'custom', name='drive_type', create_type=False), nullable=True),
        sa.Column('nominal_bore_mm', sa.Numeric(12,4), nullable=True),
        sa.Column('cross_section_dia_mm', sa.Numeric(12,4), nullable=True),
        sa.Column('flange_diameter_mm', sa.Numeric(12,4), nullable=True),
        sa.Column('hole_pattern_count', sa.Integer, nullable=True),
        sa.Column('hole_pattern_dia_mm', sa.Numeric(12,4), nullable=True),
        sa.Column('hole_pattern_pcd_mm', sa.Numeric(12,4), nullable=True),
        # Material
        sa.Column('material_name', sa.String(200), nullable=True),
        sa.Column('material_standard', sa.String(200), nullable=True),
        sa.Column('material_class', sa.Enum('aluminum','titanium','steel','stainless_steel',
            'nickel_alloy','polymer','composite','ceramic','other',
            name='material_class', create_type=False), nullable=True),
        sa.Column('density_g_cm3', sa.Numeric(10,4), nullable=True),
        sa.Column('yield_strength_mpa', sa.Numeric(10,2), nullable=True),
        sa.Column('ultimate_strength_mpa', sa.Numeric(10,2), nullable=True),
        sa.Column('elastic_modulus_gpa', sa.Numeric(10,2), nullable=True),
        sa.Column('hardness', sa.String(50), nullable=True),
        sa.Column('thermal_conductivity_wm', sa.Numeric(10,4), nullable=True),
        sa.Column('cte_um_m_c', sa.Numeric(10,4), nullable=True),
        sa.Column('corrosion_protection', sa.String(200), nullable=True),
        sa.Column('flammability_class', sa.String(100), nullable=True),
        sa.Column('outgassing_tml_pct', sa.Numeric(8,4), nullable=True),
        sa.Column('outgassing_cvcm_pct', sa.Numeric(8,4), nullable=True),
        # Performance
        sa.Column('mass_nominal_g', sa.Numeric(12,4), nullable=True),
        sa.Column('mass_max_g', sa.Numeric(12,4), nullable=True),
        sa.Column('proof_load_n', sa.Numeric(12,2), nullable=True),
        sa.Column('clamp_load_n', sa.Numeric(12,2), nullable=True),
        sa.Column('torque_nominal_nm', sa.Numeric(10,4), nullable=True),
        sa.Column('torque_min_nm', sa.Numeric(10,4), nullable=True),
        sa.Column('torque_max_nm', sa.Numeric(10,4), nullable=True),
        sa.Column('torque_lubricated_nm', sa.Numeric(10,4), nullable=True),
        sa.Column('locking_feature', sa.Enum('none','nylok','prevailing_torque','safety_wire',
            'loctite','castellated','lockwire_hole',
            name='locking_feature', create_type=False), nullable=True, server_default='none'),
        sa.Column('safety_wire_holes', sa.Boolean, nullable=True),
        sa.Column('shear_strength_n', sa.Numeric(12,2), nullable=True),
        sa.Column('bearing_load_n', sa.Numeric(12,2), nullable=True),
        sa.Column('compression_set_pct', sa.Numeric(8,2), nullable=True),
        sa.Column('sealing_pressure_max_bar', sa.Numeric(10,3), nullable=True),
        sa.Column('temperature_min_c', sa.Numeric(8,2), nullable=True),
        sa.Column('temperature_max_c', sa.Numeric(8,2), nullable=True),
        # Procurement
        sa.Column('unit_cost_usd', sa.Numeric(12,4), nullable=True),
        sa.Column('lead_time_weeks', sa.Integer, nullable=True),
        sa.Column('min_order_qty', sa.Integer, nullable=True),
        sa.Column('preferred_supplier_id', sa.Integer,
            sa.ForeignKey('suppliers.id', ondelete='SET NULL'), nullable=True),
        sa.Column('supplier_part_number', sa.String(200), nullable=True),
        sa.Column('qualification_status', sa.Enum('unqualified','qual_testing','qualified',
            'flight_proven','demanufactured',
            name='qualification_status', create_type=False), nullable=True,
            server_default='unqualified'),
        sa.Column('qualification_basis', sa.Text, nullable=True),
        sa.Column('shelf_life_months', sa.Integer, nullable=True),
        sa.Column('date_of_manufacture', sa.Date, nullable=True),
        sa.Column('restricted_use', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('restriction_notes', sa.Text, nullable=True),
        # STEP traceability
        sa.Column('step_file_id', sa.Integer,
            sa.ForeignKey('documents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('step_file_checksum', sa.String(64), nullable=True),
        sa.Column('step_entity_id', sa.String(200), nullable=True),
        # Audit
        sa.Column('approved_by_id', sa.Integer,
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by_id', sa.Integer,
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )

    # ── 4. pending_parts_imports ───────────────────────────────────────────────
    op.create_table('pending_parts_imports',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('document_id', sa.Integer,
            sa.ForeignKey('documents.id', ondelete='CASCADE'), nullable=False),
        sa.Column('status', sa.Enum('pending','under_review','approved','rejected',
            name='pending_parts_status', create_type=False),
            nullable=False, server_default='pending'),
        sa.Column('proposed_data', postgresql.JSONB, nullable=False,
            server_default='{}'),
        sa.Column('confidence_scores', postgresql.JSONB, nullable=False,
            server_default='{}'),
        sa.Column('low_confidence_fields', postgresql.ARRAY(sa.String), nullable=False,
            server_default='{}'),
        sa.Column('extraction_log', sa.Text, nullable=True),
        sa.Column('parser_version', sa.String(32), nullable=True),
        sa.Column('reviewed_by_id', sa.Integer,
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejection_reason', sa.Text, nullable=True),
        sa.Column('library_part_id', sa.Integer,
            sa.ForeignKey('library_parts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by_id', sa.Integer,
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )

    # ── 5. project_parts ──────────────────────────────────────────────────────
    op.create_table('project_parts',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('project_id', sa.Integer,
            sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('library_part_id', sa.Integer,
            sa.ForeignKey('library_parts.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('quantity', sa.Integer, nullable=False, server_default='1'),
        sa.Column('designation', sa.String(64), nullable=True),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('added_by_id', sa.Integer,
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('added_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('project_id', 'library_part_id', name='uq_project_part'),
    )

    # ── 6. system_part_assignments ────────────────────────────────────────────
    op.create_table('system_part_assignments',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('system_id', sa.Integer,
            sa.ForeignKey('systems.id', ondelete='CASCADE'), nullable=False),
        sa.Column('project_part_id', sa.Integer,
            sa.ForeignKey('project_parts.id', ondelete='CASCADE'), nullable=False),
        sa.Column('position_order', sa.Integer, nullable=False, server_default='0'),
        sa.Column('assigned_by_id', sa.Integer,
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False),
        sa.UniqueConstraint('system_id', 'project_part_id',
            name='uq_system_part_assignment'),
    )

    # ── 7. mechanical_joint_sequences ─────────────────────────────────────────
    op.create_table('mechanical_joint_sequences',
        sa.Column('project_id', sa.Integer, primary_key=True),
        sa.Column('next_val', sa.Integer, nullable=False, server_default='1'),
    )

    # ── 8. assembly_parse_jobs ────────────────────────────────────────────────
    op.create_table('assembly_parse_jobs',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('project_id', sa.Integer,
            sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('document_id', sa.Integer,
            sa.ForeignKey('documents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.Enum('queued','running','complete','failed',
            name='assembly_parse_job_status', create_type=False),
            nullable=False, server_default='queued'),
        sa.Column('progress_log', sa.Text, nullable=True),
        sa.Column('result', postgresql.JSONB, nullable=True),
        sa.Column('error', sa.Text, nullable=True),
        sa.Column('created_by_id', sa.Integer,
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
    )

    # ── 9. mechanical_joints ──────────────────────────────────────────────────
    op.create_table('mechanical_joints',
        sa.Column('id', sa.Integer, primary_key=True),
        sa.Column('joint_id', sa.String(32), nullable=False, unique=True),
        sa.Column('project_id', sa.Integer,
            sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('joint_type', sa.Enum('bolted','riveted','press_fit','adhesive','weld',
            'seal','alignment_pin','thermal_bond','spring_clip',
            name='joint_type', create_type=False), nullable=False),
        sa.Column('part_a_id', sa.Integer,
            sa.ForeignKey('project_parts.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('part_b_id', sa.Integer,
            sa.ForeignKey('project_parts.id', ondelete='RESTRICT'), nullable=False),
        sa.Column('fastener_part_id', sa.Integer,
            sa.ForeignKey('library_parts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('fastener_count', sa.Integer, nullable=True),
        sa.Column('torque_nominal_nm', sa.Numeric(10,4), nullable=True),
        sa.Column('torque_min_nm', sa.Numeric(10,4), nullable=True),
        sa.Column('torque_max_nm', sa.Numeric(10,4), nullable=True),
        sa.Column('engagement_length_mm', sa.Numeric(10,4), nullable=True),
        sa.Column('locking_feature', sa.Enum('none','nylok','prevailing_torque',
            'safety_wire','loctite','castellated','lockwire_hole',
            name='locking_feature', create_type=False), nullable=True),
        sa.Column('hole_pattern_description', sa.String(300), nullable=True),
        sa.Column('mating_surface_flatness_mm', sa.Numeric(10,4), nullable=True),
        sa.Column('mating_surface_finish_ra', sa.Numeric(10,4), nullable=True),
        sa.Column('seal_part_id', sa.Integer,
            sa.ForeignKey('library_parts.id', ondelete='SET NULL'), nullable=True),
        sa.Column('leak_rate_max_scc_s', sa.Numeric(12,6), nullable=True),
        sa.Column('test_pressure_bar', sa.Numeric(10,3), nullable=True),
        sa.Column('interface_drawing', sa.String(200), nullable=True),
        sa.Column('source_step_file_id', sa.Integer,
            sa.ForeignKey('documents.id', ondelete='SET NULL'), nullable=True),
        sa.Column('source_step_entity', sa.Text, nullable=True),
        sa.Column('confidence', sa.Enum('high','medium','low',
            name='confidence_level', create_type=False), nullable=True),
        sa.Column('status', sa.Enum('draft','active','superseded',
            name='joint_status', create_type=False),
            nullable=False, server_default='draft'),
        sa.Column('notes', sa.Text, nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True),
            server_default=sa.text('now()'), nullable=False),
        sa.Column('created_by_id', sa.Integer,
            sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
    )

    # ── 10. ALTER existing table: units ───────────────────────────────────────
    op.add_column('units',
        sa.Column('library_part_id', sa.Integer,
            sa.ForeignKey('library_parts.id', ondelete='SET NULL'), nullable=True)
    )

    # ── 11. Add MECHANICAL_JOINT to source_entity_type enum ──────────────────
    op.execute("ALTER TYPE source_entity_type ADD VALUE IF NOT EXISTS 'mechanical_joint'")

    # ── 12. Indexes ───────────────────────────────────────────────────────────
    op.create_index('ix_library_part_type_status', 'library_parts',
        ['part_type', 'status'])
    op.create_index('ix_library_part_step_checksum', 'library_parts',
        ['step_file_checksum'])
    op.create_index('ix_library_part_mpn', 'library_parts',
        ['manufacturer_part_number'])
    op.create_index('ix_project_parts_project', 'project_parts', ['project_id'])
    op.create_index('ix_project_parts_library', 'project_parts', ['library_part_id'])
    op.create_index('ix_spa_system', 'system_part_assignments', ['system_id'])
    op.create_index('ix_spa_ppart', 'system_part_assignments', ['project_part_id'])
    op.create_index('ix_mj_project_status', 'mechanical_joints',
        ['project_id', 'status'])
    op.create_index('ix_mj_parts', 'mechanical_joints', ['part_a_id', 'part_b_id'])
    op.create_index('ix_apj_project', 'assembly_parse_jobs', ['project_id'])

    # ── 13. Seed wpn_sequences ────────────────────────────────────────────────
    op.execute("""
        INSERT INTO wpn_sequences (part_type_code, next_val) VALUES
        ('FAST', 1), ('WASH', 1), ('INSR', 1), ('BRKT', 1), ('ENCL', 1),
        ('SEAL', 1), ('BEAR', 1), ('HNGL', 1), ('THIF', 1), ('PCBM', 1),
        ('CUST', 1)
        ON CONFLICT DO NOTHING
    """)


def downgrade():
    # Reverse in exact reverse order
    op.execute("DELETE FROM wpn_sequences")
    op.drop_index('ix_apj_project', table_name='assembly_parse_jobs')
    op.drop_index('ix_mj_parts', table_name='mechanical_joints')
    op.drop_index('ix_mj_project_status', table_name='mechanical_joints')
    op.drop_index('ix_spa_ppart', table_name='system_part_assignments')
    op.drop_index('ix_spa_system', table_name='system_part_assignments')
    op.drop_index('ix_project_parts_library', table_name='project_parts')
    op.drop_index('ix_project_parts_project', table_name='project_parts')
    op.drop_index('ix_library_part_mpn', table_name='library_parts')
    op.drop_index('ix_library_part_step_checksum', table_name='library_parts')
    op.drop_index('ix_library_part_type_status', table_name='library_parts')
    op.drop_column('units', 'library_part_id')
    op.drop_table('mechanical_joints')
    op.drop_table('assembly_parse_jobs')
    op.drop_table('mechanical_joint_sequences')
    op.drop_table('system_part_assignments')
    op.drop_table('project_parts')
    op.drop_table('pending_parts_imports')
    op.drop_table('library_parts')
    op.drop_table('wpn_sequences')
    # Drop enum types in reverse
    for name in [
        'assembly_parse_job_status', 'joint_status', 'joint_type',
        'confidence_level', 'pending_parts_status', 'qualification_status',
        'locking_feature', 'drive_type', 'head_type', 'thread_standard',
        'material_class', 'part_status', 'part_type',
    ]:
        op.execute(f"DROP TYPE IF EXISTS {name}")
    # NOTE: Cannot remove 'mechanical_joint' from source_entity_type in downgrade
    # without recreating the type. Leave it — it has no rows referencing it at this point.
```

After writing the migration, run the down/up cycle test:
```bash
docker exec astra-backend-1 alembic downgrade -1
docker exec astra-backend-1 alembic upgrade head
```
Both must succeed. The down test requires the DB to be in a known state — use the pre-flight snapshot if needed.

---

### 3.7 Phase 1 verification gate

```bash
docker exec astra-backend-1 alembic upgrade head
docker exec astra-backend-1 alembic check
docker exec astra-db-1 psql -U astra -d astra -c "\d library_parts" | head -60
docker exec astra-db-1 psql -U astra -d astra -c "\d mechanical_joints" | head -50
docker exec astra-db-1 psql -U astra -d astra -c "SELECT * FROM wpn_sequences;"
docker exec astra-db-1 psql -U astra -d astra -c "SELECT enum_range(NULL::part_type);"
docker exec astra-db-1 psql -U astra -d astra -c "SELECT enum_range(NULL::joint_type);"
docker exec astra-backend-1 python3 -c "
from app.models.parts_library import (
    LibraryPart, MechanicalJoint, ProjectPart, WPNSequence
)
from app.schemas.parts_library import (
    LibraryPartCreate, MechanicalJointCreate, LibraryPartResponse
)
print('All models and schemas import cleanly')
"
docker exec astra-backend-1 pytest tests/ -q -m "not performance"
# Zero regressions — count must equal TESTS_BEFORE
```

Commit: `feat(parts): phase-1-complete — models, migration NNNN, pydantic schemas`

---

## 4. Phase 2 — Services, Routers, Tests

---

### 4.1 WPN service: `backend/app/services/parts/wpn_service.py`

```python
"""Wardstone Part Number assignment service.

Format: WS-{TYPE_CODE}-{SEQ:06d}-{REV:02d}
Assignment uses SELECT FOR UPDATE to prevent race conditions.
"""
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models.parts_library import WPNSequence, PartType

WPN_TYPE_CODES: dict[PartType, str] = {
    PartType.FASTENER:          "FAST",
    PartType.WASHER:            "WASH",
    PartType.INSERT:            "INSR",
    PartType.BRACKET:           "BRKT",
    PartType.ENCLOSURE:         "ENCL",
    PartType.SEAL:              "SEAL",
    PartType.BEARING:           "BEAR",
    PartType.HINGE_LATCH:       "HNGL",
    PartType.THERMAL_INTERFACE: "THIF",
    PartType.PCB_MECHANICAL:    "PCBM",
    PartType.CUSTOM:            "CUST",
}

def assign_wpn(db: Session, part_type: PartType) -> str:
    """
    Assign a unique WPN. Thread-safe via SELECT FOR UPDATE.
    Must be called within an open transaction — caller commits.
    """
    code = WPN_TYPE_CODES[part_type]
    seq = (
        db.query(WPNSequence)
        .filter(WPNSequence.part_type_code == code)
        .with_for_update()
        .first()
    )
    if seq is None:
        seq = WPNSequence(part_type_code=code, next_val=1)
        db.add(seq)
        db.flush()
    wpn = f"WS-{code}-{seq.next_val:06d}-00"
    seq.next_val += 1
    return wpn

def bump_revision(wpn: str) -> str:
    """
    WS-FAST-000042-00 → WS-FAST-000042-01
    WS-FAST-000042-09 → WS-FAST-000042-10
    """
    base, rev_str = wpn.rsplit("-", 1)
    return f"{base}-{int(rev_str) + 1:02d}"
```

---

### 4.2 STEP parser service: `backend/app/services/parts/step_parser.py`

```python
"""
STEP file geometry and metadata extraction.

Two execution paths:
  Full:  pythonOCC installed → extracts B-rep geometry, holes, bounding box, volume
  Stub:  pythonOCC not available → extracts PRODUCT metadata via regex only
         All geometry fields return None; confidence = LOW.

Thread recognition table maps clearance-hole diameters to thread families and
nominal torque values for dry A286 stainless fasteners.
"""
import re
import hashlib
import logging
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional
from app.models.parts_library import ThreadStandard, ConfidenceLevel

logger = logging.getLogger(__name__)

PARSER_VERSION = "1.0.0"

# Thread recognition table: (dia_min_mm, dia_max_mm, thread_size, standard, torque_nm)
THREAD_TABLE = [
    (Decimal("3.30"),  Decimal("3.50"),  "M3×0.5",    ThreadStandard.ISO_METRIC, Decimal("1.2")),
    (Decimal("4.40"),  Decimal("4.60"),  "M4×0.7",    ThreadStandard.ISO_METRIC, Decimal("2.9")),
    (Decimal("5.40"),  Decimal("5.60"),  "M5×0.8",    ThreadStandard.ISO_METRIC, Decimal("5.7")),
    (Decimal("6.50"),  Decimal("6.70"),  "M6×1.0",    ThreadStandard.ISO_METRIC, Decimal("9.8")),
    (Decimal("8.50"),  Decimal("8.70"),  "M8×1.25",   ThreadStandard.ISO_METRIC, Decimal("23.0")),
    (Decimal("10.50"), Decimal("10.70"), "M10×1.5",   ThreadStandard.ISO_METRIC, Decimal("45.0")),
    (Decimal("3.28"),  Decimal("3.32"),  "#6-32 UNC", ThreadStandard.UNC,        Decimal("0.9")),
    (Decimal("4.19"),  Decimal("4.22"),  "#8-32 UNC", ThreadStandard.UNC,        Decimal("1.5")),
    (Decimal("5.16"),  Decimal("5.18"),  "#10-32 UNF",ThreadStandard.UNF,        Decimal("2.4")),
    (Decimal("6.45"),  Decimal("6.50"),  "1/4-28 UNF",ThreadStandard.UNF,        Decimal("6.8")),
]

def match_thread(clearance_dia_mm: Decimal) -> Optional[tuple]:
    """Return (thread_size, standard, torque_nm) or None."""
    for lo, hi, size, std, torque in THREAD_TABLE:
        if lo <= clearance_dia_mm <= hi:
            return size, std, torque
    return None

@dataclass
class StepParserResult:
    # Metadata (always populated)
    product_name:          Optional[str]    = None
    product_description:   Optional[str]    = None
    manufacturer_part_number: Optional[str] = None
    step_entity_id:        Optional[str]    = None
    # Geometry (None if pythonOCC not available)
    bounding_box_x_mm:     Optional[Decimal] = None
    bounding_box_y_mm:     Optional[Decimal] = None
    bounding_box_z_mm:     Optional[Decimal] = None
    volume_mm3:            Optional[Decimal] = None
    surface_area_mm2:      Optional[Decimal] = None
    nominal_diameter_mm:   Optional[Decimal] = None
    nominal_length_mm:     Optional[Decimal] = None
    thread_size:           Optional[str]     = None
    thread_standard:       Optional[ThreadStandard] = None
    torque_nominal_nm:     Optional[Decimal] = None
    hole_pattern_count:    Optional[int]     = None
    hole_pattern_dia_mm:   Optional[Decimal] = None
    hole_pattern_pcd_mm:   Optional[Decimal] = None
    mass_nominal_g:        Optional[Decimal] = None
    # Confidence
    confidence_scores:     dict[str, str]   = field(default_factory=dict)
    low_confidence_fields: list[str]        = field(default_factory=list)
    parser_version:        str              = PARSER_VERSION
    extraction_log:        str              = ""
    occ_available:         bool             = False


def parse_step_file(file_path: str) -> StepParserResult:
    """
    Main entry point. Attempts full OCC extraction; falls back to metadata-only.
    """
    result = StepParserResult()
    log_lines: list[str] = []

    # Always run metadata extraction first
    _extract_metadata(file_path, result, log_lines)

    # Attempt full geometry extraction
    try:
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.IFSelect import IFSelect_RetDone
        from OCC.Core.BRepBndLib import brepbndlib
        from OCC.Core.Bnd import Bnd_Box
        from OCC.Core.GProp import GProp_GProps
        from OCC.Core.BRepGProp import brepgprop
        from OCC.Core.BRep import BRep_Tool
        from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_EDGE
        from OCC.Core.TopExp import TopExp_Explorer
        from OCC.Core.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
        from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
        import math

        reader = STEPControl_Reader()
        status = reader.ReadFile(file_path)
        if status != IFSelect_RetDone:
            log_lines.append(f"OCC ReadFile failed with status {status}")
            raise RuntimeError("ReadFile failed")

        reader.TransferRoots()
        shape = reader.OneShape()

        # Bounding box
        bbox = Bnd_Box()
        brepbndlib.Add(shape, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        result.bounding_box_x_mm = Decimal(str(round(xmax - xmin, 4)))
        result.bounding_box_y_mm = Decimal(str(round(ymax - ymin, 4)))
        result.bounding_box_z_mm = Decimal(str(round(zmax - zmin, 4)))

        # Volume and surface area via BRepGProp
        props = GProp_GProps()
        brepgprop.VolumeProperties(shape, props)
        result.volume_mm3 = Decimal(str(round(props.Mass(), 4)))
        brepgprop.SurfaceProperties(shape, props)
        result.surface_area_mm2 = Decimal(str(round(props.Mass(), 4)))

        # Estimate mass from volume × typical material density (steel 7.85 g/cm³)
        if result.volume_mm3:
            density_g_mm3 = Decimal("0.00785")  # steel default
            result.mass_nominal_g = round(result.volume_mm3 * density_g_mm3, 4)

        # Cylindrical face analysis — find hole candidates
        hole_diameters: list[Decimal] = []
        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = exp.Current()
            surface = BRepAdaptor_Surface(face)
            if surface.GetType() == GeomAbs_Cylinder:
                cyl = surface.Cylinder()
                dia = Decimal(str(round(cyl.Radius() * 2, 4)))
                hole_diameters.append(dia)
            exp.Next()

        if hole_diameters:
            # Most common diameter = primary hole feature
            from collections import Counter
            most_common_dia = Counter(hole_diameters).most_common(1)[0][0]
            result.hole_pattern_count = hole_diameters.count(most_common_dia)
            result.hole_pattern_dia_mm = most_common_dia
            # Attempt thread match
            thread_match = match_thread(most_common_dia)
            if thread_match:
                result.thread_size, result.thread_standard, result.torque_nominal_nm = thread_match
                _set_confidence(result, "thread_size", ConfidenceLevel.HIGH)
                _set_confidence(result, "torque_nominal_nm", ConfidenceLevel.MEDIUM)
            else:
                _set_confidence(result, "thread_size", ConfidenceLevel.LOW)
                result.low_confidence_fields.append("thread_size")

        # Overall part nominal diameter and length from bbox
        result.nominal_diameter_mm = min(
            result.bounding_box_x_mm, result.bounding_box_y_mm
        )
        result.nominal_length_mm = result.bounding_box_z_mm

        result.occ_available = True
        _set_high_confidence_geometry(result)
        log_lines.append("OCC full extraction complete")

    except ImportError:
        log_lines.append(
            "pythonOCC not available. Stub mode: metadata extraction only. "
            "All geometry fields are None. Confidence = LOW for all geometric fields."
        )
        logger.warning("pythonOCC not installed — STEP parser running in stub mode")
        for f_name in ["bounding_box_x_mm", "bounding_box_y_mm", "bounding_box_z_mm",
                       "volume_mm3", "surface_area_mm2", "thread_size",
                       "hole_pattern_count", "mass_nominal_g"]:
            result.confidence_scores[f_name] = ConfidenceLevel.LOW.value
            result.low_confidence_fields.append(f_name)

    result.extraction_log = "\n".join(log_lines)
    return result


def _extract_metadata(file_path: str, result: StepParserResult,
                       log_lines: list[str]) -> None:
    """
    Regex-based STEP text parser. Reads the raw STEP file to extract:
    - PRODUCT entity name and description
    - FILE_NAME header entity
    - Any embedded MPN-like strings
    """
    try:
        with open(file_path, 'r', errors='replace') as f:
            content = f.read(512_000)  # Read first 500 KB only for speed

        # PRODUCT('name','description', ...) — STEP AP214 §4.2.2
        product_matches = re.findall(
            r"PRODUCT\s*\(\s*'([^']*)'\s*,\s*'([^']*)'",
            content, re.IGNORECASE
        )
        if product_matches:
            # Last PRODUCT entity is typically the top-level assembly or part
            name, description = product_matches[-1]
            result.product_name = name.strip() or None
            result.product_description = description.strip() or None
            # Try to extract MPN from name patterns like "DG2002-01MM-V-G5" or PN: ...
            mpn_pattern = re.search(
                r'\b([A-Z0-9][A-Z0-9\-]{4,20})\b', name
            )
            if mpn_pattern and not any(c in mpn_pattern.group(1) for c in [' ']):
                result.manufacturer_part_number = mpn_pattern.group(1)
                _set_confidence(result, "manufacturer_part_number", ConfidenceLevel.MEDIUM)

        # PRODUCT_DEFINITION entity ID for traceability
        pd_match = re.search(
            r'#(\d+)\s*=\s*PRODUCT_DEFINITION\s*\(', content, re.IGNORECASE
        )
        if pd_match:
            result.step_entity_id = f"#PRODUCT_DEFINITION:{pd_match.group(1)}"

        _set_confidence(result, "product_name", ConfidenceLevel.HIGH)
        _set_confidence(result, "product_description", ConfidenceLevel.HIGH)
        log_lines.append(
            f"Metadata extraction: name='{result.product_name}' "
            f"mpn='{result.manufacturer_part_number}'"
        )

    except Exception as exc:
        log_lines.append(f"Metadata extraction failed: {exc}")


def _set_confidence(result: StepParserResult,
                    field_name: str,
                    level: ConfidenceLevel) -> None:
    result.confidence_scores[field_name] = level.value
    if level == ConfidenceLevel.LOW and field_name not in result.low_confidence_fields:
        result.low_confidence_fields.append(field_name)


def _set_high_confidence_geometry(result: StepParserResult) -> None:
    for f_name in ["bounding_box_x_mm", "bounding_box_y_mm", "bounding_box_z_mm",
                   "volume_mm3", "surface_area_mm2", "mass_nominal_g",
                   "nominal_diameter_mm", "nominal_length_mm"]:
        if getattr(result, f_name) is not None:
            _set_confidence(result, f_name, ConfidenceLevel.HIGH)
```

---

### 4.3 AI interpreter: `backend/app/services/parts/ai_interpreter.py`

```python
"""
AI interpretation pass for STEP parser results.
Uses the existing three-tier AI pattern from services/ai/:
  1. Anthropic Claude Sonnet  (primary)
  2. OpenAI GPT-4o            (secondary)
  3. Rules-based fallback     (always succeeds)
"""
import json
import logging
from typing import Any
from app.services.parts.step_parser import StepParserResult
from app.models.parts_library import PartType, MaterialClass, LockingFeature

logger = logging.getLogger(__name__)

AI_SYSTEM_PROMPT = """You are an aerospace mechanical engineering AI.
Given structured data extracted from a STEP file, return ONLY a JSON object with these fields.
No prose, no markdown, no backticks. Pure JSON only.

{
  "part_type": "fastener|washer|insert|bracket|enclosure|seal|bearing|hinge_latch|thermal_interface|pcb_mechanical|custom",
  "material_name": "string or null",
  "material_class": "aluminum|titanium|steel|stainless_steel|nickel_alloy|polymer|composite|ceramic|other|null",
  "torque_nominal_nm": number_or_null,
  "torque_min_nm": number_or_null,
  "torque_max_nm": number_or_null,
  "locking_feature": "none|nylok|prevailing_torque|safety_wire|loctite|castellated|lockwire_hole|null",
  "confidence_overrides": {"field_name": "high|medium|low"},
  "flags": ["string"]
}

Rules:
- If thread_size contains 'M' (ISO metric), try to infer material class = stainless_steel for aerospace.
- If part name contains 'Ti', 'Titanium', or 'CRES', override material_class accordingly.
- torque_min_nm = torque_nominal_nm * 0.85 if only nominal is known.
- torque_max_nm = torque_nominal_nm * 1.10 if only nominal is known.
- Nylok = nylok, NY-LOK, Nyloc, patch = nylok. Prevailing = prevailing_torque.
- If part_name ends in '.stl' or '.stp', strip extension before classifying.
- flags: note unusual configurations, possible mis-identification, missing critical data."""


def interpret(parser_result: StepParserResult,
              ai_service=None) -> dict[str, Any]:
    """
    Returns a dict of field overrides to merge into proposed_data.
    Never raises — falls back to rules-based if AI is unavailable.
    """
    user_content = json.dumps({
        "product_name": parser_result.product_name,
        "product_description": parser_result.product_description,
        "manufacturer_part_number": parser_result.manufacturer_part_number,
        "bounding_box_x_mm": str(parser_result.bounding_box_x_mm or ""),
        "bounding_box_y_mm": str(parser_result.bounding_box_y_mm or ""),
        "bounding_box_z_mm": str(parser_result.bounding_box_z_mm or ""),
        "thread_size": parser_result.thread_size,
        "nominal_diameter_mm": str(parser_result.nominal_diameter_mm or ""),
        "hole_pattern_count": parser_result.hole_pattern_count,
        "torque_nominal_nm": str(parser_result.torque_nominal_nm or ""),
    }, indent=2)

    # Try AI
    if ai_service:
        try:
            ai_result = ai_service.complete(
                system=AI_SYSTEM_PROMPT,
                user=user_content,
                max_tokens=500,
            )
            text = ai_result.strip()
            # Strip JSON fences if present
            text = text.replace("```json", "").replace("```", "").strip()
            return json.loads(text)
        except Exception as exc:
            logger.warning("AI interpretation pass failed: %s — using rules fallback", exc)

    return _rules_fallback(parser_result)


def _rules_fallback(r: StepParserResult) -> dict[str, Any]:
    """
    Deterministic rules-based classification. Always returns a valid dict.
    """
    result: dict[str, Any] = {
        "part_type": None,
        "material_name": None,
        "material_class": None,
        "torque_nominal_nm": None,
        "torque_min_nm": None,
        "torque_max_nm": None,
        "locking_feature": "none",
        "confidence_overrides": {},
        "flags": [],
    }

    name = (r.product_name or "").lower()

    # Part type classification from name keywords
    if any(k in name for k in ["screw", "bolt", "stud", "fastener", "m3", "m4",
                                 "m5", "m6", "m8", "m10", "#6", "#8", "#10"]):
        result["part_type"] = "fastener"
    elif any(k in name for k in ["washer", "shim"]):
        result["part_type"] = "washer"
    elif any(k in name for k in ["insert", "helicoil", "keensert", "nutsert"]):
        result["part_type"] = "insert"
    elif any(k in name for k in ["bracket", "mount", "standoff", "spacer"]):
        result["part_type"] = "bracket"
    elif any(k in name for k in ["housing", "enclosure", "chassis", "panel", "cover"]):
        result["part_type"] = "enclosure"
    elif any(k in name for k in ["o-ring", "oring", "gasket", "seal"]):
        result["part_type"] = "seal"
    elif any(k in name for k in ["bearing"]):
        result["part_type"] = "bearing"
    elif r.thread_size:
        # Has a thread → assume fastener
        result["part_type"] = "fastener"
        result["confidence_overrides"]["part_type"] = "medium"

    # Material from name
    if any(k in name for k in ["ti-6", "titanium", "ti "]):
        result["material_name"] = "Ti-6Al-4V"
        result["material_class"] = "titanium"
    elif any(k in name for k in ["a286", "a-286"]):
        result["material_name"] = "A286"
        result["material_class"] = "stainless_steel"
    elif any(k in name for k in ["17-4", "cres"]):
        result["material_name"] = "17-4 PH H900"
        result["material_class"] = "stainless_steel"
    elif result["part_type"] == "fastener":
        # Aerospace fasteners default to stainless
        result["material_class"] = "stainless_steel"
        result["confidence_overrides"]["material_class"] = "low"

    # Torque from existing thread match
    if r.torque_nominal_nm:
        result["torque_nominal_nm"] = float(r.torque_nominal_nm)
        result["torque_min_nm"]     = round(float(r.torque_nominal_nm) * 0.85, 4)
        result["torque_max_nm"]     = round(float(r.torque_nominal_nm) * 1.10, 4)

    # Nylok detection from name
    if any(k in name for k in ["nylok", "ny-lok", "nyloc", "patch"]):
        result["locking_feature"] = "nylok"
    elif any(k in name for k in ["prevail", "pt"]):
        result["locking_feature"] = "prevailing_torque"

    if result["part_type"] is None:
        result["part_type"] = "custom"
        result["flags"].append("Could not classify part type — defaulted to custom")
        result["confidence_overrides"]["part_type"] = "low"

    return result
```

---

### 4.4 Mechanical req templates: `backend/app/services/parts/mechanical_req_templates.py`

```python
"""
Auto-requirement templates for mechanical joints.
Each template is a str.format_map() pattern.
Context keys are resolved by build_template_context() at requirement-generation time.

Template IDs are stable — once assigned to a RequirementSourceLink, they never change.
Adding new templates is safe. Removing templates requires a migration to NULL-out the
generation_template_id on affected requirements first.
"""
from typing import Optional
from app.models.parts_library import JointType

TEMPLATES: dict[str, str] = {
    "MECH-BOLT-001": (
        "The {part_b_name} SHALL be secured to {part_a_name} using "
        "{fastener_count}× {fastener_description} fasteners installed to a torque "
        "of {torque_nominal_nm} N·m ± {torque_tolerance_nm} N·m."
    ),
    "MECH-BOLT-002": (
        "The installation torque for {fastener_description} fasteners at the "
        "{part_a_name}/{part_b_name} interface SHALL NOT exceed {torque_max_nm} N·m."
    ),
    "MECH-BOLT-003": (
        "All {fastener_description} fasteners at the {part_a_name}/{part_b_name} "
        "interface SHALL incorporate {locking_feature_description} positive locking."
    ),
    "MECH-BOLT-004": (
        "Thread engagement length for {fastener_description} fasteners at the "
        "{part_a_name}/{part_b_name} interface SHALL be a minimum of "
        "{engagement_length_mm} mm."
    ),
    "MECH-SEAL-001": (
        "The {part_a_name}/{part_b_name} interface SHALL maintain leak-tightness "
        "at a maximum leak rate of {leak_rate_max_scc_s} standard cubic centimetres "
        "per second (scc/s) when tested at {test_pressure_bar} bar proof pressure."
    ),
    "MECH-SEAL-002": (
        "The {seal_description} sealing element at the {part_a_name}/{part_b_name} "
        "interface SHALL achieve a mating surface flatness of ≤ "
        "{mating_surface_flatness_mm} mm across the sealing land."
    ),
    "MECH-SURF-001": (
        "The mating surface finish at the {part_a_name}/{part_b_name} interface "
        "SHALL be {mating_surface_finish_ra} µm Ra or better."
    ),
    "MECH-PRESS-001": (
        "The {part_b_name} SHALL be installed into {part_a_name} with an "
        "interference fit achieving a minimum retention force of "
        "{retention_force_n} N at the operating temperature extremes."
    ),
    "MECH-ALIGN-001": (
        "The {part_b_name} SHALL be aligned to {part_a_name} using "
        "{fastener_count}× alignment pin(s), achieving a maximum positional "
        "deviation of {alignment_tolerance_mm} mm."
    ),
    "MECH-MASS-001": (
        "The {part_name} SHALL have a maximum installed mass of {mass_max_g} g "
        "including all fasteners, sealant, and ancillary hardware."
    ),
}

# Which templates apply to each joint type
JOINT_TYPE_TEMPLATES: dict[JointType, list[str]] = {
    JointType.BOLTED:        ["MECH-BOLT-001", "MECH-BOLT-002", "MECH-BOLT-003",
                               "MECH-BOLT-004", "MECH-SURF-001"],
    JointType.SEAL:          ["MECH-SEAL-001", "MECH-SEAL-002", "MECH-SURF-001"],
    JointType.PRESS_FIT:     ["MECH-PRESS-001", "MECH-SURF-001"],
    JointType.ALIGNMENT_PIN: ["MECH-ALIGN-001"],
    JointType.RIVETED:       ["MECH-BOLT-001", "MECH-SURF-001"],
    JointType.THERMAL_BOND:  ["MECH-SURF-001"],
    JointType.SPRING_CLIP:   [],
    JointType.ADHESIVE:      ["MECH-SURF-001"],
    JointType.WELD:          ["MECH-SURF-001"],
}

LOCKING_FEATURE_DESCRIPTIONS: dict[str, str] = {
    "nylok":              "Nylok-insert",
    "prevailing_torque":  "prevailing-torque",
    "safety_wire":        "safety-wire",
    "loctite":            "Loctite thread-locking compound",
    "castellated":        "castellated nut and cotter pin",
    "lockwire_hole":      "lockwire",
    "none":               "no",
}

def build_template_context(joint, part_a_lp, part_b_lp,
                            fastener_lp=None, seal_lp=None) -> dict:
    """
    Resolve all template tokens from a MechanicalJoint + related LibraryParts.
    Returns a dict suitable for str.format_map().
    Missing values are substituted with "TBD" so templates never raise KeyError.
    """
    torque_nom = joint.torque_nominal_nm
    torque_max = joint.torque_max_nm
    torque_min = joint.torque_min_nm
    torque_tolerance = (
        round((float(torque_max) - float(torque_min)) / 2, 4)
        if torque_max and torque_min
        else "TBD"
    )
    lf = (joint.locking_feature or "none").value if hasattr(
        joint.locking_feature, 'value') else (joint.locking_feature or "none")

    return {
        "part_a_name":             part_a_lp.name if part_a_lp else "Part A",
        "part_b_name":             part_b_lp.name if part_b_lp else "Part B",
        "fastener_description":    fastener_lp.name if fastener_lp else "fasteners",
        "fastener_count":          joint.fastener_count or "TBD",
        "torque_nominal_nm":       str(torque_nom or "TBD"),
        "torque_min_nm":           str(torque_min or "TBD"),
        "torque_max_nm":           str(torque_max or "TBD"),
        "torque_tolerance_nm":     str(torque_tolerance),
        "engagement_length_mm":    str(joint.engagement_length_mm or "TBD"),
        "locking_feature_description": LOCKING_FEATURE_DESCRIPTIONS.get(lf, lf),
        "mating_surface_flatness_mm":  str(joint.mating_surface_flatness_mm or "TBD"),
        "mating_surface_finish_ra":    str(joint.mating_surface_finish_ra or "TBD"),
        "seal_description":        seal_lp.name if seal_lp else "sealing element",
        "leak_rate_max_scc_s":     str(joint.leak_rate_max_scc_s or "TBD"),
        "test_pressure_bar":       str(joint.test_pressure_bar or "TBD"),
        "alignment_tolerance_mm":  "0.050",   # default GD&T tolerance, override manually
        "retention_force_n":       "TBD",
        "part_name":               part_b_lp.name if part_b_lp else "Part",
        "mass_max_g":              str(part_b_lp.mass_max_g if part_b_lp else "TBD"),
    }

def render_template(template_id: str, context: dict) -> Optional[str]:
    """Render a template to a SHALL statement. Returns None if template_id unknown."""
    tmpl = TEMPLATES.get(template_id)
    if not tmpl:
        return None
    try:
        return tmpl.format_map(context)
    except (KeyError, ValueError):
        # Partial context — replace missing tokens with TBD
        class SafeDict(dict):
            def __missing__(self, key):
                return "TBD"
        return tmpl.format_map(SafeDict(context))
```

---

### 4.5 Router: `backend/app/routers/parts_library.py`

Register in `main.py` with prefix `/api/v1/parts-library`, tags=`["parts-library"]`.

Implement every endpoint below with the exact signatures specified. Auth pattern follows existing codebase (`Depends(get_current_user)` for reads, `Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER))` for writes).

#### `GET /parts-library/`

```python
@router.get("/", response_model=list[LibraryPartSummary])
async def list_parts(
    part_type: Optional[PartType] = Query(None),
    status: Optional[PartStatus] = Query(None),
    material_class: Optional[MaterialClass] = Query(None),
    search: Optional[str] = Query(None, min_length=2, max_length=100),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    List all library parts. Filterable by part_type, status, material_class.
    `search` does a case-insensitive ILIKE on name, manufacturer_part_number,
    wardstone_part_number, and manufacturer_name.
    Default: returns only APPROVED parts unless status is explicitly specified.
    """
    query = db.query(LibraryPart)
    if status:
        query = query.filter(LibraryPart.status == status)
    else:
        # Default: approved only
        query = query.filter(LibraryPart.status == PartStatus.APPROVED)
    if part_type:
        query = query.filter(LibraryPart.part_type == part_type)
    if material_class:
        query = query.filter(LibraryPart.material_class == material_class)
    if search:
        ilike = f"%{search}%"
        query = query.filter(
            or_(
                LibraryPart.name.ilike(ilike),
                LibraryPart.manufacturer_part_number.ilike(ilike),
                LibraryPart.wardstone_part_number.ilike(ilike),
                LibraryPart.manufacturer_name.ilike(ilike),
            )
        )
    query = query.order_by(LibraryPart.created_at.desc())
    return query.offset(offset).limit(limit).all()
```

#### `POST /parts-library/`

```python
@router.post("/", response_model=LibraryPartResponse, status_code=201)
async def create_part(
    data: LibraryPartCreate,
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """
    Create a library part manually. WPN is assigned server-side.
    Status is set to DRAFT (requires explicit approval to become APPROVED).
    """
    wpn = assign_wpn(db, data.part_type)
    part = LibraryPart(
        **data.model_dump(exclude_none=True),
        wardstone_part_number=wpn,
        revision="00",
        status=PartStatus.DRAFT,
        created_by_id=current_user.id,
    )
    db.add(part)
    db.commit()
    db.refresh(part)
    await audit_service.log(
        db=db, actor=current_user,
        action="parts_library.part_created",
        entity_type="library_part", entity_id=part.id,
        after_state={"wpn": wpn, "name": part.name, "part_type": part.part_type.value},
    )
    return part
```

#### `PATCH /parts-library/{part_id}`

```python
@router.patch("/{part_id}", response_model=LibraryPartResponse)
async def update_part(
    part_id: int,
    data: LibraryPartUpdate,
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
    db: Session = Depends(get_db),
):
    """
    Update a library part.
    - DRAFT parts: update in place.
    - APPROVED parts that change dimensional fields:
      creates a new revision row; sets superseded_by_id on the old row.
      The old row status → SUPERSEDED.
    Dimensional fields: any of the Numeric measurement columns.
    """
    part = db.query(LibraryPart).filter(LibraryPart.id == part_id).first()
    if not part:
        raise HTTPException(404, "Library part not found")

    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    DIMENSIONAL_FIELDS = {
        "bounding_box_x_mm", "bounding_box_y_mm", "bounding_box_z_mm",
        "volume_mm3", "surface_area_mm2", "nominal_diameter_mm", "nominal_length_mm",
        "hole_pattern_dia_mm", "hole_pattern_pcd_mm", "hole_pattern_count",
        "thread_size", "torque_nominal_nm", "torque_min_nm", "torque_max_nm",
        "mass_nominal_g", "mass_max_g",
    }

    before_state = {k: str(getattr(part, k)) for k in update_data if hasattr(part, k)}

    if (part.status == PartStatus.APPROVED and
            any(f in update_data for f in DIMENSIONAL_FIELDS)):
        # Create new revision row
        new_wpn = bump_revision(part.wardstone_part_number)
        new_rev = part.wardstone_part_number.rsplit("-", 1)[1]
        new_rev_int = int(new_rev) + 1
        new_revision = f"{new_rev_int:02d}"
        new_part_data = {
            col.name: getattr(part, col.name)
            for col in LibraryPart.__table__.columns
            if col.name not in ("id", "wardstone_part_number", "revision",
                                 "approved_at", "approved_by_id",
                                 "created_at", "updated_at", "superseded_by_id")
        }
        new_part_data.update(update_data)
        new_part_data["wardstone_part_number"] = new_wpn
        new_part_data["revision"] = new_revision
        new_part_data["status"] = PartStatus.DRAFT  # new revision requires re-approval
        new_part_data["created_by_id"] = current_user.id

        new_part = LibraryPart(**new_part_data)
        db.add(new_part)
        db.flush()
        part.superseded_by_id = new_part.id
        part.status = PartStatus.SUPERSEDED
        db.commit()
        db.refresh(new_part)
        return new_part
    else:
        for k, v in update_data.items():
            setattr(part, k, v)
        db.commit()
        db.refresh(part)
        await audit_service.log(
            db=db, actor=current_user,
            action="parts_library.part_updated",
            entity_type="library_part", entity_id=part.id,
            before_state=before_state,
            after_state={k: str(getattr(part, k)) for k in update_data},
        )
        return part
```

#### `POST /parts-library/upload-step`

```python
@router.post("/upload-step", status_code=202)
async def upload_step_file(
    file: UploadFile = File(...),
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
    db: Session = Depends(get_db),
    background_tasks: BackgroundTasks = None,
):
    """
    Upload a STEP file. Validates extension and MIME.
    Computes SHA-256 — if a part already has this checksum, returns existing part.
    Enqueues background parser. Returns pending_import_id immediately.
    Max file size enforced by body_size_limit middleware (50 MB).
    """
    # Extension validation
    filename = file.filename or ""
    if not filename.lower().endswith(('.step', '.stp')):
        raise HTTPException(
            400, {"detail": "Only .step and .stp files are accepted",
                  "code": "INVALID_FILE_TYPE"}
        )

    # Read content and compute checksum
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, {"detail": "Empty file", "code": "EMPTY_FILE"})

    checksum = hashlib.sha256(content).hexdigest()

    # Duplicate check
    existing = (
        db.query(LibraryPart)
        .filter(LibraryPart.step_file_checksum == checksum)
        .first()
    )
    if existing:
        return {
            "duplicate": True,
            "existing_part_id": existing.id,
            "existing_wpn": existing.wardstone_part_number,
            "message": "This exact STEP file is already in the Parts Library.",
        }

    # Also check pending imports
    existing_pending = (
        db.query(PendingPartsImport)
        .join(Document, PendingPartsImport.document_id == Document.id)
        .filter(Document.sha256 == checksum)
        .filter(PendingPartsImport.status.in_(
            [PendingPartsStatus.PENDING, PendingPartsStatus.UNDER_REVIEW]
        ))
        .first()
    )
    if existing_pending:
        return {
            "duplicate": True,
            "pending_import_id": existing_pending.id,
            "message": "A parse is already pending for this file.",
        }

    # Save file to documents system
    # Use the existing document storage pattern from catalog.py
    file_path = _save_document_file(content, filename, checksum)
    document = Document(
        filename=filename,
        file_path=file_path,
        file_size_bytes=len(content),
        sha256=checksum,
        mime_type="application/step",
        document_type="step_cad",
        uploaded_by_id=current_user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    # Create pending import placeholder
    pending = PendingPartsImport(
        document_id=document.id,
        status=PendingPartsStatus.PENDING,
        proposed_data={},
        confidence_scores={},
        low_confidence_fields=[],
        created_by_id=current_user.id,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)

    # Enqueue background task
    background_tasks.add_task(
        _run_step_parser_pipeline,
        pending_import_id=pending.id,
        file_path=file_path,
        user_id=current_user.id,
    )

    return {
        "duplicate": False,
        "pending_import_id": pending.id,
        "message": "STEP file accepted. Parsing in progress.",
    }
```

#### `_run_step_parser_pipeline` (background task, same file)

```python
async def _run_step_parser_pipeline(
    pending_import_id: int,
    file_path: str,
    user_id: int,
) -> None:
    """
    Background task: parse STEP → AI interpret → update PendingPartsImport.
    Uses a fresh DB session (background tasks run outside the request session).
    """
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        pending = db.query(PendingPartsImport).get(pending_import_id)
        if not pending:
            return

        pending.status = PendingPartsStatus.UNDER_REVIEW
        db.commit()

        # Stage 1: geometry extraction
        parser_result = parse_step_file(file_path)

        # Stage 2: AI interpretation
        ai_service = get_ai_service()   # uses existing services/ai/ pattern
        ai_overrides = interpret(parser_result, ai_service)

        # Stage 3: merge into proposed_data
        proposed: dict = {}
        # Geometry fields from parser
        for f_name in [
            "product_name", "product_description", "manufacturer_part_number",
            "step_entity_id", "bounding_box_x_mm", "bounding_box_y_mm",
            "bounding_box_z_mm", "volume_mm3", "surface_area_mm2",
            "nominal_diameter_mm", "nominal_length_mm", "thread_size",
            "thread_standard", "torque_nominal_nm", "hole_pattern_count",
            "hole_pattern_dia_mm", "mass_nominal_g",
        ]:
            val = getattr(parser_result, f_name, None)
            if val is not None:
                proposed[f_name] = str(val) if hasattr(val, '__float__') else val

        # Rename product_name → name in proposed_data
        if "product_name" in proposed:
            proposed["name"] = proposed.pop("product_name")
        if "product_description" in proposed:
            proposed["description"] = proposed.pop("product_description")

        # AI overrides
        for key in ["part_type", "material_name", "material_class",
                    "torque_nominal_nm", "torque_min_nm", "torque_max_nm",
                    "locking_feature"]:
            if ai_overrides.get(key) is not None:
                proposed[key] = ai_overrides[key]

        # Merge confidence scores
        confidence_scores = {**parser_result.confidence_scores}
        for field_name, level in ai_overrides.get("confidence_overrides", {}).items():
            confidence_scores[field_name] = level

        low_confidence = list(set(
            parser_result.low_confidence_fields +
            [k for k, v in confidence_scores.items() if v == "low"]
        ))

        pending.proposed_data = proposed
        pending.confidence_scores = confidence_scores
        pending.low_confidence_fields = low_confidence
        pending.extraction_log = (
            parser_result.extraction_log +
            "\n\nAI flags: " + "; ".join(ai_overrides.get("flags", []))
        )
        pending.parser_version = parser_result.parser_version
        db.commit()

    except Exception as exc:
        import traceback
        if pending:
            pending.status = PendingPartsStatus.PENDING  # allow retry
            pending.extraction_log = traceback.format_exc()
            db.commit()
        logger.error("STEP parser pipeline failed for import %d: %s",
                     pending_import_id, exc)
    finally:
        db.close()
```

#### `POST /parts-library/pending-imports/{id}/approve`

```python
@router.post("/pending-imports/{import_id}/approve",
             response_model=LibraryPartResponse)
async def approve_import(
    import_id: int,
    data: PendingPartsImportApprove,
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
    db: Session = Depends(get_db),
):
    """
    Approve a pending parts import.
    Merges proposed_data with overrides, assigns WPN, creates LibraryPart.
    If supplier_id provided in body, creates CatalogPart link.
    Emits audit event. Idempotent — returns existing part if already approved.
    """
    pending = db.query(PendingPartsImport).get(import_id)
    if not pending:
        raise HTTPException(404, "Pending import not found")
    if pending.status == PendingPartsStatus.APPROVED and pending.library_part_id:
        # Idempotent — return the already-created part
        return db.query(LibraryPart).get(pending.library_part_id)
    if pending.status not in (PendingPartsStatus.PENDING,
                               PendingPartsStatus.UNDER_REVIEW):
        raise HTTPException(
            409,
            {"detail": f"Import is {pending.status.value} and cannot be approved",
             "code": "WRONG_STATE"}
        )

    # Merge proposed_data + overrides
    merged = {**pending.proposed_data, **data.overrides}

    # Validate required fields
    if not merged.get("name"):
        raise HTTPException(
            422,
            {"detail": "Field 'name' is required before approval",
             "code": "MISSING_REQUIRED_FIELD"}
        )
    if not merged.get("part_type"):
        raise HTTPException(
            422,
            {"detail": "Field 'part_type' is required before approval",
             "code": "MISSING_REQUIRED_FIELD"}
        )

    # Assign WPN inside transaction
    part_type = PartType(merged["part_type"])
    wpn = assign_wpn(db, part_type)

    # Coerce Decimal fields — JSON stores them as strings
    NUMERIC_FIELDS = [
        "bounding_box_x_mm", "bounding_box_y_mm", "bounding_box_z_mm",
        "volume_mm3", "surface_area_mm2", "nominal_diameter_mm",
        "nominal_length_mm", "torque_nominal_nm", "torque_min_nm",
        "torque_max_nm", "mass_nominal_g", "mass_max_g",
        "hole_pattern_dia_mm", "hole_pattern_pcd_mm",
    ]
    for f_name in NUMERIC_FIELDS:
        if f_name in merged and merged[f_name] is not None:
            try:
                merged[f_name] = Decimal(str(merged[f_name]))
            except Exception:
                merged.pop(f_name)

    # Filter to only valid LibraryPart columns
    valid_columns = {c.name for c in LibraryPart.__table__.columns}
    safe_data = {k: v for k, v in merged.items() if k in valid_columns}

    # Never allow these to be set from user-supplied data
    for protected in ("id", "wardstone_part_number", "revision", "status",
                       "approved_by_id", "approved_at", "created_at",
                       "updated_at", "created_by_id"):
        safe_data.pop(protected, None)

    # Get step file info from document
    doc = db.query(Document).get(pending.document_id)

    part = LibraryPart(
        **safe_data,
        wardstone_part_number=wpn,
        revision="00",
        status=PartStatus.APPROVED,
        step_file_id=pending.document_id,
        step_file_checksum=doc.sha256 if doc else None,
        step_entity_id=merged.get("step_entity_id"),
        approved_by_id=current_user.id,
        approved_at=func.now(),
        created_by_id=current_user.id,
    )
    db.add(part)
    db.flush()

    # Link back to pending import
    pending.status = PendingPartsStatus.APPROVED
    pending.library_part_id = part.id
    pending.reviewed_by_id = current_user.id
    pending.reviewed_at = func.now()

    # Optional: create CatalogPart link
    if data.supplier_id:
        catalog_part = CatalogPart(
            supplier_id=data.supplier_id,
            part_number=part.manufacturer_part_number or wpn,
            name=part.name,
            library_part_id=part.id,
            created_by_id=current_user.id,
        )
        db.add(catalog_part)

    db.commit()
    db.refresh(part)

    await audit_service.log(
        db=db, actor=current_user,
        action="parts_library.import_approved",
        entity_type="library_part", entity_id=part.id,
        after_state={"wpn": wpn, "name": part.name,
                     "part_type": part.part_type.value},
    )
    return part
```

---

### 4.6 Router: `backend/app/routers/project_parts.py`

Register at `/api/v1/projects/{project_id}/parts`. All endpoints `Depends(project_member_required)`.

Full endpoint signatures:

```
GET  /                  list_project_parts(project_id, limit, offset, db, user)
     → list[ProjectPartResponse]
     selectinload(ProjectPart.library_part) — no N+1
     Also resolves system_id from SystemPartAssignment for each part.

POST /                  add_part_to_project(project_id, data: ProjectPartCreate, db, user)
     → ProjectPartResponse, 201
     Validates library_part_id exists and is APPROVED.
     Raises 409 if part already in project (unique constraint).
     Audit: parts_library.project_part_added

DELETE /{project_part_id}  remove_part_from_project(project_id, project_part_id, db, user)
     → 204 No Content
     Validates ownership: project_part.project_id == project_id.
     Raises 409 if part has active MechanicalJoint references (use force=true to override).
     Audit: parts_library.project_part_removed

PATCH /{project_part_id}   update_project_part(project_id, project_part_id, data: ProjectPartUpdate)
     → ProjectPartResponse
     Only quantity, designation, notes are updatable.
     No audit needed for non-critical field changes.

GET  /unassigned           list_unassigned_parts(project_id, db, user)
     → list[ProjectPartResponse]
     Parts in this project with no SystemPartAssignment record.
```

---

### 4.7 Router: `backend/app/routers/mechanical_joints.py`

Register at `/api/v1/projects/{project_id}/mechanical-joints`. All endpoints `Depends(project_member_required)`.

```
GET  /                    list_joints(project_id, joint_type, status, confidence, part_id, limit, offset)
     → list[MechanicalJointResponse]
     selectinload(MechanicalJoint.part_a, MechanicalJoint.part_b,
                  MechanicalJoint.fastener_part, MechanicalJoint.seal_part)
     No N+1.

POST /                    create_joint(project_id, data: MechanicalJointCreate)
     → MechanicalJointResponse, 201
     Assigns joint_id: MJ-{project_id:04d}-{seq:06d} using MechanicalJointSequence with SELECT FOR UPDATE.
     Validates: part_a_id and part_b_id both belong to this project.
     Validates: if fastener_part_id set, that part is APPROVED and part_type == FASTENER.
     Validates: if seal_part_id set, that part is APPROVED and part_type == SEAL.
     Status = DRAFT on creation.
     Audit: mechanical_joints.joint_created

GET  /{joint_id}          get_joint(project_id, joint_id)
     → MechanicalJointResponse
     Validates: joint.project_id == project_id (ownership check).

PATCH /{joint_id}         update_joint(project_id, joint_id, data: MechanicalJointUpdate)
     → MechanicalJointResponse
     Validates: joint.status != SUPERSEDED (cannot update superseded joints).
     Before/after audit for all field changes.

DELETE /{joint_id}         delete_joint(project_id, joint_id, force: bool = False)
     → 204 No Content
     DRAFT joints can be deleted freely.
     ACTIVE joints: requires force=true (admin only for ACTIVE deletion).
     Sets joint.status = SUPERSEDED (soft delete) rather than hard delete if ACTIVE.
     Audit: mechanical_joints.joint_deleted

POST /{joint_id}/approve  approve_joint(project_id, joint_id)
     → MechanicalJointResponse
     Sets status = ACTIVE.
     Creates RequirementSourceLink records for each applicable template
       (from JOINT_TYPE_TEMPLATES[joint.joint_type]).
     Fires req_sync listener via explicit after_update flush.
     Generates auto-requirements by calling the mechanical req template renderer.
     Audit: mechanical_joints.joint_approved

POST /upload-assembly     upload_assembly(project_id, file: UploadFile)
     → {job_id: int, status: "queued"}
     Max size: 100 MB. Extension: .step or .stp.
     Creates Document record + AssemblyParseJob record.
     Enqueues background task: _run_assembly_parser(job_id).

GET  /assembly-parse-status/{job_id}  get_parse_status(project_id, job_id)
     → AssemblyParseJobResponse
     Returns job status, progress_log, partial result if available.
```

---

### 4.8 `approve_joint` — full implementation

The approve endpoint is the most complex — it wires mechanical joints into the existing req_sync engine:

```python
@router.post("/{joint_id}/approve", response_model=MechanicalJointResponse)
async def approve_joint(
    project_id: int,
    joint_id: str,
    current_user: User = Depends(project_member_required),
    db: Session = Depends(get_db),
):
    joint = (
        db.query(MechanicalJoint)
        .filter(
            MechanicalJoint.joint_id == joint_id,
            MechanicalJoint.project_id == project_id,
        )
        .first()
    )
    if not joint:
        raise HTTPException(404, "Joint not found")
    if joint.status != JointStatus.DRAFT:
        raise HTTPException(
            409,
            {"detail": f"Joint is already {joint.status.value}",
             "code": "WRONG_STATE"}
        )

    # Resolve full part data for template rendering
    part_a_pp = db.query(ProjectPart).get(joint.part_a_id)
    part_b_pp = db.query(ProjectPart).get(joint.part_b_id)
    part_a_lp = db.query(LibraryPart).get(part_a_pp.library_part_id) if part_a_pp else None
    part_b_lp = db.query(LibraryPart).get(part_b_pp.library_part_id) if part_b_pp else None
    fastener_lp = db.query(LibraryPart).get(joint.fastener_part_id) if joint.fastener_part_id else None
    seal_lp = db.query(LibraryPart).get(joint.seal_part_id) if joint.seal_part_id else None

    # Build template context
    context = build_template_context(joint, part_a_lp, part_b_lp, fastener_lp, seal_lp)

    # Get applicable templates for this joint type
    template_ids = JOINT_TYPE_TEMPLATES.get(joint.joint_type, [])

    # Create auto-requirements + RequirementSourceLinks
    for template_id in template_ids:
        statement = render_template(template_id, context)
        if not statement:
            continue

        # Create the Requirement record
        req = Requirement(
            project_id=project_id,
            req_id=next_human_id(db, project_id, prefix="MECH",
                                  source_model=Requirement, id_field="req_id"),
            title=f"Mechanical Interface: {joint.joint_id} — {template_id}",
            statement=statement,
            status="auto_generated",
            req_type="interface",
            level=3,
            generation_template_id=template_id,
            created_by_id=current_user.id,
        )
        db.add(req)
        db.flush()

        # Create RequirementSourceLink (wires into reactive sync engine)
        source_link = RequirementSourceLink(
            requirement_id=req.id,
            source_entity_type=SourceEntityType.MECHANICAL_JOINT,
            source_entity_id=joint.id,
            project_id=project_id,
            generation_template_id=template_id,
        )
        db.add(source_link)

    # Approve the joint
    joint.status = JointStatus.ACTIVE
    db.commit()
    db.refresh(joint)

    await audit_service.log(
        db=db, actor=current_user,
        action="mechanical_joints.joint_approved",
        entity_type="mechanical_joint", entity_id=joint.id,
        after_state={
            "joint_id": joint.joint_id,
            "joint_type": joint.joint_type.value,
            "templates_applied": template_ids,
            "requirements_generated": len(template_ids),
        },
    )
    return joint
```

---

### 4.9 req_sync listener additions

In `backend/app/services/req_sync/listener.py`, add after the existing listeners:

```python
from app.models.parts_library import MechanicalJoint, JointStatus
from sqlalchemy import event

@event.listens_for(MechanicalJoint, "after_update")
def _mj_after_update(mapper, connection, target):
    """
    Fires whenever a MechanicalJoint row is updated.
    Fans out to RequirementSourceLinks sourced from this joint.
    Re-entrancy guard: same contextvar depth cap (=1) as existing listeners.
    """
    if _get_listener_depth() >= 1:
        return
    if target.status != JointStatus.ACTIVE:
        return
    _increment_depth()
    try:
        from app.services.req_sync.fan_out import fan_out_to_source_links
        # Use connection (not a new session) to stay in same transaction
        fan_out_to_source_links(
            connection=connection,
            source_entity_type="mechanical_joint",
            source_entity_id=target.id,
        )
    finally:
        _decrement_depth()

@event.listens_for(MechanicalJoint, "after_delete")
def _mj_after_delete(mapper, connection, target):
    """Mark all requirements sourced from this joint as needing review."""
    if _get_listener_depth() >= 1:
        return
    _increment_depth()
    try:
        from app.services.req_sync.fan_out import mark_source_deleted
        mark_source_deleted(
            connection=connection,
            source_entity_type="mechanical_joint",
            source_entity_id=target.id,
        )
    finally:
        _decrement_depth()
```

Register these listeners in `main.py` app startup event, same as the existing listeners.

---

### 4.10 Tests

#### `backend/tests/test_parts_library.py`

Write the following test cases. Each is a standalone function using pytest fixtures. Follow the exact pattern of existing test files in the codebase.

```
test_wpn_assignment_unique_sequential
  Create 5 parts of type FASTENER sequentially.
  Assert WPNs are WS-FAST-000001-00 through WS-FAST-000005-00.

test_wpn_assignment_race_condition
  Use threading.Thread to fire two simultaneous approve_import calls
  for two pending imports with part_type=FASTENER.
  Assert both succeed (201) and return distinct WPNs.
  Assert no WPN appears twice in the database.

test_create_part_manually_assigns_wpn
  POST /parts-library/ with valid LibraryPartCreate (WASHER type).
  Assert 201, wardstone_part_number starts with "WS-WASH-", status == "draft".

test_approved_part_requires_pm_or_admin
  POST /parts-library/ as a DEVELOPER role user.
  Assert 403.

test_upload_step_creates_pending_import
  POST /parts-library/upload-step with a valid minimal STEP file
  (fixture: a 1mm cube STEP file).
  Assert 202, response contains pending_import_id.
  Assert PendingPartsImport record exists in DB with status=pending or under_review.

test_upload_step_duplicate_checksum_returns_existing
  Upload the same STEP file twice.
  First upload: 202, duplicate=False.
  Second upload: 200, duplicate=True, existing_part_id or pending_import_id present.

test_upload_non_step_file_rejected
  POST /parts-library/upload-step with a .pdf file.
  Assert 400, code=INVALID_FILE_TYPE.

test_approve_import_creates_part_with_wpn
  Create PendingPartsImport fixture with proposed_data={name:"Test Bolt", part_type:"fastener"}.
  POST /parts-library/pending-imports/{id}/approve.
  Assert 200, wardstone_part_number is set, status=approved, approved_by_id set.
  Assert PendingPartsImport.status == "approved" in DB.

test_approve_import_with_overrides
  Approve with overrides={"name": "Override Name", "torque_nominal_nm": "12.5"}.
  Assert returned part has name="Override Name" and torque_nominal_nm=Decimal("12.5").

test_approve_import_creates_catalog_part_when_supplier_given
  Approve with supplier_id=1 (Mason's seed supplier).
  Assert CatalogPart record created with library_part_id set.

test_reject_import
  POST /parts-library/pending-imports/{id}/reject with reason="Test rejection".
  Assert PendingPartsImport.status == "rejected", rejection_reason set.

test_update_draft_part_in_place
  Create draft part. PATCH name to "Updated Name".
  Assert same row updated (same id), no new row created.

test_update_approved_part_dimensional_creates_revision
  Create approved part with torque_nominal_nm=9.8.
  PATCH torque_nominal_nm=10.5.
  Assert: new part created with WPN ending in "-01", status=draft.
  Assert: original part status=superseded, superseded_by_id=new_part.id.

test_list_parts_default_approved_only
  DB has 3 APPROVED + 1 DRAFT + 1 SUPERSEDED parts.
  GET /parts-library/ with no filters.
  Assert only 3 parts returned (the APPROVED ones).

test_list_parts_filter_by_type
  GET /parts-library/?part_type=fastener&status=approved.
  Assert only fasteners returned.

test_search_by_mpn
  GET /parts-library/?search=DG2002.
  Assert part with matching manufacturer_part_number returned.

test_step_parser_stub_returns_metadata_only
  If pythonOCC not installed: call parse_step_file() on test fixture.
  Assert occ_available=False, all geometry fields None.
  Assert product_name extracted from STEP metadata.

test_thread_table_m6_match
  Call match_thread(Decimal("6.55")).
  Assert returns ("M6×1.0", ThreadStandard.ISO_METRIC, Decimal("9.8")).

test_thread_table_no_match
  Call match_thread(Decimal("99.0")).
  Assert returns None.

test_ai_fallback_classifies_screw
  Call _rules_fallback with product_name="M6 Socket Head Cap Screw".
  Assert part_type="fastener", material_class="stainless_steel".

test_ai_fallback_nylok_detection
  Call _rules_fallback with product_name="M4 Nylok Screw".
  Assert locking_feature="nylok".
```

#### `backend/tests/test_project_parts.py`

```
test_add_part_to_project_creates_join_record
  POST /projects/1/parts/ with library_part_id of an APPROVED part.
  Assert 201, ProjectPart record created, library_part data NOT duplicated.

test_add_draft_part_to_project_rejected
  POST /projects/1/parts/ with library_part_id of a DRAFT part.
  Assert 422, code=PART_NOT_APPROVED.

test_duplicate_add_rejected
  Add part twice to same project.
  Assert second add returns 409.

test_non_member_cannot_add_part
  Authenticate as dev_test_user (member of no projects).
  POST /projects/1/parts/.
  Assert 403.

test_remove_part_does_not_delete_library_record
  Add part. Remove it. Assert LibraryPart still exists.

test_remove_part_with_active_joint_rejected
  Add part. Create + approve MechanicalJoint using this part.
  DELETE /projects/1/parts/{project_part_id}.
  Assert 409. With force=true: 204.

test_list_unassigned_parts
  Add 3 parts to project. Assign 2 to a system.
  GET /projects/1/parts/unassigned.
  Assert 1 part returned.
```

#### `backend/tests/test_mechanical_joints.py`

```
test_joint_id_format
  Create joint. Assert joint_id matches "MJ-0001-000001".

test_joint_id_race_condition
  Two concurrent joint creates for same project.
  Assert distinct joint_ids.

test_create_joint_validates_part_ownership
  Create joint with part_a_id from project 2 while authenticated to project 1.
  Assert 422, code=PART_NOT_IN_PROJECT.

test_fastener_type_validation
  Create BOLTED joint with fastener_part_id pointing to a WASHER part.
  Assert 422, code=INVALID_FASTENER_TYPE.

test_approve_joint_generates_requirements
  Create + approve a BOLTED joint with fastener, torque, count set.
  Assert Requirement records created in DB.
  Assert MECH-BOLT-001 requirement contains joint's torque value in statement.
  Assert RequirementSourceLink records created with source_entity_type=MECHANICAL_JOINT.

test_approve_joint_fires_sync_on_subsequent_update
  Approve joint. Then update torque_nominal_nm.
  Assert RequirementSyncProposal records created for sourced requirements.

test_delete_draft_joint
  Create joint (status=DRAFT). DELETE it.
  Assert 204, joint gone from DB.

test_delete_active_joint_without_force_rejected
  Approve joint (status=ACTIVE). DELETE without force.
  Assert 409.

test_delete_active_joint_with_force_soft_deletes
  Approve joint. DELETE with force=true (admin user).
  Assert joint.status == "superseded" (not hard deleted).

test_non_member_cannot_create_joint
  dev_test_user POST to /projects/1/mechanical-joints/.
  Assert 403.

test_render_template_mech_bolt_001
  Build context dict. Call render_template("MECH-BOLT-001", context).
  Assert rendered statement contains "4×", the fastener name, and torque value.
  Assert no "{" or "}" in rendered string (no unresolved tokens).

test_render_template_missing_context_falls_back_to_tbd
  Call render_template with empty context.
  Assert rendered string contains "TBD" for missing fields.
  Assert no KeyError raised.
```

---

### 4.11 Phase 2 verification gate

```bash
docker exec astra-backend-1 pytest tests/test_parts_library.py tests/test_project_parts.py tests/test_mechanical_joints.py -v
docker exec astra-backend-1 pytest tests/ -q -m "not performance"
# Zero regressions from TESTS_BEFORE
docker exec astra-backend-1 python -c "
from app.main import app
paths = [r.path for r in app.routes if 'parts' in r.path]
print(f'{len(paths)} parts routes registered')
print('\n'.join(sorted(paths)))
"
# Should show >= 15 routes
```

Commit: `feat(parts): phase-2-complete — services, routers, tests (+N tests)`

---

## 5. Phase 3 — Frontend

---

### 5.1 TypeScript interfaces: `frontend/src/types/parts-library.ts`

```typescript
import { Decimal } from 'decimal.js';  // or use string for Decimal backend fields

export type PartType =
  | 'fastener' | 'washer' | 'insert' | 'bracket' | 'enclosure'
  | 'seal' | 'bearing' | 'hinge_latch' | 'thermal_interface'
  | 'pcb_mechanical' | 'custom';

export type PartStatus =
  | 'draft' | 'under_review' | 'approved' | 'superseded' | 'obsolete';

export type MaterialClass =
  | 'aluminum' | 'titanium' | 'steel' | 'stainless_steel' | 'nickel_alloy'
  | 'polymer' | 'composite' | 'ceramic' | 'other';

export type JointType =
  | 'bolted' | 'riveted' | 'press_fit' | 'adhesive' | 'weld'
  | 'seal' | 'alignment_pin' | 'thermal_bond' | 'spring_clip';

export type JointStatus = 'draft' | 'active' | 'superseded';
export type ConfidenceLevel = 'high' | 'medium' | 'low';

// All Numeric fields from backend arrive as string (JSON serialization of Decimal)
export interface LibraryPartSummary {
  id: number;
  wardstone_part_number: string;  // "WS-FAST-000042-00"
  revision: string;
  part_type: PartType;
  name: string;
  status: PartStatus;
  manufacturer_name: string | null;
  manufacturer_part_number: string | null;
  material_name: string | null;
  material_class: MaterialClass | null;
  mass_nominal_g: string | null;
  approved_at: string | null;
}

export interface LibraryPartResponse extends LibraryPartSummary {
  description: string | null;
  cage_code: string | null;
  nsn: string | null;
  drawing_number: string | null;
  drawing_revision: string | null;
  heritage: string | null;
  // Dimensional
  bounding_box_x_mm: string | null;
  bounding_box_y_mm: string | null;
  bounding_box_z_mm: string | null;
  volume_mm3: string | null;
  surface_area_mm2: string | null;
  thread_size: string | null;
  thread_standard: string | null;
  nominal_diameter_mm: string | null;
  nominal_length_mm: string | null;
  head_type: string | null;
  drive_type: string | null;
  nominal_bore_mm: string | null;
  cross_section_dia_mm: string | null;
  flange_diameter_mm: string | null;
  hole_pattern_count: number | null;
  hole_pattern_dia_mm: string | null;
  hole_pattern_pcd_mm: string | null;
  // Material
  material_standard: string | null;
  density_g_cm3: string | null;
  yield_strength_mpa: string | null;
  ultimate_strength_mpa: string | null;
  elastic_modulus_gpa: string | null;
  hardness: string | null;
  thermal_conductivity_wm: string | null;
  cte_um_m_c: string | null;
  corrosion_protection: string | null;
  flammability_class: string | null;
  outgassing_tml_pct: string | null;
  outgassing_cvcm_pct: string | null;
  // Performance
  mass_max_g: string | null;
  proof_load_n: string | null;
  clamp_load_n: string | null;
  torque_nominal_nm: string | null;
  torque_min_nm: string | null;
  torque_max_nm: string | null;
  torque_lubricated_nm: string | null;
  locking_feature: string | null;
  safety_wire_holes: boolean | null;
  shear_strength_n: string | null;
  bearing_load_n: string | null;
  compression_set_pct: string | null;
  sealing_pressure_max_bar: string | null;
  temperature_min_c: string | null;
  temperature_max_c: string | null;
  // Procurement
  unit_cost_usd: string | null;
  lead_time_weeks: number | null;
  min_order_qty: number | null;
  preferred_supplier_id: number | null;
  supplier_part_number: string | null;
  qualification_status: string | null;
  qualification_basis: string | null;
  shelf_life_months: number | null;
  restricted_use: boolean;
  restriction_notes: string | null;
  step_file_checksum: string | null;
  created_at: string;
  updated_at: string;
  created_by_id: number | null;
  superseded_by_id: number | null;
}

export interface LibraryPartCreate {
  part_type: PartType;
  name: string;
  description?: string;
  manufacturer_part_number?: string;
  manufacturer_name?: string;
  cage_code?: string;
  nsn?: string;
  drawing_number?: string;
  drawing_revision?: string;
  heritage?: string;
  // All optional measurement fields — send as string to preserve precision
  bounding_box_x_mm?: string;
  bounding_box_y_mm?: string;
  bounding_box_z_mm?: string;
  thread_size?: string;
  thread_standard?: string;
  nominal_diameter_mm?: string;
  nominal_length_mm?: string;
  head_type?: string;
  drive_type?: string;
  hole_pattern_count?: number;
  hole_pattern_dia_mm?: string;
  hole_pattern_pcd_mm?: string;
  material_name?: string;
  material_standard?: string;
  material_class?: MaterialClass;
  density_g_cm3?: string;
  yield_strength_mpa?: string;
  ultimate_strength_mpa?: string;
  elastic_modulus_gpa?: string;
  hardness?: string;
  thermal_conductivity_wm?: string;
  cte_um_m_c?: string;
  corrosion_protection?: string;
  flammability_class?: string;
  outgassing_tml_pct?: string;
  outgassing_cvcm_pct?: string;
  mass_nominal_g?: string;
  mass_max_g?: string;
  torque_nominal_nm?: string;
  torque_min_nm?: string;
  torque_max_nm?: string;
  torque_lubricated_nm?: string;
  locking_feature?: string;
  safety_wire_holes?: boolean;
  shear_strength_n?: string;
  bearing_load_n?: string;
  compression_set_pct?: string;
  sealing_pressure_max_bar?: string;
  temperature_min_c?: string;
  temperature_max_c?: string;
  unit_cost_usd?: string;
  lead_time_weeks?: number;
  min_order_qty?: number;
  preferred_supplier_id?: number;
  supplier_part_number?: string;
  qualification_status?: string;
  qualification_basis?: string;
  shelf_life_months?: number;
  restricted_use?: boolean;
  restriction_notes?: string;
}

export interface ProjectPartResponse {
  id: number;
  project_id: number;
  library_part_id: number;
  quantity: number;
  designation: string | null;
  notes: string | null;
  added_at: string;
  library_part: LibraryPartSummary;
  system_id: number | null;
}

export interface ProjectPartCreate {
  library_part_id: number;
  quantity?: number;
  designation?: string;
  notes?: string;
}

export interface SystemPartAssignmentCreate {
  project_part_id: number;
  position_order?: number;
}

export interface SystemPartAssignmentResponse {
  id: number;
  system_id: number;
  project_part_id: number;
  position_order: number;
  assigned_at: string;
  project_part: ProjectPartResponse;
}

export interface MechanicalJointCreate {
  joint_type: JointType;
  part_a_id: number;
  part_b_id: number;
  fastener_part_id?: number;
  fastener_count?: number;
  torque_nominal_nm?: string;
  torque_min_nm?: string;
  torque_max_nm?: string;
  engagement_length_mm?: string;
  locking_feature?: string;
  hole_pattern_description?: string;
  mating_surface_flatness_mm?: string;
  mating_surface_finish_ra?: string;
  seal_part_id?: number;
  leak_rate_max_scc_s?: string;
  test_pressure_bar?: string;
  interface_drawing?: string;
  notes?: string;
}

export interface MechanicalJointResponse extends MechanicalJointCreate {
  id: number;
  joint_id: string;
  project_id: number;
  status: JointStatus;
  confidence: ConfidenceLevel | null;
  source_step_file_id: number | null;
  created_at: string;
  updated_at: string;
  fastener_part: LibraryPartSummary | null;
  seal_part: LibraryPartSummary | null;
}

export interface PendingPartsImportResponse {
  id: number;
  document_id: number;
  status: string;
  proposed_data: Record<string, unknown>;
  confidence_scores: Record<string, ConfidenceLevel>;
  low_confidence_fields: string[];
  extraction_log: string | null;
  parser_version: string | null;
  library_part_id: number | null;
  created_at: string;
}

export interface AssemblyParseJobResponse {
  id: number;
  project_id: number;
  status: 'queued' | 'running' | 'complete' | 'failed';
  progress_log: string | null;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: string;
  completed_at: string | null;
}
```

---

### 5.2 API client additions: append to `frontend/src/lib/api.ts`

```typescript
// ── Parts Library (global, no project scope) ─────────────────────────────────

export const partsLibraryAPI = {
  list: (params?: {
    part_type?: string;
    status?: string;
    material_class?: string;
    search?: string;
    limit?: number;
    offset?: number;
  }) =>
    axios.get<LibraryPartSummary[]>('/parts-library/', { params }),

  get: (id: number) =>
    axios.get<LibraryPartResponse>(`/parts-library/${id}`),

  create: (data: LibraryPartCreate) =>
    axios.post<LibraryPartResponse>('/parts-library/', data),

  update: (id: number, data: Partial<LibraryPartCreate>) =>
    axios.patch<LibraryPartResponse>(`/parts-library/${id}`, data),

  search: (q: string) =>
    axios.get<LibraryPartSummary[]>('/parts-library/', { params: { search: q } }),

  uploadStep: (file: File, onProgress?: (pct: number) => void) => {
    const form = new FormData();
    form.append('file', file);
    return axios.post<{
      duplicate: boolean;
      pending_import_id?: number;
      existing_part_id?: number;
      existing_wpn?: string;
      message: string;
    }>('/parts-library/upload-step', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      onUploadProgress: (e) => {
        if (onProgress && e.total) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      },
    });
  },

  getPendingImports: () =>
    axios.get<PendingPartsImportResponse[]>('/parts-library/pending-imports/'),

  getPendingImport: (id: number) =>
    axios.get<PendingPartsImportResponse>(`/parts-library/pending-imports/${id}`),

  approveImport: (id: number, overrides: Record<string, unknown> = {},
                  supplier_id?: number) =>
    axios.post<LibraryPartResponse>(
      `/parts-library/pending-imports/${id}/approve`,
      { overrides, supplier_id }
    ),

  rejectImport: (id: number, reason: string) =>
    axios.post(`/parts-library/pending-imports/${id}/reject`, { reason }),
};

// ── Project Parts ─────────────────────────────────────────────────────────────

export const projectPartsAPI = {
  list: (projectId: number, params?: { limit?: number; offset?: number }) =>
    axios.get<ProjectPartResponse[]>(`/projects/${projectId}/parts/`, { params }),

  add: (projectId: number, data: ProjectPartCreate) =>
    axios.post<ProjectPartResponse>(`/projects/${projectId}/parts/`, data),

  update: (projectId: number, id: number,
           data: { quantity?: number; designation?: string; notes?: string }) =>
    axios.patch<ProjectPartResponse>(`/projects/${projectId}/parts/${id}`, data),

  remove: (projectId: number, id: number, force = false) =>
    axios.delete(`/projects/${projectId}/parts/${id}`, { params: { force } }),

  listUnassigned: (projectId: number) =>
    axios.get<ProjectPartResponse[]>(`/projects/${projectId}/parts/unassigned`),
};

// ── System Part Assignments ───────────────────────────────────────────────────

export const systemPartsAPI = {
  list: (projectId: number, systemId: number) =>
    axios.get<SystemPartAssignmentResponse[]>(
      `/projects/${projectId}/systems/${systemId}/parts/`
    ),
  assign: (projectId: number, systemId: number,
           data: SystemPartAssignmentCreate) =>
    axios.post<SystemPartAssignmentResponse>(
      `/projects/${projectId}/systems/${systemId}/parts/`, data
    ),
  remove: (projectId: number, systemId: number, assignmentId: number) =>
    axios.delete(
      `/projects/${projectId}/systems/${systemId}/parts/${assignmentId}`
    ),
  reorder: (projectId: number, systemId: number, assignmentId: number,
            position_order: number) =>
    axios.patch(
      `/projects/${projectId}/systems/${systemId}/parts/${assignmentId}`,
      { position_order }
    ),
};

// ── Mechanical Joints ─────────────────────────────────────────────────────────

export const mechanicalJointsAPI = {
  list: (projectId: number, params?: {
    joint_type?: string;
    status?: string;
    confidence?: string;
    part_id?: number;
    limit?: number;
    offset?: number;
  }) =>
    axios.get<MechanicalJointResponse[]>(
      `/projects/${projectId}/mechanical-joints/`, { params }
    ),

  get: (projectId: number, jointId: string) =>
    axios.get<MechanicalJointResponse>(
      `/projects/${projectId}/mechanical-joints/${jointId}`
    ),

  create: (projectId: number, data: MechanicalJointCreate) =>
    axios.post<MechanicalJointResponse>(
      `/projects/${projectId}/mechanical-joints/`, data
    ),

  update: (projectId: number, jointId: string,
           data: Partial<MechanicalJointCreate>) =>
    axios.patch<MechanicalJointResponse>(
      `/projects/${projectId}/mechanical-joints/${jointId}`, data
    ),

  approve: (projectId: number, jointId: string) =>
    axios.post<MechanicalJointResponse>(
      `/projects/${projectId}/mechanical-joints/${jointId}/approve`
    ),

  delete: (projectId: number, jointId: string, force = false) =>
    axios.delete(
      `/projects/${projectId}/mechanical-joints/${jointId}`,
      { params: { force } }
    ),

  uploadAssembly: (projectId: number, file: File,
                   onProgress?: (pct: number) => void) => {
    const form = new FormData();
    form.append('file', file);
    return axios.post<{ job_id: number; status: string }>(
      `/projects/${projectId}/mechanical-joints/upload-assembly`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
        onUploadProgress: (e) => {
          if (onProgress && e.total) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        },
      }
    );
  },

  getParseStatus: (projectId: number, jobId: number) =>
    axios.get<AssemblyParseJobResponse>(
      `/projects/${projectId}/mechanical-joints/assembly-parse-status/${jobId}`
    ),
};
```

---

### 5.3 Parts Library pages

#### Global nav addition in `Sidebar.tsx`

Find the Catalog nav entry. Immediately AFTER it (not replacing it), add:

```tsx
<NavItem
  href="/parts-library"
  icon={<WrenchScrewdriverIcon className="w-5 h-5" />}
  label="Parts Library"
  isActive={pathname.startsWith('/parts-library')}
/>
```

Use whatever icon component the codebase uses (check existing nav items for the pattern — `HeroIcons` or `lucide-react`). If `WrenchScrewdriverIcon` is not available, use `CogIcon` or `SettingsIcon`.

#### `frontend/src/app/(parts-library)/parts-library/page.tsx`

State:
```tsx
const [parts, setParts] = useState<LibraryPartSummary[]>([]);
const [loading, setLoading] = useState(true);
const [error, setError] = useState<string | null>(null);
const [filters, setFilters] = useState<{
  part_type?: PartType;
  status?: PartStatus;
  material_class?: MaterialClass;
  search: string;
}>({ search: '' });
const [uploadModalOpen, setUploadModalOpen] = useState(false);
const debouncedSearch = useDebounce(filters.search, 300);
```

Effects:
```tsx
useEffect(() => {
  setLoading(true);
  partsLibraryAPI.list({
    part_type: filters.part_type,
    status: filters.status,
    material_class: filters.material_class,
    search: debouncedSearch || undefined,
  })
    .then(res => { setParts(res.data); setError(null); })
    .catch(err => setError(err.response?.data?.detail || 'Failed to load parts'))
    .finally(() => setLoading(false));
}, [filters.part_type, filters.status, filters.material_class, debouncedSearch]);
```

Layout:
- Page header: "Parts Library" h1, subtitle "Global cross-project parts database"
- Actions row: search input (left), filter chips for part_type + status (middle), "Upload STEP File" button + "New Part" button (right)
- Loading state: table skeleton (5 rows, each with 8 column placeholders matching table column widths)
- Error state: red banner with message + Retry button
- Empty state (no data): centered illustration with text "No parts in the library. Upload a STEP file to get started." + Upload button
- Empty state (filtered, no results): "No parts match your filters." + Clear filters link
- Table columns: WPN (monospace font, copyable on click), Name, Type (colored badge), Material, Manufacturer, MPN, Status (badge), Approved (relative date)
- Row click: navigate to `/parts-library/{id}`

Part type badge colors (use the existing project's badge/chip component):
```
fastener → blue
washer → gray
insert → purple
bracket → teal
enclosure → orange
seal → green
bearing → amber
hinge_latch → pink
thermal_interface → red
pcb_mechanical → indigo
custom → gray
```

Status badge colors:
```
draft → gray
under_review → amber
approved → green
superseded → orange
obsolete → red
```

#### `frontend/src/app/(parts-library)/parts-library/[id]/page.tsx`

State:
```tsx
const [part, setPart] = useState<LibraryPartResponse | null>(null);
const [loading, setLoading] = useState(true);
const [editing, setEditing] = useState(false);
const [editData, setEditData] = useState<Partial<LibraryPartCreate>>({});
const [saving, setSaving] = useState(false);
const [activeTab, setActiveTab] = useState<'overview'|'dimensions'|'material'|'performance'|'procurement'>('overview');
```

Five tabs:

**Overview tab:** Two-column layout.
- Left column: Name, Description, WPN badge (monospace, dark background, white text, copy icon), Type badge, Status badge, Heritage, Drawing Number + Revision, CAGE, NSN, Manufacturer + MPN
- Right column (sticky): "3D Preview" card — `<StepViewer gltfUrl={...} mode="part" />`. If no STEP file: `<StepViewerPlaceholder onUpload={() => setUploadModalOpen(true)} />`
- Below left: "Linked Projects" section — list of projects using this part (from `/parts-library/{id}/linked-projects` endpoint — add this endpoint in Phase 2 if not present)
- Bottom: "Requirements" section — list of auto-requirements sourced from this part

**Dimensions tab:** Three-column form grid.
- Column 1: Bounding Box (X mm, Y mm, Z mm), Volume (mm³), Surface Area (mm²)
- Column 2: Thread Size, Thread Standard, Nominal Diameter (mm), Nominal Length (mm), Head Type, Drive Type
- Column 3: Bore (mm), Cross-Section Dia (mm), Flange Dia (mm), Hole Pattern Count, Hole Pattern Dia (mm), Hole Pattern PCD (mm)
- All fields: read-only by default, editable when `editing=true`

**Material tab:** Two-column form grid.
- Column 1: Material Name, Material Standard, Material Class, Density (g/cm³), Yield Strength (MPa), UTS (MPa), E-Modulus (GPa), Hardness
- Column 2: Thermal Conductivity (W/m·K), CTE (µm/m·°C), Corrosion Protection, Flammability Class, Outgassing TML (%), Outgassing CVCM (%)

**Performance tab:** Three-column form grid.
- Column 1: Mass Nominal (g), Mass Max (g), Proof Load (N), Clamp Load (N)
- Column 2: Torque Nominal (N·m), Torque Min (N·m), Torque Max (N·m), Torque Lubricated (N·m), Locking Feature, Safety Wire Holes
- Column 3: Shear Strength (N), Bearing Load (N), Compression Set (%), Sealing Pressure Max (bar), Temp Min (°C), Temp Max (°C)

**Procurement tab:** Two-column form.
- Column 1: Unit Cost (USD), Lead Time (weeks), Min Order Qty, Preferred Supplier (searchable select), Supplier P/N
- Column 2: Qualification Status, Qualification Basis (textarea), Shelf Life (months), Date of Manufacture, Restricted Use (checkbox), Restriction Notes (textarea, visible only if restricted_use=true)

Edit flow:
- Edit button → `setEditing(true)`, `setEditData({...part})` (all current values)
- Save button → `partsLibraryAPI.update(part.id, editData)` → on success: `setPart(result)`, `setEditing(false)`
- Cancel button → `setEditing(false)`, `setEditData({})`
- If save returns a new part (revision bump): show toast "A new revision WS-...-01 has been created. You are now viewing the new revision." and navigate to new part ID.

#### `frontend/src/app/(parts-library)/parts-library/pending-imports/[id]/page.tsx`

Two-panel layout (50/50 on desktop, stacked on mobile):

**Left panel — 3D preview:**
- `<StepViewer gltfUrl={...} mode="part" />` showing the uploaded STEP geometry
- Below viewer: STEP file name, checksum (truncated, monospace), upload date

**Right panel — field review:**
- Header: "Review extracted data" + parser version badge
- For each field in `proposed_data`:
  - Label (human-readable)
  - Current value (editable input)
  - Confidence badge: HIGH = green, MEDIUM = amber, LOW = red with warning icon
  - Fields in `low_confidence_fields` have amber background + "Low confidence — please verify" tooltip
- Required fields (name, part_type) are marked with *
- "Assign Supplier" optional dropdown (fetches from existing supplier list)
- Approve button (primary, disabled until name + part_type filled)
  - On click: shows confirm dialog "Approve and assign WPN?"
  - On confirm: `partsLibraryAPI.approveImport(id, editedValues, supplierId)`
  - On success: toast "Part WS-FAST-000042-00 approved" + navigate to part detail
- Reject button (secondary): opens modal with required reason text

---

### 5.4 Engineering nav restructure

Find the project-level Engineering section in the left navigation component. Apply these changes:

1. **Rename:** Find the nav item with label "Interfaces" (or "INTERFACES"). Change label to "ELECTRICAL INTERFACES". Do NOT change its `href` — it must still point to `/projects/[id]/interfaces`. This is a label change only.

2. **Add SYSTEM ARCHITECTURE** tab. `href=/projects/[id]/system-architecture`. Position: first in Engineering section (before ELECTRICAL INTERFACES). Icon: `CubeTransparentIcon` or equivalent.

3. **Add PARTS** tab. `href=/projects/[id]/parts`. Position: second. Icon: `CircleStackIcon` or `DatabaseIcon`.

4. **Add MECHANICAL INTERFACES** tab. `href=/projects/[id]/mechanical-interfaces`. Position: fourth (after ELECTRICAL INTERFACES). Icon: `WrenchIcon` or `CogIcon`.

Final Engineering section left-nav order:
```
SYSTEM ARCHITECTURE   →  /projects/[id]/system-architecture
PARTS                 →  /projects/[id]/parts
ELECTRICAL INTERFACES →  /projects/[id]/interfaces  (renamed label)
MECHANICAL INTERFACES →  /projects/[id]/mechanical-interfaces
```

Add a yellow info banner at the top of `/projects/[id]/interfaces`:
```tsx
<Banner variant="info">
  System and Unit management has been moved to{' '}
  <Link href={`/projects/${id}/system-architecture`}>
    System Architecture
  </Link>
  . This tab now focuses on Electrical Interfaces only.
</Banner>
```

---

### 5.5 PARTS tab: `frontend/src/app/projects/[id]/parts/page.tsx`

State:
```tsx
const [parts, setParts] = useState<ProjectPartResponse[]>([]);
const [loading, setLoading] = useState(true);
const [pickerOpen, setPickerOpen] = useState(false);
const [selectedPart, setSelectedPart] = useState<ProjectPartResponse | null>(null);
const [detailOpen, setDetailOpen] = useState(false);
```

Layout:
- Page header: "Parts" + project name badge + "Add Part" button
- Table columns: Designation (or "—"), WPN (link to global library), Name, Type badge, Material, Quantity, System (badge or "Unassigned" amber badge), Actions (remove icon)
- Unassigned parts highlighted with amber left border on the row
- Row click: `setSelectedPart(part)`, `setDetailOpen(true)` — opens slide-over panel showing full library part data (read-only, same 5-tab layout as part detail page but condensed)
- "Add Part" button → `setPickerOpen(true)` → `<LibraryPartPickerModal>`
- Remove (trash icon): confirmation dialog "Remove [part name] from this project?" → `projectPartsAPI.remove(projectId, part.id)`

`LibraryPartPickerModal` component (`frontend/src/components/parts/LibraryPartPickerModal.tsx`):

```tsx
interface LibraryPartPickerModalProps {
  open: boolean;
  onClose: () => void;
  onAdd: (partId: number, quantity: number, designation: string) => Promise<void>;
  projectId: number;
}
```

Internal state:
```tsx
const [search, setSearch] = useState('');
const [typeFilter, setTypeFilter] = useState<PartType | ''>('');
const [parts, setParts] = useState<LibraryPartSummary[]>([]);
const [loading, setLoading] = useState(false);
const [selectedId, setSelectedId] = useState<number | null>(null);
const [quantity, setQuantity] = useState(1);
const [designation, setDesignation] = useState('');
const [adding, setAdding] = useState(false);
```

Layout:
- Modal title: "Add Part from Library"
- Search bar + Type filter (left), results list (right/main)
- Results list: WPN, Name, Type badge, Material, Manufacturer — 10 rows max, scrollable
- Selected part highlighted with blue border
- Bottom: Quantity stepper (min=1, max=999), optional Designation input, "Add to Project" button
- Multi-add: "Add Another" button resets form but keeps modal open

---

### 5.6 SYSTEM ARCHITECTURE tab: `frontend/src/app/projects/[id]/system-architecture/page.tsx`

Two sub-tabs: "Overview" and "Systems".

**Overview sub-tab:**

Uses the existing `ForceGraph` component. Fetch:
```tsx
const [systems, setSystems] = useState<System[]>([]);
const [projectParts, setProjectParts] = useState<ProjectPartResponse[]>([]);
const [electricalInterfaces, setElectricalInterfaces] = useState([]);
const [mechanicalJoints, setMechanicalJoints] = useState<MechanicalJointResponse[]>([]);
```

Graph node data:
```tsx
const nodes = [
  // System nodes (large)
  ...systems.map(s => ({
    id: `system-${s.id}`,
    label: s.name,
    type: 'system',
    size: 20,
    color: getSystemColor(s.system_type),
  })),
  // Part nodes (small, positioned by system)
  ...projectParts.map(pp => ({
    id: `part-${pp.id}`,
    label: pp.library_part.name,
    type: 'part',
    size: 8,
    color: getPartTypeColor(pp.library_part.part_type),
    parentSystemId: pp.system_id ? `system-${pp.system_id}` : null,
  })),
];

const links = [
  // Electrical edges (blue)
  ...electricalInterfaces.map(iface => ({
    source: `system-${iface.source_system_id}`,
    target: `system-${iface.target_system_id}`,
    type: 'electrical',
    color: '#3B82F6',
    width: 1,
  })),
  // Mechanical edges (amber)
  ...mechanicalJoints
    .filter(j => j.status === 'active')
    .map(j => ({
      source: `part-${j.part_a_id}`,
      target: `part-${j.part_b_id}`,
      type: 'mechanical',
      color: '#F59E0B',
      width: Math.min(1 + (j.fastener_count || 1) / 4, 3),
    })),
];
```

Filter bar: toggle buttons for "Electrical edges", "Mechanical edges", "Unassigned parts".

Click handlers:
- System node click → open system detail side panel (shows system name, type, assigned parts list)
- Part node click → open part detail side panel (shows library part data read-only)

Export button: screenshot the canvas as PNG.

**Systems sub-tab:**

List of systems in accordion layout. Each system accordion:
- Header: System name, type badge, part count, "Assign Part" button
- Expanded: drag-sortable list of assigned parts (calls `systemPartsAPI.reorder` on drop)
- Each part row: designation, WPN link, name, type badge, remove from system button
- "Create System" button at top → same modal as currently in Interfaces tab (does NOT change backend route)
- "Assign Part" button → opens `LibraryPartPickerModal` filtered to parts already in this project (not the global library) — `listUnassigned` parts + already-assigned parts

---

### 5.7 MECHANICAL INTERFACES tab: `frontend/src/app/projects/[id]/mechanical-interfaces/page.tsx`

State:
```tsx
const [joints, setJoints] = useState<MechanicalJointResponse[]>([]);
const [loading, setLoading] = useState(true);
const [selectedJoint, setSelectedJoint] = useState<MechanicalJointResponse | null>(null);
const [createModalOpen, setCreateModalOpen] = useState(false);
const [uploadModalOpen, setUploadModalOpen] = useState(false);
const [parseJob, setParseJob] = useState<AssemblyParseJobResponse | null>(null);
const [filters, setFilters] = useState<{
  joint_type?: JointType;
  status?: JointStatus;
  confidence?: ConfidenceLevel;
}>({});
```

Layout (top to bottom):

**3D Assembly Viewer section** (Phase 4 — in Phase 3, render placeholder):
```tsx
// Phase 3 placeholder:
<div className="rounded-lg border border-dashed border-gray-300 dark:border-gray-600 p-8 text-center mb-6">
  <p className="text-gray-500">3D assembly view available after Phase 4.</p>
  <button
    disabled
    className="mt-2 text-sm text-blue-400 cursor-not-allowed"
  >
    Upload Assembly STEP file (coming soon)
  </button>
</div>
```

**Parse job status banner** (visible when `parseJob !== null`):
```tsx
{parseJob && parseJob.status !== 'complete' && (
  <StatusBanner
    status={parseJob.status}
    message={
      parseJob.status === 'running'
        ? 'Parsing assembly file...'
        : parseJob.status === 'failed'
          ? `Parse failed: ${parseJob.error}`
          : 'Queued for parsing...'
    }
  />
)}
```

**Joints list section:**
- Toolbar: filter chips (Type, Status, Confidence), "Add Joint" button, "Upload Assembly" button
- Table columns: Joint ID (monospace), Type badge, Part A, Part B, Fastener (WPN link or "—"), Count, Torque (formatted as "X.X N·m"), Status badge, Confidence badge, Actions
- Confidence badge: HIGH = green, MEDIUM = yellow, LOW = red
- Row click → right-side slide panel showing full joint detail + editable fields

**Joint detail slide panel:**
- All MechanicalJoint fields in editable form
- Fastener picker: `<LibraryPartPickerModal>` filtered to `part_type=fastener`
- Seal picker: `<LibraryPartPickerModal>` filtered to `part_type=seal`
- Part A + B pickers: dropdown over `projectParts` in this project
- Status badge + Approve button (if DRAFT)
- Requirements section: list of auto-requirements sourced from this joint (read-only with sync status)

**`AddJointManuallyModal` component** (`frontend/src/components/parts/AddJointManuallyModal.tsx`):
- Form with all MechanicalJointCreate fields
- Part A + Part B: searchable select over `projectParts`
- Joint Type: radio group with icons (bolt icon for BOLTED, ring for SEAL, etc.)
- Fastener picker: appears when joint_type=BOLTED or RIVETED
- Seal picker: appears when joint_type=SEAL
- Torque fields: appear when joint_type=BOLTED
- Leak fields: appear when joint_type=SEAL
- Conditional field visibility matches the joint_type selection
- Submit: `mechanicalJointsAPI.create(projectId, formData)` → on success close modal + refresh joints

---

### 5.8 Phase 3 verification gate

```bash
cd frontend && npm run typecheck    # exit 0
cd frontend && npm run build        # exit 0, "Compiled successfully"
docker exec astra-backend-1 pytest tests/ -q -m "not performance"
```

Manual route verification (check build output for these pages):
- `/parts-library` — Parts Library list page
- `/parts-library/new` — Manual create form
- `/parts-library/[id]` — Part detail with 5 tabs
- `/parts-library/pending-imports` — Review queue
- `/parts-library/pending-imports/[id]` — Review detail
- `/projects/1/parts` — PARTS tab
- `/projects/1/system-architecture` — SYSTEM ARCHITECTURE tab
- `/projects/1/mechanical-interfaces` — MECHANICAL INTERFACES tab (shell)
- `/projects/1/interfaces` — ELECTRICAL INTERFACES (renamed label, works)

Commit: `feat(parts): phase-3-complete — Parts Library UI, nav restructure, PARTS tab, System Architecture, Mechanical Interfaces shell`

---

## 6. Phase 4 — Assembly Parser, 3D Viewer, Full Integration

---

### 6.1 Assembly parser: `backend/app/services/parts/assembly_parser.py`

```python
"""
Assembly STEP file parser.
Detects mating relationships between parts and creates draft MechanicalJoint records.

Stages:
  1. Parse assembly tree via NEXT_ASSEMBLY_USAGE_OCCURENCE (NAUO) entities
  2. Match STEP instances to project's LibraryPart records
  3. Detect mating faces (co-planar, COINCIDENT_SURFACE_RELATIONSHIP or geometric proximity)
  4. Detect fastener patterns (hole clustering on mating faces)
  5. Detect sealing grooves (annular features adjacent to mating faces)
  6. Detect alignment pins (cylindrical pairs crossing mating faces)
  7. AI interpretation of detected joint configurations
  8. Create PendingMechanicalJoint draft records
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional
import logging
import json

logger = logging.getLogger(__name__)
ASSEMBLY_PARSER_VERSION = "1.0.0"


@dataclass
class AssemblyInstanceResult:
    step_entity_id: str
    step_product_name: str
    transform_matrix: list[float]    # 4×4 column-major homogeneous transform
    matched_library_part_id: Optional[int] = None
    confidence: str = "low"


@dataclass
class AssemblyJointResult:
    part_a_step_entity: str
    part_b_step_entity: str
    joint_type: str                  # JointType enum value string
    mating_face_entities: list[str]  # STEP entity IDs of the paired faces
    fastener_thread_size: Optional[str] = None
    fastener_thread_standard: Optional[str] = None
    fastener_count: Optional[int] = None
    torque_nominal_nm: Optional[Decimal] = None
    torque_min_nm: Optional[Decimal] = None
    torque_max_nm: Optional[Decimal] = None
    has_seal_groove: bool = False
    confidence: str = "low"


@dataclass
class AssemblyParseResult:
    instances: list[AssemblyInstanceResult] = field(default_factory=list)
    joints: list[AssemblyJointResult] = field(default_factory=list)
    unmatched_instance_names: list[str] = field(default_factory=list)
    extraction_log: str = ""
    parser_version: str = ASSEMBLY_PARSER_VERSION
    occ_available: bool = False


def parse_assembly_step(
    file_path: str,
    library_parts_lookup: dict[str, int],  # {product_name: library_part_id, mpn: library_part_id}
) -> AssemblyParseResult:
    """
    library_parts_lookup maps known identifiers to library_part_id values.
    Built by the caller by querying all APPROVED LibraryParts in the project.
    """
    log_lines: list[str] = []
    result = AssemblyParseResult()

    # Stage 1: Always try metadata-based assembly tree
    _parse_assembly_metadata(file_path, result, library_parts_lookup, log_lines)

    # Stage 2-7: Full OCC geometry analysis
    try:
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.IFSelect import IFSelect_RetDone
        from OCC.Core.BRep import BRep_Tool
        from OCC.Core.TopAbs import TopAbs_FACE, TopAbs_SOLID
        from OCC.Core.TopExp import TopExp_Explorer
        from OCC.Core.GeomAbs import GeomAbs_Cylinder, GeomAbs_Plane
        from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
        from OCC.Core.gp import gp_Pln
        import math

        reader = STEPControl_Reader()
        if reader.ReadFile(file_path) != IFSelect_RetDone:
            log_lines.append("OCC assembly read failed")
            raise RuntimeError("ReadFile failed")

        reader.TransferRoots()

        # Build shape map: PRODUCT entity ID → TopoDS_Shape
        shapes = {}
        for i in range(1, reader.NbRootsForTransfer() + 1):
            reader.TransferRoot(i)
            shapes[str(i)] = reader.Shape(i)

        log_lines.append(f"OCC loaded {len(shapes)} root shapes")

        # Stage 3: Detect mating faces between instances
        # For each pair of instances, find co-planar face pairs
        # (simplified: planar faces with normals pointing at each other within 1°)
        _detect_mating_pairs(shapes, result, log_lines)

        # Stage 4: Detect fastener patterns on mating faces
        _detect_fastener_patterns(shapes, result, log_lines)

        # Stage 5: Detect sealing grooves
        _detect_seal_grooves(shapes, result, log_lines)

        result.occ_available = True
        log_lines.append("OCC assembly analysis complete")

    except ImportError:
        log_lines.append(
            "pythonOCC not available — assembly parser running in stub mode. "
            "Part matching from metadata only; no joint detection."
        )

    result.extraction_log = "\n".join(log_lines)
    return result


def _parse_assembly_metadata(
    file_path: str,
    result: AssemblyParseResult,
    lookup: dict[str, int],
    log_lines: list[str],
) -> None:
    """
    Stage 1: Parse STEP text to extract assembly tree from NAUO entities.
    Matches instances to LibraryParts by product name and MPN.
    """
    import re
    try:
        with open(file_path, 'r', errors='replace') as f:
            content = f.read()

        # Extract all PRODUCT entities: #N = PRODUCT('name','desc',...)
        products = {}
        for m in re.finditer(
            r'#(\d+)\s*=\s*PRODUCT\s*\(\s*\'([^\']*)\'\s*,\s*\'([^\']*)\'\s*,',
            content, re.IGNORECASE
        ):
            entity_id, name, description = m.group(1), m.group(2), m.group(3)
            products[entity_id] = {"name": name.strip(), "description": description.strip()}

        # Extract transforms from AXIS2_PLACEMENT_3D and PRODUCT_DEFINITION_PLACEMENT
        # (simplified: use identity transform for now; full transform extraction
        # requires OCC and is done in stage 2+)
        identity = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]

        for entity_id, prod in products.items():
            name = prod["name"]
            # Match to library parts
            matched_id = (
                lookup.get(name.lower()) or
                lookup.get(name.upper()) or
                lookup.get(name)
            )

            instance = AssemblyInstanceResult(
                step_entity_id=f"#PRODUCT:{entity_id}",
                step_product_name=name,
                transform_matrix=identity,
                matched_library_part_id=matched_id,
                confidence="high" if matched_id else "low",
            )
            result.instances.append(instance)
            if not matched_id:
                result.unmatched_instance_names.append(name)

        log_lines.append(
            f"Assembly tree: {len(products)} products, "
            f"{len(result.unmatched_instance_names)} unmatched"
        )

    except Exception as exc:
        log_lines.append(f"Assembly metadata parse failed: {exc}")


def _detect_mating_pairs(shapes, result, log_lines):
    """Stub — full implementation uses OCC face proximity analysis."""
    log_lines.append("Mating pair detection: stub (OCC available but not fully implemented in v1)")


def _detect_fastener_patterns(shapes, result, log_lines):
    """Stub — full implementation uses hole clustering on detected mating faces."""
    log_lines.append("Fastener pattern detection: stub")


def _detect_seal_grooves(shapes, result, log_lines):
    """Stub — full implementation detects annular grooves adjacent to planar mating faces."""
    log_lines.append("Seal groove detection: stub")
```

---

### 6.2 Assembly parse background task: `_run_assembly_parser`

Add to `backend/app/routers/mechanical_joints.py`:

```python
async def _run_assembly_parser(
    job_id: int,
    project_id: int,
    file_path: str,
    user_id: int,
) -> None:
    from app.database import SessionLocal
    db = SessionLocal()
    job = None
    try:
        job = db.query(AssemblyParseJob).get(job_id)
        if not job:
            return

        job.status = AssemblyParseJobStatus.RUNNING
        job.progress_log = "Stage 1: Loading library parts lookup...\n"
        db.commit()

        # Build lookup dict: name.lower() → library_part_id, mpn.lower() → library_part_id
        project_parts = (
            db.query(ProjectPart)
            .options(selectinload(ProjectPart.library_part))
            .filter(ProjectPart.project_id == project_id)
            .all()
        )
        lookup = {}
        for pp in project_parts:
            lp = pp.library_part
            if lp.name:
                lookup[lp.name.lower()] = lp.id
            if lp.manufacturer_part_number:
                lookup[lp.manufacturer_part_number.lower()] = lp.id
            if lp.wardstone_part_number:
                lookup[lp.wardstone_part_number.lower()] = lp.id

        job.progress_log += f"Lookup built: {len(lookup)} keys, {len(project_parts)} project parts\n"
        db.commit()

        # Run parser
        parse_result = parse_assembly_step(file_path, lookup)
        job.progress_log += parse_result.extraction_log
        db.commit()

        # Create draft MechanicalJoint records for each detected joint
        joints_created = 0
        for joint_result in parse_result.joints:
            # Resolve part_a and part_b from step entity IDs
            part_a_pp = _resolve_project_part(
                db, project_id, joint_result.part_a_step_entity, project_parts
            )
            part_b_pp = _resolve_project_part(
                db, project_id, joint_result.part_b_step_entity, project_parts
            )
            if not part_a_pp or not part_b_pp:
                job.progress_log += (
                    f"Skipping joint {joint_result.part_a_step_entity} ↔ "
                    f"{joint_result.part_b_step_entity}: could not resolve project parts\n"
                )
                continue

            # Assign joint ID
            joint_id = _assign_joint_id(db, project_id)

            joint = MechanicalJoint(
                joint_id=joint_id,
                project_id=project_id,
                joint_type=JointType(joint_result.joint_type),
                part_a_id=part_a_pp.id,
                part_b_id=part_b_pp.id,
                fastener_count=joint_result.fastener_count,
                torque_nominal_nm=joint_result.torque_nominal_nm,
                torque_min_nm=joint_result.torque_min_nm,
                torque_max_nm=joint_result.torque_max_nm,
                source_step_file_id=job.document_id,
                source_step_entity=json.dumps(joint_result.mating_face_entities),
                confidence=ConfidenceLevel(joint_result.confidence),
                status=JointStatus.DRAFT,
                created_by_id=user_id,
            )

            # Try to link fastener from library if thread size detected
            if joint_result.fastener_thread_size:
                fastener = (
                    db.query(LibraryPart)
                    .filter(
                        LibraryPart.thread_size == joint_result.fastener_thread_size,
                        LibraryPart.part_type == PartType.FASTENER,
                        LibraryPart.status == PartStatus.APPROVED,
                    )
                    .first()
                )
                if fastener:
                    joint.fastener_part_id = fastener.id
                    joint.torque_nominal_nm = fastener.torque_nominal_nm
                    joint.torque_min_nm = fastener.torque_min_nm
                    joint.torque_max_nm = fastener.torque_max_nm
                    joint.locking_feature = fastener.locking_feature

            db.add(joint)
            joints_created += 1

        db.flush()

        # Store transform data for 3D viewer in result JSON
        result_json = {
            "joints_created": joints_created,
            "unmatched_parts": parse_result.unmatched_instance_names,
            "transforms": [
                {
                    "step_entity_id": inst.step_entity_id,
                    "library_part_id": inst.matched_library_part_id,
                    "transform_matrix": inst.transform_matrix,
                }
                for inst in parse_result.instances
                if inst.matched_library_part_id is not None
            ],
            "occ_available": parse_result.occ_available,
        }

        job.status = AssemblyParseJobStatus.COMPLETE
        job.result = result_json
        job.completed_at = func.now()
        job.progress_log += (
            f"\nComplete: {joints_created} joints created, "
            f"{len(parse_result.unmatched_instance_names)} parts unmatched"
        )
        db.commit()

    except Exception as exc:
        import traceback
        if job:
            job.status = AssemblyParseJobStatus.FAILED
            job.error = traceback.format_exc()
            job.completed_at = func.now()
            db.commit()
        logger.error("Assembly parser job %d failed: %s", job_id, exc)
    finally:
        db.close()
```

---

### 6.3 GLTF export endpoint

Add to `backend/app/routers/parts_library.py`:

```python
@router.get("/{part_id}/gltf")
async def get_part_gltf(
    part_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the GLTF file for a part's STEP geometry.
    GLTF is cached by STEP file checksum — regenerated only on new STEP upload.
    Returns 404 if no STEP file has been uploaded for this part.
    Returns 202 Accepted if GLTF is being generated (poll again in 3s).
    """
    part = db.query(LibraryPart).get(part_id)
    if not part or not part.step_file_id:
        raise HTTPException(404, "No STEP file for this part")

    import os
    from fastapi.responses import FileResponse

    gltf_cache_dir = os.environ.get("GLTF_CACHE_DIR", "/tmp/astra_gltf_cache")
    os.makedirs(gltf_cache_dir, exist_ok=True)
    gltf_path = os.path.join(gltf_cache_dir, f"{part.step_file_checksum}.gltf")

    if os.path.exists(gltf_path):
        return FileResponse(
            gltf_path,
            media_type="model/gltf+json",
            headers={"Cache-Control": "public, max-age=86400"},
        )

    # GLTF not yet generated — attempt generation
    doc = db.query(Document).get(part.step_file_id)
    if not doc:
        raise HTTPException(404, "STEP document not found")

    # Attempt synchronous generation (fast parts only — < 2 seconds)
    # For large parts, queue a background task instead
    generated = _generate_gltf_sync(doc.file_path, gltf_path)
    if generated:
        return FileResponse(
            gltf_path,
            media_type="model/gltf+json",
            headers={"Cache-Control": "public, max-age=86400"},
        )
    else:
        # pythonOCC not available or generation failed
        raise HTTPException(
            404,
            {"detail": "3D preview not available (pythonOCC not installed)",
             "code": "GLTF_UNAVAILABLE"}
        )


def _generate_gltf_sync(step_path: str, output_path: str) -> bool:
    """
    Generate GLTF from STEP using pythonOCC.
    Returns True on success, False if pythonOCC is unavailable.
    The GLTF is a minimal single-mesh representation sufficient for three.js display.
    """
    try:
        from OCC.Core.STEPControl import STEPControl_Reader
        from OCC.Core.IFSelect import IFSelect_RetDone
        from OCC.Core.BRepMesh import BRepMesh_IncrementalMesh
        from OCC.Core.BRep import BRep_Tool
        from OCC.Core.TopExp import TopExp_Explorer
        from OCC.Core.TopAbs import TopAbs_FACE
        import json, struct, base64

        reader = STEPControl_Reader()
        if reader.ReadFile(step_path) != IFSelect_RetDone:
            return False
        reader.TransferRoots()
        shape = reader.OneShape()

        # Tessellate with deflection=0.5mm
        mesh = BRepMesh_IncrementalMesh(shape, 0.5, False, 0.5)
        mesh.Perform()

        vertices = []
        indices = []
        vertex_count = 0

        exp = TopExp_Explorer(shape, TopAbs_FACE)
        while exp.More():
            face = exp.Current()
            location = face.Location()
            facing = BRep_Tool.Triangulation(face, location)
            if facing is None:
                exp.Next()
                continue

            tri_offset = vertex_count
            for i in range(1, facing.NbNodes() + 1):
                node = facing.Node(i)
                node.Transform(location.IsIdentity() and node or node.Transformed(location.Transformation()))
                vertices.extend([node.X(), node.Y(), node.Z()])
                vertex_count += 1

            for i in range(1, facing.NbTriangles() + 1):
                tri = facing.Triangle(i)
                n1, n2, n3 = tri.Get()
                indices.extend([
                    tri_offset + n1 - 1,
                    tri_offset + n2 - 1,
                    tri_offset + n3 - 1,
                ])
            exp.Next()

        if not vertices:
            return False

        # Cap at 500k triangles
        max_tris = 500_000
        if len(indices) // 3 > max_tris:
            indices = indices[:max_tris * 3]

        # Build minimal GLTF JSON with embedded buffers
        vertex_data = struct.pack(f"{len(vertices)}f", *vertices)
        index_data  = struct.pack(f"{len(indices)}I", *[max(0, i) for i in indices])
        buffer_data = vertex_data + index_data
        buffer_b64  = base64.b64encode(buffer_data).decode()

        gltf = {
            "asset": {"version": "2.0"},
            "scene": 0,
            "scenes": [{"nodes": [0]}],
            "nodes": [{"mesh": 0}],
            "meshes": [{
                "primitives": [{
                    "attributes": {"POSITION": 0},
                    "indices": 1,
                }]
            }],
            "accessors": [
                {
                    "bufferView": 0,
                    "componentType": 5126,   # FLOAT
                    "count": vertex_count,
                    "type": "VEC3",
                    "byteOffset": 0,
                },
                {
                    "bufferView": 1,
                    "componentType": 5125,   # UNSIGNED_INT
                    "count": len(indices),
                    "type": "SCALAR",
                    "byteOffset": 0,
                },
            ],
            "bufferViews": [
                {
                    "buffer": 0,
                    "byteOffset": 0,
                    "byteLength": len(vertex_data),
                    "target": 34962,  # ARRAY_BUFFER
                },
                {
                    "buffer": 0,
                    "byteOffset": len(vertex_data),
                    "byteLength": len(index_data),
                    "target": 34963,  # ELEMENT_ARRAY_BUFFER
                },
            ],
            "buffers": [{
                "uri": f"data:application/octet-stream;base64,{buffer_b64}",
                "byteLength": len(buffer_data),
            }],
        }

        with open(output_path, 'w') as f:
            json.dump(gltf, f)
        return True

    except ImportError:
        return False
    except Exception as exc:
        logger.error("GLTF generation failed: %s", exc)
        return False
```

---

### 6.4 3D Viewer component: `frontend/src/components/parts/StepViewer.tsx`

```tsx
'use client';
import { useEffect, useRef, useState, useCallback } from 'react';

interface MissingPartInfo {
  name: string;
  library_part_id: number;
  bounding_box?: { x: number; y: number; z: number };
}

interface StepViewerProps {
  gltfUrl: string | null;
  missingParts?: MissingPartInfo[];
  highlightJointId?: string;
  mode: 'part' | 'assembly';
  className?: string;
}

const ISOMETRIC_AZIMUTH  = Math.PI / 4;           // 45°
const ISOMETRIC_ELEVATION = Math.atan(1 / Math.sqrt(2)); // 35.264°

export function StepViewer({
  gltfUrl, missingParts = [], highlightJointId, mode, className,
}: StepViewerProps) {
  const mountRef      = useRef<HTMLDivElement>(null);
  const rendererRef   = useRef<unknown>(null);  // THREE.WebGLRenderer
  const sceneRef      = useRef<unknown>(null);
  const cameraRef     = useRef<unknown>(null);
  const controlsRef   = useRef<unknown>(null);
  const frameIdRef    = useRef<number>(0);

  const [loading,  setLoading]  = useState(false);
  const [error,    setError]    = useState<string | null>(null);
  const [polling,  setPolling]  = useState(false);

  // Initialize three.js renderer (lazy — only when gltfUrl is set)
  useEffect(() => {
    if (!gltfUrl || !mountRef.current) return;

    let THREE: typeof import('three') | null = null;
    let cleanup: (() => void) | null = null;

    setLoading(true);

    import('three').then(async (three) => {
      THREE = three;
      const { GLTFLoader } = await import('three/examples/jsm/loaders/GLTFLoader.js');
      const { OrbitControls } = await import(
        'three/examples/jsm/controls/OrbitControls.js'
      );

      if (!mountRef.current) return;
      const container = mountRef.current;
      const w = container.clientWidth;
      const h = container.clientHeight || 400;

      // Orthographic camera (true isometric — no perspective distortion)
      const aspect = w / h;
      const frustumSize = 100;
      const camera = new THREE.OrthographicCamera(
        -frustumSize * aspect / 2,
         frustumSize * aspect / 2,
         frustumSize / 2,
        -frustumSize / 2,
        0.1,
        10000,
      );
      // Isometric position
      camera.position.set(
        Math.cos(ISOMETRIC_AZIMUTH) * Math.cos(ISOMETRIC_ELEVATION) * 200,
        Math.sin(ISOMETRIC_ELEVATION) * 200,
        Math.sin(ISOMETRIC_AZIMUTH) * Math.cos(ISOMETRIC_ELEVATION) * 200,
      );
      camera.lookAt(0, 0, 0);
      cameraRef.current = camera;

      // Scene setup
      const scene = new THREE.Scene();
      scene.background = null;  // transparent — host provides background
      const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
      const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
      dirLight.position.set(100, 200, 100);
      scene.add(ambientLight, dirLight);
      sceneRef.current = scene;

      // Renderer
      const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
      renderer.setSize(w, h);
      container.appendChild(renderer.domElement);
      rendererRef.current = renderer;

      // Controls
      const controls = new OrbitControls(camera, renderer.domElement);
      controls.enableDamping = true;
      controls.dampingFactor = 0.05;
      controlsRef.current = controls;

      // Load GLTF
      const loader = new GLTFLoader();
      loader.load(
        gltfUrl,
        (gltf) => {
          scene.add(gltf.scene);
          // Center model
          const box = new THREE.Box3().setFromObject(gltf.scene);
          const center = box.getCenter(new THREE.Vector3());
          gltf.scene.position.sub(center);
          // Adjust frustum to fit
          const size = box.getSize(new THREE.Vector3());
          const maxDim = Math.max(size.x, size.y, size.z);
          const newFrustum = maxDim * 1.5;
          (camera as THREE.OrthographicCamera).left   = -newFrustum * aspect / 2;
          (camera as THREE.OrthographicCamera).right  =  newFrustum * aspect / 2;
          (camera as THREE.OrthographicCamera).top    =  newFrustum / 2;
          (camera as THREE.OrthographicCamera).bottom = -newFrustum / 2;
          camera.updateProjectionMatrix();
          camera.position.setLength(maxDim * 2);
          camera.lookAt(0, 0, 0);
          setLoading(false);
        },
        undefined,
        (err) => {
          if ((err as { status?: number }).status === 202) {
            // GLTF being generated — poll
            setPolling(true);
            setLoading(false);
          } else if ((err as { status?: number }).status === 404) {
            setError('no_step_file');
            setLoading(false);
          } else {
            setError('load_failed');
            setLoading(false);
          }
        },
      );

      // Render missing parts as bounding box wireframes
      for (const missing of missingParts) {
        const box = new THREE.BoxGeometry(
          missing.bounding_box?.x ?? 50,
          missing.bounding_box?.y ?? 50,
          missing.bounding_box?.z ?? 50,
        );
        const edges = new THREE.EdgesGeometry(box);
        const wireframe = new THREE.LineSegments(
          edges,
          new THREE.LineBasicMaterial({ color: 0x888888, transparent: true, opacity: 0.4 })
        );
        wireframe.userData = { missingPartName: missing.name };
        scene.add(wireframe);
      }

      // Animation loop
      const animate = () => {
        frameIdRef.current = requestAnimationFrame(animate);
        (controlsRef.current as { update: () => void })?.update();
        renderer.render(scene, camera);
      };
      animate();

      // Resize observer
      const ro = new ResizeObserver(() => {
        const nw = container.clientWidth;
        const nh = container.clientHeight || 400;
        renderer.setSize(nw, nh);
        const na = nw / nh;
        (camera as THREE.OrthographicCamera).left   = -frustumSize * na / 2;
        (camera as THREE.OrthographicCamera).right  =  frustumSize * na / 2;
        camera.updateProjectionMatrix();
      });
      ro.observe(container);

      cleanup = () => {
        cancelAnimationFrame(frameIdRef.current);
        ro.disconnect();
        renderer.dispose();
        if (container.contains(renderer.domElement)) {
          container.removeChild(renderer.domElement);
        }
      };
    }).catch(() => {
      setError('three_load_failed');
      setLoading(false);
    });

    return () => { cleanup?.(); };
  }, [gltfUrl]);

  // Poll for GLTF availability (when 202 received)
  useEffect(() => {
    if (!polling || !gltfUrl) return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(gltfUrl, { method: 'HEAD' });
        if (res.ok) {
          setPolling(false);
          // Trigger re-render by resetting gltfUrl (parent must handle this)
          window.location.reload(); // simplest approach — refactor with onReady callback if needed
        }
      } catch {
        // still waiting
      }
    }, 3000);
    return () => clearInterval(interval);
  }, [polling, gltfUrl]);

  const handleExportPNG = useCallback(() => {
    const renderer = rendererRef.current as { domElement: HTMLCanvasElement } | null;
    if (!renderer) return;
    const link = document.createElement('a');
    link.download = 'astra-3d-view.png';
    link.href = renderer.domElement.toDataURL('image/png');
    link.click();
  }, []);

  const handleResetView = useCallback(() => {
    const camera = cameraRef.current as { position: { setLength: (n: number) => void }; lookAt: (x: number, y: number, z: number) => void } | null;
    if (!camera) return;
    camera.position.setLength(200);
    camera.lookAt(0, 0, 0);
  }, []);

  if (!gltfUrl) {
    return (
      <div className={`flex flex-col items-center justify-center h-64 rounded-lg border border-dashed border-gray-300 dark:border-gray-600 ${className}`}>
        <p className="text-sm text-gray-500 dark:text-gray-400">No STEP file uploaded</p>
        <p className="text-xs text-gray-400 mt-1">Upload a STEP file to enable 3D preview</p>
      </div>
    );
  }

  return (
    <div className={`relative ${className}`}>
      {/* Toolbar */}
      <div className="absolute top-2 right-2 z-10 flex gap-1">
        <button
          onClick={handleResetView}
          className="px-2 py-1 text-xs bg-black/30 text-white rounded hover:bg-black/50"
          title="Reset to isometric view"
        >
          ⊡ Reset
        </button>
        <button
          onClick={handleExportPNG}
          className="px-2 py-1 text-xs bg-black/30 text-white rounded hover:bg-black/50"
          title="Export as PNG"
        >
          ↓ PNG
        </button>
      </div>

      {/* Viewer mount */}
      <div
        ref={mountRef}
        className="w-full h-80 rounded-lg overflow-hidden"
        style={{ touchAction: 'none' }}
      />

      {/* Loading overlay */}
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center bg-black/20 rounded-lg">
          <div className="text-sm text-white">Loading 3D model...</div>
        </div>
      )}

      {/* Polling overlay */}
      {polling && (
        <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/20 rounded-lg">
          <div className="text-sm text-white">Generating 3D preview...</div>
          <div className="text-xs text-gray-300 mt-1">Checking every 3 seconds</div>
        </div>
      )}

      {/* Missing parts warning */}
      {missingParts.length > 0 && (
        <div className="mt-2 p-2 bg-amber-50 dark:bg-amber-900/20 rounded border border-amber-200 dark:border-amber-800">
          <p className="text-xs font-medium text-amber-800 dark:text-amber-200">
            {missingParts.length} part(s) not shown — no STEP file uploaded:
          </p>
          <ul className="mt-1 text-xs text-amber-700 dark:text-amber-300">
            {missingParts.map(p => (
              <li key={p.library_part_id}>
                • {p.name}{' '}
                <a href={`/parts-library/${p.library_part_id}`}
                   className="underline">Upload STEP →</a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
```

---

### 6.5 Wire 3D viewer into pages

**In `parts-library/[id]/page.tsx`** — Overview tab right panel:
```tsx
<StepViewer
  gltfUrl={part.step_file_id
    ? `/api/v1/parts-library/${part.id}/gltf`
    : null}
  mode="part"
  className="h-80"
/>
```

**In `projects/[id]/mechanical-interfaces/page.tsx`** — replace Phase 3 placeholder:
```tsx
<StepViewer
  gltfUrl={assemblyGltfUrl}
  missingParts={missingParts}
  highlightJointId={selectedJoint?.joint_id}
  mode="assembly"
  className="h-96 mb-4"
/>
```

Where `assemblyGltfUrl` and `missingParts` are derived from the latest completed `AssemblyParseJob`:
```tsx
useEffect(() => {
  if (!latestJob || latestJob.status !== 'complete') return;
  // assemblyGltfUrl: from a new endpoint /projects/{id}/mechanical-joints/assembly-gltf
  // which serves the combined assembly GLTF built from individual part GLTFs + transforms
  setAssemblyGltfUrl(`/api/v1/projects/${projectId}/mechanical-joints/assembly-gltf/${latestJob.id}`);
  const unmatched = latestJob.result?.unmatched_parts as string[] || [];
  // Map unmatched names to project parts for warning display
  const missing = unmatched.map(name => ({
    name,
    library_part_id: 0,
    // bounding_box resolved from project parts if available
  }));
  setMissingParts(missing);
}, [latestJob, projectId]);
```

Wire "Upload Assembly File" button:
```tsx
const handleUploadAssembly = async (file: File) => {
  try {
    const res = await mechanicalJointsAPI.uploadAssembly(projectId, file, setPct);
    setParseJob({ id: res.data.job_id, status: 'queued', ... });
    // Poll status
    const pollInterval = setInterval(async () => {
      const status = await mechanicalJointsAPI.getParseStatus(projectId, res.data.job_id);
      setParseJob(status.data);
      if (['complete', 'failed'].includes(status.data.status)) {
        clearInterval(pollInterval);
        if (status.data.status === 'complete') {
          // Refresh joints list
          const jointsRes = await mechanicalJointsAPI.list(projectId);
          setJoints(jointsRes.data);
          toast.success(`${status.data.result?.joints_created ?? 0} joints detected`);
        }
      }
    }, 2000);
  } catch (err) {
    toast.error('Assembly upload failed');
  }
};
```

---

### 6.6 Phase 4 verification gate

```bash
# Backend
docker exec astra-backend-1 pytest tests/test_parts_library.py -v
docker exec astra-backend-1 pytest tests/test_project_parts.py -v
docker exec astra-backend-1 pytest tests/test_mechanical_joints.py -v
docker exec astra-backend-1 pytest tests/ -q -m "not performance"
# Zero regressions from TESTS_BEFORE

# Frontend
cd frontend && npm run typecheck
cd frontend && npm run build   # must be "Compiled successfully"

# Schema integrity
docker exec astra-backend-1 alembic check   # "No new upgrade operations"

# Integration smoke (manual, document results in log)
# 1. Upload a .step file → verify pending import created, confidence scores present
# 2. Approve import → verify WPN assigned (WS-FAST-000001-00 format)
# 3. Add part to project 1 → verify ProjectPart join created
# 4. Assign to a system → verify SystemPartAssignment created
# 5. Create mechanical joint → verify joint_id format MJ-0001-000001
# 6. Approve joint → verify Requirement + RequirementSourceLink created in DB
# 7. Update joint torque → verify RequirementSyncProposal created
# 8. Navigate /projects/1/mechanical-interfaces → verify 3D viewer or placeholder shown
# 9. Navigate /projects/1/interfaces → verify "ELECTRICAL INTERFACES" label, all flows work
# 10. Navigate /projects/1/system-architecture → verify system list + overview graph
```

Commit: `feat(parts): phase-4-complete — assembly parser, 3D viewer, auto-requirements, full integration`

---

## 7. Cross-Cutting Requirements (All Phases)

### 7.1 Audit trail emissions — complete list

Every mutation below MUST emit an audit event via `audit_service.log()` with `actor`, `action`, `entity_type`, `entity_id`, `before_state` (nullable on creates), `after_state`:

| Action string | Trigger |
|---|---|
| `parts_library.part_created` | Manual part creation |
| `parts_library.part_updated` | PATCH to non-approved part |
| `parts_library.part_revision_bumped` | Dimensional update to approved part |
| `parts_library.import_pending` | STEP upload completes parsing |
| `parts_library.import_approved` | Pending import approved |
| `parts_library.import_rejected` | Pending import rejected |
| `parts_library.project_part_added` | ProjectPart created |
| `parts_library.project_part_removed` | ProjectPart deleted |
| `parts_library.system_part_assigned` | SystemPartAssignment created |
| `parts_library.system_part_removed` | SystemPartAssignment deleted |
| `mechanical_joints.joint_created` | MechanicalJoint created |
| `mechanical_joints.joint_updated` | MechanicalJoint updated |
| `mechanical_joints.joint_approved` | Status DRAFT → ACTIVE |
| `mechanical_joints.joint_deleted` | Hard or soft delete |
| `mechanical_joints.assembly_parsed` | Assembly parse job completed |

### 7.2 Structured error codes

Every `HTTPException` in the new routers must include a `code` field:

```python
raise HTTPException(
    status_code=422,
    detail={"detail": "Human-readable message", "code": "SNAKE_CASE_CODE"}
)
```

Required codes:
```
INVALID_FILE_TYPE          Upload endpoint, wrong extension
EMPTY_FILE                 Upload endpoint, zero bytes
PART_NOT_APPROVED          Adding draft part to project
PART_NOT_IN_PROJECT        Joint references part from wrong project
INVALID_FASTENER_TYPE      Fastener_part_id references a non-fastener part
INVALID_SEAL_TYPE          Seal_part_id references a non-seal part
WRONG_STATE                Action not valid for current status
MISSING_REQUIRED_FIELD     Approve without name or part_type
DUPLICATE_PROJECT_PART     Adding same library part twice to a project
HAS_ACTIVE_JOINTS          Removing a part that has active mechanical joints
```

### 7.3 N+1 query prevention — mandatory selectinload list

Every list endpoint must use `selectinload` for any relationship accessed in the response serializer. Required:

```python
# project_parts list
db.query(ProjectPart)
  .options(
    selectinload(ProjectPart.library_part),
    selectinload(ProjectPart.system_assignments),
  )

# mechanical_joints list
db.query(MechanicalJoint)
  .options(
    selectinload(MechanicalJoint.part_a).selectinload(ProjectPart.library_part),
    selectinload(MechanicalJoint.part_b).selectinload(ProjectPart.library_part),
    selectinload(MechanicalJoint.fastener_part),
    selectinload(MechanicalJoint.seal_part),
  )

# system part assignments list
db.query(SystemPartAssignment)
  .options(
    selectinload(SystemPartAssignment.project_part)
      .selectinload(ProjectPart.library_part),
  )
```

### 7.4 No `any` in TypeScript

Run `npx tsc --noEmit --strict` on all new files before committing frontend code. Fix every error. No `as any`, no `// @ts-ignore`.

### 7.5 Form validation

Every form must validate before calling the API. Required fields show red border + helper text when empty. Number fields reject non-numeric input. Decimal fields accept "." as decimal separator and reject "," (European format — the aerospace community uses "." universally).

### 7.6 Loading / empty / error states — required for every data-fetching component

```tsx
// Pattern to follow for every data-fetching component:
if (loading) return <TableSkeleton rows={5} columns={8} />;
if (error)   return <ErrorBanner message={error} onRetry={refetch} />;
if (!data || data.length === 0) return <EmptyState message="..." action={<PrimaryButton>...</PrimaryButton>} />;
return <DataTable ... />;
```

---

## 8. Deferred — Do Not Build

Log these in `PARTS_BUILD_LOG.md` under "Deferred". Do not implement:

- **SolidWorks add-in** — separate spec, separate build.
- **Mass budget rollup** — System-level mass tracking (OQ-2 from spec).
- **ITAR access controls** — `itar_controlled` role-gating (OQ-1).
- **Installation records** — Torque verification records per joint (OQ-3).
- **LOD switching** — Level-of-detail for large assemblies (OQ-7). 500k triangle cap is sufficient.
- **Assembly GLTF with applied transforms** — The `assembly-gltf` endpoint is a stretch goal. If time permits, implement it in Phase 4. If not, the per-part GLTF in part detail is the Phase 4 deliverable.
- **Mating pair detection via OCC geometry proximity** — The stubs in `_detect_mating_pairs`, `_detect_fastener_patterns`, `_detect_seal_grooves` are sufficient for Phase 4. Full OCC-based detection is Phase 5 work.

---

## 9. New Issues Protocol

If you discover something broken or concerning not already in `BACKLOG.md`:

1. If it directly blocks current phase and fix < 5 lines: fix it and document it.
2. Otherwise: add to `PARTS_BUILD_LOG.md` "New Issues" table and continue.
3. If Critical or High severity that would be caught by the original audit criteria: stop and surface.

---

## 10. Final Delivery Checklist

```
[ ] All 4 phases committed with "phase-N-complete" tags in git log
[ ] pytest tests/ -q -m "not performance" → 0 failures, 0 errors
[ ] npm run typecheck → exit 0
[ ] npm run build → "Compiled successfully"
[ ] alembic check → "No new upgrade operations detected"
[ ] All new endpoints in Swagger /docs with correct schemas
[ ] WPN collision test passes (concurrent approve → distinct WPNs)
[ ] STEP duplicate check test passes
[ ] Non-member 403 test passes for all new project-scoped endpoints
[ ] Audit events emitted for all 15 mutation types listed in §7.1
[ ] No .bak files created
[ ] No hardcoded API URLs in frontend (all through axios instance)
[ ] No any types in TypeScript new files
[ ] /projects/1/interfaces still functional with renamed label
[ ] PARTS_BUILD_LOG.md complete
[ ] git log --oneline shows bisectable per-phase commits
```

When complete:
```
PARTS & MECHANICAL MODULE BUILD COMPLETE
Phases: 4/4
New tests: <N>
New migrations: 1 (NNNN_parts_library_and_mechanical)
Final alembic revision: <SHA>
New routes (backend): <N>
New pages (frontend): <N>
See PARTS_BUILD_LOG.md
```

Stop. Do not summarize in chat.

---

## 11. Safety Rails

- **Before Phase 1 migration:** DB snapshot mandatory.
- **`with_for_update()` on WPN assignment:** Non-negotiable. Two concurrent approvals MUST get distinct WPNs.
- **`LibraryPart` immutable after approval:** Dimensional changes create a new revision row. Never overwrite.
- **`ondelete="RESTRICT"` on `project_parts.library_part_id`:** A library part that is in use in a project CANNOT be deleted. This is intentional — it protects data integrity. The UI must surface a clear error message.
- **`ondelete="RESTRICT"` on `mechanical_joints.part_a_id` and `part_b_id`:** A project part that is referenced by a mechanical joint CANNOT be removed from the project without force=true.
- **Never `docker compose down -v`.**
- **Never `alembic downgrade base`.**
- **Never `alembic revision --autogenerate`.**

---

## 12. `PARTS_BUILD_LOG.md` Template

```markdown
# ASTRA Parts Library & Mechanical Module — Build Log
**Started:** <YYYY-MM-DD>
**Spec:** ASTRA-SPEC-PARTS-001 v0.1
**Branch:** feat/parts-mechanical-module
**Pre-flight alembic revision:** <HEAD_BEFORE>
**Pre-flight test count:** <TESTS_BEFORE>
**DB snapshot:** ..\ASTRA-backups\pre_parts_<timestamp>.dump

## Phase Status

| Phase | Status | Commit | Alembic | Tests delta | Build | Notes |
|---|---|---|---|---|---|---|
| 1 — Models, migration, schemas | | | | | — | |
| 2 — Services, routers, tests | | | | | — | |
| 3 — Frontend | | | — | — | | |
| 4 — Assembly parser, 3D, integration | | | — | | | |

## New Issues Discovered

| Date | File:Line | Severity | Description | Action |
|---|---|---|---|---|

## Deferred Items

| Item | Reason | Spec ref |
|---|---|---|
| SolidWorks add-in | Separate spec | OQ-4 |
| Mass budget rollup | OQ-2 | §7 |
| ITAR role-gating | OQ-1 | §3.5.1 |
| Installation records | OQ-3 | §5.1.1 |
| LOD switching | OQ-7 | §6.3 |
| Full OCC mating-pair detection | Phase 5 | §5.2 stages 3-6 |
| Assembly GLTF with transforms | Stretch goal | §6.3 |

## pythonOCC status
Available in container: yes / no
Stub mode active: yes / no
Stub mode impacts: (list affected features)
```
