"""
ASTRA — Report job runner (F-019 + F-032)
==========================================
File: backend/app/services/reports/jobs.py

Bridges the report-generator registry to the persistent
``report_jobs`` table.

* ``create_pending_job``  — insert a row in PENDING and return its id.
* ``run_job``             — execute the generator and update the row
                            (RUNNING → COMPLETED / FAILED). Used by
                            BackgroundTasks for the async path.
* ``record_completed``    — for the synchronous path: take an already-
                            generated ReportOutput and persist a
                            COMPLETED job row in one shot.
* ``get_job_for_user``    — load a job and enforce project membership.

Each operation owns its own DB session (see ``_with_session``) because
BackgroundTasks runs after the request's session is closed.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.dependencies.project_access import _check_membership
from app.models import User
from app.models.report_job import ReportJob, ReportJobStatus
from app.services.reports import REPORT_REGISTRY, ReportOutput

logger = logging.getLogger("astra.reports")


@contextmanager
def _with_session():
    """Yield a fresh DB session, commit/rollback + close on exit."""
    session: Session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def create_pending_job(
    db: Session,
    *,
    project_id: int,
    report_type: str,
    fmt: str,
    options: dict | None,
    requested_by: User,
) -> ReportJob:
    """Insert a PENDING row and return it. Caller commits."""
    if report_type not in REPORT_REGISTRY:
        raise HTTPException(404, f"Unknown report type: {report_type}")

    job = ReportJob(
        project_id=project_id,
        report_type=report_type,
        format=fmt,
        status=ReportJobStatus.PENDING,
        requested_by_id=requested_by.id,
        options=options or {},
    )
    db.add(job)
    db.flush()
    db.refresh(job)
    return job


def record_completed(
    db: Session,
    *,
    project_id: int,
    report_type: str,
    fmt: str,
    options: dict | None,
    requested_by: User,
    output: ReportOutput,
) -> ReportJob:
    """
    Persist a COMPLETED job row from an already-generated ReportOutput.
    Used by the synchronous endpoints so the same row that powers
    /reports/history is written for both sync + async paths.
    """
    now = datetime.utcnow()
    job = ReportJob(
        project_id=project_id,
        report_type=report_type,
        format=fmt,
        status=ReportJobStatus.COMPLETED,
        requested_by_id=requested_by.id,
        options=options or {},
        result_blob=output.content,
        result_filename=output.filename,
        result_content_type=output.content_type,
        result_metadata=_jsonable(output.metadata),
        created_at=now,
        started_at=now,
        completed_at=now,
    )
    db.add(job)
    db.flush()
    db.refresh(job)
    return job


def run_job(job_id: int) -> None:
    """
    Execute the generator for *job_id* and persist the result.

    Designed for BackgroundTasks: opens its own session because the
    request's session is already closed by the time we run.
    """
    with _with_session() as db:
        job = db.query(ReportJob).filter(ReportJob.id == job_id).first()
        if job is None:
            logger.error("run_job: job %s not found", job_id)
            return
        if job.status != ReportJobStatus.PENDING:
            logger.warning(
                "run_job: job %s already in status %s; skipping",
                job_id, job.status,
            )
            return

        job.status = ReportJobStatus.RUNNING
        job.started_at = datetime.utcnow()
        db.flush()

        gen_cls = REPORT_REGISTRY.get(job.report_type)
        if gen_cls is None:
            _mark_failed(db, job, f"Unknown report type: {job.report_type}")
            return

        try:
            output = gen_cls().generate(
                job.project_id, db, dict(job.options or {}),
            )
        except Exception as exc:  # noqa: BLE001
            logger.exception("run_job %s failed", job_id)
            _mark_failed(db, job, f"{type(exc).__name__}: {exc}")
            return

        job.status = ReportJobStatus.COMPLETED
        job.result_blob = output.content
        job.result_filename = output.filename
        job.result_content_type = output.content_type
        job.result_metadata = _jsonable(output.metadata)
        job.completed_at = datetime.utcnow()


def get_job_for_user(
    db: Session, job_id: int, user: User,
) -> ReportJob:
    """Load a job; 404 if missing, 403 if user is not a project member."""
    job = db.query(ReportJob).filter(ReportJob.id == job_id).first()
    if job is None:
        raise HTTPException(404, "Report job not found")
    _check_membership(db, job.project_id, user)
    return job


def _mark_failed(db: Session, job: ReportJob, msg: str) -> None:
    job.status = ReportJobStatus.FAILED
    job.error_message = msg
    job.completed_at = datetime.utcnow()


def _jsonable(value: Any) -> Any:
    """Coerce report metadata into a JSON-serialisable dict."""
    if value is None:
        return None
    if isinstance(value, dict):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)
