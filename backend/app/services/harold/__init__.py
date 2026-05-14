"""ASTRA — HAROLD V2 integration service package.

Phase 2 of TDD-HAROLD-INT-002 (Path A: delete + rebuild fresh).
Replaces the prior speculative HAROLD-001 surface entirely. The
public exports below are what Phase 3's router and Phase 3's
catalog upload/approval hooks consume — anything not re-exported
here is an implementation detail.
"""
from __future__ import annotations

from . import client, fallback
from .class_to_system import (
    DEFAULT_SYSTEM_CODE,
    PART_CLASS_TO_SYSTEM_CODE,
    SYSTEM_CODE_LABELS,
    map_class_to_system,
)
from .errors import (
    HaroldDuplicateError,
    HaroldError,
    HaroldInvalidResponseError,
    HaroldUnavailableError,
    HaroldValidationError,
)
from .filename_validator import (
    FilenameValidationResult,
    extract_wpn_from_filename,
    looks_like_wardstone_wpn,
    validate_filename,
)
from .service import (
    heartbeat,
    is_enabled,
    issue_wpn_for_catalog_part,
    list_system_codes,
    reconcile_pending_sync,
    suggest_wpn_for_part,
    validate_filename_wpn,
    validate_wpn,
)

__all__ = [
    # Errors
    "HaroldError",
    "HaroldUnavailableError",
    "HaroldInvalidResponseError",
    "HaroldDuplicateError",
    "HaroldValidationError",
    # Class → system mapping
    "PART_CLASS_TO_SYSTEM_CODE",
    "DEFAULT_SYSTEM_CODE",
    "SYSTEM_CODE_LABELS",
    "map_class_to_system",
    # Filename validator
    "FilenameValidationResult",
    "validate_filename",
    "looks_like_wardstone_wpn",
    "extract_wpn_from_filename",
    # Service-layer entry points
    "is_enabled",
    "heartbeat",
    "list_system_codes",
    "suggest_wpn_for_part",
    "validate_wpn",
    "validate_filename_wpn",
    "issue_wpn_for_catalog_part",
    "reconcile_pending_sync",
    # Sub-modules (callers occasionally reach into client / fallback)
    "client",
    "fallback",
]
