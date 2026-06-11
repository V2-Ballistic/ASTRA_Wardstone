"""ASTRA — Configurations tracker schemas (spec §8/§9). pydantic v2."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

#: Closed §1 role set — mirrors bundle_schema.Role.
ComponentRole = Literal[
    "oml", "structure", "avionics", "payload",
    "propulsion", "recovery", "ballast", "other",
]


class ComponentIn(BaseModel):
    """One BOM line. ``role`` is REQUIRED (closed set); ``placement``
    is a 4×4 row-major homogeneous matrix (CADPORT §6 transform_m
    convention); missing placement ⇒ identity."""
    role: ComponentRole
    wpn: str = Field(..., min_length=1, max_length=64)
    rev: Optional[str] = Field(None, max_length=8)
    name: Optional[str] = Field(None, max_length=500)
    placement: Optional[List[List[float]]] = Field(
        None, min_length=4, max_length=4,
    )
    notes: Optional[str] = None


class AeroBindingIn(BaseModel):
    wpn: str = Field(..., min_length=1, max_length=64)
    rev_letter: str = Field(..., min_length=1, max_length=8)


class StageIn(BaseModel):
    stageNum: int = Field(..., ge=1)
    motorWpn: str = Field(..., min_length=1, max_length=64)
    motorRevLetter: str = Field(..., min_length=1, max_length=8)
    ignitionTime_s: float = 0.0
    thrustAxis_B: List[float] = Field(
        default=[1.0, 0.0, 0.0], min_length=3, max_length=3,
    )
    mcTrialId: Optional[str] = None


class ConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    components: List[ComponentIn]
    aero_binding: Optional[AeroBindingIn] = None
    stage_map: List[StageIn] = Field(default_factory=list)
    top_assembly_wpn: Optional[str] = Field(None, max_length=64)
    astra_baseline_id: Optional[int] = None
    notes: Optional[str] = None


class ConfigRevisionCreate(BaseModel):
    """Same body as create, minus the name (identity is fixed)."""
    description: Optional[str] = None
    components: List[ComponentIn]
    aero_binding: Optional[AeroBindingIn] = None
    stage_map: List[StageIn] = Field(default_factory=list)
    top_assembly_wpn: Optional[str] = Field(None, max_length=64)
    astra_baseline_id: Optional[int] = None
    notes: Optional[str] = None


class ConfigCloneRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=500)


class ConfigActiveRevisionUpdate(BaseModel):
    rev_letter: str = Field(..., min_length=1, max_length=8)


# ── Read models ─────────────────────────────────────────────────────


class ConfigRevisionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wpn: str
    rev_letter: str
    description: Optional[str] = None
    total_mass_kg: Optional[float] = None
    component_count: int = 0
    astra_baseline_id: Optional[int] = None
    created_utc: Optional[datetime] = None


class ConfigSummary(BaseModel):
    """List-view row (spec §8 list endpoint)."""
    id: int
    wpn: str
    name: str
    system_code: str = "CFG"
    revision_count: int = 0
    current_rev: Optional[str] = None
    total_mass_kg: Optional[float] = None
    component_count: int = 0
    astra_baseline_id: Optional[int] = None
    updated_at: Optional[datetime] = None


class ConfigDetail(ConfigSummary):
    base_index: Optional[int] = None
    created_at: Optional[datetime] = None
    revisions: List[ConfigRevisionSummary] = Field(default_factory=list)


class ConfigRevisionDetail(BaseModel):
    """Full resolved revision — the on-screen flight card."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    wpn: str
    rev_letter: str
    config_wpn: str
    config_name: str
    description: Optional[str] = None
    top_assembly_wpn: Optional[str] = None
    frame_icd_id: int
    frame_icd_rev: int
    astra_baseline_id: Optional[int] = None
    components: List[Dict[str, Any]] = Field(default_factory=list)
    aero_binding: Optional[Dict[str, Any]] = None
    stage_map: List[Dict[str, Any]] = Field(default_factory=list)
    rollup: Dict[str, Any]
    validation: Dict[str, Any] = Field(default_factory=dict)
    notes: Optional[str] = None
    created_utc: Optional[datetime] = None


class ConfigCreateResponse(BaseModel):
    """Create / revise / clone response. ``wpn`` is the FULL
    HAROLD-issued WPN of the created revision, verbatim."""
    config_id: int
    config_wpn: str
    wpn: str
    rev_letter: str
    name: str
    rollup: Dict[str, Any]
    validation: Dict[str, Any] = Field(default_factory=dict)
    is_new_config: bool


# ── Bundle export (§9) ──────────────────────────────────────────────


class BundleExportSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    config_wpn: str
    rev_letter: str
    bundle_hash: str
    bundle_dirname: str
    artifact_count: int
    created_utc: Optional[datetime] = None


class BundleExportResponse(BundleExportSummary):
    manifest: Dict[str, Any]
    reused: bool = False
    warnings: List[str] = Field(default_factory=list)
