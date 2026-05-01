# ASTRA — Interface Module Foundation Refactor & Supplier Catalog Integration

**Document ID:** ASTRA-TDD-INTF-002
**Version:** 1.1
**Status:** Approved for Implementation
**Author Intent:** Mason
**Target Executor:** Claude Code
**Repository:** V2Ballistic/ASTRA_Wardstone
**Codebase Root:** `C:\Users\Mason\Documents\ASTRA\`
**Active Project:** SMDS (project_id=1)
**User:** mason / password123 (user_id=1, admin)

**Changelog v1.1:**
- §9 Auto-wire revised to **three-way validation**: internal_signal_name match + direction compatibility + LRU endpoint validation
- §6 RBAC clarified: **admin role bypasses all approval gates** (catalog imports, sync proposals, coverage exceptions)
- New §8 **Database Robustness & Indexing Strategy** for high-volume catalog data
- §14 Catalog Placement UX rewritten: explicit **"Existing from catalog vs Brand new"** flow
- New §12 **Reactive Requirement Sync Engine** — auto-generated requirements update when source data (system, LRU, connection, wire, signal) changes
- New §13 **Requirement Source Coverage Validator** — every L3-L5 requirement (and most L2) must trace to a real interface element

---

## 0. Executive Summary

This document specifies a foundational refactor of ASTRA's Interface Module to introduce a **global Supplier & LRU/Catalog layer** that decouples reusable part library data from project-specific placement data. It also defines:

- **ICD/Datasheet ingestion** via direct Anthropic API → review queue → catalog commit
- **Dual pin-naming** (manufacturer name locked + internal signal name editable)
- **Three-way auto-wire validation** (name + direction + LRU endpoint)
- **Connection Builder** wizard for fast unit-to-unit integration
- **Reactive Requirement Sync** — when source data changes, derived requirements automatically re-render and surface for review
- **Source Coverage Validator** — flag any L3-L5 requirement without a real architectural source

This refactor is load-bearing. It must be completed before the Test Integration Module (ASTRA-TDD-TEST-001) and Phase 2 Communication Module are built on top of it.

---

## 1. Goals & Non-Goals

### Goals

1. **Top-level master library.** Suppliers and LRUs/CatalogParts are global, cross-project, master-data entities. A part bought once is available forever. Creating a new project never duplicates LRU specs — it points to the master.
2. **New-project ergonomics.** When adding an LRU to a project, the user is asked once: "Pick from existing catalog" or "Create brand new". Brand-new entries always land in the global catalog and are immediately available to all other projects.
3. **Data integrity.** Project Units *instantiate* CatalogParts. Physics specs (mass, power, env envelopes, EMI limits) live on the catalog entry, never duplicated.
4. **ICD-to-database pipeline.** Uploading a vendor ICD/datasheet (PDF/DOCX/XLSX) automatically populates the entire catalog entry — supplier, part identity, connectors, pin table, environmental specs — with full audit chain-of-custody back to the source document.
5. **Dual pin naming.** Every pin carries both the manufacturer's name (locked from the datasheet) and the user's internal signal name (editable, project-scoped).
6. **Three-way auto-wire.** Auto-wire pairs two pins only when **all three** conditions hold: matching internal_signal_name, compatible directions (input↔output or bidirectional), correct LRU endpoint per the declared Interface.
7. **Reactive requirements.** When any source data (system rename, LRU swap, connection edit, wire change, signal rename) is modified, every auto-generated requirement linked to that data is automatically re-rendered and surfaced for review.
8. **Source coverage.** Every requirement at L3, L4, L5 (and most L2) must have a documented source: a wire, a signal, a bus message, an LRU connection, or a parent requirement chain. Orphan requirements at these levels are flagged.
9. **Admin override.** Admin users bypass all approval gates — for catalog imports, sync proposals, coverage exceptions, and lock states.
10. **Database robustness.** The schema and indexes are designed to handle catalogs with 10,000+ parts, 100,000+ pins, and projects with 1,000+ requirements without query degradation.

### Non-Goals

- This refactor does not implement the Test Integration Module (separate TDD).
- This refactor does not implement bit-level protocol modeling (Phase 2 Communication Module — separate spec).
- This refactor does not change auth, RBAC infrastructure, or audit-log infrastructure (only adds new permission scopes).

---

## 2. Current State (As of Migration 0007)

The Interface Module ships with these project-scoped entities, defined in `backend/app/models/interface.py`:

- `System`, `Unit`, `Connector`, `Pin`
- `BusDefinition`, `PinBusAssignment`, `MessageDefinition`, `MessageField`
- `WireHarness`, `Wire`, `Interface`
- `UnitEnvironmentalSpec`, `InterfaceRequirementLink`, `AutoRequirementLog`

Every `Unit` directly carries fields like `manufacturer`, `part_number`, `mass_kg`, `power_watts_nominal`, `temp_operating_min_c`, etc. These are project-bound. Adding the same Raytheon RSP-100 to a second project requires re-entering all of it.

`Pin` carries a single `name` field. There is no distinction between vendor pin label and user signal name.

Auto-wire today matches by `Pin.name` string equality only — no direction check, no LRU endpoint validation.

Auto-generated requirements today are created once and never re-rendered when source data changes. Editing a wire after requirements are generated leaves the requirements stale.

---

## 3. Architectural Changes — Overview

```
┌─────────────────────────── GLOBAL LAYER (cross-project, master) ─────────────────────────┐
│                                                                                            │
│   Supplier ◄──────── SupplierDocument                                                     │
│      │                     │                                                               │
│      │                     │ (chain of custody)                                            │
│      ▼                     ▼                                                               │
│   CatalogPart ──── CatalogPartRevision ──── CatalogConnector ──── CatalogPin              │
│      (LRU master spec, env envelope, lifecycle)               (mfr_pin_name, mfr signal)   │
│                                                                                            │
└────────────────────────────────────────────────────────────────────────────────────────────┘
                                              ▲
                                              │ instantiated_from
                                              │
┌─────────────────────────── PROJECT LAYER (per-project, instance) ─────────────────────────┐
│                                                                                            │
│   Project ──── System ──── Unit (instance of CatalogPart) ──── Connector ──── Pin         │
│                              │                                                  │          │
│                              │                                  internal_signal_name      │
│                              │                                  (editable, auto-wire key)  │
│                              ▼                                                             │
│                        Interface ◄──── WireHarness ──── Wire                              │
│                              │                                                             │
│                              │ generates                                                   │
│                              ▼                                                             │
│                        Requirement ◄──── InterfaceRequirementLink (source linkage)        │
│                              │                                                             │
│                              ▼                                                             │
│                        ReqSyncProposal (when source changes)                              │
│                                                                                            │
└────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Key idea:** Suppliers and LRUs are master data. Projects subscribe to them. When source data changes — at either layer — derived requirements track the change and ask for re-approval rather than going stale.

---

## 4. Schema Design

All new tables go in `backend/app/models/catalog.py` (new file). New requirement-sync entities go in `backend/app/models/req_sync.py` (new file). Existing `interface.py` is modified only where noted.

### 4.1 Supplier

```python
class Supplier(Base):
    __tablename__ = "suppliers"

    id                = Column(Integer, primary_key=True)
    name              = Column(String(200), nullable=False, unique=True, index=True)
    short_name        = Column(String(50), nullable=True)
    cage_code         = Column(String(10), nullable=True, index=True)   # 5-char NCAGE
    duns              = Column(String(15), nullable=True)
    website           = Column(String(500), nullable=True)
    address           = Column(Text, nullable=True)
    country           = Column(String(100), nullable=True)
    primary_contact   = Column(String(200), nullable=True)
    primary_email     = Column(String(200), nullable=True)
    notes             = Column(Text, nullable=True)
    is_active         = Column(Boolean, default=True, nullable=False)

    created_at        = Column(DateTime(timezone=True), server_default=func.now())
    updated_at        = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id     = Column(Integer, ForeignKey("users.id"), nullable=False)

    documents         = relationship("SupplierDocument", back_populates="supplier", cascade="all, delete-orphan")
    catalog_parts     = relationship("CatalogPart", back_populates="supplier")
```

### 4.2 SupplierDocument

```python
class SupplierDocument(Base):
    __tablename__ = "supplier_documents"

    id                = Column(Integer, primary_key=True)
    supplier_id       = Column(Integer, ForeignKey("suppliers.id", ondelete="CASCADE"), nullable=False, index=True)
    title             = Column(String(500), nullable=False)
    document_type     = Column(SQLEnum(SupplierDocumentType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    revision          = Column(String(50), nullable=True)
    document_number   = Column(String(200), nullable=True)
    publication_date  = Column(Date, nullable=True)
    file_path         = Column(String(1000), nullable=False)
    file_size_bytes   = Column(BigInteger, nullable=False)
    sha256            = Column(String(64), nullable=False, index=True)  # chain of custody
    mime_type         = Column(String(100), nullable=False)
    page_count        = Column(Integer, nullable=True)

    extraction_status = Column(SQLEnum(ExtractionStatus, values_callable=lambda x: [e.value for e in x]),
                                nullable=False, default=ExtractionStatus.UPLOADED)
    extraction_log    = Column(JSONB, nullable=True)
    extraction_at     = Column(DateTime(timezone=True), nullable=True)

    uploaded_at       = Column(DateTime(timezone=True), server_default=func.now())
    uploaded_by_id    = Column(Integer, ForeignKey("users.id"), nullable=False)

    supplier          = relationship("Supplier", back_populates="documents")
    pending_imports   = relationship("PendingCatalogImport", back_populates="source_document",
                                      cascade="all, delete-orphan")
```

```python
class SupplierDocumentType(str, enum.Enum):
    ICD            = "icd"
    DATASHEET      = "datasheet"
    SPEC_SHEET     = "spec_sheet"
    DRAWING        = "drawing"
    APP_NOTE       = "app_note"
    USER_MANUAL    = "user_manual"
    OTHER          = "other"

class ExtractionStatus(str, enum.Enum):
    UPLOADED         = "uploaded"
    EXTRACTING       = "extracting"
    PENDING_REVIEW   = "pending_review"
    APPROVED         = "approved"
    REJECTED         = "rejected"
    FAILED           = "failed"
```

### 4.3 CatalogPart

```python
class CatalogPart(Base):
    __tablename__ = "catalog_parts"
    __table_args__ = (
        UniqueConstraint("supplier_id", "part_number", "revision", name="uq_catalog_part_pn_rev"),
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
    part_class          = Column(SQLEnum(PartClass, values_callable=lambda x: [e.value for e in x]), nullable=False)
    lru_classification  = Column(SQLEnum(LRUClass, values_callable=lambda x: [e.value for e in x]),
                                  nullable=False, default=LRUClass.LRU)

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
    lifecycle_status    = Column(SQLEnum(LifecycleStatus, values_callable=lambda x: [e.value for e in x]),
                                  nullable=False, default=LifecycleStatus.ACTIVE)
    eol_date            = Column(Date, nullable=True)

    # Variant tree (for binned parts, custom builds)
    parent_part_id      = Column(Integer, ForeignKey("catalog_parts.id", ondelete="SET NULL"), nullable=True, index=True)
    variant_label       = Column(String(100), nullable=True)             # "BIN-A", "FLIGHT-CERT"

    # Source traceability
    source_document_id  = Column(Integer, ForeignKey("supplier_documents.id", ondelete="SET NULL"), nullable=True)
    source_page_refs    = Column(JSONB, nullable=True)

    notes               = Column(Text, nullable=True)
    image_path          = Column(String(1000), nullable=True)

    created_at          = Column(DateTime(timezone=True), server_default=func.now())
    updated_at          = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by_id       = Column(Integer, ForeignKey("users.id"), nullable=False)

    supplier            = relationship("Supplier", back_populates="catalog_parts")
    source_document     = relationship("SupplierDocument")
    parent_part         = relationship("CatalogPart", remote_side=[id], backref="variants")
    connectors          = relationship("CatalogConnector", back_populates="catalog_part",
                                        cascade="all, delete-orphan", order_by="CatalogConnector.position")
    project_units       = relationship("Unit", back_populates="catalog_part")
```

```python
class PartClass(str, enum.Enum):
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
```

### 4.4 CatalogConnector

```python
class CatalogConnector(Base):
    __tablename__ = "catalog_connectors"
    __table_args__ = (
        UniqueConstraint("catalog_part_id", "reference", name="uq_catalog_connector_ref"),
        Index("ix_catalog_connector_part", "catalog_part_id"),
    )

    id                  = Column(Integer, primary_key=True)
    catalog_part_id     = Column(Integer, ForeignKey("catalog_parts.id", ondelete="CASCADE"), nullable=False)
    reference            = Column(String(50), nullable=False)
    position             = Column(Integer, nullable=False, default=0)
    description          = Column(String(500), nullable=True)
    connector_type       = Column(String(100), nullable=True)
    shell_size           = Column(String(50), nullable=True)
    insert_arrangement   = Column(String(50), nullable=True)
    gender               = Column(SQLEnum(ConnectorGender, values_callable=lambda x: [e.value for e in x]), nullable=True)
    pin_count            = Column(Integer, nullable=False, default=0)
    keying               = Column(String(50), nullable=True)
    mating_part_number   = Column(String(200), nullable=True)
    notes                = Column(Text, nullable=True)

    catalog_part         = relationship("CatalogPart", back_populates="connectors")
    pins                 = relationship("CatalogPin", back_populates="catalog_connector",
                                         cascade="all, delete-orphan", order_by="CatalogPin.pin_position")


class ConnectorGender(str, enum.Enum):
    MALE              = "male"
    FEMALE            = "female"
    HERMAPHRODITIC    = "hermaphroditic"
    UNKNOWN           = "unknown"
```

### 4.5 CatalogPin

```python
class CatalogPin(Base):
    __tablename__ = "catalog_pins"
    __table_args__ = (
        UniqueConstraint("catalog_connector_id", "pin_position", name="uq_catalog_pin_position"),
        Index("ix_catalog_pin_connector", "catalog_connector_id"),
    )

    id                  = Column(Integer, primary_key=True)
    catalog_connector_id = Column(Integer, ForeignKey("catalog_connectors.id", ondelete="CASCADE"), nullable=False)
    pin_position        = Column(String(20), nullable=False)

    # ── Manufacturer-locked fields (immutable in projects) ──
    mfr_pin_name        = Column(String(100), nullable=False)
    mfr_signal_function = Column(String(500), nullable=True)
    mfr_signal_type     = Column(SQLEnum(SignalType, values_callable=lambda x: [e.value for e in x]), nullable=True)
    mfr_direction       = Column(SQLEnum(SignalDirection, values_callable=lambda x: [e.value for e in x]),
                                  nullable=True, default=SignalDirection.UNKNOWN)
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


class SignalType(str, enum.Enum):
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
    INPUT           = "input"
    OUTPUT          = "output"
    BIDIRECTIONAL   = "bidirectional"
    POWER           = "power"
    GROUND          = "ground"
    UNKNOWN         = "unknown"
```

### 4.6 Modified `Pin` (project-side)

```python
# ── Catalog linkage (NULL for legacy/manual pins) ──
catalog_pin_id      = Column(Integer, ForeignKey("catalog_pins.id", ondelete="SET NULL"),
                              nullable=True, index=True)

# ── Dual naming ──
mfr_pin_name        = Column(String(100), nullable=True)
    # Cached from CatalogPin at instantiation. Locked. Read-only in UI.

internal_signal_name = Column(String(100), nullable=True, index=True)
    # USER-EDITABLE. Auto-wire key. Defaults to mfr_pin_name at instantiation.

# ── Direction (CRITICAL for auto-wire) ──
direction_override  = Column(SQLEnum(SignalDirection, values_callable=lambda x: [e.value for e in x]), nullable=True)
    # When NULL, falls back to catalog mfr_direction.
    # When set, this overrides the catalog (e.g., a bidirectional pin used as input-only in this project).

# ── Project-scope override ──
function_override   = Column(String(500), nullable=True)
```

The existing `Pin.name` field is **deprecated but kept** through migration 0008 for backward compatibility. Drop scheduled for 0009 only after grep confirms zero readers.

### 4.7 Modified `Unit` (project-side)

```python
# ── Catalog linkage (NULL for legacy units) ──
catalog_part_id     = Column(Integer, ForeignKey("catalog_parts.id", ondelete="SET NULL"),
                              nullable=True, index=True)

# ── Project-specific instance fields ──
location_zone       = Column(String(100), nullable=True)             # NEW
serial_number       = Column(String(200), nullable=True)             # NEW
asset_tag           = Column(String(200), nullable=True)             # NEW
```

**Specs source-of-truth rule:** if `catalog_part_id` is set, all physics fields (mass, power, env) are read from the catalog part via property accessor. If a project legitimately needs different specs, the user must create a CatalogPart **variant** (with `parent_part_id` pointing back to the original) and re-place. Project-side Unit physics fields are kept on the model only for legacy units where `catalog_part_id IS NULL`.

This eliminates the dual-source-of-truth problem from v1.0 of this doc.

### 4.8 PendingCatalogImport

```python
class PendingCatalogImport(Base):
    __tablename__ = "pending_catalog_imports"

    id                       = Column(Integer, primary_key=True)
    source_document_id       = Column(Integer, ForeignKey("supplier_documents.id", ondelete="CASCADE"),
                                       nullable=False, index=True)
    supplier_id              = Column(Integer, ForeignKey("suppliers.id"), nullable=False)

    extracted_data           = Column(JSONB, nullable=False)
    extraction_warnings      = Column(JSONB, nullable=True)
    extraction_confidence    = Column(Numeric(4, 3), nullable=True)

    status                   = Column(SQLEnum(PendingImportStatus, values_callable=lambda x: [e.value for e in x]),
                                       nullable=False, default=PendingImportStatus.PENDING)

    committed_catalog_part_id = Column(Integer, ForeignKey("catalog_parts.id", ondelete="SET NULL"), nullable=True)

    rejection_reason         = Column(Text, nullable=True)
    reviewer_notes           = Column(Text, nullable=True)

    created_at               = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at              = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_id           = Column(Integer, ForeignKey("users.id"), nullable=True)

    source_document          = relationship("SupplierDocument", back_populates="pending_imports")


class PendingImportStatus(str, enum.Enum):
    PENDING        = "pending"
    APPROVED       = "approved"
    REJECTED       = "rejected"
    SUPERSEDED     = "superseded"
```

### 4.9 Reactive Requirement Sync — new entities

**File:** `backend/app/models/req_sync.py` (new)

```python
class RequirementSourceLink(Base):
    """
    The 'this requirement was generated FROM this source' record.
    Replaces the old InterfaceRequirementLink with a more general schema.
    A requirement can have multiple source links (e.g., a wire requirement
    cites the wire, the harness, and the bus).
    """
    __tablename__ = "requirement_source_links"
    __table_args__ = (
        Index("ix_req_source_link_entity", "source_entity_type", "source_entity_id"),
        Index("ix_req_source_link_req", "requirement_id"),
        UniqueConstraint("requirement_id", "source_entity_type", "source_entity_id",
                          name="uq_req_source_unique"),
    )

    id                   = Column(Integer, primary_key=True)
    requirement_id       = Column(Integer, ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False)
    source_entity_type   = Column(SQLEnum(SourceEntityType, values_callable=lambda x: [e.value for e in x]),
                                   nullable=False)
    source_entity_id     = Column(Integer, nullable=False)
    template_id          = Column(String(100), nullable=False)         # which auto-req template generated this
    template_inputs      = Column(JSONB, nullable=False)
        # Snapshot of {field: value} used at last generation. Compared on edits to detect drift.
    role                 = Column(String(50), nullable=False, default="primary")
        # "primary" (the main source), "supporting" (cited in rationale), "context"
    last_synced_at       = Column(DateTime(timezone=True), server_default=func.now())

    requirement          = relationship("Requirement")


class SourceEntityType(str, enum.Enum):
    SYSTEM         = "system"
    UNIT           = "unit"
    CONNECTOR      = "connector"
    PIN            = "pin"
    INTERFACE      = "interface"
    WIRE_HARNESS   = "wire_harness"
    WIRE           = "wire"
    BUS_DEFINITION = "bus_definition"
    MESSAGE        = "message_definition"
    MESSAGE_FIELD  = "message_field"
    UNIT_ENV_SPEC  = "unit_env_spec"
    CATALOG_PART   = "catalog_part"
    REQUIREMENT    = "requirement"           # for parent-child trace


class RequirementSyncProposal(Base):
    """
    Surfaces when source data changes and an auto-generated requirement
    no longer reflects current reality. The user reviews and accepts/rejects.
    """
    __tablename__ = "requirement_sync_proposals"
    __table_args__ = (
        Index("ix_req_sync_proposal_status", "status"),
        Index("ix_req_sync_proposal_req", "requirement_id"),
    )

    id                       = Column(Integer, primary_key=True)
    requirement_id           = Column(Integer, ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False)
    triggered_by_entity_type = Column(SQLEnum(SourceEntityType, values_callable=lambda x: [e.value for e in x]),
                                       nullable=False)
    triggered_by_entity_id   = Column(Integer, nullable=False)
    trigger_event            = Column(String(50), nullable=False)          # "update", "delete", "rename"

    old_statement            = Column(Text, nullable=False)
    new_statement            = Column(Text, nullable=True)                 # NULL means "delete this req"
    old_rationale            = Column(Text, nullable=True)
    new_rationale            = Column(Text, nullable=True)
    field_diffs              = Column(JSONB, nullable=False)               # {field_name: {old, new}}

    proposal_type            = Column(SQLEnum(SyncProposalType, values_callable=lambda x: [e.value for e in x]),
                                       nullable=False)
    status                   = Column(SQLEnum(SyncProposalStatus, values_callable=lambda x: [e.value for e in x]),
                                       nullable=False, default=SyncProposalStatus.PENDING)

    auto_applied             = Column(Boolean, default=False)
        # True if requirement was in pending_review status and the proposal was silently auto-applied.

    created_at               = Column(DateTime(timezone=True), server_default=func.now())
    reviewed_at              = Column(DateTime(timezone=True), nullable=True)
    reviewed_by_id           = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewer_notes           = Column(Text, nullable=True)

    requirement              = relationship("Requirement")


class SyncProposalType(str, enum.Enum):
    UPDATE_STATEMENT  = "update_statement"   # new_statement differs from old
    OBSOLETE          = "obsolete"           # source was deleted, requirement no longer has reason to exist
    REGENERATE        = "regenerate"         # catastrophic change, full re-render

class SyncProposalStatus(str, enum.Enum):
    PENDING          = "pending"
    ACCEPTED         = "accepted"
    REJECTED         = "rejected"
    AUTO_APPLIED     = "auto_applied"
    SUPERSEDED       = "superseded"          # newer proposal replaced this one
```

**Add to existing `Requirement` model:**

```python
# ── Auto-sync controls ──
sync_locked         = Column(Boolean, default=False, nullable=False)
    # When True, auto-generated requirements are protected from sync proposals.
    # Set by user when they hand-edit a generated req and want to preserve their edits.
sync_locked_reason  = Column(String(500), nullable=True)
sync_locked_by_id   = Column(Integer, ForeignKey("users.id"), nullable=True)
sync_locked_at      = Column(DateTime(timezone=True), nullable=True)

generation_template_id = Column(String(100), nullable=True, index=True)
    # Which template generated this req. NULL for hand-written reqs.
```

**Migration of existing `InterfaceRequirementLink`:** Data migrated 1-to-1 into `requirement_source_links` with `source_entity_type` set per existing link's `entity_type` column. The old table is kept for one release as deprecated, then dropped in 0009.

---

## 5. Alembic Migration 0008

**File:** `backend/alembic/versions/0008_supplier_catalog_layer.py`

**Hand-write this migration. Do not autogenerate.**

### 5.1 Up steps (order matters)

1. Create enum types: `supplier_document_type`, `extraction_status`, `part_class`, `lru_class`, `lifecycle_status`, `connector_gender`, `signal_type`, `signal_direction`, `pending_import_status`, `source_entity_type`, `sync_proposal_type`, `sync_proposal_status`.
2. `CREATE TABLE suppliers`
3. `CREATE TABLE supplier_documents`
4. `CREATE TABLE catalog_parts` (note: `parent_part_id` FK is a self-reference, defer constraint)
5. `CREATE TABLE catalog_connectors`
6. `CREATE TABLE catalog_pins`
7. `CREATE TABLE pending_catalog_imports`
8. `CREATE TABLE requirement_source_links`
9. `CREATE TABLE requirement_sync_proposals`
10. `ALTER TABLE units` — add `catalog_part_id`, `location_zone`, `serial_number`, `asset_tag`
11. `ALTER TABLE pins` — add `catalog_pin_id`, `mfr_pin_name`, `internal_signal_name`, `direction_override`, `function_override`
12. `ALTER TABLE requirements` — add `sync_locked`, `sync_locked_reason`, `sync_locked_by_id`, `sync_locked_at`, `generation_template_id`
13. Create indexes (see §4 table args).
14. Backfill `pins.internal_signal_name = pins.mfr_pin_name = pins.name` where `name IS NOT NULL`.
15. Backfill `requirement_source_links` from existing `interface_requirement_links` (1-to-1 mapping).
16. Backfill `requirements.generation_template_id` from `auto_requirement_logs` join where applicable.

### 5.2 Down

Reverse order. Drop tables, columns, indexes, enums. Test on a snapshot.

### 5.3 Verify

```powershell
docker compose exec backend alembic upgrade head
docker compose exec db psql -U astra -d astra -c "\d suppliers"
docker compose exec db psql -U astra -d astra -c "\d catalog_parts"
docker compose exec db psql -U astra -d astra -c "\d requirement_source_links"
docker compose exec db psql -U astra -d astra -c "SELECT COUNT(*) FROM pins WHERE internal_signal_name IS NULL;"
docker compose exec db psql -U astra -d astra -c "SELECT COUNT(*) FROM requirement_source_links;"
```

---

## 6. RBAC — Roles & Permissions

ASTRA's existing roles: `admin`, `project_manager`, `requirements_engineer`, `reviewer`, `stakeholder`.

New scope additions for catalog and sync features:

| Action | admin | proj_mgr | req_eng | reviewer | stakeholder |
|---|---|---|---|---|---|
| Create / edit Supplier | ✅ | ✅ | ✅ | ❌ | ❌ |
| Delete Supplier | ✅ | ❌ | ❌ | ❌ | ❌ |
| Upload SupplierDocument | ✅ | ✅ | ✅ | ❌ | ❌ |
| Trigger ICD extraction | ✅ | ✅ | ✅ | ❌ | ❌ |
| Approve PendingCatalogImport | ✅ | ✅ | ✅ | ❌ | ❌ |
| Reject PendingCatalogImport | ✅ | ✅ | ✅ | ❌ | ❌ |
| Create / edit CatalogPart | ✅ | ✅ | ✅ | ❌ | ❌ |
| Delete CatalogPart | ✅ | ❌ | ❌ | ❌ | ❌ |
| Place CatalogPart in project | ✅ | ✅ | ✅ | ❌ | ❌ |
| Approve RequirementSyncProposal | ✅ | ✅ | ✅ | ✅ | ❌ |
| Reject RequirementSyncProposal | ✅ | ✅ | ✅ | ✅ | ❌ |
| Lock requirement from sync | ✅ | ✅ | ✅ | ❌ | ❌ |
| Override coverage validator | ✅ | ✅ | ❌ | ❌ | ❌ |
| Read all catalog & projects | ✅ | (membership) | (membership) | (membership) | (membership) |

**Critical rule:** the `admin` role bypasses all approval gates, lock states, coverage warnings, and project membership checks. Admin is the global override.

Permission helpers in `backend/app/services/rbac.py`:

```python
def can_approve_catalog_import(user: User) -> bool:
    return user.role in {UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.REQUIREMENTS_ENGINEER}

def can_approve_sync_proposal(user: User) -> bool:
    return user.role in {UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.REQUIREMENTS_ENGINEER, UserRole.REVIEWER}

def can_lock_requirement(user: User) -> bool:
    return user.role in {UserRole.ADMIN, UserRole.PROJECT_MANAGER, UserRole.REQUIREMENTS_ENGINEER}

def admin_bypass(user: User) -> bool:
    return user.role == UserRole.ADMIN
```

---

## 7. Pydantic Schemas

**Files:**
- `backend/app/schemas/catalog.py` (new) — Supplier, SupplierDocument, CatalogPart, CatalogConnector, CatalogPin, PendingCatalogImport
- `backend/app/schemas/req_sync.py` (new) — RequirementSourceLink, RequirementSyncProposal, coverage report schemas
- `backend/app/schemas/interface.py` — modify Pin, Unit response schemas to include new fields

Required schemas per existing convention (Create/Update/Response/Detail). All enum fields use `values_callable=lambda x: [e.value for e in x]`.

---

## 8. Database Robustness & Indexing Strategy

The catalog and sync tables will be the largest in the system over time. A mature deployment may have 10K parts, 100K catalog pins, 50K requirements, 200K source links, and 1M+ sync proposals (most archived).

### 8.1 Indexes — required (already specified above)

| Table | Index | Why |
|---|---|---|
| `suppliers` | UNIQUE(name), INDEX(cage_code) | Lookup by name and CAGE on every part create |
| `catalog_parts` | UNIQUE(supplier_id, part_number, revision), INDEX(part_number, name), INDEX(part_class, lifecycle_status), INDEX(parent_part_id) | Search, filter, variant trees |
| `catalog_connectors` | UNIQUE(catalog_part_id, reference) | Always queried by part |
| `catalog_pins` | UNIQUE(catalog_connector_id, pin_position) | Always queried by connector |
| `pins` | INDEX(catalog_pin_id), INDEX(internal_signal_name) | Auto-wire lookup, catalog drill-down |
| `units` | INDEX(catalog_part_id) | "Where used" queries |
| `requirement_source_links` | INDEX(source_entity_type, source_entity_id), INDEX(requirement_id), UNIQUE(req, type, id) | Reverse-lookup on edits triggers fan-out queries |
| `requirement_sync_proposals` | INDEX(status), INDEX(requirement_id) | Dashboard "pending sync proposals" loads on every page |

### 8.2 JSONB columns — GIN indexes

```sql
CREATE INDEX ix_pending_imports_extracted_gin
    ON pending_catalog_imports USING gin (extracted_data jsonb_path_ops);

CREATE INDEX ix_req_source_link_inputs_gin
    ON requirement_source_links USING gin (template_inputs jsonb_path_ops);
```

### 8.3 Query patterns to enforce

- **Pagination is mandatory.** All list endpoints cap `limit` at **200** (per ASTRA convention; documented to fail with 422 if exceeded).
- **Eager-loading on detail endpoints.** Catalog part detail uses `joinedload(CatalogPart.connectors).joinedload(CatalogConnector.pins)` — never lazy.
- **No N+1 in the sync engine.** When an edit triggers proposal fan-out, source links are loaded in one query: `db.query(RequirementSourceLink).filter(type, id).all()` then a single bulk-load of requirements via `id IN (...)`.
- **Materialized view for coverage report.** See §13.4.

### 8.4 Connection pool

Update `backend/app/database.py`:

```python
engine = create_engine(
    DATABASE_URL,
    pool_size=20,            # was 5
    max_overflow=30,         # was 10
    pool_pre_ping=True,
    pool_recycle=1800,       # 30 min, prevents stale conns
)
```

### 8.5 VACUUM / autovacuum tuning

Add to a maintenance migration or document for ops:

```sql
ALTER TABLE requirement_sync_proposals SET (autovacuum_vacuum_scale_factor = 0.05);
ALTER TABLE audit_log SET (autovacuum_vacuum_scale_factor = 0.05);
ALTER TABLE requirement_history SET (autovacuum_vacuum_scale_factor = 0.05);
```

These tables churn frequently; the default 0.2 scale factor leaves them bloated.

### 8.6 Future: archival strategy

A scheduled job (Phase 8 follow-up, out of scope here) moves `requirement_sync_proposals` rows older than 90 days with status in (`accepted`, `rejected`, `superseded`) to a `_archive` table. Not required for v1 but designed-for: status field is enum'd, indexed, and proposals are immutable post-review.

---

## 9. API Endpoints

**Routers:**
- `backend/app/routers/catalog.py` (new) — mounted at `/api/v1/catalog`
- `backend/app/routers/req_sync.py` (new) — mounted at `/api/v1/req-sync`
- `backend/app/routers/coverage.py` (new) — mounted at `/api/v1/coverage`
- `backend/app/routers/interface.py` (modified) — Connection Builder endpoints

Register all in `backend/app/main.py` `_optional_routers` list.

### 9.1 Suppliers

| Method | Path | Purpose | Min Role |
|---|---|---|---|
| GET | `/catalog/suppliers` | List with search | any logged in |
| POST | `/catalog/suppliers` | Create | req_eng+ |
| GET | `/catalog/suppliers/{id}` | Detail | any logged in |
| PATCH | `/catalog/suppliers/{id}` | Update | req_eng+ |
| DELETE | `/catalog/suppliers/{id}` | Delete | admin only |

### 9.2 Supplier Documents

| Method | Path | Purpose | Min Role |
|---|---|---|---|
| POST | `/catalog/suppliers/{id}/documents/upload` | Multipart upload | req_eng+ |
| GET | `/catalog/documents/{doc_id}` | Metadata | any logged in |
| GET | `/catalog/documents/{doc_id}/file` | Download original | any logged in |
| GET | `/catalog/documents/{doc_id}/preview` | PDF page renders | any logged in |
| POST | `/catalog/documents/{doc_id}/extract` | Trigger extraction | req_eng+ |
| DELETE | `/catalog/documents/{doc_id}` | Delete | admin only |

### 9.3 Catalog Parts

| Method | Path | Purpose | Min Role |
|---|---|---|---|
| GET | `/catalog/parts` | List with search/filter | any logged in |
| POST | `/catalog/parts` | Manual create | req_eng+ |
| GET | `/catalog/parts/{id}` | Detail (connectors+pins eager) | any logged in |
| PATCH | `/catalog/parts/{id}` | Update | req_eng+ |
| DELETE | `/catalog/parts/{id}` | Delete (refuses if in use unless admin) | admin |
| GET | `/catalog/parts/{id}/usage` | Where used (project units) | any logged in |
| POST | `/catalog/parts/{id}/place` | Place in project | req_eng+ |
| POST | `/catalog/parts/{id}/variant` | Create variant | req_eng+ |

### 9.4 Pending Imports

| Method | Path | Purpose | Min Role |
|---|---|---|---|
| GET | `/catalog/pending-imports` | List | req_eng+ |
| GET | `/catalog/pending-imports/{id}` | Detail | req_eng+ |
| PATCH | `/catalog/pending-imports/{id}` | Edit before approval | req_eng+ |
| POST | `/catalog/pending-imports/{id}/approve` | Commit to catalog | req_eng+ |
| POST | `/catalog/pending-imports/{id}/reject` | Reject | req_eng+ |

### 9.5 Connection Builder (in interface router)

| Method | Path | Purpose | Min Role |
|---|---|---|---|
| POST | `/interfaces/connection-builder/start` | Begin guided connection | req_eng+ |
| POST | `/interfaces/connection-builder/{interface_id}/auto-suggest-wires` | Run three-way match | req_eng+ |
| POST | `/interfaces/connection-builder/{interface_id}/commit` | Create harness + wires | req_eng+ |

### 9.6 Requirement Sync

| Method | Path | Purpose | Min Role |
|---|---|---|---|
| GET | `/req-sync/proposals` | List, filterable by project/status | reviewer+ |
| GET | `/req-sync/proposals/{id}` | Detail (full diff) | reviewer+ |
| POST | `/req-sync/proposals/{id}/accept` | Apply proposed change | reviewer+ |
| POST | `/req-sync/proposals/{id}/reject` | Discard proposal | reviewer+ |
| POST | `/req-sync/proposals/bulk-accept` | Bulk accept by ID list | reviewer+ |
| POST | `/req-sync/requirements/{req_id}/lock` | Lock req from auto-sync | req_eng+ |
| POST | `/req-sync/requirements/{req_id}/unlock` | Unlock | req_eng+ |
| GET | `/req-sync/requirements/{req_id}/sources` | Show all source links | any logged in |

### 9.7 Coverage

| Method | Path | Purpose | Min Role |
|---|---|---|---|
| GET | `/coverage/source/{project_id}` | Source coverage report (orphan reqs by level) | any logged in |
| GET | `/coverage/source/{project_id}/orphans` | Just the offenders | any logged in |
| POST | `/coverage/exception` | File a coverage exception | proj_mgr+ |
| GET | `/coverage/exceptions/{project_id}` | List exceptions | any logged in |

---

## 10. ICD Ingestion Pipeline

Architecture, file layout, and Claude API prompt unchanged from v1.0. Summary recap:

1. Upload (multipart) → SHA-256 → store under `/data/supplier_docs/{uuid}.{ext}`
2. Pre-extract: PyMuPDF (text + 200 DPI page images, capped at 50 pages), `python-docx`, `openpyxl`, `camelot-py` for tables
3. Send to Anthropic API with strict JSON schema prompt (full prompt in `backend/app/services/catalog/prompts.py`)
4. Validate response against `IcdExtractionResultSchema` Pydantic model
5. On success: create `PendingCatalogImport`; status = `PENDING_REVIEW`
6. Reviewer (req_eng+ or admin) reviews in side-by-side UI, edits if needed, approves
7. On approve: transactional commit creating `Supplier` (if new), `CatalogPart`, `CatalogConnectors`, `CatalogPins`; status = `APPROVED`

The full §10 from v1.0 applies unchanged — see prior version for prompt and schema details.

Add to `requirements.txt`:
```
PyMuPDF==1.24.5
camelot-py[cv]==0.11.0
python-docx==1.1.2
```

---

## 11. Auto-Wire Algorithm — Three-Way Validation

**File:** `backend/app/services/interface/auto_wire.py`

This is the headline algorithm change in v1.1. Auto-wire pairs two pins **only when all three conditions hold**:

1. **Internal signal name matches** (after normalization)
2. **Directions are compatible** (input ↔ output, or either side bidirectional)
3. **LRU endpoints are correct** — pins belong to the actual source/target Units declared on the Interface

Without all three, no wire is proposed.

### 11.1 Inputs

```python
def auto_wire_interface(
    db: Session,
    interface_id: int,
    options: AutoWireOptions = AutoWireOptions(),
) -> AutoWireResult:
    ...

class AutoWireOptions(BaseModel):
    require_signal_type_match: bool = True       # power↔power, digital↔digital
    require_direction_compatibility: bool = True  # the direction check (default ON)
    enforce_lru_endpoints: bool = True            # the LRU check (default ON, never off in prod)
    exclude_no_connect: bool = True
    exclude_chassis_ground: bool = False
    case_sensitive_names: bool = False
    only_unmatched_pins: bool = True
```

### 11.2 Algorithm — explicit three-way check

```
INPUT: interface_id
1. Load Interface → must exist, status ∈ {draft, proposed}
   FAIL FAST if status = approved (don't auto-wire approved interfaces)

2. LRU ENDPOINT VALIDATION (Check #3 of three)
   a. source_unit = Interface.source_unit_id   (must NOT be NULL)
   b. target_unit = Interface.target_unit_id   (must NOT be NULL)
   c. Both units in same project? If not → REJECT with "cross-project wires not allowed"
   d. (Optional) If interface.declared_source_lru_class is set, source_unit.catalog_part.lru_classification must match
   e. Same check for target

3. Load all pins for source_unit (across all its connectors): pins_src
   Load all pins for target_unit: pins_tgt

4. Build target index keyed by normalized internal_signal_name:
   tgt_index: dict[str, list[Pin]] = {}
   for p in pins_tgt:
       key = normalize(p.internal_signal_name)
       if not key: continue
       tgt_index.setdefault(key, []).append(p)

5. For each src_pin in pins_src:

   # ── Pre-filters ──
   if not src_pin.internal_signal_name: skip
   if exclude_no_connect and src_pin.is_no_connect: skip
   if exclude_chassis_ground and src_pin.is_chassis_ground: skip
   if only_unmatched_pins and pin_already_wired(src_pin, in_harness): skip

   # ── Check #1: NAME MATCH ──
   key = normalize(src_pin.internal_signal_name)
   candidates = tgt_index.get(key, [])
   if len(candidates) == 0:
       → unmatched_source.append(src_pin)
       continue
   if len(candidates) > 1:
       → ambiguous.append((src_pin, candidates))
       continue

   tgt_pin = candidates[0]

   # ── Check #2: DIRECTION COMPATIBILITY ──
   src_dir = src_pin.direction_override or src_pin.catalog_pin.mfr_direction or UNKNOWN
   tgt_dir = tgt_pin.direction_override or tgt_pin.catalog_pin.mfr_direction or UNKNOWN

   if not directions_compatible(src_dir, tgt_dir):
       → direction_conflicts.append((src_pin, tgt_pin, src_dir, tgt_dir))
       continue

   # ── (Already passed Check #3 by virtue of step 2) ──

   # ── Optional signal type filter ──
   if require_signal_type_match:
       src_type = src_pin.catalog_pin.mfr_signal_type or UNKNOWN
       tgt_type = tgt_pin.catalog_pin.mfr_signal_type or UNKNOWN
       if src_type != tgt_type and UNKNOWN not in {src_type, tgt_type}:
           → type_mismatches.append(...)
           continue

   → proposed_wires.append(ProposedWire(src_pin, tgt_pin, key, ...))

6. Compute unmatched_target = pins_tgt not consumed
7. Return AutoWireResult
```

### 11.3 Direction compatibility matrix

```python
COMPATIBLE_DIRECTIONS = {
    (INPUT, OUTPUT),         # data flowing src → tgt or src ← tgt
    (OUTPUT, INPUT),
    (BIDIRECTIONAL, INPUT),
    (BIDIRECTIONAL, OUTPUT),
    (INPUT, BIDIRECTIONAL),
    (OUTPUT, BIDIRECTIONAL),
    (BIDIRECTIONAL, BIDIRECTIONAL),
    (POWER, POWER),          # power-to-power is fine
    (GROUND, GROUND),
    (POWER, GROUND): False,  # must be opposite-polarity? actually power and ground both go through dedicated pins
    (UNKNOWN, *): True,      # be permissive on unknowns; flag for review
    (*, UNKNOWN): True,
}

def directions_compatible(src: SignalDirection, tgt: SignalDirection) -> bool:
    if src == UNKNOWN or tgt == UNKNOWN:
        return True  # warn but don't block
    return (src, tgt) in COMPATIBLE_DIRECTIONS
```

### 11.4 Result schema

```python
class AutoWireResult(BaseModel):
    proposed_wires: list[ProposedWire]      # ✅ all 3 checks pass
    ambiguous: list[AmbiguousMatch]
    unmatched_source: list[PinSummary]
    unmatched_target: list[PinSummary]
    type_mismatches: list[TypeMismatchPair]
    direction_conflicts: list[DirectionConflictPair]    # ← NEW prominent in UI
    lru_validation_errors: list[str]                    # ← NEW: failed Check #3
    summary: AutoWireSummary

class ProposedWire(BaseModel):
    source_pin_id: int
    target_pin_id: int
    matched_signal_name: str
    direction_pair: tuple[SignalDirection, SignalDirection]
    confidence: Literal["high", "medium", "low"]
    suggested_wire_gauge: str | None
    suggested_wire_color: str | None
```

### 11.5 UI surfacing

Direction conflicts MUST appear prominently in the Connection Builder Step 2 view, in red, with explanation:

```
⚠ Direction conflict
   Source: J1.5 PWR_DEBUG (output)  ↔  Target: J3.B7 PWR_DEBUG (output)
   → Both pins are outputs. This connection would create contention.
   [Override (admin)] [Mark as bidirectional] [Skip]
```

---

## 12. Reactive Requirement Sync Engine

When source data (system, LRU, connection, wire, signal name, bus, message) is edited, every auto-generated requirement linked to that source is re-rendered against the new values. If the rendered statement differs, a `RequirementSyncProposal` is created.

### 12.1 Trigger architecture

**File:** `backend/app/services/req_sync/listener.py`

Use SQLAlchemy event listeners (`@event.listens_for(target, 'after_update')`) on the source entity classes:

```python
SYNC_WATCHED_MODELS = [
    System, Unit, Connector, Pin, Interface,
    WireHarness, Wire, BusDefinition,
    MessageDefinition, MessageField, UnitEnvironmentalSpec,
    CatalogPart,  # affects placed units transitively
]

@event.listens_for(Wire, 'after_update')
def on_wire_update(mapper, connection, target):
    fan_out_sync_proposals(
        connection,
        source_entity_type=SourceEntityType.WIRE,
        source_entity_id=target.id,
        trigger_event='update',
    )

@event.listens_for(Wire, 'after_delete')
def on_wire_delete(mapper, connection, target):
    fan_out_sync_proposals(..., trigger_event='delete')
```

### 12.2 Fan-out service

**File:** `backend/app/services/req_sync/fan_out.py`

```python
def fan_out_sync_proposals(
    db, source_entity_type, source_entity_id, trigger_event, changed_fields=None
):
    """
    1. Find all RequirementSourceLinks with (source_entity_type, source_entity_id).
    2. Bulk-load the requirements they reference.
    3. For each requirement:
        a. Skip if requirement.sync_locked == True (log skip)
        b. Skip if requirement.status == 'cancelled' or 'superseded'
        c. Re-fetch the source entity (or recognize it's deleted)
        d. Re-render the requirement using its generation_template_id and current source data
        e. Compare new statement to current — if identical, no proposal
        f. If different:
           - If req.status == 'pending_review' → AUTO-APPLY (silent update + audit log)
           - If req.status == 'draft' or 'approved' → CREATE PROPOSAL with status=PENDING
        g. If source is deleted → CREATE PROPOSAL with type=OBSOLETE (suggest deleting req)
    4. Supersede any prior PENDING proposals for the same (req, source) pair.
    """
```

This runs **synchronously inside the same DB transaction** as the source edit, so users see proposals immediately. For high-fan-out cases (e.g., editing a CatalogPart with 50 placed units), wrap in a background task using FastAPI's `BackgroundTasks`.

### 12.3 Re-rendering

**File:** `backend/app/services/req_sync/renderer.py`

```python
def render_requirement_from_template(
    db, template_id: str, source_links: list[RequirementSourceLink]
) -> RenderedRequirement:
    """
    Reuses the same template engine as backend/app/services/interface/auto_requirements.py.
    Loads template by ID, gathers source data fresh from DB, renders statement+rationale.
    """
```

### 12.4 The "edit triggered N proposals" notification

After any fan-out, the API response includes a header `X-Sync-Proposals-Created: 7`. The frontend shows a toast: *"7 requirements need re-sync due to this change. Review now?"*

A persistent badge on the project nav shows pending proposal count, refreshing on every page load.

### 12.5 Auto-apply policy

| Requirement Status | Source Edit Action | Outcome |
|---|---|---|
| `pending_review` | any | Silent auto-apply, log to audit |
| `draft` | non-trivial edit | Create proposal (PENDING) |
| `under_review` | any | Create proposal (PENDING), block source approval until resolved |
| `approved` | any | Create proposal (PENDING) — never auto-apply, requires reviewer |
| `implemented` / `verified` | source delete | Create proposal type=OBSOLETE (warn loudly — verified req has lost its source!) |
| `cancelled` / `superseded` | any | Skip |
| Any (with `sync_locked=True`) | any | Skip with log entry |

Admin can force-apply any proposal via `POST /req-sync/proposals/{id}/accept?admin_force=true`.

### 12.6 Sync proposal review UI

**Page:** `/projects/[id]/req-sync`

Three-pane layout:

```
┌─ Pending Sync Proposals (12) ─┐  ┌─ Selected Proposal: REQ-1247 ──────────────────────┐
│                                │  │                                                     │
│ ▶ REQ-1247 (Wire change)       │  │ Trigger: Wire HARN-007.W12 mfr changed             │
│   REQ-1248 (Wire change)       │  │ Source:  Wire data_rate 1Mbps → 10Mbps             │
│   REQ-1392 (LRU rename)        │  │                                                     │
│   REQ-1402 (Bus deleted)       │  │ ┌─ OLD ────────────────┐ ┌─ NEW ──────────────────┐│
│   ...                          │  │ │ The Radar shall      │ │ The Radar shall        ││
│                                │  │ │ transmit data to     │ │ transmit data to       ││
│ Filters:                       │  │ │ C2 via MIL-1553B     │ │ C2 via MIL-1553B       ││
│ ☐ Statement updates            │  │ │ at 1 Mbps.           │ │ at 10 Mbps.            ││
│ ☐ Obsolete                     │  │ └──────────────────────┘ └────────────────────────┘│
│ ☐ Wire-related                 │  │                                                     │
│ ☐ LRU-related                  │  │ Field diffs:                                        │
│ ☐ Bus-related                  │  │   data_rate: "1 Mbps" → "10 Mbps"                  │
│                                │  │                                                     │
│ [Bulk accept selected]         │  │ [Accept] [Reject] [Lock & keep current] [Edit]     │
│ [Bulk reject selected]         │  │                                                     │
└────────────────────────────────┘  └─────────────────────────────────────────────────────┘
```

### 12.7 Required tests

`backend/tests/test_req_sync.py`:

- Edit a wire → proposal created for wire-derived req
- Edit a system name → all child reqs receive proposals
- Delete a bus → bus-derived reqs get OBSOLETE proposals
- Locked req → no proposal regardless of source change
- pending_review req → auto-applied silently
- approved req → proposal pending, never auto-applied
- Concurrent edits → second proposal supersedes first
- Bulk accept N proposals — atomic, all or none

---

## 13. Requirement Source Coverage Validator

Every requirement at L3, L4, L5 (and most L2) must trace to a real architectural element. Orphans are flagged.

### 13.1 Coverage definition

A requirement is **source-traced** if any of these is true:

1. It has at least one `RequirementSourceLink` with `role='primary'` to an interface entity (Wire, Harness, Bus, Message, Pin, Connector, Unit, System, Interface).
2. It has a `TraceLink` (parent-child) to another requirement that is itself source-traced (recursively).
3. It has a link to a project artifact (concept doc, ICD, drawing) that justifies its existence.
4. It is admin-flagged with a `CoverageException` row.

### 13.2 Rules by level

| Level | Source required | Severity if orphan |
|---|---|---|
| L1 (mission/system goals) | No | none |
| L2 (system requirements) | Preferred | warning |
| L3 (subsystem) | **Required** | error |
| L4 (component) | **Required** | error |
| L5 (interface/detailed) | **Required** | error |

### 13.3 Validator service

**File:** `backend/app/services/coverage/source_validator.py`

```python
def compute_source_coverage(db, project_id: int) -> SourceCoverageReport:
    """
    Returns:
        {
            "total_requirements": 487,
            "by_level": {
                "L1": {total: 8, traced: 8, orphan: 0, severity: "ok"},
                "L2": {total: 24, traced: 22, orphan: 2, severity: "warning"},
                "L3": {total: 110, traced: 108, orphan: 2, severity: "error"},
                "L4": {total: 195, traced: 195, orphan: 0, severity: "ok"},
                "L5": {total: 150, traced: 142, orphan: 8, severity: "error"},
            },
            "orphans": [
                {req_id: "FR-099", level: "L5", title: "...", suggested_source_type: "wire"},
                ...
            ],
            "exceptions": [...],
        }
    """
```

### 13.4 Materialized view for performance

```sql
CREATE MATERIALIZED VIEW mv_requirement_source_coverage AS
SELECT
    r.id AS requirement_id,
    r.project_id,
    r.req_id,
    r.level,
    r.status,
    EXISTS(
        SELECT 1 FROM requirement_source_links rsl
        WHERE rsl.requirement_id = r.id AND rsl.role = 'primary'
    ) AS has_primary_source,
    EXISTS(
        SELECT 1 FROM trace_links tl
        WHERE tl.target_requirement_id = r.id
        AND tl.link_type IN ('derives_from', 'refines')
    ) AS has_parent_trace,
    EXISTS(
        SELECT 1 FROM coverage_exceptions ce
        WHERE ce.requirement_id = r.id AND ce.is_active = true
    ) AS has_exception
FROM requirements r;

CREATE INDEX ix_mv_req_source_cov_proj_level
    ON mv_requirement_source_coverage(project_id, level);
```

Refresh: `REFRESH MATERIALIZED VIEW CONCURRENTLY mv_requirement_source_coverage;` runs after every batch source-link insert/delete and on a 10-minute scheduled job.

### 13.5 Suggestion engine

For an orphan L4/L5 req, suggest a source by NLP-light pattern matching on its statement:

```python
def suggest_source_type(req: Requirement) -> SourceEntityType | None:
    s = req.statement.lower()
    if any(k in s for k in ["wire", "harness", "cable", "awg"]): return SourceEntityType.WIRE
    if any(k in s for k in ["pin", "connector", "j1", "p1", "tb"]): return SourceEntityType.PIN
    if any(k in s for k in ["bus", "1553", "can", "arinc"]): return SourceEntityType.BUS_DEFINITION
    if any(k in s for k in ["temperature", "vibration", "shock", "humidity"]): return SourceEntityType.UNIT_ENV_SPEC
    ...
```

Surfaced in UI as: *"This L5 requirement looks like an interface requirement. Was it meant to link to a wire? [Browse wires] [Mark as exception]"*

### 13.6 Coverage Exception

**File:** `backend/app/models/coverage_exception.py`

```python
class CoverageException(Base):
    __tablename__ = "coverage_exceptions"

    id              = Column(Integer, primary_key=True)
    requirement_id  = Column(Integer, ForeignKey("requirements.id"), nullable=False, index=True)
    reason          = Column(Text, nullable=False)
    is_active       = Column(Boolean, default=True, nullable=False)
    expires_at      = Column(DateTime(timezone=True), nullable=True)   # optional
    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id   = Column(Integer, ForeignKey("users.id"), nullable=False)
    approved_by_id  = Column(Integer, ForeignKey("users.id"), nullable=True)  # admin co-sign
```

Filing an exception requires `proj_mgr` role. Admin co-sign required for it to count toward coverage. Without admin co-sign, the orphan still appears as severity=warning instead of error.

### 13.7 UI surfacing

**Page:** `/projects/[id]/coverage`

Top bar: traffic light per level (green/yellow/red) with counts. Below, a sortable table of orphans with:
- Req ID, Title, Level, Status, Suggested source type, Actions

Actions: **Link to source** (opens source picker), **File exception** (textarea + admin signoff prompt), **Mark deferred**.

Coverage badge in the project nav: red dot if any L4/L5 orphans exist.

---

## 14. Catalog Placement UX — Existing vs Brand New

The single most important user-facing flow. When a user adds an LRU to a project, they're presented with two clear paths:

### 14.1 Entry points

- Project Interfaces page → "Add Unit" button
- System Detail page → "Add Unit to this system" button
- Connection Builder Step 1 → "+ New Unit" inline option

All three open the same modal: **`<PlaceLruModal>`**.

### 14.2 The modal — three-tab UI

```
┌─ Add LRU to Project ──────────────────────────────────────────────────────┐
│                                                                           │
│  [📚 From Catalog]  [➕ Brand New]  [📄 Upload ICD]                       │
│  ──────────────                                                           │
│                                                                           │
│  Search: [____________________________]                                   │
│  Filter: [Supplier ▼] [Class ▼] [Status: Active ▼]                        │
│                                                                           │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │ 🟢 Raytheon RSP-100 Rev C — Radar Signal Processor                  │  │
│  │    Class: Processor | LRU | Mass: 2.3 kg | Power: 45 W              │  │
│  │    Used in 3 projects: SMDS, GBI-PRG, AAS                           │  │
│  │                                                              [Pick] │  │
│  ├─────────────────────────────────────────────────────────────────────┤  │
│  │ 🟢 BAE C2P-200 Rev B — Command & Control Processor                  │  │
│  │    Class: Processor | LRU | Mass: 3.1 kg | Power: 60 W              │  │
│  │    Used in 1 project: SMDS                                          │  │
│  │                                                              [Pick] │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                           │
└───────────────────────────────────────────────────────────────────────────┘
```

**Tab 1: From Catalog** — search/filter the master library. Picking a part opens a placement form: assign system, set unit_id_tag (project-scoped, e.g. "UNIT-RADAR-01"), optional designation override, location_zone, serial_number. Confirm creates the project Unit with `catalog_part_id` set; pins instantiate with `mfr_pin_name` locked and `internal_signal_name` defaulted to mfr.

**Tab 2: Brand New** — multi-step form to create a CatalogPart from scratch:
- Step 1: Pick supplier (search existing or "+ Create new supplier" sub-modal)
- Step 2: Part identity (part_number, name, designation, class, LRU class, revision)
- Step 3: Specs (physical, power, environmental — all optional)
- Step 4: Connectors & pins (add connector → add pins, repeatable)
- Step 5: Confirm — shows "This will be added to the global catalog. After creation it will be available for all future projects." with checkbox to also place in current project (default ON).

**Tab 3: Upload ICD** — drag-and-drop a vendor document. Triggers the ingestion pipeline (§10). After extraction completes, user is sent to the review page. Once approved, the user returns to the placement modal pre-filtered to the new part, ready to place.

### 14.3 No-duplicates guarantee

The "Brand New" tab pre-emptively checks: when user types a part_number, the form queries `/catalog/parts?q={pn}` and if matches exist, shows a banner:

> ⚠ A part with number "RSP-100" already exists from supplier Raytheon. [View existing] [Create as variant] [Continue anyway]

This prevents the "every project recreates the same RSP-100" anti-pattern.

### 14.4 Placement service

**File:** `backend/app/services/catalog/placement.py`

```python
def place_part_in_project(
    db: Session,
    catalog_part_id: int,
    project_id: int,
    system_id: int,
    unit_id_tag: str,
    designation_override: str | None = None,
    location_zone: str | None = None,
    serial_number: str | None = None,
    user_id: int = ...,
) -> Unit:
    """
    Atomically:
      1. Validate catalog_part exists and is not OBSOLETE (warn) or RESTRICTED (require admin)
      2. Validate unit_id_tag is unique within project_id
      3. Create Unit row with catalog_part_id set
      4. For each CatalogConnector: create project Connector
      5. For each CatalogPin: create project Pin with
            - catalog_pin_id set
            - mfr_pin_name copied (locked)
            - internal_signal_name defaulted to mfr_pin_name
            - direction_override = NULL (will read catalog mfr_direction)
      6. Audit log: catalog.part.placed
      7. Return Unit
    """
```

---

## 15. Connection Builder UX

Three-step wizard at `/projects/[id]/interfaces/connect`. Largely unchanged from v1.0 doc but with two key updates for v1.1:

### 15.1 Step 2 — Pin pairing now shows direction

```
┌─ SOURCE: J1 (38 pins) ───────┐                            ┌─ TARGET: J3 (32 pins) ──────┐
│ ✓ 1   PWR_28V_PRI    ▶ Pwr   ════ PWR_28V_PRI ════ Pwr ▶  ✓ A1  PWR_28V_PRI            │
│ ✓ 2   PWR_RTN_PRI    ▶ Gnd   ════ PWR_RTN_PRI ════ Gnd ▶  ✓ A2  PWR_RTN_PRI            │
│ ✓ 3   1553_BUS_A_HI  ◄▶      ════ 1553_BUS_A_HI ════  ◄▶  ✓ B1  1553_BUS_A_HI          │
│ ⚠ 7   STATUS_LED     ▶ Out   ⨯ DIRECTION CONFLICT       ▶  C5  STATUS_LED ▶ Out        │
│       (both outputs — will create bus contention)                                       │
│       [Override] [Mark target as input]                                                 │
└──────────────────────────────┘                            └─────────────────────────────┘

Auto-matched: 4   Direction conflicts: 1   Ambiguous: 0   Unmatched src: 2

Filters:  [✓] Hide N/C   [✓] Match signal type   [✓] Enforce direction (REQUIRED)
```

The direction filter is on by default and warns prominently if turned off.

### 15.2 LRU validation banner

Above Step 2, a colored bar:

```
✅ LRU validation: Source = Raytheon RSP-100 (LRU) ↔ Target = BAE C2P-200 (LRU). Both endpoints valid.
```

Or, if LRU classes don't match a declared interface expectation:

```
⚠ LRU validation warning: Source is an SRU but Interface expects LRU↔LRU. [Override (admin)]
```

---

## 16. Frontend Pages — Full List

(Revised count for v1.1)

New pages:

| Path | Purpose |
|---|---|
| `/catalog` | Landing — Suppliers / Parts / Pending Imports tabs |
| `/catalog/suppliers/[id]` | Supplier detail with documents + parts |
| `/catalog/suppliers/new` | Create supplier |
| `/catalog/parts/[id]` | Part detail (specs, connectors+pins, where-used, variants) |
| `/catalog/parts/new` | Manual create catalog part |
| `/catalog/documents/[id]/review` | ICD review side-by-side |
| `/projects/[id]/interfaces/connect` | Connection Builder wizard |
| `/projects/[id]/req-sync` | Sync proposals review (new) |
| `/projects/[id]/coverage` | Source coverage report (new) |

Modified pages:

| Path | Change |
|---|---|
| `/projects/[id]/interfaces/unit/[unitId]` | Catalog badge + variants link + sync proposal indicator |
| `/projects/[id]/interfaces/connector/[connectorId]` | Dual-name pin table (Mfr locked, Internal editable) |
| `/projects/[id]/interfaces/page.tsx` | "Add Unit" CTA opens PlaceLruModal; "Connect Two Units" launches builder |
| `/projects/[id]/interfaces/harness/[harnessId]` | Wire rows show internal name primary + mfr name secondary |
| `/projects/[id]/requirements/[reqId]` | Source links panel + sync lock button + sync proposal banner |
| Project nav | Coverage badge + Sync Proposals badge |

---

## 17. Implementation Phases

Each phase independently testable and deployable. **Do not skip ahead.**

### Phase 1 — Schema & migration (foundation)

1. Create `backend/app/models/catalog.py` — all 7 catalog entities + enums
2. Create `backend/app/models/req_sync.py` — RequirementSourceLink, RequirementSyncProposal, SyncProposalType, SyncProposalStatus, SourceEntityType enum
3. Create `backend/app/models/coverage_exception.py`
4. Create `backend/app/schemas/catalog.py`, `backend/app/schemas/req_sync.py`, `backend/app/schemas/coverage.py`
5. Modify `backend/app/models/interface.py` — Pin and Unit additions
6. Modify `backend/app/models/__init__.py` — export new models
7. Hand-write `backend/alembic/versions/0008_supplier_catalog_layer.py`. Test up + down on a snapshot.
8. Apply migration in dev. Verify backfill (pins.internal_signal_name populated; requirement_source_links populated from old InterfaceRequirementLink).
9. Update connection pool config in `backend/app/database.py`.

**Acceptance:** `alembic current` shows 0008. SELECT counts confirm backfill. All existing tests still pass.

### Phase 2 — Catalog CRUD backend

1. Create `backend/app/routers/catalog.py` with all endpoints from §9.1-9.4 except ICD ingestion routes.
2. Implement `backend/app/services/catalog/placement.py`.
3. Register router in `backend/app/main.py`.
4. RBAC enforcement per §6.
5. Tests in `backend/tests/test_catalog_crud.py` — target 30+ tests.
6. Validate Python: `python3 -c "import ast; ast.parse(...)"` on every new file.

**Acceptance:** Manual smoke: create Supplier → create CatalogPart with 2 connectors and 10 pins → place in SMDS → verify Unit + Pins created with correct catalog linkage.

### Phase 3 — Catalog UI (no ingestion)

1. Build pages from §16: `/catalog`, `/catalog/suppliers/*`, `/catalog/parts/*`.
2. Build `<PlaceLruModal>` with three tabs (Catalog, Brand New, Upload ICD — last tab disabled until Phase 6).
3. Modify Unit detail and Connector detail per §16.
4. Implement bulk pin actions (rename pattern, copy mfr → internal).
5. ASTRA dark theme conformance: `bg-astra-surface`, `border-astra-border`, blue accents, `rounded-xl`.

**Acceptance:** End-to-end: create supplier, create catalog part, place in SMDS, see dual-name pin table.

### Phase 4 — Connection Builder + three-way auto-wire

1. Create `backend/app/services/interface/auto_wire.py` per §11.
2. Create `backend/app/services/interface/wire_heuristics.py`.
3. Add Connection Builder backend endpoints (§9.5).
4. Build `ConnectionBuilder.tsx`, `PinPairingMatrix.tsx`, `HarnessAssignmentForm.tsx`.
5. Direction conflict UI per §15.1, LRU banner per §15.2.
6. Tests: `backend/tests/test_auto_wire.py` covering all three checks (name, direction, LRU endpoint), edge cases.

**Acceptance:** From SMDS, connect Radar to C2 in under 60 seconds with auto-wire correctly catching a deliberate direction conflict.

### Phase 5 — Reactive Requirement Sync engine

1. Create `backend/app/services/req_sync/listener.py` — SQLAlchemy event listeners on watched models.
2. Create `backend/app/services/req_sync/fan_out.py`.
3. Create `backend/app/services/req_sync/renderer.py` — reuse existing template engine.
4. Create `backend/app/routers/req_sync.py` with endpoints from §9.6.
5. Build `/projects/[id]/req-sync` page per §12.6.
6. Add sync_locked toggle on requirement detail page.
7. Add "X proposals pending" badge on project nav.
8. Tests: `backend/tests/test_req_sync.py` — all cases from §12.7.

**Acceptance:** Edit a wire's data rate in SMDS → within 1 second the related auto-generated requirement appears in the sync proposals queue with correct old/new diff. Approving the proposal updates the requirement; rejecting preserves the old.

### Phase 6 — Source Coverage Validator

1. Create `backend/app/services/coverage/source_validator.py`.
2. Create migration 0008.5 (or fold into 0008): `mv_requirement_source_coverage` materialized view.
3. Create `backend/app/services/coverage/refresh.py` — refresh job triggered after batch source-link writes + scheduled.
4. Create `backend/app/routers/coverage.py` with endpoints from §9.7.
5. Build `/projects/[id]/coverage` page per §13.7.
6. Add coverage badge in project nav.
7. Implement suggestion engine.
8. Tests: `backend/tests/test_coverage.py` covering orphan detection per level + exceptions.

**Acceptance:** SMDS coverage page shows: green for L1/L2, accurate counts of orphan L3-L5 reqs, suggested source type per orphan, exception filing flow with admin co-sign.

### Phase 7 — ICD ingestion pipeline

1. Add `PyMuPDF`, `camelot-py[cv]`, `python-docx` to requirements.txt. Rebuild backend image.
2. Implement `backend/app/services/catalog/document_extractor.py`.
3. Implement `backend/app/services/catalog/icd_extractor.py` using existing `ai_service`.
4. Implement `backend/app/services/catalog/prompts.py`.
5. Add upload + extract endpoints from §9.2 / §9.4.
6. Build review UI page per §10.
7. Implement transactional approve/commit.
8. Enable Tab 3 (Upload ICD) in PlaceLruModal.
9. Tests with synthetic ICD fixture.

**Acceptance:** Upload a real Glenair Mil-DTL-38999 datasheet → in <60 seconds it's in pending review → engineer approves → catalog has the part → place in SMDS → connect.

### Phase 8 — Polish, RBAC verification, robustness

1. Update README with catalog and sync architecture sections.
2. Seed script for starter suppliers (Raytheon, BAE, TE Connectivity, Glenair, Amphenol).
3. Audit log events for every catalog mutation, import approval, sync proposal acceptance, coverage exception.
4. Verify admin override paths work end-to-end (forced approval, locked req override, restricted-part placement).
5. Run full test suite. Target zero regressions.
6. Performance test: catalog with 1000 parts and 10000 pins, project with 500 reqs and 2000 source links — verify all dashboard loads under 2 seconds.

**Acceptance:** Full E2E walkthrough from fresh DB → seed → upload → approve → place → connect → auto-wire → generate reqs → edit source → review proposal → accept → coverage report green. Zero regressions on existing SMDS data.

---

## 18. Testing Strategy

### Unit & integration tests

- `test_catalog_models.py` — relationships, cascades, unique constraints
- `test_catalog_crud.py` — all CRUD endpoints with RBAC
- `test_catalog_placement.py` — placement service, no-dup detection
- `test_icd_extraction.py` — schema validation, mocked AI calls
- `test_auto_wire.py` — three-way validation, all matrix combinations
- `test_connection_builder.py` — wizard E2E
- `test_req_sync.py` — fan-out, auto-apply policies, lock behavior
- `test_coverage.py` — orphan detection, exceptions, MV refresh
- `test_e2e_catalog_to_wires.py` — golden path

### Performance test

`test_perf_catalog_scale.py`:

1. Seed 1000 catalog parts, 5 connectors each, 10 pins each = 50K catalog pins
2. Seed 500 requirements with ~4 source links each = 2K source links
3. Time critical queries:
   - Catalog list paginated: <200ms
   - Catalog part detail: <300ms
   - Auto-wire on 100-pin units: <500ms
   - Coverage report: <1s
   - Sync proposal fan-out on CatalogPart edit affecting 50 placed units: <2s
4. Fail the test if any threshold blown.

### Quality gates

- `ruff check backend/`
- `python3 -c "import ast; ast.parse(...)"` on every Python file before commit
- `npm run type-check` in frontend
- Coverage on new code ≥ 80%

---

## 19. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Migration breaks existing SMDS data | `pins.name` not dropped in 0008. Backfill is additive. Test on backup snapshot. |
| Sync engine fan-out is slow on big edits | Background tasks for >10 affected reqs. Materialized view for coverage. |
| Ambiguous internal_signal_name causes wrong auto-wire | Three-way validation (name + direction + LRU) blocks most failures. Ambiguous matches always surface for manual resolution, never auto-paired. |
| Direction enums are wrong on imported pins | Direction filter shows conflicts in UI. User can override per-pin. Admin can disable filter for legacy data. |
| Catalog part deletion when widely placed | DELETE returns 409 with reference list. Admin force-delete only via explicit `?admin_force=true` flag with audit log. |
| Sync proposals overwhelm reviewers | Auto-apply for `pending_review` reqs. Bulk accept/reject. Filter by trigger type. |
| Locked requirements drift permanently from source | Coverage page flags locked reqs whose source has changed since lock. Periodic "stale lock" report. |
| ICD extraction wrong, user approves anyway | Source document remains attached. Future re-extraction creates a superseding pending import. Audit log preserves history. |
| Catalog grows to 100K+ parts | GIN indexes on JSONB, materialized views, pagination cap at 200, connection pool 20+30. |
| Vendor releases revision, projects need to upgrade | New revision = new CatalogPart row (not in-place edit). Migration UI per project (deferred). |

---

## 20. Out of Scope

- Test Integration Module (separate TDD)
- Bit-level protocol modeling (Phase 2 Communication Module)
- Vendor revision diff/upgrade UI (deferred)
- Image extraction from ICDs (text + tables only in v1)
- Catalog-to-Catalog mating constraints
- Cross-project full-graph where-used
- Archival job for old sync proposals (designed-for, not implemented in v1)
- Signal entity abstraction (deferred — three-way auto-wire mitigates the immediate need)

---

## 21. PowerShell / Windows Notes

- Complete drop-in files only, no patches.
- Direct SQL inside container for verification: `docker compose exec db psql -U astra -d astra -f /tmp/check.sql`
- `curl` is a PS alias — use `Invoke-RestMethod` or `docker compose exec backend curl ...`
- `[System.IO.File]::ReadAllText/WriteAllText` instead of `Get-Content -Raw`
- `$` chars in psql require escaping or run inside container
- Backend rate limit is **200**, not 1000
- Validate every generated Python file with `python3 -c "import ast; ast.parse(...)"` before delivery

---

## 22. Acceptance: Definition of Done

This refactor is complete when:

1. ✅ Migration 0008 applied cleanly on SMDS, no data loss
2. ✅ All catalog entities have full CRUD + RBAC + tests passing
3. ✅ Pin table shows two name columns; Mfr locked, Internal editable
4. ✅ Three-way auto-wire validates name + direction + LRU endpoint
5. ✅ Connection Builder takes a user from "two units" to "harness with wires" in three clicks
6. ✅ Uploading a supplier ICD produces a pending import; approving creates a complete CatalogPart
7. ✅ Placing a catalog part creates Unit + Connectors + Pins with proper catalog linkage
8. ✅ "Brand New" placement always creates a global catalog entry, never project-local
9. ✅ Editing source data (system, LRU, wire, signal) creates sync proposals for affected requirements
10. ✅ pending_review reqs auto-apply, approved reqs require explicit reviewer accept
11. ✅ Locked requirements never receive sync proposals
12. ✅ Coverage report flags every L3-L5 orphan requirement
13. ✅ Coverage exceptions require admin co-sign for L4-L5
14. ✅ Admin role bypasses all gates (catalog approval, sync, coverage, lock state)
15. ✅ Performance tests pass at scale (1000 parts, 50K pins, 500 reqs)
16. ✅ Zero regressions on existing SMDS interfaces, harnesses, requirements, traceability
17. ✅ E2E test passes
18. ✅ Audit log captures every catalog, sync, coverage, and admin override mutation

---

**End of Document — ASTRA-TDD-INTF-002 v1.1**
