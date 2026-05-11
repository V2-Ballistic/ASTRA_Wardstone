"""HAROLD integration errors.

Distinguish unavailability (HAROLD off, unreachable, or feature flag
disabled) from invalid-response (HAROLD replied but the body didn't
match what we asked for). The router maps both onto a structured
`{harold_available: false, reason: …}` response.
"""


class HaroldUnavailableError(RuntimeError):
    """HAROLD is not reachable or the integration flag is off."""


class HaroldInvalidResponseError(RuntimeError):
    """HAROLD responded but the payload is malformed."""
