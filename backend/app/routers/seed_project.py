"""
ASTRA — Project-Scoped Data Seeder
=====================================
File: backend/app/routers/seed_project.py

New endpoint: POST /api/v1/dev/seed-project/{project_id}

Populates a project with realistic aerospace/defense requirements data:
  - 48 requirements across L1–L5 with proper parent-child hierarchy
  - 30+ trace links (decomposition, satisfaction, verification)
  - 20 verifications (mixed statuses)
  - 5 source artifacts
  - 2 baselines
  - Quality scores varying from 45 to 95

All SHALL statements follow NASA SE Handbook Appendix C guidelines.
All enum values use lowercase to match the DB enum definitions.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import (
    User, Project, Requirement, SourceArtifact, TraceLink,
    Verification, RequirementHistory, Baseline, BaselineRequirement,
    Comment,
)
from app.services.quality_checker import check_requirement_quality

router = APIRouter(prefix="/dev", tags=["dev"])


# ══════════════════════════════════════════════════════════
#  Source Artifacts (5)
# ══════════════════════════════════════════════════════════

SEED_ARTIFACTS = [
    {
        "artifact_id": "SA-MRD-001",
        "title": "Mission Requirements Document (MRD)",
        "artifact_type": "document",
        "description": "Top-level mission requirements from the sponsoring agency defining the operational need for a satellite-deployed kinetic interceptor system.",
        "participants": ["Col. Harris", "Dr. Patel", "Mason"],
    },
    {
        "artifact_id": "SA-SAD-001",
        "title": "System Architecture Document (SAD)",
        "artifact_type": "document",
        "description": "Defines the high-level system decomposition into radar, IR, C2, interceptor, and telemetry subsystems with interface boundaries.",
        "participants": ["Chen", "Dr. Kim", "Mason"],
    },
    {
        "artifact_id": "SA-SAR-001",
        "title": "Safety Analysis Report (SAR)",
        "artifact_type": "document",
        "description": "Preliminary hazard analysis per MIL-STD-882E identifying 14 hazards with risk mitigation requirements.",
        "participants": ["Jess", "Dr. Lopez"],
    },
    {
        "artifact_id": "SA-ICD-001",
        "title": "Interface Control Document (ICD)",
        "artifact_type": "document",
        "description": "Defines all external and internal interfaces including ground station uplink/downlink, inter-subsystem data buses, and power distribution.",
        "participants": ["Chen", "Priya", "Hank"],
    },
    {
        "artifact_id": "SA-TP-001",
        "title": "System Verification Test Plan (SVTP)",
        "artifact_type": "document",
        "description": "Master test plan covering all verification activities including hardware-in-the-loop simulation, analysis, inspection, and demonstration events.",
        "participants": ["Jess", "Chen", "Mason"],
    },
]


# ══════════════════════════════════════════════════════════
#  Requirements — 48 across L1–L5 with hierarchy
#  Format: (req_id_suffix, title, statement, rationale, type, priority, level, parent_key, quality_override)
#  parent_key references another requirement by its req_id_suffix
# ══════════════════════════════════════════════════════════

SEED_REQUIREMENTS: List[dict] = [
    # ─────────────── L1 System Requirements (8) ───────────────
    {
        "key": "FR-001", "title": "Target Detection",
        "statement": "The system shall detect ballistic missile targets at a range of no less than 2000 km with a probability of detection of 0.95 or greater.",
        "rationale": "Early detection is critical to enabling interceptor trajectory computation and launch within the required engagement timeline.",
        "req_type": "functional", "priority": "critical", "level": "L1", "parent_key": None,
    },
    {
        "key": "FR-002", "title": "Target Tracking",
        "statement": "The system shall maintain continuous track on a detected target with a track update rate of no less than 10 Hz and a position accuracy of 50 meters CEP or better.",
        "rationale": "Continuous tracking with sufficient accuracy enables the fire control solution to converge within the engagement window.",
        "req_type": "functional", "priority": "critical", "level": "L1", "parent_key": None,
    },
    {
        "key": "FR-003", "title": "Missile Launch Execution",
        "statement": "The system shall execute a kinetic interceptor launch within 45 seconds of receiving a valid fire command from the command authority.",
        "rationale": "The engagement timeline requires rapid launch to achieve intercept geometry within the kinematic boundary.",
        "req_type": "functional", "priority": "critical", "level": "L1", "parent_key": None,
    },
    {
        "key": "PR-001", "title": "Detection Range Performance",
        "statement": "The system shall achieve an effective detection range of 2500 km against a 1-square-meter radar cross section target under clear-sky conditions.",
        "rationale": "Extended detection range provides additional engagement timeline margin and enables multiple intercept opportunities.",
        "req_type": "performance", "priority": "high", "level": "L1", "parent_key": None,
    },
    {
        "key": "PR-002", "title": "System Response Time",
        "statement": "The system shall complete the detect-to-launch sequence in no more than 120 seconds from initial target detection to interceptor release.",
        "rationale": "End-to-end response time drives the maximum engagement range and determines single-shot versus salvo engagement capability.",
        "req_type": "performance", "priority": "critical", "level": "L1", "parent_key": None,
    },
    {
        "key": "IR-001", "title": "Ground Station Interface",
        "statement": "The system shall interface with the ground station command and control segment via MIL-STD-1553B data bus at a minimum data rate of 1 Mbps.",
        "rationale": "Ground station interoperability is required for mission planning, real-time command, and post-mission data download.",
        "req_type": "interface", "priority": "high", "level": "L1", "parent_key": None,
    },
    {
        "key": "SAF-001", "title": "Failsafe Mode",
        "statement": "The system shall enter a safe state within 500 milliseconds of detecting any single-point failure in the launch sequencing subsystem, preventing unintended ordnance release.",
        "rationale": "Failsafe mode is mandatory per MIL-STD-882E to prevent catastrophic hazard from inadvertent launch.",
        "req_type": "safety", "priority": "critical", "level": "L1", "parent_key": None,
    },
    {
        "key": "SR-001", "title": "Command Encryption",
        "statement": "The system shall encrypt all command and telemetry links using AES-256 encryption with NSA Type 1 certified key management.",
        "rationale": "Command link security prevents adversarial spoofing or jamming that could result in mission failure or fratricide.",
        "req_type": "security", "priority": "critical", "level": "L1", "parent_key": None,
    },

    # ─────────────── L2 Subsystem Requirements (15) ───────────────
    {
        "key": "FR-004", "title": "Radar Signal Processing",
        "statement": "The radar subsystem shall process raw antenna returns and generate target detection reports within 200 milliseconds of pulse reception.",
        "rationale": "Processing latency directly impacts the track update rate and overall system response time budget.",
        "req_type": "functional", "priority": "high", "level": "L2", "parent_key": "FR-001",
    },
    {
        "key": "FR-005", "title": "Infrared Detection",
        "statement": "The infrared sensor subsystem shall detect target thermal signatures in the 3-5 micrometer MWIR band with a noise equivalent irradiance of no greater than 1e-12 W/cm².",
        "rationale": "Dual-mode detection (radar + IR) improves detection probability and reduces false alarm rate.",
        "req_type": "functional", "priority": "high", "level": "L2", "parent_key": "FR-001",
    },
    {
        "key": "FR-006", "title": "Multi-Target Correlation",
        "statement": "The tracking subsystem shall correlate radar and IR detections for up to 20 simultaneous targets with a correct association probability of 0.98 or greater.",
        "rationale": "Multi-sensor correlation is required to maintain track accuracy in a multi-target threat environment.",
        "req_type": "functional", "priority": "high", "level": "L2", "parent_key": "FR-002",
    },
    {
        "key": "FR-007", "title": "Track Prediction Algorithm",
        "statement": "The tracking subsystem shall predict target position 60 seconds ahead with a prediction error of no more than 200 meters RMS using an extended Kalman filter.",
        "rationale": "Accurate track prediction is required for fire control solution convergence and interceptor midcourse guidance.",
        "req_type": "functional", "priority": "high", "level": "L2", "parent_key": "FR-002",
    },
    {
        "key": "FR-008", "title": "Launch Sequence Controller",
        "statement": "The launch controller shall execute the 12-step launch sequence including power-up, alignment, arm, and release in the correct order with no step taking more than 5 seconds.",
        "rationale": "Deterministic launch sequencing ensures the 45-second launch timeline requirement is achievable.",
        "req_type": "functional", "priority": "critical", "level": "L2", "parent_key": "FR-003",
    },
    {
        "key": "FR-009", "title": "Warhead Arming Logic",
        "statement": "The warhead arming subsystem shall arm the interceptor warhead only after confirming three independent safety interlocks have been released in the correct sequence.",
        "rationale": "Triple-interlock arming logic prevents inadvertent detonation per MIL-STD-1316 requirements.",
        "req_type": "functional", "priority": "critical", "level": "L2", "parent_key": "FR-003",
    },
    {
        "key": "PR-003", "title": "Radar Range Resolution",
        "statement": "The radar subsystem shall achieve a range resolution of 15 meters or better at the maximum detection range of 2500 km.",
        "rationale": "Range resolution drives the ability to discriminate closely-spaced objects and resolve countermeasure decoys.",
        "req_type": "performance", "priority": "high", "level": "L2", "parent_key": "PR-001",
    },
    {
        "key": "PR-004", "title": "Track Update Rate",
        "statement": "The tracking subsystem shall provide target state updates to the fire control computer at a rate of no less than 10 Hz per tracked target.",
        "rationale": "The fire control solution convergence time is directly proportional to the track update rate.",
        "req_type": "performance", "priority": "high", "level": "L2", "parent_key": "PR-002",
    },
    {
        "key": "IR-002", "title": "Telemetry Downlink",
        "statement": "The telemetry subsystem shall transmit interceptor health and status data to the ground station at a rate of 256 kbps with a bit error rate of no more than 1e-6.",
        "rationale": "Real-time telemetry enables ground operators to monitor interceptor status and abort if necessary.",
        "req_type": "interface", "priority": "medium", "level": "L2", "parent_key": "IR-001",
    },
    {
        "key": "IR-003", "title": "Command Uplink",
        "statement": "The command receiver shall accept ground station commands via S-band uplink at 64 kbps with anti-jam processing gain of 30 dB.",
        "rationale": "Robust command uplink ensures ground authority can issue abort or retarget commands in a contested RF environment.",
        "req_type": "interface", "priority": "high", "level": "L2", "parent_key": "IR-001",
    },
    {
        "key": "SAF-002", "title": "Launch Abort Capability",
        "statement": "The system shall execute a launch abort sequence within 200 milliseconds of receiving an abort command, de-energizing all launch circuits and safing the interceptor.",
        "rationale": "Rapid abort capability is required to prevent launch in the event of target misidentification or change in rules of engagement.",
        "req_type": "safety", "priority": "critical", "level": "L2", "parent_key": "SAF-001",
    },
    {
        "key": "SAF-003", "title": "Flight Termination System",
        "statement": "The interceptor shall include an independent flight termination system capable of destroying the vehicle within 3 seconds of activation at any point in the flight envelope.",
        "rationale": "Flight termination prevents collateral damage from a malfunctioning interceptor per range safety requirements.",
        "req_type": "safety", "priority": "critical", "level": "L2", "parent_key": "SAF-001",
    },
    {
        "key": "SR-002", "title": "Key Management",
        "statement": "The key management subsystem shall support over-the-air rekeying of AES-256 encryption keys with a key changeover time of no more than 50 milliseconds.",
        "rationale": "Rapid rekeying capability ensures continued secure communications during extended mission operations.",
        "req_type": "security", "priority": "high", "level": "L2", "parent_key": "SR-001",
    },
    {
        "key": "SR-003", "title": "Command Authentication",
        "statement": "The command receiver shall authenticate all incoming commands using HMAC-SHA-256 message authentication codes and reject any command failing authentication within 10 milliseconds.",
        "rationale": "Command authentication prevents adversarial command injection attacks on the interceptor system.",
        "req_type": "security", "priority": "high", "level": "L2", "parent_key": "SR-001",
    },
    {
        "key": "ER-001", "title": "Space Environment Survivability",
        "statement": "The system shall operate within specification after exposure to a total ionizing dose of 100 krad(Si) over the 7-year mission life.",
        "rationale": "Radiation hardness ensures system reliability in the geosynchronous orbit radiation environment.",
        "req_type": "environmental", "priority": "high", "level": "L2", "parent_key": None,
    },

    # ─────────────── L3 Component Requirements (15) ───────────────
    {
        "key": "FR-010", "title": "Pulse Compression Processor",
        "statement": "The radar signal processor shall implement linear frequency modulated pulse compression with a compression ratio of no less than 1000:1.",
        "rationale": "Pulse compression provides the required range resolution while maintaining transmitter peak power within thermal limits.",
        "req_type": "functional", "priority": "high", "level": "L3", "parent_key": "FR-004",
    },
    {
        "key": "FR-011", "title": "Clutter Rejection Filter",
        "statement": "The signal processor shall reject ground clutter returns with a minimum improvement factor of 60 dB using adaptive space-time adaptive processing.",
        "rationale": "Clutter rejection is essential for detecting low-RCS targets against terrain backgrounds.",
        "req_type": "functional", "priority": "high", "level": "L3", "parent_key": "FR-004",
    },
    {
        "key": "FR-012", "title": "IR Focal Plane Array",
        "statement": "The MWIR focal plane array shall provide a minimum of 640x512 pixels with a pixel pitch of 15 micrometers and an operability of 99.5 percent.",
        "rationale": "Array size and operability drive the instantaneous field of regard and detection sensitivity.",
        "req_type": "functional", "priority": "high", "level": "L3", "parent_key": "FR-005",
    },
    {
        "key": "FR-013", "title": "IR Signal Conditioning",
        "statement": "The IR signal conditioning electronics shall digitize focal plane array output at 14-bit resolution with a frame rate of no less than 60 Hz.",
        "rationale": "Digitization resolution and frame rate determine the minimum detectable signal and tracking precision.",
        "req_type": "functional", "priority": "medium", "level": "L3", "parent_key": "FR-005",
    },
    {
        "key": "FR-014", "title": "Track Association Algorithm",
        "statement": "The multi-sensor track associator shall use a Joint Probabilistic Data Association filter with a maximum computation time of 50 milliseconds per update cycle.",
        "rationale": "JPDAF provides optimal multi-target association while meeting the real-time processing budget.",
        "req_type": "functional", "priority": "high", "level": "L3", "parent_key": "FR-006",
    },
    {
        "key": "FR-015", "title": "Kalman Filter Implementation",
        "statement": "The extended Kalman filter shall maintain a 9-state target model including position, velocity, and acceleration in three dimensions with a filter update rate matching the track update rate.",
        "rationale": "A 9-state model captures ballistic target dynamics including drag and gravity perturbations.",
        "req_type": "functional", "priority": "high", "level": "L3", "parent_key": "FR-007",
    },
    {
        "key": "FR-016", "title": "Launch Sequencer State Machine",
        "statement": "The launch sequence controller shall implement a deterministic state machine with 12 states and no more than 2 transitions per state, logging all state transitions to non-volatile memory.",
        "rationale": "Deterministic state machine design prevents race conditions and enables post-mission fault analysis.",
        "req_type": "functional", "priority": "critical", "level": "L3", "parent_key": "FR-008",
    },
    {
        "key": "FR-017", "title": "Safety Interlock Controller",
        "statement": "Each safety interlock controller shall independently verify arm conditions using a separate sensor input and processor, with no shared failure modes between controllers.",
        "rationale": "Independent interlock verification ensures no single-point failure can defeat the arming safeguards.",
        "req_type": "functional", "priority": "critical", "level": "L3", "parent_key": "FR-009",
    },
    {
        "key": "PR-005", "title": "Radar Transmitter Power",
        "statement": "The radar transmitter shall deliver a peak power of no less than 500 watts with a duty cycle of 10 percent and a pulse repetition frequency selectable from 1 to 10 kHz.",
        "rationale": "Transmitter power and duty cycle determine the radar energy budget required for the specified detection range.",
        "req_type": "performance", "priority": "high", "level": "L3", "parent_key": "PR-003",
    },
    {
        "key": "PR-006", "title": "Tracking Processor Throughput",
        "statement": "The tracking processor shall maintain real-time performance processing 20 simultaneous tracks at 10 Hz each with a CPU utilization of no more than 70 percent.",
        "rationale": "Processor margin ensures deterministic timing under worst-case multi-target loading.",
        "req_type": "performance", "priority": "high", "level": "L3", "parent_key": "PR-004",
    },
    {
        "key": "IR-004", "title": "Telemetry Encoder",
        "statement": "The telemetry encoder shall format interceptor health data into IRIG-106 Chapter 4 compliant packets with Reed-Solomon forward error correction providing 6 dB coding gain.",
        "rationale": "Standardized telemetry format and FEC ensure ground station compatibility and link reliability.",
        "req_type": "interface", "priority": "medium", "level": "L3", "parent_key": "IR-002",
    },
    {
        "key": "IR-005", "title": "Command Decoder",
        "statement": "The command decoder shall parse and validate ground station command packets within 5 milliseconds and reject malformed packets with a false acceptance rate of less than 1e-9.",
        "rationale": "Rapid command decoding ensures timely response while extremely low false acceptance prevents unintended actions.",
        "req_type": "interface", "priority": "high", "level": "L3", "parent_key": "IR-003",
    },
    {
        "key": "SAF-004", "title": "Abort Circuit Design",
        "statement": "The abort circuit shall use a fail-safe open design with redundant relay paths such that loss of power results in automatic launch inhibit.",
        "rationale": "Fail-safe open design ensures that any power failure automatically prevents launch, the safest default state.",
        "req_type": "safety", "priority": "critical", "level": "L3", "parent_key": "SAF-002",
    },
    {
        "key": "SAF-005", "title": "FTS Receiver",
        "statement": "The flight termination receiver shall operate on two independent frequencies with a receiver sensitivity of -110 dBm and a command authentication latency of no more than 100 milliseconds.",
        "rationale": "Dual-frequency FTS receiver ensures termination capability even under single-frequency jamming conditions.",
        "req_type": "safety", "priority": "critical", "level": "L3", "parent_key": "SAF-003",
    },
    {
        "key": "ER-002", "title": "Thermal Control System",
        "statement": "The thermal control system shall maintain all electronic assemblies within their qualified operating temperature range of -20 to +65 degrees Celsius throughout all mission phases.",
        "rationale": "Temperature control ensures electronic component reliability during orbital thermal cycling.",
        "req_type": "environmental", "priority": "medium", "level": "L3", "parent_key": "ER-001",
    },

    # ─────────────── L4 Sub-component Requirements (7) ───────────────
    {
        "key": "FR-018", "title": "ADC Sampling Rate",
        "statement": "The radar analog-to-digital converter shall sample the intermediate frequency signal at a rate of no less than 200 MHz with 12-bit resolution and a spurious-free dynamic range of 70 dBc.",
        "rationale": "ADC performance directly limits the radar instantaneous bandwidth and dynamic range.",
        "req_type": "functional", "priority": "high", "level": "L4", "parent_key": "FR-010",
    },
    {
        "key": "FR-019", "title": "FPGA Processing Core",
        "statement": "The signal processing FPGA shall implement the pulse compression and Doppler filtering algorithms with a worst-case processing latency of no more than 100 microseconds per pulse.",
        "rationale": "FPGA processing latency must be bounded to guarantee real-time signal processing throughput.",
        "req_type": "functional", "priority": "high", "level": "L4", "parent_key": "FR-010",
    },
    {
        "key": "FR-020", "title": "IR Cooler Assembly",
        "statement": "The Stirling cycle cooler shall cool the focal plane array to 77 Kelvin plus or minus 0.5 Kelvin with a cool-down time of no more than 8 minutes from ambient.",
        "rationale": "Precise temperature control is required for MWIR detector sensitivity and uniformity.",
        "req_type": "functional", "priority": "high", "level": "L4", "parent_key": "FR-012",
    },
    {
        "key": "FR-021", "title": "State Machine Watchdog Timer",
        "statement": "The launch sequencer watchdog timer shall reset the state machine to the safe state if any single state persists for more than 10 seconds without a valid transition.",
        "rationale": "Watchdog timer prevents launch sequence hang conditions that could leave the system in an unsafe intermediate state.",
        "req_type": "functional", "priority": "critical", "level": "L4", "parent_key": "FR-016",
    },
    {
        "key": "PR-007", "title": "Power Amplifier Efficiency",
        "statement": "The radar solid-state power amplifier shall achieve a power-added efficiency of no less than 40 percent at the rated peak output power.",
        "rationale": "Amplifier efficiency determines the thermal dissipation budget and drives thermal control system sizing.",
        "req_type": "performance", "priority": "medium", "level": "L4", "parent_key": "PR-005",
    },
    {
        "key": "SAF-006", "title": "Relay Contact Rating",
        "statement": "Each abort relay shall be rated for a minimum of 10000 operations at full load current with a contact resistance of no more than 100 milliohms.",
        "rationale": "Relay reliability rating ensures abort circuit functionality over the system operational life with margin.",
        "req_type": "safety", "priority": "high", "level": "L4", "parent_key": "SAF-004",
    },
    {
        "key": "ER-003", "title": "Heat Pipe Assembly",
        "statement": "The heat pipe assembly shall transport no less than 50 watts of thermal energy from the radar transmitter to the radiator panel with a thermal resistance of no more than 0.5 degrees Celsius per watt.",
        "rationale": "Heat pipe capacity must exceed worst-case transmitter dissipation to prevent thermal runaway.",
        "req_type": "environmental", "priority": "medium", "level": "L4", "parent_key": "ER-002",
    },

    # ─────────────── L5 Detail / Part-Level Requirements (3) ───────────────
    {
        "key": "FR-022", "title": "ADC Clock Jitter",
        "statement": "The ADC sampling clock shall exhibit a maximum RMS jitter of 0.5 picoseconds to maintain the specified spurious-free dynamic range at the 200 MHz sampling rate.",
        "rationale": "Clock jitter directly degrades ADC SFDR per the relationship SFDR = -20log(2*pi*f_in*tj_rms).",
        "req_type": "functional", "priority": "medium", "level": "L5", "parent_key": "FR-018",
    },
    {
        "key": "PR-008", "title": "FPGA Clock Speed",
        "statement": "The signal processing FPGA shall operate at a core clock frequency of no less than 250 MHz with timing closure achieved at worst-case process, voltage, and temperature conditions.",
        "rationale": "Clock frequency determines the processing throughput margin for real-time pulse compression.",
        "req_type": "performance", "priority": "medium", "level": "L5", "parent_key": "FR-019",
    },
    {
        "key": "SAF-007", "title": "Relay Coil Suppression Diode",
        "statement": "Each abort relay coil shall include a transient suppression diode rated at 2 times the coil voltage with a response time of no more than 5 nanoseconds.",
        "rationale": "Coil suppression prevents voltage transients from corrupting adjacent digital circuits during relay switching.",
        "req_type": "safety", "priority": "low", "level": "L5", "parent_key": "SAF-006",
    },
]


# ══════════════════════════════════════════════════════════
#  Verification Seeds — method, criteria, status
#  References requirements by key
# ══════════════════════════════════════════════════════════

SEED_VERIFICATIONS = [
    # L1 verifications
    {"req_key": "FR-001", "method": "test", "status": "pass",
     "criteria": "Demonstrate detection of calibrated 1m² RCS target at 2000 km in HWIL simulation. PD >= 0.95 over 100 trials."},
    {"req_key": "FR-002", "method": "test", "status": "pass",
     "criteria": "Verify 10 Hz track update rate and < 50m CEP against simulated ballistic trajectory."},
    {"req_key": "FR-003", "method": "demonstration", "status": "in_progress",
     "criteria": "Demonstrate 45-second launch timeline from fire command to interceptor release in integrated ground test."},
    {"req_key": "PR-001", "method": "analysis", "status": "pass",
     "criteria": "Radar range equation analysis showing Pd >= 0.95 at 2500 km for 1m² RCS with link budget margin >= 3 dB."},
    {"req_key": "PR-002", "method": "test", "status": "planned",
     "criteria": "End-to-end timeline test from simulated target injection to launch command generation."},
    {"req_key": "IR-001", "method": "inspection", "status": "pass",
     "criteria": "Inspect ICD compliance: verify MIL-STD-1553B bus implementation and measure sustained data rate >= 1 Mbps."},
    {"req_key": "SAF-001", "method": "test", "status": "pass",
     "criteria": "Inject 15 single-point failure modes and verify safe state entry within 500 ms for each."},
    {"req_key": "SR-001", "method": "inspection", "status": "pass",
     "criteria": "Verify NSA Type 1 certification documentation and AES-256 implementation compliance."},

    # L2 verifications
    {"req_key": "FR-004", "method": "test", "status": "pass",
     "criteria": "Measure signal processing latency from pulse reception to detection report. Must be < 200 ms."},
    {"req_key": "FR-006", "method": "test", "status": "fail",
     "criteria": "Run 1000-trial Monte Carlo with 20 simultaneous targets. Association probability must be >= 0.98. [FAILED: achieved 0.96]"},
    {"req_key": "FR-008", "method": "demonstration", "status": "pass",
     "criteria": "Step through all 12 launch sequence states and verify correct ordering and per-step timing < 5s."},
    {"req_key": "FR-009", "method": "test", "status": "pass",
     "criteria": "Verify triple interlock sequence. Attempt arming with each interlock permutation; only correct sequence enables."},
    {"req_key": "SAF-002", "method": "test", "status": "in_progress",
     "criteria": "Issue abort command at each launch sequence state and verify de-energization within 200 ms."},
    {"req_key": "SAF-003", "method": "demonstration", "status": "planned",
     "criteria": "Demonstrate FTS activation and vehicle destruction within 3 seconds. (Scheduled for Flight Test 2)"},
    {"req_key": "SR-002", "method": "test", "status": "pass",
     "criteria": "Execute OTA rekey sequence and measure key changeover time. Must complete within 50 ms."},

    # L3 verifications
    {"req_key": "FR-010", "method": "analysis", "status": "pass",
     "criteria": "Verify pulse compression ratio >= 1000:1 through matched filter analysis and HWIL measurement."},
    {"req_key": "FR-016", "method": "inspection", "status": "pass",
     "criteria": "Code inspection of state machine HDL: verify 12 states, max 2 transitions/state, NVM logging on all transitions."},
    {"req_key": "FR-017", "method": "analysis", "status": "in_progress",
     "criteria": "Fault tree analysis showing no shared failure modes between the three independent interlock controllers."},
    {"req_key": "SAF-004", "method": "inspection", "status": "pass",
     "criteria": "Schematic review: verify fail-safe open relay design with redundant paths."},
    {"req_key": "SAF-005", "method": "test", "status": "planned",
     "criteria": "Test FTS receiver sensitivity at -110 dBm on both frequencies and measure authentication latency."},
]


# ══════════════════════════════════════════════════════════
#  Endpoint
# ══════════════════════════════════════════════════════════

@router.post("/seed-project/{project_id}")
def seed_project_data(project_id: int, db: Session = Depends(get_db)):
    """
    Populate an existing project with a full set of realistic aerospace/defense
    requirements, trace links, verifications, source artifacts, and baselines.

    Idempotent: if the project already has 20+ requirements, returns early.
    """
    # ── Validate project ──
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, f"Project {project_id} not found")

    # Get the project owner (or first admin)
    owner = db.query(User).filter(User.id == project.owner_id).first()
    if not owner:
        owner = db.query(User).filter(User.role == "admin").first()
    if not owner:
        raise HTTPException(400, "No admin user found. Run /dev/seed first.")

    # ── Idempotency check ──
    existing_count = db.query(func.count(Requirement.id)).filter(
        Requirement.project_id == project_id
    ).scalar()
    if existing_count >= 20:
        return {
            "status": "already_seeded",
            "project_id": project_id,
            "existing_requirements": existing_count,
        }

    # ══════════════════════════════════════
    #  Step 1: Source Artifacts
    # ══════════════════════════════════════
    artifact_map: Dict[str, SourceArtifact] = {}
    for a in SEED_ARTIFACTS:
        artifact = SourceArtifact(
            artifact_id=a["artifact_id"],
            title=a["title"],
            artifact_type=a["artifact_type"],
            description=a["description"],
            participants=a["participants"],
            project_id=project_id,
            created_by_id=owner.id,
        )
        db.add(artifact)
        db.flush()
        artifact_map[a["artifact_id"]] = artifact

    # ══════════════════════════════════════
    #  Step 2: Requirements (48)
    # ══════════════════════════════════════
    req_map: Dict[str, Requirement] = {}  # key -> Requirement ORM instance

    # Status distribution for realism
    status_cycle = [
        "draft", "under_review", "approved", "baselined", "approved",
        "approved", "baselined", "approved", "under_review", "approved",
        "baselined", "verified", "approved", "approved", "baselined",
        "approved", "draft", "under_review", "approved", "baselined",
        "approved", "approved", "baselined", "under_review", "approved",
        "approved", "baselined", "approved", "approved", "draft",
        "approved", "baselined", "approved", "approved", "under_review",
        "approved", "approved", "baselined", "approved", "approved",
        "approved", "baselined", "approved", "approved", "verified",
        "approved", "draft", "approved",
    ]

    for i, seed in enumerate(SEED_REQUIREMENTS):
        # Compute quality score
        quality = check_requirement_quality(
            seed["statement"], seed["title"], seed.get("rationale", "")
        )

        # Resolve parent
        parent_id = None
        if seed["parent_key"] and seed["parent_key"] in req_map:
            parent_id = req_map[seed["parent_key"]].id

        status = status_cycle[i % len(status_cycle)]

        req = Requirement(
            req_id=seed["key"],
            title=seed["title"],
            statement=seed["statement"],
            rationale=seed.get("rationale"),
            req_type=seed["req_type"],
            priority=seed["priority"],
            status=status,
            level=seed["level"],
            project_id=project_id,
            parent_id=parent_id,
            owner_id=owner.id,
            created_by_id=owner.id,
            quality_score=quality["score"],
            version=1,
        )
        db.add(req)
        db.flush()
        req_map[seed["key"]] = req

        # Record creation history
        history = RequirementHistory(
            requirement_id=req.id,
            version=1,
            field_changed="created",
            old_value=None,
            new_value=req.req_id,
            change_description=f"Requirement {req.req_id} created via project seeder",
            changed_by_id=owner.id,
        )
        db.add(history)

    db.flush()

    # ══════════════════════════════════════
    #  Step 3: Trace Links (decomposition + satisfaction + verification)
    # ══════════════════════════════════════

    trace_links_created = 0

    # 3a. Decomposition links: parent → child
    for seed in SEED_REQUIREMENTS:
        if seed["parent_key"] and seed["parent_key"] in req_map:
            parent_req = req_map[seed["parent_key"]]
            child_req = req_map[seed["key"]]
            link = TraceLink(
                source_type="requirement",
                source_id=parent_req.id,
                target_type="requirement",
                target_id=child_req.id,
                link_type="decomposition",
                description=f"Decomposition: {parent_req.req_id} → {child_req.req_id}",
                status="active",
                created_by_id=owner.id,
            )
            db.add(link)
            trace_links_created += 1

    # 3b. Satisfaction links: L1 reqs → source artifacts
    satisfaction_map = {
        "FR-001": "SA-MRD-001",
        "FR-002": "SA-MRD-001",
        "FR-003": "SA-MRD-001",
        "PR-001": "SA-MRD-001",
        "PR-002": "SA-MRD-001",
        "IR-001": "SA-ICD-001",
        "SAF-001": "SA-SAR-001",
        "SR-001": "SA-MRD-001",
        # L2 satisfaction links to architecture
        "FR-004": "SA-SAD-001",
        "FR-005": "SA-SAD-001",
        "FR-006": "SA-SAD-001",
        "FR-007": "SA-SAD-001",
        "FR-008": "SA-SAD-001",
        "FR-009": "SA-SAR-001",
        "IR-002": "SA-ICD-001",
        "IR-003": "SA-ICD-001",
        "SAF-002": "SA-SAR-001",
        "SAF-003": "SA-SAR-001",
        "ER-001": "SA-SAD-001",
    }
    for req_key, art_id in satisfaction_map.items():
        if req_key in req_map and art_id in artifact_map:
            link = TraceLink(
                source_type="source_artifact",
                source_id=artifact_map[art_id].id,
                target_type="requirement",
                target_id=req_map[req_key].id,
                link_type="satisfaction",
                description=f"Satisfies: {art_id} → {req_key}",
                status="active",
                created_by_id=owner.id,
            )
            db.add(link)
            trace_links_created += 1

    # 3c. Cross-cutting dependency links
    dependency_pairs = [
        ("FR-008", "SAF-002"),   # Launch controller depends on abort capability
        ("FR-009", "SAF-001"),   # Warhead arming depends on failsafe
        ("IR-003", "SR-003"),    # Command uplink depends on authentication
        ("IR-002", "SR-001"),    # Telemetry depends on encryption
        ("PR-004", "FR-006"),    # Track update drives multi-target correlation
        ("FR-003", "PR-002"),    # Launch execution depends on response time
    ]
    for src_key, tgt_key in dependency_pairs:
        if src_key in req_map and tgt_key in req_map:
            link = TraceLink(
                source_type="requirement",
                source_id=req_map[src_key].id,
                target_type="requirement",
                target_id=req_map[tgt_key].id,
                link_type="dependency",
                description=f"Dependency: {src_key} → {tgt_key}",
                status="active",
                created_by_id=owner.id,
            )
            db.add(link)
            trace_links_created += 1

    db.flush()

    # ══════════════════════════════════════
    #  Step 4: Verifications (20)
    # ══════════════════════════════════════

    verif_count = 0
    for v in SEED_VERIFICATIONS:
        if v["req_key"] not in req_map:
            continue
        req = req_map[v["req_key"]]
        verif = Verification(
            requirement_id=req.id,
            method=v["method"],
            status=v["status"],
            criteria=v["criteria"],
            responsible_id=owner.id,
            evidence=f"See {artifact_map.get('SA-TP-001', {}).title if 'SA-TP-001' in artifact_map else 'SVTP'}" if v["status"] in ("pass", "fail") else None,
            completed_at=datetime.utcnow() - timedelta(days=5) if v["status"] in ("pass", "fail") else None,
        )
        db.add(verif)
        verif_count += 1

        # Also create verification trace links
        link = TraceLink(
            source_type="requirement",
            source_id=req.id,
            target_type="verification",
            target_id=0,  # Will be updated after flush
            link_type="verification",
            description=f"Verification: {req.req_id} ({v['method']})",
            status="active",
            created_by_id=owner.id,
        )
        db.add(link)
        db.flush()
        # Update the target_id now that verification has an ID
        link.target_id = verif.id
        trace_links_created += 1

    db.flush()

    # ══════════════════════════════════════
    #  Step 5: Baselines (2)
    # ══════════════════════════════════════

    # Baseline 1: SRR — first 30 requirements
    srr_reqs = list(req_map.values())[:30]
    baseline1 = Baseline(
        name="SRR Baseline v1.0",
        description="System Requirements Review baseline — initial 30 requirements covering L1 and L2 decomposition.",
        project_id=project_id,
        requirements_count=len(srr_reqs),
        created_by_id=owner.id,
        created_at=datetime.utcnow() - timedelta(days=30),
    )
    db.add(baseline1)
    db.flush()

    for req in srr_reqs:
        br = BaselineRequirement(
            baseline_id=baseline1.id,
            requirement_id=req.id,
            req_id_snapshot=req.req_id,
            title_snapshot=req.title,
            statement_snapshot=req.statement,
            rationale_snapshot=req.rationale or "",
            status_snapshot="approved",
            level_snapshot=req.level if isinstance(req.level, str) else (req.level.value if hasattr(req.level, "value") else str(req.level)),
        )
        db.add(br)

    # Baseline 2: PDR — all 48 requirements
    all_reqs = list(req_map.values())
    baseline2 = Baseline(
        name="PDR Baseline v1.1",
        description="Preliminary Design Review baseline — full L1–L5 decomposition with 48 requirements.",
        project_id=project_id,
        requirements_count=len(all_reqs),
        created_by_id=owner.id,
        created_at=datetime.utcnow() - timedelta(days=7),
    )
    db.add(baseline2)
    db.flush()

    for req in all_reqs:
        br = BaselineRequirement(
            baseline_id=baseline2.id,
            requirement_id=req.id,
            req_id_snapshot=req.req_id,
            title_snapshot=req.title,
            statement_snapshot=req.statement,
            rationale_snapshot=req.rationale or "",
            status_snapshot="approved",
            level_snapshot=req.level if isinstance(req.level, str) else (req.level.value if hasattr(req.level, "value") else str(req.level)),
        )
        db.add(br)

    # ══════════════════════════════════════
    #  Step 6: A few seed comments for realism
    # ══════════════════════════════════════

    seed_comments = [
        ("FR-001", "Detection probability threshold confirmed with mission planning team. 0.95 aligns with Phase 2 engagement analysis."),
        ("FR-006", "FAILED verification — correlation drops to 0.96 with 20 targets. Investigation ongoing, may need JPDAF parameter tuning."),
        ("SAF-001", "MIL-STD-882E review complete. All 14 identified hazards have mitigating requirements."),
        ("FR-003", "45-second timeline is aggressive. Consider adding a 10-second margin for thermal stabilization of the launch tube."),
        ("SR-001", "NSA Type 1 certification audit scheduled for Q3. Key management pre-assessment passed."),
    ]
    for req_key, content in seed_comments:
        if req_key in req_map:
            comment = Comment(
                requirement_id=req_map[req_key].id,
                author_id=owner.id,
                content=content,
            )
            db.add(comment)

    # ══════════════════════════════════════
    #  Commit everything
    # ══════════════════════════════════════
    db.commit()

    # Build summary
    level_counts = {}
    for seed in SEED_REQUIREMENTS:
        lv = seed["level"]
        level_counts[lv] = level_counts.get(lv, 0) + 1

    return {
        "status": "seeded",
        "project_id": project_id,
        "project_code": project.code,
        "requirements_created": len(SEED_REQUIREMENTS),
        "by_level": level_counts,
        "trace_links_created": trace_links_created,
        "verifications_created": verif_count,
        "source_artifacts_created": len(SEED_ARTIFACTS),
        "baselines_created": 2,
        "comments_created": len(seed_comments),
    }
