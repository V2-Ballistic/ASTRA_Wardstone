"""
ASTRA — Security Database Models
==================================
File: backend/app/models/security_models.py   ← NEW

NIST 800-53 AC-7: Unsuccessful Logon Attempts tracking.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime
from app.database import Base


class AccountLockout(Base):
    __tablename__ = "account_lockouts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    failed_attempts = Column(Integer, default=0, nullable=False)
    locked_until = Column(DateTime, nullable=True)
    last_attempt_at = Column(DateTime, default=datetime.utcnow)
    last_attempt_ip = Column(String(45), default="")
