"""
ASTRA — Supplier & Catalog Layer (global, cross-project master data)
=====================================================================
File: backend/app/models/catalog.py   ← NEW (Phase 1, ASTRA-TDD-INTF-002)

Defines the supplier catalog layer that decouples reusable LRU/part library
data from project-specific placement data. Project-side `Unit`, `Connector`,
`Pin` instantiate from `CatalogPart`, `CatalogConnector`, `CatalogPin` — physics
specs (mass, power, env envelope) live on the catalog entity, never duplicated.

Naming-collision note
---------------------
The existing `app.models.interface` module defines its own `ConnectorGender`
(MALE_PIN/FEMALE_SOCKET/HERMAPHRODITIC/GENDERLESS) and `SignalType` (POWER_PRIMARY,
SIGNAL_DIGITAL_*, …). Those are project-side enums and remain untouched. The
catalog-side enums in this module are intentionally distinct — supplier
perspective (MALE/FEMALE/UNKNOWN, POWER/GROUND/DIGITAL/…). The Postgres ENUM
types are namespaced under `catalog_*` to avoid collision with the existing
`connectorgender` and `signaltype` PG enum types.
"""

from __future__ import annotations

import enum

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Date, Boolean, Numeric, BigInteger,
    Float, ForeignKey, Enum as SQLEnum, Index, JSON, UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


# Use JSONB on PostgreSQL (richer indexing, jsonb_path_ops GIN) but degrade to
# the generic JSON type on SQLite (test environment). The conftest creates all
# tables via Base.metadata.create_all, which can't render JSONB on SQLite.
_JSON = JSON().with_variant(JSONB(), "postgresql")


# ══════════════════════════════════════════════════════════════
#  Enums — catalog-side (distinct from project-side enums in interface.py)
# ══════════════════════════════════════════════════════════════

class PartClass(str, enum.Enum):
    # ── Existing electrical / electronic values (INTF-002) ──
    PROCESSOR        = "processor"
    SENSOR           = "sensor"
    POWER_SUPPLY     = "power_supply"
    RADIO            = "radio"
    ANTENNA          = "antenna"
    ACTUATOR         = "actuator"
    DISPLAY          = "display"
    HARNESS          = "harness"
    CONNECTOR        = "connector_only"
    COMPUTE_MODULE   = "compute_module"
    POWER_DIST       = "power_distribution"
    INTERFACE_CARD   = "interface_card"
    OTHER            = "other"

    # ── TDD-CAT-002: mechanical / structural values ──
    # Added in migration 0029 via ALTER TYPE ... ADD VALUE.
    FASTENER_SCREW       = "fastener_screw"
    FASTENER_BOLT        = "fastener_bolt"
    NUT                  = "nut"
    WASHER               = "washer"
    BRACKET              = "bracket"
    HOUSING              = "housing"
    ENCLOSURE            = "enclosure"
    SEAL_O_RING          = "seal_o_ring"
    BEARING              = "bearing"
    SPRING               = "spring"
    STRUCTURAL_MEMBER    = "structural_member"
    MECHANICAL_OTHER     = "mechanical_other"


class LRUClass(str, enum.Enum):
    LRU              = "lru"
    SRU              = "sru"
    WRA              = "wra"
    SUBASSEMBLY      = "subassembly"
    COMPONENT        = "component"


class LifecycleStatus(str, enum.Enum):
    ACTIVE           = "active"
    PREFERRED        = "preferred"
    OBSOLETE         = "obsolete"
    EOL_ANNOUNCED    = "eol_announced"
    NRND             = "nrnd"
    RESTRICTED       = "restricted"


class ConnectorGender(str, enum.Enum):
    """Catalog-side connector gender (supplier perspective).

    Distinct from the project-side `interface.ConnectorGender` enum which uses
    MALE_PIN/FEMALE_SOCKET/HERMAPHRODITIC/GENDERLESS values for backward
    compatibility with existing project data.
    """
    MALE              = "male"
    FEMALE            = "female"
    HERMAPHRODITIC    = "hermaphroditic"
    UNKNOWN           = "unknown"


class SignalType(str, enum.Enum):
    """Catalog-side signal type (supplier perspective).

    Distinct from the project-side `interface.SignalType` which carries finer
    grain (POWER_PRIMARY, SIGNAL_DIGITAL_DIFFERENTIAL, …). Catalog rolls those
    up into broad categories that map cleanly to vendor datasheets.
    """
    POWER           = "power"
    GROUND          = "ground"
    DIGITAL         = "digital"
    ANALOG          = "analog"
    DIFF_PAIR       = "diff_pair"
    RF              = "rf"
    DISCRETE        = "discrete"
    NO_CONNECT      = "no_connect"
    RESERVED        = "reserved"
    UNKNOWN         = "unknown"


class SignalDirection(str, enum.Enum):
    """Catalog-side signal direction.

    Used both on `CatalogPin.mfr_direction` AND on the project-side
    `Pin.direction_override` (when a project legitimately overrides the
    manufacturer direction for a placed pin). The project-side `interface.py`
    has a separate `PinDirection` enum that includes legacy values like
    OPEN_COLLECTOR, TRI_STATE etc. — those are kept on the existing
    `Pin.direction` column, this enum is the new catalog-aligned scheme.
    """
    INPUT           = "input"
    OUTPUT          = "output"
    BIDIRECTIONAL   = "bidirectional"
    POWER           = "power"
    GROUND          = "ground"
    UNKNOWN         = "unknown"


class SupplierDocumentType(str, enum.Enum):
    ICD            = "icd"
    DATASHEET      = "datasheet"
    SPEC_SHEET     = "spec_sheet"
    DRAWING        = "drawing"
    APP_NOTE       = "app_note"
    USER_MANUAL    = "user_manual"
    OTHER          = "other"
    # CADPORT-REBUILD-002 (AD-5): §6 CITADEL mass-property YAMLs stored
    # as supplier_documents get a truthful document_type. Added to the
    # PG enum in migration 0036 via ALTER TYPE ... ADD VALUE.
    YAML           = "yaml"


class ExtractionStatus(str, enum.Enum):
    UPLOADED         = "uploaded"
    EXTRACTING       = "extracting"
    PENDING_REVIEW   = "pending_review"
    APPROVED         = "approved"
    REJECTED         = "rejected"
    FAILED           = "failed"


class PendingImportStatus(str, enum.Enum):
    PENDING        = "pending"
    APPROVED       = "approved"
    REJECTED       = "rejected"
    SUPERSEDED     = "superseded"


# Postgres ENUM type names — namespaced under `catalog_*` so the catalog-side
# enums do not collide with the existing `connectorgender` and `signaltype`
# Postgres types created by earlier migrations for the project-side enums.
_PG_PART_CLASS = "part_class"
_PG_LRU_CLASS = "lru_class"
_PG_LIFECYCLE_STATUS = "lifecycle_status"
_PG_CATALOG_CONNECTOR_GENDER = "catalog_connector_gender"
_PG_CATALOG_SIGNAL_TYPE = "catalog_signal_type"
_PG_CATALOG_SIGNAL_DIRECTION = "catalog_signal_direction"
_PG_SUPPLIER_DOCUMENT_TYPE = "supplier_document_type"
_PG_EXTRACTION_STATUS = "extraction_status"
_PG_PENDING_IMPORT_STATUS = "pending_import_status"


# ══════════════════════════════════════════════════════════════
#  4.1 Supplier
# ══════════════════════════════════════════════════════════════

class Supplier(Base):
    __tablename__ = "suppliers"

    id                = Column(Integer, primary_key=True)
    name              = Column(String(200), nullable=False, unique=True, index=True)
    short_name        = Column(String(50), nullable=True)
    cage_code         = Column(String(10), nullable=True, index=True)
    duns              = Column(String(15), nullable=True)
    website           = Column(String(500), nullable=True)
    address           = Column(Text, nullable=True)
    country           = Column(String(100), nullable=True)
    primary_contact   = Column(String(200), nullable=True)
    primary_email     = Column(String(200), nullable=True)
    notes             = Column(Text, nullable=True)
    is_active         = Column(Boolean, default=True, nullable=False)
    # TDD-CAT-002: in-house parts default to Wardstone when no vendor is
    # detected from a STEP filename. Migration 0029 seeds Wardstone with
    # is_in_house=True; vendor-detected suppliers default to False.
    is_in_house       = Column(Boolean, default=False, nullable=False)

    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id     = Column(Integer, ForeignKey("users.id"), nullable=False)

    documents         = relationship(
        "SupplierDocument", back_populates="supplier", cascade="all, delete-orphan"
    )
    catalog_parts     = relationship("CatalogPart", back_populates="supplier")
    # TDD-CAT-002: name aliases for vendor auto-detect dedup
    aliases           = relationship(
        "SupplierAlias", back_populates="supplier", cascade="all, delete-orphan"
    )


# ══════════════════════════════════════════════════════════════
#  4.2 SupplierDocument
# ══════════════════════════════════════════════════════════════

class SupplierDocument(Base):
    __tablename__ = "supplier_documents"

    id                = Column(Integer, primary_key=True)
    supplier_id       = Column(
        Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title             = Column(String(500), nullable=False)
    # HAROLD-IN-WRENCH-001 Phase 6 (locked Q2 option a): the actual
    # multipart upload filename, preserved verbatim so HAROLD's
    # /filename-precheck can stem-match against ASTRA's stored
    # documents. Nullable because pre-Phase-6 rows may not have it
    # (migration 0034 backfills from title where title looks like a
    # filename; the rest stay NULL).
    original_filename = Column(String(500), nullable=True, index=True)
    document_type     = Column(
        SQLEnum(
            SupplierDocumentType,
            name=_PG_SUPPLIER_DOCUMENT_TYPE,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    revision          = Column(String(50), nullable=True)
    document_number   = Column(String(200), nullable=True)
    publication_date  = Column(Date, nullable=True)
    file_path         = Column(String(1000), nullable=False)
    file_size_bytes   = Column(BigInteger, nullable=False)
    sha256            = Column(String(64), nullable=False, index=True)
    mime_type         = Column(String(100), nullable=False)
    page_count        = Column(Integer, nullable=True)

    extraction_status = Column(
        SQLEnum(
            ExtractionStatus,
            name=_PG_EXTRACTION_STATUS,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=ExtractionStatus.UPLOADED,
    )
    extraction_log    = Column(_JSON, nullable=True)
    extraction_at     = Column(DateTime(timezone=True), nullable=True)

    uploaded_at       = Column(DateTime(timezone=True), server_default=func.now())
    uploaded_by_id    = Column(Integer, ForeignKey("users.id"), nullable=False)

    supplier          = relationship("Supplier", back_populates="documents")
    pending_imports   = relationship(
        "PendingCatalogImport",
        back_populates="source_document",
        cascade="all, delete-orphan",
    )


# ══════════════════════════════════════════════════════════════
#  4.3 CatalogPart
# ══════════════════════════════════════════════════════════════

class CatalogPart(Base):
    __tablename__ = "catalog_parts"
    __table_args__ = (
        UniqueConstraint(
            "supplier_id", "part_number", "revision", name="uq_catalog_part_pn_rev"
        ),
        Index("ix_catalog_part_search", "part_number", "name"),
        Index("ix_catalog_part_class_status", "part_class", "lifecycle_status"),
    )

    id                  = Column(Integer, primary_key=True)
    supplier_id         = Column(Integer, ForeignKey("suppliers.id"), nullable=False, index=True)
    part_number         = Column(String(200), nullable=False, index=True)
    revision            = Column(String(50), nullable=True)
    name                = Column(String(500), nullable=False)
    designation         = Column(String(200), nullable=True)
    description         = Column(Text, nullable=True)
    part_class          = Column(
        SQLEnum(PartClass, name=_PG_PART_CLASS, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
    )
    lru_classification  = Column(
        SQLEnum(LRUClass, name=_PG_LRU_CLASS, values_callable=lambda x: [e.value for e in x]),
        nullable=False,
        default=LRUClass.LRU,
    )

    # Physical specs
    mass_kg             = Column(Numeric(10, 4), nullable=True)
    dim_length_mm       = Column(Numeric(10, 2), nullable=True)
    dim_width_mm        = Column(Numeric(10, 2), nullable=True)
    dim_height_mm       = Column(Numeric(10, 2), nullable=True)

    # Power
    power_watts_nominal = Column(Numeric(10, 3), nullable=True)
    power_watts_peak    = Column(Numeric(10, 3), nullable=True)
    voltage_input_min_v = Column(Numeric(10, 2), nullable=True)
    voltage_input_max_v = Column(Numeric(10, 2), nullable=True)

    # Environmental envelope
    temp_operating_min_c    = Column(Numeric(6, 2), nullable=True)
    temp_operating_max_c    = Column(Numeric(6, 2), nullable=True)
    temp_storage_min_c      = Column(Numeric(6, 2), nullable=True)
    temp_storage_max_c      = Column(Numeric(6, 2), nullable=True)
    vibration_random_grms   = Column(Numeric(8, 3), nullable=True)
    shock_mechanical_g      = Column(Numeric(8, 2), nullable=True)
    humidity_max_pct        = Column(Numeric(5, 2), nullable=True)
    altitude_max_m          = Column(Numeric(10, 2), nullable=True)
    emi_ce102_limit_dbua    = Column(Numeric(8, 2), nullable=True)
    emi_rs103_limit_vm      = Column(Numeric(8, 2), nullable=True)
    esd_hbm_v               = Column(Numeric(10, 2), nullable=True)

    # Compliance / qual
    mil_std_810_tested  = Column(Boolean, default=False)
    mil_std_461_tested  = Column(Boolean, default=False)
    rohs_compliant      = Column(Boolean, default=False)
    itar_controlled     = Column(Boolean, default=False)
    export_classification = Column(String(50), nullable=True)

    # Lifecycle
    lifecycle_status    = Column(
        SQLEnum(
            LifecycleStatus,
            name=_PG_LIFECYCLE_STATUS,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=LifecycleStatus.ACTIVE,
    )
    eol_date            = Column(Date, nullable=True)

    # Variant tree
    parent_part_id      = Column(
        Integer,
        ForeignKey("catalog_parts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    variant_label       = Column(String(100), nullable=True)

    # Source traceability
    source_document_id  = Column(
        Integer, ForeignKey("supplier_documents.id", ondelete="SET NULL"), nullable=True
    )
    source_page_refs    = Column(_JSON, nullable=True)

    notes               = Column(Text, nullable=True)
    image_path          = Column(String(1000), nullable=True)

    # ════════════════════════════════════════════════════════════
    # TDD-CAT-002: CAD / STEP-derived fields. All nullable — only
    # populated when a part originated from a STEP upload (or was
    # backfilled later). Migration 0029 adds the columns.
    # ════════════════════════════════════════════════════════════
    part_subtype        = Column(String(64), nullable=True, index=True)
    material_name       = Column(String(128), nullable=True)
    material_class      = Column(String(64), nullable=True, index=True)
    bbox_x_mm           = Column(Numeric(10, 3), nullable=True)
    bbox_y_mm           = Column(Numeric(10, 3), nullable=True)
    bbox_z_mm           = Column(Numeric(10, 3), nullable=True)
    volume_mm3          = Column(Numeric(14, 4), nullable=True)
    cad_step_path       = Column(Text, nullable=True)
    cad_preview_path    = Column(Text, nullable=True)
    cad_authoring_tool  = Column(String(64), nullable=True)
    native_units        = Column(String(16), nullable=True)

    # ════════════════════════════════════════════════════════════
    # TDD-HAROLD-INT-002 Phase 1: WPN integration columns.
    # `internal_part_number` is the Wardstone Part Number assigned by
    # HAROLD V2 on approval (e.g. "WS-FH-P000042-A"). NULL means
    # no WPN issued yet — legitimate state for parts uploaded before
    # integration enabled, or while HAROLD is unreachable and the
    # pending import hasn't been approved. The partial unique index
    # in migration 0033 enforces uniqueness only for non-NULL values.
    # `wpn_pending_sync` flags rows that got a fallback (local-allocator)
    # WPN because HAROLD was down at approval time; cleared on manual
    # "Sync with HAROLD" or future reconciliation worker.
    # ════════════════════════════════════════════════════════════
    internal_part_number = Column(String(32), nullable=True, index=True)
    wpn_pending_sync     = Column(Boolean, nullable=False, default=False)

    # ════════════════════════════════════════════════════════════
    # CADPORT-REBUILD-002 (L4 + AD-2/AD-6): CADPORT extraction
    # linkage spine + mass properties parsed out of the §6 part
    # YAML (CITADEL body frame, SI units). All nullable — only
    # populated for parts that originated from a CADPORT SolidWorks
    # extraction. `cadport_part_id` is the immutable §5 spine key
    # (L4: Part ↔ catalog_part). `content_hash` drives the AD-2
    # dedup gate. mass_kg lives above (Numeric, INTF-002); the new
    # physics columns are DOUBLE PRECISION for full precision.
    # Migration 0036 adds the columns.
    # ════════════════════════════════════════════════════════════
    cadport_part_id     = Column(UUID(as_uuid=True), nullable=True, unique=True, index=True)
    content_hash        = Column(String(256), nullable=True, index=True)
    volume_m3           = Column(Float, nullable=True)
    surface_area_m2     = Column(Float, nullable=True)
    density_kg_m3       = Column(Float, nullable=True)
    center_of_mass_x    = Column(Float, nullable=True)
    center_of_mass_y    = Column(Float, nullable=True)
    center_of_mass_z    = Column(Float, nullable=True)
    ixx                 = Column(Float, nullable=True)
    iyy                 = Column(Float, nullable=True)
    izz                 = Column(Float, nullable=True)
    ixy                 = Column(Float, nullable=True)
    ixz                 = Column(Float, nullable=True)
    iyz                 = Column(Float, nullable=True)

    deleted_at          = Column(DateTime(timezone=True), nullable=True, index=True)

    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id       = Column(Integer, ForeignKey("users.id"), nullable=False)

    supplier            = relationship("Supplier", back_populates="catalog_parts")
    source_document     = relationship("SupplierDocument")
    parent_part         = relationship("CatalogPart", remote_side=[id], backref="variants")
    connectors          = relationship(
        "CatalogConnector",
        back_populates="catalog_part",
        cascade="all, delete-orphan",
        order_by="CatalogConnector.position",
    )
    project_units       = relationship("Unit", back_populates="catalog_part")
    # TDD-PROJPARTS-001 (Path C): reverse side of ProjectPart.catalog_part.
    # Every BOM line that has been linked to its canonical catalog row.
    project_part_instances = relationship(
        "ProjectPart", back_populates="catalog_part",
        foreign_keys="ProjectPart.catalog_part_id",
    )


# ══════════════════════════════════════════════════════════════
#  4.3b WpnFallbackSequence (TDD-HAROLD-INT-002 Phase 2)
# ══════════════════════════════════════════════════════════════
#
#  Per-system local counter used by the fallback allocator when
#  HAROLD V2 is unreachable. Migration 0033 creates the table and
#  seeds all 21 codes at next_index=1. ORM coverage here so
#  Base.metadata.create_all picks the table up in SQLite test
#  environments — production still runs through the Alembic
#  migration.

class WpnFallbackSequence(Base):
    __tablename__ = "catalog_wpn_fallback_sequences"

    system_code = Column(String(2), primary_key=True)
    next_index  = Column(Integer, nullable=False, default=1)
    updated_at  = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

    def __repr__(self) -> str:  # pragma: no cover — debug only
        return f"<WpnFallbackSequence {self.system_code} next={self.next_index}>"


# ══════════════════════════════════════════════════════════════
#  4.4 CatalogConnector
# ══════════════════════════════════════════════════════════════

class CatalogConnector(Base):
    __tablename__ = "catalog_connectors"
    __table_args__ = (
        UniqueConstraint("catalog_part_id", "reference", name="uq_catalog_connector_ref"),
        Index("ix_catalog_connector_part", "catalog_part_id"),
    )

    id                  = Column(Integer, primary_key=True)
    catalog_part_id     = Column(
        Integer, ForeignKey("catalog_parts.id", ondelete="CASCADE"), nullable=False
    )
    reference            = Column(String(50), nullable=False)
    position             = Column(Integer, nullable=False, default=0)
    description          = Column(String(500), nullable=True)
    connector_type       = Column(String(100), nullable=True)
    shell_size           = Column(String(50), nullable=True)
    insert_arrangement   = Column(String(50), nullable=True)
    gender               = Column(
        SQLEnum(
            ConnectorGender,
            name=_PG_CATALOG_CONNECTOR_GENDER,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )
    pin_count            = Column(Integer, nullable=False, default=0)
    keying               = Column(String(50), nullable=True)
    mating_part_number   = Column(String(200), nullable=True)
    notes                = Column(Text, nullable=True)

    catalog_part         = relationship("CatalogPart", back_populates="connectors")
    pins                 = relationship(
        "CatalogPin",
        back_populates="catalog_connector",
        cascade="all, delete-orphan",
        order_by="CatalogPin.pin_position",
    )


# ══════════════════════════════════════════════════════════════
#  4.5 CatalogPin
# ══════════════════════════════════════════════════════════════

class CatalogPin(Base):
    __tablename__ = "catalog_pins"
    __table_args__ = (
        UniqueConstraint(
            "catalog_connector_id", "pin_position", name="uq_catalog_pin_position"
        ),
        Index("ix_catalog_pin_connector", "catalog_connector_id"),
    )

    id                  = Column(Integer, primary_key=True)
    catalog_connector_id = Column(
        Integer,
        ForeignKey("catalog_connectors.id", ondelete="CASCADE"),
        nullable=False,
    )
    pin_position        = Column(String(20), nullable=False)

    # ── Manufacturer-locked fields (immutable in projects) ──
    mfr_pin_name        = Column(String(100), nullable=False)
    mfr_signal_function = Column(String(500), nullable=True)
    mfr_signal_type     = Column(
        SQLEnum(
            SignalType,
            name=_PG_CATALOG_SIGNAL_TYPE,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
    )
    mfr_direction       = Column(
        SQLEnum(
            SignalDirection,
            name=_PG_CATALOG_SIGNAL_DIRECTION,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=True,
        default=SignalDirection.UNKNOWN,
    )
    mfr_voltage_min_v   = Column(Numeric(8, 3), nullable=True)
    mfr_voltage_max_v   = Column(Numeric(8, 3), nullable=True)
    mfr_current_max_ma  = Column(Numeric(10, 3), nullable=True)
    mfr_impedance_ohm   = Column(Numeric(10, 2), nullable=True)
    mfr_protocol_hint   = Column(String(100), nullable=True)
    mfr_is_paired_with  = Column(String(50), nullable=True)

    is_no_connect       = Column(Boolean, default=False)
    is_reserved         = Column(Boolean, default=False)
    is_chassis_ground   = Column(Boolean, default=False)

    notes               = Column(Text, nullable=True)

    catalog_connector   = relationship("CatalogConnector", back_populates="pins")


# ══════════════════════════════════════════════════════════════
#  4.8 PendingCatalogImport
# ══════════════════════════════════════════════════════════════

class PendingCatalogImport(Base):
    __tablename__ = "pending_catalog_imports"

    id                       = Column(Integer, primary_key=True)
    source_document_id       = Column(
        Integer,
        ForeignKey("supplier_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    supplier_id              = Column(Integer, ForeignKey("suppliers.id"), nullable=False)

    extracted_data           = Column(_JSON, nullable=False)
    extraction_warnings      = Column(_JSON, nullable=True)
    extraction_confidence    = Column(Numeric(4, 3), nullable=True)

    status                   = Column(
        SQLEnum(
            PendingImportStatus,
            name=_PG_PENDING_IMPORT_STATUS,
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
        default=PendingImportStatus.PENDING,
    )

    committed_catalog_part_id = Column(
        Integer, ForeignKey("catalog_parts.id", ondelete="SET NULL"), nullable=True
    )

    rejection_reason         = Column(Text, nullable=True)
    reviewer_notes           = Column(Text, nullable=True)

    created_at               = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at              = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_id           = Column(Integer, ForeignKey("users.id"), nullable=True)

    source_document          = relationship("SupplierDocument", back_populates="pending_imports")


# ══════════════════════════════════════════════════════════════
#  TDD-CAT-002 — Supplier alias map (vendor-name dedup)
# ══════════════════════════════════════════════════════════════

class SupplierAlias(Base):
    """Maps alternate-spelling vendor names back to their canonical Supplier.

    Used by the STEP-upload supplier resolver: a filename matching a
    McMaster-Carr regex emits the canonical name "McMaster-Carr" plus the
    alias list ["McMaster", "MCMASTER", ...]. The resolver looks up via
    case-insensitive alias match before falling back to ``suppliers.name``.
    """

    __tablename__ = "supplier_aliases"

    id          = Column(BigInteger, primary_key=True)
    supplier_id = Column(
        Integer,
        ForeignKey("suppliers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    alias       = Column(String(255), nullable=False, unique=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    supplier    = relationship("Supplier", back_populates="aliases")


# ══════════════════════════════════════════════════════════════
#  CADPORT-REBUILD-002 — Assembly ↔ Project linkage (L7)
# ══════════════════════════════════════════════════════════════
#
#  An assembly extracted through CADPORT attaches to exactly one
#  ASTRA project (vehicle variant). The assembly_id UUID is the
#  immutable §5 spine key assigned in TDD-1. Component parts are
#  mapped via CadportAssemblyComponent — each row points at the
#  catalog_part that L4 created for that component (NULL until the
#  part is imported / deduped). Migration 0036 creates both tables.

class CadportAssembly(Base):
    __tablename__ = "cadport_assemblies"

    id                        = Column(Integer, primary_key=True)
    assembly_id               = Column(UUID(as_uuid=True), nullable=False, unique=True, index=True)
    project_id                = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name              = Column(String(500), nullable=False)
    source_file               = Column(String(500), nullable=False)
    content_hash              = Column(String(256), nullable=True, index=True)
    total_mass_kg             = Column(Float, nullable=True)
    center_of_mass_x          = Column(Float, nullable=True)
    center_of_mass_y          = Column(Float, nullable=True)
    center_of_mass_z          = Column(Float, nullable=True)
    component_count           = Column(Integer, nullable=False, default=0)
    solidworks_version        = Column(String(64), nullable=True)
    assembly_yaml_document_id = Column(
        Integer, ForeignKey("supplier_documents.id", ondelete="SET NULL"), nullable=True
    )
    created_at                = Column(DateTime(timezone=True), server_default=func.now())
    updated_at                = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    components = relationship(
        "CadportAssemblyComponent",
        back_populates="assembly",
        cascade="all, delete-orphan",
    )
    assembly_yaml_document = relationship("SupplierDocument")


class CadportAssemblyComponent(Base):
    __tablename__ = "cadport_assembly_components"

    id              = Column(Integer, primary_key=True)
    assembly_id     = Column(
        Integer,
        ForeignKey("cadport_assemblies.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    catalog_part_id = Column(
        Integer,
        ForeignKey("catalog_parts.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # The §5 spine key for the component part — survives even if the
    # catalog_part link is later nulled.
    cadport_part_id = Column(UUID(as_uuid=True), nullable=True)
    instance_name   = Column(String(500), nullable=False)
    quantity        = Column(Integer, nullable=False, default=1)
    transform_json  = Column(Text, nullable=True)  # 4x4 matrix as JSON
    suppressed      = Column(Boolean, nullable=False, default=False)

    assembly        = relationship("CadportAssembly", back_populates="components")
    catalog_part    = relationship("CatalogPart")
