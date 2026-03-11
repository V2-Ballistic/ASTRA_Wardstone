from typing import Optional, List
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models import Requirement, RequirementHistory, Project, User, TraceLink, Verification, Comment
from app.schemas import (
    RequirementCreate, RequirementUpdate, RequirementResponse,
    RequirementDetail, QualityCheckResult
)
from pydantic import BaseModel, Field
from app.services.auth import get_current_user
from app.services.quality_checker import check_requirement_quality, generate_requirement_id

router = APIRouter(prefix="/requirements", tags=["Requirements"])


# ══════════════════════════════════════
#  Status Workflow — allowed transitions
# ══════════════════════════════════════

ALLOWED_TRANSITIONS = {
    "draft":        ["under_review", "deleted"],
    "under_review":  ["approved", "draft", "deleted"],
    "approved":     ["baselined", "under_review", "deleted"],
    "baselined":    ["approved", "deleted"],
    "implemented":  ["verified", "approved", "deleted"],
    "verified":     ["validated", "approved", "deleted"],
    "validated":    ["approved", "deleted"],
    "deferred":     ["draft", "deleted"],
    "deleted":      ["draft"],  # restore from deleted
}


def _record_history(
    db: Session,
    requirement_id: int,
    version: int,
    field_changed: str,
    old_value,
    new_value,
    changed_by_id: int,
    description: str = None,
):
    """Write a single field change to the requirement_history table."""
    # Convert enum values to their string representation
    old_str = old_value.value if hasattr(old_value, "value") else str(old_value) if old_value is not None else None
    new_str = new_value.value if hasattr(new_value, "value") else str(new_value) if new_value is not None else None

    history = RequirementHistory(
        requirement_id=requirement_id,
        version=version,
        field_changed=field_changed,
        old_value=old_str,
        new_value=new_str,
        change_description=description or f"{field_changed} changed from '{old_str}' to '{new_str}'",
        changed_by_id=changed_by_id,
        changed_at=datetime.utcnow(),
    )
    db.add(history)


# ══════════════════════════════════════
#  Endpoints
# ══════════════════════════════════════

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
        level=req_data.level,
        project_id=project_id,
        owner_id=current_user.id,
        created_by_id=current_user.id,
        parent_id=req_data.parent_id,
        quality_score=quality["score"],
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    # Record creation in history
    _record_history(db, req.id, 1, "created", None, req.req_id, current_user.id,
                    f"Requirement {req.req_id} created")
    db.commit()

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

    # ── Validate status transition ──
    if "status" in update_data:
        current_status = req.status.value if hasattr(req.status, "value") else str(req.status)
        new_status = update_data["status"]

        if new_status != current_status:
            allowed = ALLOWED_TRANSITIONS.get(current_status, [])
            if new_status not in allowed:
                raise HTTPException(
                    status_code=422,
                    detail=f"Invalid status transition: '{current_status}' → '{new_status}'. "
                           f"Allowed transitions from '{current_status}': {allowed}"
                )

    # ── Track changes field by field ──
    fields_that_affect_quality = {"statement", "title", "rationale"}
    quality_needs_recalc = False

    for field, new_value in update_data.items():
        old_value = getattr(req, field)

        # Normalize for comparison: convert enums to string
        old_comparable = old_value.value if hasattr(old_value, "value") else old_value
        new_comparable = new_value

        # Skip if value didn't actually change
        if str(old_comparable) == str(new_comparable):
            continue

        # Record the change in history BEFORE applying
        _record_history(
            db=db,
            requirement_id=req.id,
            version=req.version,
            field_changed=field,
            old_value=old_comparable,
            new_value=new_comparable,
            changed_by_id=current_user.id,
        )

        # Apply the change
        setattr(req, field, new_value)

        # Flag if quality-affecting field changed
        if field in fields_that_affect_quality:
            quality_needs_recalc = True

    # ── Recalculate quality score if any text field changed ──
    if quality_needs_recalc:
        quality = check_requirement_quality(
            req.statement if hasattr(req.statement, '__str__') else str(req.statement),
            req.title if hasattr(req.title, '__str__') else str(req.title),
            req.rationale or ""
        )
        old_score = req.quality_score
        new_score = quality["score"]

        if old_score != new_score:
            _record_history(db, req.id, req.version, "quality_score",
                            old_score, new_score, current_user.id,
                            f"Quality score recalculated: {old_score} → {new_score}")
            req.quality_score = new_score

    # ── Increment version ──
    req.version += 1
    db.commit()
    db.refresh(req)
    return req


@router.delete("/{req_id}", status_code=200)
def delete_requirement(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Soft-delete: sets status to 'deleted' and records history. Does NOT remove from database."""
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    old_status = req.status.value if hasattr(req.status, "value") else str(req.status)

    # Already deleted
    if old_status == "deleted":
        raise HTTPException(status_code=400, detail="Requirement is already deleted")

    # Record the soft-delete in history
    _record_history(
        db=db,
        requirement_id=req.id,
        version=req.version,
        field_changed="status",
        old_value=old_status,
        new_value="deleted",
        changed_by_id=current_user.id,
        description=f"Requirement {req.req_id} soft-deleted by {current_user.username}",
    )

    req.status = "deleted"
    req.version += 1
    db.commit()
    db.refresh(req)
    return {"status": "deleted", "req_id": req.req_id, "id": req.id}


@router.post("/{req_id}/restore", response_model=RequirementResponse)
def restore_requirement(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Restore a soft-deleted requirement back to draft status."""
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    current_status = req.status.value if hasattr(req.status, "value") else str(req.status)
    if current_status != "deleted":
        raise HTTPException(status_code=400, detail="Requirement is not deleted")

    _record_history(
        db=db,
        requirement_id=req.id,
        version=req.version,
        field_changed="status",
        old_value="deleted",
        new_value="draft",
        changed_by_id=current_user.id,
        description=f"Requirement {req.req_id} restored by {current_user.username}",
    )

    req.status = "draft"
    req.version += 1
    db.commit()
    db.refresh(req)
    return req


@router.post("/{req_id}/clone", response_model=RequirementResponse, status_code=201)
def clone_requirement(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clone/duplicate a requirement. Copies all fields, prefixes title with [CLONE], forces draft status."""
    source = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="Source requirement not found")

    # Generate a new req_id
    project = db.query(Project).filter(Project.id == source.project_id).first()
    req_type_str = source.req_type.value if hasattr(source.req_type, "value") else str(source.req_type)
    count = db.query(func.count(Requirement.id)).filter(
        Requirement.project_id == source.project_id,
        Requirement.req_type == source.req_type,
    ).scalar()
    new_req_id = generate_requirement_id(
        project.code if project else "PROJ",
        req_type_str,
        count + 1,
    )

    # Recalculate quality
    statement = source.statement or ""
    title = f"[CLONE] {source.title}"
    rationale = source.rationale or ""
    quality = check_requirement_quality(statement, title, rationale)

    level_str = source.level.value if hasattr(source.level, "value") else str(source.level) if source.level else "L1"

    clone = Requirement(
        req_id=new_req_id,
        title=title,
        statement=statement,
        rationale=rationale if rationale else None,
        req_type=req_type_str,
        priority=source.priority.value if hasattr(source.priority, "value") else str(source.priority),
        level=level_str,
        status="draft",
        project_id=source.project_id,
        parent_id=source.parent_id,
        owner_id=current_user.id,
        created_by_id=current_user.id,
        quality_score=quality["score"],
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)

    # Record creation in history
    _record_history(db, clone.id, 1, "created", None, clone.req_id, current_user.id,
                    f"Cloned from {source.req_id}")
    db.commit()

    return clone


# ══════════════════════════════════════
#  History & Comments Endpoints
# ══════════════════════════════════════

@router.get("/{req_id}/history")
def get_requirement_history(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return full change history for a requirement, newest first."""
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    history = (
        db.query(RequirementHistory)
        .filter(RequirementHistory.requirement_id == req_id)
        .order_by(RequirementHistory.changed_at.desc())
        .all()
    )

    results = []
    for h in history:
        user = db.query(User).filter(User.id == h.changed_by_id).first() if h.changed_by_id else None
        results.append({
            "id": h.id,
            "version": h.version,
            "field_changed": h.field_changed,
            "old_value": h.old_value,
            "new_value": h.new_value,
            "change_description": h.change_description,
            "changed_by": user.full_name if user else "System",
            "changed_by_username": user.username if user else None,
            "changed_at": h.changed_at.isoformat() if h.changed_at else None,
        })

    return {"requirement_id": req_id, "req_id": req.req_id, "total": len(results), "history": results}


@router.get("/status-transitions/{current_status}")
def get_allowed_transitions(
    current_status: str,
    current_user: User = Depends(get_current_user),
):
    """Return allowed status transitions from the given current status."""
    allowed = ALLOWED_TRANSITIONS.get(current_status, [])
    return {"current_status": current_status, "allowed": allowed}


@router.post("/quality-check", response_model=QualityCheckResult)
def quality_check(
    statement: str,
    title: str = "",
    rationale: str = "",
    current_user: User = Depends(get_current_user),
):
    """Run NASA Appendix C quality checks on a requirement statement without saving."""
    return check_requirement_quality(statement, title, rationale)


# ══════════════════════════════════════
#  Comments Endpoints
# ══════════════════════════════════════

class CommentCreate(BaseModel):
    content: str = Field(..., min_length=1, max_length=5000)
    parent_id: Optional[int] = None


@router.get("/{req_id}/comments")
def get_requirement_comments(
    req_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return all comments for a requirement, with author info and threading."""
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    comments = (
        db.query(Comment)
        .filter(Comment.requirement_id == req_id)
        .order_by(Comment.created_at.asc())
        .all()
    )

    results = []
    for c in comments:
        author = db.query(User).filter(User.id == c.author_id).first()
        results.append({
            "id": c.id,
            "content": c.content,
            "parent_id": c.parent_id,
            "author_id": c.author_id,
            "author_name": author.full_name if author else "Unknown",
            "author_username": author.username if author else None,
            "author_role": author.role.value if author and hasattr(author.role, "value") else str(author.role) if author else None,
            "created_at": c.created_at.isoformat() if c.created_at else None,
            "updated_at": c.updated_at.isoformat() if c.updated_at else None,
        })

    return {"requirement_id": req_id, "total": len(results), "comments": results}


@router.post("/{req_id}/comments", status_code=201)
def create_comment(
    req_id: int,
    data: CommentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a new comment on a requirement."""
    req = db.query(Requirement).filter(Requirement.id == req_id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Requirement not found")

    # Validate parent comment exists if replying
    if data.parent_id:
        parent = db.query(Comment).filter(
            Comment.id == data.parent_id,
            Comment.requirement_id == req_id,
        ).first()
        if not parent:
            raise HTTPException(status_code=404, detail="Parent comment not found")

    comment = Comment(
        requirement_id=req_id,
        author_id=current_user.id,
        content=data.content,
        parent_id=data.parent_id,
    )
    db.add(comment)
    db.commit()
    db.refresh(comment)

    return {
        "id": comment.id,
        "content": comment.content,
        "parent_id": comment.parent_id,
        "author_id": current_user.id,
        "author_name": current_user.full_name,
        "author_username": current_user.username,
        "created_at": comment.created_at.isoformat() if comment.created_at else None,
    }
