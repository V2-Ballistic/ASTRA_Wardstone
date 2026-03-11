"""
ASTRA — Unified Auth Manager
==============================
File: backend/app/services/auth_manager.py

Delegates to the configured provider, handles MFA step, and manages
refresh tokens and token blacklisting (logout).

Env vars:
    AUTH_PROVIDER       — "local" | "saml" | "oidc" | "piv"  (default: "local")
    AUTH_MFA_REQUIRED   — "true" to require MFA after primary auth
"""

import os
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Optional

from jose import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User
from app.models.auth_models import RefreshToken, AuthSession
from app.services.auth_providers import get_provider
from app.services import mfa as mfa_service


ACTIVE_PROVIDER = os.getenv("AUTH_PROVIDER", "local")
MFA_REQUIRED = os.getenv("AUTH_MFA_REQUIRED", "false").lower() == "true"

REFRESH_TOKEN_EXPIRE_DAYS = 30


# ══════════════════════════════════════
#  Token helpers
# ══════════════════════════════════════

def create_access_token(
    data: dict, expires_delta: timedelta | None = None, partial: bool = False,
) -> str:
    """
    Issue a JWT.  If *partial* is True the token only grants the
    ``/auth/mfa/verify`` endpoint (user still needs to pass MFA).
    """
    to_encode = data.copy()
    expire = datetime.utcnow() + (
        expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    to_encode.update({"exp": expire})
    if partial:
        to_encode["mfa_pending"] = True
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def create_refresh_token(db: Session, user_id: int) -> str:
    """Generate an opaque refresh token, store its hash, return the raw value."""
    raw = secrets.token_urlsafe(64)
    token_hash = hashlib.sha256(raw.encode()).hexdigest()

    rt = RefreshToken(
        user_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(rt)
    db.commit()
    return raw


def refresh_access_token(db: Session, raw_refresh: str) -> str | None:
    """Validate a refresh token and return a new access token (or None)."""
    token_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
    rt = (
        db.query(RefreshToken)
        .filter(
            RefreshToken.token_hash == token_hash,
            RefreshToken.revoked == False,  # noqa: E712
            RefreshToken.expires_at > datetime.utcnow(),
        )
        .first()
    )
    if not rt:
        return None

    user = db.query(User).filter(User.id == rt.user_id).first()
    if not user or not user.is_active:
        return None

    return create_access_token(data={"sub": user.username})


def revoke_refresh_token(db: Session, raw_refresh: str) -> bool:
    token_hash = hashlib.sha256(raw_refresh.encode()).hexdigest()
    rt = db.query(RefreshToken).filter(RefreshToken.token_hash == token_hash).first()
    if not rt:
        return False
    rt.revoked = True
    db.commit()
    return True


# ── Token blacklist (simple DB approach; swap for Redis in prod) ──

_BLACKLIST: set[str] = set()


def blacklist_token(jti_or_raw: str) -> None:
    _BLACKLIST.add(jti_or_raw)


def is_token_blacklisted(jti_or_raw: str) -> bool:
    return jti_or_raw in _BLACKLIST


# ══════════════════════════════════════
#  Session tracking
# ══════════════════════════════════════

def record_session(
    db: Session, user_id: int, provider: str,
    ip: str = "", user_agent: str = "",
) -> AuthSession:
    sess = AuthSession(
        user_id=user_id,
        auth_provider=provider,
        ip_address=ip,
        user_agent=user_agent,
    )
    db.add(sess)
    db.commit()
    db.refresh(sess)
    return sess


def list_sessions(db: Session, user_id: int) -> list[AuthSession]:
    return (
        db.query(AuthSession)
        .filter(AuthSession.user_id == user_id)
        .order_by(AuthSession.created_at.desc())
        .limit(50)
        .all()
    )


# ══════════════════════════════════════
#  Primary login flow
# ══════════════════════════════════════

def authenticate(db: Session, **kwargs) -> dict:
    """
    Top-level login entry point.

    Returns dict:
        {"status": "ok",          "access_token": ..., "refresh_token": ...}
        {"status": "mfa_required", "partial_token": ...}
        {"status": "error",        "detail": ...}
    """
    provider = get_provider(ACTIVE_PROVIDER)
    user = provider.authenticate(db, **kwargs)
    if not user:
        return {"status": "error", "detail": "Authentication failed"}

    # Update last_login
    user.last_login = datetime.utcnow()
    db.commit()

    # Check MFA
    user_mfa = mfa_service.is_mfa_enabled(db, user.id)
    if MFA_REQUIRED or user_mfa:
        partial = create_access_token(
            data={"sub": user.username}, partial=True,
            expires_delta=timedelta(minutes=5),
        )
        return {"status": "mfa_required", "partial_token": partial}

    access = create_access_token(data={"sub": user.username})
    refresh = create_refresh_token(db, user.id)

    record_session(
        db, user.id, ACTIVE_PROVIDER,
        ip=kwargs.get("ip", ""),
        user_agent=kwargs.get("user_agent", ""),
    )

    return {
        "status": "ok",
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
    }


def complete_mfa(db: Session, username: str, mfa_token: str, **kwargs) -> dict:
    """After primary auth, verify the TOTP token and issue full tokens."""
    user = db.query(User).filter(User.username == username).first()
    if not user:
        return {"status": "error", "detail": "User not found"}

    if not mfa_service.verify_mfa_token(db, user.id, mfa_token):
        return {"status": "error", "detail": "Invalid MFA token"}

    access = create_access_token(data={"sub": user.username})
    refresh = create_refresh_token(db, user.id)

    record_session(
        db, user.id, ACTIVE_PROVIDER,
        ip=kwargs.get("ip", ""),
        user_agent=kwargs.get("user_agent", ""),
    )

    return {
        "status": "ok",
        "access_token": access,
        "refresh_token": refresh,
        "token_type": "bearer",
    }
