from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Baseline, BaselineRequirement, Requirement, Project, User
from app.services.auth import get_current_user

router = APIRouter(prefix="/baselines", tags=["Baselines"])


# ── Schemas ──

class BaselineCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None
    project_id: int


# ══════════════════════════════════════
#  Endpoints
# ══════════════════════════════════════

@router.post("/", status_code=201)
def create_baseline(
    data: BaselineCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a named baseline that snapshots all current requirements."""
    project = db.query(Project).filter(Project.id == data.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Check for duplicate name within project
    existing = db.query(Baseline).filter(
        Baseline.project_id == data.project_id,
        Baseline.name == data.name,
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Baseline '{data.name}' already exists for this project")

    # Get all non-deleted requirements for the project
    reqs = db.query(Requirement).filter(
        Requirement.project_id == data.project_id,
        Requirement.status != "deleted",
    ).all()

    if not reqs:
        raise HTTPException(status_code=400, detail="No requirements to baseline (all deleted or none exist)")

    # Create the baseline
    baseline = Baseline(
        name=data.name,
        description=data.description,
        project_id=data.project_id,
        requirements_count=len(reqs),
        created_by_id=current_user.id,
    )
    db.add(baseline)
    db.flush()  # Get the ID

    # Snapshot every requirement
    for req in reqs:
        snapshot = BaselineRequirement(
            baseline_id=baseline.id,
            requirement_id=req.id,
            req_id_snapshot=req.req_id,
            title_snapshot=req.title,
            statement_snapshot=req.statement,
            rationale_snapshot=req.rationale,
            status_snapshot=req.status.value if hasattr(req.status, "value") else str(req.status),
            level_snapshot=req.level.value if hasattr(req.level, "value") else str(req.level) if req.level else "L1",
            type_snapshot=req.req_type.value if hasattr(req.req_type, "value") else str(req.req_type),
            priority_snapshot=req.priority.value if hasattr(req.priority, "value") else str(req.priority),
            quality_score_snapshot=req.quality_score or 0.0,
            version_snapshot=req.version or 1,
            parent_id_snapshot=req.parent_id,
        )
        db.add(snapshot)

    db.commit()
    db.refresh(baseline)

    creator = db.query(User).filter(User.id == baseline.created_by_id).first()

    return {
        "id": baseline.id,
        "name": baseline.name,
        "description": baseline.description,
        "project_id": baseline.project_id,
        "requirements_count": baseline.requirements_count,
        "created_by": creator.full_name if creator else "Unknown",
        "created_at": baseline.created_at.isoformat() if baseline.created_at else None,
    }


@router.get("/")
def list_baselines(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all baselines for a project, newest first."""
    baselines = (
        db.query(Baseline)
        .filter(Baseline.project_id == project_id)
        .order_by(Baseline.created_at.desc())
        .all()
    )

    results = []
    for b in baselines:
        creator = db.query(User).filter(User.id == b.created_by_id).first() if b.created_by_id else None
        results.append({
            "id": b.id,
            "name": b.name,
            "description": b.description,
            "project_id": b.project_id,
            "requirements_count": b.requirements_count or len(b.requirements),
            "created_by": creator.full_name if creator else "Unknown",
            "created_at": b.created_at.isoformat() if b.created_at else None,
        })

    return {"project_id": project_id, "total": len(results), "baselines": results}


@router.get("/{baseline_id}")
def get_baseline(
    baseline_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a baseline with all frozen requirement snapshots."""
    baseline = db.query(Baseline).filter(Baseline.id == baseline_id).first()
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")

    creator = db.query(User).filter(User.id == baseline.created_by_id).first() if baseline.created_by_id else None

    snapshots = (
        db.query(BaselineRequirement)
        .filter(BaselineRequirement.baseline_id == baseline_id)
        .order_by(BaselineRequirement.req_id_snapshot)
        .all()
    )

    return {
        "id": baseline.id,
        "name": baseline.name,
        "description": baseline.description,
        "project_id": baseline.project_id,
        "requirements_count": len(snapshots),
        "created_by": creator.full_name if creator else "Unknown",
        "created_at": baseline.created_at.isoformat() if baseline.created_at else None,
        "requirements": [
            {
                "id": s.id,
                "requirement_id": s.requirement_id,
                "req_id": s.req_id_snapshot,
                "title": s.title_snapshot,
                "statement": s.statement_snapshot,
                "rationale": s.rationale_snapshot,
                "status": s.status_snapshot,
                "level": s.level_snapshot,
                "type": s.type_snapshot,
                "priority": s.priority_snapshot,
                "quality_score": s.quality_score_snapshot,
                "version": s.version_snapshot,
                "parent_id": s.parent_id_snapshot,
            }
            for s in snapshots
        ],
    }


@router.get("/compare/{baseline_a_id}/{baseline_b_id}")
def compare_baselines(
    baseline_a_id: int,
    baseline_b_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Compare two baselines: show added, removed, and modified requirements with field diffs."""
    baseline_a = db.query(Baseline).filter(Baseline.id == baseline_a_id).first()
    baseline_b = db.query(Baseline).filter(Baseline.id == baseline_b_id).first()
    if not baseline_a or not baseline_b:
        raise HTTPException(status_code=404, detail="One or both baselines not found")

    snaps_a = db.query(BaselineRequirement).filter(BaselineRequirement.baseline_id == baseline_a_id).all()
    snaps_b = db.query(BaselineRequirement).filter(BaselineRequirement.baseline_id == baseline_b_id).all()

    # Index by requirement_id for comparison
    map_a = {s.requirement_id: s for s in snaps_a}
    map_b = {s.requirement_id: s for s in snaps_b}

    ids_a = set(map_a.keys())
    ids_b = set(map_b.keys())

    added_ids = ids_b - ids_a
    removed_ids = ids_a - ids_b
    common_ids = ids_a & ids_b

    # Build diff results
    added = []
    for rid in added_ids:
        s = map_b[rid]
        added.append({"req_id": s.req_id_snapshot, "title": s.title_snapshot, "status": s.status_snapshot, "level": s.level_snapshot})

    removed = []
    for rid in removed_ids:
        s = map_a[rid]
        removed.append({"req_id": s.req_id_snapshot, "title": s.title_snapshot, "status": s.status_snapshot, "level": s.level_snapshot})

    modified = []
    COMPARE_FIELDS = [
        ("title", "title_snapshot"),
        ("statement", "statement_snapshot"),
        ("rationale", "rationale_snapshot"),
        ("status", "status_snapshot"),
        ("level", "level_snapshot"),
        ("type", "type_snapshot"),
        ("priority", "priority_snapshot"),
        ("quality_score", "quality_score_snapshot"),
        ("version", "version_snapshot"),
    ]

    for rid in common_ids:
        sa = map_a[rid]
        sb = map_b[rid]
        changes = []
        for field_label, field_attr in COMPARE_FIELDS:
            val_a = getattr(sa, field_attr)
            val_b = getattr(sb, field_attr)
            if str(val_a) != str(val_b):
                changes.append({
                    "field": field_label,
                    "baseline_a": str(val_a) if val_a is not None else None,
                    "baseline_b": str(val_b) if val_b is not None else None,
                })
        if changes:
            modified.append({
                "req_id": sb.req_id_snapshot,
                "title": sb.title_snapshot,
                "changes": changes,
            })

    return {
        "baseline_a": {"id": baseline_a.id, "name": baseline_a.name, "created_at": baseline_a.created_at.isoformat() if baseline_a.created_at else None},
        "baseline_b": {"id": baseline_b.id, "name": baseline_b.name, "created_at": baseline_b.created_at.isoformat() if baseline_b.created_at else None},
        "summary": {
            "added": len(added),
            "removed": len(removed),
            "modified": len(modified),
            "unchanged": len(common_ids) - len(modified),
        },
        "added": added,
        "removed": removed,
        "modified": modified,
    }


@router.delete("/{baseline_id}", status_code=204)
def delete_baseline(
    baseline_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete a baseline and its snapshots."""
    baseline = db.query(Baseline).filter(Baseline.id == baseline_id).first()
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    db.delete(baseline)
    db.commit()
