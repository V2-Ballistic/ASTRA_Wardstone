"""
ASTRA — AI Embedding Features Router
========================================
File: backend/app/routers/ai.py   ← NEW

Endpoints:
  GET  /ai/duplicates          — find all duplicate groups in project
  POST /ai/check-duplicate     — check if new statement has duplicates
  GET  /ai/trace-suggestions   — get suggested trace links for a requirement
  GET  /ai/verification-suggestion — get suggested verification method
  POST /ai/feedback            — submit feedback on AI suggestion
  GET  /ai/stats               — AI usage statistics
  POST /ai/reindex             — re-generate all embeddings for project

All endpoints gracefully degrade when no embedding provider is configured.
"""

import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import get_db
from app.models import User, Requirement, Project
from app.services.auth import get_current_user

# Embedding services
from app.services.ai.embeddings import (
    is_embedding_available,
    get_embedding_info,
    get_project_embeddings,
    hash_statement,
)
from app.services.ai.duplicate_detector import find_duplicates, check_new_requirement
from app.services.ai.trace_suggester import suggest_trace_links, suggest_verification_method

# Schemas
from app.schemas.ai_embeddings import (
    DuplicateCheckRequest,
    DuplicateCheckResponse,
    ProjectDuplicatesResponse,
    TraceSuggestionsResponse,
    VerificationSuggestion,
    AISuggestionFeedback,
    ReindexRequest,
    ReindexResponse,
    AIEmbeddingStats,
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

logger = logging.getLogger("astra.ai.router")

router = APIRouter(prefix="/ai", tags=["AI — Semantic Analysis"])


# ══════════════════════════════════════
#  Duplicate Detection
# ══════════════════════════════════════

@router.get("/duplicates", response_model=ProjectDuplicatesResponse)
def get_project_duplicates(
    project_id: int = Query(..., description="Project ID to scan for duplicates"),
    threshold: float = Query(0.85, ge=0.5, le=1.0, description="Similarity threshold"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Find all groups of near-duplicate requirements in a project."""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    result = find_duplicates(db, project_id, threshold)
    return result


@router.post("/check-duplicate", response_model=DuplicateCheckResponse)
def check_duplicate(
    data: DuplicateCheckRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Check if a new requirement statement is similar to existing ones.
    Use this before creating a requirement to warn about potential duplicates.
    """
    project = db.query(Project).filter(Project.id == data.project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    return check_new_requirement(
        db=db,
        statement=data.statement,
        project_id=data.project_id,
        title=data.title,
    )


# ══════════════════════════════════════
#  Trace Link Suggestions
# ══════════════════════════════════════

@router.get("/trace-suggestions", response_model=TraceSuggestionsResponse)
def get_trace_suggestions(
    requirement_id: int = Query(..., description="Requirement to get suggestions for"),
    project_id: Optional[int] = Query(None, description="Project ID (auto-detected if omitted)"),
    threshold: float = Query(0.60, ge=0.3, le=1.0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get suggested trace links for a requirement based on semantic similarity."""
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")

    pid = project_id or req.project_id

    return suggest_trace_links(
        db=db,
        requirement_id=requirement_id,
        project_id=pid,
        threshold=threshold,
    )


# ══════════════════════════════════════
#  Verification Suggestion
# ══════════════════════════════════════

@router.get("/verification-suggestion", response_model=VerificationSuggestion)
def get_verification_suggestion(
    requirement_id: int = Query(..., description="Requirement to analyze"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Suggest a verification method (test/analysis/inspection/demonstration) for a requirement."""
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        raise HTTPException(404, "Requirement not found")

    return suggest_verification_method(db, requirement_id)


# ══════════════════════════════════════
#  Suggestion Feedback
# ══════════════════════════════════════

@router.post("/feedback", status_code=200)
def submit_feedback(
    data: AISuggestionFeedback,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Submit feedback on an AI suggestion (accepted/rejected/dismissed)."""
    from app.models.embedding import AISuggestion

    suggestion = db.query(AISuggestion).filter(AISuggestion.id == data.suggestion_id).first()
    if not suggestion:
        raise HTTPException(404, "Suggestion not found")

    suggestion.status = data.action
    suggestion.resolved_by_id = current_user.id
    suggestion.resolved_at = datetime.utcnow()

    db.commit()

    # Also record in the general AI feedback table if available
    try:
        from app.services.ai.feedback import record_feedback
        record_feedback(
            db, current_user.id,
            suggestion.requirement_id,
            suggestion.suggestion_type,
            suggestion.explanation[:500],
            data.action == "accepted",
        )
    except Exception:
        pass

    return {
        "suggestion_id": data.suggestion_id,
        "status": data.action,
        "resolved_by": current_user.username,
    }


# ══════════════════════════════════════
#  Reindex Embeddings
# ══════════════════════════════════════

@router.post("/reindex", response_model=ReindexResponse)
def reindex_embeddings(
    data: ReindexRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("ai.reindex")),
):
    """
    Re-generate all embeddings for a project.
    Runs synchronously for small projects, background for large ones.
    """
    project = db.query(Project).filter(Project.id == data.project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")

    if not is_embedding_available():
        return ReindexResponse(
            project_id=data.project_id,
            ai_available=False,
        )

    # Count requirements
    count = (
        db.query(func.count(Requirement.id))
        .filter(Requirement.project_id == data.project_id, Requirement.status != "deleted")
        .scalar()
    )

    # For small projects (< 200), run synchronously
    if count <= 200:
        result = _run_reindex(db, data.project_id, data.force)
        _audit(db, "ai.reindex", "project", data.project_id, current_user.id,
               {"embedded": result["embedded"], "force": data.force},
               project_id=data.project_id)
        info = get_embedding_info()
        return ReindexResponse(
            project_id=data.project_id,
            total_requirements=result["total"],
            embedded=result["embedded"],
            skipped=result["skipped"],
            errors=result["errors"],
            model_version=info["model"],
        )
    else:
        # For large projects, run in background
        background_tasks.add_task(_run_reindex_background, data.project_id, data.force)
        info = get_embedding_info()
        return ReindexResponse(
            project_id=data.project_id,
            total_requirements=count,
            embedded=0,
            skipped=0,
            errors=0,
            model_version=info["model"] + " (background task started)",
        )


def _run_reindex(db: Session, project_id: int, force: bool) -> dict:
    """Synchronous reindex — returns summary stats."""
    from app.models.embedding import RequirementEmbedding
    from app.services.ai.embeddings import (
        get_or_create_embedding, hash_statement, get_embedding_info,
    )

    reqs = (
        db.query(Requirement)
        .filter(Requirement.project_id == project_id, Requirement.status != "deleted")
        .all()
    )

    embedded = 0
    skipped = 0
    errors = 0

    for req in reqs:
        try:
            result = get_or_create_embedding(db, req.id, req.statement, force=force)
            if result is not None:
                embedded += 1
            else:
                errors += 1
        except Exception as exc:
            logger.error("Reindex error for req %d: %s", req.id, exc)
            errors += 1

    return {"total": len(reqs), "embedded": embedded, "skipped": skipped, "errors": errors}


def _run_reindex_background(project_id: int, force: bool) -> None:
    """Background task wrapper — creates its own DB session."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        _run_reindex(db, project_id, force)
    finally:
        db.close()


# ══════════════════════════════════════
#  AI Statistics
# ══════════════════════════════════════

@router.get("/stats", response_model=AIEmbeddingStats)
def get_ai_stats(
    project_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return AI embedding and suggestion statistics."""
    from app.models.embedding import RequirementEmbedding, AISuggestion

    info = get_embedding_info()

    # Embedding counts
    embed_query = db.query(func.count(RequirementEmbedding.id))
    if project_id:
        embed_query = embed_query.join(
            Requirement, RequirementEmbedding.requirement_id == Requirement.id
        ).filter(Requirement.project_id == project_id)
    total_embeddings = embed_query.scalar() or 0

    # Suggestion counts
    sugg_base = db.query(AISuggestion)
    if project_id:
        sugg_base = sugg_base.filter(AISuggestion.project_id == project_id)

    total_suggestions = sugg_base.count()
    pending = sugg_base.filter(AISuggestion.status == "pending").count()
    accepted = sugg_base.filter(AISuggestion.status == "accepted").count()
    rejected = sugg_base.filter(AISuggestion.status == "rejected").count()

    acceptance_rate = round(accepted / max(accepted + rejected, 1) * 100, 1)

    # By type
    by_type = {}
    for stype in ["duplicate", "trace_link", "verification"]:
        by_type[stype] = sugg_base.filter(AISuggestion.suggestion_type == stype).count()

    # Get existing feedback stats if available
    feedback_stats = {}
    try:
        from app.services.ai.feedback import get_feedback_stats
        feedback_stats = get_feedback_stats(db, project_id)
    except Exception:
        pass

    return AIEmbeddingStats(
        ai_available=info["available"],
        embedding_provider=info["provider"],
        model_version=info["model"],
        total_embeddings=total_embeddings,
        total_suggestions=total_suggestions,
        pending_suggestions=pending,
        accepted_suggestions=accepted,
        rejected_suggestions=rejected,
        acceptance_rate=acceptance_rate,
        suggestions_by_type=by_type,
        feedback_stats=feedback_stats,
    )
