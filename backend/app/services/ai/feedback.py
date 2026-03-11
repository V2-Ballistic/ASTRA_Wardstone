"""
ASTRA — AI Feedback Tracking
===============================
File: backend/app/services/ai/feedback.py   ← NEW

Tracks whether users accept or reject AI suggestions.  This data
can be used to:
  - Measure AI suggestion quality over time
  - Identify which prompt/category combos need improvement
  - Report acceptance rates on the AI dashboard
"""

from datetime import datetime
from sqlalchemy.orm import Session

from app.models.ai_models import AIFeedback, AIAnalysisCache


def record_feedback(
    db: Session,
    user_id: int,
    requirement_id: int,
    suggestion_type: str,
    suggestion_text: str,
    accepted: bool,
) -> AIFeedback:
    """Store a user's accept/reject decision on an AI suggestion."""
    fb = AIFeedback(
        user_id=user_id,
        requirement_id=requirement_id,
        suggestion_type=suggestion_type,
        suggestion_text=suggestion_text[:2000],
        accepted=accepted,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


def get_feedback_stats(db: Session, project_id: int | None = None) -> dict:
    """Return acceptance-rate statistics."""
    query = db.query(AIFeedback)
    # If project_id is provided, join through requirement
    # For simplicity, compute over all feedback
    total = query.count()
    accepted = query.filter(AIFeedback.accepted == True).count()
    rejected = total - accepted
    rate = round(accepted / total * 100, 1) if total > 0 else 0.0

    # Breakdown by suggestion type
    by_type: dict[str, dict] = {}
    for fb in query.all():
        t = fb.suggestion_type or "other"
        if t not in by_type:
            by_type[t] = {"total": 0, "accepted": 0}
        by_type[t]["total"] += 1
        if fb.accepted:
            by_type[t]["accepted"] += 1

    for t in by_type:
        by_type[t]["rate"] = round(
            by_type[t]["accepted"] / by_type[t]["total"] * 100, 1
        ) if by_type[t]["total"] > 0 else 0.0

    return {
        "total_suggestions": total,
        "accepted": accepted,
        "rejected": rejected,
        "acceptance_rate": rate,
        "by_type": by_type,
    }


# ── Analysis caching ──

def cache_analysis(
    db: Session,
    requirement_id: int,
    analysis_type: str,
    result_json: dict,
    model_used: str = "",
) -> AIAnalysisCache:
    """Store an AI analysis result for later retrieval."""
    # Upsert: replace if already cached for this requirement + type
    existing = db.query(AIAnalysisCache).filter(
        AIAnalysisCache.requirement_id == requirement_id,
        AIAnalysisCache.analysis_type == analysis_type,
    ).first()

    if existing:
        existing.result_json = result_json
        existing.model_used = model_used
        existing.analyzed_at = datetime.utcnow()
        db.commit()
        db.refresh(existing)
        return existing

    entry = AIAnalysisCache(
        requirement_id=requirement_id,
        analysis_type=analysis_type,
        result_json=result_json,
        model_used=model_used,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def get_cached_analysis(
    db: Session, requirement_id: int, analysis_type: str = "deep",
) -> dict | None:
    """Retrieve a cached AI analysis result."""
    entry = db.query(AIAnalysisCache).filter(
        AIAnalysisCache.requirement_id == requirement_id,
        AIAnalysisCache.analysis_type == analysis_type,
    ).first()
    if not entry:
        return None
    return {
        "id": entry.id,
        "requirement_id": entry.requirement_id,
        "analysis_type": entry.analysis_type,
        "result": entry.result_json,
        "model_used": entry.model_used,
        "analyzed_at": entry.analyzed_at.isoformat() if entry.analyzed_at else None,
    }
