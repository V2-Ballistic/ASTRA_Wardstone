"""
ASTRA — Source Coverage HTTP Router (per spec §9.7)
=====================================================
File: backend/app/routers/coverage.py    ← NEW (Phase 6, ASTRA-TDD-INTF-002)

Mounted at ``/api/v1/coverage`` via ``main._optional_routers``. Endpoints:

    GET    /coverage/source/{project_id}
    GET    /coverage/source/{project_id}/orphans
    POST   /coverage/exception
    GET    /coverage/exceptions/{project_id}
    POST   /coverage/exceptions/{id}/cosign

RBAC:
  - any logged-in (project member)            → reads
  - proj_mgr+                                  → file exception
  - admin only                                 → cosign exception

All endpoints check project membership via :func:`_check_membership`. Audit
events fire on every state change (filed / cosigned / withdrawn).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.project_access import _check_membership
from app.models import Requirement, User, UserRole
from app.models.coverage_exception import CoverageException
from app.schemas.coverage import (
    CosignRequest,
    CoverageExceptionCreate,
    CoverageExceptionListResponse,
    CoverageExceptionResponse,
    CoverageReportResponse,
    LevelSeveritySummary,
    OrphanListResponse,
    OrphanRequirementResponse,
)
from app.services.auth import get_current_user
from app.services.coverage import validate_project_coverage

# Optional audit emitter — same pattern as req_sync router.
try:
    from app.services.audit_service import record_event as _audit
except ImportError:  # pragma: no cover
    def _audit(*a, **kw):  # type: ignore
        return None

logger = logging.getLogger("astra.coverage.router")

router = APIRouter(prefix="/coverage", tags=["Source Coverage"])


# ══════════════════════════════════════════════════════════════
#  RBAC helpers (mirrors req_sync.py)
# ══════════════════════════════════════════════════════════════

_PROJ_MGR_OR_ABOVE = {
    UserRole.ADMIN,
    UserRole.PROJECT_MANAGER,
}


def _user_role(user: User) -> Optional[UserRole]:
    try:
        return UserRole(user.role) if isinstance(user.role, str) else user.role
    except ValueError:
        return None


def _require_proj_mgr(user: User) -> None:
    role = _user_role(user)
    if role is None or role not in _PROJ_MGR_OR_ABOVE:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Requires project_manager role or above to file coverage exceptions",
        )


def _require_admin(user: User) -> None:
    if _user_role(user) != UserRole.ADMIN:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Admin role required to co-sign coverage exceptions",
        )


# ══════════════════════════════════════════════════════════════
#  GET /coverage/source/{project_id}
# ══════════════════════════════════════════════════════════════

@router.get(
    "/source/{project_id}",
    response_model=CoverageReportResponse,
)
def get_coverage_report(
    project_id: int,
    live: bool = Query(
        False,
        description="If true, recompute from raw tables instead of the MV. "
                    "Use during a long-running source-link write to see fresh data.",
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CoverageReportResponse:
    _check_membership(db, project_id, current_user)
    report = validate_project_coverage(
        db, project_id, use_materialized_view=not live,
    )
    summary_payload = {
        lvl: LevelSeveritySummary(
            total=ls.total, ok=ls.ok, warning=ls.warning, error=ls.error,
        )
        for lvl, ls in report.summary.items()
    }
    return CoverageReportResponse(
        project_id=report.project_id,
        summary=summary_payload,
        computed_at=report.computed_at,
        used_materialized_view=report.used_materialized_view,
        exception_count=report.exception_count,
    )


# ══════════════════════════════════════════════════════════════
#  GET /coverage/source/{project_id}/orphans
# ══════════════════════════════════════════════════════════════

@router.get(
    "/source/{project_id}/orphans",
    response_model=OrphanListResponse,
)
def get_coverage_orphans(
    project_id: int,
    severity: Optional[str] = Query(
        None,
        description="Filter to a single severity ('warning' or 'error'). "
                    "Default returns warning + error.",
    ),
    level: Optional[str] = Query(
        None, description="Filter to a single level (L1..L5).",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    live: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrphanListResponse:
    _check_membership(db, project_id, current_user)
    report = validate_project_coverage(
        db, project_id, use_materialized_view=not live,
    )
    items = report.orphans
    if severity:
        items = [o for o in items if o.severity == severity]
    if level:
        items = [o for o in items if o.level == level]
    total = len(items)
    page = items[offset : offset + limit]
    return OrphanListResponse(
        project_id=project_id,
        total=total,
        items=[
            OrphanRequirementResponse(
                requirement_id=o.req_id,
                req_text=o.req_text,
                title=o.title,
                level=o.level,
                severity=o.severity,
                parent_id=o.parent_id,
                parent_traced=o.parent_traced,
                suggested_source_type=o.suggested_source_type,
                has_active_exception=o.has_active_exception,
            )
            for o in page
        ],
    )


# ══════════════════════════════════════════════════════════════
#  POST /coverage/exception      (file a new exception)
# ══════════════════════════════════════════════════════════════

@router.post(
    "/exception",
    response_model=CoverageExceptionResponse,
    status_code=status.HTTP_201_CREATED,
)
def file_coverage_exception(
    body: CoverageExceptionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CoverageExceptionResponse:
    _require_proj_mgr(current_user)
    _check_membership(db, body.project_id, current_user)

    req = (
        db.query(Requirement)
        .filter(
            Requirement.id == body.requirement_id,
            Requirement.project_id == body.project_id,
        )
        .first()
    )
    if req is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "Requirement not found in this project",
        )

    # Supersede any existing active exception on the same requirement (the
    # uq_coverage_exception_req constraint forbids duplicates).
    existing = (
        db.query(CoverageException)
        .filter(
            CoverageException.project_id == body.project_id,
            CoverageException.requirement_id == body.requirement_id,
        )
        .first()
    )
    if existing is not None:
        existing.is_active = False
        existing.reason = body.reason
        existing.expires_at = body.expires_at
        existing.created_by_id = current_user.id
        # Re-filing resets the cosign — the new reason needs fresh review.
        existing.approved_by_id = None
        existing.approved_at = None
        existing.is_active = True
        ex = existing
    else:
        ex = CoverageException(
            project_id=body.project_id,
            requirement_id=body.requirement_id,
            reason=body.reason,
            expires_at=body.expires_at,
            is_active=True,
            created_by_id=current_user.id,
        )
        db.add(ex)
    db.commit()
    db.refresh(ex)

    try:
        _audit(
            db,
            event_type="coverage.exception_filed",
            entity_type="requirement",
            entity_id=req.id,
            user_id=current_user.id,
            project_id=body.project_id,
            action_detail={
                "exception_id": ex.id,
                "reason": body.reason,
                "expires_at": (
                    body.expires_at.isoformat() if body.expires_at else None
                ),
            },
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("audit emit failed: %s", exc)

    return CoverageExceptionResponse.model_validate(ex, from_attributes=True)


# ══════════════════════════════════════════════════════════════
#  GET /coverage/exceptions/{project_id}
# ══════════════════════════════════════════════════════════════

@router.get(
    "/exceptions/{project_id}",
    response_model=CoverageExceptionListResponse,
)
def list_coverage_exceptions(
    project_id: int,
    active_only: bool = Query(True),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CoverageExceptionListResponse:
    _check_membership(db, project_id, current_user)
    q = db.query(CoverageException).filter(
        CoverageException.project_id == project_id,
    )
    if active_only:
        q = q.filter(CoverageException.is_active.is_(True))
    total = q.count()
    rows = (
        q.order_by(CoverageException.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return CoverageExceptionListResponse(
        total=total,
        items=[
            CoverageExceptionResponse.model_validate(r, from_attributes=True)
            for r in rows
        ],
    )


# ══════════════════════════════════════════════════════════════
#  POST /coverage/exceptions/{id}/cosign
# ══════════════════════════════════════════════════════════════

@router.post(
    "/exceptions/{exception_id}/cosign",
    response_model=CoverageExceptionResponse,
)
def cosign_coverage_exception(
    exception_id: int,
    body: Optional[CosignRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CoverageExceptionResponse:
    _require_admin(current_user)
    ex = (
        db.query(CoverageException)
        .filter(CoverageException.id == exception_id)
        .first()
    )
    if ex is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Exception not found")
    _check_membership(db, ex.project_id, current_user)

    if not ex.is_active:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Cannot cosign an inactive exception",
        )

    ex.approved_by_id = current_user.id
    ex.approved_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(ex)

    try:
        _audit(
            db,
            event_type="coverage.exception_cosigned",
            entity_type="requirement",
            entity_id=ex.requirement_id,
            user_id=current_user.id,
            project_id=ex.project_id,
            action_detail={
                "exception_id": ex.id,
                "notes": body.notes if body else None,
            },
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("audit emit failed: %s", exc)

    return CoverageExceptionResponse.model_validate(ex, from_attributes=True)
