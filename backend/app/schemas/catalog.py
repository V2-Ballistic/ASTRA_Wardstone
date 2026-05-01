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

from pydantic import BaseModel, Field

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
    created_at: datetime
    updated_at: datetime
    created_by_id: int
    # Computed / aggregate fields populated by the response layer
    catalog_part_count: int = 0
    document_count: int = 0

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
    created_at: datetime
    updated_at: datetime
    created_by_id: int
    connectors: List[CatalogConnectorResponse] = Field(default_factory=list)


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


class PendingCatalogImportResponse(BaseModel):
    id: int
    source_document_id: int
    supplier_id: int
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
