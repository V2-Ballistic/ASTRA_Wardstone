"""ASTRA-TDD-HAROLD-INT-002 Phase 2 — filename validator (regex only).

Pure-regex unit tests. The HAROLD-validate-call combination lives in
``test_harold_service.py``.
"""
from __future__ import annotations

import pytest

from app.services.harold.filename_validator import (
    WPN_PATTERN,
    extract_wpn_from_filename,
    looks_like_wardstone_wpn,
    validate_filename,
)


# ── WPN_PATTERN ───────────────────────────────────────────────────


@pytest.mark.parametrize("good", [
    "WS-FH-P000001-A",
    "WS-MH-P000042-B",
    "WS-EH-P999999-Y",
    "WS-ST-P001014-A",
])
def test_wpn_pattern_matches_canonical(good):
    assert WPN_PATTERN.match(good)


@pytest.mark.parametrize("bad", [
    "",
    "WS-FH-P1014-A",          # V1 4-digit (rejected per lock #1)
    "WS-fh-P000001-A",        # lowercase system
    "ws-fh-p000001-a",        # all lowercase
    "WS-FH-P000001-Z",        # forbidden ASME letter Z
    "WS-FH-P000001-I",        # forbidden ASME letter I
    "WS-FH-P000001-O",        # forbidden ASME letter O
    "WS-FH-P000001-Q",        # forbidden ASME letter Q
    "WS-FH-P000001-S",        # forbidden ASME letter S
    "WS-FH-P000001-X",        # forbidden ASME letter X
    "WS-FH-P0000001-A",       # 7 digits
    "WS-FH-P00001-A",         # 5 digits
    "WS-F-P000001-A",         # 1-letter system
    "WS-FOO-P000001-A",       # 3-letter system
    "WS-FH-P000001",          # missing rev
    "FH-P000001-A",           # missing WS prefix
    "WS-FH-P000001-AB",       # double-letter rev
    "ws-FH-P000001-A",        # mixed case
])
def test_wpn_pattern_rejects(bad):
    assert WPN_PATTERN.match(bad) is None


# ── looks_like_wardstone_wpn ─────────────────────────────────────


def test_looks_like_strips_whitespace():
    assert looks_like_wardstone_wpn("  WS-FH-P000001-A  ")


def test_looks_like_non_string_returns_false():
    assert looks_like_wardstone_wpn(None) is False           # type: ignore[arg-type]
    assert looks_like_wardstone_wpn(12345) is False          # type: ignore[arg-type]
    assert looks_like_wardstone_wpn("") is False


# ── extract_wpn_from_filename ────────────────────────────────────


@pytest.mark.parametrize("filename, expected", [
    ("WS-FH-P000001-A",          "WS-FH-P000001-A"),
    ("WS-FH-P000001-A.STEP",     "WS-FH-P000001-A"),
    ("WS-FH-P000001-A.step",     "WS-FH-P000001-A"),
    ("WS-FH-P000001-A.stp",      "WS-FH-P000001-A"),
    ("WS-ST-P001014-A.SLDPRT",   "WS-ST-P001014-A"),
])
def test_extract_extracts_wpn_from_filename(filename, expected):
    assert extract_wpn_from_filename(filename) == expected


@pytest.mark.parametrize("filename", [
    "92196A196_18-8 Stainless Steel Socket Head Screw.STEP",
    "anonymous-part.STEP",
    "WS-FH-P000001-A_v2.step",       # suffix beyond extension
    "WS-FH-P0001-A.STEP",            # V1 4-digit
    "ws-fh-p000001-a.STEP",          # lowercase
    "",
    None,
])
def test_extract_returns_none_for_non_matching(filename):
    assert extract_wpn_from_filename(filename) is None         # type: ignore[arg-type]


# ── validate_filename ─────────────────────────────────────────────


def test_validate_filename_extracts_extension():
    r = validate_filename("WS-FH-P000001-A.STEP")
    assert r.filename == "WS-FH-P000001-A.STEP"
    assert r.base_name == "WS-FH-P000001-A"
    assert r.extension == ".STEP"
    assert r.is_wardstone_format is True
    assert r.extracted_wpn == "WS-FH-P000001-A"


def test_validate_filename_no_extension():
    r = validate_filename("WS-FH-P000001-A")
    assert r.base_name == "WS-FH-P000001-A"
    assert r.extension == ""
    assert r.is_wardstone_format is True


def test_validate_filename_mcmaster_style():
    r = validate_filename("92196A196_Socket_Head_Screw.STEP")
    assert r.is_wardstone_format is False
    assert r.extracted_wpn is None
    assert r.base_name == "92196A196_Socket_Head_Screw"
    assert r.extension == ".STEP"


def test_validate_filename_empty():
    r = validate_filename("")
    assert r.filename == ""
    assert r.base_name == ""
    assert r.extension == ""
    assert r.is_wardstone_format is False
    assert r.extracted_wpn is None


def test_validate_filename_strips_whitespace():
    r = validate_filename("  WS-FH-P000001-A.STEP  ")
    assert r.filename == "WS-FH-P000001-A.STEP"
    assert r.is_wardstone_format is True
