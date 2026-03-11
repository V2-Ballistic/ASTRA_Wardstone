"""
ASTRA — Requirements Router (AI-Enhanced)
============================================
File: backend/app/routers/requirements.py   ← REPLACES existing

Additions:
  POST /requirements/quality-check/deep   — Tier 2 AI analysis
  POST /requirements/quality-check/batch  — Tier 3 batch analysis
  GET  /requirements/{id}/ai-analysis     — Stored AI results
  POST /requirements/{id}/ai-feedback     — Accept/reject AI suggestion
  GET  /requirements/ai/stats             — AI usage + feedback stats

All existing endpoints preserved exactly as-is.
"""

from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query, Request, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func
from pydantic import BaseModel, Field

from app.database import get_db
from app.models import (
    Requirement, RequirementHistory, Project, User,
    TraceLink, Verification, Comment,
)
from app.schemas import (
    RequirementCreate, RequirementUpdate, RequirementResponse,
    RequirementDetail, QualityCheckResult,
)
from app.services.auth import get_current_user
from app.services.quality_checker import check_requirement_quality, generate_requirement_id

# AI imports (optional — all functions handle unavailability gracefully)
from app.schemas.ai import (
    DeepQualityResult, SetAnalysisResult,
    DeepAnalysisRequest, BatchAnalysisRequest,
    AIFeedbackCreate,
)
from app.services.ai.quality_analyzer import (
    analyze_quality_deep, analyze_requirement_set, suggest_rewrite,
)
from app.services.ai.llm_client import is_ai_available, usage_tracker
from app.services.ai.feedback import (
    record_feedback, get_feedback_stats,
    cache_analysis, get_cached_analysis,
)

# Optional audit + RBAC
try:
    from app.services.audit_service import record_event as _audit
except ImportError:
    def _audit(*a, **kw):
        pass
try:
    from app.services.rbac import require_permission
except ImportError:
    def require_permission(action):
        return get_current_user

router = APIRouter(prefix="/requirements", tags=["Requirements"])


# ══════════════════════════════════════
#  Status Workflow
# ══════════════════════════════════════

ALLOWED_TRANSITIONS = {
    "draft":        ["under_review", "deleted"],
    "under_review": ["approved", "draft", "deleted"],
    "approved":     ["baselined", "under_review", "deleted"],
    "baselined":    ["approved", "deleted"],
    "implemented":  ["verified", "approved", "deleted"],
    "verified":     ["validated", "approved", "deleted"],
    "validated":    ["approved", "deleted"],
    "deferred":     ["draft", "deleted"],
    "deleted":      ["draft"],
}


def _record_history(db, requirement_id, version, field_changed,
                    old_value, new_value, changed_by_id, description=None):
    old_str = old_value.value if hasattr(old_value, "value") else str(old_value) if old_value is not None else None
    new_str = new_value.value if hasattr(new_value, "value") else str(new_value) if new_value is not None else None
    history = RequirementHistory(
        requirement_id=requirement_id, version=version,
        field_changed=field_changed, old_value=old_str, new_value=new_str,
        change_description=description or f"{field_changed} changed from '{old_str}' to '{new_str}'",
        changed_by_id=changed_by_id, changed_at=datetime.utcnow(),
    )
    db.add(history)


def _ev(v):
    return v.value if hasattr(v, "value") else str(v) if v else ""


# ══════════════════════════════════════
#  Read endpoints
# ══════════════════════════════════════

@router.get("/", response_model=List[RequirementResponse])
def list_requirements(
    project_id: int, status: Optional[str] = None, req_type: Optional[str] = None,
    priority: Optional[str] = None, search: Optional[str] = None,
    skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db), current_user: User = Depends(get_current_user),
):
    query = db.query(Requirement).filter(Requirement.project_id == project_id)
    if status:
        query = query.filter(Requirement.status == status)
    if req_type:
        query = query.filter(Requirement.req_type == req_type)
    if priority:
        query = query.filter(Requirement.priority == priority)
    if search:
        t = f"%{search}%"
        query = query.filter(
            Requirement.req_id.ilike(t) | Requirement.title.ilike(t) | Requirement.statement.ilike(t)
        )
    return query.order_by(Requirement.req_id).offset(skip).limit(limit).all()


@router.get("/{req_id}", response_model=RequirementDetail)
def get_requirement(req_id: int, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")
    trace_count = db.query(TraceLink).filter(
        ((TraceLink.source_type == "requirement") & (TraceLink.source_id == req.id)) |
        ((TraceLink.target_type == "requirement") & (TraceLink.target_id == req.id))
    ).count()
    verification = db.query(Verification).filter(Verification.requirement_id == req.id).first()
    result = RequirementDetail.model_validate(req)
    result.trace_count = trace_count
    result.verification_status = verification.status if verification else None
    result.owner = req.owner
    result.children = req.children or []
    return result


# ══════════════════════════════════════
#  Create  (Tier 1 sync + Tier 2 background)
# ══════════════════════════════════════

def _run_background_ai(db_url: str, req_id: int):
    """Background task: run Tier 2 AI analysis and cache the result."""
    if not is_ai_available():
        return
    try:
        from app.database import SessionLocal
        db = SessionLocal()
        req = db.query(Requirement).filter(Requirement.id == req_id).first()
        if not req:
            db.close()
            return
        result = analyze_quality_deep(
            req.statement or "", req.title or "", req.rationale or "")
        cache_analysis(db, req_id, "deep", result.model_dump(), result.model_used)
        db.close()
    except Exception as exc:
        import logging
        logging.getLogger("astra.ai").error("Background AI failed for req %d: %s", req_id, exc)


@router.post("/", response_model=RequirementResponse, status_code=201)
def create_requirement(
    project_id: int, req_data: RequirementCreate,
    background_tasks: BackgroundTasks,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requirements.create")),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    count = db.query(func.count(Requirement.id)).filter(
        Requirement.project_id == project_id,
        Requirement.req_type == req_data.req_type,
    ).scalar()
    req_id = generate_requirement_id(project.code, req_data.req_type, count + 1)
    quality = check_requirement_quality(req_data.statement, req_data.title, req_data.rationale or "")

    req = Requirement(
        req_id=req_id, title=req_data.title, statement=req_data.statement,
        rationale=req_data.rationale, req_type=req_data.req_type,
        priority=req_data.priority, level=req_data.level,
        project_id=project_id, owner_id=current_user.id,
        created_by_id=current_user.id, parent_id=req_data.parent_id,
        quality_score=quality["score"],
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    _record_history(db, req.id, 1, "created", None, req.req_id, current_user.id,
                    f"Requirement {req.req_id} created")
    db.commit()

    # Audit
    try:
        _audit(db, "requirement.created", "requirement", req.id, current_user.id,
               {"req_id": req.req_id, "quality_score": quality["score"]},
               project_id=project_id, request=request)
    except Exception:
        pass

    # Background: run Tier 2 AI analysis (non-blocking)
    if is_ai_available():
        from app.config import settings
        db_url = settings.DATABASE_URL
        if hasattr(db_url, "get_secret_value"):
            db_url = db_url.get_secret_value()
        background_tasks.add_task(_run_background_ai, str(db_url), req.id)

    return req


# ══════════════════════════════════════
#  Update
# ══════════════════════════════════════

@router.patch("/{req_id}", response_model=RequirementResponse)
def update_requirement(
    req_id: int, req_data: RequirementUpdate,
    background_tasks: BackgroundTasks,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("requirements.update")),
):
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")

    update_data = req_data.model_dump(exclude_unset=True)
    changes: dict = {}

    if "status" in update_data:
        cur = _ev(req.status)
        new = update_data["status"]
        if new != cur:
            allowed = ALLOWED_TRANSITIONS.get(cur, [])
            if new not in allowed:
                raise HTTPException(422,
                    f"Invalid status transition: '{cur}' → '{new}'. Allowed: {allowed}")

    quality_recalc = False
    for field, new_value in update_data.items():
        old_value = getattr(req, field)
        old_cmp = _ev(old_value) if hasattr(old_value, "value") else old_value
        if str(old_cmp) == str(new_value):
            continue
        changes[field] = {"old": str(old_cmp), "new": str(new_value)}
        _record_history(db, req.id, req.version, field, old_cmp, new_value, current_user.id)
        setattr(req, field, new_value)
        if field in ("statement", "title", "rationale"):
            quality_recalc = True

    if quality_recalc:
        quality = check_requirement_quality(str(req.statement), str(req.title), req.rationale or "")
        if req.quality_score != quality["score"]:
            _record_history(db, req.id, req.version, "quality_score",
                            req.quality_score, quality["score"], current_user.id)
            req.quality_score = quality["score"]

    req.version += 1
    db.commit()
    db.refresh(req)

    try:
        if changes:
            _audit(db, "requirement.updated", "requirement", req.id, current_user.id,
                   {"changes": changes}, project_id=req.project_id, request=request)
    except Exception:
        pass

    # Re-run background AI on content changes
    if quality_recalc and is_ai_available():
        from app.config import settings
        db_url = settings.DATABASE_URL
        if hasattr(db_url, "get_secret_value"):
            db_url = db_url.get_secret_value()
        background_tasks.add_task(_run_background_ai, str(db_url), req.id)

    return req


# ══════════════════════════════════════
#  Delete / Restore / Clone
# ══════════════════════════════════════

@router.delete("/{req_id}", status_code=200)
def delete_requirement(req_id: int, request: Request = None,
                       db: Session = Depends(get_db),
                       current_user: User = Depends(require_permission("requirements.delete"))):
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")
    old_status = _ev(req.status)
    if old_status == "deleted":
        raise HTTPException(400, "Requirement is already deleted")
    _record_history(db, req.id, req.version, "status", old_status, "deleted",
                    current_user.id, f"Requirement {req.req_id} soft-deleted")
    req.status = "deleted"
    req.version += 1
    db.commit()
    db.refresh(req)
    try:
        _audit(db, "requirement.deleted", "requirement", req.id, current_user.id,
               {"req_id": req.req_id}, project_id=req.project_id, request=request)
    except Exception:
        pass
    return {"status": "deleted", "req_id": req.req_id, "id": req.id}


@router.post("/{req_id}/restore", response_model=RequirementResponse)
def restore_requirement(req_id: int, request: Request = None,
                        db: Session = Depends(get_db),
                        current_user: User = Depends(require_permission("requirements.update"))):
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")
    if _ev(req.status) != "deleted":
        raise HTTPException(400, "Requirement is not deleted")
    _record_history(db, req.id, req.version, "status", "deleted", "draft",
                    current_user.id, f"Requirement {req.req_id} restored")
    req.status = "draft"
    req.version += 1
    db.commit()
    db.refresh(req)
    return req


@router.post("/{req_id}/clone", response_model=RequirementResponse, status_code=201)
def clone_requirement(req_id: int, request: Request = None,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission("requirements.create"))):
    source = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not source:
        raise HTTPException(404, "Source requirement not found")
    project = db.query(Project).filter(Project.id == source.project_id).first()
    req_type_str = _ev(source.req_type)
    count = db.query(func.count(Requirement.id)).filter(
        Requirement.project_id == source.project_id, Requirement.req_type == source.req_type,
    ).scalar()
    new_req_id = generate_requirement_id(project.code if project else "PROJ", req_type_str, count + 1)
    title = f"[CLONE] {source.title}"
    quality = check_requirement_quality(source.statement or "", title, source.rationale or "")
    level_str = _ev(source.level) if hasattr(source, "level") and source.level else "L1"
    clone = Requirement(
        req_id=new_req_id, title=title, statement=source.statement or "",
        rationale=source.rationale, req_type=req_type_str,
        priority=_ev(source.priority), level=level_str, status="draft",
        project_id=source.project_id, parent_id=source.parent_id,
        owner_id=current_user.id, created_by_id=current_user.id,
        quality_score=quality["score"],
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    _record_history(db, clone.id, 1, "created", None, clone.req_id,
                    current_user.id, f"Cloned from {source.req_id}")
    db.commit()
    return clone


# ══════════════════════════════════════
#  History / Transitions / Comments (unchanged)
# ══════════════════════════════════════

@router.get("/{req_id}/history")
def get_requirement_history(req_id: int, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")
    history = (db.query(RequirementHistory)
               .filter(RequirementHistory.requirement_id == req_id)
               .order_by(RequirementHistory.changed_at.desc()).all())
    return {
        "requirement_id": req_id, "req_id": req.req_id, "total": len(history),
        "history": [{
            "id": h.id, "version": h.version, "field_changed": h.field_changed,
            "old_value": h.old_value, "new_value": h.new_value,
            "change_description": h.change_description,
            "changed_by": h.changed_by.full_name if h.changed_by else "System",
            "changed_by_username": h.changed_by.username if h.changed_by else None,
            "changed_at": h.changed_at.isoformat() if h.changed_at else None,
        } for h in history],
    }


@router.get("/status-transitions/{current_status}")
def get_allowed_transitions(current_status: str,
                            current_user: User = Depends(get_current_user)):
    return {"current_status": current_status,
            "allowed": ALLOWED_TRANSITIONS.get(current_status, [])}


class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    parent_id: Optional[int] = None


@router.get("/{req_id}/comments")
def get_requirement_comments(req_id: int, db: Session = Depends(get_db),
                             current_user: User = Depends(get_current_user)):
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")
    comments = db.query(Comment).filter(Comment.requirement_id == req_id).order_by(Comment.created_at.asc()).all()
    return {
        "requirement_id": req_id, "total": len(comments),
        "comments": [{
            "id": c.id, "content": c.content, "parent_id": c.parent_id,
            "author_id": c.author_id,
            "author_name": c.author.full_name if c.author else "Unknown",
            "author_username": c.author.username if c.author else None,
            "author_role": _ev(c.author.role) if c.author else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        } for c in comments],
    }


@router.post("/{req_id}/comments", status_code=201)
def create_comment(req_id: int, data: CommentCreate, request: Request = None,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")
    if data.parent_id:
        parent = db.query(Comment).filter(Comment.id == data.parent_id,
                                          Comment.requirement_id == req_id).first()
        if not parent:
            raise HTTPException(404, "Parent comment not found")
    comment = Comment(requirement_id=req_id, author_id=current_user.id,
                      content=data.content, parent_id=data.parent_id)
    db.add(comment)
    db.commit()
    db.refresh(comment)
    return {
        "id": comment.id, "content": comment.content,
        "parent_id": comment.parent_id, "author_id": current_user.id,
        "author_name": current_user.full_name,
        "author_username": current_user.username,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }


# ══════════════════════════════════════
#  Tier 1: Quality Check (instant, regex)
# ══════════════════════════════════════

@router.post("/quality-check", response_model=QualityCheckResult)
def quality_check(statement: str, title: str = "", rationale: str = "",
                  current_user: User = Depends(get_current_user)):
    return check_requirement_quality(statement, title, rationale)


# ══════════════════════════════════════
#  Tier 2: Deep AI Quality Check        ← NEW
# ══════════════════════════════════════

@router.post("/quality-check/deep", response_model=DeepQualityResult)
def quality_check_deep(
    data: DeepAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run Tier 2 AI-powered quality analysis on a single requirement.
    Falls back to regex-based scoring if AI is unavailable.
    """
    result = analyze_quality_deep(
        data.statement, data.title, data.rationale, data.domain_context,
    )
    return result


# ══════════════════════════════════════
#  Tier 3: Batch Analysis                ← NEW
# ══════════════════════════════════════

@router.post("/quality-check/batch", response_model=SetAnalysisResult)
def quality_check_batch(
    data: BatchAnalysisRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Run Tier 3 batch analysis: detect contradictions, redundancies,
    and gaps across a set of requirements.
    """
    query = db.query(Requirement).filter(
        Requirement.project_id == data.project_id,
        Requirement.status != "deleted",
    )
    if data.requirement_ids:
        query = query.filter(Requirement.id.in_(data.requirement_ids))

    reqs = query.order_by(Requirement.req_id).all()

    req_dicts = [{
        "req_id": r.req_id,
        "title": r.title,
        "statement": r.statement,
        "type": _ev(r.req_type),
        "priority": _ev(r.priority),
        "status": _ev(r.status),
    } for r in reqs]

    result = analyze_requirement_set(req_dicts)
    return result


# ══════════════════════════════════════
#  Stored AI Analysis Results            ← NEW
# ══════════════════════════════════════

@router.get("/{req_id}/ai-analysis")
def get_ai_analysis(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Retrieve stored AI analysis results for a requirement."""
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")

    cached = get_cached_analysis(db, req_id, "deep")
    return {
        "requirement_id": req_id,
        "req_id": req.req_id,
        "ai_available": is_ai_available(),
        "analysis": cached,
    }


# ══════════════════════════════════════
#  AI Feedback                           ← NEW
# ══════════════════════════════════════

@router.post("/{req_id}/ai-feedback", status_code=201)
def submit_ai_feedback(
    req_id: int,
    data: AIFeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Record user acceptance or rejection of an AI suggestion."""
    fb = record_feedback(
        db, current_user.id, req_id,
        data.suggestion_type, data.suggestion_text, data.accepted,
    )
    return {"id": fb.id, "accepted": fb.accepted}


# ══════════════════════════════════════
#  AI Stats                              ← NEW
# ══════════════════════════════════════

@router.get("/ai/stats")
def get_ai_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return AI usage stats and feedback acceptance rates."""
    return {
        "ai_available": is_ai_available(),
        "usage": usage_tracker.summary(),
        "feedback": get_feedback_stats(db),
    }
