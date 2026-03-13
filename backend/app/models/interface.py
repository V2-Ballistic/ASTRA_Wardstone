"""
ASTRA — Interface Control Document (ICD) Management Models
=============================================================
File: backend/app/models/interface.py   ← NEW

Domain references:
  NASA-HDBK-2361, MIL-STD-1521B, INCOSE SE Handbook Ch.8,
  MIL-STD-461G (EMI/EMC), MIL-STD-810H (Environmental)

38 enums, 15 SQLAlchemy models covering:
  Systems, Units, Connectors, Pins, Bus Definitions,
  Pin-Bus Assignments, Messages, Message Fields,
  Wire Harnesses, Wires, Interfaces,
  Unit Environmental Specs, Interface-Requirement Links,
  Auto-Requirement Logs, Interface Change Impact
"""

import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, Float,
    ForeignKey, Enum as SQLEnum, JSON, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship, backref
from app.database import Base


# ══════════════════════════════════════════════════════════════
#  Enums (38)
# ══════════════════════════════════════════════════════════════

# ── 1. SystemType ──

class SystemType(str, enum.Enum):
    SUBSYSTEM = "subsystem"
    LRU = "lru"
    WRU = "wru"
    SRU = "sru"
    SENSOR_SUITE = "sensor_suite"
    ACTUATOR_ASSEMBLY = "actuator_assembly"
    PROCESSOR_UNIT = "processor_unit"
    POWER_SYSTEM = "power_system"
    THERMAL_SYSTEM = "thermal_system"
    STRUCTURAL = "structural"
    GROUND_SEGMENT = "ground_segment"
    VEHICLE = "vehicle"
    PAYLOAD = "payload"
    ANTENNA_SYSTEM = "antenna_system"
    PROPULSION = "propulsion"
    GUIDANCE_NAV_CONTROL = "guidance_nav_control"
    COMMUNICATION = "communication"
    DATA_HANDLING = "data_handling"
    ORDNANCE = "ordnance"
    TEST_EQUIPMENT = "test_equipment"
    EXTERNAL_SYSTEM = "external_system"
    SOFTWARE = "software"
    FIRMWARE = "firmware"
    CUSTOM = "custom"


# ── 2. SystemStatus ──

class SystemStatus(str, enum.Enum):
    CONCEPT = "concept"
    PRELIMINARY_DESIGN = "preliminary_design"
    DETAILED_DESIGN = "detailed_design"
    FABRICATION = "fabrication"
    INTEGRATION = "integration"
    QUALIFICATION_TEST = "qualification_test"
    ACCEPTANCE_TEST = "acceptance_test"
    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    RETIRED = "retired"
    OBSOLETE = "obsolete"


# ── 3. UnitType ──

class UnitType(str, enum.Enum):
    LRU = "lru"
    WRU = "wru"
    SRU = "sru"
    CCA = "cca"
    PCB = "pcb"
    BACKPLANE = "backplane"
    CHASSIS = "chassis"
    SENSOR = "sensor"
    ACTUATOR = "actuator"
    MOTOR = "motor"
    PROCESSOR = "processor"
    FPGA = "fpga"
    ASIC = "asic"
    POWER_SUPPLY = "power_supply"
    POWER_CONVERTER = "power_converter"
    BATTERY = "battery"
    SOLAR_PANEL = "solar_panel"
    TRANSMITTER = "transmitter"
    RECEIVER = "receiver"
    TRANSCEIVER = "transceiver"
    ANTENNA = "antenna"
    WAVEGUIDE = "waveguide"
    FILTER_RF = "filter_rf"
    AMPLIFIER = "amplifier"
    OSCILLATOR = "oscillator"
    SWITCH_RF = "switch_rf"
    DIPLEXER = "diplexer"
    COUPLER = "coupler"
    CABLE_ASSEMBLY = "cable_assembly"
    CONNECTOR_ASSEMBLY = "connector_assembly"
    RELAY_BOX = "relay_box"
    JUNCTION_BOX = "junction_box"
    TERMINAL_BLOCK = "terminal_block"
    FUSE_BOX = "fuse_box"
    TRANSFORMER = "transformer"
    REGULATOR = "regulator"
    GYROSCOPE = "gyroscope"
    ACCELEROMETER = "accelerometer"
    STAR_TRACKER = "star_tracker"
    SUN_SENSOR = "sun_sensor"
    EARTH_SENSOR = "earth_sensor"
    GPS_RECEIVER = "gps_receiver"
    INERTIAL_MEASUREMENT_UNIT = "inertial_measurement_unit"
    REACTION_WHEEL = "reaction_wheel"
    THRUSTER = "thruster"
    VALVE = "valve"
    PYROTECHNIC = "pyrotechnic"
    COTS_EQUIPMENT = "cots_equipment"
    GSE = "gse"
    FIRMWARE_MODULE = "firmware_module"
    SOFTWARE_MODULE = "software_module"
    CUSTOM = "custom"


# ── 4. UnitStatus ──

class UnitStatus(str, enum.Enum):
    CONCEPT = "concept"
    PRELIMINARY_DESIGN = "preliminary_design"
    DETAILED_DESIGN = "detailed_design"
    PROTOTYPE = "prototype"
    ENGINEERING_MODEL = "engineering_model"
    QUALIFICATION_UNIT = "qualification_unit"
    FLIGHT_UNIT = "flight_unit"
    FLIGHT_SPARE = "flight_spare"
    PRODUCTION = "production"
    INSTALLED = "installed"
    QUALIFIED = "qualified"
    ACCEPTED = "accepted"
    OPERATIONAL = "operational"
    FAILED = "failed"
    OBSOLETE = "obsolete"


# ── 5. ConnectorType ──

class ConnectorType(str, enum.Enum):
    MIL_DTL_38999_SERIES_I = "mil_dtl_38999_series_i"
    MIL_DTL_38999_SERIES_II = "mil_dtl_38999_series_ii"
    MIL_DTL_38999_SERIES_III = "mil_dtl_38999_series_iii"
    MIL_DTL_38999_SERIES_IV = "mil_dtl_38999_series_iv"
    MIL_DTL_26482_SERIES_I = "mil_dtl_26482_series_i"
    MIL_DTL_26482_SERIES_II = "mil_dtl_26482_series_ii"
    MIL_DTL_83723_SERIES_III = "mil_dtl_83723_series_iii"
    MIL_DTL_5015 = "mil_dtl_5015"
    MIL_C_26500 = "mil_c_26500"
    D_SUB_9 = "d_sub_9"
    D_SUB_15 = "d_sub_15"
    D_SUB_25 = "d_sub_25"
    D_SUB_37 = "d_sub_37"
    D_SUB_50 = "d_sub_50"
    D_SUB_HD15 = "d_sub_hd15"
    D_SUB_HD26 = "d_sub_hd26"
    MICRO_D_9 = "micro_d_9"
    MICRO_D_15 = "micro_d_15"
    MICRO_D_25 = "micro_d_25"
    MICRO_D_37 = "micro_d_37"
    MICRO_D_51 = "micro_d_51"
    NANO_D_9 = "nano_d_9"
    NANO_D_15 = "nano_d_15"
    NANO_D_25 = "nano_d_25"
    NANO_D_31 = "nano_d_31"
    NANO_D_37 = "nano_d_37"
    RJ11 = "rj11"
    RJ45 = "rj45"
    RJ45_SHIELDED = "rj45_shielded"
    USB_A = "usb_a"
    USB_B = "usb_b"
    USB_MINI_B = "usb_mini_b"
    USB_MICRO_B = "usb_micro_b"
    USB_C = "usb_c"
    SMA = "sma"
    SMA_REVERSE = "sma_reverse"
    SMB = "smb"
    SMC = "smc"
    BNC = "bnc"
    TNC = "tnc"
    N_TYPE = "n_type"
    F_TYPE = "f_type"
    FIBER_LC = "fiber_lc"
    FIBER_SC = "fiber_sc"
    FIBER_ST = "fiber_st"
    FIBER_FC = "fiber_fc"
    FIBER_MTP_MPO = "fiber_mtp_mpo"
    M8_3PIN = "m8_3pin"
    M8_4PIN = "m8_4pin"
    M12_4PIN = "m12_4pin"
    M12_5PIN = "m12_5pin"
    M12_8PIN = "m12_8pin"
    M12_12PIN = "m12_12pin"
    MOLEX_MINI_FIT = "molex_mini_fit"
    MOLEX_MICRO_FIT = "molex_micro_fit"
    JST_XH = "jst_xh"
    JST_PH = "jst_ph"
    AMPHENOL_PT = "amphenol_pt"
    AMPHENOL_MS = "amphenol_ms"
    WINCHESTER = "winchester"
    BURNDY = "burndy"
    POWER_ANDERSON = "power_anderson"
    POWER_MIL_C_22992 = "power_mil_c_22992"
    TERMINAL_BLOCK_2 = "terminal_block_2"
    TERMINAL_BLOCK_4 = "terminal_block_4"
    TERMINAL_BLOCK_8 = "terminal_block_8"
    TERMINAL_BLOCK_12 = "terminal_block_12"
    TERMINAL_BLOCK_16 = "terminal_block_16"
    TERMINAL_BLOCK_24 = "terminal_block_24"
    BACKPLANE_VME = "backplane_vme"
    BACKPLANE_CPCI = "backplane_cpci"
    BACKPLANE_VPX = "backplane_vpx"
    BACKPLANE_VITA_46 = "backplane_vita_46"
    SAMTEC_SEARAY = "samtec_searay"
    SAMTEC_TIGER_EYE = "samtec_tiger_eye"
    HARWIN_M80 = "harwin_m80"
    HARWIN_GECKO = "harwin_gecko"
    CIRCULAR_PLASTIC = "circular_plastic"
    RECTANGULAR_SEALED = "rectangular_sealed"
    HERMETIC_FEEDTHROUGH = "hermetic_feedthrough"
    CUSTOM = "custom"


# ── 6. ConnectorGender ──

class ConnectorGender(str, enum.Enum):
    MALE_PIN = "male_pin"
    FEMALE_SOCKET = "female_socket"
    HERMAPHRODITIC = "hermaphroditic"
    GENDERLESS = "genderless"


# ── 7. ConnectorMounting ──

class ConnectorMounting(str, enum.Enum):
    PANEL_MOUNT = "panel_mount"
    BOX_MOUNT = "box_mount"
    BULKHEAD = "bulkhead"
    CABLE_MOUNT = "cable_mount"
    PCB_THROUGH_HOLE = "pcb_through_hole"
    PCB_SURFACE_MOUNT = "pcb_surface_mount"
    RACK_MOUNT = "rack_mount"
    FLANGE_MOUNT = "flange_mount"
    JAM_NUT = "jam_nut"
    THREADED_COUPLING = "threaded_coupling"
    BAYONET = "bayonet"
    PUSH_PULL = "push_pull"
    FREE_HANGING = "free_hanging"
    HERMETIC_SEAL = "hermetic_seal"
    CUSTOM = "custom"


# ── 8. ShellMaterial ──

class ShellMaterial(str, enum.Enum):
    ALUMINUM = "aluminum"
    STAINLESS_STEEL = "stainless_steel"
    COMPOSITE = "composite"
    NICKEL_ALLOY = "nickel_alloy"
    BRASS = "brass"
    TITANIUM = "titanium"
    PLASTIC_NYLON = "plastic_nylon"
    PLASTIC_PBT = "plastic_pbt"
    ZINC_DIECAST = "zinc_diecast"
    CUSTOM = "custom"


# ── 9. ShellFinish ──

class ShellFinish(str, enum.Enum):
    CADMIUM_OLIVE_DRAB = "cadmium_olive_drab"
    ELECTROLESS_NICKEL = "electroless_nickel"
    BLACK_ZINC_NICKEL = "black_zinc_nickel"
    PASSIVATED_STAINLESS = "passivated_stainless"
    ANODIZED = "anodized"
    ZINC_COBALT = "zinc_cobalt"
    TIN = "tin"
    GOLD = "gold"
    UNFINISHED = "unfinished"
    CUSTOM = "custom"


# ── 10. ContactFinish ──

class ContactFinish(str, enum.Enum):
    GOLD = "gold"
    SILVER = "silver"
    TIN = "tin"
    NICKEL = "nickel"
    PALLADIUM = "palladium"
    RHODIUM = "rhodium"
    SOLDER = "solder"
    CRIMP = "crimp"
    CUSTOM = "custom"


# ── 11. SignalType ──

class SignalType(str, enum.Enum):
    POWER_PRIMARY = "power_primary"
    POWER_SECONDARY = "power_secondary"
    POWER_RETURN = "power_return"
    CHASSIS_GROUND = "chassis_ground"
    SIGNAL_GROUND = "signal_ground"
    SIGNAL_DIGITAL_SINGLE = "signal_digital_single"
    SIGNAL_DIGITAL_DIFFERENTIAL = "signal_digital_differential"
    SIGNAL_ANALOG_SINGLE = "signal_analog_single"
    SIGNAL_ANALOG_DIFFERENTIAL = "signal_analog_differential"
    CLOCK_SINGLE = "clock_single"
    CLOCK_DIFFERENTIAL = "clock_differential"
    CLOCK_REFERENCE = "clock_reference"
    RF_SIGNAL = "rf_signal"
    RF_LO = "rf_lo"
    RF_IF = "rf_if"
    DISCRETE_INPUT = "discrete_input"
    DISCRETE_OUTPUT = "discrete_output"
    DISCRETE_BIDIRECTIONAL = "discrete_bidirectional"
    SERIAL_DATA = "serial_data"
    PARALLEL_DATA = "parallel_data"
    PWM = "pwm"
    PULSE = "pulse"
    THERMOCOUPLE = "thermocouple"
    RTD = "rtd"
    STRAIN_GAUGE = "strain_gauge"
    LVDT = "lvdt"
    FIBER_OPTIC_SINGLE = "fiber_optic_single"
    FIBER_OPTIC_MULTI = "fiber_optic_multi"
    COAX_SIGNAL = "coax_signal"
    SPARE = "spare"
    NO_CONNECT = "no_connect"
    SHIELD_OVERALL = "shield_overall"
    SHIELD_INDIVIDUAL = "shield_individual"
    SHIELD_DRAIN = "shield_drain"
    TEST_POINT = "test_point"
    KEY_PIN = "key_pin"
    ALIGNMENT_PIN = "alignment_pin"
    RESERVED = "reserved"
    CUSTOM = "custom"


# ── 12. PinDirection ──

class PinDirection(str, enum.Enum):
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    TRI_STATE = "tri_state"
    POWER_SOURCE = "power_source"
    POWER_SINK = "power_sink"
    POWER_RETURN = "power_return"
    GROUND = "ground"
    CHASSIS_GROUND = "chassis_ground"
    NO_CONNECT = "no_connect"
    SPARE = "spare"
    CUSTOM = "custom"


# ── 13. PinSize ──

class PinSize(str, enum.Enum):
    SIZE_22 = "size_22"
    SIZE_22D = "size_22d"
    SIZE_20 = "size_20"
    SIZE_16 = "size_16"
    SIZE_12 = "size_12"
    SIZE_8 = "size_8"
    SIZE_4 = "size_4"
    SIZE_0 = "size_0"
    COAX = "coax"
    TWINAX = "twinax"
    FIBER = "fiber"
    POWER_HIGH_CURRENT = "power_high_current"
    CUSTOM = "custom"


# ── 14. BusProtocol ──

class BusProtocol(str, enum.Enum):
    MIL_STD_1553A = "mil_std_1553a"
    MIL_STD_1553B = "mil_std_1553b"
    MIL_STD_1773 = "mil_std_1773"
    SPACEWIRE = "spacewire"
    SPACEWIRE_RMAP = "spacewire_rmap"
    CAN_2A = "can_2a"
    CAN_2B = "can_2b"
    CANFD = "canfd"
    CANOPEN = "canopen"
    DEVICENET = "devicenet"
    J1939 = "j1939"
    RS232 = "rs232"
    RS422 = "rs422"
    RS422_DIFFERENTIAL = "rs422_differential"
    RS485 = "rs485"
    RS485_MULTIPOINT = "rs485_multipoint"
    UART_TTL = "uart_ttl"
    UART_CMOS = "uart_cmos"
    SPI_MODE0 = "spi_mode0"
    SPI_MODE1 = "spi_mode1"
    SPI_MODE2 = "spi_mode2"
    SPI_MODE3 = "spi_mode3"
    QSPI = "qspi"
    I2C_STANDARD = "i2c_standard"
    I2C_FAST = "i2c_fast"
    I2C_FAST_PLUS = "i2c_fast_plus"
    I2C_HIGH_SPEED = "i2c_high_speed"
    SMBUS = "smbus"
    ETHERNET_10BASE_T = "ethernet_10base_t"
    ETHERNET_100BASE_TX = "ethernet_100base_tx"
    ETHERNET_100BASE_FX = "ethernet_100base_fx"
    ETHERNET_1000BASE_T = "ethernet_1000base_t"
    ETHERNET_1000BASE_SX = "ethernet_1000base_sx"
    ETHERNET_10GBASE_T = "ethernet_10gbase_t"
    ETHERNET_10GBASE_SR = "ethernet_10gbase_sr"
    ARINC_429 = "arinc_429"
    ARINC_629 = "arinc_629"
    ARINC_664_PART7 = "arinc_664_part7"
    ARINC_818 = "arinc_818"
    USB_1_1 = "usb_1_1"
    USB_2_0 = "usb_2_0"
    USB_3_0 = "usb_3_0"
    MIL_STD_1760 = "mil_std_1760"
    CCSDS_AOS = "ccsds_aos"
    CCSDS_TM = "ccsds_tm"
    CCSDS_TC = "ccsds_tc"
    CCSDS_CFDP = "ccsds_cfdp"
    TTE_ETHERNET = "tte_ethernet"
    PROFINET = "profinet"
    PROFIBUS_DP = "profibus_dp"
    MODBUS_RTU = "modbus_rtu"
    MODBUS_TCP = "modbus_tcp"
    FLEXRAY = "flexray"
    LIN = "lin"
    SERDES_LVDS = "serdes_lvds"
    SERDES_CML = "serdes_cml"
    JESD204B = "jesd204b"
    JESD204C = "jesd204c"
    PCI_EXPRESS = "pci_express"
    RAPID_IO = "rapid_io"
    FIBRE_CHANNEL = "fibre_channel"
    JTAG = "jtag"
    SWD = "swd"
    ONEWIRE = "oneWire"
    ANALOG_0_5V = "analog_0_5v"
    ANALOG_4_20MA = "analog_4_20ma"
    ANALOG_0_10V = "analog_0_10v"
    DISCRETE_28V = "discrete_28v"
    DISCRETE_5V = "discrete_5v"
    DISCRETE_3V3 = "discrete_3v3"
    DISCRETE_OPEN_COLLECTOR = "discrete_open_collector"
    DISCRETE_RELAY_CONTACT = "discrete_relay_contact"
    SYNCHRO = "synchro"
    RESOLVER = "resolver"
    ENCODER_INCREMENTAL = "encoder_incremental"
    ENCODER_ABSOLUTE = "encoder_absolute"
    CUSTOM = "custom"


# ── 15. BusRole ──

class BusRole(str, enum.Enum):
    BUS_CONTROLLER = "bus_controller"
    REMOTE_TERMINAL = "remote_terminal"
    BUS_MONITOR = "bus_monitor"
    MASTER = "master"
    SLAVE = "slave"
    MULTI_MASTER = "multi_master"
    PUBLISHER = "publisher"
    SUBSCRIBER = "subscriber"
    REQUESTER = "requester"
    RESPONDER = "responder"
    INITIATOR = "initiator"
    TARGET = "target"
    PEER = "peer"
    PRIMARY = "primary"
    SECONDARY = "secondary"
    ARBITER = "arbiter"
    CUSTOM = "custom"


# ── 16. BusTopology ──

class BusTopology(str, enum.Enum):
    BUS_SHARED = "bus_shared"
    BUS_STUB = "bus_stub"
    POINT_TO_POINT = "point_to_point"
    STAR = "star"
    RING = "ring"
    DUAL_RING = "dual_ring"
    MESH = "mesh"
    PARTIAL_MESH = "partial_mesh"
    TREE = "tree"
    DAISY_CHAIN = "daisy_chain"
    MULTI_DROP = "multi_drop"
    CROSSBAR = "crossbar"
    SWITCHED_FABRIC = "switched_fabric"
    CUSTOM = "custom"


# ── 17. BusRedundancy ──

class BusRedundancy(str, enum.Enum):
    NONE = "none"
    DUAL_STANDBY = "dual_standby"
    DUAL_ACTIVE = "dual_active"
    DUAL_HOT_SPARE = "dual_hot_spare"
    TRIPLE_MODULAR_REDUNDANCY = "triple_modular_redundancy"
    QUAD = "quad"
    RING_PROTECTION = "ring_protection"
    CUSTOM = "custom"


# ── 18. PinBusRole ──

class PinBusRole(str, enum.Enum):
    DATA_POSITIVE = "data_positive"
    DATA_NEGATIVE = "data_negative"
    DATA_SINGLE_ENDED = "data_single_ended"
    CLOCK_POSITIVE = "clock_positive"
    CLOCK_NEGATIVE = "clock_negative"
    CLOCK_SINGLE_ENDED = "clock_single_ended"
    STROBE_POSITIVE = "strobe_positive"
    STROBE_NEGATIVE = "strobe_negative"
    TX_POSITIVE = "tx_positive"
    TX_NEGATIVE = "tx_negative"
    TX_SINGLE = "tx_single"
    RX_POSITIVE = "rx_positive"
    RX_NEGATIVE = "rx_negative"
    RX_SINGLE = "rx_single"
    CHIP_SELECT_ACTIVE_LOW = "chip_select_active_low"
    CHIP_SELECT_ACTIVE_HIGH = "chip_select_active_high"
    ENABLE_ACTIVE_LOW = "enable_active_low"
    ENABLE_ACTIVE_HIGH = "enable_active_high"
    RESET_ACTIVE_LOW = "reset_active_low"
    RESET_ACTIVE_HIGH = "reset_active_high"
    INTERRUPT = "interrupt"
    READY = "ready"
    ACKNOWLEDGE = "acknowledge"
    REQUEST = "request"
    GRANT = "grant"
    SHIELD = "shield"
    DRAIN_WIRE = "drain_wire"
    BUS_POWER = "bus_power"
    BUS_GROUND = "bus_ground"
    BUS_BIAS = "bus_bias"
    SPARE = "spare"
    CUSTOM = "custom"


# ── 19. MessageDirection ──

class MessageDirection(str, enum.Enum):
    TRANSMIT = "transmit"
    RECEIVE = "receive"
    TRANSMIT_RECEIVE = "transmit_receive"
    BROADCAST = "broadcast"
    REQUEST = "request"
    RESPONSE = "response"
    STATUS = "status"


# ── 20. MessagePriority ──

class MessagePriority(str, enum.Enum):
    SAFETY_CRITICAL = "safety_critical"
    MISSION_CRITICAL = "mission_critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    BACKGROUND = "background"
    DIAGNOSTIC = "diagnostic"


# ── 21. MessageScheduling ──

class MessageScheduling(str, enum.Enum):
    PERIODIC_SYNCHRONOUS = "periodic_synchronous"
    PERIODIC_ASYNCHRONOUS = "periodic_asynchronous"
    APERIODIC_EVENT_DRIVEN = "aperiodic_event_driven"
    APERIODIC_COMMAND_RESPONSE = "aperiodic_command_response"
    SPORADIC = "sporadic"
    ON_CHANGE = "on_change"
    ONE_SHOT = "one_shot"
    STARTUP_ONLY = "startup_only"


# ── 22. FieldDataType ──

class FieldDataType(str, enum.Enum):
    BOOLEAN = "boolean"
    UINT8 = "uint8"
    INT8 = "int8"
    UINT16 = "uint16"
    INT16 = "int16"
    UINT32 = "uint32"
    INT32 = "int32"
    UINT64 = "uint64"
    INT64 = "int64"
    FLOAT16 = "float16"
    FLOAT32 = "float32"
    FLOAT64 = "float64"
    ENUM_CODED = "enum_coded"
    BITFIELD = "bitfield"
    BITMASK = "bitmask"
    BCD_PACKED = "bcd_packed"
    BCD_UNPACKED = "bcd_unpacked"
    CHAR_ASCII = "char_ascii"
    CHAR_UTF8 = "char_utf8"
    STRING_FIXED = "string_fixed"
    STRING_VARIABLE = "string_variable"
    TIMESTAMP_TAI = "timestamp_tai"
    TIMESTAMP_UTC = "timestamp_utc"
    TIMESTAMP_GPS = "timestamp_gps"
    TIMESTAMP_UNIX = "timestamp_unix"
    ANGLE_BAM16 = "angle_bam16"
    ANGLE_BAM32 = "angle_bam32"
    RAW_BYTES = "raw_bytes"
    RESERVED = "reserved"
    SPARE = "spare"
    CUSTOM = "custom"


# ── 23. ByteOrder ──

class ByteOrder(str, enum.Enum):
    BIG_ENDIAN = "big_endian"
    LITTLE_ENDIAN = "little_endian"
    PDP_ENDIAN = "pdp_endian"
    NATIVE = "native"


# ── 24. WireType ──

class WireType(str, enum.Enum):
    SIGNAL_SINGLE = "signal_single"
    SIGNAL_TWISTED_PAIR_A = "signal_twisted_pair_a"
    SIGNAL_TWISTED_PAIR_B = "signal_twisted_pair_b"
    SIGNAL_SHIELDED_SINGLE = "signal_shielded_single"
    SIGNAL_SHIELDED_PAIR = "signal_shielded_pair"
    POWER_POSITIVE = "power_positive"
    POWER_NEGATIVE = "power_negative"
    POWER_RETURN = "power_return"
    GROUND_SIGNAL = "ground_signal"
    GROUND_CHASSIS = "ground_chassis"
    GROUND_POWER = "ground_power"
    SHIELD_OVERALL_DRAIN = "shield_overall_drain"
    SHIELD_INDIVIDUAL_DRAIN = "shield_individual_drain"
    SHIELD_BRAID = "shield_braid"
    COAX_CENTER = "coax_center"
    COAX_SHIELD = "coax_shield"
    COAX_DRAIN = "coax_drain"
    TRIAX_CENTER = "triax_center"
    TRIAX_INNER_SHIELD = "triax_inner_shield"
    TRIAX_OUTER_SHIELD = "triax_outer_shield"
    TWINAX_A = "twinax_a"
    TWINAX_B = "twinax_b"
    TWINAX_SHIELD = "twinax_shield"
    FIBER_TX = "fiber_tx"
    FIBER_RX = "fiber_rx"
    SPARE = "spare"
    JUMPER = "jumper"
    TEST = "test"
    CUSTOM = "custom"


# ── 25. WireGauge ──

class WireGauge(str, enum.Enum):
    AWG_30 = "awg_30"
    AWG_28 = "awg_28"
    AWG_26 = "awg_26"
    AWG_24 = "awg_24"
    AWG_22 = "awg_22"
    AWG_20 = "awg_20"
    AWG_18 = "awg_18"
    AWG_16 = "awg_16"
    AWG_14 = "awg_14"
    AWG_12 = "awg_12"
    AWG_10 = "awg_10"
    AWG_8 = "awg_8"
    AWG_6 = "awg_6"
    AWG_4 = "awg_4"
    AWG_2 = "awg_2"
    AWG_1 = "awg_1"
    AWG_0 = "awg_0"
    AWG_00 = "awg_00"
    AWG_000 = "awg_000"
    AWG_0000 = "awg_0000"
    CUSTOM = "custom"


# ── 26. HarnessStatus ──

class HarnessStatus(str, enum.Enum):
    CONCEPT = "concept"
    PRELIMINARY_DESIGN = "preliminary_design"
    DETAILED_DESIGN = "detailed_design"
    DRAWING_RELEASED = "drawing_released"
    FABRICATION = "fabrication"
    INSPECTION = "inspection"
    ACCEPTANCE_TEST = "acceptance_test"
    INSTALLED = "installed"
    REWORK = "rework"
    FIELD_MODIFICATION = "field_modification"
    RETIRED = "retired"


# ── 27. CableJacketMaterial ──

class CableJacketMaterial(str, enum.Enum):
    PTFE_TEFLON = "ptfe_teflon"
    FEP = "fep"
    ETFE_TEFZEL = "etfe_tefzel"
    PFA = "pfa"
    PVDF_KYNAR = "pvdf_kynar"
    POLYIMIDE_KAPTON = "polyimide_kapton"
    SILICONE_RUBBER = "silicone_rubber"
    EPR = "epr"
    PVC = "pvc"
    XLPE = "xlpe"
    POLYETHYLENE = "polyethylene"
    POLYPROPYLENE = "polypropylene"
    NEOPRENE = "neoprene"
    HYPALON = "hypalon"
    THERMOPLASTIC_ELASTOMER = "thermoplastic_elastomer"
    NOMEX = "nomex"
    FIBERGLASS = "fiberglass"
    STAINLESS_STEEL_BRAID = "stainless_steel_braid"
    COMPOSITE = "composite"
    CUSTOM = "custom"


# ── 28. ShieldType ──

class ShieldType(str, enum.Enum):
    NONE = "none"
    OVERALL_BRAID = "overall_braid"
    OVERALL_FOIL = "overall_foil"
    OVERALL_SPIRAL = "overall_spiral"
    OVERALL_BRAID_PLUS_FOIL = "overall_braid_plus_foil"
    OVERALL_CONDUIT = "overall_conduit"
    INDIVIDUAL_PAIR_BRAID = "individual_pair_braid"
    INDIVIDUAL_PAIR_FOIL = "individual_pair_foil"
    INDIVIDUAL_PAIR_BRAID_PLUS_FOIL = "individual_pair_braid_plus_foil"
    COMBINATION_INDIVIDUAL_PLUS_OVERALL = "combination_individual_plus_overall"
    CONDUCTIVE_POLYMER = "conductive_polymer"
    CUSTOM = "custom"


# ── 29. InterfaceType ──

class InterfaceType(str, enum.Enum):
    ELECTRICAL_POWER = "electrical_power"
    ELECTRICAL_SIGNAL = "electrical_signal"
    ELECTRICAL_COMBINED = "electrical_combined"
    DATA_DIGITAL = "data_digital"
    DATA_ANALOG = "data_analog"
    DATA_MIXED = "data_mixed"
    RF_TRANSMIT = "rf_transmit"
    RF_RECEIVE = "rf_receive"
    RF_DUPLEX = "rf_duplex"
    OPTICAL_FIBER = "optical_fiber"
    OPTICAL_FREE_SPACE = "optical_free_space"
    MECHANICAL_STRUCTURAL = "mechanical_structural"
    MECHANICAL_THERMAL = "mechanical_thermal"
    FLUID_PNEUMATIC = "fluid_pneumatic"
    FLUID_HYDRAULIC = "fluid_hydraulic"
    FLUID_COOLANT = "fluid_coolant"
    THERMAL_CONDUCTIVE = "thermal_conductive"
    THERMAL_RADIATIVE = "thermal_radiative"
    ELECTROMAGNETIC = "electromagnetic"
    ACOUSTIC = "acoustic"
    CUSTOM = "custom"


# ── 30. InterfaceDirection ──

class InterfaceDirection(str, enum.Enum):
    SOURCE_TO_TARGET = "source_to_target"
    TARGET_TO_SOURCE = "target_to_source"
    BIDIRECTIONAL = "bidirectional"
    BROADCAST = "broadcast"


# ── 31. InterfaceStatus ──

class InterfaceStatus(str, enum.Enum):
    PROPOSED = "proposed"
    DEFINED = "defined"
    PRELIMINARY = "preliminary"
    UNDER_REVIEW = "under_review"
    AGREED = "agreed"
    BASELINED = "baselined"
    IMPLEMENTED = "implemented"
    INTEGRATION_TESTED = "integration_tested"
    VERIFIED = "verified"
    VALIDATED = "validated"
    WAIVED = "waived"
    CUSTOM = "custom"


# ── 32. InterfaceCriticality ──

class InterfaceCriticality(str, enum.Enum):
    CATASTROPHIC = "catastrophic"
    HAZARDOUS = "hazardous"
    MAJOR = "major"
    MINOR = "minor"
    NO_EFFECT = "no_effect"
    SAFETY_CRITICAL_A = "safety_critical_a"
    SAFETY_CRITICAL_B = "safety_critical_b"
    SAFETY_CRITICAL_C = "safety_critical_c"
    MISSION_CRITICAL = "mission_critical"
    MISSION_ESSENTIAL = "mission_essential"
    MISSION_SUPPORT = "mission_support"
    NON_CRITICAL = "non_critical"


# ── 33. EnvironmentalCategory ──

class EnvironmentalCategory(str, enum.Enum):
    TEMPERATURE_OPERATING = "temperature_operating"
    TEMPERATURE_STORAGE = "temperature_storage"
    TEMPERATURE_SURVIVAL = "temperature_survival"
    HUMIDITY = "humidity"
    ALTITUDE = "altitude"
    PRESSURE = "pressure"
    VACUUM = "vacuum"
    VIBRATION_RANDOM = "vibration_random"
    VIBRATION_SINUSOIDAL = "vibration_sinusoidal"
    VIBRATION_COMBINED = "vibration_combined"
    SHOCK_MECHANICAL = "shock_mechanical"
    SHOCK_PYROTECHNIC = "shock_pyrotechnic"
    SHOCK_BALLISTIC = "shock_ballistic"
    ACCELERATION_SUSTAINED = "acceleration_sustained"
    ACCELERATION_TRANSIENT = "acceleration_transient"
    ACOUSTIC_NOISE = "acoustic_noise"
    SAND_DUST = "sand_dust"
    SALT_FOG = "salt_fog"
    RAIN = "rain"
    ICING = "icing"
    FUNGUS = "fungus"
    EXPLOSIVE_ATMOSPHERE = "explosive_atmosphere"
    SOLAR_RADIATION = "solar_radiation"
    THERMAL_CYCLING = "thermal_cycling"
    THERMAL_SHOCK = "thermal_shock"
    RADIATION_TOTAL_DOSE = "radiation_total_dose"
    RADIATION_SINGLE_EVENT = "radiation_single_event"
    RADIATION_DISPLACEMENT = "radiation_displacement"
    EMI_CE101 = "emi_ce101"
    EMI_CE102 = "emi_ce102"
    EMI_CE106 = "emi_ce106"
    EMI_CS101 = "emi_cs101"
    EMI_CS103 = "emi_cs103"
    EMI_CS104 = "emi_cs104"
    EMI_CS105 = "emi_cs105"
    EMI_CS106 = "emi_cs106"
    EMI_CS109 = "emi_cs109"
    EMI_CS114 = "emi_cs114"
    EMI_CS115 = "emi_cs115"
    EMI_CS116 = "emi_cs116"
    EMI_RE101 = "emi_re101"
    EMI_RE102 = "emi_re102"
    EMI_RE103 = "emi_re103"
    EMI_RS101 = "emi_rs101"
    EMI_RS103 = "emi_rs103"
    EMI_RS105 = "emi_rs105"
    ESD_HBM = "esd_hbm"
    ESD_CDM = "esd_cdm"
    ESD_MM = "esd_mm"
    LIGHTNING_DIRECT = "lightning_direct"
    LIGHTNING_INDIRECT = "lightning_indirect"
    EMP_HEMP = "emp_hemp"
    EMP_SREMP = "emp_sremp"
    MAGNETIC_FIELD_DC = "magnetic_field_dc"
    MAGNETIC_FIELD_AC = "magnetic_field_ac"
    CUSTOM = "custom"


# ── 34. EnvironmentalStandard ──

class EnvironmentalStandard(str, enum.Enum):
    MIL_STD_810H = "mil_std_810h"
    MIL_STD_810G = "mil_std_810g"
    MIL_STD_461G = "mil_std_461g"
    MIL_STD_461F = "mil_std_461f"
    MIL_STD_464C = "mil_std_464c"
    MIL_HDBK_217F = "mil_hdbk_217f"
    DO_160G = "do_160g"
    DO_160F = "do_160f"
    ISO_16750 = "iso_16750"
    ISO_11452 = "iso_11452"
    ISO_7637 = "iso_7637"
    IEC_61000_SERIES = "iec_61000_series"
    IEC_60068 = "iec_60068"
    NASA_STD_4003A = "nasa_std_4003a"
    NASA_STD_4005A = "nasa_std_4005a"
    ECSS_E_ST_10_03C = "ecss_e_st_10_03c"
    ECSS_E_ST_20C = "ecss_e_st_20c"
    JSSG_2009 = "jssg_2009"
    JSSG_2010 = "jssg_2010"
    CUSTOM = "custom"


# ── 35. InterfaceEntityType ──

class InterfaceEntityType(str, enum.Enum):
    SYSTEM = "system"
    UNIT = "unit"
    CONNECTOR = "connector"
    PIN = "pin"
    PIN_BUS_ASSIGNMENT = "pin_bus_assignment"
    BUS_DEFINITION = "bus_definition"
    MESSAGE_DEFINITION = "message_definition"
    MESSAGE_FIELD = "message_field"
    WIRE_HARNESS = "wire_harness"
    WIRE = "wire"
    CABLE_ASSEMBLY = "cable_assembly"
    INTERFACE = "interface"
    INTERFACE_DOCUMENT = "interface_document"


# ── 36. InterfaceLinkType ──

class InterfaceLinkType(str, enum.Enum):
    SATISFIES = "satisfies"
    PARTIALLY_SATISFIES = "partially_satisfies"
    VERIFIES = "verifies"
    VALIDATES = "validates"
    DERIVES_FROM = "derives_from"
    DECOMPOSES = "decomposes"
    REFINES = "refines"
    ELABORATES = "elaborates"
    CONSTRAINS = "constrains"
    ENABLES = "enables"
    CONFLICTS_WITH = "conflicts_with"
    IMPLEMENTS = "implements"
    ALLOCATED_TO = "allocated_to"
    REALIZED_BY = "realized_by"
    TESTED_BY = "tested_by"
    ANALYZED_BY = "analyzed_by"
    INSPECTED_BY = "inspected_by"
    DEMONSTRATED_BY = "demonstrated_by"
    TRACES_TO = "traces_to"
    REFERENCES = "references"
    CUSTOM = "custom"


# ── 37. AutoReqSource ──

class AutoReqSource(str, enum.Enum):
    WIRE_CONNECTION = "wire_connection"
    BUS_CONNECTION = "bus_connection"
    MESSAGE_DEFINITION = "message_definition"
    MESSAGE_FIELD = "message_field"
    POWER_WIRE = "power_wire"
    GROUND_WIRE = "ground_wire"
    DISCRETE_SIGNAL = "discrete_signal"
    RF_CONNECTION = "rf_connection"
    SHIELD_GROUNDING = "shield_grounding"
    HARNESS_OVERALL = "harness_overall"
    ENVIRONMENTAL_SPEC = "environmental_spec"
    EMI_SPEC = "emi_spec"
    UNIT_IMPORT = "unit_import"
    MANUAL = "manual"


# ── 38. AutoReqStatus ──

class AutoReqStatus(str, enum.Enum):
    PENDING_REVIEW = "pending_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    MERGED = "merged"
    DEFERRED = "deferred"


# ══════════════════════════════════════════════════════════════
#  Models (15)
# ══════════════════════════════════════════════════════════════

# ── 1. System ──

class System(Base):
    __tablename__ = "systems"

    id = Column(Integer, primary_key=True, index=True)
    system_id = Column(String(30), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    abbreviation = Column(String(30))
    description = Column(Text, default="")
    system_type = Column(SQLEnum(SystemType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    system_type_custom = Column(String(100))
    status = Column(SQLEnum(SystemStatus, values_callable=lambda x: [e.value for e in x]), default=SystemStatus.CONCEPT)
    parent_system_id = Column(Integer, ForeignKey("systems.id"), nullable=True)
    wbs_number = Column(String(30))
    responsible_org = Column(String(255))
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    units = relationship("Unit", back_populates="system")
    child_systems = relationship("System", backref=backref("parent_system", remote_side=[id]))
    owner = relationship("User")

    __table_args__ = (
        Index("ix_system_project_type", "project_id", "system_type"),
        Index("ix_system_parent", "parent_system_id"),
    )


# ── 2. Unit ──

class Unit(Base):
    __tablename__ = "units"

    id = Column(Integer, primary_key=True, index=True)
    unit_id = Column(String(30), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    designation = Column(String(50), nullable=False)
    description = Column(Text, default="")
    part_number = Column(String(100), nullable=False)
    manufacturer = Column(String(255), nullable=False)
    cage_code = Column(String(10))
    nsn = Column(String(20))
    drawing_number = Column(String(50))
    revision = Column(String(20))
    serial_number_prefix = Column(String(30))
    unit_type = Column(SQLEnum(UnitType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    unit_type_custom = Column(String(100))
    status = Column(SQLEnum(UnitStatus, values_callable=lambda x: [e.value for e in x]), default=UnitStatus.CONCEPT)
    heritage = Column(String(255))

    # Physical
    mass_kg = Column(Float)
    mass_max_kg = Column(Float)
    dimensions_l_mm = Column(Float)
    dimensions_w_mm = Column(Float)
    dimensions_h_mm = Column(Float)
    volume_cc = Column(Float)

    # Electrical
    power_watts_nominal = Column(Float)
    power_watts_peak = Column(Float)
    power_watts_standby = Column(Float)
    voltage_input_nominal = Column(String(30))
    voltage_input_min = Column(Float)
    voltage_input_max = Column(Float)
    voltage_ripple_max_mvpp = Column(Float)
    current_inrush_amps = Column(Float)
    current_steady_state_amps = Column(Float)

    # Thermal
    temp_operating_min_c = Column(Float)
    temp_operating_max_c = Column(Float)
    temp_storage_min_c = Column(Float)
    temp_storage_max_c = Column(Float)
    temp_survival_min_c = Column(Float)
    temp_survival_max_c = Column(Float)

    # Mechanical
    vibration_random_grms = Column(Float)
    vibration_sine_g_peak = Column(Float)
    shock_mechanical_g = Column(Float)
    shock_mechanical_duration_ms = Column(Float)
    shock_pyrotechnic_g = Column(Float)
    acceleration_max_g = Column(Float)
    acoustic_spl_db = Column(Float)

    # Climate
    humidity_min_pct = Column(Float)
    humidity_max_pct = Column(Float)
    altitude_operating_max_m = Column(Float)
    altitude_storage_max_m = Column(Float)
    pressure_min_kpa = Column(Float)
    pressure_max_kpa = Column(Float)
    sand_dust_exposed = Column(Boolean, default=False)
    salt_fog_exposed = Column(Boolean, default=False)
    fungus_resistant = Column(Boolean, default=False)

    # EMI/EMC (MIL-STD-461G)
    emi_ce101_limit_dba = Column(Float)
    emi_ce102_limit_dbua = Column(Float)
    emi_cs101_limit_db = Column(Float)
    emi_cs114_limit_dba = Column(Float)
    emi_cs115_limit_v = Column(Float)
    emi_cs116_limit_db = Column(Float)
    emi_re101_limit_dba = Column(Float)
    emi_re102_limit_dbm = Column(Float)
    emi_rs101_limit_db = Column(Float)
    emi_rs103_limit_vm = Column(Float)
    esd_hbm_v = Column(Float)
    esd_cdm_v = Column(Float)

    # Radiation
    radiation_tid_krad = Column(Float)
    radiation_see_let_threshold = Column(Float)
    radiation_dd_mev_cm2_g = Column(Float)

    # Reliability
    mtbf_hours = Column(Float)
    mtbf_environment = Column(String(30))
    design_life_years = Column(Float)
    duty_cycle_pct = Column(Float)
    derating_standard = Column(String(50))

    # References
    datasheet_url = Column(String(500))
    specification_doc = Column(String(255))
    test_report_doc = Column(String(255))
    notes = Column(Text, default="")
    metadata_json = Column(JSON, default={})

    # Foreign keys
    system_id = Column(Integer, ForeignKey("systems.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    connectors = relationship("Connector", back_populates="unit", cascade="all, delete-orphan")
    bus_definitions = relationship("BusDefinition", back_populates="unit", cascade="all, delete-orphan")
    system = relationship("System", back_populates="units")

    __table_args__ = (
        UniqueConstraint("project_id", "designation", name="uq_unit_designation"),
        Index("ix_unit_system", "system_id"),
        Index("ix_unit_mfg", "manufacturer"),
    )


# ── 3. Connector ──

class Connector(Base):
    __tablename__ = "connectors"

    id = Column(Integer, primary_key=True, index=True)
    connector_id = Column(String(30))
    designator = Column(String(20), nullable=False)
    name = Column(String(255))
    description = Column(Text, default="")
    connector_type = Column(SQLEnum(ConnectorType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    connector_type_custom = Column(String(100))
    gender = Column(SQLEnum(ConnectorGender, values_callable=lambda x: [e.value for e in x]), nullable=False)
    mounting = Column(SQLEnum(ConnectorMounting, values_callable=lambda x: [e.value for e in x]))
    mounting_custom = Column(String(100))
    shell_size = Column(String(20))
    insert_arrangement = Column(String(30))
    total_contacts = Column(Integer, nullable=False)
    signal_contacts = Column(Integer)
    power_contacts = Column(Integer)
    coax_contacts = Column(Integer)
    fiber_contacts = Column(Integer)
    spare_contacts = Column(Integer)
    keying = Column(String(50))
    polarization = Column(String(30))
    coupling = Column(String(30))
    ip_rating = Column(String(10))
    operating_temp_min_c = Column(Float)
    operating_temp_max_c = Column(Float)
    mating_cycles = Column(Integer)
    shell_material = Column(SQLEnum(ShellMaterial, values_callable=lambda x: [e.value for e in x]))
    shell_finish = Column(SQLEnum(ShellFinish, values_callable=lambda x: [e.value for e in x]))
    contact_finish = Column(SQLEnum(ContactFinish, values_callable=lambda x: [e.value for e in x]))
    mil_spec = Column(String(80))
    manufacturer_part_number = Column(String(100))
    connector_manufacturer = Column(String(255))
    backshell_type = Column(String(100))
    notes = Column(Text, default="")

    # Foreign keys
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    pins = relationship("Pin", back_populates="connector", cascade="all, delete-orphan")
    unit = relationship("Unit", back_populates="connectors")

    __table_args__ = (
        UniqueConstraint("unit_id", "designator", name="uq_connector_designator"),
    )


# ── 4. Pin ──

class Pin(Base):
    __tablename__ = "pins"

    id = Column(Integer, primary_key=True, index=True)
    pin_number = Column(String(10), nullable=False)
    pin_label = Column(String(30))
    signal_name = Column(String(150), nullable=False)
    signal_type = Column(SQLEnum(SignalType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    signal_type_custom = Column(String(100))
    direction = Column(SQLEnum(PinDirection, values_callable=lambda x: [e.value for e in x]), nullable=False)
    pin_size = Column(SQLEnum(PinSize, values_callable=lambda x: [e.value for e in x]))
    contact_type = Column(String(30))
    voltage_nominal = Column(String(30))
    voltage_min = Column(Float)
    voltage_max = Column(Float)
    voltage_dc_bias = Column(Float)
    current_nominal_amps = Column(Float)
    current_max_amps = Column(Float)
    impedance_ohms = Column(Float)
    frequency_mhz = Column(Float)
    rise_time_ns = Column(Float)
    termination = Column(String(50))
    pull_up_down = Column(String(30))
    esd_protection = Column(String(50))
    description = Column(Text, default="")
    notes = Column(Text, default="")

    # Foreign keys
    connector_id = Column(Integer, ForeignKey("connectors.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    connector = relationship("Connector", back_populates="pins")

    __table_args__ = (
        UniqueConstraint("connector_id", "pin_number", name="uq_pin_number"),
        Index("ix_pin_signal_name", "signal_name"),
    )


# ── 5. BusDefinition ──

class BusDefinition(Base):
    __tablename__ = "bus_definitions"

    id = Column(Integer, primary_key=True, index=True)
    bus_def_id = Column(String(30))
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    protocol = Column(SQLEnum(BusProtocol, values_callable=lambda x: [e.value for e in x]), nullable=False)
    protocol_custom = Column(String(100))
    protocol_version = Column(String(20))
    bus_role = Column(SQLEnum(BusRole, values_callable=lambda x: [e.value for e in x]), nullable=False)
    bus_role_custom = Column(String(100))
    bus_address = Column(String(30))
    bus_address_secondary = Column(String(30))
    bus_name_network = Column(String(100))
    data_rate = Column(String(30))
    data_rate_actual_bps = Column(Integer)
    word_size_bits = Column(Integer)
    frame_size_max_bytes = Column(Integer)
    topology = Column(SQLEnum(BusTopology, values_callable=lambda x: [e.value for e in x]))
    redundancy = Column(SQLEnum(BusRedundancy, values_callable=lambda x: [e.value for e in x]), default=BusRedundancy.NONE)
    deterministic = Column(Boolean)
    fault_tolerance = Column(String(100))
    bus_loading_max_pct = Column(Float)
    latency_budget_ms = Column(Float)
    jitter_max_us = Column(Float)
    error_rate_max = Column(String(30))
    encoding = Column(String(50))
    electrical_standard = Column(String(50))
    coupling = Column(String(50))
    stub_length_max_m = Column(Float)
    bus_length_max_m = Column(Float)
    termination_required = Column(String(50))
    notes = Column(Text, default="")
    metadata_json = Column(JSON, default={})

    # Foreign keys
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    pin_assignments = relationship("PinBusAssignment", back_populates="bus_definition", cascade="all, delete-orphan")
    messages = relationship("MessageDefinition", back_populates="bus", cascade="all, delete-orphan")
    unit = relationship("Unit", back_populates="bus_definitions")


# ── 6. PinBusAssignment ──

class PinBusAssignment(Base):
    __tablename__ = "pin_bus_assignments"

    id = Column(Integer, primary_key=True, index=True)
    pin_id = Column(Integer, ForeignKey("pins.id"), nullable=False)
    bus_def_id = Column(Integer, ForeignKey("bus_definitions.id"), nullable=False)
    pin_role = Column(SQLEnum(PinBusRole, values_callable=lambda x: [e.value for e in x]), nullable=False)
    pin_role_custom = Column(String(100))
    notes = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    pin = relationship("Pin")
    bus_definition = relationship("BusDefinition", back_populates="pin_assignments")

    __table_args__ = (
        UniqueConstraint("pin_id", "bus_def_id", name="uq_pin_bus_assignment"),
    )


# ── 7. MessageDefinition ──

class MessageDefinition(Base):
    __tablename__ = "message_definitions"

    id = Column(Integer, primary_key=True, index=True)
    msg_def_id = Column(String(30))
    label = Column(String(100), nullable=False)
    mnemonic = Column(String(30))
    description = Column(Text, default="")
    protocol_message_id = Column(String(30))
    message_id_hex = Column(String(20))
    subaddress = Column(Integer)
    word_count = Column(Integer)
    byte_count = Column(Integer)
    direction = Column(SQLEnum(MessageDirection, values_callable=lambda x: [e.value for e in x]), nullable=False)
    scheduling = Column(SQLEnum(MessageScheduling, values_callable=lambda x: [e.value for e in x]), default=MessageScheduling.PERIODIC_SYNCHRONOUS)
    rate_hz = Column(Float)
    rate_min_hz = Column(Float)
    rate_max_hz = Column(Float)
    latency_max_ms = Column(Float)
    latency_typical_ms = Column(Float)
    priority = Column(SQLEnum(MessagePriority, values_callable=lambda x: [e.value for e in x]), default=MessagePriority.MEDIUM)
    is_periodic = Column(Boolean, default=True)
    timeout_ms = Column(Float)
    integrity_mechanism = Column(String(50))
    fragmentation = Column(Boolean, default=False)
    encryption = Column(String(50))
    authentication = Column(String(50))
    source_system_name = Column(String(100))
    target_system_name = Column(String(100))
    icd_reference = Column(String(100))
    notes = Column(Text, default="")
    metadata_json = Column(JSON, default={})

    # Foreign keys
    bus_def_id = Column(Integer, ForeignKey("bus_definitions.id"), nullable=False)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    fields = relationship("MessageField", back_populates="message", cascade="all, delete-orphan")
    bus = relationship("BusDefinition", back_populates="messages")
    unit = relationship("Unit")


# ── 8. MessageField ──

class MessageField(Base):
    __tablename__ = "message_fields"

    id = Column(Integer, primary_key=True, index=True)
    field_name = Column(String(100), nullable=False)
    label = Column(String(100))
    description = Column(Text, default="")
    data_type = Column(SQLEnum(FieldDataType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    data_type_custom = Column(String(100))
    byte_order = Column(SQLEnum(ByteOrder, values_callable=lambda x: [e.value for e in x]), default=ByteOrder.BIG_ENDIAN)
    word_number = Column(Integer)
    byte_offset = Column(Integer)
    bit_offset = Column(Integer)
    bit_length = Column(Integer, nullable=False)
    unit_of_measure = Column(String(50))
    scale_factor = Column(Float, default=1.0)
    offset_value = Column(Float, default=0.0)
    lsb_value = Column(Float)
    min_value = Column(Float)
    max_value = Column(Float)
    resolution = Column(Float)
    accuracy = Column(Float)
    default_value = Column(String(50))
    initial_value = Column(String(50))
    invalid_value = Column(String(50))
    stale_timeout_ms = Column(Float)
    enum_values = Column(JSON)
    bit_mask = Column(String(20))
    field_order = Column(Integer)
    is_padding = Column(Boolean, default=False)
    is_spare = Column(Boolean, default=False)
    notes = Column(Text, default="")

    # Foreign keys
    message_id = Column(Integer, ForeignKey("message_definitions.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    message = relationship("MessageDefinition", back_populates="fields")


# ── 9. WireHarness ──

class WireHarness(Base):
    __tablename__ = "wire_harnesses"

    id = Column(Integer, primary_key=True, index=True)
    harness_id = Column(String(30))
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    cable_type = Column(String(100))
    cable_spec = Column(String(100))
    cable_part_number = Column(String(100))
    cable_manufacturer = Column(String(255))
    overall_length_m = Column(Float)
    overall_length_max_m = Column(Float)
    mass_kg = Column(Float)
    outer_diameter_mm = Column(Float)
    jacket_material = Column(SQLEnum(CableJacketMaterial, values_callable=lambda x: [e.value for e in x]))
    jacket_material_custom = Column(String(100))
    jacket_color = Column(String(30))
    temp_rating_min_c = Column(Float)
    temp_rating_max_c = Column(Float)
    voltage_rating_v = Column(Float)
    bend_radius_min_mm = Column(Float)
    shield_type = Column(SQLEnum(ShieldType, values_callable=lambda x: [e.value for e in x]))
    shield_coverage_pct = Column(Float)
    shield_material = Column(String(50))
    overall_shield_termination = Column(String(100))
    conductor_count = Column(Integer)
    pair_count = Column(Integer)
    status = Column(SQLEnum(HarnessStatus, values_callable=lambda x: [e.value for e in x]), default=HarnessStatus.CONCEPT)
    drawing_number = Column(String(50))
    drawing_revision = Column(String(10))
    approved_by = Column(String(100))
    approval_date = Column(DateTime)

    # Foreign keys
    from_unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    from_connector_id = Column(Integer, ForeignKey("connectors.id"), nullable=False)
    to_unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    to_connector_id = Column(Integer, ForeignKey("connectors.id"), nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    wires = relationship("Wire", back_populates="harness", cascade="all, delete-orphan")
    from_unit = relationship("Unit", foreign_keys=[from_unit_id])
    from_connector = relationship("Connector", foreign_keys=[from_connector_id])
    to_unit = relationship("Unit", foreign_keys=[to_unit_id])
    to_connector = relationship("Connector", foreign_keys=[to_connector_id])

    __table_args__ = (
        UniqueConstraint("from_connector_id", "to_connector_id", name="uq_harness_connectors"),
    )


# ── 10. Wire ──

class Wire(Base):
    __tablename__ = "wires"

    id = Column(Integer, primary_key=True, index=True)
    wire_number = Column(String(20), nullable=False)
    signal_name = Column(String(150), nullable=False)
    wire_gauge = Column(SQLEnum(WireGauge, values_callable=lambda x: [e.value for e in x]))
    wire_gauge_custom = Column(String(10))
    wire_color_primary = Column(String(30))
    wire_color_secondary = Column(String(30))
    wire_color_tertiary = Column(String(30))
    wire_type = Column(SQLEnum(WireType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    wire_type_custom = Column(String(100))
    wire_spec = Column(String(80))
    wire_material = Column(String(50))
    insulation_material = Column(String(50))
    insulation_color = Column(String(30))
    length_m = Column(Float)
    length_max_m = Column(Float)

    # Foreign keys
    from_pin_id = Column(Integer, ForeignKey("pins.id"), nullable=False)
    to_pin_id = Column(Integer, ForeignKey("pins.id"), nullable=False)
    harness_id = Column(Integer, ForeignKey("wire_harnesses.id"), nullable=False)
    splice_info = Column(String(100))
    termination_from = Column(String(50))
    termination_to = Column(String(50))
    heat_shrink = Column(Boolean, default=False)
    heat_shrink_size = Column(String(20))
    notes = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    from_pin = relationship("Pin", foreign_keys=[from_pin_id])
    to_pin = relationship("Pin", foreign_keys=[to_pin_id])
    harness = relationship("WireHarness", back_populates="wires")

    __table_args__ = (
        UniqueConstraint("harness_id", "wire_number", name="uq_wire_number"),
        Index("ix_wire_from_pin", "from_pin_id"),
        Index("ix_wire_to_pin", "to_pin_id"),
        Index("ix_wire_signal_name", "signal_name"),
    )


# ── 11. Interface ──

class Interface(Base):
    __tablename__ = "interfaces"

    id = Column(Integer, primary_key=True, index=True)
    interface_id = Column(String(30))
    name = Column(String(255), nullable=False)
    description = Column(Text, default="")
    interface_type = Column(SQLEnum(InterfaceType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    interface_type_custom = Column(String(100))
    direction = Column(SQLEnum(InterfaceDirection, values_callable=lambda x: [e.value for e in x]), nullable=False)
    source_system_id = Column(Integer, ForeignKey("systems.id"), nullable=False)
    target_system_id = Column(Integer, ForeignKey("systems.id"), nullable=False)
    status = Column(SQLEnum(InterfaceStatus, values_callable=lambda x: [e.value for e in x]), default=InterfaceStatus.PROPOSED)
    criticality = Column(SQLEnum(InterfaceCriticality, values_callable=lambda x: [e.value for e in x]), default=InterfaceCriticality.NON_CRITICAL)
    icd_document_number = Column(String(100))
    icd_document_revision = Column(String(20))
    icd_section = Column(String(50))
    version = Column(Integer, default=1)
    data_rate_aggregate = Column(String(30))
    latency_requirement_ms = Column(Float)
    availability_requirement_pct = Column(Float)
    notes = Column(Text, default="")
    metadata_json = Column(JSON, default={})

    # Foreign keys
    project_id = Column(Integer, ForeignKey("projects.id"))
    owner_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    source_system = relationship("System", foreign_keys=[source_system_id])
    target_system = relationship("System", foreign_keys=[target_system_id])
    owner = relationship("User")


# ── 12. UnitEnvironmentalSpec ──

class UnitEnvironmentalSpec(Base):
    __tablename__ = "unit_environmental_specs"

    id = Column(Integer, primary_key=True, index=True)
    unit_id = Column(Integer, ForeignKey("units.id"), nullable=False)
    category = Column(SQLEnum(EnvironmentalCategory, values_callable=lambda x: [e.value for e in x]), nullable=False)
    standard = Column(SQLEnum(EnvironmentalStandard, values_callable=lambda x: [e.value for e in x]))
    standard_custom = Column(String(100))
    test_method = Column(String(100))
    test_level = Column(String(100))
    limit_value = Column(Float)
    limit_unit = Column(String(30))
    limit_min = Column(Float)
    limit_max = Column(Float)
    frequency_range = Column(String(50))
    duration = Column(String(50))
    test_condition = Column(Text)
    compliance_status = Column(String(20), default="untested")
    test_report_ref = Column(String(100))
    notes = Column(Text, default="")
    auto_generated = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    unit = relationship("Unit")

    __table_args__ = (
        Index("ix_env_spec_unit_cat", "unit_id", "category"),
    )


# ── 13. InterfaceRequirementLink ──

class InterfaceRequirementLink(Base):
    __tablename__ = "interface_requirement_links"

    id = Column(Integer, primary_key=True, index=True)
    entity_type = Column(SQLEnum(InterfaceEntityType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    entity_id = Column(Integer, nullable=False)
    requirement_id = Column(Integer, ForeignKey("requirements.id"), nullable=False)
    link_type = Column(SQLEnum(InterfaceLinkType, values_callable=lambda x: [e.value for e in x]), nullable=False)
    link_type_custom = Column(String(100))
    description = Column(Text, default="")
    auto_generated = Column(Boolean, default=False)
    auto_req_source = Column(SQLEnum(AutoReqSource, values_callable=lambda x: [e.value for e in x]))
    auto_req_template = Column(String(50))
    confidence_score = Column(Float)
    status = Column(SQLEnum(AutoReqStatus, values_callable=lambda x: [e.value for e in x]), default=AutoReqStatus.PENDING_REVIEW)
    reviewed_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    created_by_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    requirement = relationship("Requirement")
    reviewed_by = relationship("User", foreign_keys=[reviewed_by_id])
    created_by = relationship("User", foreign_keys=[created_by_id])

    __table_args__ = (
        Index("ix_ifl_entity", "entity_type", "entity_id"),
        Index("ix_ifl_requirement", "requirement_id"),
        Index("ix_ifl_auto_status", "auto_generated", "status"),
    )


# ── 14. AutoRequirementLog ──

class AutoRequirementLog(Base):
    __tablename__ = "auto_requirement_logs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    trigger_entity_type = Column(String(30))
    trigger_entity_id = Column(Integer)
    trigger_action = Column(String(20))
    requirements_generated = Column(Integer)
    verifications_generated = Column(Integer)
    links_generated = Column(Integer)
    template_used = Column(String(50))
    generation_summary = Column(JSON)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("Project")
    user = relationship("User")

    __table_args__ = (
        Index("ix_autoreq_project_date", "project_id", "created_at"),
    )


# ── 15. InterfaceChangeImpact ──

class InterfaceChangeImpact(Base):
    __tablename__ = "interface_change_impacts"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    change_type = Column(String(30))
    entity_type = Column(String(30))
    entity_id = Column(Integer)
    entity_description = Column(String(255))
    affected_requirements = Column(JSON)
    affected_verifications = Column(JSON)
    risk_level = Column(String(20))
    total_affected = Column(Integer)
    user_action = Column(String(30))
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)
    user_id = Column(Integer, ForeignKey("users.id"))
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("Project")
    user = relationship("User")

    __table_args__ = (
        Index("ix_ici_project_date", "project_id", "created_at"),
        Index("ix_ici_resolved", "resolved"),
    )
