"""
ASTRA — Multi-Factor Authentication Service
=============================================
File: backend/app/services/mfa.py

TOTP-based MFA using pyotp.  Secrets are stored Fernet-encrypted
in the MFAConfig table.

Key derivation aligned with ``services.encryption`` (PBKDF2-SHA256,
480k iterations) — covers AUDIT_FINDINGS F-003. The raw key material
comes from ``ENCRYPTION_KEY`` (preferred) or ``SECRET_KEY`` (fallback),
salted distinctly with ``b"astra-mfa-v1"`` so MFA-secret encryption
keys are independent of field-encryption keys derived from the same
input.
"""

import base64
import os
from io import BytesIO
from datetime import datetime

import pyotp
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.models.auth_models import MFAConfig
from app.services.encryption import derive_key, _resolve_raw_key

# ── Encryption key — PBKDF2 of ENCRYPTION_KEY or SECRET_KEY,
#   salted distinctly so MFA Fernet key ≠ field-encryption Fernet key.
_MFA_SALT = b"astra-mfa-v1"
_fernet = Fernet(derive_key(_resolve_raw_key(), salt=_MFA_SALT))


def _encrypt(plaintext: str) -> str:
    return _fernet.encrypt(plaintext.encode()).decode()


def _decrypt(ciphertext: str) -> str:
    return _fernet.decrypt(ciphertext.encode()).decode()


# ── Public API ──────────────────────────────────────────────


def generate_mfa_secret(db: Session, user_id: int) -> dict:
    """
    Create a TOTP secret for the user and return
    ``{"secret": ..., "qr_uri": ..., "provisioning_uri": ...}``.
    Does NOT enable MFA yet — call ``enable_mfa`` after the user
    confirms a valid token.
    """
    secret = pyotp.random_base32()

    # Upsert
    cfg = db.query(MFAConfig).filter(MFAConfig.user_id == user_id).first()
    if cfg:
        cfg.secret_encrypted = _encrypt(secret)
        cfg.is_enabled = False
    else:
        cfg = MFAConfig(
            user_id=user_id,
            secret_encrypted=_encrypt(secret),
            is_enabled=False,
        )
        db.add(cfg)
    db.commit()

    provisioning_uri = pyotp.TOTP(secret).provisioning_uri(
        name=f"user:{user_id}",
        issuer_name="ASTRA",
    )

    # Generate QR data URI (optional — uses qrcode lib if available)
    qr_data_uri = ""
    try:
        import qrcode  # type: ignore
        img = qrcode.make(provisioning_uri)
        buf = BytesIO()
        img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode()
        qr_data_uri = f"data:image/png;base64,{b64}"
    except ImportError:
        pass  # QR code generation optional

    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri,
        "qr_data_uri": qr_data_uri,
    }


def verify_mfa_token(db: Session, user_id: int, token: str) -> bool:
    """Validate a 6-digit TOTP token. Returns True if valid."""
    cfg = db.query(MFAConfig).filter(MFAConfig.user_id == user_id).first()
    if not cfg:
        return False

    secret = _decrypt(cfg.secret_encrypted)
    totp = pyotp.TOTP(secret)
    valid = totp.verify(token, valid_window=1)

    if valid:
        cfg.last_used_at = datetime.utcnow()
        db.commit()

    return valid


def enable_mfa(db: Session, user_id: int, token: str) -> bool:
    """
    Enable MFA after the user proves they can produce a valid token.
    Returns True on success, False if the token is wrong.
    """
    if not verify_mfa_token(db, user_id, token):
        return False

    cfg = db.query(MFAConfig).filter(MFAConfig.user_id == user_id).first()
    if cfg:
        cfg.is_enabled = True
        db.commit()
    return True


def disable_mfa(db: Session, user_id: int) -> bool:
    """Disable MFA for a user (admin approval should be checked by caller)."""
    cfg = db.query(MFAConfig).filter(MFAConfig.user_id == user_id).first()
    if not cfg:
        return False
    cfg.is_enabled = False
    db.commit()
    return True


def is_mfa_enabled(db: Session, user_id: int) -> bool:
    cfg = db.query(MFAConfig).filter(MFAConfig.user_id == user_id).first()
    return bool(cfg and cfg.is_enabled)
