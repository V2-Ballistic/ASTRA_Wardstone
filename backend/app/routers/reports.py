"""
ASTRA — Reports Router
========================
File: backend/app/routers/reports.py   ← NEW

Endpoints for every report type, plus report generation history
and a custom template save/load mechanism.

All endpoints return a streaming file download with the correct
Content-Disposition header so browsers trigger "Save As".
"""

import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
import io

from app.database import get_db
from app.models import User
from app.services.auth import get_current_user
from app.services.reports import REPORT_REGISTRY, ReportOutput

# Optional audit hook
try:
    from app.services.audit_service import record_event as _audit
except ImportError:
    def _audit(*a, **kw):
        pass

router = APIRouter(prefix="/reports", tags=["Reports"])

# ── In-memory report history (swap for DB table in production) ──
_report_history: list[dict] = []
_MAX_HISTORY = 200


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


def _log_generation(report_type: str, project_id: int, fmt: str,
                    user: User, meta: dict) -> None:
    """Record in the history log."""
    _report_history.insert(0, {
        "report_type": report_type,
        "project_id": project_id,
        "format": fmt,
        "user_id": user.id,
        "username": user.username,
        "user_full_name": user.full_name,
        "generated_at": datetime.utcnow().isoformat(),
        "metadata": meta,
    })
    if len(_report_history) > _MAX_HISTORY:
        _report_history.pop()


# ══════════════════════════════════════
#  Traceability Matrix
# ══════════════════════════════════════

@router.get("/traceability-matrix")
def report_traceability_matrix(
    project_id: int,
    format: str = Query("xlsx", pattern="^(xlsx|pdf|html)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gen = REPORT_REGISTRY["traceability-matrix"]()
    output = gen.generate(project_id, db, {"format": format})
    _log_generation("traceability-matrix", project_id, format, current_user, output.metadata)
    _audit(db, "report.generated", "project", project_id, current_user.id,
           {"report": "traceability-matrix", "format": format}, project_id=project_id)
    return _stream(output)


# ══════════════════════════════════════
#  Requirements Specification
# ══════════════════════════════════════

@router.get("/requirements-spec")
def report_requirements_spec(
    project_id: int,
    format: str = Query("docx", pattern="^(docx|pdf)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gen = REPORT_REGISTRY["requirements-spec"]()
    output = gen.generate(project_id, db, {"format": format})
    _log_generation("requirements-spec", project_id, format, current_user, output.metadata)
    _audit(db, "report.generated", "project", project_id, current_user.id,
           {"report": "requirements-spec", "format": format}, project_id=project_id)
    return _stream(output)


# ══════════════════════════════════════
#  Quality Report
# ══════════════════════════════════════

@router.get("/quality")
def report_quality(
    project_id: int,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gen = REPORT_REGISTRY["quality"]()
    output = gen.generate(project_id, db, {"format": format})
    _log_generation("quality", project_id, format, current_user, output.metadata)
    _audit(db, "report.generated", "project", project_id, current_user.id,
           {"report": "quality", "format": format}, project_id=project_id)
    return _stream(output)


# ══════════════════════════════════════
#  Compliance Matrix
# ══════════════════════════════════════

@router.get("/compliance")
def report_compliance(
    project_id: int,
    framework: str = Query("nist-800-53"),
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gen = REPORT_REGISTRY["compliance"]()
    try:
        output = gen.generate(project_id, db, {"format": format, "framework": framework})
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    _log_generation("compliance", project_id, format, current_user, output.metadata)
    _audit(db, "report.generated", "project", project_id, current_user.id,
           {"report": "compliance", "framework": framework, "format": format},
           project_id=project_id)
    return _stream(output)


# ══════════════════════════════════════
#  Status Dashboard
# ══════════════════════════════════════

@router.get("/status-dashboard")
def report_status_dashboard(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    gen = REPORT_REGISTRY["status-dashboard"]()
    output = gen.generate(project_id, db, {"format": "pdf"})
    _log_generation("status-dashboard", project_id, "pdf", current_user, output.metadata)
    _audit(db, "report.generated", "project", project_id, current_user.id,
           {"report": "status-dashboard"}, project_id=project_id)
    return _stream(output)


# ══════════════════════════════════════
#  Change History
# ══════════════════════════════════════

@router.get("/change-history")
def report_change_history(
    project_id: int,
    format: str = Query("xlsx", pattern="^(xlsx|pdf)$"),
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    opts: dict = {"format": format}
    if date_from:
        opts["date_from"] = datetime.fromisoformat(date_from)
    if date_to:
        opts["date_to"] = datetime.fromisoformat(date_to)

    gen = REPORT_REGISTRY["change-history"]()
    output = gen.generate(project_id, db, opts)
    _log_generation("change-history", project_id, format, current_user, output.metadata)
    _audit(db, "report.generated", "project", project_id, current_user.id,
           {"report": "change-history", "format": format}, project_id=project_id)
    return _stream(output)


# ══════════════════════════════════════
#  Report History
# ══════════════════════════════════════

@router.get("/history")
def get_report_history(
    project_id: Optional[int] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
):
    """Return the log of recently generated reports."""
    items = _report_history
    if project_id is not None:
        items = [h for h in items if h.get("project_id") == project_id]
    return {
        "total": len(items),
        "items": items[skip : skip + limit],
    }


# ══════════════════════════════════════
#  Available Reports (for frontend catalog)
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
    ]
