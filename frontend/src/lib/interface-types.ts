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
  | 'm12_4pin' | 'm12_8pin' | 'backplane_vpx'
  // ── Board-level / prototype headers (Pi, Arduino, FPGA mezzanines) ──
  | 'pcb_header' | 'pcb_header_2_54mm' | 'pcb_header_2_00mm' | 'pcb_header_1_27mm'
  | 'pcb_header_idc' | 'pcb_header_shrouded'
  // ── Small-signal JST variants (HATs, sensor breakouts) ──
  | 'jst_sh' | 'jst_gh' | 'jst_zh'
  // ── Modular interop ──
  | 'qwiic_stemma_qt'
  | 'custom' | string;

export type ConnectorGender = 'male_pin' | 'female_socket' | 'hermaphroditic' | 'genderless';

export type SignalType =
  // ── Power ──
  | 'power_primary' | 'power_secondary' | 'power_return'
  | 'chassis_ground' | 'signal_ground'
  // ── Generic digital / analog (legacy backend) ──
  | 'signal_digital_single' | 'signal_digital_differential'
  | 'signal_analog_single' | 'signal_analog_differential'
  // ── Voltage-specific digital (board-level) ──
  | 'digital_3v3' | 'digital_5v' | 'digital_12v' | 'digital_lvds'
  // ── Specific analog ──
  | 'analog_voltage' | 'analog_current_4_20ma'
  // ── Clocks ──
  | 'clock_single' | 'clock_differential' | 'clock_reference'
  // ── RF ──
  | 'rf_signal' | 'rf_lo' | 'rf_if'
  // ── Discrete I/O ──
  | 'discrete_input' | 'discrete_output' | 'discrete_bidirectional'
  | 'discrete_command' | 'discrete_status'
  // ── Serial protocols ──
  | 'serial_data' | 'parallel_data' | 'serial_rs232' | 'serial_rs422'
  | 'serial_rs485' | 'serial_uart'
  // ── Board-level digital buses ──
  | 'i2c_scl' | 'i2c_sda'
  | 'spi_clk' | 'spi_mosi' | 'spi_miso' | 'spi_cs'
  | 'can_high' | 'can_low'
  // ── Aerospace buses (pin-level) ──
  | 'mil_std_1553_a' | 'mil_std_1553_b' | 'arinc_429' | 'arinc_664'
  | 'spacewire_data' | 'spacewire_strobe'
  // ── Ethernet variants (pin-level) ──
  | 'ethernet_100base_t' | 'ethernet_1000base_t'
  // ── Media ──
  | 'video_analog' | 'video_sdi' | 'audio_analog' | 'audio_digital_aes'
  // ── Fiber ──
  | 'fiber_optic_single' | 'fiber_optic_multi' | 'fiber_tx' | 'fiber_rx'
  // ── Pulse / timing ──
  | 'pwm' | 'pulse'
  // ── Transducers ──
  | 'thermocouple' | 'rtd' | 'strain_gauge' | 'lvdt'
  // ── Ordnance ──
  | 'pyro_fire' | 'pyro_arm'
  // ── Misc ──
  | 'coax_signal'
  | 'spare' | 'no_connect'
  | 'shield' | 'shield_overall' | 'shield_individual' | 'shield_drain'
  | 'test_point' | 'key_pin' | 'alignment_pin'
  | 'reserved' | 'custom';

export type PinDirection =
  | 'input' | 'output' | 'bidirectional' | 'tri_state'
  | 'open_collector' | 'open_drain' | 'passive'
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
  /**
   * Nullable post-Phase-1: `owner_type='harness'` connectors (mating
   * connectors owned by a wire harness endpoint) leave this null.
   * LRU-side connectors always have unit_id set.
   */
  unit_id?: number | null;
  /**
   * Discriminator added in Phase 1. Values: 'unit' (LRU-side, default) or
   * 'harness' (owned by a wire_harness endpoint as a mating connector).
   */
  owner_type?: 'unit' | 'harness';
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
  /**
   * FK to the peer Unit this pin is intended to connect to across the
   * mating connector. Nullable — spare pins, chassis grounds, or pins
   * that connect to something external (test equipment, a different
   * project, etc.) leave this null.
   *
   * When set, enables the `by_peer_lru` auto-wire strategy, which pairs
   * pins whose mating_unit_ids cross-reference each other and whose
   * signal_name/direction are conjugate (input↔output, or both bidi).
   */
  mating_unit_id?: number | null;
  /** Denormalized for display — the designation of the mating Unit. */
  mating_unit_designation?: string | null;
  /** Denormalized for display — the name of the mating Unit. */
  mating_unit_name?: string | null;
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
  /**
   * Legacy 2-endpoint fields — populated by the backend for backward
   * compatibility during the Phase 1 → Phase 3 transition. New code should
   * iterate `endpoints` instead of reading these.
   */
  from_unit_id?: number | null;
  from_connector_id?: number | null;
  to_unit_id?: number | null;
  to_connector_id?: number | null;
  project_id?: number;
  created_at: string;
  updated_at: string;
  /**
   * Phase 1 — new Harness Overview fields, matching the migration's
   * wire_harnesses column additions. All optional, all editable.
   */
  shielding_class?: string;
  sleeve_type?: string;
  operating_temp_min_c?: number;
  operating_temp_max_c?: number;
  min_bend_radius_mm?: number;
  weight_g_per_m?: number;
  drain_wire_spec?: string;
  service_loop_m?: number;
  mil_spec?: string;
  wire_count: number;
  from_unit_designation?: string;
  from_connector_designator?: string;
  to_unit_designation?: string;
  to_connector_designator?: string;
  /**
   * Phase 1 — list of endpoints. Each entry is a mating connector owned by
   * this harness, plugged into one LRU connector. Multi-endpoint harnesses
   * (>2 entries) are built up by the auto-grow engine.
   */
  endpoints?: HarnessEndpoint[];
}

/**
 * One harness endpoint: a mating connector owned by the harness, plugged
 * into an LRU-side connector. The mating connector has its own Pin rows
 * cloned from the LRU side at endpoint-creation time.
 */
export interface HarnessEndpoint {
  id: number;
  harness_id: number;
  mating_connector_id: number;
  lru_connector_id?: number | null;
  label?: string;
  tail_length_m?: number;
  notes?: string;
  created_at: string;
  updated_at: string;
  // Denormalized display fields populated by the router
  mating_connector_designator?: string;
  mating_connector_type?: string;
  lru_connector_designator?: string;
  lru_unit_id?: number | null;
  lru_unit_designation?: string;
  lru_unit_name?: string;
  wire_count?: number;
}

/**
 * A Connection is the logical "these two LRUs have wires between them"
 * view. One row per unordered unit pair. Auto-maintained by the
 * wire-create/delete path.
 *
 * Canonical ordering: `lru_a_id` is always numerically less than `lru_b_id`.
 * Both "UPS connected to RPI" and "RPI connected to UPS" resolve to the
 * same row — the UI just renders whichever direction feels natural.
 */
export interface Connection {
  id: number;
  project_id: number;
  lru_a_id: number;
  lru_b_id: number;
  created_at: string;
  updated_at: string;
  // Denormalized
  lru_a_designation?: string;
  lru_a_name?: string;
  lru_b_designation?: string;
  lru_b_name?: string;
  wire_count: number;
  harness_ids: number[];
  harness_names: string[];
}

export interface ConnectionDetail extends Connection {
  wires: Wire[];
}

// ── Auto-grow engine ──

/** One proposed wire in an auto-grow batch. */
export interface AutoGrowPair {
  from_lru_pin_id: number;
  to_lru_pin_id: number;
  signal_name?: string;
  wire_type?: string;
  wire_gauge?: string;
}

/** User's decision on one ambiguous merge case. */
export interface AmbiguityDecision {
  pair_index: number;
  /**
   * One of:
   *   'merge_into_a'  — add the pair's wire to harness A, and fold harness B
   *                     (and its wires/endpoints) into A
   *   'merge_into_b'  — inverse
   *   'new_harness'   — don't merge, create a third harness just for this wire
   *   'cancel'        — skip this pair, don't create a wire for it
   */
  action: 'merge_into_a' | 'merge_into_b' | 'new_harness' | 'cancel';
  new_harness_name?: string;
}

export interface AutoGrowRequest {
  project_id: number;
  pairs: AutoGrowPair[];
  decisions?: AmbiguityDecision[];
}

/** One ambiguous pair the engine surfaced back to the UI. */
export interface AutoGrowAmbiguity {
  pair_index: number;
  from_lru_pin_id: number;
  to_lru_pin_id: number;
  from_lru_unit_id: number;
  from_lru_unit_designation: string;
  to_lru_unit_id: number;
  to_lru_unit_designation: string;
  harness_a_id: number;
  harness_a_name: string;
  harness_a_wire_count: number;
  harness_a_endpoint_count: number;
  harness_b_id: number;
  harness_b_name: string;
  harness_b_wire_count: number;
  harness_b_endpoint_count: number;
  /** LRU designations spanned by harness A — displayed in the modal so
   *  the user sees "A spans {DG3, DG4}" without extra round-trips. */
  harness_a_lru_designations: string[];
  harness_b_lru_designations: string[];
  /** Which actions the user may pick. 'new_harness' only appears when
   *  BOTH LRU connectors on this pair are un-claimed. The modal hides or
   *  disables options not in this list. 'cancel' is always present. */
  valid_actions: Array<'merge_into_a' | 'merge_into_b' | 'new_harness' | 'cancel'>;
  /** When 'new_harness' is not in valid_actions, this explains why — the
   *  modal can show the option greyed out with this as the tooltip. */
  new_harness_disallowed_reason?: string | null;
}

export interface AutoGrowSkipped {
  pair_index: number;
  from_lru_pin_id: number;
  to_lru_pin_id: number;
  /** Human-readable explanation: bad pin id, same LRU, pin already wired,
   *  etc. UI can show these as a "Skipped 2 of 8 pairs" detail. */
  reason: string;
}

export interface AutoGrowResult {
  wires_created: number;
  harnesses_created: number;
  endpoints_added: number;
  ambiguities: AutoGrowAmbiguity[];
  connections_touched: number[];
  new_wire_ids: number[];
  new_harness_ids: number[];
  /** Phase 2b — pairs that couldn't be processed, with reasons. */
  skipped?: AutoGrowSkipped[];
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
  /**
   * Phase 1 additions — the wire's pin endpoints on the harness's own
   * mating connectors. Null until the wire is assigned to a harness with
   * proper endpoints. Kept in sync with the LRU pin refs by the auto-grow
   * engine: same pin_number on the matching mating connector.
   *
   * Queries that traverse the LRU side should keep using from_pin_id /
   * to_pin_id. Queries for BOM or harness drawings use the mating refs.
   */
  from_mating_pin_id?: number | null;
  to_mating_pin_id?: number | null;
  // Computed joins (LRU side)
  from_pin_number?: string;
  from_signal_name?: string;
  from_connector_designator?: string;
  from_unit_designation?: string;
  to_pin_number?: string;
  to_signal_name?: string;
  to_connector_designator?: string;
  to_unit_designation?: string;
  // Computed joins (mating side)
  from_mating_connector_designator?: string;
  to_mating_connector_designator?: string;
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
  // Power
  power_primary: '#EF4444',
  power_secondary: '#F97316',
  power_return: '#F59E0B',
  // Ground
  chassis_ground: '#6B7280',
  signal_ground: '#9CA3AF',
  // Generic digital
  signal_digital_single: '#3B82F6',
  signal_digital_differential: '#2563EB',
  digital_3v3: '#3B82F6',
  digital_5v: '#2563EB',
  digital_12v: '#1D4ED8',
  digital_lvds: '#4F46E5',
  // Analog
  signal_analog_single: '#10B981',
  signal_analog_differential: '#059669',
  analog_voltage: '#10B981',
  analog_current_4_20ma: '#047857',
  // Transducers
  thermocouple: '#D97706',
  rtd: '#C2410C',
  strain_gauge: '#B45309',
  lvdt: '#92400E',
  // RF
  rf_signal: '#8B5CF6',
  rf_lo: '#7C3AED',
  rf_if: '#A78BFA',
  // Discrete
  discrete_input: '#06B6D4',
  discrete_output: '#0891B2',
  discrete_bidirectional: '#0E7490',
  discrete_command: '#06B6D4',
  discrete_status: '#0891B2',
  // Serial
  serial_data: '#14B8A6',
  serial_rs232: '#14B8A6',
  serial_rs422: '#0D9488',
  serial_rs485: '#0F766E',
  serial_uart: '#14B8A6',
  // I²C / SPI / CAN
  i2c_sda: '#F472B6',
  i2c_scl: '#EC4899',
  spi_mosi: '#A855F7',
  spi_miso: '#9333EA',
  spi_clk: '#7E22CE',
  spi_cs: '#6B21A8',
  can_high: '#F59E0B',
  can_low: '#D97706',
  // Aerospace buses
  mil_std_1553_a: '#DC2626',
  mil_std_1553_b: '#B91C1C',
  arinc_429: '#EA580C',
  arinc_664: '#C2410C',
  spacewire_data: '#4F46E5',
  spacewire_strobe: '#4338CA',
  // Ethernet
  ethernet_100base_t: '#0284C7',
  ethernet_1000base_t: '#0369A1',
  // Media
  video_analog: '#DB2777',
  video_sdi: '#BE185D',
  audio_analog: '#E11D48',
  audio_digital_aes: '#BE123C',
  // Fiber
  fiber_optic_single: '#22C55E',
  fiber_optic_multi: '#16A34A',
  fiber_tx: '#22C55E',
  fiber_rx: '#16A34A',
  // Clocks
  clock_single: '#818CF8',
  clock_differential: '#6366F1',
  clock_reference: '#4F46E5',
  // Pulse
  pwm: '#FB923C',
  pulse: '#F97316',
  // Ordnance
  pyro_fire: '#DC2626',
  pyro_arm: '#991B1B',
  // Coax
  coax_signal: '#7C3AED',
  // Misc
  spare: '#475569',
  no_connect: '#334155',
  shield: '#A78BFA',
  shield_overall: '#A78BFA',
  shield_individual: '#8B5CF6',
  shield_drain: '#7C3AED',
  test_point: '#EAB308',
  key_pin: '#64748B',
  alignment_pin: '#64748B',
  reserved: '#475569',
  custom: '#64748B',
};

export const RISK_COLORS: Record<string, { bg: string; text: string }> = {
  none:     { bg: 'rgba(100,116,139,0.1)', text: '#94A3B8' },
  low:      { bg: 'rgba(16,185,129,0.15)', text: '#10B981' },
  medium:   { bg: 'rgba(245,158,11,0.15)', text: '#F59E0B' },
  high:     { bg: 'rgba(239,68,68,0.15)',  text: '#EF4444' },
  critical: { bg: 'rgba(239,68,68,0.25)',  text: '#DC2626' },
};

// ══════════════════════════════════════════════════════════════
//  labelize() — smart human-readable labels for enum values
//
//  Turns snake_case enum values into properly-cased display labels,
//  with domain-aware overrides for acronyms and standards.
//    'signal_ground'      → 'Signal Ground'
//    'i2c_sda'            → 'I²C SDA'
//    'mil_std_1553_a'     → 'MIL-STD-1553 A'
//    'rj45'               → 'RJ-45'
//    'd_sub_25'           → 'D-Sub 25'
//    'rs232'              → 'RS-232'
//    'open_collector'     → 'Open Collector'
//
//  Use in every <option> label and display chip throughout the app.
// ══════════════════════════════════════════════════════════════

// Exact-match overrides (take precedence over word-level rules)
const LABEL_OVERRIDES: Record<string, string> = {
  // Pin / signal
  i2c_sda: 'I²C SDA',
  i2c_scl: 'I²C SCL',
  spi_mosi: 'SPI MOSI',
  spi_miso: 'SPI MISO',
  spi_clk: 'SPI CLK',
  spi_cs: 'SPI CS',
  can_high: 'CAN High',
  can_low: 'CAN Low',
  serial_rs232: 'Serial RS-232',
  serial_rs422: 'Serial RS-422',
  serial_rs485: 'Serial RS-485',
  serial_uart: 'Serial UART',
  rs232: 'RS-232',
  rs422: 'RS-422',
  rs485: 'RS-485',
  uart: 'UART',
  digital_3v3: 'Digital 3.3V',
  digital_5v: 'Digital 5V',
  digital_12v: 'Digital 12V',
  digital_lvds: 'Digital LVDS',
  analog_voltage: 'Analog Voltage',
  analog_current_4_20ma: 'Analog Current 4–20 mA',
  mil_std_1553_a: 'MIL-STD-1553 A',
  mil_std_1553_b: 'MIL-STD-1553 B',
  arinc_429: 'ARINC-429',
  arinc_664: 'ARINC-664',
  spacewire_data: 'SpaceWire Data',
  spacewire_strobe: 'SpaceWire Strobe',
  ethernet_100base_t: 'Ethernet 100BASE-T',
  ethernet_1000base_t: 'Ethernet 1000BASE-T',
  ethernet_10gbase_t: 'Ethernet 10GBASE-T',
  ethernet_100base_tx: 'Ethernet 100BASE-TX',
  audio_digital_aes: 'Audio Digital AES',
  video_sdi: 'Video SDI',
  video_analog: 'Video Analog',
  audio_analog: 'Audio Analog',
  fiber_tx: 'Fiber TX',
  fiber_rx: 'Fiber RX',
  fiber_optic_single: 'Fiber Optic (Single-Mode)',
  fiber_optic_multi: 'Fiber Optic (Multi-Mode)',
  pyro_fire: 'Pyro Fire',
  pyro_arm: 'Pyro Arm',
  pwm: 'PWM',
  lvdt: 'LVDT',
  rtd: 'RTD',
  rf_signal: 'RF Signal',
  rf_lo: 'RF LO',
  rf_if: 'RF IF',
  tri_state: 'Tri-State',
  open_collector: 'Open Collector',
  open_drain: 'Open Drain',
  no_connect: 'No Connect',
  test_point: 'Test Point',
  key_pin: 'Key Pin',
  alignment_pin: 'Alignment Pin',

  // Connector
  rj45: 'RJ-45',
  rj45_shielded: 'RJ-45 Shielded',
  rj11: 'RJ-11',
  usb_a: 'USB-A',
  usb_b: 'USB-B',
  usb_c: 'USB-C',
  usb_mini_b: 'USB Mini-B',
  usb_micro_b: 'USB Micro-B',
  sma: 'SMA',
  sma_reverse: 'SMA Reverse',
  smb: 'SMB',
  smc: 'SMC',
  bnc: 'BNC',
  tnc: 'TNC',
  n_type: 'N-Type',
  f_type: 'F-Type',
  d_sub_9: 'D-Sub 9',
  d_sub_15: 'D-Sub 15',
  d_sub_25: 'D-Sub 25',
  d_sub_37: 'D-Sub 37',
  d_sub_50: 'D-Sub 50',
  d_sub_hd15: 'D-Sub HD15',
  d_sub_hd26: 'D-Sub HD26',
  micro_d_9: 'Micro-D 9',
  micro_d_15: 'Micro-D 15',
  micro_d_25: 'Micro-D 25',
  micro_d_37: 'Micro-D 37',
  micro_d_51: 'Micro-D 51',
  nano_d_9: 'Nano-D 9',
  nano_d_15: 'Nano-D 15',
  nano_d_25: 'Nano-D 25',
  nano_d_31: 'Nano-D 31',
  nano_d_37: 'Nano-D 37',
  m8_3pin: 'M8 3-Pin',
  m8_4pin: 'M8 4-Pin',
  m12_4pin: 'M12 4-Pin',
  m12_5pin: 'M12 5-Pin',
  m12_8pin: 'M12 8-Pin',
  m12_12pin: 'M12 12-Pin',
  fiber_lc: 'Fiber LC',
  fiber_sc: 'Fiber SC',
  fiber_st: 'Fiber ST',
  fiber_fc: 'Fiber FC',
  fiber_mtp_mpo: 'Fiber MTP/MPO',
  mil_dtl_38999_series_i: 'MIL-DTL-38999 Series I',
  mil_dtl_38999_series_ii: 'MIL-DTL-38999 Series II',
  mil_dtl_38999_series_iii: 'MIL-DTL-38999 Series III',
  mil_dtl_38999_series_iv: 'MIL-DTL-38999 Series IV',
  mil_dtl_26482_series_i: 'MIL-DTL-26482 Series I',
  mil_dtl_26482_series_ii: 'MIL-DTL-26482 Series II',
  mil_dtl_83723_series_iii: 'MIL-DTL-83723 Series III',
  mil_dtl_5015: 'MIL-DTL-5015',
  mil_c_26500: 'MIL-C-26500',
  backplane_vme: 'Backplane VME',
  backplane_cpci: 'Backplane cPCI',
  backplane_vpx: 'Backplane VPX',
  backplane_vita_46: 'Backplane VITA-46',
  samtec_searay: 'Samtec SEARAY',
  samtec_tiger_eye: 'Samtec Tiger Eye',
  harwin_m80: 'Harwin M80',
  harwin_gecko: 'Harwin Gecko',
  molex_mini_fit: 'Molex Mini-Fit',
  molex_micro_fit: 'Molex Micro-Fit',
  jst_xh: 'JST XH',
  jst_ph: 'JST PH',
  jst_sh: 'JST SH',
  jst_gh: 'JST GH',
  jst_zh: 'JST ZH',
  amphenol_pt: 'Amphenol PT',
  amphenol_ms: 'Amphenol MS',
  power_anderson: 'Power Anderson',
  power_mil_c_22992: 'Power MIL-C-22992',
  hermetic_feedthrough: 'Hermetic Feedthrough',
  pcb_header: 'PCB Header',
  pcb_header_2_54mm: 'PCB Header 2.54 mm',
  pcb_header_2_00mm: 'PCB Header 2.00 mm',
  pcb_header_1_27mm: 'PCB Header 1.27 mm',
  pcb_header_idc: 'PCB Header IDC',
  pcb_header_shrouded: 'PCB Header Shrouded',
  qwiic_stemma_qt: 'Qwiic / STEMMA QT',

  // Gender
  male_pin: 'Male (Pin)',
  female_socket: 'Female (Socket)',

  // Bus protocol shortforms
  mil_std_1553a: 'MIL-STD-1553A',
  mil_std_1553b: 'MIL-STD-1553B',
  mil_std_1773: 'MIL-STD-1773',
  spacewire: 'SpaceWire',
  spacewire_rmap: 'SpaceWire RMAP',
  can_2b: 'CAN 2.0B',
  canfd: 'CAN FD',
  canopen: 'CANopen',
  spi_mode0: 'SPI Mode 0',
  i2c_standard: 'I²C Standard',
  i2c_fast: 'I²C Fast',
  arinc_664_part7: 'ARINC-664 Part 7',
  usb_2_0: 'USB 2.0',
  usb_3_0: 'USB 3.0',
  jtag: 'JTAG',
  swd: 'SWD',
  ccsds_tm: 'CCSDS TM',
  ccsds_tc: 'CCSDS TC',
  analog_4_20ma: 'Analog 4–20 mA',
  discrete_28v: 'Discrete 28V',
  discrete_5v: 'Discrete 5V',
};

// Words that should stay uppercase when they appear as tokens
const ACRONYMS = new Set([
  'id', 'ip', 'rf', 'dc', 'ac', 'tx', 'rx', 'io',
  'mosi', 'miso', 'clk', 'cs', 'sck', 'cpu', 'gpu',
  'lo', 'if', 'hi', 'lo',
  'pcb', 'icd', 'ecu', 'mcu',
]);

/**
 * Convert a snake_case enum value to a human-readable label.
 * Handles overrides (I²C, MIL-STD, etc.), acronyms, and Title Case fallback.
 */
export function labelize(value: string | null | undefined): string {
  if (!value) return '';
  const key = String(value).toLowerCase().trim();
  if (LABEL_OVERRIDES[key]) return LABEL_OVERRIDES[key];

  // Fallback: split on underscores and title-case each word
  return key.split('_').map(word => {
    if (!word) return word;
    if (ACRONYMS.has(word)) return word.toUpperCase();
    // Numbers stay as-is
    if (/^\d/.test(word)) return word;
    // Capitalize first letter
    return word.charAt(0).toUpperCase() + word.slice(1);
  }).join(' ');
}
