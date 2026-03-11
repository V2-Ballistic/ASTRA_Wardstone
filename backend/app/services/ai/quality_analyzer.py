"""
ASTRA — Multi-Tier Quality Analyzer
======================================
File: backend/app/services/ai/quality_analyzer.py   ← NEW

Three analysis tiers:
  Tier 1 (instant):  Existing regex checks — runs on every create/update
  Tier 2 (fast AI):  LLM analysis of a single requirement (~2-5 sec)
  Tier 3 (batch AI): LLM analysis of an entire requirement set (~10-30 sec)

All tiers degrade gracefully: if AI is unavailable, Tier 2 returns
a regex-based fallback result, and Tier 3 returns an empty result.
"""

import json
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.services.ai.llm_client import LLMClient, is_ai_available, usage_tracker
from app.services.ai.prompts import (
    SYSTEM_PROMPT, DEEP_QUALITY_PROMPT, SET_ANALYSIS_PROMPT,
    REWRITE_PROMPT, PROMPT_VERSION,
)
from app.services.quality_checker import check_requirement_quality
from app.schemas.ai import (
    DeepQualityResult, QualityIssue,
    SetAnalysisResult, Contradiction, Redundancy, Gap,
)

logger = logging.getLogger("astra.ai.quality")


# ══════════════════════════════════════
#  Tier 2: Deep Single-Requirement Analysis
# ══════════════════════════════════════

def analyze_quality_deep(
    statement: str,
    title: str = "",
    rationale: str = "",
    domain_context: str = "",
) -> DeepQualityResult:
    """
    Run Tier 2 AI quality analysis on a single requirement.
    Falls back to regex-based scoring if AI is unavailable.
    """
    # Always run Tier 1 first for the baseline score
    tier1 = check_requirement_quality(statement, title, rationale)

    if not is_ai_available():
        return _regex_fallback(tier1)

    client = LLMClient()
    prompt = DEEP_QUALITY_PROMPT.format(
        title=title or "(no title)",
        statement=statement,
        rationale=rationale or "(no rationale provided)",
        domain_context=domain_context or "General systems engineering",
    )

    raw = client.complete(SYSTEM_PROMPT, prompt, temperature=0.1)

    if raw is None:
        logger.info("AI analysis unavailable — using regex fallback")
        return _regex_fallback(tier1)

    # Parse into typed result
    try:
        issues = []
        for iss in raw.get("issues", []):
            try:
                issues.append(QualityIssue(
                    severity=iss.get("severity", "info"),
                    category=iss.get("category", "completeness"),
                    description=iss.get("description", ""),
                    location=iss.get("location", ""),
                    suggestion=iss.get("suggestion", ""),
                ))
            except Exception:
                continue

        result = DeepQualityResult(
            overall_score=_clamp(raw.get("overall_score", tier1["score"]), 0, 100),
            dimensions=raw.get("dimensions", {}),
            issues=issues,
            suggested_rewrites=raw.get("suggested_rewrites", [])[:3],
            verification_approach=raw.get("verification_approach", ""),
            confidence=_clamp(raw.get("confidence", 0.5), 0, 1),
            analysis_source="ai",
            model_used=client.model,
            prompt_version=PROMPT_VERSION,
        )

        # Blend: average AI score with regex score (regex is fast ground truth)
        blended = round((result.overall_score * 0.7 + tier1["score"] * 0.3), 1)
        result.overall_score = blended

        # Merge regex warnings into issues if not already covered
        for w in tier1.get("warnings", []):
            if not any(w.lower()[:30] in i.description.lower() for i in result.issues):
                result.issues.append(QualityIssue(
                    severity="warning",
                    category="completeness",
                    description=w,
                    location="",
                    suggestion="",
                ))

        return result

    except Exception as exc:
        logger.error("Failed to parse AI quality result: %s", exc)
        return _regex_fallback(tier1)


def _regex_fallback(tier1: dict) -> DeepQualityResult:
    """Build a DeepQualityResult from regex-only Tier 1 results."""
    score = tier1.get("score", 0)
    issues = []
    for w in tier1.get("warnings", []):
        issues.append(QualityIssue(
            severity="warning", category="completeness",
            description=w, location="", suggestion="",
        ))
    for s in tier1.get("suggestions", []):
        issues.append(QualityIssue(
            severity="info", category="completeness",
            description=s, location="", suggestion="",
        ))

    # Approximate dimension scores from the overall regex score
    return DeepQualityResult(
        overall_score=score,
        dimensions={
            "ambiguity": min(100, score + 10),
            "testability": score,
            "completeness": score,
            "atomicity": min(100, score + 5),
            "consistency": min(100, score + 15),
            "feasibility": min(100, score + 15),
        },
        issues=issues,
        suggested_rewrites=[],
        verification_approach="",
        confidence=0.3,     # low confidence — regex only
        analysis_source="regex_fallback",
        model_used="",
        prompt_version=PROMPT_VERSION,
    )


# ══════════════════════════════════════
#  Tier 3: Batch Set Analysis
# ══════════════════════════════════════

def analyze_requirement_set(
    requirements: list[dict],
) -> SetAnalysisResult:
    """
    Analyze a set of requirements for contradictions, redundancies,
    gaps, and overall completeness.
    """
    if not requirements:
        return SetAnalysisResult(total_requirements_analyzed=0)

    if not is_ai_available():
        return SetAnalysisResult(
            total_requirements_analyzed=len(requirements),
            analysis_source="unavailable",
            completeness_notes="AI provider not configured — batch analysis requires an AI provider.",
        )

    # Format requirements for the prompt (limit to first 60 to stay within context)
    limit = min(len(requirements), 60)
    lines = []
    for r in requirements[:limit]:
        lines.append(
            f"- [{r.get('req_id', '?')}] ({r.get('type', '?')}, {r.get('priority', '?')}) "
            f"{r.get('title', '?')}: {r.get('statement', '?')[:200]}"
        )
    reqs_text = "\n".join(lines)

    if len(requirements) > limit:
        reqs_text += f"\n\n(... and {len(requirements) - limit} more requirements not shown)"

    client = LLMClient()
    prompt = SET_ANALYSIS_PROMPT.format(requirements_text=reqs_text)
    raw = client.complete(SYSTEM_PROMPT, prompt, temperature=0.2, max_tokens=3000)

    if raw is None:
        return SetAnalysisResult(
            total_requirements_analyzed=len(requirements),
            analysis_source="failed",
            completeness_notes="AI analysis failed — check AI provider configuration.",
        )

    try:
        contradictions = [
            Contradiction(**c) for c in raw.get("contradictions", [])
        ]
        redundancies = [
            Redundancy(**r) for r in raw.get("redundancies", [])
        ]
        gaps = [
            Gap(**g) for g in raw.get("gaps", [])
        ]

        return SetAnalysisResult(
            contradictions=contradictions,
            redundancies=redundancies,
            gaps=gaps,
            completeness_score=_clamp(raw.get("completeness_score", 50), 0, 100),
            completeness_notes=raw.get("completeness_notes", ""),
            confidence=_clamp(raw.get("confidence", 0.5), 0, 1),
            total_requirements_analyzed=len(requirements),
            analysis_source="ai",
            model_used=client.model,
        )

    except Exception as exc:
        logger.error("Failed to parse batch analysis result: %s", exc)
        return SetAnalysisResult(
            total_requirements_analyzed=len(requirements),
            analysis_source="parse_error",
            completeness_notes=f"AI returned data but parsing failed: {exc}",
        )


# ══════════════════════════════════════
#  Rewrite suggestion
# ══════════════════════════════════════

def suggest_rewrite(
    statement: str, title: str = "", rationale: str = "",
    issues: list[str] | None = None,
) -> dict | None:
    """Ask the LLM for a rewritten requirement.  Returns None on failure."""
    if not is_ai_available():
        return None

    client = LLMClient()
    prompt = REWRITE_PROMPT.format(
        title=title or "(no title)",
        statement=statement,
        rationale=rationale or "(none)",
        issues="; ".join(issues or ["general quality improvement"]),
    )
    return client.complete(SYSTEM_PROMPT, prompt, temperature=0.3)


def _clamp(val, lo, hi):
    try:
        return max(lo, min(hi, float(val)))
    except (TypeError, ValueError):
        return lo
