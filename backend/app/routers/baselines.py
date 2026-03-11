"""
ASTRA — Baselines Router (Audit-Instrumented)
===============================================
File: backend/app/routers/baselines.py   ← REPLACES existing

Adds record_event() to create_baseline and delete_baseline.
List / get / compare endpoints are read-only and unchanged.
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Baseline, BaselineRequirement, Requirement, Project, User
from app.services.auth import get_current_user
from app.services.audit_service import record_event

try:
    from app.services.rbac import require_permission
except ImportError:
    def require_permission(action):
        return get_current_user

router = APIRouter(prefix="/baselines", tags=["Baselines"])


class BaselineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    project_id: int


# ── Create  ← AUDITED ──

@router.post("/", status_code=201)
def create_baseline(
    data: BaselineCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("baselines.create")),
):
    project = db.query(Project).filter(Project.id == data.project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    if db.query(Baseline).filter(Baseline.project_id == data.project_id,
                                 Baseline.name == data.name).first():
        raise HTTPException(400, f"Baseline '{data.name}' already exists for this project")

    reqs = db.query(Requirement).filter(
        Requirement.project_id == data.project_id, Requirement.status != "deleted"
    ).all()
    if not reqs:
        raise HTTPException(400, "No requirements to baseline")

    baseline = Baseline(name=data.name, description=data.description,
                        project_id=data.project_id,
                        requirements_count=len(reqs),
                        created_by_id=current_user.id)
    db.add(baseline)
    db.flush()

    for req in reqs:
        snap = BaselineRequirement(
            baseline_id=baseline.id, requirement_id=req.id,
            req_id_snapshot=req.req_id, title_snapshot=req.title,
            statement_snapshot=req.statement, rationale_snapshot=req.rationale,
            status_snapshot=req.status.value if hasattr(req.status, "value") else str(req.status),
            level_snapshot=req.level.value if hasattr(req.level, "value") else str(req.level) if req.level else "L1",
            type_snapshot=req.req_type.value if hasattr(req.req_type, "value") else str(req.req_type),
            priority_snapshot=req.priority.value if hasattr(req.priority, "value") else str(req.priority),
            quality_score_snapshot=req.quality_score or 0.0,
            version_snapshot=req.version or 1,
            parent_id_snapshot=req.parent_id,
        )
        db.add(snap)

    db.commit()
    db.refresh(baseline)
    creator = db.query(User).filter(User.id == baseline.created_by_id).first()

    record_event(db, "baseline.created", "baseline", baseline.id, current_user.id,
                 {"name": data.name, "requirements_count": len(reqs)},
                 project_id=data.project_id, request=request)

    return {
        "id": baseline.id, "name": baseline.name,
        "description": baseline.description, "project_id": baseline.project_id,
        "requirements_count": baseline.requirements_count,
        "created_by": creator.full_name if creator else "Unknown",
        "created_at": baseline.created_at.isoformat() if baseline.created_at else None,
    }


# ── List (read-only) ──

@router.get("/")
def list_baselines(project_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    baselines = db.query(Baseline).filter(
        Baseline.project_id == project_id
    ).order_by(Baseline.created_at.desc()).all()
    results = []
    for b in baselines:
        creator = db.query(User).filter(User.id == b.created_by_id).first() if b.created_by_id else None
        results.append({
            "id": b.id, "name": b.name, "description": b.description,
            "project_id": b.project_id,
            "requirements_count": b.requirements_count or len(b.requirements),
            "created_by": creator.full_name if creator else "Unknown",
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })
    return {"project_id": project_id, "total": len(results), "baselines": results}


# ── Get detail (read-only) ──

@router.get("/{baseline_id}")
def get_baseline(baseline_id: int, db: Session = Depends(get_db),
                 current_user: User = Depends(get_current_user)):
    baseline = db.query(Baseline).filter(Baseline.id == baseline_id).first()
    if not baseline:
        raise HTTPException(404, "Baseline not found")
    creator = db.query(User).filter(User.id == baseline.created_by_id).first() if baseline.created_by_id else None
    snapshots = db.query(BaselineRequirement).filter(
        BaselineRequirement.baseline_id == baseline_id
    ).order_by(BaselineRequirement.req_id_snapshot).all()
    return {
        "id": baseline.id, "name": baseline.name, "description": baseline.description,
        "project_id": baseline.project_id, "requirements_count": len(snapshots),
        "created_by": creator.full_name if creator else "Unknown",
        "created_at": baseline.created_at.isoformat() if baseline.created_at else None,
        "requirements": [{
            "id": s.id, "requirement_id": s.requirement_id,
            "req_id": s.req_id_snapshot, "title": s.title_snapshot,
            "statement": s.statement_snapshot, "rationale": s.rationale_snapshot,
            "status": s.status_snapshot, "level": s.level_snapshot,
            "type": s.type_snapshot, "priority": s.priority_snapshot,
            "quality_score": s.quality_score_snapshot,
            "version": s.version_snapshot, "parent_id": s.parent_id_snapshot,
        } for s in snapshots],
    }


# ── Compare (read-only) ──

@router.get("/compare/{baseline_a_id}/{baseline_b_id}")
def compare_baselines(baseline_a_id: int, baseline_b_id: int,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(get_current_user)):
    a = db.query(Baseline).filter(Baseline.id == baseline_a_id).first()
    b = db.query(Baseline).filter(Baseline.id == baseline_b_id).first()
    if not a or not b:
        raise HTTPException(404, "One or both baselines not found")
    snaps_a = db.query(BaselineRequirement).filter(BaselineRequirement.baseline_id == baseline_a_id).all()
    snaps_b = db.query(BaselineRequirement).filter(BaselineRequirement.baseline_id == baseline_b_id).all()
    map_a = {s.requirement_id: s for s in snaps_a}
    map_b = {s.requirement_id: s for s in snaps_b}
    ids_a, ids_b = set(map_a), set(map_b)
    added = [{"req_id": map_b[i].req_id_snapshot, "title": map_b[i].title_snapshot,
              "status": map_b[i].status_snapshot, "level": map_b[i].level_snapshot}
             for i in ids_b - ids_a]
    removed = [{"req_id": map_a[i].req_id_snapshot, "title": map_a[i].title_snapshot,
                "status": map_a[i].status_snapshot, "level": map_a[i].level_snapshot}
               for i in ids_a - ids_b]
    CMP = [("title","title_snapshot"),("statement","statement_snapshot"),
           ("rationale","rationale_snapshot"),("status","status_snapshot"),
           ("level","level_snapshot"),("type","type_snapshot"),
           ("priority","priority_snapshot"),("quality_score","quality_score_snapshot"),
           ("version","version_snapshot")]
    modified = []
    for rid in ids_a & ids_b:
        sa, sb = map_a[rid], map_b[rid]
        changes = [{"field": fl, "baseline_a": str(getattr(sa, fa)),
                     "baseline_b": str(getattr(sb, fa))}
                   for fl, fa in CMP if str(getattr(sa, fa)) != str(getattr(sb, fa))]
        if changes:
            modified.append({"req_id": sb.req_id_snapshot, "title": sb.title_snapshot,
                             "changes": changes})
    return {
        "baseline_a": {"id": a.id, "name": a.name, "created_at": a.created_at.isoformat() if a.created_at else None},
        "baseline_b": {"id": b.id, "name": b.name, "created_at": b.created_at.isoformat() if b.created_at else None},
        "summary": {"added": len(added), "removed": len(removed),
                    "modified": len(modified), "unchanged": len(ids_a & ids_b) - len(modified)},
        "added": added, "removed": removed, "modified": modified,
    }


# ── Delete  ← AUDITED ──

@router.delete("/{baseline_id}", status_code=204)
def delete_baseline(baseline_id: int, request: Request,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(require_permission("baselines.delete"))):
    baseline = db.query(Baseline).filter(Baseline.id == baseline_id).first()
    if not baseline:
        raise HTTPException(404, "Baseline not found")

    detail = {"name": baseline.name, "project_id": baseline.project_id}
    pid = baseline.project_id
    db.delete(baseline)
    db.commit()

    record_event(db, "baseline.deleted", "baseline", baseline_id, current_user.id,
                 detail, project_id=pid, request=request)
