"""
ASTRA — Interface Control Document (ICD) Router
====================================================
File: backend/app/routers/interface.py
Path: C:\\Users\\Mason\\Documents\\ASTRA\\backend\\app\\routers\\interface.py

Phase 1: Systems, Units, Connectors, Pins
Phase 2: Buses, Messages, Fields, Harnesses, Wires,
         Signal Trace, N² Matrix, Block Diagram,
         Requirement Links, Coverage
"""

import re
import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func

from app.database import get_db
from app.dependencies.project_access import _check_membership
from app.models import (
    User, Project, RequirementHistory, TraceLink,
)
from app.models.interface import (
    System, Unit, Connector, Pin, BusDefinition,
    PinBusAssignment, MessageDefinition, MessageField,
    WireHarness, Wire, Interface,
    UnitEnvironmentalSpec, InterfaceRequirementLink,
    AutoRequirementLog, InterfaceChangeImpact,
    HarnessEndpoint, Connection,
)
from app.models import Requirement
from app.schemas.interface import (
    # Systems
    SystemCreate, SystemUpdate, SystemResponse, SystemDetail,
    # Units
    UnitCreate, UnitUpdate, UnitSummary, UnitResponse, UnitDetail,
    # Connectors
    ConnectorCreate, ConnectorUpdate, ConnectorResponse, ConnectorWithPins,
    # Pins
    PinCreate, PinUpdate, PinBatchCreate, PinResponse,
    # Bus
    PinBusAssignmentCreate, PinBusAssignmentResponse,
    BusDefinitionCreate, BusDefinitionUpdate, BusDefinitionResponse,
    BusWithMessages, MessageSummary,
    # Messages + Fields
    MessageDefinitionCreate, MessageDefinitionUpdate, MessageDefinitionResponse,
    MessageWithFields,
    MessageFieldCreate, MessageFieldUpdate, MessageFieldBatchCreate, MessageFieldResponse,
    # Harnesses + Wires
    WireHarnessCreate, WireHarnessUpdate, WireHarnessResponse, WireHarnessDetail,
    WireCreate, WireUpdate, WireBatchCreate, WireResponse,
    # Phase 1/2: multi-endpoint harness + connections + auto-grow
    HarnessEndpointCreate, HarnessEndpointUpdate, HarnessEndpointResponse,
    ConnectionResponse, ConnectionDetail,
    AutoGrowPair as AutoGrowPairSchema,
    AmbiguityDecision as AmbiguityDecisionSchema,
    AutoGrowRequest, AutoGrowAmbiguity as AutoGrowAmbiguitySchema,
    AutoGrowResult as AutoGrowResultSchema,
    # Interfaces
    InterfaceCreate, InterfaceUpdate, InterfaceResponse,
    # Requirement links
    InterfaceReqLinkCreate, InterfaceReqLinkUpdate, InterfaceReqLinkResponse,
    # Environmental
    EnvironmentalSpecResponse,
    # Aggregates
    SignalTraceHop, SignalTraceResult,
    N2MatrixCell, N2MatrixResponse,
    BlockDiagramNode, BlockDiagramEdge, BlockDiagramResponse,
    InterfaceCoverageResponse,
    ImpactPreview,
)
from app.services.auth import get_current_user

# Optional audit
try:
    from app.services.audit_service import record_event as _audit
except ImportError:
    def _audit(*a, **kw):
        pass

# Optional RBAC
try:
    from app.services.rbac import require_permission
except ImportError:
    def require_permission(action):
        return get_current_user

logger = logging.getLogger("astra.interface")

router = APIRouter(prefix="/interfaces", tags=["Interface Management"])

class AutoReqApproveRequest(BaseModel):
    requirement_ids: List[int]


class AutoReqRejectRequest(BaseModel):
    requirement_ids: List[int]
    reason: Optional[str] = None

# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════

def _ev(v) -> str:
    """Enum-safe value extraction."""
    return v.value if hasattr(v, "value") else str(v) if v else ""


def _next_id(db: Session, model, project_id: int, prefix: str, id_field: str) -> str:
    """Generate next auto-ID: PREFIX-{N:03d}"""
    max_row = (
        db.query(model)
        .filter(model.project_id == project_id)
        .order_by(model.id.desc())
        .first()
    )
    if max_row:
        existing_id = getattr(max_row, id_field, "") or ""
        match = re.search(r"(\d+)$", existing_id)
        next_num = (int(match.group(1)) + 1) if match else 1
    else:
        next_num = 1
    return f"{prefix}-{next_num:03d}"


def _require_project(db: Session, project_id: int, current_user: User) -> Project:
    """
    Validate project exists AND the caller is a member (or owner / admin).

    Raises 404 on missing project, 403 on non-member.
    AUDIT_FINDINGS F-014: every interface endpoint that takes a project_id
    in path/query/body funnels through this helper.
    """
    return _check_membership(db, project_id, current_user)


def _assert_member_for_entity(db: Session, current_user: User, entity) -> None:
    """
    Inline membership check for endpoints keyed by entity primary key
    (system_pk, unit_pk, conn_pk, etc.). Pulls project_id off the entity
    and asserts the caller is a member. Raises 403 on non-member.

    Use this at the top of every entity-keyed handler immediately after
    the entity has been loaded (and a 404 has been raised if missing).

    For entities that don't carry project_id directly (Pin, MessageField,
    Wire, HarnessEndpoint, PinBusAssignment), this helper walks the
    one-step parent chain to resolve project_id.
    """
    pid = getattr(entity, "project_id", None)

    if pid is None:
        # Walk the parent chain for entities that don't carry project_id
        # on their own row.
        if isinstance(entity, Pin):
            row = db.query(Connector.project_id).filter(
                Connector.id == entity.connector_id
            ).first()
            pid = row[0] if row else None
        elif isinstance(entity, MessageField):
            row = db.query(MessageDefinition.project_id).filter(
                MessageDefinition.id == entity.message_id
            ).first()
            pid = row[0] if row else None
        elif isinstance(entity, Wire):
            row = db.query(WireHarness.project_id).filter(
                WireHarness.id == entity.harness_id
            ).first()
            pid = row[0] if row else None
        elif isinstance(entity, HarnessEndpoint):
            row = db.query(WireHarness.project_id).filter(
                WireHarness.id == entity.harness_id
            ).first()
            pid = row[0] if row else None
        elif isinstance(entity, PinBusAssignment):
            row = db.query(BusDefinition.project_id).filter(
                BusDefinition.id == entity.bus_def_id
            ).first()
            pid = row[0] if row else None

    if pid is None:
        # Caller passed an unsupported entity type — fail loudly so this
        # gets noticed in dev rather than silently skipping the check.
        raise HTTPException(
            500,
            f"_assert_member_for_entity: cannot resolve project_id for "
            f"entity ({type(entity).__name__})",
        )
    _check_membership(db, pid, current_user)


# ══════════════════════════════════════════════════════════════
#  SYSTEMS
# ══════════════════════════════════════════════════════════════

@router.get("/systems", response_model=List[SystemResponse])
def list_systems(
    project_id: int,
    mode: str = Query("flat", regex="^(flat|tree)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all systems for a project.  mode=flat (default) or tree."""
    _require_project(db, project_id, current_user)
    query = db.query(System).filter(System.project_id == project_id)

    if mode == "tree":
        # Return only root-level systems; children are loaded via relationship
        query = query.filter(System.parent_system_id.is_(None))

    systems = query.order_by(System.name).all()
    results = []
    for s in systems:
        unit_count = db.query(func.count(Unit.id)).filter(Unit.system_id == s.id).scalar()
        iface_count = db.query(func.count(Interface.id)).filter(
            (Interface.source_system_id == s.id) | (Interface.target_system_id == s.id)
        ).scalar()
        resp = SystemResponse.model_validate(s)
        resp.unit_count = unit_count
        resp.interface_count = iface_count
        results.append(resp)
    return results


@router.post("/systems", response_model=SystemResponse, status_code=201)
def create_system(
    data: SystemCreate,
    project_id: int = Query(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    _require_project(db, project_id, current_user)
    system_id = _next_id(db, System, project_id, "SYS", "system_id")

    system = System(
        system_id=system_id,
        project_id=project_id,
        owner_id=current_user.id,
        **data.model_dump(exclude_unset=True),
    )
    db.add(system)
    db.commit()
    db.refresh(system)

    _audit(db, "system.created", "system", system.id, current_user.id,
           {"system_id": system_id, "name": data.name, "type": data.system_type},
           project_id=project_id, request=request)

    resp = SystemResponse.model_validate(system)
    resp.unit_count = 0
    resp.interface_count = 0
    return resp


@router.get("/systems/{system_pk}", response_model=SystemDetail)
def get_system(
    system_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    system = db.query(System).filter(System.id == system_pk).first()
    if not system:
        raise HTTPException(404, "System not found")
    _assert_member_for_entity(db, current_user, system)

    units = db.query(Unit).filter(Unit.system_id == system.id).order_by(Unit.designation).all()
    unit_summaries = []
    for u in units:
        conn_count = db.query(func.count(Connector.id)).filter(Connector.unit_id == u.id).scalar()
        bus_count = db.query(func.count(BusDefinition.id)).filter(BusDefinition.unit_id == u.id).scalar()
        us = UnitSummary.model_validate(u)
        us.connector_count = conn_count
        us.bus_count = bus_count
        unit_summaries.append(us)

    unit_count = len(unit_summaries)
    iface_count = db.query(func.count(Interface.id)).filter(
        (Interface.source_system_id == system.id) | (Interface.target_system_id == system.id)
    ).scalar()

    resp = SystemDetail.model_validate(system)
    resp.unit_count = unit_count
    resp.interface_count = iface_count
    resp.units = unit_summaries
    return resp


@router.patch("/systems/{system_pk}", response_model=SystemResponse)
def update_system(
    system_pk: int,
    data: SystemUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.update")),
):
    system = db.query(System).filter(System.id == system_pk).first()
    if not system:
        raise HTTPException(404, "System not found")
    _assert_member_for_entity(db, current_user, system)

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(system, field, value)
    system.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(system)

    _audit(db, "system.updated", "system", system.id, current_user.id,
           {"fields": list(updates.keys())},
           project_id=system.project_id, request=request)

    unit_count = db.query(func.count(Unit.id)).filter(Unit.system_id == system.id).scalar()
    iface_count = db.query(func.count(Interface.id)).filter(
        (Interface.source_system_id == system.id) | (Interface.target_system_id == system.id)
    ).scalar()
    resp = SystemResponse.model_validate(system)
    resp.unit_count = unit_count
    resp.interface_count = iface_count
    return resp


@router.delete("/systems/{system_pk}", status_code=200)
def delete_system(
    system_pk: int,
    force: bool = Query(False),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    system = db.query(System).filter(System.id == system_pk).first()
    if not system:
        raise HTTPException(404, "System not found")
    _assert_member_for_entity(db, current_user, system)

    unit_count = db.query(func.count(Unit.id)).filter(Unit.system_id == system.id).scalar()

    if unit_count > 0 and not force:
        raise HTTPException(
            409,
            f"System has {unit_count} unit(s). Use force=true to cascade delete.",
        )

    if unit_count > 0 and force:
        # Cascade: delete units and all their children
        units = db.query(Unit).filter(Unit.system_id == system.id).all()
        for u in units:
            _cascade_delete_unit(db, u)

    _audit(db, "system.deleted", "system", system.id, current_user.id,
           {"system_id": system.system_id, "force": force, "units_deleted": unit_count},
           project_id=system.project_id, request=request)

    db.delete(system)
    db.commit()
    return {"status": "deleted", "id": system_pk, "units_deleted": unit_count}


# ══════════════════════════════════════════════════════════════
#  UNITS
# ══════════════════════════════════════════════════════════════

@router.get("/units", response_model=List[UnitSummary])
def list_units(
    project_id: int,
    system_id: Optional[int] = None,
    unit_type: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_project(db, project_id, current_user)
    query = db.query(Unit).filter(Unit.project_id == project_id)

    if system_id:
        query = query.filter(Unit.system_id == system_id)
    if unit_type:
        query = query.filter(Unit.unit_type == unit_type)
    if search:
        t = f"%{search}%"
        query = query.filter(
            Unit.name.ilike(t) | Unit.designation.ilike(t) | Unit.part_number.ilike(t)
        )

    units = query.order_by(Unit.designation).offset(skip).limit(limit).all()
    results = []
    for u in units:
        conn_count = db.query(func.count(Connector.id)).filter(Connector.unit_id == u.id).scalar()
        bus_count = db.query(func.count(BusDefinition.id)).filter(BusDefinition.unit_id == u.id).scalar()
        s = UnitSummary.model_validate(u)
        s.connector_count = conn_count
        s.bus_count = bus_count
        results.append(s)
    return results


@router.post("/units", response_model=UnitResponse, status_code=201)
def create_unit(
    data: UnitCreate,
    project_id: int = Query(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    _require_project(db, project_id, current_user)

    # Validate unique designation within project
    existing = db.query(Unit).filter(
        Unit.project_id == project_id, Unit.designation == data.designation
    ).first()
    if existing:
        raise HTTPException(409, f"Designation '{data.designation}' already exists in this project")

    # Validate system exists
    sys_obj = db.query(System).filter(System.id == data.system_id).first()
    if not sys_obj:
        raise HTTPException(404, f"System {data.system_id} not found")

    unit_id = _next_id(db, Unit, project_id, "UNIT", "unit_id")

    unit = Unit(
        unit_id=unit_id,
        project_id=project_id,
        **data.model_dump(exclude_unset=True),
    )
    db.add(unit)
    db.commit()
    db.refresh(unit)

    _audit(db, "unit.created", "unit", unit.id, current_user.id,
           {"unit_id": unit_id, "designation": data.designation, "type": data.unit_type},
           project_id=project_id, request=request)

    resp = UnitResponse.model_validate(unit)
    resp.connector_count = 0
    resp.bus_count = 0
    resp.message_count = 0
    return resp


@router.get("/units/{unit_pk}", response_model=UnitDetail)
def get_unit(
    unit_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    unit = db.query(Unit).filter(Unit.id == unit_pk).first()
    if not unit:
        raise HTTPException(404, "Unit not found")
    _assert_member_for_entity(db, current_user, unit)

    # Connectors with pins
    connectors = db.query(Connector).filter(Connector.unit_id == unit.id).order_by(Connector.designator).all()
    connector_list = []
    total_pin_count = 0
    for c in connectors:
        pins = db.query(Pin).filter(Pin.connector_id == c.id).order_by(Pin.pin_number).all()
        pin_responses = []
        for p in pins:
            pr = PinResponse.model_validate(p)
            # Load bus assignment if exists
            assignment = db.query(PinBusAssignment).filter(PinBusAssignment.pin_id == p.id).first()
            if assignment:
                pr.bus_assignment = PinBusAssignmentResponse.model_validate(assignment)
            _populate_pin_mating(db, pr, p)
            pin_responses.append(pr)
        total_pin_count += len(pin_responses)

        assigned_count = db.query(func.count(PinBusAssignment.id)).join(Pin).filter(
            Pin.connector_id == c.id
        ).scalar()

        cwp = ConnectorWithPins.model_validate(c)
        cwp.pins = pin_responses
        cwp.pin_count = len(pin_responses)
        cwp.assigned_pin_count = assigned_count
        connector_list.append(cwp)

    # Bus definitions with messages
    bus_defs = db.query(BusDefinition).filter(BusDefinition.unit_id == unit.id).all()
    bus_list = []
    total_msg_count = 0
    for bd in bus_defs:
        messages = db.query(MessageDefinition).filter(MessageDefinition.bus_def_id == bd.id).all()
        msg_summaries = []
        for m in messages:
            field_count = db.query(func.count(MessageField.id)).filter(
                MessageField.message_id == m.id
            ).scalar()
            ms = MessageSummary.model_validate(m)
            ms.field_count = field_count
            msg_summaries.append(ms)
        total_msg_count += len(msg_summaries)

        pin_assignments = db.query(PinBusAssignment).filter(
            PinBusAssignment.bus_def_id == bd.id
        ).all()
        pa_list = []
        for pa in pin_assignments:
            par = PinBusAssignmentResponse.model_validate(pa)
            pin = db.query(Pin).filter(Pin.id == pa.pin_id).first()
            if pin:
                par.pin_number = pin.pin_number
                par.signal_name = pin.signal_name
                conn = db.query(Connector).filter(Connector.id == pin.connector_id).first()
                if conn:
                    par.connector_designator = conn.designator
            pa_list.append(par)

        bwm = BusWithMessages.model_validate(bd)
        bwm.messages = msg_summaries
        bwm.message_count = len(msg_summaries)
        bwm.pin_assignments = pa_list
        bwm.pin_assignment_count = len(pa_list)
        bus_list.append(bwm)

    # Environmental specs
    env_specs = db.query(UnitEnvironmentalSpec).filter(
        UnitEnvironmentalSpec.unit_id == unit.id
    ).order_by(UnitEnvironmentalSpec.category).all()
    env_list = [EnvironmentalSpecResponse.model_validate(e) for e in env_specs]

    resp = UnitDetail.model_validate(unit)
    resp.connector_count = len(connector_list)
    resp.bus_count = len(bus_list)
    resp.message_count = total_msg_count
    resp.connectors = connector_list
    resp.bus_definitions = bus_list
    resp.environmental_specs = env_list
    return resp


@router.patch("/units/{unit_pk}", response_model=UnitResponse)
def update_unit(
    unit_pk: int,
    data: UnitUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.update")),
):
    unit = db.query(Unit).filter(Unit.id == unit_pk).first()
    if not unit:
        raise HTTPException(404, "Unit not found")
    _assert_member_for_entity(db, current_user, unit)

    updates = data.model_dump(exclude_unset=True)

    # Validate designation uniqueness if changing
    if "designation" in updates and updates["designation"] != unit.designation:
        dup = db.query(Unit).filter(
            Unit.project_id == unit.project_id,
            Unit.designation == updates["designation"],
            Unit.id != unit.id,
        ).first()
        if dup:
            raise HTTPException(409, f"Designation '{updates['designation']}' already exists")

    for field, value in updates.items():
        setattr(unit, field, value)
    unit.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(unit)

    _audit(db, "unit.updated", "unit", unit.id, current_user.id,
           {"fields": list(updates.keys())},
           project_id=unit.project_id, request=request)

    conn_count = db.query(func.count(Connector.id)).filter(Connector.unit_id == unit.id).scalar()
    bus_count = db.query(func.count(BusDefinition.id)).filter(BusDefinition.unit_id == unit.id).scalar()
    msg_count = db.query(func.count(MessageDefinition.id)).join(BusDefinition).filter(
        BusDefinition.unit_id == unit.id
    ).scalar()

    resp = UnitResponse.model_validate(unit)
    resp.connector_count = conn_count
    resp.bus_count = bus_count
    resp.message_count = msg_count
    return resp


@router.delete("/units/{unit_pk}", status_code=200)
def delete_unit(
    unit_pk: int,
    confirm: bool = Query(False),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    unit = db.query(Unit).filter(Unit.id == unit_pk).first()
    if not unit:
        raise HTTPException(404, "Unit not found")
    _assert_member_for_entity(db, current_user, unit)

    # Impact preview
    conn_count = db.query(func.count(Connector.id)).filter(Connector.unit_id == unit.id).scalar()
    bus_count = db.query(func.count(BusDefinition.id)).filter(BusDefinition.unit_id == unit.id).scalar()
    pin_count = db.query(func.count(Pin.id)).join(Connector).filter(Connector.unit_id == unit.id).scalar()
    wire_count = (
        db.query(func.count(Wire.id))
        .join(Pin, Wire.from_pin_id == Pin.id)
        .join(Connector)
        .filter(Connector.unit_id == unit.id)
        .scalar()
    )

    if not confirm:
        return {
            "status": "preview",
            "message": "Use confirm=true to proceed with deletion",
            "impact": {
                "connectors": conn_count,
                "pins": pin_count,
                "bus_definitions": bus_count,
                "wires_affected": wire_count,
            },
        }

    _audit(db, "unit.deleted", "unit", unit.id, current_user.id,
           {"unit_id": unit.unit_id, "designation": unit.designation},
           project_id=unit.project_id, request=request)

    _cascade_delete_unit(db, unit)
    db.commit()

    return {
        "status": "deleted",
        "id": unit_pk,
        "cascade": {
            "connectors": conn_count,
            "pins": pin_count,
            "bus_definitions": bus_count,
        },
    }


@router.get("/units/{unit_pk}/specifications")
def get_unit_specifications(
    unit_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return environmental/EMI specs grouped by category."""
    unit = db.query(Unit).filter(Unit.id == unit_pk).first()
    if not unit:
        raise HTTPException(404, "Unit not found")
    _assert_member_for_entity(db, current_user, unit)

    specs = db.query(UnitEnvironmentalSpec).filter(
        UnitEnvironmentalSpec.unit_id == unit.id
    ).order_by(UnitEnvironmentalSpec.category).all()

    grouped: dict = {}
    for s in specs:
        cat = _ev(s.category)
        # Group into high-level categories
        if cat.startswith("temperature") or cat.startswith("thermal"):
            group = "thermal"
        elif cat.startswith("vibration") or cat.startswith("shock") or cat.startswith("acceleration") or cat.startswith("acoustic"):
            group = "mechanical"
        elif cat.startswith("emi_ce") or cat.startswith("emi_re"):
            group = "emi_emissions"
        elif cat.startswith("emi_cs") or cat.startswith("emi_rs"):
            group = "emi_susceptibility"
        elif cat.startswith("esd") or cat.startswith("lightning") or cat.startswith("emp"):
            group = "transient_protection"
        elif cat.startswith("radiation"):
            group = "radiation"
        else:
            group = "environmental"

        if group not in grouped:
            grouped[group] = []
        grouped[group].append(EnvironmentalSpecResponse.model_validate(s))

    return {
        "unit_id": unit.id,
        "designation": unit.designation,
        "specifications": grouped,
        "total_specs": len(specs),
    }


def _cascade_delete_unit(db: Session, unit: Unit):
    """Delete a unit and all its dependent records."""
    # Delete environmental specs
    db.query(UnitEnvironmentalSpec).filter(UnitEnvironmentalSpec.unit_id == unit.id).delete()

    # Delete bus definitions → pin_assignments + messages → fields
    bus_defs = db.query(BusDefinition).filter(BusDefinition.unit_id == unit.id).all()
    for bd in bus_defs:
        db.query(PinBusAssignment).filter(PinBusAssignment.bus_def_id == bd.id).delete()
        msgs = db.query(MessageDefinition).filter(MessageDefinition.bus_def_id == bd.id).all()
        for m in msgs:
            db.query(MessageField).filter(MessageField.message_id == m.id).delete()
            db.delete(m)
        db.delete(bd)

    # Delete connectors → pins
    connectors = db.query(Connector).filter(Connector.unit_id == unit.id).all()
    for c in connectors:
        db.query(Pin).filter(Pin.connector_id == c.id).delete()
        db.delete(c)

    # Mark auto-generated requirement links as orphaned
    db.query(InterfaceRequirementLink).filter(
        InterfaceRequirementLink.entity_type == "unit",
        InterfaceRequirementLink.entity_id == unit.id,
    ).delete()

    db.delete(unit)


# ══════════════════════════════════════════════════════════════
#  CONNECTORS
# ══════════════════════════════════════════════════════════════

@router.get("/connectors", response_model=List[ConnectorResponse])
def list_connectors(
    unit_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    unit = db.query(Unit).filter(Unit.id == unit_id).first()
    if not unit:
        raise HTTPException(404, "Unit not found")

    connectors = db.query(Connector).filter(Connector.unit_id == unit_id).order_by(Connector.designator).all()
    results = []
    for c in connectors:
        pin_count = db.query(func.count(Pin.id)).filter(Pin.connector_id == c.id).scalar()
        assigned_count = db.query(func.count(PinBusAssignment.id)).join(Pin).filter(
            Pin.connector_id == c.id
        ).scalar()
        resp = ConnectorResponse.model_validate(c)
        resp.pin_count = pin_count
        resp.assigned_pin_count = assigned_count
        results.append(resp)
    return results


@router.post("/connectors", status_code=201)
def create_connector(
    data: ConnectorCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    unit = db.query(Unit).filter(Unit.id == data.unit_id).first()
    if not unit:
        raise HTTPException(404, f"Unit {data.unit_id} not found")

    # Validate unique designator within unit
    existing = db.query(Connector).filter(
        Connector.unit_id == data.unit_id, Connector.designator == data.designator
    ).first()
    if existing:
        raise HTTPException(409, f"Designator '{data.designator}' already exists on unit {data.unit_id}")

    connector_id = _next_id(db, Connector, unit.project_id, "CONN", "connector_id")

    # Separate pins payload from connector data
    pins_data = data.pins
    conn_fields = data.model_dump(exclude_unset=True, exclude={"pins"})

    connector = Connector(
        connector_id=connector_id,
        project_id=unit.project_id,
        **conn_fields,
    )
    db.add(connector)
    db.flush()  # Get connector.id for pins

    # Batch create pins if included
    created_pins = []
    if pins_data:
        _validate_pin_numbers(pins_data)
        for pin_data in pins_data:
            pin = Pin(
                connector_id=connector.id,
                **pin_data.model_dump(exclude_unset=True),
            )
            db.add(pin)
            created_pins.append(pin)

    db.commit()
    db.refresh(connector)

    _audit(db, "connector.created", "connector", connector.id, current_user.id,
           {"connector_id": connector_id, "designator": data.designator,
            "pins_created": len(created_pins)},
           project_id=unit.project_id, request=request)

    if created_pins:
        # Refresh pins and return ConnectorWithPins
        for p in created_pins:
            db.refresh(p)
        pin_responses = []
        for p in created_pins:
            pr = PinResponse.model_validate(p)
            _populate_pin_mating(db, pr, p)
            pin_responses.append(pr)
        resp = ConnectorWithPins.model_validate(connector)
        resp.pins = pin_responses
        resp.pin_count = len(pin_responses)
        resp.assigned_pin_count = 0
        return resp
    else:
        resp = ConnectorResponse.model_validate(connector)
        resp.pin_count = 0
        resp.assigned_pin_count = 0
        return resp


@router.get("/connectors/{conn_pk}", response_model=ConnectorWithPins)
def get_connector(
    conn_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    connector = db.query(Connector).filter(Connector.id == conn_pk).first()
    if not connector:
        raise HTTPException(404, "Connector not found")
    _assert_member_for_entity(db, current_user, connector)

    pins = db.query(Pin).filter(Pin.connector_id == conn_pk).order_by(Pin.pin_number).all()
    pin_responses = []
    for p in pins:
        pr = PinResponse.model_validate(p)
        assignment = db.query(PinBusAssignment).filter(PinBusAssignment.pin_id == p.id).first()
        if assignment:
            pr.bus_assignment = PinBusAssignmentResponse.model_validate(assignment)
        _populate_pin_mating(db, pr, p)
        pin_responses.append(pr)

    assigned_count = db.query(func.count(PinBusAssignment.id)).join(Pin).filter(
        Pin.connector_id == conn_pk
    ).scalar()

    resp = ConnectorWithPins.model_validate(connector)
    resp.pins = pin_responses
    resp.pin_count = len(pin_responses)
    resp.assigned_pin_count = assigned_count
    return resp


@router.get("/connectors/{conn_pk}/pinout")
def get_connector_pinout(
    conn_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Structured pinout data optimized for table/diagram rendering."""
    connector = db.query(Connector).filter(Connector.id == conn_pk).first()
    if not connector:
        raise HTTPException(404, "Connector not found")
    _assert_member_for_entity(db, current_user, connector)

    pins = db.query(Pin).filter(Pin.connector_id == conn_pk).order_by(Pin.pin_number).all()

    # Build pin summary by category
    summary = {"power": 0, "ground": 0, "signal": 0, "spare": 0, "no_connect": 0, "other": 0}
    pin_list = []
    for p in pins:
        pr = PinResponse.model_validate(p)
        _populate_pin_mating(db, pr, p)
        pin_list.append(pr)

        sig_type = _ev(p.signal_type)
        if sig_type.startswith("power"):
            summary["power"] += 1
        elif sig_type in ("chassis_ground", "signal_ground") or _ev(p.direction) in ("ground", "chassis_ground"):
            summary["ground"] += 1
        elif sig_type in ("spare",):
            summary["spare"] += 1
        elif sig_type in ("no_connect",) or _ev(p.direction) == "no_connect":
            summary["no_connect"] += 1
        else:
            summary["signal"] += 1

    return {
        "connector_info": {
            "id": connector.id,
            "connector_id": connector.connector_id,
            "designator": connector.designator,
            "name": connector.name,
            "connector_type": _ev(connector.connector_type),
            "gender": _ev(connector.gender),
            "total_contacts": connector.total_contacts,
            "shell_size": connector.shell_size,
            "insert_arrangement": connector.insert_arrangement,
        },
        "pins": pin_list,
        "pin_summary": summary,
        "total_pins": len(pin_list),
    }


@router.patch("/connectors/{conn_pk}", response_model=ConnectorResponse)
def update_connector(
    conn_pk: int,
    data: ConnectorUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.update")),
):
    connector = db.query(Connector).filter(Connector.id == conn_pk).first()
    if not connector:
        raise HTTPException(404, "Connector not found")
    _assert_member_for_entity(db, current_user, connector)

    updates = data.model_dump(exclude_unset=True)

    # Validate designator uniqueness if changing
    if "designator" in updates and updates["designator"] != connector.designator:
        dup = db.query(Connector).filter(
            Connector.unit_id == connector.unit_id,
            Connector.designator == updates["designator"],
            Connector.id != connector.id,
        ).first()
        if dup:
            raise HTTPException(409, f"Designator '{updates['designator']}' already exists on this unit")

    for field, value in updates.items():
        setattr(connector, field, value)
    db.commit()
    db.refresh(connector)

    pin_count = db.query(func.count(Pin.id)).filter(Pin.connector_id == connector.id).scalar()
    assigned_count = db.query(func.count(PinBusAssignment.id)).join(Pin).filter(
        Pin.connector_id == connector.id
    ).scalar()

    _audit(db, "connector.updated", "connector", connector.id, current_user.id,
           {"fields": list(updates.keys())},
           project_id=connector.project_id, request=request)

    resp = ConnectorResponse.model_validate(connector)
    resp.pin_count = pin_count
    resp.assigned_pin_count = assigned_count
    return resp


@router.delete("/connectors/{conn_pk}", status_code=200)
def delete_connector(
    conn_pk: int,
    force: bool = Query(False),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    """Delete a connector and all dependent data.

    Foreign-key chain (in deletion order to satisfy Postgres FK constraints):
      1. requirement_history / verifications (not touched here — those cascade
         from the req tables on their own)
      2. interface_requirement_links where entity_type in ('connector','pin')
         and entity_id matches this connector or its pins
      3. wires where from_pin_id or to_pin_id is a pin of this connector
      4. wire_harnesses where from_connector_id or to_connector_id = conn_pk
         (including their remaining wires and req links)
      5. pin_bus_assignments for this connector's pins
      6. pins for this connector
      7. the connector itself

    Without force=True: refuses if there are connected wires OR harness
    endpoint references, and reports counts so the user can decide.
    """
    connector = db.query(Connector).filter(Connector.id == conn_pk).first()
    if not connector:
        raise HTTPException(404, "Connector not found")
    _assert_member_for_entity(db, current_user, connector)

    # ── Pre-flight impact count ──
    pin_ids_subq = db.query(Pin.id).filter(Pin.connector_id == conn_pk).subquery()

    wire_count = (
        db.query(func.count(Wire.id))
        .filter((Wire.from_pin_id.in_(pin_ids_subq)) | (Wire.to_pin_id.in_(pin_ids_subq)))
        .scalar()
    ) or 0

    harness_endpoint_count = (
        db.query(func.count(WireHarness.id))
        .filter(
            (WireHarness.from_connector_id == conn_pk) |
            (WireHarness.to_connector_id == conn_pk)
        )
        .scalar()
    ) or 0

    if (wire_count > 0 or harness_endpoint_count > 0) and not force:
        raise HTTPException(
            409,
            (
                f"Connector is still wired into the system: "
                f"{wire_count} wire(s), {harness_endpoint_count} harness endpoint(s). "
                f"Use force=true to cascade-delete wires, harnesses that used this "
                f"connector as an endpoint, and all associated requirement links."
            ),
        )

    _audit(
        db, "connector.deleted", "connector", connector.id, current_user.id,
        {
            "designator": connector.designator,
            "force": force,
            "wires_removed": wire_count,
            "harnesses_removed": harness_endpoint_count,
        },
        project_id=connector.project_id, request=request,
    )

    # ── 1. Requirement links pointing at the connector itself ──
    db.query(InterfaceRequirementLink).filter(
        InterfaceRequirementLink.entity_type == "connector",
        InterfaceRequirementLink.entity_id == conn_pk,
    ).delete(synchronize_session="fetch")

    # ── 2. Requirement links pointing at any pin of this connector ──
    db.query(InterfaceRequirementLink).filter(
        InterfaceRequirementLink.entity_type == "pin",
        InterfaceRequirementLink.entity_id.in_(
            db.query(Pin.id).filter(Pin.connector_id == conn_pk)
        ),
    ).delete(synchronize_session="fetch")

    # ── 3. Wires touching this connector's pins (standalone wires that may
    #       exist outside of a wire_harness row, or wires that survived their
    #       harness being deleted) ──
    db.query(Wire).filter(
        (Wire.from_pin_id.in_(db.query(Pin.id).filter(Pin.connector_id == conn_pk))) |
        (Wire.to_pin_id.in_(db.query(Pin.id).filter(Pin.connector_id == conn_pk)))
    ).delete(synchronize_session="fetch")

    # ── 4. Harnesses that used this connector as an endpoint. These are
    #       meaningless without one of their endpoints, so we cascade-delete
    #       them entirely (their remaining wires + req links). ──
    dependent_harness_ids = [
        r[0] for r in db.query(WireHarness.id).filter(
            (WireHarness.from_connector_id == conn_pk) |
            (WireHarness.to_connector_id == conn_pk)
        ).all()
    ]

    if dependent_harness_ids:
        # Req links pointing at any of those harnesses
        db.query(InterfaceRequirementLink).filter(
            InterfaceRequirementLink.entity_type == "wire_harness",
            InterfaceRequirementLink.entity_id.in_(dependent_harness_ids),
        ).delete(synchronize_session="fetch")

        # Any wires still tied to those harnesses (step 3 caught pins on this
        # connector, but a harness can have wires to OTHER connectors too)
        db.query(Wire).filter(
            Wire.harness_id.in_(dependent_harness_ids)
        ).delete(synchronize_session="fetch")

        # The harnesses themselves
        db.query(WireHarness).filter(
            WireHarness.id.in_(dependent_harness_ids)
        ).delete(synchronize_session="fetch")

    # ── 5. Pin bus assignments ──
    db.query(PinBusAssignment).filter(
        PinBusAssignment.pin_id.in_(
            db.query(Pin.id).filter(Pin.connector_id == conn_pk)
        )
    ).delete(synchronize_session="fetch")

    # ── 6. Pins ──
    db.query(Pin).filter(Pin.connector_id == conn_pk).delete(synchronize_session="fetch")

    # ── 7. The connector ──
    db.delete(connector)
    db.commit()

    return {
        "status": "deleted",
        "id": conn_pk,
        "wires_removed": wire_count,
        "harnesses_removed": harness_endpoint_count,
    }


# ══════════════════════════════════════════════════════════════
#  PINS
# ══════════════════════════════════════════════════════════════

@router.post("/connectors/{conn_pk}/pins", response_model=List[PinResponse], status_code=201)
def batch_create_pins(
    conn_pk: int,
    data: PinBatchCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    """Batch add pins to a connector."""
    connector = db.query(Connector).filter(Connector.id == conn_pk).first()
    if not connector:
        raise HTTPException(404, "Connector not found")
    _assert_member_for_entity(db, current_user, connector)

    _validate_pin_numbers(data.pins)

    # Check for conflicts with existing pins
    existing_numbers = set(
        r[0] for r in db.query(Pin.pin_number).filter(Pin.connector_id == conn_pk).all()
    )
    incoming_numbers = {p.pin_number for p in data.pins}
    conflicts = existing_numbers & incoming_numbers
    if conflicts:
        raise HTTPException(409, f"Pin numbers already exist: {sorted(conflicts)}")

    created = []
    for pin_data in data.pins:
        pin = Pin(
            connector_id=conn_pk,
            **pin_data.model_dump(exclude_unset=True),
        )
        db.add(pin)
        created.append(pin)

    db.commit()
    for p in created:
        db.refresh(p)

    _audit(db, "pins.batch_created", "connector", conn_pk, current_user.id,
           {"count": len(created)},
           project_id=connector.project_id, request=request)

    responses = []
    for p in created:
        pr = PinResponse.model_validate(p)
        _populate_pin_mating(db, pr, p)
        responses.append(pr)
    return responses


@router.post("/connectors/{conn_pk}/pins/auto-generate", response_model=List[PinResponse], status_code=201)
def auto_generate_pins(
    conn_pk: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    """Auto-create pins numbered 1 through total_contacts, all set to spare/no_connect."""
    connector = db.query(Connector).filter(Connector.id == conn_pk).first()
    if not connector:
        raise HTTPException(404, "Connector not found")
    _assert_member_for_entity(db, current_user, connector)

    if not connector.total_contacts or connector.total_contacts <= 0:
        raise HTTPException(400, "Connector total_contacts must be > 0")

    # Check if pins already exist
    existing_count = db.query(func.count(Pin.id)).filter(Pin.connector_id == conn_pk).scalar()
    if existing_count > 0:
        raise HTTPException(409, f"Connector already has {existing_count} pin(s). Delete existing pins first.")

    created = []
    for i in range(1, connector.total_contacts + 1):
        pin = Pin(
            connector_id=conn_pk,
            pin_number=str(i),
            pin_label=f"PIN_{i:03d}",
            signal_name=f"SPARE_{i:03d}",
            signal_type="spare",
            direction="no_connect",
        )
        db.add(pin)
        created.append(pin)

    db.commit()
    for p in created:
        db.refresh(p)

    _audit(db, "pins.auto_generated", "connector", conn_pk, current_user.id,
           {"count": len(created)},
           project_id=connector.project_id, request=request)

    responses = []
    for p in created:
        pr = PinResponse.model_validate(p)
        _populate_pin_mating(db, pr, p)
        responses.append(pr)
    return responses


@router.patch("/pins/{pin_pk}", response_model=PinResponse)
def update_pin(
    pin_pk: int,
    data: PinUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.update")),
):
    pin = db.query(Pin).filter(Pin.id == pin_pk).first()
    if not pin:
        raise HTTPException(404, "Pin not found")
    _assert_member_for_entity(db, current_user, pin)

    updates = data.model_dump(exclude_unset=True)

    # Check for signal_name change with connected wire
    if "signal_name" in updates and updates["signal_name"] != pin.signal_name:
        wire_count = db.query(func.count(Wire.id)).filter(
            (Wire.from_pin_id == pin_pk) | (Wire.to_pin_id == pin_pk)
        ).scalar()
        if wire_count > 0:
            logger.warning(
                f"Pin {pin_pk} signal_name changed from '{pin.signal_name}' to "
                f"'{updates['signal_name']}' — {wire_count} wire(s) may need updating"
            )

    # Validate pin_number uniqueness within connector if changing
    if "pin_number" in updates and updates["pin_number"] != pin.pin_number:
        dup = db.query(Pin).filter(
            Pin.connector_id == pin.connector_id,
            Pin.pin_number == updates["pin_number"],
            Pin.id != pin.id,
        ).first()
        if dup:
            raise HTTPException(409, f"Pin number '{updates['pin_number']}' already exists on this connector")

    # Validate mating_unit_id: must be a real unit in the same project as
    # this pin's connector. Passing null clears the mating, which is allowed.
    if "mating_unit_id" in updates and updates["mating_unit_id"] is not None:
        target_unit = db.query(Unit).filter(Unit.id == updates["mating_unit_id"]).first()
        if not target_unit:
            raise HTTPException(404, f"Mating unit id {updates['mating_unit_id']} not found")
        # Cross-project check — pin's connector belongs to a unit, that unit
        # belongs to a project. Mating must be same project.
        connector = db.query(Connector).filter(Connector.id == pin.connector_id).first()
        if connector and target_unit.project_id != connector.project_id:
            raise HTTPException(
                400,
                "Mating unit must belong to the same project as this pin's connector",
            )
        # Prevent trivially-wrong self-reference — a pin shouldn't mate to
        # the unit its own connector belongs to.
        if connector and target_unit.id == connector.unit_id:
            raise HTTPException(
                400,
                "Mating unit cannot be the same as this pin's own LRU",
            )

    for field, value in updates.items():
        setattr(pin, field, value)
    db.commit()
    db.refresh(pin)

    connector = db.query(Connector).filter(Connector.id == pin.connector_id).first()
    _audit(db, "pin.updated", "pin", pin.id, current_user.id,
           {"fields": list(updates.keys())},
           project_id=connector.project_id if connector else None, request=request)

    resp = PinResponse.model_validate(pin)
    assignment = db.query(PinBusAssignment).filter(PinBusAssignment.pin_id == pin.id).first()
    if assignment:
        resp.bus_assignment = PinBusAssignmentResponse.model_validate(assignment)
    _populate_pin_mating(db, resp, pin)
    return resp


@router.delete("/pins/{pin_pk}", status_code=200)
def delete_pin(
    pin_pk: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    pin = db.query(Pin).filter(Pin.id == pin_pk).first()
    if not pin:
        raise HTTPException(404, "Pin not found")
    _assert_member_for_entity(db, current_user, pin)

    # Refuse if connected
    wire_count = db.query(func.count(Wire.id)).filter(
        (Wire.from_pin_id == pin_pk) | (Wire.to_pin_id == pin_pk)
    ).scalar()
    if wire_count > 0:
        raise HTTPException(
            409,
            f"Pin has {wire_count} wire connection(s). Disconnect wires before deleting.",
        )

    bus_count = db.query(func.count(PinBusAssignment.id)).filter(
        PinBusAssignment.pin_id == pin_pk
    ).scalar()
    if bus_count > 0:
        raise HTTPException(
            409,
            f"Pin has {bus_count} bus assignment(s). Remove assignments before deleting.",
        )

    connector = db.query(Connector).filter(Connector.id == pin.connector_id).first()
    _audit(db, "pin.deleted", "pin", pin.id, current_user.id,
           {"pin_number": pin.pin_number, "signal_name": pin.signal_name},
           project_id=connector.project_id if connector else None, request=request)

    db.delete(pin)
    db.commit()
    return {"status": "deleted", "id": pin_pk}


@router.get("/pins/search", response_model=List[dict])
def search_pins(
    project_id: int = Query(...),
    signal_name: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search pins across ALL units in a project by signal name."""
    _require_project(db, project_id, current_user)

    t = f"%{signal_name}%"
    pins = (
        db.query(Pin)
        .join(Connector)
        .join(Unit)
        .filter(Unit.project_id == project_id, Pin.signal_name.ilike(t))
        .order_by(Pin.signal_name, Unit.designation)
        .limit(100)
        .all()
    )

    results = []
    for p in pins:
        connector = db.query(Connector).filter(Connector.id == p.connector_id).first()
        unit = db.query(Unit).filter(Unit.id == connector.unit_id).first() if connector else None
        results.append({
            "pin_id": p.id,
            "pin_number": p.pin_number,
            "signal_name": p.signal_name,
            "signal_type": _ev(p.signal_type),
            "direction": _ev(p.direction),
            "connector_id": connector.id if connector else None,
            "connector_designator": connector.designator if connector else None,
            "unit_id": unit.id if unit else None,
            "unit_designation": unit.designation if unit else None,
            "unit_name": unit.name if unit else None,
        })
    return results


# ══════════════════════════════════════════════════════════════
#  Pin validation helper
# ══════════════════════════════════════════════════════════════

def _validate_pin_numbers(pins: list):
    """Check for duplicate pin_numbers within a batch."""
    numbers = [p.pin_number for p in pins]
    seen = set()
    dupes = set()
    for n in numbers:
        if n in seen:
            dupes.add(n)
        seen.add(n)
    if dupes:
        raise HTTPException(400, f"Duplicate pin_numbers in batch: {sorted(dupes)}")


def _field_color(field_name: str) -> str:
    """Deterministic hex color from field name for byte-map visualization."""
    import hashlib
    h = hashlib.md5(field_name.encode()).hexdigest()[:6]
    # Ensure readability by boosting brightness
    r = max(int(h[0:2], 16), 80)
    g = max(int(h[2:4], 16), 80)
    b = max(int(h[4:6], 16), 80)
    return f"#{r:02X}{g:02X}{b:02X}"


def _infer_wire_type(signal_type: str) -> str:
    """Infer wire_type from a pin's signal_type for auto-wiring."""
    st = signal_type.lower() if signal_type else ""
    if st.startswith("power"):
        if "return" in st:
            return "power_return"
        elif "secondary" in st or "negative" in st:
            return "power_negative"
        return "power_positive"
    if "ground" in st or "chassis_ground" in st:
        return "ground_signal" if "signal" in st else "ground_chassis"
    if "shield" in st:
        return "shield_overall_drain"
    if "coax" in st:
        return "coax_center"
    if "fiber" in st:
        return "fiber_tx"
    if "differential" in st or "twisted_pair" in st:
        return "signal_twisted_pair_a"
    return "signal_single"


def _infer_wire_gauge(current_amps: float | None) -> str:
    """Infer AWG wire gauge from max current rating."""
    if not current_amps or current_amps <= 0:
        return "awg_22"  # Default signal wire
    if current_amps <= 0.5:
        return "awg_26"
    if current_amps <= 1.0:
        return "awg_24"
    if current_amps <= 3.0:
        return "awg_22"
    if current_amps <= 5.0:
        return "awg_20"
    if current_amps <= 8.0:
        return "awg_18"
    if current_amps <= 13.0:
        return "awg_16"
    if current_amps <= 18.0:
        return "awg_14"
    if current_amps <= 25.0:
        return "awg_12"
    if current_amps <= 35.0:
        return "awg_10"
    return "awg_8"


# ══════════════════════════════════════════════════════════════
#  BUS DEFINITIONS
# ══════════════════════════════════════════════════════════════

@router.get("/buses", response_model=List[BusDefinitionResponse])
def list_buses(
    unit_id: Optional[int] = None,
    project_id: Optional[int] = None,
    bus_name_network: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not unit_id and not project_id:
        raise HTTPException(400, "Provide unit_id or project_id")

    query = db.query(BusDefinition)
    if unit_id:
        query = query.filter(BusDefinition.unit_id == unit_id)
    if project_id:
        query = query.filter(BusDefinition.project_id == project_id)
    if bus_name_network:
        query = query.filter(BusDefinition.bus_name_network.ilike(f"%{bus_name_network}%"))

    buses = query.order_by(BusDefinition.name).all()
    results = []
    for bd in buses:
        msg_count = db.query(func.count(MessageDefinition.id)).filter(
            MessageDefinition.bus_def_id == bd.id
        ).scalar()
        pa_count = db.query(func.count(PinBusAssignment.id)).filter(
            PinBusAssignment.bus_def_id == bd.id
        ).scalar()
        resp = BusDefinitionResponse.model_validate(bd)
        resp.message_count = msg_count
        resp.pin_assignment_count = pa_count
        results.append(resp)
    return results


@router.post("/buses", response_model=BusDefinitionResponse, status_code=201)
def create_bus(
    data: BusDefinitionCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    unit = db.query(Unit).filter(Unit.id == data.unit_id).first()
    if not unit:
        raise HTTPException(404, f"Unit {data.unit_id} not found")

    bus_def_id = _next_id(db, BusDefinition, unit.project_id, "BUS", "bus_def_id")

    bus = BusDefinition(
        bus_def_id=bus_def_id,
        project_id=unit.project_id,
        **data.model_dump(exclude_unset=True),
    )
    db.add(bus)
    db.commit()
    db.refresh(bus)

    _audit(db, "bus.created", "bus_definition", bus.id, current_user.id,
           {"bus_def_id": bus_def_id, "protocol": data.protocol},
           project_id=unit.project_id, request=request)

    resp = BusDefinitionResponse.model_validate(bus)
    resp.message_count = 0
    resp.pin_assignment_count = 0
    return resp


@router.get("/buses/{bus_pk}", response_model=BusWithMessages)
def get_bus(
    bus_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bd = db.query(BusDefinition).filter(BusDefinition.id == bus_pk).first()
    if not bd:
        raise HTTPException(404, "Bus definition not found")

    messages = db.query(MessageDefinition).filter(
        MessageDefinition.bus_def_id == bus_pk
    ).order_by(MessageDefinition.label).all()
    msg_summaries = []
    for m in messages:
        fc = db.query(func.count(MessageField.id)).filter(
            MessageField.message_id == m.id
        ).scalar()
        ms = MessageSummary.model_validate(m)
        ms.field_count = fc
        msg_summaries.append(ms)

    pin_assignments = db.query(PinBusAssignment).filter(
        PinBusAssignment.bus_def_id == bus_pk
    ).all()
    pa_list = []
    for pa in pin_assignments:
        par = PinBusAssignmentResponse.model_validate(pa)
        pin = db.query(Pin).filter(Pin.id == pa.pin_id).first()
        if pin:
            par.pin_number = pin.pin_number
            par.signal_name = pin.signal_name
            conn = db.query(Connector).filter(Connector.id == pin.connector_id).first()
            if conn:
                par.connector_designator = conn.designator
        pa_list.append(par)

    resp = BusWithMessages.model_validate(bd)
    resp.messages = msg_summaries
    resp.message_count = len(msg_summaries)
    resp.pin_assignments = pa_list
    resp.pin_assignment_count = len(pa_list)
    return resp


@router.patch("/buses/{bus_pk}", response_model=BusDefinitionResponse)
def update_bus(
    bus_pk: int,
    data: BusDefinitionUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.update")),
):
    bd = db.query(BusDefinition).filter(BusDefinition.id == bus_pk).first()
    if not bd:
        raise HTTPException(404, "Bus definition not found")

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(bd, field, value)
    bd.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(bd)

    _audit(db, "bus.updated", "bus_definition", bd.id, current_user.id,
           {"fields": list(updates.keys())},
           project_id=bd.project_id, request=request)

    msg_count = db.query(func.count(MessageDefinition.id)).filter(
        MessageDefinition.bus_def_id == bd.id
    ).scalar()
    pa_count = db.query(func.count(PinBusAssignment.id)).filter(
        PinBusAssignment.bus_def_id == bd.id
    ).scalar()
    resp = BusDefinitionResponse.model_validate(bd)
    resp.message_count = msg_count
    resp.pin_assignment_count = pa_count
    return resp


@router.delete("/buses/{bus_pk}", status_code=200)
def delete_bus(
    bus_pk: int,
    confirm: bool = Query(False),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    bd = db.query(BusDefinition).filter(BusDefinition.id == bus_pk).first()
    if not bd:
        raise HTTPException(404, "Bus definition not found")

    msg_count = db.query(func.count(MessageDefinition.id)).filter(
        MessageDefinition.bus_def_id == bus_pk
    ).scalar()
    pa_count = db.query(func.count(PinBusAssignment.id)).filter(
        PinBusAssignment.bus_def_id == bus_pk
    ).scalar()
    req_link_count = db.query(func.count(InterfaceRequirementLink.id)).filter(
        InterfaceRequirementLink.entity_type == "bus_definition",
        InterfaceRequirementLink.entity_id == bus_pk,
    ).scalar()

    if not confirm:
        return {
            "status": "preview",
            "impact": {
                "messages": msg_count,
                "pin_assignments": pa_count,
                "requirement_links": req_link_count,
            },
        }

    # Cascade: fields → messages, pin_assignments
    msgs = db.query(MessageDefinition).filter(MessageDefinition.bus_def_id == bus_pk).all()
    for m in msgs:
        db.query(MessageField).filter(MessageField.message_id == m.id).delete()
        db.delete(m)
    db.query(PinBusAssignment).filter(PinBusAssignment.bus_def_id == bus_pk).delete()
    db.query(InterfaceRequirementLink).filter(
        InterfaceRequirementLink.entity_type == "bus_definition",
        InterfaceRequirementLink.entity_id == bus_pk,
    ).delete()

    _audit(db, "bus.deleted", "bus_definition", bd.id, current_user.id,
           {"bus_def_id": bd.bus_def_id, "messages_deleted": msg_count},
           project_id=bd.project_id, request=request)

    db.delete(bd)
    db.commit()
    return {"status": "deleted", "id": bus_pk, "messages_deleted": msg_count}


@router.post("/buses/{bus_pk}/pin-assignments", response_model=List[PinBusAssignmentResponse], status_code=201)
def batch_assign_pins_to_bus(
    bus_pk: int,
    assignments: List[PinBusAssignmentCreate],
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    bd = db.query(BusDefinition).filter(BusDefinition.id == bus_pk).first()
    if not bd:
        raise HTTPException(404, "Bus definition not found")

    created = []
    for a in assignments:
        pin = db.query(Pin).filter(Pin.id == a.pin_id).first()
        if not pin:
            raise HTTPException(404, f"Pin {a.pin_id} not found")
        # Validate pin belongs to same unit
        conn = db.query(Connector).filter(Connector.id == pin.connector_id).first()
        if not conn or conn.unit_id != bd.unit_id:
            raise HTTPException(
                400, f"Pin {a.pin_id} is not on the same unit as bus {bus_pk}"
            )
        # Check not already assigned to this bus
        existing = db.query(PinBusAssignment).filter(
            PinBusAssignment.pin_id == a.pin_id,
            PinBusAssignment.bus_def_id == bus_pk,
        ).first()
        if existing:
            raise HTTPException(409, f"Pin {a.pin_id} already assigned to bus {bus_pk}")

        pa = PinBusAssignment(
            pin_id=a.pin_id,
            bus_def_id=bus_pk,
            pin_role=a.pin_role,
            pin_role_custom=a.pin_role_custom,
            notes=a.notes,
        )
        db.add(pa)
        created.append(pa)

    db.commit()
    results = []
    for pa in created:
        db.refresh(pa)
        par = PinBusAssignmentResponse.model_validate(pa)
        pin = db.query(Pin).filter(Pin.id == pa.pin_id).first()
        if pin:
            par.pin_number = pin.pin_number
            par.signal_name = pin.signal_name
            conn = db.query(Connector).filter(Connector.id == pin.connector_id).first()
            if conn:
                par.connector_designator = conn.designator
        results.append(par)

    _audit(db, "bus.pins_assigned", "bus_definition", bus_pk, current_user.id,
           {"count": len(created)},
           project_id=bd.project_id, request=request)
    return results


@router.delete("/buses/pin-assignments/{pa_pk}", status_code=200)
def remove_pin_assignment(
    pa_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    pa = db.query(PinBusAssignment).filter(PinBusAssignment.id == pa_pk).first()
    if not pa:
        raise HTTPException(404, "Pin-bus assignment not found")
    db.delete(pa)
    db.commit()
    return {"status": "deleted", "id": pa_pk}


@router.get("/buses/{bus_pk}/utilization")
def get_bus_utilization(
    bus_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    bd = db.query(BusDefinition).filter(BusDefinition.id == bus_pk).first()
    if not bd:
        raise HTTPException(404, "Bus definition not found")

    capacity_bps = bd.data_rate_actual_bps or 0
    word_bits = bd.word_size_bits or 16  # Default 1553 word size

    messages = db.query(MessageDefinition).filter(
        MessageDefinition.bus_def_id == bus_pk
    ).all()

    msg_details = []
    total_bps = 0
    for m in messages:
        wc = m.word_count or 0
        hz = m.rate_hz or 0
        bits_per_sec = wc * word_bits * hz
        total_bps += bits_per_sec
        msg_details.append({
            "id": m.id,
            "label": m.label,
            "word_count": wc,
            "rate_hz": hz,
            "bits_per_second": bits_per_sec,
            "pct_of_total": 0,  # Filled below
        })

    # Calculate percentages
    for md in msg_details:
        if total_bps > 0:
            md["pct_of_total"] = round(md["bits_per_second"] / total_bps * 100, 2)

    utilization_pct = round(total_bps / capacity_bps * 100, 2) if capacity_bps > 0 else None

    return {
        "bus_id": bd.id,
        "bus_name": bd.name,
        "protocol": _ev(bd.protocol),
        "capacity_bps": capacity_bps,
        "used_bps": total_bps,
        "utilization_pct": utilization_pct,
        "message_count": len(messages),
        "messages": msg_details,
    }


# ══════════════════════════════════════════════════════════════
#  MESSAGES
# ══════════════════════════════════════════════════════════════

@router.get("/messages", response_model=List[MessageSummary])
def list_messages(
    bus_id: Optional[int] = None,
    unit_id: Optional[int] = None,
    project_id: Optional[int] = None,
    label: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not bus_id and not unit_id and not project_id:
        raise HTTPException(400, "Provide bus_id, unit_id, or project_id")

    query = db.query(MessageDefinition)
    if bus_id:
        query = query.filter(MessageDefinition.bus_def_id == bus_id)
    if unit_id:
        query = query.filter(MessageDefinition.unit_id == unit_id)
    if project_id:
        query = query.filter(MessageDefinition.project_id == project_id)
    if label:
        t = f"%{label}%"
        query = query.filter(
            MessageDefinition.label.ilike(t) | MessageDefinition.mnemonic.ilike(t)
        )

    messages = query.order_by(MessageDefinition.label).all()
    results = []
    for m in messages:
        fc = db.query(func.count(MessageField.id)).filter(
            MessageField.message_id == m.id
        ).scalar()
        ms = MessageSummary.model_validate(m)
        ms.field_count = fc
        results.append(ms)
    return results


@router.post("/messages", status_code=201)
def create_message(
    data: MessageDefinitionCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    bd = db.query(BusDefinition).filter(BusDefinition.id == data.bus_def_id).first()
    if not bd:
        raise HTTPException(404, f"Bus definition {data.bus_def_id} not found")
    unit = db.query(Unit).filter(Unit.id == data.unit_id).first()
    if not unit:
        raise HTTPException(404, f"Unit {data.unit_id} not found")

    # Validate subaddress uniqueness within bus (MIL-STD-1553)
    if data.subaddress is not None:
        dup = db.query(MessageDefinition).filter(
            MessageDefinition.bus_def_id == data.bus_def_id,
            MessageDefinition.subaddress == data.subaddress,
            MessageDefinition.direction == data.direction,
        ).first()
        if dup:
            raise HTTPException(
                409,
                f"Subaddress {data.subaddress} ({data.direction}) already in use on bus {data.bus_def_id}",
            )

    msg_def_id = _next_id(db, MessageDefinition, unit.project_id, "MSG", "msg_def_id")
    fields_data = data.fields
    msg_fields = data.model_dump(exclude_unset=True, exclude={"fields"})

    msg = MessageDefinition(
        msg_def_id=msg_def_id,
        project_id=unit.project_id,
        **msg_fields,
    )
    db.add(msg)
    db.flush()

    created_fields = []
    if fields_data:
        for idx, fd in enumerate(fields_data):
            field_dict = fd.model_dump(exclude_unset=True)
            field_dict["message_id"] = msg.id
            if field_dict.get("field_order") is None:
                field_dict["field_order"] = idx + 1
            f = MessageField(**field_dict)
            db.add(f)
            created_fields.append(f)

    db.commit()
    db.refresh(msg)

    _audit(db, "message.created", "message_definition", msg.id, current_user.id,
           {"msg_def_id": msg_def_id, "label": data.label, "fields_created": len(created_fields)},
           project_id=unit.project_id, request=request)

    if created_fields:
        for f in created_fields:
            db.refresh(f)
        total_bits = sum(f.bit_length for f in created_fields)
        resp = MessageWithFields.model_validate(msg)
        resp.fields = [MessageFieldResponse.model_validate(f) for f in created_fields]
        resp.field_count = len(created_fields)
        resp.total_bits = total_bits
        return resp
    else:
        resp = MessageDefinitionResponse.model_validate(msg)
        resp.field_count = 0
        resp.total_bits = 0
        return resp


@router.get("/messages/{msg_pk}", response_model=MessageWithFields)
def get_message(
    msg_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    msg = db.query(MessageDefinition).filter(MessageDefinition.id == msg_pk).first()
    if not msg:
        raise HTTPException(404, "Message definition not found")

    fields = db.query(MessageField).filter(
        MessageField.message_id == msg_pk
    ).order_by(MessageField.field_order, MessageField.byte_offset, MessageField.bit_offset).all()

    total_bits = sum(f.bit_length for f in fields)

    resp = MessageWithFields.model_validate(msg)
    resp.fields = [MessageFieldResponse.model_validate(f) for f in fields]
    resp.field_count = len(fields)
    resp.total_bits = total_bits
    return resp


@router.patch("/messages/{msg_pk}", response_model=MessageDefinitionResponse)
def update_message(
    msg_pk: int,
    data: MessageDefinitionUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.update")),
):
    msg = db.query(MessageDefinition).filter(MessageDefinition.id == msg_pk).first()
    if not msg:
        raise HTTPException(404, "Message definition not found")

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(msg, field, value)
    msg.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(msg)

    _audit(db, "message.updated", "message_definition", msg.id, current_user.id,
           {"fields": list(updates.keys())},
           project_id=msg.project_id, request=request)

    fc = db.query(func.count(MessageField.id)).filter(MessageField.message_id == msg.id).scalar()
    total_bits = db.query(func.sum(MessageField.bit_length)).filter(
        MessageField.message_id == msg.id
    ).scalar() or 0

    resp = MessageDefinitionResponse.model_validate(msg)
    resp.field_count = fc
    resp.total_bits = total_bits
    return resp


@router.delete("/messages/{msg_pk}", status_code=200)
def delete_message(
    msg_pk: int,
    confirm: bool = Query(False),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    msg = db.query(MessageDefinition).filter(MessageDefinition.id == msg_pk).first()
    if not msg:
        raise HTTPException(404, "Message definition not found")

    fc = db.query(func.count(MessageField.id)).filter(MessageField.message_id == msg_pk).scalar()
    rl = db.query(func.count(InterfaceRequirementLink.id)).filter(
        InterfaceRequirementLink.entity_type == "message_definition",
        InterfaceRequirementLink.entity_id == msg_pk,
    ).scalar()

    if not confirm:
        return {"status": "preview", "impact": {"fields": fc, "requirement_links": rl}}

    db.query(MessageField).filter(MessageField.message_id == msg_pk).delete()
    db.query(InterfaceRequirementLink).filter(
        InterfaceRequirementLink.entity_type == "message_definition",
        InterfaceRequirementLink.entity_id == msg_pk,
    ).delete()

    _audit(db, "message.deleted", "message_definition", msg.id, current_user.id,
           {"msg_def_id": msg.msg_def_id, "fields_deleted": fc},
           project_id=msg.project_id, request=request)

    db.delete(msg)
    db.commit()
    return {"status": "deleted", "id": msg_pk, "fields_deleted": fc}


# ══════════════════════════════════════════════════════════════
#  MESSAGE FIELDS
# ══════════════════════════════════════════════════════════════

@router.post("/messages/{msg_pk}/fields", response_model=List[MessageFieldResponse], status_code=201)
def batch_create_fields(
    msg_pk: int,
    data: MessageFieldBatchCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    msg = db.query(MessageDefinition).filter(MessageDefinition.id == msg_pk).first()
    if not msg:
        raise HTTPException(404, "Message definition not found")

    # Get existing max field_order
    max_order = db.query(func.max(MessageField.field_order)).filter(
        MessageField.message_id == msg_pk
    ).scalar() or 0

    created = []
    for idx, fd in enumerate(data.fields):
        field_dict = fd.model_dump(exclude_unset=True)
        field_dict["message_id"] = msg_pk
        if field_dict.get("field_order") is None:
            field_dict["field_order"] = max_order + idx + 1
        f = MessageField(**field_dict)
        db.add(f)
        created.append(f)

    db.commit()
    for f in created:
        db.refresh(f)

    _audit(db, "fields.batch_created", "message_definition", msg_pk, current_user.id,
           {"count": len(created)},
           project_id=msg.project_id, request=request)

    return [MessageFieldResponse.model_validate(f) for f in created]


@router.patch("/fields/{field_pk}", response_model=MessageFieldResponse)
def update_field(
    field_pk: int,
    data: MessageFieldUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.update")),
):
    field = db.query(MessageField).filter(MessageField.id == field_pk).first()
    if not field:
        raise HTTPException(404, "Message field not found")

    updates = data.model_dump(exclude_unset=True)
    for k, v in updates.items():
        setattr(field, k, v)
    db.commit()
    db.refresh(field)
    return MessageFieldResponse.model_validate(field)


@router.delete("/fields/{field_pk}", status_code=200)
def delete_field(
    field_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    field = db.query(MessageField).filter(MessageField.id == field_pk).first()
    if not field:
        raise HTTPException(404, "Message field not found")

    # Mark linked auto-requirements for review
    db.query(InterfaceRequirementLink).filter(
        InterfaceRequirementLink.entity_type == "message_field",
        InterfaceRequirementLink.entity_id == field_pk,
    ).update({"status": "pending_review"})

    db.delete(field)
    db.commit()
    return {"status": "deleted", "id": field_pk}


@router.get("/messages/{msg_pk}/byte-map")
def get_message_byte_map(
    msg_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return word/byte layout for message visualization."""
    msg = db.query(MessageDefinition).filter(MessageDefinition.id == msg_pk).first()
    if not msg:
        raise HTTPException(404, "Message definition not found")

    bd = db.query(BusDefinition).filter(BusDefinition.id == msg.bus_def_id).first()
    word_bits = bd.word_size_bits if bd and bd.word_size_bits else 16
    total_words = msg.word_count or 0

    fields = db.query(MessageField).filter(
        MessageField.message_id == msg_pk
    ).order_by(MessageField.word_number, MessageField.bit_offset).all()

    # Build layout indexed by word
    layout = {}
    for f in fields:
        wn = f.word_number or 1
        if wn not in layout:
            layout[wn] = []
        layout[wn].append({
            "field_id": f.id,
            "field_name": f.field_name,
            "bit_offset": f.bit_offset or 0,
            "bit_length": f.bit_length,
            "start": f.bit_offset or 0,
            "end": (f.bit_offset or 0) + f.bit_length - 1,
            "data_type": _ev(f.data_type),
            "color": _field_color(f.field_name),
            "is_spare": f.is_spare or False,
            "is_padding": f.is_padding or False,
        })

    # Convert to ordered list
    word_layout = []
    for w in range(1, max(total_words, max(layout.keys(), default=0)) + 1):
        word_layout.append({
            "word": w,
            "bits": sorted(layout.get(w, []), key=lambda x: x["start"]),
        })

    return {
        "message_id": msg.id,
        "label": msg.label,
        "total_words": total_words,
        "word_size_bits": word_bits,
        "total_fields": len(fields),
        "total_bits_used": sum(f.bit_length for f in fields),
        "layout": word_layout,
    }


# ══════════════════════════════════════════════════════════════
#  WIRE HARNESSES
# ══════════════════════════════════════════════════════════════

@router.get("/harnesses", response_model=List[WireHarnessResponse])
def list_harnesses(
    project_id: int = Query(...),
    from_unit_id: Optional[int] = None,
    to_unit_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_project(db, project_id, current_user)
    query = db.query(WireHarness).filter(WireHarness.project_id == project_id)
    if from_unit_id:
        query = query.filter(WireHarness.from_unit_id == from_unit_id)
    if to_unit_id:
        query = query.filter(WireHarness.to_unit_id == to_unit_id)

    harnesses = query.order_by(WireHarness.name).all()
    results = []
    for h in harnesses:
        wc = db.query(func.count(Wire.id)).filter(Wire.harness_id == h.id).scalar()
        resp = WireHarnessResponse.model_validate(h)
        resp.wire_count = wc
        # Resolve join names
        fu = db.query(Unit).filter(Unit.id == h.from_unit_id).first()
        fc = db.query(Connector).filter(Connector.id == h.from_connector_id).first()
        tu = db.query(Unit).filter(Unit.id == h.to_unit_id).first()
        tc = db.query(Connector).filter(Connector.id == h.to_connector_id).first()
        resp.from_unit_designation = fu.designation if fu else None
        resp.from_connector_designator = fc.designator if fc else None
        resp.to_unit_designation = tu.designation if tu else None
        resp.to_connector_designator = tc.designator if tc else None
        results.append(resp)
    return results


@router.post("/harnesses", response_model=WireHarnessResponse, status_code=201)
def create_harness(
    data: WireHarnessCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    # Validate from connector belongs to from unit
    fc = db.query(Connector).filter(Connector.id == data.from_connector_id).first()
    if not fc:
        raise HTTPException(404, f"From connector {data.from_connector_id} not found")
    if fc.unit_id != data.from_unit_id:
        raise HTTPException(400, f"Connector {data.from_connector_id} does not belong to unit {data.from_unit_id}")

    tc = db.query(Connector).filter(Connector.id == data.to_connector_id).first()
    if not tc:
        raise HTTPException(404, f"To connector {data.to_connector_id} not found")
    if tc.unit_id != data.to_unit_id:
        raise HTTPException(400, f"Connector {data.to_connector_id} does not belong to unit {data.to_unit_id}")

    fu = db.query(Unit).filter(Unit.id == data.from_unit_id).first()
    if not fu:
        raise HTTPException(404, f"From unit {data.from_unit_id} not found")

    harness_id = _next_id(db, WireHarness, fu.project_id, "HAR", "harness_id")

    harness = WireHarness(
        harness_id=harness_id,
        project_id=fu.project_id,
        **data.model_dump(exclude_unset=True),
    )
    db.add(harness)
    db.commit()
    db.refresh(harness)

    _audit(db, "harness.created", "wire_harness", harness.id, current_user.id,
           {"harness_id": harness_id},
           project_id=fu.project_id, request=request)

    resp = WireHarnessResponse.model_validate(harness)
    resp.wire_count = 0
    resp.from_unit_designation = fu.designation
    resp.from_connector_designator = fc.designator
    tu = db.query(Unit).filter(Unit.id == data.to_unit_id).first()
    resp.to_unit_designation = tu.designation if tu else None
    resp.to_connector_designator = tc.designator
    return resp


@router.get("/harnesses/{har_pk}", response_model=WireHarnessDetail)
def get_harness(
    har_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    harness = db.query(WireHarness).filter(WireHarness.id == har_pk).first()
    if not harness:
        raise HTTPException(404, "Wire harness not found")

    wires = db.query(Wire).filter(Wire.harness_id == har_pk).order_by(Wire.wire_number).all()
    wire_list = []
    for w in wires:
        wr = WireResponse.model_validate(w)
        _populate_wire_joins(db, wr, w)
        wire_list.append(wr)

    resp = WireHarnessDetail.model_validate(harness)
    resp.wires = wire_list
    resp.wire_count = len(wire_list)
    _populate_harness_joins(db, resp, harness)
    return resp


@router.patch("/harnesses/{har_pk}", response_model=WireHarnessResponse)
def update_harness(
    har_pk: int,
    data: WireHarnessUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.update")),
):
    harness = db.query(WireHarness).filter(WireHarness.id == har_pk).first()
    if not harness:
        raise HTTPException(404, "Wire harness not found")

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(harness, field, value)
    harness.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(harness)

    _audit(db, "harness.updated", "wire_harness", harness.id, current_user.id,
           {"fields": list(updates.keys())},
           project_id=harness.project_id, request=request)

    wc = db.query(func.count(Wire.id)).filter(Wire.harness_id == harness.id).scalar()
    resp = WireHarnessResponse.model_validate(harness)
    resp.wire_count = wc
    _populate_harness_joins(db, resp, harness)
    return resp


@router.delete("/harnesses/{har_pk}", status_code=200)
def delete_harness(
    har_pk: int,
    confirm: bool = Query(False),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    harness = db.query(WireHarness).filter(WireHarness.id == har_pk).first()
    if not harness:
        raise HTTPException(404, "Wire harness not found")

    wc = db.query(func.count(Wire.id)).filter(Wire.harness_id == har_pk).scalar()
    rl = db.query(func.count(InterfaceRequirementLink.id)).filter(
        InterfaceRequirementLink.entity_type == "wire_harness",
        InterfaceRequirementLink.entity_id == har_pk,
    ).scalar()

    if not confirm:
        return {"status": "preview", "impact": {"wires": wc, "requirement_links": rl}}

    db.query(Wire).filter(Wire.harness_id == har_pk).delete()
    db.query(InterfaceRequirementLink).filter(
        InterfaceRequirementLink.entity_type == "wire_harness",
        InterfaceRequirementLink.entity_id == har_pk,
    ).delete()

    _audit(db, "harness.deleted", "wire_harness", harness.id, current_user.id,
           {"harness_id": harness.harness_id, "wires_deleted": wc},
           project_id=harness.project_id, request=request)

    db.delete(harness)
    db.commit()
    return {"status": "deleted", "id": har_pk, "wires_deleted": wc}


# ══════════════════════════════════════════════════════════════
#  WIRES
# ══════════════════════════════════════════════════════════════

@router.post("/harnesses/{har_pk}/wires", status_code=201)
def batch_create_wires(
    har_pk: int,
    data: WireBatchCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    """Manually add wires to an existing harness.

    Phase 2b change: validation is now multi-endpoint aware. Previously
    we only allowed pins belonging to harness.from_connector or
    harness.to_connector (the legacy 2-endpoint model). Now we allow pins
    belonging to ANY of the harness's endpoints — so adding wires to a
    3+ endpoint harness works.

    If a pin's connector isn't on this harness at all, we don't silently
    extend the harness here. Instead we return a clean 400 directing the
    caller to /interfaces/auto-grow, which has the proper ambiguity and
    extend-harness logic. Rationale: this endpoint is for "I've already
    decided which harness the wire goes on" cases; auto-grow is for "let
    the engine figure out harness assignment." Keeping them distinct
    prevents accidental harness restructuring from innocent-looking
    single-wire creates.

    Also populates each wire's from_mating_pin_id / to_mating_pin_id by
    looking up the matching pin on the appropriate harness endpoint's
    mating connector.
    """
    harness = db.query(WireHarness).filter(WireHarness.id == har_pk).first()
    if not harness:
        raise HTTPException(404, "Wire harness not found")

    # Build: set of pin_ids that belong to any endpoint's LRU connector on
    # this harness. For a 2-endpoint harness this equals the old from_pin_ids
    # ∪ to_pin_ids. For larger harnesses it's the union across all endpoints.
    endpoint_rows = (db.query(HarnessEndpoint.lru_connector_id, HarnessEndpoint.mating_connector_id)
                     .filter(HarnessEndpoint.harness_id == har_pk).all())
    lru_connector_ids = {lru for (lru, _) in endpoint_rows if lru is not None}
    # lru_connector_id -> mating_connector_id, used for mating pin resolution
    lru_to_mating: dict = {lru: mating for (lru, mating) in endpoint_rows if lru is not None}

    # Fallback for harnesses that pre-date Phase 1 and somehow lack
    # endpoint rows (shouldn't happen post-migration, but defensive).
    if not lru_connector_ids and harness.from_connector_id and harness.to_connector_id:
        lru_connector_ids = {harness.from_connector_id, harness.to_connector_id}
        lru_to_mating = {}

    valid_pin_ids = set(
        r[0] for r in db.query(Pin.id).filter(Pin.connector_id.in_(lru_connector_ids)).all()
    ) if lru_connector_ids else set()

    # Pre-fetch existing state for conflict checks
    existing_numbers = set(
        r[0] for r in db.query(Wire.wire_number).filter(Wire.harness_id == har_pk).all()
    )
    existing_from = set(
        r[0] for r in db.query(Wire.from_pin_id).filter(Wire.harness_id == har_pk).all()
    )
    existing_to = set(
        r[0] for r in db.query(Wire.to_pin_id).filter(Wire.harness_id == har_pk).all()
    )

    # Helper: given an LRU pin, find its matching pin on the harness's
    # mating connector for that pin's LRU connector. Returns None if either
    # the endpoint doesn't exist or the pin_number doesn't match anything
    # on the mating side (shouldn't happen if the migration ran; the
    # engine's cloning preserves pin_number 1:1).
    def _resolve_mating_pin(lru_pin_id: int):
        lru_pin = db.query(Pin).filter(Pin.id == lru_pin_id).first()
        if not lru_pin:
            return None
        mating_conn_id = lru_to_mating.get(lru_pin.connector_id)
        if not mating_conn_id:
            return None
        return (db.query(Pin)
                .filter(Pin.connector_id == mating_conn_id,
                        Pin.pin_number == lru_pin.pin_number)
                .first())

    created = []
    for wd in data.wires:
        # Validate both pins live on this harness's endpoint LRUs
        if wd.from_pin_id not in valid_pin_ids:
            raise HTTPException(
                400,
                f"Pin {wd.from_pin_id} is not on any LRU connector plugged into harness {har_pk}. "
                f"If you want to wire pins across different harnesses, use POST /interfaces/auto-grow."
            )
        if wd.to_pin_id not in valid_pin_ids:
            raise HTTPException(
                400,
                f"Pin {wd.to_pin_id} is not on any LRU connector plugged into harness {har_pk}. "
                f"If you want to wire pins across different harnesses, use POST /interfaces/auto-grow."
            )
        if wd.from_pin_id == wd.to_pin_id:
            raise HTTPException(400, "A wire cannot connect a pin to itself")

        if wd.wire_number in existing_numbers:
            raise HTTPException(409, f"Wire number '{wd.wire_number}' already exists in harness")
        if wd.from_pin_id in existing_from:
            raise HTTPException(409, f"From-pin {wd.from_pin_id} already connected in harness")
        if wd.to_pin_id in existing_to:
            raise HTTPException(409, f"To-pin {wd.to_pin_id} already connected in harness")

        existing_numbers.add(wd.wire_number)
        existing_from.add(wd.from_pin_id)
        existing_to.add(wd.to_pin_id)

        # Resolve mating-side pin refs for each end
        from_mating = _resolve_mating_pin(wd.from_pin_id)
        to_mating = _resolve_mating_pin(wd.to_pin_id)

        wire = Wire(
            harness_id=har_pk,
            from_mating_pin_id=from_mating.id if from_mating else None,
            to_mating_pin_id=to_mating.id if to_mating else None,
            **wd.model_dump(exclude_unset=True),
        )
        db.add(wire)
        created.append(wire)

        # Maintain the Connection rollup row for this LRU pair. We do this
        # per-wire so a batch that spans multiple LRU pairs updates all the
        # relevant connections.
        try:
            from app.services.interface.auto_grow import AutoGrowEngine
            engine = AutoGrowEngine(db, harness.project_id, current_user)
            from_pin = db.query(Pin).filter(Pin.id == wd.from_pin_id).first()
            to_pin = db.query(Pin).filter(Pin.id == wd.to_pin_id).first()
            if from_pin and to_pin:
                from_conn = db.query(Connector).filter(Connector.id == from_pin.connector_id).first()
                to_conn = db.query(Connector).filter(Connector.id == to_pin.connector_id).first()
                if (from_conn and to_conn and
                        from_conn.unit_id and to_conn.unit_id and
                        from_conn.unit_id != to_conn.unit_id):
                    engine._upsert_connection(from_conn.unit_id, to_conn.unit_id)
        except Exception as e:
            logger.warning(f"connection rollup maintenance failed for wire create: {e}")

    db.commit()
    results = []
    for w in created:
        db.refresh(w)
        wr = WireResponse.model_validate(w)
        _populate_wire_joins(db, wr, w)
        results.append(wr)

    _audit(db, "wires.batch_created", "wire_harness", har_pk, current_user.id,
           {"count": len(created)},
           project_id=harness.project_id, request=request)

    # Auto-generate requirements from new wires
    auto_result = {"requirements_generated": 0}
    try:
        from app.services.interface.auto_requirements import AutoRequirementGenerator
        generator = AutoRequirementGenerator(db, harness.project_id, current_user)
        auto_result = generator.on_wires_created(harness, created)
        db.commit()
    except Exception as e:
        import logging
        logging.getLogger("astra").error(f"Auto-req generation failed: {e}")
        auto_result = {"requirements_generated": 0, "error": str(e)}

    return {"wires": results, "count": len(results), "auto_requirements": auto_result}


@router.post("/harnesses/{har_pk}/auto-wire")
def auto_wire_harness(
    har_pk: int,
    mapping: str = Query(
        "auto",
        description=(
            "Wiring strategy: "
            "'auto' prefers by_peer_lru if pins have mating_unit_id set, else straight-through for RJ-45 pairs, else signal-name matching; "
            "'by_signal' always matches on pin.signal_name (case-insensitive); "
            "'by_peer_lru' matches pins where A.mating_unit == B's unit AND vice versa, with signal_name+complementary direction; "
            "'straight_through' wires pin 1→1, 2→2, ... N→N (ignores names); "
            "'crossover' uses T568B-style crossover (1↔3, 2↔6, rest straight). RJ-45 only."
        ),
    ),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    """Auto-create wires between the two connectors on a harness.

    Strategy (`mapping` query param):
      * **auto**            — default. Priority order: by_peer_lru (if ≥1 pin
                              on each side has mating_unit_id pointing at the
                              other side's unit), then straight_through (RJ-45
                              pairs with matching pin count), then by_signal.
      * **by_signal**       — matches pins by normalized signal_name.
      * **by_peer_lru**     — matches pins where:
                                A.mating_unit_id == B.connector.unit_id AND
                                B.mating_unit_id == A.connector.unit_id AND
                                signal_name matches AND
                                signal_type matches AND
                                directions are complementary (input↔output or
                                bidirectional↔bidirectional).
      * **straight_through**— wires each pin N to pin N on the opposite end
                              (by pin_number). Ignores signal names entirely.
      * **crossover**       — T568B crossover: 1↔3, 2↔6, 3↔1, 6↔2, and
                              4,5,7,8 straight. RJ-45 only.

    Returns counts, the strategy actually used, and lists of unmatched pins
    from each side so the caller can fill in the gaps manually.
    """
    VALID_STRATEGIES = {"auto", "by_signal", "by_peer_lru", "straight_through", "crossover"}
    if mapping not in VALID_STRATEGIES:
        raise HTTPException(
            400,
            f"Invalid mapping '{mapping}'. Must be one of: {', '.join(sorted(VALID_STRATEGIES))}",
        )

    harness = db.query(WireHarness).filter(WireHarness.id == har_pk).first()
    if not harness:
        raise HTTPException(404, "Wire harness not found")

    # Load both endpoint connectors (for type/pin-count detection) and pins
    from_connector = db.query(Connector).filter(Connector.id == harness.from_connector_id).first()
    to_connector = db.query(Connector).filter(Connector.id == harness.to_connector_id).first()
    if not from_connector or not to_connector:
        raise HTTPException(409, "Harness is missing one or both endpoint connectors")

    from_pins = db.query(Pin).filter(Pin.connector_id == harness.from_connector_id).all()
    to_pins = db.query(Pin).filter(Pin.connector_id == harness.to_connector_id).all()

    # Already-connected pins on this harness
    existing_from = set(
        r[0] for r in db.query(Wire.from_pin_id).filter(Wire.harness_id == har_pk).all()
    )
    existing_to = set(
        r[0] for r in db.query(Wire.to_pin_id).filter(Wire.harness_id == har_pk).all()
    )
    max_wire_num = db.query(func.max(Wire.wire_number)).filter(Wire.harness_id == har_pk).scalar()
    wire_counter = (
        int(re.search(r"(\d+)", max_wire_num).group(1)) + 1
        if max_wire_num and re.search(r"(\d+)", max_wire_num) else 1
    )

    # ── Resolve 'auto' into a concrete strategy ──
    from_type = _ev(from_connector.connector_type) if from_connector.connector_type else None
    to_type = _ev(to_connector.connector_type) if to_connector.connector_type else None
    from_unit_id = from_connector.unit_id
    to_unit_id = to_connector.unit_id

    # For the auto-detection: does any from_pin declare the to-side unit as
    # its mate, and vice versa? If yes on both sides, by_peer_lru is the
    # most specific signal so we prefer it.
    from_has_peer_match = any(
        getattr(p, "mating_unit_id", None) == to_unit_id for p in from_pins
    )
    to_has_peer_match = any(
        getattr(p, "mating_unit_id", None) == from_unit_id for p in to_pins
    )

    chosen_strategy = mapping
    if mapping == "auto":
        if from_has_peer_match and to_has_peer_match:
            # Strongest signal: users have explicitly tagged which pins mate
            # with which peer unit. Use that over any other heuristic.
            chosen_strategy = "by_peer_lru"
        elif (
            from_type == "rj45" and to_type == "rj45"
            and len(from_pins) > 0 and len(from_pins) == len(to_pins)
        ):
            # RJ-45 pairs: positional mapping is almost always right.
            chosen_strategy = "straight_through"
        else:
            chosen_strategy = "by_signal"

    # Crossover is only meaningful for RJ-45 (T568B crossover definition)
    if chosen_strategy == "crossover" and not (from_type == "rj45" and to_type == "rj45"):
        raise HTTPException(
            400,
            f"Crossover mapping requires both connectors to be RJ-45. "
            f"This harness has {from_type or 'unknown'} → {to_type or 'unknown'}.",
        )

    # ── Build pin lookups for each strategy ──
    # All three strategies end up populating `pairs`: a list of (from_pin, to_pin)
    # tuples that will become wires. Unmatched pins are tracked separately.
    pairs: list[tuple[Pin, Pin]] = []
    unmatched_from: list[dict] = []
    unmatched_to: list[dict] = []

    def _pin_summary(p: Pin) -> dict:
        return {
            "pin_id": p.id,
            "pin_number": p.pin_number,
            "signal_name": p.signal_name,
        }

    if chosen_strategy == "by_signal":
        # Original behavior: case-insensitive signal_name match. Skips
        # SPARE/NC pins since those are intentionally unwired.
        to_map: dict = {}
        for tp in to_pins:
            if tp.id in existing_to:
                continue
            if tp.signal_name:
                sn = tp.signal_name.upper().strip()
                if sn not in to_map:  # first match wins on duplicates
                    to_map[sn] = tp
        unmatched_to_names = set(to_map.keys())

        for fp in from_pins:
            if fp.id in existing_from:
                continue
            sn = (fp.signal_name or "").upper().strip()
            if not sn or sn.startswith("SPARE") or sn.startswith("NC"):
                unmatched_from.append(_pin_summary(fp))
                continue
            tp = to_map.get(sn)
            if tp:
                pairs.append((fp, tp))
                unmatched_to_names.discard(sn)
            else:
                unmatched_from.append(_pin_summary(fp))
        for sn in unmatched_to_names:
            unmatched_to.append(_pin_summary(to_map[sn]))

    elif chosen_strategy == "by_peer_lru":
        # Peer-LRU match: each pin knows which unit it's supposed to talk to
        # (via mating_unit_id). Wire A_pin to B_pin when:
        #   1. A.mating_unit_id == B's connector's unit_id  AND
        #   2. B.mating_unit_id == A's connector's unit_id  AND
        #   3. signal_name matches (case-insensitive, whitespace-stripped) AND
        #   4. signal_type matches AND
        #   5. directions are complementary:
        #        input  ↔ output
        #        bidirectional ↔ bidirectional
        # This is the intended-design strategy for inter-LRU buses where
        # users label pins like "FCC_IMU_Avionics_Bus_Hi" and set direction
        # per endpoint — the engine then figures out which pins are conjugate.
        def _norm(s: str | None) -> str:
            return (s or "").strip().upper()

        def _directions_match(a: str | None, b: str | None) -> bool:
            a = _norm(a); b = _norm(b)
            if not a or not b:
                return False
            if a == "BIDIRECTIONAL" and b == "BIDIRECTIONAL":
                return True
            if {a, b} == {"INPUT", "OUTPUT"}:
                return True
            return False

        # Pre-filter the to-side pins by peer-unit match + not-already-wired.
        # Group them in a dict keyed by (signal_name, signal_type) for O(1)
        # lookup during the from-side walk. If multiple to-pins share the
        # same (name, type), first one wins — later ones land in unmatched_to.
        to_candidates: dict[tuple[str, str], list[Pin]] = {}
        to_excluded: list[Pin] = []
        for tp in to_pins:
            if tp.id in existing_to:
                continue
            if getattr(tp, "mating_unit_id", None) != from_unit_id:
                to_excluded.append(tp)
                continue
            key = (_norm(tp.signal_name), _norm(_ev(tp.signal_type) if tp.signal_type else ""))
            to_candidates.setdefault(key, []).append(tp)

        consumed_to_ids: set[int] = set()

        for fp in from_pins:
            if fp.id in existing_from:
                continue
            if getattr(fp, "mating_unit_id", None) != to_unit_id:
                # This pin doesn't claim to mate with the other side's unit.
                # Could be a spare, a chassis ground, or a pin that mates
                # with some third party. Leave it alone.
                unmatched_from.append(_pin_summary(fp))
                continue
            key = (_norm(fp.signal_name), _norm(_ev(fp.signal_type) if fp.signal_type else ""))
            candidates = to_candidates.get(key, [])
            # Pick the first candidate with complementary direction that
            # hasn't already been consumed.
            match = None
            for tp in candidates:
                if tp.id in consumed_to_ids:
                    continue
                if _directions_match(_ev(fp.direction), _ev(tp.direction)):
                    match = tp
                    break
            if match:
                pairs.append((fp, match))
                consumed_to_ids.add(match.id)
            else:
                unmatched_from.append(_pin_summary(fp))

        # Any to-candidate we didn't consume is reported as unmatched
        for key, cands in to_candidates.items():
            for tp in cands:
                if tp.id not in consumed_to_ids:
                    unmatched_to.append(_pin_summary(tp))
        # Pins that didn't even declare a peer link aren't reported as
        # unmatched on the to-side either — they were never in scope.

    elif chosen_strategy in ("straight_through", "crossover"):
        # Both strategies map pins by pin_number. Build pin_number → Pin
        # lookups so ordering is deterministic even if DB rows come back
        # in insert order rather than pin order.
        # pin_number is stored as text ("1", "1A", "J1-2"...) — we only do
        # purely-numeric matching here since these strategies only make sense
        # for numbered connectors like RJ-45.
        def _by_number(pins: list[Pin]) -> dict:
            d: dict = {}
            for p in pins:
                if p.pin_number and p.pin_number.strip().isdigit():
                    d[int(p.pin_number.strip())] = p
            return d

        from_by_num = _by_number(from_pins)
        to_by_num = _by_number(to_pins)

        # Crossover swap map. For T568B crossover cables:
        #   TX pair (1,2) on one end ↔ RX pair (3,6) on the other
        # 4, 5, 7, 8 stay straight. This is a symmetric map, so applying it
        # once from each end produces consistent results.
        CROSSOVER_MAP = {1: 3, 2: 6, 3: 1, 6: 2, 4: 4, 5: 5, 7: 7, 8: 8}

        matched_to_ids: set[int] = set()

        for num, fp in sorted(from_by_num.items()):
            if fp.id in existing_from:
                continue
            target_num = CROSSOVER_MAP.get(num, num) if chosen_strategy == "crossover" else num
            tp = to_by_num.get(target_num)
            if tp and tp.id not in existing_to and tp.id not in matched_to_ids:
                pairs.append((fp, tp))
                matched_to_ids.add(tp.id)
            else:
                unmatched_from.append(_pin_summary(fp))

        for num, tp in sorted(to_by_num.items()):
            if tp.id in existing_to or tp.id in matched_to_ids:
                continue
            unmatched_to.append(_pin_summary(tp))

    # ── Materialize the wires via the auto-grow engine (Phase 2b) ──
    #
    # Before Phase 2b, this block did `db.add(Wire(...))` inline per pair.
    # That worked but hardcoded the assumption "wires always stay on this
    # specific harness and never trigger harness restructuring." With the
    # multi-endpoint model, that's wrong: a wire between pins whose LRUs
    # aren't both plugged into THIS harness may need to extend it, merge
    # with another harness, or surface an ambiguity.
    #
    # So we keep ALL the matching logic above (strategy dispatch, pin
    # matching, unmatched lists) unchanged — those are high-quality
    # per-connector decisions — and just hand the resulting pairs to the
    # engine. The engine figures out harness assignment.
    #
    # For the common 2-endpoint case (both pins belong to LRUs that already
    # have endpoints on this harness), the engine's `existing_harness` path
    # fires and wires land exactly where they would have before. Behavior
    # is unchanged for old data.
    from app.services.interface.auto_grow import (
        AutoGrowEngine, AutoGrowPair as _AGPair,
    )
    engine = AutoGrowEngine(db, harness.project_id, current_user)
    grow_pairs = [
        _AGPair(
            from_lru_pin_id=fp.id,
            to_lru_pin_id=tp.id,
            signal_name=fp.signal_name or tp.signal_name or f"PIN_{fp.pin_number}_TO_{tp.pin_number}",
            wire_type=_infer_wire_type(_ev(fp.signal_type) if fp.signal_type else ""),
            wire_gauge=_infer_wire_gauge(fp.current_max_amps),
        )
        for fp, tp in pairs
    ]
    try:
        grow_result = engine.run(pairs=grow_pairs, decisions=[])
    except ValueError as e:
        db.rollback()
        raise HTTPException(400, str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"auto-wire via engine failed: {e}", exc_info=True)
        raise HTTPException(500, f"Auto-wire failed: {e}")

    # If the engine surfaced ambiguities, we can't quietly commit. Return
    # them to the caller so the UI can resolve them via the same modal as
    # a direct /auto-grow call. The `auto_wire` endpoint is a convenience
    # wrapper that usually doesn't hit ambiguities (it's called per-harness
    # and the pairs are all between the same 2 LRUs) — but we handle the
    # edge case cleanly rather than silently dropping wires.
    if grow_result.ambiguities:
        return {
            "matched": 0,
            "unmatched_from": unmatched_from,
            "unmatched_to": unmatched_to,
            "wires_created": [],
            "ambiguities": [
                {
                    "pair_index": a.pair_index,
                    "from_lru_pin_id": a.from_lru_pin_id,
                    "to_lru_pin_id": a.to_lru_pin_id,
                    "from_lru_unit_designation": a.from_lru_unit_designation,
                    "to_lru_unit_designation": a.to_lru_unit_designation,
                    "harness_a_id": a.harness_a_id,
                    "harness_a_name": a.harness_a_name,
                    "harness_a_lru_designations": a.harness_a_lru_designations,
                    "harness_b_id": a.harness_b_id,
                    "harness_b_name": a.harness_b_name,
                    "harness_b_lru_designations": a.harness_b_lru_designations,
                    "valid_actions": a.valid_actions,
                    "new_harness_disallowed_reason": a.new_harness_disallowed_reason,
                }
                for a in grow_result.ambiguities
            ],
            "strategy": chosen_strategy,
            "strategy_requested": mapping,
            "message": (
                "Auto-wire produced pin matches that would span multiple harnesses. "
                "Resolve each ambiguity via POST /interfaces/auto-grow with the decisions array."
            ),
        }

    # No ambiguity — engine already committed. Hydrate the new wires for
    # the response.
    matched_wires: list[Wire] = []
    if grow_result.new_wire_ids:
        matched_wires = (db.query(Wire)
                         .filter(Wire.id.in_(grow_result.new_wire_ids))
                         .all())

    # Build response wire list with joined names (for UI display)
    wire_results = []
    for w in matched_wires:
        db.refresh(w)
        wr = WireResponse.model_validate(w)
        _populate_wire_joins(db, wr, w)
        wire_results.append(wr)

    _audit(
        db, "harness.auto_wired", "wire_harness", har_pk, current_user.id,
        {
            "matched": len(matched_wires),
            "unmatched_from": len(unmatched_from),
            "unmatched_to": len(unmatched_to),
            "strategy": chosen_strategy,
            "requested": mapping,
        },
        project_id=harness.project_id, request=request,
    )

    # Auto-generate requirements from new wires
    auto_result = {"requirements_generated": 0}
    if matched_wires:
        try:
            from app.services.interface.auto_requirements import AutoRequirementGenerator
            generator = AutoRequirementGenerator(db, harness.project_id, current_user)
            auto_result = generator.on_wires_created(harness, matched_wires)
            db.commit()
        except Exception as e:
            import logging
            logging.getLogger("astra").error(f"Auto-req generation on auto-wire failed: {e}")
            auto_result = {"requirements_generated": 0, "error": str(e)}

    return {
        "matched": len(matched_wires),
        "unmatched_from": unmatched_from,
        "unmatched_to": unmatched_to,
        "wires_created": wire_results,
        "auto_requirements": auto_result,
        "strategy": chosen_strategy,
        "strategy_requested": mapping,
    }


@router.post("/harnesses/{har_pk}/generate-requirements")
def generate_harness_requirements(
    har_pk: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    """
    Generate (or regenerate) auto-requirements for all wires in a harness.
    
    Unlike auto-wire (which creates wires AND generates reqs), this endpoint
    runs the requirement generator on existing wires. Useful when:
      - Wires were created manually without triggering auto-req
      - Requirements were rejected and user wants to regenerate
      - Bus assignments changed after initial wiring
    
    Returns the same result shape as AutoRequirementGenerator.on_wires_created().
    """
    harness = db.query(WireHarness).filter(WireHarness.id == har_pk).first()
    if not harness:
        raise HTTPException(404, "Harness not found")

    wires = db.query(Wire).filter(Wire.harness_id == har_pk).all()
    if not wires:
        return {
            "requirements_generated": 0,
            "verifications_generated": 0,
            "links_generated": 0,
            "requirements": [],
            "message": "No wires found on this harness. Create wires first (manually or via auto-wire).",
        }

    try:
        from app.services.interface.auto_requirements import AutoRequirementGenerator
        generator = AutoRequirementGenerator(db, harness.project_id, current_user)
        result = generator.on_wires_created(harness, wires)
        db.commit()

        _audit(db, "harness.requirements_generated", "wire_harness", har_pk,
               current_user.id,
               {
                   "requirements_generated": result.get("requirements_generated", 0),
                   "verifications_generated": result.get("verifications_generated", 0),
                   "links_generated": result.get("links_generated", 0),
               },
               project_id=harness.project_id, request=request)

        return result
    except Exception as e:
        logger.error(f"Requirement generation failed for harness {har_pk}: {e}")
        db.rollback()
        raise HTTPException(500, f"Requirement generation failed: {str(e)}")

@router.post("/auto-requirements/approve")
def approve_auto_requirements(
    data: AutoReqApproveRequest,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.update")),
):
    """
    Approve auto-generated requirements:
      1. Set each requirement status → 'draft'
      2. Set each InterfaceRequirementLink status → 'approved'
      3. Auto-create trace links to parent requirements
      4. Return summary with counts
    """
    approved = 0
    trace_links_created = 0

    for req_id in data.requirement_ids:
        req = db.query(Requirement).filter(Requirement.id == req_id).first()
        if not req:
            continue

        # 1. Update requirement status to draft
        old_status = _ev(req.status)
        if old_status in ("pending_review", "under_review"):
            req.status = "draft"
            req.version = (req.version or 1) + 1

            # Record history
            hist = RequirementHistory(
                requirement_id=req.id,
                version=req.version,
                field_changed="status",
                old_value=old_status,
                new_value="draft",
                changed_by_id=current_user.id,
                change_description="Approved from auto-requirement review",
            )
            db.add(hist)

        # 2. Update all interface requirement links for this req
        links = db.query(InterfaceRequirementLink).filter(
            InterfaceRequirementLink.requirement_id == req_id,
            InterfaceRequirementLink.auto_generated.is_(True),
        ).all()
        for link in links:
            link.status = "approved"
            link.reviewed_by_id = current_user.id
            link.reviewed_at = datetime.utcnow()

        # 3. Auto-create trace links
        # a) If requirement has a parent_id, create derives_from trace
        if req.parent_id:
            from app.models import TraceLink
            existing_trace = db.query(TraceLink).filter(
                TraceLink.source_type == "requirement",
                TraceLink.source_id == req.id,
                TraceLink.target_type == "requirement",
                TraceLink.target_id == req.parent_id,
                TraceLink.link_type == "derives_from",
            ).first()
            if not existing_trace:
                trace = TraceLink(
                    source_type="requirement",
                    source_id=req.id,
                    target_type="requirement",
                    target_id=req.parent_id,
                    link_type="derives_from",
                    description=f"Auto-traced on approval: {req.req_id} derives from parent",
                    status="active",
                    created_by_id=current_user.id,
                )
                db.add(trace)
                trace_links_created += 1

        # b) For each interface link, create a trace link to source entity's requirement
        for link in links:
            # Find other requirements linked to the same source entity
            sibling_links = db.query(InterfaceRequirementLink).filter(
                InterfaceRequirementLink.entity_type == link.entity_type,
                InterfaceRequirementLink.entity_id == link.entity_id,
                InterfaceRequirementLink.requirement_id != req_id,
                InterfaceRequirementLink.status == "approved",
            ).all()
            for sib in sibling_links:
                from app.models import TraceLink
                existing = db.query(TraceLink).filter(
                    TraceLink.source_type == "requirement",
                    TraceLink.source_id == req.id,
                    TraceLink.target_type == "requirement",
                    TraceLink.target_id == sib.requirement_id,
                ).first()
                if not existing:
                    trace = TraceLink(
                        source_type="requirement",
                        source_id=req.id,
                        target_type="requirement",
                        target_id=sib.requirement_id,
                        link_type="related_to",
                        description=f"Auto-traced: shared interface entity {link.entity_type}:{link.entity_id}",
                        status="active",
                        created_by_id=current_user.id,
                    )
                    db.add(trace)
                    trace_links_created += 1

        approved += 1

    db.commit()

    _audit(db, "auto_requirements.approved", "bulk", 0, current_user.id,
           {"approved": approved, "trace_links_created": trace_links_created,
            "requirement_ids": data.requirement_ids},
           request=request)

    return {
        "approved": approved,
        "trace_links_created": trace_links_created,
        "requirement_ids": data.requirement_ids,
    }


@router.post("/auto-requirements/reject")
def reject_auto_requirements(
    data: AutoReqRejectRequest,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.update")),
):
    """
    Reject auto-generated requirements:
      1. Soft-delete each requirement (status → 'deleted')
      2. Set each InterfaceRequirementLink status → 'rejected'
    """
    rejected = 0

    for req_id in data.requirement_ids:
        req = db.query(Requirement).filter(Requirement.id == req_id).first()
        if not req:
            continue

        old_status = _ev(req.status)
        req.status = "deleted"
        req.version = (req.version or 1) + 1

        hist = RequirementHistory(
            requirement_id=req.id,
            version=req.version,
            field_changed="status",
            old_value=old_status,
            new_value="deleted",
            changed_by_id=current_user.id,
            change_description=f"Rejected from auto-requirement review. {data.reason or ''}".strip(),
        )
        db.add(hist)

        # Update links
        db.query(InterfaceRequirementLink).filter(
            InterfaceRequirementLink.requirement_id == req_id,
            InterfaceRequirementLink.auto_generated.is_(True),
        ).update({
            InterfaceRequirementLink.status: "rejected",
            InterfaceRequirementLink.reviewed_by_id: current_user.id,
            InterfaceRequirementLink.reviewed_at: datetime.utcnow(),
        }, synchronize_session="fetch")

        rejected += 1

    db.commit()

    _audit(db, "auto_requirements.rejected", "bulk", 0, current_user.id,
           {"rejected": rejected, "reason": data.reason,
            "requirement_ids": data.requirement_ids},
           request=request)

    return {
        "rejected": rejected,
        "requirement_ids": data.requirement_ids,
    }

@router.patch("/wires/{wire_pk}", response_model=WireResponse)
def update_wire(
    wire_pk: int,
    data: WireUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.update")),
):
    wire = db.query(Wire).filter(Wire.id == wire_pk).first()
    if not wire:
        raise HTTPException(404, "Wire not found")

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(wire, field, value)
    db.commit()
    db.refresh(wire)

    resp = WireResponse.model_validate(wire)
    _populate_wire_joins(db, resp, wire)
    return resp


@router.delete("/wires/{wire_pk}", status_code=200)
def delete_wire(
    wire_pk: int,
    confirm: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    wire = db.query(Wire).filter(Wire.id == wire_pk).first()
    if not wire:
        raise HTTPException(404, "Wire not found")

    rl = db.query(func.count(InterfaceRequirementLink.id)).filter(
        InterfaceRequirementLink.entity_type == "wire",
        InterfaceRequirementLink.entity_id == wire_pk,
    ).scalar()

    if not confirm and rl > 0:
        return {"status": "preview", "impact": {"requirement_links": rl}}

    db.query(InterfaceRequirementLink).filter(
        InterfaceRequirementLink.entity_type == "wire",
        InterfaceRequirementLink.entity_id == wire_pk,
    ).delete()

    # Phase 2: check if this is the last wire between its two LRUs; if so
    # remove the Connection rollup row. Done BEFORE db.delete(wire) so the
    # helper can still query the wire's pins.
    try:
        from app.services.interface.auto_grow import maybe_delete_connection_for_wire
        maybe_delete_connection_for_wire(db, wire)
    except Exception as e:
        logger.warning(f"connection cleanup after wire delete failed: {e}")

    db.delete(wire)
    db.commit()
    return {"status": "deleted", "id": wire_pk}


@router.get("/wires/search")
def search_wires(
    project_id: int = Query(...),
    signal_name: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Search wires by signal name with full path context."""
    _require_project(db, project_id, current_user)
    t = f"%{signal_name}%"
    wires = (
        db.query(Wire)
        .join(WireHarness)
        .filter(WireHarness.project_id == project_id, Wire.signal_name.ilike(t))
        .order_by(Wire.signal_name)
        .limit(100)
        .all()
    )
    results = []
    for w in wires:
        wr = WireResponse.model_validate(w)
        _populate_wire_joins(db, wr, w)
        results.append(wr)
    return results


# ══════════════════════════════════════════════════════════════
#  SIGNAL TRACE
# ══════════════════════════════════════════════════════════════

@router.get("/signal-trace", response_model=SignalTraceResult)
def trace_signal(
    project_id: int = Query(...),
    signal_name: str = Query(..., min_length=1),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trace a signal end-to-end across the entire system."""
    _require_project(db, project_id, current_user)

    # 1. Find all pins with this signal name
    pins = (
        db.query(Pin)
        .join(Connector)
        .join(Unit)
        .filter(Unit.project_id == project_id, Pin.signal_name.ilike(f"%{signal_name}%"))
        .all()
    )

    if not pins:
        return SignalTraceResult(signal_name=signal_name, path=[])

    pin_ids = [p.id for p in pins]

    # 2. Find all wires connected to those pins
    wires = db.query(Wire).filter(
        (Wire.from_pin_id.in_(pin_ids)) | (Wire.to_pin_id.in_(pin_ids))
    ).all()

    paths = []
    for w in wires:
        from_pin = db.query(Pin).filter(Pin.id == w.from_pin_id).first()
        to_pin = db.query(Pin).filter(Pin.id == w.to_pin_id).first()
        from_conn = db.query(Connector).filter(Connector.id == from_pin.connector_id).first() if from_pin else None
        to_conn = db.query(Connector).filter(Connector.id == to_pin.connector_id).first() if to_pin else None
        from_unit = db.query(Unit).filter(Unit.id == from_conn.unit_id).first() if from_conn else None
        to_unit = db.query(Unit).filter(Unit.id == to_conn.unit_id).first() if to_conn else None
        harness = db.query(WireHarness).filter(WireHarness.id == w.harness_id).first()

        hop = SignalTraceHop(
            unit=from_unit.designation if from_unit else None,
            connector=from_conn.designator if from_conn else None,
            pin=from_pin.pin_number if from_pin else None,
            wire=w.wire_number,
            harness=harness.name if harness else None,
        )
        paths.append(hop)

        # Add destination hop
        hop2 = SignalTraceHop(
            unit=to_unit.designation if to_unit else None,
            connector=to_conn.designator if to_conn else None,
            pin=to_pin.pin_number if to_pin else None,
        )
        paths.append(hop2)

    # 3. Find bus assignments for those pins
    bus_assignments = db.query(PinBusAssignment).filter(
        PinBusAssignment.pin_id.in_(pin_ids)
    ).all()
    for ba in bus_assignments:
        bd = db.query(BusDefinition).filter(BusDefinition.id == ba.bus_def_id).first()
        if bd:
            # Find messages on this bus
            msgs = db.query(MessageDefinition).filter(
                MessageDefinition.bus_def_id == bd.id
            ).all()
            for m in msgs:
                paths.append(SignalTraceHop(
                    bus=f"{bd.name} ({_ev(bd.protocol)})",
                    message=f"{m.label} @{m.rate_hz}Hz" if m.rate_hz else m.label,
                ))

    return SignalTraceResult(signal_name=signal_name, path=paths)


# ══════════════════════════════════════════════════════════════
#  N² MATRIX
# ══════════════════════════════════════════════════════════════

@router.get("/n2-matrix", response_model=N2MatrixResponse)
def get_n2_matrix(
    project_id: int = Query(...),
    level: str = Query("system", regex="^(system|unit)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Build N² interface matrix at system or unit level."""
    _require_project(db, project_id, current_user)

    if level == "system":
        systems = db.query(System).filter(System.project_id == project_id).order_by(System.name).all()
        sys_responses = []
        for s in systems:
            uc = db.query(func.count(Unit.id)).filter(Unit.system_id == s.id).scalar()
            ic = db.query(func.count(Interface.id)).filter(
                (Interface.source_system_id == s.id) | (Interface.target_system_id == s.id)
            ).scalar()
            sr = SystemResponse.model_validate(s)
            sr.unit_count = uc
            sr.interface_count = ic
            sys_responses.append(sr)

        # Build matrix
        interfaces = db.query(Interface).filter(Interface.project_id == project_id).all()
        harnesses = db.query(WireHarness).filter(WireHarness.project_id == project_id).all()

        # Map unit_id → system_id for harnesses
        unit_system_map = {}
        for u in db.query(Unit).filter(Unit.project_id == project_id).all():
            unit_system_map[u.id] = u.system_id

        # Build cell data
        cells: dict = {}
        for iface in interfaces:
            key = (iface.source_system_id, iface.target_system_id)
            if key not in cells:
                src = next((s for s in systems if s.id == iface.source_system_id), None)
                tgt = next((s for s in systems if s.id == iface.target_system_id), None)
                cells[key] = N2MatrixCell(
                    source_system_id=iface.source_system_id,
                    source_system_name=src.name if src else "",
                    target_system_id=iface.target_system_id,
                    target_system_name=tgt.name if tgt else "",
                )
            cells[key].interface_count += 1
            crit = _ev(iface.criticality)
            if not cells[key].criticality_max or _crit_rank(crit) > _crit_rank(cells[key].criticality_max):
                cells[key].criticality_max = crit

        # Count harnesses per system pair
        for h in harnesses:
            src_sys = unit_system_map.get(h.from_unit_id)
            tgt_sys = unit_system_map.get(h.to_unit_id)
            if src_sys and tgt_sys:
                key = (src_sys, tgt_sys)
                if key in cells:
                    cells[key].harness_count += 1

        # Build matrix grid
        sys_ids = [s.id for s in systems]
        matrix = []
        for src_id in sys_ids:
            row = []
            for tgt_id in sys_ids:
                row.append(cells.get((src_id, tgt_id)))
            matrix.append(row)

        return N2MatrixResponse(systems=sys_responses, matrix=matrix)

    # Unit level (simplified — same structure, units as rows/cols)
    return N2MatrixResponse(systems=[], matrix=[])


# ══════════════════════════════════════════════════════════════
#  BLOCK DIAGRAM
# ══════════════════════════════════════════════════════════════

@router.get("/block-diagram", response_model=BlockDiagramResponse)
def get_block_diagram(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """System-level block diagram: nodes = systems, edges = interfaces."""
    _require_project(db, project_id, current_user)

    systems = db.query(System).filter(System.project_id == project_id).order_by(System.name).all()
    nodes = []
    for idx, s in enumerate(systems):
        uc = db.query(func.count(Unit.id)).filter(Unit.system_id == s.id).scalar()
        nodes.append(BlockDiagramNode(
            id=s.id,
            system_id=s.system_id,
            name=s.name,
            abbreviation=s.abbreviation,
            type=_ev(s.system_type),
            unit_count=uc,
            x=float(idx % 4) * 250,
            y=float(idx // 4) * 200,
        ))

    interfaces = db.query(Interface).filter(Interface.project_id == project_id).all()

    # Count harnesses per interface pair
    harness_counts: dict = {}
    for h in db.query(WireHarness).filter(WireHarness.project_id == project_id).all():
        fu = db.query(Unit).filter(Unit.id == h.from_unit_id).first()
        tu = db.query(Unit).filter(Unit.id == h.to_unit_id).first()
        if fu and tu:
            key = (fu.system_id, tu.system_id)
            harness_counts[key] = harness_counts.get(key, 0) + 1

    edges = []
    for iface in interfaces:
        edges.append(BlockDiagramEdge(
            source_id=iface.source_system_id,
            target_id=iface.target_system_id,
            interface_id=iface.id,
            name=iface.name,
            type=_ev(iface.interface_type),
            criticality=_ev(iface.criticality),
            direction=_ev(iface.direction),
            harness_count=harness_counts.get(
                (iface.source_system_id, iface.target_system_id), 0
            ),
        ))

    return BlockDiagramResponse(nodes=nodes, edges=edges)


# ══════════════════════════════════════════════════════════════
#  INTERFACE REQUIREMENT LINKS
# ══════════════════════════════════════════════════════════════

@router.post("/req-links", response_model=InterfaceReqLinkResponse, status_code=201)
def create_req_link(
    data: InterfaceReqLinkCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    # Validate requirement exists
    req = db.query(Requirement).filter(Requirement.id == data.requirement_id).first()
    if not req:
        raise HTTPException(404, f"Requirement {data.requirement_id} not found")

    link = InterfaceRequirementLink(
        created_by_id=current_user.id,
        **data.model_dump(exclude_unset=True),
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    resp = InterfaceReqLinkResponse.model_validate(link)
    resp.requirement_req_id = req.req_id
    resp.requirement_title = req.title
    return resp


@router.get("/req-links", response_model=List[InterfaceReqLinkResponse])
def list_req_links(
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    requirement_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not entity_type and not entity_id and not requirement_id:
        raise HTTPException(400, "Provide entity_type+entity_id or requirement_id")

    query = db.query(InterfaceRequirementLink)
    if entity_type:
        query = query.filter(InterfaceRequirementLink.entity_type == entity_type)
    if entity_id:
        query = query.filter(InterfaceRequirementLink.entity_id == entity_id)
    if requirement_id:
        query = query.filter(InterfaceRequirementLink.requirement_id == requirement_id)

    links = query.order_by(InterfaceRequirementLink.created_at.desc()).all()
    results = []
    for lk in links:
        resp = InterfaceReqLinkResponse.model_validate(lk)
        req = db.query(Requirement).filter(Requirement.id == lk.requirement_id).first()
        if req:
            resp.requirement_req_id = req.req_id
            resp.requirement_title = req.title
        results.append(resp)
    return results


@router.delete("/req-links/{link_pk}", status_code=200)
def delete_req_link(
    link_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    link = db.query(InterfaceRequirementLink).filter(InterfaceRequirementLink.id == link_pk).first()
    if not link:
        raise HTTPException(404, "Requirement link not found")
    db.delete(link)
    db.commit()
    return {"status": "deleted", "id": link_pk}


# ══════════════════════════════════════════════════════════════
#  COVERAGE
# ══════════════════════════════════════════════════════════════

@router.get("/coverage", response_model=InterfaceCoverageResponse)
def get_interface_coverage(
    project_id: int = Query(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Interface-to-requirement traceability coverage stats."""
    _require_project(db, project_id, current_user)

    total_interfaces = db.query(func.count(Interface.id)).filter(
        Interface.project_id == project_id
    ).scalar()

    # Interfaces with at least one requirement link
    linked_ifaces = db.query(func.count(func.distinct(InterfaceRequirementLink.entity_id))).filter(
        InterfaceRequirementLink.entity_type == "interface",
    ).scalar()

    # Units with env specs
    units_total = db.query(func.count(Unit.id)).filter(Unit.project_id == project_id).scalar()
    units_with = db.query(func.count(func.distinct(UnitEnvironmentalSpec.unit_id))).join(Unit).filter(
        Unit.project_id == project_id
    ).scalar()

    # Auto-generated link stats
    auto_total = db.query(func.count(InterfaceRequirementLink.id)).filter(
        InterfaceRequirementLink.auto_generated.is_(True),
    ).scalar()
    auto_approved = db.query(func.count(InterfaceRequirementLink.id)).filter(
        InterfaceRequirementLink.auto_generated.is_(True),
        InterfaceRequirementLink.status == "approved",
    ).scalar()
    auto_pending = db.query(func.count(InterfaceRequirementLink.id)).filter(
        InterfaceRequirementLink.auto_generated.is_(True),
        InterfaceRequirementLink.status == "pending_review",
    ).scalar()

    coverage_pct = round(linked_ifaces / total_interfaces * 100, 1) if total_interfaces > 0 else 0.0

    return InterfaceCoverageResponse(
        total_interfaces=total_interfaces,
        with_requirements=linked_ifaces,
        without_requirements=total_interfaces - linked_ifaces,
        coverage_pct=coverage_pct,
        units_with_specs=units_with,
        units_without_specs=units_total - units_with,
        auto_generated_count=auto_total,
        approved_count=auto_approved,
        pending_count=auto_pending,
    )


# ══════════════════════════════════════════════════════════════
#  IMPACT ANALYSIS
# ══════════════════════════════════════════════════════════════

class _ImpactPreviewRequest(BaseModel):
    action: str  # delete_wire, delete_bus, edit_bus, edit_message, delete_unit
    entity_id: int | list[int]  # single ID or list for wires
    changes: dict | None = None  # for edit actions


class _ImpactExecuteRequest(BaseModel):
    affected_req_ids: list[int]
    action: str  # delete_requirements, orphan_requirements, mark_for_review
    change_description: str = ""
    project_id: int | None = None


@router.post("/impact/preview")
def impact_preview(
    data: _ImpactPreviewRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Preview the impact of deleting or editing an interface entity.
    Call this BEFORE applying the change — shows affected requirements,
    risk level, and available resolution actions.
    """
    from app.services.interface.impact_analyzer import InterfaceImpactAnalyzer

    analyzer = InterfaceImpactAnalyzer(db)

    if data.action == "delete_wire":
        wire_ids = data.entity_id if isinstance(data.entity_id, list) else [data.entity_id]
        return analyzer.preview_wire_deletion(wire_ids)

    elif data.action == "delete_bus":
        entity_id = data.entity_id if isinstance(data.entity_id, int) else data.entity_id[0]
        return analyzer.preview_bus_deletion(entity_id)

    elif data.action == "edit_bus":
        entity_id = data.entity_id if isinstance(data.entity_id, int) else data.entity_id[0]
        return analyzer.preview_bus_edit(entity_id, data.changes or {})

    elif data.action == "edit_message":
        entity_id = data.entity_id if isinstance(data.entity_id, int) else data.entity_id[0]
        return analyzer.preview_message_edit(entity_id, data.changes or {})

    elif data.action == "delete_unit":
        entity_id = data.entity_id if isinstance(data.entity_id, int) else data.entity_id[0]
        return analyzer.preview_unit_deletion(entity_id)

    else:
        raise HTTPException(400, f"Unknown action: {data.action}. "
                            f"Valid: delete_wire, delete_bus, edit_bus, edit_message, delete_unit")


@router.post("/impact/execute")
def impact_execute(
    data: _ImpactExecuteRequest,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    """
    Execute the user's chosen resolution for affected requirements.
    Call this AFTER the user reviews the impact preview and picks an action.
    """
    from app.services.interface.impact_analyzer import InterfaceImpactAnalyzer

    if data.action not in ("delete_requirements", "orphan_requirements", "mark_for_review"):
        raise HTTPException(400, f"Unknown action: {data.action}. "
                            f"Valid: delete_requirements, orphan_requirements, mark_for_review")

    if not data.affected_req_ids:
        raise HTTPException(400, "No requirement IDs provided")

    analyzer = InterfaceImpactAnalyzer(db)
    result = analyzer.execute_action(
        affected_req_ids=data.affected_req_ids,
        action=data.action,
        user=current_user,
        project_id=data.project_id,
        change_description=data.change_description,
    )
    db.commit()

    _audit(db, "interface.impact_executed", "bulk", 0, current_user.id,
           {"action": data.action, "req_count": len(data.affected_req_ids),
            "processed": result.get("processed", 0)},
           project_id=data.project_id, request=request)

    return result


# ══════════════════════════════════════════════════════════════
#  Phase 2 helpers
# ══════════════════════════════════════════════════════════════

def _populate_wire_joins(db: Session, resp: WireResponse, wire: Wire):
    """Fill computed join fields on a WireResponse."""
    fp = db.query(Pin).filter(Pin.id == wire.from_pin_id).first()
    tp = db.query(Pin).filter(Pin.id == wire.to_pin_id).first()
    if fp:
        resp.from_pin_number = fp.pin_number
        resp.from_signal_name = fp.signal_name
        fc = db.query(Connector).filter(Connector.id == fp.connector_id).first()
        if fc:
            resp.from_connector_designator = fc.designator
            fu = db.query(Unit).filter(Unit.id == fc.unit_id).first()
            if fu:
                resp.from_unit_designation = fu.designation
    if tp:
        resp.to_pin_number = tp.pin_number
        resp.to_signal_name = tp.signal_name
        tc = db.query(Connector).filter(Connector.id == tp.connector_id).first()
        if tc:
            resp.to_connector_designator = tc.designator
            tu = db.query(Unit).filter(Unit.id == tc.unit_id).first()
            if tu:
                resp.to_unit_designation = tu.designation


def _populate_harness_joins(db: Session, resp, harness: WireHarness):
    """Fill computed join fields on a WireHarnessResponse."""
    fu = db.query(Unit).filter(Unit.id == harness.from_unit_id).first()
    fc = db.query(Connector).filter(Connector.id == harness.from_connector_id).first()
    tu = db.query(Unit).filter(Unit.id == harness.to_unit_id).first()
    tc = db.query(Connector).filter(Connector.id == harness.to_connector_id).first()
    resp.from_unit_designation = fu.designation if fu else None
    resp.from_connector_designator = fc.designator if fc else None
    resp.to_unit_designation = tu.designation if tu else None
    resp.to_connector_designator = tc.designator if tc else None


def _populate_pin_mating(db: Session, resp: "PinResponse", pin: "Pin"):
    """Fill mating-LRU display fields on a PinResponse.

    The Pin row stores only `mating_unit_id` (FK). For the frontend to
    render the peer's designation without a second round-trip, we look
    up the Unit here and populate `mating_unit_designation` / `_name`.

    Safe to call when mating_unit_id is None (no-op) or when the target
    unit has been deleted (leaves display fields null).
    """
    mating_id = getattr(pin, "mating_unit_id", None)
    if not mating_id:
        return
    mu = db.query(Unit).filter(Unit.id == mating_id).first()
    if mu:
        resp.mating_unit_designation = mu.designation
        resp.mating_unit_name = mu.name


_CRIT_RANKS = {
    "catastrophic": 10, "hazardous": 9, "major": 8, "minor": 7,
    "safety_critical_a": 6, "safety_critical_b": 5, "safety_critical_c": 4,
    "mission_critical": 3, "mission_essential": 2, "mission_support": 1,
    "no_effect": 0, "non_critical": 0,
}


def _crit_rank(c: str | None) -> int:
    return _CRIT_RANKS.get(c or "", -1)


# ══════════════════════════════════════════════════════════════════════════
#  Phase 2a — Auto-Grow, Connections, and Harness Endpoint CRUD
# ══════════════════════════════════════════════════════════════════════════

from app.services.interface.auto_grow import (
    AutoGrowEngine,
    AutoGrowPair as _AGPair,
    AmbiguityDecision as _AGDec,
    maybe_delete_connection_for_wire,
)


def _populate_endpoint_joins(db: Session, resp: HarnessEndpointResponse, endpoint: HarnessEndpoint):
    """Fill in denormalized display fields on a HarnessEndpointResponse so
    the frontend can render without extra round-trips."""
    mating = db.query(Connector).filter(Connector.id == endpoint.mating_connector_id).first()
    if mating:
        resp.mating_connector_designator = mating.designator
        resp.mating_connector_type = _ev(mating.connector_type) if mating.connector_type else None
    if endpoint.lru_connector_id is not None:
        lru = db.query(Connector).filter(Connector.id == endpoint.lru_connector_id).first()
        if lru:
            resp.lru_connector_designator = lru.designator
            if lru.unit_id:
                resp.lru_unit_id = lru.unit_id
                u = db.query(Unit).filter(Unit.id == lru.unit_id).first()
                if u:
                    resp.lru_unit_designation = u.designation
                    resp.lru_unit_name = u.name
    # Wire count for this endpoint = wires that touch this endpoint's mating
    # connector on either side
    if mating:
        wc = (db.query(func.count(Wire.id))
              .join(Pin, (Pin.id == Wire.from_mating_pin_id) | (Pin.id == Wire.to_mating_pin_id))
              .filter(Pin.connector_id == mating.id)
              .scalar()) or 0
        resp.wire_count = wc


# ── Auto-Grow entry point ───────────────────────────────────────────────

@router.post("/auto-grow", response_model=AutoGrowResultSchema)
def auto_grow(
    payload: AutoGrowRequest,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    """Process a batch of proposed wires, auto-growing harnesses as needed.

    If any pair is ambiguous (both LRUs already on different harnesses) and
    the caller didn't supply a decision for it, the response contains an
    `ambiguities` list and nothing was committed. The caller resolves each
    ambiguity modal sequentially, accumulates AmbiguityDecision entries,
    and re-submits with the full `decisions` list.

    When `ambiguities` is empty, wires are created and Connection rollups
    are updated in a single atomic commit.
    """
    _require_project(db, payload.project_id, current_user)
    engine = AutoGrowEngine(db, payload.project_id, current_user)

    pairs = [_AGPair(
        from_lru_pin_id=p.from_lru_pin_id,
        to_lru_pin_id=p.to_lru_pin_id,
        signal_name=p.signal_name,
        wire_type=p.wire_type,
        wire_gauge=p.wire_gauge,
    ) for p in payload.pairs]

    decisions = [_AGDec(
        pair_index=d.pair_index,
        action=d.action,
        new_harness_name=d.new_harness_name,
    ) for d in (payload.decisions or [])]

    try:
        result = engine.run(pairs=pairs, decisions=decisions)
    except ValueError as e:
        # Engine raises ValueError for invalid inputs / impossible decisions
        # (bad action for an ambiguity, claimed connector for new_harness,
        # etc.). Translate to a loud 400 so the client sees a clean error
        # instead of a mystery 500.
        db.rollback()
        raise HTTPException(400, str(e))
    except Exception as e:
        db.rollback()
        logger.error(f"auto-grow failed: {e}", exc_info=True)
        raise HTTPException(500, f"Auto-grow failed: {e}")

    # Audit whichever path completed
    if not result.ambiguities:
        try:
            _audit(
                db, "auto_grow.executed", "project", payload.project_id, current_user.id,
                {
                    "pairs_submitted": len(payload.pairs),
                    "wires_created": result.wires_created,
                    "harnesses_created": result.harnesses_created,
                    "endpoints_added": result.endpoints_added,
                    "connections_touched": result.connections_touched,
                },
                project_id=payload.project_id, request=request,
            )
        except Exception:
            pass

    # Map dataclass result → Pydantic
    return AutoGrowResultSchema(
        wires_created=result.wires_created,
        harnesses_created=result.harnesses_created,
        endpoints_added=result.endpoints_added,
        ambiguities=[AutoGrowAmbiguitySchema(
            pair_index=a.pair_index,
            from_lru_pin_id=a.from_lru_pin_id,
            to_lru_pin_id=a.to_lru_pin_id,
            from_lru_unit_id=a.from_lru_unit_id,
            from_lru_unit_designation=a.from_lru_unit_designation,
            to_lru_unit_id=a.to_lru_unit_id,
            to_lru_unit_designation=a.to_lru_unit_designation,
            harness_a_id=a.harness_a_id,
            harness_a_name=a.harness_a_name,
            harness_a_wire_count=a.harness_a_wire_count,
            harness_a_endpoint_count=a.harness_a_endpoint_count,
            harness_b_id=a.harness_b_id,
            harness_b_name=a.harness_b_name,
            harness_b_wire_count=a.harness_b_wire_count,
            harness_b_endpoint_count=a.harness_b_endpoint_count,
            harness_a_lru_designations=a.harness_a_lru_designations,
            harness_b_lru_designations=a.harness_b_lru_designations,
            valid_actions=a.valid_actions,
            new_harness_disallowed_reason=a.new_harness_disallowed_reason,
        ) for a in result.ambiguities],
        connections_touched=result.connections_touched,
        new_wire_ids=result.new_wire_ids,
        new_harness_ids=result.new_harness_ids,
        skipped=[{
            "pair_index": s.pair_index,
            "from_lru_pin_id": s.from_lru_pin_id,
            "to_lru_pin_id": s.to_lru_pin_id,
            "reason": s.reason,
        } for s in result.skipped],
    )


# ── Connections (bidirectional LRU-pair rollup) ─────────────────────────

@router.get("/connections", response_model=List[ConnectionResponse])
def list_connections(
    project_id: int = Query(...),
    system_id: Optional[int] = Query(None, description="Filter to connections where at least one LRU is in this system"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List connections for a project. Each row is an unordered LRU pair
    that has at least one wire between the two units.

    Per Mason's spec, a system filter is available: when passed, the result
    is filtered to connections where at least one endpoint LRU belongs to
    the given system. This drives the system-scoped Connections tab.
    """
    _require_project(db, project_id, current_user)

    q = db.query(Connection).filter(Connection.project_id == project_id)

    if system_id is not None:
        # Connection qualifies if unit_a's system OR unit_b's system matches
        relevant_unit_ids = [r[0] for r in db.query(Unit.id).filter(Unit.system_id == system_id).all()]
        if not relevant_unit_ids:
            return []
        q = q.filter(
            (Connection.lru_a_id.in_(relevant_unit_ids)) |
            (Connection.lru_b_id.in_(relevant_unit_ids))
        )

    connections = q.order_by(Connection.id).all()

    # Build responses with denormalized fields
    results = []
    for c in connections:
        resp = ConnectionResponse.model_validate(c)
        ua = db.query(Unit).filter(Unit.id == c.lru_a_id).first()
        ub = db.query(Unit).filter(Unit.id == c.lru_b_id).first()
        if ua:
            resp.lru_a_designation = ua.designation
            resp.lru_a_name = ua.name
        if ub:
            resp.lru_b_designation = ub.designation
            resp.lru_b_name = ub.name

        # wire_count and harness_ids: walk wires touching either unit pair
        from sqlalchemy.orm import aliased
        FromPin = aliased(Pin); ToPin = aliased(Pin)
        FromConn = aliased(Connector); ToConn = aliased(Connector)
        wire_rows = (
            db.query(Wire.id, Wire.harness_id)
            .join(FromPin, FromPin.id == Wire.from_pin_id)
            .join(FromConn, FromConn.id == FromPin.connector_id)
            .join(ToPin, ToPin.id == Wire.to_pin_id)
            .join(ToConn, ToConn.id == ToPin.connector_id)
            .filter(
                ((FromConn.unit_id == c.lru_a_id) & (ToConn.unit_id == c.lru_b_id)) |
                ((FromConn.unit_id == c.lru_b_id) & (ToConn.unit_id == c.lru_a_id))
            ).all()
        )
        resp.wire_count = len(wire_rows)
        harness_ids_set = {h for (_, h) in wire_rows if h is not None}
        resp.harness_ids = sorted(harness_ids_set)
        if harness_ids_set:
            names = [
                n[0] for n in
                db.query(WireHarness.name).filter(WireHarness.id.in_(harness_ids_set)).all()
            ]
            resp.harness_names = names
        results.append(resp)

    return results


@router.get("/connections/{conn_pk}", response_model=ConnectionDetail)
def get_connection(
    conn_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full detail for a Connection: all wires between the two LRUs,
    grouped for UI consumption."""
    c = db.query(Connection).filter(Connection.id == conn_pk).first()
    if not c:
        raise HTTPException(404, "Connection not found")

    resp = ConnectionDetail.model_validate(c)

    ua = db.query(Unit).filter(Unit.id == c.lru_a_id).first()
    ub = db.query(Unit).filter(Unit.id == c.lru_b_id).first()
    if ua:
        resp.lru_a_designation = ua.designation
        resp.lru_a_name = ua.name
    if ub:
        resp.lru_b_designation = ub.designation
        resp.lru_b_name = ub.name

    # Gather all wires between these two LRUs
    from sqlalchemy.orm import aliased
    FromPin = aliased(Pin); ToPin = aliased(Pin)
    FromConn = aliased(Connector); ToConn = aliased(Connector)
    wires = (
        db.query(Wire)
        .join(FromPin, FromPin.id == Wire.from_pin_id)
        .join(FromConn, FromConn.id == FromPin.connector_id)
        .join(ToPin, ToPin.id == Wire.to_pin_id)
        .join(ToConn, ToConn.id == ToPin.connector_id)
        .filter(
            ((FromConn.unit_id == c.lru_a_id) & (ToConn.unit_id == c.lru_b_id)) |
            ((FromConn.unit_id == c.lru_b_id) & (ToConn.unit_id == c.lru_a_id))
        )
        .order_by(Wire.wire_number)
        .all()
    )
    resp.wire_count = len(wires)
    harness_ids_set = {w.harness_id for w in wires if w.harness_id}
    resp.harness_ids = sorted(harness_ids_set)
    if harness_ids_set:
        resp.harness_names = [
            n[0] for n in
            db.query(WireHarness.name).filter(WireHarness.id.in_(harness_ids_set)).all()
        ]

    wire_responses = []
    for w in wires:
        wr = WireResponse.model_validate(w)
        _populate_wire_joins(db, wr, w)
        wire_responses.append(wr)
    resp.wires = wire_responses

    return resp


# ── Harness Endpoint CRUD ───────────────────────────────────────────────

@router.get("/harnesses/{har_pk}/endpoints", response_model=List[HarnessEndpointResponse])
def list_harness_endpoints(
    har_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all endpoints for a harness with denormalized display fields."""
    harness = db.query(WireHarness).filter(WireHarness.id == har_pk).first()
    if not harness:
        raise HTTPException(404, "Wire harness not found")

    endpoints = (db.query(HarnessEndpoint)
                 .filter(HarnessEndpoint.harness_id == har_pk)
                 .order_by(HarnessEndpoint.id).all())
    results = []
    for ep in endpoints:
        resp = HarnessEndpointResponse.model_validate(ep)
        _populate_endpoint_joins(db, resp, ep)
        results.append(resp)
    return results


@router.post("/harnesses/{har_pk}/endpoints", response_model=HarnessEndpointResponse, status_code=201)
def create_harness_endpoint(
    har_pk: int,
    data: HarnessEndpointCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    """Add a new endpoint to an existing harness.

    The router uses AutoGrowEngine._create_endpoint so the mating connector
    cloning logic (gender-flip, pin cloning, etc.) stays in one place.
    """
    harness = db.query(WireHarness).filter(WireHarness.id == har_pk).first()
    if not harness:
        raise HTTPException(404, "Wire harness not found")

    lru_conn = db.query(Connector).filter(Connector.id == data.lru_connector_id).first()
    if not lru_conn:
        raise HTTPException(404, "LRU connector not found")
    if lru_conn.owner_type != "unit":
        raise HTTPException(400, "lru_connector_id must reference a unit-owned connector")

    # Uniqueness check — an LRU connector can only be on one harness
    existing = db.query(HarnessEndpoint).filter(HarnessEndpoint.lru_connector_id == data.lru_connector_id).first()
    if existing:
        raise HTTPException(
            409,
            f"Connector {lru_conn.designator} is already plugged into harness {existing.harness_id}"
        )

    engine = AutoGrowEngine(db, harness.project_id, current_user)
    ep = engine._create_endpoint(har_pk, lru_conn, label=data.label or f"P{len(harness.endpoints or []) + 1}" if hasattr(harness, 'endpoints') else (data.label or "P?"))
    if data.tail_length_m is not None:
        ep.tail_length_m = data.tail_length_m
    if data.notes is not None:
        ep.notes = data.notes
    db.commit()
    db.refresh(ep)

    _audit(db, "harness.endpoint_added", "wire_harness", har_pk, current_user.id,
           {"endpoint_id": ep.id, "lru_connector_id": data.lru_connector_id},
           project_id=harness.project_id, request=request)

    resp = HarnessEndpointResponse.model_validate(ep)
    _populate_endpoint_joins(db, resp, ep)
    return resp


@router.patch("/endpoints/{ep_pk}", response_model=HarnessEndpointResponse)
def update_harness_endpoint(
    ep_pk: int,
    data: HarnessEndpointUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.update")),
):
    ep = db.query(HarnessEndpoint).filter(HarnessEndpoint.id == ep_pk).first()
    if not ep:
        raise HTTPException(404, "Harness endpoint not found")
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(ep, field, value)
    db.commit()
    db.refresh(ep)

    harness = db.query(WireHarness).filter(WireHarness.id == ep.harness_id).first()
    _audit(db, "harness.endpoint_updated", "wire_harness", ep.harness_id, current_user.id,
           {"endpoint_id": ep.id, "fields": list(updates.keys())},
           project_id=harness.project_id if harness else None, request=request)

    resp = HarnessEndpointResponse.model_validate(ep)
    _populate_endpoint_joins(db, resp, ep)
    return resp


@router.delete("/endpoints/{ep_pk}", status_code=200)
def delete_harness_endpoint(
    ep_pk: int,
    confirm: bool = Query(False),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.delete")),
):
    """Delete a harness endpoint. This also deletes the mating connector
    (and its pins via cascade) and any wires that touch this endpoint's
    mating pins on either side.

    Requires confirm=true if there are wires to avoid surprises.
    """
    ep = db.query(HarnessEndpoint).filter(HarnessEndpoint.id == ep_pk).first()
    if not ep:
        raise HTTPException(404, "Harness endpoint not found")

    mating_connector_id = ep.mating_connector_id
    harness_id = ep.harness_id

    # Count wires touching this endpoint's mating pins
    wire_count = (db.query(func.count(Wire.id))
                  .join(Pin, (Pin.id == Wire.from_mating_pin_id) | (Pin.id == Wire.to_mating_pin_id))
                  .filter(Pin.connector_id == mating_connector_id)
                  .scalar()) or 0

    if wire_count > 0 and not confirm:
        return {"status": "preview", "impact": {"wires": wire_count}}

    # Delete wires touching this endpoint's mating pins
    if wire_count > 0:
        wires_to_delete = (db.query(Wire)
                           .join(Pin, (Pin.id == Wire.from_mating_pin_id) | (Pin.id == Wire.to_mating_pin_id))
                           .filter(Pin.connector_id == mating_connector_id).all())
        for w in wires_to_delete:
            maybe_delete_connection_for_wire(db, w)
            db.delete(w)
        db.flush()

    # Delete the endpoint (CASCADE in migration drops mating connector + its pins)
    db.delete(ep)
    # Also delete the mating connector explicitly (belt and suspenders since
    # the FK is ON DELETE CASCADE the other way — harness_endpoints cascades
    # from connectors deletion, not the other direction)
    mating = db.query(Connector).filter(Connector.id == mating_connector_id).first()
    if mating and mating.owner_type == "harness":
        # Its pins will cascade via the pins.connector_id FK
        db.delete(mating)

    db.commit()

    harness = db.query(WireHarness).filter(WireHarness.id == harness_id).first()
    _audit(db, "harness.endpoint_deleted", "wire_harness", harness_id, current_user.id,
           {"endpoint_id": ep_pk, "wires_removed": wire_count},
           project_id=harness.project_id if harness else None, request=request)

    return {"status": "deleted", "id": ep_pk, "wires_removed": wire_count}
