"""ASTRA — STEP file parser (TDD-CAT-002).

Pure-Python STEP HEADER + PRODUCT extraction. Outputs a dict whose keys
align with ``IcdExtractionResultSchema`` so the existing
``_approve_pending_import`` flow can dump it straight onto a
``CatalogPart`` row via ``**scalar``.

pythonOCC enrichment (volume / mass) is opportunistic — a missing import
is logged as a warning and the pure-Python path is returned unchanged.

Validation reference: ``92196A196_18-8 Stainless Steel Socket Head Screw.STEP``
must yield manufacturer="McMaster-Carr", part_number="92196A196",
material_class="stainless_steel", part_class="fastener_screw",
part_subtype="socket_head_cap_screw", at HIGH confidence.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.services.cad.material_lexicon import match_material, density_for
from app.services.cad.part_type_lexicon import match_part_type
from app.services.cad.supplier_detection import (
    SupplierMatch,
    detect_supplier_from_filename,
)

logger = logging.getLogger(__name__)

PARSER_VERSION = "2.0.0"

# Read at most 32 MiB for HEADER + DATA scanning. Files larger than this
# fall through to a streamed read of the whole content; the parser's
# regexes still operate on the decoded blob.
_MAX_INLINE_BYTES = 32 * 1024 * 1024

# ─────────────────────────────────────────────────────────────────
#  Regex compilation
# ─────────────────────────────────────────────────────────────────

# FILE_NAME('name', 'timestamp', ('author'), ('org'),
#           'preprocessor_version', 'originating_system', 'authorization');
_FILE_NAME_RE = re.compile(
    r"FILE_NAME\s*\(\s*"
    r"'([^']*)'\s*,\s*"
    r"'([^']*)'\s*,\s*"
    r"\(([^)]*)\)\s*,\s*"
    r"\(([^)]*)\)\s*,\s*"
    r"'([^']*)'\s*,\s*"
    r"'([^']*)'\s*,\s*"
    r"'([^']*)'\s*\)\s*;",
    re.DOTALL | re.IGNORECASE,
)

_FILE_SCHEMA_RE = re.compile(
    r"FILE_SCHEMA\s*\(\s*\(\s*'([^']+)'", re.IGNORECASE
)

# PRODUCT entity has the form:
#   #N = PRODUCT('id', 'name', '...', (...));
# The first arg is the part identifier (often the MPN); the second is
# the descriptive product name that the lexicon needs to hit. Capture
# both so the part-type / material lookups have a real string to search.
_PRODUCT_RE = re.compile(
    r"#(\d+)\s*=\s*PRODUCT\s*\(\s*'([^']*)'\s*,\s*'([^']*)'",
    re.IGNORECASE,
)

_PRP_CATEGORY_RE = re.compile(
    r"PRODUCT_RELATED_PRODUCT_CATEGORY\s*\(\s*'([^']*)'", re.IGNORECASE
)

# Match scientific-notation floats inside CARTESIAN_POINT tuples.
# Common gotcha: STEP uses 1.000000000000000082E-05; a naive \d+\.?\d*
# misses negatives and scientific notation.
_NUM = r"[+-]?\d+\.?\d*(?:[eE][+-]?\d+)?"
_CART_POINT_RE = re.compile(
    rf"CARTESIAN_POINT\s*\(\s*'[^']*'\s*,\s*\(\s*({_NUM})\s*,\s*({_NUM})\s*,\s*({_NUM})\s*\)",
    re.IGNORECASE,
)

_LENGTH_UNIT_RE = re.compile(
    r"LENGTH_MEASURE_WITH_UNIT\s*\(\s*LENGTH_MEASURE\s*\(\s*(" + _NUM + r")\s*\)",
    re.IGNORECASE,
)

# Per-confidence float weights for averaging into extraction_confidence.
_CONFIDENCE_WEIGHT = {"high": 1.0, "medium": 0.6, "low": 0.3}


# ─────────────────────────────────────────────────────────────────
#  Result container
# ─────────────────────────────────────────────────────────────────

@dataclass
class ParsedStepResult:
    """Structured output of the STEP parser.

    ``extracted`` keys map onto IcdExtractionResultSchema field names so
    the catalog approve handler can dump them straight onto CatalogPart.
    """

    extracted: dict[str, Any] = field(default_factory=dict)
    confidence: dict[str, str] = field(default_factory=dict)
    detected_supplier_canonical: Optional[str] = None
    detected_supplier_aliases: list[str] = field(default_factory=list)
    parser_version: str = PARSER_VERSION
    warnings: list[str] = field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────

def _read_step_text(path: Path) -> str:
    """Decode the STEP file as ISO-8859-1. STEP is plain text."""
    size = path.stat().st_size
    if size <= _MAX_INLINE_BYTES:
        return path.read_bytes().decode("iso-8859-1", errors="replace")
    # Whole-file read for oversize STEP — still bounded by host RAM but
    # we don't try to be cleverer than that for v1.
    with path.open("rb") as fh:
        return fh.read().decode("iso-8859-1", errors="replace")


def _detect_units(text: str) -> tuple[Optional[str], float]:
    """Return (label, mm-scale-factor) for the first recognized unit.

    Common STEP encodings:
      0.0254  → INCH    → multiply raw values by 25.4 to get mm
      0.001   → MM      → multiply by 1.0
      1.0     → M       → multiply by 1000.0
      0.3048  → FOOT    → multiply by 304.8
    """
    for m in _LENGTH_UNIT_RE.finditer(text):
        try:
            f = float(m.group(1))
        except ValueError:
            continue
        if abs(f - 0.0254) < 1e-9:
            return "inch", 25.4
        if abs(f - 0.001) < 1e-12:
            return "mm", 1.0
        if abs(f - 1.0) < 1e-12:
            return "m", 1000.0
        if abs(f - 0.3048) < 1e-9:
            return "foot", 304.8

    # Fallback: look for explicit CONVERSION_BASED_UNIT ('INCH', ...)
    if re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'INCH'", text, re.IGNORECASE):
        return "inch", 25.4
    if re.search(r"CONVERSION_BASED_UNIT\s*\(\s*'MILLI", text, re.IGNORECASE):
        return "mm", 1.0
    return None, 1.0


def _scan_bbox(text: str, scale_to_mm: float) -> Optional[tuple[float, float, float]]:
    xs: list[float] = []
    ys: list[float] = []
    zs: list[float] = []
    for m in _CART_POINT_RE.finditer(text):
        try:
            xs.append(float(m.group(1)))
            ys.append(float(m.group(2)))
            zs.append(float(m.group(3)))
        except ValueError:
            continue
    if not xs:
        return None
    return (
        round((max(xs) - min(xs)) * scale_to_mm, 4),
        round((max(ys) - min(ys)) * scale_to_mm, 4),
        round((max(zs) - min(zs)) * scale_to_mm, 4),
    )


def _is_assembly(text: str) -> Optional[bool]:
    cats = [m.group(1).lower() for m in _PRP_CATEGORY_RE.finditer(text)]
    if not cats:
        return None
    if any("assembly" in c for c in cats):
        return True
    if any(c == "part" for c in cats):
        return False
    return None


def _try_pythonocc(
    file_path: Path, material_class: Optional[str],
) -> tuple[dict[str, Any], list[str]]:
    """Best-effort volume / mass enrichment.

    Returns (extras_dict, warnings). On any import or runtime failure,
    returns an empty dict + a warning — the caller proceeds with the
    pure-Python output.
    """
    extras: dict[str, Any] = {}
    warnings: list[str] = []
    try:
        from OCP.STEPControl import STEPControl_Reader  # type: ignore
        from OCP.IFSelect import IFSelect_RetDone       # type: ignore
        from OCP.BRepGProp import BRepGProp             # type: ignore
        from OCP.GProp import GProp_GProps              # type: ignore
    except Exception as exc:
        warnings.append(f"pythonOCC not available — volume/mass/preview skipped: {exc}")
        return extras, warnings

    try:
        reader = STEPControl_Reader()
        if reader.ReadFile(str(file_path)) != IFSelect_RetDone:
            warnings.append("pythonOCC: STEPControl_Reader could not read file")
            return extras, warnings
        reader.TransferRoots()
        shape = reader.OneShape()

        vprops = GProp_GProps()
        BRepGProp.VolumeProperties_s(shape, vprops)
        volume_mm3 = float(vprops.Mass())  # OCC: "Mass" of volume = volume
        extras["volume_mm3"] = round(volume_mm3, 4)

        if material_class:
            density = density_for(material_class)
            if density:
                extras["mass_kg"] = round((volume_mm3 * density) / 1000.0, 4)
    except Exception as exc:    # noqa: BLE001
        warnings.append(f"pythonOCC processing failed: {exc}")

    return extras, warnings


def _confidence_to_float(level: str) -> float:
    return _CONFIDENCE_WEIGHT.get(level, 0.3)


# ─────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────

def parse_step_file(
    file_path: Path | str,
    *,
    run_pythonocc: bool = True,
    original_filename: Optional[str] = None,
) -> ParsedStepResult:
    """Parse a STEP file and produce a ParsedStepResult.

    The output ``extracted`` dict keys align with
    ``IcdExtractionResultSchema``:
      - ``supplier``: ``{"name": ...}`` (set by the upload handler from
        ``detected_supplier_canonical`` or "Wardstone")
      - ``part_number``: detected MPN, or filename-derived stub
      - ``name``: PRODUCT entity name, or filename basename
      - ``part_class``: string value of a PartClass enum (e.g.
        ``"fastener_screw"`` or ``"mechanical_other"``)
      - ``part_subtype``, ``material_class``, ``material_name``,
        ``bbox_x_mm``, ..., ``cad_authoring_tool``, ``native_units``

    Raises ValueError when the file cannot be read or appears to be
    non-STEP — caller maps that to HTTP 422.
    """
    p = Path(file_path)
    result = ParsedStepResult()

    if not p.exists():
        raise ValueError(f"STEP file not found: {p}")

    try:
        text = _read_step_text(p)
    except OSError as exc:
        raise ValueError(f"could not read STEP file: {exc}") from exc

    # Cheap sanity check — STEP files start with "ISO-10303-21" and
    # contain a HEADER section. Pure-binary or empty files fail loudly.
    if "ISO-10303" not in text and "HEADER" not in text.upper():
        raise ValueError(
            "file does not look like a STEP file (no ISO-10303 marker)"
        )

    # Vendor detection runs against the user-supplied filename, not the
    # on-disk path — the upload handler stores the bytes under a UUID
    # to avoid collisions, which would otherwise hide the MPN regex.
    basename = (original_filename or p.name)
    result.extracted["original_filename"] = basename
    result.confidence["original_filename"] = "high"

    # ── HEADER → FILE_NAME ──
    fn_match = _FILE_NAME_RE.search(text)
    if fn_match:
        # arg 5 = preprocessor_version, arg 6 = originating_system
        preprocessor = (fn_match.group(5) or "").strip() or None
        originating = (fn_match.group(6) or "").strip() or None
        if originating:
            result.extracted["cad_authoring_tool"] = originating
            result.confidence["cad_authoring_tool"] = "high"
        if preprocessor:
            result.extracted["cad_translator"] = preprocessor
            result.confidence["cad_translator"] = "high"
    else:
        result.warnings.append("FILE_NAME header not found")

    # ── HEADER → FILE_SCHEMA ──
    fs_match = _FILE_SCHEMA_RE.search(text)
    if fs_match:
        # Take the leading identifier (e.g. AUTOMOTIVE_DESIGN) without
        # the version-and-bracket suffix.
        schema_full = fs_match.group(1).strip()
        schema = schema_full.split()[0] if schema_full else schema_full
        result.extracted["schema"] = schema
        result.confidence["schema"] = "high"

    # ── PRODUCT entity (first one) ──
    product_name = ""
    pm = _PRODUCT_RE.search(text)
    if pm:
        result.extracted["step_entity_id"] = f"#PRODUCT:{pm.group(1)}"
        # Group 2 is the part identifier (often the MPN); group 3 is the
        # descriptive name. Lexicon matching wants the descriptive name;
        # fall back to the identifier when the description is empty.
        product_id = pm.group(2).strip()
        product_desc = pm.group(3).strip()
        product_name = product_desc or product_id
        if product_id:
            result.extracted["product_id"] = product_id
        result.extracted["product_name"] = product_name
        result.confidence["step_entity_id"] = "high"
        result.confidence["product_name"] = "high"

    # ── Assembly vs single part ──
    is_asm = _is_assembly(text)
    if is_asm is not None:
        result.extracted["is_assembly"] = is_asm
        result.confidence["is_assembly"] = "high"

    # ── Native units ──
    unit_label, scale_to_mm = _detect_units(text)
    if unit_label:
        result.extracted["native_units"] = unit_label
        result.confidence["native_units"] = "high"
    else:
        result.extracted["native_units"] = "mm"
        result.confidence["native_units"] = "medium"
        result.warnings.append("could not detect native units; assuming mm")

    # ── Bounding box ──
    bbox = _scan_bbox(text, scale_to_mm)
    if bbox is not None:
        bx, by, bz = bbox
        result.extracted["bbox_x_mm"] = bx
        result.extracted["bbox_y_mm"] = by
        result.extracted["bbox_z_mm"] = bz
        conf = "high" if unit_label else "medium"
        for k in ("bbox_x_mm", "bbox_y_mm", "bbox_z_mm"):
            result.confidence[k] = conf

    # ── Vendor + MPN (filename → product_name fallback) ──
    sup_match: Optional[SupplierMatch] = detect_supplier_from_filename(basename)
    if sup_match is None and product_name:
        sup_match = detect_supplier_from_filename(product_name)
        if sup_match is not None:
            sup_match.confidence = "medium"

    if sup_match is not None:
        result.detected_supplier_canonical = sup_match.canonical
        result.detected_supplier_aliases = sup_match.aliases
        result.extracted["manufacturer"] = sup_match.canonical
        result.confidence["manufacturer"] = sup_match.confidence
        if sup_match.mpn:
            # IcdExtractionResultSchema requires `part_number` at top level.
            result.extracted["part_number"] = sup_match.mpn
            result.confidence["part_number"] = sup_match.confidence

    # If no MPN was extracted, default part_number to the filename stem
    # — IcdExtractionResultSchema requires it as a non-null string.
    if "part_number" not in result.extracted:
        stem = p.stem.strip() or "UNKNOWN"
        result.extracted["part_number"] = stem
        result.confidence["part_number"] = "low"

    # ── Material match (filename + product_name blob) ──
    blob = f"{basename} {product_name}"
    mat = match_material(blob)
    if mat is not None:
        result.extracted["material_class"] = mat.material_class
        result.extracted["material_name"] = mat.material_name
        result.confidence["material_class"] = mat.confidence
        result.confidence["material_name"] = mat.confidence

    # ── Part class / subtype lexicon match ──
    pt = match_part_type(blob)
    if pt is not None:
        result.extracted["part_class"] = pt.part_class
        result.confidence["part_class"] = pt.confidence
        if pt.part_subtype:
            result.extracted["part_subtype"] = pt.part_subtype
            result.confidence["part_subtype"] = pt.confidence
    else:
        # IcdExtractionResultSchema requires a non-null part_class.
        result.extracted["part_class"] = "mechanical_other"
        result.confidence["part_class"] = "low"

    # IcdExtractionResultSchema requires `name` as a non-null string.
    if product_name:
        result.extracted["name"] = product_name
    else:
        # Use the filename stem with extension stripped, spaces normalised.
        result.extracted["name"] = p.stem.replace("_", " ").strip() or basename

    # ── Optional pythonOCC enrichment (volume / mass) ──
    if run_pythonocc:
        extras, warns = _try_pythonocc(p, result.extracted.get("material_class"))
        for k, v in extras.items():
            result.extracted[k] = v
            result.confidence[k] = "high"
        result.warnings.extend(warns)

    return result


def average_confidence(confidence_map: dict[str, str]) -> float:
    """Return a 0.0-1.0 score weighted by the high/medium/low scale.

    Used to populate ``pending_catalog_imports.extraction_confidence``.
    Average over all field-level entries; empty map → 0.0.
    """
    if not confidence_map:
        return 0.0
    weights = [_confidence_to_float(v) for v in confidence_map.values()]
    return round(sum(weights) / len(weights), 3)
