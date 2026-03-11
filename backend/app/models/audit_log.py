"""
ASTRA — Tamper-Evident Audit Log Model
========================================
File: backend/app/models/audit_log.py   ← NEW

Append-only ledger with a SHA-256 hash chain.  Every record hashes
its own content plus the previous record's hash, forming a
cryptographic chain that makes silent tampering detectable.

The companion SQL migration (database/migrations/audit_append_only.sql)
installs a PostgreSQL trigger that physically prevents UPDATE and DELETE
on this table.
"""

from datetime import datetime
from sqlalchemy import (
    Column, BigInteger, Integer, String, Text, DateTime,
    ForeignKey, JSON, Index,
)
from sqlalchemy.orm import relationship
from app.database import Base


class AuditLog(Base):
    __tablename__ = "audit_log"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # ── Event metadata ──
    timestamp = Column(DateTime, nullable=False, default=datetime.utcnow)
    event_type = Column(String(50), nullable=False)       # e.g. "requirement.created"
    entity_type = Column(String(50), nullable=False)      # e.g. "requirement"
    entity_id = Column(Integer, nullable=False)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    user_ip = Column(String(45), default="")              # IPv6-safe
    user_agent = Column(String(500), default="")

    # ── Payload ──
    action_detail = Column(JSON, default={})
    # e.g. {"field": "status", "old": "draft", "new": "approved"}

    # ── Tamper-evidence chain ──
    previous_hash = Column(String(64), nullable=False)    # SHA-256 of prior record
    record_hash = Column(String(64), nullable=False, unique=True)
    sequence_number = Column(BigInteger, nullable=False, unique=True)

    # ── Relationships (read-only) ──
    user = relationship("User", foreign_keys=[user_id], lazy="joined")

    __table_args__ = (
        Index("ix_audit_entity", "entity_type", "entity_id"),
        Index("ix_audit_project", "project_id", "timestamp"),
        Index("ix_audit_user", "user_id", "timestamp"),
        Index("ix_audit_seq", "sequence_number"),
    )
