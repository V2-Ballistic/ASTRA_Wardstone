"""
ASTRA — Reports Router
========================
File: backend/app/routers/reports.py

Endpoints for every report type plus a persistent job/history surface.

Two paths to a report:

  1. **Synchronous** (existing GET endpoints, kept for the existing
     frontend download flow): the generator runs in-request, the file
     streams back, AND a COMPLETED row is written to ``report_jobs``
     so the same row that powers ``/reports/history`` lands for sync
     calls too.

  2. **Async** (F-019 fix for long-running reports): POST
     ``/reports/{report_type}/jobs`` enqueues a BackgroundTask, returns
     ``{job_id}`` immediately. Clients poll
     ``GET /reports/jobs/{id}`` and download via
     ``GET /reports/jobs/{id}/download``. Long-running PDF / DOCX
     generations no longer time out the worker pool.

The history list (``GET /reports/history``) is now backed by the
``report_jobs`` table — durable across restarts, shared across
workers, and project-membership-scoped (F-032).
"""

import io
import json
from datetime import datetime
from typing import Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, HTTPException, Query,
)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.project_access import (
    _check_membership,
    project_member_required,
)
from app.models import Project, User
from app.models.report_job import ReportJob, ReportJobStatus
from app.services.auth import get_current_user
from app.services.reports import REPORT_REGISTRY, ReportOutput
from app.services.reports.jobs import (
    create_pending_job, get_job_for_user, record_completed, run_job,
)

# Optional audit hook
try:
    from app.services.audit_service import record_event as _audit
except ImportError:
    def _audit(*a, **kw):
        pass

router = APIRouter(prefix="/reports", tags=["Reports"])


# ══════════════════════════════════════
#  Helpers
# ══════════════════════════════════════


def _stream(output: ReportOutput) -> StreamingResponse:
    """Convert a ReportOutput into a streaming download response."""
    return StreamingResponse(
        io.BytesIO(output.content),
        media_type=output.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{output.filename}"',
            "X-Report-Metadata": json.dumps(output.metadata, default=str),
        },
    )


def _stream_job(job: ReportJob) -> StreamingResponse:
    """Stream the persisted blob from a COMPLETED job."""
    if job.status != ReportJobStatus.COMPLETED or not job.result_blob:
        raise HTTPException(
            409, f"Job {job.id} is not downloadable (status={job.status.value if hasattr(job.status, 'value') else job.status})",
        )
    return StreamingResponse(
        io.BytesIO(job.result_blob),
        media_type=job.result_content_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{job.result_filename or "report.bin"}"',
            "X-Report-Metadata": json.dumps(job.result_metadata or {}, default=str),
        },
    )


def _persist_sync(
    db: Session, *, project_id: int, report_type: str, fmt: str,
    options: dict, user: User, output: ReportOutput,
) -> None:
    """Record a synchronous run as a COMPLETED report_jobs row."""
    record_completed(
        db,
        project_id=project_id,
        report_type=report_type,
        fmt=fmt,
        options=options,
        requested_by=user,
        output=output,
    )
    _audit(
        db, "report.generated", "project", project_id, user.id,
        {"report": report_type, "format": fmt}, project_id=project_id,
    )


# ══════════════════════════════════════
#  Synchronous report endpoints (existing frontend flow)
# ══════════════════════════════════════

@router.get("/traceability-matrix")
def report_traceability_matrix(
    project_id: int,
    format: str = Query("xlsx", pattern="^(xlsx|pdf|html)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    opts = {"format": format}
    output = REPORT_REGISTRY["traceability-matrix"]().generate(project_id, db, opts)
    _persist_sync(db, project_id=project_id, report_type="traceability-matrix",
                  fmt=format, options=opts, user=current_user, output=output)
    return _stream(output)


@router.get("/requirements-spec")
def report_requirements_spec(
    project_id: int,
    format: str = Query("docx", pattern="^(docx|pdf)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    opts = {"format": format}
    output = REPORT_REGISTRY["requirements-spec"]().generate(project_id, db, opts)
    _persist_sync(db, project_id=project_id, report_type="requirements-spec",
                  fmt=format, options=opts, user=current_user, output=output)
    return _stream(output)


@router.get("/quality")
def report_quality(
    project_id: int,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    opts = {"format": format}
    output = REPORT_REGISTRY["quality"]().generate(project_id, db, opts)
    _persist_sync(db, project_id=project_id, report_type="quality",
                  fmt=format, options=opts, user=current_user, output=output)
    return _stream(output)


@router.get("/compliance")
def report_compliance(
    project_id: int,
    framework: str = Query("nist-800-53"),
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    opts = {"format": format, "framework": framework}
    try:
        output = REPORT_REGISTRY["compliance"]().generate(project_id, db, opts)
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    _persist_sync(db, project_id=project_id, report_type="compliance",
                  fmt=format, options=opts, user=current_user, output=output)
    return _stream(output)


@router.get("/status-dashboard")
def report_status_dashboard(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    opts = {"format": "pdf"}
    output = REPORT_REGISTRY["status-dashboard"]().generate(project_id, db, opts)
    _persist_sync(db, project_id=project_id, report_type="status-dashboard",
                  fmt="pdf", options=opts, user=current_user, output=output)
    return _stream(output)


@router.get("/change-history")
def report_change_history(
    project_id: int,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    opts: dict = {"format": format}
    if date_from:
        opts["date_from"] = datetime.fromisoformat(date_from)
    if date_to:
        opts["date_to"] = datetime.fromisoformat(date_to)
    output = REPORT_REGISTRY["change-history"]().generate(project_id, db, opts)
    # Strip non-JSON-serialisable datetimes from options for the record
    persisted_opts = {
        k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in opts.items()
    }
    _persist_sync(db, project_id=project_id, report_type="change-history",
                  fmt=format, options=persisted_opts, user=current_user, output=output)
    return _stream(output)


# ── ICD report (interface control document — xlsx-only) ──
# F-119: kept here at the bottom of the sync block rather than
# alongside the other multi-format generators because it doesn't take
# a `format` query param (always xlsx). The sub-banner above makes
# the grouping explicit instead of implying it from physical proximity.
@router.get("/icd")
def report_icd(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    opts = {"format": "xlsx"}
    output = REPORT_REGISTRY["icd"]().generate(project_id, db, opts)
    _persist_sync(db, project_id=project_id, report_type="icd",
                  fmt="xlsx", options=opts, user=current_user, output=output)
    return _stream(output)


# ── Persistent generation history (F-032) ──
# F-131: kept under the sync-reports umbrella because the history view
# is paired with the sync endpoints in the UI (the "Reports" page lists
# what's been generated). Originally lived in its own banner block
# further down; promoted here so the /reports/* surface is ordered
# top-to-bottom by user-flow rather than by when the endpoint landed.
@router.get("/history")
def get_report_history(
    project_id: int = Query(...),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Return the project-scoped report-generation log. Backed by the
    ``report_jobs`` table — survives restarts and is consistent across
    workers (F-032). Membership is enforced (F-014).
    """
    _check_membership(db, project_id, current_user)

    base_q = (
        db.query(ReportJob)
        .filter(ReportJob.project_id == project_id)
        .order_by(ReportJob.created_at.desc())
    )
    total = base_q.count()
    rows = base_q.offset(skip).limit(limit).all()
    return {
        "total": total,
        "items": [r.to_summary() for r in rows],
    }


# ══════════════════════════════════════
#  Async job pattern (F-019)
# ══════════════════════════════════════

@router.post("/{report_type}/jobs", status_code=202)
def enqueue_report_job(
    report_type: str,
    project_id: int = Query(...),
    format: Optional[str] = Query(None),
    framework: Optional[str] = Query(None),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    background_tasks: BackgroundTasks = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enqueue a report generation job. Returns ``{job_id}`` immediately;
    the generator runs in a BackgroundTask. Poll
    ``GET /reports/jobs/{job_id}`` for status.
    """
    if report_type not in REPORT_REGISTRY:
        raise HTTPException(404, f"Unknown report type: {report_type}")

    _check_membership(db, project_id, current_user)

    # Default format per report type — mirrors the GET endpoints above.
    default_formats = {
        "requirements-spec": "docx",
        "status-dashboard": "pdf",
        "icd": "xlsx",
    }
    fmt = format or default_formats.get(report_type, "xlsx")

    options: dict = {"format": fmt}
    if framework:
        options["framework"] = framework
    if date_from:
        options["date_from"] = date_from
    if date_to:
        options["date_to"] = date_to

    job = create_pending_job(
        db,
        project_id=project_id,
        report_type=report_type,
        fmt=fmt,
        options=options,
        requested_by=current_user,
    )
    db.commit()  # ensure the row is visible before BackgroundTask runs
    job_id = job.id

    if background_tasks is not None:
        background_tasks.add_task(run_job, job_id)
    else:  # safety net for any caller passing background_tasks=None
        run_job(job_id)

    _audit(
        db, "report.enqueued", "project", project_id, current_user.id,
        {"report": report_type, "format": fmt, "job_id": job_id},
        project_id=project_id,
    )

    return {"job_id": job_id, "status": "pending"}


@router.get("/jobs/{job_id}")
def get_report_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = get_job_for_user(db, job_id, current_user)
    return job.to_summary()


@router.get("/jobs/{job_id}/download")
def download_report_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = get_job_for_user(db, job_id, current_user)
    return _stream_job(job)


# ══════════════════════════════════════
#  Available reports (for frontend catalog)
# ══════════════════════════════════════

@router.get("/catalog")
def get_report_catalog(current_user: User = Depends(get_current_user)):
    """Return metadata about all available report types."""
    return [
        {
            "key": "traceability-matrix",
            "name": "Traceability Matrix (RTM)",
            "description": "Full requirements-to-artifacts-to-verification traceability matrix with color-coded coverage status.",
            "formats": ["xlsx", "pdf", "html"],
            "icon": "Network",
        },
        {
            "key": "requirements-spec",
            "name": "Requirements Specification (SRS)",
            "description": "Formal IEEE 830 / ISO 29148 specification document with cover page, revision history, and grouped requirements.",
            "formats": ["docx", "pdf"],
            "icon": "FileText",
        },
        {
            "key": "quality",
            "name": "Quality Assessment",
            "description": "Quality score distribution, common issues, prohibited terms tracking, TBD/TBR counts, and improvement recommendations.",
            "formats": ["xlsx", "pdf"],
            "icon": "Shield",
        },
        {
            "key": "compliance",
            "name": "Compliance Matrix",
            "description": "Map requirements to compliance frameworks (NIST 800-53, MIL-STD-882E, DO-178C, ISO 29148) with gap analysis.",
            "formats": ["xlsx", "pdf"],
            "frameworks": ["nist-800-53", "mil-std-882e", "do-178c", "iso-29148"],
            "icon": "CheckSquare",
        },
        {
            "key": "status-dashboard",
            "name": "Status Dashboard",
            "description": "Project snapshot: requirement counts, verification progress, traceability coverage, baselines, and recent activity.",
            "formats": ["pdf"],
            "icon": "LayoutDashboard",
        },
        {
            "key": "change-history",
            "name": "Change History (CCB)",
            "description": "Detailed change log grouped by requirement, showing field diffs within a date range. For Configuration Control Board meetings.",
            "formats": ["xlsx", "pdf"],
            "icon": "History",
        },
        {
            "key": "icd",
            "name": "Interface Control Document (ICD)",
            "description": "Comprehensive ICD with N² matrix, unit catalog, connector pinouts, bus config, message catalog, wire harnesses, signal dictionary, environmental summary, and requirements trace.",
            "formats": ["xlsx"],
            "icon": "Cable",
        },
    ]
