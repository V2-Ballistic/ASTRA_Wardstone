"""ASTRA-TDD-HAROLD-INT-002 Phase 2 — fallback allocator tests.

These run against SQLite (per the conftest setup). SQLite's
``SELECT ... FOR UPDATE`` is a no-op so concurrent-lock semantics
aren't asserted here — Phase 5's end-to-end smoke against the real
Postgres container exercises that. These tests verify the
single-thread increment semantics, format, error paths, and seeding.

The migration's table-seed SQL doesn't run under ``create_all``, so
each test seeds the 21 codes manually first.
"""
from __future__ import annotations

import pytest

from app.models.catalog import WpnFallbackSequence
from app.services.harold.class_to_system import DEFAULT_SYSTEM_CODE
from app.services.harold.fallback import (
    ALLOWED_SYSTEM_CODES,
    allocate_fallback_wpn,
    allocate_for_part_class,
    format_wpn,
)


@pytest.fixture
def seeded(db_session):
    """Seed the fallback-sequences table with all 21 codes."""
    for code in sorted(ALLOWED_SYSTEM_CODES):
        db_session.add(WpnFallbackSequence(system_code=code, next_index=1))
    db_session.commit()
    return db_session


# ── format_wpn ────────────────────────────────────────────────────


def test_format_wpn_pads_to_six_digits():
    assert format_wpn("FH", 1, "A") == "WS-FH-P000001-A"
    assert format_wpn("FH", 999999, "Y") == "WS-FH-P999999-Y"


def test_format_wpn_default_rev_is_A():
    assert format_wpn("MH", 42) == "WS-MH-P000042-A"


# ── allocate_fallback_wpn ────────────────────────────────────────


def test_first_allocation_returns_000001(seeded):
    wpn = allocate_fallback_wpn(seeded, "FH")
    seeded.commit()
    assert wpn == "WS-FH-P000001-A"


def test_sequential_allocations_increment(seeded):
    a = allocate_fallback_wpn(seeded, "FH")
    b = allocate_fallback_wpn(seeded, "FH")
    c = allocate_fallback_wpn(seeded, "FH")
    seeded.commit()
    assert [a, b, c] == [
        "WS-FH-P000001-A",
        "WS-FH-P000002-A",
        "WS-FH-P000003-A",
    ]


def test_independent_counters_per_system(seeded):
    fh1 = allocate_fallback_wpn(seeded, "FH")
    mh1 = allocate_fallback_wpn(seeded, "MH")
    fh2 = allocate_fallback_wpn(seeded, "FH")
    seeded.commit()
    assert fh1 == "WS-FH-P000001-A"
    assert mh1 == "WS-MH-P000001-A"
    assert fh2 == "WS-FH-P000002-A"


def test_dry_run_does_not_advance(seeded):
    peek = allocate_fallback_wpn(seeded, "FH", dry_run=True)
    real = allocate_fallback_wpn(seeded, "FH")
    seeded.commit()
    assert peek == "WS-FH-P000001-A"
    assert real == "WS-FH-P000001-A"  # dry_run didn't consume


def test_unknown_system_code_rejected(seeded):
    with pytest.raises(ValueError, match="Unknown system code"):
        allocate_fallback_wpn(seeded, "XX")


def test_unknown_system_lowercase_rejected(seeded):
    with pytest.raises(ValueError):
        allocate_fallback_wpn(seeded, "fh")  # case-sensitive


def test_missing_row_raises_runtime(db_session):
    """Empty table → RuntimeError pointing at the migration."""
    with pytest.raises(RuntimeError, match="migration 0033"):
        allocate_fallback_wpn(db_session, "FH")


@pytest.mark.parametrize("code", sorted(ALLOWED_SYSTEM_CODES))
def test_every_seeded_system_can_allocate(code, seeded):
    wpn = allocate_fallback_wpn(seeded, code)
    seeded.commit()
    assert wpn == f"WS-{code}-P000001-A"


# ── allocate_for_part_class (convenience) ─────────────────────────


def test_allocate_for_part_class_routes_to_fh(seeded):
    wpn, sys_code = allocate_for_part_class(seeded, "fastener_screw")
    seeded.commit()
    assert sys_code == "FH"
    assert wpn == "WS-FH-P000001-A"


def test_allocate_for_part_class_unknown_routes_to_default(seeded):
    wpn, sys_code = allocate_for_part_class(seeded, "not_a_class")
    seeded.commit()
    assert sys_code == DEFAULT_SYSTEM_CODE  # MH
    assert wpn.startswith(f"WS-{DEFAULT_SYSTEM_CODE}-P")


def test_allocate_for_part_class_dry_run(seeded):
    wpn1, _ = allocate_for_part_class(seeded, "bracket", dry_run=True)
    wpn2, _ = allocate_for_part_class(seeded, "bracket", dry_run=True)
    assert wpn1 == wpn2 == "WS-MH-P000001-A"


# ── State preserved between sessions ─────────────────────────────


def test_state_persists_after_commit(seeded, db_session):
    """Allocate + commit on one session; query on another and see the
    advance. (SQLite's transactional semantics behave like Postgres
    here.)"""
    allocate_fallback_wpn(seeded, "EH")
    seeded.commit()

    row = (
        db_session.query(WpnFallbackSequence)
        .filter_by(system_code="EH")
        .one()
    )
    assert row.next_index == 2
