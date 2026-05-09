"""TDD-CAT-002 — STEP parser tests.

Validation reference: ``92196A196_18-8 Stainless Steel Socket Head Screw.STEP``.
The fixture is placed by the user at
``backend/tests/fixtures/cad/92196A196_18-8_Stainless_Steel_Socket_Head_Screw.STEP``
before this test runs. When the fixture is missing the McMaster test
skips with a clear message — the suite stays green.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from app.services.cad.step_parser import (
    PARSER_VERSION,
    ParsedStepResult,
    average_confidence,
    parse_step_file,
)


# ─────────────────────────────────────────────────────────────────
#  Synthetic STEP fixtures (no external file required)
# ─────────────────────────────────────────────────────────────────

INHOUSE_STEP = textwrap.dedent("""\
ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('STEP AP214'),'1');
FILE_NAME(
    'WS_AV_P0042_A_Custom_Bracket',
    '2026-05-01T12:00:00',
    ('Mason'),
    ('Wardstone'),
    'SwSTEP 2.0',
    'SolidWorks 2025',
    '');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1 = APPLICATION_PROTOCOL_DEFINITION('international standard','automotive_design',2000,#2);
#10 = PRODUCT('WS-AV-P0042-A','Custom mounting bracket','',(#11));
#20 = PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(#10));
#30 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.001),#31);
#100 = CARTESIAN_POINT('NONE',(0.0,0.0,0.0));
#101 = CARTESIAN_POINT('NONE',(20.0,40.0,5.0));
ENDSEC;
END-ISO-10303-21;
""")


MM_HEX_NUT_STEP = textwrap.dedent("""\
ISO-10303-21;
HEADER;
FILE_NAME('M5_hex_nut','2026','','','SwSTEP','SolidWorks','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));
ENDSEC;
DATA;
#10 = PRODUCT('M5_hex_nut','M5 hex nut',$,(#11));
#20 = PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(#10));
#30 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.001),#31);
#100 = CARTESIAN_POINT('NONE',(0,0,0));
#101 = CARTESIAN_POINT('NONE',(8,8,4));
ENDSEC;
END-ISO-10303-21;
""")


# Synthetic *second* McMaster file — used for the "second upload reuses
# existing supplier" test. Different MPN prefix than the validation fixture.
SECOND_MCMASTER_STEP = textwrap.dedent("""\
ISO-10303-21;
HEADER;
FILE_NAME(
    '90115A123_316_Stainless_Steel_Hex_Bolt',
    '2026-05-02T12:00:00',
    ('Mason'),
    ('Wardstone'),
    'SwSTEP 2.0',
    'SolidWorks 2025',
    '');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN'));
ENDSEC;
DATA;
#10 = PRODUCT('90115A123','316 Stainless Steel Hex Bolt M6 x 20mm','',(#11));
#20 = PRODUCT_RELATED_PRODUCT_CATEGORY('part',$,(#10));
#30 = LENGTH_MEASURE_WITH_UNIT(LENGTH_MEASURE(0.0254),#31);
#100 = CARTESIAN_POINT('NONE',(0,0,0));
#101 = CARTESIAN_POINT('NONE',(0.236,0.236,0.787));
ENDSEC;
END-ISO-10303-21;
""")


@pytest.fixture()
def inhouse_step_path(tmp_path: Path) -> Path:
    p = tmp_path / "WS_AV_P0042_A_Custom_Bracket.STEP"
    p.write_text(INHOUSE_STEP, encoding="iso-8859-1")
    return p


@pytest.fixture()
def mm_hex_nut_path(tmp_path: Path) -> Path:
    p = tmp_path / "M5_hex_nut.STEP"
    p.write_text(MM_HEX_NUT_STEP, encoding="iso-8859-1")
    return p


@pytest.fixture()
def mcmaster_real_fixture_path() -> Path | None:
    """Real McMaster fixture placed by the user. None when missing."""
    candidate = (
        Path(__file__).parent
        / "fixtures"
        / "cad"
        / "92196A196_18-8_Stainless_Steel_Socket_Head_Screw.STEP"
    )
    return candidate if candidate.exists() else None


# ─────────────────────────────────────────────────────────────────
#  Validation case (real fixture)
# ─────────────────────────────────────────────────────────────────

def test_mcmaster_socket_head_screw(mcmaster_real_fixture_path):
    """Validation per CAT-002 §Validation fixture."""
    if mcmaster_real_fixture_path is None:
        pytest.skip(
            "McMaster fixture not present at "
            "backend/tests/fixtures/cad/92196A196_18-8_Stainless_Steel_Socket_Head_Screw.STEP — "
            "place the file before running this test."
        )

    r = parse_step_file(mcmaster_real_fixture_path, run_pythonocc=False)

    assert r.parser_version == PARSER_VERSION
    assert r.detected_supplier_canonical == "McMaster-Carr"
    assert "McMaster" in r.detected_supplier_aliases
    assert "MCMASTER" in r.detected_supplier_aliases

    ex = r.extracted
    assert ex["manufacturer"] == "McMaster-Carr"
    assert ex["part_number"] == "92196A196"
    assert ex["material_class"] == "stainless_steel"
    assert "Stainless" in ex["material_name"]
    assert ex["part_class"] == "fastener_screw"
    assert ex["part_subtype"] == "socket_head_cap_screw"

    # Bounding box populated; inch units → mm conversion (×25.4) yields
    # >2 mm on every axis for a typical M3 cap screw.
    for k in ("bbox_x_mm", "bbox_y_mm", "bbox_z_mm"):
        assert ex.get(k) is not None
        assert float(ex[k]) > 0

    assert ex["native_units"] == "inch"
    assert ex["cad_authoring_tool"]
    assert ex["schema"].startswith("AUTOMOTIVE_DESIGN")
    assert ex["is_assembly"] is False

    # The IcdExtractionResultSchema-required fields are present:
    assert ex["name"]
    assert ex["part_number"]
    assert ex["part_class"]


# ─────────────────────────────────────────────────────────────────
#  In-house (no vendor pattern)
# ─────────────────────────────────────────────────────────────────

def test_inhouse_no_vendor_pattern(inhouse_step_path):
    r = parse_step_file(inhouse_step_path, run_pythonocc=False)
    assert r.detected_supplier_canonical is None
    assert r.detected_supplier_aliases == []
    assert "manufacturer" not in r.extracted

    # Bracket lexicon hit
    assert r.extracted["part_class"] == "bracket"
    assert r.extracted["native_units"] == "mm"
    # Required-by-schema fields still present
    assert r.extracted["part_number"]
    assert r.extracted["name"]


# ─────────────────────────────────────────────────────────────────
#  pythonOCC fallback
# ─────────────────────────────────────────────────────────────────

def test_pythonocc_unavailable_fallback(monkeypatch, inhouse_step_path):
    """When pythonOCC import fails, parser still returns pure-Python
    fields and emits a warning."""

    # Patch the helper directly so we don't have to fake the OCP import.
    from app.services.cad import step_parser as sp_mod

    def _fake_try_pythonocc(file_path, material_class):
        return {}, ["pythonOCC not available — volume/mass/preview skipped: stub"]

    monkeypatch.setattr(sp_mod, "_try_pythonocc", _fake_try_pythonocc)

    r = parse_step_file(inhouse_step_path, run_pythonocc=True)
    assert r.extracted["part_class"] == "bracket"
    assert any("pythonOCC" in w for w in r.warnings)
    # No volume/mass populated when OCC failed
    assert "volume_mm3" not in r.extracted


# ─────────────────────────────────────────────────────────────────
#  MM units
# ─────────────────────────────────────────────────────────────────

def test_mm_units(mm_hex_nut_path):
    r = parse_step_file(mm_hex_nut_path, run_pythonocc=False)
    assert r.extracted["native_units"] == "mm"
    # 8 mm × 1.0 → 8 mm
    assert float(r.extracted["bbox_x_mm"]) == pytest.approx(8.0, rel=1e-3)
    assert r.extracted["part_class"] == "nut"
    assert r.extracted["part_subtype"] == "hex_nut"


# ─────────────────────────────────────────────────────────────────
#  Corrupted / missing files
# ─────────────────────────────────────────────────────────────────

def test_corrupted_step_returns_useful_error(tmp_path: Path):
    p = tmp_path / "garbage.step"
    p.write_text("this is not a STEP file", encoding="utf-8")
    with pytest.raises(ValueError) as exc_info:
        parse_step_file(p, run_pythonocc=False)
    assert "STEP" in str(exc_info.value)


def test_missing_step_raises(tmp_path: Path):
    with pytest.raises(ValueError) as exc_info:
        parse_step_file(tmp_path / "nope.step", run_pythonocc=False)
    assert "not found" in str(exc_info.value)


# ─────────────────────────────────────────────────────────────────
#  Confidence averaging
# ─────────────────────────────────────────────────────────────────

def test_average_confidence_weighting():
    assert average_confidence({}) == 0.0
    # All-high → 1.0
    assert average_confidence({"a": "high", "b": "high"}) == 1.0
    # high + low → (1.0 + 0.3) / 2 = 0.65
    assert average_confidence({"a": "high", "b": "low"}) == pytest.approx(0.65, rel=1e-3)
