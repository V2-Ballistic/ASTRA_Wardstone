"""
ASTRA — Pydantic schemas for the reactive requirement sync engine
==================================================================
File: backend/app/schemas/req_sync.py   ← NEW (Phase 1, ASTRA-TDD-INTF-002)

Schemas for RequirementSourceLink, RequirementSyncProposal, plus the
CoverageReport summary dataclass shape used by the §13 validator (logic
implementation lands in Phase 6 — only the schema is defined now so the
catalog/req-sync UI in Phase 3 can typecheck against the eventual response).

Conventions:
  - F-038: list/dict defaults via `Field(default_factory=...)`.
  - F-133: every `Optional[...]` field gets `= None`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.models.req_sync import (
    SourceEntityType,
    SyncProposalStatus,
    SyncProposalType,
)


# ══════════════════════════════════════════════════════════════
#  RequirementSourceLink
# ══════════════════════════════════════════════════════════════

class RequirementSourceLinkCreate(BaseModel):
    requirement_id: int
    source_entity_type: SourceEntityType
    source_entity_id: int
    template_id: str = Field(..., max_length=100)
    template_inputs: Dict[str, Any] = Field(default_factory=dict)
    role: str = Field(default="primary", max_length=50)


class RequirementSourceLinkResponse(BaseModel):
    id: int
    requirement_id: int
    source_entity_type: SourceEntityType
    source_entity_id: int
    template_id: str
    template_inputs: Dict[str, Any] = Field(default_factory=dict)
    role: str
    last_synced_at: datetime

    class Config:
        from_attributes = True


# ══════════════════════════════════════════════════════════════
#  RequirementSyncProposal
# ══════════════════════════════════════════════════════════════

class RequirementSyncProposalResponse(BaseModel):
    id: int
    requirement_id: int
    triggered_by_entity_type: SourceEntityType
    triggered_by_entity_id: int
    trigger_event: str
    old_statement: str
    new_statement: Optional[str] = None
    old_rationale: Optional[str] = None
    new_rationale: Optional[str] = None
    field_diffs: Dict[str, Any] = Field(default_factory=dict)
    proposal_type: SyncProposalType
    status: SyncProposalStatus
    auto_applied: bool = False
    created_at: datetime
    reviewed_at: Optional[datetime] = None
    reviewed_by_id: Optional[int] = None
    reviewer_notes: Optional[str] = None

    class Config:
        from_attributes = True


class RequirementSyncProposalReviewRequest(BaseModel):
    """Body of /req-sync/proposals/{id}/{accept,reject}."""
    reviewer_notes: Optional[str] = None
    admin_force: bool = False


class BulkAcceptRequest(BaseModel):
    """Body of /req-sync/proposals/bulk-accept — atomic all-or-none."""
    proposal_ids: List[int] = Field(default_factory=list)
    reviewer_notes: Optional[str] = None


# ══════════════════════════════════════════════════════════════
#  Sync-lock controls
# ══════════════════════════════════════════════════════════════

class RequirementSyncLockRequest(BaseModel):
    reason: Optional[str] = Field(None, max_length=500)


# ══════════════════════════════════════════════════════════════
#  Coverage report (placeholder shape — logic in Phase 6 §13)
# ══════════════════════════════════════════════════════════════

class CoverageLevelSummary(BaseModel):
    total: int = 0
    traced: int = 0
    orphan: int = 0
    severity: str = "ok"  # one of: ok, warning, error


class CoverageOrphanRow(BaseModel):
    requirement_id: int
    req_id: str
    title: str
    level: str
    status: str
    suggested_source_type: Optional[SourceEntityType] = None


class CoverageReport(BaseModel):
    project_id: int
    total_requirements: int = 0
    by_level: Dict[str, CoverageLevelSummary] = Field(default_factory=dict)
    orphans: List[CoverageOrphanRow] = Field(default_factory=list)
    exception_count: int = 0


# ══════════════════════════════════════════════════════════════
#  Phase 5 — endpoint payloads
# ══════════════════════════════════════════════════════════════

class RequirementSyncProposalDetailResponse(RequirementSyncProposalResponse):
    """Detail view — adds requirement context the list view doesn't carry."""
    requirement_req_id: Optional[str] = None
    requirement_title: Optional[str] = None
    requirement_status: Optional[str] = None
    requirement_level: Optional[str] = None
    project_id: Optional[int] = None


class SyncProposalListResponse(BaseModel):
    total: int = 0
    items: List[RequirementSyncProposalResponse] = Field(default_factory=list)


class BulkProposalActionResult(BaseModel):
    proposal_id: int
    success: bool
    error: Optional[str] = None


class BulkProposalActionResponse(BaseModel):
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    results: List[BulkProposalActionResult] = Field(default_factory=list)


class SourceLinksResponse(BaseModel):
    requirement_id: int
    items: List[RequirementSourceLinkResponse] = Field(default_factory=list)
