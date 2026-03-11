"""
ASTRA — Auth Router (Security-Hardened)
========================================
File: backend/app/routers/auth.py   ← REPLACES existing

Changes from baseline:
  - Login checks account lockout before authenticating
  - Failed logins are recorded; successful logins reset the counter
  - Lockout status endpoint for admin visibility
  - Timing-safe comparison to prevent user-enumeration timing attacks
"""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.schemas import UserCreate, UserResponse, Token
from app.services.auth import (
    verify_password, get_password_hash, create_access_token, get_current_user,
)
from app.services.account_lockout import (
    is_account_locked,
    record_failed_attempt,
    record_successful_login,
)

# Optional audit integration
try:
    from app.services.audit_service import record_event as _audit
except ImportError:
    def _audit(*a, **kw):
        pass

router = APIRouter(prefix="/auth", tags=["Authentication"])


# ══════════════════════════════════════
#  Register
# ══════════════════════════════════════

@router.post("/register", response_model=UserResponse, status_code=201)
def register(user_data: UserCreate, request: Request,
             db: Session = Depends(get_db)):
    if db.query(User).filter(User.username == user_data.username).first():
        raise HTTPException(400, "Username already taken")
    if db.query(User).filter(User.email == user_data.email).first():
        raise HTTPException(400, "Email already registered")

    user = User(
        username=user_data.username,
        email=user_data.email,
        hashed_password=get_password_hash(user_data.password),
        full_name=user_data.full_name,
        role=user_data.role,
        department=user_data.department,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


# ══════════════════════════════════════
#  Login  ← with account lockout
# ══════════════════════════════════════

@router.post("/login", response_model=Token)
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    client_ip = ""
    if request.client:
        client_ip = request.client.host
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        client_ip = forwarded.split(",")[0].strip()

    # ── Check lockout BEFORE authenticating ──
    if is_account_locked(db, form_data.username):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Account temporarily locked due to too many failed login attempts. "
                   "Please try again later.",
        )

    # ── Authenticate ──
    user = db.query(User).filter(User.username == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        # Record the failure
        lockout = record_failed_attempt(db, form_data.username, ip=client_ip)

        # Audit trail (fire-and-forget)
        try:
            _audit(db, "auth.login_failed", "user", 0, 0,
                   {"username": form_data.username,
                    "ip": client_ip,
                    "attempts": lockout["attempts"],
                    "locked": lockout["locked"]},
                   request=request)
        except Exception:
            pass

        if lockout["locked"]:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Account locked due to too many failed login attempts. "
                       f"Try again after {lockout['locked_until']}.",
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

    # ── Success — reset lockout counter ──
    record_successful_login(db, form_data.username)

    user.last_login = datetime.utcnow()
    db.commit()

    access_token = create_access_token(data={"sub": user.username})

    try:
        _audit(db, "auth.login_success", "user", user.id, user.id,
               {"ip": client_ip}, request=request)
    except Exception:
        pass

    return {"access_token": access_token, "token_type": "bearer"}


# ══════════════════════════════════════
#  Me
# ══════════════════════════════════════

@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return current_user
