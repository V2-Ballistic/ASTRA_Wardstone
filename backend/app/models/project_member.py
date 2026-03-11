"""
ASTRA — Project Member Association Model
=========================================
Tracks which users are assigned to which projects,
with optional per-project role overrides.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, ForeignKey, String, DateTime, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.database import Base


class ProjectMember(Base):
    __tablename__ = "project_members"
    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role_override = Column(String(50), nullable=True)  # optional project-specific role
    added_at = Column(DateTime, default=datetime.utcnow)
    added_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Relationships
    project = relationship("Project", backref="members")
    user = relationship("User", foreign_keys=[user_id], backref="project_memberships")
    added_by = relationship("User", foreign_keys=[added_by_id])
