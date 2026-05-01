"""ASTRA — Pin Direction Compatibility Matrix (INTF-002 Phase 4)
=================================================================
File: backend/app/services/interface/direction_matrix.py

Single source of truth for the 6×6 ``SignalDirection`` compatibility check
referenced by spec §11.3 and digest §6 (anomaly #9 — the spec's dict literal
is malformed; the digest's matrix table is canonical).

Implementation choice: every cell of the matrix is enumerated explicitly so
that the test suite can assert the full table without re-deriving anything.
The function returns a (compatible, reason) pair so the auto-wire engine can
forward the explanation to the UI tooltip without re-computing it.

Matrix (src on row, tgt on col):

    | src \\ tgt    | INPUT | OUTPUT | BIDIR | POWER | GROUND | UNKNOWN |
    |---------------|-------|--------|-------|-------|--------|---------|
    | INPUT         |   F   |   T    |   T   |   F   |   F    |   T(W)  |
    | OUTPUT        |   T   |   F    |   T   |   F   |   F    |   T(W)  |
    | BIDIRECTIONAL |   T   |   T    |   T   |   F   |   F    |   T(W)  |
    | POWER         |   F   |   F    |   F   |   T   |   F    |   T(W)  |
    | GROUND        |   F   |   F    |   F   |   F   |   T    |   T(W)  |
    | UNKNOWN       | T(W)  | T(W)   | T(W)  | T(W)  | T(W)   |   T(W)  |

Notes:
  * INPUT↔INPUT and OUTPUT↔OUTPUT are rejected (no driver / bus contention).
  * POWER↔GROUND is rejected (different rail polarity).
  * POWER↔INPUT/OUTPUT is rejected (mixing power with signal).
  * UNKNOWN is permissive on both sides but the caller should flag a warning.
"""

from __future__ import annotations

from typing import Optional

from app.models.catalog import SignalDirection


# ──────────────────────────────────────────────────────────────
# Verbatim cell lookup. True = compatible, False = conflict.
# Constructed as a frozenset of compatible pairs (anything not in
# the set is incompatible). UNKNOWN is handled separately so the
# caller can route the "warning" status without losing the True.
# ──────────────────────────────────────────────────────────────
_COMPATIBLE: frozenset[tuple[SignalDirection, SignalDirection]] = frozenset({
    # Signal pairs (driver ↔ listener combinations)
    (SignalDirection.INPUT,         SignalDirection.OUTPUT),
    (SignalDirection.OUTPUT,        SignalDirection.INPUT),
    (SignalDirection.INPUT,         SignalDirection.BIDIRECTIONAL),
    (SignalDirection.BIDIRECTIONAL, SignalDirection.INPUT),
    (SignalDirection.OUTPUT,        SignalDirection.BIDIRECTIONAL),
    (SignalDirection.BIDIRECTIONAL, SignalDirection.OUTPUT),
    (SignalDirection.BIDIRECTIONAL, SignalDirection.BIDIRECTIONAL),
    # Power-rail pairs (only same-class)
    (SignalDirection.POWER,         SignalDirection.POWER),
    (SignalDirection.GROUND,        SignalDirection.GROUND),
})


# ══════════════════════════════════════════════════════════════
#  Public API
# ══════════════════════════════════════════════════════════════

def is_direction_compatible(
    src: SignalDirection,
    tgt: SignalDirection,
) -> tuple[bool, Optional[str]]:
    """Per the 6×6 matrix above.

    Returns ``(True,  None)``       — explicitly compatible pair (no warning).
    Returns ``(True,  reason)``     — UNKNOWN-permissive pair (warning).
    Returns ``(False, reason)``     — explicit conflict, reason explains why.
    """
    # ── UNKNOWN is permissive on either side, but emit a warning ──
    if src == SignalDirection.UNKNOWN or tgt == SignalDirection.UNKNOWN:
        return True, (
            f"One or both sides have UNKNOWN direction "
            f"(src={src.value}, tgt={tgt.value}); review before wiring."
        )

    # ── Direct table lookup ──
    if (src, tgt) in _COMPATIBLE:
        return True, None

    # ── Build a precise rejection reason for the UI ──
    return False, _explain_conflict(src, tgt)


def _explain_conflict(src: SignalDirection, tgt: SignalDirection) -> str:
    """Plain-language explanation for an incompatible pair."""
    if src == tgt == SignalDirection.INPUT:
        return (
            "Both pins are INPUTs — no driver on either side. "
            "Connecting two listeners produces no signal."
        )
    if src == tgt == SignalDirection.OUTPUT:
        return (
            "Both pins are OUTPUTs — bus contention. "
            "Two drivers on the same wire fight for control."
        )
    if {src, tgt} == {SignalDirection.POWER, SignalDirection.GROUND}:
        return (
            "Connecting POWER to GROUND would short the rail. "
            "Use a power-to-power or ground-to-ground pairing."
        )
    if SignalDirection.POWER in (src, tgt):
        other = tgt if src == SignalDirection.POWER else src
        return (
            f"POWER pins must connect to other POWER pins; "
            f"connecting POWER to {other.value} mixes power and signal."
        )
    if SignalDirection.GROUND in (src, tgt):
        other = tgt if src == SignalDirection.GROUND else src
        return (
            f"GROUND pins must connect to other GROUND pins; "
            f"connecting GROUND to {other.value} mixes return and signal."
        )
    # Generic fallback (should not be reachable given the cases above).
    return (
        f"Source pin direction {src.value.upper()} cannot connect to "
        f"target pin direction {tgt.value.upper()}."
    )


def directions_compatible(
    src: SignalDirection, tgt: SignalDirection
) -> bool:
    """Convenience wrapper that drops the reason and returns just the bool.

    Mirrors the helper signature used in the spec algorithm pseudocode
    (§11.3) for callers that don't need the explanation string.
    """
    compat, _ = is_direction_compatible(src, tgt)
    return compat
