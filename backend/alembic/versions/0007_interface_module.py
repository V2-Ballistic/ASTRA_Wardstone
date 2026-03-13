"""add_interface_module

Revision ID: 0007
Revises: 0006
Create Date: 2026-03-13 00:00:00.000000

Adds the Interface Control Document (ICD) management module:
  38 PostgreSQL enum types
  15 tables: systems, units, connectors, pins, bus_definitions,
    pin_bus_assignments, message_definitions, message_fields,
    wire_harnesses, wires, interfaces, unit_environmental_specs,
    interface_requirement_links, auto_requirement_logs,
    interface_change_impacts
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSON

revision: str = "0007"
down_revision: Union[str, None] = "0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ══════════════════════════════════════════════════════════════
#  Enum type definitions (38)
# ══════════════════════════════════════════════════════════════

systemtype = postgresql.ENUM(
    "subsystem", "lru", "wru", "sru", "sensor_suite", "actuator_assembly",
    "processor_unit", "power_system", "thermal_system", "structural",
    "ground_segment", "vehicle", "payload", "antenna_system", "propulsion",
    "guidance_nav_control", "communication", "data_handling", "ordnance",
    "test_equipment", "external_system", "software", "firmware", "custom",
    name="systemtype", create_type=False,
)
systemstatus = postgresql.ENUM(
    "concept", "preliminary_design", "detailed_design", "fabrication",
    "integration", "qualification_test", "acceptance_test", "operational",
    "maintenance", "retired", "obsolete",
    name="systemstatus", create_type=False,
)
unittype = postgresql.ENUM(
    "lru", "wru", "sru", "cca", "pcb", "backplane", "chassis", "sensor",
    "actuator", "motor", "processor", "fpga", "asic", "power_supply",
    "power_converter", "battery", "solar_panel", "transmitter", "receiver",
    "transceiver", "antenna", "waveguide", "filter_rf", "amplifier",
    "oscillator", "switch_rf", "diplexer", "coupler", "cable_assembly",
    "connector_assembly", "relay_box", "junction_box", "terminal_block",
    "fuse_box", "transformer", "regulator", "gyroscope", "accelerometer",
    "star_tracker", "sun_sensor", "earth_sensor", "gps_receiver",
    "inertial_measurement_unit", "reaction_wheel", "thruster", "valve",
    "pyrotechnic", "cots_equipment", "gse", "firmware_module",
    "software_module", "custom",
    name="unittype", create_type=False,
)
unitstatus = postgresql.ENUM(
    "concept", "preliminary_design", "detailed_design", "prototype",
    "engineering_model", "qualification_unit", "flight_unit", "flight_spare",
    "production", "installed", "qualified", "accepted", "operational",
    "failed", "obsolete",
    name="unitstatus", create_type=False,
)
connectortype = postgresql.ENUM(
    "mil_dtl_38999_series_i", "mil_dtl_38999_series_ii",
    "mil_dtl_38999_series_iii", "mil_dtl_38999_series_iv",
    "mil_dtl_26482_series_i", "mil_dtl_26482_series_ii",
    "mil_dtl_83723_series_iii", "mil_dtl_5015", "mil_c_26500",
    "d_sub_9", "d_sub_15", "d_sub_25", "d_sub_37", "d_sub_50",
    "d_sub_hd15", "d_sub_hd26",
    "micro_d_9", "micro_d_15", "micro_d_25", "micro_d_37", "micro_d_51",
    "nano_d_9", "nano_d_15", "nano_d_25", "nano_d_31", "nano_d_37",
    "rj11", "rj45", "rj45_shielded",
    "usb_a", "usb_b", "usb_mini_b", "usb_micro_b", "usb_c",
    "sma", "sma_reverse", "smb", "smc", "bnc", "tnc", "n_type", "f_type",
    "fiber_lc", "fiber_sc", "fiber_st", "fiber_fc", "fiber_mtp_mpo",
    "m8_3pin", "m8_4pin", "m12_4pin", "m12_5pin", "m12_8pin", "m12_12pin",
    "molex_mini_fit", "molex_micro_fit", "jst_xh", "jst_ph",
    "amphenol_pt", "amphenol_ms", "winchester", "burndy",
    "power_anderson", "power_mil_c_22992",
    "terminal_block_2", "terminal_block_4", "terminal_block_8",
    "terminal_block_12", "terminal_block_16", "terminal_block_24",
    "backplane_vme", "backplane_cpci", "backplane_vpx", "backplane_vita_46",
    "samtec_searay", "samtec_tiger_eye", "harwin_m80", "harwin_gecko",
    "circular_plastic", "rectangular_sealed", "hermetic_feedthrough", "custom",
    name="connectortype", create_type=False,
)
connectorgender = postgresql.ENUM(
    "male_pin", "female_socket", "hermaphroditic", "genderless",
    name="connectorgender", create_type=False,
)
connectormounting = postgresql.ENUM(
    "panel_mount", "box_mount", "bulkhead", "cable_mount",
    "pcb_through_hole", "pcb_surface_mount", "rack_mount", "flange_mount",
    "jam_nut", "threaded_coupling", "bayonet", "push_pull", "free_hanging",
    "hermetic_seal", "custom",
    name="connectormounting", create_type=False,
)
shellmaterial = postgresql.ENUM(
    "aluminum", "stainless_steel", "composite", "nickel_alloy", "brass",
    "titanium", "plastic_nylon", "plastic_pbt", "zinc_diecast", "custom",
    name="shellmaterial", create_type=False,
)
shellfinish = postgresql.ENUM(
    "cadmium_olive_drab", "electroless_nickel", "black_zinc_nickel",
    "passivated_stainless", "anodized", "zinc_cobalt", "tin", "gold",
    "unfinished", "custom",
    name="shellfinish", create_type=False,
)
contactfinish = postgresql.ENUM(
    "gold", "silver", "tin", "nickel", "palladium", "rhodium",
    "solder", "crimp", "custom",
    name="contactfinish", create_type=False,
)
signaltype = postgresql.ENUM(
    "power_primary", "power_secondary", "power_return",
    "chassis_ground", "signal_ground",
    "signal_digital_single", "signal_digital_differential",
    "signal_analog_single", "signal_analog_differential",
    "clock_single", "clock_differential", "clock_reference",
    "rf_signal", "rf_lo", "rf_if",
    "discrete_input", "discrete_output", "discrete_bidirectional",
    "serial_data", "parallel_data", "pwm", "pulse",
    "thermocouple", "rtd", "strain_gauge", "lvdt",
    "fiber_optic_single", "fiber_optic_multi",
    "coax_signal", "spare", "no_connect",
    "shield_overall", "shield_individual", "shield_drain",
    "test_point", "key_pin", "alignment_pin", "reserved", "custom",
    name="signaltype", create_type=False,
)
pindirection = postgresql.ENUM(
    "input", "output", "bidirectional", "tri_state",
    "power_source", "power_sink", "power_return",
    "ground", "chassis_ground", "no_connect", "spare", "custom",
    name="pindirection", create_type=False,
)
pinsize = postgresql.ENUM(
    "size_22", "size_22d", "size_20", "size_16", "size_12", "size_8",
    "size_4", "size_0", "coax", "twinax", "fiber",
    "power_high_current", "custom",
    name="pinsize", create_type=False,
)
busprotocol = postgresql.ENUM(
    "mil_std_1553a", "mil_std_1553b", "mil_std_1773",
    "spacewire", "spacewire_rmap",
    "can_2a", "can_2b", "canfd", "canopen", "devicenet", "j1939",
    "rs232", "rs422", "rs422_differential", "rs485", "rs485_multipoint",
    "uart_ttl", "uart_cmos",
    "spi_mode0", "spi_mode1", "spi_mode2", "spi_mode3", "qspi",
    "i2c_standard", "i2c_fast", "i2c_fast_plus", "i2c_high_speed", "smbus",
    "ethernet_10base_t", "ethernet_100base_tx", "ethernet_100base_fx",
    "ethernet_1000base_t", "ethernet_1000base_sx",
    "ethernet_10gbase_t", "ethernet_10gbase_sr",
    "arinc_429", "arinc_629", "arinc_664_part7", "arinc_818",
    "usb_1_1", "usb_2_0", "usb_3_0",
    "mil_std_1760",
    "ccsds_aos", "ccsds_tm", "ccsds_tc", "ccsds_cfdp",
    "tte_ethernet", "profinet", "profibus_dp",
    "modbus_rtu", "modbus_tcp",
    "flexray", "lin",
    "serdes_lvds", "serdes_cml",
    "jesd204b", "jesd204c",
    "pci_express", "rapid_io",
    "fibre_channel",
    "jtag", "swd",
    "oneWire",
    "analog_0_5v", "analog_4_20ma", "analog_0_10v",
    "discrete_28v", "discrete_5v", "discrete_3v3",
    "discrete_open_collector", "discrete_relay_contact",
    "synchro", "resolver", "encoder_incremental", "encoder_absolute",
    "custom",
    name="busprotocol", create_type=False,
)
busrole = postgresql.ENUM(
    "bus_controller", "remote_terminal", "bus_monitor",
    "master", "slave", "multi_master",
    "publisher", "subscriber", "requester", "responder",
    "initiator", "target", "peer",
    "primary", "secondary", "arbiter", "custom",
    name="busrole", create_type=False,
)
bustopology = postgresql.ENUM(
    "bus_shared", "bus_stub", "point_to_point", "star", "ring",
    "dual_ring", "mesh", "partial_mesh", "tree", "daisy_chain",
    "multi_drop", "crossbar", "switched_fabric", "custom",
    name="bustopology", create_type=False,
)
busredundancy = postgresql.ENUM(
    "none", "dual_standby", "dual_active", "dual_hot_spare",
    "triple_modular_redundancy", "quad", "ring_protection", "custom",
    name="busredundancy", create_type=False,
)
pinbusrole = postgresql.ENUM(
    "data_positive", "data_negative", "data_single_ended",
    "clock_positive", "clock_negative", "clock_single_ended",
    "strobe_positive", "strobe_negative",
    "tx_positive", "tx_negative", "tx_single",
    "rx_positive", "rx_negative", "rx_single",
    "chip_select_active_low", "chip_select_active_high",
    "enable_active_low", "enable_active_high",
    "reset_active_low", "reset_active_high",
    "interrupt", "ready", "acknowledge", "request", "grant",
    "shield", "drain_wire", "bus_power", "bus_ground", "bus_bias",
    "spare", "custom",
    name="pinbusrole", create_type=False,
)
messagedirection = postgresql.ENUM(
    "transmit", "receive", "transmit_receive", "broadcast",
    "request", "response", "status",
    name="messagedirection", create_type=False,
)
messagepriority = postgresql.ENUM(
    "safety_critical", "mission_critical", "high", "medium", "low",
    "background", "diagnostic",
    name="messagepriority", create_type=False,
)
messagescheduling = postgresql.ENUM(
    "periodic_synchronous", "periodic_asynchronous",
    "aperiodic_event_driven", "aperiodic_command_response",
    "sporadic", "on_change", "one_shot", "startup_only",
    name="messagescheduling", create_type=False,
)
fielddatatype = postgresql.ENUM(
    "boolean", "uint8", "int8", "uint16", "int16", "uint32", "int32",
    "uint64", "int64", "float16", "float32", "float64",
    "enum_coded", "bitfield", "bitmask", "bcd_packed", "bcd_unpacked",
    "char_ascii", "char_utf8", "string_fixed", "string_variable",
    "timestamp_tai", "timestamp_utc", "timestamp_gps", "timestamp_unix",
    "angle_bam16", "angle_bam32",
    "raw_bytes", "reserved", "spare", "custom",
    name="fielddatatype", create_type=False,
)
byteorder = postgresql.ENUM(
    "big_endian", "little_endian", "pdp_endian", "native",
    name="byteorder", create_type=False,
)
wiretype = postgresql.ENUM(
    "signal_single", "signal_twisted_pair_a", "signal_twisted_pair_b",
    "signal_shielded_single", "signal_shielded_pair",
    "power_positive", "power_negative", "power_return",
    "ground_signal", "ground_chassis", "ground_power",
    "shield_overall_drain", "shield_individual_drain", "shield_braid",
    "coax_center", "coax_shield", "coax_drain",
    "triax_center", "triax_inner_shield", "triax_outer_shield",
    "twinax_a", "twinax_b", "twinax_shield",
    "fiber_tx", "fiber_rx", "spare", "jumper", "test", "custom",
    name="wiretype", create_type=False,
)
wiregauge = postgresql.ENUM(
    "awg_30", "awg_28", "awg_26", "awg_24", "awg_22", "awg_20",
    "awg_18", "awg_16", "awg_14", "awg_12", "awg_10", "awg_8",
    "awg_6", "awg_4", "awg_2", "awg_1", "awg_0", "awg_00",
    "awg_000", "awg_0000", "custom",
    name="wiregauge", create_type=False,
)
harnessstatus = postgresql.ENUM(
    "concept", "preliminary_design", "detailed_design", "drawing_released",
    "fabrication", "inspection", "acceptance_test", "installed",
    "rework", "field_modification", "retired",
    name="harnessstatus", create_type=False,
)
cablejacketmaterial = postgresql.ENUM(
    "ptfe_teflon", "fep", "etfe_tefzel", "pfa", "pvdf_kynar",
    "polyimide_kapton", "silicone_rubber", "epr",
    "pvc", "xlpe", "polyethylene", "polypropylene",
    "neoprene", "hypalon", "thermoplastic_elastomer",
    "nomex", "fiberglass", "stainless_steel_braid", "composite", "custom",
    name="cablejacketmaterial", create_type=False,
)
shieldtype = postgresql.ENUM(
    "none", "overall_braid", "overall_foil", "overall_spiral",
    "overall_braid_plus_foil", "overall_conduit",
    "individual_pair_braid", "individual_pair_foil",
    "individual_pair_braid_plus_foil",
    "combination_individual_plus_overall",
    "conductive_polymer", "custom",
    name="shieldtype", create_type=False,
)
interfacetype = postgresql.ENUM(
    "electrical_power", "electrical_signal", "electrical_combined",
    "data_digital", "data_analog", "data_mixed",
    "rf_transmit", "rf_receive", "rf_duplex",
    "optical_fiber", "optical_free_space",
    "mechanical_structural", "mechanical_thermal",
    "fluid_pneumatic", "fluid_hydraulic", "fluid_coolant",
    "thermal_conductive", "thermal_radiative",
    "electromagnetic", "acoustic", "custom",
    name="interfacetype", create_type=False,
)
interfacedirection = postgresql.ENUM(
    "source_to_target", "target_to_source", "bidirectional", "broadcast",
    name="interfacedirection", create_type=False,
)
interfacestatus = postgresql.ENUM(
    "proposed", "defined", "preliminary", "under_review", "agreed",
    "baselined", "implemented", "integration_tested", "verified",
    "validated", "waived", "custom",
    name="interfacestatus", create_type=False,
)
interfacecriticality = postgresql.ENUM(
    "catastrophic", "hazardous", "major", "minor", "no_effect",
    "safety_critical_a", "safety_critical_b", "safety_critical_c",
    "mission_critical", "mission_essential", "mission_support", "non_critical",
    name="interfacecriticality", create_type=False,
)
environmentalcategory = postgresql.ENUM(
    "temperature_operating", "temperature_storage", "temperature_survival",
    "humidity", "altitude", "pressure", "vacuum",
    "vibration_random", "vibration_sinusoidal", "vibration_combined",
    "shock_mechanical", "shock_pyrotechnic", "shock_ballistic",
    "acceleration_sustained", "acceleration_transient",
    "acoustic_noise", "sand_dust", "salt_fog", "rain", "icing",
    "fungus", "explosive_atmosphere", "solar_radiation",
    "thermal_cycling", "thermal_shock",
    "radiation_total_dose", "radiation_single_event", "radiation_displacement",
    "emi_ce101", "emi_ce102", "emi_ce106",
    "emi_cs101", "emi_cs103", "emi_cs104", "emi_cs105", "emi_cs106", "emi_cs109",
    "emi_cs114", "emi_cs115", "emi_cs116",
    "emi_re101", "emi_re102", "emi_re103",
    "emi_rs101", "emi_rs103", "emi_rs105",
    "esd_hbm", "esd_cdm", "esd_mm",
    "lightning_direct", "lightning_indirect",
    "emp_hemp", "emp_sremp",
    "magnetic_field_dc", "magnetic_field_ac", "custom",
    name="environmentalcategory", create_type=False,
)
environmentalstandard = postgresql.ENUM(
    "mil_std_810h", "mil_std_810g",
    "mil_std_461g", "mil_std_461f",
    "mil_std_464c", "mil_hdbk_217f",
    "do_160g", "do_160f",
    "iso_16750", "iso_11452", "iso_7637",
    "iec_61000_series", "iec_60068",
    "nasa_std_4003a", "nasa_std_4005a",
    "ecss_e_st_10_03c", "ecss_e_st_20c",
    "jssg_2009", "jssg_2010", "custom",
    name="environmentalstandard", create_type=False,
)
interfaceentitytype = postgresql.ENUM(
    "system", "unit", "connector", "pin", "pin_bus_assignment",
    "bus_definition", "message_definition", "message_field",
    "wire_harness", "wire", "cable_assembly", "interface", "interface_document",
    name="interfaceentitytype", create_type=False,
)
interfacelinktype = postgresql.ENUM(
    "satisfies", "partially_satisfies", "verifies", "validates",
    "derives_from", "decomposes", "refines", "elaborates",
    "constrains", "enables", "conflicts_with",
    "implements", "allocated_to", "realized_by",
    "tested_by", "analyzed_by", "inspected_by", "demonstrated_by",
    "traces_to", "references", "custom",
    name="interfacelinktype", create_type=False,
)
autoreqsource = postgresql.ENUM(
    "wire_connection", "bus_connection", "message_definition",
    "message_field", "power_wire", "ground_wire", "discrete_signal",
    "rf_connection", "shield_grounding", "harness_overall",
    "environmental_spec", "emi_spec", "unit_import", "manual",
    name="autoreqsource", create_type=False,
)
autoreqstatus = postgresql.ENUM(
    "pending_review", "approved", "rejected", "superseded", "merged", "deferred",
    name="autoreqstatus", create_type=False,
)

_ALL_ENUMS = [
    systemtype, systemstatus, unittype, unitstatus,
    connectortype, connectorgender, connectormounting,
    shellmaterial, shellfinish, contactfinish,
    signaltype, pindirection, pinsize,
    busprotocol, busrole, bustopology, busredundancy, pinbusrole,
    messagedirection, messagepriority, messagescheduling,
    fielddatatype, byteorder,
    wiretype, wiregauge, harnessstatus, cablejacketmaterial, shieldtype,
    interfacetype, interfacedirection, interfacestatus, interfacecriticality,
    environmentalcategory, environmentalstandard,
    interfaceentitytype, interfacelinktype, autoreqsource, autoreqstatus,
]


def upgrade() -> None:
    # ── Create all 38 enum types ──
    for e in _ALL_ENUMS:
        e.create(op.get_bind(), checkfirst=True)

    # ══════════════════════════════════════
    #  1. systems
    # ══════════════════════════════════════

    op.create_table(
        "systems",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("system_id", sa.String(30), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("abbreviation", sa.String(30), nullable=True),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("system_type", systemtype, nullable=False),
        sa.Column("system_type_custom", sa.String(100), nullable=True),
        sa.Column("status", systemstatus, server_default="concept"),
        sa.Column("parent_system_id", sa.Integer(), sa.ForeignKey("systems.id"), nullable=True),
        sa.Column("wbs_number", sa.String(30), nullable=True),
        sa.Column("responsible_org", sa.String(255), nullable=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_systems_system_id", "systems", ["system_id"])
    op.create_index("ix_system_project_type", "systems", ["project_id", "system_type"])
    op.create_index("ix_system_parent", "systems", ["parent_system_id"])

    # ══════════════════════════════════════
    #  2. units
    # ══════════════════════════════════════

    op.create_table(
        "units",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("unit_id", sa.String(30), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("designation", sa.String(50), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("part_number", sa.String(100), nullable=False),
        sa.Column("manufacturer", sa.String(255), nullable=False),
        sa.Column("cage_code", sa.String(10), nullable=True),
        sa.Column("nsn", sa.String(20), nullable=True),
        sa.Column("drawing_number", sa.String(50), nullable=True),
        sa.Column("revision", sa.String(20), nullable=True),
        sa.Column("serial_number_prefix", sa.String(30), nullable=True),
        sa.Column("unit_type", unittype, nullable=False),
        sa.Column("unit_type_custom", sa.String(100), nullable=True),
        sa.Column("status", unitstatus, server_default="concept"),
        sa.Column("heritage", sa.String(255), nullable=True),
        # Physical
        sa.Column("mass_kg", sa.Float(), nullable=True),
        sa.Column("mass_max_kg", sa.Float(), nullable=True),
        sa.Column("dimensions_l_mm", sa.Float(), nullable=True),
        sa.Column("dimensions_w_mm", sa.Float(), nullable=True),
        sa.Column("dimensions_h_mm", sa.Float(), nullable=True),
        sa.Column("volume_cc", sa.Float(), nullable=True),
        # Electrical
        sa.Column("power_watts_nominal", sa.Float(), nullable=True),
        sa.Column("power_watts_peak", sa.Float(), nullable=True),
        sa.Column("power_watts_standby", sa.Float(), nullable=True),
        sa.Column("voltage_input_nominal", sa.String(30), nullable=True),
        sa.Column("voltage_input_min", sa.Float(), nullable=True),
        sa.Column("voltage_input_max", sa.Float(), nullable=True),
        sa.Column("voltage_ripple_max_mvpp", sa.Float(), nullable=True),
        sa.Column("current_inrush_amps", sa.Float(), nullable=True),
        sa.Column("current_steady_state_amps", sa.Float(), nullable=True),
        # Thermal
        sa.Column("temp_operating_min_c", sa.Float(), nullable=True),
        sa.Column("temp_operating_max_c", sa.Float(), nullable=True),
        sa.Column("temp_storage_min_c", sa.Float(), nullable=True),
        sa.Column("temp_storage_max_c", sa.Float(), nullable=True),
        sa.Column("temp_survival_min_c", sa.Float(), nullable=True),
        sa.Column("temp_survival_max_c", sa.Float(), nullable=True),
        # Mechanical
        sa.Column("vibration_random_grms", sa.Float(), nullable=True),
        sa.Column("vibration_sine_g_peak", sa.Float(), nullable=True),
        sa.Column("shock_mechanical_g", sa.Float(), nullable=True),
        sa.Column("shock_mechanical_duration_ms", sa.Float(), nullable=True),
        sa.Column("shock_pyrotechnic_g", sa.Float(), nullable=True),
        sa.Column("acceleration_max_g", sa.Float(), nullable=True),
        sa.Column("acoustic_spl_db", sa.Float(), nullable=True),
        # Climate
        sa.Column("humidity_min_pct", sa.Float(), nullable=True),
        sa.Column("humidity_max_pct", sa.Float(), nullable=True),
        sa.Column("altitude_operating_max_m", sa.Float(), nullable=True),
        sa.Column("altitude_storage_max_m", sa.Float(), nullable=True),
        sa.Column("pressure_min_kpa", sa.Float(), nullable=True),
        sa.Column("pressure_max_kpa", sa.Float(), nullable=True),
        sa.Column("sand_dust_exposed", sa.Boolean(), server_default="false"),
        sa.Column("salt_fog_exposed", sa.Boolean(), server_default="false"),
        sa.Column("fungus_resistant", sa.Boolean(), server_default="false"),
        # EMI/EMC
        sa.Column("emi_ce101_limit_dba", sa.Float(), nullable=True),
        sa.Column("emi_ce102_limit_dbua", sa.Float(), nullable=True),
        sa.Column("emi_cs101_limit_db", sa.Float(), nullable=True),
        sa.Column("emi_cs114_limit_dba", sa.Float(), nullable=True),
        sa.Column("emi_cs115_limit_v", sa.Float(), nullable=True),
        sa.Column("emi_cs116_limit_db", sa.Float(), nullable=True),
        sa.Column("emi_re101_limit_dba", sa.Float(), nullable=True),
        sa.Column("emi_re102_limit_dbm", sa.Float(), nullable=True),
        sa.Column("emi_rs101_limit_db", sa.Float(), nullable=True),
        sa.Column("emi_rs103_limit_vm", sa.Float(), nullable=True),
        sa.Column("esd_hbm_v", sa.Float(), nullable=True),
        sa.Column("esd_cdm_v", sa.Float(), nullable=True),
        # Radiation
        sa.Column("radiation_tid_krad", sa.Float(), nullable=True),
        sa.Column("radiation_see_let_threshold", sa.Float(), nullable=True),
        sa.Column("radiation_dd_mev_cm2_g", sa.Float(), nullable=True),
        # Reliability
        sa.Column("mtbf_hours", sa.Float(), nullable=True),
        sa.Column("mtbf_environment", sa.String(30), nullable=True),
        sa.Column("design_life_years", sa.Float(), nullable=True),
        sa.Column("duty_cycle_pct", sa.Float(), nullable=True),
        sa.Column("derating_standard", sa.String(50), nullable=True),
        # References
        sa.Column("datasheet_url", sa.String(500), nullable=True),
        sa.Column("specification_doc", sa.String(255), nullable=True),
        sa.Column("test_report_doc", sa.String(255), nullable=True),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("metadata_json", JSON, server_default="{}"),
        # FKs
        sa.Column("system_id", sa.Integer(), sa.ForeignKey("systems.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_units_unit_id", "units", ["unit_id"])
    op.create_index("ix_unit_system", "units", ["system_id"])
    op.create_index("ix_unit_mfg", "units", ["manufacturer"])
    op.create_unique_constraint("uq_unit_designation", "units", ["project_id", "designation"])

    # ══════════════════════════════════════
    #  3. connectors
    # ══════════════════════════════════════

    op.create_table(
        "connectors",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("connector_id", sa.String(30), nullable=True),
        sa.Column("designator", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("connector_type", connectortype, nullable=False),
        sa.Column("connector_type_custom", sa.String(100), nullable=True),
        sa.Column("gender", connectorgender, nullable=False),
        sa.Column("mounting", connectormounting, nullable=True),
        sa.Column("mounting_custom", sa.String(100), nullable=True),
        sa.Column("shell_size", sa.String(20), nullable=True),
        sa.Column("insert_arrangement", sa.String(30), nullable=True),
        sa.Column("total_contacts", sa.Integer(), nullable=False),
        sa.Column("signal_contacts", sa.Integer(), nullable=True),
        sa.Column("power_contacts", sa.Integer(), nullable=True),
        sa.Column("coax_contacts", sa.Integer(), nullable=True),
        sa.Column("fiber_contacts", sa.Integer(), nullable=True),
        sa.Column("spare_contacts", sa.Integer(), nullable=True),
        sa.Column("keying", sa.String(50), nullable=True),
        sa.Column("polarization", sa.String(30), nullable=True),
        sa.Column("coupling", sa.String(30), nullable=True),
        sa.Column("ip_rating", sa.String(10), nullable=True),
        sa.Column("operating_temp_min_c", sa.Float(), nullable=True),
        sa.Column("operating_temp_max_c", sa.Float(), nullable=True),
        sa.Column("mating_cycles", sa.Integer(), nullable=True),
        sa.Column("shell_material", shellmaterial, nullable=True),
        sa.Column("shell_finish", shellfinish, nullable=True),
        sa.Column("contact_finish", contactfinish, nullable=True),
        sa.Column("mil_spec", sa.String(80), nullable=True),
        sa.Column("manufacturer_part_number", sa.String(100), nullable=True),
        sa.Column("connector_manufacturer", sa.String(255), nullable=True),
        sa.Column("backshell_type", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_connector_designator", "connectors", ["unit_id", "designator"])

    # ══════════════════════════════════════
    #  4. pins
    # ══════════════════════════════════════

    op.create_table(
        "pins",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pin_number", sa.String(10), nullable=False),
        sa.Column("pin_label", sa.String(30), nullable=True),
        sa.Column("signal_name", sa.String(150), nullable=False),
        sa.Column("signal_type", signaltype, nullable=False),
        sa.Column("signal_type_custom", sa.String(100), nullable=True),
        sa.Column("direction", pindirection, nullable=False),
        sa.Column("pin_size", pinsize, nullable=True),
        sa.Column("contact_type", sa.String(30), nullable=True),
        sa.Column("voltage_nominal", sa.String(30), nullable=True),
        sa.Column("voltage_min", sa.Float(), nullable=True),
        sa.Column("voltage_max", sa.Float(), nullable=True),
        sa.Column("voltage_dc_bias", sa.Float(), nullable=True),
        sa.Column("current_nominal_amps", sa.Float(), nullable=True),
        sa.Column("current_max_amps", sa.Float(), nullable=True),
        sa.Column("impedance_ohms", sa.Float(), nullable=True),
        sa.Column("frequency_mhz", sa.Float(), nullable=True),
        sa.Column("rise_time_ns", sa.Float(), nullable=True),
        sa.Column("termination", sa.String(50), nullable=True),
        sa.Column("pull_up_down", sa.String(30), nullable=True),
        sa.Column("esd_protection", sa.String(50), nullable=True),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("connector_id", sa.Integer(), sa.ForeignKey("connectors.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_pin_number", "pins", ["connector_id", "pin_number"])
    op.create_index("ix_pin_signal_name", "pins", ["signal_name"])

    # ══════════════════════════════════════
    #  5. bus_definitions
    # ══════════════════════════════════════

    op.create_table(
        "bus_definitions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("bus_def_id", sa.String(30), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("protocol", busprotocol, nullable=False),
        sa.Column("protocol_custom", sa.String(100), nullable=True),
        sa.Column("protocol_version", sa.String(20), nullable=True),
        sa.Column("bus_role", busrole, nullable=False),
        sa.Column("bus_role_custom", sa.String(100), nullable=True),
        sa.Column("bus_address", sa.String(30), nullable=True),
        sa.Column("bus_address_secondary", sa.String(30), nullable=True),
        sa.Column("bus_name_network", sa.String(100), nullable=True),
        sa.Column("data_rate", sa.String(30), nullable=True),
        sa.Column("data_rate_actual_bps", sa.Integer(), nullable=True),
        sa.Column("word_size_bits", sa.Integer(), nullable=True),
        sa.Column("frame_size_max_bytes", sa.Integer(), nullable=True),
        sa.Column("topology", bustopology, nullable=True),
        sa.Column("redundancy", busredundancy, server_default="none"),
        sa.Column("deterministic", sa.Boolean(), nullable=True),
        sa.Column("fault_tolerance", sa.String(100), nullable=True),
        sa.Column("bus_loading_max_pct", sa.Float(), nullable=True),
        sa.Column("latency_budget_ms", sa.Float(), nullable=True),
        sa.Column("jitter_max_us", sa.Float(), nullable=True),
        sa.Column("error_rate_max", sa.String(30), nullable=True),
        sa.Column("encoding", sa.String(50), nullable=True),
        sa.Column("electrical_standard", sa.String(50), nullable=True),
        sa.Column("coupling", sa.String(50), nullable=True),
        sa.Column("stub_length_max_m", sa.Float(), nullable=True),
        sa.Column("bus_length_max_m", sa.Float(), nullable=True),
        sa.Column("termination_required", sa.String(50), nullable=True),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("metadata_json", JSON, server_default="{}"),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ══════════════════════════════════════
    #  6. pin_bus_assignments
    # ══════════════════════════════════════

    op.create_table(
        "pin_bus_assignments",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("pin_id", sa.Integer(), sa.ForeignKey("pins.id"), nullable=False),
        sa.Column("bus_def_id", sa.Integer(), sa.ForeignKey("bus_definitions.id"), nullable=False),
        sa.Column("pin_role", pinbusrole, nullable=False),
        sa.Column("pin_role_custom", sa.String(100), nullable=True),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_pin_bus_assignment", "pin_bus_assignments", ["pin_id", "bus_def_id"])

    # ══════════════════════════════════════
    #  7. message_definitions
    # ══════════════════════════════════════

    op.create_table(
        "message_definitions",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("msg_def_id", sa.String(30), nullable=True),
        sa.Column("label", sa.String(100), nullable=False),
        sa.Column("mnemonic", sa.String(30), nullable=True),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("protocol_message_id", sa.String(30), nullable=True),
        sa.Column("message_id_hex", sa.String(20), nullable=True),
        sa.Column("subaddress", sa.Integer(), nullable=True),
        sa.Column("word_count", sa.Integer(), nullable=True),
        sa.Column("byte_count", sa.Integer(), nullable=True),
        sa.Column("direction", messagedirection, nullable=False),
        sa.Column("scheduling", messagescheduling, server_default="periodic_synchronous"),
        sa.Column("rate_hz", sa.Float(), nullable=True),
        sa.Column("rate_min_hz", sa.Float(), nullable=True),
        sa.Column("rate_max_hz", sa.Float(), nullable=True),
        sa.Column("latency_max_ms", sa.Float(), nullable=True),
        sa.Column("latency_typical_ms", sa.Float(), nullable=True),
        sa.Column("priority", messagepriority, server_default="medium"),
        sa.Column("is_periodic", sa.Boolean(), server_default="true"),
        sa.Column("timeout_ms", sa.Float(), nullable=True),
        sa.Column("integrity_mechanism", sa.String(50), nullable=True),
        sa.Column("fragmentation", sa.Boolean(), server_default="false"),
        sa.Column("encryption", sa.String(50), nullable=True),
        sa.Column("authentication", sa.String(50), nullable=True),
        sa.Column("source_system_name", sa.String(100), nullable=True),
        sa.Column("target_system_name", sa.String(100), nullable=True),
        sa.Column("icd_reference", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("metadata_json", JSON, server_default="{}"),
        sa.Column("bus_def_id", sa.Integer(), sa.ForeignKey("bus_definitions.id"), nullable=False),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ══════════════════════════════════════
    #  8. message_fields
    # ══════════════════════════════════════

    op.create_table(
        "message_fields",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("field_name", sa.String(100), nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("data_type", fielddatatype, nullable=False),
        sa.Column("data_type_custom", sa.String(100), nullable=True),
        sa.Column("byte_order", byteorder, server_default="big_endian"),
        sa.Column("word_number", sa.Integer(), nullable=True),
        sa.Column("byte_offset", sa.Integer(), nullable=True),
        sa.Column("bit_offset", sa.Integer(), nullable=True),
        sa.Column("bit_length", sa.Integer(), nullable=False),
        sa.Column("unit_of_measure", sa.String(50), nullable=True),
        sa.Column("scale_factor", sa.Float(), server_default="1.0"),
        sa.Column("offset_value", sa.Float(), server_default="0.0"),
        sa.Column("lsb_value", sa.Float(), nullable=True),
        sa.Column("min_value", sa.Float(), nullable=True),
        sa.Column("max_value", sa.Float(), nullable=True),
        sa.Column("resolution", sa.Float(), nullable=True),
        sa.Column("accuracy", sa.Float(), nullable=True),
        sa.Column("default_value", sa.String(50), nullable=True),
        sa.Column("initial_value", sa.String(50), nullable=True),
        sa.Column("invalid_value", sa.String(50), nullable=True),
        sa.Column("stale_timeout_ms", sa.Float(), nullable=True),
        sa.Column("enum_values", JSON, nullable=True),
        sa.Column("bit_mask", sa.String(20), nullable=True),
        sa.Column("field_order", sa.Integer(), nullable=True),
        sa.Column("is_padding", sa.Boolean(), server_default="false"),
        sa.Column("is_spare", sa.Boolean(), server_default="false"),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("message_definitions.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ══════════════════════════════════════
    #  9. wire_harnesses
    # ══════════════════════════════════════

    op.create_table(
        "wire_harnesses",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("harness_id", sa.String(30), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("cable_type", sa.String(100), nullable=True),
        sa.Column("cable_spec", sa.String(100), nullable=True),
        sa.Column("cable_part_number", sa.String(100), nullable=True),
        sa.Column("cable_manufacturer", sa.String(255), nullable=True),
        sa.Column("overall_length_m", sa.Float(), nullable=True),
        sa.Column("overall_length_max_m", sa.Float(), nullable=True),
        sa.Column("mass_kg", sa.Float(), nullable=True),
        sa.Column("outer_diameter_mm", sa.Float(), nullable=True),
        sa.Column("jacket_material", cablejacketmaterial, nullable=True),
        sa.Column("jacket_material_custom", sa.String(100), nullable=True),
        sa.Column("jacket_color", sa.String(30), nullable=True),
        sa.Column("temp_rating_min_c", sa.Float(), nullable=True),
        sa.Column("temp_rating_max_c", sa.Float(), nullable=True),
        sa.Column("voltage_rating_v", sa.Float(), nullable=True),
        sa.Column("bend_radius_min_mm", sa.Float(), nullable=True),
        sa.Column("shield_type", shieldtype, nullable=True),
        sa.Column("shield_coverage_pct", sa.Float(), nullable=True),
        sa.Column("shield_material", sa.String(50), nullable=True),
        sa.Column("overall_shield_termination", sa.String(100), nullable=True),
        sa.Column("conductor_count", sa.Integer(), nullable=True),
        sa.Column("pair_count", sa.Integer(), nullable=True),
        sa.Column("status", harnessstatus, server_default="concept"),
        sa.Column("drawing_number", sa.String(50), nullable=True),
        sa.Column("drawing_revision", sa.String(10), nullable=True),
        sa.Column("approved_by", sa.String(100), nullable=True),
        sa.Column("approval_date", sa.DateTime(), nullable=True),
        sa.Column("from_unit_id", sa.Integer(), sa.ForeignKey("units.id"), nullable=False),
        sa.Column("from_connector_id", sa.Integer(), sa.ForeignKey("connectors.id"), nullable=False),
        sa.Column("to_unit_id", sa.Integer(), sa.ForeignKey("units.id"), nullable=False),
        sa.Column("to_connector_id", sa.Integer(), sa.ForeignKey("connectors.id"), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_harness_connectors", "wire_harnesses", ["from_connector_id", "to_connector_id"])

    # ══════════════════════════════════════
    #  10. wires
    # ══════════════════════════════════════

    op.create_table(
        "wires",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("wire_number", sa.String(20), nullable=False),
        sa.Column("signal_name", sa.String(150), nullable=False),
        sa.Column("wire_gauge", wiregauge, nullable=True),
        sa.Column("wire_gauge_custom", sa.String(10), nullable=True),
        sa.Column("wire_color_primary", sa.String(30), nullable=True),
        sa.Column("wire_color_secondary", sa.String(30), nullable=True),
        sa.Column("wire_color_tertiary", sa.String(30), nullable=True),
        sa.Column("wire_type", wiretype, nullable=False),
        sa.Column("wire_type_custom", sa.String(100), nullable=True),
        sa.Column("wire_spec", sa.String(80), nullable=True),
        sa.Column("wire_material", sa.String(50), nullable=True),
        sa.Column("insulation_material", sa.String(50), nullable=True),
        sa.Column("insulation_color", sa.String(30), nullable=True),
        sa.Column("length_m", sa.Float(), nullable=True),
        sa.Column("length_max_m", sa.Float(), nullable=True),
        sa.Column("from_pin_id", sa.Integer(), sa.ForeignKey("pins.id"), nullable=False),
        sa.Column("to_pin_id", sa.Integer(), sa.ForeignKey("pins.id"), nullable=False),
        sa.Column("harness_id", sa.Integer(), sa.ForeignKey("wire_harnesses.id"), nullable=False),
        sa.Column("splice_info", sa.String(100), nullable=True),
        sa.Column("termination_from", sa.String(50), nullable=True),
        sa.Column("termination_to", sa.String(50), nullable=True),
        sa.Column("heat_shrink", sa.Boolean(), server_default="false"),
        sa.Column("heat_shrink_size", sa.String(20), nullable=True),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_unique_constraint("uq_wire_number", "wires", ["harness_id", "wire_number"])
    op.create_index("ix_wire_from_pin", "wires", ["from_pin_id"])
    op.create_index("ix_wire_to_pin", "wires", ["to_pin_id"])
    op.create_index("ix_wire_signal_name", "wires", ["signal_name"])

    # ══════════════════════════════════════
    #  11. interfaces
    # ══════════════════════════════════════

    op.create_table(
        "interfaces",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("interface_id", sa.String(30), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("interface_type", interfacetype, nullable=False),
        sa.Column("interface_type_custom", sa.String(100), nullable=True),
        sa.Column("direction", interfacedirection, nullable=False),
        sa.Column("source_system_id", sa.Integer(), sa.ForeignKey("systems.id"), nullable=False),
        sa.Column("target_system_id", sa.Integer(), sa.ForeignKey("systems.id"), nullable=False),
        sa.Column("status", interfacestatus, server_default="proposed"),
        sa.Column("criticality", interfacecriticality, server_default="non_critical"),
        sa.Column("icd_document_number", sa.String(100), nullable=True),
        sa.Column("icd_document_revision", sa.String(20), nullable=True),
        sa.Column("icd_section", sa.String(50), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column("data_rate_aggregate", sa.String(30), nullable=True),
        sa.Column("latency_requirement_ms", sa.Float(), nullable=True),
        sa.Column("availability_requirement_pct", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("metadata_json", JSON, server_default="{}"),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("owner_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now()),
    )

    # ══════════════════════════════════════
    #  12. unit_environmental_specs
    # ══════════════════════════════════════

    op.create_table(
        "unit_environmental_specs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("unit_id", sa.Integer(), sa.ForeignKey("units.id"), nullable=False),
        sa.Column("category", environmentalcategory, nullable=False),
        sa.Column("standard", environmentalstandard, nullable=True),
        sa.Column("standard_custom", sa.String(100), nullable=True),
        sa.Column("test_method", sa.String(100), nullable=True),
        sa.Column("test_level", sa.String(100), nullable=True),
        sa.Column("limit_value", sa.Float(), nullable=True),
        sa.Column("limit_unit", sa.String(30), nullable=True),
        sa.Column("limit_min", sa.Float(), nullable=True),
        sa.Column("limit_max", sa.Float(), nullable=True),
        sa.Column("frequency_range", sa.String(50), nullable=True),
        sa.Column("duration", sa.String(50), nullable=True),
        sa.Column("test_condition", sa.Text(), nullable=True),
        sa.Column("compliance_status", sa.String(20), server_default="untested"),
        sa.Column("test_report_ref", sa.String(100), nullable=True),
        sa.Column("notes", sa.Text(), server_default=""),
        sa.Column("auto_generated", sa.Boolean(), server_default="false"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_env_spec_unit_cat", "unit_environmental_specs", ["unit_id", "category"])

    # ══════════════════════════════════════
    #  13. interface_requirement_links
    # ══════════════════════════════════════

    op.create_table(
        "interface_requirement_links",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("entity_type", interfaceentitytype, nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column("requirement_id", sa.Integer(), sa.ForeignKey("requirements.id"), nullable=False),
        sa.Column("link_type", interfacelinktype, nullable=False),
        sa.Column("link_type_custom", sa.String(100), nullable=True),
        sa.Column("description", sa.Text(), server_default=""),
        sa.Column("auto_generated", sa.Boolean(), server_default="false"),
        sa.Column("auto_req_source", autoreqsource, nullable=True),
        sa.Column("auto_req_template", sa.String(50), nullable=True),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("status", autoreqstatus, server_default="pending_review"),
        sa.Column("reviewed_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_ifl_entity", "interface_requirement_links", ["entity_type", "entity_id"])
    op.create_index("ix_ifl_requirement", "interface_requirement_links", ["requirement_id"])
    op.create_index("ix_ifl_auto_status", "interface_requirement_links", ["auto_generated", "status"])

    # ══════════════════════════════════════
    #  14. auto_requirement_logs
    # ══════════════════════════════════════

    op.create_table(
        "auto_requirement_logs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("trigger_entity_type", sa.String(30), nullable=True),
        sa.Column("trigger_entity_id", sa.Integer(), nullable=True),
        sa.Column("trigger_action", sa.String(20), nullable=True),
        sa.Column("requirements_generated", sa.Integer(), nullable=True),
        sa.Column("verifications_generated", sa.Integer(), nullable=True),
        sa.Column("links_generated", sa.Integer(), nullable=True),
        sa.Column("template_used", sa.String(50), nullable=True),
        sa.Column("generation_summary", JSON, nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_autoreq_project_date", "auto_requirement_logs", ["project_id", "created_at"])

    # ══════════════════════════════════════
    #  15. interface_change_impacts
    # ══════════════════════════════════════

    op.create_table(
        "interface_change_impacts",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("change_type", sa.String(30), nullable=True),
        sa.Column("entity_type", sa.String(30), nullable=True),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("entity_description", sa.String(255), nullable=True),
        sa.Column("affected_requirements", JSON, nullable=True),
        sa.Column("affected_verifications", JSON, nullable=True),
        sa.Column("risk_level", sa.String(20), nullable=True),
        sa.Column("total_affected", sa.Integer(), nullable=True),
        sa.Column("user_action", sa.String(30), nullable=True),
        sa.Column("resolved", sa.Boolean(), server_default="false"),
        sa.Column("resolved_at", sa.DateTime(), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_index("ix_ici_project_date", "interface_change_impacts", ["project_id", "created_at"])
    op.create_index("ix_ici_resolved", "interface_change_impacts", ["resolved"])


def downgrade() -> None:
    # ── Drop tables in reverse dependency order ──
    op.drop_table("interface_change_impacts")
    op.drop_table("auto_requirement_logs")
    op.drop_table("interface_requirement_links")
    op.drop_table("unit_environmental_specs")
    op.drop_table("interfaces")
    op.drop_table("wires")
    op.drop_table("wire_harnesses")
    op.drop_table("message_fields")
    op.drop_table("message_definitions")
    op.drop_table("pin_bus_assignments")
    op.drop_table("bus_definitions")
    op.drop_table("pins")
    op.drop_table("connectors")
    op.drop_table("units")
    op.drop_table("systems")

    # ── Drop all 38 enum types ──
    for name in [
        "autoreqstatus", "autoreqsource",
        "interfacelinktype", "interfaceentitytype",
        "environmentalstandard", "environmentalcategory",
        "interfacecriticality", "interfacestatus", "interfacedirection", "interfacetype",
        "shieldtype", "cablejacketmaterial", "harnessstatus",
        "wiregauge", "wiretype",
        "byteorder", "fielddatatype",
        "messagescheduling", "messagepriority", "messagedirection",
        "pinbusrole", "busredundancy", "bustopology", "busrole", "busprotocol",
        "pinsize", "pindirection", "signaltype",
        "contactfinish", "shellfinish", "shellmaterial",
        "connectormounting", "connectorgender", "connectortype",
        "unitstatus", "unittype", "systemstatus", "systemtype",
    ]:
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
