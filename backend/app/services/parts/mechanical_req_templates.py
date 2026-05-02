"""
ASTRA — Auto-requirement templates for mechanical joints.

Each template ID renders a SHALL-statement string from a context dict.
Used by the mechanical-joints router on `approve_joint` to generate
auto-requirements + RequirementSourceLink records.
"""

from __future__ import annotations

from typing import Optional

from app.models.parts_library import JointType


TEMPLATES: dict[str, str] = {
    "MECH-BOLT-001": (
        "The {part_b_name} SHALL be secured to {part_a_name} using "
        "{fastener_count}× {fastener_description} fasteners installed to a torque "
        "of {torque_nominal_nm} N·m ± {torque_tolerance_nm} N·m."
    ),
    "MECH-BOLT-002": (
        "The installation torque for {fastener_description} fasteners at the "
        "{part_a_name}/{part_b_name} interface SHALL NOT exceed "
        "{torque_max_nm} N·m."
    ),
    "MECH-BOLT-003": (
        "All {fastener_description} fasteners at the {part_a_name}/{part_b_name} "
        "interface SHALL incorporate {locking_feature_description} positive locking."
    ),
    "MECH-BOLT-004": (
        "Thread engagement length for {fastener_description} fasteners at the "
        "{part_a_name}/{part_b_name} interface SHALL be a minimum of "
        "{engagement_length_mm} mm."
    ),
    "MECH-SEAL-001": (
        "The {part_a_name}/{part_b_name} interface SHALL maintain leak-tightness "
        "at a maximum leak rate of {leak_rate_max_scc_s} standard cubic centimetres "
        "per second (scc/s) when tested at {test_pressure_bar} bar proof pressure."
    ),
    "MECH-SEAL-002": (
        "The {seal_description} sealing element at the {part_a_name}/{part_b_name} "
        "interface SHALL achieve a mating surface flatness of ≤ "
        "{mating_surface_flatness_mm} mm across the sealing land."
    ),
    "MECH-SURF-001": (
        "The mating surface finish at the {part_a_name}/{part_b_name} interface "
        "SHALL be {mating_surface_finish_ra} µm Ra or better."
    ),
    "MECH-PRESS-001": (
        "The {part_b_name} SHALL be installed into {part_a_name} with an "
        "interference fit achieving a minimum retention force of "
        "{retention_force_n} N at the operating temperature extremes."
    ),
    "MECH-ALIGN-001": (
        "The {part_b_name} SHALL be aligned to {part_a_name} using "
        "{fastener_count}× alignment pin(s), achieving a maximum positional "
        "deviation of {alignment_tolerance_mm} mm."
    ),
    "MECH-MASS-001": (
        "The {part_name} SHALL have a maximum installed mass of {mass_max_g} g "
        "including all fasteners, sealant, and ancillary hardware."
    ),
}


# Which templates fire for each joint type. Every JointType member must
# appear in this map — test_joint_type_templates_map_all_joint_types
# enforces this contract.
JOINT_TYPE_TEMPLATES: dict[JointType, list[str]] = {
    JointType.BOLTED:        ["MECH-BOLT-001", "MECH-BOLT-002", "MECH-BOLT-003",
                              "MECH-BOLT-004", "MECH-SURF-001"],
    JointType.SEAL:          ["MECH-SEAL-001", "MECH-SEAL-002", "MECH-SURF-001"],
    JointType.PRESS_FIT:     ["MECH-PRESS-001", "MECH-SURF-001"],
    JointType.ALIGNMENT_PIN: ["MECH-ALIGN-001"],
    JointType.RIVETED:       ["MECH-BOLT-001", "MECH-SURF-001"],
    JointType.THERMAL_BOND:  ["MECH-SURF-001"],
    JointType.SPRING_CLIP:   [],
    JointType.ADHESIVE:      ["MECH-SURF-001"],
    JointType.WELD:          ["MECH-SURF-001"],
}


LOCKING_FEATURE_DESCRIPTIONS: dict[str, str] = {
    "nylok":              "Nylok-insert",
    "prevailing_torque":  "prevailing-torque",
    "safety_wire":        "safety-wire",
    "loctite":            "Loctite thread-locking compound",
    "castellated":        "castellated nut and cotter pin",
    "lockwire_hole":      "lockwire",
    "none":               "no",
}


class _SafeDict(dict):
    """str.format_map dict that returns 'TBD' for missing keys."""
    def __missing__(self, key):
        return "TBD"


def render_template(template_id: str, context: dict) -> Optional[str]:
    """Render a template. Returns None for unknown ``template_id``.
    Missing context keys substitute as ``TBD``."""
    tmpl = TEMPLATES.get(template_id)
    if not tmpl:
        return None
    try:
        return tmpl.format_map(_SafeDict(context))
    except (ValueError, IndexError):
        return tmpl.format_map(_SafeDict(context))


def build_template_context(joint, part_a_lp, part_b_lp,
                            fastener_lp=None, seal_lp=None) -> dict:
    """Resolve all template tokens from a MechanicalJoint + LibraryParts.

    Missing values resolve to "TBD" so templates never raise.
    """
    torque_nom = joint.torque_nominal_nm
    torque_max = joint.torque_max_nm
    torque_min = joint.torque_min_nm
    if torque_max is not None and torque_min is not None:
        tolerance = round((float(torque_max) - float(torque_min)) / 2, 4)
        torque_tolerance = str(tolerance)
    else:
        torque_tolerance = "TBD"

    lf = joint.locking_feature
    lf_value = lf.value if hasattr(lf, "value") else (lf or "none")

    return {
        "part_a_name":               part_a_lp.name if part_a_lp else "Part A",
        "part_b_name":               part_b_lp.name if part_b_lp else "Part B",
        "fastener_description":      fastener_lp.name if fastener_lp else "fasteners",
        "fastener_count":            str(joint.fastener_count) if joint.fastener_count else "TBD",
        "torque_nominal_nm":         str(torque_nom) if torque_nom is not None else "TBD",
        "torque_min_nm":             str(torque_min) if torque_min is not None else "TBD",
        "torque_max_nm":             str(torque_max) if torque_max is not None else "TBD",
        "torque_tolerance_nm":       torque_tolerance,
        "engagement_length_mm":      (
            str(joint.engagement_length_mm)
            if joint.engagement_length_mm is not None else "TBD"
        ),
        "locking_feature_description": LOCKING_FEATURE_DESCRIPTIONS.get(lf_value, lf_value),
        "mating_surface_flatness_mm": (
            str(joint.mating_surface_flatness_mm)
            if joint.mating_surface_flatness_mm is not None else "TBD"
        ),
        "mating_surface_finish_ra":  (
            str(joint.mating_surface_finish_ra)
            if joint.mating_surface_finish_ra is not None else "TBD"
        ),
        "seal_description":          seal_lp.name if seal_lp else "sealing element",
        "leak_rate_max_scc_s":       (
            str(joint.leak_rate_max_scc_s)
            if joint.leak_rate_max_scc_s is not None else "TBD"
        ),
        "test_pressure_bar":         (
            str(joint.test_pressure_bar)
            if joint.test_pressure_bar is not None else "TBD"
        ),
        "alignment_tolerance_mm":    "0.050",
        "retention_force_n":         "TBD",
        "part_name":                 part_b_lp.name if part_b_lp else "Part",
        "mass_max_g":                (
            str(part_b_lp.mass_max_g)
            if part_b_lp and part_b_lp.mass_max_g is not None else "TBD"
        ),
    }
