"""
ASTRA — AI Analysis Schemas
==============================
File: backend/app/schemas/ai.py   ← NEW

Pydantic models for AI quality analysis requests and responses.
These are used both for API serialisation and for validating
LLM output structure.
"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


# ══════════════════════════════════════
#  Quality Issue
# ══════════════════════════════════════

class QualityIssue(BaseModel):
    severity: str = Field(..., pattern="^(critical|warning|info)$")
    category: str = Field(..., pattern="^(ambiguity|testability|completeness|atomicity|consistency|feasibility)$")
    description: str
    location: str = ""
    suggestion: str = ""


# ══════════════════════════════════════
#  Tier 2: Deep Quality Result
# ══════════════════════════════════════

class DeepQualityResult(BaseModel):
    overall_score: float = Field(ge=0, le=100)
    dimensions: dict = Field(default_factory=lambda: {
        "ambiguity": 0, "testability": 0, "completeness": 0,
        "atomicity": 0, "consistency": 0, "feasibility": 0,
    })
    issues: list[QualityIssue] = Field(default_factory=list)
    suggested_rewrites: list[str] = Field(default_factory=list)
    verification_approach: str = ""
    confidence: float = Field(ge=0, le=1, default=0.0)
    # Metadata
    analysis_source: str = "ai"     # "ai" or "regex_fallback"
    model_used: str = ""
    prompt_version: str = ""


# ══════════════════════════════════════
#  Tier 3: Set Analysis Result
# ══════════════════════════════════════

class Contradiction(BaseModel):
    req_ids: list[str]
    description: str
    severity: str = "warning"

class Redundancy(BaseModel):
    req_ids: list[str]
    description: str
    suggestion: str = ""

class Gap(BaseModel):
    category: str
    description: str
    suggestion: str = ""

class SetAnalysisResult(BaseModel):
    contradictions: list[Contradiction] = Field(default_factory=list)
    redundancies: list[Redundancy] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    completeness_score: int = 0
    completeness_notes: str = ""
    confidence: float = 0.0
    total_requirements_analyzed: int = 0
    analysis_source: str = "ai"
    model_used: str = ""


# ══════════════════════════════════════
#  Request Schemas
# ══════════════════════════════════════

class DeepAnalysisRequest(BaseModel):
    statement: str = Field(..., min_length=5)
    title: str = ""
    rationale: str = ""
    domain_context: str = ""

class BatchAnalysisRequest(BaseModel):
    project_id: int
    requirement_ids: list[int] = Field(default_factory=list)
    # If requirement_ids is empty, analyze all non-deleted requirements


# ══════════════════════════════════════
#  Feedback
# ══════════════════════════════════════

class AIFeedbackCreate(BaseModel):
    requirement_id: int
    suggestion_type: str = ""        # "rewrite", "issue", "gap", etc.
    suggestion_text: str = ""
    accepted: bool = False

class AIFeedbackStats(BaseModel):
    total_suggestions: int = 0
    accepted: int = 0
    rejected: int = 0
    acceptance_rate: float = 0.0


# ══════════════════════════════════════
#  Usage Stats
# ══════════════════════════════════════

class AIUsageStats(BaseModel):
    provider: str = ""
    model: str = ""
    total_requests: int = 0
    total_errors: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    tracking_since: str = ""
