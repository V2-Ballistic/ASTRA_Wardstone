"""
ASTRA — Multi-Factor Authentication Service
=============================================
File: backend/app/services/mfa.py

TOTP-based MFA using pyotp.  Secrets are stored Fernet-encrypted
in the MFAConfig table.
"""

import os
import base64
from io import BytesIO
from datetime import datetime

import pyotp
from cryptography.fernet import Fernet
from sqlalchemy.orm import Session

from app.models.auth_models import MFAConfig

# ── Encryption key — derived from SECRET_KEY (must be 32 url-safe base64 bytes)
_raw_key = os.getenv("SECRET_KEY", "test-secret-key-not-for-production")
_fernet_key = base64.urlsafe_b64encode(_raw_key.encode()[:32].ljust(32, b"\0"))
_fernet = Fernet(_fernet_key)


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
