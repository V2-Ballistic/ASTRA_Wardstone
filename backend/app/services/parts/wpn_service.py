"""
ASTRA — Wardstone Part Number (WPN) assignment service.

Format: WS-{TYPECODE}-{seq:06d}-{rev:02d}
Examples:
    WS-FAST-000001-00     ← first fastener, revision 00
    WS-FAST-000042-03     ← 42nd fastener, fourth revision
    WS-WASH-000001-00     ← first washer, revision 00

assign_wpn() must be called inside a transaction. It does
``SELECT ... FOR UPDATE`` on the relevant ``wpn_sequences`` row,
increments ``next_val``, and returns the formatted WPN. Two concurrent
callers cannot get the same WPN — F-203 lesson applied.

bump_revision() is pure-string logic — increments the trailing RR
suffix. Used when an APPROVED LibraryPart is re-revisioned via PATCH.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.parts_library import PartType, WPNSequence


# ── PartType → 4-char WPN code map (every member must be present) ──
WPN_TYPE_CODES: dict[PartType, str] = {
    PartType.FASTENER:          "FAST",
    PartType.WASHER:            "WASH",
    PartType.INSERT:            "INSR",
    PartType.BRACKET:           "BRKT",
    PartType.ENCLOSURE:         "ENCL",
    PartType.SEAL:              "SEAL",
    PartType.BEARING:           "BEAR",
    PartType.HINGE_LATCH:       "HNGL",
    PartType.THERMAL_INTERFACE: "THIF",
    PartType.PCB_MECHANICAL:    "PCBM",
    PartType.CUSTOM:            "CUST",
}


def assign_wpn(db: Session, part_type: PartType) -> str:
    """
    Atomically assign the next WPN for ``part_type``. Caller must commit
    the transaction; if the caller rolls back, the sequence row's
    increment also rolls back — no IDs are leaked.

    Raises:
        KeyError: if ``part_type`` has no entry in WPN_TYPE_CODES.
    """
    code = WPN_TYPE_CODES[part_type]
    seq = (
        db.query(WPNSequence)
        .filter(WPNSequence.part_type_code == code)
        .with_for_update()
        .first()
    )
    if seq is None:
        # Defensive: row should be seeded by migration 0027. If it isn't
        # (e.g. SQLite test env where the migration didn't run), create.
        seq = WPNSequence(part_type_code=code, next_val=1)
        db.add(seq)
        db.flush()

    n = seq.next_val
    seq.next_val = n + 1
    db.flush()
    return f"WS-{code}-{n:06d}-00"


def bump_revision(wpn: str) -> str:
    """Increment the trailing RR suffix. Pure string logic.

    >>> bump_revision("WS-FAST-000042-00")
    'WS-FAST-000042-01'
    >>> bump_revision("WS-BRKT-000001-09")
    'WS-BRKT-000001-10'
    """
    base, rev = wpn.rsplit("-", 1)
    new_rev = int(rev) + 1
    return f"{base}-{new_rev:02d}"
