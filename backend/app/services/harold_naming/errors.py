"""harold_naming error types.

Only one new type lives here — everything else re-uses the typed
exceptions from ``app.services.harold.errors`` so callers keep a
single exception taxonomy for all HAROLD failures.
"""
from __future__ import annotations

from app.services.harold.errors import HaroldError


class HaroldOrphanWpnError(HaroldError):
    """An allocated WPN could not be persisted locally AND the
    compensating ``release`` (DELETE /wpn/{wpn}) also failed. The WPN
    is now orphaned in HAROLD's ledger: it counts toward the gapless
    sequence but no ASTRA record references it.

    Spec §2.7: the ledger must never drift; ASTRA must never silently
    re-allocate. This error is raised (after a CRITICAL log naming the
    orphan WPN) so the failure is loud and operator-visible.
    """

    def __init__(self, message: str, *, wpn: str | None = None) -> None:
        super().__init__(message)
        self.wpn = wpn
