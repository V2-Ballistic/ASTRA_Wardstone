"""
ASTRA — Auth Router
====================
File: backend/app/routers/auth.py

Login flow includes account lockout (NIST AC-7) and full audit
trail for both successful AND failed authentication attempts
(NIST AU-2). See AUDIT_FINDINGS F-016, F-031, F-124.
"""

import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import User, UserRole
from app.schemas import UserCreate, UserResponse, Token
from app.services import account_lockout
from app.services.auth import (
    verify_password, get_password_hash, create_access_token, get_current_user,
    revoke_access_token_jti, oauth2_scheme,
)


# F-122: dedicated /me response shape, decoupled from UserResponse.
# Pre-fix /me serialised through `UserResponse`, which is the
# admin-facing shape ("show me a user"). Coupling them meant any
# future field added to UserResponse for an admin view would silently
# leak into the /me endpoint that every authenticated frontend calls
# on every page load. Splitting them gives /me an explicit contract.
class MeResponse(BaseModel):
    id: int
    username: str
    email: str
    full_name: str
    role: str
    department: Optional[str] = None

    class Config:
        from_attributes = True

# Optional audit integration. The router REQUIRES audit_service in
# the success/failure paths below; the shim only protects the import
# itself for environments that haven't installed audit yet (dev only).
try:
    from app.services.audit_service import record_event as _audit
except ImportError:
    def _audit(*a, **kw):
        pass

logger = logging.getLogger("astra.auth")

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ══════════════════════════════════════
#  Register
# ══════════════════════════════════════

@router.post("/register", response_model=UserResponse, status_code=201)
def register(user_data: UserCreate, request: Request,
             db: Session = Depends(get_db)):
    """
    Public self-registration.

    AUDIT_FINDINGS F-015: any `role` field in the request body is IGNORED.
    Self-registered users always receive UserRole.DEVELOPER. Elevated
    roles (admin, project_manager, requirements_engineer, reviewer,
    stakeholder) must be assigned by an existing admin via
    POST /api/v1/admin/users — never via this endpoint.
    """
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(400, "Username already taken")
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(400, "Email already registered")

    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=UserRole.DEVELOPER,        # F-015: ignore any role in the body
        department=user_data.department,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ══════════════════════════════════════
#  Login (with account lockout + full audit)
# ══════════════════════════════════════

def _retry_after_seconds(locked_until_iso: str | None) -> str:
    """Compute a Retry-After header value in seconds from a locked_until ISO string."""
    if not locked_until_iso:
        return str(account_lockout.LOCKOUT_MINUTES * 60)
    try:
        locked_until = datetime.fromisoformat(locked_until_iso)
        delta = (locked_until - datetime.utcnow()).total_seconds()
        return str(max(1, int(delta)))
    except (ValueError, TypeError):
        return str(account_lockout.LOCKOUT_MINUTES * 60)


@router.post("/login", response_model=Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """
    Username + password login.

    AUDIT_FINDINGS:
      - F-016 (NIST AC-7): account_lockout is checked BEFORE password
        verification; failed attempts are recorded; reaching
        MAX_LOGIN_ATTEMPTS locks the account for LOCKOUT_DURATION_MINUTES.
      - F-031 (NIST AU-2): every failed attempt against a known user
        emits an `auth.login_failed` audit row; failures against
        unknown usernames are logged via the stdlib logger (audit_log
        has user_id FK NOT NULL so we cannot write a row without a
        valid user — enumeration probes still surface in stdout/syslog).
      - F-124: removed silent `try/except: pass` around the success-side
        audit; record_event is now allowed to raise.

    Status codes:
      200 — success
      401 — invalid credentials (or unknown user; same response shape
            to avoid username enumeration)
      429 — Too Many Requests (account is locked; Retry-After header
            indicates seconds until auto-unlock)
    """
    username = form_data.username
    ip = request.client.host if request.client else ""

    # ── F-016: lockout check BEFORE any password work ──
    if account_lockout.is_account_locked(db, username):
        lock_status = account_lockout.get_lockout_status(db, username)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Account temporarily locked due to repeated failed login attempts",
            headers={"Retry-After": _retry_after_seconds(lock_status.get("locked_until"))},
        )

    user = db.query(User).filter(User.username == username).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        # ── F-016: count this failure ──
        result = account_lockout.record_failed_attempt(db, username, ip=ip)

        # ── F-031: audit every failed attempt against a known user ──
        if user is not None:
            _audit(
                db, "auth.login_failed", "user", user.id, user.id,
                {
                    "ip": ip,
                    "username": username,
                    "attempts": result["attempts"],
                    "locked": result["locked"],
                },
                request=request,
            )
        else:
            # Unknown username — audit_log.user_id is FK NOT NULL, so we
            # cannot write a row. Stdlib logger still surfaces this for
            # SOC tooling that consumes container stdout / syslog.
            logger.warning(
                "auth.login_failed (unknown_user) username=%r ip=%s "
                "attempts=%d locked=%s",
                username, ip, result["attempts"], result["locked"],
            )

        # If this attempt triggered the lockout, prefer 429 over 401 so
        # the client knows to back off rather than retry with a different
        # password.
        if result["locked"]:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Account locked due to repeated failed login attempts",
                headers={
                    "Retry-After": _retry_after_seconds(result.get("locked_until")),
                },
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated",
        )

    # ── Success path ──
    # F-016: clear the failure counter so a future attempt starts fresh.
    account_lockout.record_successful_login(db, username)

    user.last_login = datetime.utcnow()
    db.commit()

    access_token = create_access_token(data={"sub": user.username})

    # F-124: no try/except here. record_event has its own retry / chain
    # semantics; if it raises, the login surfaces the failure rather
    # than silently dropping the audit trail.
    _audit(
        db, "auth.login_success", "user", user.id, user.id,
        {"ip": ip}, request=request,
    )

    return {"access_token": access_token, "token_type": "bearer"}


# ══════════════════════════════════════
#  Me
# ══════════════════════════════════════

@router.get("/me", response_model=MeResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user


# ══════════════════════════════════════
#  Logout (F-063)
# ══════════════════════════════════════

@router.post("/logout", status_code=204)
def logout(
    request: Request,
    token: str = Depends(oauth2_scheme),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """F-063: write the access token's jti to the durable revocation
    list so the same token can't keep authenticating on other workers
    after this call returns. Pre-fix logout was a no-op on the server
    (the only "logout" was the frontend dropping the token from local
    storage), so a stolen token survived as long as its 8-hour expiry."""
    try:
        payload = jwt.decode(
            token, settings.SECRET_KEY.get_secret_value(),
            algorithms=[settings.ALGORITHM],
            options={"verify_exp": False},  # already validated by get_current_user
        )
        jti = payload.get("jti")
        exp_ts = payload.get("exp")
    except JWTError:
        # Caller had a valid token to reach this dep but somehow we
        # can't re-decode it — surface as 401 rather than silently
        # accepting an unrevoked token.
        raise HTTPException(401, "Invalid token")

    if jti and exp_ts:
        exp_dt = datetime.utcfromtimestamp(exp_ts)
        revoke_access_token_jti(
            db, jti, exp_dt, user_id=current_user.id, reason="logout",
        )

    _audit(
        db, "auth.logout", "user", current_user.id, current_user.id,
        {"jti": jti}, request=request,
    )

    return None


# ══════════════════════════════════════
#  Refresh-token rotation (F-068)
# ══════════════════════════════════════

class RefreshRequest(BaseModel):
    refresh_token: str


@router.post("/refresh", response_model=Token)
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)):
    """F-068: rotate the refresh token. Returns a new
    (access_token, refresh_token) pair; the incoming refresh token is
    revoked atomically so a stolen refresh can be used at most once
    before the legitimate user's next refresh invalidates it."""
    from app.services.auth_manager import refresh_access_token

    result = refresh_access_token(db, payload.refresh_token)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )
    return {
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],
        "token_type": "bearer",
    }
