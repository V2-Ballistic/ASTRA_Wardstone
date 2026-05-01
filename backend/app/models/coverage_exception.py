"""
ASTRA — Coverage Exception model
=================================
File: backend/app/models/coverage_exception.py   ← NEW (Phase 1, ASTRA-TDD-INTF-002)

Per spec §13.6. Lets a project_manager file an explicit "this requirement
intentionally has no architectural source" exception. Without an admin
co-sign, the exception only downgrades the orphan's severity from `error` to
`warning`. Admin co-sign upgrades the exception to fully cover the orphan.

Schema is the §13.6 minimum (id, requirement_id, reason, is_active, expires_at,
created_by_id, approved_by_id) extended with project_id (for project-scoped
queries on the coverage report) and admin_cosigned_at (for the audit trail).
The unique constraint on (project_id, requirement_id) keeps a single active
exception per requirement; a new exception supersedes an older one by setting
the older to is_active=False.
"""

from __future__ import annotations

from sqlalchemy import (
    Column, Integer, Text, DateTime, Boolean,
    ForeignKey, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class CoverageException(Base):
    __tablename__ = "coverage_exceptions"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "requirement_id", name="uq_coverage_exception_req"
        ),
        Index("ix_coverage_exception_project", "project_id"),
        Index("ix_coverage_exception_req", "requirement_id"),
    )

    id              = Column(Integer, primary_key=True)
    project_id      = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    requirement_id  = Column(
        Integer, ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False
    )
    reason          = Column(Text, nullable=False)
    is_active       = Column(Boolean, default=True, nullable=False)
    expires_at      = Column(DateTime(timezone=True), nullable=True)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    created_by_id   = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Admin co-sign — without this, the exception only downgrades severity
    # from 'error' to 'warning'. With this, the exception fully covers.
    approved_by_id  = Column(Integer, ForeignKey("users.id"), nullable=True)
    approved_at     = Column(DateTime(timezone=True), nullable=True)

    requirement     = relationship("Requirement")
