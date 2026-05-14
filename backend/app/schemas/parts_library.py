"""
ASTRA — Parts Library & Mechanical Joints — Pydantic schemas
==============================================================
File: backend/app/schemas/parts_library.py   ← NEW
"""

from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.parts_library import (
    PartType, PartStatus, MaterialClass, ThreadStandard, HeadType,
    DriveType, LockingFeature, QualificationStatus, PendingPartsStatus,
    ConfidenceLevel, JointType, JointStatus, AssemblyParseJobStatus,
    BomStatus,
)


# ══════════════════════════════════════════════════════════════
#  LibraryPart
# ══════════════════════════════════════════════════════════════

class LibraryPartCreate(BaseModel):
    part_type:                PartType
    name:                     str = Field(..., min_length=1, max_length=500)
    description:              Optional[str] = None
    manufacturer_part_number: Optional[str] = Field(default=None, max_length=200)
    manufacturer_name:        Optional[str] = Field(default=None, max_length=200)
    cage_code:                Optional[str] = None
    nsn:                      Optional[str] = Field(default=None, max_length=20)
    drawing_number:           Optional[str] = Field(default=None, max_length=200)
    drawing_revision:         Optional[str] = Field(default=None, max_length=20)
    heritage:                 Optional[str] = None
    # Dimensional
    bounding_box_x_mm:        Optional[Decimal] = None
    bounding_box_y_mm:        Optional[Decimal] = None
    bounding_box_z_mm:        Optional[Decimal] = None
    volume_mm3:               Optional[Decimal] = None
    surface_area_mm2:         Optional[Decimal] = None
    thread_size:              Optional[str] = Field(default=None, max_length=50)
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
    material_name:            Optional[str] = Field(default=None, max_length=200)
    material_standard:        Optional[str] = Field(default=None, max_length=200)
    material_class:           Optional[MaterialClass] = None
    density_g_cm3:            Optional[Decimal] = None
    yield_strength_mpa:       Optional[Decimal] = None
    ultimate_strength_mpa:    Optional[Decimal] = None
    elastic_modulus_gpa:      Optional[Decimal] = None
    hardness:                 Optional[str] = Field(default=None, max_length=50)
    thermal_conductivity_wm:  Optional[Decimal] = None
    cte_um_m_c:               Optional[Decimal] = None
    corrosion_protection:     Optional[str] = Field(default=None, max_length=200)
    flammability_class:       Optional[str] = Field(default=None, max_length=100)
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
    lead_time_weeks:          Optional[int] = Field(default=None, ge=0)
    min_order_qty:            Optional[int] = Field(default=None, ge=1)
    preferred_supplier_id:    Optional[int] = None
    supplier_part_number:     Optional[str] = Field(default=None, max_length=200)
    qualification_status:     Optional[QualificationStatus] = QualificationStatus.UNQUALIFIED
    qualification_basis:      Optional[str] = None
    shelf_life_months:        Optional[int] = Field(default=None, gt=0)
    date_of_manufacture:      Optional[date] = None
    restricted_use:           bool = False
    restriction_notes:        Optional[str] = None

    @field_validator(
        "bounding_box_x_mm", "bounding_box_y_mm", "bounding_box_z_mm",
        "volume_mm3", "surface_area_mm2", "nominal_diameter_mm",
        "nominal_length_mm", "nominal_bore_mm", "cross_section_dia_mm",
        "flange_diameter_mm", "hole_pattern_dia_mm", "hole_pattern_pcd_mm",
        "density_g_cm3", "yield_strength_mpa", "ultimate_strength_mpa",
        "elastic_modulus_gpa", "thermal_conductivity_wm",
        "outgassing_tml_pct", "outgassing_cvcm_pct",
        "mass_nominal_g", "mass_max_g", "proof_load_n", "clamp_load_n",
        "torque_nominal_nm", "torque_min_nm", "torque_max_nm",
        "torque_lubricated_nm", "shear_strength_n", "bearing_load_n",
        "sealing_pressure_max_bar", "unit_cost_usd",
        mode="before",
    )
    @classmethod
    def _coerce_nonneg_decimal(cls, v: Any) -> Optional[Decimal]:
        if v is None or v == "":
            return None
        try:
            d = Decimal(str(v))
        except (InvalidOperation, ValueError):
            raise ValueError(f"Invalid numeric value: {v!r}")
        if d < 0:
            raise ValueError(f"Value must be non-negative, got {d}")
        return d

    @field_validator(
        "temperature_min_c", "temperature_max_c", "cte_um_m_c",
        "compression_set_pct",
        mode="before",
    )
    @classmethod
    def _coerce_decimal_allow_negative(cls, v: Any) -> Optional[Decimal]:
        if v is None or v == "":
            return None
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            raise ValueError(f"Invalid numeric value: {v!r}")

    @field_validator("cage_code", mode="before")
    @classmethod
    def _validate_cage(cls, v: Any) -> Optional[str]:
        if v is None or v == "":
            return None
        s = str(v).upper().strip()
        if len(s) != 5:
            raise ValueError("CAGE code must be exactly 5 characters")
        return s

    @model_validator(mode="after")
    def _validate_torque_range(self) -> "LibraryPartCreate":
        if (
            self.torque_min_nm is not None
            and self.torque_max_nm is not None
            and self.torque_min_nm > self.torque_max_nm
        ):
            raise ValueError(
                f"torque_min_nm ({self.torque_min_nm}) must be <= "
                f"torque_max_nm ({self.torque_max_nm})"
            )
        return self

    @model_validator(mode="after")
    def _validate_temperature_range(self) -> "LibraryPartCreate":
        if (
            self.temperature_min_c is not None
            and self.temperature_max_c is not None
            and self.temperature_min_c >= self.temperature_max_c
        ):
            raise ValueError(
                f"temperature_min_c ({self.temperature_min_c}) must be < "
                f"temperature_max_c ({self.temperature_max_c})"
            )
        return self

    @model_validator(mode="after")
    def _validate_mass_range(self) -> "LibraryPartCreate":
        if (
            self.mass_nominal_g is not None
            and self.mass_max_g is not None
            and self.mass_max_g < self.mass_nominal_g
        ):
            raise ValueError(
                f"mass_max_g ({self.mass_max_g}) must be >= "
                f"mass_nominal_g ({self.mass_nominal_g})"
            )
        return self


class LibraryPartUpdate(BaseModel):
    """All fields optional — PATCH semantics. Validators mirror Create."""
    part_type:                Optional[PartType] = None
    name:                     Optional[str] = Field(default=None, min_length=1, max_length=500)
    description:              Optional[str] = None
    manufacturer_part_number: Optional[str] = None
    manufacturer_name:        Optional[str] = None
    cage_code:                Optional[str] = None
    nsn:                      Optional[str] = None
    drawing_number:           Optional[str] = None
    drawing_revision:         Optional[str] = None
    heritage:                 Optional[str] = None
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
    mass_nominal_g:           Optional[Decimal] = None
    mass_max_g:               Optional[Decimal] = None
    proof_load_n:             Optional[Decimal] = None
    clamp_load_n:             Optional[Decimal] = None
    torque_nominal_nm:        Optional[Decimal] = None
    torque_min_nm:            Optional[Decimal] = None
    torque_max_nm:            Optional[Decimal] = None
    torque_lubricated_nm:     Optional[Decimal] = None
    locking_feature:          Optional[LockingFeature] = None
    safety_wire_holes:        Optional[bool] = None
    shear_strength_n:         Optional[Decimal] = None
    bearing_load_n:           Optional[Decimal] = None
    compression_set_pct:      Optional[Decimal] = None
    sealing_pressure_max_bar: Optional[Decimal] = None
    temperature_min_c:        Optional[Decimal] = None
    temperature_max_c:        Optional[Decimal] = None
    unit_cost_usd:            Optional[Decimal] = None
    lead_time_weeks:          Optional[int] = None
    min_order_qty:            Optional[int] = None
    preferred_supplier_id:    Optional[int] = None
    supplier_part_number:     Optional[str] = None
    qualification_status:     Optional[QualificationStatus] = None
    qualification_basis:      Optional[str] = None
    shelf_life_months:        Optional[int] = None
    date_of_manufacture:      Optional[date] = None
    restricted_use:           Optional[bool] = None
    restriction_notes:        Optional[str] = None

    @field_validator(
        "bounding_box_x_mm", "bounding_box_y_mm", "bounding_box_z_mm",
        "volume_mm3", "surface_area_mm2", "nominal_diameter_mm",
        "nominal_length_mm", "nominal_bore_mm", "cross_section_dia_mm",
        "flange_diameter_mm", "hole_pattern_dia_mm", "hole_pattern_pcd_mm",
        "density_g_cm3", "yield_strength_mpa", "ultimate_strength_mpa",
        "elastic_modulus_gpa", "thermal_conductivity_wm",
        "outgassing_tml_pct", "outgassing_cvcm_pct",
        "mass_nominal_g", "mass_max_g", "proof_load_n", "clamp_load_n",
        "torque_nominal_nm", "torque_min_nm", "torque_max_nm",
        "torque_lubricated_nm", "shear_strength_n", "bearing_load_n",
        "sealing_pressure_max_bar", "unit_cost_usd",
        mode="before",
    )
    @classmethod
    def _coerce_nonneg_decimal(cls, v: Any) -> Optional[Decimal]:
        if v is None or v == "":
            return None
        try:
            d = Decimal(str(v))
        except (InvalidOperation, ValueError):
            raise ValueError(f"Invalid numeric value: {v!r}")
        if d < 0:
            raise ValueError(f"Value must be non-negative, got {d}")
        return d

    @field_validator(
        "temperature_min_c", "temperature_max_c", "cte_um_m_c",
        "compression_set_pct",
        mode="before",
    )
    @classmethod
    def _coerce_decimal_allow_negative(cls, v: Any) -> Optional[Decimal]:
        if v is None or v == "":
            return None
        try:
            return Decimal(str(v))
        except (InvalidOperation, ValueError):
            raise ValueError(f"Invalid numeric value: {v!r}")


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


class LibraryPartResponse(BaseModel):
    """Full LibraryPart serialization."""
    model_config = ConfigDict(from_attributes=True)

    id:                       int
    wardstone_part_number:    str
    revision:                 str
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
    status:                   PartStatus
    superseded_by_id:         Optional[int] = None
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
    mass_nominal_g:           Optional[Decimal] = None
    mass_max_g:               Optional[Decimal] = None
    proof_load_n:             Optional[Decimal] = None
    clamp_load_n:             Optional[Decimal] = None
    torque_nominal_nm:        Optional[Decimal] = None
    torque_min_nm:            Optional[Decimal] = None
    torque_max_nm:            Optional[Decimal] = None
    torque_lubricated_nm:     Optional[Decimal] = None
    locking_feature:          Optional[LockingFeature] = None
    safety_wire_holes:        Optional[bool] = None
    shear_strength_n:         Optional[Decimal] = None
    bearing_load_n:           Optional[Decimal] = None
    compression_set_pct:      Optional[Decimal] = None
    sealing_pressure_max_bar: Optional[Decimal] = None
    temperature_min_c:        Optional[Decimal] = None
    temperature_max_c:        Optional[Decimal] = None
    unit_cost_usd:            Optional[Decimal] = None
    lead_time_weeks:          Optional[int] = None
    min_order_qty:            Optional[int] = None
    preferred_supplier_id:    Optional[int] = None
    supplier_part_number:     Optional[str] = None
    qualification_status:     Optional[QualificationStatus] = None
    qualification_basis:      Optional[str] = None
    shelf_life_months:        Optional[int] = None
    date_of_manufacture:      Optional[date] = None
    restricted_use:           bool = False
    restriction_notes:        Optional[str] = None
    step_file_id:             Optional[int] = None
    step_file_checksum:       Optional[str] = None
    step_entity_id:           Optional[str] = None
    approved_by_id:           Optional[int] = None
    approved_at:              Optional[datetime] = None
    created_at:               datetime
    updated_at:               datetime
    created_by_id:            Optional[int] = None


# ══════════════════════════════════════════════════════════════
#  ProjectPart
# ══════════════════════════════════════════════════════════════

# ── PROJPARTS-001 Path C: nested summaries for BOM responses ──
# Defined locally rather than imported to avoid a cross-module cycle
# (interface.py imports from this file, catalog.py is a heavyweight
# module). These two summaries carry only what the BOM grid needs.

class ProjectPartCatalogSummary(BaseModel):
    """Slim catalog_part payload embedded in ProjectPartResponse."""
    model_config = ConfigDict(from_attributes=True)

    id:               int
    part_number:      str
    name:             str
    part_class:       str
    lifecycle_status: str
    revision:         Optional[str]  = None
    supplier_name:    Optional[str]  = None
    mass_kg:          Optional[Decimal] = None


class ProjectPartUnitSummary(BaseModel):
    """Slim unit payload for the `linked_unit` field on BOM lines."""
    model_config = ConfigDict(from_attributes=True)

    id:          int
    unit_id:     str
    name:        str
    designation: str
    system_id:   int


class ProjectPartCreate(BaseModel):
    # `library_part_id` stays for back-compat with old callers and the
    # mechanical-joint surface, but Path C makes the catalog link the
    # canonical reference. Either may be supplied; if both are present
    # the catalog FK wins for display + class filtering.
    library_part_id:    Optional[int] = None
    catalog_part_id:    Optional[int] = None
    quantity:           Decimal       = Field(default=Decimal("1"), gt=0)
    quantity_unit:      str           = Field(default="each", max_length=16)
    designation:        Optional[str] = Field(default=None, max_length=255)
    bom_position:       Optional[str] = Field(default=None, max_length=64)
    parent_bom_id:      Optional[int] = None
    status:             BomStatus     = BomStatus.PLANNED
    unit_id:            Optional[int] = None
    location_zone:      Optional[str] = Field(default=None, max_length=128)
    installation_notes: Optional[str] = None
    procurement_notes:  Optional[str] = None
    notes:              Optional[str] = None

    @model_validator(mode="after")
    def _require_part_reference(self) -> "ProjectPartCreate":
        if self.library_part_id is None and self.catalog_part_id is None:
            raise ValueError(
                "ProjectPartCreate requires at least one of "
                "`library_part_id` or `catalog_part_id`."
            )
        return self


class ProjectPartUpdate(BaseModel):
    catalog_part_id:    Optional[int]       = None
    quantity:           Optional[Decimal]   = Field(default=None, gt=0)
    quantity_unit:      Optional[str]       = Field(default=None, max_length=16)
    designation:        Optional[str]       = Field(default=None, max_length=255)
    bom_position:       Optional[str]       = Field(default=None, max_length=64)
    parent_bom_id:      Optional[int]       = None
    status:             Optional[BomStatus] = None
    unit_id:            Optional[int]       = None
    location_zone:      Optional[str]       = Field(default=None, max_length=128)
    installation_notes: Optional[str]       = None
    procurement_notes:  Optional[str]       = None
    notes:              Optional[str]       = None


class ProjectPartResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                 int
    project_id:         int
    library_part_id:    Optional[int] = None
    catalog_part_id:    Optional[int] = None
    quantity:           Decimal
    quantity_unit:      str
    designation:        Optional[str] = None
    bom_position:       Optional[str] = None
    parent_bom_id:      Optional[int] = None
    status:             BomStatus
    unit_id:            Optional[int] = None
    location_zone:      Optional[str] = None
    installation_notes: Optional[str] = None
    procurement_notes:  Optional[str] = None
    notes:              Optional[str] = None
    added_at:           datetime
    updated_at:         Optional[datetime] = None

    library_part:         Optional[LibraryPartSummary] = None
    catalog_part_summary: Optional[ProjectPartCatalogSummary] = None
    linked_unit:          Optional[ProjectPartUnitSummary] = None
    parent_designation:   Optional[str] = None

    system_id:       Optional[int] = None  # resolved from SystemPartAssignment


class ProjectPartListItem(BaseModel):
    """Lighter row payload for the BOM grid (no nested library_part)."""
    model_config = ConfigDict(from_attributes=True)

    id:                   int
    project_id:           int
    catalog_part_id:      Optional[int] = None
    library_part_id:      Optional[int] = None
    quantity:             Decimal
    quantity_unit:        str
    designation:          Optional[str] = None
    bom_position:         Optional[str] = None
    parent_bom_id:        Optional[int] = None
    parent_designation:   Optional[str] = None
    status:               BomStatus
    unit_id:              Optional[int] = None
    linked_unit:          Optional[ProjectPartUnitSummary] = None
    location_zone:        Optional[str] = None
    catalog_part_summary: Optional[ProjectPartCatalogSummary] = None
    added_at:             datetime
    updated_at:           Optional[datetime] = None


class BomStatsResponse(BaseModel):
    """Aggregated counts for the BOM stat strip."""
    total:         int
    by_status:     dict[str, int]
    by_part_class: dict[str, int]


# ══════════════════════════════════════════════════════════════
#  SystemPartAssignment
# ══════════════════════════════════════════════════════════════

class SystemPartAssignmentCreate(BaseModel):
    project_part_id: int
    position_order:  int = 0


class SystemPartAssignmentUpdate(BaseModel):
    position_order: Optional[int] = None


class SystemPartAssignmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:              int
    system_id:       int
    project_part_id: int
    position_order:  int
    assigned_at:     datetime
    project_part:    ProjectPartResponse


# ══════════════════════════════════════════════════════════════
#  MechanicalJoint
# ══════════════════════════════════════════════════════════════

class MechanicalJointCreate(BaseModel):
    joint_type:                 JointType
    part_a_id:                  int
    part_b_id:                  int
    fastener_part_id:           Optional[int] = None
    fastener_count:             Optional[int] = None
    torque_nominal_nm:          Optional[Decimal] = None
    torque_min_nm:              Optional[Decimal] = None
    torque_max_nm:              Optional[Decimal] = None
    engagement_length_mm:       Optional[Decimal] = None
    locking_feature:            Optional[LockingFeature] = None
    hole_pattern_description:   Optional[str] = Field(default=None, max_length=300)
    mating_surface_flatness_mm: Optional[Decimal] = None
    mating_surface_finish_ra:   Optional[Decimal] = None
    seal_part_id:               Optional[int] = None
    leak_rate_max_scc_s:        Optional[Decimal] = None
    test_pressure_bar:          Optional[Decimal] = None
    interface_drawing:          Optional[str] = Field(default=None, max_length=200)
    notes:                      Optional[str] = None

    @field_validator(
        "torque_nominal_nm", "torque_min_nm", "torque_max_nm",
        "engagement_length_mm", "mating_surface_flatness_mm",
        "mating_surface_finish_ra", "leak_rate_max_scc_s",
        "test_pressure_bar",
        mode="before",
    )
    @classmethod
    def _coerce_decimal(cls, v: Any) -> Optional[Decimal]:
        if v is None or v == "":
            return None
        try:
            d = Decimal(str(v))
        except (InvalidOperation, ValueError):
            raise ValueError(f"Invalid numeric value: {v!r}")
        if d < 0:
            raise ValueError(f"Value must be non-negative, got {d}")
        return d

    @model_validator(mode="after")
    def _validate_parts_different(self) -> "MechanicalJointCreate":
        if self.part_a_id == self.part_b_id:
            raise ValueError("part_a_id and part_b_id must be different parts")
        return self

    @model_validator(mode="after")
    def _validate_torque_range(self) -> "MechanicalJointCreate":
        if (
            self.torque_min_nm is not None
            and self.torque_max_nm is not None
            and self.torque_min_nm > self.torque_max_nm
        ):
            raise ValueError(
                f"torque_min_nm ({self.torque_min_nm}) must be <= "
                f"torque_max_nm ({self.torque_max_nm})"
            )
        return self

    @model_validator(mode="after")
    def _validate_fastener_count(self) -> "MechanicalJointCreate":
        if self.fastener_count is not None and self.fastener_count < 1:
            raise ValueError("fastener_count must be >= 1")
        return self


class MechanicalJointUpdate(BaseModel):
    joint_type:                 Optional[JointType] = None
    part_a_id:                  Optional[int] = None
    part_b_id:                  Optional[int] = None
    fastener_part_id:           Optional[int] = None
    fastener_count:             Optional[int] = None
    torque_nominal_nm:          Optional[Decimal] = None
    torque_min_nm:              Optional[Decimal] = None
    torque_max_nm:              Optional[Decimal] = None
    engagement_length_mm:       Optional[Decimal] = None
    locking_feature:            Optional[LockingFeature] = None
    hole_pattern_description:   Optional[str] = None
    mating_surface_flatness_mm: Optional[Decimal] = None
    mating_surface_finish_ra:   Optional[Decimal] = None
    seal_part_id:               Optional[int] = None
    leak_rate_max_scc_s:        Optional[Decimal] = None
    test_pressure_bar:          Optional[Decimal] = None
    interface_drawing:          Optional[str] = None
    notes:                      Optional[str] = None


class MechanicalJointResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                         int
    joint_id:                   str
    project_id:                 int
    joint_type:                 JointType
    part_a_id:                  int
    part_b_id:                  int
    fastener_part_id:           Optional[int] = None
    fastener_count:             Optional[int] = None
    torque_nominal_nm:          Optional[Decimal] = None
    torque_min_nm:              Optional[Decimal] = None
    torque_max_nm:              Optional[Decimal] = None
    engagement_length_mm:       Optional[Decimal] = None
    locking_feature:            Optional[LockingFeature] = None
    hole_pattern_description:   Optional[str] = None
    mating_surface_flatness_mm: Optional[Decimal] = None
    mating_surface_finish_ra:   Optional[Decimal] = None
    seal_part_id:               Optional[int] = None
    leak_rate_max_scc_s:        Optional[Decimal] = None
    test_pressure_bar:          Optional[Decimal] = None
    interface_drawing:          Optional[str] = None
    source_step_file_id:        Optional[int] = None
    source_step_entity:         Optional[str] = None
    confidence:                 Optional[ConfidenceLevel] = None
    status:                     JointStatus
    notes:                      Optional[str] = None
    created_at:                 datetime
    updated_at:                 datetime
    created_by_id:              Optional[int] = None
    fastener_part:              Optional[LibraryPartSummary] = None
    seal_part:                  Optional[LibraryPartSummary] = None


# ══════════════════════════════════════════════════════════════
#  Pending parts import (review queue)
# ══════════════════════════════════════════════════════════════

class PendingPartsImportApprove(BaseModel):
    overrides:    dict[str, Any] = Field(default_factory=dict)
    supplier_id:  Optional[int] = None


class PendingPartsImportReject(BaseModel):
    reason: str = Field(..., min_length=1, max_length=2000)


class PendingPartsImportResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:                    int
    document_id:           int
    status:                PendingPartsStatus
    proposed_data:         dict[str, Any]
    confidence_scores:     dict[str, Any]
    low_confidence_fields: list[str]
    extraction_log:        Optional[str] = None
    parser_version:        Optional[str] = None
    library_part_id:       Optional[int] = None
    rejection_reason:      Optional[str] = None
    created_at:            datetime


# ══════════════════════════════════════════════════════════════
#  Assembly parse job
# ══════════════════════════════════════════════════════════════

class AssemblyParseJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id:           int
    project_id:   int
    document_id:  Optional[int] = None
    status:       AssemblyParseJobStatus
    progress_log: Optional[str] = None
    result:       Optional[dict[str, Any]] = None
    error:        Optional[str] = None
    created_at:   Optional[datetime] = None
    completed_at: Optional[datetime] = None
