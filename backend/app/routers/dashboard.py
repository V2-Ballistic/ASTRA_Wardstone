from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func, case
from app.database import get_db
from app.models import (
    Requirement, Project, Verification, TraceLink,
    RequirementHistory, User, SourceArtifact,
)
from app.schemas import DashboardStats
from app.services.auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aggregate dashboard statistics for a project."""
    reqs = db.query(Requirement).filter(Requirement.project_id == project_id).all()
    total = len(reqs)
    req_ids = [r.id for r in reqs]

    # ── By Status ──
    by_status = {}
    for r in reqs:
        s = r.status.value if hasattr(r.status, "value") else str(r.status)
        by_status[s] = by_status.get(s, 0) + 1

    # ── By Type ──
    by_type = {}
    for r in reqs:
        t = r.req_type.value if hasattr(r.req_type, "value") else str(r.req_type)
        by_type[t] = by_type.get(t, 0) + 1

    # ── Verified Count ──
    verified_count = 0
    if req_ids:
        verified_count = (
            db.query(func.count(Verification.id))
            .filter(
                Verification.requirement_id.in_(req_ids),
                Verification.status == "pass",
            )
            .scalar()
            or 0
        )

    # ── Average Quality Score ──
    avg_quality = 0.0
    if total > 0:
        avg_quality = round(sum(r.quality_score or 0 for r in reqs) / total, 1)

    # ── Trace Links ──
    total_trace_links = 0
    orphan_ids = set(req_ids)
    if req_ids:
        links = (
            db.query(TraceLink)
            .filter(
                ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids)))
                | ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids)))
            )
            .all()
        )
        total_trace_links = len(links)
        for link in links:
            if link.source_type == "requirement":
                orphan_ids.discard(link.source_id)
            if link.target_type == "requirement":
                orphan_ids.discard(link.target_id)

    orphan_count = len(orphan_ids)

    # ── Recent Activity (last 20 changes) ──
    recent_activity = []
    if req_ids:
        history_rows = (
            db.query(RequirementHistory)
            .filter(RequirementHistory.requirement_id.in_(req_ids))
            .order_by(RequirementHistory.changed_at.desc())
            .limit(20)
            .all()
        )
        for h in history_rows:
            req = next((r for r in reqs if r.id == h.requirement_id), None)
            user = db.query(User).filter(User.id == h.changed_by_id).first() if h.changed_by_id else None
            recent_activity.append({
                "req_id": req.req_id if req else "?",
                "field": h.field_changed,
                "old_value": h.old_value,
                "new_value": h.new_value,
                "description": h.change_description or f"{h.field_changed} updated",
                "user": user.full_name if user else "System",
                "timestamp": h.changed_at.isoformat() if h.changed_at else None,
            })

    # If no history yet, show creation-based activity
    if not recent_activity:
        for r in sorted(reqs, key=lambda x: x.created_at or x.id, reverse=True)[:10]:
            owner = db.query(User).filter(User.id == r.owner_id).first() if r.owner_id else None
            recent_activity.append({
                "req_id": r.req_id,
                "field": "created",
                "old_value": None,
                "new_value": r.status.value if hasattr(r.status, "value") else str(r.status),
                "description": f"{r.req_id} created",
                "user": owner.full_name if owner else "System",
                "timestamp": r.created_at.isoformat() if r.created_at else None,
            })

    return DashboardStats(
        total_requirements=total,
        by_status=by_status,
        by_type=by_type,
        verified_count=verified_count,
        avg_quality_score=avg_quality,
        total_trace_links=total_trace_links,
        orphan_count=orphan_count,
        recent_activity=recent_activity,
    )
