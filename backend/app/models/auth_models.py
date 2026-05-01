"""
ASTRA — Auth-Related Database Models
======================================
File: backend/app/models/auth_models.py

Tables for MFA secrets, refresh tokens, and session tracking.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean, ForeignKey,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.database import Base


class MFAConfig(Base):
    __tablename__ = "mfa_configs"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    secret_encrypted = Column(Text, nullable=False)
    is_enabled = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_used_at = Column(DateTime, nullable=True)

    user = relationship("User", backref="mfa_config")


class RefreshToken(Base):
    __tablename__ = "refresh_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # `unique=True` replaced with an explicitly-named UniqueConstraint
    # matching the PG auto-name so `alembic check` sees no drift.
    token_hash = Column(String(128), nullable=False, index=True)
    expires_at = Column(DateTime, nullable=False)
    revoked = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="refresh_tokens")

    __table_args__ = (
        UniqueConstraint("token_hash", name="refresh_tokens_token_hash_key"),
    )


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    auth_provider = Column(String(50), nullable=False, default="local")
    ip_address = Column(String(50), default="")
    user_agent = Column(Text, default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", backref="auth_sessions")


class RevokedToken(Base):
    """F-063: durable, cross-worker access-token revocation list.

    The pre-fix implementation kept revoked JTIs in a process-local
    ``set()`` (``auth_manager._BLACKLIST``) — a logout in worker A had
    no effect on worker B, so the same JWT could keep authenticating
    on the other worker(s) until it expired naturally. With access
    tokens previously living for 8 hours that meant a stolen token
    survived a logout for the rest of the work day.

    Each access token now carries a ``jti`` claim; logout (and any
    future "revoke session" admin action) inserts a row here, and
    ``get_current_user`` rejects any token whose jti is present.
    Rows older than ``exp`` can be reaped by a periodic cleanup —
    once the underlying JWT expires the row is no longer load-bearing.
    """
    __tablename__ = "revoked_tokens"

    id = Column(Integer, primary_key=True, index=True)
    jti = Column(String(64), nullable=False, index=True)
    exp = Column(DateTime, nullable=False, index=True)
    revoked_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    reason = Column(String(50), nullable=True)  # 'logout', 'admin_revoke', etc.

    __table_args__ = (
        UniqueConstraint("jti", name="revoked_tokens_jti_key"),
    )
