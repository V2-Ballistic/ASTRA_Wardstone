"""
ASTRA — Workflow & Signature Router
=====================================
File: backend/app/routers/workflows.py   ← NEW

Endpoints:
  Workflow Templates:
    POST   /workflows/                — create workflow template
    GET    /workflows/                — list templates for a project
    GET    /workflows/{id}            — get template with stages
    PATCH  /workflows/{id}            — update template metadata
    DELETE /workflows/{id}            — deactivate template

  Stages:
    POST   /workflows/{id}/stages     — add a stage
    PATCH  /workflows/stages/{sid}    — update a stage
    DELETE /workflows/stages/{sid}    — remove a stage

  Instances:
    POST   /workflows/instances/start — start a workflow on an entity
    GET    /workflows/instances/      — list instances (filterable)
    GET    /workflows/instances/{id}  — full instance detail + stage progress
    POST   /workflows/instances/{id}/action — approve / reject at current stage

  Signatures:
    GET    /workflows/signatures/{entity_type}/{entity_id} — list e-sigs
    GET    /workflows/signatures/verify/{sig_id}           — verify hash
"""

from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.models.workflow import (
    ApprovalWorkflow, WorkflowStage, WorkflowStatus,
)
from app.services.auth import get_current_user
from app.services.workflow_engine import (
    start_workflow, perform_action, get_instance_detail,
    list_instances, check_timeouts,
)
from app.services.signature_service import (
    get_signatures, verify_signature,
)

try:
    from app.services.rbac import require_any_role
except ImportError:
    def require_any_role(*roles):
        return get_current_user

router = APIRouter(prefix="/workflows", tags=["Workflows"])


# ══════════════════════════════════════
#  Schemas
# ══════════════════════════════════════

class WorkflowCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = ""
    project_id: int
    entity_type: str = "requirement"

class WorkflowUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None

class StageCreate(BaseModel):
    stage_number: int
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = ""
    required_role: Optional[str] = None
    required_count: int = 1
    timeout_hours: int = 0
    auto_escalate_to_role: Optional[str] = None
    can_parallel: bool = False
    require_signature: bool = True

class StageUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    required_role: Optional[str] = None
    required_count: Optional[int] = None
    timeout_hours: Optional[int] = None
    auto_escalate_to_role: Optional[str] = None
    can_parallel: Optional[bool] = None
    require_signature: Optional[bool] = None

class InstanceStart(BaseModel):
    workflow_id: int
    entity_type: str
    entity_id: int
    project_id: int

class ActionPerform(BaseModel):
    action: str = Field(..., pattern="^(approved|rejected|reviewed)$")
    password: str = ""
    comment: str = ""


# ══════════════════════════════════════
#  Workflow Templates
# ══════════════════════════════════════

@router.post("/", status_code=201)
def create_workflow(
    data: WorkflowCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
):
    wf = ApprovalWorkflow(
        name=data.name, description=data.description,
        project_id=data.project_id, entity_type=data.entity_type,
        created_by_id=current_user.id,
    )
    db.add(wf)
    db.commit()
    db.refresh(wf)
    return _wf_to_dict(wf)


@router.get("/")
def list_workflows(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wfs = db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.project_id == project_id,
    ).order_by(ApprovalWorkflow.created_at.desc()).all()
    return [_wf_to_dict(w) for w in wfs]


@router.get("/{workflow_id}")
def get_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(404, "Workflow not found")
    return _wf_to_dict(wf, include_stages=True)


@router.patch("/{workflow_id}")
def update_workflow(
    workflow_id: int, data: WorkflowUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
):
    wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(404, "Workflow not found")
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(wf, field, val)
    db.commit()
    db.refresh(wf)
    return _wf_to_dict(wf, include_stages=True)


@router.delete("/{workflow_id}", status_code=200)
def deactivate_workflow(
    workflow_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
):
    wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(404, "Workflow not found")
    wf.status = WorkflowStatus.INACTIVE
    db.commit()
    return {"status": "deactivated", "id": workflow_id}


# ══════════════════════════════════════
#  Stages
# ══════════════════════════════════════

@router.post("/{workflow_id}/stages", status_code=201)
def add_stage(
    workflow_id: int, data: StageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
):
    wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == workflow_id).first()
    if not wf:
        raise HTTPException(404, "Workflow not found")
    stage = WorkflowStage(workflow_id=workflow_id, **data.model_dump())
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return _stage_to_dict(stage)


@router.patch("/stages/{stage_id}")
def update_stage(
    stage_id: int, data: StageUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
):
    stage = db.query(WorkflowStage).filter(WorkflowStage.id == stage_id).first()
    if not stage:
        raise HTTPException(404, "Stage not found")
    for field, val in data.model_dump(exclude_unset=True).items():
        setattr(stage, field, val)
    db.commit()
    db.refresh(stage)
    return _stage_to_dict(stage)


@router.delete("/stages/{stage_id}", status_code=204)
def remove_stage(
    stage_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
):
    stage = db.query(WorkflowStage).filter(WorkflowStage.id == stage_id).first()
    if not stage:
        raise HTTPException(404, "Stage not found")
    db.delete(stage)
    db.commit()


# ══════════════════════════════════════
#  Instances
# ══════════════════════════════════════

@router.post("/instances/start", status_code=201)
def start_instance(
    data: InstanceStart,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        inst = start_workflow(
            db, data.workflow_id, data.entity_type,
            data.entity_id, data.project_id, current_user.id,
        )
        return get_instance_detail(db, inst.id)
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@router.get("/instances/")
def list_workflow_instances(
    project_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    status: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return list_instances(
        db, project_id=project_id, entity_type=entity_type,
        entity_id=entity_id, status_filter=status,
        skip=skip, limit=limit,
    )


@router.get("/instances/{instance_id}")
def get_workflow_instance(
    instance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    detail = get_instance_detail(db, instance_id)
    if not detail:
        raise HTTPException(404, "Workflow instance not found")
    return detail


@router.post("/instances/{instance_id}/action")
def action_on_instance(
    instance_id: int,
    data: ActionPerform,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ip = request.client.host if request.client else ""
    ua = request.headers.get("user-agent", "")
    result = perform_action(
        db, instance_id, current_user.id,
        data.action, data.password, data.comment,
        ip_address=ip, user_agent=ua,
    )
    if result["status"] == "error":
        raise HTTPException(400, result["detail"])
    return result


@router.post("/instances/check-timeouts")
def run_timeout_check(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
):
    """Manually trigger timeout checks (also runnable via cron)."""
    escalations = check_timeouts(db)
    return {"checked_at": __import__("datetime").datetime.utcnow().isoformat(),
            "escalations": escalations}


# ══════════════════════════════════════
#  Signatures
# ══════════════════════════════════════

@router.get("/signatures/{entity_type}/{entity_id}")
def list_signatures(
    entity_type: str, entity_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return get_signatures(db, entity_type, entity_id)


@router.get("/signatures/verify/{signature_id}")
def verify_sig(
    signature_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return verify_signature(db, signature_id)


# ══════════════════════════════════════
#  Seed: Default 4-Stage Workflow
# ══════════════════════════════════════

@router.post("/seed-default/{project_id}", status_code=201)
def seed_default_workflow(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
):
    """Create the standard 4-stage requirement approval workflow for a project."""
    wf = ApprovalWorkflow(
        name="Standard Requirement Approval",
        description="Engineer Submit → Peer Review → PM Approval → CCB Approval",
        project_id=project_id,
        entity_type="requirement",
        created_by_id=current_user.id,
    )
    db.add(wf)
    db.flush()

    stages = [
        {"stage_number": 1, "name": "Engineer Submission",
         "required_role": "requirements_engineer", "required_count": 1,
         "require_signature": False, "timeout_hours": 0},
        {"stage_number": 2, "name": "Peer Review",
         "required_role": "requirements_engineer", "required_count": 1,
         "require_signature": True, "timeout_hours": 48,
         "auto_escalate_to_role": "project_manager"},
        {"stage_number": 3, "name": "PM Approval",
         "required_role": "project_manager", "required_count": 1,
         "require_signature": True, "timeout_hours": 72,
         "auto_escalate_to_role": "admin"},
        {"stage_number": 4, "name": "CCB Approval",
         "required_role": "admin", "required_count": 1,
         "require_signature": True, "timeout_hours": 120},
    ]
    for s in stages:
        db.add(WorkflowStage(workflow_id=wf.id, **s))
    db.commit()
    db.refresh(wf)
    return _wf_to_dict(wf, include_stages=True)


# ══════════════════════════════════════
#  Helpers
# ══════════════════════════════════════

def _wf_to_dict(wf: ApprovalWorkflow, include_stages: bool = False) -> dict:
    d = {
        "id": wf.id,
        "name": wf.name,
        "description": wf.description,
        "project_id": wf.project_id,
        "entity_type": wf.entity_type,
        "status": wf.status.value if hasattr(wf.status, "value") else str(wf.status),
        "stage_count": len(wf.stages) if wf.stages else 0,
        "created_at": wf.created_at.isoformat() if wf.created_at else None,
    }
    if include_stages:
        d["stages"] = [_stage_to_dict(s) for s in (wf.stages or [])]
    return d


def _stage_to_dict(s: WorkflowStage) -> dict:
    return {
        "id": s.id,
        "stage_number": s.stage_number,
        "name": s.name,
        "description": s.description,
        "required_role": s.required_role,
        "required_count": s.required_count,
        "timeout_hours": s.timeout_hours,
        "auto_escalate_to_role": s.auto_escalate_to_role,
        "can_parallel": s.can_parallel,
        "require_signature": s.require_signature,
    }
