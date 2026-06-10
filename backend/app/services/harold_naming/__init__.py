"""ASTRA — strict HAROLD naming-authority service (engineering domains).

Spec §2: mandatory, sequential, gapless. This package is the ONLY
sanctioned path for the engineering domains (solid motors, aero
decks, vehicle configurations, …) to obtain WPNs. Unlike the catalog
integration in ``app.services.harold``, there is NO local fallback —
if HAROLD is unavailable, callers get ``HaroldUnavailableError`` and
surface 503.
"""
from __future__ import annotations

from app.services.harold.errors import (
    HaroldDuplicateError,
    HaroldError,
    HaroldInvalidResponseError,
    HaroldUnavailableError,
    HaroldValidationError,
)

from .errors import HaroldOrphanWpnError
from .service import (
    AER_CODE,
    CFG_CODE,
    MTR_CODE,
    SYSTEM_CODE_REGISTRY,
    allocate_and_persist,
    allocate_next,
    ensure_system_code,
    issue_revision,
    ledger_query,
    precheck_filename,
    record_use,
    release,
)

__all__ = [
    # Errors (re-exported harold taxonomy + the orphan error)
    "HaroldError",
    "HaroldUnavailableError",
    "HaroldInvalidResponseError",
    "HaroldDuplicateError",
    "HaroldValidationError",
    "HaroldOrphanWpnError",
    # Spec-mandated engineering system codes
    "MTR_CODE",
    "AER_CODE",
    "CFG_CODE",
    "SYSTEM_CODE_REGISTRY",
    # Service surface
    "ensure_system_code",
    "allocate_next",
    "precheck_filename",
    "issue_revision",
    "record_use",
    "release",
    "ledger_query",
    "allocate_and_persist",
]
