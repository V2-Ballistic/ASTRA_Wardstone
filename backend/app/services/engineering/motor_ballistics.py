"""
ASTRA — Parametric SRM internal-ballistics solver (spec §5.3)
=============================================================
File: backend/app/services/engineering/motor_ballistics.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §5.3 — openMotor reference pattern)

Classic equilibrium internal ballistics for BATES grain stacks,
SI units throughout. Marches web regression ``w`` in fixed steps:

    rc(w)  = core/2 + w                       (port radius, per segment)
    L(w)   = L0 − faces·w                     (faces = 2 − inhibited_ends)
    Ab     = Σ_seg [ 2π·rc·L(w) + faces·π((OD/2)² − rc²) ]
    Kn     = Ab / At
    Pc     = (Kn·ρp·a(T)·c*)^(1/(1−n))        (equilibrium chamber pressure)
    r      = a(T)·Pc^n                        (Saint-Robert)
    ṁ      = ρp·Ab·r
    Pe     from ε via the isentropic area-ratio relation (supersonic branch)
    Cf     = Γ·sqrt(2k/(k−1)·(1−(Pe/Pc)^((k−1)/k))) + (Pe−Pa)/Pc·(Ae/At)
    F      = max(Cf·At·Pc, 0)
    Isp    = F/(ṁ·g0),  dt = dw/r

with  Γ = sqrt(k)·(2/(k+1))^((k+1)/(2(k−1)))  and
a(T) = a·exp(σp·(T − 294.15)) (temperature-adjusted coefficient).
c* = cstar_mps if given, else sqrt((R_u/M)·Tc)/Γ.

Conventions (DOCUMENTED — load-bearing for the mass-property series)
--------------------------------------------------------------------
* **Axial datum / +x:** the grain-stack AFT face is x = 0; +x points
  forward along the body axis. ``PropCGOffset_m_B`` is the stack CG's
  offset from that aft face along +x.
* **Segment slots:** the N identical segments sit in contiguous fixed
  slots ``[i·L0, (i+1)·L0]`` (casing positions do not move as the
  propellant regresses).
* **End-face regression:**
    - ``inhibited_ends = 0`` (both faces exposed): the segment shrinks
      SYMMETRICALLY about its slot center — grain spans
      ``[i·L0 + w, (i+1)·L0 − w]``; segment CG stays at the slot
      center.
    - ``inhibited_ends = 1``: the AFT face is inhibited, the FORWARD
      face regresses — grain spans ``[i·L0, (i+1)·L0 − w]``; segment
      CG drifts aft as the forward face burns back.
    - ``inhibited_ends = 2``: no end-face regression; L = L0.
* **Inertias:** hollow-cylinder per segment.
  I_axial = Σ ½·m·(R² + rc²);  I_transverse (about the stack CG,
  axis ⟂ to x) = Σ [ (1/12)·m·(3(R²+rc²) + L²) + m·d² ] with
  d = segment CG − stack CG (parallel-axis).
* **Burnout:** half-web burnout at rc ≥ OD/2 (or face burnout at
  L(w) ≤ 0 if that comes first). The march appends one exact terminal
  sample at the burnout web so the propellant-mass series reaches 0.
* **3-temperature grid:** the march runs at [284.15, 294.15, 304.15] K
  by scaling ``a`` with σp. The artifact time grid spans the LONGEST
  burn (cold); each temperature row is zero-padded after its own
  burnout. ``BurnTime_s`` / ``Thrust_N`` / scalars are the NOMINAL
  (294.15 K) row.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List

from app.schemas.engineering_motor import MotorDesignInputs
from app.services.engineering.motor_artifact import (
    G0,
    GRAIN_TEMP_GRID_K,
    motor_class_letter,
    resample_uniform,
    trapz,
    uniform_grid,
)

#: Universal gas constant, J/(mol·K).
R_UNIVERSAL = 8.314462618

#: Nominal grain soak temperature, K (σp reference).
T_NOMINAL_K = 294.15

#: Relative tolerance for the ∫ṁdt ↔ propellant-mass self-check.
MASS_BURN_TOLERANCE = 0.01


class MotorDesignError(ValueError):
    """Raised for design inputs the solver cannot honour (the router
    maps this to HTTP 422)."""


# ══════════════════════════════════════════════════════════════
#  Thermochemistry helpers
# ══════════════════════════════════════════════════════════════

def gamma_function(k: float) -> float:
    """Γ = sqrt(k)·(2/(k+1))^((k+1)/(2(k−1)))."""
    return math.sqrt(k) * (2.0 / (k + 1.0)) ** ((k + 1.0) / (2.0 * (k - 1.0)))


def resolve_cstar(inputs: MotorDesignInputs) -> float:
    """c* from inputs: explicit cstar_mps, else sqrt((R_u/M)·Tc)/Γ."""
    p = inputs.propellant
    if p.cstar_mps is not None:
        return p.cstar_mps
    gamma = gamma_function(p.k)
    r_specific = R_UNIVERSAL / p.molar_mass_kgpmol  # J/(kg·K)
    return math.sqrt(r_specific * p.Tc_K) / gamma


def area_ratio_from_mach(mach: float, k: float) -> float:
    """Isentropic A/A* for exit Mach ``mach``."""
    term = (2.0 / (k + 1.0)) * (1.0 + 0.5 * (k - 1.0) * mach * mach)
    return (1.0 / mach) * term ** ((k + 1.0) / (2.0 * (k - 1.0)))


def exit_mach_from_area_ratio(eps: float, k: float) -> float:
    """Supersonic-branch exit Mach for area ratio ε (bisection)."""
    if eps <= 1.0:
        return 1.0
    lo, hi = 1.0 + 1e-9, 50.0
    # Area ratio is monotonically increasing on the supersonic branch.
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if area_ratio_from_mach(mid, k) < eps:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-10:
            break
    return 0.5 * (lo + hi)


# ══════════════════════════════════════════════════════════════
#  Result containers
# ══════════════════════════════════════════════════════════════

@dataclass
class TempCurve:
    """One temperature row of the march (native, non-uniform grid)."""
    temp_K: float
    time_s: List[float] = field(default_factory=list)
    thrust_n: List[float] = field(default_factory=list)
    pchamber_pa: List[float] = field(default_factory=list)
    mdot_kgps: List[float] = field(default_factory=list)      # positive burn rate
    prop_mass_rem_kg: List[float] = field(default_factory=list)
    cg_offset_m: List[float] = field(default_factory=list)
    inertia_axial_kgm2: List[float] = field(default_factory=list)
    inertia_transverse_kgm2: List[float] = field(default_factory=list)
    burn_time_s: float = 0.0
    peak_thrust_n: float = 0.0
    total_impulse_ns: float = 0.0


@dataclass
class BallisticsResult:
    """Full solver output: nominal curve + the 3-temperature grid."""
    nominal: TempCurve
    by_temp: List[TempCurve]                  # cold / nominal / hot
    prop_mass_init_kg: float
    grain_stack_length_m: float
    area_throat_m2: float
    area_exit_m2: float
    total_impulse_ns: float
    peak_thrust_n: float
    burn_time_s: float
    isp_s: float
    max_pchamber_pa: float
    motor_class: str
    mass_burned_integral_kg: float            # ∫|ṁ| dt (nominal)
    warnings: List[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
#  Geometry / mass properties
# ══════════════════════════════════════════════════════════════

def _segment_geometry(inputs: MotorDesignInputs, w: float):
    """Per-segment (rc, L, span placement fn) at web w. Returns
    (rc, L, seg_center_offset) where seg_center_offset is the segment
    CG's offset INSIDE its slot, relative to the slot's aft edge."""
    g = inputs.grain
    faces = 2 - g.inhibited_ends
    rc = g.core_d_m / 2.0 + w
    length = g.length_m - faces * w
    if faces == 2:
        # Symmetric shrink: CG stays at slot center.
        center_in_slot = g.length_m / 2.0
    elif faces == 1:
        # Aft face inhibited; forward face regresses. Grain spans
        # [0, L0 − w] within the slot → CG at L(w)/2 from slot aft.
        center_in_slot = length / 2.0
    else:
        center_in_slot = g.length_m / 2.0
    return rc, length, center_in_slot


def _mass_properties(inputs: MotorDesignInputs, w: float):
    """(total mass, stack CG offset from aft face, I_axial,
    I_transverse about stack CG) at web w."""
    g = inputs.grain
    rho = inputs.propellant.density_kgpm3
    R = g.od_m / 2.0
    n_seg = g.segment_count
    rc, length, center_in_slot = _segment_geometry(inputs, w)
    if rc >= R or length <= 0:
        return 0.0, None, 0.0, 0.0

    m_seg = rho * math.pi * (R * R - rc * rc) * length
    centers = [i * g.length_m + center_in_slot for i in range(n_seg)]
    m_total = m_seg * n_seg
    cg = sum(centers) / n_seg  # identical segment masses

    i_axial = n_seg * 0.5 * m_seg * (R * R + rc * rc)
    i_trans = 0.0
    for c in centers:
        d = c - cg
        i_trans += (
            (1.0 / 12.0) * m_seg * (3.0 * (R * R + rc * rc) + length * length)
            + m_seg * d * d
        )
    return m_total, cg, i_axial, i_trans


def _burning_area(inputs: MotorDesignInputs, w: float) -> float:
    """Total burning area at web w (all segments)."""
    g = inputs.grain
    faces = 2 - g.inhibited_ends
    R = g.od_m / 2.0
    rc, length, _ = _segment_geometry(inputs, w)
    if rc >= R or length <= 0:
        return 0.0
    ab_seg = 2.0 * math.pi * rc * length + faces * math.pi * (R * R - rc * rc)
    return g.segment_count * ab_seg


# ══════════════════════════════════════════════════════════════
#  The march
# ══════════════════════════════════════════════════════════════

def _march_at_temp(
    inputs: MotorDesignInputs,
    temp_K: float,
    cstar: float,
) -> TempCurve:
    p = inputs.propellant
    g = inputs.grain
    nz = inputs.nozzle
    k = p.k
    gamma = gamma_function(k)

    a_t = p.a * math.exp(p.sigma_p * (temp_K - T_NOMINAL_K))

    at = math.pi * nz.throat_d_m ** 2 / 4.0
    if nz.expansion_ratio is not None:
        eps = nz.expansion_ratio
    else:
        eps = (nz.exit_d_m / nz.throat_d_m) ** 2
    me = exit_mach_from_area_ratio(eps, k)
    pe_over_pc = (1.0 + 0.5 * (k - 1.0) * me * me) ** (-k / (k - 1.0))
    pa = nz.ambient_pressure_pa

    faces = 2 - g.inhibited_ends
    web_face = g.length_m / faces if faces > 0 else math.inf
    web_radial = (g.od_m - g.core_d_m) / 2.0
    w_burnout = min(web_radial, web_face)

    curve = TempCurve(temp_K=temp_K)
    dw = inputs.sim.web_step_m
    t = 0.0
    w = 0.0
    last_r = None

    def _sample(w_s: float, t_s: float) -> float:
        """Record one sample; returns the local burn rate r."""
        ab = _burning_area(inputs, w_s)
        if ab <= 0.0:
            return 0.0
        kn = ab / at
        pc = (kn * p.density_kgpm3 * a_t * cstar) ** (1.0 / (1.0 - p.n))
        r = a_t * pc ** p.n
        mdot = p.density_kgpm3 * ab * r
        pe = pe_over_pc * pc
        cf = gamma * math.sqrt(
            (2.0 * k / (k - 1.0)) * (1.0 - (pe / pc) ** ((k - 1.0) / k))
        ) + ((pe - pa) / pc) * eps
        thrust = max(cf * at * pc, 0.0)
        mass, cg, i_ax, i_tr = _mass_properties(inputs, w_s)
        if cg is None:
            cg = curve.cg_offset_m[-1] if curve.cg_offset_m else 0.0
        curve.time_s.append(t_s)
        curve.thrust_n.append(thrust)
        curve.pchamber_pa.append(pc)
        curve.mdot_kgps.append(mdot)
        curve.prop_mass_rem_kg.append(mass)
        curve.cg_offset_m.append(cg)
        curve.inertia_axial_kgm2.append(i_ax)
        curve.inertia_transverse_kgm2.append(i_tr)
        return r

    while w < w_burnout - 1e-12:
        r = _sample(w, t)
        if r <= 0.0:
            break
        last_r = r
        step = min(dw, w_burnout - w)
        # dt = dw / r at the local burn rate.
        t += step / r
        w += step

    # Exact terminal sample at the burnout web: the propellant slab
    # thickness is zero there, so mass is exactly 0 — the geometric
    # ṁ at w_burnout keeps the ∫ṁdt ↔ m₀ trapezoid closed; thrust
    # falls to its terminal cliff value then the series ends.
    if last_r is not None:
        # Evaluate just below burnout to avoid the degenerate rc == R.
        w_term = w_burnout - 1e-12
        _sample(w_term, t)
        # Force the terminal mass/inertias to exactly zero.
        curve.prop_mass_rem_kg[-1] = 0.0
        curve.inertia_axial_kgm2[-1] = 0.0
        curve.inertia_transverse_kgm2[-1] = 0.0

    curve.burn_time_s = curve.time_s[-1] if curve.time_s else 0.0
    curve.peak_thrust_n = max(curve.thrust_n) if curve.thrust_n else 0.0
    curve.total_impulse_ns = trapz(curve.thrust_n, curve.time_s) if curve.time_s else 0.0
    return curve


def solve_design(inputs: MotorDesignInputs) -> BallisticsResult:
    """Run the equilibrium march at the 3-temperature grid; nominal
    row = 294.15 K. Raises ``MotorDesignError`` for unsupported grain
    geometries."""
    g = inputs.grain
    if g.type.upper() != "BATES":
        raise MotorDesignError(
            f"grain type {g.type!r} not yet implemented — BATES only "
            "(finocyl/endburner are declared future geometries)"
        )

    cstar = resolve_cstar(inputs)
    warnings: List[str] = []

    by_temp = [_march_at_temp(inputs, t_k, cstar) for t_k in GRAIN_TEMP_GRID_K]
    nominal = by_temp[GRAIN_TEMP_GRID_K.index(T_NOMINAL_K)]

    if not nominal.time_s or nominal.burn_time_s <= 0.0:
        raise MotorDesignError(
            "design produced no burn — check grain geometry and web step"
        )

    prop_mass_init, _, _, _ = _mass_properties(inputs, 0.0)
    mass_burned = trapz(nominal.mdot_kgps, nominal.time_s)

    rel_err = abs(mass_burned - prop_mass_init) / prop_mass_init if prop_mass_init else 0.0
    if rel_err > MASS_BURN_TOLERANCE:
        warnings.append(
            f"mass-burn self-check failed: ∫ṁdt = {mass_burned:.6g} kg vs "
            f"propellant mass {prop_mass_init:.6g} kg "
            f"({rel_err * 100:.2f}% > {MASS_BURN_TOLERANCE * 100:.0f}%)"
        )

    total_impulse = nominal.total_impulse_ns
    isp = total_impulse / (prop_mass_init * G0) if prop_mass_init > 0 else 0.0

    at = math.pi * inputs.nozzle.throat_d_m ** 2 / 4.0
    if inputs.nozzle.expansion_ratio is not None:
        ae = inputs.nozzle.expansion_ratio * at
    else:
        ae = math.pi * inputs.nozzle.exit_d_m ** 2 / 4.0

    return BallisticsResult(
        nominal=nominal,
        by_temp=by_temp,
        prop_mass_init_kg=prop_mass_init,
        grain_stack_length_m=g.segment_count * g.length_m,
        area_throat_m2=at,
        area_exit_m2=ae,
        total_impulse_ns=total_impulse,
        peak_thrust_n=nominal.peak_thrust_n,
        burn_time_s=nominal.burn_time_s,
        isp_s=isp,
        max_pchamber_pa=max(nominal.pchamber_pa),
        motor_class=motor_class_letter(total_impulse),
        mass_burned_integral_kg=mass_burned,
        warnings=warnings,
    )


# ══════════════════════════════════════════════════════════════
#  Artifact series (uniform 1 kHz grid)
# ══════════════════════════════════════════════════════════════

def result_to_artifact_series(result: BallisticsResult) -> Dict[str, object]:
    """Resample the solver output onto the §5.4 uniform 1 kHz grid.

    The grid spans the LONGEST burn across the temperature grid (the
    cold row); every row is zero-padded after its own burnout so the
    three ``byTgrain`` tables share ``MotorTime_s``. ``Mdot_kgps`` is
    sign-flipped to the artifact's negative convention.
    """
    t_end = max(c.burn_time_s for c in result.by_temp)
    grid = uniform_grid(t_end)

    def _row(curve: TempCurve, series: List[float], zero_after_burnout: bool,
             flip_sign: bool = False) -> List[float]:
        out = resample_uniform(curve.time_s, series, grid)
        if zero_after_burnout:
            out = [
                0.0 if g_t > curve.burn_time_s + 1e-12 else v
                for g_t, v in zip(grid, out)
            ]
        if flip_sign:
            out = [-v for v in out]
        return out

    nom = result.nominal
    thrust_by_t = [_row(c, c.thrust_n, True) for c in result.by_temp]
    mdot_by_t = [_row(c, c.mdot_kgps, True, flip_sign=True) for c in result.by_temp]
    nominal_idx = result.by_temp.index(nom)

    return {
        "time_s": grid,
        "thrust_n": thrust_by_t[nominal_idx],
        "mdot_kgps": mdot_by_t[nominal_idx],
        "prop_mass_rem_kg": _row(nom, nom.prop_mass_rem_kg, False),
        "pchamber_pa": _row(nom, nom.pchamber_pa, True),
        "prop_cg_offset_m_b": _row(nom, nom.cg_offset_m, False),
        "prop_inertia_axial_kgm2": _row(nom, nom.inertia_axial_kgm2, False),
        "prop_inertia_transverse_kgm2": _row(nom, nom.inertia_transverse_kgm2, False),
        "thrust_n_by_tgrain": thrust_by_t,
        "mdot_kgps_by_tgrain": mdot_by_t,
    }
