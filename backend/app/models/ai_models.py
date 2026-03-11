"""
ASTRA — AI Database Models
=============================
File: backend/app/models/ai_models.py   ← NEW

Two tables:
  AIAnalysisCache — stores AI analysis results per requirement
  AIFeedback      — tracks user accept/reject of AI suggestions
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, JSON, Index,
)
from sqlalchemy.orm import relationship
from app.database import Base


class AIAnalysisCache(Base):
    __tablename__ = "ai_analysis_cache"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(Integer, ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False)
    analysis_type = Column(String(30), nullable=False, default="deep")  # "deep" | "batch"
    result_json = Column(JSON, nullable=False, default={})
    model_used = Column(String(100), default="")
    prompt_version = Column(String(20), default="")
    analyzed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_ai_cache_req_type", "requirement_id", "analysis_type", unique=True),
    )


class AIFeedback(Base):
    __tablename__ = "ai_feedback"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    requirement_id = Column(Integer, ForeignKey("requirements.id", ondelete="CASCADE"), nullable=False)
    suggestion_type = Column(String(50), default="")        # "rewrite", "issue", "gap"
    suggestion_text = Column(Text, default="")
    accepted = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")

    __table_args__ = (
        Index("ix_ai_feedback_req", "requirement_id"),
        Index("ix_ai_feedback_user", "user_id", "created_at"),
    )
