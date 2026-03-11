"""
ASTRA — Report Generator Base
===============================
File: backend/app/services/reports/base.py   ← NEW

Abstract base class that every report type implements, plus
the ReportOutput dataclass returned to the router, and shared
helper functions for extracting data from the ASTRA DB.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import (
    Requirement, Project, TraceLink, SourceArtifact,
    Verification, RequirementHistory, Baseline, User,
)


@dataclass
class ReportOutput:
    """Returned by every generate() call."""
    content: bytes
    filename: str
    content_type: str
    metadata: dict = field(default_factory=dict)


class ReportGenerator(ABC):
    """Interface every report type implements."""

    name: str = "base"
    supported_formats: list[str] = []

    @abstractmethod
    def generate(
        self, project_id: int, db: Session, options: dict | None = None,
    ) -> ReportOutput:
        ...

    # ── Shared query helpers ─────────────────────────────

    @staticmethod
    def _get_project(db: Session, project_id: int) -> Project:
        p = db.query(Project).filter(Project.id == project_id).first()
        if not p:
            raise ValueError(f"Project {project_id} not found")
        return p

    @staticmethod
    def _get_requirements(db: Session, project_id: int) -> list[Requirement]:
        return (
            db.query(Requirement)
            .filter(Requirement.project_id == project_id, Requirement.status != "deleted")
            .order_by(Requirement.req_id)
            .all()
        )

    @staticmethod
    def _get_trace_links(db: Session, req_ids: list[int]) -> list[TraceLink]:
        if not req_ids:
            return []
        return db.query(TraceLink).filter(
            ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids))) |
            ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids)))
        ).all()

    @staticmethod
    def _get_verifications(db: Session, req_ids: list[int]) -> dict[int, list[Verification]]:
        if not req_ids:
            return {}
        result: dict[int, list[Verification]] = {}
        for v in db.query(Verification).filter(Verification.requirement_id.in_(req_ids)).all():
            result.setdefault(v.requirement_id, []).append(v)
        return result

    @staticmethod
    def _get_history(
        db: Session, req_ids: list[int],
        date_from: datetime | None = None, date_to: datetime | None = None,
    ) -> list[RequirementHistory]:
        if not req_ids:
            return []
        q = db.query(RequirementHistory).filter(RequirementHistory.requirement_id.in_(req_ids))
        if date_from:
            q = q.filter(RequirementHistory.changed_at >= date_from)
        if date_to:
            q = q.filter(RequirementHistory.changed_at <= date_to)
        return q.order_by(RequirementHistory.changed_at.desc()).all()

    @staticmethod
    def _enum_val(v: Any) -> str:
        return v.value if hasattr(v, "value") else str(v) if v else ""

    @staticmethod
    def _ts(dt: datetime | None) -> str:
        return dt.strftime("%Y-%m-%d %H:%M") if dt else ""
