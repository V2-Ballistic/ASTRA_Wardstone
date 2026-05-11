"""ASTRA — HAROLD nomenclature integration — Pydantic schemas

TDD-HAROLD-001 Phase 2. Every HAROLD-proxy endpoint returns a
`{harold_available: bool, ...}` shape so the frontend can decide
whether to render the HAROLD affordances without parsing HTTP status
codes — see AD-8 + Phase 3 §3.1 in the prompt for rationale.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


class HaroldSystemCode(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    code:        str
    name:        str
    description: str


class HaroldHeartbeatResponse(BaseModel):
    """Result of GET /api/v1/harold/heartbeat. Always 200; the
    flag-and-reachability live inside the body."""

    enabled:          bool
    reachable:        bool
    base_url:         str
    response_time_ms: Optional[int] = None
    version:          Optional[str] = None
    reason:           Optional[str] = None


class HaroldUnavailable(BaseModel):
    """Generic shape returned by every HAROLD-proxy endpoint when the
    integration is off or HAROLD is down."""

    harold_available: bool = Field(default=False)
    reason:           str


# ── /system-codes ────────────────────────────────────────────────

class SystemCodesPayload(BaseModel):
    codes: list[HaroldSystemCode]


class SystemCodesAvailable(BaseModel):
    harold_available: bool = Field(default=True)
    data:             SystemCodesPayload


# ── /suggest-wpn ─────────────────────────────────────────────────

class WpnSuggestion(BaseModel):
    """Mirrors the `output` block of HAROLD's `_wardstone-harold-search`
    tool. The prompt's old "next-WPN allocator" fields
    (suggested_wpn / next_index / existing_count) don't exist in real
    HAROLD — this is the actual NL-search response shape."""

    suggestion:       str
    pattern_id:       str
    pattern_label:    str
    confidence:       float
    reasoning:        str
    extracted_fields: dict[str, str]
    candidates:       list[dict[str, Any]]
    notes:            list[str]
    llm_used:         Optional[str] = None


class WpnSuggestionAvailable(BaseModel):
    harold_available: bool = Field(default=True)
    data:             WpnSuggestion


# ── /catalog/designators (outbound, HAROLD ← ASTRA) ──────────────

class CatalogDesignatorsResponse(BaseModel):
    designators:   list[str]
    total:         int
    system_filter: Optional[str] = None
