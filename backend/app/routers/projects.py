"""
ASTRA — Projects & Traceability Router (Audit-Instrumented)
=============================================================
File: backend/app/routers/projects.py   ← REPLACES existing

Adds record_event() calls to: create_project, create_trace_link, delete_trace_link.
Read-only endpoints (list, matrix, graph, coverage) are unchanged.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, User, TraceLink, Requirement, SourceArtifact, Verification
from app.schemas import (
    ProjectCreate, ProjectResponse,
    TraceLinkCreate, TraceLinkResponse,
    SourceArtifactCreate, SourceArtifactResponse,
)
from app.services.auth import get_current_user
from app.services.audit_service import record_event

try:
    from app.services.rbac import require_permission
except ImportError:
    def require_permission(action):
        return get_current_user

# ══════════════════════════════════════
#  Projects
# ══════════════════════════════════════

projects_router = APIRouter(prefix="/projects", tags=["Projects"])


@projects_router.get("/", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db),
                  current_user: User = Depends(get_current_user)):
    return db.query(Project).all()


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
                current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
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
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req_ids = [r.id for r in db.query(Requirement.id).filter(Requirement.project_id == project_id).all()]
    art_ids = [a.id for a in db.query(SourceArtifact.id).filter(SourceArtifact.project_id == project_id).all()]
    query = db.query(TraceLink).filter(
        ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids))) |
        ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids))) |
        ((TraceLink.source_type == "source_artifact") & (TraceLink.source_id.in_(art_ids))) |
        ((TraceLink.target_type == "source_artifact") & (TraceLink.target_id.in_(art_ids)))
    )
    if source_type:
        query = query.filter(TraceLink.source_type == source_type)
    if target_type:
        query = query.filter(TraceLink.target_type == target_type)
    if link_type:
        query = query.filter(TraceLink.link_type == link_type)
    return query.all()


@traceability_router.post("/links", response_model=TraceLinkResponse, status_code=201)
def create_trace_link(data: TraceLinkCreate, request: Request,
                      db: Session = Depends(get_db),
                      current_user: User = Depends(require_permission("traceability.create"))):
    link = TraceLink(**data.model_dump(), created_by_id=current_user.id)
    db.add(link)
    db.commit()
    db.refresh(link)

    # Determine project_id from source requirement (best-effort)
    pid = None
    if data.source_type == "requirement":
        r = db.query(Requirement).filter(Requirement.id == data.source_id).first()
        pid = r.project_id if r else None

    record_event(db, "trace_link.created", "trace_link", link.id, current_user.id,
                 {"source": f"{data.source_type}:{data.source_id}",
                  "target": f"{data.target_type}:{data.target_id}",
                  "link_type": data.link_type},
                 project_id=pid, request=request)
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


# ── Matrix / Graph / Coverage (read-only — unchanged) ──

@traceability_router.get("/matrix")
def get_traceability_matrix(project_id: int, db: Session = Depends(get_db),
                            current_user: User = Depends(get_current_user)):
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


@traceability_router.get("/graph")
def get_traceability_graph(project_id: int, db: Session = Depends(get_db),
                           current_user: User = Depends(get_current_user)):
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


@traceability_router.get("/coverage")
def get_coverage_stats(project_id: int, db: Session = Depends(get_db),
                       current_user: User = Depends(get_current_user)):
    reqs = db.query(Requirement).filter(
        Requirement.project_id == project_id, Requirement.status != "deleted"
    ).all()
    req_ids = [r.id for r in reqs]
    if not req_ids:
        return {"project_id": project_id, "total_requirements": 0,
                "forward_traced": 0, "backward_traced": 0, "verified": 0,
                "forward_coverage": 0.0, "backward_coverage": 0.0,
                "verification_coverage": 0.0}
    links = db.query(TraceLink).filter(
        ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids))) |
        ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids)))
    ).all()
    fwd, bwd = set(), set()
    for l in links:
        if l.source_type == "requirement" and l.source_id in req_ids:
            fwd.add(l.source_id)
        if l.target_type == "requirement" and l.target_id in req_ids:
            bwd.add(l.target_id)
        if l.source_type == "source_artifact" and l.target_type == "requirement":
            bwd.add(l.target_id)
    verified = {v.requirement_id for v in
                db.query(Verification).filter(Verification.requirement_id.in_(req_ids)).all()}
    t = len(req_ids)
    return {
        "project_id": project_id, "total_requirements": t,
        "forward_traced": len(fwd), "backward_traced": len(bwd), "verified": len(verified),
        "forward_coverage": round(len(fwd) / t * 100, 1) if t else 0.0,
        "backward_coverage": round(len(bwd) / t * 100, 1) if t else 0.0,
        "verification_coverage": round(len(verified) / t * 100, 1) if t else 0.0,
    }


# ══════════════════════════════════════
#  Source Artifacts
# ══════════════════════════════════════

artifacts_router = APIRouter(prefix="/artifacts", tags=["Source Artifacts"])


@artifacts_router.get("/", response_model=List[SourceArtifactResponse])
def list_artifacts(project_id: int, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    return db.query(SourceArtifact).filter(SourceArtifact.project_id == project_id).all()


@artifacts_router.post("/", response_model=SourceArtifactResponse, status_code=201)
def create_artifact(project_id: int, data: SourceArtifactCreate, request: Request,
                    db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "Project not found")
    count = db.query(SourceArtifact).filter(SourceArtifact.project_id == project_id).count()
    artifact_id = f"ART-{project.code}-{count + 1:03d}"
    artifact = SourceArtifact(artifact_id=artifact_id, **data.model_dump(), project_id=project_id)
    db.add(artifact)
    db.commit()
    db.refresh(artifact)

    record_event(db, "artifact.created", "source_artifact", artifact.id, current_user.id,
                 {"artifact_id": artifact_id}, project_id=project_id, request=request)
    return artifact
