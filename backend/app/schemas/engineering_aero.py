"""ASTRA — Aero deck schemas (spec §6). pydantic v2."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


class AeroEnvelope(BaseModel):
    mach_min: Optional[float] = None
    mach_max: Optional[float] = None
    alpha_min_deg: Optional[float] = None
    alpha_max_deg: Optional[float] = None


class AeroDeckRevisionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wpn: str
    rev_letter: str
    deck_sha256: str
    source_filenames: List[str] = Field(default_factory=list)
    mach_min: Optional[float] = None
    mach_max: Optional[float] = None
    alpha_min_deg: Optional[float] = None
    alpha_max_deg: Optional[float] = None
    sref_m2: Optional[float] = None
    lref_m: Optional[float] = None
    warnings: List[str] = Field(default_factory=list)
    defaulted_fields: List[str] = Field(default_factory=list)
    notes: Optional[str] = None
    created_utc: Optional[datetime] = None


class AeroDeckRevisionDetail(AeroDeckRevisionSummary):
    source_sha256s: List[str] = Field(default_factory=list)
    deck: Dict[str, Any]


class AeroDeckSummary(BaseModel):
    """List-view row: identity + active-revision envelope."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    wpn: str
    name: str
    oml_wpn: Optional[str] = None
    system_code: str = "AER"
    current_rev: Optional[str] = None
    revision_count: int = 0
    mach_min: Optional[float] = None
    mach_max: Optional[float] = None
    alpha_min_deg: Optional[float] = None
    alpha_max_deg: Optional[float] = None
    updated_at: Optional[datetime] = None


class AeroDeckDetail(AeroDeckSummary):
    base_index: Optional[int] = None
    created_at: Optional[datetime] = None
    revisions: List[AeroDeckRevisionSummary] = Field(default_factory=list)


class AeroIngestResponse(BaseModel):
    """Result of the auto-name ingest flow. ``wpn`` is the FULL
    HAROLD-issued WPN for the created revision, verbatim."""
    deck_id: int
    deck_wpn: str
    wpn: str
    rev_letter: str
    name: str
    deck_sha256: str
    is_new_deck: bool
    envelope: AeroEnvelope
    warnings: List[str] = Field(default_factory=list)
    defaulted_fields: List[str] = Field(default_factory=list)


class AeroActiveRevisionUpdate(BaseModel):
    rev_letter: str = Field(..., min_length=1, max_length=8)


class AeroPreviewResponse(BaseModel):
    wpn: str
    rev_letter: str
    mach: float
    alpha_deg: float
    beta_deg: float
    delta_deg: float
    values: Dict[str, float]
