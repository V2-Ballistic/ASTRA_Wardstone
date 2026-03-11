"""
ASTRA — Integration Database Models
======================================
File: backend/app/models/integration.py   ← NEW

Two tables:
  IntegrationConfig — stores connection details (encrypted) and
                      field mapping for each project ↔ tool pair
  SyncLog           — records every sync operation for auditability
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, DateTime, Boolean,
    ForeignKey, JSON, Index,
)
from sqlalchemy.orm import relationship
from app.database import Base


class IntegrationConfig(Base):
    __tablename__ = "integration_configs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=False)
    integration_type = Column(String(50), nullable=False)  # "jira", "azure_devops", "doors"
    display_name = Column(String(255), default="")          # user-friendly label

    # Connection details — stored encrypted via app.services.encryption
    config_encrypted = Column(Text, nullable=False, default="{}")

    # Field mapping: external_field → astra_field
    field_mapping = Column(JSON, default={
        "title": "title",
        "description": "statement",
        "priority": "priority",
        "status": "status",
        "type": "req_type",
    })

    sync_direction = Column(String(20), default="import")   # import | export | bidirectional
    external_project = Column(String(255), default="")      # Jira project key, ADO project name, DOORS area URI
    sync_schedule = Column(String(50), default="")          # cron expression, empty = manual only
    last_sync_at = Column(DateTime, nullable=True)
    is_active = Column(Boolean, default=True)

    created_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    project = relationship("Project")
    created_by = relationship("User")
    sync_logs = relationship("SyncLog", back_populates="integration_config",
                             cascade="all, delete-orphan",
                             order_by="SyncLog.started_at.desc()")

    __table_args__ = (
        Index("ix_intconfig_project", "project_id", "integration_type"),
    )


class SyncLog(Base):
    __tablename__ = "sync_logs"

    id = Column(Integer, primary_key=True, index=True)
    integration_config_id = Column(Integer, ForeignKey("integration_configs.id"), nullable=False)
    direction = Column(String(20), nullable=False)          # "import" | "export"
    status = Column(String(20), nullable=False, default="running")  # running | success | partial | failed
    created_count = Column(Integer, default=0)
    updated_count = Column(Integer, default=0)
    skipped_count = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    details = Column(JSON, default={})                      # error messages, item-level details
    triggered_by_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    integration_config = relationship("IntegrationConfig", back_populates="sync_logs")
    triggered_by = relationship("User")

    __table_args__ = (
        Index("ix_synclog_config", "integration_config_id", "started_at"),
    )
