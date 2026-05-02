"""
ASTRA — Mechanical Joints router (project-scoped)
===================================================
File: backend/app/routers/mechanical_joints.py    ← NEW (ASTRA-SPEC-PARTS-001)

Endpoints (all under /api/v1/projects/{project_id}/mechanical-joints/):
  GET    /                       list_joints
  POST   /                       create_joint
  GET    /{joint_id}             get_joint
  PATCH  /{joint_id}             update_joint
  DELETE /{joint_id}             delete_joint
  POST   /{joint_id}/approve     approve_joint  (writes RequirementSourceLink + Requirement rows)
  POST   /upload-assembly        upload_assembly  (Phase 4)
  GET    /assembly-parse-status/{job_id}  get_parse_status
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile,
)
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.sql import func

from app.database import get_db
from app.dependencies.project_access import project_member_required
from app.models import (
    Project, Requirement, RequirementType, RequirementPriority,
    RequirementStatus, RequirementLevel, User, UserRole,
)
from app.models.parts_library import (
    AssemblyParseJob, AssemblyParseJobStatus, ConfidenceLevel, JointStatus,
    JointType, LibraryPart, MechanicalJoint, MechanicalJointSequence,
    PartStatus, PartType, ProjectPart,
)
from app.models.req_sync import RequirementSourceLink, SourceEntityType
from app.schemas.parts_library import (
    AssemblyParseJobResponse, MechanicalJointCreate, MechanicalJointResponse,
    MechanicalJointUpdate,
)
from app.services.audit_service import record_event
from app.services.auth import get_current_user
from app.services.id_sequence import next_human_id
from app.services.parts.mechanical_req_templates import (
    JOINT_TYPE_TEMPLATES, build_template_context, render_template,
)


logger = logging.getLogger(__name__)
router = APIRouter(tags=["mechanical-joints"])


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════

def _assign_joint_id(db: Session, project_id: int) -> str:
    """Atomic joint ID assignment via SELECT FOR UPDATE.
    Format: MJ-{project_id:04d}-{seq:06d}."""
    seq = (
        db.query(MechanicalJointSequence)
        .filter(MechanicalJointSequence.project_id == project_id)
        .with_for_update()
        .first()
    )
    if seq is None:
        seq = MechanicalJointSequence(project_id=project_id, next_val=1)
        db.add(seq)
        db.flush()
    n = seq.next_val
    seq.next_val = n + 1
    db.flush()
    return f"MJ-{project_id:04d}-{n:06d}"


def _validate_joint_part_refs(
    db: Session, project_id: int, data, existing: MechanicalJoint = None
) -> tuple[ProjectPart, ProjectPart]:
    """Validate part_a_id, part_b_id, fastener_part_id, seal_part_id.
    Returns (part_a_pp, part_b_pp). Used by both create and update."""
    part_a_id = data.part_a_id if hasattr(data, 'part_a_id') and data.part_a_id is not None else (
        existing.part_a_id if existing else None
    )
    part_b_id = data.part_b_id if hasattr(data, 'part_b_id') and data.part_b_id is not None else (
        existing.part_b_id if existing else None
    )

    part_a = (
        db.query(ProjectPart)
        .filter(ProjectPart.id == part_a_id, ProjectPart.project_id == project_id)
        .first()
    )
    if not part_a:
        raise HTTPException(
            422,
            {"detail": "part_a_id does not belong to this project",
             "code": "PART_NOT_IN_PROJECT"},
        )
    part_b = (
        db.query(ProjectPart)
        .filter(ProjectPart.id == part_b_id, ProjectPart.project_id == project_id)
        .first()
    )
    if not part_b:
        raise HTTPException(
            422,
            {"detail": "part_b_id does not belong to this project",
             "code": "PART_NOT_IN_PROJECT"},
        )

    if hasattr(data, "fastener_part_id") and data.fastener_part_id is not None:
        fastener = (
            db.query(LibraryPart).filter(LibraryPart.id == data.fastener_part_id).first()
        )
        if not fastener:
            raise HTTPException(
                422, {"detail": "fastener_part_id not found",
                      "code": "PART_NOT_FOUND"},
            )
        if fastener.part_type != PartType.FASTENER:
            raise HTTPException(
                422,
                {"detail": (
                    f"fastener_part_id references a {fastener.part_type.value}, "
                    f"not a fastener"
                ),
                 "code": "INVALID_FASTENER_TYPE"},
            )
        if fastener.status != PartStatus.APPROVED:
            raise HTTPException(
                422,
                {"detail": "Fastener must be APPROVED before use in a joint",
                 "code": "PART_NOT_APPROVED"},
            )

    if hasattr(data, "seal_part_id") and data.seal_part_id is not None:
        seal = db.query(LibraryPart).filter(LibraryPart.id == data.seal_part_id).first()
        if not seal:
            raise HTTPException(
                422, {"detail": "seal_part_id not found",
                      "code": "PART_NOT_FOUND"},
            )
        if seal.part_type != PartType.SEAL:
            raise HTTPException(
                422,
                {"detail": (
                    f"seal_part_id references a {seal.part_type.value}, not a seal"
                ),
                 "code": "INVALID_SEAL_TYPE"},
            )
        if seal.status != PartStatus.APPROVED:
            raise HTTPException(
                422,
                {"detail": "Seal must be APPROVED before use in a joint",
                 "code": "PART_NOT_APPROVED"},
            )

    return part_a, part_b


# ══════════════════════════════════════════════════════════════
#  Endpoints
# ══════════════════════════════════════════════════════════════

@router.get(
    "/projects/{project_id}/mechanical-joints/",
    response_model=list[MechanicalJointResponse],
)
async def list_joints(
    project_id: int,
    joint_type: Optional[JointType] = Query(None),
    status: Optional[JointStatus] = Query(None),
    confidence: Optional[ConfidenceLevel] = Query(None),
    part_id: Optional[int] = Query(None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
):
    q = (
        db.query(MechanicalJoint)
        .options(
            selectinload(MechanicalJoint.part_a)
                .selectinload(ProjectPart.library_part),
            selectinload(MechanicalJoint.part_b)
                .selectinload(ProjectPart.library_part),
            selectinload(MechanicalJoint.fastener_part),
            selectinload(MechanicalJoint.seal_part),
        )
        .filter(MechanicalJoint.project_id == project_id)
    )
    if joint_type:
        q = q.filter(MechanicalJoint.joint_type == joint_type)
    if status:
        q = q.filter(MechanicalJoint.status == status)
    else:
        q = q.filter(MechanicalJoint.status != JointStatus.SUPERSEDED)
    if confidence:
        q = q.filter(MechanicalJoint.confidence == confidence)
    if part_id is not None:
        q = q.filter(
            or_(
                MechanicalJoint.part_a_id == part_id,
                MechanicalJoint.part_b_id == part_id,
            )
        )
    return (
        q.order_by(MechanicalJoint.created_at.desc())
        .offset(offset).limit(limit).all()
    )


@router.post(
    "/projects/{project_id}/mechanical-joints/",
    response_model=MechanicalJointResponse,
    status_code=201,
)
async def create_joint(
    project_id: int,
    data: MechanicalJointCreate,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _validate_joint_part_refs(db, project_id, data)
    joint_id = _assign_joint_id(db, project_id)

    payload = data.model_dump(exclude_none=True)
    joint = MechanicalJoint(
        **payload,
        joint_id=joint_id,
        project_id=project_id,
        status=JointStatus.DRAFT,
        created_by_id=current_user.id,
    )
    db.add(joint)
    db.commit()
    db.refresh(joint)
    if joint.fastener_part_id:
        _ = joint.fastener_part
    if joint.seal_part_id:
        _ = joint.seal_part

    record_event(
        db, "mechanical_joints.joint_created", "mechanical_joint", joint.id,
        current_user.id,
        {
            "joint_id": joint.joint_id,
            "joint_type": joint.joint_type.value,
            "part_a_id": joint.part_a_id,
            "part_b_id": joint.part_b_id,
        },
        project_id=project_id,
    )
    db.commit()
    return joint


@router.get(
    "/projects/{project_id}/mechanical-joints/{joint_id}",
    response_model=MechanicalJointResponse,
)
async def get_joint(
    project_id: int,
    joint_id: str,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
):
    joint = (
        db.query(MechanicalJoint)
        .options(
            selectinload(MechanicalJoint.fastener_part),
            selectinload(MechanicalJoint.seal_part),
        )
        .filter(
            MechanicalJoint.joint_id == joint_id,
            MechanicalJoint.project_id == project_id,
        )
        .first()
    )
    if not joint:
        raise HTTPException(404, "Joint not found")
    return joint


@router.patch(
    "/projects/{project_id}/mechanical-joints/{joint_id}",
    response_model=MechanicalJointResponse,
)
async def update_joint(
    project_id: int,
    joint_id: str,
    data: MechanicalJointUpdate,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    joint = (
        db.query(MechanicalJoint)
        .filter(
            MechanicalJoint.joint_id == joint_id,
            MechanicalJoint.project_id == project_id,
        )
        .first()
    )
    if not joint:
        raise HTTPException(404, "Joint not found")
    if joint.status == JointStatus.SUPERSEDED:
        raise HTTPException(
            409,
            {"detail": "Cannot update a superseded joint",
             "code": "WRONG_STATE"},
        )

    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    if not update_data:
        return joint

    # Validate any newly referenced parts
    if any(
        k in update_data
        for k in ("part_a_id", "part_b_id", "fastener_part_id", "seal_part_id")
    ):
        # Build a temporary object that has the fields we need
        class _T:
            pass
        t = _T()
        for k in ("part_a_id", "part_b_id", "fastener_part_id", "seal_part_id"):
            setattr(t, k, update_data.get(k))
        _validate_joint_part_refs(db, project_id, t, existing=joint)

    before = {k: str(getattr(joint, k)) for k in update_data if hasattr(joint, k)}
    for k, v in update_data.items():
        setattr(joint, k, v)
    db.commit()
    db.refresh(joint)
    if joint.fastener_part_id:
        _ = joint.fastener_part
    if joint.seal_part_id:
        _ = joint.seal_part

    record_event(
        db, "mechanical_joints.joint_updated", "mechanical_joint", joint.id,
        current_user.id,
        {"before": before,
         "after": {k: str(getattr(joint, k)) for k in update_data}},
        project_id=project_id,
    )
    db.commit()
    return joint


@router.delete(
    "/projects/{project_id}/mechanical-joints/{joint_id}",
    status_code=204,
)
async def delete_joint(
    project_id: int,
    joint_id: str,
    force: bool = Query(default=False),
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    joint = (
        db.query(MechanicalJoint)
        .filter(
            MechanicalJoint.joint_id == joint_id,
            MechanicalJoint.project_id == project_id,
        )
        .first()
    )
    if not joint:
        raise HTTPException(404, "Joint not found")
    if joint.status == JointStatus.SUPERSEDED:
        raise HTTPException(
            409,
            {"detail": "Joint is already superseded", "code": "WRONG_STATE"},
        )

    if joint.status == JointStatus.DRAFT:
        joint_db_id = joint.id
        db.delete(joint)
        db.commit()
        record_event(
            db, "mechanical_joints.joint_deleted", "mechanical_joint",
            joint_db_id, current_user.id,
            {"joint_id": joint_id, "status": "draft"},
            project_id=project_id,
        )
        db.commit()
        return

    # ACTIVE joint
    if not force:
        raise HTTPException(
            409,
            {
                "detail": (
                    "Active joints cannot be deleted without force=true. "
                    "Auto-generated requirements are linked to this joint."
                ),
                "code": "ACTIVE_JOINT_REQUIRES_FORCE",
            },
        )
    # Only admin may force
    if str(current_user.role) != UserRole.ADMIN.value and current_user.role != UserRole.ADMIN:
        raise HTTPException(
            403,
            {"detail": "Only admins can force-delete active joints",
             "code": "INSUFFICIENT_ROLE"},
        )

    joint.status = JointStatus.SUPERSEDED
    db.commit()
    record_event(
        db, "mechanical_joints.joint_deleted", "mechanical_joint", joint.id,
        current_user.id,
        {"joint_id": joint_id, "status": "superseded", "force": True},
        project_id=project_id,
    )
    db.commit()


@router.post(
    "/projects/{project_id}/mechanical-joints/{joint_id}/approve",
    response_model=MechanicalJointResponse,
)
async def approve_joint(
    project_id: int,
    joint_id: str,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Approve a DRAFT joint. Generates auto-requirements + RequirementSourceLink
    rows for every applicable template (from JOINT_TYPE_TEMPLATES)."""
    joint = (
        db.query(MechanicalJoint)
        .options(
            selectinload(MechanicalJoint.fastener_part),
            selectinload(MechanicalJoint.seal_part),
        )
        .filter(
            MechanicalJoint.joint_id == joint_id,
            MechanicalJoint.project_id == project_id,
        )
        .first()
    )
    if not joint:
        raise HTTPException(404, "Joint not found")
    if joint.status != JointStatus.DRAFT:
        raise HTTPException(
            409,
            {"detail": f"Joint is already {joint.status.value}",
             "code": "WRONG_STATE"},
        )

    part_a_pp = db.query(ProjectPart).filter(ProjectPart.id == joint.part_a_id).first()
    part_b_pp = db.query(ProjectPart).filter(ProjectPart.id == joint.part_b_id).first()
    part_a_lp = (
        db.query(LibraryPart).filter(LibraryPart.id == part_a_pp.library_part_id).first()
        if part_a_pp else None
    )
    part_b_lp = (
        db.query(LibraryPart).filter(LibraryPart.id == part_b_pp.library_part_id).first()
        if part_b_pp else None
    )
    fastener_lp = joint.fastener_part
    seal_lp = joint.seal_part

    context = build_template_context(joint, part_a_lp, part_b_lp, fastener_lp, seal_lp)
    template_ids = JOINT_TYPE_TEMPLATES.get(joint.joint_type, [])

    requirements_created = 0
    for template_id in template_ids:
        statement = render_template(template_id, context)
        if not statement:
            continue

        req_id_str = next_human_id(
            db, project_id=project_id, prefix="MECH",
            fmt="{prefix}-{n:03d}",
            source_model=Requirement, id_field="req_id",
        )

        title = f"Mechanical Interface: {joint.joint_id} — {template_id}"

        req = Requirement(
            project_id=project_id,
            req_id=req_id_str,
            title=title[:500],
            statement=statement,
            req_type=RequirementType.INTERFACE,
            priority=RequirementPriority.HIGH,
            status=RequirementStatus.AUTO_GENERATED,
            level=RequirementLevel.L3,
            owner_id=current_user.id,
            created_by_id=current_user.id,
            generation_template_id=template_id,
        )
        db.add(req)
        db.flush()

        # RequirementSourceLink — uses existing schema (template_id +
        # template_inputs JSON), not generation_template_id+project_id.
        source_link = RequirementSourceLink(
            requirement_id=req.id,
            source_entity_type=SourceEntityType.MECHANICAL_JOINT,
            source_entity_id=joint.id,
            template_id=template_id,
            template_inputs=context,
            role="primary",
        )
        db.add(source_link)
        requirements_created += 1

    joint.status = JointStatus.ACTIVE
    db.commit()
    db.refresh(joint)
    if joint.fastener_part_id:
        _ = joint.fastener_part
    if joint.seal_part_id:
        _ = joint.seal_part

    record_event(
        db, "mechanical_joints.joint_approved", "mechanical_joint", joint.id,
        current_user.id,
        {
            "joint_id": joint.joint_id,
            "joint_type": joint.joint_type.value,
            "templates_applied": template_ids,
            "requirements_generated": requirements_created,
        },
        project_id=project_id,
    )
    db.commit()
    return joint


# ══════════════════════════════════════════════════════════════
#  Assembly upload (Phase 4 — graceful stub)
# ══════════════════════════════════════════════════════════════

@router.post(
    "/projects/{project_id}/mechanical-joints/upload-assembly",
    status_code=202,
)
async def upload_assembly(
    project_id: int,
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Phase 4 entry point. Creates an AssemblyParseJob in QUEUED state
    and returns the job_id. Background parsing wired in Phase 4."""
    import hashlib, os
    from app.models.document import Document

    filename = file.filename or ""
    if not filename.lower().endswith((".step", ".stp")):
        raise HTTPException(
            400, {"detail": "Only .step and .stp assemblies are accepted",
                  "code": "INVALID_FILE_TYPE"},
        )
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, {"detail": "Empty file", "code": "EMPTY_FILE"})
    checksum = hashlib.sha256(content).hexdigest()

    upload_dir = os.environ.get("UPLOAD_DIR", "/tmp/astra_uploads")
    os.makedirs(upload_dir, exist_ok=True)
    ext = os.path.splitext(filename)[1].lower()
    dest = os.path.join(upload_dir, f"{checksum}{ext}")
    if not os.path.exists(dest):
        with open(dest, "wb") as f:
            f.write(content)

    document = Document(
        filename=filename, file_path=dest, file_size_bytes=len(content),
        sha256=checksum, mime_type="application/step",
        document_type="step_assembly", uploaded_by_id=current_user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    job = AssemblyParseJob(
        project_id=project_id,
        document_id=document.id,
        status=AssemblyParseJobStatus.QUEUED,
        progress_log="Queued",
        created_by_id=current_user.id,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    if background_tasks is not None:
        background_tasks.add_task(
            _run_assembly_parser,
            job_id=job.id, project_id=project_id,
            file_path=dest, user_id=current_user.id,
        )

    return {"job_id": job.id, "status": job.status.value}


@router.get(
    "/projects/{project_id}/mechanical-joints/assembly-parse-status/{job_id}",
    response_model=AssemblyParseJobResponse,
)
async def get_parse_status(
    project_id: int,
    job_id: int,
    project: Project = Depends(project_member_required),
    db: Session = Depends(get_db),
):
    job = (
        db.query(AssemblyParseJob)
        .filter(
            AssemblyParseJob.id == job_id,
            AssemblyParseJob.project_id == project_id,
        )
        .first()
    )
    if not job:
        raise HTTPException(404, "Parse job not found")
    return job


def _run_assembly_parser(
    job_id: int, project_id: int, file_path: str, user_id: int
) -> None:
    """Phase 4 stub. Marks job COMPLETE with empty result so the UI
    polling loop terminates. Full implementation deferred."""
    from app.database import SessionLocal
    db = SessionLocal()
    try:
        job = db.query(AssemblyParseJob).filter(AssemblyParseJob.id == job_id).first()
        if not job:
            return
        job.status = AssemblyParseJobStatus.RUNNING
        job.progress_log = (job.progress_log or "") + "\nRunning (stub)"
        db.commit()

        # Minimal: try to parse_assembly_step via parts.assembly_parser
        try:
            from app.services.parts.assembly_parser import parse_assembly_step
            project_parts = (
                db.query(ProjectPart)
                .options(selectinload(ProjectPart.library_part))
                .filter(ProjectPart.project_id == project_id)
                .all()
            )
            lookup: dict[str, int] = {}
            for pp in project_parts:
                lp = pp.library_part
                if lp.name:
                    lookup[lp.name.lower()] = lp.id
                if lp.manufacturer_part_number:
                    lookup[lp.manufacturer_part_number.lower()] = lp.id
                if lp.wardstone_part_number:
                    lookup[lp.wardstone_part_number.lower()] = lp.id
            parse_result = parse_assembly_step(file_path, lookup)
            job.progress_log = (
                (job.progress_log or "") + "\n" + parse_result.extraction_log
            )
            job.result = {
                "joints_created": 0,
                "unmatched_parts": parse_result.unmatched_instance_names,
                "transforms": [],
                "occ_available": parse_result.occ_available,
            }
        except Exception as exc:
            job.progress_log = (
                (job.progress_log or "") + f"\nParser exception: {exc}"
            )
            job.result = {
                "joints_created": 0, "unmatched_parts": [],
                "transforms": [], "occ_available": False,
            }

        job.status = AssemblyParseJobStatus.COMPLETE
        job.completed_at = func.now()
        db.commit()
        record_event(
            db, "mechanical_joints.assembly_parsed", "assembly_parse_job",
            job.id, user_id,
            {"joints_created": (job.result or {}).get("joints_created", 0)},
            project_id=project_id,
        )
        db.commit()
    except Exception as exc:
        import traceback
        logger.error("Assembly parser failed: %s", exc)
        try:
            job = (
                db.query(AssemblyParseJob).filter(AssemblyParseJob.id == job_id).first()
            )
            if job:
                job.status = AssemblyParseJobStatus.FAILED
                job.error = traceback.format_exc()
                job.completed_at = func.now()
                db.commit()
        except Exception:
            db.rollback()
    finally:
        db.close()
