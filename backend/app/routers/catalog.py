"""
ASTRA — Catalog Router (Suppliers, Documents, Catalog Parts, Pending Imports)
==============================================================================
File: backend/app/routers/catalog.py   ← NEW (Phase 2, ASTRA-TDD-INTF-002)

Mounts at ``/api/v1/catalog``. Implements §9.1, §9.2, §9.3, and the read-only
slice of §9.4 (pending imports — POST extract / approve / reject ship in
Phase 7 alongside the AI ingestion pipeline).

Behaviour notes
---------------
- Pure catalog reads/writes (suppliers, parts, documents) are GLOBAL — they
  do NOT require project membership.
- Project-scoped operations (``/parts/{id}/place``) DO require
  ``project_member_required`` per audit Phase 1 (F-014).
- Pagination cap: ``limit ≤ 200``. Larger values produce a 422 via FastAPI's
  ``Query(..., le=200)`` declaration.
- Audit emit pattern follows existing routers — uses
  ``app.services.audit_service.record_event`` aliased as ``_audit``.
- File storage: ``/data/supplier_docs/{uuid}.{ext}`` (the directory is
  created on first upload). SHA-256 dedup is *per-supplier* — the same
  datasheet may be re-uploaded under a different vendor.
- Brand-new placement is a separate path on the POST /parts handler:
  if ``placement`` is supplied alongside ``new_supplier``/``supplier_id``,
  the part is also placed in the same atomic boundary.

RBAC
----
Per spec §6 / digest §4:

| Action                      | admin | proj_mgr | req_eng | reviewer | stakeholder |
|-----------------------------|-------|----------|---------|----------|-------------|
| Create / edit Supplier      | ✓     | ✓        | ✓       | ✗        | ✗           |
| Delete Supplier             | ✓     | ✗        | ✗       | ✗        | ✗           |
| Upload SupplierDocument     | ✓     | ✓        | ✓       | ✗        | ✗           |
| Create / edit CatalogPart   | ✓     | ✓        | ✓       | ✗        | ✗           |
| Delete CatalogPart          | ✓     | ✗        | ✗       | ✗        | ✗           |
| Place CatalogPart           | ✓     | ✓        | ✓       | ✗        | ✗           |

The project-side ``interfaces.create`` / ``interfaces.update`` /
``interfaces.delete`` permission strings already grant the matching role
matrix — we reuse those rather than introducing brand-new permission
keys (avoids a corresponding rbac.py edit just for Phase 2).
"""

from __future__ import annotations

import hashlib
import logging
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies.project_access import project_member_required
from app.models import Project, User, UserRole
from app.models.catalog import (
    CatalogConnector,
    CatalogPart,
    CatalogPin,
    ExtractionStatus,
    LifecycleStatus,
    LRUClass,
    PartClass,
    PendingCatalogImport,
    PendingImportStatus,
    Supplier,
    SupplierAlias,                      # TDD-CAT-002
    SupplierDocument,
    SupplierDocumentType,
)
from app.models.interface import Unit
# CLEANUP-002 Phase 4 (AD-7 + AD-8): the catalog_part usage check
# spans project_parts (direct) and mechanical_joints (transitive via
# project_parts.part_a_id / part_b_id, per Phase 0). Both live in the
# legacy parts_library models module.
from app.models.parts_library import MechanicalJoint, ProjectPart
from app.schemas.catalog import (
    CatalogConnectorResponse,
    CatalogDocumentMetadata,           # HAROLD-IN-WRENCH-001 Phase 6
    CatalogDocumentsResponse,          # HAROLD-IN-WRENCH-001 Phase 6
    CatalogPartCreate,
    CatalogPartPlacementRequest,
    CatalogPartResponse,
    CatalogPartSummary,
    CatalogPartUpdate,
    CatalogPartUsageProjectEntry,
    CatalogPartUsageReport,
    CatalogPartUsageRow,
    CatalogPinResponse,
    IcdExtractionResultSchema,
    IcdExtractionTriggerResponse,
    PendingCatalogImportResponse,
    PendingCatalogImportUpdate,
    PendingImportRejectRequest,
    StepUploadResponse,                # TDD-CAT-002
    SupplierCreate,
    SupplierDocumentResponse,
    SupplierResponse,
    SupplierUpdate,
)
from app.schemas.harold import (
    CatalogDesignatorEntry,
    CatalogDesignatorsResponseV2,  # TDD-HAROLD-INT-002 Phase 3 (AD-9)
)
from app.schemas.interface import UnitResponse
from app.config import settings
from app.services.auth import get_current_user
from app.services.catalog import placement as placement_svc

# Optional audit
try:
    from app.services.audit_service import record_event as _audit
except ImportError:  # pragma: no cover - dev test fallback
    def _audit(*a, **kw):
        pass

# Optional HAROLD V2 integration (TDD-HAROLD-INT-002 Phase 3).
# Loaded lazily and gated on settings.HAROLD_INTEGRATION_ENABLED so
# legacy paths keep working unmodified when the flag is off
# (gotcha #12 — flag-off behaviour must be byte-identical to today).
try:
    from app.services.harold import (
        HaroldDuplicateError,
        issue_wpn_for_catalog_part as _harold_issue,
        suggest_wpn_for_part as _harold_suggest,
        validate_filename_wpn as _harold_validate_filename,
    )
    _HAROLD_AVAILABLE = True
except ImportError:  # pragma: no cover
    _HAROLD_AVAILABLE = False
    HaroldDuplicateError = Exception  # type: ignore[assignment,misc]

# Optional RBAC
try:
    from app.services.rbac import require_permission
except ImportError:  # pragma: no cover - dev test fallback
    def require_permission(_action: str):
        return get_current_user

logger = logging.getLogger("astra.catalog")

router = APIRouter(prefix="/catalog", tags=["Catalog"])


# Storage root for supplier documents. Created lazily on first upload —
# the entrypoint container may not have /data pre-mounted in dev/test.
SUPPLIER_DOC_DIR = Path(os.environ.get("SUPPLIER_DOC_DIR", "/data/supplier_docs"))

# Permission keys (reused from existing matrix; see module docstring).
_PERM_CATALOG_WRITE = "interfaces.update"   # req_eng+
_PERM_CATALOG_DELETE = "interfaces.delete"  # admin / proj_mgr — refined to admin in handlers


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════

def _user_role(user: User) -> Optional[UserRole]:
    try:
        return UserRole(user.role) if isinstance(user.role, str) else user.role
    except ValueError:
        return None


def _is_admin(user: User) -> bool:
    return _user_role(user) == UserRole.ADMIN


def _require_admin(user: User) -> None:
    if not _is_admin(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions: admin role required",
        )


def _require_req_eng_plus(user: User) -> User:
    """Allow admin / project_manager / requirements_engineer; deny others."""
    role = _user_role(user)
    if role in (
        UserRole.ADMIN,
        UserRole.PROJECT_MANAGER,
        UserRole.REQUIREMENTS_ENGINEER,
    ):
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Insufficient permissions: catalog write requires admin, "
            "project_manager, or requirements_engineer role"
        ),
    )


def _get_supplier_or_404(db: Session, supplier_id: int) -> Supplier:
    s = db.query(Supplier).filter(Supplier.id == supplier_id).first()
    if s is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Supplier {supplier_id} not found",
        )
    return s


def _get_catalog_part_or_404(db: Session, part_id: int) -> CatalogPart:
    p = db.query(CatalogPart).filter(CatalogPart.id == part_id).first()
    if p is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CatalogPart {part_id} not found",
        )
    return p


def _build_catalog_part_usage_report(
    db: Session, part: CatalogPart,
) -> CatalogPartUsageReport:
    """CLEANUP-002 Phase 4 (AD-7 + AD-8). Usage report across the
    three "downstream consumer" categories that should block delete:

        project_parts.catalog_part_id              (direct, BOM lines)
        mechanical_joints.part_a_id / part_b_id    (transitive via project_parts)
        units.catalog_part_id                      (direct, project placements)

    ``deletable`` is true iff every count is zero.

    Phase 0's FK sweep also flagged catalog_connectors.catalog_part_id
    and catalog_parts.parent_part_id (variant children). Both were
    excluded after writing the first cut against the existing test
    suite: connectors are *owned* by the part (the part's own pin
    definition) and cascade with it on hard-delete; parent_part_id
    is ``ON DELETE SET NULL`` so it doesn't block at the DB level
    and variant children survive parent deletion with the parent
    link nulled. Counting either as "usage" 409'd the pre-Phase-4
    test that creates a part with connectors and immediately deletes
    it, which is a legitimate flow.

    Pending-import committed FKs and assembly_components are also
    excluded — Phase 0 confirmed the former is ON DELETE SET NULL
    and the latter table doesn't exist.
    """
    pp_rows = (
        db.query(ProjectPart.id, ProjectPart.project_id)
        .filter(ProjectPart.catalog_part_id == part.id)
        .all()
    )
    pp_ids = [r[0] for r in pp_rows]

    # Mechanical joints reach catalog_parts only through project_parts;
    # mechanical_joints itself has no deleted_at column (Phase 0).
    joint_rows: List = []
    if pp_ids:
        joint_rows = (
            db.query(MechanicalJoint.id, MechanicalJoint.project_id)
            .filter(
                or_(
                    MechanicalJoint.part_a_id.in_(pp_ids),
                    MechanicalJoint.part_b_id.in_(pp_ids),
                )
            )
            .all()
        )

    unit_rows = (
        db.query(Unit.id, Unit.project_id)
        .filter(Unit.catalog_part_id == part.id)
        .all()
    )

    # Aggregate the project-scoped categories. A project may have zero
    # of any one category but still show up because it has the others.
    project_aggregate: Dict[int, CatalogPartUsageProjectEntry] = {}

    def _ensure_entry(proj_id: int) -> CatalogPartUsageProjectEntry:
        if proj_id not in project_aggregate:
            proj = (
                db.query(Project.code, Project.name)
                .filter(Project.id == proj_id)
                .first()
            )
            project_aggregate[proj_id] = CatalogPartUsageProjectEntry(
                project_id=proj_id,
                project_name=proj[1] if proj else None,
                project_code=proj[0] if proj else None,
            )
        return project_aggregate[proj_id]

    for _pp_id, proj_id in pp_rows:
        _ensure_entry(proj_id).project_part_count += 1
    for _j_id, proj_id in joint_rows:
        _ensure_entry(proj_id).mechanical_joint_count += 1
    for _u_id, proj_id in unit_rows:
        _ensure_entry(proj_id).unit_count += 1

    total = len(pp_rows) + len(joint_rows) + len(unit_rows)

    return CatalogPartUsageReport(
        part_id=part.id,
        part_number=part.part_number,
        internal_part_number=part.internal_part_number,
        total_references=total,
        deletable=total == 0,
        projects=sorted(
            project_aggregate.values(),
            key=lambda e: (e.project_code or "", e.project_id),
        ),
    )


def _supplier_response(db: Session, s: Supplier) -> SupplierResponse:
    parts_count = (
        db.query(func.count(CatalogPart.id))
        .filter(CatalogPart.supplier_id == s.id)
        .scalar()
        or 0
    )
    docs_count = (
        db.query(func.count(SupplierDocument.id))
        .filter(SupplierDocument.supplier_id == s.id)
        .scalar()
        or 0
    )
    resp = SupplierResponse.model_validate(s)
    resp.catalog_part_count = parts_count
    resp.document_count = docs_count
    return resp


def _catalog_part_response(db: Session, p: CatalogPart) -> CatalogPartResponse:
    """Detail response with eager connectors/pins + supplier + usage count."""
    supplier_name = (
        db.query(Supplier.name)
        .filter(Supplier.id == p.supplier_id)
        .scalar()
    )
    used_in = (
        db.query(func.count(Unit.id))
        .filter(Unit.catalog_part_id == p.id)
        .scalar()
        or 0
    )

    # Eager-load connectors and pins.
    connectors = (
        db.query(CatalogConnector)
        .filter(CatalogConnector.catalog_part_id == p.id)
        .order_by(CatalogConnector.position)
        .all()
    )
    conn_responses: List[CatalogConnectorResponse] = []
    for c in connectors:
        pins = (
            db.query(CatalogPin)
            .filter(CatalogPin.catalog_connector_id == c.id)
            .order_by(CatalogPin.pin_position)
            .all()
        )
        pin_resps = [CatalogPinResponse.model_validate(pi) for pi in pins]
        conn_resp = CatalogConnectorResponse.model_validate(c)
        conn_resp.pins = pin_resps
        conn_responses.append(conn_resp)

    resp = CatalogPartResponse.model_validate(p)
    resp.supplier_name = supplier_name
    resp.used_in_project_count = used_in
    resp.connectors = conn_responses
    return resp


def _catalog_part_summary(
    db: Session, p: CatalogPart, *, supplier_name_cache: Optional[Dict[int, str]] = None,
    usage_cache: Optional[Dict[int, int]] = None,
) -> CatalogPartSummary:
    if supplier_name_cache is not None and p.supplier_id in supplier_name_cache:
        sname = supplier_name_cache[p.supplier_id]
    else:
        sname = (
            db.query(Supplier.name).filter(Supplier.id == p.supplier_id).scalar()
        )
    if usage_cache is not None and p.id in usage_cache:
        usage = usage_cache[p.id]
    else:
        usage = (
            db.query(func.count(Unit.id))
            .filter(Unit.catalog_part_id == p.id)
            .scalar()
            or 0
        )
    resp = CatalogPartSummary.model_validate(p)
    resp.supplier_name = sname
    resp.used_in_project_count = usage
    return resp


# ══════════════════════════════════════════════════════════════
#  §9.1 Suppliers
# ══════════════════════════════════════════════════════════════

@router.get("/suppliers", response_model=List[SupplierResponse])
def list_suppliers(
    q: Optional[str] = Query(None, description="Search by name or cage_code"),
    is_active: Optional[bool] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List suppliers with optional search + pagination."""
    query = db.query(Supplier)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Supplier.name.ilike(like), Supplier.cage_code.ilike(like)))
    if is_active is not None:
        query = query.filter(Supplier.is_active == is_active)
    suppliers = query.order_by(Supplier.name).offset(skip).limit(limit).all()
    return [_supplier_response(db, s) for s in suppliers]


@router.post("/suppliers", response_model=SupplierResponse, status_code=201)
def create_supplier(
    data: SupplierCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_req_eng_plus(current_user)
    # Unique-name guard (DB also has UNIQUE on name; this just gives a clean 409).
    dup = db.query(Supplier.id).filter(Supplier.name == data.name).first()
    if dup is not None:
        raise HTTPException(409, f"Supplier with name '{data.name}' already exists")

    supplier = Supplier(
        created_by_id=current_user.id,
        **data.model_dump(exclude_unset=True),
    )
    db.add(supplier)
    db.commit()
    db.refresh(supplier)

    _audit(
        db, "supplier.created", "supplier", supplier.id, current_user.id,
        {"name": supplier.name, "cage_code": supplier.cage_code},
        request=request,
    )
    return _supplier_response(db, supplier)


@router.get("/suppliers/{supplier_id}", response_model=SupplierResponse)
def get_supplier(
    supplier_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    s = _get_supplier_or_404(db, supplier_id)
    return _supplier_response(db, s)


@router.patch("/suppliers/{supplier_id}", response_model=SupplierResponse)
def update_supplier(
    supplier_id: int,
    data: SupplierUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_req_eng_plus(current_user)
    s = _get_supplier_or_404(db, supplier_id)
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(s, field, value)
    db.commit()
    db.refresh(s)
    _audit(
        db, "supplier.updated", "supplier", s.id, current_user.id,
        {"fields": list(updates.keys())},
        request=request,
    )
    return _supplier_response(db, s)


@router.delete("/suppliers/{supplier_id}", status_code=200)
def delete_supplier(
    supplier_id: int,
    admin_force: bool = Query(False),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    s = _get_supplier_or_404(db, supplier_id)
    parts_count = (
        db.query(func.count(CatalogPart.id))
        .filter(CatalogPart.supplier_id == s.id)
        .scalar()
        or 0
    )
    if parts_count > 0 and not admin_force:
        raise HTTPException(
            409,
            f"Supplier has {parts_count} catalog part(s). Pass ?admin_force=true to delete anyway.",
        )

    # admin_force=true: explicitly cascade-delete the parts first so the FK
    # doesn't trip. (CatalogPart.supplier_id is NOT NULL with no ondelete=CASCADE
    # at the DB level — the relationship lets us cascade in Python explicitly.)
    if parts_count > 0 and admin_force:
        parts = db.query(CatalogPart).filter(CatalogPart.supplier_id == s.id).all()
        for p in parts:
            db.delete(p)
        db.flush()

    _audit(
        db, "supplier.deleted", "supplier", s.id, current_user.id,
        {"name": s.name, "parts_dropped": parts_count, "admin_force": admin_force},
        request=request,
    )
    db.delete(s)
    db.commit()
    return {"status": "deleted", "id": supplier_id, "parts_dropped": parts_count}


# ══════════════════════════════════════════════════════════════
#  §9.2 Supplier Documents
# ══════════════════════════════════════════════════════════════

@router.post(
    "/suppliers/{supplier_id}/documents/upload",
    response_model=SupplierDocumentResponse,
    status_code=201,
)
async def upload_supplier_document(
    supplier_id: int,
    file: UploadFile = File(...),
    title: str = Form(...),
    document_type: SupplierDocumentType = Form(...),
    revision: Optional[str] = Form(None),
    document_number: Optional[str] = Form(None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Multipart upload. SHA-256 hashed before save; same-supplier dup → 409.
    Different supplier may legitimately re-upload the same datasheet.

    No extraction is triggered — that's Phase 7. The row lands with
    ``extraction_status=UPLOADED``.
    """
    _require_req_eng_plus(current_user)
    supplier = _get_supplier_or_404(db, supplier_id)

    content = await file.read()
    sha256 = hashlib.sha256(content).hexdigest()

    # Per-supplier dedup: reject if the SAME hash already exists for this supplier.
    dup = (
        db.query(SupplierDocument.id)
        .filter(
            SupplierDocument.supplier_id == supplier_id,
            SupplierDocument.sha256 == sha256,
        )
        .first()
    )
    if dup is not None:
        raise HTTPException(
            409,
            f"Document with sha256={sha256[:12]}… already exists for supplier {supplier_id}",
        )

    # Resolve extension. Strip leading dot. Default to "bin" if absent.
    original_name = file.filename or "upload.bin"
    ext = (Path(original_name).suffix or ".bin").lstrip(".").lower()
    file_uuid = uuid.uuid4().hex
    SUPPLIER_DOC_DIR.mkdir(parents=True, exist_ok=True)
    file_path = SUPPLIER_DOC_DIR / f"{file_uuid}.{ext}"
    file_path.write_bytes(content)

    doc = SupplierDocument(
        supplier_id=supplier_id,
        title=title,
        # HAROLD-IN-WRENCH-001 Phase 6: persist the multipart filename
        # so HAROLD's filename-precheck can stem-match.
        original_filename=original_name,
        document_type=document_type,
        revision=revision,
        document_number=document_number,
        file_path=str(file_path),
        file_size_bytes=len(content),
        sha256=sha256,
        mime_type=file.content_type or "application/octet-stream",
        page_count=None,  # populated by Phase 7 extraction
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    _audit(
        db, "supplier.document.uploaded", "supplier_document", doc.id, current_user.id,
        {
            "supplier_id": supplier_id,
            "title": title,
            "type": document_type.value if hasattr(document_type, "value") else str(document_type),
            "size_bytes": len(content),
            "sha256": sha256,
        },
        request=request,
    )
    return SupplierDocumentResponse.model_validate(doc)


@router.get("/documents", response_model=CatalogDocumentsResponse)
def list_documents(
    supplier_id: Optional[int] = Query(None),
    document_type: Optional[SupplierDocumentType] = Query(None),
    filename_stem: Optional[str] = Query(
        None,
        description=(
            "Leading-anchored ILIKE match against original_filename "
            "(falls back to title for pre-Phase-6 rows where "
            "original_filename was not yet captured)."
        ),
    ),
    extraction_status: Optional[ExtractionStatus] = Query(None),
    since: Optional[datetime] = Query(
        None, description="Only documents with uploaded_at >= this timestamp.",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """HAROLD-IN-WRENCH-001 Phase 6 (AD-7). Peer-service-friendly list
    of supplier documents joined to their catalog_part metadata, used
    by HAROLD's filename precheck endpoint.

    Unauthenticated for LAN-only peer consumption — matches the
    convention established by ``/api/v1/catalog/designators`` (the
    earlier HAROLD-INTEGRATION-002 endpoint). A future TDD will add a
    shared-token header when HAROLD-in-WRENCH ships to non-LAN
    deployments.

    Pagination matches the rest of the catalog router (skip / limit
    default 50, cap 200).
    """
    q = db.query(SupplierDocument)
    if supplier_id is not None:
        q = q.filter(SupplierDocument.supplier_id == supplier_id)
    if document_type is not None:
        q = q.filter(SupplierDocument.document_type == document_type)
    if filename_stem:
        # ILIKE leading-anchored. Match against original_filename if
        # present, fall back to title for pre-Phase-6 rows.
        pat = f"{filename_stem}%"
        q = q.filter(
            or_(
                SupplierDocument.original_filename.ilike(pat),
                and_(
                    SupplierDocument.original_filename.is_(None),
                    SupplierDocument.title.ilike(pat),
                ),
            )
        )
    if extraction_status is not None:
        q = q.filter(SupplierDocument.extraction_status == extraction_status)
    if since is not None:
        q = q.filter(SupplierDocument.uploaded_at >= since)

    total = q.count()
    rows = (
        q.order_by(SupplierDocument.uploaded_at.desc())
        .offset(skip).limit(limit).all()
    )

    # Join each document to its (most recent) live catalog_part for
    # the WPN context HAROLD wants. Single batched lookup so we don't
    # N+1 the catalog_part query inside the loop.
    doc_ids = [d.id for d in rows]
    part_by_doc_id: Dict[int, CatalogPart] = {}
    if doc_ids:
        part_rows = (
            db.query(CatalogPart)
            .filter(
                CatalogPart.source_document_id.in_(doc_ids),
                CatalogPart.deleted_at.is_(None),
            )
            .all()
        )
        for p in part_rows:
            # If multiple live parts share a source_document_id, prefer
            # the lowest id (oldest) — matches the supplier_doc → part
            # association order the rest of the catalog uses.
            existing = part_by_doc_id.get(p.source_document_id)
            if existing is None or p.id < existing.id:
                part_by_doc_id[p.source_document_id] = p

    documents = [
        CatalogDocumentMetadata(
            id=d.id,
            title=d.title,
            original_filename=d.original_filename,
            document_type=d.document_type,
            file_path=d.file_path,
            mime_type=d.mime_type,
            sha256=d.sha256,
            supplier_id=d.supplier_id,
            supplier_document_id=d.id,
            catalog_part_id=(
                part_by_doc_id[d.id].id if d.id in part_by_doc_id else None
            ),
            internal_part_number=(
                part_by_doc_id[d.id].internal_part_number
                if d.id in part_by_doc_id else None
            ),
            extraction_status=d.extraction_status,
            uploaded_at=d.uploaded_at,
        )
        for d in rows
    ]
    return CatalogDocumentsResponse(documents=documents, total=total)


@router.get("/documents/{doc_id}", response_model=SupplierDocumentResponse)
def get_document(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(SupplierDocument).filter(SupplierDocument.id == doc_id).first()
    if doc is None:
        raise HTTPException(404, f"SupplierDocument {doc_id} not found")
    return SupplierDocumentResponse.model_validate(doc)


@router.get("/documents/{doc_id}/file")
def get_document_file(
    doc_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    doc = db.query(SupplierDocument).filter(SupplierDocument.id == doc_id).first()
    if doc is None:
        raise HTTPException(404, f"SupplierDocument {doc_id} not found")
    p = Path(doc.file_path)
    if not p.exists():
        raise HTTPException(
            500,
            f"Document {doc_id} metadata exists but file missing on disk ({doc.file_path})",
        )
    return FileResponse(
        path=str(p),
        media_type=doc.mime_type or "application/octet-stream",
        filename=f"{doc.title}",
    )


@router.delete("/documents/{doc_id}", status_code=200)
def delete_document(
    doc_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_admin(current_user)
    doc = db.query(SupplierDocument).filter(SupplierDocument.id == doc_id).first()
    if doc is None:
        raise HTTPException(404, f"SupplierDocument {doc_id} not found")
    file_path = Path(doc.file_path) if doc.file_path else None
    _audit(
        db, "supplier.document.deleted", "supplier_document", doc.id, current_user.id,
        {"supplier_id": doc.supplier_id, "title": doc.title},
        request=request,
    )
    db.delete(doc)
    db.commit()
    # Best-effort unlink AFTER the DB row is gone, so a failed unlink doesn't
    # corrupt the metadata invariant. A future cleanup job sweeps orphans.
    if file_path is not None and file_path.exists():
        try:
            file_path.unlink()
        except OSError as exc:
            logger.warning("Failed to unlink supplier document file %s: %s", file_path, exc)
    return {"status": "deleted", "id": doc_id}


# ══════════════════════════════════════════════════════════════
#  §9.3 Catalog Parts
# ══════════════════════════════════════════════════════════════

@router.get("/parts", response_model=List[CatalogPartSummary])
def list_catalog_parts(
    q: Optional[str] = Query(None),
    supplier_id: Optional[int] = Query(None),
    part_class: Optional[PartClass] = Query(None),
    lifecycle_status: Optional[LifecycleStatus] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(CatalogPart)
    if q:
        like = f"%{q}%"
        query = query.filter(
            or_(
                CatalogPart.part_number.ilike(like),
                CatalogPart.name.ilike(like),
                CatalogPart.designation.ilike(like),
            )
        )
    if supplier_id is not None:
        query = query.filter(CatalogPart.supplier_id == supplier_id)
    if part_class is not None:
        query = query.filter(CatalogPart.part_class == part_class)
    if lifecycle_status is not None:
        query = query.filter(CatalogPart.lifecycle_status == lifecycle_status)

    parts = query.order_by(CatalogPart.part_number).offset(skip).limit(limit).all()
    if not parts:
        return []

    # Batch caches to avoid per-row lookups.
    sids = list({p.supplier_id for p in parts})
    pids = [p.id for p in parts]
    supplier_names = dict(
        db.query(Supplier.id, Supplier.name).filter(Supplier.id.in_(sids)).all()
    )
    usage_rows = (
        db.query(Unit.catalog_part_id, func.count(Unit.id))
        .filter(Unit.catalog_part_id.in_(pids))
        .group_by(Unit.catalog_part_id)
        .all()
    )
    usage_counts = {pid: c for pid, c in usage_rows}

    return [
        _catalog_part_summary(
            db, p,
            supplier_name_cache=supplier_names,
            usage_cache=usage_counts,
        )
        for p in parts
    ]


class CatalogPartCreateRequest(CatalogPartCreate):
    """Same as CatalogPartCreate but exposed under a router-local name so the
    OpenAPI schema groups under ``Catalog`` and the docs make it obvious that
    nested ``connectors`` are accepted on the create call."""


@router.post("/parts", response_model=CatalogPartResponse, status_code=201)
def create_catalog_part(
    data: CatalogPartCreateRequest,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_req_eng_plus(current_user)
    _get_supplier_or_404(db, data.supplier_id)

    payload = data.model_dump(exclude_unset=True)
    nested_connectors = payload.pop("connectors", None) or []

    part = CatalogPart(created_by_id=current_user.id, **payload)
    db.add(part)
    db.flush()

    for c_data in nested_connectors:
        c_payload = dict(c_data)
        pins_payload = c_payload.pop("pins", None) or []
        connector = CatalogConnector(catalog_part_id=part.id, **c_payload)
        db.add(connector)
        db.flush()
        for p_data in pins_payload:
            pin = CatalogPin(catalog_connector_id=connector.id, **p_data)
            db.add(pin)
        if not connector.pin_count:
            connector.pin_count = len(pins_payload)

    db.commit()
    db.refresh(part)

    _audit(
        db, "catalog_part.created", "catalog_part", part.id, current_user.id,
        {
            "part_number": part.part_number,
            "supplier_id": part.supplier_id,
            "connector_count": len(nested_connectors),
        },
        request=request,
    )
    return _catalog_part_response(db, part)


@router.get("/parts/{part_id}", response_model=CatalogPartResponse)
def get_catalog_part(
    part_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_catalog_part_or_404(db, part_id)
    return _catalog_part_response(db, p)


@router.patch("/parts/{part_id}", response_model=CatalogPartResponse)
def update_catalog_part(
    part_id: int,
    data: CatalogPartUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_req_eng_plus(current_user)
    p = _get_catalog_part_or_404(db, part_id)
    if data.supplier_id is not None and data.supplier_id != p.supplier_id:
        _get_supplier_or_404(db, data.supplier_id)

    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(p, field, value)
    db.commit()
    db.refresh(p)

    _audit(
        db, "catalog_part.updated", "catalog_part", p.id, current_user.id,
        {"fields": list(updates.keys())},
        request=request,
    )
    return _catalog_part_response(db, p)


@router.delete("/parts/{part_id}", status_code=200)
def delete_catalog_part(
    part_id: int,
    admin_force: bool = Query(False),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """CLEANUP-002 Phase 4 (AD-7).

    Default path (no admin_force): soft-delete when no downstream
    refs; structured 409 with the full usage report when refs exist
    (UI renders a project list + the reason). Hard-block — the user
    removes the usage first, then retries.

    Legacy ``?admin_force=true`` path: unchanged from pre-cleanup
    behavior. Hard-deletes the row and lets the FK constraints
    cascade or null-out as configured. Kept because existing tests
    + admin tooling depend on it (rule #3 forbids adding a *new*
    cascade override; this one already exists).
    """
    _require_admin(current_user)
    p = _get_catalog_part_or_404(db, part_id)

    if admin_force:
        # Legacy hard-delete escape. Pre-CLEANUP-002 behaviour: rows
        # with units pointing here get unlinked via the FK's SET NULL;
        # rows with project_parts pointing here fail RESTRICT and
        # surface a 500 to the caller (the existing behaviour).
        usage_count = (
            db.query(func.count(Unit.id))
            .filter(Unit.catalog_part_id == p.id)
            .scalar()
            or 0
        )
        _audit(
            db, "catalog_part.deleted", "catalog_part", p.id, current_user.id,
            {
                "part_number": p.part_number,
                "supplier_id": p.supplier_id,
                "units_unlinked": usage_count,
                "admin_force": True,
            },
            request=request,
        )
        db.delete(p)
        db.commit()
        return {
            "status": "deleted", "id": part_id,
            "units_unlinked": usage_count, "admin_force": True,
        }

    # Already soft-deleted — surface a 404 so callers don't double-act.
    if p.deleted_at is not None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"CatalogPart {part_id} not found",
        )

    usage = _build_catalog_part_usage_report(db, p)
    if not usage.deletable:
        _audit(
            db, "catalog.part.deletion_blocked", "catalog_part", p.id,
            current_user.id,
            {
                "part_number": p.part_number,
                "total_references": usage.total_references,
                "project_count": len(usage.projects),
            },
            request=request,
        )
        db.commit()
        raise HTTPException(
            status_code=409,
            detail={
                "code": "part_in_use",
                "message": (
                    f"Cannot delete part {p.part_number}. It is "
                    f"referenced by {usage.total_references} "
                    f"{'entity' if usage.total_references == 1 else 'entities'} "
                    f"across {len(usage.projects)} project(s). Remove "
                    "those references first."
                ),
                "usage": usage.model_dump(),
            },
        )

    p.deleted_at = datetime.utcnow()
    _audit(
        db, "catalog.part.deleted", "catalog_part", p.id, current_user.id,
        {
            "part_number": p.part_number,
            "internal_part_number": p.internal_part_number,
            "supplier_id": p.supplier_id,
        },
        request=request,
    )
    db.commit()
    return {"status": "deleted", "id": part_id, "soft_delete": True}


@router.get("/parts/{part_id}/usage", response_model=List[CatalogPartUsageRow])
def list_catalog_part_usage(
    part_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    p = _get_catalog_part_or_404(db, part_id)

    rows = (
        db.query(Unit, Project.code)
        .outerjoin(Project, Project.id == Unit.project_id)
        .filter(Unit.catalog_part_id == p.id)
        .order_by(Unit.project_id, Unit.designation)
        .all()
    )
    out: List[CatalogPartUsageRow] = []
    for u, project_code in rows:
        out.append(
            CatalogPartUsageRow(
                unit_id=u.id,
                project_id=u.project_id,
                project_code=project_code,
                system_id=u.system_id,
                designation=u.designation,
                location_zone=u.location_zone,
                serial_number=u.serial_number,
            )
        )
    return out


@router.get(
    "/parts/{part_id}/usage-report", response_model=CatalogPartUsageReport,
)
def get_catalog_part_usage_report(
    part_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """CLEANUP-002 Phase 4 (AD-8). Returns the structured usage
    report the frontend renders as a "Used in N projects" badge and
    consults to decide whether the Delete button is live. Mirrors
    the report the DELETE handler computes internally before
    blocking with 409, so the UI never lies about deletability."""
    p = _get_catalog_part_or_404(db, part_id)
    return _build_catalog_part_usage_report(db, p)


@router.post("/parts/{part_id}/place", response_model=UnitResponse, status_code=201)
def place_catalog_part_endpoint(
    part_id: int,
    data: CatalogPartPlacementRequest,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    # Project-membership gate — applied for the project_id in the body.
    # We can't inject project_member_required directly because it reads
    # project_id from path/query, not body. Manual check below.
):
    """Place an existing CatalogPart into a project as a Unit (+ connectors + pins).

    RBAC: req_eng+ AND project_member.
    """
    _require_req_eng_plus(current_user)

    # Manual project-membership check (project_id is in body, not path).
    from app.dependencies.project_access import _check_membership
    _check_membership(db, data.project_id, current_user)

    unit = placement_svc.place_catalog_part(
        db,
        catalog_part_id=part_id,
        project_id=data.project_id,
        system_id=data.system_id,
        designation=data.unit_id_tag,
        designation_override=data.designation_override,
        location_zone=data.location_zone,
        serial_number=data.serial_number,
        asset_tag=data.asset_tag,
        admin_force=data.admin_force,
        user=current_user,
    )
    db.commit()
    db.refresh(unit)

    _audit(
        db, "catalog.part_placed", "catalog_part", part_id, current_user.id,
        {
            "project_id": data.project_id,
            "system_id": data.system_id,
            "unit_id": unit.id,
            "designation": unit.designation,
        },
        project_id=data.project_id,
        request=request,
    )

    resp = UnitResponse.model_validate(unit)
    resp.connector_count = (
        db.query(func.count())
        .select_from(unit.__class__)
        .filter(unit.__class__.id == unit.id)
        .scalar()
    ) or 0  # best-effort; the actual children count is computed below.
    # Replace the placeholder above with a real connector count.
    from app.models.interface import Connector as _Conn
    resp.connector_count = (
        db.query(func.count(_Conn.id))
        .filter(_Conn.unit_id == unit.id)
        .scalar()
        or 0
    )
    resp.bus_count = 0
    resp.message_count = 0
    return resp


class CatalogPartVariantRequest(BaseModel):
    """Body of POST /catalog/parts/{id}/variant."""
    variant_label: str = Field(..., max_length=100)
    revision: Optional[str] = Field(None, max_length=50)
    name: Optional[str] = Field(None, max_length=500)
    designation: Optional[str] = Field(None, max_length=200)
    notes: Optional[str] = None
    # If True, copy connectors+pins from the parent. Defaults to True so
    # variants normally inherit the connector tree.
    copy_connectors: bool = True


@router.post("/parts/{part_id}/variant", response_model=CatalogPartResponse, status_code=201)
def create_catalog_part_variant(
    part_id: int,
    data: CatalogPartVariantRequest,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_req_eng_plus(current_user)
    parent = _get_catalog_part_or_404(db, part_id)

    # Build a child CatalogPart copying parent metadata, with parent_part_id set.
    base_dict = {
        col.name: getattr(parent, col.name)
        for col in CatalogPart.__table__.columns
        if col.name not in {
            "id", "created_at", "updated_at",
            "parent_part_id", "variant_label",
        }
    }
    if data.name:
        base_dict["name"] = data.name
    if data.revision is not None:
        base_dict["revision"] = data.revision
    if data.designation is not None:
        base_dict["designation"] = data.designation
    if data.notes is not None:
        base_dict["notes"] = data.notes

    base_dict["parent_part_id"] = parent.id
    base_dict["variant_label"] = data.variant_label
    base_dict["created_by_id"] = current_user.id

    variant = CatalogPart(**base_dict)
    db.add(variant)
    db.flush()

    if data.copy_connectors:
        parent_connectors = (
            db.query(CatalogConnector)
            .filter(CatalogConnector.catalog_part_id == parent.id)
            .order_by(CatalogConnector.position)
            .all()
        )
        for pc in parent_connectors:
            child_conn = CatalogConnector(
                catalog_part_id=variant.id,
                reference=pc.reference,
                position=pc.position,
                description=pc.description,
                connector_type=pc.connector_type,
                shell_size=pc.shell_size,
                insert_arrangement=pc.insert_arrangement,
                gender=pc.gender,
                pin_count=pc.pin_count,
                keying=pc.keying,
                mating_part_number=pc.mating_part_number,
                notes=pc.notes,
            )
            db.add(child_conn)
            db.flush()
            parent_pins = (
                db.query(CatalogPin)
                .filter(CatalogPin.catalog_connector_id == pc.id)
                .order_by(CatalogPin.pin_position)
                .all()
            )
            for pp in parent_pins:
                db.add(CatalogPin(
                    catalog_connector_id=child_conn.id,
                    pin_position=pp.pin_position,
                    mfr_pin_name=pp.mfr_pin_name,
                    mfr_signal_function=pp.mfr_signal_function,
                    mfr_signal_type=pp.mfr_signal_type,
                    mfr_direction=pp.mfr_direction,
                    mfr_voltage_min_v=pp.mfr_voltage_min_v,
                    mfr_voltage_max_v=pp.mfr_voltage_max_v,
                    mfr_current_max_ma=pp.mfr_current_max_ma,
                    mfr_impedance_ohm=pp.mfr_impedance_ohm,
                    mfr_protocol_hint=pp.mfr_protocol_hint,
                    mfr_is_paired_with=pp.mfr_is_paired_with,
                    is_no_connect=pp.is_no_connect,
                    is_reserved=pp.is_reserved,
                    is_chassis_ground=pp.is_chassis_ground,
                    notes=pp.notes,
                ))

    db.commit()
    db.refresh(variant)

    _audit(
        db, "catalog_part.variant_created", "catalog_part", variant.id, current_user.id,
        {
            "parent_part_id": parent.id,
            "variant_label": data.variant_label,
            "copy_connectors": data.copy_connectors,
        },
        request=request,
    )
    return _catalog_part_response(db, variant)


# ══════════════════════════════════════════════════════════════
#  §9.4 Pending Imports (READ-ONLY in Phase 2; approve/reject in Phase 7)
# ══════════════════════════════════════════════════════════════

@router.get("/pending-imports", response_model=List[PendingCatalogImportResponse])
def list_pending_imports(
    status_filter: Optional[PendingImportStatus] = Query(None, alias="status"),
    supplier_id: Optional[int] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_req_eng_plus(current_user)
    query = db.query(PendingCatalogImport)
    if status_filter is not None:
        query = query.filter(PendingCatalogImport.status == status_filter)
    if supplier_id is not None:
        query = query.filter(PendingCatalogImport.supplier_id == supplier_id)
    rows = (
        query.order_by(PendingCatalogImport.created_at.desc())
        .offset(skip).limit(limit).all()
    )
    return [PendingCatalogImportResponse.model_validate(r) for r in rows]


@router.get("/pending-imports/{import_id}", response_model=PendingCatalogImportResponse)
def get_pending_import(
    import_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_req_eng_plus(current_user)
    row = (
        db.query(PendingCatalogImport)
        .filter(PendingCatalogImport.id == import_id)
        .first()
    )
    if row is None:
        raise HTTPException(404, f"PendingCatalogImport {import_id} not found")
    return PendingCatalogImportResponse.model_validate(row)


@router.patch("/pending-imports/{import_id}", response_model=PendingCatalogImportResponse)
def patch_pending_import(
    import_id: int,
    data: PendingCatalogImportUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_req_eng_plus(current_user)
    row = (
        db.query(PendingCatalogImport)
        .filter(PendingCatalogImport.id == import_id)
        .first()
    )
    if row is None:
        raise HTTPException(404, f"PendingCatalogImport {import_id} not found")
    updates = data.model_dump(exclude_unset=True)
    for field, value in updates.items():
        setattr(row, field, value)
    db.commit()
    db.refresh(row)
    _audit(
        db, "catalog.import.edited", "pending_catalog_import", row.id, current_user.id,
        {"fields": list(updates.keys())},
        request=request,
    )
    return PendingCatalogImportResponse.model_validate(row)


@router.delete("/pending-imports/{import_id}", status_code=200)
def delete_pending_import(
    import_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """CLEANUP-002 Phase 4 (AD-6). Hard-delete the row — pending
    imports are pre-catalog ephemeral state with no audit-retention
    requirement once rejected. Cascades to deleting the linked
    ``supplier_document`` *only if* no other live reference remains
    (no other pending imports against it; no non-soft-deleted
    catalog_part sourced from it). Otherwise the document is left in
    place so its other dependents keep working.

    ``deleted_at`` does not exist on pending_catalog_imports —
    ``status='rejected'`` is the soft equivalent today. This
    endpoint adds a true hard-delete option so the list page can
    be cleaned up directly.
    """
    _require_req_eng_plus(current_user)
    pi = (
        db.query(PendingCatalogImport)
        .filter(PendingCatalogImport.id == import_id)
        .first()
    )
    if pi is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PendingCatalogImport {import_id} not found",
        )
    supplier_doc_id = pi.source_document_id
    pi_status = pi.status

    db.delete(pi)
    db.flush()

    supplier_doc_deleted = False
    if supplier_doc_id is not None:
        other_pi = (
            db.query(func.count(PendingCatalogImport.id))
            .filter(PendingCatalogImport.source_document_id == supplier_doc_id)
            .scalar()
            or 0
        )
        live_parts = (
            db.query(func.count(CatalogPart.id))
            .filter(
                CatalogPart.source_document_id == supplier_doc_id,
                CatalogPart.deleted_at.is_(None),
            )
            .scalar()
            or 0
        )
        if other_pi == 0 and live_parts == 0:
            db.query(SupplierDocument).filter(
                SupplierDocument.id == supplier_doc_id
            ).delete()
            supplier_doc_deleted = True

    _audit(
        db, "pending_import.deleted", "pending_catalog_import", import_id,
        current_user.id,
        {
            "prior_status": pi_status.value if hasattr(pi_status, "value") else str(pi_status),
            "source_document_id": supplier_doc_id,
            "supplier_document_deleted": supplier_doc_deleted,
        },
        request=request,
    )
    db.commit()
    return {
        "deleted": True,
        "id": import_id,
        "supplier_document_deleted": supplier_doc_deleted,
    }


# ══════════════════════════════════════════════════════════════
#  Phase 7 — ICD Ingestion endpoints (extract / approve / reject)
# ══════════════════════════════════════════════════════════════


def _run_extraction_in_background(document_id: int) -> None:
    """Background-task entrypoint. Owns its OWN DB session — the request's
    session is closed by the time this fires."""
    # Late imports: don't pull pymupdf / camelot during module import.
    from app.database import SessionLocal
    from app.services.catalog import icd_extractor

    db = SessionLocal()
    try:
        icd_extractor.trigger_extraction(db, document_id)
    except Exception:    # noqa: BLE001 - background tasks must not crash the worker
        logger.exception("Background ICD extraction crashed for document %s", document_id)
        # Best-effort failure marker if the orchestrator's own try/except didn't catch it.
        try:
            doc = db.query(SupplierDocument).filter(SupplierDocument.id == document_id).first()
            if doc is not None and doc.extraction_status not in (
                ExtractionStatus.PENDING_REVIEW,
                ExtractionStatus.APPROVED,
                ExtractionStatus.FAILED,
            ):
                doc.extraction_status = ExtractionStatus.FAILED
                doc.extraction_log = {"code": "background_crash", "message": "see backend logs"}
                doc.extraction_at = datetime.utcnow()
                db.commit()
        except Exception:    # pragma: no cover
            db.rollback()
    finally:
        db.close()


@router.post(
    "/documents/{doc_id}/extract",
    response_model=IcdExtractionTriggerResponse,
    status_code=202,
)
def trigger_document_extraction(
    doc_id: int,
    background_tasks: BackgroundTasks,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Trigger ICD ingestion for an UPLOADED supplier document.

    Returns 202 + {job_id, status, started_at} immediately; the actual
    extraction runs in a BackgroundTask. Poll ``GET /catalog/documents/{id}``
    to watch the ``extraction_status`` move UPLOADED → EXTRACTING →
    PENDING_REVIEW (or FAILED).
    """
    _require_req_eng_plus(current_user)
    doc = db.query(SupplierDocument).filter(SupplierDocument.id == doc_id).first()
    if doc is None:
        raise HTTPException(404, f"SupplierDocument {doc_id} not found")

    # Only re-run from UPLOADED or FAILED. EXTRACTING means a background
    # task is already in flight; PENDING_REVIEW / APPROVED / REJECTED need
    # an explicit reset before re-extraction.
    if doc.extraction_status not in (ExtractionStatus.UPLOADED, ExtractionStatus.FAILED):
        raise HTTPException(
            409,
            f"Document {doc_id} cannot be re-extracted from status "
            f"'{doc.extraction_status.value if hasattr(doc.extraction_status, 'value') else doc.extraction_status}'. "
            "Allowed source statuses: uploaded, failed.",
        )

    # Flip status now so the caller's poll sees EXTRACTING immediately.
    doc.extraction_status = ExtractionStatus.EXTRACTING
    doc.extraction_log = {"queued_at": datetime.utcnow().isoformat()}
    doc.extraction_at = datetime.utcnow()
    db.commit()

    background_tasks.add_task(_run_extraction_in_background, doc_id)

    _audit(
        db, "catalog.extraction_started", "supplier_document", doc.id, current_user.id,
        {"supplier_id": doc.supplier_id, "title": doc.title, "mime_type": doc.mime_type},
        request=request,
    )

    return IcdExtractionTriggerResponse(
        job_id=doc.id,
        status=ExtractionStatus.EXTRACTING.value,
        started_at=doc.extraction_at or datetime.utcnow(),
    )


def _approve_pending_import(
    db: Session,
    pending_id: int,
    current_user: User,
) -> CatalogPart:
    """Atomic approval: re-validate extracted_data, build Supplier (if new) +
    CatalogPart + CatalogConnectors + CatalogPins, and link pending row.

    Raises HTTPException for caller-friendly 4xx; lets unexpected errors
    bubble (caller wraps with rollback).
    """
    pending = (
        db.query(PendingCatalogImport)
        .filter(PendingCatalogImport.id == pending_id)
        .first()
    )
    if pending is None:
        raise HTTPException(404, f"PendingCatalogImport {pending_id} not found")
    if pending.status != PendingImportStatus.PENDING:
        current = pending.status.value if hasattr(pending.status, "value") else str(pending.status)
        raise HTTPException(409, f"Cannot approve PendingCatalogImport {pending_id} in status '{current}'")

    # Re-validate the extracted blob — reviewers may have edited it via PATCH.
    try:
        extracted = IcdExtractionResultSchema.model_validate(pending.extracted_data or {})
    except Exception as exc:    # noqa: BLE001
        raise HTTPException(
            422,
            f"PendingCatalogImport {pending_id} has invalid extracted_data: {exc}",
        )

    # Resolve / create supplier. Match by name (case-insensitive) + cage_code
    # if both are present, otherwise just by name.
    supplier_q = db.query(Supplier).filter(Supplier.name == extracted.supplier.name)
    supplier = supplier_q.first()
    if supplier is None:
        supplier = Supplier(
            name=extracted.supplier.name,
            cage_code=extracted.supplier.cage_code,
            country=extracted.supplier.country,
            is_active=True,
            created_by_id=current_user.id,
        )
        db.add(supplier)
        db.flush()

    # Refuse to silently re-create an existing (supplier, part_number, revision)
    # tuple — the unique constraint would explode anyway.
    pn_dup = (
        db.query(CatalogPart.id)
        .filter(
            CatalogPart.supplier_id == supplier.id,
            CatalogPart.part_number == extracted.part_number,
            CatalogPart.revision == extracted.revision,
        )
        .first()
    )
    if pn_dup is not None:
        raise HTTPException(
            409,
            f"CatalogPart with supplier '{supplier.name}', part_number "
            f"'{extracted.part_number}', revision '{extracted.revision}' "
            f"already exists (id={pn_dup[0]}). Reject this import or update "
            "the extracted data to a different revision before approving.",
        )

    # Create the catalog part using the extracted scalar fields. Skip the
    # nested supplier/connectors/extraction_warnings fields — they're handled
    # separately or stored elsewhere.
    scalar = extracted.model_dump(exclude={
        "supplier",
        "connectors",
        "extraction_warnings",
        "extraction_confidence",
        "source_page_refs",
    })

    part = CatalogPart(
        supplier_id=supplier.id,
        source_document_id=pending.source_document_id,
        source_page_refs=extracted.source_page_refs,
        created_by_id=current_user.id,
        **scalar,
    )
    db.add(part)
    db.flush()

    # Connectors + pins
    for idx, ext_conn in enumerate(extracted.connectors):
        conn_dump = ext_conn.model_dump(exclude={"pins", "source_page"})
        conn = CatalogConnector(
            catalog_part_id=part.id,
            position=idx,
            **conn_dump,
        )
        db.add(conn)
        db.flush()
        for ext_pin in ext_conn.pins:
            pin_dump = ext_pin.model_dump(exclude={"source_page"})
            db.add(CatalogPin(catalog_connector_id=conn.id, **pin_dump))
        # Backfill pin_count if extractor didn't capture it.
        if not conn.pin_count:
            conn.pin_count = len(ext_conn.pins)
        db.flush()

    # Wire up pending → committed link, mark APPROVED, and stamp the document.
    pending.status = PendingImportStatus.APPROVED
    pending.committed_catalog_part_id = part.id
    pending.reviewed_at = datetime.utcnow()
    pending.reviewed_by_id = current_user.id
    if pending.source_document is not None:
        pending.source_document.extraction_status = ExtractionStatus.APPROVED

    db.flush()
    return part


@router.post(
    "/pending-imports/{import_id}/approve",
    response_model=CatalogPartResponse,
    status_code=201,
)
async def approve_pending_import(
    import_id: int,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Commit a PendingCatalogImport into the live catalog.

    Atomic: any failure rolls every newly-created Supplier / CatalogPart /
    CatalogConnector / CatalogPin row back. Marks the source document
    APPROVED on success.

    Phase 3 of HAROLD-INT-002: when the integration is enabled, also
    assigns ``internal_part_number`` via HAROLD. Three branches per
    AD-11:
      1. ``user_supplied_wpn`` set in pending.extracted_data → call
         issue_specific. 409 from HAROLD → reject the approval.
      2. user didn't override + HAROLD up → issue (auto-allocate).
      3. user didn't override + HAROLD down → fallback allocator,
         set ``wpn_pending_sync=True``.

    Flag-off: the new code path is skipped entirely; behaviour
    identical to today.
    """
    _require_req_eng_plus(current_user)

    # Pull the WPN metadata from extracted_data BEFORE `_approve_pending_import`
    # runs — the IcdExtractionResultSchema inside that helper drops
    # unknown keys, so reading these after would return nothing.
    harold_meta: dict[str, object] = {}
    if _HAROLD_AVAILABLE and settings.HAROLD_INTEGRATION_ENABLED:
        peek = (
            db.query(PendingCatalogImport)
            .filter(PendingCatalogImport.id == import_id)
            .first()
        )
        if peek is not None and isinstance(peek.extracted_data, dict):
            ext = peek.extracted_data
            # AD-11: only an explicit user_supplied_wpn drives
            # issue-specific. proposed_wpn in extracted_data is just
            # the UI hint and never implicitly becomes a commitment —
            # auto-allocate happens when the user didn't override.
            user_supplied = (ext.get("user_supplied_wpn") or "").strip() or None
            harold_meta["final_wpn"] = user_supplied
            harold_meta["had_user_override"] = bool(user_supplied)

    try:
        part = _approve_pending_import(db, import_id, current_user)

        # HAROLD WPN assignment — feature-flagged. Must happen BEFORE
        # the commit so a hard failure (e.g. caller-supplied duplicate)
        # rolls back the whole approval.
        wpn_audit_payload: dict[str, object] | None = None
        if _HAROLD_AVAILABLE and settings.HAROLD_INTEGRATION_ENABLED:
            try:
                wpn, source, pending_sync = await _harold_issue(
                    db, part,
                    supplied_wpn=harold_meta.get("final_wpn"),  # type: ignore[arg-type]
                )
                part.internal_part_number = wpn
                part.wpn_pending_sync = bool(pending_sync)
                wpn_audit_payload = {
                    "wpn":              wpn,
                    "source":           source,
                    "wpn_pending_sync": bool(pending_sync),
                    "had_user_override": bool(harold_meta.get("had_user_override")),
                }
            except HaroldDuplicateError as exc:
                db.rollback()
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"WPN {harold_meta.get('final_wpn')!r} is already "
                        f"issued in HAROLD's ledger. Pick a different WPN "
                        f"or clear the override to auto-allocate. "
                        f"({exc!s})"
                    ),
                ) from exc

        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception:    # noqa: BLE001 - rollback then re-raise as 500
        db.rollback()
        logger.exception("approve_pending_import crashed for import_id=%s", import_id)
        raise HTTPException(500, "Failed to approve pending import — see backend logs")

    _audit(
        db, "catalog.import_approved", "pending_catalog_import", import_id, current_user.id,
        {
            "catalog_part_id": part.id,
            "supplier_id": part.supplier_id,
            "part_number": part.part_number,
            "connector_count": len(part.connectors or []),
        },
        request=request,
    )
    if wpn_audit_payload is not None:
        _audit(
            db, "catalog.part.wpn_assigned", "catalog_part", part.id, current_user.id,
            wpn_audit_payload,
            request=request,
        )

    return _catalog_part_response(db, part)


@router.post(
    "/pending-imports/{import_id}/reject",
    response_model=PendingCatalogImportResponse,
)
def reject_pending_import(
    import_id: int,
    data: PendingImportRejectRequest = None,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Reject a PendingCatalogImport. No catalog data is created.

    The source SupplierDocument moves to REJECTED so it stops appearing in
    the review queue UI; the document file stays on disk for the audit.
    """
    _require_req_eng_plus(current_user)
    pending = (
        db.query(PendingCatalogImport)
        .filter(PendingCatalogImport.id == import_id)
        .first()
    )
    if pending is None:
        raise HTTPException(404, f"PendingCatalogImport {import_id} not found")
    if pending.status != PendingImportStatus.PENDING:
        current_status = pending.status.value if hasattr(pending.status, "value") else str(pending.status)
        raise HTTPException(409, f"Cannot reject PendingCatalogImport {import_id} in status '{current_status}'")

    pending.status = PendingImportStatus.REJECTED
    pending.reviewed_at = datetime.utcnow()
    pending.reviewed_by_id = current_user.id
    if data and data.reason:
        pending.rejection_reason = data.reason
    if pending.source_document is not None:
        pending.source_document.extraction_status = ExtractionStatus.REJECTED
    db.commit()
    db.refresh(pending)

    _audit(
        db, "catalog.import_rejected", "pending_catalog_import", pending.id, current_user.id,
        {"reason": pending.rejection_reason or None, "supplier_id": pending.supplier_id},
        request=request,
    )
    return PendingCatalogImportResponse.model_validate(pending)


# ══════════════════════════════════════════════════════════════
#  TDD-CAT-002 — STEP file upload (additive endpoint)
# ══════════════════════════════════════════════════════════════
#
# The PDF / datasheet flow uploads a document FIRST (with the supplier
# known up-front) then runs an LLM-driven ICD extractor in the
# background. STEP files invert that: the supplier is auto-detected
# from the filename, the parser runs INLINE (CPU only), and the row
# lands in the existing pending_catalog_imports queue ready for review
# via the existing /pending-imports/{id}/approve endpoint.
#
# The two flows share the underlying tables (suppliers,
# supplier_documents, pending_catalog_imports) but use distinct upload
# routes — keeps each handler small and avoids overloading the PDF
# upload semantics. AD-3 in CAT-002.
# ══════════════════════════════════════════════════════════════

from app.services.cad.step_parser import (   # noqa: E402  (after main imports)
    PARSER_VERSION as _STEP_PARSER_VERSION,
    average_confidence as _step_avg_confidence,
    parse_step_file as _parse_step_file,
)


def _resolve_supplier_for_step(
    db: Session,
    canonical: Optional[str],
    aliases: List[str],
    current_user: User,
) -> tuple[Supplier, bool]:
    """Look up the canonical-named supplier (alias → name match), creating
    a new row + alias entries when nothing matches.

    Returns ``(supplier, was_created)``. When ``canonical`` is None the
    caller resolves to Wardstone separately; this helper assumes a vendor
    name is in hand.
    """
    if not canonical:
        raise ValueError("_resolve_supplier_for_step requires a canonical name")

    # 1. Alias hit (case-insensitive across the canonical + detected aliases)
    candidates = list(dict.fromkeys([canonical, *aliases]))
    lower_candidates = [c.lower() for c in candidates if c]
    alias_hit = (
        db.query(SupplierAlias)
        .filter(func.lower(SupplierAlias.alias).in_(lower_candidates))
        .first()
    )
    if alias_hit is not None:
        sup = db.query(Supplier).filter(Supplier.id == alias_hit.supplier_id).first()
        if sup is not None:
            return sup, False

    # 2. Direct supplier-name match (case-insensitive against canonical)
    name_hit = (
        db.query(Supplier)
        .filter(func.lower(Supplier.name) == canonical.lower())
        .first()
    )
    if name_hit is not None:
        return name_hit, False

    # 3. Auto-create
    sup = Supplier(
        name=canonical,
        is_active=True,
        is_in_house=False,
        notes=f"Auto-created from STEP upload at {datetime.utcnow().isoformat()}.",
        created_by_id=current_user.id,
    )
    db.add(sup)
    db.flush()  # need sup.id for alias inserts

    # Insert each detected alias. UNIQUE collisions are silently skipped
    # — another supplier may already own the alias text. (Common gotcha
    # §13.) Use a SAVEPOINT around each insert so a failure on one alias
    # doesn't abort the whole transaction.
    for raw_alias in candidates:
        if not raw_alias:
            continue
        try:
            with db.begin_nested():
                db.add(SupplierAlias(supplier_id=sup.id, alias=raw_alias))
                # Force the INSERT now so a UNIQUE collision raises
                # inside this with-block (savepoint can roll back),
                # not at outer commit (where the whole tx blows up).
                db.flush()
        except Exception as exc:  # noqa: BLE001 - integrity errors stay narrow
            logger.info(
                "Skipping alias %r for new supplier %r (collision): %s",
                raw_alias, canonical, exc,
            )
    db.flush()
    return sup, True


def _wardstone_or_500(db: Session) -> Supplier:
    sup = (
        db.query(Supplier)
        .filter(func.lower(Supplier.name) == "wardstone")
        .first()
    )
    if sup is None:
        raise HTTPException(
            500,
            "Wardstone supplier missing — apply migration 0029 (`alembic upgrade head`).",
        )
    return sup


@router.post(
    "/upload-step",
    response_model=StepUploadResponse,
    status_code=201,
)
async def upload_step_file(
    file: UploadFile = File(...),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """TDD-CAT-002 — STEP file ingest.

    Pipeline (synchronous):
      1. SHA-256 dedup across ALL suppliers (STEP files are globally
         identifiable by content — same hash = same geometry).
      2. Run the pure-Python STEP parser (`backend/app/services/cad`).
         pythonOCC enrichment is opportunistic.
      3. Resolve the detected supplier — alias map → name match →
         auto-create new Supplier row + alias entries. No vendor
         detected → link to Wardstone (the in-house default seeded in
         migration 0029).
      4. Save the file under SUPPLIER_DOC_DIR/{uuid}.step.
      5. Create a SupplierDocument (extraction_status=PENDING_REVIEW —
         the parser already ran).
      6. Create a PendingCatalogImport with the parser's extracted_data
         JSONB. Reviewer approves via the existing
         /pending-imports/{id}/approve endpoint.
      7. Return IDs + detection result.

    RBAC: req_eng+ (mirrors document upload).
    """
    _require_req_eng_plus(current_user)

    # ── 1. read + dedup ──
    content = await file.read()
    if not content:
        raise HTTPException(422, "uploaded file is empty")
    sha256 = hashlib.sha256(content).hexdigest()

    # CLEANUP-002 Phase 2 (AD-2 revised per Phase 0): soft-delete-aware
    # dedup. A supplier_document with this hash blocks re-upload only
    # if it still has live downstream state — either a non-soft-deleted
    # catalog_part, or a still-pending pending_import. Once both are
    # gone (catalog_part soft-deleted; pending_import terminal or
    # hard-deleted by Phase 4's cleanup flow), the supplier_document is
    # effectively orphaned and re-uploading the same STEP succeeds.
    # supplier_documents itself has no deleted_at column, so the
    # liveness check joins through the dependent tables.
    dup_row = (
        db.query(SupplierDocument.id, SupplierDocument.supplier_id)
        .outerjoin(
            CatalogPart, CatalogPart.source_document_id == SupplierDocument.id,
        )
        .outerjoin(
            PendingCatalogImport,
            PendingCatalogImport.source_document_id == SupplierDocument.id,
        )
        .filter(SupplierDocument.sha256 == sha256)
        .filter(
            or_(
                and_(
                    CatalogPart.id.isnot(None),
                    CatalogPart.deleted_at.is_(None),
                ),
                and_(
                    PendingCatalogImport.id.isnot(None),
                    PendingCatalogImport.status == PendingImportStatus.PENDING,
                ),
            )
        )
        .first()
    )
    if dup_row is not None:
        existing_doc_id, _existing_supplier_id = dup_row
        # AD-3: enrich the 409 body with actionable IDs + URL so the
        # frontend can route the user to the existing pending import
        # rather than show the opaque ID dump that prompted this TDD.
        active_pi = (
            db.query(PendingCatalogImport.id)
            .filter(
                PendingCatalogImport.source_document_id == existing_doc_id,
                PendingCatalogImport.status == PendingImportStatus.PENDING,
            )
            .first()
        )
        active_pi_id = active_pi[0] if active_pi else None
        raise HTTPException(
            status_code=409,
            detail={
                "code": "step_already_uploaded",
                "message": (
                    f"This STEP file (sha256={sha256[:8]}…) is already "
                    "uploaded and has live downstream state. Open the "
                    "existing pending import instead."
                ),
                "existing_supplier_document_id": existing_doc_id,
                "existing_pending_import_id": active_pi_id,
                "existing_pending_import_url": (
                    f"/catalog/pending-imports/{active_pi_id}"
                    if active_pi_id else None
                ),
            },
        )

    # ── 2. save to disk + parse ──
    SUPPLIER_DOC_DIR.mkdir(parents=True, exist_ok=True)
    file_uuid = uuid.uuid4().hex
    stored_path = SUPPLIER_DOC_DIR / f"{file_uuid}.step"
    stored_path.write_bytes(content)

    original_filename = file.filename or "upload.step"
    try:
        # Pass the user-supplied filename so vendor regex / lexicon
        # match against the real name, not the UUID storage path.
        parsed = _parse_step_file(
            stored_path,
            run_pythonocc=True,
            original_filename=original_filename,
        )
    except ValueError as exc:
        # Clean up the partial save before bubbling.
        try:
            stored_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(422, f"STEP parse failed: {exc}") from exc

    # ── 3. resolve / auto-create supplier ──
    supplier_was_created = False
    if parsed.detected_supplier_canonical:
        supplier, supplier_was_created = _resolve_supplier_for_step(
            db,
            canonical=parsed.detected_supplier_canonical,
            aliases=parsed.detected_supplier_aliases,
            current_user=current_user,
        )
    else:
        # In-house default
        supplier = _wardstone_or_500(db)
        # Surface the in-house decision in the parsed result so the
        # review UI can show the right banner.
        parsed.extracted.setdefault("manufacturer", supplier.name)
        parsed.confidence.setdefault("manufacturer", "low")

    # IcdExtractionResultSchema requires a nested supplier.name on
    # approve — synthesize it here so /pending-imports/{id}/approve
    # validates without per-handler special-casing.
    parsed.extracted["supplier"] = {
        "name": supplier.name,
        "cage_code": supplier.cage_code,
        "country": supplier.country,
    }

    # ── 4b. HAROLD integration: WPN suggestion + filename WPN check ──
    # Flag-gated per AD-1; when off, the parsed.extracted dict stays
    # exactly as today. The suggestion fields land in extracted_data
    # so the pending-imports review page can render the proposed WPN
    # without re-calling HAROLD on every page load.
    if _HAROLD_AVAILABLE and settings.HAROLD_INTEGRATION_ENABLED:
        part_class_value = parsed.extracted.get("part_class") or ""
        try:
            suggestion = await _harold_suggest(
                db, part_class_value, hint=original_filename,
            )
            parsed.extracted["proposed_wpn"]          = suggestion.get("suggested_wpn")
            parsed.extracted["wpn_source"]            = suggestion.get("source")
            parsed.extracted["wpn_system_code"]       = suggestion.get("system_code")
            if suggestion.get("reason"):
                parsed.extracted["wpn_suggestion_reason"] = suggestion.get("reason")
        except Exception as exc:  # noqa: BLE001 — best-effort during upload
            logger.warning("HAROLD suggest failed during upload: %s", exc)
            parsed.extracted["wpn_source"] = "unavailable"
            parsed.extracted["wpn_suggestion_reason"] = str(exc)

        # If the filename itself looks like a Wardstone WPN, validate
        # it and surface a duplicate warning so the reviewer knows.
        try:
            fcheck = await _harold_validate_filename(original_filename)
            if fcheck.get("is_wardstone_format"):
                parsed.extracted["filename_wpn"] = fcheck.get("extracted_wpn")
                wv = fcheck.get("wpn_validation") or {}
                if wv.get("is_issued"):
                    parsed.warnings.append(
                        f"Filename WPN {fcheck['extracted_wpn']!r} is already "
                        "issued in HAROLD's ledger. Use the suggested WPN or pick "
                        "a different filename."
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("HAROLD validate-filename failed during upload: %s", exc)

    # ── 5. SupplierDocument ──
    extraction_log = {
        "warnings": parsed.warnings,
        "parser_version": parsed.parser_version,
        "confidence_per_field": parsed.confidence,
        "supplier_was_auto_created": supplier_was_created,
    }

    doc = SupplierDocument(
        supplier_id=supplier.id,
        title=original_filename,
        # HAROLD-IN-WRENCH-001 Phase 6: distinct column so HAROLD's
        # filename precheck can stem-match. STEP path always has a
        # real filename in hand.
        original_filename=original_filename,
        document_type=SupplierDocumentType.OTHER,
        file_path=str(stored_path),
        file_size_bytes=len(content),
        sha256=sha256,
        mime_type="model/step",
        extraction_status=ExtractionStatus.PENDING_REVIEW,
        extraction_log=extraction_log,
        extraction_at=datetime.utcnow(),
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    db.flush()

    # ── 6. PendingCatalogImport ──
    extraction_confidence = _step_avg_confidence(parsed.confidence)
    pending = PendingCatalogImport(
        source_document_id=doc.id,
        supplier_id=supplier.id,
        extracted_data=parsed.extracted,
        extraction_warnings={
            "warnings": parsed.warnings,
            "supplier_was_auto_created": supplier_was_created,
            "parser_version": parsed.parser_version,
        },
        extraction_confidence=extraction_confidence,
        status=PendingImportStatus.PENDING,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)
    db.refresh(doc)
    db.refresh(supplier)

    # ── 7. audit trail ──
    if supplier_was_created:
        _audit(
            db, "catalog.supplier.auto_created", "supplier", supplier.id, current_user.id,
            {
                "detected_name": parsed.detected_supplier_canonical,
                "alias_count": len(parsed.detected_supplier_aliases),
                "supplier_document_id": doc.id,
            },
            request=request,
        )

    _audit(
        db, "catalog.step_uploaded", "supplier_document", doc.id, current_user.id,
        {
            "supplier_id": supplier.id,
            "supplier_was_created": supplier_was_created,
            "pending_import_id": pending.id,
            "mpn": parsed.extracted.get("part_number"),
            "sha256_short": sha256[:12],
            "size_bytes": len(content),
            "extraction_confidence": float(extraction_confidence),
        },
        request=request,
    )

    return StepUploadResponse(
        pending_import_id=pending.id,
        supplier_document_id=doc.id,
        detected_supplier_id=supplier.id,
        detected_supplier_name=supplier.name,
        supplier_was_created=supplier_was_created,
        extraction_confidence=float(extraction_confidence),
        warnings=parsed.warnings,
    )



# ═════════════════════════════════════════════════════════════════
#  TDD-HAROLD-001: outbound designator feed (HAROLD ← ASTRA)
# ═════════════════════════════════════════════════════════════════

@router.get("/designators", response_model=CatalogDesignatorsResponseV2)
def list_catalog_designators(
    system: Optional[str] = Query(
        None,
        description="2-letter HAROLD system code, e.g. FH. Case-insensitive.",
    ),
    skip: int = Query(0, ge=0),
    limit: int = Query(200, ge=1, le=200),
    db: Session = Depends(get_db),
    # AD-10: unauthenticated in v1 — peer-service consumption on a
    # trusted LAN. Future TDD adds a shared-token header.
):
    """List Wardstone Part Numbers (WPNs) ASTRA has issued.

    Phase 3 of HAROLD-INT-002 pivots the source column from the
    manufacturer ``part_number`` (MPN) to the assigned
    ``internal_part_number`` (WPN) per AD-9. Only rows with a
    non-NULL WPN are returned — pre-integration parts (e.g. the
    McMaster row, ``internal_part_number IS NULL``) are excluded.

    When ``system`` is supplied, filters to WPNs matching
    ``WS-<SYSTEM>-P%``. Returns structured rows so HAROLD's browse
    surface can show part_class + part_id linkbacks without a second
    query.

    The response shape is the V2 form ``CatalogDesignatorsResponseV2``;
    confirmed in Phase 0 that no caller was on the legacy flat-list
    shape (the endpoint was added speculatively in the prior
    HAROLD-001 phase-3 commit and never exercised).
    """
    query = (
        db.query(CatalogPart)
        .filter(
            CatalogPart.internal_part_number.isnot(None),
            CatalogPart.deleted_at.is_(None),
        )
    )
    sys_upper: Optional[str] = None
    if system:
        sys_upper = system.upper()
        query = query.filter(
            CatalogPart.internal_part_number.like(f"WS-{sys_upper}-P%")
        )

    total = query.count()
    rows = (
        query.order_by(CatalogPart.internal_part_number)
        .offset(skip)
        .limit(limit)
        .all()
    )

    designators = []
    for p in rows:
        wpn = p.internal_part_number or ""
        sys_code = None
        if wpn.count("-") >= 3:
            sys_code = wpn.split("-")[1]
        designators.append(CatalogDesignatorEntry(
            wpn=wpn,
            part_id=p.id,
            part_class=p.part_class.value if p.part_class else None,
            system_code=sys_code,
            created_at=p.created_at,
        ))

    return CatalogDesignatorsResponseV2(
        designators=designators,
        total=int(total or 0),
        system_filter=sys_upper,
    )
