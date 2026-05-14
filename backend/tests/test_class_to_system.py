"""ASTRA-TDD-HAROLD-INT-002 Phase 2 — class → system_code mapping."""
from __future__ import annotations

import pytest

from app.services.harold.class_to_system import (
    DEFAULT_SYSTEM_CODE,
    PART_CLASS_TO_SYSTEM_CODE,
    SYSTEM_CODE_LABELS,
    map_class_to_system,
)


# ── Library codes only — no project-system codes should appear ────


def test_only_four_library_codes_in_target_set():
    """AD-6: every value in the table must be one of FH/MH/EH/SH."""
    library = {"FH", "MH", "EH", "SH"}
    assert set(PART_CLASS_TO_SYSTEM_CODE.values()).issubset(library)


def test_default_is_mh():
    assert DEFAULT_SYSTEM_CODE == "MH"


# ── Every fastener category → FH ──────────────────────────────────


@pytest.mark.parametrize("cls", [
    "fastener_screw", "fastener_bolt", "nut", "washer",
])
def test_fasteners_map_to_fh(cls):
    assert map_class_to_system(cls) == "FH"


# ── Mechanical non-fasteners → MH ─────────────────────────────────


@pytest.mark.parametrize("cls", [
    "bracket", "housing", "enclosure", "bearing", "spring",
    "structural_member", "mechanical_other",
])
def test_mechanical_maps_to_mh(cls):
    assert map_class_to_system(cls) == "MH"


# ── Sealing → SH ─────────────────────────────────────────────────


def test_seals_map_to_sh():
    assert map_class_to_system("seal_o_ring") == "SH"


# ── Electrical → EH ──────────────────────────────────────────────


@pytest.mark.parametrize("cls", [
    "processor", "sensor", "power_supply", "radio", "antenna",
    "actuator", "display", "harness", "connector_only",
    "compute_module", "power_distribution", "interface_card",
])
def test_electrical_maps_to_eh(cls):
    assert map_class_to_system(cls) == "EH"


# ── Unmapped / edge cases ────────────────────────────────────────


def test_unknown_class_falls_back_to_default():
    assert map_class_to_system("not_a_real_class") == DEFAULT_SYSTEM_CODE


def test_empty_class_falls_back_to_default():
    assert map_class_to_system("") == DEFAULT_SYSTEM_CODE


def test_none_falls_back_to_default():
    # type: ignore[arg-type]
    assert map_class_to_system(None) == DEFAULT_SYSTEM_CODE  # type: ignore[arg-type]


# ── Labels ───────────────────────────────────────────────────────


def test_labels_cover_all_four_library_codes():
    assert set(SYSTEM_CODE_LABELS.keys()) == {"FH", "MH", "EH", "SH"}


def test_label_contents():
    assert SYSTEM_CODE_LABELS["FH"] == "Fastener Hardware"
    assert SYSTEM_CODE_LABELS["MH"] == "Mechanical Hardware"
    assert SYSTEM_CODE_LABELS["EH"] == "Electrical Hardware"
    assert SYSTEM_CODE_LABELS["SH"] == "Soft / Sealing Hardware"
