"""
ASTRA — AI Prompt Templates
==============================
File: backend/app/services/ai/prompts.py   ← NEW

All LLM prompts stored as versioned templates.  Each prompt is
designed to elicit structured JSON output matching the schemas
in app.schemas.ai.
"""

PROMPT_VERSION = "1.0"

# ══════════════════════════════════════
#  System prompt (shared across all modes)
# ══════════════════════════════════════

SYSTEM_PROMPT = """You are an expert requirements engineer with deep knowledge of:
- INCOSE Guide for Writing Requirements
- IEEE 830 / ISO/IEC/IEEE 29148 (Requirements Specification)
- NASA SP-2016-6105 Rev2 (Systems Engineering Handbook), especially Appendix C
- DO-178C (Airborne Software) and DO-254 (Airborne Hardware)
- MIL-STD-882E (System Safety)
- 21 CFR Part 820 (Medical Device Quality Systems)

Your role is to evaluate requirements for quality, clarity, testability,
completeness, and atomicity.  Always provide specific, actionable feedback
with concrete suggestions for improvement.

You MUST respond ONLY with valid JSON matching the requested schema.
Do not include any text before or after the JSON object.
Do not use markdown code fences."""


# ══════════════════════════════════════
#  Tier 2: Deep Quality Analysis (single requirement)
# ══════════════════════════════════════

DEEP_QUALITY_PROMPT = """Analyze this requirement for quality according to INCOSE and NASA standards.

REQUIREMENT:
  Title: {title}
  Statement: {statement}
  Rationale: {rationale}
  Domain Context: {domain_context}

Evaluate these dimensions (score each 0-100):
1. **Ambiguity**: Is the meaning clear and unambiguous? Are terms well-defined?
2. **Testability**: Can this requirement be verified through test, analysis, inspection, or demonstration?
3. **Completeness**: Are all necessary conditions, constraints, and acceptance criteria specified?
4. **Atomicity**: Does this requirement specify exactly one testable thing? (No compound "and/shall" statements)
5. **Consistency**: Is the requirement internally consistent and appropriate for the domain?
6. **Feasibility**: Is this requirement technically achievable and realistic?

For each issue found, provide:
- severity: "critical" (blocks acceptance), "warning" (should fix), or "info" (improvement opportunity)
- category: which dimension it falls under
- description: what the problem is
- location: which part of the statement (quote the problematic phrase)
- suggestion: how to fix it

Also provide:
- Up to 3 suggested rewrites that fix all identified issues
- A recommended verification approach (test, analysis, inspection, or demonstration)

Respond with this exact JSON structure:
{{
  "overall_score": <float 0-100>,
  "dimensions": {{
    "ambiguity": <int 0-100>,
    "testability": <int 0-100>,
    "completeness": <int 0-100>,
    "atomicity": <int 0-100>,
    "consistency": <int 0-100>,
    "feasibility": <int 0-100>
  }},
  "issues": [
    {{
      "severity": "<critical|warning|info>",
      "category": "<ambiguity|testability|completeness|atomicity|consistency|feasibility>",
      "description": "<what is wrong>",
      "location": "<quoted phrase from statement>",
      "suggestion": "<how to fix>"
    }}
  ],
  "suggested_rewrites": ["<improved statement 1>", "<improved statement 2>"],
  "verification_approach": "<recommended approach with brief justification>",
  "confidence": <float 0-1>
}}"""


# ══════════════════════════════════════
#  Tier 3: Batch Set Analysis
# ══════════════════════════════════════

SET_ANALYSIS_PROMPT = """Analyze this set of requirements for cross-cutting quality issues.

REQUIREMENTS:
{requirements_text}

Analyze for:
1. **Contradictions**: Requirements that conflict with each other
2. **Redundancies**: Requirements that overlap or duplicate each other
3. **Gaps**: Areas that should be covered but aren't (based on the types present)
4. **Overall Completeness**: How thorough is this specification?

Respond with this exact JSON structure:
{{
  "contradictions": [
    {{
      "req_ids": ["<id1>", "<id2>"],
      "description": "<what conflicts>",
      "severity": "<critical|warning>"
    }}
  ],
  "redundancies": [
    {{
      "req_ids": ["<id1>", "<id2>"],
      "description": "<what overlaps>",
      "suggestion": "<how to consolidate>"
    }}
  ],
  "gaps": [
    {{
      "category": "<functional|performance|security|interface|...>",
      "description": "<what is missing>",
      "suggestion": "<suggested requirement>"
    }}
  ],
  "completeness_score": <int 0-100>,
  "completeness_notes": "<brief assessment>",
  "confidence": <float 0-1>
}}"""


# ══════════════════════════════════════
#  Rewrite Suggestion
# ══════════════════════════════════════

REWRITE_PROMPT = """Rewrite this requirement to fix all quality issues while preserving the original intent.

ORIGINAL:
  Title: {title}
  Statement: {statement}
  Rationale: {rationale}
  Issues: {issues}

Requirements for the rewrite:
- Use "shall" for mandatory requirements
- One testable condition per statement (atomic)
- Include measurable acceptance criteria where possible
- Use active voice
- Avoid prohibited terms (flexible, easy, sufficient, adequate, appropriate, etc.)
- Specify the subject (e.g., "The system shall...")

Respond with this exact JSON structure:
{{
  "rewritten_statement": "<improved statement>",
  "rewritten_rationale": "<improved rationale if needed, or original>",
  "changes_made": ["<description of each change>"],
  "confidence": <float 0-1>
}}"""
