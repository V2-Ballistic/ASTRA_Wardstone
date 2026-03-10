from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Requirement, Project, User, TraceLink, Verification
from app.schemas import (
    RequirementCreate, RequirementUpdate, RequirementResponse,
    RequirementDetail, QualityCheckResult
)
from app.services.auth import get_current_user
from app.services.quality_checker import check_requirement_quality, generate_requirement_id

router = APIRouter(prefix="/requirements", tags=["Requirements"])


@router.get("/", response_model=List[RequirementResponse])
def list_requirements(
    project_id: int,
    status: Optional[str] = None,
    req_type: Optional[str] = None,
    priority: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Requirement).filter(Requirement.project_id == project_id)

    if status:
        query = query.filter(Requirement.status == status)
    if req_type:
        query = query.filter(Requirement.req_type == req_type)
    if priority:
        query = query.filter(Requirement.priority == priority)
    if search:
        search_term = f"%{search}%"
        query = query.filter(
            (Requirement.req_id.ilike(search_term)) |
            (Requirement.title.ilike(search_term)) |
            (Requirement.statement.ilike(search_term))
        )

    return query.order_by(Requirement.req_id).offset(skip).limit(limit).all()


@router.get("/{req_id}", response_model=RequirementDetail)
def get_requirement(req_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    trace_count = db.query(TraceLink).filter(
        ((TraceLink.source_type == "requirement") & (TraceLink.source_id == req.id)) |
        ((TraceLink.target_type == "requirement") & (TraceLink.target_id == req.id))
    ).count()

    verification = db.query(Verification).filter(Verification.requirement_id == req.id).first()

    result = RequirementDetail.model_validate(req)
    result.trace_count = trace_count
    result.verification_status = verification.status if verification else None
    result.owner = req.owner
    result.children = req.children or []
    return result


@router.post("/", response_model=RequirementResponse, status_code=201)
def create_requirement(
    project_id: int,
    req_data: RequirementCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # Generate next sequential ID
    count = db.query(func.count(Requirement.id)).filter(
        Requirement.project_id == project_id,
        Requirement.req_type == req_data.req_type,
    ).scalar()

    req_id = generate_requirement_id(project.code, req_data.req_type, count + 1)

    # Run quality check
    quality = check_requirement_quality(req_data.statement, req_data.title, req_data.rationale or "")

    req = Requirement(
        req_id=req_id,
        title=req_data.title,
        statement=req_data.statement,
        rationale=req_data.rationale,
        req_type=req_data.req_type,
        priority=req_data.priority,
        project_id=project_id,
        owner_id=current_user.id,
        created_by_id=current_user.id,
        parent_id=req_data.parent_id,
        quality_score=quality["score"],
    )
    db.add(req)
    db.commit()
    db.refresh(req)
    return req


@router.patch("/{req_id}", response_model=RequirementResponse)
def update_requirement(
    req_id: int,
    req_data: RequirementUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    update_data = req_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(req, field, value)

    # Recalculate quality if statement changed
    if "statement" in update_data:
        quality = check_requirement_quality(req.statement, req.title, req.rationale or "")
        req.quality_score = quality["score"]

    req.version += 1
    db.commit()
    db.refresh(req)
    return req


@router.delete("/{req_id}", status_code=204)
def delete_requirement(req_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")
    db.delete(req)
    db.commit()


@router.post("/quality-check", response_model=QualityCheckResult)
def quality_check(
    statement: str,
    title: str = "",
    rationale: str = "",
    current_user: User = Depends(get_current_user),
):
    """Run NASA Appendix C quality checks on a requirement statement without saving."""
    return check_requirement_quality(statement, title, rationale)
