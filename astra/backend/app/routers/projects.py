from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Project, User, TraceLink, Requirement, SourceArtifact
from app.schemas import (
    ProjectCreate, ProjectResponse,
    TraceLinkCreate, TraceLinkResponse,
    SourceArtifactCreate, SourceArtifactResponse,
)
from app.services.auth import get_current_user

# ══════════════════════════════════════
#  Projects Router
# ══════════════════════════════════════

projects_router = APIRouter(prefix="/projects", tags=["Projects"])


@projects_router.get("/", response_model=List[ProjectResponse])
def list_projects(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(Project).all()


@projects_router.post("/", response_model=ProjectResponse, status_code=201)
def create_project(data: ProjectCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if db.query(Project).filter(Project.code == data.code).first():
        raise HTTPException(status_code=400, detail="Project code already exists")
    project = Project(**data.model_dump(), owner_id=current_user.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


@projects_router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


# ══════════════════════════════════════
#  Traceability Router
# ══════════════════════════════════════

traceability_router = APIRouter(prefix="/traceability", tags=["Traceability"])


@traceability_router.get("/links", response_model=List[TraceLinkResponse])
def list_trace_links(
    project_id: int,
    source_type: Optional[str] = None,
    target_type: Optional[str] = None,
    link_type: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Get all requirement IDs for this project to scope trace links
    req_ids = [r.id for r in db.query(Requirement.id).filter(Requirement.project_id == project_id).all()]
    artifact_ids = [a.id for a in db.query(SourceArtifact.id).filter(SourceArtifact.project_id == project_id).all()]

    query = db.query(TraceLink).filter(
        ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids))) |
        ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids))) |
        ((TraceLink.source_type == "source_artifact") & (TraceLink.source_id.in_(artifact_ids))) |
        ((TraceLink.target_type == "source_artifact") & (TraceLink.target_id.in_(artifact_ids)))
    )

    if source_type:
        query = query.filter(TraceLink.source_type == source_type)
    if target_type:
        query = query.filter(TraceLink.target_type == target_type)
    if link_type:
        query = query.filter(TraceLink.link_type == link_type)

    return query.all()


@traceability_router.post("/links", response_model=TraceLinkResponse, status_code=201)
def create_trace_link(data: TraceLinkCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    link = TraceLink(**data.model_dump(), created_by_id=current_user.id)
    db.add(link)
    db.commit()
    db.refresh(link)
    return link


@traceability_router.delete("/links/{link_id}", status_code=204)
def delete_trace_link(link_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    link = db.query(TraceLink).filter(TraceLink.id == link_id).first()
    if not link:
        raise HTTPException(status_code=404, detail="Trace link not found")
    db.delete(link)
    db.commit()


@traceability_router.get("/matrix")
def get_traceability_matrix(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Generate the full RTM for a project — requirements vs artifacts/tests."""
    reqs = db.query(Requirement).filter(Requirement.project_id == project_id).all()
    req_ids = [r.id for r in reqs]
    links = db.query(TraceLink).filter(
        ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids))) |
        ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids)))
    ).all()

    matrix = []
    for req in reqs:
        req_links = [l for l in links if l.source_id == req.id or l.target_id == req.id]
        matrix.append({
            "req_id": req.req_id,
            "title": req.title,
            "status": req.status,
            "source_artifacts": [l.source_id for l in req_links if l.source_type == "source_artifact"],
            "design_links": [l.target_id for l in req_links if l.target_type == "design"],
            "test_links": [l.target_id for l in req_links if l.target_type == "verification"],
            "children": [l.target_id for l in req_links if l.link_type == "decomposition"],
        })

    return {"project_id": project_id, "requirements_count": len(reqs), "matrix": matrix}


@traceability_router.get("/coverage")
def get_coverage_stats(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Calculate traceability coverage metrics."""
    reqs = db.query(Requirement).filter(Requirement.project_id == project_id).all()
    total = len(reqs)
    if total == 0:
        return {"total": 0, "with_source": 0, "with_tests": 0, "with_design": 0, "orphans": 0}

    req_ids = [r.id for r in reqs]
    links = db.query(TraceLink).filter(
        ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids))) |
        ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids)))
    ).all()

    with_source = set()
    with_tests = set()
    linked_reqs = set()

    for l in links:
        if l.source_type == "source_artifact" and l.target_type == "requirement":
            with_source.add(l.target_id)
        if l.source_type == "requirement" and l.target_type == "verification":
            with_tests.add(l.source_id)
        if l.source_type == "requirement":
            linked_reqs.add(l.source_id)
        if l.target_type == "requirement":
            linked_reqs.add(l.target_id)

    orphans = total - len(linked_reqs)

    return {
        "total": total,
        "with_source": len(with_source),
        "with_source_pct": round(len(with_source) / total * 100, 1),
        "with_tests": len(with_tests),
        "with_tests_pct": round(len(with_tests) / total * 100, 1),
        "orphans": orphans,
        "orphan_pct": round(orphans / total * 100, 1),
    }


# ══════════════════════════════════════
#  Source Artifacts Router
# ══════════════════════════════════════

artifacts_router = APIRouter(prefix="/artifacts", tags=["Source Artifacts"])


@artifacts_router.get("/", response_model=List[SourceArtifactResponse])
def list_artifacts(project_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return db.query(SourceArtifact).filter(SourceArtifact.project_id == project_id).all()


@artifacts_router.post("/", response_model=SourceArtifactResponse, status_code=201)
def create_artifact(
    project_id: int,
    data: SourceArtifactCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = db.query(SourceArtifact).filter(SourceArtifact.project_id == project_id).count()
    TYPE_PREFIX = {
        "interview": "INT", "meeting": "MTG", "decision": "DEC", "standard": "STD",
        "legacy": "LEG", "email": "EML", "multimedia": "MED", "document": "DOC",
    }
    prefix = TYPE_PREFIX.get(data.artifact_type, "SA")
    artifact_id = f"SA-{prefix}-{count + 1:03d}"

    artifact = SourceArtifact(
        artifact_id=artifact_id,
        **data.model_dump(),
        project_id=project_id,
        created_by_id=current_user.id,
    )
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact
