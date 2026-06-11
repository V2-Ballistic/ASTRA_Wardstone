"""
ASTRA — Engineering Frame ICD Router
=====================================
File: backend/app/routers/engineering_frame.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §3)

Mounts at ``/api/v1/engineering/frame-icd``. The Frame ICD is the
CITADEL Vehicle Body Frame definition every other engineering surface
(motors, aero decks, vehicle configurations, config bundles)
references for its coordinate frame.

Endpoints
---------
  GET  /engineering/frame-icd/            current ICD + current (highest)
                                          revision; 404 until registered
  GET  /engineering/frame-icd/revisions   full immutable revision history
  POST /engineering/frame-icd/            idempotent ensure/register; body
                                          overrides that differ from the
                                          current revision create a NEW
                                          revision (never edit in place)

Auth: ``get_current_user`` — same global (non-project-scoped) gate as
the catalog router; the frame ICD is vehicle-level master data.

No HAROLD interaction here (the frame ICD is not a numbered part), so
handlers are plain ``def`` per convention.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.models.engineering_frame import CITADEL_FRAME_KEY, FrameIcd
from app.schemas.engineering_frame import (
    FrameIcdRegisterRequest,
    FrameIcdResponse,
    FrameIcdRevisionResponse,
    FrameIcdRevisionsResponse,
)
from app.services.auth import get_current_user
from app.services.engineering import frame as frame_svc

# Optional audit (same pattern as catalog router)
try:
    from app.services.audit_service import record_event as _audit
except ImportError:  # pragma: no cover - dev test fallback
    def _audit(*a, **kw):
        pass

router = APIRouter(prefix="/engineering/frame-icd", tags=["Engineering Frame ICD"])


def _icd_response(icd: FrameIcd) -> FrameIcdResponse:
    current = frame_svc.get_current_revision(icd)
    if current is None:  # defensive: header without revisions
        raise HTTPException(404, "Frame ICD has no revisions")
    return FrameIcdResponse(
        id=icd.id,
        key=icd.key,
        name=icd.name,
        created_at=icd.created_at,
        created_by_id=icd.created_by_id,
        current_rev=current.rev,
        revision=FrameIcdRevisionResponse.model_validate(current),
    )


def _get_icd_or_404(db: Session) -> FrameIcd:
    icd = db.query(FrameIcd).filter(FrameIcd.key == CITADEL_FRAME_KEY).first()
    if icd is None:
        raise HTTPException(
            404,
            "Frame ICD not registered yet — POST /engineering/frame-icd "
            "to register the CITADEL Vehicle Body Frame",
        )
    return icd


@router.get("/", response_model=FrameIcdResponse)
def get_current_frame_icd(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Current ICD + its current (highest-rev) revision."""
    return _icd_response(_get_icd_or_404(db))


@router.get("/revisions", response_model=FrameIcdRevisionsResponse)
def list_frame_icd_revisions(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full immutable revision history, ascending by rev."""
    icd = _get_icd_or_404(db)
    revisions = sorted(icd.revisions, key=lambda r: r.rev)
    return FrameIcdRevisionsResponse(
        icd_id=icd.id,
        key=icd.key,
        name=icd.name,
        total=len(revisions),
        revisions=[FrameIcdRevisionResponse.model_validate(r) for r in revisions],
    )


@router.post("/", response_model=FrameIcdResponse, status_code=200)
def register_frame_icd(
    data: FrameIcdRegisterRequest,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Idempotent ensure/register of the canonical CITADEL frame ICD.

    - Absent → creates the ICD with rev 1 (spec §3 defaults; body
      fields override the defaults).
    - Present, body matches current revision (or body empty) → returns
      the existing ICD/revision unchanged (idempotent).
    - Present, body differs from current revision → creates a NEW
      immutable revision at current_rev + 1.
    """
    icd, revision, created_icd, created_revision = frame_svc.ensure_frame(
        db,
        current_user.id,
        datum=data.datum,
        axes=data.axes,
        units=data.units,
        rules=data.rules,
        notes=data.notes,
    )

    if created_icd:
        _audit(
            db, "engineering.frame_icd.registered", "frame_icd", icd.id,
            current_user.id,
            {"key": icd.key, "rev": revision.rev, "datum": revision.datum},
            request=request,
        )
    elif created_revision:
        _audit(
            db, "engineering.frame_icd.revision_created", "frame_icd", icd.id,
            current_user.id,
            {"key": icd.key, "rev": revision.rev, "datum": revision.datum},
            request=request,
        )

    return _icd_response(icd)
