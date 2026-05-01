"""
ASTRA — Source Coverage Validator package
===========================================
File: backend/app/services/coverage/__init__.py   ← NEW (Phase 6, ASTRA-TDD-INTF-002)

Per spec §13. Computes per-requirement source-link coverage status, surfaces
orphans, and refreshes a materialized view used by the dashboard. The
validator severity rules (§13.2) live in :mod:`source_validator`, the MV
refresh in :mod:`refresh`, and the source-type pattern matcher in
:mod:`suggestions`.
"""

from app.services.coverage.source_validator import (
    OrphanRequirement,
    CoverageReport,
    LevelSummary,
    validate_project_coverage,
)
from app.services.coverage.refresh import refresh_coverage_mv
from app.services.coverage.suggestions import suggest_source_type

__all__ = [
    "OrphanRequirement",
    "CoverageReport",
    "LevelSummary",
    "validate_project_coverage",
    "refresh_coverage_mv",
    "suggest_source_type",
]
