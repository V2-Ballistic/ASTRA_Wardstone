"""
ASTRA — Impact Analysis Database Models
==========================================
File: backend/app/models/impact.py   ← NEW

Stores computed impact reports so they can be linked to
change history entries and reviewed later.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime,
    ForeignKey, JSON, Index,
)
from app.database import Base


class ImpactReport(Base):
    """
    Persisted impact analysis report.

    Created whenever an impact analysis is run — either manually
    via the API or automatically during a requirement update.
    Linked to the requirement that was changed.
    """
    __tablename__ = "impact_reports"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(
        Integer,
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    change_description = Column(Text, default="")
    action_type = Column(String(20), default="modify")        # modify, delete, what_if
    report_json = Column(JSON, nullable=False, default={})     # Full ImpactReport as JSON
    risk_level = Column(String(20), nullable=False, default="low")
    total_affected = Column(Integer, default=0)
    dependency_depth = Column(Integer, default=0)
    ai_summary = Column(Text, default="")
    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_impact_req_date", "requirement_id", "created_at"),
        Index("ix_impact_risk", "risk_level"),
    )
