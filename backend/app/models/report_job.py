"""
ASTRA — ReportJob model (F-019 + F-032)
=========================================
File: backend/app/models/report_job.py

A persistent record of every report generation. Replaces the
process-local `_report_history` list in routers/reports.py and serves
as the substrate for the async generation pattern (POST returns
job_id, BackgroundTasks runs the generator, GET polls + downloads).

Status state machine:
    pending  → running  → completed
                       ↘ failed
    pending  → failed                (synchronous failure)

The completed-job blob is stored inline in `result_blob`. For very
large outputs you may later switch to S3 / object store; the API
contract (job_id + download endpoint) stays stable.
"""

from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, ForeignKey,
    Enum as SQLEnum, JSON, LargeBinary, Index,
)
from sqlalchemy.orm import relationship

from app.database import Base


class ReportJobStatus(str, enum.Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class ReportJob(Base):
    __tablename__ = "report_jobs"

    id = Column(Integer, primary_key=True, index=True)
    project_id = Column(
        Integer, ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    report_type = Column(String(64), nullable=False)
    format = Column(String(16), nullable=False)
    status = Column(
        SQLEnum(
            ReportJobStatus,
            name="reportjobstatus",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False, default=ReportJobStatus.PENDING, index=True,
    )

    # Caller identity
    requested_by_id = Column(
        Integer, ForeignKey("users.id"), nullable=False, index=True,
    )

    # Generation parameters (framework, date range, etc.)
    options = Column(JSON, default=dict)

    # Result (only populated when status == "completed")
    result_blob = Column(LargeBinary, nullable=True)
    result_filename = Column(String(255), nullable=True)
    result_content_type = Column(String(128), nullable=True)
    result_metadata = Column(JSON, nullable=True)

    # Failure detail
    error_message = Column(Text, nullable=True)

    # Lifecycle timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    project = relationship("Project")
    requested_by = relationship("User")

    __table_args__ = (
        Index("ix_report_jobs_project_created", "project_id", "created_at"),
    )

    def to_summary(self) -> dict:
        """Lightweight dict for list responses (no blob)."""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "report_type": self.report_type,
            "format": self.format,
            "status": self.status.value if isinstance(self.status, enum.Enum) else self.status,
            "requested_by_id": self.requested_by_id,
            "options": self.options or {},
            "filename": self.result_filename,
            "content_type": self.result_content_type,
            "metadata": self.result_metadata or {},
            "error": self.error_message,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
