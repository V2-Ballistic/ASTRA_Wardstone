"""
ASTRA — Projects & Traceability Router (Audit-Instrumented)
=============================================================
File: backend/app/routers/projects.py

Routers:
  projects_router      — /projects
  traceability_router  — /traceability (links, matrix, graph, coverage)
  artifacts_router     — /artifacts
"""

import os
from typing import List, Optional
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.project_access import (
    _check_membership,
    project_member_required,
)
from app.models import Project, User, TraceLink, Requirement, SourceArtifact, Verification
from app.models.project_member import ProjectMember
from app.schemas import (
    ProjectCreate, ProjectResponse,
    TraceLinkCreate, TraceLinkResponse,
    SourceArtifactCreate, SourceArtifactResponse, SourceArtifactUpdate,
    RequirementResponse,
)
from app.services.auth import get_current_user
from app.services.audit_service import record_event

try:
    from app.services.rbac import require_permission
except ImportError:
    def require_permission(action):
        return get_current_user


def _ev(v):
    """Enum-safe value extraction."""
    return v.value if hasattr(v, "value") else str(v) if v else ""


# ══════════════════════════════════════
#  Projects
# ══════════════════════════════════════

projects_router = APIRouter(prefix="/projects", tags=["Projects"])


@projects_router.get("/", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    """
    List projects visible to the caller. AUDIT_FINDINGS F-014: previously
    returned every project to every authenticated user. Now scoped to:
      - ADMIN: all projects
      - others: projects owned by the user OR projects where the user
        appears in project_members.
    """
    from app.models import UserRole

    role = current_user.role if isinstance(current_user.role, UserRole) else None
    try:
        role = UserRole(current_user.role) if not isinstance(current_user.role, UserRole) else current_user.role
    except (ValueError, TypeError):
        role = None

    if role == UserRole.ADMIN:
        return db.query(Project).all()

    member_pids = [
        row[0]
        for row in db.query(ProjectMember.project_id).filter(
            ProjectMember.user_id == current_user.id
        ).all()
    ]
    return (
        db.query(Project)
        .filter(
            (Project.owner_id == current_user.id)
            | (Project.id.in_(member_pids))
        )
        .all()
    )


@projects_router.post("/", response_model=ProjectResponse, status_code=201)
def create_project(data: ProjectCreate, request: Request,
                   db: Session = Depends(get_db),
                   current_user: User = Depends(require_permission("projects.create"))):
    if db.query(Project).filter(Project.code == data.code).first():
        raise HTTPException(400, "Project code already exists")
    project = Project(**data.model_dump(), owner_id=current_user.id)
    db.add(project)
    db.commit()
    db.refresh(project)

    record_event(db, "project.created", "project", project.id, current_user.id,
                 {"code": project.code, "name": project.name},
                 project_id=project.id, request=request)
    return project


@projects_router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db),
                current_user: User = Depends(get_current_user),
                project: Project = Depends(project_member_required)):
    return project


# ══════════════════════════════════════
#  Traceability
# ══════════════════════════════════════

traceability_router = APIRouter(prefix="/traceability", tags=["Traceability"])


@traceability_router.get("/links", response_model=List[TraceLinkResponse])
def list_trace_links(
    project_id: int,
    source_type: Optional[str] = None, target_type: Optional[str] = None,
    link_type: Optional[str] = None,
    skip: int = 0,
    limit: int = 200,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    """F-044: pre-fix this loaded all Requirement.id and
    SourceArtifact.id for the project into Python, then sent two
    OR'd IN-clauses (4 IN expressions total) to TraceLink — risking
    Postgres parameter limits on large projects and returning unbounded
    rows.

    F-035 added `trace_links.project_id`, so the filter is now one
    indexed column comparison plus optional secondary filters.
    Pagination is enforced server-side (default 200, hard cap 200 per
    the platform standard)."""
    if limit > 200:
        limit = 200
    if skip < 0:
        skip = 0

    query = db.query(TraceLink).filter(TraceLink.project_id == project_id)
    if source_type:
        query = query.filter(TraceLink.source_type == source_type)
    if target_type:
        query = query.filter(TraceLink.target_type == target_type)
    if link_type:
        query = query.filter(TraceLink.link_type == link_type)

    return (
        query.order_by(TraceLink.id)
        .offset(skip)
        .limit(limit)
        .all()
    )


def _resolve_entity_project(db: Session, entity_type: str, entity_id: int) -> int | None:
    """
    Polymorphic project_id resolver for trace-link endpoints. Returns
    the project_id of the entity, or ``None`` if the entity doesn't
    exist (or its type is unsupported).
    """
    from app.models import Verification  # local import — avoids cycles

    if entity_type == "requirement":
        row = db.query(Requirement.project_id).filter(Requirement.id == entity_id).first()
    elif entity_type == "source_artifact":
        row = db.query(SourceArtifact.project_id).filter(SourceArtifact.id == entity_id).first()
    elif entity_type == "verification":
        # verifications.project_id lives via the parent requirement.
        row = (
            db.query(Requirement.project_id)
            .join(Verification, Verification.requirement_id == Requirement.id)
            .filter(Verification.id == entity_id)
            .first()
        )
    else:
        return None
    return row[0] if row else None


@traceability_router.post("/links", response_model=TraceLinkResponse, status_code=201)
def create_trace_link(data: TraceLinkCreate, request: Request,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission("traceability.create"))):
    # F-035: full integrity validation.
    #   1. Source AND target entities must exist (no dangling refs).
    #   2. Both must live in the SAME project (no cross-project links).
    #   3. Caller must be a member of that project (F-014).
    #   4. The (source, target, link_type) tuple must be unique
    #      (uq_trace_link_endpoints — enforced by DB; we pre-check
    #      to return a friendly 409 instead of an IntegrityError 500).
    src_pid = _resolve_entity_project(db, data.source_type, data.source_id)
    if src_pid is None:
        raise HTTPException(
            400,
            f"Source {data.source_type}:{data.source_id} does not exist or "
            "has no resolvable project.",
        )
    tgt_pid = _resolve_entity_project(db, data.target_type, data.target_id)
    if tgt_pid is None:
        raise HTTPException(
            400,
            f"Target {data.target_type}:{data.target_id} does not exist or "
            "has no resolvable project.",
        )
    if src_pid != tgt_pid:
        raise HTTPException(
            400,
            f"Trace link endpoints span projects (source project {src_pid} → "
            f"target project {tgt_pid}); cross-project links are not allowed.",
        )

    _check_membership(db, src_pid, current_user)

    duplicate = (
        db.query(TraceLink.id)
        .filter(
            TraceLink.source_type == data.source_type,
            TraceLink.source_id == data.source_id,
            TraceLink.target_type == data.target_type,
            TraceLink.target_id == data.target_id,
            TraceLink.link_type == data.link_type,
        )
        .first()
    )
    if duplicate:
        raise HTTPException(
            409,
            f"A {data.link_type} link from {data.source_type}:{data.source_id} "
            f"to {data.target_type}:{data.target_id} already exists.",
        )

    link = TraceLink(
        **data.model_dump(),
        project_id=src_pid,
        created_by_id=current_user.id,
    )
    db.add(link)
    db.commit()
    db.refresh(link)

    record_event(db, "trace_link.created", "trace_link", link.id, current_user.id,
                 {"source": f"{data.source_type}:{data.source_id}",
                  "target": f"{data.target_type}:{data.target_id}",
                  "link_type": data.link_type},
                 project_id=src_pid, request=request)
    return link


@traceability_router.delete("/links/{link_id}", status_code=204)
def delete_trace_link(link_id: int, request: Request,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission("traceability.delete"))):
    link = db.query(TraceLink).filter(TraceLink.id == link_id).first()
    if not link:
        raise HTTPException(404, "Trace link not found")

    detail = {"source": f"{link.source_type}:{link.source_id}",
              "target": f"{link.target_type}:{link.target_id}"}
    db.delete(link)
    db.commit()

    record_event(db, "trace_link.deleted", "trace_link", link_id, current_user.id,
                 detail, request=request)


# ── Matrix ──

@traceability_router.get("/matrix")
def get_traceability_matrix(project_id: int, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user),
                            project: Project = Depends(project_member_required)):
    reqs = db.query(Requirement).filter(
        Requirement.project_id == project_id, Requirement.status != "deleted"
    ).order_by(Requirement.req_id).all()
    req_ids = [r.id for r in reqs]
    links = []
    if req_ids:
        links = db.query(TraceLink).filter(
            ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids))) |
            ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids)))
        ).all()
    children_map: dict = {}
    for r in reqs:
        if r.parent_id and r.parent_id in req_ids:
            children_map.setdefault(r.parent_id, []).append(r.id)
    verifications: dict = {}
    if req_ids:
        for v in db.query(Verification).filter(Verification.requirement_id.in_(req_ids)).all():
            verifications.setdefault(v.requirement_id, []).append(v.id)
    matrix = []
    for req in reqs:
        req_links = [l for l in links if l.source_id == req.id or l.target_id == req.id]
        level_str = req.level.value if hasattr(req.level, "value") else str(req.level) if req.level else "L1"
        status_str = req.status.value if hasattr(req.status, "value") else str(req.status)
        priority_str = req.priority.value if hasattr(req.priority, "value") else str(req.priority)
        src_arts = [l.source_id for l in req_links if l.source_type == "source_artifact"]
        child_ids = children_map.get(req.id, [])
        ver_ids = verifications.get(req.id, [])
        test_lnk = [l.target_id for l in req_links if l.target_type == "verification"]
        matrix.append({
            "id": req.id, "req_id": req.req_id, "title": req.title,
            "level": level_str, "status": status_str, "priority": priority_str,
            "parent_id": req.parent_id,
            "source_artifacts": src_arts, "source_artifact_count": len(src_arts),
            "children": child_ids, "children_count": len(child_ids),
            "verifications": ver_ids, "verification_count": len(ver_ids),
            "test_links": test_lnk, "test_count": len(test_lnk),
            "total_links": len(req_links),
        })
    return {"project_id": project_id, "requirements_count": len(reqs), "matrix": matrix}


# ── Graph ──

@traceability_router.get("/graph")
def get_traceability_graph(project_id: int, db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user),
                           project: Project = Depends(project_member_required)):
    reqs = db.query(Requirement).filter(
        Requirement.project_id == project_id, Requirement.status != "deleted"
    ).all()
    req_ids = [r.id for r in reqs]
    links = db.query(TraceLink).filter(
        ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids))) |
        ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids)))
    ).all() if req_ids else []
    nodes = [{
        "id": r.id, "req_id": r.req_id, "title": r.title,
        "level": r.level.value if hasattr(r.level, "value") else str(r.level) if r.level else "L1",
        "status": r.status.value if hasattr(r.status, "value") else str(r.status),
        "parent_id": r.parent_id, "quality_score": r.quality_score or 0,
    } for r in reqs]
    edges = [{
        "source": l.source_id, "target": l.target_id,
        "source_type": l.source_type, "target_type": l.target_type,
        "link_type": l.link_type.value if hasattr(l.link_type, "value") else str(l.link_type),
    } for l in links]
    for r in reqs:
        if r.parent_id and r.parent_id in req_ids:
            edges.append({"source": r.parent_id, "target": r.id,
                          "source_type": "requirement", "target_type": "requirement",
                          "link_type": "parent_child"})
    return {"nodes": nodes, "edges": edges}


# ── Coverage ──

@traceability_router.get("/coverage")
def get_coverage_stats(project_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user),
                       project: Project = Depends(project_member_required)):
    """
    Compute coverage statistics for a project.

    Returns counts and percentages for:
      - with_source:       reqs traced back to at least one source artifact
      - with_children:     reqs that have at least one child (decomposition)
      - with_verification: reqs that have at least one verification record
      - orphans:           reqs with NO trace links at all

    Also returns legacy fields (forward_coverage, backward_coverage,
    verification_coverage) for backward compatibility with the landing page.
    """
    reqs = db.query(Requirement).filter(
        Requirement.project_id == project_id, Requirement.status != "deleted"
    ).all()
    req_ids = [r.id for r in reqs]
    req_id_set = set(req_ids)
    t = len(req_ids)

    empty = {
        "project_id": project_id, "total_requirements": 0, "total": 0,
        "with_source": 0, "with_source_pct": 0.0,
        "with_children": 0, "with_children_pct": 0.0,
        "with_verification": 0, "with_verification_pct": 0.0,
        "orphans": 0, "orphan_pct": 0.0,
        "forward_traced": 0, "backward_traced": 0, "verified": 0,
        "forward_coverage": 0.0, "backward_coverage": 0.0,
        "verification_coverage": 0.0,
    }
    if not req_ids:
        return empty

    # ── Load all relevant trace links ──
    # Include links where a source_artifact points to a requirement
    art_ids = [a.id for a in db.query(SourceArtifact.id).filter(
        SourceArtifact.project_id == project_id
    ).all()]

    links = db.query(TraceLink).filter(
        ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids))) |
        ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids))) |
        ((TraceLink.source_type == "source_artifact") & (TraceLink.source_id.in_(art_ids)))
    ).all()

    # ── Categorize ──
    # Reqs that have at least one source artifact tracing to them
    with_source_ids: set = set()
    # Reqs that have at least one child (via parent_id OR decomposition link)
    with_children_ids: set = set()
    # Reqs that participate in ANY trace link (for orphan detection)
    linked_ids: set = set()

    for link in links:
        src_type = link.source_type
        tgt_type = link.target_type
        link_type = _ev(link.link_type)

        # Track all linked requirement IDs (for orphan detection)
        if src_type == "requirement" and link.source_id in req_id_set:
            linked_ids.add(link.source_id)
        if tgt_type == "requirement" and link.target_id in req_id_set:
            linked_ids.add(link.target_id)

        # With source: source_artifact → requirement
        if src_type == "source_artifact" and tgt_type == "requirement":
            if link.target_id in req_id_set:
                with_source_ids.add(link.target_id)

        # With children: decomposition links (parent → child)
        if link_type == "decomposition":
            if src_type == "requirement" and link.source_id in req_id_set:
                with_children_ids.add(link.source_id)

    # Also count parent_id relationships as "with_children"
    for req in reqs:
        if req.parent_id and req.parent_id in req_id_set:
            with_children_ids.add(req.parent_id)

    # ── Verification coverage ──
    verified_ids: set = set()
    if req_ids:
        verif_rows = db.query(Verification.requirement_id).filter(
            Verification.requirement_id.in_(req_ids)
        ).distinct().all()
        verified_ids = {v[0] for v in verif_rows}

    # ── Orphans: no trace links AND no verifications AND no children ──
    orphan_ids = req_id_set - linked_ids - verified_ids
    # Also remove reqs that have children via parent_id (they're connected)
    parent_ids = {r.parent_id for r in reqs if r.parent_id and r.parent_id in req_id_set}
    child_ids_set = {r.id for r in reqs if r.parent_id and r.parent_id in req_id_set}
    orphan_ids = orphan_ids - parent_ids - child_ids_set

    # ── Compute counts and percentages ──
    with_source = len(with_source_ids)
    with_children = len(with_children_ids)
    with_verification = len(verified_ids)
    orphans = len(orphan_ids)

    def pct(n):
        return round(n / t * 100, 1) if t else 0.0

    return {
        "project_id": project_id,
        "total_requirements": t,
        "total": t,

        # New fields (used by traceability pages + project dashboard)
        "with_source": with_source,
        "with_source_pct": pct(with_source),
        "with_children": with_children,
        "with_children_pct": pct(with_children),
        "with_verification": with_verification,
        "with_verification_pct": pct(with_verification),
        "orphans": orphans,
        "orphan_pct": pct(orphans),

        # Legacy fields (used by landing page ProjectWithStats)
        "forward_traced": with_source,
        "backward_traced": with_children,
        "verified": with_verification,
        "forward_coverage": pct(with_source),
        "backward_coverage": pct(with_children),
        "verification_coverage": pct(with_verification),
    }


# ══════════════════════════════════════
#  Source Artifacts
# ══════════════════════════════════════

artifacts_router = APIRouter(prefix="/artifacts", tags=["Source Artifacts"])


# Files attached to artifacts go here, scoped per project + artifact.
ARTIFACTS_UPLOAD_ROOT = "uploads/artifacts"
ARTIFACT_ALLOWED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".txt", ".md", ".png", ".jpg", ".jpeg"}


def _ensure_artifact(db: Session, project_id: int, artifact_id: int) -> SourceArtifact:
    artifact = db.query(SourceArtifact).filter(
        SourceArtifact.id == artifact_id,
        SourceArtifact.project_id == project_id,
    ).first()
    if not artifact:
        raise HTTPException(404, "Source artifact not found")
    return artifact


@artifacts_router.get("/", response_model=List[SourceArtifactResponse])
def list_artifacts(
    project_id: int,
    artifact_type: Optional[str] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    """List source artifacts for a project, with optional type filter and search."""
    q = db.query(SourceArtifact).filter(SourceArtifact.project_id == project_id)
    if artifact_type:
        q = q.filter(SourceArtifact.artifact_type == artifact_type)
    if search:
        like = f"%{search}%"
        q = q.filter(
            (SourceArtifact.title.ilike(like))
            | (SourceArtifact.artifact_id.ilike(like))
            | (SourceArtifact.description.ilike(like))
        )
    return q.order_by(SourceArtifact.created_at.desc()).all()


@artifacts_router.get("/stats", response_model=List[dict])
def list_artifacts_with_stats(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    """List artifacts with per-artifact statistics (linked requirement counts)."""
    # Aggregate counts in one grouped query to avoid N+1.
    from sqlalchemy import case, Integer
    counts_rows = (
        db.query(
            Requirement.source_artifact_id.label("artifact_id"),
            func.count(Requirement.id).label("total"),
            func.sum(case((Requirement.level == "L0", 1), else_=0)).label("l0_total"),
        )
        .filter(Requirement.source_artifact_id.isnot(None))
        .group_by(Requirement.source_artifact_id)
        .all()
    )
    counts = {
        row.artifact_id: {"total": int(row.total or 0), "l0": int(row.l0_total or 0)}
        for row in counts_rows
    }

    artifacts = (
        db.query(SourceArtifact)
        .filter(SourceArtifact.project_id == project_id)
        .order_by(SourceArtifact.created_at.desc())
        .all()
    )

    return [
        {
            "id": a.id,
            "artifact_id": a.artifact_id,
            "title": a.title,
            "artifact_type": _ev(a.artifact_type),
            "description": a.description,
            "file_path": a.file_path,
            "source_date": a.source_date.isoformat() if a.source_date else None,
            "participants": a.participants or [],
            "project_id": a.project_id,
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "l0_requirement_count": counts.get(a.id, {}).get("l0", 0),
            "total_requirement_count": counts.get(a.id, {}).get("total", 0),
        }
        for a in artifacts
    ]


@artifacts_router.get("/{artifact_id}", response_model=SourceArtifactResponse)
def get_artifact(
    project_id: int,
    artifact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    """Get a single artifact by ID."""
    return _ensure_artifact(db, project_id, artifact_id)


@artifacts_router.get("/{artifact_id}/requirements", response_model=List[RequirementResponse])
def get_artifact_requirements(
    project_id: int,
    artifact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    """List requirements that reference this artifact, ordered by level then req_id."""
    _ensure_artifact(db, project_id, artifact_id)
    return (
        db.query(Requirement)
        .filter(Requirement.source_artifact_id == artifact_id)
        .order_by(Requirement.level, Requirement.req_id)
        .all()
    )


@artifacts_router.post("/", response_model=SourceArtifactResponse, status_code=201)
def create_artifact(
    project_id: int,
    data: SourceArtifactCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("artifacts.create")),
    project: Project = Depends(project_member_required),
):
    # F-074: replace racy `count + 1` (two concurrent creates compute
    # the same number) with the FOR-UPDATE-locked id_sequences row.
    from app.services.id_sequence import next_human_id
    artifact_id = next_human_id(
        db,
        project_id=project_id,
        prefix=f"ART-{project.code}",
        source_model=SourceArtifact,
        id_field="artifact_id",
    )
    artifact = SourceArtifact(artifact_id=artifact_id, **data.model_dump(), project_id=project_id)
    db.add(artifact)
    db.commit()
    db.refresh(artifact)

    record_event(
        db, "artifact.created", "source_artifact", artifact.id, current_user.id,
        {"artifact_id": artifact_id, "title": artifact.title},
        project_id=project_id, request=request,
    )
    return artifact


@artifacts_router.patch("/{artifact_id}", response_model=SourceArtifactResponse)
def update_artifact(
    project_id: int,
    artifact_id: int,
    data: SourceArtifactUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("artifacts.update")),
    project: Project = Depends(project_member_required),
):
    """Update an existing source artifact."""
    artifact = _ensure_artifact(db, project_id, artifact_id)

    changes: dict = {}
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        old_value = getattr(artifact, field, None)
        old_str = _ev(old_value) if hasattr(old_value, "value") else old_value
        if old_str != value:
            changes[field] = {"old": str(old_str), "new": str(value)}
            setattr(artifact, field, value)

    if changes:
        db.commit()
        db.refresh(artifact)
        record_event(
            db, "artifact.updated", "source_artifact", artifact.id, current_user.id,
            {"artifact_id": artifact.artifact_id, "changes": changes},
            project_id=project_id, request=request,
        )

    return artifact


@artifacts_router.delete("/{artifact_id}", status_code=204)
def delete_artifact(
    project_id: int,
    artifact_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("artifacts.delete")),
    project: Project = Depends(project_member_required),
):
    """
    Delete a source artifact. Refuses if any requirements still reference it,
    to protect audit-trail integrity. The user must update or delete the
    referencing requirements first.
    """
    artifact = _ensure_artifact(db, project_id, artifact_id)

    ref_count = (
        db.query(func.count(Requirement.id))
        .filter(Requirement.source_artifact_id == artifact_id)
        .scalar() or 0
    )
    if ref_count > 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot delete artifact '{artifact.artifact_id}': "
                f"{ref_count} requirement(s) still reference it. "
                "Update or delete the linked requirements first."
            ),
        )

    record_event(
        db, "artifact.deleted", "source_artifact", artifact.id, current_user.id,
        {"artifact_id": artifact.artifact_id, "title": artifact.title},
        project_id=project_id, request=request,
    )
    db.delete(artifact)
    db.commit()
    return None


@artifacts_router.post("/{artifact_id}/upload", response_model=SourceArtifactResponse)
async def upload_artifact_file(
    project_id: int,
    artifact_id: int,
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("artifacts.update")),
    project: Project = Depends(project_member_required),
):
    """Upload a file to attach to a source artifact (PDF, DOCX, etc.)."""
    artifact = _ensure_artifact(db, project_id, artifact_id)

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ARTIFACT_ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"File type '{ext}' not allowed. Permitted: "
            f"{', '.join(sorted(ARTIFACT_ALLOWED_EXTENSIONS))}",
        )

    upload_dir = os.path.join(ARTIFACTS_UPLOAD_ROOT, project.code, artifact.artifact_id)
    os.makedirs(upload_dir, exist_ok=True)
    safe_filename = os.path.basename(file.filename or "upload")
    file_path = os.path.join(upload_dir, safe_filename)

    contents = await file.read()
    with open(file_path, "wb") as f:
        f.write(contents)

    artifact.file_path = file_path
    db.commit()
    db.refresh(artifact)

    record_event(
        db, "artifact.file_uploaded", "source_artifact", artifact.id, current_user.id,
        {
            "artifact_id": artifact.artifact_id,
            "filename": safe_filename,
            "size_bytes": len(contents),
        },
        project_id=project_id, request=request,
    )
    return artifact


@artifacts_router.get("/{artifact_id}/download")
def download_artifact_file(
    project_id: int,
    artifact_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    """Download the file attached to a source artifact."""
    artifact = _ensure_artifact(db, project_id, artifact_id)
    if not artifact.file_path:
        raise HTTPException(404, "No file attached to this artifact")
    if not os.path.exists(artifact.file_path):
        raise HTTPException(404, "Attached file not found on disk")

    return FileResponse(
        path=artifact.file_path,
        filename=os.path.basename(artifact.file_path),
        media_type="application/octet-stream",
    )
