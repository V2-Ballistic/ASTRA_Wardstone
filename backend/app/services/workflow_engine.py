"""
ASTRA — Multi-Stage Workflow Engine
=====================================
File: backend/app/services/workflow_engine.py   ← NEW

Orchestrates the lifecycle of approval workflows:
  start_workflow()   — create an instance and activate stage 1
  perform_action()   — approve/reject at a stage (with e-sig)
  advance_stages()   — check if current stage is satisfied → move forward
  check_timeouts()   — escalate or time-out overdue stages
  get_instance_detail() — full status view of a running instance

Standard 4-stage example:
  1. Req Engineer submits → 2. Peer Review → 3. PM Approval → 4. CCB (for baselines)
"""

from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session

from app.models import User
from app.models.workflow import (
    ApprovalWorkflow, WorkflowStage, WorkflowInstance,
    StageAction, ElectronicSignature,
    InstanceStatus, StageInstanceStatus, WorkflowStatus,
)
from app.services.signature_service import request_signature

# Optional audit hook
try:
    from app.services.audit_service import record_event as _audit
except ImportError:
    def _audit(*a, **kw):
        pass


# ══════════════════════════════════════
#  Start
# ══════════════════════════════════════

def start_workflow(
    db: Session,
    workflow_id: int,
    entity_type: str,
    entity_id: int,
    project_id: int,
    submitted_by_id: int,
) -> WorkflowInstance:
    """Create a workflow instance and activate stage 1."""
    wf = db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.id == workflow_id,
        ApprovalWorkflow.status == WorkflowStatus.ACTIVE,
    ).first()
    if not wf:
        raise ValueError("Workflow not found or inactive")

    if not wf.stages:
        raise ValueError("Workflow has no stages configured")

    instance = WorkflowInstance(
        workflow_id=workflow_id,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        status=InstanceStatus.IN_PROGRESS,
        current_stage_number=1,
        submitted_by_id=submitted_by_id,
    )
    db.add(instance)
    db.commit()
    db.refresh(instance)

    _audit(
        db, "workflow.started", entity_type, entity_id, submitted_by_id,
        {"workflow_id": workflow_id, "instance_id": instance.id,
         "workflow_name": wf.name},
        project_id=project_id,
    )

    return instance


# ══════════════════════════════════════
#  Perform Action
# ══════════════════════════════════════

def perform_action(
    db: Session,
    instance_id: int,
    user_id: int,
    action: str,
    password: str = "",
    comment: str = "",
    ip_address: str = "",
    user_agent: str = "",
) -> dict:
    """
    Record an approve / reject / review action on the current stage.

    If the stage requires a signature, *password* must be provided for
    e-sig creation.

    Returns {"status": "ok"|"error", ...}
    """
    instance = db.query(WorkflowInstance).filter(
        WorkflowInstance.id == instance_id,
    ).first()
    if not instance:
        return {"status": "error", "detail": "Workflow instance not found"}
    if instance.status not in (InstanceStatus.IN_PROGRESS, InstanceStatus.PENDING):
        return {"status": "error", "detail": f"Workflow is {instance.status.value}, not actionable"}

    wf = db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.id == instance.workflow_id
    ).first()
    if not wf:
        return {"status": "error", "detail": "Workflow template missing"}

    # Find the current stage template
    stage_tmpl = _get_stage(wf, instance.current_stage_number)
    if not stage_tmpl:
        return {"status": "error", "detail": "Current stage template not found"}

    # Role check
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return {"status": "error", "detail": "User not found"}
    if stage_tmpl.required_role:
        user_role = user.role.value if hasattr(user.role, "value") else str(user.role)
        if user_role != stage_tmpl.required_role:
            return {
                "status": "error",
                "detail": f"Stage '{stage_tmpl.name}' requires role '{stage_tmpl.required_role}', you are '{user_role}'",
            }

    # Prevent duplicate actions by same user on same stage
    existing = db.query(StageAction).filter(
        StageAction.instance_id == instance_id,
        StageAction.stage_number == instance.current_stage_number,
        StageAction.user_id == user_id,
    ).first()
    if existing:
        return {"status": "error", "detail": "You have already acted on this stage"}

    # E-signature (if required by stage)
    sig_id = None
    if stage_tmpl.require_signature:
        if not password:
            return {"status": "error", "detail": "Password required for electronic signature at this stage"}
        sig = request_signature(
            db, user_id, instance.entity_type, instance.entity_id,
            action, password,
            statement=f"Stage '{stage_tmpl.name}': {action}",
            ip_address=ip_address, user_agent=user_agent,
        )
        if not sig:
            return {"status": "error", "detail": "Password verification failed — signature denied"}
        sig_id = sig.id

    # Record the action
    sa = StageAction(
        instance_id=instance_id,
        stage_number=instance.current_stage_number,
        user_id=user_id,
        action=action,
        comment=comment,
        signature_id=sig_id,
    )
    db.add(sa)
    db.commit()

    _audit(
        db, f"workflow.stage_{action}", instance.entity_type,
        instance.entity_id, user_id,
        {"instance_id": instance_id,
         "stage": stage_tmpl.name,
         "stage_number": instance.current_stage_number,
         "action": action},
        project_id=instance.project_id,
    )

    # Advance the workflow
    result = _advance(db, instance, wf)

    return {
        "status": "ok",
        "action": action,
        "stage": stage_tmpl.name,
        "signature_id": sig_id,
        "workflow_status": result["instance_status"],
        "current_stage": result["current_stage"],
    }


# ══════════════════════════════════════
#  Internal: Advance Logic
# ══════════════════════════════════════

def _get_stage(wf: ApprovalWorkflow, stage_number: int) -> Optional[WorkflowStage]:
    for s in wf.stages:
        if s.stage_number == stage_number:
            return s
    return None


def _advance(db: Session, instance: WorkflowInstance, wf: ApprovalWorkflow) -> dict:
    """Check if the current stage is satisfied and advance."""
    stage_tmpl = _get_stage(wf, instance.current_stage_number)
    if not stage_tmpl:
        return {"instance_status": instance.status.value, "current_stage": None}

    # Count approvals and rejections at the current stage
    actions = db.query(StageAction).filter(
        StageAction.instance_id == instance.id,
        StageAction.stage_number == instance.current_stage_number,
    ).all()
    approvals = [a for a in actions if a.action == "approved"]
    rejections = [a for a in actions if a.action == "rejected"]

    # Rejection at any stage rejects the whole workflow
    if rejections:
        instance.status = InstanceStatus.REJECTED
        instance.completed_at = datetime.utcnow()
        db.commit()
        _audit(
            db, "workflow.rejected", instance.entity_type,
            instance.entity_id, rejections[0].user_id,
            {"instance_id": instance.id, "stage": stage_tmpl.name},
            project_id=instance.project_id,
        )
        return {"instance_status": "rejected", "current_stage": stage_tmpl.name}

    # Check if required approvals met
    if len(approvals) >= stage_tmpl.required_count:
        max_stage = max(s.stage_number for s in wf.stages)

        if instance.current_stage_number >= max_stage:
            # All stages done
            instance.status = InstanceStatus.APPROVED
            instance.completed_at = datetime.utcnow()
            db.commit()
            _audit(
                db, "workflow.approved", instance.entity_type,
                instance.entity_id, instance.submitted_by_id,
                {"instance_id": instance.id},
                project_id=instance.project_id,
            )
            return {"instance_status": "approved", "current_stage": None}
        else:
            # Move to next stage
            next_num = instance.current_stage_number + 1
            # Handle parallel: if current stage has can_parallel, we already
            # allowed next-stage actions; just bump the pointer
            instance.current_stage_number = next_num
            db.commit()
            next_tmpl = _get_stage(wf, next_num)
            _audit(
                db, "workflow.stage_advanced", instance.entity_type,
                instance.entity_id, instance.submitted_by_id,
                {"instance_id": instance.id,
                 "from_stage": stage_tmpl.name,
                 "to_stage": next_tmpl.name if next_tmpl else "?"},
                project_id=instance.project_id,
            )
            return {
                "instance_status": "in_progress",
                "current_stage": next_tmpl.name if next_tmpl else None,
            }

    # Not enough approvals yet
    return {
        "instance_status": "in_progress",
        "current_stage": stage_tmpl.name,
    }


# ══════════════════════════════════════
#  Timeout / Escalation
# ══════════════════════════════════════

def check_timeouts(db: Session) -> list[dict]:
    """
    Check all in-progress instances for stage timeouts.
    Call this from a periodic task / cron job.
    Returns a list of escalation events that occurred.
    """
    active = db.query(WorkflowInstance).filter(
        WorkflowInstance.status == InstanceStatus.IN_PROGRESS,
    ).all()

    escalations = []

    for inst in active:
        wf = db.query(ApprovalWorkflow).filter(
            ApprovalWorkflow.id == inst.workflow_id
        ).first()
        if not wf:
            continue
        stage = _get_stage(wf, inst.current_stage_number)
        if not stage or stage.timeout_hours <= 0:
            continue

        # Find the latest action or instance submission time
        latest_action = (
            db.query(StageAction)
            .filter(
                StageAction.instance_id == inst.id,
                StageAction.stage_number == inst.current_stage_number,
            )
            .order_by(StageAction.acted_at.desc())
            .first()
        )
        ref_time = latest_action.acted_at if latest_action else inst.submitted_at
        deadline = ref_time + timedelta(hours=stage.timeout_hours)

        if datetime.utcnow() > deadline:
            if stage.auto_escalate_to_role:
                escalations.append({
                    "instance_id": inst.id,
                    "entity": f"{inst.entity_type}:{inst.entity_id}",
                    "stage": stage.name,
                    "escalate_to": stage.auto_escalate_to_role,
                })
            else:
                inst.status = InstanceStatus.TIMED_OUT
                inst.completed_at = datetime.utcnow()
                escalations.append({
                    "instance_id": inst.id,
                    "entity": f"{inst.entity_type}:{inst.entity_id}",
                    "stage": stage.name,
                    "timed_out": True,
                })

    db.commit()
    return escalations


# ══════════════════════════════════════
#  Query
# ══════════════════════════════════════

def get_instance_detail(db: Session, instance_id: int) -> dict | None:
    """Full status view of a workflow instance with all stages."""
    inst = db.query(WorkflowInstance).filter(
        WorkflowInstance.id == instance_id
    ).first()
    if not inst:
        return None

    wf = db.query(ApprovalWorkflow).filter(
        ApprovalWorkflow.id == inst.workflow_id
    ).first()
    submitter = db.query(User).filter(User.id == inst.submitted_by_id).first()

    stages_detail = []
    for stage in (wf.stages if wf else []):
        actions = db.query(StageAction).filter(
            StageAction.instance_id == inst.id,
            StageAction.stage_number == stage.stage_number,
        ).order_by(StageAction.acted_at.asc()).all()

        approvals = len([a for a in actions if a.action == "approved"])
        rejections = len([a for a in actions if a.action == "rejected"])

        # Determine stage status
        if rejections:
            s_status = "rejected"
        elif approvals >= stage.required_count:
            s_status = "completed"
        elif stage.stage_number < inst.current_stage_number:
            s_status = "completed"
        elif stage.stage_number == inst.current_stage_number:
            s_status = "active"
        else:
            s_status = "waiting"

        action_list = []
        for a in actions:
            u = db.query(User).filter(User.id == a.user_id).first()
            action_list.append({
                "id": a.id,
                "user_id": a.user_id,
                "user_full_name": u.full_name if u else "Unknown",
                "user_role": u.role.value if u and hasattr(u.role, "value") else str(u.role) if u else None,
                "action": a.action,
                "comment": a.comment,
                "signature_id": a.signature_id,
                "acted_at": a.acted_at.isoformat() if a.acted_at else None,
            })

        stages_detail.append({
            "stage_number": stage.stage_number,
            "name": stage.name,
            "description": stage.description,
            "required_role": stage.required_role,
            "required_count": stage.required_count,
            "require_signature": stage.require_signature,
            "timeout_hours": stage.timeout_hours,
            "can_parallel": stage.can_parallel,
            "status": s_status,
            "approval_count": approvals,
            "rejection_count": rejections,
            "actions": action_list,
        })

    return {
        "id": inst.id,
        "workflow_id": inst.workflow_id,
        "workflow_name": wf.name if wf else None,
        "entity_type": inst.entity_type,
        "entity_id": inst.entity_id,
        "project_id": inst.project_id,
        "status": inst.status.value if hasattr(inst.status, "value") else str(inst.status),
        "current_stage_number": inst.current_stage_number,
        "submitted_by": submitter.full_name if submitter else "Unknown",
        "submitted_at": inst.submitted_at.isoformat() if inst.submitted_at else None,
        "completed_at": inst.completed_at.isoformat() if inst.completed_at else None,
        "stages": stages_detail,
    }


def list_instances(
    db: Session, project_id: int | None = None,
    entity_type: str | None = None, entity_id: int | None = None,
    status_filter: str | None = None,
    skip: int = 0, limit: int = 50,
) -> dict:
    """Paginated list of workflow instances."""
    query = db.query(WorkflowInstance)
    if project_id:
        query = query.filter(WorkflowInstance.project_id == project_id)
    if entity_type:
        query = query.filter(WorkflowInstance.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(WorkflowInstance.entity_id == entity_id)
    if status_filter:
        query = query.filter(WorkflowInstance.status == status_filter)

    total = query.count()
    instances = query.order_by(WorkflowInstance.submitted_at.desc()).offset(skip).limit(limit).all()

    items = []
    for inst in instances:
        wf = db.query(ApprovalWorkflow).filter(ApprovalWorkflow.id == inst.workflow_id).first()
        sub = db.query(User).filter(User.id == inst.submitted_by_id).first()
        items.append({
            "id": inst.id,
            "workflow_name": wf.name if wf else None,
            "entity_type": inst.entity_type,
            "entity_id": inst.entity_id,
            "status": inst.status.value if hasattr(inst.status, "value") else str(inst.status),
            "current_stage_number": inst.current_stage_number,
            "submitted_by": sub.full_name if sub else "Unknown",
            "submitted_at": inst.submitted_at.isoformat() if inst.submitted_at else None,
        })
    return {"total": total, "items": items}
