"""
ASTRA — Embedding Database Models
====================================
File: backend/app/models/embedding.py   ← NEW

Tables:
  RequirementEmbedding — stores vector embeddings per requirement for
                          semantic duplicate detection & trace suggestion.
  AISuggestion         — stores generated AI suggestions (duplicates,
                          trace links, verification methods) for frontend display.

Supports both JSON-stored embeddings (portable) and pgvector extension
(efficient similarity search) depending on deployment configuration.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Float, DateTime, Boolean,
    ForeignKey, JSON, Index, UniqueConstraint,
)
from sqlalchemy.orm import relationship
from app.database import Base


class RequirementEmbedding(Base):
    """
    Cached vector embedding for a requirement's statement text.

    The embedding is regenerated whenever the statement text changes,
    detected by comparing statement_hash.  Supports multiple embedding
    models via model_version tracking.
    """
    __tablename__ = "requirement_embeddings"

    id = Column(Integer, primary_key=True, index=True)
    requirement_id = Column(
        Integer,
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    # Embedding stored as JSON array of floats (portable, works without pgvector)
    embedding = Column(JSON, nullable=False, default=[])
    # Embedding dimensionality for validation
    dimensions = Column(Integer, nullable=False, default=384)
    # Which model produced this embedding
    model_version = Column(String(100), nullable=False, default="all-MiniLM-L6-v2")
    # SHA-256 hash of the statement text — if it changes, re-embed
    statement_hash = Column(String(64), nullable=False, default="")
    # When this embedding was generated
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        Index("ix_req_embed_model", "model_version"),
    )


class AISuggestion(Base):
    """
    Persisted AI suggestion for frontend display and tracking.

    Types:
      - duplicate        : this requirement may duplicate another
      - trace_link       : suggested traceability link
      - verification     : suggested verification method
    """
    __tablename__ = "ai_suggestions"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    requirement_id = Column(
        Integer,
        ForeignKey("requirements.id", ondelete="CASCADE"),
        nullable=False,
    )
    suggestion_type = Column(String(30), nullable=False)  # duplicate, trace_link, verification
    # For duplicate / trace: the target requirement or artifact
    target_type = Column(String(50), default="")       # "requirement", "source_artifact", "verification"
    target_id = Column(Integer, nullable=True)
    # Confidence score 0.0 — 1.0
    confidence = Column(Float, nullable=False, default=0.0)
    # Human-readable explanation
    explanation = Column(Text, default="")
    # Extra structured data (e.g., verification criteria, similarity details)
    metadata_json = Column(JSON, default={})
    # Resolution status
    status = Column(String(20), nullable=False, default="pending")  # pending, accepted, rejected, dismissed
    resolved_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    resolved_at = Column(DateTime, nullable=True)
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_ai_sugg_project", "project_id"),
        Index("ix_ai_sugg_req", "requirement_id"),
        Index("ix_ai_sugg_status", "status"),
        Index("ix_ai_sugg_type", "suggestion_type"),
    )
