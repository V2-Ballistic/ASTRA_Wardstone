"""ASTRA — Aero deck normalization service (spec §6 + §12).

Parses aero coefficient sources, merges them, grids them onto a full
breakpoint lattice and emits the versioned normalized artifact
``astra-aero-deck/1.0`` (the ``*.aero.json`` deck).

Concrete source format (spec §12 sanctions picking ONE)
-------------------------------------------------------
The upstream aero source format is undecided. This module implements
exactly one concrete format — a **long-form coefficient CSV** — and
keeps the deck schema aero-team-extensible through the ``extensions``
pass-through block. DATCOM ``.out`` files are declared-future: they are
rejected with "format not yet supported: datcom" (the router maps that
to 422).

CSV format (long form)
----------------------
One row per (mach, alpha[, beta][, delta]) point. The header row is
matched case- and punctuation-insensitively (a header is normalized by
lowercasing and stripping every non-alphanumeric character) against
alias sets:

    axis      aliases (pre-normalization)
    ─────     ───────────────────────────
    mach      mach, M
    alpha     alpha_deg, alpha, aoa_deg, aoa
    beta      beta_deg, beta                       (optional)
    delta     delta_deg, delta                     (optional, control)

    coeff     aliases
    ─────     ───────
    CA        ca, cx_axial, caxial
    CN        cn, cnormal
    CY        cy
    Cl        cl, cll, c_roll
    Cm        cm, cpm
    Cn        cn_yaw, cln, c_yaw                   (yaw moment)

Cl / CN / Cn disambiguation rule (DOCUMENTED, deliberate):
  * a bare ``cn`` / ``CN`` header is ALWAYS the normal-force
    coefficient CN. The yaw-moment coefficient Cn MUST be spelled
    ``cn_yaw``, ``cln`` or ``c_yaw`` — header matching is
    case-insensitive so there is no way to distinguish "CN" from "Cn"
    by capitalization, and aliasing is the tie-breaker.
  * a bare ``cl`` / ``Cl`` header is ALWAYS the roll-moment
    coefficient Cl (body axes carry no lift coefficient here).

Control-derivative columns: any header whose normalized form is
``<coeff-alias>delta`` (e.g. ``CN_delta``, ``Cm_delta``,
``cn_yaw_delta``) is stored as the derivative table
``<Canonical>_delta`` (``CN_delta``, ``Cm_delta``, ``Cn_delta`` …).

Metadata rides on comment lines ``# key: value``:
``Sref_m2``, ``Lref_m``, ``refPoint_m_B`` (3 floats, comma/space
separated), ``omlWpn``. Unknown ``# key: value`` keys are preserved
verbatim in the deck's ``extensions`` block (the aero-team
extensibility hook). Upload form fields override comment metadata.

Gridding rules
--------------
Breakpoints are the sorted unique values per axis (beta/delta default
to ``[0.0]`` when the column is absent). Tables are nested lists with
``axes: ["mach", "alpha_deg", "beta_deg", "delta_deg"]``.

  * full cartesian input            → exact
  * ragged input                    → 1-D linear interpolation onto the
                                      full grid where bracketing
                                      neighbours exist (alpha first,
                                      then mach, beta, delta; repeated
                                      to fixpoint), else AeroGridError
                                      listing the missing points
  * duplicate row, same value       → deduplicated silently
  * duplicate row, differing value  → AeroGridError /
                                      AeroMergeConflictError (>1e-9)
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

DECK_SCHEMA = "astra-aero-deck/1.0"
DECK_FRAME = "citadel-vehicle-body-frame"
DECK_AXES = ["mach", "alpha_deg", "beta_deg", "delta_deg"]
DECK_UNITS = "SI/deg"

#: numerical tolerance for "the same value" (merge conflicts / dups)
VALUE_TOLERANCE = 1e-9

# ── Errors ──────────────────────────────────────────────────────────


class AeroDeckError(ValueError):
    """Base for every aero-deck validation failure (router → 422)."""

    def __init__(self, message: str, *, points: Optional[List[dict]] = None):
        super().__init__(message)
        self.points = points or []

    def detail(self) -> dict:
        d: dict = {"message": str(self)}
        if self.points:
            d["points"] = self.points
        return d


class AeroFormatError(AeroDeckError):
    """Unsupported / unparseable source format (incl. DATCOM .out)."""


class AeroGridError(AeroDeckError):
    """Ragged grid that cannot be interpolated, or duplicate
    conflicting rows inside a single source."""


class AeroMergeConflictError(AeroDeckError):
    """Overlapping grid point with differing value across sources."""


class AeroEnvelopeError(AeroDeckError):
    """Preview query outside the deck's validity envelope."""


# ── Header alias tables ─────────────────────────────────────────────


def _norm(token: str) -> str:
    """Case/punctuation-insensitive normalization: lowercase + strip
    every non-alphanumeric character."""
    return re.sub(r"[^a-z0-9]", "", token.lower())


_AXIS_ALIASES: Dict[str, frozenset] = {
    "mach":      frozenset({"mach", "m"}),
    "alpha_deg": frozenset({"alphadeg", "alpha", "aoadeg", "aoa"}),
    "beta_deg":  frozenset({"betadeg", "beta"}),
    "delta_deg": frozenset({"deltadeg", "delta"}),
}

# Canonical coefficient table names per the deck schema. NOTE the
# disambiguation rule in the module docstring: bare "cn" → CN (normal
# force); the yaw moment Cn requires cn_yaw / cln / c_yaw.
_COEFF_ALIASES: Dict[str, frozenset] = {
    "CA": frozenset({"ca", "cxaxial", "caxial"}),
    "CN": frozenset({"cn", "cnormal"}),
    "CY": frozenset({"cy"}),
    "Cl": frozenset({"cl", "cll", "croll"}),
    "Cm": frozenset({"cm", "cpm"}),
    "Cn": frozenset({"cnyaw", "cln", "cyaw"}),
}

_METADATA_KEYS: Dict[str, str] = {
    "srefm2":     "Sref_m2",
    "lrefm":      "Lref_m",
    "refpointmb": "refPoint_m_B",
    "omlwpn":     "omlWpn",
}


def _resolve_header(raw: str) -> Optional[str]:
    """Map one raw CSV header to its canonical role.

    Returns an axis name (``mach``/``alpha_deg``/``beta_deg``/
    ``delta_deg``), a coefficient name (``CA``…``Cn``), a derivative
    table name (``CN_delta``…) or ``None`` for unrecognized columns.
    """
    n = _norm(raw)
    if not n:
        return None
    for axis, aliases in _AXIS_ALIASES.items():
        if n in aliases:
            return axis
    for coeff, aliases in _COEFF_ALIASES.items():
        if n in aliases:
            return coeff
    # control-derivative columns: <coeff-alias>delta
    if n.endswith("delta") and len(n) > 5:
        prefix = n[: -len("delta")]
        for coeff, aliases in _COEFF_ALIASES.items():
            if prefix in aliases:
                return f"{coeff}_delta"
    return None


# ── Parsed source ───────────────────────────────────────────────────


@dataclass
class ParsedSource:
    """One parsed coefficient CSV."""
    filename: str
    #: list of {"mach","alpha_deg","beta_deg","delta_deg","coeffs"}
    rows: List[dict] = field(default_factory=list)
    #: recognized # key: value metadata (canonical keys)
    metadata: Dict[str, Any] = field(default_factory=dict)
    #: unrecognized # key: value metadata — extensions pass-through
    extensions: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    #: canonical coefficient/derivative table names present
    columns: List[str] = field(default_factory=list)
    has_beta: bool = False
    has_delta: bool = False


def _parse_ref_point(value: str) -> List[float]:
    parts = [p for p in re.split(r"[,\s]+", value.strip()) if p]
    if len(parts) != 3:
        raise AeroFormatError(
            f"refPoint_m_B must be 3 floats, got {value!r}"
        )
    try:
        return [float(p) for p in parts]
    except ValueError as exc:
        raise AeroFormatError(
            f"refPoint_m_B must be 3 floats, got {value!r}"
        ) from exc


def _coerce_scalar(value: str) -> Any:
    try:
        return float(value)
    except ValueError:
        return value


def parse_source(filename: str, text: str) -> ParsedSource:
    """Parse one aero source file into a :class:`ParsedSource`.

    Raises :class:`AeroFormatError` for DATCOM ``.out`` files (the
    declared-future format) and any malformed CSV; raises
    :class:`AeroGridError` for duplicate conflicting rows.
    """
    if filename.lower().endswith(".out"):
        raise AeroFormatError("format not yet supported: datcom")
    if not text or not text.strip():
        raise AeroFormatError(f"{filename}: empty source file")

    src = ParsedSource(filename=filename)

    data_lines: List[str] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#"):
            body = line.lstrip("#").strip()
            if ":" in body:
                key, _, value = body.partition(":")
                canon = _METADATA_KEYS.get(_norm(key))
                value = value.strip()
                if canon == "refPoint_m_B":
                    src.metadata[canon] = _parse_ref_point(value)
                elif canon in ("Sref_m2", "Lref_m"):
                    try:
                        src.metadata[canon] = float(value)
                    except ValueError as exc:
                        raise AeroFormatError(
                            f"{filename}: metadata {canon} must be a "
                            f"float, got {value!r}"
                        ) from exc
                elif canon == "omlWpn":
                    src.metadata[canon] = value
                else:
                    # aero-team extensibility hook: unknown metadata
                    # keys are preserved verbatim in extensions.
                    src.extensions[key.strip()] = _coerce_scalar(value)
            continue
        data_lines.append(line)

    if not data_lines:
        raise AeroFormatError(f"{filename}: no header/data rows found")

    reader = csv.reader(io.StringIO("\n".join(data_lines)))
    rows = list(reader)
    header = rows[0]

    roles: List[Optional[str]] = []
    seen: Dict[str, str] = {}
    for raw in header:
        role = _resolve_header(raw)
        if role is not None and role in seen:
            raise AeroFormatError(
                f"{filename}: columns {seen[role]!r} and {raw!r} both "
                f"map to {role!r}"
            )
        if role is None:
            src.warnings.append(
                f"{filename}: unrecognized column ignored: {raw.strip()!r}"
            )
        else:
            seen[role] = raw
        roles.append(role)

    if "mach" not in seen or "alpha_deg" not in seen:
        raise AeroFormatError(
            f"{filename}: header must contain a mach column and an "
            f"alpha column (got {[h.strip() for h in header]!r})"
        )
    coeff_cols = [r for r in seen if r not in _AXIS_ALIASES]
    if not coeff_cols:
        raise AeroFormatError(
            f"{filename}: no coefficient columns recognized"
        )
    src.columns = sorted(coeff_cols)
    src.has_beta = "beta_deg" in seen
    src.has_delta = "delta_deg" in seen

    point_map: Dict[Tuple[float, float, float, float], dict] = {}
    conflicts: List[dict] = []
    for line_no, cells in enumerate(rows[1:], start=2):
        if not any(c.strip() for c in cells):
            continue
        if len(cells) < len([r for r in roles if r is not None]):
            # csv module already pads consistent rows; a short row is
            # a malformed line.
            if len(cells) != len(roles):
                raise AeroFormatError(
                    f"{filename}: row {line_no} has {len(cells)} cells, "
                    f"expected {len(roles)}"
                )
        values: Dict[str, float] = {}
        for role, cell in zip(roles, cells):
            if role is None:
                continue
            cell = cell.strip()
            if cell == "":
                continue  # missing coefficient at this point
            try:
                values[role] = float(cell)
            except ValueError as exc:
                raise AeroFormatError(
                    f"{filename}: row {line_no}: non-numeric value "
                    f"{cell!r} in column {seen.get(role, role)!r}"
                ) from exc
        if "mach" not in values or "alpha_deg" not in values:
            raise AeroFormatError(
                f"{filename}: row {line_no}: missing mach/alpha value"
            )
        key = (
            round(values["mach"], 9),
            round(values["alpha_deg"], 9),
            round(values.get("beta_deg", 0.0), 9),
            round(values.get("delta_deg", 0.0), 9),
        )
        coeffs = {k: v for k, v in values.items() if k not in _AXIS_ALIASES}
        existing = point_map.get(key)
        if existing is None:
            point_map[key] = coeffs
        else:
            for cname, cval in coeffs.items():
                if cname in existing:
                    if abs(existing[cname] - cval) > VALUE_TOLERANCE:
                        conflicts.append({
                            "mach": key[0], "alpha_deg": key[1],
                            "beta_deg": key[2], "delta_deg": key[3],
                            "coefficient": cname,
                            "values": [existing[cname], cval],
                        })
                else:
                    existing[cname] = cval

    if conflicts:
        raise AeroGridError(
            f"{filename}: duplicate conflicting rows "
            f"({len(conflicts)} conflicting point/coefficient pairs)",
            points=conflicts,
        )

    for key, coeffs in point_map.items():
        src.rows.append({
            "mach": key[0], "alpha_deg": key[1],
            "beta_deg": key[2], "delta_deg": key[3],
            "coeffs": coeffs,
        })
    if not src.rows:
        raise AeroFormatError(f"{filename}: no data rows found")
    return src


# ── Merge ───────────────────────────────────────────────────────────


def _merge_rows(
    sources: Sequence[ParsedSource],
) -> Dict[Tuple[float, float, float, float], Dict[str, float]]:
    """Union of all source rows. Overlapping grid point with a
    differing value (>1e-9) for the same coefficient →
    :class:`AeroMergeConflictError` listing the offending points."""
    merged: Dict[Tuple[float, float, float, float], Dict[str, float]] = {}
    origin: Dict[Tuple[float, float, float, float], Dict[str, str]] = {}
    conflicts: List[dict] = []
    for src in sources:
        for row in src.rows:
            key = (row["mach"], row["alpha_deg"],
                   row["beta_deg"], row["delta_deg"])
            slot = merged.setdefault(key, {})
            oslot = origin.setdefault(key, {})
            for cname, cval in row["coeffs"].items():
                if cname in slot:
                    if abs(slot[cname] - cval) > VALUE_TOLERANCE:
                        conflicts.append({
                            "mach": key[0], "alpha_deg": key[1],
                            "beta_deg": key[2], "delta_deg": key[3],
                            "coefficient": cname,
                            "values": [slot[cname], cval],
                            "sources": [oslot.get(cname, "?"),
                                        src.filename],
                        })
                else:
                    slot[cname] = cval
                    oslot[cname] = src.filename
    if conflicts:
        raise AeroMergeConflictError(
            f"merge conflict: {len(conflicts)} overlapping grid "
            f"point(s) with differing values",
            points=conflicts,
        )
    return merged


# ── Gridding ────────────────────────────────────────────────────────


def _interp_pass(
    table: list, breakpoints: List[List[float]], axis: int,
) -> int:
    """One linear-interpolation pass along ``axis``. Fills every
    missing cell that has bracketing filled neighbours along that
    axis. Returns the number of cells filled."""
    n = [len(b) for b in breakpoints]
    filled = 0

    def get(idx):  # idx: 4-tuple
        return table[idx[0]][idx[1]][idx[2]][idx[3]]

    def put(idx, v):
        table[idx[0]][idx[1]][idx[2]][idx[3]] = v

    import itertools
    for idx in itertools.product(*(range(c) for c in n)):
        if get(idx) is not None:
            continue
        lo = None
        for j in range(idx[axis] - 1, -1, -1):
            cand = list(idx); cand[axis] = j
            if get(tuple(cand)) is not None:
                lo = j
                break
        hi = None
        for j in range(idx[axis] + 1, n[axis]):
            cand = list(idx); cand[axis] = j
            if get(tuple(cand)) is not None:
                hi = j
                break
        if lo is None or hi is None:
            continue
        x = breakpoints[axis][idx[axis]]
        x0, x1 = breakpoints[axis][lo], breakpoints[axis][hi]
        i0 = list(idx); i0[axis] = lo
        i1 = list(idx); i1[axis] = hi
        y0, y1 = get(tuple(i0)), get(tuple(i1))
        put(idx, y0 + (y1 - y0) * (x - x0) / (x1 - x0))
        filled += 1
    return filled


def _grid_tables(
    merged: Dict[Tuple[float, float, float, float], Dict[str, float]],
) -> Tuple[Dict[str, List[float]], Dict[str, list], List[str]]:
    """Build the full breakpoint lattice and per-coefficient nested
    tables (axes order: mach × alpha × beta × delta). Ragged inputs are
    linearly interpolated where possible; unfillable cells →
    :class:`AeroGridError` listing the missing points."""
    machs = sorted({k[0] for k in merged})
    alphas = sorted({k[1] for k in merged})
    betas = sorted({k[2] for k in merged}) or [0.0]
    deltas = sorted({k[3] for k in merged}) or [0.0]
    bp_lists = [machs, alphas, betas, deltas]
    mi = {v: i for i, v in enumerate(machs)}
    ai = {v: i for i, v in enumerate(alphas)}
    bi = {v: i for i, v in enumerate(betas)}
    di = {v: i for i, v in enumerate(deltas)}

    coeff_names = sorted({c for cs in merged.values() for c in cs})
    warnings: List[str] = []
    tables: Dict[str, list] = {}

    for cname in coeff_names:
        table = [[[[None for _ in deltas] for _ in betas]
                  for _ in alphas] for _ in machs]
        for (m, a, b, d), coeffs in merged.items():
            if cname in coeffs:
                table[mi[m]][ai[a]][bi[b]][di[d]] = coeffs[cname]

        missing = _count_missing(table)
        if missing:
            # Ragged → interpolate onto the full grid, alpha axis
            # first, then mach, beta, delta; repeat to fixpoint.
            total_filled = 0
            progress = True
            while progress:
                progress = False
                for axis in (1, 0, 2, 3):
                    nfilled = _interp_pass(table, bp_lists, axis)
                    total_filled += nfilled
                    if nfilled:
                        progress = True
            still_missing = _missing_points(table, bp_lists)
            if still_missing:
                raise AeroGridError(
                    f"ragged grid for {cname}: "
                    f"{len(still_missing)} grid point(s) missing and "
                    f"not linearly interpolable",
                    points=[{
                        "coefficient": cname,
                        "mach": p[0], "alpha_deg": p[1],
                        "beta_deg": p[2], "delta_deg": p[3],
                    } for p in still_missing],
                )
            warnings.append(
                f"{cname}: {total_filled} missing grid point(s) "
                f"filled by linear interpolation"
            )
        tables[cname] = table

    breakpoints = {
        "mach": machs, "alpha_deg": alphas,
        "beta_deg": betas, "delta_deg": deltas,
    }
    return breakpoints, tables, warnings


def _count_missing(table: list) -> int:
    return sum(
        1
        for plane in table for line in plane for cells in line
        for v in cells if v is None
    )


def _missing_points(
    table: list, bp_lists: List[List[float]],
) -> List[Tuple[float, float, float, float]]:
    import itertools
    out = []
    for i, j, k, l in itertools.product(
        *(range(len(b)) for b in bp_lists)
    ):
        if table[i][j][k][l] is None:
            out.append((bp_lists[0][i], bp_lists[1][j],
                        bp_lists[2][k], bp_lists[3][l]))
    return out


# ── Derived quantities ──────────────────────────────────────────────


def _closest_index(values: List[float], target: float) -> int:
    return min(range(len(values)), key=lambda i: abs(values[i] - target))


def _alpha_slope_per_mach(
    table: list, machs: List[float], alphas: List[float],
    ib: int, idl: int,
) -> Tuple[List[Optional[float]], float]:
    """d(coeff)/d(alpha) per Mach, evaluated at the alpha breakpoint
    nearest 0 deg, on the beta/delta slice nearest 0. Central
    difference at interior points, one-sided at the ends."""
    ia = _closest_index(alphas, 0.0)
    slopes: List[Optional[float]] = []
    for im in range(len(machs)):
        col = [table[im][j][ib][idl] for j in range(len(alphas))]
        if len(alphas) < 2:
            slopes.append(None)
            continue
        if 0 < ia < len(alphas) - 1:
            num = col[ia + 1] - col[ia - 1]
            den = alphas[ia + 1] - alphas[ia - 1]
        elif ia == 0:
            num = col[1] - col[0]
            den = alphas[1] - alphas[0]
        else:
            num = col[ia] - col[ia - 1]
            den = alphas[ia] - alphas[ia - 1]
        slopes.append(num / den)
    return slopes, alphas[ia]


def _derived(breakpoints: dict, tables: dict) -> dict:
    """Stability derivatives CNalpha / Cmalpha per Mach (central
    differences over alpha) + a static-margin proxy where computable.
    Anything not computable is simply skipped."""
    machs, alphas = breakpoints["mach"], breakpoints["alpha_deg"]
    ib = _closest_index(breakpoints["beta_deg"], 0.0)
    idl = _closest_index(breakpoints["delta_deg"], 0.0)
    derived: dict = {}
    cn_slopes = cm_slopes = None
    if "CN" in tables and len(alphas) >= 2:
        cn_slopes, alpha_ref = _alpha_slope_per_mach(
            tables["CN"], machs, alphas, ib, idl)
        derived["CNalpha_per_deg"] = cn_slopes
        derived["alpha_ref_deg"] = alpha_ref
    if "Cm" in tables and len(alphas) >= 2:
        cm_slopes, alpha_ref = _alpha_slope_per_mach(
            tables["Cm"], machs, alphas, ib, idl)
        derived["Cmalpha_per_deg"] = cm_slopes
        derived["alpha_ref_deg"] = alpha_ref
    # staticMargin_proxy = -Cmalpha/CNalpha (in Lref units), per Mach.
    # Skipped entirely when either derivative is unavailable; None for
    # Machs where CNalpha is ~0 (not computable there).
    if cn_slopes is not None and cm_slopes is not None:
        proxy: List[Optional[float]] = []
        for cn_a, cm_a in zip(cn_slopes, cm_slopes):
            if cn_a is None or cm_a is None or abs(cn_a) < 1e-12:
                proxy.append(None)
            else:
                proxy.append(-cm_a / cn_a)
        if any(p is not None for p in proxy):
            derived["staticMargin_proxy"] = proxy
    return derived


# ── Deck build / merge ──────────────────────────────────────────────


@dataclass
class BuiltDeck:
    deck: dict
    warnings: List[str]
    defaulted_fields: List[str]


def merge_decks(
    sources: Sequence[ParsedSource],
    *,
    sref_m2: Optional[float] = None,
    lref_m: Optional[float] = None,
    ref_point_m_b: Optional[List[float]] = None,
    oml_wpn: Optional[str] = None,
    wpn: Optional[str] = None,
    author: Optional[str] = None,
    ingest_utc: Optional[str] = None,
    source_files: Optional[List[dict]] = None,
) -> BuiltDeck:
    """Merge 1..N parsed sources into ONE normalized deck.

    Breakpoints are unioned; an overlapping grid point with a
    differing value (>1e-9) raises :class:`AeroMergeConflictError`
    listing the offending points; tables are re-gridded onto the full
    merged lattice.

    Explicit keyword metadata (the upload form fields) WINS over
    ``# key: value`` comment metadata; comment metadata is first-wins
    across sources. ``Sref_m2``/``Lref_m`` are mandatory —
    :class:`AeroDeckError` when missing after both layers.
    """
    if not sources:
        raise AeroFormatError("no source files supplied")

    warnings: List[str] = []
    defaulted: List[str] = []
    meta: Dict[str, Any] = {}
    extensions: Dict[str, Any] = {}
    for src in sources:
        warnings.extend(src.warnings)
        for k, v in src.metadata.items():
            if k not in meta:
                meta[k] = v
            elif meta[k] != v:
                warnings.append(
                    f"{src.filename}: metadata {k} ({v!r}) differs from "
                    f"earlier source value ({meta[k]!r}); first wins"
                )
        for k, v in src.extensions.items():
            extensions.setdefault(k, v)

    sref = sref_m2 if sref_m2 is not None else meta.get("Sref_m2")
    lref = lref_m if lref_m is not None else meta.get("Lref_m")
    if sref is None or lref is None:
        missing = [n for n, v in
                   (("Sref_m2", sref), ("Lref_m", lref)) if v is None]
        raise AeroDeckError(
            "mandatory reference metadata missing: " + ", ".join(missing)
            + " (supply as form fields or '# key: value' comments)"
        )
    ref_point = (
        ref_point_m_b if ref_point_m_b is not None
        else meta.get("refPoint_m_B")
    )
    if ref_point is None:
        ref_point = [0.0, 0.0, 0.0]
        defaulted.append("refPoint_m_B")
    oml = oml_wpn if oml_wpn is not None else meta.get("omlWpn")

    merged = _merge_rows(sources)
    breakpoints, tables, grid_warnings = _grid_tables(merged)
    warnings.extend(grid_warnings)

    deck: dict = {
        "schema": DECK_SCHEMA,
        "omlWpn": oml,
        "Sref_m2": float(sref),
        "Lref_m": float(lref),
        "refPoint_m_B": [float(x) for x in ref_point],
        "frame": DECK_FRAME,
        "axes": list(DECK_AXES),
        "breakpoints": breakpoints,
        "tables": tables,
        "derived": _derived(breakpoints, tables),
        "validityEnvelope": {
            "machRange": [breakpoints["mach"][0],
                          breakpoints["mach"][-1]],
            "alphaRange_deg": [breakpoints["alpha_deg"][0],
                               breakpoints["alpha_deg"][-1]],
            "betaRange_deg": [breakpoints["beta_deg"][0],
                              breakpoints["beta_deg"][-1]],
        },
        "units": DECK_UNITS,
        "provenance": {
            "sourceFiles": source_files or [],
            "ingestUtc": ingest_utc,
            "author": author,
            "wpn": wpn,
        },
        # aero-team extensibility hook — preserved pass-through.
        "extensions": extensions,
    }
    return BuiltDeck(deck=deck, warnings=warnings,
                     defaulted_fields=defaulted)


# alias: a deck built from a single source is just a 1-way merge
build_deck = merge_decks


# ── Canonical hash ──────────────────────────────────────────────────


def canonical_json(deck: dict) -> str:
    """Canonical JSON: sorted keys, compact separators."""
    return json.dumps(deck, sort_keys=True, separators=(",", ":"))


def deck_sha256(deck: dict) -> str:
    return hashlib.sha256(canonical_json(deck).encode("utf-8")).hexdigest()


# ── Preview interpolation ───────────────────────────────────────────


def interpolate_point(deck: dict, mach: float, alpha_deg: float) -> dict:
    """Bilinear interpolation of every table at (mach, alpha) on the
    beta/delta slice nearest 0. Outside the validity envelope →
    :class:`AeroEnvelopeError`."""
    bp = deck["breakpoints"]
    machs, alphas = bp["mach"], bp["alpha_deg"]
    if not (machs[0] - 1e-12 <= mach <= machs[-1] + 1e-12):
        raise AeroEnvelopeError(
            f"mach {mach} outside validity envelope "
            f"[{machs[0]}, {machs[-1]}]"
        )
    if not (alphas[0] - 1e-12 <= alpha_deg <= alphas[-1] + 1e-12):
        raise AeroEnvelopeError(
            f"alpha {alpha_deg} deg outside validity envelope "
            f"[{alphas[0]}, {alphas[-1]}]"
        )
    ib = _closest_index(bp["beta_deg"], 0.0)
    idl = _closest_index(bp["delta_deg"], 0.0)

    def _bracket(values: List[float], x: float) -> Tuple[int, int, float]:
        if len(values) == 1:
            return 0, 0, 0.0
        for i in range(len(values) - 1):
            if values[i] <= x <= values[i + 1]:
                t = ((x - values[i]) / (values[i + 1] - values[i])
                     if values[i + 1] != values[i] else 0.0)
                return i, i + 1, t
        # clamped by the envelope check above; numeric edge:
        return (len(values) - 2, len(values) - 1, 1.0)

    im0, im1, tm = _bracket(machs, mach)
    ia0, ia1, ta = _bracket(alphas, alpha_deg)

    out: Dict[str, float] = {}
    for cname, table in deck["tables"].items():
        v00 = table[im0][ia0][ib][idl]
        v01 = table[im0][ia1][ib][idl]
        v10 = table[im1][ia0][ib][idl]
        v11 = table[im1][ia1][ib][idl]
        v0 = v00 + (v01 - v00) * ta
        v1 = v10 + (v11 - v10) * ta
        out[cname] = v0 + (v1 - v0) * tm
    return out
