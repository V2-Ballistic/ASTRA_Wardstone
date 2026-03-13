"""
ASTRA Quality Checker — NASA Systems Engineering Handbook Appendix C

Implements automated editorial checks, general goodness checks, and
requirements validation checks per NASA SP-2016-6105 Rev2 Appendix C.
"""

import re
from typing import List, Tuple

# NASA Appendix C: Prohibited ambiguous/unverifiable terms
PROHIBITED_TERMS = [
    "flexible", "easy", "sufficient", "safe", "ad hoc", "adequate",
    "accommodate", "user-friendly", "usable", "when required",
    "if required", "appropriate", "fast", "portable", "lightweight",
    "light-weight", "small", "large", "maximize", "minimize",
    "sufficient", "robust", "quickly", "easily", "clearly",
    "simply", "efficiently", "effectively", "reasonable",
    "as appropriate", "etc", "and/or", "but not limited to",
    "as needed", "timely", "user friendly"
]

# Terms that are ambiguous quantifiers
AMBIGUOUS_QUANTIFIERS = [
    "some", "several", "many", "few", "often", "usually",
    "generally", "normally", "approximately", "about",
    "significant", "minimal", "considerable"
]

# NASA Appendix C: Correct keyword usage
# SHALL = requirement, WILL = fact/declaration, SHOULD = goal
REQUIREMENT_KEYWORDS = {
    "shall": "Mandatory requirement (correct usage)",
    "will": "Statement of fact or declaration of purpose",
    "should": "Goal or recommended practice (not binding)",
    "must": "Consider using 'shall' instead for requirements",
}


def check_requirement_quality(statement: str, title: str = "", rationale: str = "") -> dict:
    """
    Run the full NASA Appendix C quality check suite on a requirement.
    
    Returns:
        dict with score (0-100), passed (bool), warnings (list), suggestions (list)
    """
    warnings = []
    suggestions = []
    score = 100.0

    if not statement or len(statement.strip()) < 10:
        return {
            "score": 0, "passed": False,
            "warnings": ["Requirement statement is empty or too short"],
            "suggestions": ["Write a complete requirement statement using: 'The system shall [verb] [condition]'"]
        }

    text = statement.strip()

    # ── Editorial Checks (NASA Appendix C: Editorial Checklist) ──

    # 1. Check for SHALL keyword
    has_shall = bool(re.search(r'\bshall\b', text, re.IGNORECASE))
    has_will = bool(re.search(r'\bwill\b', text, re.IGNORECASE))
    has_should = bool(re.search(r'\bshould\b', text, re.IGNORECASE))

    if not has_shall and not has_will and not has_should:
        warnings.append("Missing requirement keyword — use 'shall' for requirements, 'will' for facts, 'should' for goals")
        score -= 20

    # 2. Check for passive voice indicators
    passive_indicators = [
        r'\bshall\s+be\s+\w+ed\b',       # "shall be processed"
        r'\bis\s+\w+ed\b',                # "is processed"
        r'\bare\s+\w+ed\b',               # "are processed"
        r'\bwas\s+\w+ed\b',               # "was processed"
        r'\bwere\s+\w+ed\b',              # "were processed"
        r'\bbeen\s+\w+ed\b',              # "been processed"
        r'\bbe\s+\w+ed\b',                # "be processed"
    ]
    
    for pattern in passive_indicators:
        if re.search(pattern, text, re.IGNORECASE):
            suggestions.append("Possible passive voice detected — use active voice: 'The system shall [verb]'")
            score -= 5
            break

    # 3. Check for multiple SHALL (compound requirement)
    shall_count = len(re.findall(r'\bshall\b', text, re.IGNORECASE))
    if shall_count > 1:
        warnings.append(f"Multiple 'shall' statements ({shall_count}) — split into {shall_count} separate requirements")
        score -= 15

    # 4. Check for compound statements with "and"
    if has_shall and re.search(r'\bshall\b.*\band\b.*\bshall\b', text, re.IGNORECASE):
        warnings.append("Compound requirement detected — each requirement should express one testable statement")
        score -= 10

    # 5. Check for negation (shall not)
    if re.search(r'\bshall\s+not\b', text, re.IGNORECASE):
        suggestions.append("Negative requirement ('shall not') — consider restating positively when possible")
        score -= 3

    # ── Prohibited Terms Check ──

    found_prohibited = []
    text_lower = text.lower()
    for term in PROHIBITED_TERMS:
        if term.lower() in text_lower:
            found_prohibited.append(term)

    if found_prohibited:
        warnings.append(f"Prohibited unverifiable terms: {', '.join(found_prohibited)} — replace with measurable, verifiable values")
        score -= min(5 * len(found_prohibited), 25)

    # Check ambiguous quantifiers
    found_ambiguous = []
    for term in AMBIGUOUS_QUANTIFIERS:
        if re.search(rf'\b{term}\b', text, re.IGNORECASE):
            found_ambiguous.append(term)

    if found_ambiguous:
        suggestions.append(f"Ambiguous quantifiers: {', '.join(found_ambiguous)} — use specific numeric values")
        score -= min(3 * len(found_ambiguous), 15)

    # ── General Goodness Checks ──

    # Check for TBD/TBR values
    tbd_count = len(re.findall(r'\bTBD\b', text))
    tbr_count = len(re.findall(r'\bTBR\b', text))
    if tbd_count > 0:
        warnings.append(f"{tbd_count} TBD value(s) — provide resolution plan, responsible party, and deadline")
        score -= 8 * tbd_count
    if tbr_count > 0:
        suggestions.append(f"{tbr_count} TBR value(s) — confirm best-estimate values before baselining")
        score -= 3 * tbr_count

    # Check for vague pronouns
    vague_pronouns = re.findall(r'\b(this|these|that|those|it)\b', text, re.IGNORECASE)
    if len(vague_pronouns) > 1:
        suggestions.append("Multiple indefinite pronouns — replace 'this/these/it' with specific nouns for clarity")
        score -= 5

    # Check minimum length (too short = likely incomplete)
    word_count = len(text.split())
    if word_count < 5:
        warnings.append("Requirement is very short — may be incomplete")
        score -= 10
    elif word_count > 80:
        suggestions.append("Requirement is very long — consider splitting into sub-requirements")
        score -= 5

    # ── Rationale Check ──

    if not rationale or len(rationale.strip()) < 5:
        suggestions.append("Missing rationale — explain WHY this requirement is needed")
        score -= 5

    # ── Verifiability Check ──

    # Look for measurable criteria
    has_numeric = bool(re.search(r'\d+', text))
    has_unit = bool(re.search(
        r'\b(seconds?|minutes?|hours?|ms|MB|GB|percent|%|users?|requests?|px|dpi)\b',
        text, re.IGNORECASE
    ))
    if has_shall and not has_numeric and not has_unit:
        suggestions.append("No measurable criteria detected — add quantifiable acceptance values when possible")
        score -= 5

    # Clamp score
    score = max(0, min(100, score))

    return {
        "score": round(score, 1),
        "passed": score >= 70 and len(warnings) == 0,
        "warnings": warnings,
        "suggestions": suggestions,
    }


def generate_requirement_id(project_code: str, req_type: str, sequence: int) -> str:
    """Generate a hierarchical requirement ID per INCOSE conventions."""
    TYPE_PREFIXES = {
        "functional": "FR",
        "performance": "PR",
        "interface": "IR",
        "environmental": "ER",
        "constraint": "CR",
        "safety": "SAF",
        "security": "SR",
        "reliability": "RL",
        "maintainability": "MR",
        "derived": "DR",
    }
    prefix = TYPE_PREFIXES.get(req_type.lower(), "GR")
    return f"{prefix}-{sequence:03d}"
