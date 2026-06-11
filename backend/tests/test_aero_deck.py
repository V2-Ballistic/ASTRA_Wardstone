"""Unit tests for the aero-deck normalization service (spec §6).

Pure-python tests of ``app.services.engineering.aero_deck`` — CSV
parsing (alias matching, Cn-yaw disambiguation), grid building, ragged
grids, merging, derived stability derivatives, the envelope, canonical
hashing and preview interpolation. No HTTP, no DB.
"""
from __future__ import annotations

import hashlib
import json

import pytest

from app.services.engineering.aero_deck import (
    SOURCE_PARSERS,
    AeroDeckError,
    AeroEnvelopeError,
    AeroFormatError,
    AeroGridError,
    AeroMergeConflictError,
    ParsedSource,
    canonical_json,
    deck_sha256,
    detect_source_format,
    interpolate,
    interpolate_point,
    merge_decks,
    parse_csv_source,
    parse_source,
    register_source_parser,
)

MACHS = (0.3, 0.8, 1.2)
ALPHAS = (-4.0, 0.0, 4.0, 8.0)


def _ca(m, a):  # alpha-independent, mach-linear
    return 0.3 + 0.1 * m


def _cn(m, a):  # mach-independent, alpha-linear → CNalpha = 0.05/deg
    return 0.05 * a


def _cm(m, a):  # Cmalpha = -0.02/deg
    return -0.02 * a


def _csv(machs=MACHS, alphas=ALPHAS, *, header="Mach,Alpha_deg,CA,CN,Cm",
         comments=True, cn=_cn):
    lines = []
    if comments:
        lines += [
            "# Sref_m2: 0.018",
            "# Lref_m: 0.152",
            "# refPoint_m_B: 0.45, 0.0, 0.0",
            "# omlWpn: WS-OML-P000010-A",
            "# vortexModel: spinner-v2",
        ]
    lines.append(header)
    for m in machs:
        for a in alphas:
            lines.append(f"{m},{a},{_ca(m, a)},{cn(m, a)},{_cm(m, a)}")
    return "\n".join(lines) + "\n"


def _build(*texts, **kwargs):
    sources = [parse_source(f"src{i}.csv", t) for i, t in enumerate(texts)]
    return merge_decks(sources, **kwargs)


# ── Alias matching & disambiguation ─────────────────────────────────


def test_header_aliases_case_and_punctuation_insensitive():
    text = (
        "# Sref_m2: 1\n# Lref_m: 1\n"
        "M, AoA_deg , cx_axial, cNormal, C_PM\n"
        "0.5,0,0.31,0.0,0.0\n"
        "0.5,4,0.31,0.2,-0.08\n"
    )
    src = parse_source("x.csv", text)
    assert src.columns == ["CA", "CN", "Cm"]
    assert src.rows[0]["mach"] == 0.5


def test_cn_yaw_disambiguation_bare_cn_is_normal_force():
    """Bare 'CN' (any case) is the normal-force coefficient; the yaw
    moment Cn requires cn_yaw / cln / c_yaw."""
    text = (
        "# Sref_m2: 1\n# Lref_m: 1\n"
        "mach,alpha,CN,Cn_yaw,Cl\n"
        "0.5,0,0.0,0.01,0.002\n"
        "0.5,4,0.2,0.03,0.004\n"
    )
    src = parse_source("x.csv", text)
    assert src.columns == ["CN", "Cl", "Cn"]
    row = next(r for r in src.rows if r["alpha_deg"] == 4.0)
    assert row["coeffs"]["CN"] == pytest.approx(0.2)
    assert row["coeffs"]["Cn"] == pytest.approx(0.03)
    assert row["coeffs"]["Cl"] == pytest.approx(0.004)


def test_cln_and_c_yaw_aliases_map_to_yaw_moment():
    for yaw_header in ("CLN", "c_yaw"):
        text = (
            "# Sref_m2: 1\n# Lref_m: 1\n"
            f"mach,alpha,cn,{yaw_header}\n0.5,0,0.0,0.02\n0.5,4,0.2,0.04\n"
        )
        src = parse_source("x.csv", text)
        assert "Cn" in src.columns and "CN" in src.columns


def test_control_derivative_columns_recognized():
    text = (
        "# Sref_m2: 1\n# Lref_m: 1\n"
        "mach,alpha,delta_deg,CN,CN_delta,Cm_delta\n"
        "0.5,0,0,0.0,0.05,-0.02\n"
        "0.5,4,0,0.2,0.05,-0.02\n"
    )
    src = parse_source("x.csv", text)
    assert "CN_delta" in src.columns
    assert "Cm_delta" in src.columns
    assert src.has_delta


def test_unrecognized_column_warns_and_is_ignored():
    text = (
        "# Sref_m2: 1\n# Lref_m: 1\n"
        "mach,alpha,CN,wibble\n0.5,0,0.0,9\n0.5,4,0.2,9\n"
    )
    src = parse_source("x.csv", text)
    assert any("wibble" in w for w in src.warnings)
    assert src.columns == ["CN"]


def test_datcom_out_rejected_as_future_format():
    with pytest.raises(AeroFormatError, match="format not yet supported: datcom"):
        parse_source("missile.out", "DATCOM output ...")


# ── Source-format dispatch seam (the DATCOM extension point) ────────


def test_detect_source_format_extension_and_content_sniff():
    assert detect_source_format("missile.out", "anything") == "datcom"
    assert detect_source_format("MISSILE.OUT", "") == "datcom"
    assert detect_source_format("deck.csv", "mach,alpha,CN\n") == "csv"
    # DATCOM namelist cards are sniffed even without the .out extension
    assert detect_source_format(
        "for005.dat", "CASEID demo case\n $FLTCON NMACH=1.$\n",
    ) == "datcom"
    assert detect_source_format(
        "run2.dat", " $FLTCON NMACH=2.0$\n",
    ) == "datcom"


def test_source_parser_registry_declares_datcom_future():
    """The registry is the documented extension point: csv is the one
    concrete parser, datcom is registered-but-NotImplemented."""
    assert set(SOURCE_PARSERS) >= {"csv", "datcom"}
    assert SOURCE_PARSERS["csv"] is parse_csv_source
    with pytest.raises(AeroFormatError,
                       match="format not yet supported: datcom"):
        SOURCE_PARSERS["datcom"]("missile.out", "...")


def test_datcom_content_sniffed_without_out_extension_is_rejected():
    with pytest.raises(AeroFormatError, match="datcom"):
        parse_source("for005.dat", "CASEID demo\n$FLTCON NMACH=1.$\n")


def test_registered_datcom_parser_takes_over_dispatch():
    """Plugging a parser into the registry reroutes parse_source with
    no other change — the seam the aero team will use."""
    calls = {}

    def fake_datcom(filename: str, text: str) -> ParsedSource:
        calls["args"] = (filename, text)
        src = ParsedSource(filename=filename)
        src.rows = [{"mach": 0.5, "alpha_deg": 0.0, "beta_deg": 0.0,
                     "delta_deg": 0.0, "coeffs": {"CN": 0.0}}]
        src.columns = ["CN"]
        return src

    original = SOURCE_PARSERS["datcom"]
    register_source_parser("datcom", fake_datcom)
    try:
        src = parse_source("missile.out", "DATCOM output ...")
        assert calls["args"] == ("missile.out", "DATCOM output ...")
        assert src.filename == "missile.out"
        assert src.columns == ["CN"]
    finally:
        register_source_parser("datcom", original)
    # restored: the declared-future rejection is back
    with pytest.raises(AeroFormatError, match="datcom"):
        parse_source("missile.out", "DATCOM output ...")


def test_metadata_comments_and_extensions_passthrough():
    built = _build(_csv())
    deck = built.deck
    assert deck["Sref_m2"] == pytest.approx(0.018)
    assert deck["Lref_m"] == pytest.approx(0.152)
    assert deck["refPoint_m_B"] == [0.45, 0.0, 0.0]
    assert deck["omlWpn"] == "WS-OML-P000010-A"
    # unknown # key: value preserved verbatim — the extensibility hook
    assert deck["extensions"] == {"vortexModel": "spinner-v2"}
    assert "refPoint_m_B" not in built.defaulted_fields


def test_missing_sref_lref_rejected():
    with pytest.raises(AeroDeckError, match="Sref_m2"):
        _build(_csv(comments=False))


def test_form_field_overrides_win_over_comments():
    built = _build(_csv(), sref_m2=0.999)
    assert built.deck["Sref_m2"] == pytest.approx(0.999)
    assert built.deck["Lref_m"] == pytest.approx(0.152)  # comment kept


def test_ref_point_defaults_to_origin_and_is_recorded():
    text = "# Sref_m2: 1\n# Lref_m: 1\nmach,alpha,CN\n0.5,0,0\n0.5,4,0.2\n"
    built = _build(text)
    assert built.deck["refPoint_m_B"] == [0.0, 0.0, 0.0]
    assert "refPoint_m_B" in built.defaulted_fields


# ── Grid building ───────────────────────────────────────────────────


def test_grid_axes_ordering_and_breakpoints():
    deck = _build(_csv()).deck
    assert deck["schema"] == "astra-aero-deck/1.0"
    assert deck["frame"] == "citadel-vehicle-body-frame"
    assert deck["units"] == "SI/deg"
    assert deck["axes"] == ["mach", "alpha_deg", "beta_deg", "delta_deg"]
    bp = deck["breakpoints"]
    assert bp["mach"] == [0.3, 0.8, 1.2]
    assert bp["alpha_deg"] == [-4.0, 0.0, 4.0, 8.0]
    assert bp["beta_deg"] == [0.0]      # beta absent → [0]
    assert bp["delta_deg"] == [0.0]     # delta absent → [0]
    # table shape: [mach][alpha][beta][delta]
    cn = deck["tables"]["CN"]
    assert len(cn) == 3 and len(cn[0]) == 4
    assert len(cn[0][0]) == 1 and len(cn[0][0][0]) == 1
    # value placement: CN(mach=0.8, alpha=4) = 0.2
    assert cn[1][2][0][0] == pytest.approx(0.2)
    # CA mach-dependence lands on the mach axis
    ca = deck["tables"]["CA"]
    assert ca[0][0][0][0] == pytest.approx(0.33)
    assert ca[2][0][0][0] == pytest.approx(0.42)


def test_beta_axis_gridded_when_present():
    rows = ["# Sref_m2: 1", "# Lref_m: 1", "mach,alpha,beta_deg,CY"]
    for b in (-2.0, 0.0, 2.0):
        for a in (0.0, 4.0):
            rows.append(f"0.5,{a},{b},{0.01 * b}")
    deck = _build("\n".join(rows)).deck
    assert deck["breakpoints"]["beta_deg"] == [-2.0, 0.0, 2.0]
    cy = deck["tables"]["CY"]
    # [mach=0][alpha=0][beta=2 → +2.0][delta=0]
    assert cy[0][0][2][0] == pytest.approx(0.02)


def test_full_cartesian_grid_is_exact_no_warnings():
    built = _build(_csv())
    assert not any("interpolation" in w for w in built.warnings)


def test_ragged_grid_interpolated_where_possible():
    # full grid minus the (0.8, 0.0) point → 1-D interp along alpha
    lines = ["# Sref_m2: 1", "# Lref_m: 1", "mach,alpha,CN"]
    for m in MACHS:
        for a in ALPHAS:
            if (m, a) == (0.8, 0.0):
                continue
            lines.append(f"{m},{a},{_cn(m, a)}")
    built = _build("\n".join(lines))
    cn = built.deck["tables"]["CN"]
    # interpolated between CN(0.8,-4)=-0.2 and CN(0.8,4)=0.2 → 0.0
    assert cn[1][1][0][0] == pytest.approx(0.0)
    assert any("interpolation" in w and "CN" in w for w in built.warnings)


def test_ragged_grid_unfillable_lists_missing_points():
    # Cm given only at mach 0.3 — at mach 1.2 (grid edge) there is no
    # bracketing neighbour, so interpolation cannot fill it.
    lines = ["# Sref_m2: 1", "# Lref_m: 1", "mach,alpha,CN,Cm"]
    for m in (0.3, 1.2):
        for a in (0.0, 4.0):
            cm_cell = f"{_cm(m, a)}" if m == 0.3 else ""
            lines.append(f"{m},{a},{_cn(m, a)},{cm_cell}")
    with pytest.raises(AeroGridError) as excinfo:
        _build("\n".join(lines))
    pts = excinfo.value.points
    assert len(pts) == 2
    assert all(p["coefficient"] == "Cm" for p in pts)
    assert {p["mach"] for p in pts} == {1.2}
    assert {p["alpha_deg"] for p in pts} == {0.0, 4.0}


def test_duplicate_conflicting_rows_rejected():
    text = (
        "# Sref_m2: 1\n# Lref_m: 1\n"
        "mach,alpha,CN\n0.5,0,0.10\n0.5,4,0.2\n0.5,0,0.11\n"
    )
    with pytest.raises(AeroGridError, match="duplicate conflicting"):
        parse_source("x.csv", text)


def test_duplicate_identical_rows_deduplicated():
    text = (
        "# Sref_m2: 1\n# Lref_m: 1\n"
        "mach,alpha,CN\n0.5,0,0.10\n0.5,4,0.2\n0.5,0,0.10\n"
    )
    src = parse_source("x.csv", text)
    assert len(src.rows) == 2


# ── Merge ───────────────────────────────────────────────────────────


def test_merge_unions_breakpoints():
    built = _build(
        _csv(machs=(0.3, 0.8, 1.2)),
        _csv(machs=(1.5, 2.0), comments=False),
    )
    bp = built.deck["breakpoints"]
    assert bp["mach"] == [0.3, 0.8, 1.2, 1.5, 2.0]
    env = built.deck["validityEnvelope"]
    assert env["machRange"] == [0.3, 2.0]
    cn = built.deck["tables"]["CN"]
    assert cn[4][3][0][0] == pytest.approx(_cn(2.0, 8.0))


def test_merge_conflict_lists_offending_points():
    a = _csv(machs=(0.3, 0.8))
    b = _csv(machs=(0.8, 1.2), comments=False,
             cn=lambda m, x: 0.05 * x + 0.01)  # differs at mach 0.8
    with pytest.raises(AeroMergeConflictError) as excinfo:
        _build(a, b)
    pts = excinfo.value.points
    assert pts and all(p["mach"] == 0.8 for p in pts)
    assert all(p["coefficient"] == "CN" for p in pts)
    assert any("src0.csv" in p["sources"] and "src1.csv" in p["sources"]
               for p in pts)


def test_merge_overlap_with_identical_values_is_fine():
    built = _build(_csv(machs=(0.3, 0.8)),
                   _csv(machs=(0.8, 1.2), comments=False))
    assert built.deck["breakpoints"]["mach"] == [0.3, 0.8, 1.2]


# ── Derived quantities ──────────────────────────────────────────────


def test_cnalpha_cmalpha_central_difference_hand_check():
    deck = _build(_csv()).deck
    derived = deck["derived"]
    # hand check: central difference about alpha=0 with neighbours ±4:
    # CNalpha = (CN(4) - CN(-4)) / 8 = (0.2 - (-0.2)) / 8 = 0.05 /deg
    assert derived["CNalpha_per_deg"] == pytest.approx([0.05] * 3)
    # Cmalpha = (Cm(4) - Cm(-4)) / 8 = (-0.08 - 0.08) / 8 = -0.02 /deg
    assert derived["Cmalpha_per_deg"] == pytest.approx([-0.02] * 3)
    assert derived["alpha_ref_deg"] == 0.0
    # staticMargin_proxy = -Cmalpha / CNalpha = 0.4 (Lref units)
    assert derived["staticMargin_proxy"] == pytest.approx([0.4] * 3)


def test_static_margin_proxy_skipped_when_not_computable():
    # CN-only deck: Cmalpha unavailable → no proxy key at all
    text = "# Sref_m2: 1\n# Lref_m: 1\nmach,alpha,CN\n0.5,0,0\n0.5,4,0.2\n"
    derived = _build(text).deck["derived"]
    assert "CNalpha_per_deg" in derived
    assert "staticMargin_proxy" not in derived
    assert "Cmalpha_per_deg" not in derived


def _beta_csv():
    """Full mach × alpha × beta grid with beta-linear Cn / Cl:
    Cn = 0.01·β (Cnbeta = 0.01/deg), Cl = -0.004·β (Clbeta =
    -0.004/deg); CN/Cm stay alpha-linear for the longitudinal checks."""
    lines = ["# Sref_m2: 1", "# Lref_m: 1",
             "mach,alpha,beta_deg,CN,Cm,Cn_yaw,Cl"]
    for m in (0.5, 1.0):
        for a in (-4.0, 0.0, 4.0):
            for b in (-4.0, 0.0, 4.0):
                lines.append(
                    f"{m},{a},{b},{0.05 * a},{-0.02 * a},"
                    f"{0.01 * b},{-0.004 * b}"
                )
    return "\n".join(lines) + "\n"


def test_cnbeta_clbeta_central_difference_hand_check():
    derived = _build(_beta_csv()).deck["derived"]
    # central difference about beta=0 with neighbours ±4:
    # Cnbeta = (Cn(4) - Cn(-4)) / 8 = (0.04 + 0.04) / 8 = 0.01 /deg
    assert derived["Cnbeta_per_deg"] == pytest.approx([0.01, 0.01])
    # Clbeta = (Cl(4) - Cl(-4)) / 8 = (-0.016 - 0.016) / 8 = -0.004
    assert derived["Clbeta_per_deg"] == pytest.approx([-0.004, -0.004])
    assert derived["beta_ref_deg"] == 0.0
    # longitudinal derivatives still computed on the beta≈0 slice
    assert derived["CNalpha_per_deg"] == pytest.approx([0.05, 0.05])
    assert derived["Cmalpha_per_deg"] == pytest.approx([-0.02, -0.02])


def test_beta_derivatives_skipped_on_degenerate_beta_grid():
    """Documented skip: Cn/Cl tables exist, but the beta grid is the
    degenerate default [0.0] — nothing to difference, keys absent."""
    text = (
        "# Sref_m2: 1\n# Lref_m: 1\n"
        "mach,alpha,Cn_yaw,Cl\n0.5,0,0.01,0.002\n0.5,4,0.02,0.003\n"
    )
    deck = _build(text).deck
    assert deck["breakpoints"]["beta_deg"] == [0.0]
    derived = deck["derived"]
    assert "Cnbeta_per_deg" not in derived
    assert "Clbeta_per_deg" not in derived
    assert "beta_ref_deg" not in derived


# ── Envelope ────────────────────────────────────────────────────────


def test_validity_envelope():
    env = _build(_csv()).deck["validityEnvelope"]
    assert env["machRange"] == [0.3, 1.2]
    assert env["alphaRange_deg"] == [-4.0, 8.0]
    assert env["betaRange_deg"] == [0.0, 0.0]


# ── Canonical hash ──────────────────────────────────────────────────


def test_deck_sha256_is_canonical_sorted_compact():
    deck = _build(_csv()).deck
    sha = deck_sha256(deck)
    expected = hashlib.sha256(
        json.dumps(deck, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    assert sha == expected
    # key order must not matter
    shuffled = json.loads(json.dumps(deck))
    assert deck_sha256(shuffled) == sha


# ── Preview interpolation ───────────────────────────────────────────


def test_interpolate_point_bilinear_hand_check():
    deck = _build(_csv()).deck
    vals = interpolate_point(deck, mach=0.55, alpha_deg=2.0)
    # all fixture coefficients are (bi)linear → interpolation is exact
    assert vals["CA"] == pytest.approx(0.3 + 0.1 * 0.55)
    assert vals["CN"] == pytest.approx(0.05 * 2.0)
    assert vals["Cm"] == pytest.approx(-0.02 * 2.0)


def test_interpolate_point_at_breakpoint_exact():
    deck = _build(_csv()).deck
    vals = interpolate_point(deck, mach=0.8, alpha_deg=4.0)
    assert vals["CN"] == pytest.approx(0.2)


def test_interpolate_point_outside_envelope_raises():
    deck = _build(_csv()).deck
    with pytest.raises(AeroEnvelopeError, match="mach"):
        interpolate_point(deck, mach=3.0, alpha_deg=0.0)
    with pytest.raises(AeroEnvelopeError, match="alpha"):
        interpolate_point(deck, mach=0.5, alpha_deg=30.0)


# ── Multilinear runtime lookup (interpolate) ────────────────────────


def _beta_delta_csv():
    """Full mach × alpha × beta × delta grid with multilinear
    coefficients: CN = 0.05·α + 0.03·δ, CY = 0.02·β."""
    lines = ["# Sref_m2: 1", "# Lref_m: 1",
             "mach,alpha,beta_deg,delta_deg,CN,CY"]
    for m in (0.5, 1.0):
        for a in (0.0, 4.0):
            for b in (-4.0, 0.0, 4.0):
                for d in (0.0, 10.0):
                    lines.append(
                        f"{m},{a},{b},{d},{0.05 * a + 0.03 * d},"
                        f"{0.02 * b}"
                    )
    return "\n".join(lines) + "\n"


def test_interpolate_multilinear_4d_hand_check():
    deck = _build(_beta_delta_csv()).deck
    vals = interpolate(deck, mach=0.75, alpha_deg=2.0,
                       beta_deg=1.0, delta_deg=5.0)
    # multilinear fixtures → interpolation is exact off-breakpoint
    assert vals["CN"] == pytest.approx(0.05 * 2.0 + 0.03 * 5.0)
    assert vals["CY"] == pytest.approx(0.02 * 1.0)


def test_interpolate_defaults_to_beta_delta_zero():
    deck = _build(_beta_delta_csv()).deck
    vals = interpolate(deck, mach=0.5, alpha_deg=4.0)
    assert vals["CN"] == pytest.approx(0.2)   # delta = 0
    assert vals["CY"] == pytest.approx(0.0)   # beta = 0


def test_interpolate_degenerate_axes_collapse():
    # deck without beta/delta columns: grids are [0.0]; querying the
    # only slice works, anything else is outside the envelope
    deck = _build(_csv()).deck
    vals = interpolate(deck, mach=0.8, alpha_deg=4.0)
    assert vals["CN"] == pytest.approx(0.2)
    with pytest.raises(AeroEnvelopeError, match="beta"):
        interpolate(deck, 0.8, 4.0, beta_deg=2.0)


def test_interpolate_beta_delta_outside_envelope_raise():
    deck = _build(_beta_delta_csv()).deck
    with pytest.raises(AeroEnvelopeError, match="beta"):
        interpolate(deck, 0.5, 0.0, beta_deg=10.0)
    with pytest.raises(AeroEnvelopeError, match="delta"):
        interpolate(deck, 0.5, 0.0, delta_deg=-5.0)


def test_interpolate_point_is_nearest_zero_slice_of_interpolate():
    deck = _build(_beta_delta_csv()).deck
    vals = interpolate_point(deck, mach=0.5, alpha_deg=4.0)
    assert vals == pytest.approx(
        interpolate(deck, 0.5, 4.0, beta_deg=0.0, delta_deg=0.0)
    )
