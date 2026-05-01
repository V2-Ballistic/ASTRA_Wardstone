"""ASTRA — Catalog Seed Script (Phase 8, ASTRA-TDD-INTF-002)
================================================================
File: backend/app/scripts/seed_catalog.py

Idempotently seeds the global supplier catalog with five representative
defense-electronics suppliers and one or two catalog parts each, complete
with physical / environmental / power specs and a connector + pin tree
suitable for downstream auto-wire and placement testing.

Run from the backend container::

    docker exec astra-backend-1 python -m app.scripts.seed_catalog

Idempotency
-----------
- ``Supplier.name`` is UNIQUE — a name match means the supplier already
  exists; the script skips inserting it again.
- ``CatalogPart`` has ``UniqueConstraint(supplier_id, part_number, revision)``
  — same idempotency strategy: query first, skip on hit.
- Connectors / pins are only created for *newly inserted* parts so we
  never duplicate the connector tree of an already-seeded part.

Re-running the script after the first run is a no-op and prints a single
summary line.

Usage notes
-----------
- A "seeder" service user is reused / created so audit trails attribute the
  rows to a known principal. The user has the ``admin`` role; it is created
  with a random hashed password and is *not* a login account (no email
  verification, no MFA enrolment) — it exists purely as a created_by_id FK
  target.
- The script does NOT emit audit events. Audit events on creation are only
  emitted from the HTTP routers; running the seeder is a privileged
  bootstrap operation and the row provenance lives in created_by_id.
"""

from __future__ import annotations

import logging
import sys
from typing import Optional

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import User, UserRole
from app.models.catalog import (
    CatalogConnector,
    CatalogPart,
    CatalogPin,
    ConnectorGender,
    LifecycleStatus,
    LRUClass,
    PartClass,
    SignalDirection,
    SignalType,
    Supplier,
)
from app.services.auth import get_password_hash

logger = logging.getLogger("astra.seed_catalog")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


SEED_USER_USERNAME = "catalog_seeder"
SEED_USER_EMAIL = "catalog-seeder@astra.local"


# ══════════════════════════════════════════════════════════════
#  Pin builder helpers (defined BEFORE SEED_DATA so the literal can call them)
# ══════════════════════════════════════════════════════════════


def _pin(
    pos: int,
    name: str,
    function: str,
    sig_type: SignalType,
    direction: SignalDirection,
    *,
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    imax_ma: Optional[float] = None,
    impedance: Optional[float] = None,
    no_connect: bool = False,
    reserved: bool = False,
    chassis_ground: bool = False,
) -> dict:
    return {
        "pin_position": str(pos),
        "mfr_pin_name": name,
        "mfr_signal_function": function,
        "mfr_signal_type": sig_type,
        "mfr_direction": direction,
        "mfr_voltage_min_v": vmin,
        "mfr_voltage_max_v": vmax,
        "mfr_current_max_ma": imax_ma,
        "mfr_impedance_ohm": impedance,
        "is_no_connect": no_connect,
        "is_reserved": reserved,
        "is_chassis_ground": chassis_ground,
    }


def _make_pin_block_38999_25pin_power() -> list[dict]:
    """Receiver J1: 25 pins. Power + grounds + LO/IF + control."""
    pins: list[dict] = []
    pins.append(_pin(1, "PWR_28V_A", "Primary 28V supply, channel A",
                     SignalType.POWER, SignalDirection.POWER, vmin=22, vmax=30, imax_ma=2000))
    pins.append(_pin(2, "PWR_28V_B", "Primary 28V supply, channel B (redundant)",
                     SignalType.POWER, SignalDirection.POWER, vmin=22, vmax=30, imax_ma=2000))
    pins.append(_pin(3, "GND_PWR", "Power ground",
                     SignalType.GROUND, SignalDirection.GROUND))
    pins.append(_pin(4, "GND_SIG", "Signal ground",
                     SignalType.GROUND, SignalDirection.GROUND))
    pins.append(_pin(5, "LO_REF_IN", "Local oscillator reference in",
                     SignalType.RF, SignalDirection.INPUT, impedance=50.0))
    pins.append(_pin(6, "LO_REF_RTN", "LO reference return",
                     SignalType.GROUND, SignalDirection.GROUND))
    pins.append(_pin(7, "IF_OUT_P", "IF output, positive (diff)",
                     SignalType.DIFF_PAIR, SignalDirection.OUTPUT, impedance=100.0))
    pins.append(_pin(8, "IF_OUT_N", "IF output, negative (diff)",
                     SignalType.DIFF_PAIR, SignalDirection.OUTPUT, impedance=100.0))
    pins.append(_pin(9, "I2C_SDA", "I2C data",
                     SignalType.DIGITAL, SignalDirection.BIDIRECTIONAL))
    pins.append(_pin(10, "I2C_SCL", "I2C clock",
                     SignalType.DIGITAL, SignalDirection.INPUT))
    pins.append(_pin(11, "RESET_N", "Active-low reset",
                     SignalType.DISCRETE, SignalDirection.INPUT))
    pins.append(_pin(12, "STATUS_LED", "Status LED open-collector",
                     SignalType.DISCRETE, SignalDirection.OUTPUT))
    pins.append(_pin(13, "TEMP_SENSE", "Internal temp sensor analog out",
                     SignalType.ANALOG, SignalDirection.OUTPUT, vmin=0, vmax=5))
    pins.append(_pin(14, "PWR_MON", "Power-monitor analog out",
                     SignalType.ANALOG, SignalDirection.OUTPUT, vmin=0, vmax=5))
    pins.append(_pin(15, "BIT_FAIL", "Built-in-test fail discrete",
                     SignalType.DISCRETE, SignalDirection.OUTPUT))
    pins.append(_pin(16, "BIT_PASS", "Built-in-test pass discrete",
                     SignalType.DISCRETE, SignalDirection.OUTPUT))
    for i in range(17, 26):
        if i in (17, 18, 19):
            pins.append(_pin(i, f"NC_{i:02d}", "No connect",
                             SignalType.NO_CONNECT, SignalDirection.UNKNOWN, no_connect=True))
        else:
            pins.append(_pin(i, f"RSVD_{i:02d}", "Reserved by manufacturer",
                             SignalType.RESERVED, SignalDirection.UNKNOWN, reserved=True))
    return pins


def _make_pin_block_fcc_chanA() -> list[dict]:
    """Flight Computer J1 — Channel A: power, 1553, ARINC, discretes."""
    pins: list[dict] = []
    pins.append(_pin(1, "PWR_28V_A", "Primary 28V channel A",
                     SignalType.POWER, SignalDirection.POWER, vmin=22, vmax=30, imax_ma=3000))
    pins.append(_pin(2, "GND_A", "Channel A return",
                     SignalType.GROUND, SignalDirection.GROUND))
    pins.append(_pin(3, "MIL1553_A_HI", "MIL-STD-1553 channel A high",
                     SignalType.DIFF_PAIR, SignalDirection.BIDIRECTIONAL, impedance=78.0))
    pins.append(_pin(4, "MIL1553_A_LO", "MIL-STD-1553 channel A low",
                     SignalType.DIFF_PAIR, SignalDirection.BIDIRECTIONAL, impedance=78.0))
    pins.append(_pin(5, "MIL1553_A_SHLD", "MIL-1553 channel A shield",
                     SignalType.GROUND, SignalDirection.GROUND))
    pins.append(_pin(6, "ARINC429_TX_A_HI", "ARINC-429 transmit A high",
                     SignalType.DIFF_PAIR, SignalDirection.OUTPUT))
    pins.append(_pin(7, "ARINC429_TX_A_LO", "ARINC-429 transmit A low",
                     SignalType.DIFF_PAIR, SignalDirection.OUTPUT))
    pins.append(_pin(8, "ARINC429_RX_A_HI", "ARINC-429 receive A high",
                     SignalType.DIFF_PAIR, SignalDirection.INPUT))
    pins.append(_pin(9, "ARINC429_RX_A_LO", "ARINC-429 receive A low",
                     SignalType.DIFF_PAIR, SignalDirection.INPUT))
    for i, (label, desc, dirn) in enumerate([
        ("DISC_IN_01", "Discrete input 1", SignalDirection.INPUT),
        ("DISC_IN_02", "Discrete input 2", SignalDirection.INPUT),
        ("DISC_OUT_01", "Discrete output 1", SignalDirection.OUTPUT),
        ("DISC_OUT_02", "Discrete output 2", SignalDirection.OUTPUT),
        ("WOW_SENSE", "Weight-on-wheels sense", SignalDirection.INPUT),
        ("MASTER_RESET", "Master reset", SignalDirection.INPUT),
        ("FAULT_OUT", "Fault asserted (open collector)", SignalDirection.OUTPUT),
        ("HEALTH_OUT", "Health pulse output", SignalDirection.OUTPUT),
    ], start=10):
        pins.append(_pin(i, label, desc, SignalType.DISCRETE, dirn))
    for i in range(18, 27):
        pins.append(_pin(i, f"SPARE_{i:02d}", "Spare", SignalType.RESERVED,
                         SignalDirection.UNKNOWN, reserved=True))
    return pins


def _make_pin_block_fcc_chanB() -> list[dict]:
    """Flight Computer J2 — Channel B: power, 1553, Ethernet, telemetry."""
    pins: list[dict] = []
    pins.append(_pin(1, "PWR_28V_B", "Primary 28V channel B",
                     SignalType.POWER, SignalDirection.POWER, vmin=22, vmax=30, imax_ma=3000))
    pins.append(_pin(2, "GND_B", "Channel B return",
                     SignalType.GROUND, SignalDirection.GROUND))
    pins.append(_pin(3, "MIL1553_B_HI", "MIL-1553 channel B high",
                     SignalType.DIFF_PAIR, SignalDirection.BIDIRECTIONAL, impedance=78.0))
    pins.append(_pin(4, "MIL1553_B_LO", "MIL-1553 channel B low",
                     SignalType.DIFF_PAIR, SignalDirection.BIDIRECTIONAL, impedance=78.0))
    pins.append(_pin(5, "MIL1553_B_SHLD", "MIL-1553 channel B shield",
                     SignalType.GROUND, SignalDirection.GROUND))
    pins.append(_pin(6, "ETH_TX_P", "Ethernet TX positive",
                     SignalType.DIFF_PAIR, SignalDirection.OUTPUT, impedance=100.0))
    pins.append(_pin(7, "ETH_TX_N", "Ethernet TX negative",
                     SignalType.DIFF_PAIR, SignalDirection.OUTPUT, impedance=100.0))
    pins.append(_pin(8, "ETH_RX_P", "Ethernet RX positive",
                     SignalType.DIFF_PAIR, SignalDirection.INPUT, impedance=100.0))
    pins.append(_pin(9, "ETH_RX_N", "Ethernet RX negative",
                     SignalType.DIFF_PAIR, SignalDirection.INPUT, impedance=100.0))
    pins.append(_pin(10, "ETH_SHLD", "Ethernet shield",
                     SignalType.GROUND, SignalDirection.GROUND))
    pins.append(_pin(11, "TEMP_SENSE_B", "Internal temp B",
                     SignalType.ANALOG, SignalDirection.OUTPUT, vmin=0, vmax=5))
    pins.append(_pin(12, "PWR_MON_B", "Power monitor B",
                     SignalType.ANALOG, SignalDirection.OUTPUT, vmin=0, vmax=5))
    pins.append(_pin(13, "BIT_FAIL_B", "BIT fail discrete B",
                     SignalType.DISCRETE, SignalDirection.OUTPUT))
    pins.append(_pin(14, "BIT_PASS_B", "BIT pass discrete B",
                     SignalType.DISCRETE, SignalDirection.OUTPUT))
    for i in range(15, 25):
        pins.append(_pin(i, f"SPARE_B_{i:02d}", "Spare", SignalType.RESERVED,
                         SignalDirection.UNKNOWN, reserved=True))
    return pins


def _make_pin_block_passive_37pin() -> list[dict]:
    """Generic 37-pin passive connector pin-out — unspecified function."""
    return [
        _pin(i, f"PIN_{i:02d}", "Position placeholder",
             SignalType.UNKNOWN, SignalDirection.UNKNOWN)
        for i in range(1, 38)
    ]


def _make_pin_block_passive_6pin() -> list[dict]:
    return [
        _pin(i, f"PIN_{i:02d}", "Position placeholder",
             SignalType.UNKNOWN, SignalDirection.UNKNOWN)
        for i in range(1, 7)
    ]


def _make_pin_block_dsub9_rs422() -> list[dict]:
    """DE-9 male RS-422 / RS-232 — common test-equipment pin-out."""
    return [
        _pin(1, "DCD", "Carrier detect", SignalType.DISCRETE, SignalDirection.INPUT),
        _pin(2, "RXD", "Receive data", SignalType.DIGITAL, SignalDirection.INPUT),
        _pin(3, "TXD", "Transmit data", SignalType.DIGITAL, SignalDirection.OUTPUT),
        _pin(4, "DTR", "Data terminal ready", SignalType.DISCRETE, SignalDirection.OUTPUT),
        _pin(5, "GND", "Signal ground", SignalType.GROUND, SignalDirection.GROUND),
        _pin(6, "DSR", "Data set ready", SignalType.DISCRETE, SignalDirection.INPUT),
        _pin(7, "RTS", "Request to send", SignalType.DISCRETE, SignalDirection.OUTPUT),
        _pin(8, "CTS", "Clear to send", SignalType.DISCRETE, SignalDirection.INPUT),
        _pin(9, "RI", "Ring indicator", SignalType.DISCRETE, SignalDirection.INPUT),
    ]


# ══════════════════════════════════════════════════════════════
#  Seed payload — five suppliers + ≥6 catalog parts
# ══════════════════════════════════════════════════════════════


def _build_seed_data() -> list[dict]:
    """Built lazily inside a function so the helpers above are guaranteed to
    exist when the dict literal is evaluated. (A module-level literal would
    work too since helpers are defined first, but the function form lets us
    cleanly re-build the payload across test invocations.)"""
    return [
        # ── 1. Raytheon ──────────────────────────────────────────
        {
            "supplier": {
                "name": "Raytheon Technologies",
                "short_name": "RTX",
                "cage_code": "49956",
                "country": "USA",
                "website": "https://www.rtx.com",
                "primary_email": "catalog@rtx.com",
                "is_active": True,
            },
            "parts": [
                {
                    "part_number": "RTN-PSU-050",
                    "revision": "A",
                    "name": "28V Aircraft DC-DC Power Supply, 50W",
                    "designation": "PSU-050",
                    "description": (
                        "Hardened 50-watt 28-V aircraft DC-DC PSU; meets "
                        "MIL-STD-704 input transients and MIL-STD-461F EMI."
                    ),
                    "part_class": PartClass.POWER_SUPPLY,
                    "lru_classification": LRUClass.LRU,
                    "mass_kg": 0.65,
                    "dim_length_mm": 110.0,
                    "dim_width_mm": 80.0,
                    "dim_height_mm": 25.0,
                    "power_watts_nominal": 50.0,
                    "power_watts_peak": 75.0,
                    "voltage_input_min_v": 18.0,
                    "voltage_input_max_v": 32.0,
                    "temp_operating_min_c": -55.0,
                    "temp_operating_max_c": 85.0,
                    "vibration_random_grms": 14.0,
                    "shock_mechanical_g": 100.0,
                    "humidity_max_pct": 100.0,
                    "altitude_max_m": 21000.0,
                    "mil_std_810_tested": True,
                    "mil_std_461_tested": True,
                    "lifecycle_status": LifecycleStatus.ACTIVE,
                    "rohs_compliant": True,
                    "connectors": [
                        {
                            "reference": "J1",
                            "position": 0,
                            "description": "Input + output power",
                            "connector_type": "MIL-DTL-38999 Series III",
                            "shell_size": "11",
                            "insert_arrangement": "11-05",
                            "gender": ConnectorGender.MALE,
                            "pin_count": 5,
                            "keying": "Normal",
                            "mating_part_number": "D38999/26WB05SN",
                            "pins": [
                                _pin(1, "VIN_28V", "28V input", SignalType.POWER,
                                     SignalDirection.INPUT, vmin=18, vmax=32, imax_ma=4000),
                                _pin(2, "VIN_RTN", "Input return", SignalType.GROUND,
                                     SignalDirection.GROUND),
                                _pin(3, "VOUT_5V", "5V regulated output", SignalType.POWER,
                                     SignalDirection.POWER, vmin=4.95, vmax=5.05, imax_ma=10000),
                                _pin(4, "VOUT_RTN", "Output return", SignalType.GROUND,
                                     SignalDirection.GROUND),
                                _pin(5, "EN_N", "Active-low enable", SignalType.DISCRETE,
                                     SignalDirection.INPUT),
                            ],
                        },
                    ],
                },
                {
                    "part_number": "RTN-RX-100",
                    "revision": "B",
                    "name": "X-Band Receiver Front-End",
                    "designation": "RX-FE-100",
                    "description": (
                        "X-band low-noise receiver front-end with integrated "
                        "down-converter; designed for airborne radar systems."
                    ),
                    "part_class": PartClass.RADIO,
                    "lru_classification": LRUClass.LRU,
                    "mass_kg": 1.85,
                    "dim_length_mm": 220.0,
                    "dim_width_mm": 140.0,
                    "dim_height_mm": 60.0,
                    "power_watts_nominal": 18.0,
                    "power_watts_peak": 26.0,
                    "voltage_input_min_v": 22.0,
                    "voltage_input_max_v": 30.0,
                    "temp_operating_min_c": -40.0,
                    "temp_operating_max_c": 71.0,
                    "temp_storage_min_c": -55.0,
                    "temp_storage_max_c": 85.0,
                    "vibration_random_grms": 11.95,
                    "shock_mechanical_g": 75.0,
                    "humidity_max_pct": 95.0,
                    "altitude_max_m": 21000.0,
                    "mil_std_810_tested": True,
                    "mil_std_461_tested": True,
                    "lifecycle_status": LifecycleStatus.ACTIVE,
                    "itar_controlled": True,
                    "export_classification": "9A610",
                    "connectors": [
                        {
                            "reference": "J1",
                            "position": 0,
                            "description": "Power + control interface",
                            "connector_type": "MIL-DTL-38999 Series III",
                            "shell_size": "13",
                            "insert_arrangement": "13-35",
                            "gender": ConnectorGender.MALE,
                            "pin_count": 25,
                            "keying": "Normal",
                            "mating_part_number": "D38999/26WD35SN",
                            "pins": _make_pin_block_38999_25pin_power(),
                        },
                    ],
                },
            ],
        },
        # ── 2. BAE Systems ───────────────────────────────────────
        {
            "supplier": {
                "name": "BAE Systems",
                "short_name": "BAE",
                "cage_code": "1V4F8",
                "country": "USA",
                "website": "https://www.baesystems.com",
                "primary_email": "catalog@baesystems.com",
                "is_active": True,
            },
            "parts": [
                {
                    "part_number": "BAE-FCC-200",
                    "revision": "C",
                    "name": "Flight Control Computer (Dual-Channel)",
                    "designation": "FCC-200",
                    "description": (
                        "Dual-redundant flight control computer with PowerPC "
                        "processor, ARINC-429 + MIL-STD-1553 + Ethernet I/O."
                    ),
                    "part_class": PartClass.PROCESSOR,
                    "lru_classification": LRUClass.LRU,
                    "mass_kg": 4.2,
                    "dim_length_mm": 320.0,
                    "dim_width_mm": 230.0,
                    "dim_height_mm": 90.0,
                    "power_watts_nominal": 45.0,
                    "power_watts_peak": 65.0,
                    "voltage_input_min_v": 22.0,
                    "voltage_input_max_v": 30.0,
                    "temp_operating_min_c": -55.0,
                    "temp_operating_max_c": 85.0,
                    "temp_storage_min_c": -65.0,
                    "temp_storage_max_c": 105.0,
                    "vibration_random_grms": 14.0,
                    "shock_mechanical_g": 100.0,
                    "humidity_max_pct": 100.0,
                    "altitude_max_m": 24000.0,
                    "mil_std_810_tested": True,
                    "mil_std_461_tested": True,
                    "lifecycle_status": LifecycleStatus.PREFERRED,
                    "itar_controlled": True,
                    "export_classification": "9A610",
                    "connectors": [
                        {
                            "reference": "J1",
                            "position": 0,
                            "description": "Channel A power + 1553 + ARINC",
                            "connector_type": "MIL-DTL-38999 Series III",
                            "shell_size": "17",
                            "insert_arrangement": "17-26",
                            "gender": ConnectorGender.MALE,
                            "pin_count": 26,
                            "keying": "Position N",
                            "mating_part_number": "D38999/26WE26SN",
                            "pins": _make_pin_block_fcc_chanA(),
                        },
                        {
                            "reference": "J2",
                            "position": 1,
                            "description": "Channel B power + 1553 + Ethernet",
                            "connector_type": "MIL-DTL-38999 Series III",
                            "shell_size": "19",
                            "insert_arrangement": "19-35",
                            "gender": ConnectorGender.MALE,
                            "pin_count": 24,
                            "keying": "Position A",
                            "mating_part_number": "D38999/26WE35SN",
                            "pins": _make_pin_block_fcc_chanB(),
                        },
                    ],
                },
            ],
        },
        # ── 3. TE Connectivity ───────────────────────────────────
        {
            "supplier": {
                "name": "TE Connectivity",
                "short_name": "TE",
                "cage_code": "06324",
                "country": "Switzerland",
                "website": "https://www.te.com",
                "primary_email": "milaero.support@te.com",
                "is_active": True,
            },
            "parts": [
                {
                    "part_number": "TE-MS-13-35S",
                    "revision": "A",
                    "name": "MIL-DTL-38999 III Receptacle, Shell 13",
                    "designation": "MS-13-35S",
                    "description": (
                        "Box-mount jam-nut receptacle, MIL-DTL-38999 Series III, "
                        "shell size 13, insert 13-35 (37 contacts), socket "
                        "(female) inserts."
                    ),
                    "part_class": PartClass.CONNECTOR,
                    "lru_classification": LRUClass.COMPONENT,
                    "mass_kg": 0.085,
                    "dim_length_mm": 39.6,
                    "dim_width_mm": 19.0,
                    "dim_height_mm": 19.0,
                    "temp_operating_min_c": -65.0,
                    "temp_operating_max_c": 175.0,
                    "vibration_random_grms": 30.0,
                    "shock_mechanical_g": 300.0,
                    "humidity_max_pct": 100.0,
                    "altitude_max_m": 30000.0,
                    "mil_std_810_tested": True,
                    "lifecycle_status": LifecycleStatus.ACTIVE,
                    "rohs_compliant": True,
                    "connectors": [
                        {
                            "reference": "P1",
                            "position": 0,
                            "description": "Box receptacle, female socket inserts",
                            "connector_type": "MIL-DTL-38999 Series III",
                            "shell_size": "13",
                            "insert_arrangement": "13-35",
                            "gender": ConnectorGender.FEMALE,
                            "pin_count": 37,
                            "keying": "Normal",
                            "mating_part_number": "D38999/26WD35PN",
                            "pins": _make_pin_block_passive_37pin(),
                        },
                    ],
                },
            ],
        },
        # ── 4. Glenair ───────────────────────────────────────────
        {
            "supplier": {
                "name": "Glenair, Inc.",
                "short_name": "Glenair",
                "cage_code": "06324",
                "country": "USA",
                "website": "https://www.glenair.com",
                "primary_email": "techsupport@glenair.com",
                "is_active": True,
            },
            "parts": [
                {
                    "part_number": "GLE-MS-09-35P",
                    "revision": "A",
                    "name": "MIL-DTL-38999 I Plug, Shell 09 with EMI Back-shell",
                    "designation": "MS-09-35P-EMI",
                    "description": (
                        "Straight plug, MIL-DTL-38999 Series I, shell size 09, "
                        "insert 09-35 (6 contacts), male pin inserts, integrated "
                        "EMI/RFI conductive back-shell with strain relief."
                    ),
                    "part_class": PartClass.CONNECTOR,
                    "lru_classification": LRUClass.COMPONENT,
                    "mass_kg": 0.075,
                    "dim_length_mm": 56.0,
                    "dim_width_mm": 17.0,
                    "dim_height_mm": 17.0,
                    "temp_operating_min_c": -65.0,
                    "temp_operating_max_c": 200.0,
                    "vibration_random_grms": 41.7,
                    "shock_mechanical_g": 300.0,
                    "humidity_max_pct": 100.0,
                    "altitude_max_m": 30000.0,
                    "mil_std_810_tested": True,
                    "mil_std_461_tested": True,
                    "lifecycle_status": LifecycleStatus.PREFERRED,
                    "rohs_compliant": True,
                    "connectors": [
                        {
                            "reference": "P1",
                            "position": 0,
                            "description": "Cable plug, male pin inserts, EMI back-shell",
                            "connector_type": "MIL-DTL-38999 Series I",
                            "shell_size": "09",
                            "insert_arrangement": "09-35",
                            "gender": ConnectorGender.MALE,
                            "pin_count": 6,
                            "keying": "Normal",
                            "mating_part_number": "MS27656T9B35S",
                            "pins": _make_pin_block_passive_6pin(),
                        },
                    ],
                },
            ],
        },
        # ── 5. Amphenol ──────────────────────────────────────────
        {
            "supplier": {
                "name": "Amphenol Aerospace",
                "short_name": "Amphenol",
                "cage_code": "77820",
                "country": "USA",
                "website": "https://www.amphenol-aerospace.com",
                "primary_email": "aerospace.sales@amphenol.com",
                "is_active": True,
            },
            "parts": [
                {
                    "part_number": "AMP-D38999-9P",
                    "revision": "B",
                    "name": "Filtered D-Sub 9-Pin (Test Equipment)",
                    "designation": "DSUB-9P-FLT",
                    "description": (
                        "Filtered D-subminiature 9-pin plug, RS-232/422 compatible; "
                        "common in lab test-equipment harnesses."
                    ),
                    "part_class": PartClass.CONNECTOR,
                    "lru_classification": LRUClass.COMPONENT,
                    "mass_kg": 0.025,
                    "dim_length_mm": 31.0,
                    "dim_width_mm": 17.0,
                    "dim_height_mm": 12.0,
                    "temp_operating_min_c": -55.0,
                    "temp_operating_max_c": 105.0,
                    "humidity_max_pct": 95.0,
                    "lifecycle_status": LifecycleStatus.ACTIVE,
                    "rohs_compliant": True,
                    "connectors": [
                        {
                            "reference": "P1",
                            "position": 0,
                            "description": "9-pin male D-sub, filtered",
                            "connector_type": "D-Sub Filtered",
                            "shell_size": "DE-9",
                            "insert_arrangement": "9C",
                            "gender": ConnectorGender.MALE,
                            "pin_count": 9,
                            "keying": None,
                            "mating_part_number": "DE-9S",
                            "pins": _make_pin_block_dsub9_rs422(),
                        },
                    ],
                },
            ],
        },
    ]


# ══════════════════════════════════════════════════════════════
#  Seed-user resolution
# ══════════════════════════════════════════════════════════════


def _ensure_seed_user(db: Session) -> User:
    user = db.query(User).filter(User.username == SEED_USER_USERNAME).first()
    if user is not None:
        return user
    # Pick any admin if one exists — preserves history attribution.
    admin = db.query(User).filter(User.role == UserRole.ADMIN.value).first()
    if admin is not None:
        return admin
    # Otherwise create a brand-new system seeder.
    user = User(
        username=SEED_USER_USERNAME,
        email=SEED_USER_EMAIL,
        hashed_password=get_password_hash("seed-only-no-login"),
        full_name="ASTRA Catalog Seeder",
        role=UserRole.ADMIN.value,
        department="System",
        is_active=False,  # not a login account
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ══════════════════════════════════════════════════════════════
#  Idempotent seed entrypoint
# ══════════════════════════════════════════════════════════════


def seed(db: Session) -> dict:
    """Idempotent seed. Returns counts of {suppliers_inserted, parts_inserted,
    connectors_inserted, pins_inserted, suppliers_skipped, parts_skipped}."""
    user = _ensure_seed_user(db)
    seed_data = _build_seed_data()

    counts = {
        "suppliers_inserted": 0,
        "suppliers_skipped": 0,
        "parts_inserted": 0,
        "parts_skipped": 0,
        "connectors_inserted": 0,
        "pins_inserted": 0,
    }

    for entry in seed_data:
        sup_data = entry["supplier"]
        sup = (
            db.query(Supplier)
            .filter(Supplier.name == sup_data["name"])
            .first()
        )
        if sup is None:
            sup = Supplier(created_by_id=user.id, **sup_data)
            db.add(sup)
            db.flush()
            counts["suppliers_inserted"] += 1
            logger.info("Inserted supplier: %s (id=%s)", sup.name, sup.id)
        else:
            counts["suppliers_skipped"] += 1
            logger.info("Skipped existing supplier: %s (id=%s)", sup.name, sup.id)

        for part_data in entry["parts"]:
            connectors_payload = list(part_data.get("connectors", []))
            existing = (
                db.query(CatalogPart)
                .filter(
                    CatalogPart.supplier_id == sup.id,
                    CatalogPart.part_number == part_data["part_number"],
                    CatalogPart.revision == part_data.get("revision"),
                )
                .first()
            )
            if existing is not None:
                counts["parts_skipped"] += 1
                logger.info(
                    "Skipped existing part: %s %s (id=%s)",
                    sup.name, part_data["part_number"], existing.id,
                )
                continue

            # Strip nested before passing kwargs to CatalogPart(**...)
            part_kwargs = {k: v for k, v in part_data.items() if k != "connectors"}
            part = CatalogPart(
                supplier_id=sup.id,
                created_by_id=user.id,
                **part_kwargs,
            )
            db.add(part)
            db.flush()
            counts["parts_inserted"] += 1
            logger.info(
                "Inserted part: %s %s rev=%s (id=%s)",
                sup.name, part.part_number, part.revision, part.id,
            )

            for c_payload in connectors_payload:
                pins_payload = list(c_payload.get("pins", []))
                conn_kwargs = {k: v for k, v in c_payload.items() if k != "pins"}
                conn = CatalogConnector(catalog_part_id=part.id, **conn_kwargs)
                db.add(conn)
                db.flush()
                counts["connectors_inserted"] += 1
                for p in pins_payload:
                    db.add(CatalogPin(catalog_connector_id=conn.id, **p))
                counts["pins_inserted"] += len(pins_payload)

    db.commit()
    return counts


def main() -> int:
    db = SessionLocal()
    try:
        counts = seed(db)
        logger.info("=" * 60)
        logger.info("Seed summary:")
        for k, v in counts.items():
            logger.info("  %-22s %s", k, v)
        logger.info("=" * 60)
        return 0
    except Exception:    # noqa: BLE001
        db.rollback()
        logger.exception("Seed failed — rolled back")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
