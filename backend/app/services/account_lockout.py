"""
ASTRA — Account Lockout Service
=================================
File: backend/app/services/account_lockout.py   ← NEW

Tracks consecutive failed login attempts per username and temporarily
locks the account after too many failures.

NIST 800-53 AC-7: Unsuccessful Logon Attempts
  - Lock account after MAX_LOGIN_ATTEMPTS consecutive failures
  - Auto-unlock after LOCKOUT_DURATION_MINUTES
  - Record the IP and timestamp of each failed attempt

Configuration (env vars):
    MAX_LOGIN_ATTEMPTS       — default 5
    LOCKOUT_DURATION_MINUTES — default 30
"""

import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session

from app.models.security_models import AccountLockout


MAX_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
LOCKOUT_MINUTES = int(os.getenv("LOCKOUT_DURATION_MINUTES", "30"))


def is_account_locked(db: Session, username: str) -> bool:
    """Return True if the account is currently locked out."""
    record = db.query(AccountLockout).filter(
        AccountLockout.username == username
    ).first()
    if not record:
        return False
    if record.locked_until and record.locked_until > datetime.utcnow():
        return True
    # Lock period expired — reset
    if record.locked_until and record.locked_until <= datetime.utcnow():
        record.failed_attempts = 0
        record.locked_until = None
        db.commit()
    return False


def record_failed_attempt(db: Session, username: str, ip: str = "") -> dict:
    """
    Increment the failure counter.  If it reaches the threshold, lock
    the account.

    Returns:
        {
            "locked": bool,
            "attempts": int,
            "locked_until": datetime | None,
            "remaining": int,           # attempts before lockout
        }
    """
    record = db.query(AccountLockout).filter(
        AccountLockout.username == username
    ).first()

    if not record:
        record = AccountLockout(username=username, failed_attempts=0)
        db.add(record)

    record.failed_attempts += 1
    record.last_attempt_at = datetime.utcnow()
    record.last_attempt_ip = ip

    locked = False
    locked_until = None
    if record.failed_attempts >= MAX_ATTEMPTS:
        locked_until = datetime.utcnow() + timedelta(minutes=LOCKOUT_MINUTES)
        record.locked_until = locked_until
        locked = True

    db.commit()

    return {
        "locked": locked,
        "attempts": record.failed_attempts,
        "locked_until": locked_until.isoformat() if locked_until else None,
        "remaining": max(0, MAX_ATTEMPTS - record.failed_attempts),
    }


def record_successful_login(db: Session, username: str) -> None:
    """Reset the failure counter on a successful login."""
    record = db.query(AccountLockout).filter(
        AccountLockout.username == username
    ).first()
    if record:
        record.failed_attempts = 0
        record.locked_until = None
        db.commit()


def get_lockout_status(db: Session, username: str) -> dict:
    """Return the current lockout state for a username."""
    record = db.query(AccountLockout).filter(
        AccountLockout.username == username
    ).first()
    if not record:
        return {
            "locked": False,
            "attempts": 0,
            "locked_until": None,
            "remaining": MAX_ATTEMPTS,
        }
    locked = bool(record.locked_until and record.locked_until > datetime.utcnow())
    return {
        "locked": locked,
        "attempts": record.failed_attempts,
        "locked_until": record.locked_until.isoformat() if record.locked_until else None,
        "remaining": max(0, MAX_ATTEMPTS - record.failed_attempts),
    }
