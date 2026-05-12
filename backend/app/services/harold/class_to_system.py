"""ASTRA part_class → HAROLD system_code mapping.

AD-6 (locked in Phase 0): the four library-category codes added in
HAROLD V2 (FH, MH, EH, SH) are the canonical destinations for
catalog-level parts. The 17 V1 project-system codes (VH, AE, ...
ST, ... WH) are for parts that belong to a specific project system;
those don't apply at the catalog level for now and aren't in this
table.

Editable in code, version-controlled — NOT a config file (AD-7).

Future extension: when a part is placed into a project (gets a Unit
record under a System), the WPN may want to switch from the library
code to the project-system code. That's a Phase ≥6 follow-up; not
modeled here.
"""
from __future__ import annotations


# Mapping ASTRA part_class enum value → HAROLD 2-letter system code.
# Built from Mason's lock in HAROLD-INTEGRATION-002 §AD-6.
PART_CLASS_TO_SYSTEM_CODE: dict[str, str] = {
    # ── Fasteners → FH (Fastener Hardware) ──
    "fastener_screw":     "FH",
    "fastener_bolt":      "FH",
    "nut":                "FH",
    "washer":             "FH",

    # ── Mechanical non-fastener hardware → MH (Mechanical Hardware) ──
    "bracket":            "MH",
    "housing":            "MH",
    "enclosure":          "MH",
    "bearing":            "MH",
    "spring":             "MH",
    "structural_member":  "MH",
    "mechanical_other":   "MH",

    # ── Sealing / soft goods → SH (Soft / Sealing Hardware) ──
    "seal_o_ring":        "SH",

    # ── Electrical / electronic → EH (Electrical Hardware) ──
    "processor":          "EH",
    "sensor":             "EH",
    "power_supply":       "EH",
    "radio":              "EH",
    "antenna":            "EH",
    "actuator":           "EH",
    "display":            "EH",
    "harness":            "EH",
    "connector_only":     "EH",
    "compute_module":     "EH",
    "power_distribution": "EH",
    "interface_card":     "EH",
}


# Fallback when a part_class isn't in the map above. MH is the
# safest catch-all — generic mechanical-other gets routed here
# already, so an unmapped class behaves like mechanical_other.
DEFAULT_SYSTEM_CODE: str = "MH"


# Display labels for the four library-category codes (matches V2's
# wpn_reference.py SYSTEMS entries). Used by the router when
# reporting which code a part_class resolved to.
SYSTEM_CODE_LABELS: dict[str, str] = {
    "FH": "Fastener Hardware",
    "MH": "Mechanical Hardware",
    "EH": "Electrical Hardware",
    "SH": "Soft / Sealing Hardware",
}


def map_class_to_system(part_class: str) -> str:
    """Return the HAROLD system code for a part_class.

    Unmapped classes fall back to ``DEFAULT_SYSTEM_CODE``. Returns the
    raw 2-letter code (e.g. ``"FH"``); call ``SYSTEM_CODE_LABELS.get``
    for the human-readable label.
    """
    if not part_class:
        return DEFAULT_SYSTEM_CODE
    return PART_CLASS_TO_SYSTEM_CODE.get(part_class, DEFAULT_SYSTEM_CODE)
