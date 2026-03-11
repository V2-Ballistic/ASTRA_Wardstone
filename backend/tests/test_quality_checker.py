"""
ASTRA — Quality Checker Unit Tests
====================================
Pure function tests — no database or HTTP needed.

File: backend/tests/test_quality_checker.py
"""

from app.services.quality_checker import check_requirement_quality, generate_requirement_id


class TestCheckRequirementQuality:

    def test_empty_statement(self):
        result = check_requirement_quality("")
        assert result["score"] == 0, "Empty statement must score 0"
        assert result["passed"] is False

    def test_missing_shall_keyword(self):
        result = check_requirement_quality(
            "The system provides a login page for all users."
        )
        assert result["score"] < 100, "No 'shall' should reduce score"
        warnings = " ".join(result["warnings"]).lower()
        assert "keyword" in warnings or "shall" in warnings, (
            "Should warn about missing requirement keyword"
        )

    def test_prohibited_terms_detected(self):
        result = check_requirement_quality(
            "The system shall be flexible and provide adequate performance."
        )
        warnings = " ".join(result["warnings"]).lower()
        assert "prohibited" in warnings or "unverifiable" in warnings, (
            "'flexible' and 'adequate' are NASA-prohibited terms"
        )
        assert result["score"] < 100

    def test_compound_requirement(self):
        result = check_requirement_quality(
            "The system shall log all events and the system shall encrypt all data."
        )
        warnings = " ".join(result["warnings"]).lower()
        assert "multiple" in warnings or "shall" in warnings, (
            "Two 'shall' clauses should trigger compound-requirement warning"
        )
        assert result["score"] < 100

    def test_tbd_detection(self):
        result = check_requirement_quality(
            "The system shall respond within TBD seconds."
        )
        warnings = " ".join(result["warnings"]).lower()
        assert "tbd" in warnings, "TBD must be flagged"
        assert result["score"] < 100

    def test_passive_voice_detection(self):
        result = check_requirement_quality(
            "Data shall be processed and results shall be displayed by the system."
        )
        suggestions = " ".join(result["suggestions"]).lower()
        # passive voice detection is in suggestions, not warnings
        assert "passive" in suggestions, "Passive voice should be detected"

    def test_perfect_requirement(self):
        result = check_requirement_quality(
            statement="The system shall authenticate users within 3 seconds using bcrypt.",
            title="User Authentication",
            rationale="Secure authentication protects sensitive data.",
        )
        assert result["score"] > 80, (
            f"Well-formed requirement should score > 80, got {result['score']}"
        )

    def test_short_statement(self):
        result = check_requirement_quality("Hi")
        assert result["score"] == 0, "Very short statement must score 0"
        assert result["passed"] is False


class TestGenerateRequirementId:

    def test_generate_requirement_id(self):
        cases = {
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
        for req_type, expected_prefix in cases.items():
            rid = generate_requirement_id("PROJ", req_type, 1)
            assert rid == f"{expected_prefix}-001", (
                f"generate_requirement_id('PROJ', '{req_type}', 1) "
                f"should be '{expected_prefix}-001', got '{rid}'"
            )

    def test_unknown_type_gets_generic_prefix(self):
        rid = generate_requirement_id("PROJ", "unknown_type", 5)
        assert rid == "GR-005", "Unknown type should use GR prefix"

    def test_sequence_padding(self):
        rid = generate_requirement_id("X", "functional", 42)
        assert rid == "FR-042", "Sequence must be zero-padded to 3 digits"
