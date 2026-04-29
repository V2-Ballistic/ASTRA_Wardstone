"""
ASTRA — Field-Level Encryption Service
========================================
File: backend/app/services/encryption.py

Provides AES-128 symmetric encryption via Fernet for PII and sensitive
fields.  The encryption key is derived from ``ENCRYPTION_KEY`` using
PBKDF2 so the raw env-var value doesn't need to be a precise length.

Also provides ``EncryptedString`` — a SQLAlchemy TypeDecorator that
transparently encrypts on INSERT/UPDATE and decrypts on SELECT.

NIST 800-53 controls:  SC-28 (Protection of Information at Rest)

Security notes (post-AUDIT_FINDINGS F-003 + F-067):
  - The dev-only literal fallback ``"dev-fallback-encryption-key"`` was
    removed. If neither ``ENCRYPTION_KEY`` nor ``SECRET_KEY`` is set the
    module raises ``RuntimeError`` at first use — loud, easy to fix.
    Production startup is also blocked by ``config.enforce_production_guards``.
  - ``decrypt_field`` no longer silently returns ciphertext on
    ``InvalidToken`` — it re-raises by default. The legacy "passthrough
    on failure" path is gated by ``ALLOW_PLAINTEXT_LEGACY=true`` and
    emits a warning log.
  - ``_SALT`` is now configurable via ``ENCRYPTION_KEY_SALT`` so two
    installations using the same ENCRYPTION_KEY do not derive the same
    Fernet key (NIST 800-132 best practice).
"""

import base64
import logging
import os

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from sqlalchemy import String, TypeDecorator


logger = logging.getLogger("astra.encryption")


# ══════════════════════════════════════
#  Constants
# ══════════════════════════════════════

# Default salt — kept stable for backward compatibility with values
# encrypted by previous releases. Override per installation via
# ENCRYPTION_KEY_SALT env var (recommended).
_DEFAULT_SALT = b"astra-field-encryption-v1"
_PBKDF2_ITERATIONS = 480_000


def _get_salt() -> bytes:
    """Salt for PBKDF2; per-installation override via env var."""
    raw = os.getenv("ENCRYPTION_KEY_SALT", "")
    if raw:
        return raw.encode("utf-8")
    return _DEFAULT_SALT


# ══════════════════════════════════════
#  Key derivation
# ══════════════════════════════════════


def derive_key(raw_key: str, salt: bytes | None = None) -> bytes:
    """
    Derive a 32-byte url-safe base64 Fernet key from an arbitrary string.

    Public API: callers in other services (e.g. mfa.py) use this to
    keep key derivation consistent across the codebase.
    """
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt if salt is not None else _get_salt(),
        iterations=_PBKDF2_ITERATIONS,
    )
    return base64.urlsafe_b64encode(kdf.derive(raw_key.encode("utf-8")))


# ── Backwards-compat alias: some older code may import _derive_key.
_derive_key = derive_key


def _resolve_raw_key() -> str:
    """
    Locate the raw key material. Prefers ``ENCRYPTION_KEY``; falls back
    to ``SECRET_KEY`` *only* with a warning. Raises RuntimeError if both
    are unset — the module refuses to encrypt PII with a known constant.
    """
    raw = os.getenv("ENCRYPTION_KEY", "")
    if raw:
        return raw

    secret = os.getenv("SECRET_KEY", "")
    if secret:
        logger.warning(
            "ENCRYPTION_KEY not set — falling back to SECRET_KEY. "
            "Set a dedicated ENCRYPTION_KEY for production.",
        )
        return secret

    raise RuntimeError(
        "Neither ENCRYPTION_KEY nor SECRET_KEY is set; refusing to "
        "encrypt PII with a known constant. Set ENCRYPTION_KEY before "
        "starting the application.",
    )


def _get_fernet() -> Fernet:
    return Fernet(derive_key(_resolve_raw_key()))


# ══════════════════════════════════════
#  Public API
# ══════════════════════════════════════


def encrypt_field(plaintext: str) -> str:
    """Encrypt a string. Returns url-safe base64 ciphertext."""
    if not plaintext:
        return plaintext
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_field(ciphertext: str) -> str:
    """
    Decrypt a Fernet token back to plaintext.

    Raises InvalidToken on failure unless ``ALLOW_PLAINTEXT_LEGACY=true``,
    in which case the original ciphertext is returned and a warning is
    logged. The legacy passthrough exists to support pre-encryption rows;
    once migrated, leave the env var unset so tampering / wrong-key
    situations surface immediately.
    """
    if not ciphertext:
        return ciphertext
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        if os.getenv("ALLOW_PLAINTEXT_LEGACY", "false").lower() == "true":
            logger.warning(
                "decrypt_field: InvalidToken — returning ciphertext as-is "
                "(ALLOW_PLAINTEXT_LEGACY=true). Investigate and migrate this row.",
            )
            return ciphertext
        raise


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
