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
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies.project_access import project_member_required
from app.models import Project, User, UserRole
from app.models.catalog import (
    CatalogConnector,
    CatalogPart,
    CatalogPin,
    LifecycleStatus,
    PartClass,
    PendingCatalogImport,
    PendingImportStatus,
    Supplier,
    SupplierDocument,
    SupplierDocumentType,
)
from app.models.interface import Unit
from app.schemas.catalog import (
    CatalogConnectorResponse,
    CatalogPartCreate,
    CatalogPartPlacementRequest,
    CatalogPartResponse,
    CatalogPartSummary,
    CatalogPartUpdate,
    CatalogPartUsageRow,
    CatalogPinResponse,
    PendingCatalogImportResponse,
    PendingCatalogImportUpdate,
    SupplierCreate,
    SupplierDocumentResponse,
    SupplierResponse,
    SupplierUpdate,
)
from app.schemas.interface import UnitResponse
from app.services.auth import get_current_user
from app.services.catalog import placement as placement_svc

# Optional audit
try:
    from app.services.audit_service import record_event as _audit
except ImportError:  # pragma: no cover - dev test fallback
    def _audit(*a, **kw):
        pass

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
    _require_admin(current_user)
    p = _get_catalog_part_or_404(db, part_id)
    in_use = placement_svc.is_part_in_use(db, part_id)
    usage_count = (
        db.query(func.count(Unit.id))
        .filter(Unit.catalog_part_id == p.id)
        .scalar()
        or 0
    )
    if in_use and not admin_force:
        raise HTTPException(
            409,
            f"CatalogPart is placed in {usage_count} project unit(s). "
            "Pass ?admin_force=true to delete anyway (project units will have catalog_part_id set to NULL).",
        )

    _audit(
        db, "catalog_part.deleted", "catalog_part", p.id, current_user.id,
        {
            "part_number": p.part_number,
            "supplier_id": p.supplier_id,
            "units_unlinked": usage_count,
            "admin_force": admin_force,
        },
        request=request,
    )
    db.delete(p)
    db.commit()
    return {"status": "deleted", "id": part_id, "units_unlinked": usage_count}


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
