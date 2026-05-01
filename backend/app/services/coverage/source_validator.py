"""
ASTRA — Source Coverage Validator (per spec §13.3)
====================================================
File: backend/app/services/coverage/source_validator.py
                                              ← NEW (Phase 6, ASTRA-TDD-INTF-002)

Computes a per-project coverage report: for every requirement, decide whether
it has architectural source linkage (a ``RequirementSourceLink`` row, or a
covered ancestor reachable via parent_id / a ``decomposition`` /
``satisfaction`` ``TraceLink``), and assign a severity per the level rules in
spec §13.2:

  L1 orphan                                     → ok        (system-level; no source needed)
  L2 orphan, no traced parent                   → warning   (subsystem-level should usually trace)
  L2 orphan with traced parent                  → ok
  L3 orphan                                     → error     (component-level MUST trace)
  L3 with traced parent                         → ok
  L4 with traced parent (or direct source)      → ok
  L4 orphan no traced parent                    → error
  L5 with active admin-cosigned exception       → ok
  L5 with exception but NO admin co-sign        → warning
  L5 orphan, no exception, no parent trace      → error

Two execution modes:

* ``use_materialized_view=True`` (default) reads from
  ``mv_requirement_source_coverage`` (created in alembic 0025) — fast.
* ``use_materialized_view=False`` re-computes everything from raw tables.
  Slower but always current; the ``GET /coverage/source/.../?live=true``
  query string exposes this for callers that need fresh data while a
  refresh is in flight.

Integration notes
-----------------
* The MV uses the **actual** ``trace_links`` schema (polymorphic columns) per
  digest §10 anomaly #5 — the spec text references a non-existent
  ``target_requirement_id``. We map the spec's ``derives_from``/``refines``
  intent onto ``link_type IN ('decomposition','satisfaction')``.
* The ``CoverageException`` model uses ``approved_by_id``/``approved_at`` as
  the admin co-sign columns (the model was named pre-spec; the spec text
  refers to ``admin_cosigned_*``). We treat ``approved_by_id IS NOT NULL``
  as "admin cosigned" and only count active, non-expired exceptions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models import Requirement, RequirementStatus, TraceLink, TraceLinkType
from app.models.coverage_exception import CoverageException
from app.models.req_sync import RequirementSourceLink, SourceEntityType

logger = logging.getLogger("astra.coverage.validator")


# ══════════════════════════════════════════════════════════════
#  Public dataclasses
# ══════════════════════════════════════════════════════════════

@dataclass
class OrphanRequirement:
    req_id: int                                # PK
    req_text: str                              # human-facing identifier ("FR-001")
    title: str
    level: str                                 # L1..L5
    severity: str                              # 'ok' | 'warning' | 'error' (per §13.2)
    parent_id: Optional[int]
    parent_traced: bool
    suggested_source_type: Optional[str]       # from §13.5 suggestion engine
    has_active_exception: bool


@dataclass
class LevelSummary:
    level: str
    total: int = 0
    ok: int = 0
    warning: int = 0
    error: int = 0


@dataclass
class CoverageReport:
    project_id: int
    summary: Dict[str, LevelSummary] = field(default_factory=dict)
    orphans: List[OrphanRequirement] = field(default_factory=list)
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    used_materialized_view: bool = True
    exception_count: int = 0


# ══════════════════════════════════════════════════════════════
#  Severity rules (live mode helpers)
# ══════════════════════════════════════════════════════════════

_SEVERITY_OK = "ok"
_SEVERITY_WARNING = "warning"
_SEVERITY_ERROR = "error"

# Statuses that are entirely excluded from the report — a deleted requirement
# never raises a coverage error. Mirrors the WHERE clause in the MV.
_EXCLUDED_STATUSES = {"deleted"}


def _level_value(req: Requirement) -> str:
    return req.level.value if hasattr(req.level, "value") else str(req.level)


def _status_value(req: Requirement) -> str:
    return req.status.value if hasattr(req.status, "value") else str(req.status)


def _compute_severity(
    level: str,
    has_direct_source: bool,
    has_traced_parent: bool,
    has_admin_cosigned_exception: bool,
    has_pending_exception: bool,
) -> str:
    """Apply spec §13.2 severity rules.

    A "covered" L1 row is automatically OK. A direct source link or an admin-
    cosigned exception always promotes to OK. Otherwise level-specific
    fallbacks decide.
    """
    if level == "L1":
        return _SEVERITY_OK
    if has_direct_source:
        return _SEVERITY_OK
    if has_admin_cosigned_exception:
        return _SEVERITY_OK
    if level == "L2":
        return _SEVERITY_OK if has_traced_parent else _SEVERITY_WARNING
    if level in ("L4", "L5") and has_traced_parent:
        return _SEVERITY_OK
    if level == "L5" and has_pending_exception:
        return _SEVERITY_WARNING
    # L3, or L4/L5 with no traced parent and no exception
    return _SEVERITY_ERROR


# ══════════════════════════════════════════════════════════════
#  Live computation (slow path)
# ══════════════════════════════════════════════════════════════

def _live_coverage_state(
    db: Session, project_id: int,
) -> Tuple[
    List[Requirement],          # all requirements (non-deleted) for the project
    Set[int],                   # requirement_ids with ≥1 direct source link
    Set[int],                   # requirement_ids with a traced parent (via TraceLink)
    Set[int],                   # requirement_ids with an active admin-cosigned exception
    Set[int],                   # requirement_ids with an active but un-cosigned exception
]:
    """Compute the four coverage sets from raw tables.

    "Traced parent" = the requirement is the *source* of a
    ``decomposition``/``satisfaction`` ``TraceLink`` whose target is itself
    covered (direct source OR cosigned exception OR — recursively — has a
    traced parent). We walk a fixed-iteration BFS over the in-memory map
    rather than a recursive CTE so the live path also works on SQLite (the
    test harness).
    """
    reqs: List[Requirement] = (
        db.query(Requirement)
        .filter(
            Requirement.project_id == project_id,
            ~Requirement.status.in_(list(_EXCLUDED_STATUSES)),
        )
        .all()
    )
    if not reqs:
        return [], set(), set(), set(), set()
    req_ids = {r.id for r in reqs}

    # Direct source links
    src_rows = (
        db.query(RequirementSourceLink.requirement_id)
        .filter(RequirementSourceLink.requirement_id.in_(req_ids))
        .all()
    )
    direct: Set[int] = {row[0] for row in src_rows}

    # Active exceptions, split by admin co-sign (approved_by_id IS NOT NULL).
    now = datetime.now(timezone.utc)
    exc_rows = (
        db.query(CoverageException)
        .filter(
            CoverageException.project_id == project_id,
            CoverageException.is_active.is_(True),
        )
        .all()
    )
    cosigned: Set[int] = set()
    pending: Set[int] = set()
    for ex in exc_rows:
        # Expiry check — ``expires_at`` is timezone-aware in PG, may be naive
        # on SQLite. Normalize before comparison.
        exp = ex.expires_at
        if exp is not None and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp is not None and exp <= now:
            continue
        if ex.approved_by_id is not None:
            cosigned.add(ex.requirement_id)
        else:
            pending.add(ex.requirement_id)

    # Traced parents — walk decomposition/satisfaction links
    # (the spec's "derives_from" + "refines"; see digest §10 #5).
    decomp_value = TraceLinkType.DECOMPOSITION.value
    satis_value = TraceLinkType.SATISFACTION.value
    link_rows = (
        db.query(TraceLink.source_id, TraceLink.target_id)
        .filter(
            TraceLink.project_id == project_id,
            TraceLink.source_type == "requirement",
            TraceLink.target_type == "requirement",
            TraceLink.link_type.in_([decomp_value, satis_value]),
        )
        .all()
    )
    # Adjacency list: child -> set(parents)
    parents_map: Dict[int, Set[int]] = {}
    for src_id, tgt_id in link_rows:
        parents_map.setdefault(src_id, set()).add(tgt_id)

    # Also include the model's parent_id chain — the spec calls out parent_id
    # OR TraceLink as the trace graph (§13.3). A requirement whose parent is
    # itself traced should count as "covered via parent".
    for r in reqs:
        if r.parent_id is not None:
            parents_map.setdefault(r.id, set()).add(r.parent_id)

    # Iteratively expand "covered" until fixpoint.
    covered = set(direct) | set(cosigned)
    traced_parent: Set[int] = set()
    # Cap iterations to len(reqs) to guarantee termination even on a cycle.
    for _ in range(len(reqs) + 1):
        added_this_pass = False
        for child_id, parent_ids in parents_map.items():
            if child_id in covered:
                continue
            if any(pid in covered for pid in parent_ids):
                covered.add(child_id)
                traced_parent.add(child_id)
                added_this_pass = True
        if not added_this_pass:
            break

    return reqs, direct, traced_parent, cosigned, pending


# ══════════════════════════════════════════════════════════════
#  MV-backed computation (fast path)
# ══════════════════════════════════════════════════════════════

def _mv_coverage_state(
    db: Session, project_id: int,
) -> Optional[List[Tuple[int, str, bool, int, bool, bool, str]]]:
    """Read every row from ``mv_requirement_source_coverage`` for the project.

    Returns ``None`` if the MV doesn't exist (e.g., on SQLite during tests
    or before alembic 0025 has been applied). Caller falls back to the live
    path in that case.
    """
    try:
        rows = db.execute(
            text(
                """
                SELECT requirement_id,
                       level,
                       has_direct_source,
                       source_link_count,
                       has_traced_parent,
                       has_active_exception,
                       computed_severity
                  FROM mv_requirement_source_coverage
                 WHERE project_id = :pid
                """
            ),
            {"pid": project_id},
        ).fetchall()
    except Exception as exc:
        # Most likely "relation does not exist" on SQLite or a fresh DB.
        logger.debug("MV read failed (will fall back to live): %s", exc)
        return None
    return [tuple(r) for r in rows]


# ══════════════════════════════════════════════════════════════
#  Public entry point
# ══════════════════════════════════════════════════════════════

def validate_project_coverage(
    db: Session,
    project_id: int,
    use_materialized_view: bool = True,
) -> CoverageReport:
    """Build the per-level coverage report for *project_id*.

    *use_materialized_view=True* tries the MV first and silently falls back
    to the live path if the MV isn't available (test harness / pre-0025
    deployments). *False* always uses the live path.
    """
    # Suggestion engine is imported lazily to avoid a circular import — both
    # modules sit under app.services.coverage.
    from app.services.coverage.suggestions import suggest_source_type

    used_mv = False
    levels = ["L1", "L2", "L3", "L4", "L5"]
    summary: Dict[str, LevelSummary] = {lvl: LevelSummary(level=lvl) for lvl in levels}
    orphans: List[OrphanRequirement] = []

    mv_rows = (
        _mv_coverage_state(db, project_id) if use_materialized_view else None
    )

    if mv_rows is not None:
        used_mv = True
        # Bulk-load requirements + active exception ids for label/suggestion lookup.
        req_ids = [row[0] for row in mv_rows]
        if req_ids:
            req_lookup = {
                r.id: r
                for r in db.query(Requirement).filter(Requirement.id.in_(req_ids)).all()
            }
        else:
            req_lookup = {}
        active_exc_ids = _active_exception_ids(db, project_id)

        for (
            requirement_id, level, has_direct_source,
            source_link_count, has_traced_parent,
            has_active_exception, computed_severity,
        ) in mv_rows:
            r = req_lookup.get(requirement_id)
            if r is None:
                continue
            sev = str(computed_severity)
            ls = summary.setdefault(str(level), LevelSummary(level=str(level)))
            ls.total += 1
            if sev == _SEVERITY_OK:
                ls.ok += 1
            elif sev == _SEVERITY_WARNING:
                ls.warning += 1
            else:
                ls.error += 1
            if sev != _SEVERITY_OK:
                orphans.append(OrphanRequirement(
                    req_id=r.id,
                    req_text=r.req_id,
                    title=r.title,
                    level=str(level),
                    severity=sev,
                    parent_id=r.parent_id,
                    parent_traced=bool(has_traced_parent),
                    suggested_source_type=_suggestion_value(suggest_source_type(r)),
                    has_active_exception=bool(has_active_exception),
                ))
        return CoverageReport(
            project_id=project_id,
            summary=summary,
            orphans=orphans,
            used_materialized_view=used_mv,
            exception_count=len(active_exc_ids),
        )

    # ── Live path ──
    reqs, direct, traced_parent, cosigned, pending = _live_coverage_state(
        db, project_id,
    )
    for r in reqs:
        level = _level_value(r)
        has_direct = r.id in direct
        has_parent = r.id in traced_parent
        has_cosigned = r.id in cosigned
        has_pending = r.id in pending
        sev = _compute_severity(
            level=level,
            has_direct_source=has_direct,
            has_traced_parent=has_parent,
            has_admin_cosigned_exception=has_cosigned,
            has_pending_exception=has_pending,
        )
        ls = summary.setdefault(level, LevelSummary(level=level))
        ls.total += 1
        if sev == _SEVERITY_OK:
            ls.ok += 1
        elif sev == _SEVERITY_WARNING:
            ls.warning += 1
        else:
            ls.error += 1
        if sev != _SEVERITY_OK:
            orphans.append(OrphanRequirement(
                req_id=r.id,
                req_text=r.req_id,
                title=r.title,
                level=level,
                severity=sev,
                parent_id=r.parent_id,
                parent_traced=has_parent,
                suggested_source_type=_suggestion_value(suggest_source_type(r)),
                has_active_exception=has_cosigned or has_pending,
            ))
    return CoverageReport(
        project_id=project_id,
        summary=summary,
        orphans=orphans,
        used_materialized_view=used_mv,
        exception_count=len(cosigned) + len(pending),
    )


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════

def _suggestion_value(s: Optional[SourceEntityType]) -> Optional[str]:
    if s is None:
        return None
    return s.value if hasattr(s, "value") else str(s)


def _active_exception_ids(db: Session, project_id: int) -> Set[int]:
    """Requirement ids with an active (non-expired) CoverageException."""
    now = datetime.now(timezone.utc)
    rows = (
        db.query(CoverageException.requirement_id, CoverageException.expires_at)
        .filter(
            CoverageException.project_id == project_id,
            CoverageException.is_active.is_(True),
        )
        .all()
    )
    out: Set[int] = set()
    for req_id, exp in rows:
        if exp is not None and exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp is not None and exp <= now:
            continue
        out.add(req_id)
    return out
