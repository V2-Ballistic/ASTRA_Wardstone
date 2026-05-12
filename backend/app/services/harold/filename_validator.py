"""Filetype-agnostic filename → WPN validator.

Lock #8 of HAROLD-INT-002: the validator seam is built generic so
future filetypes (PDF datasheets, drawings) plug in without refactor.
STEP files are the first caller (Phase 3 of this prompt); the parsing
logic here works on the filename only and is unaware of the file body.

Regex matches HAROLD V2's canonical cad_part format:
    WS-<XX>-P<NNNNNN>-<REV>
    XX  ∈ 21 system codes (validation deferred to HAROLD's validate)
    NN  6 digits, 1..999999
    REV ASME 20-letter set ABCDEFGHJKLMNPRTUVWY

(``[A-Z]{2}`` here is loose — we let HAROLD reject unknown system
codes via the validate call. The REV bracket class is exact so we
catch ASME-forbidden letters early in the UX. Phase 4's frontend
uses an identical regex per AD-12.)
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional


# Anchored at start; runs to end via ``\Z`` so trailing chars don't
# slip through. The 20-letter ASME REV set excludes I/O/Q/S/X/Z.
_WPN_TOKEN = r"WS-[A-Z]{2}-P[0-9]{6}-[ABCDEFGHJKLMNPRTUVWY]"

# Whole-string WPN match (e.g. user typed it into a field).
WPN_PATTERN = re.compile(rf"^{_WPN_TOKEN}$")

# Embedded-in-filename WPN match (e.g. WS-FH-P000042-A.STEP). Allows
# any extension after the WPN; captures the WPN itself in group 1.
_FILENAME_WPN = re.compile(rf"^({_WPN_TOKEN})(\.[A-Za-z0-9]+)?$")


@dataclass
class FilenameValidationResult:
    """Pure parsing — no HAROLD call. Layer above (service.py)
    optionally calls HAROLD's validate on the extracted WPN to check
    issued-status."""
    filename:            str
    base_name:           str            # filename minus extension
    extension:           str            # ".STEP" / ".stp" / "" if no dot
    is_wardstone_format: bool
    extracted_wpn:       Optional[str]


def _split_extension(filename: str) -> tuple[str, str]:
    """Filename → (base, ext). Returns ``("", "")`` for empty input."""
    if not filename:
        return ("", "")
    # PurePosixPath is OS-agnostic — Windows-side filenames with
    # backslashes still parse if the caller has already taken the
    # basename. We just want suffix splitting.
    p = PurePosixPath(filename)
    if p.suffix:
        return (p.stem, p.suffix)
    return (filename, "")


def looks_like_wardstone_wpn(value: str) -> bool:
    """Whole-string WPN check. Used for the user-input field on the
    pending-imports review page."""
    if not isinstance(value, str) or not value:
        return False
    return WPN_PATTERN.match(value.strip()) is not None


def extract_wpn_from_filename(filename: str) -> Optional[str]:
    """Return the WPN inside the filename (without extension) or None.

    Cases:
      ``WS-FH-P000042-A``         → ``WS-FH-P000042-A``
      ``WS-FH-P000042-A.STEP``    → ``WS-FH-P000042-A``
      ``WS-FH-P000042-A_v2.step`` → None (suffix beyond extension)
      ``92196A196_..._Screw.STEP``→ None (no WPN-shaped prefix)
    """
    if not isinstance(filename, str) or not filename:
        return None
    base, _ = _split_extension(filename.strip())
    m = _FILENAME_WPN.match(filename.strip())
    if m:
        return m.group(1)
    # Sometimes the WPN is the entire base (no extension).
    if WPN_PATTERN.match(base):
        return base
    return None


def validate_filename(filename: str) -> FilenameValidationResult:
    """Structured filename inspection. Does NOT call HAROLD —
    ``service.validate_filename_wpn`` is the layer that combines this
    with a HAROLD ``validate`` call when a WPN was extracted.
    """
    filename = (filename or "").strip()
    base, ext = _split_extension(filename)
    wpn = extract_wpn_from_filename(filename)
    return FilenameValidationResult(
        filename=filename,
        base_name=base,
        extension=ext,
        is_wardstone_format=wpn is not None,
        extracted_wpn=wpn,
    )
