"""
ASTRA — Assembly STEP file parser (Phase 4 stub).

Currently performs metadata-only parsing (NAUO via regex on STEP text).
Full OCC mating-pair / fastener-pattern / seal-groove detection is
deferred to a future phase per spec §8.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional


ASSEMBLY_PARSER_VERSION = "1.0.0"


@dataclass
class AssemblyInstanceResult:
    step_entity_id: str
    step_product_name: str
    transform_matrix: list[float]
    matched_library_part_id: Optional[int] = None
    confidence: str = "low"


@dataclass
class AssemblyJointResult:
    part_a_step_entity: str
    part_b_step_entity: str
    joint_type: str
    mating_face_entities: list[str] = field(default_factory=list)
    fastener_thread_size: Optional[str] = None
    fastener_thread_standard: Optional[str] = None
    fastener_count: Optional[int] = None
    torque_nominal_nm: Optional[Decimal] = None
    torque_min_nm: Optional[Decimal] = None
    torque_max_nm: Optional[Decimal] = None
    has_seal_groove: bool = False
    confidence: str = "low"


@dataclass
class AssemblyParseResult:
    instances: list[AssemblyInstanceResult] = field(default_factory=list)
    joints: list[AssemblyJointResult] = field(default_factory=list)
    unmatched_instance_names: list[str] = field(default_factory=list)
    extraction_log: str = ""
    parser_version: str = ASSEMBLY_PARSER_VERSION
    occ_available: bool = False


_PRODUCT_RE = re.compile(
    r"#(\d+)\s*=\s*PRODUCT\s*\(\s*'([^']*)'\s*,\s*'([^']*)'",
    re.IGNORECASE,
)


def parse_assembly_step(
    file_path: str,
    library_parts_lookup: dict[str, int],
) -> AssemblyParseResult:
    """Always-safe metadata parse + (when OCC available) shape load.

    library_parts_lookup maps lowercased identifier strings (name, mpn, wpn)
    to library_part_id values.
    """
    log: list[str] = []
    result = AssemblyParseResult()

    # Stage 1 — assembly tree from PRODUCT entities (always available)
    try:
        with open(file_path, "r", errors="replace") as f:
            text = f.read()
        identity = [
            1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0,
        ]
        for m in _PRODUCT_RE.finditer(text):
            entity_id, name, _description = m.group(1), m.group(2), m.group(3)
            matched = (
                library_parts_lookup.get(name.lower())
                or library_parts_lookup.get(name)
            )
            inst = AssemblyInstanceResult(
                step_entity_id=f"#PRODUCT:{entity_id}",
                step_product_name=name,
                transform_matrix=identity,
                matched_library_part_id=matched,
                confidence="high" if matched else "low",
            )
            result.instances.append(inst)
            if not matched:
                result.unmatched_instance_names.append(name)
        log.append(
            f"Assembly tree: {len(result.instances)} products, "
            f"{len(result.unmatched_instance_names)} unmatched"
        )
    except Exception as exc:
        log.append(f"Metadata parse failed: {exc}")

    # Stage 2 — OCC analysis (currently stub)
    try:
        from OCC.Core.STEPControl import STEPControl_Reader  # type: ignore  # noqa: F401
        result.occ_available = True
        log.append("OCC available — full mating analysis deferred to future phase")
    except ImportError:
        log.append("pythonOCC not available — assembly parser in stub mode")

    result.extraction_log = "\n".join(log)
    return result
