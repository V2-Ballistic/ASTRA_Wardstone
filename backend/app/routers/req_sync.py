"""
ASTRA — Reactive Requirement Sync — HTTP Router
================================================
File: backend/app/routers/req_sync.py    ← NEW (Phase 5, ASTRA-TDD-INTF-002)

Mounted at ``/api/v1/req-sync`` via ``main._optional_routers``. Endpoints
listed in spec §9.6:

    GET    /req-sync/proposals
    GET    /req-sync/proposals/{id}
    POST   /req-sync/proposals/{id}/accept
    POST   /req-sync/proposals/{id}/reject
    POST   /req-sync/proposals/bulk-accept
    POST   /req-sync/requirements/{req_id}/lock
    POST   /req-sync/requirements/{req_id}/unlock
    GET    /req-sync/requirements/{req_id}/sources

RBAC:
  - reviewer+   → list / detail / accept / reject / bulk-accept
  - req_eng+    → lock / unlock
  - any logged-in → sources

All project-scoped endpoints check membership against the requirement's
project_id (not a query/path project_id).

Spec/digest anomaly notes:
  - Bulk accept is atomic — one transaction wraps every application; if
    any single proposal raises, the whole batch rolls back (digest §11).
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.project_access import _check_membership
from app.models import Requirement, User, UserRole, RequirementHistory
from app.models.req_sync import (
    RequirementSourceLink,
    RequirementSyncProposal,
    SourceEntityType,
    SyncProposalStatus,
)
from app.schemas.req_sync import (
    BulkAcceptRequest,
    BulkProposalActionResponse,
    BulkProposalActionResult,
    RequirementSyncLockRequest,
    RequirementSyncProposalDetailResponse,
    RequirementSyncProposalResponse,
    RequirementSyncProposalReviewRequest,
    RequirementSourceLinkResponse,
    SourceLinksResponse,
    SyncProposalListResponse,
)
from app.services.auth import get_current_user

# Optional audit emitter
try:
    from app.services.audit_service import record_event as _audit
except ImportError:  # pragma: no cover
    def _audit(*a, **kw):  # type: ignore
        return None

logger = logging.getLogger("astra.req_sync.router")

router = APIRouter(prefix="/req-sync", tags=["Requirement Sync"])


# ══════════════════════════════════════════════════════════════
#  RBAC helpers — no rbac.py dependency, mirror what other routers do
# ══════════════════════════════════════════════════════════════

_REVIEWER_OR_ABOVE = {
    UserRole.ADMIN,
    UserRole.PROJECT_MANAGER,
    UserRole.REQUIREMENTS_ENGINEER,
    UserRole.REVIEWER,
}

_REQ_ENG_OR_ABOVE = {
    UserRole.ADMIN,
    UserRole.PROJECT_MANAGER,
    UserRole.REQUIREMENTS_ENGINEER,
}


def _user_role(user: User) -> Optional[UserRole]:
    try:
        return UserRole(user.role) if isinstance(user.role, str) else user.role
    except ValueError:
        return None


def _require_reviewer(user: User) -> None:
    role = _user_role(user)
    if role is None or role not in _REVIEWER_OR_ABOVE:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Requires reviewer role or above",
        )


def _require_req_eng(user: User) -> None:
    role = _user_role(user)
    if role is None or role not in _REQ_ENG_OR_ABOVE:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Requires requirements engineer role or above",
        )


def _is_admin(user: User) -> bool:
    return _user_role(user) == UserRole.ADMIN


def _load_requirement_or_404(db: Session, req_id: int) -> Requirement:
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if req is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Requirement not found")
    return req


def _load_proposal_or_404(db: Session, proposal_id: int) -> RequirementSyncProposal:
    p = (
        db.query(RequirementSyncProposal)
        .filter(RequirementSyncProposal.id == proposal_id)
        .first()
    )
    if p is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Proposal not found")
    return p


def _detail_view(
    proposal: RequirementSyncProposal,
    requirement: Optional[Requirement],
) -> RequirementSyncProposalDetailResponse:
    base = RequirementSyncProposalResponse.model_validate(
        proposal, from_attributes=True
    ).model_dump()
    base.update({
        "requirement_req_id": requirement.req_id if requirement else None,
        "requirement_title": requirement.title if requirement else None,
        "requirement_status": (
            requirement.status.value if requirement and hasattr(requirement.status, "value")
            else (str(requirement.status) if requirement else None)
        ),
        "requirement_level": (
            requirement.level.value if requirement and hasattr(requirement.level, "value")
            else (str(requirement.level) if requirement else None)
        ),
        "project_id": requirement.project_id if requirement else None,
    })
    return RequirementSyncProposalDetailResponse(**base)


# ══════════════════════════════════════════════════════════════
#  GET /proposals
# ══════════════════════════════════════════════════════════════

@router.get("/proposals", response_model=SyncProposalListResponse)
def list_proposals(
    request: Request,
    project_id: int = Query(..., description="Filter by project"),
    status_filter: Optional[str] = Query(
        None, alias="status",
        description="One of pending, accepted, rejected, auto_applied, superseded",
    ),
    trigger_entity_type: Optional[SourceEntityType] = Query(
        None, description="Filter by source entity type that triggered the proposal",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SyncProposalListResponse:
    """List proposals scoped to *project_id*. Pagination cap: 200."""
    _require_reviewer(current_user)
    _check_membership(db, project_id, current_user)

    q = (
        db.query(RequirementSyncProposal)
        .join(Requirement, Requirement.id == RequirementSyncProposal.requirement_id)
        .filter(Requirement.project_id == project_id)
    )
    if status_filter:
        q = q.filter(RequirementSyncProposal.status == status_filter)
    if trigger_entity_type:
        q = q.filter(
            RequirementSyncProposal.triggered_by_entity_type == trigger_entity_type
        )
    total = q.count()
    rows = (
        q.order_by(RequirementSyncProposal.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return SyncProposalListResponse(
        total=total,
        items=[
            RequirementSyncProposalResponse.model_validate(r, from_attributes=True)
            for r in rows
        ],
    )


# ══════════════════════════════════════════════════════════════
#  GET /proposals/{id}
# ══════════════════════════════════════════════════════════════

@router.get(
    "/proposals/{proposal_id}",
    response_model=RequirementSyncProposalDetailResponse,
)
def get_proposal(
    proposal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RequirementSyncProposalDetailResponse:
    _require_reviewer(current_user)
    proposal = _load_proposal_or_404(db, proposal_id)
    req = _load_requirement_or_404(db, proposal.requirement_id)
    _check_membership(db, req.project_id, current_user)
    return _detail_view(proposal, req)


# ══════════════════════════════════════════════════════════════
#  Internal apply / reject helpers (used by single + bulk endpoints)
# ══════════════════════════════════════════════════════════════

def _apply_proposal(
    db: Session,
    proposal: RequirementSyncProposal,
    requirement: Requirement,
    reviewer: User,
    notes: Optional[str] = None,
    *,
    admin_force: bool = False,
) -> None:
    """Apply *proposal* to *requirement*. Caller controls the transaction
    so bulk-accept can wrap multiple applies in one atomic flush."""
    if proposal.status != SyncProposalStatus.PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Proposal is {proposal.status.value if hasattr(proposal.status, 'value') else proposal.status}, not pending",
        )
    if requirement.sync_locked and not admin_force:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Requirement is sync_locked; use admin_force=true to override",
        )

    old_statement = requirement.statement
    if proposal.new_statement is not None:
        requirement.statement = proposal.new_statement
    if proposal.new_rationale is not None:
        requirement.rationale = proposal.new_rationale
    requirement.version = (requirement.version or 1) + 1
    requirement.updated_at = datetime.utcnow()

    proposal.status = SyncProposalStatus.ACCEPTED
    proposal.reviewed_at = datetime.utcnow()
    proposal.reviewed_by_id = reviewer.id
    proposal.reviewer_notes = notes

    # History row + audit event
    try:
        hist = RequirementHistory(
            requirement_id=requirement.id,
            version=requirement.version,
            field_changed="statement",
            old_value=old_statement,
            new_value=requirement.statement,
            changed_by_id=reviewer.id,
            change_description=(
                f"Sync proposal #{proposal.id} accepted "
                f"(triggered by {proposal.triggered_by_entity_type.value if hasattr(proposal.triggered_by_entity_type, 'value') else proposal.triggered_by_entity_type})"
            ),
        )
        db.add(hist)
    except Exception as exc:  # pragma: no cover
        logger.warning("history insert failed: %s", exc)

    try:
        _audit(
            db,
            event_type="req_sync.proposal.accepted",
            entity_type="requirement",
            entity_id=requirement.id,
            user_id=reviewer.id,
            project_id=requirement.project_id,
            action_detail={
                "proposal_id": proposal.id,
                "admin_force": admin_force,
                "old_statement": old_statement,
                "new_statement": requirement.statement,
            },
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("audit emit failed: %s", exc)


# ══════════════════════════════════════════════════════════════
#  POST /proposals/{id}/accept
# ══════════════════════════════════════════════════════════════

@router.post(
    "/proposals/{proposal_id}/accept",
    response_model=RequirementSyncProposalDetailResponse,
)
def accept_proposal(
    proposal_id: int,
    body: Optional[RequirementSyncProposalReviewRequest] = None,
    admin_force: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RequirementSyncProposalDetailResponse:
    _require_reviewer(current_user)
    proposal = _load_proposal_or_404(db, proposal_id)
    req = _load_requirement_or_404(db, proposal.requirement_id)
    _check_membership(db, req.project_id, current_user)

    if admin_force and not _is_admin(current_user):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "admin_force=true requires admin role",
        )

    notes = body.reviewer_notes if body else None
    _apply_proposal(
        db, proposal, req, current_user,
        notes=notes,
        admin_force=admin_force or (body.admin_force if body else False),
    )
    db.commit()
    db.refresh(proposal)
    db.refresh(req)
    return _detail_view(proposal, req)


# ══════════════════════════════════════════════════════════════
#  POST /proposals/{id}/reject
# ══════════════════════════════════════════════════════════════

@router.post(
    "/proposals/{proposal_id}/reject",
    response_model=RequirementSyncProposalDetailResponse,
)
def reject_proposal(
    proposal_id: int,
    body: Optional[RequirementSyncProposalReviewRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> RequirementSyncProposalDetailResponse:
    _require_reviewer(current_user)
    proposal = _load_proposal_or_404(db, proposal_id)
    req = _load_requirement_or_404(db, proposal.requirement_id)
    _check_membership(db, req.project_id, current_user)

    if proposal.status != SyncProposalStatus.PENDING:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Only pending proposals can be rejected",
        )

    proposal.status = SyncProposalStatus.REJECTED
    proposal.reviewed_at = datetime.utcnow()
    proposal.reviewed_by_id = current_user.id
    proposal.reviewer_notes = body.reviewer_notes if body else None

    db.commit()
    try:
        _audit(
            db,
            event_type="req_sync.proposal.rejected",
            entity_type="requirement",
            entity_id=req.id,
            user_id=current_user.id,
            project_id=req.project_id,
            action_detail={
                "proposal_id": proposal.id,
                "reason": (body.reviewer_notes if body else None),
            },
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("audit emit failed: %s", exc)

    db.refresh(proposal)
    return _detail_view(proposal, req)


# ══════════════════════════════════════════════════════════════
#  POST /proposals/bulk-accept
# ══════════════════════════════════════════════════════════════

@router.post(
    "/proposals/bulk-accept",
    response_model=BulkProposalActionResponse,
)
def bulk_accept_proposals(
    body: BulkAcceptRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BulkProposalActionResponse:
    """Apply every proposal in *body.proposal_ids* atomically.

    All-or-none: if one proposal application raises, the entire batch
    rolls back and ``failed`` reports the offending entry.
    """
    _require_reviewer(current_user)

    if not body.proposal_ids:
        return BulkProposalActionResponse(total=0, succeeded=0, failed=0, results=[])
    if len(body.proposal_ids) > 200:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Bulk accept capped at 200 proposals per request",
        )

    proposals = (
        db.query(RequirementSyncProposal)
        .filter(RequirementSyncProposal.id.in_(body.proposal_ids))
        .all()
    )
    found_ids = {p.id for p in proposals}
    missing = [pid for pid in body.proposal_ids if pid not in found_ids]
    if missing:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Proposal(s) not found: {missing}",
        )

    # Pre-load requirements + check membership for every project involved.
    requirement_ids = list({p.requirement_id for p in proposals})
    requirements = (
        db.query(Requirement)
        .filter(Requirement.id.in_(requirement_ids))
        .all()
    )
    req_by_id = {r.id: r for r in requirements}
    seen_projects = set()
    for r in requirements:
        if r.project_id in seen_projects:
            continue
        _check_membership(db, r.project_id, current_user)
        seen_projects.add(r.project_id)

    results: List[BulkProposalActionResult] = []
    try:
        for p in proposals:
            req = req_by_id.get(p.requirement_id)
            if req is None:
                raise HTTPException(404, f"Requirement {p.requirement_id} not found")
            _apply_proposal(
                db, p, req, current_user,
                notes=body.reviewer_notes,
                admin_force=False,
            )
            results.append(BulkProposalActionResult(
                proposal_id=p.id, success=True,
            ))
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        logger.exception("bulk_accept_proposals failed: %s", exc)
        # Roll back the partial result list — atomic semantics.
        return BulkProposalActionResponse(
            total=len(body.proposal_ids),
            succeeded=0,
            failed=len(body.proposal_ids),
            results=[
                BulkProposalActionResult(
                    proposal_id=pid, success=False, error=str(exc),
                )
                for pid in body.proposal_ids
            ],
        )

    try:
        for p in proposals:
            _audit(
                db,
                event_type="req_sync.proposal.bulk_accepted",
                entity_type="requirement",
                entity_id=p.requirement_id,
                user_id=current_user.id,
                project_id=req_by_id[p.requirement_id].project_id,
                action_detail={"proposal_id": p.id, "batch_size": len(proposals)},
            )
    except Exception as exc:  # pragma: no cover
        logger.warning("bulk audit emit failed: %s", exc)

    # Phase 6 — refresh the coverage MV ONCE per batch (not per proposal).
    # Bulk accept can rewrite many requirements at once and any of them might
    # have toggled source-link coverage; this keeps /coverage reads fast
    # without paying the refresh cost N times.
    try:
        from app.services.coverage.refresh import refresh_coverage_mv
        refresh_coverage_mv(db, concurrent=True)
    except Exception as exc:  # pragma: no cover
        logger.warning("coverage MV refresh after bulk-accept failed: %s", exc)

    return BulkProposalActionResponse(
        total=len(proposals),
        succeeded=len(results),
        failed=0,
        results=results,
    )


# ══════════════════════════════════════════════════════════════
#  POST /requirements/{req_id}/lock
#  POST /requirements/{req_id}/unlock
# ══════════════════════════════════════════════════════════════

@router.post("/requirements/{req_id}/lock")
def lock_requirement(
    req_id: int,
    body: Optional[RequirementSyncLockRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_req_eng(current_user)
    req = _load_requirement_or_404(db, req_id)
    _check_membership(db, req.project_id, current_user)

    req.sync_locked = True
    req.sync_locked_by_id = current_user.id
    req.sync_locked_at = datetime.utcnow()
    req.sync_locked_reason = body.reason if body else None
    db.commit()
    try:
        _audit(
            db,
            event_type="req_sync.requirement.locked",
            entity_type="requirement",
            entity_id=req.id,
            user_id=current_user.id,
            project_id=req.project_id,
            action_detail={"reason": req.sync_locked_reason},
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("audit emit failed: %s", exc)
    db.refresh(req)
    return {
        "requirement_id": req.id,
        "sync_locked": req.sync_locked,
        "sync_locked_by_id": req.sync_locked_by_id,
        "sync_locked_at": req.sync_locked_at,
        "sync_locked_reason": req.sync_locked_reason,
    }


@router.post("/requirements/{req_id}/unlock")
def unlock_requirement(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_req_eng(current_user)
    req = _load_requirement_or_404(db, req_id)
    _check_membership(db, req.project_id, current_user)

    req.sync_locked = False
    req.sync_locked_by_id = None
    req.sync_locked_at = None
    req.sync_locked_reason = None
    db.commit()
    try:
        _audit(
            db,
            event_type="req_sync.requirement.unlocked",
            entity_type="requirement",
            entity_id=req.id,
            user_id=current_user.id,
            project_id=req.project_id,
            action_detail={},
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("audit emit failed: %s", exc)
    db.refresh(req)
    return {
        "requirement_id": req.id,
        "sync_locked": req.sync_locked,
    }


# ══════════════════════════════════════════════════════════════
#  GET /requirements/{req_id}/sources
# ══════════════════════════════════════════════════════════════

@router.get(
    "/requirements/{req_id}/sources",
    response_model=SourceLinksResponse,
)
def get_requirement_sources(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SourceLinksResponse:
    """Return every RequirementSourceLink attached to *req_id*. Any logged-
    in user that's a project member can read this."""
    req = _load_requirement_or_404(db, req_id)
    _check_membership(db, req.project_id, current_user)

    links = (
        db.query(RequirementSourceLink)
        .filter(RequirementSourceLink.requirement_id == req_id)
        .order_by(RequirementSourceLink.id.asc())
        .all()
    )
    return SourceLinksResponse(
        requirement_id=req_id,
        items=[
            RequirementSourceLinkResponse.model_validate(l, from_attributes=True)
            for l in links
        ],
    )
