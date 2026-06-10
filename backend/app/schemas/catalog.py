"""
ASTRA — Pydantic schemas for the supplier catalog layer
========================================================
File: backend/app/schemas/catalog.py   ← NEW (Phase 1, ASTRA-TDD-INTF-002)

Create / Update / Response / Detail per existing convention
(see backend/app/schemas/interface.py for the shape pattern).

Conventions (audit carry-forwards):
  - F-038: list/dict defaults always use `Field(default_factory=...)`.
  - F-133: every `Optional[...]` field gets `= None`.
  - Enums are accepted as their string values; Pydantic v2 coerces to the
    enum class at validation time.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from app.models.catalog import (
    ConnectorGender,
    ExtractionStatus,
    LifecycleStatus,
    LRUClass,
    PartClass,
    PendingImportStatus,
    SignalDirection,
    SignalType,
    SupplierDocumentType,
)


# ══════════════════════════════════════════════════════════════
#  Supplier
# ══════════════════════════════════════════════════════════════

class SupplierCreate(BaseModel):
    name: str = Field(..., max_length=200)
    short_name: Optional[str] = Field(None, max_length=50)
    cage_code: Optional[str] = Field(None, max_length=10)
    duns: Optional[str] = Field(None, max_length=15)
    website: Optional[str] = Field(None, max_length=500)
    address: Optional[str] = None
    country: Optional[str] = Field(None, max_length=100)
    primary_contact: Optional[str] = Field(None, max_length=200)
    primary_email: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    is_active: bool = True
    is_in_house: bool = False  # TDD-CAT-002


class SupplierUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=200)
    short_name: Optional[str] = Field(None, max_length=50)
    cage_code: Optional[str] = Field(None, max_length=10)
    duns: Optional[str] = Field(None, max_length=15)
    website: Optional[str] = Field(None, max_length=500)
    address: Optional[str] = None
    country: Optional[str] = Field(None, max_length=100)
    primary_contact: Optional[str] = Field(None, max_length=200)
    primary_email: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    is_active: Optional[bool] = None
    is_in_house: Optional[bool] = None  # TDD-CAT-002


class SupplierResponse(BaseModel):
    id: int
    name: str
    short_name: Optional[str] = None
    cage_code: Optional[str] = None
    duns: Optional[str] = None
    website: Optional[str] = None
    address: Optional[str] = None
    country: Optional[str] = None
    primary_contact: Optional[str] = None
    primary_email: Optional[str] = None
    notes: Optional[str] = None
    is_active: bool
    is_in_house: bool = False  # TDD-CAT-002
    created_at: datetime
    updated_at: datetime
    created_by_id: int
    # Computed / aggregate fields populated by the response layer
    catalog_part_count: int = 0
    document_count: int = 0

    class Config:
        from_attributes = True


class SupplierAliasResponse(BaseModel):
    """TDD-CAT-002 — one row of supplier_aliases."""
    id: int
    supplier_id: int
    alias: str
    created_at: datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  SupplierDocument (metadata only — file content via separate endpoint)
# ══════════════════════════════════════════════════════════════

class SupplierDocumentCreate(BaseModel):
    """Metadata fields posted alongside multipart upload."""
    title: str = Field(..., max_length=500)
    document_type: SupplierDocumentType
    revision: Optional[str] = Field(None, max_length=50)
    document_number: Optional[str] = Field(None, max_length=200)
    publication_date: Optional[date] = None


class SupplierDocumentUpdate(BaseModel):
    title: Optional[str] = Field(None, max_length=500)
    document_type: Optional[SupplierDocumentType] = None
    revision: Optional[str] = Field(None, max_length=50)
    document_number: Optional[str] = Field(None, max_length=200)
    publication_date: Optional[date] = None


class SupplierDocumentResponse(BaseModel):
    id: int
    supplier_id: int
    title: str
    # HAROLD-IN-WRENCH-001 Phase 6: actual multipart upload filename.
    # Nullable for pre-Phase-6 rows where the upload handler didn't
    # capture it (migration 0034 backfills where it can; the rest
    # stay None).
    original_filename: Optional[str] = None
    document_type: SupplierDocumentType
    revision: Optional[str] = None
    document_number: Optional[str] = None
    publication_date: Optional[date] = None
    file_path: str
    file_size_bytes: int
    sha256: str
    mime_type: str
    page_count: Optional[int] = None
    extraction_status: ExtractionStatus
    extraction_log: Optional[Dict[str, Any]] = None
    extraction_at: Optional[datetime] = None
    uploaded_at: datetime
    uploaded_by_id: int

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  CatalogDocuments listing — HAROLD-IN-WRENCH-001 Phase 6
# ══════════════════════════════════════════════════════════════

class CatalogDocumentMetadata(BaseModel):
    """Lightweight per-document row returned by
    ``GET /api/v1/catalog/documents``. Joins each supplier_document
    with the catalog_part it produced (when one exists) so HAROLD's
    filename precheck can return WPN context alongside the
    collision verdict in a single round-trip.
    """
    id: int
    title: str
    original_filename: Optional[str] = None
    document_type: SupplierDocumentType
    file_path: str
    mime_type: str
    sha256: str
    supplier_id: int
    # Mirror of `id` — preserved for the HAROLD-TDD payload shape.
    supplier_document_id: int
    catalog_part_id: Optional[int] = None
    internal_part_number: Optional[str] = None
    extraction_status: ExtractionStatus
    uploaded_at: datetime


class CatalogDocumentsResponse(BaseModel):
    documents: List[CatalogDocumentMetadata]
    total: int


# ══════════════════════════════════════════════════════════════
#  CatalogPin
# ══════════════════════════════════════════════════════════════

class CatalogPinCreate(BaseModel):
    pin_position: str = Field(..., max_length=20)
    mfr_pin_name: str = Field(..., max_length=100)
    mfr_signal_function: Optional[str] = Field(None, max_length=500)
    mfr_signal_type: Optional[SignalType] = None
    mfr_direction: Optional[SignalDirection] = SignalDirection.UNKNOWN
    mfr_voltage_min_v: Optional[Decimal] = None
    mfr_voltage_max_v: Optional[Decimal] = None
    mfr_current_max_ma: Optional[Decimal] = None
    mfr_impedance_ohm: Optional[Decimal] = None
    mfr_protocol_hint: Optional[str] = Field(None, max_length=100)
    mfr_is_paired_with: Optional[str] = Field(None, max_length=50)
    is_no_connect: bool = False
    is_reserved: bool = False
    is_chassis_ground: bool = False
    notes: Optional[str] = None


class CatalogPinUpdate(BaseModel):
    pin_position: Optional[str] = Field(None, max_length=20)
    mfr_pin_name: Optional[str] = Field(None, max_length=100)
    mfr_signal_function: Optional[str] = Field(None, max_length=500)
    mfr_signal_type: Optional[SignalType] = None
    mfr_direction: Optional[SignalDirection] = None
    mfr_voltage_min_v: Optional[Decimal] = None
    mfr_voltage_max_v: Optional[Decimal] = None
    mfr_current_max_ma: Optional[Decimal] = None
    mfr_impedance_ohm: Optional[Decimal] = None
    mfr_protocol_hint: Optional[str] = Field(None, max_length=100)
    mfr_is_paired_with: Optional[str] = Field(None, max_length=50)
    is_no_connect: Optional[bool] = None
    is_reserved: Optional[bool] = None
    is_chassis_ground: Optional[bool] = None
    notes: Optional[str] = None


class CatalogPinResponse(BaseModel):
    id: int
    catalog_connector_id: int
    pin_position: str
    mfr_pin_name: str
    mfr_signal_function: Optional[str] = None
    mfr_signal_type: Optional[SignalType] = None
    mfr_direction: Optional[SignalDirection] = None
    mfr_voltage_min_v: Optional[Decimal] = None
    mfr_voltage_max_v: Optional[Decimal] = None
    mfr_current_max_ma: Optional[Decimal] = None
    mfr_impedance_ohm: Optional[Decimal] = None
    mfr_protocol_hint: Optional[str] = None
    mfr_is_paired_with: Optional[str] = None
    is_no_connect: bool = False
    is_reserved: bool = False
    is_chassis_ground: bool = False
    notes: Optional[str] = None

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  CatalogConnector
# ══════════════════════════════════════════════════════════════

class CatalogConnectorCreate(BaseModel):
    reference: str = Field(..., max_length=50)
    position: int = 0
    description: Optional[str] = Field(None, max_length=500)
    connector_type: Optional[str] = Field(None, max_length=100)
    shell_size: Optional[str] = Field(None, max_length=50)
    insert_arrangement: Optional[str] = Field(None, max_length=50)
    gender: Optional[ConnectorGender] = None
    pin_count: int = 0
    keying: Optional[str] = Field(None, max_length=50)
    mating_part_number: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    pins: List[CatalogPinCreate] = Field(default_factory=list)


class CatalogConnectorUpdate(BaseModel):
    reference: Optional[str] = Field(None, max_length=50)
    position: Optional[int] = None
    description: Optional[str] = Field(None, max_length=500)
    connector_type: Optional[str] = Field(None, max_length=100)
    shell_size: Optional[str] = Field(None, max_length=50)
    insert_arrangement: Optional[str] = Field(None, max_length=50)
    gender: Optional[ConnectorGender] = None
    pin_count: Optional[int] = None
    keying: Optional[str] = Field(None, max_length=50)
    mating_part_number: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None


class CatalogConnectorResponse(BaseModel):
    id: int
    catalog_part_id: int
    reference: str
    position: int
    description: Optional[str] = None
    connector_type: Optional[str] = None
    shell_size: Optional[str] = None
    insert_arrangement: Optional[str] = None
    gender: Optional[ConnectorGender] = None
    pin_count: int
    keying: Optional[str] = None
    mating_part_number: Optional[str] = None
    notes: Optional[str] = None
    pins: List[CatalogPinResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  CatalogPart
# ══════════════════════════════════════════════════════════════

class CatalogPartCreate(BaseModel):
    supplier_id: int
    part_number: str = Field(..., max_length=200)
    revision: Optional[str] = Field(None, max_length=50)
    name: str = Field(..., max_length=500)
    designation: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    part_class: PartClass
    lru_classification: LRUClass = LRUClass.LRU
    # Physical
    mass_kg: Optional[Decimal] = None
    dim_length_mm: Optional[Decimal] = None
    dim_width_mm: Optional[Decimal] = None
    dim_height_mm: Optional[Decimal] = None
    # Power
    power_watts_nominal: Optional[Decimal] = None
    power_watts_peak: Optional[Decimal] = None
    voltage_input_min_v: Optional[Decimal] = None
    voltage_input_max_v: Optional[Decimal] = None
    # Environmental envelope
    temp_operating_min_c: Optional[Decimal] = None
    temp_operating_max_c: Optional[Decimal] = None
    temp_storage_min_c: Optional[Decimal] = None
    temp_storage_max_c: Optional[Decimal] = None
    vibration_random_grms: Optional[Decimal] = None
    shock_mechanical_g: Optional[Decimal] = None
    humidity_max_pct: Optional[Decimal] = None
    altitude_max_m: Optional[Decimal] = None
    emi_ce102_limit_dbua: Optional[Decimal] = None
    emi_rs103_limit_vm: Optional[Decimal] = None
    esd_hbm_v: Optional[Decimal] = None
    # Compliance
    mil_std_810_tested: bool = False
    mil_std_461_tested: bool = False
    rohs_compliant: bool = False
    itar_controlled: bool = False
    export_classification: Optional[str] = Field(None, max_length=50)
    # Lifecycle
    lifecycle_status: LifecycleStatus = LifecycleStatus.ACTIVE
    eol_date: Optional[date] = None
    # Variant
    parent_part_id: Optional[int] = None
    variant_label: Optional[str] = Field(None, max_length=100)
    # Source
    source_document_id: Optional[int] = None
    source_page_refs: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    image_path: Optional[str] = Field(None, max_length=1000)
    # Connectors+pins for atomic-create flows
    connectors: List[CatalogConnectorCreate] = Field(default_factory=list)
    # ── TDD-CAT-002: CAD / STEP-derived fields ──
    part_subtype: Optional[str] = Field(None, max_length=64)
    material_name: Optional[str] = Field(None, max_length=128)
    material_class: Optional[str] = Field(None, max_length=64)
    bbox_x_mm: Optional[Decimal] = None
    bbox_y_mm: Optional[Decimal] = None
    bbox_z_mm: Optional[Decimal] = None
    volume_mm3: Optional[Decimal] = None
    cad_step_path: Optional[str] = None
    cad_preview_path: Optional[str] = None
    cad_authoring_tool: Optional[str] = Field(None, max_length=64)
    native_units: Optional[str] = Field(None, max_length=16)


class CatalogPartUpdate(BaseModel):
    supplier_id: Optional[int] = None
    part_number: Optional[str] = Field(None, max_length=200)
    revision: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, max_length=500)
    designation: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    part_class: Optional[PartClass] = None
    lru_classification: Optional[LRUClass] = None
    mass_kg: Optional[Decimal] = None
    dim_length_mm: Optional[Decimal] = None
    dim_width_mm: Optional[Decimal] = None
    dim_height_mm: Optional[Decimal] = None
    power_watts_nominal: Optional[Decimal] = None
    power_watts_peak: Optional[Decimal] = None
    voltage_input_min_v: Optional[Decimal] = None
    voltage_input_max_v: Optional[Decimal] = None
    temp_operating_min_c: Optional[Decimal] = None
    temp_operating_max_c: Optional[Decimal] = None
    temp_storage_min_c: Optional[Decimal] = None
    temp_storage_max_c: Optional[Decimal] = None
    vibration_random_grms: Optional[Decimal] = None
    shock_mechanical_g: Optional[Decimal] = None
    humidity_max_pct: Optional[Decimal] = None
    altitude_max_m: Optional[Decimal] = None
    emi_ce102_limit_dbua: Optional[Decimal] = None
    emi_rs103_limit_vm: Optional[Decimal] = None
    esd_hbm_v: Optional[Decimal] = None
    mil_std_810_tested: Optional[bool] = None
    mil_std_461_tested: Optional[bool] = None
    rohs_compliant: Optional[bool] = None
    itar_controlled: Optional[bool] = None
    export_classification: Optional[str] = Field(None, max_length=50)
    lifecycle_status: Optional[LifecycleStatus] = None
    eol_date: Optional[date] = None
    parent_part_id: Optional[int] = None
    variant_label: Optional[str] = Field(None, max_length=100)
    source_document_id: Optional[int] = None
    source_page_refs: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    image_path: Optional[str] = Field(None, max_length=1000)
    # ── TDD-CAT-002 ──
    part_subtype: Optional[str] = Field(None, max_length=64)
    material_name: Optional[str] = Field(None, max_length=128)
    material_class: Optional[str] = Field(None, max_length=64)
    bbox_x_mm: Optional[Decimal] = None
    bbox_y_mm: Optional[Decimal] = None
    bbox_z_mm: Optional[Decimal] = None
    volume_mm3: Optional[Decimal] = None
    cad_step_path: Optional[str] = None
    cad_preview_path: Optional[str] = None
    cad_authoring_tool: Optional[str] = Field(None, max_length=64)
    native_units: Optional[str] = Field(None, max_length=16)


class CatalogPartSummary(BaseModel):
    """List/grid-view payload — omits the connector tree for size."""
    id: int
    supplier_id: int
    supplier_name: Optional[str] = None
    part_number: str
    revision: Optional[str] = None
    name: str
    designation: Optional[str] = None
    part_class: PartClass
    lru_classification: LRUClass
    lifecycle_status: LifecycleStatus
    mass_kg: Optional[Decimal] = None
    power_watts_nominal: Optional[Decimal] = None
    used_in_project_count: int = 0
    # ── TDD-CAT-002 (only the chip-render fields belong on summary) ──
    part_subtype: Optional[str] = None
    material_class: Optional[str] = None

    class Config:
        from_attributes = True


class CatalogPartResponse(CatalogPartSummary):
    """Detail-view payload — includes the full connector + pin tree."""
    description: Optional[str] = None
    dim_length_mm: Optional[Decimal] = None
    dim_width_mm: Optional[Decimal] = None
    dim_height_mm: Optional[Decimal] = None
    power_watts_peak: Optional[Decimal] = None
    voltage_input_min_v: Optional[Decimal] = None
    voltage_input_max_v: Optional[Decimal] = None
    temp_operating_min_c: Optional[Decimal] = None
    temp_operating_max_c: Optional[Decimal] = None
    temp_storage_min_c: Optional[Decimal] = None
    temp_storage_max_c: Optional[Decimal] = None
    vibration_random_grms: Optional[Decimal] = None
    shock_mechanical_g: Optional[Decimal] = None
    humidity_max_pct: Optional[Decimal] = None
    altitude_max_m: Optional[Decimal] = None
    emi_ce102_limit_dbua: Optional[Decimal] = None
    emi_rs103_limit_vm: Optional[Decimal] = None
    esd_hbm_v: Optional[Decimal] = None
    mil_std_810_tested: bool = False
    mil_std_461_tested: bool = False
    rohs_compliant: bool = False
    itar_controlled: bool = False
    export_classification: Optional[str] = None
    eol_date: Optional[date] = None
    parent_part_id: Optional[int] = None
    variant_label: Optional[str] = None
    source_document_id: Optional[int] = None
    source_page_refs: Optional[Dict[str, Any]] = None
    notes: Optional[str] = None
    image_path: Optional[str] = None
    # ── TDD-CAT-002 detail fields ──
    material_name: Optional[str] = None
    bbox_x_mm: Optional[Decimal] = None
    bbox_y_mm: Optional[Decimal] = None
    bbox_z_mm: Optional[Decimal] = None
    volume_mm3: Optional[Decimal] = None
    cad_step_path: Optional[str] = None
    cad_preview_path: Optional[str] = None
    cad_authoring_tool: Optional[str] = None
    native_units: Optional[str] = None
    # ── CADPORT-REBUILD-002 (migration 0036) mass-property columns ──
    # CITADEL body frame, SI units. Populated only for CADPORT-
    # extracted parts. Surfaced so the part-detail UI can render the
    # full Mass Properties card without opening the YAML blob.
    cadport_part_id: Optional[str] = None
    content_hash: Optional[str] = None
    volume_m3: Optional[float] = None
    surface_area_m2: Optional[float] = None
    density_kg_m3: Optional[float] = None
    center_of_mass_x: Optional[float] = None
    center_of_mass_y: Optional[float] = None
    center_of_mass_z: Optional[float] = None
    ixx: Optional[float] = None
    iyy: Optional[float] = None
    izz: Optional[float] = None
    ixy: Optional[float] = None
    ixz: Optional[float] = None
    iyz: Optional[float] = None
    # Principal moments — eigenvalues of the symmetric inertia tensor,
    # computed in the response (not stored). Empty when no tensor.
    principal_moments_kg_m2: List[float] = Field(default_factory=list)
    # ── CADPORT-TDD-STEP-001 (migration 0040) provenance ──
    # The ASTRA Edit-mass affordance gates on these: a part with
    # source_format='sldprt' AND mass_source='cad' is SW-imported and
    # carries SW-side mass; PATCH /mass returns 409 in that case.
    source_format: str = "sldprt"
    step_material_key: Optional[str] = None
    mass_source: str = "cad"
    inertia_revised_via_uniform_scaling: bool = False

    deleted_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    created_by_id: int
    connectors: List[CatalogConnectorResponse] = Field(default_factory=list)

    @field_validator("cadport_part_id", mode="before")
    @classmethod
    def _uuid_to_str(cls, v):
        # The ORM column is UUID(as_uuid=True); coerce to str so the
        # response field stays a plain string (Pydantic v2 won't
        # auto-cast UUID -> str).
        return str(v) if v is not None else None


# ══════════════════════════════════════════════════════════════
#  PendingCatalogImport
# ══════════════════════════════════════════════════════════════

class PendingCatalogImportUpdate(BaseModel):
    """Reviewer edits the extracted_data blob before approving."""
    extracted_data: Optional[Dict[str, Any]] = None
    extraction_warnings: Optional[Dict[str, Any]] = None
    extraction_confidence: Optional[Decimal] = None
    rejection_reason: Optional[str] = None
    reviewer_notes: Optional[str] = None
    # CADPORT-TDD-ASTRA-BRIDGE-001 Phase 1: operator can change the
    # supplier choice before approving. Setting supplier_id to a real
    # id wins; setting proposed_supplier_name carries the create-on-
    # approval intent forward. Sending both → 400 at approve time.
    supplier_id: Optional[int] = None
    proposed_supplier_name: Optional[str] = None


class PendingCatalogImportResponse(BaseModel):
    id: int
    source_document_id: int
    # CADPORT-TDD-ASTRA-BRIDGE-001 Phase 1: nullable for cadport.
    supplier_id: Optional[int] = None
    proposed_supplier_name: Optional[str] = None
    source_kind: str = "pdf"
    extracted_data: Dict[str, Any] = Field(default_factory=dict)
    extraction_warnings: Optional[Dict[str, Any]] = None
    extraction_confidence: Optional[Decimal] = None
    status: PendingImportStatus
    committed_catalog_part_id: Optional[int] = None
    rejection_reason: Optional[str] = None
    reviewer_notes: Optional[str] = None
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by_id: Optional[int] = None

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  Placement (the catalog-part → project-unit instantiation request)
# ══════════════════════════════════════════════════════════════

class CatalogPartPlacementRequest(BaseModel):
    """Body of POST /catalog/parts/{id}/place."""
    project_id: int
    system_id: int
    unit_id_tag: str = Field(..., max_length=30)
    designation_override: Optional[str] = Field(None, max_length=50)
    location_zone: Optional[str] = Field(None, max_length=100)
    serial_number: Optional[str] = Field(None, max_length=200)
    asset_tag: Optional[str] = Field(None, max_length=200)
    admin_force: bool = False  # Required when placing RESTRICTED parts


class CatalogPartUsageRow(BaseModel):
    """One row of /catalog/parts/{id}/usage — a placed Unit instance."""
    unit_id: int
    project_id: int
    project_code: Optional[str] = None
    system_id: int
    designation: str
    location_zone: Optional[str] = None
    serial_number: Optional[str] = None

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  CLEANUP-002 Phase 4: usage report for safe-deletion (AD-8)
# ══════════════════════════════════════════════════════════════

class CatalogPartUsageProjectEntry(BaseModel):
    """One project that references this catalog_part. Counts each
    category of reference so the UI can show 'used as 2 BOM lines +
    1 joint in DART' without further drilling."""
    project_id: int
    project_name: Optional[str] = None
    project_code: Optional[str] = None
    project_part_count: int = 0
    mechanical_joint_count: int = 0
    unit_count: int = 0


class CatalogPartUsageReport(BaseModel):
    """Usage report for GET /catalog/parts/{id}/usage-report. Powers
    the delete-with-warning UX: ``deletable`` is the single bit the
    UI checks before enabling the Delete button; ``projects``
    explains why if False. Counts cover project_parts (BOM lines),
    mechanical_joints (transitive via project_parts), and units
    (project placements). catalog_connectors and variant children
    are intentionally excluded from blocking — connectors are owned
    by the part and cascade with it; parent_part_id is ON DELETE
    SET NULL."""
    part_id: int
    part_number: str
    internal_part_number: Optional[str] = None
    total_references: int
    deletable: bool
    projects: List[CatalogPartUsageProjectEntry] = []


# ══════════════════════════════════════════════════════════════
#  ICD Extraction (Phase 7) — strict schema for AI output
# ══════════════════════════════════════════════════════════════
#
# These models define the EXACT shape the LLM is asked to return for an ICD
# extraction. Pydantic validates the parsed JSON; on validation failure the
# orchestrator marks the SupplierDocument FAILED and stores the validation
# errors in `extraction_log`.
#
# All fields are intentionally Optional except ``supplier.name``,
# ``part_number``, ``name``, and ``part_class`` — those are the minimum to
# instantiate a CatalogPart row downstream. Everything else lands as null
# when not present in the source.
# ══════════════════════════════════════════════════════════════


class ExtractedSupplier(BaseModel):
    name: str = Field(..., max_length=200)
    cage_code: Optional[str] = Field(None, max_length=10)
    country: Optional[str] = Field(None, max_length=100)
    source_page: Optional[int] = None


class ExtractedPin(BaseModel):
    pin_position: str = Field(..., max_length=20)
    mfr_pin_name: str = Field(..., max_length=100)
    mfr_signal_function: Optional[str] = Field(None, max_length=500)
    mfr_signal_type: Optional[SignalType] = None
    mfr_direction: Optional[SignalDirection] = None
    mfr_voltage_min_v: Optional[float] = None
    mfr_voltage_max_v: Optional[float] = None
    mfr_current_max_ma: Optional[float] = None
    mfr_impedance_ohm: Optional[float] = None
    mfr_protocol_hint: Optional[str] = Field(None, max_length=100)
    mfr_is_paired_with: Optional[str] = Field(None, max_length=50)
    is_no_connect: bool = False
    is_reserved: bool = False
    is_chassis_ground: bool = False
    notes: Optional[str] = None
    source_page: Optional[int] = None


class ExtractedConnector(BaseModel):
    reference: str = Field(..., max_length=50)
    description: Optional[str] = Field(None, max_length=500)
    connector_type: Optional[str] = Field(None, max_length=100)
    shell_size: Optional[str] = Field(None, max_length=50)
    insert_arrangement: Optional[str] = Field(None, max_length=50)
    gender: Optional[ConnectorGender] = None
    pin_count: int = 0
    keying: Optional[str] = Field(None, max_length=50)
    mating_part_number: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    pins: List[ExtractedPin] = Field(default_factory=list)
    source_page: Optional[int] = None


class IcdExtractionResultSchema(BaseModel):
    """Strict-JSON schema the LLM is asked to return for an ICD extraction."""

    supplier: ExtractedSupplier
    part_number: str = Field(..., max_length=200)
    revision: Optional[str] = Field(None, max_length=50)
    name: str = Field(..., max_length=500)
    designation: Optional[str] = Field(None, max_length=200)
    description: Optional[str] = None
    part_class: PartClass
    lru_classification: LRUClass = LRUClass.LRU

    # Physical
    mass_kg: Optional[float] = None
    dim_length_mm: Optional[float] = None
    dim_width_mm: Optional[float] = None
    dim_height_mm: Optional[float] = None

    # Power
    power_watts_nominal: Optional[float] = None
    power_watts_peak: Optional[float] = None
    voltage_input_min_v: Optional[float] = None
    voltage_input_max_v: Optional[float] = None

    # Environmental envelope
    temp_operating_min_c: Optional[float] = None
    temp_operating_max_c: Optional[float] = None
    temp_storage_min_c: Optional[float] = None
    temp_storage_max_c: Optional[float] = None
    vibration_random_grms: Optional[float] = None
    shock_mechanical_g: Optional[float] = None
    humidity_max_pct: Optional[float] = None
    altitude_max_m: Optional[float] = None
    emi_ce102_limit_dbua: Optional[float] = None
    emi_rs103_limit_vm: Optional[float] = None
    esd_hbm_v: Optional[float] = None

    # Compliance / qual
    mil_std_810_tested: bool = False
    mil_std_461_tested: bool = False
    rohs_compliant: bool = False
    itar_controlled: bool = False
    export_classification: Optional[str] = Field(None, max_length=50)

    # Lifecycle
    lifecycle_status: LifecycleStatus = LifecycleStatus.ACTIVE
    eol_date: Optional[date] = None

    # Connectors+pins
    connectors: List[ExtractedConnector] = Field(default_factory=list)

    # Source-trace metadata
    source_page_refs: Optional[Dict[str, Any]] = None

    # Quality signals
    extraction_warnings: List[str] = Field(default_factory=list)
    extraction_confidence: Optional[float] = Field(None, ge=0.0, le=1.0)

    # ── TDD-CAT-002: CAD / STEP-derived fields ──
    # All optional; populated only on STEP-upload-derived imports. The
    # approve handler dumps the model and forwards these fields to the
    # CatalogPart row via **scalar.
    part_subtype: Optional[str] = Field(None, max_length=64)
    material_name: Optional[str] = Field(None, max_length=128)
    material_class: Optional[str] = Field(None, max_length=64)
    bbox_x_mm: Optional[float] = None
    bbox_y_mm: Optional[float] = None
    bbox_z_mm: Optional[float] = None
    volume_mm3: Optional[float] = None
    cad_step_path: Optional[str] = None
    cad_preview_path: Optional[str] = None
    cad_authoring_tool: Optional[str] = Field(None, max_length=64)
    native_units: Optional[str] = Field(None, max_length=16)


# ══════════════════════════════════════════════════════════════
#  Approve / reject — Phase 7 endpoints
# ══════════════════════════════════════════════════════════════


class PendingImportRejectRequest(BaseModel):
    """Body of POST /catalog/pending-imports/{id}/reject."""
    reason: Optional[str] = Field(None, max_length=2000)


class IcdExtractionTriggerResponse(BaseModel):
    """Body returned by POST /catalog/documents/{id}/extract."""
    job_id: int            # the SupplierDocument.id (acts as the job key)
    status: str            # ExtractionStatus value
    started_at: datetime


# ══════════════════════════════════════════════════════════════
#  TDD-CAT-002 — STEP upload response
# ══════════════════════════════════════════════════════════════

class StepUploadResponse(BaseModel):
    """Returned by POST /catalog/upload-step on success.

    Every STEP upload lands in the existing pending_catalog_imports queue;
    this payload tells the caller the IDs to navigate to and surfaces
    whether a new supplier had to be auto-created.
    """
    pending_import_id: int
    supplier_document_id: int
    detected_supplier_id: int
    detected_supplier_name: str
    supplier_was_created: bool
    extraction_confidence: float
    warnings: List[str] = Field(default_factory=list)
