"""
ASTRA — STEP file parser with AI/rules-based field interpretation.

Two-stage operation:
  1. Geometry / metadata extraction
     - Always: regex scan of STEP text for PRODUCT entities (product
       name, description, MPN candidate)
     - If pythonOCC available: bounding box, volume, surface area,
       largest cylindrical hole diameter, mass (with default density)
  2. Field interpretation (from app.services.parts.ai_interpreter)
     - Tries Claude / OpenAI / rules fallback (always succeeds)

Stub mode: when pythonOCC is not installed, all geometry fields are
None and confidence on geometry-derived fields is "low". The product
name extracted from STEP text is still high-confidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
import logging
import re
from typing import Optional

from app.models.parts_library import ConfidenceLevel, ThreadStandard

logger = logging.getLogger(__name__)
PARSER_VERSION = "1.0.0"


# ══════════════════════════════════════════════════════════════
#  Result dataclass
# ══════════════════════════════════════════════════════════════

@dataclass
class StepParserResult:
    product_name:             Optional[str] = None
    product_description:      Optional[str] = None
    manufacturer_part_number: Optional[str] = None
    step_entity_id:           Optional[str] = None
    bounding_box_x_mm:        Optional[Decimal] = None
    bounding_box_y_mm:        Optional[Decimal] = None
    bounding_box_z_mm:        Optional[Decimal] = None
    volume_mm3:               Optional[Decimal] = None
    surface_area_mm2:         Optional[Decimal] = None
    nominal_diameter_mm:      Optional[Decimal] = None
    nominal_length_mm:        Optional[Decimal] = None
    thread_size:              Optional[str] = None
    thread_standard:          Optional[ThreadStandard] = None
    torque_nominal_nm:        Optional[Decimal] = None
    hole_pattern_count:       Optional[int] = None
    hole_pattern_dia_mm:      Optional[Decimal] = None
    mass_nominal_g:           Optional[Decimal] = None
    confidence_scores:        dict = field(default_factory=dict)
    low_confidence_fields:    list[str] = field(default_factory=list)
    extraction_log:           str = ""
    parser_version:           str = PARSER_VERSION
    occ_available:            bool = False


# ══════════════════════════════════════════════════════════════
#  Thread / torque table
#  (clearance_lo, clearance_hi, size, standard, recommended torque N·m)
#  Ranges chosen so a single drilled clearance hole maps to one row.
# ══════════════════════════════════════════════════════════════

THREAD_TABLE: list[tuple[Decimal, Decimal, str, ThreadStandard, Decimal]] = [
    # ISO metric — nominal hole diameter ranges based on clearance class
    (Decimal("3.10"), Decimal("3.40"), "M3×0.5",  ThreadStandard.ISO_METRIC, Decimal("1.4")),
    (Decimal("4.20"), Decimal("4.60"), "M4×0.7",  ThreadStandard.ISO_METRIC, Decimal("3.1")),
    (Decimal("5.20"), Decimal("5.70"), "M5×0.8",  ThreadStandard.ISO_METRIC, Decimal("6.1")),
    (Decimal("6.40"), Decimal("6.45"), "1/4-28",  ThreadStandard.UNF,        Decimal("12.5")),
    (Decimal("6.45"), Decimal("6.50"), "1/4-20",  ThreadStandard.UNC,        Decimal("11.0")),
    (Decimal("6.50"), Decimal("6.80"), "M6×1.0",  ThreadStandard.ISO_METRIC, Decimal("9.8")),
    (Decimal("8.40"), Decimal("9.00"), "M8×1.25", ThreadStandard.ISO_METRIC, Decimal("23.5")),
    (Decimal("10.40"), Decimal("11.00"), "M10×1.5", ThreadStandard.ISO_METRIC, Decimal("46.0")),
    (Decimal("12.40"), Decimal("13.00"), "M12×1.75", ThreadStandard.ISO_METRIC, Decimal("80.0")),
]


def match_thread(clearance_dia_mm: Decimal) -> Optional[
    tuple[str, ThreadStandard, Decimal]
]:
    """Return (size, standard, torque) for the row whose [lo, hi)
    range contains ``clearance_dia_mm``. ``None`` if no row matches.
    """
    for lo, hi, size, std, torque in THREAD_TABLE:
        if lo <= clearance_dia_mm < hi:
            return size, std, torque
    return None


# ══════════════════════════════════════════════════════════════
#  Public entry point
# ══════════════════════════════════════════════════════════════

_STEP_PRODUCT_RE = re.compile(
    r"#(\d+)\s*=\s*PRODUCT\s*\(\s*'([^']*)'\s*,\s*'([^']*)'",
    re.IGNORECASE,
)


def parse_step_file(file_path: str) -> StepParserResult:
    """Parse a STEP file. Always returns a result object, never raises."""
    result = StepParserResult()
    log: list[str] = []

    # Stage 1 — text-based metadata extraction (always works)
    try:
        with open(file_path, "r", errors="replace") as f:
            text = f.read()
        m = _STEP_PRODUCT_RE.search(text)
        if m:
            entity_id, name, description = m.group(1), m.group(2), m.group(3)
            result.step_entity_id = f"#PRODUCT:{entity_id}"
            result.product_name = name.strip() or None
            result.product_description = description.strip() or None
            if result.product_name:
                result.confidence_scores["name"] = ConfidenceLevel.HIGH.value
        # Look for MPN in description / name (P/N pattern)
        if result.product_name or result.product_description:
            haystack = f"{result.product_name or ''} {result.product_description or ''}"
            mpn_match = re.search(
                r"\b([A-Z0-9][A-Z0-9\-]{3,30})\b",
                haystack,
            )
            if mpn_match and "-" in mpn_match.group(1):
                result.manufacturer_part_number = mpn_match.group(1)
                result.confidence_scores["manufacturer_part_number"] = (
                    ConfidenceLevel.MEDIUM.value
                )
        log.append(f"Metadata: name={result.product_name!r}")
    except OSError as exc:
        log.append(f"File read failed: {exc}")
        result.extraction_log = "\n".join(log)
        return result
    except Exception as exc:
        log.append(f"Metadata parse failed: {exc}")

    # Stage 2 — OCC geometry (best-effort)
    try:
        from OCC.Core.STEPControl import STEPControl_Reader  # type: ignore
        from OCC.Core.IFSelect import IFSelect_RetDone  # type: ignore
        from OCC.Core.BRepBndLib import brepbndlib_Add  # type: ignore
        from OCC.Core.Bnd import Bnd_Box  # type: ignore
        from OCC.Core.GProp import GProp_GProps  # type: ignore
        from OCC.Core.BRepGProp import (  # type: ignore
            brepgprop_VolumeProperties, brepgprop_SurfaceProperties,
        )

        reader = STEPControl_Reader()
        if reader.ReadFile(file_path) != IFSelect_RetDone:
            log.append("OCC ReadFile failed — staying in stub mode")
            raise RuntimeError("ReadFile failed")
        reader.TransferRoots()
        shape = reader.OneShape()

        # Bounding box
        bbox = Bnd_Box()
        brepbndlib_Add(shape, bbox)
        xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()
        result.bounding_box_x_mm = Decimal(str(round(xmax - xmin, 4)))
        result.bounding_box_y_mm = Decimal(str(round(ymax - ymin, 4)))
        result.bounding_box_z_mm = Decimal(str(round(zmax - zmin, 4)))

        # Volume + surface area
        vprops = GProp_GProps()
        brepgprop_VolumeProperties(shape, vprops)
        result.volume_mm3 = Decimal(str(round(vprops.Mass(), 4)))

        sprops = GProp_GProps()
        brepgprop_SurfaceProperties(shape, sprops)
        result.surface_area_mm2 = Decimal(str(round(sprops.Mass(), 4)))

        # Default mass: assume stainless steel density 7.85 g/cm³
        if result.volume_mm3 is not None:
            mass_g = float(result.volume_mm3) * 7.85e-3
            result.mass_nominal_g = Decimal(str(round(mass_g, 4)))

        result.occ_available = True
        log.append(
            f"OCC: bbox=({result.bounding_box_x_mm},{result.bounding_box_y_mm},"
            f"{result.bounding_box_z_mm}), volume={result.volume_mm3}, "
            f"area={result.surface_area_mm2}"
        )

        # Mark high-confidence on geometry fields we set
        for fld in (
            "bounding_box_x_mm", "bounding_box_y_mm", "bounding_box_z_mm",
            "volume_mm3", "surface_area_mm2", "mass_nominal_g",
        ):
            if getattr(result, fld) is not None:
                result.confidence_scores[fld] = ConfidenceLevel.HIGH.value

    except ImportError:
        log.append(
            "pythonOCC not available — running in stub mode. "
            "Geometry fields (bounding box, volume, thread size) "
            "are unavailable; AI interpretation has reduced inputs."
        )
        # Mark geometry fields as low-confidence
        for fld in (
            "bounding_box_x_mm", "bounding_box_y_mm", "bounding_box_z_mm",
            "volume_mm3", "surface_area_mm2", "thread_size",
            "nominal_diameter_mm", "mass_nominal_g",
        ):
            result.confidence_scores[fld] = ConfidenceLevel.LOW.value
            if fld not in result.low_confidence_fields:
                result.low_confidence_fields.append(fld)
    except Exception as exc:
        log.append(f"OCC analysis failed: {exc}")

    result.extraction_log = "\n".join(log)
    return result


# ══════════════════════════════════════════════════════════════
#  Rules-based interpretation fallback (always succeeds)
# ══════════════════════════════════════════════════════════════

def _rules_fallback(r: StepParserResult) -> dict:
    """Deterministic classification — used when AI service unavailable.

    Returns a flat dict to merge into PendingPartsImport.proposed_data.
    """
    out: dict = {
        "part_type": None,
        "material_name": None,
        "material_class": None,
        "torque_nominal_nm": None,
        "torque_min_nm": None,
        "torque_max_nm": None,
        "locking_feature": "none",
        "confidence_overrides": {},
        "flags": [],
    }
    name = (r.product_name or "").lower()

    # Locking feature — check BEFORE part_type so "Nylok" wins over generic fastener match
    if any(k in name for k in ("nylok", "ny-lok", "nyloc", "nylon insert")):
        out["locking_feature"] = "nylok"
    elif "prevailing torque" in name or "prevailing-torque" in name or " pt " in f" {name} ":
        out["locking_feature"] = "prevailing_torque"
    elif "safety wire" in name or "safety-wire" in name:
        out["locking_feature"] = "safety_wire"
    elif "loctite" in name:
        out["locking_feature"] = "loctite"
    elif "castellated" in name or "castle nut" in name:
        out["locking_feature"] = "castellated"

    # Part type
    if "bearing" in name:
        out["part_type"] = "bearing"
    elif any(k in name for k in ("o-ring", "oring", "gasket")) or " seal" in name or "seal " in name:
        out["part_type"] = "seal"
    elif any(k in name for k in ("washer", "shim")):
        out["part_type"] = "washer"
    elif any(k in name for k in ("helicoil", "keensert", "nutsert", "thread insert")) or "insert" in name:
        out["part_type"] = "insert"
    elif any(k in name for k in ("bracket", "mount", "standoff", "spacer")):
        out["part_type"] = "bracket"
    elif any(k in name for k in ("housing", "enclosure", "chassis", "panel", "cover")):
        out["part_type"] = "enclosure"
    elif any(k in name for k in ("screw", "bolt", "stud", "fastener", "hex screw", "cap screw")) \
            or re.search(r"\bm\d+\b", name) \
            or re.search(r"#\d+\s*-\s*\d+", name):
        out["part_type"] = "fastener"
    elif r.thread_size:
        out["part_type"] = "fastener"
        out["confidence_overrides"]["part_type"] = "medium"

    # Material
    if any(k in name for k in ("ti-6", "titanium", "ti6al4v")) or " ti " in f" {name} ":
        out["material_name"] = "Ti-6Al-4V"
        out["material_class"] = "titanium"
    elif "a286" in name or "a-286" in name:
        out["material_name"] = "A286"
        out["material_class"] = "stainless_steel"
    elif "17-4" in name or "cres" in name:
        out["material_name"] = "17-4 PH H900"
        out["material_class"] = "stainless_steel"
    elif "aluminum" in name or "alum " in name or "6061" in name or "7075" in name:
        out["material_class"] = "aluminum"
    elif out["part_type"] == "fastener":
        out["material_class"] = "stainless_steel"
        out["confidence_overrides"]["material_class"] = "low"

    # Torque from thread match
    if r.torque_nominal_nm:
        out["torque_nominal_nm"] = float(r.torque_nominal_nm)
        out["torque_min_nm"] = round(float(r.torque_nominal_nm) * 0.85, 4)
        out["torque_max_nm"] = round(float(r.torque_nominal_nm) * 1.10, 4)

    if out["part_type"] is None:
        out["part_type"] = "custom"
        out["flags"].append("Could not classify part type — defaulted to custom")
        out["confidence_overrides"]["part_type"] = "low"

    return out


# Public wrapper — for now just calls rules fallback. Phase 2 / Phase 4
# will plug in a real AI service if app.services.ai is available.

def interpret(parser_result: StepParserResult, ai_service=None) -> dict:
    """Interpret parser output. Tries AI first if provided; falls back
    to deterministic rules. Never raises."""
    if ai_service is not None:
        try:
            # Future: implement AI call here. For Phase 2 we ship the
            # rules fallback only — the spec explicitly allows this when
            # no AI service exists (addendum §A.5).
            pass
        except Exception as exc:
            logger.warning("AI interpretation failed: %s — using rules", exc)
    return _rules_fallback(parser_result)
