"""
ASTRA — Project Parts router (project-scoped joins to library parts)
======================================================================
File: backend/app/routers/project_parts.py    ← NEW (ASTRA-SPEC-PARTS-001)

Endpoints (all under /api/v1/projects/{project_id}/parts/):
  GET    /                    list_project_parts
  GET    /unassigned          list_unassigned_parts
  POST   /                    add_part_to_project (PM/Admin)
  PATCH  /{project_part_id}   update_project_part
  DELETE /{project_part_id}   remove_part_from_project

  GET    /systems/{system_id}/parts/   list_system_parts
  POST   /systems/{system_id}/parts/   assign_part_to_system
  DELETE /systems/{system_id}/parts/{assignment_id}  remove_system_part
  PATCH  /systems/{system_id}/parts/{assignment_id}  reorder_system_part
"""

from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.dependencies.project_access import project_member_required
from app.models import Project, User
from app.models.parts_library import (
    LibraryPart, MechanicalJoint, PartStatus, ProjectPart,
    SystemPartAssignment, JointStatus,
)
from app.schemas.parts_library import (
    ProjectPartCreate, ProjectPartUpdate, ProjectPartResponse,
    SystemPartAssignmentCreate, SystemPartAssignmentUpdate,
    SystemPartAssignmentResponse,
)
from app.services.audit_service import record_event
from app.services.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["project-parts"])


def _to_response(pp: ProjectPart, system_id: Optional[int] = None) -> dict:
    """Build the dict shape ProjectPartResponse expects."""
    if system_id is None:
        # Resolve from system_assignments if present
        if pp.system_assignments:
            system_id = pp.system_assignments[0].system_id
    return {
        "id": pp.id,
        "project_id": pp.project_id,
        "library_part_id": pp.library_part_id,
        "quantity": pp.quantity,
        "designation": pp.designation,
        "notes": pp.notes,
        "added_at": pp.added_at,
        "library_part": pp.library_part,
        "system_id": system_id,
    }


# ══════════════════════════════════════════════════════════════
#  Project parts CRUD
# ══════════════════════════════════════════════════════════════

@router.get(
    "/projects/{project_id}/parts/",
    response_model=list[ProjectPartResponse],
)
async def list_project_parts(
    project_id: int,
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
):
    parts = (
        db.query(ProjectPart)
        .options(
            selectinload(ProjectPart.library_part),
            selectinload(ProjectPart.system_assignments),
        )
        .filter(ProjectPart.project_id == project_id)
        .order_by(ProjectPart.added_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_to_response(pp) for pp in parts]


@router.get(
    "/projects/{project_id}/parts/unassigned",
    response_model=list[ProjectPartResponse],
)
async def list_unassigned_parts(
    project_id: int,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
):
    """Project parts with no SystemPartAssignment record."""
    assigned_ids_subq = (
        db.query(SystemPartAssignment.project_part_id).subquery()
    )
    parts = (
        db.query(ProjectPart)
        .options(selectinload(ProjectPart.library_part))
        .filter(ProjectPart.project_id == project_id)
        .filter(~ProjectPart.id.in_(assigned_ids_subq))
        .order_by(ProjectPart.added_at.desc())
        .all()
    )
    return [_to_response(pp, system_id=None) for pp in parts]


@router.post(
    "/projects/{project_id}/parts/",
    response_model=ProjectPartResponse,
    status_code=201,
)
async def add_part_to_project(
    project_id: int,
    data: ProjectPartCreate,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Add an APPROVED library part to a project."""
    lp = (
        db.query(LibraryPart).filter(LibraryPart.id == data.library_part_id).first()
    )
    if not lp:
        raise HTTPException(
            422,
            {"detail": "library_part_id not found", "code": "PART_NOT_FOUND"},
        )
    if lp.status != PartStatus.APPROVED:
        raise HTTPException(
            422,
            {"detail": "Only APPROVED library parts can be added to a project",
             "code": "PART_NOT_APPROVED"},
        )

    existing = (
        db.query(ProjectPart)
        .filter(
            ProjectPart.project_id == project_id,
            ProjectPart.library_part_id == data.library_part_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            409,
            {"detail": "This library part is already in the project",
             "code": "DUPLICATE_PROJECT_PART"},
        )

    pp = ProjectPart(
        project_id=project_id,
        library_part_id=data.library_part_id,
        quantity=data.quantity,
        designation=data.designation,
        notes=data.notes,
        added_by_id=current_user.id,
    )
    db.add(pp)
    db.commit()
    db.refresh(pp)
    # Eager-load library_part for response
    _ = pp.library_part

    record_event(
        db, "parts_library.project_part_added", "project_part", pp.id,
        current_user.id,
        {
            "library_part_id": data.library_part_id,
            "wpn": lp.wardstone_part_number,
            "quantity": pp.quantity,
        },
        project_id=project_id,
    )
    db.commit()
    return _to_response(pp, system_id=None)


@router.patch(
    "/projects/{project_id}/parts/{project_part_id}",
    response_model=ProjectPartResponse,
)
async def update_project_part(
    project_id: int,
    project_part_id: int,
    data: ProjectPartUpdate,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
):
    pp = (
        db.query(ProjectPart)
        .options(
            selectinload(ProjectPart.library_part),
            selectinload(ProjectPart.system_assignments),
        )
        .filter(
            ProjectPart.id == project_part_id,
            ProjectPart.project_id == project_id,
        )
        .first()
    )
    if not pp:
        raise HTTPException(404, "Project part not found")
    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    for k, v in update_data.items():
        setattr(pp, k, v)
    db.commit()
    db.refresh(pp)
    return _to_response(pp)


@router.delete(
    "/projects/{project_id}/parts/{project_part_id}", status_code=204,
)
async def remove_part_from_project(
    project_id: int,
    project_part_id: int,
    force: bool = Query(default=False),
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pp = (
        db.query(ProjectPart)
        .filter(
            ProjectPart.id == project_part_id,
            ProjectPart.project_id == project_id,
        )
        .first()
    )
    if not pp:
        raise HTTPException(404, "Project part not found")

    # Block if active mechanical joints reference this part
    active_joint = (
        db.query(MechanicalJoint)
        .filter(
            MechanicalJoint.project_id == project_id,
            MechanicalJoint.status == JointStatus.ACTIVE,
            (MechanicalJoint.part_a_id == project_part_id)
            | (MechanicalJoint.part_b_id == project_part_id),
        )
        .first()
    )
    if active_joint and not force:
        raise HTTPException(
            409,
            {
                "detail": (
                    f"Project part is referenced by active joint "
                    f"{active_joint.joint_id}. Pass force=true to override."
                ),
                "code": "HAS_ACTIVE_JOINTS",
            },
        )

    audit_payload = {
        "library_part_id": pp.library_part_id,
        "force": bool(force),
    }
    db.delete(pp)
    db.commit()
    record_event(
        db, "parts_library.project_part_removed", "project_part",
        project_part_id, current_user.id, audit_payload,
        project_id=project_id,
    )
    db.commit()


# ══════════════════════════════════════════════════════════════
#  System part assignments
# ══════════════════════════════════════════════════════════════

@router.get(
    "/projects/{project_id}/systems/{system_id}/parts/",
    response_model=list[SystemPartAssignmentResponse],
)
async def list_system_parts(
    project_id: int,
    system_id: int,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(SystemPartAssignment)
        .options(
            selectinload(SystemPartAssignment.project_part)
            .selectinload(ProjectPart.library_part),
        )
        .filter(SystemPartAssignment.system_id == system_id)
        .order_by(SystemPartAssignment.position_order.asc())
        .all()
    )
    out = []
    for spa in rows:
        out.append({
            "id": spa.id,
            "system_id": spa.system_id,
            "project_part_id": spa.project_part_id,
            "position_order": spa.position_order,
            "assigned_at": spa.assigned_at,
            "project_part": _to_response(spa.project_part, system_id=spa.system_id),
        })
    return out


@router.post(
    "/projects/{project_id}/systems/{system_id}/parts/",
    response_model=SystemPartAssignmentResponse,
    status_code=201,
)
async def assign_part_to_system(
    project_id: int,
    system_id: int,
    data: SystemPartAssignmentCreate,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pp = (
        db.query(ProjectPart)
        .filter(
            ProjectPart.id == data.project_part_id,
            ProjectPart.project_id == project_id,
        )
        .first()
    )
    if not pp:
        raise HTTPException(
            422,
            {"detail": "project_part_id not in this project",
             "code": "PART_NOT_IN_PROJECT"},
        )

    existing = (
        db.query(SystemPartAssignment)
        .filter(
            SystemPartAssignment.system_id == system_id,
            SystemPartAssignment.project_part_id == data.project_part_id,
        )
        .first()
    )
    if existing:
        raise HTTPException(
            409,
            {"detail": "Part already assigned to this system",
             "code": "DUPLICATE_ASSIGNMENT"},
        )

    spa = SystemPartAssignment(
        system_id=system_id,
        project_part_id=data.project_part_id,
        position_order=data.position_order,
        assigned_by_id=current_user.id,
    )
    db.add(spa)
    db.commit()
    db.refresh(spa)
    _ = spa.project_part.library_part  # eager-load for response

    record_event(
        db, "parts_library.system_part_assigned", "system_part_assignment",
        spa.id, current_user.id,
        {"system_id": system_id, "project_part_id": data.project_part_id},
        project_id=project_id,
    )
    db.commit()
    return {
        "id": spa.id,
        "system_id": spa.system_id,
        "project_part_id": spa.project_part_id,
        "position_order": spa.position_order,
        "assigned_at": spa.assigned_at,
        "project_part": _to_response(spa.project_part, system_id=system_id),
    }


@router.patch(
    "/projects/{project_id}/systems/{system_id}/parts/{assignment_id}",
    response_model=SystemPartAssignmentResponse,
)
async def reorder_system_part(
    project_id: int,
    system_id: int,
    assignment_id: int,
    data: SystemPartAssignmentUpdate,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
):
    spa = (
        db.query(SystemPartAssignment)
        .options(
            selectinload(SystemPartAssignment.project_part)
            .selectinload(ProjectPart.library_part),
        )
        .filter(
            SystemPartAssignment.id == assignment_id,
            SystemPartAssignment.system_id == system_id,
        )
        .first()
    )
    if not spa:
        raise HTTPException(404, "Assignment not found")
    if data.position_order is not None:
        spa.position_order = data.position_order
    db.commit()
    db.refresh(spa)
    return {
        "id": spa.id,
        "system_id": spa.system_id,
        "project_part_id": spa.project_part_id,
        "position_order": spa.position_order,
        "assigned_at": spa.assigned_at,
        "project_part": _to_response(spa.project_part, system_id=system_id),
    }


@router.delete(
    "/projects/{project_id}/systems/{system_id}/parts/{assignment_id}",
    status_code=204,
)
async def remove_system_part(
    project_id: int,
    system_id: int,
    assignment_id: int,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    spa = (
        db.query(SystemPartAssignment)
        .filter(
            SystemPartAssignment.id == assignment_id,
            SystemPartAssignment.system_id == system_id,
        )
        .first()
    )
    if not spa:
        raise HTTPException(404, "Assignment not found")
    pp_id = spa.project_part_id
    db.delete(spa)
    db.commit()
    record_event(
        db, "parts_library.system_part_removed", "system_part_assignment",
        assignment_id, current_user.id,
        {"system_id": system_id, "project_part_id": pp_id},
        project_id=project_id,
    )
    db.commit()
