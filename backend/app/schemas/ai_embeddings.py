"""
ASTRA — AI Embedding Schemas
===============================
File: backend/app/schemas/ai_embeddings.py   ← NEW

Pydantic models for:
  - Duplicate detection results
  - Trace link suggestions
  - Verification method suggestions
  - AI suggestion feedback
  - AI analytics / stats
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ══════════════════════════════════════
#  Duplicate Detection
# ══════════════════════════════════════

class SimilarRequirement(BaseModel):
    """A single similar requirement found during duplicate check."""
    requirement_id: int
    req_id: str = ""
    title: str = ""
    statement: str = ""
    similarity_score: float = Field(..., ge=0.0, le=1.0)
    explanation: str = ""


class DuplicateGroup(BaseModel):
    """A group of requirements that are near-duplicates of each other."""
    group_id: int = 0
    requirements: List[SimilarRequirement] = []
    max_similarity: float = 0.0
    avg_similarity: float = 0.0


class DuplicateCheckRequest(BaseModel):
    """Request body for checking a new statement against existing requirements."""
    statement: str = Field(..., min_length=5)
    title: str = ""
    project_id: int


class DuplicateCheckResponse(BaseModel):
    """Response for duplicate check on a new statement."""
    is_likely_duplicate: bool = False
    similar_requirements: List[SimilarRequirement] = []
    ai_available: bool = True


class ProjectDuplicatesResponse(BaseModel):
    """All duplicate groups found in a project."""
    project_id: int
    total_requirements: int = 0
    duplicate_groups: List[DuplicateGroup] = []
    threshold: float = 0.85
    ai_available: bool = True


# ══════════════════════════════════════
#  Trace Link Suggestions
# ══════════════════════════════════════

class TraceSuggestion(BaseModel):
    """A suggested trace link between artifacts."""
    suggestion_id: Optional[int] = None
    source_id: int
    source_type: str = "requirement"
    target_id: int
    target_type: str = "requirement"   # requirement, source_artifact, verification
    target_req_id: str = ""
    target_title: str = ""
    suggested_link_type: str = "derives"  # derives, satisfies, verifies, refines
    confidence: float = Field(..., ge=0.0, le=1.0)
    explanation: str = ""
    status: str = "pending"


class TraceSuggestionsResponse(BaseModel):
    """Trace link suggestions for a requirement."""
    requirement_id: int
    req_id: str = ""
    suggestions: List[TraceSuggestion] = []
    ai_available: bool = True


# ══════════════════════════════════════
#  Verification Suggestions
# ══════════════════════════════════════

class VerificationSuggestion(BaseModel):
    """Suggested verification method and criteria for a requirement."""
    requirement_id: int
    req_id: str = ""
    suggested_method: str = ""          # test, analysis, inspection, demonstration
    method_rationale: str = ""
    suggested_criteria: str = ""
    success_conditions: List[str] = []
    confidence: float = 0.0
    ai_available: bool = True


# ══════════════════════════════════════
#  AI Suggestion Feedback
# ══════════════════════════════════════

class AISuggestionFeedback(BaseModel):
    """User feedback on an AI suggestion (accepted/rejected)."""
    suggestion_id: int
    action: str = Field(..., pattern="^(accepted|rejected|dismissed)$")
    comment: str = ""


# ══════════════════════════════════════
#  Reindex Request
# ══════════════════════════════════════

class ReindexRequest(BaseModel):
    """Request to re-generate all embeddings for a project."""
    project_id: int
    force: bool = False  # re-embed even if hash hasn't changed


class ReindexResponse(BaseModel):
    """Result of a reindex operation."""
    project_id: int
    total_requirements: int = 0
    embedded: int = 0
    skipped: int = 0
    errors: int = 0
    model_version: str = ""
    ai_available: bool = True


# ══════════════════════════════════════
#  AI Stats / Analytics
# ══════════════════════════════════════

class AIEmbeddingStats(BaseModel):
    """Statistics about AI embedding and suggestion features."""
    ai_available: bool = False
    embedding_provider: str = ""
    model_version: str = ""
    total_embeddings: int = 0
    total_suggestions: int = 0
    pending_suggestions: int = 0
    accepted_suggestions: int = 0
    rejected_suggestions: int = 0
    acceptance_rate: float = 0.0
    suggestions_by_type: Dict[str, int] = {}
    # Feedback stats from existing AI feedback system
    feedback_stats: Dict[str, Any] = {}
