"""
ASTRA — Interface Module Impact Analyzer
=============================================
File: backend/app/services/interface/impact_analyzer.py
Path: C:\\Users\\Mason\\Documents\\ASTRA\\backend\\app\\services\\interface\\impact_analyzer.py

Previews the impact on requirements BEFORE interface entities are
deleted or edited. Integrates with the existing impact analysis
engine (app.services.ai.impact_analyzer) for downstream traversal.

Entry points:
  preview_wire_deletion   — blast radius of removing wires
  preview_bus_deletion    — blast radius of removing a bus definition
  preview_bus_edit        — which reqs need regeneration after bus changes
  preview_message_edit    — which reqs need update after message changes
  preview_unit_deletion   — nuclear option: full entity tree impact
  execute_action          — apply user's chosen resolution to affected reqs
"""

import logging
from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models import (
    User, Requirement, RequirementHistory, Verification,
)
from app.models.interface import (
    System, Unit, Connector, Pin, BusDefinition,
    PinBusAssignment, MessageDefinition, MessageField,
    WireHarness, Wire, Interface,
    UnitEnvironmentalSpec, InterfaceRequirementLink,
    InterfaceChangeImpact,
)

logger = logging.getLogger("astra.interface.impact")


def _ev(v) -> str:
    return v.value if hasattr(v, "value") else str(v) if v else ""


# ══════════════════════════════════════════════════════════════
#  Risk classification constants
# ══════════════════════════════════════════════════════════════

_HIGH_PRIORITY = {"critical", "high", "safety_critical", "mission_critical"}
_CRITICAL_LEVELS = {"L1", "L2"}
_HIGH_LEVELS = {"L3"}


# ══════════════════════════════════════════════════════════════
#  InterfaceImpactAnalyzer
# ══════════════════════════════════════════════════════════════

class InterfaceImpactAnalyzer:
    """
    Previews the blast radius of interface entity changes on the
    requirement tree before changes are applied.
    """

    def __init__(self, db: Session):
        self.db = db

    # ──────────────────────────────────
    #  Wire Deletion Preview
    # ──────────────────────────────────

    def preview_wire_deletion(self, wire_ids: List[int]) -> dict:
        """
        Full blast radius of deleting one or more wires.

        Traversal path:
          wire → direct links
          wire → pin → PinBusAssignment → BusDefinition → links
          bus → messages → links
          messages → fields → links
          harness-level links
        """
        affected: List[dict] = []
        affected_ids: set = set()

        # 1. Direct wire links
        self._collect_entity_links("wire", wire_ids, affected, affected_ids)

        # 2. Harness-level links (wires share a harness)
        harness_ids = set()
        for wid in wire_ids:
            wire = self.db.query(Wire).filter(Wire.id == wid).first()
            if wire:
                harness_ids.add(wire.harness_id)
        if harness_ids:
            self._collect_entity_links("wire_harness", list(harness_ids), affected, affected_ids)

        # 3. Bus-level via pin assignments
        pin_ids = set()
        for wid in wire_ids:
            wire = self.db.query(Wire).filter(Wire.id == wid).first()
            if wire:
                pin_ids.add(wire.from_pin_id)
                pin_ids.add(wire.to_pin_id)

        bus_def_ids = set()
        if pin_ids:
            assignments = self.db.query(PinBusAssignment).filter(
                PinBusAssignment.pin_id.in_(pin_ids)
            ).all()
            for pa in assignments:
                bus_def_ids.add(pa.bus_def_id)

        if bus_def_ids:
            self._collect_entity_links("bus_definition", list(bus_def_ids), affected, affected_ids)

            # 4. Message-level via buses
            msg_ids = set()
            for bd_id in bus_def_ids:
                msgs = self.db.query(MessageDefinition.id).filter(
                    MessageDefinition.bus_def_id == bd_id
                ).all()
                msg_ids.update(m[0] for m in msgs)

            if msg_ids:
                self._collect_entity_links("message_definition", list(msg_ids), affected, affected_ids)

                # 5. Field-level via messages
                field_ids = set()
                for mid in msg_ids:
                    fields = self.db.query(MessageField.id).filter(
                        MessageField.message_id == mid
                    ).all()
                    field_ids.update(f[0] for f in fields)
                if field_ids:
                    self._collect_entity_links("message_field", list(field_ids), affected, affected_ids)

        # 6. Run existing impact analyzer on each affected requirement for downstream
        downstream = self._get_downstream_impacts(affected_ids)

        risk = self._assess_risk(affected)

        return {
            "action": "delete_wire",
            "entity_ids": wire_ids,
            "affected_requirements": affected,
            "downstream_requirements": downstream,
            "risk_level": risk,
            "total_affected": len(affected) + len(downstream),
            "summary": {
                "direct_interface_reqs": len(affected),
                "downstream_reqs": len(downstream),
                "harnesses_affected": len(harness_ids),
                "buses_affected": len(bus_def_ids),
            },
            "action_options": [
                "delete_requirements",
                "orphan_requirements",
                "mark_for_review",
                "cancel",
            ],
        }

    # ──────────────────────────────────
    #  Bus Deletion Preview
    # ──────────────────────────────────

    def preview_bus_deletion(self, bus_def_id: int) -> dict:
        """Blast radius of deleting a bus definition."""
        affected: List[dict] = []
        affected_ids: set = set()

        # Bus-level links
        self._collect_entity_links("bus_definition", [bus_def_id], affected, affected_ids)

        # All messages on this bus
        msg_ids = [
            m[0] for m in self.db.query(MessageDefinition.id).filter(
                MessageDefinition.bus_def_id == bus_def_id
            ).all()
        ]
        if msg_ids:
            self._collect_entity_links("message_definition", msg_ids, affected, affected_ids)

            # All fields on those messages
            field_ids = [
                f[0] for f in self.db.query(MessageField.id).filter(
                    MessageField.message_id.in_(msg_ids)
                ).all()
            ]
            if field_ids:
                self._collect_entity_links("message_field", field_ids, affected, affected_ids)

        # Pin assignments that will be orphaned
        pa_count = self.db.query(func.count(PinBusAssignment.id)).filter(
            PinBusAssignment.bus_def_id == bus_def_id
        ).scalar()

        downstream = self._get_downstream_impacts(affected_ids)
        risk = self._assess_risk(affected)

        return {
            "action": "delete_bus",
            "entity_id": bus_def_id,
            "affected_requirements": affected,
            "downstream_requirements": downstream,
            "risk_level": risk,
            "total_affected": len(affected) + len(downstream),
            "summary": {
                "direct_interface_reqs": len(affected),
                "downstream_reqs": len(downstream),
                "messages_deleted": len(msg_ids),
                "fields_deleted": len(field_ids) if msg_ids else 0,
                "pin_assignments_orphaned": pa_count,
            },
            "action_options": [
                "delete_requirements",
                "orphan_requirements",
                "mark_for_review",
                "cancel",
            ],
        }

    # ──────────────────────────────────
    #  Bus Edit Preview
    # ──────────────────────────────────

    def preview_bus_edit(self, bus_def_id: int, changes: dict) -> dict:
        """
        Preview which requirements need regeneration after bus edits.

        - protocol changed → ALL message reqs need regeneration
        - data_rate changed → bus connection req statement needs update
        - bus_address changed → message req statements need update
        """
        affected: List[dict] = []
        affected_ids: set = set()
        reasons: Dict[int, List[str]] = {}  # req_id → list of change reasons

        bd = self.db.query(BusDefinition).filter(BusDefinition.id == bus_def_id).first()
        if not bd:
            return {"action": "edit_bus", "entity_id": bus_def_id,
                    "affected_requirements": [], "total_affected": 0}

        protocol_changed = "protocol" in changes and changes["protocol"] != _ev(bd.protocol)
        data_rate_changed = "data_rate" in changes or "data_rate_actual_bps" in changes
        address_changed = "bus_address" in changes

        # Bus-level links (always affected for any bus change)
        bus_links = self.db.query(InterfaceRequirementLink).filter(
            InterfaceRequirementLink.entity_type == "bus_definition",
            InterfaceRequirementLink.entity_id == bus_def_id,
        ).all()
        for lk in bus_links:
            self._add_affected_req(lk, affected, affected_ids, reasons,
                                   "Bus definition changed")
            if data_rate_changed:
                reasons.setdefault(lk.requirement_id, []).append(
                    "Data rate changed — statement needs update")

        # If protocol changed, all messages need regeneration
        if protocol_changed:
            msg_ids = [
                m[0] for m in self.db.query(MessageDefinition.id).filter(
                    MessageDefinition.bus_def_id == bus_def_id
                ).all()
            ]
            if msg_ids:
                msg_links = self.db.query(InterfaceRequirementLink).filter(
                    InterfaceRequirementLink.entity_type == "message_definition",
                    InterfaceRequirementLink.entity_id.in_(msg_ids),
                ).all()
                for lk in msg_links:
                    self._add_affected_req(lk, affected, affected_ids, reasons,
                                           "Protocol changed — message req needs regeneration")

                field_ids = [
                    f[0] for f in self.db.query(MessageField.id).filter(
                        MessageField.message_id.in_(msg_ids)
                    ).all()
                ]
                if field_ids:
                    field_links = self.db.query(InterfaceRequirementLink).filter(
                        InterfaceRequirementLink.entity_type == "message_field",
                        InterfaceRequirementLink.entity_id.in_(field_ids),
                    ).all()
                    for lk in field_links:
                        self._add_affected_req(lk, affected, affected_ids, reasons,
                                               "Protocol changed — field req needs regeneration")

        # If address changed, message reqs need statement update
        if address_changed and not protocol_changed:
            msg_links = self.db.query(InterfaceRequirementLink).filter(
                InterfaceRequirementLink.entity_type == "message_definition",
                InterfaceRequirementLink.entity_id.in_(
                    self.db.query(MessageDefinition.id).filter(
                        MessageDefinition.bus_def_id == bus_def_id
                    )
                ),
            ).all()
            for lk in msg_links:
                self._add_affected_req(lk, affected, affected_ids, reasons,
                                       "Bus address changed — message statement needs update")

        # Enrich affected items with reasons
        for item in affected:
            item["change_reasons"] = reasons.get(item["requirement_id"], [])

        risk = self._assess_risk(affected)

        return {
            "action": "edit_bus",
            "entity_id": bus_def_id,
            "changes": changes,
            "affected_requirements": affected,
            "risk_level": risk,
            "total_affected": len(affected),
            "protocol_changed": protocol_changed,
            "data_rate_changed": data_rate_changed,
            "address_changed": address_changed,
            "action_options": [
                "auto_update_statements",
                "mark_for_review",
                "cancel",
            ],
        }

    # ──────────────────────────────────
    #  Message Edit Preview
    # ──────────────────────────────────

    def preview_message_edit(self, message_id: int, changes: dict) -> dict:
        """
        Preview which requirements need update after message edits.

        - rate_hz changed → message req statement needs update
        - word_count changed → field reqs may need update
        - direction changed → message req statement needs update
        """
        affected: List[dict] = []
        affected_ids: set = set()
        reasons: Dict[int, List[str]] = {}

        msg = self.db.query(MessageDefinition).filter(
            MessageDefinition.id == message_id
        ).first()
        if not msg:
            return {"action": "edit_message", "entity_id": message_id,
                    "affected_requirements": [], "total_affected": 0}

        rate_changed = "rate_hz" in changes
        word_count_changed = "word_count" in changes
        direction_changed = "direction" in changes

        # Message-level links
        msg_links = self.db.query(InterfaceRequirementLink).filter(
            InterfaceRequirementLink.entity_type == "message_definition",
            InterfaceRequirementLink.entity_id == message_id,
        ).all()
        for lk in msg_links:
            change_list = []
            if rate_changed:
                change_list.append("Rate changed — statement needs update")
            if direction_changed:
                change_list.append("Direction changed — statement needs update")
            if word_count_changed:
                change_list.append("Word count changed — capacity may be affected")
            self._add_affected_req(lk, affected, affected_ids, reasons,
                                   "; ".join(change_list) or "Message definition changed")

        # If word_count changed, field reqs may need position updates
        if word_count_changed:
            field_ids = [
                f[0] for f in self.db.query(MessageField.id).filter(
                    MessageField.message_id == message_id
                ).all()
            ]
            if field_ids:
                field_links = self.db.query(InterfaceRequirementLink).filter(
                    InterfaceRequirementLink.entity_type == "message_field",
                    InterfaceRequirementLink.entity_id.in_(field_ids),
                ).all()
                for lk in field_links:
                    self._add_affected_req(lk, affected, affected_ids, reasons,
                                           "Word count changed — field positions may shift")

        for item in affected:
            item["change_reasons"] = reasons.get(item["requirement_id"], [])

        risk = self._assess_risk(affected)

        return {
            "action": "edit_message",
            "entity_id": message_id,
            "changes": changes,
            "affected_requirements": affected,
            "risk_level": risk,
            "total_affected": len(affected),
            "action_options": [
                "auto_update_statements",
                "mark_for_review",
                "cancel",
            ],
        }

    # ──────────────────────────────────
    #  Unit Deletion Preview (nuclear)
    # ──────────────────────────────────

    def preview_unit_deletion(self, unit_id: int) -> dict:
        """
        Full blast radius of deleting a unit — the nuclear option.

        Finds EVERYTHING:
          1. All connectors → all pins → all wires → all harnesses
          2. All bus definitions → all messages → all fields
          3. All environmental specs
          4. ALL requirements linked to any of the above
          5. Downstream requirements via existing impact analyzer
        """
        affected: List[dict] = []
        affected_ids: set = set()

        unit = self.db.query(Unit).filter(Unit.id == unit_id).first()
        if not unit:
            return {"action": "delete_unit", "entity_id": unit_id,
                    "affected_requirements": [], "total_affected": 0}

        # Unit-level links
        self._collect_entity_links("unit", [unit_id], affected, affected_ids)

        # Connectors → pins
        connector_ids = [
            c[0] for c in self.db.query(Connector.id).filter(
                Connector.unit_id == unit_id
            ).all()
        ]
        pin_ids = []
        if connector_ids:
            self._collect_entity_links("connector", connector_ids, affected, affected_ids)
            pin_ids = [
                p[0] for p in self.db.query(Pin.id).filter(
                    Pin.connector_id.in_(connector_ids)
                ).all()
            ]
            if pin_ids:
                self._collect_entity_links("pin", pin_ids, affected, affected_ids)

        # Wires connected to any pin on this unit
        wire_ids = set()
        if pin_ids:
            wires = self.db.query(Wire.id).filter(
                (Wire.from_pin_id.in_(pin_ids)) | (Wire.to_pin_id.in_(pin_ids))
            ).all()
            wire_ids = {w[0] for w in wires}
            if wire_ids:
                self._collect_entity_links("wire", list(wire_ids), affected, affected_ids)

        # Harnesses involving this unit
        harness_ids = set()
        harnesses = self.db.query(WireHarness).filter(
            (WireHarness.from_unit_id == unit_id) | (WireHarness.to_unit_id == unit_id)
        ).all()
        for h in harnesses:
            harness_ids.add(h.id)
        if harness_ids:
            self._collect_entity_links("wire_harness", list(harness_ids), affected, affected_ids)

        # Bus definitions → messages → fields
        bus_def_ids = [
            b[0] for b in self.db.query(BusDefinition.id).filter(
                BusDefinition.unit_id == unit_id
            ).all()
        ]
        msg_ids = []
        field_ids = []
        if bus_def_ids:
            self._collect_entity_links("bus_definition", bus_def_ids, affected, affected_ids)
            msg_ids = [
                m[0] for m in self.db.query(MessageDefinition.id).filter(
                    MessageDefinition.bus_def_id.in_(bus_def_ids)
                ).all()
            ]
            if msg_ids:
                self._collect_entity_links("message_definition", msg_ids, affected, affected_ids)
                field_ids = [
                    f[0] for f in self.db.query(MessageField.id).filter(
                        MessageField.message_id.in_(msg_ids)
                    ).all()
                ]
                if field_ids:
                    self._collect_entity_links("message_field", field_ids, affected, affected_ids)

        # Environmental specs
        env_count = self.db.query(func.count(UnitEnvironmentalSpec.id)).filter(
            UnitEnvironmentalSpec.unit_id == unit_id
        ).scalar()

        # Downstream via existing impact analyzer
        downstream = self._get_downstream_impacts(affected_ids)

        risk = self._assess_risk(affected)
        # Unit deletion is always at least medium risk
        if risk == "low" and affected:
            risk = "medium"

        return {
            "action": "delete_unit",
            "entity_id": unit_id,
            "unit_designation": unit.designation,
            "unit_name": unit.name,
            "affected_requirements": affected,
            "downstream_requirements": downstream,
            "risk_level": risk,
            "total_affected": len(affected) + len(downstream),
            "summary": {
                "direct_interface_reqs": len(affected),
                "downstream_reqs": len(downstream),
                "connectors": len(connector_ids),
                "pins": len(pin_ids),
                "wires": len(wire_ids),
                "harnesses": len(harness_ids),
                "bus_definitions": len(bus_def_ids),
                "messages": len(msg_ids),
                "fields": len(field_ids),
                "environmental_specs": env_count,
            },
            "action_options": [
                "delete_requirements",
                "orphan_requirements",
                "mark_for_review",
                "cancel",
            ],
        }

    # ──────────────────────────────────
    #  Execute Action
    # ──────────────────────────────────

    def execute_action(
        self,
        affected_req_ids: List[int],
        action: str,
        user: User,
        project_id: Optional[int] = None,
        change_description: str = "",
    ) -> dict:
        """
        Apply user's chosen resolution to affected requirements.

        Actions:
          delete_requirements  — soft-delete requirements, record history
          orphan_requirements  — remove InterfaceRequirementLinks, keep reqs
          mark_for_review      — set status to under_review, record history
        """
        if action not in ("delete_requirements", "orphan_requirements", "mark_for_review"):
            return {"error": f"Unknown action: {action}", "processed": 0}

        processed = 0
        for req_id in affected_req_ids:
            req = self.db.query(Requirement).filter(Requirement.id == req_id).first()
            if not req:
                continue

            if action == "delete_requirements":
                old_status = _ev(req.status)
                req.status = "deleted"
                req.version = (req.version or 1) + 1
                self._record_history(
                    req, "status", old_status, "deleted",
                    f"Auto-deleted: source interface entity removed. {change_description}",
                    user.id,
                )
                processed += 1

            elif action == "orphan_requirements":
                deleted_count = self.db.query(InterfaceRequirementLink).filter(
                    InterfaceRequirementLink.requirement_id == req_id,
                    InterfaceRequirementLink.auto_generated.is_(True),
                ).delete()
                if deleted_count > 0:
                    self._record_history(
                        req, "interface_link", "linked", "orphaned",
                        f"Interface link(s) removed; requirement preserved. {change_description}",
                        user.id,
                    )
                processed += 1

            elif action == "mark_for_review":
                old_status = _ev(req.status)
                if old_status != "under_review":
                    req.status = "under_review"
                    req.version = (req.version or 1) + 1
                    self._record_history(
                        req, "status", old_status, "under_review",
                        f"Flagged for review: interface entity changed. {change_description}",
                        user.id,
                    )
                processed += 1

        # Log the change impact
        if project_id:
            impact_log = InterfaceChangeImpact(
                project_id=project_id,
                change_type=action,
                entity_type="bulk_action",
                entity_description=change_description[:255],
                affected_requirements={
                    "req_ids": affected_req_ids,
                    "action": action,
                },
                risk_level="medium",
                total_affected=len(affected_req_ids),
                user_action=action,
                resolved=True,
                resolved_at=datetime.utcnow(),
                user_id=user.id,
            )
            self.db.add(impact_log)

        self.db.flush()

        return {
            "action": action,
            "processed": processed,
            "total_requested": len(affected_req_ids),
        }

    # ══════════════════════════════════════
    #  Private helpers
    # ══════════════════════════════════════

    def _collect_entity_links(
        self,
        entity_type: str,
        entity_ids: List[int],
        affected: List[dict],
        affected_ids: set,
    ):
        """Find all InterfaceRequirementLinks for the given entities and add to affected list."""
        links = self.db.query(InterfaceRequirementLink).filter(
            InterfaceRequirementLink.entity_type == entity_type,
            InterfaceRequirementLink.entity_id.in_(entity_ids),
        ).all()

        for lk in links:
            if lk.requirement_id in affected_ids:
                continue
            req = self.db.query(Requirement).filter(
                Requirement.id == lk.requirement_id
            ).first()
            if not req:
                continue

            affected_ids.add(req.id)
            affected.append({
                "requirement_id": req.id,
                "req_id": req.req_id,
                "title": req.title,
                "level": _ev(req.level),
                "status": _ev(req.status),
                "priority": _ev(req.priority),
                "link_type": _ev(lk.link_type),
                "entity_type": entity_type,
                "entity_id": lk.entity_id,
                "auto_generated": lk.auto_generated,
                "template": lk.auto_req_template,
            })

    def _add_affected_req(
        self,
        link: InterfaceRequirementLink,
        affected: List[dict],
        affected_ids: set,
        reasons: Dict[int, List[str]],
        reason: str,
    ):
        """Add a single requirement from a link to the affected list."""
        if link.requirement_id in affected_ids:
            reasons.setdefault(link.requirement_id, []).append(reason)
            return
        req = self.db.query(Requirement).filter(
            Requirement.id == link.requirement_id
        ).first()
        if not req:
            return

        affected_ids.add(req.id)
        reasons.setdefault(req.id, []).append(reason)
        affected.append({
            "requirement_id": req.id,
            "req_id": req.req_id,
            "title": req.title,
            "level": _ev(req.level),
            "status": _ev(req.status),
            "priority": _ev(req.priority),
            "link_type": _ev(link.link_type),
            "entity_type": _ev(link.entity_type),
            "entity_id": link.entity_id,
            "auto_generated": link.auto_generated,
            "template": link.auto_req_template,
        })

    def _get_downstream_impacts(self, affected_req_ids: set) -> List[dict]:
        """
        For each affected requirement, find downstream children and
        verifications using ASTRA's existing impact engine.
        """
        downstream = []
        seen_ids: set = set()

        try:
            from app.services.ai.impact_analyzer import preview_what_if
        except ImportError:
            logger.debug("Existing impact analyzer not available; skipping downstream traversal")
            return downstream

        for req_id in affected_req_ids:
            req = self.db.query(Requirement).filter(Requirement.id == req_id).first()
            if not req:
                continue

            try:
                preview = preview_what_if(req_id, "modify", self.db)
                for item in preview.affected_items:
                    if item.entity_id not in seen_ids and item.entity_id not in affected_req_ids:
                        seen_ids.add(item.entity_id)
                        downstream.append({
                            "requirement_id": item.entity_id,
                            "entity_type": item.entity_type,
                            "title": item.entity_title,
                            "hop_count": item.hop_count,
                            "impact_level": item.impact_level,
                            "via_requirement": req.req_id,
                        })
            except Exception as e:
                logger.warning(f"Downstream traversal failed for req {req_id}: {e}")

        return downstream

    def _assess_risk(self, affected: List[dict]) -> str:
        """Classify risk based on affected requirements' levels and priorities."""
        if not affected:
            return "none"

        levels = {a.get("level", "L5") for a in affected}
        priorities = {a.get("priority", "low") for a in affected}
        statuses = {a.get("status", "draft") for a in affected}

        # Critical if any L1/L2 or safety/mission-critical
        if levels & _CRITICAL_LEVELS or priorities & _HIGH_PRIORITY:
            return "critical"

        # High if L3 or baselined/verified requirements
        if levels & _HIGH_LEVELS or statuses & {"baselined", "verified", "validated"}:
            return "high"

        # Medium if more than 5 requirements affected or any approved
        if len(affected) > 5 or "approved" in statuses:
            return "medium"

        return "low"

    def _record_history(self, req: Requirement, field: str,
                        old_val: str, new_val: str, desc: str, user_id: int):
        """Record a history entry for the requirement."""
        hist = RequirementHistory(
            requirement_id=req.id,
            version=req.version or 1,
            field_changed=field,
            old_value=old_val,
            new_value=new_val,
            changed_by_id=user_id,
            change_description=desc[:500],
        )
        self.db.add(hist)
