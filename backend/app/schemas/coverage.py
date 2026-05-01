"""
ASTRA — Pydantic schemas for the Source Coverage Validator
============================================================
File: backend/app/schemas/coverage.py   ← NEW (Phase 1, ASTRA-TDD-INTF-002)

Schemas for CoverageException Create/Response plus the per-level summary
report shape described in spec §13.7. Logic implementation lands in Phase 6.

Conventions:
  - F-038: list/dict defaults via `Field(default_factory=...)`.
  - F-133: every `Optional[...]` field gets `= None`.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models.req_sync import SourceEntityType


# ══════════════════════════════════════════════════════════════
#  CoverageException
# ══════════════════════════════════════════════════════════════

class CoverageExceptionCreate(BaseModel):
    project_id: int
    requirement_id: int
    reason: str
    expires_at: Optional[datetime] = None


class CoverageExceptionApprove(BaseModel):
    """Admin co-sign flow — approves the exception so it counts toward coverage."""
    notes: Optional[str] = None


class CoverageExceptionResponse(BaseModel):
    id: int
    project_id: int
    requirement_id: int
    reason: str
    is_active: bool
    expires_at: Optional[datetime] = None
    created_at: datetime
    created_by_id: int
    approved_by_id: Optional[int] = None
    approved_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  Coverage report (per spec §13.7 traffic-light page)
# ══════════════════════════════════════════════════════════════

class CoverageSeverity:
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class CoverageLevelSummary(BaseModel):
    level: str
    total: int = 0
    traced: int = 0
    orphan: int = 0
    severity: str = CoverageSeverity.OK


class OrphanRequirement(BaseModel):
    requirement_id: int
    req_id: str
    title: str
    level: str
    status: str
    suggested_source_type: Optional[SourceEntityType] = None


class CoverageReportResponse(BaseModel):
    project_id: int
    total_requirements: int = 0
    by_level: List[CoverageLevelSummary] = Field(default_factory=list)
    orphans: List[OrphanRequirement] = Field(default_factory=list)
    exception_count: int = 0
    generated_at: datetime
