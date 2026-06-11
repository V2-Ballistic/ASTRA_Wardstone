"""
ASTRA — Motor CSV ingest (spec §5.2, CITADEL ``ingestMotorCSV`` port)
=====================================================================
File: backend/app/services/engineering/motor_ingest.py   ← NEW

Behavioral port of the proven CITADEL ``ingestMotorCSV`` derivation.
**The original CITADEL source is unavailable on this machine** (see
docs/ASTRA_CONFIG_ECOSYSTEM_AS_FOUND.md); this module is implemented
faithfully from the spec §5.2 behavioral contract. Where the contract
left room, the choices below are documented as ASSUMPTIONS:

ASSUMPTIONS (documented per §12 spirit)
---------------------------------------
1. **Header detection:** the header row is the first CSV row whose
   cells contain a recognized *time* alias plus at least one other
   recognized column alias. Rows above it of the form
   ``key, value`` (and ``#``-comment lines anywhere) are treated as
   key/value metadata (grain masses, total propellant mass).
2. **Time base:** shifted so the first sample is t = 0; non-increasing
   time samples are dropped with a warning.
3. **ṁ preference:** the derived d(PropMassRem)/dt is ALWAYS the ṁ
   used in the artifact; a nozzle-flow column is a cross-check only
   (>5 % integral discrepancy ⇒ warning, derived preferred).
4. **qualityTier precedence** (spec lists overlapping rules):
   ``workable`` wins when the constant-Isp fallback was used, when
   chamber pressure is missing, or when any cross-check fails
   (mass-burn > 2 %, nozzle-flow > 5 %, impulse raw-vs-resampled
   > 2 %). ``excellent`` requires thrust + mass time-series +
   pressure all present, all cross-checks passing, AND the total
   propellant mass independently confirmed (grain-mass row-sum or an
   explicit metadata value). Otherwise ``good`` — e.g. PropMassInit
   inferred from the first mass sample (a "minor default").
   Geometry fields a bare CSV can never provide (CG, inertias,
   nozzle areas, grain-stack length, σp temperature grid) are ALWAYS
   defaulted for csv-origin revisions and do NOT affect the tier.
5. **Temperature grid:** CSV origin carries no σp, so the nominal
   curves are replicated across ``GrainTempGrid_K`` and listed in
   ``defaultedFields``.
6. **Multi-segment is first-class:** N per-grain mass entries are
   summed — total propellant mass = grain-mass row-sum (the 8-grain
   WS01 form). Nothing assumes a single segment.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from app.services.engineering.motor_artifact import (
    G0,
    GRAIN_TEMP_GRID_K,
    burnout_end_time,
    resample_uniform,
    trapz,
    uniform_grid,
)

LBF_TO_N = 4.4482216152605
PSI_TO_PA = 6894.757293168

#: Cross-check tolerances.
MASS_BURN_TOLERANCE = 0.02      # ∫|ṁ|dt vs propellant mass
NOZZLE_FLOW_TOLERANCE = 0.05    # derived vs nozzle-station ṁ integrals
IMPULSE_TOLERANCE = 0.02        # raw vs resampled ∫F dt


class MotorCsvError(ValueError):
    """Unusable CSV (no thrust, no mass info, …) — router maps to 422."""


# ══════════════════════════════════════════════════════════════
#  Alias tables (case/space/punctuation-insensitive)
# ══════════════════════════════════════════════════════════════

def _norm(cell: str) -> str:
    """Normalize a header/metadata key: lowercase, strip everything
    that is not a letter or digit ("Thrust (N)" → "thrustn")."""
    return re.sub(r"[^a-z0-9]", "", cell.lower())


_TIME_ALIASES = {"time", "times", "t", "motortimes", "timesec", "timeseconds"}
_THRUST_N_ALIASES = {"thrust", "thrustn", "forcen", "fn", "force"}
_THRUST_LBF_ALIASES = {"thrustlbf", "forcelbf", "flbf", "thrustlb", "forcelb"}
_MASS_KG_ALIASES = {
    "masskg", "propmasskg", "propmassremkg", "propellantmass",
    "propmassrem", "propellantmasskg", "propmassremaining",
}
_PC_PA_ALIASES = {
    "pc", "pchamberpa", "chamberpressurepa", "pcpa", "chamberpressure",
    "pchamber",
}
_PC_PSI_ALIASES = {"pcpsi", "chamberpressurepsi", "pchamberpsi"}
_MDOT_ALIASES = {"mdot", "mdotkgps", "nozzlemdotkgps", "nozzlemdot"}
#: Metadata keys carrying TOTAL propellant mass.
_PROP_MASS_META_ALIASES = {
    "propellantmass", "propmasskg", "totalpropmass", "propmass",
    "propellantmasskg", "totalpropellantmasskg", "totalpropmasskg",
}
#: grain1_mass_kg / grain_mass_1 / GrainMass_3 … (normalized forms).
_GRAIN_MASS_RE = re.compile(r"^grain(?:mass)?(\d+)(?:mass)?(?:kg)?$")


_COLUMN_KINDS: List[Tuple[str, set, float]] = [
    # (kind, alias set, conversion factor to SI)
    ("time", _TIME_ALIASES, 1.0),
    ("thrust", _THRUST_N_ALIASES, 1.0),
    ("thrust", _THRUST_LBF_ALIASES, LBF_TO_N),
    ("mass", _MASS_KG_ALIASES, 1.0),
    ("pc", _PC_PA_ALIASES, 1.0),
    ("pc", _PC_PSI_ALIASES, PSI_TO_PA),
    ("mdot", _MDOT_ALIASES, 1.0),
]


def _classify_header_cell(cell: str) -> Optional[Tuple[str, float, Optional[int]]]:
    """(kind, factor, grain_index) for a header cell, or None."""
    key = _norm(cell)
    if not key:
        return None
    for kind, aliases, factor in _COLUMN_KINDS:
        if key in aliases:
            return kind, factor, None
    m = _GRAIN_MASS_RE.match(key)
    if m:
        return "grain_mass", 1.0, int(m.group(1))
    return None


def _try_float(cell: str) -> Optional[float]:
    try:
        return float(cell.strip())
    except (TypeError, ValueError):
        return None


# ══════════════════════════════════════════════════════════════
#  Result container
# ══════════════════════════════════════════════════════════════

@dataclass
class MotorIngestResult:
    """Everything the artifact builder + persistence layer needs.
    All series are on the uniform 1 kHz grid (``time_s``); ``mdot_kgps``
    follows the artifact's NEGATIVE convention."""

    time_s: List[float] = field(default_factory=list)
    thrust_n: List[float] = field(default_factory=list)
    mdot_kgps: List[float] = field(default_factory=list)
    prop_mass_rem_kg: List[float] = field(default_factory=list)
    pchamber_pa: List[float] = field(default_factory=list)

    prop_mass_init_kg: float = 0.0
    grain_masses_kg: List[float] = field(default_factory=list)

    total_impulse_ns: float = 0.0
    peak_thrust_n: float = 0.0
    burn_time_s: float = 0.0
    isp_s: float = 0.0

    quality_tier: str = "workable"
    recommended_fidelity: str = "Nominal"
    defaulted_fields: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    # Replicated across GrainTempGrid_K (no σp from a CSV).
    thrust_n_by_tgrain: List[List[float]] = field(default_factory=list)
    mdot_kgps_by_tgrain: List[List[float]] = field(default_factory=list)

    # Geometry the CSV cannot provide — zeros, listed in defaultedFields.
    prop_cg_offset_m_b: List[float] = field(default_factory=list)
    prop_inertia_axial_kgm2: List[float] = field(default_factory=list)
    prop_inertia_transverse_kgm2: List[float] = field(default_factory=list)
    area_throat_m2: float = 0.0
    area_exit_m2: float = 0.0
    grain_stack_length_m: float = 0.0


# ══════════════════════════════════════════════════════════════
#  Parsing
# ══════════════════════════════════════════════════════════════

def _parse_metadata_pair(cells: List[str]) -> Optional[Tuple[str, Optional[int], float]]:
    """If ``cells`` is a key/value metadata pair carrying a grain mass
    or total propellant mass, return (kind, grain_index, value)."""
    if len(cells) < 2:
        return None
    key = _norm(cells[0])
    value = _try_float(cells[1])
    if not key or value is None:
        return None
    m = _GRAIN_MASS_RE.match(key)
    if m:
        return "grain_mass", int(m.group(1)), value
    if key in _PROP_MASS_META_ALIASES:
        return "prop_mass", None, value
    return None


def _split_cells(line: str) -> List[str]:
    """Split one metadata-ish line on comma or colon."""
    if "," in line:
        return [c.strip() for c in line.split(",")]
    if ":" in line:
        return [c.strip() for c in line.split(":", 1)]
    return [line.strip()]


def parse_motor_csv(csv_text: str):
    """Tokenize the CSV: returns (columns, data, grain_masses,
    prop_mass_meta, warnings) where ``columns`` maps column index →
    (kind, factor, grain_index) and ``data`` is the list of raw rows.
    """
    warnings: List[str] = []
    grain_masses: Dict[int, float] = {}
    prop_mass_meta: Optional[float] = None

    raw_lines = csv_text.splitlines()
    body_lines: List[str] = []
    for line in raw_lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            # Comment line — may carry metadata ("# GrainMass_3, 0.812").
            meta = _parse_metadata_pair(_split_cells(stripped.lstrip("#").strip()))
            if meta is not None:
                kind, gidx, value = meta
                if kind == "grain_mass":
                    grain_masses[gidx] = value
                else:
                    prop_mass_meta = value
            continue
        body_lines.append(line)

    rows = list(csv.reader(io.StringIO("\n".join(body_lines))))

    # Locate the header row: needs a time alias + ≥1 other alias.
    header_idx: Optional[int] = None
    columns: Dict[int, Tuple[str, float, Optional[int]]] = {}
    for i, row in enumerate(rows):
        classified = {
            j: c for j, cell in enumerate(row)
            if (c := _classify_header_cell(cell)) is not None
        }
        kinds = {c[0] for c in classified.values()}
        if "time" in kinds and len(classified) >= 2:
            header_idx = i
            columns = classified
            break
        # Pre-header key/value metadata rows.
        meta = _parse_metadata_pair([c for c in row if c.strip() != ""])
        if meta is not None:
            kind, gidx, value = meta
            if kind == "grain_mass":
                grain_masses[gidx] = value
            else:
                prop_mass_meta = value

    if header_idx is None:
        raise MotorCsvError(
            "no recognizable header row (need at least a time column "
            "and one of thrust / mass / pressure / mdot)"
        )

    data = rows[header_idx + 1:]

    # Grain-mass COLUMNS (constant columns): take the first numeric
    # value of each as that grain's mass and drop from the series map.
    for j, (kind, factor, gidx) in list(columns.items()):
        if kind == "grain_mass":
            for row in data:
                if j < len(row) and (v := _try_float(row[j])) is not None:
                    grain_masses[gidx] = v * factor
                    break
            del columns[j]

    return columns, data, grain_masses, prop_mass_meta, warnings


def _extract_series(
    columns: Dict[int, Tuple[str, float, Optional[int]]],
    data: List[List[str]],
    warnings: List[str],
) -> Dict[str, List[float]]:
    """Pull the numeric time series out of the data rows."""
    by_kind: Dict[str, Tuple[int, float]] = {}
    for j, (kind, factor, _g) in columns.items():
        if kind not in by_kind:           # first matching column wins
            by_kind[kind] = (j, factor)

    series: Dict[str, List[float]] = {k: [] for k in by_kind}
    t_col = by_kind["time"][0]
    dropped = 0
    last_t: Optional[float] = None
    for row in data:
        if t_col >= len(row):
            continue
        t_val = _try_float(row[t_col])
        if t_val is None:
            continue
        if last_t is not None and t_val <= last_t:
            dropped += 1
            continue
        # All-or-nothing row: every mapped column must parse.
        parsed: Dict[str, float] = {}
        ok = True
        for kind, (j, factor) in by_kind.items():
            v = _try_float(row[j]) if j < len(row) else None
            if v is None:
                ok = False
                break
            parsed[kind] = v * factor
        if not ok:
            continue
        last_t = t_val
        for kind, v in parsed.items():
            series[kind].append(v)
    if dropped:
        warnings.append(
            f"dropped {dropped} non-increasing time sample(s) from the CSV"
        )
    return series


def _central_differences(t: List[float], y: List[float]) -> List[float]:
    """dy/dt by central differences (one-sided at the endpoints)."""
    n = len(t)
    out = [0.0] * n
    if n < 2:
        return out
    out[0] = (y[1] - y[0]) / (t[1] - t[0])
    for i in range(1, n - 1):
        out[i] = (y[i + 1] - y[i - 1]) / (t[i + 1] - t[i - 1])
    out[n - 1] = (y[n - 1] - y[n - 2]) / (t[n - 1] - t[n - 2])
    return out


# ══════════════════════════════════════════════════════════════
#  The ingest
# ══════════════════════════════════════════════════════════════

def ingest_motor_csv(csv_text: str) -> MotorIngestResult:
    """Run the full §5.2 derivation on raw CSV text. Raises
    ``MotorCsvError`` for unusable input."""
    result = MotorIngestResult()
    warnings = result.warnings
    defaulted = result.defaulted_fields

    columns, data, grain_masses, prop_mass_meta, parse_warnings = (
        parse_motor_csv(csv_text)
    )
    warnings.extend(parse_warnings)
    series = _extract_series(columns, data, warnings)

    t_raw = series.get("time", [])
    thrust_raw = series.get("thrust", [])
    if len(t_raw) < 2 or not thrust_raw:
        raise MotorCsvError("CSV has no usable time/thrust data rows")

    # Shift the time base so t = 0 is the first sample.
    t0 = t_raw[0]
    t_raw = [t - t0 for t in t_raw]

    mass_raw = series.get("mass")
    pc_raw = series.get("pc")
    mdot_nozzle_raw = series.get("mdot")
    has_mass_series = mass_raw is not None
    has_pressure = pc_raw is not None

    # ── Total propellant mass ────────────────────────────────────
    # Grain-mass row-sum is authoritative (multi-segment first-class).
    result.grain_masses_kg = [
        grain_masses[k] for k in sorted(grain_masses)
    ]
    prop_mass_confirmed = False
    crosscheck_fail = False
    if result.grain_masses_kg:
        prop_mass_init = sum(result.grain_masses_kg)
        prop_mass_confirmed = True
        if has_mass_series:
            rel = abs(mass_raw[0] - prop_mass_init) / prop_mass_init
            if rel > MASS_BURN_TOLERANCE:
                crosscheck_fail = True
                warnings.append(
                    f"grain-mass row-sum {prop_mass_init:.6g} kg disagrees "
                    f"with first mass sample {mass_raw[0]:.6g} kg "
                    f"({rel * 100:.1f}% > {MASS_BURN_TOLERANCE * 100:.0f}%)"
                )
    elif prop_mass_meta is not None:
        prop_mass_init = prop_mass_meta
        prop_mass_confirmed = True
    elif has_mass_series:
        prop_mass_init = mass_raw[0]
        defaulted.append("PropMassInit_kg")
        warnings.append(
            "PropMassInit_kg taken from the first mass sample "
            "(no grain masses or explicit propellant-mass metadata)"
        )
    else:
        raise MotorCsvError(
            "CSV provides no propellant mass information (no mass "
            "time-series, grain masses, or propellant-mass metadata) — "
            "cannot derive ṁ"
        )
    result.prop_mass_init_kg = prop_mass_init

    # ── ṁ derivation ─────────────────────────────────────────────
    used_fallback = False
    if has_mass_series:
        # Primary: d(PropMassRem)/dt via central differences.
        mdot_raw = _central_differences(t_raw, mass_raw)
        positives = sum(1 for v in mdot_raw if v > 0.0)
        if positives:
            warnings.append(
                f"ṁ forced negative: {positives} positive d(mass)/dt "
                "sample(s) clamped to 0"
            )
        mdot_raw = [min(v, 0.0) for v in mdot_raw]

        if mdot_nozzle_raw is not None:
            derived_int = trapz([abs(v) for v in mdot_raw], t_raw)
            nozzle_int = trapz([abs(v) for v in mdot_nozzle_raw], t_raw)
            if derived_int > 0:
                rel = abs(nozzle_int - derived_int) / derived_int
                if rel > NOZZLE_FLOW_TOLERANCE:
                    crosscheck_fail = True
                    warnings.append(
                        f"nozzle mass-flow column disagrees with derived "
                        f"d(mass)/dt by {rel * 100:.1f}% "
                        f"(> {NOZZLE_FLOW_TOLERANCE * 100:.0f}%) — "
                        "derived ṁ preferred"
                    )
        mass_series_raw = mass_raw
    else:
        # Tiered fallback (a): thrust + total propellant mass ⇒
        # constant Isp: Isp = ∫F dt/(m·g0), ṁ = −F/(Isp·g0).
        used_fallback = True
        impulse_raw_full = trapz(thrust_raw, t_raw)
        if impulse_raw_full <= 0:
            raise MotorCsvError("thrust integrates to zero — unusable curve")
        isp_const = impulse_raw_full / (prop_mass_init * G0)
        mdot_raw = [-f / (isp_const * G0) for f in thrust_raw]
        # Synthesize PropMassRem by cumulative integration.
        mass_series_raw = [prop_mass_init]
        for i in range(1, len(t_raw)):
            burned = 0.5 * (abs(mdot_raw[i]) + abs(mdot_raw[i - 1])) * (
                t_raw[i] - t_raw[i - 1]
            )
            mass_series_raw.append(max(mass_series_raw[-1] - burned, 0.0))
        defaulted.extend(["Mdot_kgps", "PropMassRem_kg"])
        warnings.append(
            "no propellant-mass time-series: constant-Isp fallback used "
            f"(Isp = {isp_const:.2f} s); Mdot_kgps and PropMassRem_kg are "
            "derived, not measured"
        )

    # ── Chamber pressure ─────────────────────────────────────────
    if not has_pressure:
        pc_raw = [0.0] * len(t_raw)
        defaulted.append("Pchamber_Pa")
        warnings.append("no chamber-pressure column: Pchamber_Pa defaulted to zeros")

    # ── 1 kHz resample (burnout tail trim) ───────────────────────
    t_end = burnout_end_time(t_raw, thrust_raw)
    if t_end <= 0:
        raise MotorCsvError("burnout trim left no usable burn")
    grid = uniform_grid(t_end)
    result.time_s = grid
    result.thrust_n = resample_uniform(t_raw, thrust_raw, grid)
    result.mdot_kgps = resample_uniform(t_raw, mdot_raw, grid)
    result.prop_mass_rem_kg = resample_uniform(t_raw, mass_series_raw, grid)
    result.pchamber_pa = resample_uniform(t_raw, pc_raw, grid)

    # ── Scalars + cross-checks ───────────────────────────────────
    impulse_raw = trapz(thrust_raw, t_raw)
    impulse_resampled = trapz(result.thrust_n, grid)
    result.total_impulse_ns = impulse_resampled
    result.peak_thrust_n = max(result.thrust_n)
    result.burn_time_s = t_end
    result.isp_s = impulse_resampled / (prop_mass_init * G0)

    if impulse_raw > 0:
        rel = abs(impulse_resampled - impulse_raw) / impulse_raw
        if rel > IMPULSE_TOLERANCE:
            crosscheck_fail = True
            warnings.append(
                f"impulse cross-check failed: raw ∫F dt = {impulse_raw:.4g} "
                f"N·s vs 1 kHz resampled {impulse_resampled:.4g} N·s "
                f"({rel * 100:.1f}% > {IMPULSE_TOLERANCE * 100:.0f}%)"
            )

    mass_burned = trapz([abs(v) for v in result.mdot_kgps], grid)
    if prop_mass_init > 0 and not used_fallback:
        rel = abs(mass_burned - prop_mass_init) / prop_mass_init
        if rel > MASS_BURN_TOLERANCE:
            crosscheck_fail = True
            warnings.append(
                f"mass-burn cross-check failed: ∫|ṁ|dt = {mass_burned:.6g} "
                f"kg vs propellant mass {prop_mass_init:.6g} kg "
                f"({rel * 100:.1f}% > {MASS_BURN_TOLERANCE * 100:.0f}%)"
            )

    # ── Geometry the CSV can't provide (zeros + defaulted) ───────
    n = len(grid)
    result.prop_cg_offset_m_b = [0.0] * n
    result.prop_inertia_axial_kgm2 = [0.0] * n
    result.prop_inertia_transverse_kgm2 = [0.0] * n
    result.area_throat_m2 = 0.0
    result.area_exit_m2 = 0.0
    result.grain_stack_length_m = 0.0
    defaulted.extend([
        "PropCGOffset_m_B",
        "PropInertiaAxial_kgm2",
        "PropInertiaTransverse_kgm2",
        "AreaThroat_m2",
        "AreaExit_m2",
        "GrainStackLength_m",
    ])
    warnings.append(
        "CSV origin carries no geometry: CG offset, inertias, nozzle "
        "areas and grain-stack length defaulted to zero"
    )

    # ── 3-temperature grid (replicated — no σp from a CSV) ───────
    result.thrust_n_by_tgrain = [list(result.thrust_n) for _ in GRAIN_TEMP_GRID_K]
    result.mdot_kgps_by_tgrain = [list(result.mdot_kgps) for _ in GRAIN_TEMP_GRID_K]
    defaulted.extend(["Thrust_N_byTgrain", "Mdot_kgps_byTgrain"])
    warnings.append(
        "no σp available from CSV: nominal curves replicated across "
        "GrainTempGrid_K"
    )

    # ── qualityTier (assumption 4 in the module docstring) ───────
    if used_fallback or crosscheck_fail or not has_pressure:
        result.quality_tier = "workable"
    elif has_mass_series and has_pressure and prop_mass_confirmed:
        result.quality_tier = "excellent"
    else:
        result.quality_tier = "good"
    result.recommended_fidelity = (
        "HiFi" if result.quality_tier == "excellent" else "Nominal"
    )

    return result
