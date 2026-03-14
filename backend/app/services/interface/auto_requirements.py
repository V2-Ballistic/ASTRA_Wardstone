"""
ASTRA — Interface Module Auto-Requirement Generation Engine
================================================================
File: backend/app/services/interface/auto_requirements.py
Path: C:\\Users\\Mason\\Documents\\ASTRA\\backend\\app\\services\\interface\\auto_requirements.py

Generates NASA Appendix C compliant requirements from interface definitions.
Called when wires are created, units imported, or bus/message definitions wired.

10 requirement templates + matching verification templates.
All generated requirements pass through the standard quality checker,
are linked to source entities via InterfaceRequirementLink, and start
as 'pending_review' status for engineer review on the Auto Requirements page.
"""

import re
import logging
from typing import List, Optional
from datetime import datetime

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import (
    User, Project, Requirement, RequirementHistory, Verification,
)
from app.models.interface import (
    System, Unit, Connector, Pin, BusDefinition,
    PinBusAssignment, MessageDefinition, MessageField,
    WireHarness, Wire, Interface,
    UnitEnvironmentalSpec, InterfaceRequirementLink,
    AutoRequirementLog,
)
from app.services.quality_checker import check_requirement_quality, generate_requirement_id

logger = logging.getLogger("astra.interface.auto_req")


def _ev(v) -> str:
    return v.value if hasattr(v, "value") else str(v) if v else ""


# ══════════════════════════════════════════════════════════════
#  Requirement Templates (10)
# ══════════════════════════════════════════════════════════════

TEMPLATES = {
    "bus_connection": {
        "level": "L3",
        "req_type": "interface",
        "priority_map": {
            "mil_std_1553a": "high", "mil_std_1553b": "high",
            "spacewire": "high", "spacewire_rmap": "high",
            "ethernet_1000base_t": "high", "ethernet_1000base_sx": "high",
            "ethernet_100base_tx": "high", "arinc_429": "high",
            "can_2b": "medium", "canfd": "medium",
            "rs422": "medium", "rs422_differential": "medium",
            "rs485": "medium", "spi_mode0": "medium",
            "i2c_standard": "low", "i2c_fast": "low",
            "discrete_28v": "low", "analog_4_20ma": "low",
        },
        "statement": (
            "The {source_system} shall {direction_verb} {data_description} "
            "{preposition} the {target_system} via {protocol_display} "
            "{bus_network_name} at a data rate of {data_rate}."
        ),
        "rationale": (
            "Auto-generated from wire harness {harness_id} connecting "
            "{source_unit} ({source_connector}) to {target_unit} ({target_connector}). "
            "Bus: {bus_def_id} ({protocol}), Role: {bus_role}, Address: {bus_address}."
        ),
        "title": "{protocol_short} Data Link — {source_abbrev} to {target_abbrev}",
    },
    "message": {
        "level": "L4",
        "req_type": "interface",
        "statement": (
            "The {unit_name} shall {direction_verb} the {msg_label} message "
            "({msg_mnemonic}) on {protocol_display} {bus_detail} at a rate of "
            "{rate_hz} Hz with a maximum latency of {latency_max_ms} milliseconds."
        ),
        "rationale": (
            "Auto-generated from message definition {msg_def_id} on bus {bus_def_id}. "
            "Message contains {field_count} data field(s) in {word_count} word(s) "
            "({total_bits} bits). Scheduling: {scheduling}."
        ),
        "title": "{msg_mnemonic} Message — {unit_designation}",
    },
    "message_field": {
        "level": "L4",
        "req_type": "interface",
        "statement": (
            "The {msg_label} message shall include the {field_label} ({field_name}) "
            "parameter as a {data_type_display} occupying {position_description} "
            "with a valid range of {min_value} to {max_value} {unit_of_measure}."
        ),
        "rationale": (
            "Auto-generated from field definition in message {msg_def_id}. "
            "Scale factor: {scale_factor}, offset: {offset_value}, "
            "LSB: {lsb_value} {unit_of_measure}. Resolution: {resolution}."
        ),
        "title": "{msg_mnemonic}.{field_name} — Field Definition",
    },
    "message_field_enum": {
        "level": "L4",
        "req_type": "interface",
        "statement": (
            "The {msg_label} message shall include the {field_label} ({field_name}) "
            "parameter as a {bit_length}-bit enumerated value in {position_description} "
            "with the following defined states: {enum_states_formatted}."
        ),
        "rationale": (
            "Auto-generated from enumerated field in message {msg_def_id}. "
            "{enum_count} discrete states defined."
        ),
        "title": "{msg_mnemonic}.{field_name} — Enum Definition",
    },
    "power_wire": {
        "level": "L4",
        "req_type": "interface",
        "statement": (
            "Wire harness {harness_id} shall provide {voltage} {power_description} "
            "from the {source_unit} to the {target_unit} via {wire_gauge} AWG "
            "{wire_spec_or_material} conductor with a maximum current capacity of "
            "{current_max} A."
        ),
        "rationale": (
            "Auto-generated from wire {wire_number} in harness {harness_id}. "
            "Connection: {from_conn}:{from_pin_number} to {to_conn}:{to_pin_number}. "
            "Signal: {signal_name}, Type: {wire_type}."
        ),
        "title": "{voltage} Power — {source_abbrev} to {target_abbrev}",
    },
    "ground_wire": {
        "level": "L4",
        "req_type": "interface",
        "statement": (
            "Wire harness {harness_id} shall provide {ground_type} ground return "
            "from the {source_unit} to the {target_unit} via {wire_gauge} AWG "
            "conductor on {from_conn} pin {from_pin_number} to {to_conn} "
            "pin {to_pin_number}."
        ),
        "rationale": (
            "Auto-generated from ground wire {wire_number} in harness {harness_id}. "
            "Ground type: {ground_type}. Signal: {signal_name}."
        ),
        "title": "{ground_type} Ground — {source_abbrev} to {target_abbrev}",
    },
    "discrete_signal": {
        "level": "L4",
        "req_type": "interface",
        "statement": (
            "The {source_unit} shall provide the {signal_name} discrete {signal_subtype} "
            "signal to the {target_unit} as a {voltage_level} logic-level "
            "{direction_display} on {from_conn} pin {from_pin_number}."
        ),
        "rationale": (
            "Auto-generated from discrete wire {wire_number} in harness {harness_id}. "
            "Connection: {from_conn}:{from_pin_number} to {to_conn}:{to_pin_number}."
        ),
        "title": "{signal_name} Discrete — {source_abbrev} to {target_abbrev}",
    },
    "rf_connection": {
        "level": "L4",
        "req_type": "interface",
        "statement": (
            "The {source_unit} shall provide the {signal_name} RF signal to the "
            "{target_unit} at {frequency_display} via {cable_type} coaxial cable "
            "with a characteristic impedance of {impedance} ohms and maximum "
            "insertion loss of {insertion_loss_db} dB."
        ),
        "rationale": (
            "Auto-generated from RF wire {wire_number} in harness {harness_id}. "
            "Cable: {cable_spec}. Connector type: {connector_type}."
        ),
        "title": "{signal_name} RF — {source_abbrev} to {target_abbrev}",
    },
    "shield_grounding": {
        "level": "L5",
        "req_type": "interface",
        "statement": (
            "Wire harness {harness_id} cable shield shall be terminated at the "
            "{termination_end} end via {termination_method} to provide EMI "
            "protection for {protected_signals} signals."
        ),
        "rationale": (
            "Auto-generated from shield wire {wire_number} in harness {harness_id}. "
            "Shield type: {shield_type}. Coverage: {shield_coverage}%."
        ),
        "title": "Shield Termination — {harness_id}",
    },
    "harness_overall": {
        "level": "L3",
        "req_type": "interface",
        "statement": (
            "Wire harness {harness_id} shall interconnect the {source_unit} "
            "{from_conn} to the {target_unit} {to_conn} using {cable_spec} "
            "cable with an overall length not to exceed {max_length} meters."
        ),
        "rationale": (
            "Auto-generated from wire harness {harness_id} definition. "
            "{wire_count} conductors, {pair_count} twisted pairs. "
            "Cable type: {cable_type}. Shield: {shield_type}."
        ),
        "title": "Harness {harness_id} — {source_abbrev} to {target_abbrev}",
    },
}


# ══════════════════════════════════════════════════════════════
#  Verification Templates (7 — grouped by inspection type)
# ══════════════════════════════════════════════════════════════

VERIFICATION_TEMPLATES = {
    "bus_connection": {
        "method": "test",
        "criteria": (
            "Using a {protocol} bus analyzer, verify that {source_unit} "
            "communicates with {target_unit} on {bus_network_name} at {data_rate}. "
            "Confirm: (1) bus initialization completes without errors, "
            "(2) no bus errors over a 60-second monitoring period, "
            "(3) message throughput meets rate requirements."
        ),
    },
    "message": {
        "method": "test",
        "criteria": (
            "Verify {msg_label} ({msg_mnemonic}) is {direction_verb_past} at "
            "{rate_hz} Hz ±5%. Record 1000 consecutive message cycles. Confirm: "
            "(1) all {field_count} fields populated, (2) no data dropouts, "
            "(3) latency within {latency_max_ms} ms, (4) all field values within "
            "defined valid ranges."
        ),
    },
    "message_field": {
        "method": "analysis",
        "criteria": (
            "Review ICD and software design documents. Verify {field_name} is "
            "encoded as {data_type_display} in {position_description} with "
            "scale factor {scale_factor} and offset {offset_value}. Confirm "
            "valid range [{min_value}, {max_value}] {unit_of_measure} is "
            "correctly implemented in both transmitter and receiver."
        ),
    },
    "power_wire": {
        "method": "inspection",
        "criteria": (
            "Inspect wire harness {harness_id}. Verify: (1) wire {wire_number} "
            "is {wire_gauge} AWG as specified, (2) connected from {from_conn}:"
            "{from_pin_number} to {to_conn}:{to_pin_number}, (3) crimp "
            "terminations pass MIL-STD-1344 pull test, (4) continuity confirmed "
            "with resistance < 0.5 ohms."
        ),
    },
    "discrete_signal": {
        "method": "test",
        "criteria": (
            "With {source_unit} powered and commanding {signal_name} active, "
            "verify: (1) signal present at {to_conn}:{to_pin_number} on "
            "{target_unit}, (2) voltage level is {voltage_level} ±10%, "
            "(3) rise/fall time within specification, (4) signal correctly "
            "read by {target_unit} software."
        ),
    },
    "rf_connection": {
        "method": "test",
        "criteria": (
            "Using a network analyzer, measure S-parameters of {harness_id} "
            "RF path from {from_conn} to {to_conn}. Verify: (1) insertion "
            "loss < {insertion_loss_db} dB at {frequency_display}, "
            "(2) return loss > 14 dB (VSWR < 1.5:1), (3) impedance "
            "{impedance} ±5 ohms."
        ),
    },
    "harness_overall": {
        "method": "inspection",
        "criteria": (
            "Inspect wire harness {harness_id} per drawing {drawing_number}. "
            "Verify: (1) all {wire_count} conductors present and correctly "
            "terminated, (2) overall length within specification, (3) shield "
            "continuity < 2.5 milliohms, (4) hipot test: {voltage_rating}V "
            "for 60 seconds, no breakdown."
        ),
    },
}


# ══════════════════════════════════════════════════════════════
#  Environmental Templates (11) — per MIL-STD-810H
# ══════════════════════════════════════════════════════════════

ENV_TEMPLATES = {
    "temp_operating": {
        "category": "temperature_operating",
        "level": "L4", "req_type": "environmental", "priority": "high",
        "standard": "MIL-STD-810H",
        "test_method": "Method 501.7/502.7",
        "statement": (
            "The {unit_name} ({unit_designation}) shall operate within all performance "
            "specifications over an ambient temperature range of {min_val}°C to "
            "{max_val}°C per {standard} {test_method}."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Subject {unit_designation} to temperature cycling from {min_val}°C to "
            "{max_val}°C per {standard} {test_method}. Dwell 2 hours at each extreme. "
            "Monitor all performance parameters throughout. Pass: all parameters "
            "within specification at temperature extremes."
        ),
    },
    "temp_storage": {
        "category": "temperature_storage",
        "level": "L4", "req_type": "environmental", "priority": "medium",
        "standard": "MIL-STD-810H",
        "test_method": "Method 501.7/502.7 Procedure III",
        "statement": (
            "The {unit_name} ({unit_designation}) shall survive non-operating storage "
            "temperatures from {min_val}°C to {max_val}°C without performance "
            "degradation upon return to operating temperature."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Store {unit_designation} at {min_val}°C and {max_val}°C for 24 hours each. "
            "Return to ambient and perform full functional test. Pass: all parameters "
            "meet specification."
        ),
    },
    "vibration_random": {
        "category": "vibration_random",
        "level": "L4", "req_type": "environmental", "priority": "high",
        "standard": "MIL-STD-810H",
        "test_method": "Method 514.8",
        "statement": (
            "The {unit_name} ({unit_designation}) shall operate within specification "
            "when subjected to random vibration of {val} Grms per {standard} "
            "{test_method} in each of three mutually perpendicular axes."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Mount {unit_designation} on vibration table. Apply {val} Grms random "
            "vibration spectrum per {standard} {test_method} for 1 hour per axis "
            "(3 axes). Monitor performance throughout. Inspect for damage after."
        ),
    },
    "vibration_sine": {
        "category": "vibration_sinusoidal",
        "level": "L4", "req_type": "environmental", "priority": "medium",
        "standard": "MIL-STD-810H",
        "test_method": "Method 528",
        "statement": (
            "The {unit_name} ({unit_designation}) shall operate within specification "
            "when subjected to sinusoidal vibration of {val}g peak per {standard} "
            "{test_method}."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Perform sine sweep {val}g peak per {standard} {test_method}. "
            "Record resonant frequencies. Monitor performance throughout."
        ),
    },
    "shock_mechanical": {
        "category": "shock_mechanical",
        "level": "L4", "req_type": "environmental", "priority": "high",
        "standard": "MIL-STD-810H",
        "test_method": "Method 516.8",
        "statement": (
            "The {unit_name} ({unit_designation}) shall withstand mechanical shock "
            "of {val}g peak, {duration}ms duration per {standard} {test_method} "
            "without damage or performance degradation."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Apply {val}g {duration}ms half-sine shock per {standard} {test_method} "
            "in each of 6 directions (±X, ±Y, ±Z). 3 shocks per direction. "
            "Functional test before and after. Visual inspection for damage."
        ),
    },
    "shock_pyrotechnic": {
        "category": "shock_pyrotechnic",
        "level": "L4", "req_type": "environmental", "priority": "critical",
        "standard": "MIL-STD-810H",
        "test_method": "Method 517.4",
        "statement": (
            "The {unit_name} ({unit_designation}) shall withstand pyroshock of "
            "{val}g peak per {standard} {test_method} without damage."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Apply pyroshock {val}g SRS per {standard} {test_method}. "
            "Full functional test before and after."
        ),
    },
    "acceleration": {
        "category": "acceleration_sustained",
        "level": "L4", "req_type": "environmental", "priority": "medium",
        "standard": "MIL-STD-810H",
        "test_method": "Method 513.8",
        "statement": (
            "The {unit_name} ({unit_designation}) shall operate within specification "
            "when subjected to sustained acceleration of {val}g per {standard} "
            "{test_method}."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Apply {val}g sustained acceleration per {standard} {test_method}. "
            "Monitor performance throughout."
        ),
    },
    "humidity": {
        "category": "humidity",
        "level": "L4", "req_type": "environmental", "priority": "medium",
        "standard": "MIL-STD-810H",
        "test_method": "Method 507.6",
        "statement": (
            "The {unit_name} ({unit_designation}) shall operate within specification "
            "at relative humidity levels from {min_val}% to {max_val}% "
            "non-condensing per {standard} {test_method}."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Subject {unit_designation} to humidity cycling per {standard} "
            "{test_method}. 10 cycles, {max_val}% RH at 60°C. Functional "
            "test during and after."
        ),
    },
    "altitude": {
        "category": "altitude",
        "level": "L4", "req_type": "environmental", "priority": "medium",
        "standard": "MIL-STD-810H",
        "test_method": "Method 500.6",
        "statement": (
            "The {unit_name} ({unit_designation}) shall operate within specification "
            "at altitudes up to {val} meters above mean sea level per {standard} "
            "{test_method}."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Place {unit_designation} in altitude chamber. Reduce pressure to "
            "equivalent of {val}m altitude. Operate for 2 hours. "
            "Full functional test."
        ),
    },
    "sand_dust": {
        "category": "sand_dust",
        "level": "L4", "req_type": "environmental", "priority": "low",
        "standard": "MIL-STD-810H",
        "test_method": "Method 510.7",
        "statement": (
            "The {unit_name} ({unit_designation}) shall operate without degradation "
            "after exposure to blowing sand and dust per {standard} {test_method}."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Expose {unit_designation} to blowing sand/dust per {standard} "
            "{test_method} Procedure I. Functional test after."
        ),
    },
    "salt_fog": {
        "category": "salt_fog",
        "level": "L4", "req_type": "environmental", "priority": "low",
        "standard": "MIL-STD-810H",
        "test_method": "Method 509.7",
        "statement": (
            "The {unit_name} ({unit_designation}) shall resist corrosion from "
            "salt fog exposure per {standard} {test_method} for 48 hours."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Expose {unit_designation} to 5% NaCl salt fog per {standard} "
            "{test_method} for 48 hours. Inspect for corrosion. Functional test."
        ),
    },
}


# ══════════════════════════════════════════════════════════════
#  EMI Templates (6) — per MIL-STD-461G
# ══════════════════════════════════════════════════════════════

EMI_TEMPLATES = {
    "ce102": {
        "category": "emi_ce102",
        "level": "L4", "req_type": "environmental", "priority": "high",
        "standard": "MIL-STD-461G",
        "test_method": "CE102",
        "statement": (
            "The {unit_name} ({unit_designation}) shall not produce conducted "
            "emissions exceeding {val} dBuA on power input leads over the "
            "frequency range 10 kHz to 10 MHz per {standard} {test_method}."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Perform CE102 per {standard}. Measure conducted emissions on all "
            "power leads from 10 kHz to 10 MHz using LISN. Limit: {val} dBuA. "
            "3 dB below limit is passing."
        ),
    },
    "re102": {
        "category": "emi_re102",
        "level": "L4", "req_type": "environmental", "priority": "high",
        "standard": "MIL-STD-461G",
        "test_method": "RE102",
        "statement": (
            "The {unit_name} ({unit_designation}) shall not produce radiated "
            "electric field emissions exceeding {val} dBuV/m over the frequency "
            "range 10 kHz to 18 GHz per {standard} {test_method}."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Perform RE102 per {standard}. Measure radiated emissions at 1m "
            "distance from 10 kHz to 18 GHz. Limit: {val} dBuV/m."
        ),
    },
    "cs114": {
        "category": "emi_cs114",
        "level": "L4", "req_type": "environmental", "priority": "high",
        "standard": "MIL-STD-461G",
        "test_method": "CS114",
        "statement": (
            "The {unit_name} ({unit_designation}) shall operate without "
            "degradation when subjected to bulk cable injection of {val} dBA "
            "over the frequency range 10 kHz to 200 MHz per {standard} "
            "{test_method}."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Perform CS114 per {standard}. Inject calibrated levels on all "
            "cables from 10 kHz to 200 MHz. Monitor all {unit_designation} "
            "outputs throughout. Pass: no degradation."
        ),
    },
    "rs103": {
        "category": "emi_rs103",
        "level": "L4", "req_type": "environmental", "priority": "high",
        "standard": "MIL-STD-461G",
        "test_method": "RS103",
        "statement": (
            "The {unit_name} ({unit_designation}) shall operate without "
            "degradation when subjected to radiated electric fields of "
            "{val} V/m over the frequency range 2 MHz to 18 GHz per "
            "{standard} {test_method}."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Perform RS103 per {standard}. Illuminate {unit_designation} "
            "with {val} V/m E-field from 2 MHz to 18 GHz. Full sweep with "
            "1-second dwell. Monitor all outputs. Pass: no degradation."
        ),
    },
    "esd": {
        "category": "esd_hbm",
        "level": "L4", "req_type": "environmental", "priority": "medium",
        "standard": "MIL-STD-461G / IEC 61000-4-2",
        "test_method": "ESD",
        "statement": (
            "The {unit_name} ({unit_designation}) shall withstand electrostatic "
            "discharge of {val} V (Human Body Model) applied to all accessible "
            "surfaces and connector shells without damage or upset per "
            "{standard}."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Apply {val}V HBM ESD to all accessible points per IEC 61000-4-2. "
            "10 discharges per point, both polarities. Monitor {unit_designation} "
            "throughout. Pass: no permanent damage; transient upset recovery "
            "within 1 second."
        ),
    },
    "radiation_tid": {
        "category": "radiation_total_dose",
        "level": "L4", "req_type": "environmental", "priority": "critical",
        "standard": "MIL-STD-883 TM 1019",
        "test_method": "TM 1019.9",
        "statement": (
            "The {unit_name} ({unit_designation}) shall operate within all "
            "performance specifications after exposure to a total ionizing dose "
            "of {val} krad(Si) per {standard} {test_method}."
        ),
        "verification_method": "test",
        "verification_criteria": (
            "Irradiate {unit_designation} components to {val} krad(Si) per "
            "{standard} {test_method}. Dose rate: 50-300 rad(Si)/s. "
            "Full parametric test before and after irradiation. "
            "Anneal test per specification if applicable."
        ),
    },
}


# ══════════════════════════════════════════════════════════════
#  Field-to-Template Mapping (unit model fields → template keys)
# ══════════════════════════════════════════════════════════════

FIELD_TO_TEMPLATE = {
    # Environmental — range fields (min, max)
    ("temp_operating_min_c", "temp_operating_max_c"): ("temp_operating", "env"),
    ("temp_storage_min_c", "temp_storage_max_c"): ("temp_storage", "env"),
    ("humidity_min_pct", "humidity_max_pct"): ("humidity", "env"),
    # Environmental — single value fields
    ("vibration_random_grms",): ("vibration_random", "env"),
    ("vibration_sine_g_peak",): ("vibration_sine", "env"),
    ("shock_mechanical_g",): ("shock_mechanical", "env"),
    ("shock_pyrotechnic_g",): ("shock_pyrotechnic", "env"),
    ("acceleration_max_g",): ("acceleration", "env"),
    ("altitude_operating_max_m",): ("altitude", "env"),
    # EMI — single value fields
    ("emi_ce102_limit_dbua",): ("ce102", "emi"),
    ("emi_re102_limit_dbm",): ("re102", "emi"),
    ("emi_cs114_limit_dba",): ("cs114", "emi"),
    ("emi_rs103_limit_vm",): ("rs103", "emi"),
    ("esd_hbm_v",): ("esd", "emi"),
    ("radiation_tid_krad",): ("radiation_tid", "emi"),
}

# Boolean flag fields that trigger requirements
BOOL_FLAG_TEMPLATES = {
    "sand_dust_exposed": ("sand_dust", "env"),
    "salt_fog_exposed": ("salt_fog", "env"),
}

# Spec fields that are relevant for env/EMI (used by on_unit_updated)
ENV_EMI_FIELDS = set()
for field_tuple in FIELD_TO_TEMPLATE:
    ENV_EMI_FIELDS.update(field_tuple)
ENV_EMI_FIELDS.update(BOOL_FLAG_TEMPLATES.keys())


# ══════════════════════════════════════════════════════════════
#  AutoRequirementGenerator
# ══════════════════════════════════════════════════════════════

class AutoRequirementGenerator:
    """
    Generates traceable requirements from interface definitions.

    All generated requirements:
    - Use NASA Appendix C compliant SHALL statements
    - Pass through the standard quality checker
    - Are linked to source entities via InterfaceRequirementLink
    - Start as 'draft' status for engineer review
    - Have rationale starting with "Auto-generated from..."
    """

    def __init__(self, db: Session, project_id: int, user: User):
        self.db = db
        self.project_id = project_id
        self.user = user
        self.generated_reqs: List[Requirement] = []
        self.generated_verifs: List[Verification] = []
        self.generated_links: List[InterfaceRequirementLink] = []
        self._req_count_cache: Optional[int] = None

    # ══════════════════════════════════════
    #  Public entry points
    # ══════════════════════════════════════

    def on_wires_created(self, harness: WireHarness, wires: List[Wire]) -> dict:
        """Main entry: called after wires are successfully created."""

        classified = self._classify_wires(wires)

        # L3 harness-level requirement
        if len(wires) >= 2:
            self._gen_harness_overall(harness, wires)

        # L3 bus connection + L4 messages + L4/L5 fields
        for bus_def_id, (bus_def, bus_wires) in classified["bus_groups"].items():
            l3 = self._gen_bus_connection(harness, bus_def, bus_wires)
            if l3:
                for msg in self._get_messages(bus_def.id):
                    l4 = self._gen_message(harness, bus_def, msg, parent=l3)
                    if l4:
                        for field in self._get_fields(msg.id):
                            if _ev(field.data_type) == "enum_coded" and field.enum_values:
                                self._gen_field_enum(msg, field, parent=l4)
                            elif not field.is_padding and not field.is_spare:
                                self._gen_field(msg, field, parent=l4)

        # L4 wire-type specific requirements
        for wire in classified["power"]:
            self._gen_power_wire(harness, wire)

        for wire in classified["ground"]:
            self._gen_ground_wire(harness, wire)

        for wire in classified["discrete"]:
            self._gen_discrete_signal(harness, wire)

        for wire in classified["rf"]:
            self._gen_rf_connection(harness, wire)

        # L5 shield requirements
        for wire in classified["shield"]:
            self._gen_shield(harness, wire)

        self._log_generation("wires_created", "wire_harness", harness.id, len(wires))
        self.db.flush()

        return {
            "requirements_generated": len(self.generated_reqs),
            "verifications_generated": len(self.generated_verifs),
            "links_generated": len(self.generated_links),
            "requirements": [
                {
                    "id": r.id, "req_id": r.req_id, "title": r.title,
                    "level": _ev(r.level), "statement": r.statement[:120],
                    "quality_score": r.quality_score,
                }
                for r in self.generated_reqs
            ],
        }

    def on_wires_deleted(self, wires: List[Wire]) -> dict:
        """Preview impact of deleting wires. Called BEFORE deletion."""
        affected = self._find_affected_requirements(wires)
        risk = self._assess_risk(affected)
        return {
            "affected_requirements": len(affected),
            "risk_level": risk,
            "items": affected,
            "action_options": [
                "delete_requirements", "orphan_requirements",
                "mark_for_review", "cancel",
            ],
        }

    def execute_deletion_action(self, req_ids: List[int], action: str):
        """Execute user's chosen action on affected auto-requirements."""
        for req_id in req_ids:
            req = self.db.query(Requirement).filter(Requirement.id == req_id).first()
            if not req:
                continue
            if action == "delete_requirements":
                req.status = "deleted"
                self._record_history(
                    req, "status", _ev(req.status), "deleted",
                    "Auto-deleted: source interface entity removed",
                )
            elif action == "orphan_requirements":
                self.db.query(InterfaceRequirementLink).filter(
                    InterfaceRequirementLink.requirement_id == req_id,
                    InterfaceRequirementLink.auto_generated.is_(True),
                ).delete()
                self._record_history(
                    req, "interface_link", "linked", "orphaned",
                    "Interface link removed; requirement preserved as orphan",
                )
            elif action == "mark_for_review":
                req.status = "under_review"
                self._record_history(
                    req, "status", _ev(req.status), "under_review",
                    "Flagged for review: source interface entity changed",
                )
        self.db.flush()

    # ══════════════════════════════════════
    #  Environmental / EMI generation
    # ══════════════════════════════════════

    def on_unit_created(self, unit: Unit) -> dict:
        """Generate environmental and EMI requirements from unit specifications."""

        parent = self._find_or_create_env_parent(unit)

        # Iterate field-to-template mapping for range and single-value specs
        for field_tuple, (template_key, source) in FIELD_TO_TEMPLATE.items():
            values = [getattr(unit, f, None) for f in field_tuple]
            if not all(v is not None for v in values):
                continue

            tmpl = ENV_TEMPLATES.get(template_key) or EMI_TEMPLATES.get(template_key)
            if not tmpl:
                continue

            ctx = {
                "unit_name": unit.name,
                "unit_designation": unit.designation,
                "standard": tmpl["standard"],
                "test_method": tmpl["test_method"],
            }

            if len(values) == 2:
                ctx["min_val"] = values[0]
                ctx["max_val"] = values[1]
            else:
                ctx["val"] = values[0]

            # Special handling for shock duration
            if template_key == "shock_mechanical":
                ctx["duration"] = unit.shock_mechanical_duration_ms or 11

            self._gen_env_from_template(unit, tmpl, template_key, ctx, parent)

        # Boolean flag fields (sand/dust, salt fog)
        for flag_field, (template_key, source) in BOOL_FLAG_TEMPLATES.items():
            if getattr(unit, flag_field, False):
                tmpl = ENV_TEMPLATES.get(template_key)
                if not tmpl:
                    continue
                ctx = {
                    "unit_name": unit.name,
                    "unit_designation": unit.designation,
                    "standard": tmpl["standard"],
                    "test_method": tmpl["test_method"],
                }
                self._gen_env_from_template(unit, tmpl, template_key, ctx, parent)

        self._log_generation("unit_created", "unit", unit.id, 0)
        self.db.flush()

        env_count = sum(
            1 for r in self.generated_reqs if _ev(r.req_type) == "environmental"
        )

        return {
            "environmental_requirements": env_count,
            "total_generated": len(self.generated_reqs),
            "verifications_generated": len(self.generated_verifs),
            "links_generated": len(self.generated_links),
            "requirements": [
                {"id": r.id, "req_id": r.req_id, "title": r.title,
                 "level": _ev(r.level), "quality_score": r.quality_score}
                for r in self.generated_reqs
            ],
        }

    def on_unit_updated(self, unit: Unit, changed_fields: List[str]) -> dict:
        """Handle spec changes — update, regenerate, or flag affected requirements."""

        # Only process env/EMI-relevant field changes
        relevant_changes = [f for f in changed_fields if f in ENV_EMI_FIELDS]
        if not relevant_changes:
            return {"updated": 0, "created": 0, "flagged": 0}

        updated_count = 0
        created_count = 0
        flagged_count = 0

        # Find existing auto-generated env/emi requirements for this unit
        existing_links = self.db.query(InterfaceRequirementLink).filter(
            InterfaceRequirementLink.entity_type == "unit",
            InterfaceRequirementLink.entity_id == unit.id,
            InterfaceRequirementLink.auto_generated.is_(True),
        ).all()

        existing_by_template: dict = {}  # template_name → (link, requirement)
        for lk in existing_links:
            req = self.db.query(Requirement).filter(Requirement.id == lk.requirement_id).first()
            if req and lk.auto_req_template:
                existing_by_template[lk.auto_req_template] = (lk, req)

        parent = self._find_or_create_env_parent(unit)

        # Check each field-to-template mapping
        for field_tuple, (template_key, source) in FIELD_TO_TEMPLATE.items():
            # Check if any field in this tuple was changed
            if not any(f in relevant_changes for f in field_tuple):
                continue

            values = [getattr(unit, f, None) for f in field_tuple]
            tmpl = ENV_TEMPLATES.get(template_key) or EMI_TEMPLATES.get(template_key)
            if not tmpl:
                continue

            if template_key in existing_by_template:
                lk, existing_req = existing_by_template[template_key]
                if all(v is not None for v in values):
                    # Spec changed → regenerate statement
                    ctx = {
                        "unit_name": unit.name,
                        "unit_designation": unit.designation,
                        "standard": tmpl["standard"],
                        "test_method": tmpl["test_method"],
                    }
                    if len(values) == 2:
                        ctx["min_val"] = values[0]
                        ctx["max_val"] = values[1]
                    else:
                        ctx["val"] = values[0]
                    if template_key == "shock_mechanical":
                        ctx["duration"] = unit.shock_mechanical_duration_ms or 11

                    old_statement = existing_req.statement
                    new_statement = tmpl["statement"].format_map(_SafeDict(ctx))

                    if old_statement != new_statement:
                        self._record_history(
                            existing_req, "statement", old_statement[:80],
                            new_statement[:80],
                            f"Auto-updated: {template_key} spec changed on {unit.designation}",
                        )
                        existing_req.statement = new_statement
                        existing_req.version = (existing_req.version or 1) + 1
                        quality = check_requirement_quality(new_statement, existing_req.title or "", "")
                        existing_req.quality_score = quality["score"]
                        updated_count += 1
                else:
                    # Spec removed (set to None) → flag for review
                    existing_req.status = "under_review"
                    self._record_history(
                        existing_req, "status", _ev(existing_req.status), "under_review",
                        f"Flagged: {template_key} spec removed from {unit.designation}",
                    )
                    flagged_count += 1
            else:
                # New spec added → generate new requirement
                if all(v is not None for v in values):
                    ctx = {
                        "unit_name": unit.name,
                        "unit_designation": unit.designation,
                        "standard": tmpl["standard"],
                        "test_method": tmpl["test_method"],
                    }
                    if len(values) == 2:
                        ctx["min_val"] = values[0]
                        ctx["max_val"] = values[1]
                    else:
                        ctx["val"] = values[0]
                    if template_key == "shock_mechanical":
                        ctx["duration"] = unit.shock_mechanical_duration_ms or 11

                    self._gen_env_from_template(unit, tmpl, template_key, ctx, parent)
                    created_count += 1

        # Handle boolean flag changes
        for flag_field, (template_key, source) in BOOL_FLAG_TEMPLATES.items():
            if flag_field not in relevant_changes:
                continue
            flag_val = getattr(unit, flag_field, False)
            tmpl = ENV_TEMPLATES.get(template_key)
            if not tmpl:
                continue

            if template_key in existing_by_template:
                lk, existing_req = existing_by_template[template_key]
                if not flag_val:
                    # Flag turned off → flag requirement for review
                    existing_req.status = "under_review"
                    self._record_history(
                        existing_req, "status", _ev(existing_req.status), "under_review",
                        f"Flagged: {flag_field} disabled on {unit.designation}",
                    )
                    flagged_count += 1
            elif flag_val:
                # New flag turned on → generate
                ctx = {
                    "unit_name": unit.name,
                    "unit_designation": unit.designation,
                    "standard": tmpl["standard"],
                    "test_method": tmpl["test_method"],
                }
                self._gen_env_from_template(unit, tmpl, template_key, ctx, parent)
                created_count += 1

        self.db.flush()

        return {
            "updated": updated_count,
            "created": created_count,
            "flagged": flagged_count,
            "total_affected": updated_count + created_count + flagged_count,
        }

    def _gen_env_from_template(self, unit: Unit, tmpl: dict, template_key: str,
                               ctx: dict, parent: Optional[Requirement] = None):
        """Generate a single env/EMI requirement + verification + env spec record."""

        category_display = tmpl["category"].replace("_", " ").title()
        title = f"{unit.designation} — {category_display}"

        req = self._create_requirement(
            title=title,
            statement=tmpl["statement"].format_map(_SafeDict(ctx)),
            rationale=(
                f"Auto-generated from {unit.designation} specification. "
                f"Standard: {tmpl['standard']} {tmpl['test_method']}."
            ),
            level=tmpl["level"],
            priority=tmpl["priority"],
            parent_id=parent.id if parent else None,
            source_type="unit",
            source_id=unit.id,
            template_name="environmental_spec" if tmpl.get("standard", "").startswith("MIL-STD-810") else "emi_spec",
            req_type="environmental",
        )

        # Auto-verification
        vcriteria = tmpl["verification_criteria"].format_map(_SafeDict(ctx))
        self._create_verification(req, tmpl["verification_method"], vcriteria,
             "environmental_spec" if tmpl.get("standard", "").startswith("MIL-STD-810") else "emi_spec")
        # Map display standard to enum value
        std_display = tmpl.get("standard", "")
        std_enum_map = {
            "MIL-STD-810H": "mil_std_810h",
            "MIL-STD-810G": "mil_std_810g",
            "MIL-STD-461G": "mil_std_461g",
            "MIL-STD-461F": "mil_std_461f",
            "MIL-STD-464C": "mil_std_464c",
            "MIL-STD-883 TM 1019": "mil_hdbk_217f",
            "MIL-STD-461G / IEC 61000-4-2": "mil_std_461g",
        }
        std_value = std_enum_map.get(std_display, "custom")

        spec = UnitEnvironmentalSpec(
            unit_id=unit.id,
            category=tmpl["category"],
            standard=std_value,
            standard_custom=std_display if std_value == "custom" else None,
            test_method=tmpl.get("test_method"),
            limit_value=ctx.get("val"),
            limit_min=ctx.get("min_val"),
            limit_max=ctx.get("max_val"),
            auto_generated=True,
        )
        self.db.add(spec)

        return req

    def _find_or_create_env_parent(self, unit: Unit) -> Optional[Requirement]:
        """Find or create an L3 parent requirement for env/EMI specs on this unit."""

        # Look for existing env parent
        existing_link = self.db.query(InterfaceRequirementLink).filter(
            InterfaceRequirementLink.entity_type == "unit",
            InterfaceRequirementLink.entity_id == unit.id,
            InterfaceRequirementLink.auto_generated.is_(True),
            InterfaceRequirementLink.auto_req_template == "environmental_spec",
        ).first()

        if existing_link:
            return self.db.query(Requirement).filter(
                Requirement.id == existing_link.requirement_id
            ).first()

        # Create L3 parent
        system = self.db.query(System).filter(System.id == unit.system_id).first()
        sys_name = system.name if system else "System"

        req = self._create_requirement(
            title=f"{unit.designation} Environmental & EMI Qualification",
            statement=(
                f"The {unit.name} ({unit.designation}) shall meet all environmental "
                f"and electromagnetic interference qualification requirements as "
                f"specified in the unit environmental specification per MIL-STD-810H "
                f"and MIL-STD-461G."
            ),
            rationale=(
                f"Auto-generated parent requirement for {unit.designation} environmental "
                f"and EMI qualification. System: {sys_name}. All child requirements "
                f"derive from unit specification data."
            ),
            level="L3",
            priority="high",
            source_type="unit",
            source_id=unit.id,
            template_name="environmental_spec",
            req_type="environmental",
        )

        return req

    # ══════════════════════════════════════
    #  Wire classification
    # ══════════════════════════════════════

    def _classify_wires(self, wires: List[Wire]) -> dict:
        """Sort wires into categories for requirement generation."""
        result = {
            "bus_groups": {},  # bus_def_id → (bus_def, [wires])
            "power": [],
            "ground": [],
            "discrete": [],
            "rf": [],
            "shield": [],
            "other": [],
        }
        for wire in wires:
            from_pin = self.db.query(Pin).filter(Pin.id == wire.from_pin_id).first()
            to_pin = self.db.query(Pin).filter(Pin.id == wire.to_pin_id).first()
            if not from_pin or not to_pin:
                continue

            # Check bus assignments on either pin
            bus_assign = self.db.query(PinBusAssignment).filter(
                PinBusAssignment.pin_id.in_([from_pin.id, to_pin.id])
            ).first()

            sig = _ev(from_pin.signal_type)

            if bus_assign:
                bus_def = self.db.query(BusDefinition).filter(
                    BusDefinition.id == bus_assign.bus_def_id
                ).first()
                if bus_def:
                    if bus_def.id not in result["bus_groups"]:
                        result["bus_groups"][bus_def.id] = (bus_def, [])
                    result["bus_groups"][bus_def.id][1].append(wire)
            elif sig in ("power_primary", "power_secondary"):
                result["power"].append(wire)
            elif sig in ("power_return", "signal_ground", "chassis_ground"):
                result["ground"].append(wire)
            elif sig.startswith("discrete"):
                result["discrete"].append(wire)
            elif sig.startswith("rf") or sig == "coax_signal":
                result["rf"].append(wire)
            elif sig.startswith("shield"):
                result["shield"].append(wire)
            else:
                result["other"].append(wire)

        return result

    # ══════════════════════════════════════
    #  Core requirement creation pipeline
    # ══════════════════════════════════════

    def _create_requirement(
        self,
        title: str,
        statement: str,
        rationale: str,
        level: str,
        priority: str,
        parent_id: Optional[int] = None,
        source_type: Optional[str] = None,
        source_id: Optional[int] = None,
        template_name: Optional[str] = None,
        req_type: str = "interface",
    ) -> Requirement:
        """Create requirement through standard ASTRA pipeline."""

        # Quality check
        quality = check_requirement_quality(statement, title, rationale)

        # Generate ID
        count = (
            self.db.query(func.count(Requirement.id))
            .filter(
                Requirement.project_id == self.project_id,
                Requirement.req_type == req_type,
            )
            .scalar()
            or 0
        )
        req_id = generate_requirement_id("", req_type, count + 1)

        # Derive level from parent if available
        if parent_id:
            parent = self.db.query(Requirement).filter(Requirement.id == parent_id).first()
            if parent:
                parent_num = int(_ev(parent.level).replace("L", ""))
                level = f"L{min(parent_num + 1, 5)}"

        req = Requirement(
            req_id=req_id,
            title=title[:500],
            statement=statement,
            rationale=rationale,
            req_type=req_type,
            priority=priority,
            level=level,
            status="pending_review",
            project_id=self.project_id,
            owner_id=self.user.id,
            created_by_id=self.user.id,
            parent_id=parent_id,
            quality_score=quality["score"],
            version=1,
        )
        self.db.add(req)
        self.db.flush()

        # Record history
        hist = RequirementHistory(
            requirement_id=req.id,
            version=1,
            field_changed="created",
            new_value=req.req_id,
            changed_by_id=self.user.id,
            change_description=f"Auto-generated from interface module ({template_name})",
        )
        self.db.add(hist)

        # Create interface link
        if source_type and source_id:
            link = InterfaceRequirementLink(
                entity_type=source_type,
                entity_id=source_id,
                requirement_id=req.id,
                link_type="satisfies",
                auto_generated=True,
                auto_req_source=template_name or "manual",
                auto_req_template=template_name,
                status="pending_review",
                created_by_id=self.user.id,
            )
            self.db.add(link)
            self.generated_links.append(link)

        self.generated_reqs.append(req)
        return req

    def _create_verification(self, req: Requirement, method: str, criteria: str, template_name: str) -> Verification:
        """Create auto-verification linked to requirement."""
        verif = Verification(
            requirement_id=req.id,
            method=method,
            status="planned",
            criteria=criteria,
        )
        self.db.add(verif)
        self.db.flush()
        self.generated_verifs.append(verif)
        return verif

    def _link_entity(self, entity_type: str, entity_id: int, req_id: int, link_type: str, template: str):
        """Create additional entity → requirement link."""
        link = InterfaceRequirementLink(
            entity_type=entity_type,
            entity_id=entity_id,
            requirement_id=req_id,
            link_type=link_type,
            auto_generated=True,
            auto_req_source=template,
            status="pending_review",
            created_by_id=self.user.id,
        )
        self.db.add(link)
        self.generated_links.append(link)

    # ══════════════════════════════════════
    #  Template generators (10)
    # ══════════════════════════════════════

    def _gen_harness_overall(self, harness: WireHarness, wires: List[Wire]):
        ctx = self._build_harness_context(harness, wires)
        tmpl = TEMPLATES["harness_overall"]
        req = self._create_requirement(
            title=tmpl["title"].format_map(_SafeDict(ctx)),
            statement=tmpl["statement"].format_map(_SafeDict(ctx)),
            rationale=tmpl["rationale"].format_map(_SafeDict(ctx)),
            level=tmpl["level"], priority="high",
            source_type="wire_harness", source_id=harness.id,
            template_name="harness_overall",
        )
        vtmpl = VERIFICATION_TEMPLATES["harness_overall"]
        self._create_verification(req, vtmpl["method"],
                                  vtmpl["criteria"].format_map(_SafeDict(ctx)), "harness_overall")
        return req

    def _gen_bus_connection(self, harness: WireHarness, bus_def: BusDefinition, wires: List[Wire]):
        ctx = self._build_bus_context(harness, bus_def, wires)
        tmpl = TEMPLATES["bus_connection"]
        priority = tmpl["priority_map"].get(_ev(bus_def.protocol), "medium")
        parent = self._find_interface_parent(harness)

        req = self._create_requirement(
            title=tmpl["title"].format_map(_SafeDict(ctx)),
            statement=tmpl["statement"].format_map(_SafeDict(ctx)),
            rationale=tmpl["rationale"].format_map(_SafeDict(ctx)),
            level=tmpl["level"], priority=priority, parent_id=parent,
            source_type="bus_definition", source_id=bus_def.id,
            template_name="bus_connection",
        )
        self._link_entity("wire_harness", harness.id, req.id, "implements", "bus_connection")

        vtmpl = VERIFICATION_TEMPLATES["bus_connection"]
        self._create_verification(req, vtmpl["method"],
                                  vtmpl["criteria"].format_map(_SafeDict(ctx)), "bus_connection")
        return req

    def _gen_message(self, harness: WireHarness, bus_def: BusDefinition,
                     msg: MessageDefinition, parent: Requirement = None):
        ctx = self._build_message_context(harness, bus_def, msg)
        tmpl = TEMPLATES["message"]
        req = self._create_requirement(
            title=tmpl["title"].format_map(_SafeDict(ctx)),
            statement=tmpl["statement"].format_map(_SafeDict(ctx)),
            rationale=tmpl["rationale"].format_map(_SafeDict(ctx)),
            level=tmpl["level"], priority="medium",
            parent_id=parent.id if parent else None,
            source_type="message_definition", source_id=msg.id,
            template_name="message_definition",
        )
        vtmpl = VERIFICATION_TEMPLATES["message"]
        self._create_verification(req, vtmpl["method"],
                                  vtmpl["criteria"].format_map(_SafeDict(ctx)), "message_definition")
        return req

    def _gen_field(self, msg: MessageDefinition, field: MessageField, parent: Requirement = None):
        ctx = self._build_field_context(msg, field)
        tmpl = TEMPLATES["message_field"]
        req = self._create_requirement(
            title=tmpl["title"].format_map(_SafeDict(ctx)),
            statement=tmpl["statement"].format_map(_SafeDict(ctx)),
            rationale=tmpl["rationale"].format_map(_SafeDict(ctx)),
            level=tmpl["level"], priority="low",
            parent_id=parent.id if parent else None,
            source_type="message_field", source_id=field.id,
            template_name="message_field",
        )
        vtmpl = VERIFICATION_TEMPLATES["message_field"]
        self._create_verification(req, vtmpl["method"],
                                  vtmpl["criteria"].format_map(_SafeDict(ctx)), "message_field")
        return req

    def _gen_field_enum(self, msg: MessageDefinition, field: MessageField, parent: Requirement = None):
        ctx = self._build_field_context(msg, field)
        # Add enum-specific context
        enum_vals = field.enum_values or {}
        ctx["enum_states_formatted"] = ", ".join(
            f"{k}={v}" for k, v in (enum_vals.items() if isinstance(enum_vals, dict) else [])
        ) or "TBD"
        ctx["enum_count"] = len(enum_vals) if isinstance(enum_vals, dict) else 0

        tmpl = TEMPLATES["message_field_enum"]
        req = self._create_requirement(
            title=tmpl["title"].format_map(_SafeDict(ctx)),
            statement=tmpl["statement"].format_map(_SafeDict(ctx)),
            rationale=tmpl["rationale"].format_map(_SafeDict(ctx)),
            level=tmpl["level"], priority="low",
            parent_id=parent.id if parent else None,
            source_type="message_field", source_id=field.id,
            template_name="message_field",
        )
        # Enum fields use analysis verification same as regular fields
        vtmpl = VERIFICATION_TEMPLATES["message_field"]
        self._create_verification(req, vtmpl["method"],
                                  vtmpl["criteria"].format_map(_SafeDict(ctx)), "message_field")
        return req

    def _gen_power_wire(self, harness: WireHarness, wire: Wire):
        ctx = self._build_wire_context(harness, wire)
        from_pin = self.db.query(Pin).filter(Pin.id == wire.from_pin_id).first()
        ctx["voltage"] = from_pin.voltage_nominal or "28VDC" if from_pin else "28VDC"
        ctx["power_description"] = "primary power" if _ev(from_pin.signal_type) == "power_primary" else "secondary power"
        ctx["current_max"] = from_pin.current_max_amps or "TBD" if from_pin else "TBD"
        ctx["wire_spec_or_material"] = wire.wire_spec or wire.wire_material or "copper"

        tmpl = TEMPLATES["power_wire"]
        req = self._create_requirement(
            title=tmpl["title"].format_map(_SafeDict(ctx)),
            statement=tmpl["statement"].format_map(_SafeDict(ctx)),
            rationale=tmpl["rationale"].format_map(_SafeDict(ctx)),
            level=tmpl["level"], priority="high",
            source_type="wire", source_id=wire.id,
            template_name="power_wire",
        )
        vtmpl = VERIFICATION_TEMPLATES["power_wire"]
        self._create_verification(req, vtmpl["method"],
                                  vtmpl["criteria"].format_map(_SafeDict(ctx)), "power_wire")
        return req

    def _gen_ground_wire(self, harness: WireHarness, wire: Wire):
        ctx = self._build_wire_context(harness, wire)
        from_pin = self.db.query(Pin).filter(Pin.id == wire.from_pin_id).first()
        sig = _ev(from_pin.signal_type) if from_pin else ""
        ctx["ground_type"] = (
            "chassis" if "chassis" in sig else
            "signal" if "signal" in sig else
            "power return"
        )

        tmpl = TEMPLATES["ground_wire"]
        req = self._create_requirement(
            title=tmpl["title"].format_map(_SafeDict(ctx)),
            statement=tmpl["statement"].format_map(_SafeDict(ctx)),
            rationale=tmpl["rationale"].format_map(_SafeDict(ctx)),
            level=tmpl["level"], priority="medium",
            source_type="wire", source_id=wire.id,
            template_name="ground_wire",
        )
        # Ground wires use same verification as power
        vtmpl = VERIFICATION_TEMPLATES["power_wire"]
        self._create_verification(req, vtmpl["method"],
                                  vtmpl["criteria"].format_map(_SafeDict(ctx)), "ground_wire")
        return req

    def _gen_discrete_signal(self, harness: WireHarness, wire: Wire):
        ctx = self._build_wire_context(harness, wire)
        from_pin = self.db.query(Pin).filter(Pin.id == wire.from_pin_id).first()
        sig = _ev(from_pin.signal_type) if from_pin else "discrete_output"
        ctx["signal_subtype"] = (
            "input" if "input" in sig else
            "output" if "output" in sig else
            "bidirectional"
        )
        ctx["voltage_level"] = from_pin.voltage_nominal or "28VDC" if from_pin else "28VDC"
        ctx["direction_display"] = ctx["signal_subtype"]

        tmpl = TEMPLATES["discrete_signal"]
        req = self._create_requirement(
            title=tmpl["title"].format_map(_SafeDict(ctx)),
            statement=tmpl["statement"].format_map(_SafeDict(ctx)),
            rationale=tmpl["rationale"].format_map(_SafeDict(ctx)),
            level=tmpl["level"], priority="medium",
            source_type="wire", source_id=wire.id,
            template_name="discrete_signal",
        )
        vtmpl = VERIFICATION_TEMPLATES["discrete_signal"]
        self._create_verification(req, vtmpl["method"],
                                  vtmpl["criteria"].format_map(_SafeDict(ctx)), "discrete_signal")
        return req

    def _gen_rf_connection(self, harness: WireHarness, wire: Wire):
        ctx = self._build_wire_context(harness, wire)
        from_pin = self.db.query(Pin).filter(Pin.id == wire.from_pin_id).first()
        ctx["frequency_display"] = f"{from_pin.frequency_mhz} MHz" if from_pin and from_pin.frequency_mhz else "TBD"
        ctx["cable_type"] = harness.cable_type or "coaxial"
        ctx["cable_spec"] = harness.cable_spec or "TBD"
        ctx["impedance"] = from_pin.impedance_ohms or 50 if from_pin else 50
        ctx["insertion_loss_db"] = "TBD"
        from_conn = self.db.query(Connector).filter(Connector.id == harness.from_connector_id).first()
        ctx["connector_type"] = _ev(from_conn.connector_type) if from_conn else "SMA"

        tmpl = TEMPLATES["rf_connection"]
        req = self._create_requirement(
            title=tmpl["title"].format_map(_SafeDict(ctx)),
            statement=tmpl["statement"].format_map(_SafeDict(ctx)),
            rationale=tmpl["rationale"].format_map(_SafeDict(ctx)),
            level=tmpl["level"], priority="high",
            source_type="wire", source_id=wire.id,
            template_name="rf_connection",
        )
        vtmpl = VERIFICATION_TEMPLATES["rf_connection"]
        self._create_verification(req, vtmpl["method"],
                                  vtmpl["criteria"].format_map(_SafeDict(ctx)), "rf_connection")
        return req

    def _gen_shield(self, harness: WireHarness, wire: Wire):
        ctx = self._build_wire_context(harness, wire)
        ctx["termination_end"] = "source"
        ctx["termination_method"] = harness.overall_shield_termination or "360-degree backshell clamp"
        ctx["shield_type"] = _ev(harness.shield_type) or "overall braid"
        ctx["shield_coverage"] = harness.shield_coverage_pct or "TBD"

        # Count non-shield signals in harness
        signal_wires = (
            self.db.query(Wire)
            .filter(Wire.harness_id == harness.id)
            .join(Pin, Wire.from_pin_id == Pin.id)
            .filter(~Pin.signal_type.in_(["shield_overall", "shield_individual", "shield_drain"]))
            .count()
        )
        ctx["protected_signals"] = f"{signal_wires}" if signal_wires else "all"

        tmpl = TEMPLATES["shield_grounding"]
        req = self._create_requirement(
            title=tmpl["title"].format_map(_SafeDict(ctx)),
            statement=tmpl["statement"].format_map(_SafeDict(ctx)),
            rationale=tmpl["rationale"].format_map(_SafeDict(ctx)),
            level=tmpl["level"], priority="medium",
            source_type="wire", source_id=wire.id,
            template_name="shield_grounding",
        )
        # Shield uses harness inspection verification
        vtmpl = VERIFICATION_TEMPLATES["harness_overall"]
        self._create_verification(req, vtmpl["method"],
                                  vtmpl["criteria"].format_map(_SafeDict(ctx)), "shield_grounding")
        return req

    # ══════════════════════════════════════
    #  Context builders
    # ══════════════════════════════════════

    def _build_harness_context(self, harness: WireHarness, wires: List[Wire]) -> dict:
        fu = self.db.query(Unit).filter(Unit.id == harness.from_unit_id).first()
        tu = self.db.query(Unit).filter(Unit.id == harness.to_unit_id).first()
        fc = self.db.query(Connector).filter(Connector.id == harness.from_connector_id).first()
        tc = self.db.query(Connector).filter(Connector.id == harness.to_connector_id).first()
        fs = self.db.query(System).filter(System.id == fu.system_id).first() if fu else None
        ts = self.db.query(System).filter(System.id == tu.system_id).first() if tu else None

        return {
            "harness_id": harness.harness_id or f"HAR-{harness.id}",
            "source_unit": fu.designation if fu else "Unknown",
            "target_unit": tu.designation if tu else "Unknown",
            "source_abbrev": (fs.abbreviation if fs and fs.abbreviation else fu.designation if fu else "?")[:10],
            "target_abbrev": (ts.abbreviation if ts and ts.abbreviation else tu.designation if tu else "?")[:10],
            "from_conn": fc.designator if fc else "?",
            "to_conn": tc.designator if tc else "?",
            "cable_spec": harness.cable_spec or harness.cable_type or "TBD",
            "cable_type": harness.cable_type or "TBD",
            "max_length": harness.overall_length_max_m or harness.overall_length_m or "TBD",
            "wire_count": len(wires),
            "pair_count": harness.pair_count or 0,
            "shield_type": _ev(harness.shield_type) or "none",
            "drawing_number": harness.drawing_number or "TBD",
            "voltage_rating": harness.voltage_rating_v or "TBD",
        }

    def _build_bus_context(self, harness: WireHarness, bus_def: BusDefinition, wires: List[Wire]) -> dict:
        fu = self.db.query(Unit).filter(Unit.id == harness.from_unit_id).first()
        tu = self.db.query(Unit).filter(Unit.id == harness.to_unit_id).first()
        fc = self.db.query(Connector).filter(Connector.id == harness.from_connector_id).first()
        tc = self.db.query(Connector).filter(Connector.id == harness.to_connector_id).first()
        fs = self.db.query(System).filter(System.id == fu.system_id).first() if fu else None
        ts = self.db.query(System).filter(System.id == tu.system_id).first() if tu else None

        protocol = _ev(bus_def.protocol)
        is_bidir = protocol in (
            "mil_std_1553a", "mil_std_1553b", "can_2a", "can_2b", "canfd",
            "ethernet_100base_tx", "ethernet_1000base_t",
        )

        return {
            "harness_id": harness.harness_id or f"HAR-{harness.id}",
            "source_system": fs.name if fs else (fu.name if fu else "Unknown"),
            "target_system": ts.name if ts else (tu.name if tu else "Unknown"),
            "source_unit": fu.designation if fu else "Unknown",
            "target_unit": tu.designation if tu else "Unknown",
            "source_abbrev": (fs.abbreviation if fs and fs.abbreviation else fu.designation if fu else "?")[:10],
            "target_abbrev": (ts.abbreviation if ts and ts.abbreviation else tu.designation if tu else "?")[:10],
            "source_connector": fc.designator if fc else "?",
            "target_connector": tc.designator if tc else "?",
            "protocol": protocol,
            "protocol_display": protocol.replace("_", "-").upper(),
            "protocol_short": protocol.split("_")[-1].upper()[:8],
            "bus_def_id": bus_def.bus_def_id or f"BUS-{bus_def.id}",
            "bus_role": _ev(bus_def.bus_role),
            "bus_address": bus_def.bus_address or "N/A",
            "bus_network_name": bus_def.bus_name_network or bus_def.name,
            "data_rate": bus_def.data_rate or "TBD",
            "direction_verb": "exchange data with" if is_bidir else "transmit data to",
            "preposition": "with" if is_bidir else "to",
            "data_description": "data",
        }

    def _build_message_context(self, harness: WireHarness, bus_def: BusDefinition,
                               msg: MessageDefinition) -> dict:
        unit = self.db.query(Unit).filter(Unit.id == msg.unit_id).first()
        protocol = _ev(bus_def.protocol)
        direction = _ev(msg.direction)
        field_count = self.db.query(func.count(MessageField.id)).filter(
            MessageField.message_id == msg.id
        ).scalar()
        total_bits = self.db.query(func.sum(MessageField.bit_length)).filter(
            MessageField.message_id == msg.id
        ).scalar() or 0

        direction_verb_map = {
            "transmit": "transmit", "receive": "receive",
            "transmit_receive": "transmit and receive",
            "broadcast": "broadcast",
        }

        return {
            "unit_name": unit.name if unit else "Unknown",
            "unit_designation": unit.designation if unit else "?",
            "msg_label": msg.label,
            "msg_mnemonic": msg.mnemonic or msg.label[:8],
            "msg_def_id": msg.msg_def_id or f"MSG-{msg.id}",
            "bus_def_id": bus_def.bus_def_id or f"BUS-{bus_def.id}",
            "bus_detail": f"{bus_def.bus_name_network or bus_def.name} SA{msg.subaddress}" if msg.subaddress else bus_def.name,
            "protocol_display": protocol.replace("_", "-").upper(),
            "direction": direction,
            "direction_verb": direction_verb_map.get(direction, "transmit"),
            "direction_verb_past": direction_verb_map.get(direction, "transmitted") + "ted" if direction != "broadcast" else "broadcast",
            "rate_hz": msg.rate_hz or "TBD",
            "latency_max_ms": msg.latency_max_ms or "TBD",
            "word_count": msg.word_count or "TBD",
            "field_count": field_count,
            "total_bits": total_bits,
            "scheduling": _ev(msg.scheduling) or "periodic",
        }

    def _build_field_context(self, msg: MessageDefinition, field: MessageField) -> dict:
        bus = self.db.query(BusDefinition).filter(BusDefinition.id == msg.bus_def_id).first()
        word_bits = bus.word_size_bits if bus else 16

        position = f"word {field.word_number}" if field.word_number else "TBD"
        if field.bit_offset is not None:
            position += f", bits [{field.bit_offset}:{field.bit_offset + field.bit_length - 1}]"

        return {
            "msg_label": msg.label,
            "msg_mnemonic": msg.mnemonic or msg.label[:8],
            "msg_def_id": msg.msg_def_id or f"MSG-{msg.id}",
            "field_name": field.field_name,
            "field_label": field.label or field.field_name,
            "data_type_display": _ev(field.data_type).replace("_", " ").upper(),
            "bit_length": field.bit_length,
            "position_description": position,
            "min_value": field.min_value if field.min_value is not None else "N/A",
            "max_value": field.max_value if field.max_value is not None else "N/A",
            "unit_of_measure": field.unit_of_measure or "",
            "scale_factor": field.scale_factor or 1.0,
            "offset_value": field.offset_value or 0.0,
            "lsb_value": field.lsb_value or "N/A",
            "resolution": field.resolution or "N/A",
        }

    def _build_wire_context(self, harness: WireHarness, wire: Wire) -> dict:
        fu = self.db.query(Unit).filter(Unit.id == harness.from_unit_id).first()
        tu = self.db.query(Unit).filter(Unit.id == harness.to_unit_id).first()
        fc = self.db.query(Connector).filter(Connector.id == harness.from_connector_id).first()
        tc = self.db.query(Connector).filter(Connector.id == harness.to_connector_id).first()
        fs = self.db.query(System).filter(System.id == fu.system_id).first() if fu else None
        ts = self.db.query(System).filter(System.id == tu.system_id).first() if tu else None
        fp = self.db.query(Pin).filter(Pin.id == wire.from_pin_id).first()
        tp = self.db.query(Pin).filter(Pin.id == wire.to_pin_id).first()

        return {
            "harness_id": harness.harness_id or f"HAR-{harness.id}",
            "wire_number": wire.wire_number,
            "signal_name": wire.signal_name,
            "wire_type": _ev(wire.wire_type),
            "wire_gauge": _ev(wire.wire_gauge) if wire.wire_gauge else "22",
            "source_unit": fu.designation if fu else "Unknown",
            "target_unit": tu.designation if tu else "Unknown",
            "source_abbrev": (fs.abbreviation if fs and fs.abbreviation else fu.designation if fu else "?")[:10],
            "target_abbrev": (ts.abbreviation if ts and ts.abbreviation else tu.designation if tu else "?")[:10],
            "from_conn": fc.designator if fc else "?",
            "to_conn": tc.designator if tc else "?",
            "from_pin_number": fp.pin_number if fp else "?",
            "to_pin_number": tp.pin_number if tp else "?",
            # Harness-level fields for verification templates
            "drawing_number": harness.drawing_number or "TBD",
            "voltage_rating": harness.voltage_rating_v or "TBD",
            "wire_count": self.db.query(func.count(Wire.id)).filter(Wire.harness_id == harness.id).scalar(),
            "bus_network_name": "",
            "data_rate": "",
        }

    # ══════════════════════════════════════
    #  Impact analysis helpers
    # ══════════════════════════════════════

    def _find_affected_requirements(self, wires: List[Wire]) -> list:
        """Find auto-generated requirements linked to these wires or their buses."""
        affected = []
        wire_ids = [w.id for w in wires]

        # Direct wire links
        links = self.db.query(InterfaceRequirementLink).filter(
            InterfaceRequirementLink.entity_type == "wire",
            InterfaceRequirementLink.entity_id.in_(wire_ids),
            InterfaceRequirementLink.auto_generated.is_(True),
        ).all()

        for lk in links:
            req = self.db.query(Requirement).filter(Requirement.id == lk.requirement_id).first()
            if req:
                affected.append({
                    "requirement_id": req.id,
                    "req_id": req.req_id,
                    "title": req.title,
                    "level": _ev(req.level),
                    "link_type": _ev(lk.link_type),
                    "template": lk.auto_req_template,
                })

        # Also check harness-level links for wires in the same harness
        harness_ids = set(w.harness_id for w in wires)
        harness_links = self.db.query(InterfaceRequirementLink).filter(
            InterfaceRequirementLink.entity_type == "wire_harness",
            InterfaceRequirementLink.entity_id.in_(harness_ids),
            InterfaceRequirementLink.auto_generated.is_(True),
        ).all()
        for lk in harness_links:
            req = self.db.query(Requirement).filter(Requirement.id == lk.requirement_id).first()
            if req and not any(a["requirement_id"] == req.id for a in affected):
                affected.append({
                    "requirement_id": req.id,
                    "req_id": req.req_id,
                    "title": req.title,
                    "level": _ev(req.level),
                    "link_type": _ev(lk.link_type),
                    "template": lk.auto_req_template,
                })

        return affected

    def _assess_risk(self, affected: list) -> str:
        if not affected:
            return "none"
        levels = [a.get("level", "L5") for a in affected]
        if any(l in ("L1", "L2") for l in levels):
            return "high"
        if any(l == "L3" for l in levels):
            return "medium"
        return "low"

    def _find_interface_parent(self, harness: WireHarness) -> Optional[int]:
        """Find an existing L2/L3 interface requirement to parent under."""
        fu = self.db.query(Unit).filter(Unit.id == harness.from_unit_id).first()
        tu = self.db.query(Unit).filter(Unit.id == harness.to_unit_id).first()
        if not fu or not tu:
            return None

        # Look for existing interface entity between these systems
        iface = self.db.query(Interface).filter(
            Interface.source_system_id == fu.system_id,
            Interface.target_system_id == tu.system_id,
            Interface.project_id == self.project_id,
        ).first()
        if not iface:
            return None

        # Find a requirement linked to this interface
        link = self.db.query(InterfaceRequirementLink).filter(
            InterfaceRequirementLink.entity_type == "interface",
            InterfaceRequirementLink.entity_id == iface.id,
        ).first()
        return link.requirement_id if link else None

    def _get_messages(self, bus_def_id: int) -> list:
        return self.db.query(MessageDefinition).filter(
            MessageDefinition.bus_def_id == bus_def_id
        ).order_by(MessageDefinition.label).all()

    def _get_fields(self, msg_id: int) -> list:
        return self.db.query(MessageField).filter(
            MessageField.message_id == msg_id
        ).order_by(MessageField.field_order, MessageField.word_number).all()

    # ══════════════════════════════════════
    #  History + logging
    # ══════════════════════════════════════

    def _record_history(self, req: Requirement, field: str, old_val, new_val, desc: str):
        hist = RequirementHistory(
            requirement_id=req.id,
            version=req.version or 1,
            field_changed=field,
            old_value=str(old_val) if old_val else None,
            new_value=str(new_val) if new_val else None,
            changed_by_id=self.user.id,
            change_description=desc,
        )
        self.db.add(hist)

    def _log_generation(self, action: str, entity_type: str, entity_id: int, trigger_count: int):
        log = AutoRequirementLog(
            project_id=self.project_id,
            trigger_entity_type=entity_type,
            trigger_entity_id=entity_id,
            trigger_action=action,
            requirements_generated=len(self.generated_reqs),
            verifications_generated=len(self.generated_verifs),
            links_generated=len(self.generated_links),
            template_used="multi",
            generation_summary={
                "trigger_count": trigger_count,
                "req_ids": [r.req_id for r in self.generated_reqs],
            },
            user_id=self.user.id,
        )
        self.db.add(log)


# ══════════════════════════════════════════════════════════════
#  Safe dict for .format_map() — returns "TBD" for missing keys
# ══════════════════════════════════════════════════════════════

class _SafeDict(dict):
    """Dict subclass that returns 'TBD' for missing keys in str.format_map()."""
    def __missing__(self, key):
        return "TBD"
