"""
ASTRA — CADPORT integration router (CADPORT-REBUILD-002)
========================================================
File: backend/app/routers/cadport.py   ← NEW (TDD-2)

Mounts at ``/api/v1``. The endpoints CADPORT's astra_bridge calls
when a user chooses "Import to ASTRA" after a SolidWorks extraction.

All endpoints are ADDITIVE — no existing route is modified
(standing rule 3/4). Auth is the standard ASTRA Bearer pattern;
CADPORT authenticates as the ``mason`` admin user (gotcha #2).

Endpoints
---------
POST /api/v1/catalog/parts/check-duplicate
    content_hash → existing catalog_part (L4 link payload) or null.
    The AD-2 dedup gate. Handles the "Bottom Case extracted 3×"
    case — same content_hash, only one catalog_part.

POST /api/v1/catalog/parts/from-cadport
    Creates a catalog_part with §6 mass props parsed into columns
    (AD-6), the §6 YAML stored as a supplier_documents row with
    document_type='yaml' (AD-5), attached to the in-house Wardstone
    supplier (AD-1, looked up by name — already seeded). Sets the
    L4 spine (cadport_part_id), L5 (supplier_id), L6
    (internal_part_number = WPN). Idempotent on content_hash:
    a second call with the same hash returns the existing row +
    deduped=true rather than creating a duplicate.

POST /api/v1/cadport-assemblies
    Creates cadport_assemblies + cadport_assembly_components, stores
    the assembly §6 YAML as a supplier_documents row, links to the
    chosen project (L7).

GET  /api/v1/cadport-assemblies?project_id=X
GET  /api/v1/cadport-assemblies/{id}
"""

from __future__ import annotations

import hashlib
import os
import uuid as _uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, User
from app.models.catalog import (
    CadportAssembly,
    CadportAssemblyComponent,
    CatalogPart,
    LRUClass,
    PartClass,
    Supplier,
    SupplierDocument,
    SupplierDocumentType,
)
from app.services.auth import get_current_user

try:
    from app.services.audit_service import record_event as _audit
except Exception:  # pragma: no cover — audit is best-effort
    def _audit(*a, **kw):  # type: ignore
        return None

router = APIRouter(tags=["CADPORT"])

# Reuse the catalog router's file-storage convention so blobs all
# live in one place regardless of which router created them.
SUPPLIER_DOC_DIR = Path(os.environ.get("SUPPLIER_DOC_DIR", "/data/supplier_docs"))

WARDSTONE_NAME = "Wardstone"


# ── Request / response models ───────────────────────────────────────


class CadportInertia(BaseModel):
    ixx: float = 0.0
    iyy: float = 0.0
    izz: float = 0.0
    ixy: float = 0.0
    ixz: float = 0.0
    iyz: float = 0.0


class CadportPartImport(BaseModel):
    cadport_part_id: str = Field(..., description="§5 spine UUID from TDD-1")
    content_hash: str = Field(..., description="sha256:... from the §6 YAML")
    source_filename: str
    display_name: str
    internal_part_number: Optional[str] = Field(
        None, description="HAROLD WPN (L6); becomes catalog_part.internal_part_number"
    )
    material: Optional[str] = None
    configuration: str = "Default"
    solidworks_version: Optional[str] = None
    mass_kg: float = 0.0
    volume_m3: float = 0.0
    surface_area_m2: float = 0.0
    density_kg_m3: float = 0.0
    center_of_mass_m: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    inertia: CadportInertia = Field(default_factory=CadportInertia)
    yaml_filename: str = Field(..., description="WPN-based YAML filename (AD-8)")
    yaml_content: str = Field(..., description="The full §6 part YAML text")


class CheckDuplicateRequest(BaseModel):
    content_hash: str


class DuplicateMatch(BaseModel):
    found: bool
    catalog_part_id: Optional[int] = None
    cadport_part_id: Optional[str] = None
    part_number: Optional[str] = None
    name: Optional[str] = None
    internal_part_number: Optional[str] = None


class CatalogPartImportResult(BaseModel):
    catalog_part_id: int
    cadport_part_id: str
    part_number: str
    name: str
    supplier_id: int
    supplier_name: str
    internal_part_number: Optional[str] = None
    source_document_id: Optional[int] = None
    deduped: bool = False
    warning: Optional[str] = None


class CadportComponentImport(BaseModel):
    cadport_part_id: str
    catalog_part_id: Optional[int] = None
    instance_name: str
    quantity: int = 1
    transform: Optional[List[List[float]]] = None
    suppressed: bool = False


class CadportAssemblyImport(BaseModel):
    assembly_id: str
    project_id: int
    display_name: str
    source_file: str
    content_hash: Optional[str] = None
    total_mass_kg: float = 0.0
    center_of_mass_m: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    solidworks_version: Optional[str] = None
    yaml_filename: str
    yaml_content: str
    components: List[CadportComponentImport] = Field(default_factory=list)


class CadportComponentResult(BaseModel):
    catalog_part_id: Optional[int]
    cadport_part_id: str
    instance_name: str
    quantity: int
    suppressed: bool
    # CADPORT-REBUILD-003 Phase 1: enriched so the Assemblies-tab UI
    # doesn't need N catalog round-trips. Sourced from the linked
    # catalog_part (L4) when present.
    wpn: Optional[str] = None
    display_name: Optional[str] = None
    mass_kg: Optional[float] = None
    material: Optional[str] = None
    transform: Optional[List[List[float]]] = None  # 4x4, for the iso view
    part_yaml_document_id: Optional[int] = None
    # L8 missing-parts check: does a project_part exist for this
    # catalog_part in the assembly's project?
    project_part_exists: bool = False
    project_part_id: Optional[int] = None


class CadportAssemblyResult(BaseModel):
    id: int
    assembly_id: str
    project_id: int
    project_code: Optional[str] = None
    project_name: Optional[str] = None
    display_name: str
    source_file: str
    content_hash: Optional[str] = None
    total_mass_kg: float
    center_of_mass: List[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    solidworks_version: Optional[str] = None
    component_count: int
    assembly_yaml_document_id: Optional[int] = None
    assembly_yaml_filename: Optional[str] = None
    components: List[CadportComponentResult] = Field(default_factory=list)


# ── Helpers ─────────────────────────────────────────────────────────


def _wardstone(db: Session, current_user: User) -> Supplier:
    """AD-1: the in-house supplier. Seeded by migration 0029 — look up
    by name; create defensively if a fresh DB ever lacks it."""
    s = db.query(Supplier).filter(Supplier.name == WARDSTONE_NAME).first()
    if s is not None:
        return s
    s = Supplier(
        name=WARDSTONE_NAME,
        short_name="WS",
        is_in_house=True,
        is_active=True,
        created_by_id=current_user.id,
    )
    db.add(s)
    db.flush()
    return s


def _store_yaml_document(
    db: Session,
    *,
    supplier_id: int,
    yaml_filename: str,
    yaml_content: str,
    title: str,
    current_user: User,
) -> SupplierDocument:
    """Persist a §6 YAML as a supplier_documents row (AD-5).
    Re-uses the catalog file-storage convention."""
    content = yaml_content.encode("utf-8")
    sha256 = hashlib.sha256(content).hexdigest()
    SUPPLIER_DOC_DIR.mkdir(parents=True, exist_ok=True)
    file_uuid = _uuid.uuid4().hex
    file_path = SUPPLIER_DOC_DIR / f"{file_uuid}.yaml"
    file_path.write_bytes(content)

    doc = SupplierDocument(
        supplier_id=supplier_id,
        title=title,
        original_filename=yaml_filename,  # AD-5 / AD-8: WPN-based name
        document_type=SupplierDocumentType.YAML,
        file_path=str(file_path),
        file_size_bytes=len(content),
        sha256=sha256,
        mime_type="application/yaml",
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    db.flush()
    return doc


def _dup_payload(p: CatalogPart) -> DuplicateMatch:
    return DuplicateMatch(
        found=True,
        catalog_part_id=p.id,
        cadport_part_id=str(p.cadport_part_id) if p.cadport_part_id else None,
        part_number=p.part_number,
        name=p.name,
        internal_part_number=p.internal_part_number,
    )


# ── Endpoints ───────────────────────────────────────────────────────


@router.post("/catalog/parts/check-duplicate", response_model=DuplicateMatch)
def check_duplicate(
    body: CheckDuplicateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DuplicateMatch:
    """AD-2 dedup gate. Returns the existing catalog_part for a
    content_hash, or found=false. Non-deleted rows only."""
    p = (
        db.query(CatalogPart)
        .filter(
            CatalogPart.content_hash == body.content_hash,
            CatalogPart.deleted_at.is_(None),
        )
        .order_by(CatalogPart.id.asc())
        .first()
    )
    if p is None:
        return DuplicateMatch(found=False)
    return _dup_payload(p)


@router.post(
    "/catalog/parts/from-cadport",
    response_model=CatalogPartImportResult,
    status_code=201,
)
def create_part_from_cadport(
    body: CadportPartImport,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CatalogPartImportResult:
    """Create a catalog_part from a CADPORT extraction. Idempotent on
    content_hash (AD-2): a repeat call returns the existing row with
    deduped=true instead of creating a duplicate."""
    wardstone = _wardstone(db, current_user)

    # AD-2: dedup BEFORE creating. Handles "Bottom Case extracted 3×".
    existing = (
        db.query(CatalogPart)
        .filter(
            CatalogPart.content_hash == body.content_hash,
            CatalogPart.deleted_at.is_(None),
        )
        .order_by(CatalogPart.id.asc())
        .first()
    )
    if existing is not None:
        return CatalogPartImportResult(
            catalog_part_id=existing.id,
            cadport_part_id=str(existing.cadport_part_id) if existing.cadport_part_id else body.cadport_part_id,
            part_number=existing.part_number,
            name=existing.name,
            supplier_id=existing.supplier_id,
            supplier_name=wardstone.name,
            internal_part_number=existing.internal_part_number,
            source_document_id=existing.source_document_id,
            deduped=True,
            warning=(
                f"content_hash already in catalog as part #{existing.id} "
                f"({existing.part_number}); linked to existing, not duplicated."
            ),
        )

    # Store the §6 YAML blob (AD-5).
    doc = _store_yaml_document(
        db,
        supplier_id=wardstone.id,
        yaml_filename=body.yaml_filename,
        yaml_content=body.yaml_content,
        title=body.yaml_filename,
        current_user=current_user,
    )

    com = (body.center_of_mass_m + [0.0, 0.0, 0.0])[:3]
    # part_number: WPN if allocated, else the source-file stem. The
    # (supplier_id, part_number, revision) unique constraint holds
    # because WPNs are unique and stems collide only across distinct
    # content_hashes (already deduped above).
    part_number = body.internal_part_number or Path(body.source_filename).stem

    part = CatalogPart(
        supplier_id=wardstone.id,
        part_number=part_number,
        revision=None,
        name=body.display_name,
        description=f"CADPORT extraction from {body.source_filename}",
        part_class=PartClass.MECHANICAL_OTHER,
        lru_classification=LRUClass.COMPONENT,
        mass_kg=body.mass_kg,
        material_name=body.material,
        source_document_id=doc.id,
        internal_part_number=body.internal_part_number,
        cadport_part_id=body.cadport_part_id,
        content_hash=body.content_hash,
        volume_m3=body.volume_m3,
        surface_area_m2=body.surface_area_m2,
        density_kg_m3=body.density_kg_m3,
        center_of_mass_x=com[0],
        center_of_mass_y=com[1],
        center_of_mass_z=com[2],
        ixx=body.inertia.ixx,
        iyy=body.inertia.iyy,
        izz=body.inertia.izz,
        ixy=body.inertia.ixy,
        ixz=body.inertia.ixz,
        iyz=body.inertia.iyz,
        created_by_id=current_user.id,
    )
    db.add(part)
    db.commit()
    db.refresh(part)

    _audit(
        db, "catalog_part.from_cadport", "catalog_part", part.id, current_user.id,
        {
            "cadport_part_id": body.cadport_part_id,
            "content_hash": body.content_hash,
            "wpn": body.internal_part_number,
            "supplier_id": wardstone.id,
        },
        request=request,
    )

    return CatalogPartImportResult(
        catalog_part_id=part.id,
        cadport_part_id=body.cadport_part_id,
        part_number=part.part_number,
        name=part.name,
        supplier_id=wardstone.id,
        supplier_name=wardstone.name,
        internal_part_number=part.internal_part_number,
        source_document_id=doc.id,
        deduped=False,
    )


@router.post("/cadport-assemblies", response_model=CadportAssemblyResult, status_code=201)
def create_cadport_assembly(
    body: CadportAssemblyImport,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CadportAssemblyResult:
    """L7: create the assembly↔project link + component map + store
    the assembly §6 YAML. Idempotent on assembly_id (re-import
    updates project + refreshes components)."""
    project = db.query(Project).filter(Project.id == body.project_id).first()
    if project is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            f"Project {body.project_id} not found — pick an existing project",
        )

    wardstone = _wardstone(db, current_user)
    doc = _store_yaml_document(
        db,
        supplier_id=wardstone.id,
        yaml_filename=body.yaml_filename,
        yaml_content=body.yaml_content,
        title=body.yaml_filename,
        current_user=current_user,
    )

    com = (body.center_of_mass_m + [0.0, 0.0, 0.0])[:3]
    asm = (
        db.query(CadportAssembly)
        .filter(CadportAssembly.assembly_id == body.assembly_id)
        .first()
    )
    if asm is None:
        asm = CadportAssembly(assembly_id=body.assembly_id)
        db.add(asm)
    asm.project_id = project.id
    asm.display_name = body.display_name
    asm.source_file = body.source_file
    asm.content_hash = body.content_hash
    asm.total_mass_kg = body.total_mass_kg
    asm.center_of_mass_x = com[0]
    asm.center_of_mass_y = com[1]
    asm.center_of_mass_z = com[2]
    asm.component_count = len(body.components)
    asm.solidworks_version = body.solidworks_version
    asm.assembly_yaml_document_id = doc.id
    db.flush()

    # Refresh component rows (delete + re-insert keeps it simple +
    # idempotent on re-import).
    db.query(CadportAssemblyComponent).filter(
        CadportAssemblyComponent.assembly_id == asm.id
    ).delete()
    import json as _json

    for c in body.components:
        db.add(
            CadportAssemblyComponent(
                assembly_id=asm.id,
                catalog_part_id=c.catalog_part_id,
                cadport_part_id=c.cadport_part_id,
                instance_name=c.instance_name,
                quantity=c.quantity,
                transform_json=_json.dumps(c.transform) if c.transform else None,
                suppressed=c.suppressed,
            )
        )
    db.commit()
    db.refresh(asm)

    _audit(
        db, "cadport_assembly.created", "cadport_assembly", asm.id, current_user.id,
        {
            "assembly_id": body.assembly_id,
            "project_id": project.id,
            "component_count": len(body.components),
        },
        request=request,
    )
    return _assembly_result(db, asm, project)


@router.get("/cadport-assemblies", response_model=List[CadportAssemblyResult])
def list_cadport_assemblies(
    project_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[CadportAssemblyResult]:
    q = db.query(CadportAssembly)
    if project_id is not None:
        q = q.filter(CadportAssembly.project_id == project_id)
    out: List[CadportAssemblyResult] = []
    for asm in q.order_by(CadportAssembly.id.desc()).all():
        project = db.query(Project).filter(Project.id == asm.project_id).first()
        out.append(_assembly_result(db, asm, project))
    return out


@router.get("/cadport-assemblies/{assembly_pk}", response_model=CadportAssemblyResult)
def get_cadport_assembly(
    assembly_pk: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CadportAssemblyResult:
    asm = db.query(CadportAssembly).filter(CadportAssembly.id == assembly_pk).first()
    if asm is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"cadport_assembly {assembly_pk} not found")
    project = db.query(Project).filter(Project.id == asm.project_id).first()
    return _assembly_result(db, asm, project)


def _assembly_result(
    db: Session, asm: CadportAssembly, project: Optional[Project]
) -> CadportAssemblyResult:
    import json as _json

    from app.models.catalog import CatalogPart
    from app.models.parts_library import ProjectPart

    comps = (
        db.query(CadportAssemblyComponent)
        .filter(CadportAssemblyComponent.assembly_id == asm.id)
        .all()
    )

    # Batch-load the linked catalog parts + this project's project_parts
    # so the per-component enrichment is two queries, not 2N.
    cp_ids = [c.catalog_part_id for c in comps if c.catalog_part_id]
    cp_by_id: dict[int, CatalogPart] = {}
    if cp_ids:
        for cp in db.query(CatalogPart).filter(CatalogPart.id.in_(cp_ids)).all():
            cp_by_id[cp.id] = cp
    pp_by_cp: dict[int, ProjectPart] = {}
    if cp_ids:
        for pp in (
            db.query(ProjectPart)
            .filter(
                ProjectPart.project_id == asm.project_id,
                ProjectPart.catalog_part_id.in_(cp_ids),
            )
            .all()
        ):
            pp_by_cp[pp.catalog_part_id] = pp

    asm_doc = asm.assembly_yaml_document  # relationship → SupplierDocument

    comp_results: List[CadportComponentResult] = []
    for c in comps:
        cp = cp_by_id.get(c.catalog_part_id) if c.catalog_part_id else None
        pp = pp_by_cp.get(c.catalog_part_id) if c.catalog_part_id else None
        transform = None
        if c.transform_json:
            try:
                transform = _json.loads(c.transform_json)
            except Exception:
                transform = None
        comp_results.append(
            CadportComponentResult(
                catalog_part_id=c.catalog_part_id,
                cadport_part_id=str(c.cadport_part_id) if c.cadport_part_id else "",
                instance_name=c.instance_name,
                quantity=c.quantity,
                suppressed=c.suppressed,
                wpn=cp.internal_part_number if cp else None,
                display_name=cp.name if cp else c.instance_name,
                mass_kg=float(cp.mass_kg) if cp and cp.mass_kg is not None else None,
                material=cp.material_name if cp else None,
                transform=transform,
                part_yaml_document_id=cp.source_document_id if cp else None,
                project_part_exists=pp is not None,
                project_part_id=pp.id if pp else None,
            )
        )

    return CadportAssemblyResult(
        id=asm.id,
        assembly_id=str(asm.assembly_id),
        project_id=asm.project_id,
        project_code=project.code if project else None,
        project_name=project.name if project else None,
        display_name=asm.display_name,
        source_file=asm.source_file,
        content_hash=asm.content_hash,
        total_mass_kg=asm.total_mass_kg or 0.0,
        center_of_mass=[
            asm.center_of_mass_x or 0.0,
            asm.center_of_mass_y or 0.0,
            asm.center_of_mass_z or 0.0,
        ],
        solidworks_version=asm.solidworks_version,
        component_count=asm.component_count,
        assembly_yaml_document_id=asm.assembly_yaml_document_id,
        assembly_yaml_filename=asm_doc.original_filename if asm_doc else None,
        components=comp_results,
    )
