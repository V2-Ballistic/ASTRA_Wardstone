"""
ASTRA — Reactive Requirement Sync — Renderer
=============================================
File: backend/app/services/req_sync/renderer.py    ← NEW (Phase 5)

Deterministic re-renderer for auto-generated requirements. Given a template
id and a set of source links, this module reads the *current* state of each
referenced source entity from the DB and renders the requirement text the
way the original generator would. The fan-out engine then diffs the result
against the requirement currently stored in the DB.

This module deliberately avoids any side effects (no DB writes, no flushes,
no event emission) — `fan_out` decides what to do with the rendered output.

Design notes
------------
* We reuse the template strings declared in
  ``app.services.interface.auto_requirements.TEMPLATES``. Those strings ARE
  the canonical source of truth for auto-req language.
* Context dicts are rebuilt fresh from the DB so the result reflects the
  *current* values of source entities (the whole point of sync).
* Missing source entities (deleted) are signalled by the renderer returning
  ``None`` for ``statement`` so callers can detect "source has vanished" and
  raise an OBSOLETE proposal.
* String formatting goes through ``_SafeDict`` so a missing context key
  becomes the literal string ``"TBD"`` instead of crashing — this matches
  the production renderer's behaviour exactly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.interface import (
    System, Unit, Connector, Pin,
    BusDefinition, MessageDefinition, MessageField,
    WireHarness, Wire, UnitEnvironmentalSpec,
)
from app.models.req_sync import RequirementSourceLink, SourceEntityType
from app.services.interface.auto_requirements import (
    TEMPLATES,
    _SafeDict,
    _ev,
)

logger = logging.getLogger("astra.req_sync.renderer")


# ══════════════════════════════════════════════════════════════
#  Public dataclass
# ══════════════════════════════════════════════════════════════

@dataclass
class RenderedRequirement:
    """Result of rendering an auto-req template against current source data.

    ``statement`` and ``rationale`` are ``None`` when the primary source
    entity has been deleted (caller should raise an OBSOLETE proposal).
    """
    statement: Optional[str] = None
    rationale: Optional[str] = None
    title: Optional[str] = None
    template_inputs: Dict[str, Any] = field(default_factory=dict)
    source_deleted: bool = False
    template_missing: bool = False


# ══════════════════════════════════════════════════════════════
#  Source entity loaders
# ══════════════════════════════════════════════════════════════

_LOADER_BY_TYPE = {
    SourceEntityType.SYSTEM:         System,
    SourceEntityType.UNIT:           Unit,
    SourceEntityType.CONNECTOR:      Connector,
    SourceEntityType.PIN:            Pin,
    SourceEntityType.WIRE_HARNESS:   WireHarness,
    SourceEntityType.WIRE:           Wire,
    SourceEntityType.BUS_DEFINITION: BusDefinition,
    SourceEntityType.MESSAGE:        MessageDefinition,
    SourceEntityType.MESSAGE_FIELD:  MessageField,
    SourceEntityType.UNIT_ENV_SPEC:  UnitEnvironmentalSpec,
}


def _load_source_entity(db: Session, source_type: SourceEntityType, source_id: int):
    model = _LOADER_BY_TYPE.get(source_type)
    if model is None:
        return None
    return db.query(model).filter(model.id == source_id).first()


# ══════════════════════════════════════════════════════════════
#  Context builders (deterministic — no commits)
# ══════════════════════════════════════════════════════════════

def _harness_context(db: Session, harness: WireHarness) -> Dict[str, Any]:
    fu = db.query(Unit).filter(Unit.id == harness.from_unit_id).first()
    tu = db.query(Unit).filter(Unit.id == harness.to_unit_id).first()
    fc = db.query(Connector).filter(Connector.id == harness.from_connector_id).first()
    tc = db.query(Connector).filter(Connector.id == harness.to_connector_id).first()
    fs = db.query(System).filter(System.id == fu.system_id).first() if fu else None
    ts = db.query(System).filter(System.id == tu.system_id).first() if tu else None
    wire_count = db.query(func.count(Wire.id)).filter(Wire.harness_id == harness.id).scalar() or 0

    return {
        "harness_id": harness.harness_id or f"HAR-{harness.id}",
        "source_unit": fu.designation if fu else "Unknown",
        "target_unit": tu.designation if tu else "Unknown",
        "source_abbrev": (fs.abbreviation if fs and fs.abbreviation else fu.designation if fu else "?")[:10],
        "target_abbrev": (ts.abbreviation if ts and ts.abbreviation else tu.designation if tu else "?")[:10],
        "from_conn": fc.designator if fc else "?",
        "to_conn": tc.designator if tc else "?",
        "cable_spec": harness.cable_spec or harness.cable_type or "TBD",
        "cable_type": harness.cable_type or "TBD",
        "max_length": harness.overall_length_max_m or harness.overall_length_m or "TBD",
        "wire_count": wire_count,
        "pair_count": harness.pair_count or 0,
        "shield_type": _ev(harness.shield_type) or "none",
        "drawing_number": harness.drawing_number or "TBD",
        "voltage_rating": harness.voltage_rating_v or "TBD",
    }


def _bus_context(db: Session, bus_def: BusDefinition,
                 harness: Optional[WireHarness] = None) -> Dict[str, Any]:
    fu = tu = fc = tc = fs = ts = None
    if harness is not None:
        fu = db.query(Unit).filter(Unit.id == harness.from_unit_id).first()
        tu = db.query(Unit).filter(Unit.id == harness.to_unit_id).first()
        fc = db.query(Connector).filter(Connector.id == harness.from_connector_id).first()
        tc = db.query(Connector).filter(Connector.id == harness.to_connector_id).first()
        fs = db.query(System).filter(System.id == fu.system_id).first() if fu else None
        ts = db.query(System).filter(System.id == tu.system_id).first() if tu else None

    protocol = _ev(bus_def.protocol)
    is_bidir = protocol in (
        "mil_std_1553a", "mil_std_1553b", "can_2a", "can_2b", "canfd",
        "ethernet_100base_tx", "ethernet_1000base_t",
    )

    return {
        "harness_id": (harness.harness_id if harness else None) or (
            f"HAR-{harness.id}" if harness else "TBD"
        ),
        "source_system": (fs.name if fs else (fu.name if fu else "Unknown")),
        "target_system": (ts.name if ts else (tu.name if tu else "Unknown")),
        "source_unit": fu.designation if fu else "Unknown",
        "target_unit": tu.designation if tu else "Unknown",
        "source_abbrev": (fs.abbreviation if fs and fs.abbreviation else fu.designation if fu else "?")[:10],
        "target_abbrev": (ts.abbreviation if ts and ts.abbreviation else tu.designation if tu else "?")[:10],
        "source_connector": fc.designator if fc else "?",
        "target_connector": tc.designator if tc else "?",
        "protocol": protocol,
        "protocol_display": protocol.replace("_", "-").upper(),
        "protocol_short": protocol.split("_")[-1].upper()[:8],
        "bus_def_id": bus_def.bus_def_id or f"BUS-{bus_def.id}",
        "bus_role": _ev(bus_def.bus_role),
        "bus_address": bus_def.bus_address or "N/A",
        "bus_network_name": bus_def.bus_name_network or bus_def.name,
        "data_rate": bus_def.data_rate or "TBD",
        "direction_verb": "exchange data with" if is_bidir else "transmit data to",
        "preposition": "with" if is_bidir else "to",
        "data_description": "data",
    }


def _message_context(db: Session, msg: MessageDefinition) -> Dict[str, Any]:
    bus = db.query(BusDefinition).filter(BusDefinition.id == msg.bus_def_id).first()
    unit = db.query(Unit).filter(Unit.id == msg.unit_id).first()
    protocol = _ev(bus.protocol) if bus else ""
    direction = _ev(msg.direction)
    field_count = db.query(func.count(MessageField.id)).filter(
        MessageField.message_id == msg.id
    ).scalar() or 0
    total_bits = db.query(func.sum(MessageField.bit_length)).filter(
        MessageField.message_id == msg.id
    ).scalar() or 0
    direction_verb_map = {
        "transmit": "transmit", "receive": "receive",
        "transmit_receive": "transmit and receive",
        "broadcast": "broadcast",
    }
    bus_detail = (
        f"{(bus.bus_name_network or bus.name)} SA{msg.subaddress}"
        if (bus and msg.subaddress) else (bus.name if bus else "TBD")
    )
    return {
        "unit_name": unit.name if unit else "Unknown",
        "unit_designation": unit.designation if unit else "?",
        "msg_label": msg.label,
        "msg_mnemonic": msg.mnemonic or msg.label[:8],
        "msg_def_id": msg.msg_def_id or f"MSG-{msg.id}",
        "bus_def_id": (bus.bus_def_id or f"BUS-{bus.id}") if bus else "TBD",
        "bus_detail": bus_detail,
        "protocol_display": protocol.replace("_", "-").upper(),
        "direction": direction,
        "direction_verb": direction_verb_map.get(direction, "transmit"),
        "rate_hz": msg.rate_hz or "TBD",
        "latency_max_ms": msg.latency_max_ms or "TBD",
        "word_count": msg.word_count or "TBD",
        "field_count": field_count,
        "total_bits": total_bits,
        "scheduling": _ev(msg.scheduling) or "periodic",
    }


def _field_context(db: Session, field_obj: MessageField) -> Dict[str, Any]:
    msg = db.query(MessageDefinition).filter(
        MessageDefinition.id == field_obj.message_id
    ).first()
    if msg is None:
        return {}

    position = f"word {field_obj.word_number}" if field_obj.word_number else "TBD"
    if field_obj.bit_offset is not None:
        position += (
            f", bits [{field_obj.bit_offset}:"
            f"{field_obj.bit_offset + field_obj.bit_length - 1}]"
        )

    return {
        "msg_label": msg.label,
        "msg_mnemonic": msg.mnemonic or msg.label[:8],
        "msg_def_id": msg.msg_def_id or f"MSG-{msg.id}",
        "field_name": field_obj.field_name,
        "field_label": field_obj.label or field_obj.field_name,
        "data_type_display": _ev(field_obj.data_type).replace("_", " ").upper(),
        "bit_length": field_obj.bit_length,
        "position_description": position,
        "min_value": field_obj.min_value if field_obj.min_value is not None else "N/A",
        "max_value": field_obj.max_value if field_obj.max_value is not None else "N/A",
        "unit_of_measure": field_obj.unit_of_measure or "",
        "scale_factor": field_obj.scale_factor or 1.0,
        "offset_value": field_obj.offset_value or 0.0,
        "lsb_value": field_obj.lsb_value or "N/A",
        "resolution": field_obj.resolution or "N/A",
    }


def _wire_context(db: Session, wire: Wire) -> Dict[str, Any]:
    harness = db.query(WireHarness).filter(WireHarness.id == wire.harness_id).first()
    fu = tu = fc = tc = fs = ts = None
    if harness is not None:
        fu = db.query(Unit).filter(Unit.id == harness.from_unit_id).first()
        tu = db.query(Unit).filter(Unit.id == harness.to_unit_id).first()
        fc = db.query(Connector).filter(Connector.id == harness.from_connector_id).first()
        tc = db.query(Connector).filter(Connector.id == harness.to_connector_id).first()
        fs = db.query(System).filter(System.id == fu.system_id).first() if fu else None
        ts = db.query(System).filter(System.id == tu.system_id).first() if tu else None
    fp = db.query(Pin).filter(Pin.id == wire.from_pin_id).first()
    tp = db.query(Pin).filter(Pin.id == wire.to_pin_id).first()
    return {
        "harness_id": (harness.harness_id if harness else None) or (
            f"HAR-{harness.id}" if harness else "TBD"
        ),
        "wire_number": wire.wire_number,
        "signal_name": wire.signal_name,
        "wire_type": _ev(wire.wire_type),
        "wire_gauge": _ev(wire.wire_gauge) if wire.wire_gauge else "22",
        "wire_spec_or_material": (
            wire.wire_spec or wire.wire_material or "stranded copper"
        ),
        "current_max": "TBD",
        "voltage": "TBD",
        "power_description": "power",
        "ground_type": "signal",
        "signal_subtype": "input",
        "voltage_level": "3.3V",
        "direction_display": "input",
        "frequency_display": "TBD",
        "cable_type": (harness.cable_type if harness else None) or "TBD",
        "impedance": "50",
        "insertion_loss_db": "TBD",
        "cable_spec": (harness.cable_spec if harness else None) or "TBD",
        "connector_type": "TBD",
        "termination_end": "source",
        "termination_method": "shield braid to ground",
        "protected_signals": "all",
        "shield_type": _ev(harness.shield_type) if harness else "none",
        "shield_coverage": "85",
        "source_unit": fu.designation if fu else "Unknown",
        "target_unit": tu.designation if tu else "Unknown",
        "source_abbrev": (fs.abbreviation if fs and fs.abbreviation else fu.designation if fu else "?")[:10],
        "target_abbrev": (ts.abbreviation if ts and ts.abbreviation else tu.designation if tu else "?")[:10],
        "from_conn": fc.designator if fc else "?",
        "to_conn": tc.designator if tc else "?",
        "from_pin_number": fp.pin_number if fp else "?",
        "to_pin_number": tp.pin_number if tp else "?",
    }


# ══════════════════════════════════════════════════════════════
#  Template-id → context-builder dispatcher
# ══════════════════════════════════════════════════════════════

# Each template's "primary" source entity type. The fan-out engine guarantees
# that links carry primary-role entries first, but the dispatcher tolerates
# any link order and just searches for the right primary type.
_TEMPLATE_PRIMARY_SOURCE = {
    "harness_overall":   SourceEntityType.WIRE_HARNESS,
    "bus_connection":    SourceEntityType.BUS_DEFINITION,
    "message":           SourceEntityType.MESSAGE,
    "message_field":     SourceEntityType.MESSAGE_FIELD,
    "message_field_enum": SourceEntityType.MESSAGE_FIELD,
    "power_wire":        SourceEntityType.WIRE,
    "ground_wire":       SourceEntityType.WIRE,
    "discrete_signal":   SourceEntityType.WIRE,
    "rf_connection":     SourceEntityType.WIRE,
    "shield_grounding":  SourceEntityType.WIRE,
}


def _build_context(
    db: Session,
    template_id: str,
    source_links: List[RequirementSourceLink],
) -> tuple[Optional[Dict[str, Any]], bool]:
    """Build the format context for *template_id* from current DB state.

    Returns ``(context, source_deleted)``.
    """
    primary_type = _TEMPLATE_PRIMARY_SOURCE.get(template_id)
    if primary_type is None:
        # Unknown template — surface as missing rather than crash.
        return None, False

    primary_link = None
    for sl in source_links:
        # Normalise enum equality across Enum vs str comparisons (SQLite).
        sl_type = sl.source_entity_type
        sl_val = sl_type.value if hasattr(sl_type, "value") else str(sl_type)
        if sl_val == primary_type.value:
            primary_link = sl
            break
    if primary_link is None:
        return None, False

    entity = _load_source_entity(db, primary_type, primary_link.source_entity_id)
    if entity is None:
        return None, True  # source deleted

    if template_id == "harness_overall":
        return _harness_context(db, entity), False
    if template_id == "bus_connection":
        # Look for an associated harness in the source links so the bus
        # context can be enriched with endpoint info.
        harness = None
        for sl in source_links:
            sl_type = sl.source_entity_type
            sl_val = sl_type.value if hasattr(sl_type, "value") else str(sl_type)
            if sl_val == SourceEntityType.WIRE_HARNESS.value:
                harness = db.query(WireHarness).filter(
                    WireHarness.id == sl.source_entity_id
                ).first()
                break
        return _bus_context(db, entity, harness=harness), False
    if template_id == "message":
        return _message_context(db, entity), False
    if template_id in ("message_field", "message_field_enum"):
        return _field_context(db, entity), False
    if template_id in (
        "power_wire", "ground_wire", "discrete_signal",
        "rf_connection", "shield_grounding",
    ):
        return _wire_context(db, entity), False
    return None, False


# ══════════════════════════════════════════════════════════════
#  Public renderer
# ══════════════════════════════════════════════════════════════

def render_requirement(
    db: Session,
    template_id: str,
    source_links: List[RequirementSourceLink],
) -> RenderedRequirement:
    """Render the requirement defined by *template_id* against the *current*
    state of the source entities referenced by *source_links*.

    Deterministic: same DB state + same arguments = same output. Returns a
    :class:`RenderedRequirement` whose ``statement`` is ``None`` when the
    primary source has been deleted (caller should raise an OBSOLETE
    proposal) or when the template id is unknown (caller should log a
    REGENERATE proposal).
    """
    if template_id not in TEMPLATES:
        logger.warning("render_requirement: unknown template_id %r", template_id)
        return RenderedRequirement(template_missing=True)

    ctx, source_deleted = _build_context(db, template_id, source_links)
    if source_deleted:
        return RenderedRequirement(source_deleted=True)
    if ctx is None:
        return RenderedRequirement(template_missing=True)

    tmpl = TEMPLATES[template_id]
    safe = _SafeDict(ctx)
    try:
        statement = tmpl["statement"].format_map(safe)
        rationale = tmpl["rationale"].format_map(safe)
        title = tmpl["title"].format_map(safe)
    except Exception as exc:  # pragma: no cover — _SafeDict swallows missing keys
        logger.error(
            "render_requirement: format error for template %r: %s",
            template_id, exc,
        )
        return RenderedRequirement(template_missing=True, template_inputs=ctx)

    return RenderedRequirement(
        statement=statement,
        rationale=rationale,
        title=title,
        template_inputs=ctx,
    )
