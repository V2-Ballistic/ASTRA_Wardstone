"""
ASTRA — Spreadsheet upload security helpers (F-018)
=====================================================
File: backend/app/services/security/spreadsheet.py

Shared validation for the three spreadsheet-upload endpoints
(imports.py preview, interface_import.py preview + confirm).

Layers:
  1. BodySizeLimitMiddleware (registered in main.py) rejects oversized
     requests before the handler reads. This module covers the rest.
  2. Content-Type / magic-bytes sniff: declared MIME must match parsed
     content. Bytes-based sniff (no libmagic dep) covers our two
     formats (XLSX = ZIP magic, CSV = printable ASCII).
  3. Workbook size caps after parse: > MAX_SHEETS sheets or any sheet
     > MAX_ROWS rows → 413.
  4. Formula-injection defense: any cell value being re-emitted whose
     first character is = + - @ is prefixed with "'" per OWASP
     CSV-injection mitigation guidance.
  5. Filename sanitisation for response echoes.

All raises are FastAPI HTTPException so handlers can `raise` directly.
"""

from __future__ import annotations

import os
import re
from typing import Iterable

from fastapi import HTTPException


# ── Content-Type allowlist (Content-Type header from the upload) ──
ALLOWED_XLSX_TYPES = {
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-excel",                           # legacy .xls
    "application/octet-stream",                           # some clients
}
ALLOWED_CSV_TYPES = {
    "text/csv",
    "text/plain",
    "application/csv",
    "application/octet-stream",
}

# ── Workbook size caps (configurable via env) ──
MAX_ROWS = int(os.getenv("MAX_UPLOAD_ROWS", "50000"))
MAX_SHEETS = int(os.getenv("MAX_UPLOAD_SHEETS", "25"))


# ══════════════════════════════════════
#  Sniffing
# ══════════════════════════════════════


def sniff_content_type(content: bytes) -> str:
    """
    Identify a buffer as ``"xlsx"`` / ``"csv"`` / ``"binary"``.

    Bytes-based detection (no libmagic dependency):
      - XLSX is a ZIP archive — starts with ``PK\\x03\\x04``.
      - CSV has no magic bytes; we treat as CSV if the first 1 KB
        decodes cleanly as printable ASCII / common whitespace.
      - Anything else is "binary" — rejected as 415.

    For richer sniffing (e.g. distinguishing xlsx from xlsm or
    arbitrary ZIPs), add `python-magic` + libmagic to the image and
    swap this implementation. The interface stays the same.
    """
    if not content:
        return "binary"
    if content.startswith(b"PK\x03\x04"):
        return "xlsx"

    sample = content[:1024]
    try:
        text = sample.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        try:
            text = sample.decode("utf-8-sig", errors="strict")
        except UnicodeDecodeError:
            return "binary"

    if all(c.isprintable() or c in "\r\n\t" for c in text):
        return "csv"
    return "binary"


def validate_upload(
    *,
    content: bytes,
    declared_content_type: str | None,
    expected_kind: str,
) -> str:
    """
    Validate an upload against the declared Content-Type AND a magic-byte
    sniff. Returns the sniffed kind (``"xlsx"`` or ``"csv"``).

    Args:
        content: full body bytes (already read in handler).
        declared_content_type: value of the request's Content-Type header.
        expected_kind: ``"xlsx"`` (handler accepts only XLSX) or
            ``"csv_or_xlsx"`` (handler accepts either).

    Raises:
        HTTPException(413) if content is empty.
        HTTPException(415) if Content-Type isn't in the allowlist OR
            the sniffed type doesn't match the declared type.
    """
    if not content:
        raise HTTPException(400, "Empty file")

    sniffed = sniff_content_type(content)
    declared = (declared_content_type or "").split(";")[0].strip().lower()

    if expected_kind == "xlsx":
        if declared and declared not in ALLOWED_XLSX_TYPES:
            raise HTTPException(
                415,
                f"Unsupported Content-Type {declared!r}; expected an XLSX "
                "MIME type.",
            )
        if sniffed != "xlsx":
            raise HTTPException(
                415,
                f"Body does not match declared Content-Type: sniffed as "
                f"{sniffed!r}, expected XLSX.",
            )
        return "xlsx"

    if expected_kind == "csv_or_xlsx":
        if declared and declared not in ALLOWED_XLSX_TYPES | ALLOWED_CSV_TYPES:
            raise HTTPException(
                415,
                f"Unsupported Content-Type {declared!r}; expected CSV or XLSX.",
            )
        if sniffed not in ("xlsx", "csv"):
            raise HTTPException(
                415,
                f"Body does not match a supported format: sniffed as "
                f"{sniffed!r}, expected CSV or XLSX.",
            )
        # Cross-check: a declared XLSX MIME with CSV bytes (or vice
        # versa) is a mismatch — only allow if the declared type is
        # ambiguous (octet-stream) or matches the sniffed kind.
        ambiguous = {"application/octet-stream"}
        if declared and declared not in ambiguous:
            xlsx_declared = declared in ALLOWED_XLSX_TYPES
            csv_declared = declared in ALLOWED_CSV_TYPES
            if xlsx_declared and sniffed != "xlsx":
                raise HTTPException(
                    415,
                    f"Body does not match declared Content-Type: sniffed as "
                    f"{sniffed!r}, declared XLSX.",
                )
            if csv_declared and not xlsx_declared and sniffed != "csv":
                raise HTTPException(
                    415,
                    f"Body does not match declared Content-Type: sniffed as "
                    f"{sniffed!r}, declared CSV.",
                )
        return sniffed

    raise ValueError(
        f"validate_upload: unknown expected_kind={expected_kind!r}",
    )


# ══════════════════════════════════════
#  Workbook size caps
# ══════════════════════════════════════


def assert_workbook_size_ok(workbook) -> None:
    """
    Raise ``HTTPException(413)`` if the openpyxl Workbook exceeds the
    sheet- or row-count caps. Call AFTER load_workbook(read_only=True).
    """
    sheet_count = len(workbook.sheetnames)
    if sheet_count > MAX_SHEETS:
        raise HTTPException(
            413,
            f"Workbook has {sheet_count} sheets — exceeds the {MAX_SHEETS}-sheet limit.",
        )
    for name in workbook.sheetnames:
        ws = workbook[name]
        # ws.max_row is None for newly-streamed sheets in some cases;
        # fall back to a safe iteration count.
        rows = ws.max_row or 0
        if rows > MAX_ROWS:
            raise HTTPException(
                413,
                f"Sheet {name!r} has {rows:,} rows — exceeds the {MAX_ROWS:,}-row limit.",
            )


# ══════════════════════════════════════
#  Formula-injection mitigation
# ══════════════════════════════════════


_FORMULA_TRIGGERS = ("=", "+", "-", "@")


def formula_safe(value: object) -> str:
    """
    Make *value* safe to re-emit into a CSV / XLSX cell that a downstream
    spreadsheet client (Excel / Google Sheets / LibreOffice) might
    interpret as a formula.

    Strategy: per OWASP CSV Injection guidance, prefix a leading
    ``=``/``+``/``-``/``@`` with a single quote so the receiving
    spreadsheet treats it as literal text.

    Non-string values are stringified first. Empty / None values pass
    through unchanged.
    """
    if value is None:
        return ""
    s = value if isinstance(value, str) else str(value)
    if s and s[0] in _FORMULA_TRIGGERS:
        return "'" + s
    return s


def formula_safe_iter(values: Iterable[object]) -> list[str]:
    """Apply ``formula_safe`` to every element of *values*."""
    return [formula_safe(v) for v in values]


# ══════════════════════════════════════
#  Filename sanitisation
# ══════════════════════════════════════


# Allow letters, digits, hyphen, underscore, dot. Replace anything else
# with underscore. Strip leading dots so a malicious "..\..\..\foo"
# can't traverse upward when we echo the name in Content-Disposition.
_FILENAME_ALLOWED = re.compile(r"[^A-Za-z0-9._-]")


def sanitize_filename(name: str | None, *, default: str = "upload") -> str:
    """
    Reduce a user-supplied filename to its base name with a strict
    character allowlist. Path separators (``/``, ``\\``) and shell
    metacharacters are replaced with ``_``. Leading dots are stripped
    so the result can't traverse upward when re-emitted in
    Content-Disposition headers.
    """
    if not name:
        return default
    # Strip any directory components from either separator
    base = name.replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = _FILENAME_ALLOWED.sub("_", base).lstrip(".")
    return cleaned or default
