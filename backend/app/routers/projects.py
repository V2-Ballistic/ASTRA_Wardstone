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
    """Generate the full RTM for a project — requirements vs artifacts/tests/children."""
    reqs = db.query(Requirement).filter(
        Requirement.project_id == project_id,
        Requirement.status != "deleted",
    ).order_by(Requirement.req_id).all()
    req_ids = [r.id for r in reqs]

    links = []
    if req_ids:
        links = db.query(TraceLink).filter(
            ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids))) |
            ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids)))
        ).all()

    # Build children map from parent_id
    children_map = {}
    for r in reqs:
        if r.parent_id and r.parent_id in req_ids:
            if r.parent_id not in children_map:
                children_map[r.parent_id] = []
            children_map[r.parent_id].append(r.id)

    from app.models import Verification
    verifications = {}
    if req_ids:
        vrows = db.query(Verification).filter(Verification.requirement_id.in_(req_ids)).all()
        for v in vrows:
            if v.requirement_id not in verifications:
                verifications[v.requirement_id] = []
            verifications[v.requirement_id].append(v.id)

    matrix = []
    for req in reqs:
        req_links = [l for l in links if l.source_id == req.id or l.target_id == req.id]
        level_str = req.level.value if hasattr(req.level, "value") else str(req.level) if req.level else "L1"
        status_str = req.status.value if hasattr(req.status, "value") else str(req.status)
        priority_str = req.priority.value if hasattr(req.priority, "value") else str(req.priority)

        source_artifacts = [l.source_id for l in req_links if l.source_type == "source_artifact"]
        child_ids = children_map.get(req.id, [])
        verification_ids = verifications.get(req.id, [])
        test_links = [l.target_id for l in req_links if l.target_type == "verification"]

        matrix.append({
            "id": req.id,
            "req_id": req.req_id,
            "title": req.title,
            "level": level_str,
            "status": status_str,
            "priority": priority_str,
            "parent_id": req.parent_id,
            "source_artifacts": source_artifacts,
            "source_artifact_count": len(source_artifacts),
            "children": child_ids,
            "children_count": len(child_ids),
            "verifications": verification_ids,
            "verification_count": len(verification_ids),
            "test_links": test_links,
            "test_count": len(test_links),
            "total_links": len(req_links),
        })

    return {"project_id": project_id, "requirements_count": len(reqs), "matrix": matrix}


@traceability_router.get("/graph")
def get_traceability_graph(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return nodes and edges in D3-ready format for force-directed graph."""
    reqs = db.query(Requirement).filter(
        Requirement.project_id == project_id,
        Requirement.status != "deleted",
    ).all()
    req_ids = [r.id for r in reqs]

    links = []
    if req_ids:
        links = db.query(TraceLink).filter(
            ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids))) |
            ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids)))
        ).all()

    # Build nodes
    nodes = []
    for r in reqs:
        level_str = r.level.value if hasattr(r.level, "value") else str(r.level) if r.level else "L1"
        status_str = r.status.value if hasattr(r.status, "value") else str(r.status)
        nodes.append({
            "id": r.id,
            "req_id": r.req_id,
            "title": r.title,
            "level": level_str,
            "status": status_str,
            "parent_id": r.parent_id,
            "quality_score": r.quality_score or 0,
        })

    # Build edges from trace_links
    edges = []
    for l in links:
        link_type = l.link_type.value if hasattr(l.link_type, "value") else str(l.link_type)
        edges.append({
            "source": l.source_id,
            "target": l.target_id,
            "source_type": l.source_type,
            "target_type": l.target_type,
            "link_type": link_type,
        })

    # Also add parent-child edges from parent_id
    for r in reqs:
        if r.parent_id and r.parent_id in req_ids:
            edges.append({
                "source": r.parent_id,
                "target": r.id,
                "source_type": "requirement",
                "target_type": "requirement",
                "link_type": "parent_child",
            })

    return {"nodes": nodes, "edges": edges}


@traceability_router.get("/coverage")
def get_coverage_stats(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Calculate traceability coverage metrics."""
    reqs = db.query(Requirement).filter(
        Requirement.project_id == project_id,
        Requirement.status != "deleted",
    ).all()
    total = len(reqs)
    if total == 0:
        return {"total": 0, "with_source": 0, "with_source_pct": 0, "with_tests": 0, "with_tests_pct": 0,
                "with_children": 0, "with_children_pct": 0, "with_verification": 0, "with_verification_pct": 0,
                "orphans": 0, "orphan_pct": 0}

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

    # Children: requirements that have at least one child via parent_id
    parent_ids = set()
    for r in reqs:
        if r.parent_id and r.parent_id in set(req_ids):
            parent_ids.add(r.parent_id)

    # Verification records
    from app.models import Verification
    verified_ids = set()
    if req_ids:
        vrows = db.query(Verification.requirement_id).filter(Verification.requirement_id.in_(req_ids)).distinct().all()
        verified_ids = {v[0] for v in vrows}

    orphans = total - len(linked_reqs | parent_ids)

    return {
        "total": total,
        "with_source": len(with_source),
        "with_source_pct": round(len(with_source) / total * 100, 1),
        "with_tests": len(with_tests),
        "with_tests_pct": round(len(with_tests) / total * 100, 1),
        "with_children": len(parent_ids),
        "with_children_pct": round(len(parent_ids) / total * 100, 1),
        "with_verification": len(verified_ids),
        "with_verification_pct": round(len(verified_ids) / total * 100, 1),
        "orphans": orphans,
        "orphan_pct": round(max(0, orphans) / total * 100, 1),
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
