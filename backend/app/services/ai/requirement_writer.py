"""
ASTRA — AI Requirement Writing Assistant
============================================
File: backend/app/services/ai/requirement_writer.py   ← NEW
Path: C:\\Users\\Mason\\Documents\\ASTRA\\backend\\app\\services\\ai\\requirement_writer.py

Converts natural language prose into structured requirements and
helps users improve, decompose, and verify existing requirements.

All functions gracefully degrade when AI is unavailable.
"""

import logging
from typing import List, Optional

from app.services.ai.llm_client import LLMClient, is_ai_available
from app.schemas.ai_writer import (
    GeneratedRequirement, ProseConvertResponse,
    RewriteSuggestion, ImproveResponse,
    DecomposeResponse,
    VerificationCriteria, VerificationStep,
    GenerateRationaleResponse,
    SummarizeChangesResponse,
)

logger = logging.getLogger("astra.ai.writer")


# ══════════════════════════════════════
#  System Prompts
# ══════════════════════════════════════

_WRITER_SYSTEM = """You are an expert systems engineering requirements writer with deep knowledge of:
- INCOSE Guide for Writing Requirements
- IEEE 830 / ISO/IEC/IEEE 29148
- NASA SP-2016-6105 Rev2 (Systems Engineering Handbook), especially Appendix C
- DO-178C, MIL-STD-882E, 21 CFR Part 820

You write requirements that are:
- Atomic: one testable requirement per statement
- Unambiguous: no vague terms (adequate, appropriate, etc.)
- Testable: measurable, with clear pass/fail criteria
- Complete: all conditions, constraints, and thresholds specified
- Consistent: no contradictions with other requirements
- Feasible: technically achievable

You MUST respond ONLY with valid JSON matching the requested schema.
No text before or after the JSON. No markdown code fences."""


# ══════════════════════════════════════
#  1. Prose → Requirements
# ══════════════════════════════════════

_PROSE_PROMPT = """Extract individual, well-formed systems engineering requirements from this stakeholder prose.

PROSE INPUT:
\"\"\"
{prose}
\"\"\"

PROJECT CONTEXT: {project_context}
TARGET LEVEL: {target_level}
DOMAIN: {domain_hint}

For each requirement you extract:
1. Write a proper SHALL statement (e.g., "The system shall...")
2. Generate a concise title
3. Suggest a type: functional, performance, interface, safety, security, environmental, reliability, constraint, maintainability, derived
4. Suggest a priority: critical, high, medium, low
5. Suggest a level: L1 (system), L2 (subsystem), L3 (component), L4 (sub-component), L5 (detail)
6. Write a rationale explaining why this requirement exists
7. Note which fragment of the original prose it came from

Rules:
- Extract EVERY distinct requirement, even implied ones
- Each requirement must be atomic — one SHALL per statement
- Avoid compound requirements (no "and" joining two capabilities)
- Include quantitative thresholds where the prose implies them
- If the prose is vague, make reasonable engineering assumptions and note them

Respond with this JSON:
{{
  "requirements": [
    {{
      "title": "...",
      "statement": "The system shall ...",
      "rationale": "...",
      "req_type": "functional",
      "priority": "medium",
      "level": "{target_level}",
      "confidence": 0.85,
      "source_fragment": "the exact words from the prose",
      "notes": "any assumptions or observations"
    }}
  ],
  "source_type": "meeting_notes|email|specification|general",
  "warnings": ["any issues with the input prose"]
}}"""


def convert_prose_to_requirements(
    prose: str,
    project_context: str = "",
    target_level: str = "L1",
    domain_hint: str = "",
) -> ProseConvertResponse:
    """
    Accept free-form stakeholder prose and extract structured requirements.
    Returns an empty list if AI is unavailable.
    """
    if not is_ai_available():
        return ProseConvertResponse(
            ai_available=False,
            warnings=["AI provider not configured. Set AI_PROVIDER to enable prose conversion."],
        )

    client = LLMClient()
    prompt = _PROSE_PROMPT.format(
        prose=prose[:8000],
        project_context=project_context or "General systems engineering project",
        target_level=target_level,
        domain_hint=domain_hint or "general",
    )

    raw = client.complete(_WRITER_SYSTEM, prompt, temperature=0.3, max_tokens=4000)

    if raw is None:
        return ProseConvertResponse(
            ai_available=True,
            warnings=["AI call failed — try again or check provider configuration."],
        )

    try:
        reqs = []
        for item in raw.get("requirements", []):
            reqs.append(GeneratedRequirement(
                title=item.get("title", ""),
                statement=item.get("statement", ""),
                rationale=item.get("rationale", ""),
                req_type=_validate_type(item.get("req_type", "functional")),
                priority=_validate_priority(item.get("priority", "medium")),
                level=_validate_level(item.get("level", target_level)),
                confidence=_clamp(item.get("confidence", 0.5), 0, 1),
                source_fragment=item.get("source_fragment", ""),
                notes=item.get("notes", ""),
            ))

        return ProseConvertResponse(
            requirements=reqs,
            total_extracted=len(reqs),
            source_type=raw.get("source_type", "general"),
            model_used=client.model,
            warnings=raw.get("warnings", []),
        )

    except Exception as exc:
        logger.error("Failed to parse prose conversion result: %s", exc)
        return ProseConvertResponse(
            warnings=[f"AI returned data but parsing failed: {exc}"],
        )


# ══════════════════════════════════════
#  2. Improve Requirement
# ══════════════════════════════════════

_IMPROVE_PROMPT = """Improve this systems engineering requirement. Generate 3 alternative versions
that fix the identified issues while preserving the original intent.

CURRENT REQUIREMENT:
  Title: {title}
  Statement: {statement}
  Rationale: {rationale}

IDENTIFIED ISSUES:
{issues_text}

DOMAIN CONTEXT: {domain_context}

For each suggestion:
1. Rewrite the statement to fix the issues
2. List the specific changes you made
3. Estimate the quality improvement (e.g., "+15 points")
4. Explain why this version is better

Respond with:
{{
  "suggestions": [
    {{
      "rewritten_statement": "The system shall ...",
      "changes_made": ["Removed ambiguous term 'adequate'", "Added 10ms threshold"],
      "quality_delta": "+15 estimated quality score",
      "explanation": "This version specifies..."
    }}
  ]
}}"""


def improve_requirement(
    statement: str,
    title: str = "",
    rationale: str = "",
    issues: Optional[List[str]] = None,
    domain_context: str = "",
) -> ImproveResponse:
    """
    Given a requirement and its quality issues, generate improved versions.
    """
    if not is_ai_available():
        return ImproveResponse(original_statement=statement, ai_available=False)

    issues = issues or ["general quality improvement needed"]
    issues_text = "\n".join(f"  - {iss}" for iss in issues)

    client = LLMClient()
    prompt = _IMPROVE_PROMPT.format(
        title=title or "(untitled)",
        statement=statement,
        rationale=rationale or "(none)",
        issues_text=issues_text,
        domain_context=domain_context or "General systems engineering",
    )

    raw = client.complete(_WRITER_SYSTEM, prompt, temperature=0.4, max_tokens=2000)

    if raw is None:
        return ImproveResponse(original_statement=statement)

    try:
        suggestions = []
        for item in raw.get("suggestions", []):
            suggestions.append(RewriteSuggestion(
                rewritten_statement=item.get("rewritten_statement", ""),
                changes_made=item.get("changes_made", []),
                quality_delta=item.get("quality_delta", ""),
                explanation=item.get("explanation", ""),
            ))

        return ImproveResponse(
            original_statement=statement,
            suggestions=suggestions[:3],
            model_used=client.model,
        )

    except Exception as exc:
        logger.error("Failed to parse improvement result: %s", exc)
        return ImproveResponse(original_statement=statement)


# ══════════════════════════════════════
#  3. Decompose Requirement
# ══════════════════════════════════════

_DECOMPOSE_PROMPT = """Decompose this high-level requirement into sub-requirements at the next level down.

PARENT REQUIREMENT:
  Title: {title}
  Statement: {statement}
  Type: {req_type}
  Current Level: {current_level}

TARGET LEVEL: {target_level}
PROJECT CONTEXT: {project_context}

Decomposition guidance:
- {current_level} → {target_level}: Break the parent into its constituent capabilities
- Each sub-requirement must be independently testable
- Together, the sub-requirements must fully satisfy the parent
- Use the same domain language but be more specific
- Include performance/interface sub-requirements if implied by the parent

Respond with:
{{
  "sub_requirements": [
    {{
      "title": "...",
      "statement": "The [subsystem/component] shall ...",
      "rationale": "Derived from parent: ...",
      "req_type": "functional",
      "priority": "high",
      "level": "{target_level}",
      "confidence": 0.8,
      "source_fragment": "",
      "notes": "..."
    }}
  ],
  "decomposition_rationale": "This requirement was decomposed into N sub-requirements because..."
}}"""

_LEVEL_NEXT = {"L1": "L2", "L2": "L3", "L3": "L4", "L4": "L5", "L5": "L5"}
_LEVEL_LABELS = {
    "L1": "System", "L2": "Subsystem", "L3": "Component",
    "L4": "Sub-component", "L5": "Detail",
}


def decompose_requirement(
    statement: str,
    title: str = "",
    current_level: str = "L1",
    target_level: str = "",
    req_type: str = "functional",
    project_context: str = "",
) -> DecomposeResponse:
    """
    Take a high-level requirement and decompose it into sub-requirements.
    """
    if not is_ai_available():
        return DecomposeResponse(
            parent_statement=statement,
            parent_level=current_level,
            ai_available=False,
        )

    target = target_level or _LEVEL_NEXT.get(current_level, "L2")

    client = LLMClient()
    prompt = _DECOMPOSE_PROMPT.format(
        title=title or "(untitled)",
        statement=statement,
        req_type=req_type,
        current_level=f"{current_level} ({_LEVEL_LABELS.get(current_level, '')})",
        target_level=f"{target} ({_LEVEL_LABELS.get(target, '')})",
        project_context=project_context or "General systems engineering project",
    )

    raw = client.complete(_WRITER_SYSTEM, prompt, temperature=0.3, max_tokens=3000)

    if raw is None:
        return DecomposeResponse(parent_statement=statement, parent_level=current_level)

    try:
        subs = []
        for item in raw.get("sub_requirements", []):
            subs.append(GeneratedRequirement(
                title=item.get("title", ""),
                statement=item.get("statement", ""),
                rationale=item.get("rationale", ""),
                req_type=_validate_type(item.get("req_type", req_type)),
                priority=_validate_priority(item.get("priority", "medium")),
                level=target,
                confidence=_clamp(item.get("confidence", 0.7), 0, 1),
                source_fragment=item.get("source_fragment", ""),
                notes=item.get("notes", ""),
            ))

        return DecomposeResponse(
            parent_statement=statement,
            parent_level=current_level,
            target_level=target,
            sub_requirements=subs,
            decomposition_rationale=raw.get("decomposition_rationale", ""),
            model_used=client.model,
        )

    except Exception as exc:
        logger.error("Failed to parse decomposition result: %s", exc)
        return DecomposeResponse(parent_statement=statement, parent_level=current_level)


# ══════════════════════════════════════
#  4. Verification Criteria
# ══════════════════════════════════════

_VERIFICATION_PROMPT = """Generate detailed verification criteria for this requirement using the {method} method.

REQUIREMENT:
  Title: {title}
  Statement: {statement}

VERIFICATION METHOD: {method}
DOMAIN CONTEXT: {domain_context}

Generate a complete verification procedure including:
- Why this method is appropriate
- Preconditions that must be met
- Step-by-step procedure (numbered)
- Specific pass/fail criteria (quantitative where possible)
- What data to record
- Estimated duration
- Required resources/equipment

Respond with:
{{
  "method_justification": "...",
  "preconditions": ["System is powered on", "Test database loaded"],
  "steps": [
    {{
      "step_number": 1,
      "action": "Configure the system with...",
      "expected_result": "System displays...",
      "pass_criteria": "Response within 500ms"
    }}
  ],
  "pass_fail_criteria": "The requirement is verified if ALL steps pass...",
  "data_to_record": ["Response times", "Error codes"],
  "estimated_duration": "2 hours",
  "required_resources": ["Test server", "Load testing tool"]
}}"""


def generate_verification_criteria(
    statement: str,
    title: str = "",
    method: str = "test",
    domain_context: str = "",
) -> VerificationCriteria:
    """
    Generate specific pass/fail criteria and procedure for verifying a requirement.
    """
    if not is_ai_available():
        return VerificationCriteria(
            requirement_statement=statement,
            method=method,
            ai_available=False,
        )

    client = LLMClient()
    prompt = _VERIFICATION_PROMPT.format(
        title=title or "(untitled)",
        statement=statement,
        method=method,
        domain_context=domain_context or "General systems engineering",
    )

    raw = client.complete(_WRITER_SYSTEM, prompt, temperature=0.2, max_tokens=2000)

    if raw is None:
        return VerificationCriteria(requirement_statement=statement, method=method)

    try:
        steps = []
        for s in raw.get("steps", []):
            steps.append(VerificationStep(
                step_number=s.get("step_number", 0),
                action=s.get("action", ""),
                expected_result=s.get("expected_result", ""),
                pass_criteria=s.get("pass_criteria", ""),
            ))

        return VerificationCriteria(
            requirement_statement=statement,
            method=method,
            method_justification=raw.get("method_justification", ""),
            preconditions=raw.get("preconditions", []),
            steps=steps,
            pass_fail_criteria=raw.get("pass_fail_criteria", ""),
            data_to_record=raw.get("data_to_record", []),
            estimated_duration=raw.get("estimated_duration", ""),
            required_resources=raw.get("required_resources", []),
            model_used=client.model,
        )

    except Exception as exc:
        logger.error("Failed to parse verification criteria: %s", exc)
        return VerificationCriteria(requirement_statement=statement, method=method)


# ══════════════════════════════════════
#  5. Rationale Generation
# ══════════════════════════════════════

_RATIONALE_PROMPT = """Generate a professional rationale for this systems engineering requirement.

REQUIREMENT:
  Title: {title}
  Statement: {statement}
  Type: {req_type}

PROJECT CONTEXT: {project_context}

The rationale should:
- Explain WHY this requirement exists (not what it does)
- Reference applicable standards or best practices if relevant
- Note what could go wrong if this requirement were not met
- Be 2-4 sentences, professional tone

Also suggest 2-3 alternatives that were implicitly considered.

Respond with:
{{
  "rationale": "This requirement exists because...",
  "alternatives_considered": [
    "An alternative approach would be... but this was not chosen because..."
  ]
}}"""


def generate_rationale(
    statement: str,
    title: str = "",
    req_type: str = "functional",
    project_context: str = "",
) -> GenerateRationaleResponse:
    """Generate a rationale for a requirement that lacks one."""
    if not is_ai_available():
        return GenerateRationaleResponse(ai_available=False)

    client = LLMClient()
    prompt = _RATIONALE_PROMPT.format(
        title=title or "(untitled)",
        statement=statement,
        req_type=req_type,
        project_context=project_context or "General systems engineering project",
    )

    raw = client.complete(_WRITER_SYSTEM, prompt, temperature=0.3, max_tokens=800)

    if raw is None:
        return GenerateRationaleResponse()

    return GenerateRationaleResponse(
        rationale=raw.get("rationale", ""),
        alternatives_considered=raw.get("alternatives_considered", []),
        model_used=client.model,
    )


# ══════════════════════════════════════
#  6. Change Summary for Review Board
# ══════════════════════════════════════

_SUMMARY_PROMPT = """Summarize these requirement changes for a {board_type} review board.

PROJECT: {project_name}

CHANGES:
{changes_text}

Write a professional summary suitable for a {board_type} presentation:
1. Executive summary (2-3 sentences)
2. Key impacts (bullet points)
3. Recommendation (approve / approve with conditions / defer)

Respond with:
{{
  "summary": "Executive summary paragraph...",
  "key_impacts": ["Impact 1", "Impact 2"],
  "recommendation": "Recommend approval because..."
}}"""


def summarize_changes(
    changes: list,
    project_name: str = "",
    board_type: str = "CCB",
) -> SummarizeChangesResponse:
    """Generate a change summary for a review board."""
    if not is_ai_available():
        return SummarizeChangesResponse(ai_available=False)

    if not changes:
        return SummarizeChangesResponse(summary="No changes to summarize.")

    changes_text = ""
    for c in changes[:30]:
        changes_text += (
            f"  - {c.get('req_id', '?')}: {c.get('field', '?')} "
            f"changed from \"{c.get('old_value', '')}\" to \"{c.get('new_value', '')}\"\n"
        )

    client = LLMClient()
    prompt = _SUMMARY_PROMPT.format(
        board_type=board_type,
        project_name=project_name or "ASTRA Project",
        changes_text=changes_text,
    )

    raw = client.complete(_WRITER_SYSTEM, prompt, temperature=0.2, max_tokens=1500)

    if raw is None:
        return SummarizeChangesResponse()

    return SummarizeChangesResponse(
        summary=raw.get("summary", ""),
        key_impacts=raw.get("key_impacts", []),
        recommendation=raw.get("recommendation", ""),
        model_used=client.model,
    )


# ══════════════════════════════════════
#  Validation Helpers
# ══════════════════════════════════════

_VALID_TYPES = {
    "functional", "performance", "interface", "safety", "security",
    "environmental", "reliability", "constraint", "maintainability", "derived",
}
_VALID_PRIORITIES = {"critical", "high", "medium", "low"}
_VALID_LEVELS = {"L1", "L2", "L3", "L4", "L5"}


def _validate_type(v: str) -> str:
    return v if v in _VALID_TYPES else "functional"

def _validate_priority(v: str) -> str:
    return v if v in _VALID_PRIORITIES else "medium"

def _validate_level(v: str) -> str:
    return v if v in _VALID_LEVELS else "L1"

def _clamp(val, lo, hi):
    try:
        return max(lo, min(hi, float(val)))
    except (TypeError, ValueError):
        return lo
