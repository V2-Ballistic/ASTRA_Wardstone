"""ASTRA — Wire Heuristics (INTF-002 Phase 4)
============================================
File: backend/app/services/interface/wire_heuristics.py

Engineering-judgement defaults for proposed wires emitted by the three-way
auto-wire engine (``services/interface/auto_wire.py``). Inputs are best-effort
metadata read off the source/target pins; outputs are conservative defaults
the user can refine in the harness commit step.

Per spec §11 Inputs (signal_type, voltage / current limits, mating distance):

  * ``suggested_gauge``       — AWG enum value (string), MIL-W-22759 family
  * ``suggested_color``       — primary insulation color (str)
  * ``suggested_insulation``  — generic insulation family
  * ``max_length_m``          — voltage-drop-budgeted length cap (None when
                                no current data is available)

The defaults below are conservative for spaceflight / mil-spec harnesses:
  - 22 AWG for low-current digital signals (<500 mA)
  - 18 AWG for 1-5 A power
  - 14 AWG for >5 A power
  - Color codes follow common aerospace harness conventions:
      red    → power
      black  → ground
      white  → digital signal
      blue   → analog signal
      yellow → discrete (HK/event)
      orange → RF/coax (jacket)
      gray   → no-connect / spare

These are heuristics, not requirements — never block the auto-wire flow on
heuristic uncertainty; just emit defaults plus an optional rationale.

Stateless: all functions are pure and depend only on their arguments. No DB
calls. Safe to import from inside the auto-wire loop without N+1 risk.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


# ══════════════════════════════════════════════════════════════
#  Result type
# ══════════════════════════════════════════════════════════════

@dataclass(frozen=True)
class WireSuggestion:
    """Frozen suggestion bundle for a single proposed wire.

    All fields are best-effort defaults. None means "no defensible default —
    leave the harness designer to supply a value."
    """
    gauge: str            # AWG enum value, e.g. "awg_22"
    color: str            # insulation primary color, e.g. "white"
    insulation: str       # generic family, e.g. "PTFE"
    max_length_m: Optional[float] = None
    rationale: str = ""   # short human-readable note for tooltip / log


# ══════════════════════════════════════════════════════════════
#  Internal lookups
# ══════════════════════════════════════════════════════════════

# Gauge ladder ordered ascending current capacity. Each tuple = (max_amps,
# AWG enum value). The first tuple whose max_amps >= the request wins.
_GAUGE_LADDER: tuple[tuple[float, str], ...] = (
    (0.5,   "awg_26"),
    (1.0,   "awg_24"),
    (3.0,   "awg_22"),
    (5.0,   "awg_20"),
    (8.0,   "awg_18"),
    (13.0,  "awg_16"),
    (18.0,  "awg_14"),
    (25.0,  "awg_12"),
    (35.0,  "awg_10"),
)
_GAUGE_FALLBACK = "awg_8"

# DC resistance per metre per gauge (from MIL-W-22759 nominal copper, 20 °C).
# Used by the voltage-drop length budget. Values in ohms / metre.
_RESISTANCE_PER_M: dict[str, float] = {
    "awg_26": 0.1339,
    "awg_24": 0.0842,
    "awg_22": 0.0530,
    "awg_20": 0.0333,
    "awg_18": 0.0210,
    "awg_16": 0.0132,
    "awg_14": 0.0083,
    "awg_12": 0.0052,
    "awg_10": 0.0033,
    "awg_8":  0.0021,
}

# Color by signal_type (case-insensitive prefix match).
_COLOR_BY_SIGNAL_TYPE: tuple[tuple[str, str], ...] = (
    ("power",      "red"),
    ("ground",     "black"),
    ("digital",    "white"),
    ("analog",     "blue"),
    ("rf",         "orange"),
    ("coax",       "orange"),
    ("discrete",   "yellow"),
    ("diff_pair",  "white"),
    ("no_connect", "gray"),
    ("reserved",   "gray"),
    ("unknown",    "white"),
)


# ══════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════

def suggest_gauge(current_amps: Optional[float]) -> str:
    """Pick the smallest-gauge AWG that handles the requested current.

    None / 0 / negative → 22 AWG (default signal wire).
    """
    if current_amps is None or current_amps <= 0:
        return "awg_22"
    for ceiling, awg in _GAUGE_LADDER:
        if current_amps <= ceiling:
            return awg
    return _GAUGE_FALLBACK


def suggest_color(signal_type: Optional[str]) -> str:
    """Pick the conventional insulation color for a signal_type."""
    if not signal_type:
        return "white"
    st = signal_type.lower()
    for prefix, color in _COLOR_BY_SIGNAL_TYPE:
        if st.startswith(prefix):
            return color
    return "white"


def suggest_insulation(
    signal_type: Optional[str],
    voltage_v: Optional[float] = None,
    temp_max_c: Optional[float] = None,
) -> str:
    """Pick a generic insulation family.

    Defaults to PTFE (rated to 200 °C, used pervasively in mil-aero harnesses).
    Bumps up to ETFE for low-temp / weight-sensitive runs at modest voltage.
    """
    # >600 V — XLPE is conservative and stocked in all gauges.
    if voltage_v is not None and voltage_v > 600:
        return "XLPE"
    # >150 °C operating — PTFE is the typical pick.
    if temp_max_c is not None and temp_max_c > 150:
        return "PTFE"
    # Sub-coax / RF runs default to FEP for the dielectric stability.
    if signal_type and signal_type.lower().startswith(("rf", "coax")):
        return "FEP"
    # Default: ETFE (thinner, lighter, common on flight harnesses).
    return "ETFE"


def estimate_max_length_m(
    current_amps: Optional[float],
    voltage_v: Optional[float],
    gauge: str,
    max_drop_pct: float = 5.0,
) -> Optional[float]:
    """Voltage-drop budgeted maximum one-way length in metres.

    Returns None when current or voltage is unknown — there's no defensible
    default. Uses the round-trip resistance (×2 for the return path).
    """
    if current_amps is None or current_amps <= 0:
        return None
    if voltage_v is None or voltage_v <= 0:
        return None
    r_per_m = _RESISTANCE_PER_M.get(gauge)
    if r_per_m is None:
        return None
    # V_drop = I * R_total = I * (2 * L * r_per_m)  →  L = V_drop / (2 * I * r_per_m)
    v_drop_allowed = voltage_v * (max_drop_pct / 100.0)
    length = v_drop_allowed / (2.0 * current_amps * r_per_m)
    # Clamp to one decimal m to avoid spurious precision in the UI.
    return round(length, 1)


def suggest_wire(
    *,
    signal_type: Optional[str],
    current_amps: Optional[float] = None,
    voltage_v: Optional[float] = None,
    temp_max_c: Optional[float] = None,
    mating_distance_m: Optional[float] = None,
) -> WireSuggestion:
    """Compose all four heuristics into a single suggestion.

    ``mating_distance_m`` is currently used only as a sanity check against
    the voltage-drop budget — if the cable would exceed the budget at the
    declared distance, the rationale string flags the gauge bump-up
    recommendation. The returned ``gauge`` itself is still picked from the
    current alone (gauge selection by drop-budget is a future refinement).
    """
    gauge = suggest_gauge(current_amps)
    color = suggest_color(signal_type)
    insulation = suggest_insulation(signal_type, voltage_v, temp_max_c)
    max_len = estimate_max_length_m(current_amps, voltage_v, gauge)

    notes: list[str] = []
    if current_amps is not None and current_amps > 0:
        notes.append(f"{current_amps:.2f} A → {gauge}")
    else:
        notes.append("default signal gauge (22 AWG)")
    if mating_distance_m is not None and max_len is not None:
        if mating_distance_m > max_len:
            notes.append(
                f"declared distance {mating_distance_m:.1f} m exceeds "
                f"budget {max_len:.1f} m — consider larger gauge"
            )

    return WireSuggestion(
        gauge=gauge,
        color=color,
        insulation=insulation,
        max_length_m=max_len,
        rationale=" / ".join(notes),
    )
