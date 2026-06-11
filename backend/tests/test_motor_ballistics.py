"""§5.3 parametric SRM solver — unit tests (no HAROLD, no HTTP).

Covers: BATES single + 8-segment equilibrium against a hand-computed
analytic point (n = 0.5 ⇒ Pc = (Kn·ρp·a·c*)² is closed-form), impulse
self-consistency (∫F dt within 1 % of the reported total), mass-burn
consistency (∫ṁ dt vs propellant mass), 3-temperature grid ordering
(hotter ⇒ higher peak thrust, shorter burn), motor-class letters, CG
conventions, and the BATES-only geometry gate.
"""
from __future__ import annotations

import math

import pytest
from pydantic import ValidationError

from app.schemas.engineering_motor import MotorDesignInputs
from app.services.engineering.motor_artifact import (
    G0,
    motor_class_letter,
    trapz,
)
from app.services.engineering.motor_ballistics import (
    MotorDesignError,
    TempCurve,
    _impulse_consistency_warning,
    resolve_cstar,
    result_to_artifact_series,
    solve_design,
)

# Reference propellant / geometry (toy KN-ish numbers, SI).
RHO = 1750.0          # kg/m³
A_COEF = 6.0e-6       # m/(s·Pa^0.5)
N_EXP = 0.5           # ⇒ Pc = (Kn·ρ·a·c*)² closed-form
K_GAMMA = 1.2
CSTAR = 900.0         # m/s
OD = 0.05             # m
CORE = 0.02           # m
SEG_LEN = 0.12        # m
THROAT_D = 0.01       # m


def _inputs(**over) -> MotorDesignInputs:
    payload = {
        "propellant": {
            "density_kgpm3": RHO, "a": A_COEF, "n": N_EXP, "k": K_GAMMA,
            "cstar_mps": CSTAR, "sigma_p": 0.0,
        },
        "grain": {
            "type": "BATES", "od_m": OD, "core_d_m": CORE,
            "length_m": SEG_LEN, "segment_count": 1, "inhibited_ends": 0,
        },
        "nozzle": {
            "throat_d_m": THROAT_D, "expansion_ratio": 4.0,
            "ambient_pressure_pa": 101325.0,
        },
        "sim": {"web_step_m": 1e-4, "grain_temp_K": 294.15},
    }
    for section, fields in over.items():
        payload[section].update(fields)
    return MotorDesignInputs(**payload)


def _hand_pc0(segments: int) -> float:
    """Hand-computed equilibrium Pc at w = 0 for the reference grain.
    n = 0.5 ⇒ Pc = (Kn·ρp·a·c*)^(1/(1−n)) = (Kn·ρp·a·c*)²."""
    R = OD / 2.0
    rc = CORE / 2.0
    faces = 2
    ab_seg = 2.0 * math.pi * rc * SEG_LEN + faces * math.pi * (R * R - rc * rc)
    ab = segments * ab_seg
    at = math.pi * THROAT_D ** 2 / 4.0
    kn = ab / at
    return (kn * RHO * A_COEF * CSTAR) ** 2


# ── Equilibrium against the closed-form analytic point ─────────────


def test_single_segment_first_step_matches_hand_computed_pc():
    result = solve_design(_inputs())
    assert result.nominal.pchamber_pa[0] == pytest.approx(_hand_pc0(1), rel=1e-9)


def test_8_segment_first_step_matches_hand_computed_pc():
    """Multi-segment is first-class (WS01 = 8 grains): Ab scales ×8 ⇒
    Kn ×8 ⇒ Pc ×64 for n = 0.5."""
    result = solve_design(_inputs(grain={"segment_count": 8}))
    assert result.nominal.pchamber_pa[0] == pytest.approx(_hand_pc0(8), rel=1e-9)
    assert _hand_pc0(8) == pytest.approx(64.0 * _hand_pc0(1), rel=1e-12)


def test_8_segment_mass_and_stack_scale():
    one = solve_design(_inputs())
    eight = solve_design(_inputs(grain={"segment_count": 8}))
    assert eight.prop_mass_init_kg == pytest.approx(
        8.0 * one.prop_mass_init_kg, rel=1e-9
    )
    assert eight.grain_stack_length_m == pytest.approx(8 * SEG_LEN, rel=1e-12)
    # Hand check of the initial mass itself: ρ·π(R²−rc²)·L per segment.
    expected = RHO * math.pi * ((OD / 2) ** 2 - (CORE / 2) ** 2) * SEG_LEN
    assert one.prop_mass_init_kg == pytest.approx(expected, rel=1e-9)


# ── Self-consistency ────────────────────────────────────────────────


def test_impulse_self_consistency_within_1_percent():
    result = solve_design(_inputs())
    # Reported scalar vs direct integral of the native march.
    native = trapz(result.nominal.thrust_n, result.nominal.time_s)
    assert result.total_impulse_ns == pytest.approx(native, rel=1e-9)
    # …and vs the 1 kHz artifact series.
    series = result_to_artifact_series(result)
    resampled = trapz(series["thrust_n"], series["time_s"])
    assert resampled == pytest.approx(result.total_impulse_ns, rel=0.01)


def test_mass_burn_consistency_within_1_percent():
    result = solve_design(_inputs())
    assert result.mass_burned_integral_kg == pytest.approx(
        result.prop_mass_init_kg, rel=0.01
    )
    assert result.warnings == []  # self-check passed, no warning emitted
    # The propellant-mass series ends at zero.
    assert result.nominal.prop_mass_rem_kg[-1] == 0.0
    assert result.nominal.prop_mass_rem_kg[0] == pytest.approx(
        result.prop_mass_init_kg, rel=1e-9
    )


def test_impulse_self_check_passes_for_normal_march():
    """The §5.3 TotalImpulse ↔ ∫F dt self-check passes for a healthy
    march (no warning emitted)."""
    result = solve_design(_inputs())
    assert _impulse_consistency_warning(result.nominal) is None
    assert not any("impulse self-check" in w for w in result.warnings)


def test_impulse_self_check_flags_subgrid_thrust_features():
    """A thrust spike living entirely between 1 kHz grid samples is
    lost by the artifact resample ⇒ the self-check must warn."""
    spike = TempCurve(temp_K=294.15)
    spike.time_s = [0.0, 0.0004, 0.0005, 0.0006, 1.0]
    spike.thrust_n = [0.0, 0.0, 1.0e6, 0.0, 0.0]
    spike.burn_time_s = 1.0
    spike.total_impulse_ns = trapz(spike.thrust_n, spike.time_s)
    assert spike.total_impulse_ns > 0
    warning = _impulse_consistency_warning(spike)
    assert warning is not None
    assert "impulse self-check failed" in warning


def test_isp_definition():
    result = solve_design(_inputs())
    assert result.isp_s == pytest.approx(
        result.total_impulse_ns / (result.prop_mass_init_kg * G0), rel=1e-12
    )


# ── 3-temperature grid ──────────────────────────────────────────────


def test_three_temperature_grid_ordering():
    """Hotter grain ⇒ faster a(T) ⇒ higher peak thrust, shorter burn."""
    result = solve_design(_inputs(propellant={"sigma_p": 0.003}))
    cold, nominal, hot = result.by_temp
    assert cold.temp_K == 284.15 and nominal.temp_K == 294.15 and hot.temp_K == 304.15
    assert hot.peak_thrust_n > nominal.peak_thrust_n > cold.peak_thrust_n
    assert hot.burn_time_s < nominal.burn_time_s < cold.burn_time_s


def test_sigma_p_zero_collapses_grid():
    result = solve_design(_inputs())
    cold, nominal, hot = result.by_temp
    assert hot.peak_thrust_n == pytest.approx(cold.peak_thrust_n, rel=1e-12)
    assert hot.burn_time_s == pytest.approx(cold.burn_time_s, rel=1e-12)


def test_artifact_series_shapes():
    result = solve_design(_inputs(propellant={"sigma_p": 0.003}))
    series = result_to_artifact_series(result)
    grid = series["time_s"]
    n = len(grid)
    assert len(series["thrust_n_by_tgrain"]) == 3
    assert all(len(row) == n for row in series["thrust_n_by_tgrain"])
    assert all(len(row) == n for row in series["mdot_kgps_by_tgrain"])
    # 1 kHz grid.
    assert grid[1] - grid[0] == pytest.approx(0.001, abs=1e-12)
    # Grid spans the LONGEST (cold) burn; hot row is zero-padded after
    # its own burnout.
    cold = result.by_temp[0]
    hot = result.by_temp[2]
    assert grid[-1] == pytest.approx(cold.burn_time_s, rel=1e-9)
    assert series["thrust_n_by_tgrain"][2][-1] == 0.0
    assert hot.burn_time_s < grid[-1]
    # Artifact ṁ is negative.
    assert all(v <= 0.0 for v in series["mdot_kgps"])


# ── CG / mass-property conventions ──────────────────────────────────


def test_cg_constant_at_stack_center_when_both_faces_exposed():
    """faces = 2 ⇒ symmetric shrink about each slot center ⇒ the stack
    CG never moves (datum: grain-stack aft face, +x forward)."""
    result = solve_design(_inputs())
    for cg in result.nominal.cg_offset_m:
        assert cg == pytest.approx(SEG_LEN / 2.0, rel=1e-9)
    eight = solve_design(_inputs(grain={"segment_count": 8}))
    for cg in eight.nominal.cg_offset_m:
        assert cg == pytest.approx(8 * SEG_LEN / 2.0, rel=1e-9)


def test_cg_drifts_aft_with_one_inhibited_end():
    """inhibited_ends = 1 ⇒ aft face inhibited, forward face regresses
    ⇒ segment CG moves aft (toward x = 0) over the burn."""
    result = solve_design(_inputs(grain={"inhibited_ends": 1}))
    cg = result.nominal.cg_offset_m
    assert cg[0] == pytest.approx(SEG_LEN / 2.0, rel=1e-9)
    # Strictly non-increasing, and clearly lower by burnout.
    assert all(b <= a + 1e-12 for a, b in zip(cg, cg[1:]))
    assert cg[-2] < cg[0]


def test_inertias_decrease_and_end_at_zero():
    result = solve_design(_inputs(grain={"segment_count": 4}))
    ia = result.nominal.inertia_axial_kgm2
    it = result.nominal.inertia_transverse_kgm2
    assert ia[0] > 0 and it[0] > 0
    assert ia[-1] == 0.0 and it[-1] == 0.0


# ── Motor class letter ──────────────────────────────────────────────


@pytest.mark.parametrize("impulse,letter", [
    (0.2, "1/8A"),
    (0.3125, "1/8A"),
    (0.5, "1/4A"),
    (1.0, "1/2A"),
    (2.5, "A"),
    (4.9, "B"),
    (10.0, "C"),
    (640.0, "I"),
    (1280.0, "J"),
    (40960.0, "O"),
    (40961.0, "P+"),
])
def test_motor_class_ladder(impulse, letter):
    assert motor_class_letter(impulse) == letter


def test_solver_class_letter_matches_ladder():
    result = solve_design(_inputs())
    assert result.motor_class == motor_class_letter(result.total_impulse_ns)


# ── Geometry gate + input validation ────────────────────────────────


def test_non_bates_grain_not_yet_implemented():
    with pytest.raises(MotorDesignError, match="not yet implemented"):
        solve_design(_inputs(grain={"type": "finocyl"}))
    with pytest.raises(MotorDesignError, match="not yet implemented"):
        solve_design(_inputs(grain={"type": "endburner"}))


def test_cstar_resolves_from_tc_and_molar_mass():
    inputs = _inputs(propellant={
        "cstar_mps": None, "Tc_K": 1600.0, "molar_mass_kgpmol": 0.042,
    })
    cstar = resolve_cstar(inputs)
    # c* = sqrt((R_u/M)·Tc)/Γ — hand check.
    gamma = math.sqrt(K_GAMMA) * (2 / (K_GAMMA + 1)) ** (
        (K_GAMMA + 1) / (2 * (K_GAMMA - 1))
    )
    expected = math.sqrt((8.314462618 / 0.042) * 1600.0) / gamma
    assert cstar == pytest.approx(expected, rel=1e-12)
    # And the solver runs with it.
    result = solve_design(inputs)
    assert result.total_impulse_ns > 0


def test_propellant_requires_cstar_or_tc_and_m():
    with pytest.raises(ValidationError, match="cstar_mps OR"):
        _inputs(propellant={"cstar_mps": None})


def test_core_must_be_smaller_than_od():
    with pytest.raises(ValidationError, match="core_d_m must be <"):
        _inputs(grain={"core_d_m": 0.06})


def test_nozzle_requires_exit_or_expansion_ratio():
    with pytest.raises(ValidationError, match="exit_d_m OR expansion_ratio"):
        _inputs(nozzle={"expansion_ratio": None})


def test_exit_diameter_equivalent_to_expansion_ratio():
    """ε = (De/Dt)² — both parameterizations give the same motor."""
    by_eps = solve_design(_inputs())
    by_d = solve_design(_inputs(nozzle={
        "expansion_ratio": None, "exit_d_m": THROAT_D * 2.0,  # ε = 4
    }))
    assert by_d.total_impulse_ns == pytest.approx(by_eps.total_impulse_ns, rel=1e-9)
    assert by_d.area_exit_m2 == pytest.approx(by_eps.area_exit_m2, rel=1e-9)
