"""
ASTRA — Normalized motor artifact builder (spec §5.4)
=====================================================
File: backend/app/services/engineering/motor_artifact.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §5.4 — ``*.motor.json``)

Produces the sim-agnostic artifact dict CITADEL bakes its pack from.
Everything is on a uniform 1 kHz grid (``Ts_s = 0.001``); content is
addressed by sha256 over canonical JSON (sorted keys, compact
separators) so identical artifacts dedup across bundles.

This module also hosts the small numpy-free numeric kit (trapezoid
integration, linear interpolation, 1 kHz resampling, motor-class
letter) shared by the CSV ingest (§5.2) and the ballistics solver
(§5.3) — ASTRA's backend deliberately carries no numpy dependency
(see the closed-form eigenvalue helper in app/routers/catalog.py).
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

#: Schema identity stamped into every artifact.
ARTIFACT_SCHEMA_ID = "astra-motor-artifact/1.0"

#: 1 kHz sample period (s) — the §5.4 grid.
TS_S = 0.001

#: 3-temperature grain-soak grid (K): cold / nominal / hot.
GRAIN_TEMP_GRID_K: List[float] = [284.15, 294.15, 304.15]

#: Standard gravity (m/s²) for Isp.
G0 = 9.80665

#: Burnout tail trim: thrust below this fraction of peak ends the burn.
BURNOUT_THRUST_FRACTION = 0.005


# ══════════════════════════════════════════════════════════════
#  Numeric kit (numpy-free)
# ══════════════════════════════════════════════════════════════

def trapz(y: Sequence[float], x: Sequence[float]) -> float:
    """Trapezoidal integral of y over x."""
    if len(y) != len(x):
        raise ValueError("trapz: x and y must be the same length")
    total = 0.0
    for i in range(1, len(x)):
        total += 0.5 * (y[i] + y[i - 1]) * (x[i] - x[i - 1])
    return total


def interp_linear(x: float, xp: Sequence[float], fp: Sequence[float]) -> float:
    """Linear interpolation of (xp, fp) at x. xp must be ascending.
    Clamps outside the domain (no extrapolation)."""
    if x <= xp[0]:
        return fp[0]
    if x >= xp[-1]:
        return fp[-1]
    # Binary search for the bracketing interval.
    lo, hi = 0, len(xp) - 1
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if xp[mid] <= x:
            lo = mid
        else:
            hi = mid
    x0, x1 = xp[lo], xp[hi]
    if x1 == x0:
        return fp[lo]
    frac = (x - x0) / (x1 - x0)
    return fp[lo] + frac * (fp[hi] - fp[lo])


def uniform_grid(t_end: float, ts: float = TS_S) -> List[float]:
    """Uniform time grid [0, t_end] at period ts (t_end included as
    the final sample even if not an exact multiple)."""
    if t_end <= 0:
        return [0.0]
    n = int(t_end / ts)
    grid = [i * ts for i in range(n + 1)]
    if grid[-1] < t_end - 1e-12:
        grid.append(t_end)
    return grid


def resample_uniform(
    t: Sequence[float],
    y: Sequence[float],
    grid: Sequence[float],
) -> List[float]:
    """Linear-interpolate series (t, y) onto ``grid``."""
    return [interp_linear(g, t, y) for g in grid]


def burnout_end_time(t: Sequence[float], thrust: Sequence[float]) -> float:
    """Burn-end for grid construction: time of the last sample where
    thrust ≥ BURNOUT_THRUST_FRACTION × peak (tail trim, §5.2)."""
    if not thrust:
        return 0.0
    peak = max(thrust)
    if peak <= 0:
        return t[-1] - t[0]
    threshold = BURNOUT_THRUST_FRACTION * peak
    last = 0
    for i, f in enumerate(thrust):
        if f >= threshold:
            last = i
    return t[last] - t[0]


# ══════════════════════════════════════════════════════════════
#  Motor class letter
# ══════════════════════════════════════════════════════════════

#: (letter, upper-bound total impulse in N·s]. Standard NAR/TRA
#: doubling ladder; above O the spec says 'P+'.
_CLASS_LADDER: List[tuple] = [
    ("1/8A", 0.3125),
    ("1/4A", 0.625),
    ("1/2A", 1.25),
    ("A", 2.5),
    ("B", 5.0),
    ("C", 10.0),
    ("D", 20.0),
    ("E", 40.0),
    ("F", 80.0),
    ("G", 160.0),
    ("H", 320.0),
    ("I", 640.0),
    ("J", 1280.0),
    ("K", 2560.0),
    ("L", 5120.0),
    ("M", 10240.0),
    ("N", 20480.0),
    ("O", 40960.0),
]


def motor_class_letter(total_impulse_ns: float) -> str:
    """Class letter from total impulse (¹⁄₈A ≤ 0.3125 … O ≤ 40960, then 'P+')."""
    for letter, upper in _CLASS_LADDER:
        if total_impulse_ns <= upper:
            return letter
    return "P+"


# ══════════════════════════════════════════════════════════════
#  Canonical hashing
# ══════════════════════════════════════════════════════════════

def canonical_json(obj: Any) -> str:
    """Canonical JSON: sorted keys, compact separators — the §1
    content-addressing convention."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def artifact_sha256(artifact: Dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(artifact).encode("utf-8")).hexdigest()


# ══════════════════════════════════════════════════════════════
#  Artifact builder
# ══════════════════════════════════════════════════════════════

def build_artifact(
    *,
    origin: str,                              # 'design' | 'csv'
    time_s: List[float],
    thrust_n: List[float],
    mdot_kgps: List[float],                   # NEGATIVE by convention
    prop_mass_rem_kg: List[float],
    prop_mass_init_kg: float,
    pchamber_pa: List[float],
    prop_cg_offset_m_b: List[float],          # time series
    prop_inertia_axial_kgm2: List[float],
    prop_inertia_transverse_kgm2: List[float],
    grain_stack_length_m: float,
    burn_time_s: float,
    area_exit_m2: float,
    area_throat_m2: float,
    thrust_n_by_tgrain: List[List[float]],    # 3 rows, cold/nominal/hot
    mdot_kgps_by_tgrain: List[List[float]],
    total_impulse_ns: float,
    peak_thrust_n: float,
    isp_s: float,
    quality_tier: str,                        # 'workable'|'good'|'excellent'
    defaulted_fields: List[str],
    author: str,
    wpn: str,
    design_inputs: Optional[Dict[str, Any]] = None,
    csv_sha256: Optional[str] = None,
    created_utc: Optional[str] = None,
) -> Dict[str, Any]:
    """Assemble the §5.4 normalized motor artifact dict.

    All series must already share the uniform 1 kHz ``time_s`` grid.
    Provenance carries exactly one of ``designInputs`` / ``csvSha256``
    depending on ``origin``.
    """
    if origin not in ("design", "csv"):
        raise ValueError(f"origin must be 'design' or 'csv', got {origin!r}")
    n = len(time_s)
    for name, series in (
        ("Thrust_N", thrust_n),
        ("Mdot_kgps", mdot_kgps),
        ("PropMassRem_kg", prop_mass_rem_kg),
        ("Pchamber_Pa", pchamber_pa),
        ("PropCGOffset_m_B", prop_cg_offset_m_b),
        ("PropInertiaAxial_kgm2", prop_inertia_axial_kgm2),
        ("PropInertiaTransverse_kgm2", prop_inertia_transverse_kgm2),
    ):
        if len(series) != n:
            raise ValueError(
                f"artifact series {name} has {len(series)} samples, "
                f"MotorTime_s has {n} — all series must share the grid"
            )
    if len(thrust_n_by_tgrain) != 3 or len(mdot_kgps_by_tgrain) != 3:
        raise ValueError("byTgrain tables must have exactly 3 rows (cold/nominal/hot)")

    provenance: Dict[str, Any] = {
        "origin": origin,
        "author": author,
        "createdUtc": created_utc
        or datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "wpn": wpn,
    }
    if origin == "design":
        provenance["designInputs"] = design_inputs or {}
    else:
        provenance["csvSha256"] = csv_sha256 or ""

    return {
        "schema": ARTIFACT_SCHEMA_ID,
        "MotorTime_s": time_s,
        "Thrust_N": thrust_n,
        "Mdot_kgps": mdot_kgps,
        "PropMassRem_kg": prop_mass_rem_kg,
        "PropMassInit_kg": prop_mass_init_kg,
        "Pchamber_Pa": pchamber_pa,
        "PropCGOffset_m_B": prop_cg_offset_m_b,
        "PropInertiaAxial_kgm2": prop_inertia_axial_kgm2,
        "PropInertiaTransverse_kgm2": prop_inertia_transverse_kgm2,
        "GrainStackLength_m": grain_stack_length_m,
        "BurnTime_s": burn_time_s,
        "Ts_s": TS_S,
        "AreaExit_m2": area_exit_m2,
        "AreaThroat_m2": area_throat_m2,
        "GrainTempGrid_K": list(GRAIN_TEMP_GRID_K),
        "Thrust_N_byTgrain": thrust_n_by_tgrain,
        "Mdot_kgps_byTgrain": mdot_kgps_by_tgrain,
        "TotalImpulse_Ns": total_impulse_ns,
        "PeakThrust_N": peak_thrust_n,
        "Isp_s": isp_s,
        "qualityTier": quality_tier,
        "defaultedFields": defaulted_fields,
        "provenance": provenance,
    }
