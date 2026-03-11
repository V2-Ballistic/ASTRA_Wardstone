"""
ASTRA — Trace Link & Verification Suggester
===============================================
File: backend/app/services/ai/trace_suggester.py   ← NEW

Uses embeddings + optional LLM to suggest:
  - Trace links between related requirements
  - Trace links from requirements to source artifacts
  - Verification methods (test / analysis / inspection / demonstration)

Suggestions are persisted in the AISuggestion table for frontend display.
"""

import logging
import re
from typing import List, Optional

from sqlalchemy.orm import Session

from app.services.ai.embeddings import (
    is_embedding_available,
    get_or_create_embedding,
    get_project_embeddings,
    cosine_similarity,
)
from app.schemas.ai_embeddings import (
    TraceSuggestion,
    TraceSuggestionsResponse,
    VerificationSuggestion,
)

logger = logging.getLogger("astra.ai.trace_suggester")


# ══════════════════════════════════════
#  Trace Link Suggestions
# ══════════════════════════════════════

def suggest_trace_links(
    db: Session,
    requirement_id: int,
    project_id: int,
    threshold: float = 0.60,
    max_suggestions: int = 10,
) -> TraceSuggestionsResponse:
    """
    Find semantically related requirements and artifacts that should
    be linked to the given requirement via traceability.

    Uses embedding similarity to identify candidates, then optionally
    enriches with LLM-generated explanations.
    """
    from app.models import Requirement, TraceLink

    if not is_embedding_available():
        return TraceSuggestionsResponse(
            requirement_id=requirement_id,
            ai_available=False,
        )

    # Get the target requirement
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        return TraceSuggestionsResponse(
            requirement_id=requirement_id,
            ai_available=True,
        )

    # Get embedding for this requirement
    req_embedding = get_or_create_embedding(db, requirement_id, req.statement)
    if req_embedding is None:
        return TraceSuggestionsResponse(
            requirement_id=requirement_id,
            ai_available=False,
        )

    # Get all project embeddings
    all_embeddings = get_project_embeddings(db, project_id)

    # Get existing trace links to exclude already-linked items
    existing_links = set()
    links = (
        db.query(TraceLink)
        .filter(
            ((TraceLink.source_type == "requirement") & (TraceLink.source_id == requirement_id))
            | ((TraceLink.target_type == "requirement") & (TraceLink.target_id == requirement_id))
        )
        .all()
    )
    for link in links:
        if link.source_type == "requirement" and link.source_id == requirement_id:
            existing_links.add(("requirement", link.target_id))
        if link.target_type == "requirement" and link.target_id == requirement_id:
            existing_links.add(("requirement", link.source_id))

    # Score all other requirements
    candidates: List[TraceSuggestion] = []
    for other_id, other_req_id, other_statement, other_emb in all_embeddings:
        if other_id == requirement_id:
            continue
        if ("requirement", other_id) in existing_links:
            continue

        sim = cosine_similarity(req_embedding, other_emb)
        if sim < threshold:
            continue

        # Infer link type based on requirement hierarchy and similarity
        link_type = _infer_link_type(req, other_id, other_statement, sim, db)

        candidates.append(TraceSuggestion(
            source_id=requirement_id,
            source_type="requirement",
            target_id=other_id,
            target_type="requirement",
            target_req_id=other_req_id,
            target_title=other_statement[:100],
            suggested_link_type=link_type,
            confidence=round(sim, 4),
            explanation=_trace_explanation(sim, link_type, req.statement, other_statement),
        ))

    # Sort by confidence
    candidates.sort(key=lambda c: c.confidence, reverse=True)
    top = candidates[:max_suggestions]

    # Optionally persist suggestions to DB
    _persist_suggestions(db, requirement_id, project_id, top)

    return TraceSuggestionsResponse(
        requirement_id=requirement_id,
        req_id=req.req_id,
        suggestions=top,
    )


def _infer_link_type(
    source_req,
    target_id: int,
    target_statement: str,
    similarity: float,
    db: Session,
) -> str:
    """
    Infer the most appropriate trace link type based on hierarchy and content.
    """
    from app.models import Requirement

    target = db.query(Requirement).filter(Requirement.id == target_id).first()
    if not target:
        return "related_to"

    # If target is parent/child, suggest derives/refines
    if source_req.parent_id == target_id:
        return "derives"
    if target.parent_id == source_req.id:
        return "refines"

    # Level-based inference
    source_level = getattr(source_req, "level", "L1") or "L1"
    target_level = getattr(target, "level", "L1") or "L1"

    src_num = int(source_level.replace("L", "")) if source_level.startswith("L") else 1
    tgt_num = int(target_level.replace("L", "")) if target_level.startswith("L") else 1

    if tgt_num < src_num:
        return "derives"       # Source derives from higher-level target
    elif tgt_num > src_num:
        return "refines"       # Source is refined by lower-level target
    elif similarity >= 0.85:
        return "satisfies"     # Same level, high similarity → satisfies
    else:
        return "related_to"    # General relation


def _trace_explanation(
    similarity: float,
    link_type: str,
    source_stmt: str,
    target_stmt: str,
) -> str:
    """Generate a human-readable explanation for a trace suggestion."""
    link_labels = {
        "derives": "derives from",
        "refines": "is refined by",
        "satisfies": "satisfies",
        "related_to": "is related to",
    }
    rel = link_labels.get(link_type, "is related to")

    if similarity >= 0.85:
        return (
            f"High semantic similarity ({similarity:.0%}) — "
            f"this requirement likely {rel} the target. "
            f"Both address closely related functionality."
        )
    elif similarity >= 0.70:
        return (
            f"Moderate similarity ({similarity:.0%}) — "
            f"overlapping scope suggests this requirement {rel} the target."
        )
    else:
        return (
            f"Related content ({similarity:.0%}) — "
            f"similar terminology suggests a potential {link_type} relationship."
        )


def _persist_suggestions(
    db: Session,
    requirement_id: int,
    project_id: int,
    suggestions: List[TraceSuggestion],
) -> None:
    """Save trace suggestions to the AISuggestion table."""
    from app.models.embedding import AISuggestion

    # Remove old pending suggestions of this type for this requirement
    db.query(AISuggestion).filter(
        AISuggestion.requirement_id == requirement_id,
        AISuggestion.suggestion_type == "trace_link",
        AISuggestion.status == "pending",
    ).delete()

    for sugg in suggestions:
        db.add(AISuggestion(
            project_id=project_id,
            requirement_id=requirement_id,
            suggestion_type="trace_link",
            target_type=sugg.target_type,
            target_id=sugg.target_id,
            confidence=sugg.confidence,
            explanation=sugg.explanation,
            metadata_json={
                "suggested_link_type": sugg.suggested_link_type,
                "target_req_id": sugg.target_req_id,
                "target_title": sugg.target_title,
            },
        ))

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.error("Failed to persist trace suggestions for req %d", requirement_id)


# ══════════════════════════════════════
#  Verification Method Suggestion
# ══════════════════════════════════════

# Keyword patterns for verification method inference
_VERIFICATION_PATTERNS = {
    "test": [
        r"\bshall\s+(respond|execute|complete|process|return|output|generate)\b",
        r"\bwithin\s+\d+\s*(ms|seconds?|minutes?|hours?)\b",
        r"\bperformance\b", r"\bthroughput\b", r"\blatency\b",
        r"\bshall\s+(accept|reject|validate|handle)\b",
        r"\brate\s+of\b", r"\bcapacity\b", r"\bavailability\b",
    ],
    "analysis": [
        r"\bshall\s+(comply|conform|meet|satisfy|adhere)\b",
        r"\bstandard\b", r"\bspecification\b", r"\bregulation\b",
        r"\bshall\s+be\s+(compatible|interoperable)\b",
        r"\barchitectur", r"\bdesign\s+(shall|must)\b",
        r"\banalysis\b", r"\breliability\b", r"\bsafety\b",
    ],
    "inspection": [
        r"\bshall\s+(provide|include|contain|have|document)\b",
        r"\bshall\s+be\s+(labeled|marked|documented|identified)\b",
        r"\buser\s*(manual|guide|documentation)\b",
        r"\binterface\s*(control|definition)\b",
        r"\bvisual\b", r"\bphysical\b", r"\bappearance\b",
    ],
    "demonstration": [
        r"\bshall\s+(display|show|present|alert|notify)\b",
        r"\buser\s+interface\b", r"\bdashboard\b",
        r"\bshall\s+(allow|enable|permit|support)\b",
        r"\bworkflow\b", r"\boperator\b",
    ],
}


def suggest_verification_method(
    db: Session,
    requirement_id: int,
) -> VerificationSuggestion:
    """
    Analyze requirement text to suggest the most appropriate
    verification method: test, analysis, inspection, or demonstration.

    Uses keyword pattern matching with optional LLM enrichment.
    """
    from app.models import Requirement

    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        return VerificationSuggestion(requirement_id=requirement_id)

    statement = req.statement.lower()
    scores: dict[str, int] = {"test": 0, "analysis": 0, "inspection": 0, "demonstration": 0}

    for method, patterns in _VERIFICATION_PATTERNS.items():
        for pattern in patterns:
            matches = re.findall(pattern, statement, re.IGNORECASE)
            scores[method] += len(matches)

    # Default to 'test' if no clear winner
    best_method = max(scores, key=scores.get) if max(scores.values()) > 0 else "test"
    total_score = sum(scores.values())
    confidence = min(0.95, scores[best_method] / max(total_score, 1) * 0.9 + 0.1)

    # Generate criteria based on the method
    criteria = _generate_criteria(best_method, req.statement)
    success_conditions = _generate_success_conditions(best_method, req.statement)

    # Try LLM enrichment if available
    llm_result = _llm_verification_suggestion(req.statement, req.title)
    if llm_result:
        best_method = llm_result.get("method", best_method)
        criteria = llm_result.get("criteria", criteria)
        success_conditions = llm_result.get("success_conditions", success_conditions)
        confidence = min(0.95, llm_result.get("confidence", confidence))

    return VerificationSuggestion(
        requirement_id=requirement_id,
        req_id=req.req_id,
        suggested_method=best_method,
        method_rationale=_method_rationale(best_method),
        suggested_criteria=criteria,
        success_conditions=success_conditions,
        confidence=round(confidence, 3),
        ai_available=is_embedding_available(),
    )


def _generate_criteria(method: str, statement: str) -> str:
    """Generate basic verification criteria based on the method."""
    templates = {
        "test": (
            "Execute the function described in the requirement under nominal conditions. "
            "Measure the output against the specified thresholds. "
            "Record pass/fail with supporting data."
        ),
        "analysis": (
            "Review the design documentation and traceability matrix. "
            "Verify compliance with referenced standards through analytical methods. "
            "Document the analysis results and any deviations."
        ),
        "inspection": (
            "Visually inspect the deliverable or documentation. "
            "Verify all required elements are present and correctly formatted. "
            "Record inspection results with supporting evidence."
        ),
        "demonstration": (
            "Demonstrate the capability in a controlled environment. "
            "Walk through the operational scenario described in the requirement. "
            "Record demonstration results with screenshots or logs."
        ),
    }
    return templates.get(method, templates["test"])


def _generate_success_conditions(method: str, statement: str) -> List[str]:
    """Generate basic success conditions."""
    conditions = [
        "Requirement statement is fully addressed",
        "All specified thresholds or criteria are met",
        "Results are documented with supporting evidence",
    ]

    if method == "test":
        conditions.append("Test procedure is repeatable")
    elif method == "analysis":
        conditions.append("Analysis methodology is documented and defensible")
    elif method == "inspection":
        conditions.append("Inspection checklist is completed")
    elif method == "demonstration":
        conditions.append("Demonstration is witnessed by authorized reviewer")

    return conditions


def _method_rationale(method: str) -> str:
    """Explain why this verification method was selected."""
    rationales = {
        "test": (
            "Test is recommended because the requirement specifies measurable "
            "performance criteria, quantitative thresholds, or functional behavior "
            "that can be directly exercised and measured."
        ),
        "analysis": (
            "Analysis is recommended because the requirement references standards "
            "compliance, design constraints, or characteristics best verified "
            "through mathematical or logical evaluation of design data."
        ),
        "inspection": (
            "Inspection is recommended because the requirement specifies "
            "documentation, labeling, physical characteristics, or presence of "
            "specific elements that can be verified by visual examination."
        ),
        "demonstration": (
            "Demonstration is recommended because the requirement describes "
            "user-facing capabilities, workflows, or operational scenarios best "
            "verified by showing the system in operation."
        ),
    }
    return rationales.get(method, rationales["test"])


def _llm_verification_suggestion(statement: str, title: str = "") -> Optional[dict]:
    """
    Optionally use LLM for richer verification suggestions.
    Returns None if LLM is unavailable, letting caller use pattern-based results.
    """
    try:
        from app.services.ai.llm_client import is_ai_available, LLMClient

        if not is_ai_available():
            return None

        client = LLMClient()
        prompt = f"""Analyze this systems engineering requirement and suggest a verification method.

Requirement Title: {title or '(untitled)'}
Statement: {statement}

Respond with JSON containing:
- "method": one of "test", "analysis", "inspection", "demonstration"
- "criteria": verification criteria as a string
- "success_conditions": list of success condition strings
- "confidence": float 0.0 to 1.0

Consider INCOSE and NASA SE Handbook guidance for verification method selection."""

        system = (
            "You are a verification & validation engineer. "
            "Respond ONLY with valid JSON, no markdown or other text."
        )
        result = client.complete(system, prompt, temperature=0.1, max_tokens=500)
        return result

    except Exception as exc:
        logger.debug("LLM verification suggestion failed: %s", exc)
        return None
