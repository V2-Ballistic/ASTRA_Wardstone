"""
ASTRA — Electronic Signature Service
======================================
File: backend/app/services/signature_service.py

Provides password-verified, SHA-256-sealed electronic signatures
that satisfy 21 CFR Part 11 and NIST 800-53 AU-10 (Non-repudiation).

The signer must re-enter their password to sign.  The resulting
ElectronicSignature record contains a hash that seals the signer's
identity, the entity, the meaning, the timestamp, AND the entity's
content at sign time (AUDIT_FINDINGS F-008 — 21 CFR Part 11 §11.70
record-binding).  A subsequent edit of the signed entity invalidates
the signature on verify.
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict

from sqlalchemy.orm import Session

from app.models import User
from app.models.workflow import ElectronicSignature, SignatureMeaning
from app.services.auth import verify_password
from app.services.security.record_hash import compute_record_hash

# Optional audit hook
try:
    from app.services.audit_service import record_event as _audit
except ImportError:
    def _audit(*a, **kw):
        pass

logger = logging.getLogger("astra.signature")


# ══════════════════════════════════════
#  Entity loaders (F-008)
# ══════════════════════════════════════
#
# Entity-type → callable that loads the row by primary key. Required
# for record-hash binding: we need the actual row to feed into
# `compute_record_hash`. New entity_types must register here AND in
# `services.security.record_hash` (a hasher).

def _load_requirement(db: Session, entity_id: int):
    from app.models import Requirement
    return db.query(Requirement).filter(Requirement.id == entity_id).first()


def _load_baseline(db: Session, entity_id: int):
    from app.models import Baseline
    return db.query(Baseline).filter(Baseline.id == entity_id).first()


_ENTITY_LOADERS: Dict[str, Callable[[Session, int], Any]] = {
    "requirement": _load_requirement,
    "baseline": _load_baseline,
}


def _load_entity(db: Session, entity_type: str, entity_id: int):
    """Return the ORM row for (entity_type, entity_id), or None."""
    loader = _ENTITY_LOADERS.get(entity_type)
    if loader is None:
        return None
    return loader(db, entity_id)


# ══════════════════════════════════════
#  Sign
# ══════════════════════════════════════


def request_signature(
    db: Session,
    user_id: int,
    entity_type: str,
    entity_id: int,
    meaning: str,
    password: str,
    statement: str = "I have reviewed and approve this change.",
    ip_address: str = "",
    user_agent: str = "",
) -> ElectronicSignature | None:
    """
    Create a password-verified electronic signature.

    Returns the ElectronicSignature record on success, or None if
    the password check fails OR the entity cannot be located OR no
    record-hasher is registered for the entity_type. The latter two
    are F-008 hard requirements: signing without a content hash would
    leave the signature unbound and indistinguishable from a tampered
    record on verify.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None

    # ── Non-repudiation: re-verify password ──
    if not verify_password(password, user.hashed_password):
        return None

    # ── F-008: bind to record state ──
    entity = _load_entity(db, entity_type, entity_id)
    if entity is None:
        logger.warning(
            "request_signature: entity %s:%s not found — refusing to sign",
            entity_type, entity_id,
        )
        return None
    try:
        rec_hash = compute_record_hash(entity_type, entity)
    except ValueError as exc:
        logger.warning(
            "request_signature: no record-hasher for entity_type=%r — refusing to sign (%s)",
            entity_type, exc,
        )
        return None

    now = datetime.utcnow()
    ts_iso = now.isoformat()

    sig_hash = ElectronicSignature.compute_hash(
        user_id, entity_type, entity_id, meaning, ts_iso, rec_hash,
    )

    sig = ElectronicSignature(
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        signature_meaning=meaning,
        statement=statement,
        password_verified=True,
        ip_address=ip_address,
        user_agent=user_agent,
        timestamp=now,
        signature_hash=sig_hash,
        record_hash=rec_hash,
    )
    db.add(sig)
    db.commit()
    db.refresh(sig)

    # Audit trail
    try:
        _audit(
            db, "signature.created", entity_type, entity_id, user_id,
            {"meaning": meaning, "signature_id": sig.id, "record_hash": rec_hash},
        )
    except Exception:
        pass

    return sig


# ══════════════════════════════════════
#  Verify
# ══════════════════════════════════════


def verify_signature(db: Session, signature_id: int) -> dict:
    """
    Verify that a stored signature's hash is still intact AND that the
    signed entity's current content still matches the record_hash that
    was sealed at sign time.

    Returns ``{"valid": bool, "detail": str, "reason"?: str}``.
    Failure reasons (in `reason`):
      - "signature_not_found"
      - "hash_mismatch"        — signature row was tampered with
      - "record_mismatch"      — signed entity has been edited since signing
      - "entity_missing"       — signed entity has been deleted
      - "no_hasher"            — record_hasher missing for this entity_type
    """
    sig = db.query(ElectronicSignature).filter(
        ElectronicSignature.id == signature_id,
    ).first()
    if not sig:
        return {
            "valid": False,
            "reason": "signature_not_found",
            "detail": "Signature not found",
        }

    meaning_value = (
        sig.signature_meaning.value
        if hasattr(sig.signature_meaning, "value")
        else str(sig.signature_meaning)
    )

    # ── 1. Recompute the signature row hash ──
    recomputed = ElectronicSignature.compute_hash(
        sig.user_id,
        sig.entity_type,
        sig.entity_id,
        meaning_value,
        sig.timestamp.isoformat(),
        sig.record_hash or "",
    )
    if recomputed != sig.signature_hash:
        return {
            "valid": False,
            "reason": "hash_mismatch",
            "detail": "Hash mismatch — signature row may have been tampered with",
        }

    # ── 2. F-008: verify the signed entity hasn't been edited ──
    entity = _load_entity(db, sig.entity_type, sig.entity_id)
    if entity is None:
        return {
            "valid": False,
            "reason": "entity_missing",
            "detail": (
                f"Signed {sig.entity_type} #{sig.entity_id} no longer exists; "
                "signature cannot be verified against a missing record."
            ),
        }
    try:
        current_hash = compute_record_hash(sig.entity_type, entity)
    except ValueError:
        return {
            "valid": False,
            "reason": "no_hasher",
            "detail": (
                f"No record-hasher registered for entity_type={sig.entity_type!r}; "
                "cannot verify record binding."
            ),
        }

    if (sig.record_hash or "") != current_hash:
        return {
            "valid": False,
            "reason": "record_mismatch",
            "detail": (
                f"Signed {sig.entity_type} #{sig.entity_id} has been modified "
                "since the signature was created. The signature does not bind "
                "to the current record state (21 CFR Part 11 §11.70)."
            ),
        }

    return {
        "valid": True,
        "detail": "Signature integrity verified (record binding intact)",
    }


def get_signatures(
    db: Session, entity_type: str, entity_id: int,
) -> list[dict]:
    """List all electronic signatures for an entity."""
    sigs = (
        db.query(ElectronicSignature)
        .filter(
            ElectronicSignature.entity_type == entity_type,
            ElectronicSignature.entity_id == entity_id,
        )
        .order_by(ElectronicSignature.timestamp.asc())
        .all()
    )
    results = []
    for s in sigs:
        user = db.query(User).filter(User.id == s.user_id).first()
        results.append({
            "id": s.id,
            "user_id": s.user_id,
            "user_full_name": user.full_name if user else "Unknown",
            "user_role": user.role.value if user and hasattr(user.role, "value") else str(user.role) if user else None,
            "meaning": s.signature_meaning.value if hasattr(s.signature_meaning, "value") else str(s.signature_meaning),
            "statement": s.statement,
            "password_verified": s.password_verified,
            "timestamp": s.timestamp.isoformat() if s.timestamp else None,
            "signature_hash": s.signature_hash[:16] + "…",
            "record_hash": (s.record_hash or "")[:16] + "…" if s.record_hash else None,
        })
    return results
