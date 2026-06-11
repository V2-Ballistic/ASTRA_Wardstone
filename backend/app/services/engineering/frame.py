"""
ASTRA — Frame ICD service helper
=================================
File: backend/app/services/engineering/frame.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §3)

Small, shared helper around the CITADEL Vehicle Body Frame ICD so other
modules (config tracker, bundle export) can stamp ``frame.icdId`` /
``frame.icdRev`` without duplicating registration logic.

Commit policy: ``ensure_frame`` / ``get_or_register_default_frame``
COMMIT on write (with rollback on failure) — they are idempotent
ensure-style entry points called from multiple contexts, not steps
inside a larger caller-owned transaction.
"""

from __future__ import annotations

from typing import Optional, Tuple

from sqlalchemy.orm import Session

from app.models.engineering_frame import (
    CITADEL_FRAME_KEY,
    FrameIcd,
    FrameIcdRevision,
)

# ── Spec §3 defaults ───────────────────────────────────────────────
#
# DEFAULT_DATUM is PARAMETERIZED — the stakeholder has not confirmed
# the datum point. Until confirmed, every registration defaults to
# "OML_nose_tip"; a confirmed change lands as a new immutable revision,
# never as an edit.

DEFAULT_NAME = "CITADEL Vehicle Body Frame"
DEFAULT_DATUM = "OML_nose_tip"
DEFAULT_AXES = "x_fwd_y_right_z_down"
DEFAULT_UNITS = "SI"
DEFAULT_RULES = (
    "All position vectors expressed in the CITADEL vehicle body frame (B) "
    "share ONE datum: the frame datum point (default OML_nose_tip; "
    "PARAMETERIZED — stakeholder unconfirmed). Specifically:\n"
    "  1. CADPORT mass-property referencePoint_m_B is measured from this "
    "datum.\n"
    "  2. Every component CG (cg_m_B) in a config bundle is measured from "
    "this datum.\n"
    "  3. Motor CG offsets are expressed relative to this same datum after "
    "placement — never relative to the motor's own local frame.\n"
    "  4. Aero deck refPoint_m_B is measured from this datum.\n"
    "No secondary datums. Axes are x forward (nose direction), y right, "
    "z down; units are SI (m, kg, kg*m^2)."
)


def get_current_revision(icd: FrameIcd) -> Optional[FrameIcdRevision]:
    """Highest-rev revision of *icd* (revisions are immutable; there is
    no mutable 'current' pointer to drift). None for a header with no
    revisions — which should never happen via this module."""
    if not icd.revisions:
        return None
    return max(icd.revisions, key=lambda r: r.rev)


def ensure_frame(
    db: Session,
    user_id: int,
    *,
    datum: Optional[str] = None,
    axes: Optional[str] = None,
    units: Optional[str] = None,
    rules: Optional[str] = None,
    notes: Optional[str] = None,
) -> Tuple[FrameIcd, FrameIcdRevision, bool, bool]:
    """Idempotent ensure/register of the canonical CITADEL frame ICD.

    - ICD absent  → create it with rev 1. Overrides (datum/axes/units/
      rules) fill in for the spec defaults.
    - ICD present → compare overrides against the CURRENT revision
      (None means "keep current value", NOT "reset to default"). Any
      difference creates a NEW immutable revision at current_rev + 1;
      no difference returns the existing current revision untouched.

    Returns ``(icd, current_revision, created_icd, created_revision)``.
    Commits on write; rolls back and re-raises on failure.
    """
    icd = db.query(FrameIcd).filter(FrameIcd.key == CITADEL_FRAME_KEY).first()

    try:
        if icd is None:
            icd = FrameIcd(
                key=CITADEL_FRAME_KEY,
                name=DEFAULT_NAME,
                created_by_id=user_id,
            )
            db.add(icd)
            db.flush()
            revision = FrameIcdRevision(
                frame_icd_id=icd.id,
                rev=1,
                datum=datum if datum is not None else DEFAULT_DATUM,
                axes=axes if axes is not None else DEFAULT_AXES,
                units=units if units is not None else DEFAULT_UNITS,
                rules=rules if rules is not None else DEFAULT_RULES,
                notes=notes,
                created_by_id=user_id,
            )
            db.add(revision)
            db.commit()
            db.refresh(icd)
            db.refresh(revision)
            return icd, revision, True, True

        current = get_current_revision(icd)
        if current is None:  # defensive: header without revisions
            revision = FrameIcdRevision(
                frame_icd_id=icd.id,
                rev=1,
                datum=datum if datum is not None else DEFAULT_DATUM,
                axes=axes if axes is not None else DEFAULT_AXES,
                units=units if units is not None else DEFAULT_UNITS,
                rules=rules if rules is not None else DEFAULT_RULES,
                notes=notes,
                created_by_id=user_id,
            )
            db.add(revision)
            db.commit()
            db.refresh(revision)
            return icd, revision, False, True

        new_datum = datum if datum is not None else current.datum
        new_axes = axes if axes is not None else current.axes
        new_units = units if units is not None else current.units
        new_rules = rules if rules is not None else current.rules

        changed = (
            new_datum != current.datum
            or new_axes != current.axes
            or new_units != current.units
            or new_rules != current.rules
        )
        if not changed:
            return icd, current, False, False

        revision = FrameIcdRevision(
            frame_icd_id=icd.id,
            rev=current.rev + 1,
            datum=new_datum,
            axes=new_axes,
            units=new_units,
            rules=new_rules,
            notes=notes,
            created_by_id=user_id,
        )
        db.add(revision)
        db.commit()
        db.refresh(revision)
        return icd, revision, False, True
    except Exception:
        db.rollback()
        raise


def get_or_register_default_frame(
    db: Session, user_id: int,
) -> Tuple[FrameIcd, FrameIcdRevision]:
    """The entry point other modules (config tracker / bundle export)
    call: returns the canonical CITADEL frame ICD + its current
    revision, registering rev 1 with spec defaults if absent."""
    icd, revision, _created_icd, _created_rev = ensure_frame(db, user_id)
    return icd, revision
