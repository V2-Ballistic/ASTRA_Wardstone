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
from app.models import User, Project
from app.models.interface import (
    System, Unit, Connector, Pin, BusDefinition,
    PinBusAssignment, MessageDefinition, MessageField,
    WireHarness, Wire, Interface,
    UnitEnvironmentalSpec, InterfaceRequirementLink,
    AutoRequirementLog, InterfaceChangeImpact,
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


def _require_project(db: Session, project_id: int) -> Project:
    """Validate project exists."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, f"Project {project_id} not found")
    return project


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
    _require_project(db, project_id)
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
    _require_project(db, project_id)
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
    _require_project(db, project_id)
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
    _require_project(db, project_id)

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
        pin_responses = [PinResponse.model_validate(p) for p in created_pins]
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

    pins = db.query(Pin).filter(Pin.connector_id == conn_pk).order_by(Pin.pin_number).all()
    pin_responses = []
    for p in pins:
        pr = PinResponse.model_validate(p)
        assignment = db.query(PinBusAssignment).filter(PinBusAssignment.pin_id == p.id).first()
        if assignment:
            pr.bus_assignment = PinBusAssignmentResponse.model_validate(assignment)
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

    pins = db.query(Pin).filter(Pin.connector_id == conn_pk).order_by(Pin.pin_number).all()

    # Build pin summary by category
    summary = {"power": 0, "ground": 0, "signal": 0, "spare": 0, "no_connect": 0, "other": 0}
    pin_list = []
    for p in pins:
        pr = PinResponse.model_validate(p)
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
    connector = db.query(Connector).filter(Connector.id == conn_pk).first()
    if not connector:
        raise HTTPException(404, "Connector not found")

    # Check for wires connected to pins on this connector
    wire_count = (
        db.query(func.count(Wire.id))
        .join(Pin, (Wire.from_pin_id == Pin.id) | (Wire.to_pin_id == Pin.id))
        .filter(Pin.connector_id == conn_pk)
        .scalar()
    )

    if wire_count > 0 and not force:
        raise HTTPException(
            409,
            f"Connector has {wire_count} wire(s) connected. Use force=true to cascade delete pins.",
        )

    _audit(db, "connector.deleted", "connector", connector.id, current_user.id,
           {"designator": connector.designator, "force": force},
           project_id=connector.project_id, request=request)

    # Delete pins (cascades via relationship, but explicit for clarity)
    db.query(PinBusAssignment).filter(
        PinBusAssignment.pin_id.in_(
            db.query(Pin.id).filter(Pin.connector_id == conn_pk)
        )
    ).delete(synchronize_session="fetch")
    db.query(Pin).filter(Pin.connector_id == conn_pk).delete()
    db.delete(connector)
    db.commit()

    return {"status": "deleted", "id": conn_pk, "wires_orphaned": wire_count if force else 0}


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

    return [PinResponse.model_validate(p) for p in created]


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

    return [PinResponse.model_validate(p) for p in created]


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
    _require_project(db, project_id)

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
    _require_project(db, project_id)
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
    harness = db.query(WireHarness).filter(WireHarness.id == har_pk).first()
    if not harness:
        raise HTTPException(404, "Wire harness not found")

    from_pin_ids = set(
        r[0] for r in db.query(Pin.id).join(Connector).filter(
            Connector.id == harness.from_connector_id
        ).all()
    )
    to_pin_ids = set(
        r[0] for r in db.query(Pin.id).join(Connector).filter(
            Connector.id == harness.to_connector_id
        ).all()
    )

    # Existing wire numbers in harness
    existing_numbers = set(
        r[0] for r in db.query(Wire.wire_number).filter(Wire.harness_id == har_pk).all()
    )
    # Existing connected pins in harness
    existing_from = set(
        r[0] for r in db.query(Wire.from_pin_id).filter(Wire.harness_id == har_pk).all()
    )
    existing_to = set(
        r[0] for r in db.query(Wire.to_pin_id).filter(Wire.harness_id == har_pk).all()
    )

    created = []
    for wd in data.wires:
        # Validate from_pin belongs to from_connector
        if wd.from_pin_id not in from_pin_ids:
            raise HTTPException(
                400, f"Pin {wd.from_pin_id} is not on the from_connector of harness {har_pk}"
            )
        if wd.to_pin_id not in to_pin_ids:
            raise HTTPException(
                400, f"Pin {wd.to_pin_id} is not on the to_connector of harness {har_pk}"
            )
        if wd.wire_number in existing_numbers:
            raise HTTPException(409, f"Wire number '{wd.wire_number}' already exists in harness")
        if wd.from_pin_id in existing_from:
            raise HTTPException(409, f"From-pin {wd.from_pin_id} already connected in harness")
        if wd.to_pin_id in existing_to:
            raise HTTPException(409, f"To-pin {wd.to_pin_id} already connected in harness")

        existing_numbers.add(wd.wire_number)
        existing_from.add(wd.from_pin_id)
        existing_to.add(wd.to_pin_id)

        wire = Wire(
            harness_id=har_pk,
            **wd.model_dump(exclude_unset=True),
        )
        db.add(wire)
        created.append(wire)

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
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("interfaces.create")),
):
    """Auto-create wires by matching signal names between connectors."""
    harness = db.query(WireHarness).filter(WireHarness.id == har_pk).first()
    if not harness:
        raise HTTPException(404, "Wire harness not found")

    from_pins = db.query(Pin).join(Connector).filter(
        Connector.id == harness.from_connector_id
    ).all()
    to_pins = db.query(Pin).join(Connector).filter(
        Connector.id == harness.to_connector_id
    ).all()

    # Already-connected pins
    existing_from = set(
        r[0] for r in db.query(Wire.from_pin_id).filter(Wire.harness_id == har_pk).all()
    )
    existing_to = set(
        r[0] for r in db.query(Wire.to_pin_id).filter(Wire.harness_id == har_pk).all()
    )
    max_wire_num = db.query(func.max(Wire.wire_number)).filter(
        Wire.harness_id == har_pk
    ).scalar()
    wire_counter = int(re.search(r"(\d+)", max_wire_num).group(1)) + 1 if max_wire_num and re.search(r"(\d+)", max_wire_num) else 1

    # Build lookup from to_pins by signal_name
    to_map: dict = {}
    for tp in to_pins:
        if tp.id not in existing_to and tp.signal_name:
            sn = tp.signal_name.upper().strip()
            if sn not in to_map:
                to_map[sn] = tp

    matched = []
    unmatched_from = []
    unmatched_to_names = set(to_map.keys())

    for fp in from_pins:
        if fp.id in existing_from:
            continue
        sn = (fp.signal_name or "").upper().strip()
        if not sn or sn.startswith("SPARE") or sn.startswith("NC"):
            unmatched_from.append({"pin_id": fp.id, "pin_number": fp.pin_number, "signal_name": fp.signal_name})
            continue

        tp = to_map.get(sn)
        if tp:
            wire_num = f"W{wire_counter:03d}"
            wire_counter += 1
            wire = Wire(
                harness_id=har_pk,
                wire_number=wire_num,
                signal_name=fp.signal_name,
                wire_type=_infer_wire_type(_ev(fp.signal_type)),
                wire_gauge=_infer_wire_gauge(fp.current_max_amps),
                from_pin_id=fp.id,
                to_pin_id=tp.id,
            )
            db.add(wire)
            matched.append(wire)
            unmatched_to_names.discard(sn)
            existing_from.add(fp.id)
            existing_to.add(tp.id)
        else:
            unmatched_from.append({"pin_id": fp.id, "pin_number": fp.pin_number, "signal_name": fp.signal_name})

    db.commit()

    wire_results = []
    for w in matched:
        db.refresh(w)
        wr = WireResponse.model_validate(w)
        _populate_wire_joins(db, wr, w)
        wire_results.append(wr)

    unmatched_to = []
    for sn in unmatched_to_names:
        tp = to_map[sn]
        unmatched_to.append({"pin_id": tp.id, "pin_number": tp.pin_number, "signal_name": tp.signal_name})

    _audit(db, "harness.auto_wired", "wire_harness", har_pk, current_user.id,
           {"matched": len(matched), "unmatched_from": len(unmatched_from), "unmatched_to": len(unmatched_to)},
           project_id=harness.project_id, request=request)

    return {
        "matched": len(matched),
        "unmatched_from": unmatched_from,
        "unmatched_to": unmatched_to,
        "wires_created": wire_results,
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
    _require_project(db, project_id)
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
    _require_project(db, project_id)

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
    _require_project(db, project_id)

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
    _require_project(db, project_id)

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
    _require_project(db, project_id)

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


_CRIT_RANKS = {
    "catastrophic": 10, "hazardous": 9, "major": 8, "minor": 7,
    "safety_critical_a": 6, "safety_critical_b": 5, "safety_critical_c": 4,
    "mission_critical": 3, "mission_essential": 2, "mission_support": 1,
    "no_effect": 0, "non_critical": 0,
}


def _crit_rank(c: str | None) -> int:
    return _CRIT_RANKS.get(c or "", -1)
