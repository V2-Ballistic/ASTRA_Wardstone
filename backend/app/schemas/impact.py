"""
ASTRA — Impact Analysis Schemas
==================================
File: backend/app/schemas/impact.py   ← NEW

Pydantic models for:
  - Impact reports (full traversal results)
  - Individual impact items
  - Dependency trees (upstream / downstream chains)
  - What-if previews (delete / modify actions)
  - Stored impact report model
"""

from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


# ══════════════════════════════════════
#  Impact Items
# ══════════════════════════════════════

class ImpactItem(BaseModel):
    """A single entity affected by a requirement change."""
    entity_type: str               # "requirement", "verification", "source_artifact", "baseline"
    entity_id: int
    entity_identifier: str = ""    # e.g., "FR-003", "VER-005"
    entity_title: str = ""
    impact_level: str = "direct"   # "direct" (1 hop), "indirect" (2+ hops)
    hop_count: int = 1
    relationship_path: List[str] = []   # ["FR-001 →satisfies→ IR-003 →verifies→ VER-005"]
    link_types_involved: List[str] = []  # ["satisfies", "verifies"]
    current_status: str = ""
    ai_explanation: str = ""


class AffectedVerification(BaseModel):
    """A verification that may need re-execution."""
    verification_id: int
    requirement_id: int
    requirement_identifier: str = ""
    method: str = ""               # test, analysis, inspection, demonstration
    current_status: str = ""       # planned, in_progress, pass, fail
    needs_rerun: bool = True
    reason: str = ""


class AffectedBaseline(BaseModel):
    """A baseline that contains the changed requirement."""
    baseline_id: int
    baseline_name: str = ""
    created_at: Optional[str] = None
    requirements_count: int = 0
    is_current: bool = False
    reason: str = ""


# ══════════════════════════════════════
#  Full Impact Report
# ══════════════════════════════════════

class ImpactReport(BaseModel):
    """Complete impact analysis result."""
    # Source
    changed_requirement: Dict[str, Any] = {}
    change_description: str = ""

    # Classified impacts
    direct_impacts: List[ImpactItem] = []
    indirect_impacts: List[ImpactItem] = []

    # Affected sub-systems
    affected_verifications: List[AffectedVerification] = []
    affected_baselines: List[AffectedBaseline] = []

    # Risk assessment
    risk_level: str = "low"     # low, medium, high, critical
    risk_factors: List[str] = []

    # AI-generated summary
    ai_summary: str = ""
    ai_available: bool = True

    # Metrics
    dependency_depth: int = 0
    total_affected: int = 0
    total_direct: int = 0
    total_indirect: int = 0

    # Metadata
    analyzed_at: Optional[str] = None
    analysis_duration_ms: int = 0


# ══════════════════════════════════════
#  Dependency Tree
# ══════════════════════════════════════

class DependencyNode(BaseModel):
    """A single node in the dependency tree."""
    entity_type: str
    entity_id: int
    identifier: str = ""
    title: str = ""
    status: str = ""
    level: str = ""              # L1-L5 for requirements
    hop_count: int = 0
    link_type: str = ""          # The link type that connects this to its parent
    link_direction: str = ""     # "upstream" or "downstream"
    children: List["DependencyNode"] = []


class DependencyTree(BaseModel):
    """Full dependency chain for a requirement."""
    root_requirement: Dict[str, Any] = {}
    upstream: List[DependencyNode] = []     # What this requirement traces TO
    downstream: List[DependencyNode] = []   # What traces TO this requirement
    total_upstream: int = 0
    total_downstream: int = 0
    max_depth_up: int = 0
    max_depth_down: int = 0


# ══════════════════════════════════════
#  What-If Preview
# ══════════════════════════════════════

class WhatIfPreview(BaseModel):
    """Preview of impact before performing an action."""
    requirement_id: int
    requirement_identifier: str = ""
    action: str = "modify"         # "delete" or "modify"

    # Counts
    total_affected: int = 0
    direct_count: int = 0
    indirect_count: int = 0
    orphaned_count: int = 0        # Children that would lose parent (delete only)
    verification_rerun_count: int = 0
    baseline_impact_count: int = 0

    # Details
    affected_items: List[ImpactItem] = []
    orphaned_requirements: List[Dict[str, Any]] = []
    verifications_affected: List[AffectedVerification] = []
    baselines_affected: List[AffectedBaseline] = []

    # Risk
    risk_level: str = "low"
    ai_summary: str = ""
    ai_available: bool = True

    # Recommendation
    requires_change_request: bool = False
    recommendation: str = ""


# ══════════════════════════════════════
#  Stored Impact Report
# ══════════════════════════════════════

class StoredImpactReport(BaseModel):
    """A persisted impact report linked to requirement history."""
    id: int
    requirement_id: int
    requirement_identifier: str = ""
    change_description: str = ""
    report_json: Dict[str, Any] = {}
    risk_level: str = "low"
    total_affected: int = 0
    created_by_id: Optional[int] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


# Allow self-referencing in DependencyNode
DependencyNode.model_rebuild()
