"""
ASTRA — Dashboard router (F-040 N+1 fix)
==========================================
File: backend/app/routers/dashboard.py

Pre-fix `get_dashboard_stats` loaded every requirement into Python and
then issued a fresh `User` query inside the recent-activity loop —
~thousands of round-trips for moderate projects. This rewrite:

  * Uses GROUP BY for the by_status / by_type / by_level / verified
    aggregates (no Python iteration over every row).
  * Pulls trace-link counts via a subquery on
    `Requirement.project_id == X` instead of materialising IN-clauses
    of all req_ids (this also helps F-044's recommendation but only
    for the dashboard caller — the routers/projects.py list is
    handled by F-044 directly).
  * Batches all User lookups for the recent-activity payload into a
    single IN-clause query.
  * Drives recent_activity from a Requirement→RequirementHistory join
    so the per-row `next(... for r in reqs ...)` Python scan goes
    away.

Net query count is ~10 regardless of project size.
"""

from datetime import datetime
from typing import Iterable

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.project_access import project_member_required
from app.models import (
    Project, Requirement, RequirementHistory, SourceArtifact, TraceLink,
    User, Verification,
)
from app.schemas import DashboardStats
from app.services.auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


def _enum(v) -> str:
    return v.value if hasattr(v, "value") else str(v) if v else ""


def _user_map(db: Session, ids: Iterable[int]) -> dict[int, User]:
    """Load Users by id in a single IN query; returns {id: User}."""
    id_set = {i for i in ids if i is not None}
    if not id_set:
        return {}
    return {
        u.id: u for u in db.query(User).filter(User.id.in_(id_set)).all()
    }


@router.get("/stats", response_model=DashboardStats)
def get_dashboard_stats(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    """Aggregate dashboard statistics for a project."""

    # ── Base subquery: non-deleted requirements in this project ──
    req_id_sq = (
        db.query(Requirement.id)
        .filter(
            Requirement.project_id == project_id,
            Requirement.status != "deleted",
        )
        .subquery()
    )
    req_id_select = req_id_sq.select()  # for IN-style filters below

    # ── Total + average quality (single SQL query) ──
    total, avg_quality_raw = (
        db.query(
            func.count(Requirement.id),
            func.avg(func.coalesce(Requirement.quality_score, 0.0)),
        )
        .filter(
            Requirement.project_id == project_id,
            Requirement.status != "deleted",
        )
        .first()
    )
    total = int(total or 0)
    avg_quality = round(float(avg_quality_raw or 0.0), 1)

    # ── by_status / by_type / by_level via GROUP BY ──
    def _group(col) -> dict[str, int]:
        rows = (
            db.query(col, func.count(Requirement.id))
            .filter(
                Requirement.project_id == project_id,
                Requirement.status != "deleted",
            )
            .group_by(col)
            .all()
        )
        out: dict[str, int] = {}
        for value, count in rows:
            out[_enum(value)] = int(count or 0)
        return out

    by_status = _group(Requirement.status)
    by_type = _group(Requirement.req_type)
    by_level = _group(Requirement.level)

    # ── Verified count (single COUNT query, scoped via subquery) ──
    verified_count = (
        db.query(func.count(Verification.id))
        .filter(
            Verification.requirement_id.in_(req_id_select),
            Verification.status == "pass",
        )
        .scalar()
        or 0
    )

    # ── Trace links: count + orphan-id derivation ──
    # We need both totals AND the set of req-ids that appear in any
    # link, so a count is insufficient. But we can scope the link query
    # by the project's req_id subquery — no Python list materialisation.
    link_total = (
        db.query(func.count(TraceLink.id))
        .filter(
            ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_id_select)))
            | ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_id_select)))
        )
        .scalar()
        or 0
    )

    linked_req_ids: set[int] = set()
    if link_total:
        # Just the linked req_ids — pull source and target IDs separately
        # to avoid the OR-with-IN performance cliff on large projects.
        for (rid,) in (
            db.query(TraceLink.source_id)
            .filter(
                TraceLink.source_type == "requirement",
                TraceLink.source_id.in_(req_id_select),
            )
            .distinct()
            .all()
        ):
            linked_req_ids.add(rid)
        for (rid,) in (
            db.query(TraceLink.target_id)
            .filter(
                TraceLink.target_type == "requirement",
                TraceLink.target_id.in_(req_id_select),
            )
            .distinct()
            .all()
        ):
            linked_req_ids.add(rid)

    orphan_count = max(0, total - len(linked_req_ids))

    # ── Recent activity (last 20 history rows + their users) ──
    recent_activity: list[dict] = []
    history_rows = (
        db.query(RequirementHistory)
        .filter(RequirementHistory.requirement_id.in_(req_id_select))
        .order_by(RequirementHistory.changed_at.desc())
        .limit(20)
        .all()
    )
    if history_rows:
        # Batch-resolve req_id and user names so the loop is dict-only.
        req_id_by_pk: dict[int, str] = dict(
            db.query(Requirement.id, Requirement.req_id)
            .filter(
                Requirement.id.in_({h.requirement_id for h in history_rows}),
            )
            .all()
        )
        users = _user_map(db, (h.changed_by_id for h in history_rows))
        for h in history_rows:
            user = users.get(h.changed_by_id) if h.changed_by_id else None
            recent_activity.append({
                "req_id": req_id_by_pk.get(h.requirement_id, "?"),
                "field": h.field_changed,
                "old_value": h.old_value,
                "new_value": h.new_value,
                "description": h.change_description or f"{h.field_changed} updated",
                "user": user.full_name if user else "System",
                "timestamp": h.changed_at.isoformat() if h.changed_at else None,
            })

    # If no history yet, fall back to creation-based activity (top 10
    # most-recently-created requirements).
    if not recent_activity:
        recent_reqs = (
            db.query(Requirement)
            .filter(
                Requirement.project_id == project_id,
                Requirement.status != "deleted",
            )
            .order_by(
                func.coalesce(Requirement.created_at, datetime.min).desc(),
                Requirement.id.desc(),
            )
            .limit(10)
            .all()
        )
        owners = _user_map(db, (r.owner_id for r in recent_reqs))
        for r in recent_reqs:
            owner = owners.get(r.owner_id) if r.owner_id else None
            recent_activity.append({
                "req_id": r.req_id,
                "field": "created",
                "old_value": None,
                "new_value": _enum(r.status),
                "description": f"{r.req_id} created",
                "user": owner.full_name if owner else "System",
                "timestamp": r.created_at.isoformat() if r.created_at else None,
            })

    return DashboardStats(
        total_requirements=total,
        by_status=by_status,
        by_type=by_type,
        by_level=by_level,
        verified_count=int(verified_count),
        avg_quality_score=avg_quality,
        total_trace_links=int(link_total),
        orphan_count=orphan_count,
        recent_activity=recent_activity,
    )
