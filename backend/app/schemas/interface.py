"""
ASTRA — Interface Control Document (ICD) Schemas
====================================================
File: backend/app/schemas/interface.py   ← NEW

Pydantic schemas for all 15 ICD models:
  Create, Update (partial), Response, Detail
Plus aggregate/view schemas:
  N2Matrix, BlockDiagram, SignalTrace, InterfaceCoverage,
  AutoReqGenerationResult, ImpactPreview, WiringDiagramData
"""

from datetime import datetime
from typing import Optional, List, Any, Dict
from pydantic import BaseModel, Field


# ══════════════════════════════════════════════════════════════
#  1. System
# ══════════════════════════════════════════════════════════════

class SystemCreate(BaseModel):
    name: str = Field(..., max_length=255)
    abbreviation: Optional[str] = Field(None, max_length=30)
    description: Optional[str] = None
    system_type: str = Field(...)
    system_type_custom: Optional[str] = Field(None, max_length=100)
    status: Optional[str] = "concept"
    parent_system_id: Optional[int] = None
    wbs_number: Optional[str] = Field(None, max_length=30)
    responsible_org: Optional[str] = Field(None, max_length=255)


class SystemUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    abbreviation: Optional[str] = Field(None, max_length=30)
    description: Optional[str] = None
    system_type: Optional[str] = None
    system_type_custom: Optional[str] = Field(None, max_length=100)
    status: Optional[str] = None
    parent_system_id: Optional[int] = None
    wbs_number: Optional[str] = Field(None, max_length=30)
    responsible_org: Optional[str] = Field(None, max_length=255)


class SystemResponse(BaseModel):
    id: int
    system_id: str
    name: str
    abbreviation: Optional[str]
    description: Optional[str]
    system_type: str
    system_type_custom: Optional[str]
    status: str
    parent_system_id: Optional[int]
    wbs_number: Optional[str]
    responsible_org: Optional[str]
    project_id: int
    owner_id: int
    created_at: datetime
    updated_at: datetime
    # Computed
    unit_count: int = 0
    interface_count: int = 0

    class Config:
        from_attributes = True


# NOTE: SystemDetail defined after UnitSummary (see below)


# ══════════════════════════════════════════════════════════════
#  2. Unit
# ══════════════════════════════════════════════════════════════

class UnitCreate(BaseModel):
    name: str = Field(..., max_length=255)
    designation: str = Field(..., max_length=50)
    part_number: str = Field(..., max_length=100)
    manufacturer: str = Field(..., max_length=255)
    unit_type: str = Field(...)
    system_id: int
    # Optional identifiers
    unit_type_custom: Optional[str] = Field(None, max_length=100)
    cage_code: Optional[str] = Field(None, max_length=10)
    nsn: Optional[str] = Field(None, max_length=20)
    drawing_number: Optional[str] = Field(None, max_length=50)
    revision: Optional[str] = Field(None, max_length=20)
    serial_number_prefix: Optional[str] = Field(None, max_length=30)
    status: Optional[str] = "concept"
    heritage: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    # Physical
    mass_kg: Optional[float] = None
    mass_max_kg: Optional[float] = None
    dimensions_l_mm: Optional[float] = None
    dimensions_w_mm: Optional[float] = None
    dimensions_h_mm: Optional[float] = None
    volume_cc: Optional[float] = None
    # Electrical
    power_watts_nominal: Optional[float] = None
    power_watts_peak: Optional[float] = None
    power_watts_standby: Optional[float] = None
    voltage_input_nominal: Optional[str] = Field(None, max_length=30)
    voltage_input_min: Optional[float] = None
    voltage_input_max: Optional[float] = None
    voltage_ripple_max_mvpp: Optional[float] = None
    current_inrush_amps: Optional[float] = None
    current_steady_state_amps: Optional[float] = None
    # Thermal
    temp_operating_min_c: Optional[float] = None
    temp_operating_max_c: Optional[float] = None
    temp_storage_min_c: Optional[float] = None
    temp_storage_max_c: Optional[float] = None
    temp_survival_min_c: Optional[float] = None
    temp_survival_max_c: Optional[float] = None
    # Mechanical
    vibration_random_grms: Optional[float] = None
    vibration_sine_g_peak: Optional[float] = None
    shock_mechanical_g: Optional[float] = None
    shock_mechanical_duration_ms: Optional[float] = None
    shock_pyrotechnic_g: Optional[float] = None
    acceleration_max_g: Optional[float] = None
    acoustic_spl_db: Optional[float] = None
    # Climate
    humidity_min_pct: Optional[float] = None
    humidity_max_pct: Optional[float] = None
    altitude_operating_max_m: Optional[float] = None
    altitude_storage_max_m: Optional[float] = None
    pressure_min_kpa: Optional[float] = None
    pressure_max_kpa: Optional[float] = None
    sand_dust_exposed: Optional[bool] = False
    salt_fog_exposed: Optional[bool] = False
    fungus_resistant: Optional[bool] = False
    # EMI/EMC
    emi_ce101_limit_dba: Optional[float] = None
    emi_ce102_limit_dbua: Optional[float] = None
    emi_cs101_limit_db: Optional[float] = None
    emi_cs114_limit_dba: Optional[float] = None
    emi_cs115_limit_v: Optional[float] = None
    emi_cs116_limit_db: Optional[float] = None
    emi_re101_limit_dba: Optional[float] = None
    emi_re102_limit_dbm: Optional[float] = None
    emi_rs101_limit_db: Optional[float] = None
    emi_rs103_limit_vm: Optional[float] = None
    esd_hbm_v: Optional[float] = None
    esd_cdm_v: Optional[float] = None
    # Radiation
    radiation_tid_krad: Optional[float] = None
    radiation_see_let_threshold: Optional[float] = None
    radiation_dd_mev_cm2_g: Optional[float] = None
    # Reliability
    mtbf_hours: Optional[float] = None
    mtbf_environment: Optional[str] = Field(None, max_length=30)
    design_life_years: Optional[float] = None
    duty_cycle_pct: Optional[float] = None
    derating_standard: Optional[str] = Field(None, max_length=50)
    # References
    datasheet_url: Optional[str] = Field(None, max_length=500)
    specification_doc: Optional[str] = Field(None, max_length=255)
    test_report_doc: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None


class UnitUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    designation: Optional[str] = Field(None, max_length=50)
    part_number: Optional[str] = Field(None, max_length=100)
    manufacturer: Optional[str] = Field(None, max_length=255)
    unit_type: Optional[str] = None
    unit_type_custom: Optional[str] = Field(None, max_length=100)
    system_id: Optional[int] = None
    cage_code: Optional[str] = Field(None, max_length=10)
    nsn: Optional[str] = Field(None, max_length=20)
    drawing_number: Optional[str] = Field(None, max_length=50)
    revision: Optional[str] = Field(None, max_length=20)
    serial_number_prefix: Optional[str] = Field(None, max_length=30)
    status: Optional[str] = None
    heritage: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    # Physical
    mass_kg: Optional[float] = None
    mass_max_kg: Optional[float] = None
    dimensions_l_mm: Optional[float] = None
    dimensions_w_mm: Optional[float] = None
    dimensions_h_mm: Optional[float] = None
    volume_cc: Optional[float] = None
    # Electrical
    power_watts_nominal: Optional[float] = None
    power_watts_peak: Optional[float] = None
    power_watts_standby: Optional[float] = None
    voltage_input_nominal: Optional[str] = Field(None, max_length=30)
    voltage_input_min: Optional[float] = None
    voltage_input_max: Optional[float] = None
    voltage_ripple_max_mvpp: Optional[float] = None
    current_inrush_amps: Optional[float] = None
    current_steady_state_amps: Optional[float] = None
    # Thermal
    temp_operating_min_c: Optional[float] = None
    temp_operating_max_c: Optional[float] = None
    temp_storage_min_c: Optional[float] = None
    temp_storage_max_c: Optional[float] = None
    temp_survival_min_c: Optional[float] = None
    temp_survival_max_c: Optional[float] = None
    # Mechanical
    vibration_random_grms: Optional[float] = None
    vibration_sine_g_peak: Optional[float] = None
    shock_mechanical_g: Optional[float] = None
    shock_mechanical_duration_ms: Optional[float] = None
    shock_pyrotechnic_g: Optional[float] = None
    acceleration_max_g: Optional[float] = None
    acoustic_spl_db: Optional[float] = None
    # Climate
    humidity_min_pct: Optional[float] = None
    humidity_max_pct: Optional[float] = None
    altitude_operating_max_m: Optional[float] = None
    altitude_storage_max_m: Optional[float] = None
    pressure_min_kpa: Optional[float] = None
    pressure_max_kpa: Optional[float] = None
    sand_dust_exposed: Optional[bool] = None
    salt_fog_exposed: Optional[bool] = None
    fungus_resistant: Optional[bool] = None
    # EMI/EMC
    emi_ce101_limit_dba: Optional[float] = None
    emi_ce102_limit_dbua: Optional[float] = None
    emi_cs101_limit_db: Optional[float] = None
    emi_cs114_limit_dba: Optional[float] = None
    emi_cs115_limit_v: Optional[float] = None
    emi_cs116_limit_db: Optional[float] = None
    emi_re101_limit_dba: Optional[float] = None
    emi_re102_limit_dbm: Optional[float] = None
    emi_rs101_limit_db: Optional[float] = None
    emi_rs103_limit_vm: Optional[float] = None
    esd_hbm_v: Optional[float] = None
    esd_cdm_v: Optional[float] = None
    # Radiation
    radiation_tid_krad: Optional[float] = None
    radiation_see_let_threshold: Optional[float] = None
    radiation_dd_mev_cm2_g: Optional[float] = None
    # Reliability
    mtbf_hours: Optional[float] = None
    mtbf_environment: Optional[str] = Field(None, max_length=30)
    design_life_years: Optional[float] = None
    duty_cycle_pct: Optional[float] = None
    derating_standard: Optional[str] = Field(None, max_length=50)
    # References
    datasheet_url: Optional[str] = Field(None, max_length=500)
    specification_doc: Optional[str] = Field(None, max_length=255)
    test_report_doc: Optional[str] = Field(None, max_length=255)
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None


class UnitSummary(BaseModel):
    id: int
    unit_id: str
    name: str
    designation: str
    part_number: str
    manufacturer: str
    unit_type: str
    status: str
    connector_count: int = 0
    bus_count: int = 0

    class Config:
        from_attributes = True


class UnitResponse(BaseModel):
    id: int
    unit_id: str
    name: str
    designation: str
    description: Optional[str]
    part_number: str
    manufacturer: str
    cage_code: Optional[str]
    nsn: Optional[str]
    drawing_number: Optional[str]
    revision: Optional[str]
    serial_number_prefix: Optional[str]
    unit_type: str
    unit_type_custom: Optional[str]
    status: str
    heritage: Optional[str]
    # Physical
    mass_kg: Optional[float]
    mass_max_kg: Optional[float]
    dimensions_l_mm: Optional[float]
    dimensions_w_mm: Optional[float]
    dimensions_h_mm: Optional[float]
    volume_cc: Optional[float]
    # Electrical
    power_watts_nominal: Optional[float]
    power_watts_peak: Optional[float]
    power_watts_standby: Optional[float]
    voltage_input_nominal: Optional[str]
    voltage_input_min: Optional[float]
    voltage_input_max: Optional[float]
    voltage_ripple_max_mvpp: Optional[float]
    current_inrush_amps: Optional[float]
    current_steady_state_amps: Optional[float]
    # Thermal
    temp_operating_min_c: Optional[float]
    temp_operating_max_c: Optional[float]
    temp_storage_min_c: Optional[float]
    temp_storage_max_c: Optional[float]
    temp_survival_min_c: Optional[float]
    temp_survival_max_c: Optional[float]
    # Mechanical
    vibration_random_grms: Optional[float]
    vibration_sine_g_peak: Optional[float]
    shock_mechanical_g: Optional[float]
    shock_mechanical_duration_ms: Optional[float]
    shock_pyrotechnic_g: Optional[float]
    acceleration_max_g: Optional[float]
    acoustic_spl_db: Optional[float]
    # Climate
    humidity_min_pct: Optional[float]
    humidity_max_pct: Optional[float]
    altitude_operating_max_m: Optional[float]
    altitude_storage_max_m: Optional[float]
    pressure_min_kpa: Optional[float]
    pressure_max_kpa: Optional[float]
    sand_dust_exposed: Optional[bool]
    salt_fog_exposed: Optional[bool]
    fungus_resistant: Optional[bool]
    # EMI/EMC
    emi_ce101_limit_dba: Optional[float]
    emi_ce102_limit_dbua: Optional[float]
    emi_cs101_limit_db: Optional[float]
    emi_cs114_limit_dba: Optional[float]
    emi_cs115_limit_v: Optional[float]
    emi_cs116_limit_db: Optional[float]
    emi_re101_limit_dba: Optional[float]
    emi_re102_limit_dbm: Optional[float]
    emi_rs101_limit_db: Optional[float]
    emi_rs103_limit_vm: Optional[float]
    esd_hbm_v: Optional[float]
    esd_cdm_v: Optional[float]
    # Radiation
    radiation_tid_krad: Optional[float]
    radiation_see_let_threshold: Optional[float]
    radiation_dd_mev_cm2_g: Optional[float]
    # Reliability
    mtbf_hours: Optional[float]
    mtbf_environment: Optional[str]
    design_life_years: Optional[float]
    duty_cycle_pct: Optional[float]
    derating_standard: Optional[str]
    # References
    datasheet_url: Optional[str]
    specification_doc: Optional[str]
    test_report_doc: Optional[str]
    notes: Optional[str]
    metadata_json: Optional[dict]
    # FKs
    system_id: int
    project_id: int
    created_at: datetime
    updated_at: datetime
    # Computed
    connector_count: int = 0
    bus_count: int = 0
    message_count: int = 0

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  4. Pin  (defined before Connector so ConnectorWithPins works)
# ══════════════════════════════════════════════════════════════

class PinCreate(BaseModel):
    pin_number: str = Field(..., max_length=10)
    signal_name: str = Field(..., max_length=150)
    signal_type: str = Field(...)
    direction: str = Field(...)
    # Optional
    pin_label: Optional[str] = Field(None, max_length=30)
    signal_type_custom: Optional[str] = Field(None, max_length=100)
    pin_size: Optional[str] = None
    contact_type: Optional[str] = Field(None, max_length=30)
    voltage_nominal: Optional[str] = Field(None, max_length=30)
    voltage_min: Optional[float] = None
    voltage_max: Optional[float] = None
    voltage_dc_bias: Optional[float] = None
    current_nominal_amps: Optional[float] = None
    current_max_amps: Optional[float] = None
    impedance_ohms: Optional[float] = None
    frequency_mhz: Optional[float] = None
    rise_time_ns: Optional[float] = None
    termination: Optional[str] = Field(None, max_length=50)
    pull_up_down: Optional[str] = Field(None, max_length=30)
    esd_protection: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    notes: Optional[str] = None


class PinUpdate(BaseModel):
    pin_number: Optional[str] = Field(None, max_length=10)
    signal_name: Optional[str] = Field(None, max_length=150)
    signal_type: Optional[str] = None
    direction: Optional[str] = None
    pin_label: Optional[str] = Field(None, max_length=30)
    signal_type_custom: Optional[str] = Field(None, max_length=100)
    pin_size: Optional[str] = None
    contact_type: Optional[str] = Field(None, max_length=30)
    voltage_nominal: Optional[str] = Field(None, max_length=30)
    voltage_min: Optional[float] = None
    voltage_max: Optional[float] = None
    voltage_dc_bias: Optional[float] = None
    current_nominal_amps: Optional[float] = None
    current_max_amps: Optional[float] = None
    impedance_ohms: Optional[float] = None
    frequency_mhz: Optional[float] = None
    rise_time_ns: Optional[float] = None
    termination: Optional[str] = Field(None, max_length=50)
    pull_up_down: Optional[str] = Field(None, max_length=30)
    esd_protection: Optional[str] = Field(None, max_length=50)
    description: Optional[str] = None
    notes: Optional[str] = None


class PinBatchCreate(BaseModel):
    pins: List[PinCreate] = Field(..., min_length=1)


# ── PinBusAssignment (needed by PinResponse) ──

class PinBusAssignmentCreate(BaseModel):
    pin_id: int
    bus_def_id: int
    pin_role: str = Field(...)
    pin_role_custom: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = Field(None, max_length=255)


class PinBusAssignmentResponse(BaseModel):
    id: int
    pin_id: int
    bus_def_id: int
    pin_role: str
    pin_role_custom: Optional[str]
    notes: Optional[str]
    created_at: datetime
    # Computed joins
    pin_number: Optional[str] = None
    signal_name: Optional[str] = None
    connector_designator: Optional[str] = None

    class Config:
        from_attributes = True


class PinResponse(BaseModel):
    id: int
    pin_number: str
    pin_label: Optional[str]
    signal_name: str
    signal_type: str
    signal_type_custom: Optional[str]
    direction: str
    pin_size: Optional[str]
    contact_type: Optional[str]
    voltage_nominal: Optional[str]
    voltage_min: Optional[float]
    voltage_max: Optional[float]
    voltage_dc_bias: Optional[float]
    current_nominal_amps: Optional[float]
    current_max_amps: Optional[float]
    impedance_ohms: Optional[float]
    frequency_mhz: Optional[float]
    rise_time_ns: Optional[float]
    termination: Optional[str]
    pull_up_down: Optional[str]
    esd_protection: Optional[str]
    description: Optional[str]
    notes: Optional[str]
    connector_id: int
    created_at: datetime
    # Computed
    bus_assignment: Optional[PinBusAssignmentResponse] = None

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  3. Connector
# ══════════════════════════════════════════════════════════════

class ConnectorCreate(BaseModel):
    designator: str = Field(..., max_length=20)
    connector_type: str = Field(...)
    gender: str = Field(...)
    total_contacts: int = Field(...)
    unit_id: int
    # Optional
    connector_type_custom: Optional[str] = Field(None, max_length=100)
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    mounting: Optional[str] = None
    mounting_custom: Optional[str] = Field(None, max_length=100)
    shell_size: Optional[str] = Field(None, max_length=20)
    insert_arrangement: Optional[str] = Field(None, max_length=30)
    signal_contacts: Optional[int] = None
    power_contacts: Optional[int] = None
    coax_contacts: Optional[int] = None
    fiber_contacts: Optional[int] = None
    spare_contacts: Optional[int] = None
    keying: Optional[str] = Field(None, max_length=50)
    polarization: Optional[str] = Field(None, max_length=30)
    coupling: Optional[str] = Field(None, max_length=30)
    ip_rating: Optional[str] = Field(None, max_length=10)
    operating_temp_min_c: Optional[float] = None
    operating_temp_max_c: Optional[float] = None
    mating_cycles: Optional[int] = None
    shell_material: Optional[str] = None
    shell_finish: Optional[str] = None
    contact_finish: Optional[str] = None
    mil_spec: Optional[str] = Field(None, max_length=80)
    manufacturer_part_number: Optional[str] = Field(None, max_length=100)
    connector_manufacturer: Optional[str] = Field(None, max_length=255)
    backshell_type: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    # Batch create pins with connector
    pins: Optional[List[PinCreate]] = None


class ConnectorUpdate(BaseModel):
    designator: Optional[str] = Field(None, max_length=20)
    connector_type: Optional[str] = None
    connector_type_custom: Optional[str] = Field(None, max_length=100)
    gender: Optional[str] = None
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    mounting: Optional[str] = None
    mounting_custom: Optional[str] = Field(None, max_length=100)
    shell_size: Optional[str] = Field(None, max_length=20)
    insert_arrangement: Optional[str] = Field(None, max_length=30)
    total_contacts: Optional[int] = None
    signal_contacts: Optional[int] = None
    power_contacts: Optional[int] = None
    coax_contacts: Optional[int] = None
    fiber_contacts: Optional[int] = None
    spare_contacts: Optional[int] = None
    keying: Optional[str] = Field(None, max_length=50)
    polarization: Optional[str] = Field(None, max_length=30)
    coupling: Optional[str] = Field(None, max_length=30)
    ip_rating: Optional[str] = Field(None, max_length=10)
    operating_temp_min_c: Optional[float] = None
    operating_temp_max_c: Optional[float] = None
    mating_cycles: Optional[int] = None
    shell_material: Optional[str] = None
    shell_finish: Optional[str] = None
    contact_finish: Optional[str] = None
    mil_spec: Optional[str] = Field(None, max_length=80)
    manufacturer_part_number: Optional[str] = Field(None, max_length=100)
    connector_manufacturer: Optional[str] = Field(None, max_length=255)
    backshell_type: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class ConnectorResponse(BaseModel):
    id: int
    connector_id: Optional[str]
    designator: str
    name: Optional[str]
    description: Optional[str]
    connector_type: str
    connector_type_custom: Optional[str]
    gender: str
    mounting: Optional[str]
    mounting_custom: Optional[str]
    shell_size: Optional[str]
    insert_arrangement: Optional[str]
    total_contacts: int
    signal_contacts: Optional[int]
    power_contacts: Optional[int]
    coax_contacts: Optional[int]
    fiber_contacts: Optional[int]
    spare_contacts: Optional[int]
    keying: Optional[str]
    polarization: Optional[str]
    coupling: Optional[str]
    ip_rating: Optional[str]
    operating_temp_min_c: Optional[float]
    operating_temp_max_c: Optional[float]
    mating_cycles: Optional[int]
    shell_material: Optional[str]
    shell_finish: Optional[str]
    contact_finish: Optional[str]
    mil_spec: Optional[str]
    manufacturer_part_number: Optional[str]
    connector_manufacturer: Optional[str]
    backshell_type: Optional[str]
    notes: Optional[str]
    unit_id: int
    project_id: Optional[int]
    created_at: datetime
    # Computed
    pin_count: int = 0
    assigned_pin_count: int = 0

    class Config:
        from_attributes = True


class ConnectorWithPins(ConnectorResponse):
    pins: List[PinResponse] = []


# ══════════════════════════════════════════════════════════════
#  5. BusDefinition
# ══════════════════════════════════════════════════════════════

class BusDefinitionCreate(BaseModel):
    name: str = Field(..., max_length=255)
    protocol: str = Field(...)
    bus_role: str = Field(...)
    unit_id: int
    # Optional
    protocol_custom: Optional[str] = Field(None, max_length=100)
    protocol_version: Optional[str] = Field(None, max_length=20)
    bus_role_custom: Optional[str] = Field(None, max_length=100)
    bus_address: Optional[str] = Field(None, max_length=30)
    bus_address_secondary: Optional[str] = Field(None, max_length=30)
    bus_name_network: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    data_rate: Optional[str] = Field(None, max_length=30)
    data_rate_actual_bps: Optional[int] = None
    word_size_bits: Optional[int] = None
    frame_size_max_bytes: Optional[int] = None
    topology: Optional[str] = None
    redundancy: Optional[str] = "none"
    deterministic: Optional[bool] = None
    fault_tolerance: Optional[str] = Field(None, max_length=100)
    bus_loading_max_pct: Optional[float] = None
    latency_budget_ms: Optional[float] = None
    jitter_max_us: Optional[float] = None
    error_rate_max: Optional[str] = Field(None, max_length=30)
    encoding: Optional[str] = Field(None, max_length=50)
    electrical_standard: Optional[str] = Field(None, max_length=50)
    coupling: Optional[str] = Field(None, max_length=50)
    stub_length_max_m: Optional[float] = None
    bus_length_max_m: Optional[float] = None
    termination_required: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None


class BusDefinitionUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    protocol: Optional[str] = None
    protocol_custom: Optional[str] = Field(None, max_length=100)
    protocol_version: Optional[str] = Field(None, max_length=20)
    bus_role: Optional[str] = None
    bus_role_custom: Optional[str] = Field(None, max_length=100)
    bus_address: Optional[str] = Field(None, max_length=30)
    bus_address_secondary: Optional[str] = Field(None, max_length=30)
    bus_name_network: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    data_rate: Optional[str] = Field(None, max_length=30)
    data_rate_actual_bps: Optional[int] = None
    word_size_bits: Optional[int] = None
    frame_size_max_bytes: Optional[int] = None
    topology: Optional[str] = None
    redundancy: Optional[str] = None
    deterministic: Optional[bool] = None
    fault_tolerance: Optional[str] = Field(None, max_length=100)
    bus_loading_max_pct: Optional[float] = None
    latency_budget_ms: Optional[float] = None
    jitter_max_us: Optional[float] = None
    error_rate_max: Optional[str] = Field(None, max_length=30)
    encoding: Optional[str] = Field(None, max_length=50)
    electrical_standard: Optional[str] = Field(None, max_length=50)
    coupling: Optional[str] = Field(None, max_length=50)
    stub_length_max_m: Optional[float] = None
    bus_length_max_m: Optional[float] = None
    termination_required: Optional[str] = Field(None, max_length=50)
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None


class BusDefinitionResponse(BaseModel):
    id: int
    bus_def_id: Optional[str]
    name: str
    description: Optional[str]
    protocol: str
    protocol_custom: Optional[str]
    protocol_version: Optional[str]
    bus_role: str
    bus_role_custom: Optional[str]
    bus_address: Optional[str]
    bus_address_secondary: Optional[str]
    bus_name_network: Optional[str]
    data_rate: Optional[str]
    data_rate_actual_bps: Optional[int]
    word_size_bits: Optional[int]
    frame_size_max_bytes: Optional[int]
    topology: Optional[str]
    redundancy: Optional[str]
    deterministic: Optional[bool]
    fault_tolerance: Optional[str]
    bus_loading_max_pct: Optional[float]
    latency_budget_ms: Optional[float]
    jitter_max_us: Optional[float]
    error_rate_max: Optional[str]
    encoding: Optional[str]
    electrical_standard: Optional[str]
    coupling: Optional[str]
    stub_length_max_m: Optional[float]
    bus_length_max_m: Optional[float]
    termination_required: Optional[str]
    notes: Optional[str]
    metadata_json: Optional[dict]
    unit_id: int
    project_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    # Computed
    message_count: int = 0
    pin_assignment_count: int = 0
    bus_utilization_pct: Optional[float] = None

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  7. MessageDefinition  (defined before BusWithMessages)
# ══════════════════════════════════════════════════════════════

class MessageFieldCreate(BaseModel):
    field_name: str = Field(..., max_length=100)
    data_type: str = Field(...)
    bit_length: int = Field(...)
    message_id: int
    # Optional
    label: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    data_type_custom: Optional[str] = Field(None, max_length=100)
    byte_order: Optional[str] = "big_endian"
    word_number: Optional[int] = None
    byte_offset: Optional[int] = None
    bit_offset: Optional[int] = None
    unit_of_measure: Optional[str] = Field(None, max_length=50)
    scale_factor: Optional[float] = 1.0
    offset_value: Optional[float] = 0.0
    lsb_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    resolution: Optional[float] = None
    accuracy: Optional[float] = None
    default_value: Optional[str] = Field(None, max_length=50)
    initial_value: Optional[str] = Field(None, max_length=50)
    invalid_value: Optional[str] = Field(None, max_length=50)
    stale_timeout_ms: Optional[float] = None
    enum_values: Optional[dict] = None
    bit_mask: Optional[str] = Field(None, max_length=20)
    field_order: Optional[int] = None
    is_padding: Optional[bool] = False
    is_spare: Optional[bool] = False
    notes: Optional[str] = None


class MessageFieldUpdate(BaseModel):
    field_name: Optional[str] = Field(None, max_length=100)
    data_type: Optional[str] = None
    data_type_custom: Optional[str] = Field(None, max_length=100)
    bit_length: Optional[int] = None
    byte_order: Optional[str] = None
    word_number: Optional[int] = None
    byte_offset: Optional[int] = None
    bit_offset: Optional[int] = None
    label: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    unit_of_measure: Optional[str] = Field(None, max_length=50)
    scale_factor: Optional[float] = None
    offset_value: Optional[float] = None
    lsb_value: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    resolution: Optional[float] = None
    accuracy: Optional[float] = None
    default_value: Optional[str] = Field(None, max_length=50)
    initial_value: Optional[str] = Field(None, max_length=50)
    invalid_value: Optional[str] = Field(None, max_length=50)
    stale_timeout_ms: Optional[float] = None
    enum_values: Optional[dict] = None
    bit_mask: Optional[str] = Field(None, max_length=20)
    field_order: Optional[int] = None
    is_padding: Optional[bool] = None
    is_spare: Optional[bool] = None
    notes: Optional[str] = None


class MessageFieldBatchCreate(BaseModel):
    fields: List[MessageFieldCreate] = Field(..., min_length=1)


class MessageFieldResponse(BaseModel):
    id: int
    field_name: str
    label: Optional[str]
    description: Optional[str]
    data_type: str
    data_type_custom: Optional[str]
    byte_order: Optional[str]
    word_number: Optional[int]
    byte_offset: Optional[int]
    bit_offset: Optional[int]
    bit_length: int
    unit_of_measure: Optional[str]
    scale_factor: Optional[float]
    offset_value: Optional[float]
    lsb_value: Optional[float]
    min_value: Optional[float]
    max_value: Optional[float]
    resolution: Optional[float]
    accuracy: Optional[float]
    default_value: Optional[str]
    initial_value: Optional[str]
    invalid_value: Optional[str]
    stale_timeout_ms: Optional[float]
    enum_values: Optional[dict]
    bit_mask: Optional[str]
    field_order: Optional[int]
    is_padding: Optional[bool]
    is_spare: Optional[bool]
    notes: Optional[str]
    message_id: int
    created_at: datetime

    class Config:
        from_attributes = True


class MessageDefinitionCreate(BaseModel):
    label: str = Field(..., max_length=100)
    direction: str = Field(...)
    bus_def_id: int
    unit_id: int
    # Optional
    mnemonic: Optional[str] = Field(None, max_length=30)
    description: Optional[str] = None
    protocol_message_id: Optional[str] = Field(None, max_length=30)
    message_id_hex: Optional[str] = Field(None, max_length=20)
    subaddress: Optional[int] = None
    word_count: Optional[int] = None
    byte_count: Optional[int] = None
    scheduling: Optional[str] = "periodic_synchronous"
    rate_hz: Optional[float] = None
    rate_min_hz: Optional[float] = None
    rate_max_hz: Optional[float] = None
    latency_max_ms: Optional[float] = None
    latency_typical_ms: Optional[float] = None
    priority: Optional[str] = "medium"
    is_periodic: Optional[bool] = True
    timeout_ms: Optional[float] = None
    integrity_mechanism: Optional[str] = Field(None, max_length=50)
    fragmentation: Optional[bool] = False
    encryption: Optional[str] = Field(None, max_length=50)
    authentication: Optional[str] = Field(None, max_length=50)
    source_system_name: Optional[str] = Field(None, max_length=100)
    target_system_name: Optional[str] = Field(None, max_length=100)
    icd_reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None
    # Batch create fields with message
    fields: Optional[List[MessageFieldCreate]] = None


class MessageDefinitionUpdate(BaseModel):
    label: Optional[str] = Field(None, max_length=100)
    direction: Optional[str] = None
    mnemonic: Optional[str] = Field(None, max_length=30)
    description: Optional[str] = None
    protocol_message_id: Optional[str] = Field(None, max_length=30)
    message_id_hex: Optional[str] = Field(None, max_length=20)
    subaddress: Optional[int] = None
    word_count: Optional[int] = None
    byte_count: Optional[int] = None
    scheduling: Optional[str] = None
    rate_hz: Optional[float] = None
    rate_min_hz: Optional[float] = None
    rate_max_hz: Optional[float] = None
    latency_max_ms: Optional[float] = None
    latency_typical_ms: Optional[float] = None
    priority: Optional[str] = None
    is_periodic: Optional[bool] = None
    timeout_ms: Optional[float] = None
    integrity_mechanism: Optional[str] = Field(None, max_length=50)
    fragmentation: Optional[bool] = None
    encryption: Optional[str] = Field(None, max_length=50)
    authentication: Optional[str] = Field(None, max_length=50)
    source_system_name: Optional[str] = Field(None, max_length=100)
    target_system_name: Optional[str] = Field(None, max_length=100)
    icd_reference: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None


class MessageSummary(BaseModel):
    id: int
    msg_def_id: Optional[str]
    label: str
    mnemonic: Optional[str]
    direction: str
    rate_hz: Optional[float]
    word_count: Optional[int]
    field_count: int = 0

    class Config:
        from_attributes = True


class MessageDefinitionResponse(BaseModel):
    id: int
    msg_def_id: Optional[str]
    label: str
    mnemonic: Optional[str]
    description: Optional[str]
    protocol_message_id: Optional[str]
    message_id_hex: Optional[str]
    subaddress: Optional[int]
    word_count: Optional[int]
    byte_count: Optional[int]
    direction: str
    scheduling: Optional[str]
    rate_hz: Optional[float]
    rate_min_hz: Optional[float]
    rate_max_hz: Optional[float]
    latency_max_ms: Optional[float]
    latency_typical_ms: Optional[float]
    priority: Optional[str]
    is_periodic: Optional[bool]
    timeout_ms: Optional[float]
    integrity_mechanism: Optional[str]
    fragmentation: Optional[bool]
    encryption: Optional[str]
    authentication: Optional[str]
    source_system_name: Optional[str]
    target_system_name: Optional[str]
    icd_reference: Optional[str]
    notes: Optional[str]
    metadata_json: Optional[dict]
    bus_def_id: int
    unit_id: int
    project_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    # Computed
    field_count: int = 0
    total_bits: int = 0

    class Config:
        from_attributes = True


class MessageWithFields(MessageDefinitionResponse):
    fields: List[MessageFieldResponse] = []


# ── BusWithMessages (needs MessageSummary + PinBusAssignmentResponse) ──

class BusWithMessages(BusDefinitionResponse):
    messages: List[MessageSummary] = []
    pin_assignments: List[PinBusAssignmentResponse] = []


# ══════════════════════════════════════════════════════════════
#  12. UnitEnvironmentalSpec  (needed by UnitDetail)
# ══════════════════════════════════════════════════════════════

class EnvironmentalSpecCreate(BaseModel):
    unit_id: int
    category: str = Field(...)
    # Optional
    standard: Optional[str] = None
    standard_custom: Optional[str] = Field(None, max_length=100)
    test_method: Optional[str] = Field(None, max_length=100)
    test_level: Optional[str] = Field(None, max_length=100)
    limit_value: Optional[float] = None
    limit_unit: Optional[str] = Field(None, max_length=30)
    limit_min: Optional[float] = None
    limit_max: Optional[float] = None
    frequency_range: Optional[str] = Field(None, max_length=50)
    duration: Optional[str] = Field(None, max_length=50)
    test_condition: Optional[str] = None
    compliance_status: Optional[str] = "untested"
    test_report_ref: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    auto_generated: Optional[bool] = False


class EnvironmentalSpecUpdate(BaseModel):
    category: Optional[str] = None
    standard: Optional[str] = None
    standard_custom: Optional[str] = Field(None, max_length=100)
    test_method: Optional[str] = Field(None, max_length=100)
    test_level: Optional[str] = Field(None, max_length=100)
    limit_value: Optional[float] = None
    limit_unit: Optional[str] = Field(None, max_length=30)
    limit_min: Optional[float] = None
    limit_max: Optional[float] = None
    frequency_range: Optional[str] = Field(None, max_length=50)
    duration: Optional[str] = Field(None, max_length=50)
    test_condition: Optional[str] = None
    compliance_status: Optional[str] = None
    test_report_ref: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None


class EnvironmentalSpecResponse(BaseModel):
    id: int
    unit_id: int
    category: str
    standard: Optional[str]
    standard_custom: Optional[str]
    test_method: Optional[str]
    test_level: Optional[str]
    limit_value: Optional[float]
    limit_unit: Optional[str]
    limit_min: Optional[float]
    limit_max: Optional[float]
    frequency_range: Optional[str]
    duration: Optional[str]
    test_condition: Optional[str]
    compliance_status: Optional[str]
    test_report_ref: Optional[str]
    notes: Optional[str]
    auto_generated: Optional[bool]
    created_at: datetime

    class Config:
        from_attributes = True


# ── Now define UnitDetail (needs ConnectorWithPins, BusWithMessages, EnvironmentalSpecResponse) ──

class UnitDetail(UnitResponse):
    connectors: List[ConnectorWithPins] = []
    bus_definitions: List[BusWithMessages] = []
    environmental_specs: List[EnvironmentalSpecResponse] = []


# ── Now define SystemDetail (needs UnitSummary) ──

class SystemDetail(SystemResponse):
    units: List[UnitSummary] = []


# ══════════════════════════════════════════════════════════════
#  9. WireHarness
# ══════════════════════════════════════════════════════════════

class WireCreate(BaseModel):
    wire_number: str = Field(..., max_length=20)
    signal_name: str = Field(..., max_length=150)
    wire_type: str = Field(...)
    from_pin_id: int
    to_pin_id: int
    # Optional
    wire_gauge: Optional[str] = None
    wire_gauge_custom: Optional[str] = Field(None, max_length=10)
    wire_color_primary: Optional[str] = Field(None, max_length=30)
    wire_color_secondary: Optional[str] = Field(None, max_length=30)
    wire_color_tertiary: Optional[str] = Field(None, max_length=30)
    wire_type_custom: Optional[str] = Field(None, max_length=100)
    wire_spec: Optional[str] = Field(None, max_length=80)
    wire_material: Optional[str] = Field(None, max_length=50)
    insulation_material: Optional[str] = Field(None, max_length=50)
    insulation_color: Optional[str] = Field(None, max_length=30)
    length_m: Optional[float] = None
    length_max_m: Optional[float] = None
    splice_info: Optional[str] = Field(None, max_length=100)
    termination_from: Optional[str] = Field(None, max_length=50)
    termination_to: Optional[str] = Field(None, max_length=50)
    heat_shrink: Optional[bool] = False
    heat_shrink_size: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None


class WireUpdate(BaseModel):
    wire_number: Optional[str] = Field(None, max_length=20)
    signal_name: Optional[str] = Field(None, max_length=150)
    wire_type: Optional[str] = None
    wire_type_custom: Optional[str] = Field(None, max_length=100)
    wire_gauge: Optional[str] = None
    wire_gauge_custom: Optional[str] = Field(None, max_length=10)
    wire_color_primary: Optional[str] = Field(None, max_length=30)
    wire_color_secondary: Optional[str] = Field(None, max_length=30)
    wire_color_tertiary: Optional[str] = Field(None, max_length=30)
    wire_spec: Optional[str] = Field(None, max_length=80)
    wire_material: Optional[str] = Field(None, max_length=50)
    insulation_material: Optional[str] = Field(None, max_length=50)
    insulation_color: Optional[str] = Field(None, max_length=30)
    length_m: Optional[float] = None
    length_max_m: Optional[float] = None
    from_pin_id: Optional[int] = None
    to_pin_id: Optional[int] = None
    splice_info: Optional[str] = Field(None, max_length=100)
    termination_from: Optional[str] = Field(None, max_length=50)
    termination_to: Optional[str] = Field(None, max_length=50)
    heat_shrink: Optional[bool] = None
    heat_shrink_size: Optional[str] = Field(None, max_length=20)
    notes: Optional[str] = None


class WireBatchCreate(BaseModel):
    wires: List[WireCreate] = Field(..., min_length=1)


class WireResponse(BaseModel):
    id: int
    wire_number: str
    signal_name: str
    wire_gauge: Optional[str]
    wire_gauge_custom: Optional[str]
    wire_color_primary: Optional[str]
    wire_color_secondary: Optional[str]
    wire_color_tertiary: Optional[str]
    wire_type: str
    wire_type_custom: Optional[str]
    wire_spec: Optional[str]
    wire_material: Optional[str]
    insulation_material: Optional[str]
    insulation_color: Optional[str]
    length_m: Optional[float]
    length_max_m: Optional[float]
    from_pin_id: int
    to_pin_id: int
    harness_id: int
    splice_info: Optional[str]
    termination_from: Optional[str]
    termination_to: Optional[str]
    heat_shrink: Optional[bool]
    heat_shrink_size: Optional[str]
    notes: Optional[str]
    created_at: datetime
    # Computed joins
    from_pin_number: Optional[str] = None
    from_signal_name: Optional[str] = None
    from_connector_designator: Optional[str] = None
    from_unit_designation: Optional[str] = None
    to_pin_number: Optional[str] = None
    to_signal_name: Optional[str] = None
    to_connector_designator: Optional[str] = None
    to_unit_designation: Optional[str] = None

    class Config:
        from_attributes = True


class WireHarnessCreate(BaseModel):
    name: str = Field(..., max_length=255)
    from_unit_id: int
    from_connector_id: int
    to_unit_id: int
    to_connector_id: int
    # Optional
    description: Optional[str] = None
    cable_type: Optional[str] = Field(None, max_length=100)
    cable_spec: Optional[str] = Field(None, max_length=100)
    cable_part_number: Optional[str] = Field(None, max_length=100)
    cable_manufacturer: Optional[str] = Field(None, max_length=255)
    overall_length_m: Optional[float] = None
    overall_length_max_m: Optional[float] = None
    mass_kg: Optional[float] = None
    outer_diameter_mm: Optional[float] = None
    jacket_material: Optional[str] = None
    jacket_material_custom: Optional[str] = Field(None, max_length=100)
    jacket_color: Optional[str] = Field(None, max_length=30)
    temp_rating_min_c: Optional[float] = None
    temp_rating_max_c: Optional[float] = None
    voltage_rating_v: Optional[float] = None
    bend_radius_min_mm: Optional[float] = None
    shield_type: Optional[str] = None
    shield_coverage_pct: Optional[float] = None
    shield_material: Optional[str] = Field(None, max_length=50)
    overall_shield_termination: Optional[str] = Field(None, max_length=100)
    conductor_count: Optional[int] = None
    pair_count: Optional[int] = None
    status: Optional[str] = "concept"
    drawing_number: Optional[str] = Field(None, max_length=50)
    drawing_revision: Optional[str] = Field(None, max_length=10)
    approved_by: Optional[str] = Field(None, max_length=100)
    approval_date: Optional[datetime] = None


class WireHarnessUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    description: Optional[str] = None
    cable_type: Optional[str] = Field(None, max_length=100)
    cable_spec: Optional[str] = Field(None, max_length=100)
    cable_part_number: Optional[str] = Field(None, max_length=100)
    cable_manufacturer: Optional[str] = Field(None, max_length=255)
    overall_length_m: Optional[float] = None
    overall_length_max_m: Optional[float] = None
    mass_kg: Optional[float] = None
    outer_diameter_mm: Optional[float] = None
    jacket_material: Optional[str] = None
    jacket_material_custom: Optional[str] = Field(None, max_length=100)
    jacket_color: Optional[str] = Field(None, max_length=30)
    temp_rating_min_c: Optional[float] = None
    temp_rating_max_c: Optional[float] = None
    voltage_rating_v: Optional[float] = None
    bend_radius_min_mm: Optional[float] = None
    shield_type: Optional[str] = None
    shield_coverage_pct: Optional[float] = None
    shield_material: Optional[str] = Field(None, max_length=50)
    overall_shield_termination: Optional[str] = Field(None, max_length=100)
    conductor_count: Optional[int] = None
    pair_count: Optional[int] = None
    status: Optional[str] = None
    drawing_number: Optional[str] = Field(None, max_length=50)
    drawing_revision: Optional[str] = Field(None, max_length=10)
    approved_by: Optional[str] = Field(None, max_length=100)
    approval_date: Optional[datetime] = None


class WireHarnessResponse(BaseModel):
    id: int
    harness_id: Optional[str]
    name: str
    description: Optional[str]
    cable_type: Optional[str]
    cable_spec: Optional[str]
    cable_part_number: Optional[str]
    cable_manufacturer: Optional[str]
    overall_length_m: Optional[float]
    overall_length_max_m: Optional[float]
    mass_kg: Optional[float]
    outer_diameter_mm: Optional[float]
    jacket_material: Optional[str]
    jacket_material_custom: Optional[str]
    jacket_color: Optional[str]
    temp_rating_min_c: Optional[float]
    temp_rating_max_c: Optional[float]
    voltage_rating_v: Optional[float]
    bend_radius_min_mm: Optional[float]
    shield_type: Optional[str]
    shield_coverage_pct: Optional[float]
    shield_material: Optional[str]
    overall_shield_termination: Optional[str]
    conductor_count: Optional[int]
    pair_count: Optional[int]
    status: Optional[str]
    drawing_number: Optional[str]
    drawing_revision: Optional[str]
    approved_by: Optional[str]
    approval_date: Optional[datetime]
    from_unit_id: int
    from_connector_id: int
    to_unit_id: int
    to_connector_id: int
    project_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    # Computed joins
    wire_count: int = 0
    from_unit_designation: Optional[str] = None
    from_connector_designator: Optional[str] = None
    to_unit_designation: Optional[str] = None
    to_connector_designator: Optional[str] = None

    class Config:
        from_attributes = True


class WireHarnessDetail(WireHarnessResponse):
    wires: List[WireResponse] = []


# ══════════════════════════════════════════════════════════════
#  11. Interface
# ══════════════════════════════════════════════════════════════

class InterfaceCreate(BaseModel):
    name: str = Field(..., max_length=255)
    interface_type: str = Field(...)
    direction: str = Field(...)
    source_system_id: int
    target_system_id: int
    # Optional
    interface_type_custom: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    status: Optional[str] = "proposed"
    criticality: Optional[str] = "non_critical"
    icd_document_number: Optional[str] = Field(None, max_length=100)
    icd_document_revision: Optional[str] = Field(None, max_length=20)
    icd_section: Optional[str] = Field(None, max_length=50)
    version: Optional[int] = 1
    data_rate_aggregate: Optional[str] = Field(None, max_length=30)
    latency_requirement_ms: Optional[float] = None
    availability_requirement_pct: Optional[float] = None
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None


class InterfaceUpdate(BaseModel):
    name: Optional[str] = Field(None, max_length=255)
    interface_type: Optional[str] = None
    interface_type_custom: Optional[str] = Field(None, max_length=100)
    direction: Optional[str] = None
    source_system_id: Optional[int] = None
    target_system_id: Optional[int] = None
    description: Optional[str] = None
    status: Optional[str] = None
    criticality: Optional[str] = None
    icd_document_number: Optional[str] = Field(None, max_length=100)
    icd_document_revision: Optional[str] = Field(None, max_length=20)
    icd_section: Optional[str] = Field(None, max_length=50)
    version: Optional[int] = None
    data_rate_aggregate: Optional[str] = Field(None, max_length=30)
    latency_requirement_ms: Optional[float] = None
    availability_requirement_pct: Optional[float] = None
    notes: Optional[str] = None
    metadata_json: Optional[dict] = None


class InterfaceResponse(BaseModel):
    id: int
    interface_id: Optional[str]
    name: str
    description: Optional[str]
    interface_type: str
    interface_type_custom: Optional[str]
    direction: str
    source_system_id: int
    target_system_id: int
    status: str
    criticality: str
    icd_document_number: Optional[str]
    icd_document_revision: Optional[str]
    icd_section: Optional[str]
    version: int
    data_rate_aggregate: Optional[str]
    latency_requirement_ms: Optional[float]
    availability_requirement_pct: Optional[float]
    notes: Optional[str]
    metadata_json: Optional[dict]
    project_id: Optional[int]
    owner_id: Optional[int]
    created_at: datetime
    updated_at: datetime
    # Computed joins
    source_system_name: Optional[str] = None
    target_system_name: Optional[str] = None
    harness_count: int = 0
    bus_count: int = 0
    message_count: int = 0

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  13. InterfaceRequirementLink
# ══════════════════════════════════════════════════════════════

class InterfaceReqLinkCreate(BaseModel):
    entity_type: str = Field(...)
    entity_id: int
    requirement_id: int
    link_type: str = Field(...)
    link_type_custom: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    auto_generated: Optional[bool] = False
    auto_req_source: Optional[str] = None
    auto_req_template: Optional[str] = Field(None, max_length=50)
    confidence_score: Optional[float] = None
    status: Optional[str] = "pending_review"


class InterfaceReqLinkUpdate(BaseModel):
    link_type: Optional[str] = None
    link_type_custom: Optional[str] = Field(None, max_length=100)
    description: Optional[str] = None
    status: Optional[str] = None


class InterfaceReqLinkResponse(BaseModel):
    id: int
    entity_type: str
    entity_id: int
    requirement_id: int
    link_type: str
    link_type_custom: Optional[str]
    description: Optional[str]
    auto_generated: bool
    auto_req_source: Optional[str]
    auto_req_template: Optional[str]
    confidence_score: Optional[float]
    status: str
    reviewed_by_id: Optional[int]
    reviewed_at: Optional[datetime]
    created_by_id: Optional[int]
    created_at: datetime
    # Computed joins
    requirement_req_id: Optional[str] = None
    requirement_title: Optional[str] = None

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  14. AutoRequirementLog
# ══════════════════════════════════════════════════════════════

class AutoReqLogResponse(BaseModel):
    id: int
    project_id: int
    trigger_entity_type: Optional[str]
    trigger_entity_id: Optional[int]
    trigger_action: Optional[str]
    requirements_generated: Optional[int]
    verifications_generated: Optional[int]
    links_generated: Optional[int]
    template_used: Optional[str]
    generation_summary: Optional[dict]
    user_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  15. InterfaceChangeImpact
# ══════════════════════════════════════════════════════════════

class InterfaceChangeImpactResponse(BaseModel):
    id: int
    project_id: int
    change_type: Optional[str]
    entity_type: Optional[str]
    entity_id: Optional[int]
    entity_description: Optional[str]
    affected_requirements: Optional[dict]
    affected_verifications: Optional[dict]
    risk_level: Optional[str]
    total_affected: Optional[int]
    user_action: Optional[str]
    resolved: bool
    resolved_at: Optional[datetime]
    user_id: Optional[int]
    created_at: datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  Aggregate / View Schemas
# ══════════════════════════════════════════════════════════════

# ── N×N Interface Matrix ──

class N2MatrixCell(BaseModel):
    source_system_id: int
    source_system_name: str
    target_system_id: int
    target_system_name: str
    interface_count: int = 0
    harness_count: int = 0
    bus_protocols: List[str] = []
    signal_count: int = 0
    criticality_max: Optional[str] = None


class N2MatrixResponse(BaseModel):
    systems: List[SystemResponse] = []
    matrix: List[List[Optional[N2MatrixCell]]] = []


# ── Block Diagram ──

class BlockDiagramNode(BaseModel):
    id: int
    system_id: str
    name: str
    abbreviation: Optional[str] = None
    type: str
    unit_count: int = 0
    x: Optional[float] = None
    y: Optional[float] = None


class BlockDiagramEdge(BaseModel):
    source_id: int
    target_id: int
    interface_id: int
    name: str
    type: str
    criticality: Optional[str] = None
    direction: str
    harness_count: int = 0


class BlockDiagramResponse(BaseModel):
    nodes: List[BlockDiagramNode] = []
    edges: List[BlockDiagramEdge] = []


# ── Signal Trace ──

class SignalTraceHop(BaseModel):
    unit: Optional[str] = None
    connector: Optional[str] = None
    pin: Optional[str] = None
    wire: Optional[str] = None
    harness: Optional[str] = None
    bus: Optional[str] = None
    message: Optional[str] = None


class SignalTraceResult(BaseModel):
    signal_name: str
    path: List[SignalTraceHop] = []


# ── Interface Coverage ──

class InterfaceCoverageResponse(BaseModel):
    total_interfaces: int = 0
    with_requirements: int = 0
    without_requirements: int = 0
    coverage_pct: float = 0.0
    units_with_specs: int = 0
    units_without_specs: int = 0
    auto_generated_count: int = 0
    approved_count: int = 0
    pending_count: int = 0


# ── Auto-Requirement Generation ──

class GeneratedRequirementSummary(BaseModel):
    id: int
    req_id: str
    title: str
    level: str
    statement: str


class AutoReqGenerationResult(BaseModel):
    requirements_generated: int = 0
    verifications_generated: int = 0
    links_generated: int = 0
    requirements: List[GeneratedRequirementSummary] = []


# ── Impact Preview ──

class ImpactPreview(BaseModel):
    affected_requirements: List[Dict[str, Any]] = []
    risk_level: str = "low"
    total_affected: int = 0
    action_options: List[str] = []


# ── Wiring Diagram ──

class WiringDiagramData(BaseModel):
    from_connector: ConnectorWithPins
    to_connector: ConnectorWithPins
    wires: List[WireResponse] = []
    unconnected_from: List[PinResponse] = []
    unconnected_to: List[PinResponse] = []
