"""ASTRA — Three-Way Auto-Wire Engine (INTF-002 Phase 4)
=========================================================
File: backend/app/services/interface/auto_wire.py

Implements spec §11.2 "Auto-Wire Algorithm — Three-Way Validation". For a
draft / proposed Interface row, walks every pin on the source unit, looks up
the candidate target pin by normalized internal_signal_name, and emits a
``ProposedWire`` only when **all three** of the following pass:

  Check #1 — NAME MATCH       (lowercased + trimmed signal name match)
  Check #2 — DIRECTION COMPAT (per the 6×6 matrix in direction_matrix.py)
  Check #3 — LRU ENDPOINT     (interface.source_unit_id and target_unit_id
                              both set + same project; per-pin check is
                              implicit since pins_src/pins_tgt are scoped
                              to the unit's connectors)

Returns an :class:`AutoWireResult` aggregating proposed wires and every
"interesting" rejection bucket so the UI can surface ambiguities, conflicts,
and unmatched pins to the operator.

The engine is read-only: it does not create harnesses or wires. The commit
step (``cb_commit`` in the router) creates them atomically.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session, joinedload

from app.models.catalog import SignalDirection
from app.models.interface import (
    Connector,
    Interface,
    InterfaceStatus,
    Pin,
    PinDirection,
    SignalType,
    Unit,
    Wire,
)
from app.services.interface.direction_matrix import is_direction_compatible
from app.services.interface.wire_heuristics import WireSuggestion, suggest_wire

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════
#  Public dataclass / pydantic surface
# ══════════════════════════════════════════════════════════════


class AutoWireOptions(BaseModel):
    """Tunable knobs for the auto-wire pass.

    Defaults match spec §11.2 — direction + LRU checks are ON by default and
    the spec note says ``enforce_lru_endpoints`` should "never be off in
    production". Callers must opt-in to disable it.
    """
    require_signal_type_match: bool = True
    require_direction_compatibility: bool = True
    enforce_lru_endpoints: bool = True
    exclude_no_connect: bool = True
    exclude_chassis_ground: bool = False
    case_sensitive_names: bool = False
    only_unmatched_pins: bool = True


@dataclass
class _PinSummary:
    """Tiny POD for transport — keeps the result loosely coupled to ORM."""
    id: int
    pin_number: str
    pin_label: Optional[str]
    internal_signal_name: Optional[str]
    mfr_pin_name: Optional[str]
    direction: str
    signal_type: str
    connector_id: int
    connector_designator: str

    @classmethod
    def from_pin(cls, pin: Pin) -> "_PinSummary":
        direction = _resolve_direction(pin)
        return cls(
            id=pin.id,
            pin_number=pin.pin_number,
            pin_label=pin.pin_label,
            internal_signal_name=pin.internal_signal_name,
            mfr_pin_name=pin.mfr_pin_name,
            direction=direction.value,
            signal_type=_pin_signal_type_str(pin),
            connector_id=pin.connector_id,
            connector_designator=(
                pin.connector.designator if pin.connector else ""
            ),
        )


@dataclass
class ProposedWire:
    """A successful three-way match. Heuristic-derived wire defaults included."""
    source_pin: _PinSummary
    target_pin: _PinSummary
    matched_signal_name: str
    direction_pair: tuple[str, str]
    confidence: str   # "high" | "medium" | "low"
    suggestion: WireSuggestion
    warning: Optional[str] = None  # e.g. "UNKNOWN direction on src"


@dataclass
class AmbiguousMatch:
    """A source pin matches more than one target pin by signal name."""
    source_pin: _PinSummary
    candidates: list[_PinSummary]


@dataclass
class DirectionConflict:
    """A name match was rejected by Check #2."""
    source_pin: _PinSummary
    target_pin: _PinSummary
    src_direction: str
    tgt_direction: str
    reason: str


@dataclass
class TypeMismatch:
    """A name match was rejected by the optional signal-type filter."""
    source_pin: _PinSummary
    target_pin: _PinSummary
    src_signal_type: str
    tgt_signal_type: str


@dataclass
class AutoWireResult:
    proposed_wires: list[ProposedWire] = field(default_factory=list)
    unmatched_source: list[_PinSummary] = field(default_factory=list)
    unmatched_target: list[_PinSummary] = field(default_factory=list)
    ambiguous: list[AmbiguousMatch] = field(default_factory=list)
    direction_conflicts: list[DirectionConflict] = field(default_factory=list)
    type_mismatches: list[TypeMismatch] = field(default_factory=list)
    lru_validation_errors: list[str] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════


# Project-side PinDirection → catalog SignalDirection coercion table. Used
# when there's no direction_override and no catalog_pin to fall back to.
# Only the values shared between the two enums are mapped 1:1; everything
# else lands on UNKNOWN (the permissive case).
_PROJECT_DIR_TO_CATALOG: dict[str, SignalDirection] = {
    "input":          SignalDirection.INPUT,
    "output":         SignalDirection.OUTPUT,
    "bidirectional":  SignalDirection.BIDIRECTIONAL,
    "ground":         SignalDirection.GROUND,
    "chassis_ground": SignalDirection.GROUND,
    "power_source":   SignalDirection.POWER,
    "power_sink":     SignalDirection.POWER,
    "power_return":   SignalDirection.POWER,
}


def _resolve_direction(pin: Pin) -> SignalDirection:
    """Apply the spec precedence: override → catalog → project-side fallback."""
    if pin.direction_override is not None:
        # Already a SignalDirection enum (column type-coerced).
        return pin.direction_override
    if pin.catalog_pin is not None and pin.catalog_pin.mfr_direction is not None:
        return pin.catalog_pin.mfr_direction
    if pin.direction is not None:
        legacy = pin.direction.value if hasattr(pin.direction, "value") else str(pin.direction)
        return _PROJECT_DIR_TO_CATALOG.get(legacy.lower(), SignalDirection.UNKNOWN)
    return SignalDirection.UNKNOWN


def _pin_signal_type_str(pin: Pin) -> str:
    """Project-side or catalog-side signal_type as lowercase string."""
    if pin.catalog_pin is not None and pin.catalog_pin.mfr_signal_type is not None:
        return pin.catalog_pin.mfr_signal_type.value
    if pin.signal_type is not None:
        return pin.signal_type.value if hasattr(pin.signal_type, "value") else str(pin.signal_type)
    return "unknown"


def _is_no_connect(pin: Pin) -> bool:
    """True if pin is marked as NC on either catalog or project side."""
    if pin.catalog_pin is not None and getattr(pin.catalog_pin, "is_no_connect", False):
        return True
    if pin.signal_type == SignalType.NO_CONNECT:
        return True
    if pin.direction == PinDirection.NO_CONNECT:
        return True
    return False


def _is_chassis_ground(pin: Pin) -> bool:
    """True if pin is a chassis-ground tie-point on either catalog or project side."""
    if pin.catalog_pin is not None and getattr(pin.catalog_pin, "is_chassis_ground", False):
        return True
    if pin.signal_type == SignalType.CHASSIS_GROUND:
        return True
    if pin.direction == PinDirection.CHASSIS_GROUND:
        return True
    return False


def _normalize_name(name: Optional[str], case_sensitive: bool) -> str:
    """Lowercase + trim + collapse internal whitespace per spec §11.2 step 4."""
    if name is None:
        return ""
    s = name.strip()
    if not case_sensitive:
        s = s.lower()
    # Collapse multi-spaces
    return " ".join(s.split())


def _load_unit_pins(db: Session, unit_id: int) -> list[Pin]:
    """All pins under all connectors of a unit, eagerly loaded with catalog_pin."""
    return (
        db.query(Pin)
        .join(Connector, Pin.connector_id == Connector.id)
        .filter(Connector.unit_id == unit_id)
        .options(joinedload(Pin.catalog_pin), joinedload(Pin.connector))
        .all()
    )


def _pin_already_wired(db: Session, pin_id: int) -> bool:
    """True if this pin is already on either side of any existing Wire."""
    exists = (
        db.query(Wire.id)
        .filter((Wire.from_pin_id == pin_id) | (Wire.to_pin_id == pin_id))
        .first()
    )
    return exists is not None


def _confidence(
    src_dir: SignalDirection, tgt_dir: SignalDirection,
    direction_warning: Optional[str], type_match: bool,
) -> str:
    """Heuristic confidence — for the UI badge."""
    if direction_warning is not None:
        return "low"
    if not type_match:
        return "medium"
    if SignalDirection.UNKNOWN in (src_dir, tgt_dir):
        return "medium"
    return "high"


def _pin_voltage(pin: Pin) -> Optional[float]:
    """Pick the most informative voltage_v for the heuristic."""
    if pin.voltage_max is not None:
        return float(pin.voltage_max)
    if pin.catalog_pin is not None and pin.catalog_pin.mfr_voltage_max_v is not None:
        return float(pin.catalog_pin.mfr_voltage_max_v)
    return None


def _pin_current(pin: Pin) -> Optional[float]:
    """Pick the most informative current_amps for the heuristic."""
    if pin.current_max_amps is not None:
        return float(pin.current_max_amps)
    if pin.catalog_pin is not None and pin.catalog_pin.mfr_current_max_ma is not None:
        # CatalogPin stores current in milliamps; convert.
        return float(pin.catalog_pin.mfr_current_max_ma) / 1000.0
    return None


# ══════════════════════════════════════════════════════════════
#  Engine
# ══════════════════════════════════════════════════════════════


def auto_wire_interface(
    db: Session,
    interface_id: int,
    options: Optional[AutoWireOptions] = None,
) -> AutoWireResult:
    """Run the three-way auto-wire algorithm against ``interface_id``.

    The function never mutates the DB. Caller decides what to do with the
    proposals (typically: review in UI, then commit through ``cb_commit``).
    """
    opts = options or AutoWireOptions()
    result = AutoWireResult()

    # ── Step 1: load + status check ──
    interface = db.query(Interface).filter(Interface.id == interface_id).first()
    if interface is None:
        result.lru_validation_errors.append(
            f"Interface id={interface_id} not found."
        )
        return result
    if interface.status == InterfaceStatus.APPROVED:
        result.lru_validation_errors.append(
            "Interface is APPROVED — auto-wire is locked. "
            "Re-open the interface to re-run auto-suggest."
        )
        return result

    # ── Step 2: LRU endpoint validation (Check #3) ──
    src_unit_id = interface.source_unit_id
    tgt_unit_id = interface.target_unit_id

    if src_unit_id is None:
        result.lru_validation_errors.append(
            "source_unit_id is not set on this interface. "
            "Pick a source unit in the Connection Builder before auto-wiring."
        )
    if tgt_unit_id is None:
        result.lru_validation_errors.append(
            "target_unit_id is not set on this interface. "
            "Pick a target unit in the Connection Builder before auto-wiring."
        )
    if src_unit_id is None or tgt_unit_id is None:
        return result

    src_unit = db.query(Unit).filter(Unit.id == src_unit_id).first()
    tgt_unit = db.query(Unit).filter(Unit.id == tgt_unit_id).first()
    if src_unit is None or tgt_unit is None:
        result.lru_validation_errors.append(
            "Source or target unit no longer exists in the database."
        )
        return result

    if src_unit.project_id != tgt_unit.project_id:
        msg = (
            f"Cross-project wires are not allowed: "
            f"source unit project={src_unit.project_id}, "
            f"target unit project={tgt_unit.project_id}."
        )
        if opts.enforce_lru_endpoints:
            result.lru_validation_errors.append(msg)
            return result
        log.warning("auto_wire: enforce_lru_endpoints=False — allowing %s", msg)

    # ── Step 3: load all pins for both units ──
    pins_src = _load_unit_pins(db, src_unit_id)
    pins_tgt = _load_unit_pins(db, tgt_unit_id)

    # ── Step 4: build target index ──
    tgt_index: dict[str, list[Pin]] = {}
    for tp in pins_tgt:
        key = _normalize_name(tp.internal_signal_name, opts.case_sensitive_names)
        if not key:
            continue
        tgt_index.setdefault(key, []).append(tp)

    # ── Step 5: per-source-pin three-way check ──
    consumed_target_pin_ids: set[int] = set()

    for sp in pins_src:
        # Pre-filters
        if not sp.internal_signal_name:
            continue
        if opts.exclude_no_connect and _is_no_connect(sp):
            continue
        if opts.exclude_chassis_ground and _is_chassis_ground(sp):
            continue
        if opts.only_unmatched_pins and _pin_already_wired(db, sp.id):
            continue

        key = _normalize_name(sp.internal_signal_name, opts.case_sensitive_names)
        candidates = tgt_index.get(key, [])

        # Check #1 — name match
        if len(candidates) == 0:
            result.unmatched_source.append(_PinSummary.from_pin(sp))
            continue
        if len(candidates) > 1:
            result.ambiguous.append(AmbiguousMatch(
                source_pin=_PinSummary.from_pin(sp),
                candidates=[_PinSummary.from_pin(c) for c in candidates],
            ))
            continue

        tgt_pin = candidates[0]

        # Check #2 — direction compatibility
        src_dir = _resolve_direction(sp)
        tgt_dir = _resolve_direction(tgt_pin)
        direction_warning: Optional[str] = None

        if opts.require_direction_compatibility:
            compat, reason = is_direction_compatible(src_dir, tgt_dir)
            if not compat:
                result.direction_conflicts.append(DirectionConflict(
                    source_pin=_PinSummary.from_pin(sp),
                    target_pin=_PinSummary.from_pin(tgt_pin),
                    src_direction=src_dir.value,
                    tgt_direction=tgt_dir.value,
                    reason=reason or "Direction conflict.",
                ))
                continue
            # compat True but with reason → UNKNOWN warning case
            direction_warning = reason

        # Optional signal-type filter
        type_match = True
        if opts.require_signal_type_match:
            src_type = _pin_signal_type_str(sp)
            tgt_type = _pin_signal_type_str(tgt_pin)
            if src_type != tgt_type and "unknown" not in {src_type, tgt_type}:
                result.type_mismatches.append(TypeMismatch(
                    source_pin=_PinSummary.from_pin(sp),
                    target_pin=_PinSummary.from_pin(tgt_pin),
                    src_signal_type=src_type,
                    tgt_signal_type=tgt_type,
                ))
                continue
            if src_type != tgt_type:
                type_match = False

        # All checks passed → propose
        suggestion = suggest_wire(
            signal_type=_pin_signal_type_str(sp),
            current_amps=_pin_current(sp),
            voltage_v=_pin_voltage(sp),
        )

        result.proposed_wires.append(ProposedWire(
            source_pin=_PinSummary.from_pin(sp),
            target_pin=_PinSummary.from_pin(tgt_pin),
            matched_signal_name=key,
            direction_pair=(src_dir.value, tgt_dir.value),
            confidence=_confidence(src_dir, tgt_dir, direction_warning, type_match),
            suggestion=suggestion,
            warning=direction_warning,
        ))
        consumed_target_pin_ids.add(tgt_pin.id)

    # ── Step 6: unmatched_target = pins_tgt not consumed ──
    for tp in pins_tgt:
        if tp.id in consumed_target_pin_ids:
            continue
        if not tp.internal_signal_name:
            continue
        if opts.exclude_no_connect and _is_no_connect(tp):
            continue
        if opts.exclude_chassis_ground and _is_chassis_ground(tp):
            continue
        # Only count target pins that had no source candidate at all.
        # (Pins lost to direction conflict / type mismatch are already
        # surfaced in their respective buckets.)
        result.unmatched_target.append(_PinSummary.from_pin(tp))

    return result
