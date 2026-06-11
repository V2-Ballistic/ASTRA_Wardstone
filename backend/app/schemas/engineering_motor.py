"""
ASTRA — Engineering Motors schemas (pydantic v2)
================================================
File: backend/app/schemas/engineering_motor.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §5)

Request/response models for the Motors engineering domain, plus the
``MotorDesignInputs`` schema consumed by the §5.3 internal-ballistics
solver (``app/services/engineering/motor_ballistics.py``).

All physical quantities are SI unless the field name says otherwise.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


# ══════════════════════════════════════════════════════════════
#  §5.3 — Parametric design inputs (solver schema)
# ══════════════════════════════════════════════════════════════

class PropellantInputs(BaseModel):
    """Saint-Robert propellant: r = a · Pc^n (SI: a in m/s·Pa⁻ⁿ)."""

    density_kgpm3: float = Field(..., gt=0, description="ρp, kg/m³")
    a: float = Field(..., gt=0, description="burn-rate coefficient, m/(s·Paⁿ)")
    n: float = Field(..., gt=0, lt=1, description="burn-rate exponent (0<n<1)")
    k: float = Field(..., gt=1, description="ratio of specific heats γ")
    Tc_K: Optional[float] = Field(None, gt=0, description="combustion temperature, K")
    cstar_mps: Optional[float] = Field(None, gt=0, description="characteristic velocity c*, m/s")
    sigma_p: float = Field(
        0.0,
        description="temperature sensitivity σp, 1/K (a(T) = a·exp(σp·(T−294.15)))",
    )
    molar_mass_kgpmol: Optional[float] = Field(
        None, gt=0,
        description="exhaust molar mass M, kg/mol — used with Tc_K when cstar absent",
    )

    @model_validator(mode="after")
    def _cstar_resolvable(self) -> "PropellantInputs":
        if self.cstar_mps is None and (self.Tc_K is None or self.molar_mass_kgpmol is None):
            raise ValueError(
                "propellant requires cstar_mps OR (Tc_K AND molar_mass_kgpmol) "
                "so c* = sqrt(R_u/M·Tc)/Γ can be evaluated"
            )
        return self


class GrainInputs(BaseModel):
    """BATES grain stack. Multi-segment is first-class (WS01 = 8)."""

    type: str = Field("BATES", description="'BATES' (finocyl/endburner declared future)")
    od_m: float = Field(..., gt=0, description="grain outer diameter, m")
    core_d_m: float = Field(..., gt=0, description="core (port) diameter, m")
    length_m: float = Field(..., gt=0, description="single-segment length, m")
    segment_count: int = Field(1, ge=1, description="number of identical segments")
    inhibited_ends: int = Field(
        0, ge=0, le=2,
        description="inhibited ends per segment (0|1|2); exposed faces = 2 − inhibited",
    )

    @model_validator(mode="after")
    def _geometry_sane(self) -> "GrainInputs":
        if self.core_d_m >= self.od_m:
            raise ValueError("core_d_m must be < od_m")
        return self


class NozzleInputs(BaseModel):
    throat_d_m: float = Field(..., gt=0, description="throat diameter, m")
    exit_d_m: Optional[float] = Field(None, gt=0, description="exit diameter, m")
    expansion_ratio: Optional[float] = Field(None, gt=1, description="ε = Ae/At")
    ambient_pressure_pa: float = Field(101325.0, ge=0, description="Pa, ambient reference")

    @model_validator(mode="after")
    def _exit_resolvable(self) -> "NozzleInputs":
        if self.exit_d_m is None and self.expansion_ratio is None:
            raise ValueError("nozzle requires exit_d_m OR expansion_ratio")
        return self


class SimInputs(BaseModel):
    web_step_m: float = Field(1e-4, gt=0, description="web-march step, m")
    grain_temp_K: float = Field(294.15, gt=0, description="nominal grain soak temperature, K")


class MotorDesignInputs(BaseModel):
    """Complete input set for the §5.3 equilibrium internal-ballistics
    solver. Serialized verbatim into ``motor_revisions.design_inputs``."""

    model_config = ConfigDict(extra="forbid")

    propellant: PropellantInputs
    grain: GrainInputs
    nozzle: NozzleInputs
    sim: SimInputs = Field(default_factory=SimInputs)


# ══════════════════════════════════════════════════════════════
#  Create / mutate request bodies
# ══════════════════════════════════════════════════════════════

class MotorDesignCreate(BaseModel):
    """Body for POST /engineering/motors:design — a NEW designed motor."""

    name: str = Field(..., min_length=1, max_length=255,
                      description="display name passed to HAROLD (HAROLD owns the WPN)")
    inputs: MotorDesignInputs
    notes: Optional[str] = None


class MotorDesignRevisionCreate(BaseModel):
    """Body for POST /engineering/motors/{wpn}/revisions:from-design."""

    inputs: MotorDesignInputs
    notes: Optional[str] = None


class ActiveRevisionUpdate(BaseModel):
    """Body for PUT /engineering/motors/{wpn}/active-revision."""

    rev_letter: str = Field(..., min_length=1, max_length=4)


# ══════════════════════════════════════════════════════════════
#  Responses
# ══════════════════════════════════════════════════════════════

class MotorRevisionSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wpn: str
    rev_letter: str
    origin: str
    total_impulse_ns: Optional[float] = None
    peak_thrust_n: Optional[float] = None
    burn_time_s: Optional[float] = None
    isp_s: Optional[float] = None
    quality_tier: str
    artifact_sha256: str
    created_utc: Optional[datetime] = None
    notes: Optional[str] = None


class MotorRevisionDetail(MotorRevisionSummary):
    design_inputs: Optional[Dict[str, Any]] = None
    source_csv_filename: Optional[str] = None
    source_csv_sha256: Optional[str] = None
    defaulted_fields: Optional[List[str]] = None
    warnings: Optional[List[str]] = None


class MotorListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wpn: str
    name: str
    motor_class: Optional[str] = None
    total_impulse_ns: Optional[float] = None
    quality_tier: Optional[str] = None
    current_rev_letter: Optional[str] = None
    updated_at: Optional[datetime] = None


class MotorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    wpn: str
    base_index: int
    system_code: str
    name: str
    motor_class: Optional[str] = None
    active_revision_id: Optional[int] = None
    catalog_part_id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    revisions: List[MotorRevisionSummary] = Field(default_factory=list)


class MotorSummarySheet(BaseModel):
    """GET /engineering/motors/{wpn}/summary — class/impulse spec sheet."""

    wpn: str
    name: str
    motor_class: Optional[str] = None
    rev_letter: Optional[str] = None
    origin: Optional[str] = None
    quality_tier: Optional[str] = None
    total_impulse_ns: Optional[float] = None
    peak_thrust_n: Optional[float] = None
    burn_time_s: Optional[float] = None
    isp_s: Optional[float] = None
    prop_mass_init_kg: Optional[float] = None
    revision_count: int = 0


class MotorIngestResponse(BaseModel):
    """POST :ingestCsv / :from-csv result — motor + WPN + tier + warnings."""

    motor: MotorResponse
    wpn: str
    rev_letter: str
    quality_tier: str
    recommended_fidelity: str
    warnings: List[str] = Field(default_factory=list)
    defaulted_fields: List[str] = Field(default_factory=list)
    precheck: Optional[Dict[str, Any]] = Field(
        None, description="HAROLD filename-precheck verdict, verbatim",
    )


class DesignPreviewResponse(BaseModel):
    """POST :previewDesign — solver output, nothing persisted/named."""

    time_s: List[float]
    thrust_n: List[float]
    pchamber_pa: List[float]
    mdot_kgps: List[float]
    prop_mass_rem_kg: List[float]
    total_impulse_ns: float
    peak_thrust_n: float
    burn_time_s: float
    isp_s: float
    prop_mass_init_kg: float
    motor_class: str
    max_pchamber_pa: float
    warnings: List[str] = Field(default_factory=list)
