"""
ASTRA — Pydantic schemas for the Engineering Frame ICD
=======================================================
File: backend/app/schemas/engineering_frame.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §3)

Conventions (audit carry-forwards):
  - F-038: list/dict defaults always use `Field(default_factory=...)`.
  - F-133: every `Optional[...]` field gets `= None`.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class FrameIcdRegisterRequest(BaseModel):
    """Body for POST /engineering/frame-icd — idempotent ensure/register.

    All fields optional: an empty body registers (or returns) the
    canonical CITADEL frame with spec defaults. Supplying values that
    differ from the current revision creates a NEW revision (revisions
    are immutable; nothing is edited in place).
    """
    datum: Optional[str] = Field(
        None, max_length=100,
        description=(
            "Datum point name. PARAMETERIZED — stakeholder unconfirmed; "
            "defaults to 'OML_nose_tip'."
        ),
    )
    axes: Optional[str] = Field(
        None, max_length=100,
        description="Axis convention; defaults to 'x_fwd_y_right_z_down'.",
    )
    units: Optional[str] = Field(
        None, max_length=20, description="Unit system; defaults to 'SI'.",
    )
    rules: Optional[str] = Field(
        None,
        description="Rules text tying all numeric surfaces to the datum.",
    )
    notes: Optional[str] = None


class FrameIcdRevisionResponse(BaseModel):
    id: int
    frame_icd_id: int
    rev: int
    datum: str
    axes: str
    units: str
    rules: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    created_by_id: int

    class Config:
        from_attributes = True


class FrameIcdResponse(BaseModel):
    """ICD header + its current (highest-rev) revision."""
    id: int
    key: str
    name: str
    created_at: Optional[datetime] = None
    created_by_id: int
    current_rev: int
    revision: FrameIcdRevisionResponse

    class Config:
        from_attributes = True


class FrameIcdRevisionsResponse(BaseModel):
    icd_id: int
    key: str
    name: str
    total: int
    revisions: List[FrameIcdRevisionResponse] = Field(default_factory=list)
