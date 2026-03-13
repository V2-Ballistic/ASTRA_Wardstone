// ══════════════════════════════════════════════════════════════
//  ASTRA — Interface Module TypeScript Types
//  Mirrors backend Pydantic schemas in schemas/interface.py
//
//  File: frontend/src/lib/interface-types.ts
//  Path: C:\Users\Mason\Documents\ASTRA\frontend\src\lib\interface-types.ts
// ══════════════════════════════════════════════════════════════

// ── Enum Union Types ──

export type SystemType =
  | 'subsystem' | 'lru' | 'wru' | 'sru' | 'sensor_suite' | 'actuator_assembly'
  | 'processor_unit' | 'power_system' | 'thermal_system' | 'structural'
  | 'ground_segment' | 'vehicle' | 'payload' | 'antenna_system' | 'propulsion'
  | 'guidance_nav_control' | 'communication' | 'data_handling' | 'ordnance'
  | 'test_equipment' | 'external_system' | 'software' | 'firmware' | 'custom';

export type SystemStatus =
  | 'concept' | 'preliminary_design' | 'detailed_design' | 'fabrication'
  | 'integration' | 'qualification_test' | 'acceptance_test' | 'operational'
  | 'maintenance' | 'retired' | 'obsolete';

export type UnitType =
  | 'lru' | 'wru' | 'sru' | 'cca' | 'pcb' | 'backplane' | 'chassis'
  | 'sensor' | 'actuator' | 'motor' | 'processor' | 'fpga' | 'asic'
  | 'power_supply' | 'power_converter' | 'battery' | 'solar_panel'
  | 'transmitter' | 'receiver' | 'transceiver' | 'antenna' | 'waveguide'
  | 'filter_rf' | 'amplifier' | 'oscillator' | 'switch_rf' | 'diplexer'
  | 'coupler' | 'cable_assembly' | 'connector_assembly' | 'relay_box'
  | 'junction_box' | 'terminal_block' | 'fuse_box' | 'transformer'
  | 'regulator' | 'gyroscope' | 'accelerometer' | 'star_tracker'
  | 'sun_sensor' | 'earth_sensor' | 'gps_receiver'
  | 'inertial_measurement_unit' | 'reaction_wheel' | 'thruster' | 'valve'
  | 'pyrotechnic' | 'cots_equipment' | 'gse' | 'firmware_module'
  | 'software_module' | 'custom';

export type UnitStatus =
  | 'concept' | 'preliminary_design' | 'detailed_design' | 'prototype'
  | 'engineering_model' | 'qualification_unit' | 'flight_unit' | 'flight_spare'
  | 'production' | 'installed' | 'qualified' | 'accepted' | 'operational'
  | 'failed' | 'obsolete';

export type ConnectorType =
  | 'mil_dtl_38999_series_iii' | 'mil_dtl_38999_series_i' | 'mil_dtl_38999_series_ii'
  | 'mil_dtl_38999_series_iv' | 'mil_dtl_26482_series_i' | 'mil_dtl_26482_series_ii'
  | 'mil_dtl_5015' | 'd_sub_9' | 'd_sub_15' | 'd_sub_25' | 'd_sub_37'
  | 'micro_d_9' | 'micro_d_15' | 'micro_d_25' | 'rj45' | 'rj45_shielded'
  | 'usb_c' | 'sma' | 'bnc' | 'tnc' | 'n_type' | 'fiber_lc' | 'fiber_sc'
  | 'm12_4pin' | 'm12_8pin' | 'backplane_vpx' | 'custom' | string;

export type ConnectorGender = 'male_pin' | 'female_socket' | 'hermaphroditic' | 'genderless';

export type SignalType =
  | 'power_primary' | 'power_secondary' | 'power_return'
  | 'chassis_ground' | 'signal_ground'
  | 'signal_digital_single' | 'signal_digital_differential'
  | 'signal_analog_single' | 'signal_analog_differential'
  | 'clock_single' | 'clock_differential' | 'clock_reference'
  | 'rf_signal' | 'rf_lo' | 'rf_if'
  | 'discrete_input' | 'discrete_output' | 'discrete_bidirectional'
  | 'serial_data' | 'parallel_data' | 'pwm' | 'pulse'
  | 'thermocouple' | 'rtd' | 'strain_gauge' | 'lvdt'
  | 'fiber_optic_single' | 'fiber_optic_multi' | 'coax_signal'
  | 'spare' | 'no_connect' | 'shield_overall' | 'shield_individual'
  | 'shield_drain' | 'test_point' | 'key_pin' | 'alignment_pin'
  | 'reserved' | 'custom';

export type PinDirection =
  | 'input' | 'output' | 'bidirectional' | 'tri_state'
  | 'power_source' | 'power_sink' | 'power_return'
  | 'ground' | 'chassis_ground' | 'no_connect' | 'spare' | 'custom';

export type BusProtocol =
  | 'mil_std_1553b' | 'mil_std_1553a' | 'mil_std_1773'
  | 'spacewire' | 'spacewire_rmap'
  | 'can_2b' | 'canfd' | 'canopen' | 'rs232' | 'rs422' | 'rs485'
  | 'spi_mode0' | 'i2c_standard' | 'i2c_fast'
  | 'ethernet_100base_tx' | 'ethernet_1000base_t' | 'ethernet_10gbase_t'
  | 'arinc_429' | 'arinc_664_part7' | 'usb_2_0' | 'usb_3_0'
  | 'jtag' | 'swd' | 'ccsds_tm' | 'ccsds_tc'
  | 'analog_4_20ma' | 'discrete_28v' | 'discrete_5v' | 'custom' | string;

export type BusRole =
  | 'bus_controller' | 'remote_terminal' | 'bus_monitor'
  | 'master' | 'slave' | 'multi_master'
  | 'publisher' | 'subscriber' | 'peer' | 'custom';

export type MessageDirection =
  | 'transmit' | 'receive' | 'transmit_receive' | 'broadcast'
  | 'request' | 'response' | 'status';

export type MessagePriority =
  | 'safety_critical' | 'mission_critical' | 'high' | 'medium' | 'low'
  | 'background' | 'diagnostic';

export type FieldDataType =
  | 'boolean' | 'uint8' | 'int8' | 'uint16' | 'int16' | 'uint32' | 'int32'
  | 'uint64' | 'int64' | 'float16' | 'float32' | 'float64'
  | 'enum_coded' | 'bitfield' | 'bitmask' | 'char_ascii' | 'string_fixed'
  | 'timestamp_utc' | 'raw_bytes' | 'reserved' | 'spare' | 'custom';

export type WireType =
  | 'signal_single' | 'signal_twisted_pair_a' | 'signal_twisted_pair_b'
  | 'signal_shielded_single' | 'signal_shielded_pair'
  | 'power_positive' | 'power_negative' | 'power_return'
  | 'ground_signal' | 'ground_chassis' | 'ground_power'
  | 'shield_overall_drain' | 'shield_individual_drain' | 'shield_braid'
  | 'coax_center' | 'coax_shield' | 'fiber_tx' | 'fiber_rx'
  | 'spare' | 'jumper' | 'test' | 'custom';

export type InterfaceType =
  | 'electrical_power' | 'electrical_signal' | 'electrical_combined'
  | 'data_digital' | 'data_analog' | 'data_mixed'
  | 'rf_transmit' | 'rf_receive' | 'rf_duplex'
  | 'optical_fiber' | 'optical_free_space'
  | 'mechanical_structural' | 'mechanical_thermal'
  | 'fluid_pneumatic' | 'fluid_hydraulic' | 'fluid_coolant'
  | 'thermal_conductive' | 'thermal_radiative'
  | 'electromagnetic' | 'acoustic' | 'custom';

export type InterfaceDirection = 'source_to_target' | 'target_to_source' | 'bidirectional' | 'broadcast';

export type InterfaceCriticality =
  | 'catastrophic' | 'hazardous' | 'major' | 'minor' | 'no_effect'
  | 'safety_critical_a' | 'safety_critical_b' | 'safety_critical_c'
  | 'mission_critical' | 'mission_essential' | 'mission_support' | 'non_critical';

export type InterfaceStatus =
  | 'proposed' | 'defined' | 'preliminary' | 'under_review' | 'agreed'
  | 'baselined' | 'implemented' | 'integration_tested' | 'verified'
  | 'validated' | 'waived' | 'custom';

export type HarnessStatus =
  | 'concept' | 'preliminary_design' | 'detailed_design' | 'drawing_released'
  | 'fabrication' | 'inspection' | 'acceptance_test' | 'installed'
  | 'rework' | 'field_modification' | 'retired';

export type InterfaceEntityType =
  | 'system' | 'unit' | 'connector' | 'pin' | 'pin_bus_assignment'
  | 'bus_definition' | 'message_definition' | 'message_field'
  | 'wire_harness' | 'wire' | 'cable_assembly' | 'interface' | 'interface_document';

export type InterfaceLinkType =
  | 'satisfies' | 'partially_satisfies' | 'verifies' | 'validates'
  | 'derives_from' | 'decomposes' | 'refines' | 'elaborates'
  | 'constrains' | 'enables' | 'conflicts_with'
  | 'implements' | 'allocated_to' | 'realized_by'
  | 'tested_by' | 'analyzed_by' | 'inspected_by' | 'demonstrated_by'
  | 'traces_to' | 'references' | 'custom';


// ══════════════════════════════════════
//  Model Interfaces
// ══════════════════════════════════════

// ── 1. System ──

export interface System {
  id: number;
  system_id: string;
  name: string;
  abbreviation?: string;
  description?: string;
  system_type: SystemType;
  system_type_custom?: string;
  status: SystemStatus;
  parent_system_id?: number;
  wbs_number?: string;
  responsible_org?: string;
  project_id: number;
  owner_id: number;
  created_at: string;
  updated_at: string;
  unit_count: number;
  interface_count: number;
}

export interface SystemDetail extends System {
  units: UnitSummary[];
}

// ── 2. Unit ──

export interface UnitSummary {
  id: number;
  unit_id: string;
  name: string;
  designation: string;
  part_number: string;
  manufacturer: string;
  unit_type: UnitType;
  status: UnitStatus;
  connector_count: number;
  bus_count: number;
}

export interface Unit extends UnitSummary {
  description?: string;
  unit_type_custom?: string;
  cage_code?: string;
  nsn?: string;
  drawing_number?: string;
  revision?: string;
  serial_number_prefix?: string;
  heritage?: string;
  // Physical
  mass_kg?: number;
  mass_max_kg?: number;
  dimensions_l_mm?: number;
  dimensions_w_mm?: number;
  dimensions_h_mm?: number;
  volume_cc?: number;
  // Electrical
  power_watts_nominal?: number;
  power_watts_peak?: number;
  power_watts_standby?: number;
  voltage_input_nominal?: string;
  voltage_input_min?: number;
  voltage_input_max?: number;
  voltage_ripple_max_mvpp?: number;
  current_inrush_amps?: number;
  current_steady_state_amps?: number;
  // Thermal
  temp_operating_min_c?: number;
  temp_operating_max_c?: number;
  temp_storage_min_c?: number;
  temp_storage_max_c?: number;
  temp_survival_min_c?: number;
  temp_survival_max_c?: number;
  // Mechanical
  vibration_random_grms?: number;
  vibration_sine_g_peak?: number;
  shock_mechanical_g?: number;
  shock_mechanical_duration_ms?: number;
  shock_pyrotechnic_g?: number;
  acceleration_max_g?: number;
  acoustic_spl_db?: number;
  // Climate
  humidity_min_pct?: number;
  humidity_max_pct?: number;
  altitude_operating_max_m?: number;
  altitude_storage_max_m?: number;
  pressure_min_kpa?: number;
  pressure_max_kpa?: number;
  sand_dust_exposed?: boolean;
  salt_fog_exposed?: boolean;
  fungus_resistant?: boolean;
  // EMI/EMC
  emi_ce101_limit_dba?: number;
  emi_ce102_limit_dbua?: number;
  emi_cs101_limit_db?: number;
  emi_cs114_limit_dba?: number;
  emi_cs115_limit_v?: number;
  emi_cs116_limit_db?: number;
  emi_re101_limit_dba?: number;
  emi_re102_limit_dbm?: number;
  emi_rs101_limit_db?: number;
  emi_rs103_limit_vm?: number;
  esd_hbm_v?: number;
  esd_cdm_v?: number;
  // Radiation
  radiation_tid_krad?: number;
  radiation_see_let_threshold?: number;
  radiation_dd_mev_cm2_g?: number;
  // Reliability
  mtbf_hours?: number;
  mtbf_environment?: string;
  design_life_years?: number;
  duty_cycle_pct?: number;
  derating_standard?: string;
  // References
  datasheet_url?: string;
  specification_doc?: string;
  test_report_doc?: string;
  notes?: string;
  metadata_json?: Record<string, any>;
  // FKs
  system_id: number;
  project_id: number;
  created_at: string;
  updated_at: string;
  // Computed
  message_count: number;
}

export interface UnitDetail extends Unit {
  connectors: ConnectorWithPins[];
  bus_definitions: BusWithMessages[];
  environmental_specs: UnitEnvironmentalSpec[];
}

// ── 3. Connector ──

export interface Connector {
  id: number;
  connector_id?: string;
  designator: string;
  name?: string;
  description?: string;
  connector_type: ConnectorType;
  connector_type_custom?: string;
  gender: ConnectorGender;
  mounting?: string;
  mounting_custom?: string;
  shell_size?: string;
  insert_arrangement?: string;
  total_contacts: number;
  signal_contacts?: number;
  power_contacts?: number;
  coax_contacts?: number;
  fiber_contacts?: number;
  spare_contacts?: number;
  keying?: string;
  polarization?: string;
  coupling?: string;
  ip_rating?: string;
  operating_temp_min_c?: number;
  operating_temp_max_c?: number;
  mating_cycles?: number;
  shell_material?: string;
  shell_finish?: string;
  contact_finish?: string;
  mil_spec?: string;
  manufacturer_part_number?: string;
  connector_manufacturer?: string;
  backshell_type?: string;
  notes?: string;
  unit_id: number;
  project_id?: number;
  created_at: string;
  pin_count: number;
  assigned_pin_count: number;
}

export interface ConnectorWithPins extends Connector {
  pins: Pin[];
}

// ── 4. Pin ──

export interface PinBusAssignment {
  id: number;
  pin_id: number;
  bus_def_id: number;
  pin_role: string;
  pin_role_custom?: string;
  notes?: string;
  created_at: string;
  pin_number?: string;
  signal_name?: string;
  connector_designator?: string;
}

export interface Pin {
  id: number;
  pin_number: string;
  pin_label?: string;
  signal_name: string;
  signal_type: SignalType;
  signal_type_custom?: string;
  direction: PinDirection;
  pin_size?: string;
  contact_type?: string;
  voltage_nominal?: string;
  voltage_min?: number;
  voltage_max?: number;
  voltage_dc_bias?: number;
  current_nominal_amps?: number;
  current_max_amps?: number;
  impedance_ohms?: number;
  frequency_mhz?: number;
  rise_time_ns?: number;
  termination?: string;
  pull_up_down?: string;
  esd_protection?: string;
  description?: string;
  notes?: string;
  connector_id: number;
  created_at: string;
  bus_assignment?: PinBusAssignment;
}

// ── 5. BusDefinition ──

export interface BusDefinition {
  id: number;
  bus_def_id?: string;
  name: string;
  description?: string;
  protocol: BusProtocol;
  protocol_custom?: string;
  protocol_version?: string;
  bus_role: BusRole;
  bus_role_custom?: string;
  bus_address?: string;
  bus_address_secondary?: string;
  bus_name_network?: string;
  data_rate?: string;
  data_rate_actual_bps?: number;
  word_size_bits?: number;
  frame_size_max_bytes?: number;
  topology?: string;
  redundancy?: string;
  deterministic?: boolean;
  fault_tolerance?: string;
  bus_loading_max_pct?: number;
  latency_budget_ms?: number;
  jitter_max_us?: number;
  error_rate_max?: string;
  encoding?: string;
  electrical_standard?: string;
  coupling?: string;
  stub_length_max_m?: number;
  bus_length_max_m?: number;
  termination_required?: string;
  notes?: string;
  metadata_json?: Record<string, any>;
  unit_id: number;
  project_id?: number;
  created_at: string;
  updated_at: string;
  message_count: number;
  pin_assignment_count: number;
  bus_utilization_pct?: number;
}

export interface BusWithMessages extends BusDefinition {
  messages: MessageSummary[];
  pin_assignments: PinBusAssignment[];
}

// ── 6. MessageDefinition ──

export interface MessageSummary {
  id: number;
  msg_def_id?: string;
  label: string;
  mnemonic?: string;
  direction: MessageDirection;
  rate_hz?: number;
  word_count?: number;
  field_count: number;
}

export interface MessageDefinition extends MessageSummary {
  description?: string;
  protocol_message_id?: string;
  message_id_hex?: string;
  subaddress?: number;
  byte_count?: number;
  scheduling?: string;
  rate_min_hz?: number;
  rate_max_hz?: number;
  latency_max_ms?: number;
  latency_typical_ms?: number;
  priority?: MessagePriority;
  is_periodic?: boolean;
  timeout_ms?: number;
  integrity_mechanism?: string;
  fragmentation?: boolean;
  encryption?: string;
  authentication?: string;
  source_system_name?: string;
  target_system_name?: string;
  icd_reference?: string;
  notes?: string;
  metadata_json?: Record<string, any>;
  bus_def_id: number;
  unit_id: number;
  project_id?: number;
  created_at: string;
  updated_at: string;
  total_bits: number;
}

export interface MessageWithFields extends MessageDefinition {
  fields: MessageField[];
}

// ── 7. MessageField ──

export interface MessageField {
  id: number;
  field_name: string;
  label?: string;
  description?: string;
  data_type: FieldDataType;
  data_type_custom?: string;
  byte_order?: string;
  word_number?: number;
  byte_offset?: number;
  bit_offset?: number;
  bit_length: number;
  unit_of_measure?: string;
  scale_factor?: number;
  offset_value?: number;
  lsb_value?: number;
  min_value?: number;
  max_value?: number;
  resolution?: number;
  accuracy?: number;
  default_value?: string;
  initial_value?: string;
  invalid_value?: string;
  stale_timeout_ms?: number;
  enum_values?: Record<string, string>;
  bit_mask?: string;
  field_order?: number;
  is_padding?: boolean;
  is_spare?: boolean;
  notes?: string;
  message_id: number;
  created_at: string;
}

// ── 8. WireHarness ──

export interface WireHarness {
  id: number;
  harness_id?: string;
  name: string;
  description?: string;
  cable_type?: string;
  cable_spec?: string;
  cable_part_number?: string;
  cable_manufacturer?: string;
  overall_length_m?: number;
  overall_length_max_m?: number;
  mass_kg?: number;
  outer_diameter_mm?: number;
  jacket_material?: string;
  jacket_material_custom?: string;
  jacket_color?: string;
  temp_rating_min_c?: number;
  temp_rating_max_c?: number;
  voltage_rating_v?: number;
  bend_radius_min_mm?: number;
  shield_type?: string;
  shield_coverage_pct?: number;
  shield_material?: string;
  overall_shield_termination?: string;
  conductor_count?: number;
  pair_count?: number;
  status?: HarnessStatus;
  drawing_number?: string;
  drawing_revision?: string;
  approved_by?: string;
  approval_date?: string;
  from_unit_id: number;
  from_connector_id: number;
  to_unit_id: number;
  to_connector_id: number;
  project_id?: number;
  created_at: string;
  updated_at: string;
  wire_count: number;
  from_unit_designation?: string;
  from_connector_designator?: string;
  to_unit_designation?: string;
  to_connector_designator?: string;
}

export interface WireHarnessDetail extends WireHarness {
  wires: Wire[];
}

// ── 9. Wire ──

export interface Wire {
  id: number;
  wire_number: string;
  signal_name: string;
  wire_gauge?: string;
  wire_gauge_custom?: string;
  wire_color_primary?: string;
  wire_color_secondary?: string;
  wire_color_tertiary?: string;
  wire_type: WireType;
  wire_type_custom?: string;
  wire_spec?: string;
  wire_material?: string;
  insulation_material?: string;
  insulation_color?: string;
  length_m?: number;
  length_max_m?: number;
  from_pin_id: number;
  to_pin_id: number;
  harness_id: number;
  splice_info?: string;
  termination_from?: string;
  termination_to?: string;
  heat_shrink?: boolean;
  heat_shrink_size?: string;
  notes?: string;
  created_at: string;
  from_pin_number?: string;
  from_signal_name?: string;
  from_connector_designator?: string;
  from_unit_designation?: string;
  to_pin_number?: string;
  to_signal_name?: string;
  to_connector_designator?: string;
  to_unit_designation?: string;
}

// ── 10. Interface ──

export interface Interface {
  id: number;
  interface_id?: string;
  name: string;
  description?: string;
  interface_type: InterfaceType;
  interface_type_custom?: string;
  direction: InterfaceDirection;
  source_system_id: number;
  target_system_id: number;
  status: InterfaceStatus;
  criticality: InterfaceCriticality;
  icd_document_number?: string;
  icd_document_revision?: string;
  icd_section?: string;
  version: number;
  data_rate_aggregate?: string;
  latency_requirement_ms?: number;
  availability_requirement_pct?: number;
  notes?: string;
  metadata_json?: Record<string, any>;
  project_id?: number;
  owner_id?: number;
  created_at: string;
  updated_at: string;
  source_system_name?: string;
  target_system_name?: string;
  harness_count: number;
  bus_count: number;
  message_count: number;
}

// ── 11. UnitEnvironmentalSpec ──

export interface UnitEnvironmentalSpec {
  id: number;
  unit_id: number;
  category: string;
  standard?: string;
  standard_custom?: string;
  test_method?: string;
  test_level?: string;
  limit_value?: number;
  limit_unit?: string;
  limit_min?: number;
  limit_max?: number;
  frequency_range?: string;
  duration?: string;
  test_condition?: string;
  compliance_status?: string;
  test_report_ref?: string;
  notes?: string;
  auto_generated?: boolean;
  created_at: string;
}

// ── 12. InterfaceRequirementLink ──

export interface InterfaceRequirementLink {
  id: number;
  entity_type: InterfaceEntityType;
  entity_id: number;
  requirement_id: number;
  link_type: InterfaceLinkType;
  link_type_custom?: string;
  description?: string;
  auto_generated: boolean;
  auto_req_source?: string;
  auto_req_template?: string;
  confidence_score?: number;
  status: string;
  reviewed_by_id?: number;
  reviewed_at?: string;
  created_by_id?: number;
  created_at: string;
  requirement_req_id?: string;
  requirement_title?: string;
}

// ── 13. AutoReqLog ──

export interface AutoReqLog {
  id: number;
  project_id: number;
  trigger_entity_type?: string;
  trigger_entity_id?: number;
  trigger_action?: string;
  requirements_generated?: number;
  verifications_generated?: number;
  links_generated?: number;
  template_used?: string;
  generation_summary?: Record<string, any>;
  user_id?: number;
  created_at: string;
}

// ── 14. InterfaceChangeImpact ──

export interface InterfaceChangeImpact {
  id: number;
  project_id: number;
  change_type?: string;
  entity_type?: string;
  entity_id?: number;
  entity_description?: string;
  affected_requirements?: Record<string, any>;
  affected_verifications?: Record<string, any>;
  risk_level?: string;
  total_affected?: number;
  user_action?: string;
  resolved: boolean;
  resolved_at?: string;
  user_id?: number;
  created_at: string;
}


// ══════════════════════════════════════
//  Aggregate / View Types
// ══════════════════════════════════════

export interface N2MatrixCell {
  source_system_id: number;
  source_system_name: string;
  target_system_id: number;
  target_system_name: string;
  interface_count: number;
  harness_count: number;
  bus_protocols: string[];
  signal_count: number;
  criticality_max?: string;
}

export interface N2MatrixResponse {
  systems: System[];
  matrix: (N2MatrixCell | null)[][];
}

export interface BlockDiagramNode {
  id: number;
  system_id: string;
  name: string;
  abbreviation?: string;
  type: string;
  unit_count: number;
  x?: number;
  y?: number;
}

export interface BlockDiagramEdge {
  source_id: number;
  target_id: number;
  interface_id: number;
  name: string;
  type: string;
  criticality?: string;
  direction: string;
  harness_count: number;
}

export interface BlockDiagramResponse {
  nodes: BlockDiagramNode[];
  edges: BlockDiagramEdge[];
}

export interface SignalTraceHop {
  unit?: string;
  connector?: string;
  pin?: string;
  wire?: string;
  harness?: string;
  bus?: string;
  message?: string;
}

export interface SignalTraceResult {
  signal_name: string;
  path: SignalTraceHop[];
}

export interface InterfaceCoverageResponse {
  total_interfaces: number;
  with_requirements: number;
  without_requirements: number;
  coverage_pct: number;
  units_with_specs: number;
  units_without_specs: number;
  auto_generated_count: number;
  approved_count: number;
  pending_count: number;
}

export interface AutoReqGenerationResult {
  requirements_generated: number;
  verifications_generated: number;
  links_generated: number;
  requirements: { id: number; req_id: string; title: string; level: string; statement: string }[];
}

export interface ImpactPreview {
  action: string;
  entity_id: number | number[];
  affected_requirements: Record<string, any>[];
  downstream_requirements?: Record<string, any>[];
  risk_level: string;
  total_affected: number;
  summary?: Record<string, any>;
  action_options: string[];
}

export interface PinoutData {
  connector_info: Record<string, any>;
  pins: Pin[];
  pin_summary: { power: number; ground: number; signal: number; spare: number; no_connect: number };
  total_pins: number;
}

export interface BusUtilization {
  bus_id: number;
  bus_name: string;
  protocol: string;
  capacity_bps: number;
  used_bps: number;
  utilization_pct?: number;
  message_count: number;
  messages: { id: number; label: string; bits_per_second: number; pct_of_total: number }[];
}

export interface ByteMapLayout {
  message_id: number;
  label: string;
  total_words: number;
  word_size_bits: number;
  total_fields: number;
  total_bits_used: number;
  layout: { word: number; bits: { field_id: number; field_name: string; start: number; end: number; color: string; is_spare: boolean }[] }[];
}

export interface ImportPreviewResponse {
  file_name: string;
  sheets_found: string[];
  units: any[];
  connectors: any[];
  pins: any[];
  buses: any[];
  messages: any[];
  fields: any[];
  summary: Record<string, any>;
}

export interface ImportConfirmResponse {
  systems_created: number;
  units_created: number;
  connectors_created: number;
  pins_created: number;
  buses_created: number;
  pin_assignments_created: number;
  messages_created: number;
  fields_created: number;
  env_specs_created: number;
  errors: string[];
}


// ══════════════════════════════════════
//  UI Constants
// ══════════════════════════════════════

export const CRITICALITY_COLORS: Record<string, { bg: string; text: string }> = {
  catastrophic:      { bg: 'rgba(239,68,68,0.25)',  text: '#EF4444' },
  hazardous:         { bg: 'rgba(239,68,68,0.18)',  text: '#F87171' },
  major:             { bg: 'rgba(245,158,11,0.18)', text: '#F59E0B' },
  minor:             { bg: 'rgba(59,130,246,0.12)', text: '#3B82F6' },
  no_effect:         { bg: 'rgba(100,116,139,0.15)', text: '#64748B' },
  safety_critical_a: { bg: 'rgba(239,68,68,0.25)',  text: '#EF4444' },
  mission_critical:  { bg: 'rgba(245,158,11,0.18)', text: '#F59E0B' },
  non_critical:      { bg: 'rgba(100,116,139,0.12)', text: '#94A3B8' },
};

export const SIGNAL_TYPE_COLORS: Record<string, string> = {
  power_primary: '#EF4444',
  power_secondary: '#F97316',
  power_return: '#F59E0B',
  chassis_ground: '#6B7280',
  signal_ground: '#9CA3AF',
  signal_digital_single: '#3B82F6',
  signal_digital_differential: '#2563EB',
  signal_analog_single: '#10B981',
  signal_analog_differential: '#059669',
  rf_signal: '#8B5CF6',
  discrete_input: '#06B6D4',
  discrete_output: '#0891B2',
  spare: '#475569',
  no_connect: '#334155',
  shield_overall: '#A78BFA',
};

export const RISK_COLORS: Record<string, { bg: string; text: string }> = {
  none:     { bg: 'rgba(100,116,139,0.1)', text: '#94A3B8' },
  low:      { bg: 'rgba(16,185,129,0.15)', text: '#10B981' },
  medium:   { bg: 'rgba(245,158,11,0.15)', text: '#F59E0B' },
  high:     { bg: 'rgba(239,68,68,0.15)',  text: '#EF4444' },
  critical: { bg: 'rgba(239,68,68,0.25)',  text: '#DC2626' },
};
