"""
ASTRA — Pydantic schemas for the Source Coverage Validator
============================================================
File: backend/app/schemas/coverage.py
   ← created Phase 1 (CoverageException CRUD), extended Phase 6 (report shape)

Shapes the §13.7 dashboard JSON + the §9.7 endpoint request/response bodies.
The Phase 1 placeholder classes (``CoverageLevelSummary``, ``OrphanRequirement``)
are preserved for backwards compatibility with anything that already imported
them; Phase 6 adds the actual response shapes consumed by the new router.

Conventions:
  - F-038: list/dict defaults via `Field(default_factory=...)`.
  - F-133: every `Optional[...]` field gets `= None`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.req_sync import SourceEntityType


# ══════════════════════════════════════════════════════════════
#  CoverageException — created Phase 1
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


class CoverageExceptionListResponse(BaseModel):
    total: int = 0
    items: List[CoverageExceptionResponse] = Field(default_factory=list)


class CosignRequest(BaseModel):
    """Body for ``POST /coverage/exceptions/{id}/cosign``. ``notes`` is for
    the audit detail; the cosign itself is implied by the endpoint."""
    notes: Optional[str] = None


# ══════════════════════════════════════════════════════════════
#  Coverage severity / per-level summary
# ══════════════════════════════════════════════════════════════

class CoverageSeverity:
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"


class LevelSeveritySummary(BaseModel):
    """Per-level totals for the traffic-light render (Phase 6)."""
    total: int = 0
    ok: int = 0
    warning: int = 0
    error: int = 0


# Legacy Phase 1 placeholder — kept so any earlier importer doesn't break.
class CoverageLevelSummary(BaseModel):
    level: str
    total: int = 0
    traced: int = 0
    orphan: int = 0
    severity: str = CoverageSeverity.OK


# Legacy Phase 1 placeholder — kept for backwards compatibility.
class OrphanRequirement(BaseModel):
    requirement_id: int
    req_id: str
    title: str
    level: str
    status: str
    suggested_source_type: Optional[SourceEntityType] = None


# ══════════════════════════════════════════════════════════════
#  Phase 6 response shapes — what the router actually returns
# ══════════════════════════════════════════════════════════════

class CoverageReportResponse(BaseModel):
    """``GET /coverage/source/{project_id}`` body."""
    project_id: int
    summary: Dict[str, LevelSeveritySummary] = Field(default_factory=dict)
    computed_at: datetime
    used_materialized_view: bool = True
    exception_count: int = 0


class OrphanRequirementResponse(BaseModel):
    requirement_id: int
    req_text: str            # human-facing identifier ("FR-001")
    title: str
    level: str               # L1..L5
    severity: str            # 'ok' | 'warning' | 'error'
    parent_id: Optional[int] = None
    parent_traced: bool = False
    suggested_source_type: Optional[SourceEntityType] = None
    has_active_exception: bool = False


class OrphanListResponse(BaseModel):
    """``GET /coverage/source/{project_id}/orphans`` body."""
    project_id: int
    total: int = 0
    items: List[OrphanRequirementResponse] = Field(default_factory=list)
