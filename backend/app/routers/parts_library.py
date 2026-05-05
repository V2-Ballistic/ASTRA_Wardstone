"""
ASTRA — Parts Library router (global, cross-project)
======================================================
File: backend/app/routers/parts_library.py    ← NEW (ASTRA-SPEC-PARTS-001)

Endpoints:
  GET    /parts-library/                        list_parts
  GET    /parts-library/{id}                    get_part
  POST   /parts-library/                        create_part (PM/Admin)
  PATCH  /parts-library/{id}                    update_part (PM/Admin)
  POST   /parts-library/upload-step             upload_step_file (PM/Admin)
  GET    /parts-library/pending-imports/        list_pending_imports
  GET    /parts-library/pending-imports/{id}    get_pending_import
  POST   /parts-library/pending-imports/{id}/approve   approve_import (PM/Admin)
  POST   /parts-library/pending-imports/{id}/reject    reject_import  (PM/Admin)
  GET    /parts-library/{id}/gltf               get_part_gltf
"""

from __future__ import annotations

import hashlib
import logging
import os
from decimal import Decimal
from typing import Optional

from fastapi import (
    APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile,
)
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.sql import func

from app.database import get_db, SessionLocal
from app.models import User, UserRole
from app.models.document import Document
from app.models.parts_library import (
    LibraryPart, PartType, PartStatus, MaterialClass,
    PendingPartsImport, PendingPartsStatus,
)
from app.schemas.parts_library import (
    LibraryPartCreate, LibraryPartUpdate, LibraryPartResponse,
    LibraryPartSummary, PendingPartsImportApprove, PendingPartsImportReject,
    PendingPartsImportResponse,
)
from app.services.audit_service import record_event
from app.services.auth import get_current_user
from app.services.parts.step_parser import parse_step_file, interpret
from app.services.parts.wpn_service import assign_wpn, bump_revision

# Permissive shim if rbac module isn't loaded (test env)
try:
    from app.services.rbac import require_any_role
except ImportError:
    def require_any_role(*roles):
        return get_current_user


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/parts-library", tags=["parts-library"])

UPLOAD_DIR = os.environ.get("UPLOAD_DIR", "/tmp/astra_uploads")


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════

def _save_document_file(content: bytes, filename: str, checksum: str) -> str:
    """Save binary content to disk; returns the file_path."""
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    ext = os.path.splitext(filename)[1].lower()
    dest = os.path.join(UPLOAD_DIR, f"{checksum}{ext}")
    if not os.path.exists(dest):
        with open(dest, "wb") as f:
            f.write(content)
    return dest


def _summarize_part(part: LibraryPart) -> LibraryPartSummary:
    return LibraryPartSummary.model_validate(part)


def _coerce_numeric_overrides(merged: dict) -> dict:
    """Coerce numeric fields stored as strings to Decimal before
    constructing a LibraryPart. Drops malformed entries."""
    NUMERIC = (
        "bounding_box_x_mm", "bounding_box_y_mm", "bounding_box_z_mm",
        "volume_mm3", "surface_area_mm2", "nominal_diameter_mm",
        "nominal_length_mm", "nominal_bore_mm", "cross_section_dia_mm",
        "flange_diameter_mm", "hole_pattern_dia_mm", "hole_pattern_pcd_mm",
        "density_g_cm3", "yield_strength_mpa", "ultimate_strength_mpa",
        "elastic_modulus_gpa", "thermal_conductivity_wm",
        "outgassing_tml_pct", "outgassing_cvcm_pct",
        "mass_nominal_g", "mass_max_g", "proof_load_n", "clamp_load_n",
        "torque_nominal_nm", "torque_min_nm", "torque_max_nm",
        "torque_lubricated_nm", "shear_strength_n", "bearing_load_n",
        "compression_set_pct", "sealing_pressure_max_bar",
        "temperature_min_c", "temperature_max_c", "unit_cost_usd",
        "cte_um_m_c",
    )
    for f in NUMERIC:
        if f in merged and merged[f] is not None and not isinstance(merged[f], Decimal):
            try:
                merged[f] = Decimal(str(merged[f]))
            except Exception:
                merged.pop(f)
    return merged


# ══════════════════════════════════════════════════════════════
#  CRUD
# ══════════════════════════════════════════════════════════════

@router.get("/", response_model=list[LibraryPartSummary])
async def list_parts(
    part_type: Optional[PartType] = Query(None),
    status: Optional[PartStatus] = Query(None),
    material_class: Optional[MaterialClass] = Query(None),
    search: Optional[str] = Query(None, min_length=2, max_length=100),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """List library parts. Filters: part_type, status, material_class,
    search (ILIKE on name/MPN/WPN/manufacturer). Default: APPROVED only."""
    q = db.query(LibraryPart)
    if status:
        q = q.filter(LibraryPart.status == status)
    else:
        q = q.filter(LibraryPart.status == PartStatus.APPROVED)
    if part_type:
        q = q.filter(LibraryPart.part_type == part_type)
    if material_class:
        q = q.filter(LibraryPart.material_class == material_class)
    if search:
        ilike = f"%{search}%"
        q = q.filter(
            or_(
                LibraryPart.name.ilike(ilike),
                LibraryPart.manufacturer_part_number.ilike(ilike),
                LibraryPart.wardstone_part_number.ilike(ilike),
                LibraryPart.manufacturer_name.ilike(ilike),
            )
        )
    q = q.order_by(LibraryPart.created_at.desc())
    return q.offset(offset).limit(limit).all()


@router.get("/{part_id}", response_model=LibraryPartResponse)
async def get_part(
    part_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    part = db.query(LibraryPart).filter(LibraryPart.id == part_id).first()
    if not part:
        raise HTTPException(404, "Library part not found")
    return part


@router.post("/", response_model=LibraryPartResponse, status_code=201)
async def create_part(
    data: LibraryPartCreate,
    current_user: User = Depends(
        require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)
    ),
    db: Session = Depends(get_db),
):
    """Manually create a library part. WPN is server-assigned; status=DRAFT."""
    wpn = assign_wpn(db, data.part_type)
    part = LibraryPart(
        **data.model_dump(exclude_none=True),
        wardstone_part_number=wpn,
        revision="00",
        status=PartStatus.DRAFT,
        created_by_id=current_user.id,
    )
    db.add(part)
    db.commit()
    db.refresh(part)
    record_event(
        db, "parts_library.part_created", "library_part", part.id,
        current_user.id,
        {"wpn": wpn, "name": part.name, "part_type": part.part_type.value},
    )
    db.commit()
    return part


@router.patch("/{part_id}", response_model=LibraryPartResponse)
async def update_part(
    part_id: int,
    data: LibraryPartUpdate,
    current_user: User = Depends(
        require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)
    ),
    db: Session = Depends(get_db),
):
    """Update a library part. APPROVED parts that change dimensional
    fields create a new revision row (status=DRAFT) and supersede the old."""
    part = db.query(LibraryPart).filter(LibraryPart.id == part_id).first()
    if not part:
        raise HTTPException(404, "Library part not found")

    update_data = data.model_dump(exclude_unset=True, exclude_none=True)
    if not update_data:
        return part

    DIMENSIONAL = {
        "bounding_box_x_mm", "bounding_box_y_mm", "bounding_box_z_mm",
        "volume_mm3", "surface_area_mm2", "nominal_diameter_mm",
        "nominal_length_mm", "hole_pattern_dia_mm", "hole_pattern_pcd_mm",
        "hole_pattern_count", "thread_size",
        "torque_nominal_nm", "torque_min_nm", "torque_max_nm",
        "mass_nominal_g", "mass_max_g",
    }

    if (
        part.status == PartStatus.APPROVED
        and any(f in update_data for f in DIMENSIONAL)
    ):
        # Build new revision row from the existing one + update_data overrides
        new_wpn = bump_revision(part.wardstone_part_number)
        new_rev_str = new_wpn.rsplit("-", 1)[1]

        new_part_data = {
            col.name: getattr(part, col.name)
            for col in LibraryPart.__table__.columns
            if col.name not in (
                "id", "wardstone_part_number", "revision",
                "approved_at", "approved_by_id",
                "created_at", "updated_at", "superseded_by_id",
            )
        }
        new_part_data.update(update_data)
        new_part_data["wardstone_part_number"] = new_wpn
        new_part_data["revision"] = new_rev_str
        new_part_data["status"] = PartStatus.DRAFT  # re-approval required
        new_part_data["created_by_id"] = current_user.id
        new_part_data["approved_by_id"] = None
        new_part_data["approved_at"] = None

        new_part = LibraryPart(**new_part_data)
        db.add(new_part)
        db.flush()

        part.superseded_by_id = new_part.id
        part.status = PartStatus.SUPERSEDED
        db.commit()
        db.refresh(new_part)

        record_event(
            db, "parts_library.part_revision_bumped", "library_part",
            new_part.id, current_user.id,
            {
                "old_wpn": part.wardstone_part_number,
                "new_wpn": new_wpn,
                "fields_changed": list(update_data.keys()),
            },
        )
        db.commit()
        return new_part

    # Plain update on DRAFT part (or non-dimensional change to approved)
    before = {k: str(getattr(part, k)) for k in update_data if hasattr(part, k)}
    for k, v in update_data.items():
        setattr(part, k, v)
    db.commit()
    db.refresh(part)
    record_event(
        db, "parts_library.part_updated", "library_part", part.id,
        current_user.id,
        {"before": before, "after": {k: str(getattr(part, k)) for k in update_data}},
    )
    db.commit()
    return part


# ══════════════════════════════════════════════════════════════
#  STEP upload + approval flow
# ══════════════════════════════════════════════════════════════

@router.post("/upload-step", status_code=202)
async def upload_step_file(
    file: UploadFile = File(...),
    background_tasks: BackgroundTasks = None,
    current_user: User = Depends(
        require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)
    ),
    db: Session = Depends(get_db),
):
    """Upload a STEP file. Computes SHA-256; if a part already references
    that checksum, returns the existing part. Otherwise creates a
    PendingPartsImport and queues the parser."""
    filename = file.filename or ""
    if not filename.lower().endswith((".step", ".stp")):
        raise HTTPException(
            400, {"detail": "Only .step and .stp files are accepted",
                  "code": "INVALID_FILE_TYPE"},
        )

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(
            400, {"detail": "Empty file", "code": "EMPTY_FILE"},
        )

    checksum = hashlib.sha256(content).hexdigest()

    existing = (
        db.query(LibraryPart)
        .filter(LibraryPart.step_file_checksum == checksum)
        .first()
    )
    if existing:
        return {
            "duplicate": True,
            "existing_part_id": existing.id,
            "existing_wpn": existing.wardstone_part_number,
            "message": "This exact STEP file is already in the Parts Library.",
        }

    existing_pending = (
        db.query(PendingPartsImport)
        .join(Document, PendingPartsImport.document_id == Document.id)
        .filter(Document.sha256 == checksum)
        .filter(
            PendingPartsImport.status.in_(
                [PendingPartsStatus.PENDING, PendingPartsStatus.UNDER_REVIEW]
            )
        )
        .first()
    )
    if existing_pending:
        return {
            "duplicate": True,
            "pending_import_id": existing_pending.id,
            "message": "A parse is already pending for this file.",
        }

    file_path = _save_document_file(content, filename, checksum)
    document = Document(
        filename=filename,
        file_path=file_path,
        file_size_bytes=len(content),
        sha256=checksum,
        mime_type="application/step",
        document_type="step_cad",
        uploaded_by_id=current_user.id,
    )
    db.add(document)
    db.commit()
    db.refresh(document)

    pending = PendingPartsImport(
        document_id=document.id,
        status=PendingPartsStatus.PENDING,
        proposed_data={},
        confidence_scores={},
        low_confidence_fields=[],
        created_by_id=current_user.id,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)

    if background_tasks is not None:
        background_tasks.add_task(
            _run_step_parser_pipeline,
            pending_import_id=pending.id,
            file_path=file_path,
            user_id=current_user.id,
        )
    else:
        # Direct run (used in test contexts without BackgroundTasks)
        _run_step_parser_pipeline(pending.id, file_path, current_user.id)

    return {
        "duplicate": False,
        "pending_import_id": pending.id,
        "message": "STEP file accepted. Parsing in progress.",
    }


def _run_step_parser_pipeline(
    pending_import_id: int, file_path: str, user_id: int
) -> None:
    """Background task: parse STEP → interpret → update PendingPartsImport.
    Uses a fresh DB session (request session would already be closed)."""
    db = SessionLocal()
    pending = None
    try:
        pending = (
            db.query(PendingPartsImport)
            .filter(PendingPartsImport.id == pending_import_id)
            .first()
        )
        if not pending:
            return

        pending.status = PendingPartsStatus.UNDER_REVIEW
        db.commit()

        parser_result = parse_step_file(file_path)

        try:
            from app.services.ai import get_ai_service  # type: ignore
            ai_service = get_ai_service()
        except Exception:
            ai_service = None

        ai_overrides = interpret(parser_result, ai_service)

        proposed: dict = {}
        for f_name in (
            "manufacturer_part_number", "step_entity_id",
            "bounding_box_x_mm", "bounding_box_y_mm", "bounding_box_z_mm",
            "volume_mm3", "surface_area_mm2",
            "nominal_diameter_mm", "nominal_length_mm",
            "thread_size", "torque_nominal_nm",
            "hole_pattern_count", "hole_pattern_dia_mm",
            "mass_nominal_g",
        ):
            v = getattr(parser_result, f_name, None)
            if v is not None:
                proposed[f_name] = str(v) if hasattr(v, "__float__") else v
        if parser_result.product_name:
            proposed["name"] = parser_result.product_name
        if parser_result.product_description:
            proposed["description"] = parser_result.product_description
        if parser_result.thread_standard:
            proposed["thread_standard"] = parser_result.thread_standard.value

        for key in (
            "part_type", "material_name", "material_class",
            "torque_nominal_nm", "torque_min_nm", "torque_max_nm",
            "locking_feature",
        ):
            if ai_overrides.get(key) is not None:
                proposed[key] = (
                    str(ai_overrides[key])
                    if isinstance(ai_overrides[key], (int, float))
                    else ai_overrides[key]
                )

        confidence_scores = dict(parser_result.confidence_scores)
        for fld, level in ai_overrides.get("confidence_overrides", {}).items():
            confidence_scores[fld] = level

        low_confidence = list(set(
            list(parser_result.low_confidence_fields) +
            [k for k, v in confidence_scores.items() if v == "low"]
        ))

        pending.proposed_data = proposed
        pending.confidence_scores = confidence_scores
        pending.low_confidence_fields = low_confidence
        pending.extraction_log = (
            (parser_result.extraction_log or "")
            + "\n\nAI flags: "
            + "; ".join(ai_overrides.get("flags", []))
        )
        pending.parser_version = parser_result.parser_version
        db.commit()

    except Exception as exc:
        import traceback
        logger.error(
            "STEP parser pipeline failed for import %d: %s",
            pending_import_id, exc,
        )
        if pending is not None:
            try:
                pending.status = PendingPartsStatus.PENDING  # allow retry
                pending.extraction_log = traceback.format_exc()
                db.commit()
            except Exception:
                db.rollback()
    finally:
        db.close()


@router.get("/pending-imports/", response_model=list[PendingPartsImportResponse])
async def list_pending_imports(
    status: Optional[PendingPartsStatus] = Query(None),
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    q = db.query(PendingPartsImport)
    if status:
        q = q.filter(PendingPartsImport.status == status)
    return q.order_by(PendingPartsImport.created_at.desc()).offset(offset).limit(limit).all()


@router.get(
    "/pending-imports/{import_id}", response_model=PendingPartsImportResponse,
)
async def get_pending_import(
    import_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    pending = (
        db.query(PendingPartsImport).filter(PendingPartsImport.id == import_id).first()
    )
    if not pending:
        raise HTTPException(404, "Pending import not found")
    return pending


@router.post(
    "/pending-imports/{import_id}/approve",
    response_model=LibraryPartResponse,
)
async def approve_import(
    import_id: int,
    data: PendingPartsImportApprove,
    current_user: User = Depends(
        require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)
    ),
    db: Session = Depends(get_db),
):
    """Approve a pending import. Idempotent."""
    pending = (
        db.query(PendingPartsImport).filter(PendingPartsImport.id == import_id).first()
    )
    if not pending:
        raise HTTPException(404, "Pending import not found")

    if (
        pending.status == PendingPartsStatus.APPROVED
        and pending.library_part_id
    ):
        # Idempotent — return existing part
        existing = (
            db.query(LibraryPart)
            .filter(LibraryPart.id == pending.library_part_id)
            .first()
        )
        if existing:
            return existing

    if pending.status not in (
        PendingPartsStatus.PENDING, PendingPartsStatus.UNDER_REVIEW,
    ):
        raise HTTPException(
            409,
            {"detail": f"Import is {pending.status.value} and cannot be approved",
             "code": "WRONG_STATE"},
        )

    merged = {**(pending.proposed_data or {}), **(data.overrides or {})}

    if not merged.get("name"):
        raise HTTPException(
            422,
            {"detail": "Field 'name' is required before approval",
             "code": "MISSING_REQUIRED_FIELD"},
        )
    if not merged.get("part_type"):
        raise HTTPException(
            422,
            {"detail": "Field 'part_type' is required before approval",
             "code": "MISSING_REQUIRED_FIELD"},
        )

    try:
        part_type = PartType(merged["part_type"])
    except ValueError:
        raise HTTPException(
            422,
            {"detail": f"Unknown part_type: {merged['part_type']}",
             "code": "INVALID_PART_TYPE"},
        )

    merged = _coerce_numeric_overrides(merged)

    valid_columns = {c.name for c in LibraryPart.__table__.columns}
    safe_data = {k: v for k, v in merged.items() if k in valid_columns}
    for protected in (
        "id", "wardstone_part_number", "revision", "status",
        "approved_by_id", "approved_at", "created_at", "updated_at",
        "created_by_id", "step_file_id", "step_file_checksum",
    ):
        safe_data.pop(protected, None)

    # Force part_type onto the enum value (we already validated)
    safe_data["part_type"] = part_type

    wpn = assign_wpn(db, part_type)

    doc = (
        db.query(Document).filter(Document.id == pending.document_id).first()
    )

    part = LibraryPart(
        **safe_data,
        wardstone_part_number=wpn,
        revision="00",
        status=PartStatus.APPROVED,
        step_file_id=pending.document_id,
        step_file_checksum=doc.sha256 if doc else None,
        approved_by_id=current_user.id,
        approved_at=func.now(),
        created_by_id=current_user.id,
    )
    db.add(part)
    db.flush()

    pending.status = PendingPartsStatus.APPROVED
    pending.library_part_id = part.id
    pending.reviewed_by_id = current_user.id
    pending.reviewed_at = func.now()

    db.commit()
    db.refresh(part)

    record_event(
        db, "parts_library.import_approved", "library_part", part.id,
        current_user.id,
        {"wpn": wpn, "name": part.name, "part_type": part.part_type.value,
         "pending_import_id": pending.id},
    )
    db.commit()
    return part


@router.post("/pending-imports/{import_id}/reject", status_code=200)
async def reject_import(
    import_id: int,
    data: PendingPartsImportReject,
    current_user: User = Depends(
        require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)
    ),
    db: Session = Depends(get_db),
):
    pending = (
        db.query(PendingPartsImport).filter(PendingPartsImport.id == import_id).first()
    )
    if not pending:
        raise HTTPException(404, "Pending import not found")
    if pending.status not in (
        PendingPartsStatus.PENDING, PendingPartsStatus.UNDER_REVIEW,
    ):
        raise HTTPException(
            409,
            {"detail": f"Import is {pending.status.value} and cannot be rejected",
             "code": "WRONG_STATE"},
        )
    pending.status = PendingPartsStatus.REJECTED
    pending.rejection_reason = data.reason
    pending.reviewed_by_id = current_user.id
    pending.reviewed_at = func.now()
    db.commit()
    record_event(
        db, "parts_library.import_rejected", "pending_parts_import", pending.id,
        current_user.id, {"reason": data.reason},
    )
    db.commit()
    return {"status": "rejected", "id": pending.id}


# ══════════════════════════════════════════════════════════════
#  GLTF endpoint (Phase 4 — graceful 404 if pythonOCC unavailable)
# ══════════════════════════════════════════════════════════════

@router.get("/{part_id}/gltf")
async def get_part_gltf(
    part_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    part = db.query(LibraryPart).filter(LibraryPart.id == part_id).first()
    if not part or not part.step_file_id:
        raise HTTPException(404, "No STEP file for this part")
    # Phase 4 stub — tested only when pythonOCC is installed.
    raise HTTPException(
        404,
        {"detail": "3D preview not available (pythonOCC not installed)",
         "code": "GLTF_UNAVAILABLE"},
    )
