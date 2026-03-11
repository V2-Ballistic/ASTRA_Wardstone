"""
ASTRA — Field-Level Encryption Service
========================================
File: backend/app/services/encryption.py   ← NEW

Provides AES-128 symmetric encryption via Fernet for PII and sensitive
fields.  The encryption key is derived from ENCRYPTION_KEY using PBKDF2
so the raw env-var value doesn't need to be a precise length.

Also provides ``EncryptedString`` — a SQLAlchemy TypeDecorator that
transparently encrypts on INSERT/UPDATE and decrypts on SELECT.

NIST 800-53 controls:  SC-28 (Protection of Information at Rest)
"""

import base64
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy import String, TypeDecorator

# ══════════════════════════════════════
#  Key derivation
# ══════════════════════════════════════

_SALT = b"astra-field-encryption-v1"  # static salt — key uniqueness comes from ENCRYPTION_KEY


def _derive_key(raw_key: str) -> bytes:
    """Derive a 32-byte url-safe base64 Fernet key from an arbitrary string."""
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=_SALT,
        iterations=480_000,
    )
    return base64.urlsafe_b64encode(kdf.derive(raw_key.encode("utf-8")))


def _get_fernet() -> Fernet:
    raw = os.getenv("ENCRYPTION_KEY", "")
    if not raw:
        # Fallback for dev — deterministic but NOT secure
        raw = os.getenv("SECRET_KEY", "dev-fallback-encryption-key")
    return Fernet(_derive_key(raw))


# ══════════════════════════════════════
#  Public API
# ══════════════════════════════════════

def encrypt_field(plaintext: str) -> str:
    """Encrypt a string.  Returns url-safe base64 ciphertext."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_field(ciphertext: str) -> str:
    """Decrypt a Fernet token back to plaintext."""
    if not ciphertext:
        return ciphertext
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # If decryption fails the value is probably stored in plaintext
        # (pre-migration data).  Return as-is rather than crashing reads.
        return ciphertext


# ══════════════════════════════════════
#  SQLAlchemy TypeDecorator
# ══════════════════════════════════════

class EncryptedString(TypeDecorator):
    """
    A column type that transparently encrypts on write and decrypts on read.

    Usage::

        class User(Base):
            ssn = Column(EncryptedString(length=500), nullable=True)

    Stored as a regular VARCHAR in the database, but the value is a
    Fernet token (base64) that cannot be read without the key.
    """

    impl = String
    cache_ok = True

    def __init__(self, length: int = 500, **kw):
        super().__init__()
        self.impl = String(length)

    def process_bind_param(self, value, dialect):
        """Encrypt before INSERT / UPDATE."""
        if value is None:
            return value
        return encrypt_field(str(value))

    def process_result_value(self, value, dialect):
        """Decrypt after SELECT."""
        if value is None:
            return value
        return decrypt_field(value)
