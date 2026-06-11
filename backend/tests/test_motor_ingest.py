"""§5.2 motor CSV ingest — unit tests (no HAROLD, no HTTP).

Covers: the synthetic 8-grain WS01-like fixture (grain-mass row-sum =
PropMassInit), alias/unit-aware parsing (lbf / psi variants),
constant-Isp fallback ⇒ 'workable' + defaultedFields, ṁ forced
negative, the 1 kHz resample grid, and the qualityTier rules.
"""
from __future__ import annotations

import pytest

from app.services.engineering.motor_artifact import G0, trapz
from app.services.engineering.motor_ingest import (
    LBF_TO_N,
    PSI_TO_PA,
    MotorCsvError,
    ingest_motor_csv,
)


# ── Synthetic CSV builders ──────────────────────────────────────────

def _ws01_csv(
    *,
    n_grains: int = 8,
    grain_mass: float = 0.4,
    thrust: float = 1000.0,
    t_burn: float = 1.8,
    t_total: float = 2.0,
    dt: float = 0.01,
    pc: float = 5.0e6,
    include_pressure: bool = True,
    include_mass: bool = True,
    include_grains: bool = True,
    mass0_override: float | None = None,
    header: str | None = None,
    thrust_scale: float = 1.0,
    pc_scale: float = 1.0,
) -> str:
    """8-grain WS01-like thrust-curve CSV: grain-mass header comments +
    time/thrust/mass/pressure columns, mutually consistent (the mass
    column burns the grain-sum linearly over the burn)."""
    lines: list[str] = []
    if include_grains:
        for i in range(n_grains):
            lines.append(f"# GrainMass_{i + 1}, {grain_mass}")
    cols = ["MotorTime_s", "Thrust_N"]
    if include_mass:
        cols.append("PropMassRem_kg")
    if include_pressure:
        cols.append("Pchamber_Pa")
    lines.append(header or ",".join(cols))

    m0 = mass0_override if mass0_override is not None else n_grains * grain_mass
    n_rows = int(round(t_total / dt)) + 1
    for i in range(n_rows):
        t = i * dt
        burning = t < t_burn
        f = thrust * thrust_scale if burning else 0.0
        row = [f"{t:.4f}", f"{f:.6f}"]
        if include_mass:
            m = m0 * (1.0 - t / t_burn) if burning else 0.0
            row.append(f"{m:.9f}")
        if include_pressure:
            row.append(f"{(pc * pc_scale if burning else 0.0):.3f}")
        lines.append(",".join(row))
    return "\n".join(lines)


# ── WS01-like 8-grain happy path ────────────────────────────────────


def test_ws01_grain_mass_row_sum_is_prop_mass_init():
    res = ingest_motor_csv(_ws01_csv())
    assert res.grain_masses_kg == [0.4] * 8
    assert res.prop_mass_init_kg == pytest.approx(3.2, rel=1e-12)
    assert res.prop_mass_rem_kg[0] == pytest.approx(3.2, rel=1e-6)


def test_ws01_is_excellent_and_hifi():
    res = ingest_motor_csv(_ws01_csv())
    assert res.quality_tier == "excellent"
    assert res.recommended_fidelity == "HiFi"
    # Pressure and ṁ are measured, not defaulted.
    assert "Pchamber_Pa" not in res.defaulted_fields
    assert "Mdot_kgps" not in res.defaulted_fields
    # Geometry a CSV can never provide is always defaulted.
    for f in (
        "PropCGOffset_m_B", "PropInertiaAxial_kgm2",
        "PropInertiaTransverse_kgm2", "AreaThroat_m2", "AreaExit_m2",
        "GrainStackLength_m", "Thrust_N_byTgrain", "Mdot_kgps_byTgrain",
    ):
        assert f in res.defaulted_fields


def test_ws01_scalars_and_burn_trim():
    res = ingest_motor_csv(_ws01_csv())
    # Tail trim: thrust drops to 0 at t = 1.8; last ≥0.5%-of-peak
    # sample is t = 1.79.
    assert res.burn_time_s == pytest.approx(1.79, abs=1e-9)
    assert res.peak_thrust_n == pytest.approx(1000.0, rel=1e-9)
    assert res.total_impulse_ns == pytest.approx(1790.0, rel=0.01)
    assert res.isp_s == pytest.approx(
        res.total_impulse_ns / (3.2 * G0), rel=1e-9
    )


def test_ws01_temp_grid_replicated():
    res = ingest_motor_csv(_ws01_csv())
    assert len(res.thrust_n_by_tgrain) == 3
    assert res.thrust_n_by_tgrain[0] == res.thrust_n_by_tgrain[2] == res.thrust_n
    assert res.mdot_kgps_by_tgrain[1] == res.mdot_kgps


def test_one_khz_resample_grid():
    res = ingest_motor_csv(_ws01_csv())
    t = res.time_s
    assert t[0] == 0.0
    diffs = [b - a for a, b in zip(t, t[1:])]
    assert all(d == pytest.approx(0.001, abs=1e-12) for d in diffs[:-1])
    n = len(t)
    assert (
        len(res.thrust_n) == len(res.mdot_kgps)
        == len(res.prop_mass_rem_kg) == len(res.pchamber_pa) == n
    )


def test_resample_linearly_interpolates():
    # Coarse 0.1 s ramp: thrust 0→1000 over 1 s, then cut. The 1 kHz
    # grid samples between the raw points must sit on the line.
    rows = ["time,thrust,mass_kg", ]
    for i in range(11):
        t = i * 0.1
        rows.append(f"{t},{1000.0 * t:.3f},{1.0 - 0.09 * t:.6f}")
    res = ingest_motor_csv("\n".join(rows) + "\n# PropellantMass_kg, 1.0")
    # t = 0.05 is halfway between the first two raw samples — on the
    # 1 kHz grid that is index 50.
    assert res.time_s[50] == pytest.approx(0.05, abs=1e-12)
    assert res.thrust_n[50] == pytest.approx(50.0, rel=1e-6)


# ── Alias / unit-aware parsing ──────────────────────────────────────


def test_lbf_and_psi_unit_conversion():
    csv_text = _ws01_csv(
        header="Time (s),Thrust_lbf,PropMassRem_kg,pc_psi",
        thrust=100.0,           # lbf
        pc=500.0,               # psi
    )
    res = ingest_motor_csv(csv_text)
    assert res.thrust_n[0] == pytest.approx(100.0 * LBF_TO_N, rel=1e-9)
    assert res.pchamber_pa[0] == pytest.approx(500.0 * PSI_TO_PA, rel=1e-9)
    assert res.peak_thrust_n == pytest.approx(100.0 * LBF_TO_N, rel=1e-9)


def test_header_aliases_case_space_punctuation_insensitive():
    csv_text = _ws01_csv(header='" MotorTime_s ","THRUST (N)","prop_mass_kg","P chamber (Pa)"')
    res = ingest_motor_csv(csv_text)
    assert res.peak_thrust_n == pytest.approx(1000.0, rel=1e-9)
    assert res.pchamber_pa[0] == pytest.approx(5.0e6, rel=1e-9)


def test_key_value_metadata_rows_carry_grain_masses():
    """Non-comment key/value rows before the header also work."""
    body = _ws01_csv(include_grains=False)
    rows = "\n".join(f"Grain_Mass_{i + 1}, 0.4" for i in range(8))
    res = ingest_motor_csv(rows + "\n" + body)
    assert res.prop_mass_init_kg == pytest.approx(3.2, rel=1e-12)
    assert res.quality_tier == "excellent"


# ── ṁ derivation ────────────────────────────────────────────────────


def test_mdot_is_negative_everywhere():
    res = ingest_motor_csv(_ws01_csv())
    assert all(v <= 0.0 for v in res.mdot_kgps)
    assert min(res.mdot_kgps) < 0.0  # actually burning


def test_mdot_forced_negative_clamps_positive_excursions():
    # Inject a mass INCREASE mid-burn (sensor glitch) — derived
    # d(mass)/dt goes positive there and must be clamped with a warning.
    lines = ["# GrainMass_1, 1.0", "time,thrust,mass_kg"]
    masses = [1.0, 0.9, 0.8, 1.05, 0.7, 0.5, 0.3, 0.1, 0.0]
    for i, m in enumerate(masses):
        lines.append(f"{i * 0.1},{100.0 if m > 0 else 0.0},{m}")
    res = ingest_motor_csv("\n".join(lines))
    assert all(v <= 0.0 for v in res.mdot_kgps)
    assert any("forced negative" in w for w in res.warnings)


def test_nozzle_flow_crosscheck_prefers_derived():
    # Add a nozzle mdot column 50 % off the derived d(mass)/dt.
    lines = ["# GrainMass_1, 1.8", "time,thrust,mass_kg,nozzle_mdot_kgps"]
    for i in range(101):
        t = i * 0.01
        burning = t < 0.9
        m = 1.8 * (1 - t / 0.9) if burning else 0.0
        nozzle = -3.0 if burning else 0.0  # true ṁ is −2.0 kg/s
        lines.append(f"{t},{1000.0 if burning else 0.0},{m:.6f},{nozzle}")
    res = ingest_motor_csv("\n".join(lines))
    assert any("derived ṁ preferred" in w for w in res.warnings)
    assert res.quality_tier == "workable"  # cross-check discrepancy
    # Derived wins: ∫|ṁ|dt ≈ 1.8 kg, not 2.7.
    burned = trapz([abs(v) for v in res.mdot_kgps], res.time_s)
    assert burned == pytest.approx(1.8, rel=0.05)


# ── Constant-Isp fallback ───────────────────────────────────────────


def test_constant_isp_fallback_is_workable_with_defaults():
    lines = ["PropellantMass_kg, 1.5", "time,thrust"]
    for i in range(101):
        t = i * 0.01
        lines.append(f"{t},{800.0 if t < 0.9 else 0.0}")
    res = ingest_motor_csv("\n".join(lines))
    assert res.quality_tier == "workable"
    assert res.recommended_fidelity == "Nominal"
    for f in ("Mdot_kgps", "PropMassRem_kg", "Pchamber_Pa"):
        assert f in res.defaulted_fields
    assert any("constant-Isp" in w for w in res.warnings)
    # ṁ = −F/(Isp·g0): negative and proportional to thrust.
    assert all(v <= 0.0 for v in res.mdot_kgps)
    assert res.prop_mass_init_kg == pytest.approx(1.5, rel=1e-12)
    assert res.prop_mass_rem_kg[0] == pytest.approx(1.5, rel=1e-9)
    assert res.prop_mass_rem_kg[-1] < 0.15  # nearly all burned
    # Isp from the fallback identity (computed on the raw full curve).
    assert res.mdot_kgps[0] == pytest.approx(
        -res.thrust_n[0] / (res.isp_s * G0), rel=0.02
    )


def test_no_mass_information_raises():
    lines = ["time,thrust"] + [f"{i * 0.01},{500.0}" for i in range(100)]
    with pytest.raises(MotorCsvError, match="propellant mass"):
        ingest_motor_csv("\n".join(lines))


def test_garbage_csv_raises():
    with pytest.raises(MotorCsvError, match="header"):
        ingest_motor_csv("this,is\nnot,a\nmotor,curve")


# ── qualityTier rules ───────────────────────────────────────────────


def test_pressure_missing_is_workable():
    res = ingest_motor_csv(_ws01_csv(include_pressure=False))
    assert res.quality_tier == "workable"
    assert "Pchamber_Pa" in res.defaulted_fields


def test_mass_series_without_grain_confirmation_is_good():
    """Thrust + mass series + pressure, but PropMassInit inferred from
    the first mass sample (a minor default) ⇒ 'good'."""
    res = ingest_motor_csv(_ws01_csv(include_grains=False, mass0_override=3.2))
    assert res.quality_tier == "good"
    assert "PropMassInit_kg" in res.defaulted_fields
    assert res.prop_mass_init_kg == pytest.approx(3.2, rel=1e-9)
    assert res.recommended_fidelity == "Nominal"


def test_grain_sum_vs_mass_series_disagreement_is_workable():
    # Grain sum 3.2 kg but the mass column starts at 2.0 kg ⇒ >2 %
    # cross-check failure ⇒ workable.
    res = ingest_motor_csv(_ws01_csv(mass0_override=2.0))
    assert res.quality_tier == "workable"
    assert any("disagrees" in w for w in res.warnings)
    # Grain-mass row-sum stays authoritative.
    assert res.prop_mass_init_kg == pytest.approx(3.2, rel=1e-12)
