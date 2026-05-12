"""ASTRA — HAROLD V2 integration — Pydantic v2 schemas.

Phase 2 of TDD-HAROLD-INT-002. Mirrors HAROLD V2's REST shapes captured
in ``docs/HAROLD_V2_OPENAPI.json``. The discriminated-union pattern
(``harold_available: bool`` + either ``data`` or ``reason``) is carried
over from the prior speculative effort — it's the right shape for an
optional dependency where the frontend wants always-200 responses with
a structured payload, and never has to parse HTTP status codes.

Outbound (HAROLD ← ASTRA) shapes live here too:
  CatalogDesignatorsResponse — used by ``GET /api/v1/catalog/designators``
  CatalogDesignatorEntry      — per-row payload
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


# ────────────────────────────────────────────────────────────────────
#  Inbound: V2 response shapes (HAROLD → ASTRA)
# ────────────────────────────────────────────────────────────────────

# ── Heartbeat ───────────────────────────────────────────────────────


class HaroldHeartbeatResponse(BaseModel):
    """``GET /api/v1/harold/heartbeat`` — always 200.

    ``enabled`` reflects ``HAROLD_INTEGRATION_ENABLED``;
    ``reachable`` reflects whether V2's ``/health`` came back 200.
    The UI uses both to decide whether to render WPN affordances.
    """
    enabled:          bool
    reachable:        bool
    base_url:         str
    response_time_ms: Optional[int] = None
    version:          Optional[str] = None
    reason:           Optional[str] = None


# ── Generic discriminated-union envelope ────────────────────────────


class HaroldUnavailable(BaseModel):
    """Returned by every ``/api/v1/harold/*`` proxy when HAROLD is off
    or unreachable. Always HTTP 200; ``harold_available=False`` is the
    discriminator the frontend checks."""
    harold_available: bool = Field(default=False)
    reason:           str


# ── System codes ────────────────────────────────────────────────────


class HaroldSystemCode(BaseModel):
    code:        str
    category:    str   # "project-system" | "library-category"
    name:        str
    description: str


class SystemCodesPayload(BaseModel):
    codes: list[HaroldSystemCode]
    total: int


class SystemCodesAvailable(BaseModel):
    harold_available: bool = Field(default=True)
    data:             SystemCodesPayload


# ── Suggest WPN ─────────────────────────────────────────────────────


class WpnSuggestion(BaseModel):
    """V2's ``GET /api/v1/wpn/suggest`` response plus our annotation
    of where it came from (`source`)."""
    suggested_wpn:  str
    system_code:    str
    next_index:     int
    existing_count: int
    # Annotation added by ASTRA service layer — not a V2 field.
    source:         str = "harold"   # "harold" | "fallback"
    reason:         Optional[str] = None


class WpnSuggestionAvailable(BaseModel):
    harold_available: bool = Field(default=True)
    data:             WpnSuggestion


class HaroldSuggestRequest(BaseModel):
    """Body for ``POST /api/v1/harold/suggest``. Caller hands us a
    part_class; the service maps it to a system_code via the AD-6
    table, then calls V2's suggest endpoint."""
    part_class: str = Field(..., min_length=1, max_length=64)
    hint:       Optional[str] = Field(None, max_length=2000)


# ── Validate ────────────────────────────────────────────────────────


class WpnParsedFields(BaseModel):
    sys: str
    num: int
    rev: str


class WpnValidationResult(BaseModel):
    """V2's ``POST /api/v1/wpn/validate`` response, plus an optional
    ``ledger_entry`` hint so the UI can show the existing assignment
    when ``is_issued=True``."""
    wpn:             str
    is_valid_format: bool
    is_issued:       bool
    errors:          list[str] = Field(default_factory=list)
    warnings:        list[str] = Field(default_factory=list)
    parsed:          Optional[WpnParsedFields] = None
    # Populated when is_issued=True so the UI can deep-link.
    ledger_entry:    Optional[dict[str, Any]] = None


class WpnValidationAvailable(BaseModel):
    harold_available: bool = Field(default=True)
    data:             WpnValidationResult


class HaroldValidateRequest(BaseModel):
    wpn: str = Field(..., min_length=1, max_length=64)


# ── Validate filename ──────────────────────────────────────────────


class FilenameValidationResult(BaseModel):
    """The structured output of ``filename_validator.validate_filename``.
    Filetype-agnostic; STEP is just the first caller."""
    filename:            str
    base_name:           str
    extension:           str
    is_wardstone_format: bool
    extracted_wpn:       Optional[str] = None
    # Populated when extracted_wpn is set — the result of calling
    # V2's validate endpoint on it.
    wpn_validation:      Optional[WpnValidationResult] = None


class FilenameValidationAvailable(BaseModel):
    harold_available: bool = Field(default=True)
    data:             FilenameValidationResult


class HaroldValidateFilenameRequest(BaseModel):
    filename: str = Field(..., min_length=1, max_length=512)


# ── Ledger entry ────────────────────────────────────────────────────


class LedgerEntry(BaseModel):
    """Mirrors V2's WpnLedgerEntryResponse closely. Used by the
    reconcile path to compare HAROLD's record against ASTRA's row."""
    model_config = ConfigDict(extra="ignore")  # V2 may add fields later

    wpn:             str
    system_code:     str
    part_number_int: int
    revision:        str
    status:          str
    origin_system:   Optional[str] = None
    origin_record_id: Optional[str] = None
    display_name:    Optional[str] = None
    description:     Optional[str] = None
    issued_at:       Optional[datetime] = None
    retired_at:      Optional[datetime] = None
    superseded_by:   Optional[str] = None


# ── Reconcile ───────────────────────────────────────────────────────


class ReconcileResult(BaseModel):
    """Outcome of a manual ``Sync with HAROLD`` action on a part with
    ``wpn_pending_sync=True``."""
    reconciled:  bool
    wpn:         Optional[str] = None   # final WPN (may differ from fallback)
    via:         Optional[str] = None   # "issue_specific" | "issue" | "noop"
    reason:      Optional[str] = None


class ReconcileAvailable(BaseModel):
    harold_available: bool = Field(default=True)
    data:             ReconcileResult


# ────────────────────────────────────────────────────────────────────
#  Outbound: shape ASTRA exposes to HAROLD (and operators)
# ────────────────────────────────────────────────────────────────────


class CatalogDesignatorsResponse(BaseModel):
    """Legacy flat-list shape — preserved verbatim from the prior
    HAROLD-001 phase-3 commit so the existing endpoint serialises
    cleanly through Phase 2.

    Phase 3 replaces both the endpoint and this schema with the
    structured ``CatalogDesignatorsResponseV2`` form below (filtered
    on ``internal_part_number``, one row per WPN with `part_id` etc.).
    """
    designators:   list[str]
    total:         int
    system_filter: Optional[str] = None


class CatalogDesignatorEntry(BaseModel):
    """One structured row used by the Phase 3 form of
    ``GET /api/v1/catalog/designators``. Not wired yet; the legacy
    ``CatalogDesignatorsResponse`` is still in service in Phase 2."""
    wpn:         str
    part_id:     int
    part_class:  Optional[str] = None
    system_code: Optional[str] = None
    created_at:  Optional[datetime] = None


class CatalogDesignatorsResponseV2(BaseModel):
    """Phase 3 response shape. Replaces ``CatalogDesignatorsResponse``
    once the endpoint is switched to filter on
    ``catalog_parts.internal_part_number`` instead of
    ``catalog_parts.part_number`` (AD-9). No consumer was relying on
    the legacy flat-list shape — confirmed in Phase 0."""
    designators:   list[CatalogDesignatorEntry]
    total:         int
    system_filter: Optional[str] = None
