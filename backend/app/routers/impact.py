"""
ASTRA — Impact Analysis Router
=================================
File: backend/app/routers/impact.py   ← NEW

Endpoints:
  GET  /impact/analyze           — run impact analysis for a requirement change
  GET  /impact/dependencies      — get dependency chain (tree) for visualization
  GET  /impact/what-if           — preview impact before delete/modify
  GET  /impact/history           — past impact reports for a requirement
  GET  /impact/project-risk      — project-wide risk overview

All endpoints gracefully degrade without AI — graph traversal always
works, AI summary is optional.
"""

import logging
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.database import get_db
from app.models import Requirement, User
from app.services.auth import get_current_user
from app.services.ai.impact_analyzer import (
    analyze_impact,
    get_dependency_chain,
    preview_what_if,
)
from app.schemas.impact import (
    ImpactReport,
    DependencyTree,
    WhatIfPreview,
    StoredImpactReport,
)

# Optional RBAC
try:
    from app.services.rbac import require_permission
except ImportError:
    def require_permission(action):
        return get_current_user

# Optional audit
try:
    from app.services.audit_service import record_event as _audit
except ImportError:
    def _audit(*a, **kw):
        pass

logger = logging.getLogger("astra.impact.router")

router = APIRouter(prefix="/impact", tags=["Impact Analysis"])


# ══════════════════════════════════════
#  Run Impact Analysis
# ══════════════════════════════════════

@router.get("/analyze", response_model=ImpactReport)
def run_impact_analysis(
    requirement_id: int = Query(..., description="Requirement being changed"),
    change_description: str = Query("", description="Description of the change"),
    max_depth: int = Query(10, ge=1, le=20, description="Max traversal depth"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Analyze the impact of changing a requirement.

    Traverses all trace links (direct and transitive) to identify
    affected requirements, verifications, and baselines.  Optionally
    generates an AI-powered natural language summary.
    """
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")

    report = analyze_impact(
        requirement_id=requirement_id,
        change_description=change_description,
        db=db,
        max_depth=max_depth,
    )

    _audit(
        db, "impact.analyzed", "requirement", requirement_id,
        current_user.id,
        {
            "risk_level": report.risk_level,
            "total_affected": report.total_affected,
            "change_description": change_description[:200],
        },
        project_id=req.project_id,
    )

    return report


# ══════════════════════════════════════
#  Dependency Chain
# ══════════════════════════════════════

@router.get("/dependencies", response_model=DependencyTree)
def get_dependencies(
    requirement_id: int = Query(..., description="Requirement to inspect"),
    direction: str = Query("both", pattern="^(both|upstream|downstream)$"),
    max_depth: int = Query(10, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get the dependency chain for a requirement.

    - upstream:   what does this requirement trace to? (parent reqs, source artifacts)
    - downstream: what traces to this requirement? (child reqs, verifications)
    - both:       full picture in both directions
    """
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")

    return get_dependency_chain(
        requirement_id=requirement_id,
        db=db,
        direction=direction,
        max_depth=max_depth,
    )


# ══════════════════════════════════════
#  What-If Preview
# ══════════════════════════════════════

@router.get("/what-if", response_model=WhatIfPreview)
def what_if_preview(
    requirement_id: int = Query(..., description="Requirement to test"),
    action: str = Query("modify", pattern="^(delete|modify)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Preview impact BEFORE making a change.

    For 'delete': shows orphaned children, broken trace links,
    and verifications that would become meaningless.

    For 'modify': shows downstream items that need review and
    verifications that may need re-execution.
    """
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")

    return preview_what_if(
        requirement_id=requirement_id,
        action=action,
        db=db,
    )


# ══════════════════════════════════════
#  Impact Report History
# ══════════════════════════════════════

@router.get("/history", response_model=List[StoredImpactReport])
def get_impact_history(
    requirement_id: int = Query(..., description="Requirement ID"),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get past impact reports for a requirement."""
    from app.models.impact import ImpactReport as ImpactReportModel

    reports = (
        db.query(ImpactReportModel)
        .filter(ImpactReportModel.requirement_id == requirement_id)
        .order_by(desc(ImpactReportModel.created_at))
        .limit(limit)
        .all()
    )

    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    req_ident = req.req_id if req else ""

    return [
        StoredImpactReport(
            id=r.id,
            requirement_id=r.requirement_id,
            requirement_identifier=req_ident,
            change_description=r.change_description or "",
            report_json=r.report_json or {},
            risk_level=r.risk_level or "low",
            total_affected=r.total_affected or 0,
            created_by_id=r.created_by_id,
            created_at=r.created_at.isoformat() if r.created_at else None,
        )
        for r in reports
    ]


# ══════════════════════════════════════
#  Project-Wide Risk Overview
# ══════════════════════════════════════

@router.get("/project-risk")
def get_project_risk(
    project_id: int = Query(..., description="Project to analyze"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Quick project-level risk overview: which requirements are
    highest-impact if changed?

    Computes fan-out count for each requirement without running
    full impact analysis (for performance).
    """
    from app.models import TraceLink

    reqs = (
        db.query(Requirement)
        .filter(
            Requirement.project_id == project_id,
            Requirement.status != "deleted",
        )
        .all()
    )
    if not reqs:
        return {"project_id": project_id, "requirements": [], "total": 0}

    req_ids = {r.id for r in reqs}

    # Count outbound links per requirement (fan-out as risk proxy)
    risk_items = []
    for req in reqs:
        outbound = (
            db.query(TraceLink)
            .filter(
                TraceLink.source_type == "requirement",
                TraceLink.source_id == req.id,
            )
            .count()
        )
        inbound = (
            db.query(TraceLink)
            .filter(
                TraceLink.target_type == "requirement",
                TraceLink.target_id == req.id,
            )
            .count()
        )
        child_count = (
            db.query(Requirement)
            .filter(Requirement.parent_id == req.id)
            .count()
        )

        fan_out = outbound + child_count
        level = req.level.value if hasattr(req.level, "value") else str(req.level) if req.level else "L1"
        priority = req.priority.value if hasattr(req.priority, "value") else str(req.priority)

        risk_items.append({
            "id": req.id,
            "req_id": req.req_id,
            "title": req.title,
            "level": level,
            "priority": priority,
            "status": req.status.value if hasattr(req.status, "value") else str(req.status),
            "fan_out": fan_out,
            "fan_in": inbound,
            "child_count": child_count,
        })

    # Sort by fan-out (highest impact first)
    risk_items.sort(key=lambda x: x["fan_out"], reverse=True)

    return {
        "project_id": project_id,
        "total": len(risk_items),
        "requirements": risk_items[:50],
    }
