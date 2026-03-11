"""
ASTRA — Electronic Signature Service
======================================
File: backend/app/services/signature_service.py   ← NEW

Provides password-verified, SHA-256-sealed electronic signatures
that satisfy 21 CFR Part 11 and NIST 800-53 AU-10 (Non-repudiation).

The signer must re-enter their password to sign.  The resulting
ElectronicSignature record contains a hash that seals the signer's
identity, the entity, the meaning, and the timestamp together.
"""

from datetime import datetime
from sqlalchemy.orm import Session

from app.models import User
from app.models.workflow import ElectronicSignature, SignatureMeaning
from app.services.auth import verify_password

# Optional audit hook
try:
    from app.services.audit_service import record_event as _audit
except ImportError:
    def _audit(*a, **kw):
        pass


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
    the password check fails.
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        return None

    # ── Non-repudiation: re-verify password ──
    if not verify_password(password, user.hashed_password):
        return None

    now = datetime.utcnow()
    ts_iso = now.isoformat()

    sig_hash = ElectronicSignature.compute_hash(
        user_id, entity_type, entity_id, meaning, ts_iso,
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
    )
    db.add(sig)
    db.commit()
    db.refresh(sig)

    # Audit trail
    try:
        _audit(
            db, "signature.created", entity_type, entity_id, user_id,
            {"meaning": meaning, "signature_id": sig.id},
        )
    except Exception:
        pass

    return sig


def verify_signature(db: Session, signature_id: int) -> dict:
    """
    Verify that a stored signature's hash is still intact.
    Returns {"valid": bool, "detail": str}.
    """
    sig = db.query(ElectronicSignature).filter(
        ElectronicSignature.id == signature_id
    ).first()
    if not sig:
        return {"valid": False, "detail": "Signature not found"}

    recomputed = ElectronicSignature.compute_hash(
        sig.user_id,
        sig.entity_type,
        sig.entity_id,
        sig.signature_meaning.value if hasattr(sig.signature_meaning, "value") else str(sig.signature_meaning),
        sig.timestamp.isoformat(),
    )
    if recomputed != sig.signature_hash:
        return {
            "valid": False,
            "detail": "Hash mismatch — signature record may have been tampered with",
        }
    return {"valid": True, "detail": "Signature integrity verified"}


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
        })
    return results
