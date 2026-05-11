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
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.database import get_db
from app.dependencies.project_access import project_member_required
from app.models import Project, User
from app.models.catalog import CatalogPart, PartClass
from app.models.parts_library import (
    BomStatus, LibraryPart, MechanicalJoint, PartStatus, ProjectPart,
    SystemPartAssignment, JointStatus,
)
from app.schemas.parts_library import (
    BomStatsResponse,
    ProjectPartCreate, ProjectPartUpdate, ProjectPartResponse,
    SystemPartAssignmentCreate, SystemPartAssignmentUpdate,
    SystemPartAssignmentResponse,
)
from app.services.audit_service import record_event
from app.services.auth import get_current_user

logger = logging.getLogger(__name__)
router = APIRouter(tags=["project-parts"])


def _catalog_summary(cp: Optional[CatalogPart]) -> Optional[dict]:
    if cp is None:
        return None
    supplier_name = cp.supplier.name if getattr(cp, "supplier", None) else None
    return {
        "id":               cp.id,
        "part_number":      cp.part_number,
        "name":             cp.name,
        "part_class":       cp.part_class.value if hasattr(cp.part_class, "value") else cp.part_class,
        "lifecycle_status": cp.lifecycle_status.value if hasattr(cp.lifecycle_status, "value") else cp.lifecycle_status,
        "revision":         cp.revision,
        "supplier_name":    supplier_name,
        "mass_kg":          cp.mass_kg,
    }


def _unit_summary(unit) -> Optional[dict]:
    if unit is None:
        return None
    return {
        "id":          unit.id,
        "unit_id":     unit.unit_id,
        "name":        unit.name,
        "designation": unit.designation,
        "system_id":   unit.system_id,
    }


def _to_response(pp: ProjectPart, system_id: Optional[int] = None) -> dict:
    """Build the dict shape ProjectPartResponse expects."""
    if system_id is None:
        # Resolve from system_assignments if present
        if pp.system_assignments:
            system_id = pp.system_assignments[0].system_id
    return {
        "id":                 pp.id,
        "project_id":         pp.project_id,
        "library_part_id":    pp.library_part_id,
        "catalog_part_id":    pp.catalog_part_id,
        "quantity":           pp.quantity,
        "quantity_unit":      pp.quantity_unit,
        "designation":        pp.designation,
        "bom_position":       pp.bom_position,
        "parent_bom_id":      pp.parent_bom_id,
        "status":             pp.status,
        "unit_id":            pp.unit_id,
        "location_zone":      pp.location_zone,
        "installation_notes": pp.installation_notes,
        "procurement_notes":  pp.procurement_notes,
        "notes":              pp.notes,
        "added_at":           pp.added_at,
        "updated_at":         pp.updated_at,
        "library_part":       pp.library_part,
        "catalog_part_summary": _catalog_summary(getattr(pp, "catalog_part", None)),
        "linked_unit":          _unit_summary(getattr(pp, "linked_unit", None)),
        "parent_designation":   (pp.parent_bom.designation if getattr(pp, "parent_bom", None) else None),
        "system_id":          system_id,
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
    limit: int = Query(default=50, le=500),
    offset: int = Query(default=0, ge=0),
    part_class: Optional[PartClass] = Query(default=None),
    status: Optional[BomStatus] = Query(default=None),
    parent_bom_id: Optional[int] = Query(default=None),
    search: Optional[str] = Query(default=None, min_length=1, max_length=255),
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
):
    q = (
        db.query(ProjectPart)
        .options(
            selectinload(ProjectPart.library_part),
            selectinload(ProjectPart.system_assignments),
            joinedload(ProjectPart.catalog_part).joinedload(CatalogPart.supplier),
            joinedload(ProjectPart.linked_unit),
            joinedload(ProjectPart.parent_bom),
        )
        .filter(ProjectPart.project_id == project_id)
    )

    if part_class is not None:
        q = q.join(CatalogPart, ProjectPart.catalog_part_id == CatalogPart.id) \
             .filter(CatalogPart.part_class == part_class)
    if status is not None:
        q = q.filter(ProjectPart.status == status)
    if parent_bom_id is not None:
        q = q.filter(ProjectPart.parent_bom_id == parent_bom_id)
    if search:
        like = f"%{search}%"
        q = q.filter(or_(
            ProjectPart.designation.ilike(like),
            ProjectPart.bom_position.ilike(like),
            ProjectPart.notes.ilike(like),
        ))

    parts = (
        q.order_by(ProjectPart.added_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return [_to_response(pp) for pp in parts]


@router.get(
    "/projects/{project_id}/parts/stats",
    response_model=BomStatsResponse,
)
async def get_bom_stats(
    project_id: int,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
):
    total = (
        db.query(func.count(ProjectPart.id))
        .filter(ProjectPart.project_id == project_id)
        .scalar()
    ) or 0

    status_rows = (
        db.query(ProjectPart.status, func.count(ProjectPart.id))
        .filter(ProjectPart.project_id == project_id)
        .group_by(ProjectPart.status)
        .all()
    )
    by_status: dict[str, int] = {s.value: 0 for s in BomStatus}
    for st, cnt in status_rows:
        key = st.value if hasattr(st, "value") else str(st)
        by_status[key] = int(cnt)

    class_rows = (
        db.query(CatalogPart.part_class, func.count(ProjectPart.id))
        .join(ProjectPart, ProjectPart.catalog_part_id == CatalogPart.id)
        .filter(ProjectPart.project_id == project_id)
        .group_by(CatalogPart.part_class)
        .all()
    )
    by_part_class: dict[str, int] = {}
    for pc, cnt in class_rows:
        key = pc.value if hasattr(pc, "value") else str(pc)
        by_part_class[key] = int(cnt)

    return {
        "total":         int(total),
        "by_status":     by_status,
        "by_part_class": by_part_class,
    }


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
        .options(
            selectinload(ProjectPart.library_part),
            joinedload(ProjectPart.catalog_part).joinedload(CatalogPart.supplier),
            joinedload(ProjectPart.linked_unit),
            joinedload(ProjectPart.parent_bom),
        )
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
    """Add a BOM line to a project.

    Accepts either ``library_part_id`` (legacy fastener-class workflow,
    must reference an APPROVED LibraryPart) or ``catalog_part_id`` (Path C
    canonical BOM reference) or both. At least one is required, enforced
    in the Pydantic schema.
    """
    lp: Optional[LibraryPart] = None
    cp: Optional[CatalogPart] = None
    wpn: Optional[str] = None

    if data.library_part_id is not None:
        lp = (
            db.query(LibraryPart)
            .filter(LibraryPart.id == data.library_part_id)
            .first()
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
        wpn = lp.wardstone_part_number

    if data.catalog_part_id is not None:
        cp = (
            db.query(CatalogPart)
            .options(joinedload(CatalogPart.supplier))
            .filter(CatalogPart.id == data.catalog_part_id)
            .first()
        )
        if not cp:
            raise HTTPException(
                422,
                {"detail": "catalog_part_id not found",
                 "code": "CATALOG_PART_NOT_FOUND"},
            )

    if data.parent_bom_id is not None:
        parent = (
            db.query(ProjectPart)
            .filter(
                ProjectPart.id == data.parent_bom_id,
                ProjectPart.project_id == project_id,
            )
            .first()
        )
        if not parent:
            raise HTTPException(
                422,
                {"detail": "parent_bom_id must reference a BOM line in this project",
                 "code": "PARENT_BOM_NOT_IN_PROJECT"},
            )

    pp = ProjectPart(
        project_id=project_id,
        library_part_id=data.library_part_id,
        catalog_part_id=data.catalog_part_id,
        quantity=data.quantity,
        quantity_unit=data.quantity_unit,
        designation=data.designation,
        bom_position=data.bom_position,
        parent_bom_id=data.parent_bom_id,
        status=data.status,
        unit_id=data.unit_id,
        location_zone=data.location_zone,
        installation_notes=data.installation_notes,
        procurement_notes=data.procurement_notes,
        notes=data.notes,
        added_by_id=current_user.id,
    )
    db.add(pp)
    db.commit()
    db.refresh(pp)
    # Eager-load relationships for response
    _ = pp.library_part
    _ = pp.catalog_part
    _ = pp.linked_unit
    _ = pp.parent_bom

    audit_payload = {
        "library_part_id":  data.library_part_id,
        "catalog_part_id":  data.catalog_part_id,
        "wpn":              wpn,
        "catalog_part_number": cp.part_number if cp else None,
        "quantity":         float(pp.quantity) if pp.quantity is not None else None,
        "quantity_unit":    pp.quantity_unit,
        "status":           pp.status.value if hasattr(pp.status, "value") else pp.status,
        "bom_position":     pp.bom_position,
        "parent_bom_id":    pp.parent_bom_id,
        "unit_id":          pp.unit_id,
    }
    # Legacy event (kept for back-compat with the parts_library surface)
    record_event(
        db, "parts_library.project_part_added", "project_part", pp.id,
        current_user.id, audit_payload, project_id=project_id,
    )
    # Path C canonical BOM event
    record_event(
        db, "bom.created", "project_part", pp.id,
        current_user.id, audit_payload, project_id=project_id,
    )
    if pp.unit_id is not None:
        record_event(
            db, "bom.linked_to_unit", "project_part", pp.id,
            current_user.id,
            {"unit_id": pp.unit_id, "catalog_part_id": pp.catalog_part_id},
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
    current_user: User = Depends(get_current_user),
):
    pp = (
        db.query(ProjectPart)
        .options(
            selectinload(ProjectPart.library_part),
            selectinload(ProjectPart.system_assignments),
            joinedload(ProjectPart.catalog_part).joinedload(CatalogPart.supplier),
            joinedload(ProjectPart.linked_unit),
            joinedload(ProjectPart.parent_bom),
        )
        .filter(
            ProjectPart.id == project_part_id,
            ProjectPart.project_id == project_id,
        )
        .first()
    )
    if not pp:
        raise HTTPException(404, "Project part not found")

    update_data = data.model_dump(exclude_unset=True)
    if "parent_bom_id" in update_data and update_data["parent_bom_id"] is not None:
        if update_data["parent_bom_id"] == pp.id:
            raise HTTPException(
                422,
                {"detail": "A BOM line cannot be its own parent",
                 "code": "PARENT_BOM_SELF_REF"},
            )
        parent = (
            db.query(ProjectPart)
            .filter(
                ProjectPart.id == update_data["parent_bom_id"],
                ProjectPart.project_id == project_id,
            )
            .first()
        )
        if not parent:
            raise HTTPException(
                422,
                {"detail": "parent_bom_id must reference a BOM line in this project",
                 "code": "PARENT_BOM_NOT_IN_PROJECT"},
            )

    if "catalog_part_id" in update_data and update_data["catalog_part_id"] is not None:
        cp_check = (
            db.query(CatalogPart.id)
            .filter(CatalogPart.id == update_data["catalog_part_id"])
            .first()
        )
        if not cp_check:
            raise HTTPException(
                422,
                {"detail": "catalog_part_id not found",
                 "code": "CATALOG_PART_NOT_FOUND"},
            )

    # Track diff for audit
    diff: dict[str, dict] = {}
    prior_unit_id = pp.unit_id
    for k, v in update_data.items():
        before = getattr(pp, k, None)
        if isinstance(before, Decimal) and isinstance(v, (int, float)):
            before_cmp = before
            v_cmp = Decimal(str(v))
        else:
            before_cmp = before
            v_cmp = v
        if before_cmp != v_cmp:
            diff[k] = {
                "from": before.value if hasattr(before, "value") else (
                    float(before) if isinstance(before, Decimal) else before
                ),
                "to": v.value if hasattr(v, "value") else (
                    float(v) if isinstance(v, Decimal) else v
                ),
            }
        setattr(pp, k, v)
    db.commit()
    db.refresh(pp)

    if diff:
        record_event(
            db, "bom.updated", "project_part", pp.id,
            current_user.id, {"diff": diff}, project_id=project_id,
        )
        if "unit_id" in diff and pp.unit_id is not None and pp.unit_id != prior_unit_id:
            record_event(
                db, "bom.linked_to_unit", "project_part", pp.id,
                current_user.id,
                {"unit_id": pp.unit_id, "catalog_part_id": pp.catalog_part_id},
                project_id=project_id,
            )
        db.commit()
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
        "catalog_part_id": pp.catalog_part_id,
        "designation":     pp.designation,
        "bom_position":    pp.bom_position,
        "status":          pp.status.value if hasattr(pp.status, "value") else pp.status,
        "force":           bool(force),
    }
    db.delete(pp)
    db.commit()
    record_event(
        db, "parts_library.project_part_removed", "project_part",
        project_part_id, current_user.id, audit_payload,
        project_id=project_id,
    )
    record_event(
        db, "bom.deleted", "project_part",
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
