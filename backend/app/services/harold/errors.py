"""HAROLD V2 client exception types.

Carry-over from the prior HAROLD-001 effort; the two new types added
in Phase 2 of HAROLD-INT-002 are ``HaroldDuplicateError`` (HTTP 409
from ``issue-specific``) and ``HaroldValidationError`` (HTTP 422 or a
``is_valid_format=false`` body from ``validate``).

All inherit from ``HaroldUnavailableError``? NO — only the
network/transport failures inherit from that. Domain failures
(duplicate / validation) are distinct so the router can map them to
the right HTTP status code without swallowing them into the
"HAROLD is down" structured-unavailable response.
"""
from __future__ import annotations


class HaroldError(Exception):
    """Base class for every HAROLD client failure. Routers catch
    subclasses individually; never catch this directly."""


class HaroldUnavailableError(HaroldError):
    """HAROLD is unreachable (network error, timeout, 5xx response).
    Routers translate to ``{harold_available: false, reason: ...}``
    via the discriminated-union schema — HTTP 200 with structured
    payload, NOT 503, so the frontend doesn't have to parse status
    codes."""


class HaroldInvalidResponseError(HaroldError):
    """HAROLD responded but the payload doesn't match the expected
    shape (malformed JSON, missing required field, etc.). Usually a
    real bug; routers can let this propagate to 500 because the
    application can't recover from a contract violation."""


class HaroldDuplicateError(HaroldError):
    """HAROLD's ``POST /api/v1/wpn/issue-specific`` returned 409 —
    the caller-supplied WPN is already in the ledger. Phase 3 router
    maps this to HTTP 409 with a user-facing message."""


class HaroldValidationError(HaroldError):
    """HAROLD's ``POST /api/v1/wpn/validate`` returned 422, or the
    body says ``is_valid_format=false``. Caller's WPN is malformed;
    router maps to HTTP 422."""
