"""
ASTRA — Parts Library & Mechanical Joints — model layer
========================================================
File: backend/app/models/parts_library.py   ← NEW (ASTRA-SPEC-PARTS-001)

Six new tables + 13 new enums. All measurement fields use Numeric()
(Float is banned — F-031). All SQLEnum columns include
``values_callable=lambda x: [e.value for e in x]`` (F-016).
"""

from __future__ import annotations

import enum

from sqlalchemy import (
    Column, Integer, String, Text, Boolean, DateTime, Date,
    Numeric, ForeignKey, UniqueConstraint, Index, BigInteger,
    Enum as SQLEnum, JSON, ARRAY,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func, text

from app.database import Base


# JSONB on PostgreSQL, plain JSON on SQLite (test environment).
_JSON = JSON().with_variant(JSONB(), "postgresql")


# ══════════════════════════════════════════════════════════════
#  Enums  (defined BEFORE any model so SQLAlchemy resolves them)
# ══════════════════════════════════════════════════════════════

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
    ALUMINUM        = "aluminum"
    TITANIUM        = "titanium"
    STEEL           = "steel"
    STAINLESS_STEEL = "stainless_steel"
    NICKEL_ALLOY    = "nickel_alloy"
    POLYMER         = "polymer"
    COMPOSITE       = "composite"
    CERAMIC         = "ceramic"
    OTHER           = "other"


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
    BOLTED        = "bolted"
    RIVETED       = "riveted"
    PRESS_FIT     = "press_fit"
    ADHESIVE      = "adhesive"
    WELD          = "weld"
    SEAL          = "seal"
    ALIGNMENT_PIN = "alignment_pin"
    THERMAL_BOND  = "thermal_bond"
    SPRING_CLIP   = "spring_clip"


class JointStatus(str, enum.Enum):
    DRAFT      = "draft"
    ACTIVE     = "active"
    SUPERSEDED = "superseded"


class AssemblyParseJobStatus(str, enum.Enum):
    QUEUED   = "queued"
    RUNNING  = "running"
    COMPLETE = "complete"
    FAILED   = "failed"


# TDD-PROJPARTS-001 (Path C): BOM lifecycle on every project_parts row.
# Matches the bom_status PG enum created in migration 0030.
class BomStatus(str, enum.Enum):
    PLANNED   = "planned"
    RELEASED  = "released"
    PROCURED  = "procured"
    RECEIVED  = "received"
    INSTALLED = "installed"
    VERIFIED  = "verified"
    OBSOLETE  = "obsolete"


# Postgres ENUM type names — namespaced so they don't collide with
# Python enum names but match what the migration creates.
_PG_PART_TYPE                = "part_type"
_PG_PART_STATUS              = "part_status"
_PG_MATERIAL_CLASS           = "material_class"
_PG_THREAD_STANDARD          = "thread_standard"
_PG_HEAD_TYPE                = "head_type"
_PG_DRIVE_TYPE               = "drive_type"
_PG_LOCKING_FEATURE          = "locking_feature"
_PG_QUALIFICATION_STATUS     = "qualification_status"
_PG_PENDING_PARTS_STATUS     = "pending_parts_status"
_PG_CONFIDENCE_LEVEL         = "confidence_level"
_PG_JOINT_TYPE               = "joint_type"
_PG_JOINT_STATUS             = "joint_status"
_PG_ASSEMBLY_PARSE_JOB_STATUS = "assembly_parse_job_status"
_PG_BOM_STATUS               = "bom_status"


# Helper: standardised SQLEnum builder
def _enum(py_enum, pg_name):
    return SQLEnum(
        py_enum,
        name=pg_name,
        values_callable=lambda x: [e.value for e in x],
    )


# ══════════════════════════════════════════════════════════════
#  WPN Sequence — atomic Wardstone Part Number generator
# ══════════════════════════════════════════════════════════════

class WPNSequence(Base):
    __tablename__ = "wpn_sequences"

    part_type_code = Column(String(8), primary_key=True)  # "FAST", "WASH" etc.
    next_val       = Column(Integer, nullable=False, default=1)


# ══════════════════════════════════════════════════════════════
#  LibraryPart  — global cross-project parts master record
# ══════════════════════════════════════════════════════════════

class LibraryPart(Base):
    __tablename__ = "library_parts"
    __table_args__ = (
        UniqueConstraint("wardstone_part_number", name="uq_library_part_wpn"),
        Index("ix_library_part_type_status", "part_type", "status"),
        Index("ix_library_part_step_checksum", "step_file_checksum"),
        Index("ix_library_part_mpn", "manufacturer_part_number"),
    )

    id                       = Column(Integer, primary_key=True, index=True)

    # ── Identification ─────────────────────────────────────────
    wardstone_part_number    = Column(String(32), nullable=False, unique=True)
    revision                 = Column(String(2), nullable=False, default="00")
    part_type                = Column(_enum(PartType, _PG_PART_TYPE),
                                       nullable=False, index=True)
    name                     = Column(String(500), nullable=False)
    description              = Column(Text, nullable=True)
    manufacturer_part_number = Column(String(200), nullable=True, index=True)
    manufacturer_name        = Column(String(200), nullable=True)
    cage_code                = Column(String(10), nullable=True)
    nsn                      = Column(String(20), nullable=True)
    drawing_number           = Column(String(200), nullable=True)
    drawing_revision         = Column(String(20), nullable=True)
    heritage                 = Column(Text, nullable=True)
    status                   = Column(_enum(PartStatus, _PG_PART_STATUS),
                                       nullable=False, default=PartStatus.DRAFT,
                                       index=True)
    superseded_by_id         = Column(
        Integer,
        ForeignKey("library_parts.id", ondelete="SET NULL"),
        nullable=True,
    )

    # ── Dimensional ────────────────────────────────────────────
    bounding_box_x_mm        = Column(Numeric(12, 4), nullable=True)
    bounding_box_y_mm        = Column(Numeric(12, 4), nullable=True)
    bounding_box_z_mm        = Column(Numeric(12, 4), nullable=True)
    volume_mm3               = Column(Numeric(18, 4), nullable=True)
    surface_area_mm2         = Column(Numeric(18, 4), nullable=True)
    thread_size              = Column(String(50), nullable=True)
    thread_standard          = Column(_enum(ThreadStandard, _PG_THREAD_STANDARD),
                                       nullable=True)
    nominal_diameter_mm      = Column(Numeric(12, 4), nullable=True)
    nominal_length_mm        = Column(Numeric(12, 4), nullable=True)
    head_type                = Column(_enum(HeadType, _PG_HEAD_TYPE), nullable=True)
    drive_type               = Column(_enum(DriveType, _PG_DRIVE_TYPE), nullable=True)
    nominal_bore_mm          = Column(Numeric(12, 4), nullable=True)
    cross_section_dia_mm     = Column(Numeric(12, 4), nullable=True)
    flange_diameter_mm       = Column(Numeric(12, 4), nullable=True)
    hole_pattern_count       = Column(Integer, nullable=True)
    hole_pattern_dia_mm      = Column(Numeric(12, 4), nullable=True)
    hole_pattern_pcd_mm      = Column(Numeric(12, 4), nullable=True)

    # ── Material ───────────────────────────────────────────────
    material_name            = Column(String(200), nullable=True)
    material_standard        = Column(String(200), nullable=True)
    material_class           = Column(_enum(MaterialClass, _PG_MATERIAL_CLASS),
                                       nullable=True)
    density_g_cm3            = Column(Numeric(10, 4), nullable=True)
    yield_strength_mpa       = Column(Numeric(10, 2), nullable=True)
    ultimate_strength_mpa    = Column(Numeric(10, 2), nullable=True)
    elastic_modulus_gpa      = Column(Numeric(10, 2), nullable=True)
    hardness                 = Column(String(50), nullable=True)
    thermal_conductivity_wm  = Column(Numeric(10, 4), nullable=True)
    cte_um_m_c               = Column(Numeric(10, 4), nullable=True)
    corrosion_protection     = Column(String(200), nullable=True)
    flammability_class       = Column(String(100), nullable=True)
    outgassing_tml_pct       = Column(Numeric(8, 4), nullable=True)
    outgassing_cvcm_pct      = Column(Numeric(8, 4), nullable=True)

    # ── Mechanical performance ─────────────────────────────────
    mass_nominal_g           = Column(Numeric(12, 4), nullable=True)
    mass_max_g               = Column(Numeric(12, 4), nullable=True)
    proof_load_n             = Column(Numeric(12, 2), nullable=True)
    clamp_load_n             = Column(Numeric(12, 2), nullable=True)
    torque_nominal_nm        = Column(Numeric(10, 4), nullable=True)
    torque_min_nm            = Column(Numeric(10, 4), nullable=True)
    torque_max_nm            = Column(Numeric(10, 4), nullable=True)
    torque_lubricated_nm     = Column(Numeric(10, 4), nullable=True)
    locking_feature          = Column(_enum(LockingFeature, _PG_LOCKING_FEATURE),
                                       nullable=True, default=LockingFeature.NONE)
    safety_wire_holes        = Column(Boolean, nullable=True)
    shear_strength_n         = Column(Numeric(12, 2), nullable=True)
    bearing_load_n           = Column(Numeric(12, 2), nullable=True)
    compression_set_pct      = Column(Numeric(8, 2), nullable=True)
    sealing_pressure_max_bar = Column(Numeric(10, 3), nullable=True)
    temperature_min_c        = Column(Numeric(8, 2), nullable=True)
    temperature_max_c        = Column(Numeric(8, 2), nullable=True)

    # ── Procurement & lifecycle ────────────────────────────────
    unit_cost_usd            = Column(Numeric(12, 4), nullable=True)
    lead_time_weeks          = Column(Integer, nullable=True)
    min_order_qty            = Column(Integer, nullable=True)
    preferred_supplier_id    = Column(
        Integer, ForeignKey("suppliers.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    supplier_part_number     = Column(String(200), nullable=True)
    qualification_status     = Column(_enum(QualificationStatus, _PG_QUALIFICATION_STATUS),
                                       nullable=True,
                                       default=QualificationStatus.UNQUALIFIED)
    qualification_basis      = Column(Text, nullable=True)
    shelf_life_months        = Column(Integer, nullable=True)
    date_of_manufacture      = Column(Date, nullable=True)
    restricted_use           = Column(Boolean, nullable=False, default=False)
    restriction_notes        = Column(Text, nullable=True)

    # ── STEP file traceability ─────────────────────────────────
    step_file_id             = Column(
        Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True,
    )
    step_file_checksum       = Column(String(64), nullable=True)
    step_entity_id           = Column(String(200), nullable=True)

    # ── Approval / audit ───────────────────────────────────────
    approved_by_id           = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    approved_at              = Column(DateTime(timezone=True), nullable=True)
    created_at               = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at               = Column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
    created_by_id            = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    # ── Relationships ──────────────────────────────────────────
    superseded_by      = relationship(
        "LibraryPart", remote_side=[id], foreign_keys=[superseded_by_id],
    )
    preferred_supplier = relationship("Supplier", foreign_keys=[preferred_supplier_id])
    approved_by        = relationship("User", foreign_keys=[approved_by_id])
    created_by         = relationship("User", foreign_keys=[created_by_id])
    project_parts      = relationship("ProjectPart", back_populates="library_part")
    fastener_joints    = relationship(
        "MechanicalJoint",
        foreign_keys="MechanicalJoint.fastener_part_id",
        back_populates="fastener_part",
    )
    seal_joints        = relationship(
        "MechanicalJoint",
        foreign_keys="MechanicalJoint.seal_part_id",
        back_populates="seal_part",
    )


# ══════════════════════════════════════════════════════════════
#  PendingPartsImport  — STEP upload review queue
# ══════════════════════════════════════════════════════════════

class PendingPartsImport(Base):
    __tablename__ = "pending_parts_imports"

    id                    = Column(Integer, primary_key=True, index=True)
    document_id           = Column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    status                = Column(_enum(PendingPartsStatus, _PG_PENDING_PARTS_STATUS),
                                    nullable=False,
                                    default=PendingPartsStatus.PENDING, index=True)
    proposed_data         = Column(_JSON, nullable=False, default=dict)
    confidence_scores     = Column(_JSON, nullable=False, default=dict)
    # SQLite test env: store as JSON; PostgreSQL: native ARRAY(TEXT).
    low_confidence_fields = Column(
        ARRAY(String).with_variant(JSON(), "sqlite"),
        nullable=False,
        default=list,
    )
    extraction_log        = Column(Text, nullable=True)
    parser_version        = Column(String(32), nullable=True)
    reviewed_by_id        = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    reviewed_at           = Column(DateTime(timezone=True), nullable=True)
    rejection_reason      = Column(Text, nullable=True)
    library_part_id       = Column(
        Integer, ForeignKey("library_parts.id", ondelete="SET NULL"),
        nullable=True,
    )  # set on approval
    created_at            = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at            = Column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
    created_by_id         = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    document      = relationship("Document")
    reviewed_by   = relationship("User", foreign_keys=[reviewed_by_id])
    library_part  = relationship("LibraryPart")


# ══════════════════════════════════════════════════════════════
#  ProjectPart  — join: project ↔ library_part
# ══════════════════════════════════════════════════════════════

class ProjectPart(Base):
    """Project-scoped BOM line.

    TDD-PROJPARTS-001 (Path C) extended this model in place — same
    table, FKs to library_part_id (legacy) AND catalog_part_id (new
    canonical) coexist. mechanical_joints and system_part_assignments
    keep their FKs to project_parts(id) intact.

    `added_at` / `added_by_id` are kept for backward compat with the
    original 0027 schema; new code reads them through the
    `created_at` / `created_by_id` aliases below.
    """

    __tablename__ = "project_parts"
    # Migration 0030 dropped uq_project_part(project_id, library_part_id) and
    # replaced it with a partial UNIQUE on (project_id, bom_position) WHERE
    # bom_position IS NOT NULL. The partial index is created at the DDL level
    # (alembic) — we don't redeclare it here because SQLAlchemy can't express
    # partial uniqueness on Index/UniqueConstraint constructs cleanly across
    # the SQLite test path either.
    # Single-column indexes are auto-created from `index=True` on each
    # Column. The partial UNIQUE on (project_id, bom_position) is the
    # only multi-column / partial declaration that needs to live here
    # so both Postgres (prod, via Alembic) and SQLite (tests, via
    # Base.metadata.create_all) enforce it identically.
    __table_args__ = (
        Index(
            "uq_project_parts_bom_position",
            "project_id", "bom_position",
            unique=True,
            postgresql_where=text("bom_position IS NOT NULL"),
            sqlite_where=text("bom_position IS NOT NULL"),
        ),
    )

    id              = Column(Integer, primary_key=True, index=True)
    project_id      = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    # PROJPARTS-001 Path C: library_part_id is now optional — catalog
    # parts are the canonical BOM reference and may be the only link
    # on a line. Migration 0031 drops the NOT NULL in PostgreSQL.
    library_part_id = Column(
        Integer, ForeignKey("library_parts.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )

    # ── TDD-PROJPARTS-001: canonical catalog link, nullable today
    #    (legacy rows have no catalog mapping yet). New writes from
    #    the BOM router populate this on every create.
    catalog_part_id = Column(
        Integer, ForeignKey("catalog_parts.id", ondelete="RESTRICT"),
        nullable=True, index=True,
    )

    # Quantity is now NUMERIC(12,4); fractional units (3.5 m, 0.25 L)
    # are legal. Default 1.0 preserves the existing default semantic.
    quantity        = Column(Numeric(12, 4), nullable=False, default=1)
    quantity_unit   = Column(
        String(16), nullable=False, server_default="each", default="each",
    )

    designation     = Column(String(255), nullable=True)
    bom_position    = Column(String(64), nullable=True)
    parent_bom_id   = Column(
        Integer, ForeignKey("project_parts.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    status          = Column(
        _enum(BomStatus, _PG_BOM_STATUS),
        nullable=False,
        server_default=BomStatus.PLANNED.value,
        default=BomStatus.PLANNED,
        index=True,
    )

    unit_id         = Column(
        Integer, ForeignKey("units.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )

    location_zone      = Column(String(128), nullable=True)
    installation_notes = Column(Text, nullable=True)
    procurement_notes  = Column(Text, nullable=True)
    notes              = Column(Text, nullable=True)

    added_by_id     = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    added_at        = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at      = Column(
        DateTime(timezone=True),
        server_default=func.now(), onupdate=func.now(), nullable=False,
    )

    project            = relationship("Project")
    library_part       = relationship("LibraryPart", back_populates="project_parts")
    catalog_part       = relationship(
        "CatalogPart", back_populates="project_part_instances",
        foreign_keys=[catalog_part_id],
    )
    added_by           = relationship("User")
    linked_unit        = relationship(
        "Unit", foreign_keys=[unit_id],
    )
    parent_bom         = relationship(
        "ProjectPart", remote_side=[id], foreign_keys=[parent_bom_id],
    )
    system_assignments = relationship(
        "SystemPartAssignment",
        back_populates="project_part",
        cascade="all, delete-orphan",
    )


# ══════════════════════════════════════════════════════════════
#  SystemPartAssignment  — join: system ↔ project_part
# ══════════════════════════════════════════════════════════════

class SystemPartAssignment(Base):
    __tablename__ = "system_part_assignments"
    __table_args__ = (
        UniqueConstraint(
            "system_id", "project_part_id", name="uq_system_part_assignment",
        ),
        Index("ix_spa_system", "system_id"),
        Index("ix_spa_ppart", "project_part_id"),
    )

    id              = Column(Integer, primary_key=True, index=True)
    system_id       = Column(
        Integer, ForeignKey("systems.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    project_part_id = Column(
        Integer, ForeignKey("project_parts.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    position_order  = Column(Integer, nullable=False, default=0)
    assigned_by_id  = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    assigned_at     = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    system       = relationship("System")
    project_part = relationship("ProjectPart", back_populates="system_assignments")
    assigned_by  = relationship("User")


# ══════════════════════════════════════════════════════════════
#  MechanicalJointSequence  — atomic joint_id generator (per project)
# ══════════════════════════════════════════════════════════════

class MechanicalJointSequence(Base):
    __tablename__ = "mechanical_joint_sequences"

    project_id = Column(Integer, primary_key=True)
    next_val   = Column(Integer, nullable=False, default=1)


# ══════════════════════════════════════════════════════════════
#  AssemblyParseJob  — background parser tracking
# ══════════════════════════════════════════════════════════════

class AssemblyParseJob(Base):
    __tablename__ = "assembly_parse_jobs"
    __table_args__ = (
        Index("ix_apj_project", "project_id"),
        Index("ix_apj_status", "status"),
    )

    id            = Column(Integer, primary_key=True, index=True)
    project_id    = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    document_id   = Column(
        Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True,
    )
    status        = Column(
        _enum(AssemblyParseJobStatus, _PG_ASSEMBLY_PARSE_JOB_STATUS),
        nullable=False, default=AssemblyParseJobStatus.QUEUED, index=True,
    )
    progress_log  = Column(Text, nullable=True)
    result        = Column(_JSON, nullable=True)
    error         = Column(Text, nullable=True)
    created_by_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    created_at    = Column(DateTime(timezone=True), server_default=func.now())
    completed_at  = Column(DateTime(timezone=True), nullable=True)

    project    = relationship("Project")
    document   = relationship("Document")
    created_by = relationship("User")


# ══════════════════════════════════════════════════════════════
#  MechanicalJoint  — joint between two ProjectParts
# ══════════════════════════════════════════════════════════════

class MechanicalJoint(Base):
    __tablename__ = "mechanical_joints"
    __table_args__ = (
        Index("ix_mj_project_status", "project_id", "status"),
        Index("ix_mj_parts", "part_a_id", "part_b_id"),
        Index("ix_mj_joint_id", "joint_id"),
    )

    id                         = Column(Integer, primary_key=True, index=True)
    joint_id                   = Column(String(32), unique=True, nullable=False, index=True)
    project_id                 = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    joint_type                 = Column(_enum(JointType, _PG_JOINT_TYPE),
                                         nullable=False)
    part_a_id                  = Column(
        Integer, ForeignKey("project_parts.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    part_b_id                  = Column(
        Integer, ForeignKey("project_parts.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    fastener_part_id           = Column(
        Integer, ForeignKey("library_parts.id", ondelete="SET NULL"),
        nullable=True,
    )
    fastener_count             = Column(Integer, nullable=True)
    torque_nominal_nm          = Column(Numeric(10, 4), nullable=True)
    torque_min_nm              = Column(Numeric(10, 4), nullable=True)
    torque_max_nm              = Column(Numeric(10, 4), nullable=True)
    engagement_length_mm       = Column(Numeric(10, 4), nullable=True)
    locking_feature            = Column(_enum(LockingFeature, _PG_LOCKING_FEATURE),
                                         nullable=True)
    hole_pattern_description   = Column(String(300), nullable=True)
    mating_surface_flatness_mm = Column(Numeric(10, 4), nullable=True)
    mating_surface_finish_ra   = Column(Numeric(10, 4), nullable=True)
    seal_part_id               = Column(
        Integer, ForeignKey("library_parts.id", ondelete="SET NULL"),
        nullable=True,
    )
    leak_rate_max_scc_s        = Column(Numeric(12, 6), nullable=True)
    test_pressure_bar          = Column(Numeric(10, 3), nullable=True)
    interface_drawing          = Column(String(200), nullable=True)
    source_step_file_id        = Column(
        Integer, ForeignKey("documents.id", ondelete="SET NULL"), nullable=True,
    )
    source_step_entity         = Column(Text, nullable=True)
    confidence                 = Column(_enum(ConfidenceLevel, _PG_CONFIDENCE_LEVEL),
                                         nullable=True)
    status                     = Column(_enum(JointStatus, _PG_JOINT_STATUS),
                                         nullable=False, default=JointStatus.DRAFT,
                                         index=True)
    notes                      = Column(Text, nullable=True)
    created_at                 = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at                 = Column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )
    created_by_id              = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )

    project       = relationship("Project")
    part_a        = relationship("ProjectPart", foreign_keys=[part_a_id])
    part_b        = relationship("ProjectPart", foreign_keys=[part_b_id])
    fastener_part = relationship(
        "LibraryPart", foreign_keys=[fastener_part_id],
        back_populates="fastener_joints",
    )
    seal_part     = relationship(
        "LibraryPart", foreign_keys=[seal_part_id],
        back_populates="seal_joints",
    )
    source_file   = relationship("Document", foreign_keys=[source_step_file_id])
    created_by    = relationship("User")
