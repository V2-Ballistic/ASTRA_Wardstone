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

import base64
import hashlib
import os
import uuid as _uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Project, User
from app.models.catalog import (
    CATALOG_PART_ROLE_TAXONOMY,
    CadportAssembly,
    CadportAssemblyComponent,
    CatalogPart,
    LRUClass,
    PartClass,
    PendingCatalogImport,
    PendingImportStatus,
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

# CADPORT-TDD-SUPPLIER-001 removed the hardcoded ``WARDSTONE_NAME``
# constant and the ``_wardstone()`` default-supplier fallback. Every
# CADPORT upload now carries an explicit supplier via
# ``supplier_id`` or ``supplier_name`` (see _resolve_supplier).


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
    # CADPORT-REBUILD-004 (AD-5): binary STL mesh, base64, exported by
    # the bridge during extraction. None when SW STL export failed —
    # additive, never blocks the import (viewer falls back to a box).
    stl_base64: Optional[str] = Field(
        None, description="Binary STL bytes, base64 (None when no mesh)"
    )
    stl_filename: Optional[str] = Field(
        None, description="WPN-based STL filename, e.g. '<wpn>.stl'"
    )
    # CADPORT-TDD-STEP-001 §7.1.2: STEP / mass-source provenance.
    # Default 'sldprt' / 'cad' so legacy callers that don't send these
    # fields still get the historical SolidWorks-row shape.
    source_format: str = Field(
        "sldprt",
        description="'sldprt' | 'step'. Stored verbatim on catalog_parts.",
    )
    step_material_key: Optional[str] = Field(
        None,
        description=(
            "CADPORT materials.json key the density came from when "
            "mass_source='material'. NULL otherwise."
        ),
    )
    mass_source: str = Field(
        "cad",
        description="'cad' | 'material' | 'user_override' — how mass was determined.",
    )
    inertia_revised_via_uniform_scaling: bool = Field(
        False,
        description=(
            "True iff this row's inertia tensor was produced by linear "
            "mass-scaling rather than re-derived from geometry."
        ),
    )
    # CADPORT-TDD-ASTRA-BRIDGE-001 Phase 2: original source CAD files
    # for retention + download. Empty list when nothing is attached.
    source_files: List[Dict[str, Any]] = Field(
        default_factory=list,
        description=(
            "Source CAD file payloads. Each entry: "
            "{kind: 'sldprt' | 'sldasm' | 'step', filename, sha256, content_base64}."
        ),
    )
    # CADPORT-TDD-SUPPLIER-001 §3.3: explicit supplier choice. Exactly
    # one of these must be set — the handler returns 400 otherwise.
    # ``supplier_id`` selects an existing row (404 if missing);
    # ``supplier_name`` creates a new row when no case-insensitive
    # match exists, or reuses one when it does.
    supplier_id: Optional[int] = Field(
        None,
        description="Existing supplier id. Mutually exclusive with supplier_name.",
    )
    supplier_name: Optional[str] = Field(
        None,
        description=(
            "Supplier name. Creates a new row on first sight (case-"
            "insensitive match against existing). Mutually exclusive "
            "with supplier_id."
        ),
    )
    # Config-ecosystem deltas (spec §7.2): vehicle role taxonomy,
    # carried verbatim from cadport_parts.role. Validated against
    # CATALOG_PART_ROLE_TAXONOMY (422 on a bad value); None when the
    # CADPORT operator never set one.
    role: Optional[str] = Field(
        None,
        description=(
            "Vehicle role: oml | structure | avionics | payload | "
            "propulsion | recovery | ballast | other. 'oml' flags the "
            "airframe. None when unset."
        ),
    )

    @field_validator("role")
    @classmethod
    def _validate_role(cls, v: Optional[str]) -> Optional[str]:
        value = (v or "").strip() or None
        if value is not None and value not in CATALOG_PART_ROLE_TAXONOMY:
            raise ValueError(
                f"Invalid role {value!r}. Valid roles: "
                f"{', '.join(CATALOG_PART_ROLE_TAXONOMY)}."
            )
        return value


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
    # CADPORT-TDD-SUPPLIER-001 §5.4: True when this upload created the
    # supplier row (used by the UI to render "New supplier: VectorNav"
    # in the result panel).
    supplier_created: bool = False
    # Config-ecosystem deltas (spec §7.2): role as persisted on the
    # catalog_parts row (None when unset).
    role: Optional[str] = None


class CadportPendingImportResult(BaseModel):
    """CADPORT-TDD-ASTRA-BRIDGE-001 Phase 1: response for the new
    ``/pending-imports/from-cadport`` endpoint. ``review_url`` is a
    relative frontend path the CADPORT UI surfaces as a toast link."""
    id: int
    status: str = "pending"
    review_url: str
    source_document_id: int
    # Echo the supplier picker so the CADPORT UI can re-render the
    # ('proposed: X — will be created on approval') hint without a
    # second round-trip.
    supplier_id: Optional[int] = None
    proposed_supplier_name: Optional[str] = None


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
    # CADPORT-REBUILD-003: rollup inertia tensor (kg·m², CITADEL body
    # frame). {ixx,iyy,izz,ixy,ixz,iyz}. Optional for back-compat with
    # any caller that doesn't send it yet.
    inertia: Optional[CadportInertia] = None
    solidworks_version: Optional[str] = None
    yaml_filename: str
    yaml_content: str
    components: List[CadportComponentImport] = Field(default_factory=list)
    # CADPORT-TDD-SUPPLIER-001 §3.3 — see CadportPartImport.
    supplier_id: Optional[int] = Field(
        None,
        description="Existing supplier id. Mutually exclusive with supplier_name.",
    )
    supplier_name: Optional[str] = Field(
        None,
        description=(
            "Supplier name; created on first sight (case-insensitive). "
            "Mutually exclusive with supplier_id."
        ),
    )


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
    # CADPORT-REBUILD-004: per-component STL mesh doc for the Three.js
    # viewer. None → that component renders as a fallback box (AD-7).
    stl_document_id: Optional[int] = None
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
    # CADPORT-REBUILD-003: rollup inertia tensor + principal moments.
    inertia: Optional[CadportInertia] = None
    principal_moments_kg_m2: List[float] = Field(default_factory=list)
    solidworks_version: Optional[str] = None
    component_count: int
    assembly_yaml_document_id: Optional[int] = None
    assembly_yaml_filename: Optional[str] = None
    components: List[CadportComponentResult] = Field(default_factory=list)


# ── Helpers ─────────────────────────────────────────────────────────


def _resolve_supplier(
    db: Session,
    *,
    supplier_id: int | None,
    supplier_name: str | None,
    current_user: User,
    request=None,
) -> tuple[Supplier, bool]:
    """CADPORT-TDD-SUPPLIER-001 §3.3: surface the spec's exactly-one
    constraint as 400 / 404 errors. Returns (supplier, created)."""
    from app.services.supplier_service import resolve_supplier_choice

    try:
        return resolve_supplier_choice(
            db,
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            current_user_id=current_user.id,
            request=request,
        )
    except ValueError as exc:
        if str(exc) == "both":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Send either supplier_id or supplier_name, not both.",
            ) from exc
        if str(exc) == "neither":
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "supplier_id or supplier_name is required.",
            ) from exc
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


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


def _store_source_file_document(
    db: Session,
    *,
    supplier_id: int,
    kind: str,
    filename: str,
    content_base64: str,
    sha256_claim: Optional[str],
    current_user: "User",
) -> SupplierDocument:
    """CADPORT-TDD-ASTRA-BRIDGE-001 Phase 2: persist one source CAD
    file (sldprt / sldasm / step) as a ``supplier_documents`` row.

    Mirrors ``_store_stl_document`` / ``_store_yaml_document``: hash
    the content, write to ``SUPPLIER_DOC_DIR / <uuid>.<ext>``, and
    create the row with the right ``document_type``. Returns the
    persisted ``SupplierDocument``.

    ``sha256_claim`` is the hash the CADPORT plugin computed; we
    verify it matches the bytes we received before storing (mismatch
    → log + accept anyway; the file is still stored under its actual
    hash).
    """
    try:
        data = base64.b64decode(content_base64)
    except Exception as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"source_files entry {kind!r} ({filename!r}): undecodable base64: {exc}",
        ) from exc
    if not data:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"source_files entry {kind!r} ({filename!r}): empty",
        )
    sha256_actual = hashlib.sha256(data).hexdigest()
    if sha256_claim and sha256_claim.lower() != sha256_actual.lower():
        # Log + accept — the stored hash is the actual one.
        # Caller should already know about the mismatch if it matters.
        pass

    SUPPLIER_DOC_DIR.mkdir(parents=True, exist_ok=True)
    file_uuid = _uuid.uuid4().hex
    suffix = {"sldprt": "sldprt", "sldasm": "sldasm", "step": "step"}.get(
        kind.lower(), kind.lower()
    )
    file_path = SUPPLIER_DOC_DIR / f"{file_uuid}.{suffix}"
    file_path.write_bytes(data)

    document_type = {
        "sldprt": SupplierDocumentType.SLDPRT,
        "sldasm": SupplierDocumentType.SLDASM,
        "step":   SupplierDocumentType.STEP,
    }[kind.lower()]
    mime_type = {
        "sldprt": "application/x-solidworks-part",
        "sldasm": "application/x-solidworks-assembly",
        "step":   "application/step",
    }[kind.lower()]
    doc = SupplierDocument(
        supplier_id=supplier_id,
        title=filename or f"{file_uuid}.{suffix}",
        original_filename=filename or f"{file_uuid}.{suffix}",
        document_type=document_type,
        file_path=str(file_path),
        file_size_bytes=len(data),
        sha256=sha256_actual,
        mime_type=mime_type,
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    db.flush()
    return doc


def _attach_source_files(
    db: Session,
    *,
    part: CatalogPart,
    source_files: list[dict[str, Any]],
    current_user: "User",
) -> dict[str, int]:
    """Persist the source files attached to this CADPORT upload and
    set the matching ``catalog_parts`` FK columns. Returns a dict of
    ``{kind: document_id}`` for the rows actually attached."""
    attached: dict[str, int] = {}
    fk_map = {
        "sldprt": "sldprt_document_id",
        "sldasm": "sldasm_document_id",
        "step":   "step_document_id",
    }
    seen: set[str] = set()
    for entry in source_files or []:
        kind = (entry.get("kind") or "").lower()
        if kind not in fk_map or kind in seen:
            continue
        content = entry.get("content_base64")
        if not content:
            continue
        doc = _store_source_file_document(
            db,
            supplier_id=part.supplier_id,
            kind=kind,
            filename=entry.get("filename") or f"{kind}.bin",
            content_base64=content,
            sha256_claim=entry.get("sha256"),
            current_user=current_user,
        )
        setattr(part, fk_map[kind], doc.id)
        attached[kind] = doc.id
        seen.add(kind)
    if attached:
        db.flush()
    return attached


def _store_stl_document(
    db: Session,
    *,
    supplier_id: int,
    stl_filename: str,
    stl_bytes: bytes,
    current_user: User,
) -> SupplierDocument:
    """CADPORT-REBUILD-004 (AD-5): persist a binary STL as a
    supplier_documents row (document_type='stl'), same file-storage
    convention as the §6 YAML blob. Served back through the existing
    /catalog/documents/{id}/file route."""
    sha256 = hashlib.sha256(stl_bytes).hexdigest()
    SUPPLIER_DOC_DIR.mkdir(parents=True, exist_ok=True)
    file_uuid = _uuid.uuid4().hex
    file_path = SUPPLIER_DOC_DIR / f"{file_uuid}.stl"
    file_path.write_bytes(stl_bytes)

    doc = SupplierDocument(
        supplier_id=supplier_id,
        title=stl_filename,
        original_filename=stl_filename,
        document_type=SupplierDocumentType.STL,
        file_path=str(file_path),
        file_size_bytes=len(stl_bytes),
        sha256=sha256,
        mime_type="model/stl",
        uploaded_by_id=current_user.id,
    )
    db.add(doc)
    db.flush()
    return doc


def _decode_stl(body: "CadportPartImport") -> Optional[bytes]:
    """Decode the inline base64 STL. None (not an error) when the
    bridge had no mesh — STL is additive and never blocks an import."""
    if not body.stl_base64:
        return None
    try:
        data = base64.b64decode(body.stl_base64)
    except Exception:
        return None
    return data or None


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


class AttachStlRequest(BaseModel):
    stl_base64: str = Field(..., description="Binary STL bytes, base64")
    stl_filename: Optional[str] = Field(None, description="e.g. '<wpn>.stl'")


class AttachStlResult(BaseModel):
    catalog_part_id: int
    stl_document_id: Optional[int]
    created: bool


@router.post(
    "/catalog/parts/{catalog_part_id}/stl",
    response_model=AttachStlResult,
)
def attach_stl_to_catalog_part(
    catalog_part_id: int,
    body: AttachStlRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AttachStlResult:
    """CADPORT-REBUILD-004: attach an STL mesh to an existing
    catalog_part.

    The TDD-2 import orchestrator dedups on content_hash via
    /check-duplicate and, on a hit, links to the existing row WITHOUT
    calling /from-cadport — so the STL backfill in that endpoint never
    runs for already-cataloged parts (Bottom Case et al., imported
    pre-STL). This dedicated path lets the orchestrator's dedup branch
    still land the mesh. Idempotent: a part that already has an STL
    keeps it (created=false)."""
    cp = (
        db.query(CatalogPart)
        .filter(CatalogPart.id == catalog_part_id)
        .first()
    )
    if cp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "catalog_part not found")
    if cp.stl_document_id is not None:
        return AttachStlResult(
            catalog_part_id=cp.id,
            stl_document_id=cp.stl_document_id,
            created=False,
        )
    try:
        data = base64.b64decode(body.stl_base64)
    except Exception:
        data = b""
    if not data:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "stl_base64 empty or undecodable"
        )
    # CADPORT-TDD-SUPPLIER-001: the STL is a sibling document to the
    # part — store it under the part's existing supplier rather than
    # the deleted Wardstone default.
    doc = _store_stl_document(
        db,
        supplier_id=cp.supplier_id,
        stl_filename=body.stl_filename or f"{cp.part_number}.stl",
        stl_bytes=data,
        current_user=current_user,
    )
    cp.stl_document_id = doc.id
    db.commit()
    return AttachStlResult(
        catalog_part_id=cp.id, stl_document_id=doc.id, created=True
    )


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
    deduped=true instead of creating a duplicate.

    CADPORT-TDD-SUPPLIER-001 §3.3: supplier comes from ``body.supplier_id``
    OR ``body.supplier_name`` (exactly one required) — no more silent
    Wardstone default.
    """
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
        # Dedup hit: do NOT resolve a fresh supplier (would 400 the
        # repeat upload if a name wasn't passed). Reuse the existing
        # row's supplier — the repeat is essentially a no-op.
        existing_supplier = (
            db.query(Supplier).filter(Supplier.id == existing.supplier_id).first()
        )
        existing_supplier_name = existing_supplier.name if existing_supplier else "?"
        # CADPORT-REBUILD-004: backfill the STL for an already-deduped
        # part. Bottom Case was imported pre-STL (or 3× under TDD-2's
        # dedup proof) — a re-extraction now carries a mesh the catalog
        # row is missing. Idempotent: only fills a NULL stl_document_id.
        stl_bytes = _decode_stl(body)
        if stl_bytes and existing.stl_document_id is None:
            try:
                stl_doc = _store_stl_document(
                    db,
                    supplier_id=existing.supplier_id,
                    stl_filename=body.stl_filename
                    or f"{existing.part_number}.stl",
                    stl_bytes=stl_bytes,
                    current_user=current_user,
                )
                existing.stl_document_id = stl_doc.id
                db.commit()
            except Exception:
                db.rollback()
        return CatalogPartImportResult(
            catalog_part_id=existing.id,
            cadport_part_id=str(existing.cadport_part_id) if existing.cadport_part_id else body.cadport_part_id,
            part_number=existing.part_number,
            name=existing.name,
            supplier_id=existing.supplier_id,
            supplier_name=existing_supplier_name,
            internal_part_number=existing.internal_part_number,
            source_document_id=existing.source_document_id,
            deduped=True,
            warning=(
                f"content_hash already in catalog as part #{existing.id} "
                f"({existing.part_number}); linked to existing, not duplicated."
            ),
            supplier_created=False,
            role=existing.role,
        )

    # Resolve the upload's supplier choice. 400 if neither/both, 404 if id missing.
    supplier, supplier_created = _resolve_supplier(
        db,
        supplier_id=body.supplier_id,
        supplier_name=body.supplier_name,
        current_user=current_user,
        request=request,
    )

    # Store the §6 YAML blob (AD-5).
    doc = _store_yaml_document(
        db,
        supplier_id=supplier.id,
        yaml_filename=body.yaml_filename,
        yaml_content=body.yaml_content,
        title=body.yaml_filename,
        current_user=current_user,
    )

    # CADPORT-REBUILD-004: store the STL mesh (if any) as a sibling
    # supplier_document. Best-effort — a mesh failure must not block
    # the catalog import (AD: STL is additive).
    stl_doc_id: Optional[int] = None
    stl_bytes = _decode_stl(body)
    if stl_bytes:
        try:
            stl_doc = _store_stl_document(
                db,
                supplier_id=supplier.id,
                stl_filename=body.stl_filename
                or f"{body.internal_part_number or Path(body.source_filename).stem}.stl",
                stl_bytes=stl_bytes,
                current_user=current_user,
            )
            stl_doc_id = stl_doc.id
        except Exception:
            stl_doc_id = None

    com = (body.center_of_mass_m + [0.0, 0.0, 0.0])[:3]
    # part_number: WPN if allocated, else the source-file stem. The
    # (supplier_id, part_number, revision) unique constraint holds
    # because WPNs are unique and stems collide only across distinct
    # content_hashes (already deduped above).
    part_number = body.internal_part_number or Path(body.source_filename).stem

    # CADPORT-TDD-SUPPLIER-001: coerce cadport_part_id at the handler
    # boundary. Postgres' UUID column auto-coerces strings; SQLite (used
    # by the test suite) doesn't, so do it explicitly here.
    _cadport_uuid = (
        _uuid.UUID(body.cadport_part_id)
        if body.cadport_part_id and not isinstance(body.cadport_part_id, _uuid.UUID)
        else body.cadport_part_id
    )
    part = CatalogPart(
        supplier_id=supplier.id,
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
        cadport_part_id=_cadport_uuid,
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
        stl_document_id=stl_doc_id,
        # CADPORT-TDD-STEP-001 §7.1.2 provenance.
        source_format=body.source_format,
        step_material_key=body.step_material_key,
        mass_source=body.mass_source,
        inertia_revised_via_uniform_scaling=body.inertia_revised_via_uniform_scaling,
        # Config-ecosystem deltas (spec §7.2): role taxonomy (validated
        # by the CadportPartImport field validator).
        role=body.role,
        created_by_id=current_user.id,
    )
    db.add(part)
    db.flush()
    db.refresh(part)

    # CADPORT-TDD-ASTRA-BRIDGE-001 Phase 2: persist source CAD files
    # carried in the payload + link FKs. Failures log + continue.
    if body.source_files:
        try:
            _attach_source_files(
                db, part=part, source_files=body.source_files,
                current_user=current_user,
            )
        except HTTPException:
            raise
        except Exception:
            import logging as _log
            _log.getLogger(__name__).exception(
                "source-file attach failed for catalog_part %s (continuing)",
                part.id,
            )
    db.commit()
    db.refresh(part)

    _audit(
        db, "catalog_part.from_cadport", "catalog_part", part.id, current_user.id,
        {
            "cadport_part_id": body.cadport_part_id,
            "content_hash": body.content_hash,
            "wpn": body.internal_part_number,
            "supplier_id": supplier.id,
            "supplier_name": supplier.name,
            "supplier_created": supplier_created,
        },
        request=request,
    )

    return CatalogPartImportResult(
        catalog_part_id=part.id,
        cadport_part_id=body.cadport_part_id,
        part_number=part.part_number,
        name=part.name,
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        internal_part_number=part.internal_part_number,
        source_document_id=doc.id,
        deduped=False,
        supplier_created=supplier_created,
        role=part.role,
    )


# ══════════════════════════════════════════════════════════════
#  CADPORT-TDD-ASTRA-BRIDGE-001 Phase 1 — Pending Imports
# ══════════════════════════════════════════════════════════════


@router.post(
    "/catalog/pending-imports/from-cadport",
    response_model=CadportPendingImportResult,
    status_code=201,
)
def create_pending_import_from_cadport(
    body: CadportPartImport,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CadportPendingImportResult:
    """CADPORT upload → pending review queue (CADPORT-TDD-ASTRA-BRIDGE-001
    Phase 1).

    Same body shape as ``create_part_from_cadport``: the supplier
    picker's ``supplier_id`` XOR ``supplier_name`` rule still holds,
    enforced exactly the same way. Difference: the row lands in
    ``pending_catalog_imports`` with ``source_kind='cadport'`` instead
    of in ``catalog_parts`` directly. The §6 YAML is stored as a
    ``supplier_documents`` row (under the proposed/picked supplier when
    one resolves, else under an arbitrary holder; final wiring happens
    at approve time).

    The operator then reviews via the ASTRA pending-imports UI and
    clicks Approve to commit. On approve, supplier resolution runs
    (lookup-or-create) and the catalog_part row is created — see the
    ``approve_pending_import`` handler.
    """
    has_id = body.supplier_id is not None
    has_name = bool((body.supplier_name or "").strip())
    if has_id and has_name:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Send either supplier_id or supplier_name, not both.",
        )
    if not has_id and not has_name:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "supplier_id or supplier_name is required.",
        )

    # If supplier_id was picked, verify it exists (404 is friendlier
    # than waiting until approve).
    resolved_supplier_id: Optional[int] = None
    if has_id:
        s = db.query(Supplier).filter(Supplier.id == body.supplier_id).first()
        if s is None:
            raise HTTPException(
                status.HTTP_404_NOT_FOUND,
                f"supplier_id={body.supplier_id} not found",
            )
        resolved_supplier_id = s.id
        yaml_owner_supplier_id = s.id
    else:
        # Park the YAML under a stable placeholder — we'll re-link it
        # to the (possibly new) supplier at approve time. The simplest
        # placeholder: the first in-house supplier, falling back to
        # whatever supplier exists; the supplier_documents.supplier_id
        # is required NOT NULL so we need *some* id.
        holder = (
            db.query(Supplier)
            .filter(Supplier.is_in_house.is_(True))
            .order_by(Supplier.id.asc())
            .first()
        )
        if holder is None:
            holder = db.query(Supplier).order_by(Supplier.id.asc()).first()
        if holder is None:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Cannot create pending import — no suppliers exist to hold "
                "the YAML document. Create at least one supplier first.",
            )
        yaml_owner_supplier_id = holder.id

    # Store the §6 YAML as a supplier_documents row (mirrors the live
    # from-cadport flow exactly).
    doc = _store_yaml_document(
        db,
        supplier_id=yaml_owner_supplier_id,
        yaml_filename=body.yaml_filename,
        yaml_content=body.yaml_content,
        title=body.yaml_filename,
        current_user=current_user,
    )

    # Stuff the full payload into extracted_data so the approve handler
    # has everything it needs without re-parsing the YAML. The body's
    # cadport_part_id is a string at the wire; coerce to str for jsonb.
    extracted_data: Dict[str, Any] = body.model_dump(mode="json")
    # Annotate so the approve handler can branch cleanly.
    extracted_data["_source_kind"] = "cadport"

    pending = PendingCatalogImport(
        source_document_id=doc.id,
        supplier_id=resolved_supplier_id,
        proposed_supplier_name=(body.supplier_name or "").strip() or None,
        source_kind="cadport",
        extracted_data=extracted_data,
        extraction_confidence=1.0,  # CADPORT extraction is deterministic.
        status=PendingImportStatus.PENDING,
    )
    db.add(pending)
    db.commit()
    db.refresh(pending)

    _audit(
        db, "cadport.pending_import_created", "pending_catalog_import",
        pending.id, current_user.id,
        {
            "cadport_part_id": body.cadport_part_id,
            "content_hash": body.content_hash,
            "supplier_id": resolved_supplier_id,
            "proposed_supplier_name": pending.proposed_supplier_name,
            "source_document_id": doc.id,
        },
        request=request,
    )

    return CadportPendingImportResult(
        id=pending.id,
        status=pending.status.value if hasattr(pending.status, "value") else str(pending.status),
        review_url=f"/catalog/pending-imports/{pending.id}",
        source_document_id=doc.id,
        supplier_id=resolved_supplier_id,
        proposed_supplier_name=pending.proposed_supplier_name,
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

    # CADPORT-TDD-SUPPLIER-001 §3.3: explicit supplier required.
    supplier, _supplier_created = _resolve_supplier(
        db,
        supplier_id=body.supplier_id,
        supplier_name=body.supplier_name,
        current_user=current_user,
        request=request,
    )
    doc = _store_yaml_document(
        db,
        supplier_id=supplier.id,
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
    if body.inertia is not None:
        asm.ixx = body.inertia.ixx
        asm.iyy = body.inertia.iyy
        asm.izz = body.inertia.izz
        asm.ixy = body.inertia.ixy
        asm.ixz = body.inertia.ixz
        asm.iyz = body.inertia.iyz
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


# ── Phase 5: linkage visibility ─────────────────────────────────────


class CadportPartAssemblyRef(BaseModel):
    cadport_assembly_pk: int
    assembly_id: str
    display_name: str
    project_id: int
    project_code: Optional[str] = None
    instance_name: str
    quantity: int


class CadportPartLinkage(BaseModel):
    is_cadport: bool
    cadport_part_id: Optional[str] = None
    content_hash: Optional[str] = None
    wpn: Optional[str] = None
    yaml_document_id: Optional[int] = None
    # CADPORT-REBUILD-004: the STL mesh document (None → no mesh, the
    # part-detail viewer/download falls back to "no geometry").
    stl_document_id: Optional[int] = None
    solidworks_version: Optional[str] = None
    imported_at: Optional[str] = None
    assemblies: List[CadportPartAssemblyRef] = Field(default_factory=list)


@router.get(
    "/catalog/parts/{catalog_part_id}/cadport",
    response_model=CadportPartLinkage,
)
def catalog_part_cadport_linkage(
    catalog_part_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CadportPartLinkage:
    """Phase 5: the CADPORT linkage for a catalog part — its
    cadport_part_id / content_hash / WPN / YAML doc + every CADPORT
    assembly it appears in. Powers the catalog-part-detail CADPORT
    section. Returns is_cadport=false for non-CADPORT parts."""
    cp = (
        db.query(CatalogPart)
        .filter(CatalogPart.id == catalog_part_id)
        .first()
    )
    if cp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "catalog_part not found")
    if cp.cadport_part_id is None:
        return CadportPartLinkage(is_cadport=False)

    refs: List[CadportPartAssemblyRef] = []
    comps = (
        db.query(CadportAssemblyComponent)
        .filter(CadportAssemblyComponent.catalog_part_id == catalog_part_id)
        .all()
    )
    sw_version: Optional[str] = None
    for c in comps:
        asm = (
            db.query(CadportAssembly)
            .filter(CadportAssembly.id == c.assembly_id)
            .first()
        )
        if asm is None:
            continue
        sw_version = sw_version or asm.solidworks_version
        proj = db.query(Project).filter(Project.id == asm.project_id).first()
        refs.append(
            CadportPartAssemblyRef(
                cadport_assembly_pk=asm.id,
                assembly_id=str(asm.assembly_id),
                display_name=asm.display_name,
                project_id=asm.project_id,
                project_code=proj.code if proj else None,
                instance_name=c.instance_name,
                quantity=c.quantity,
            )
        )
    return CadportPartLinkage(
        is_cadport=True,
        cadport_part_id=str(cp.cadport_part_id),
        content_hash=cp.content_hash,
        wpn=cp.internal_part_number,
        yaml_document_id=cp.source_document_id,
        stl_document_id=cp.stl_document_id,
        solidworks_version=sw_version,
        imported_at=cp.created_at.isoformat() if cp.created_at else None,
        assemblies=refs,
    )


@router.get("/projects/{project_id}/cadport-part-ids")
def project_cadport_part_ids(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Phase 5: the set of catalog_part_ids in this project that came
    from a CADPORT assembly (i.e. appear in cadport_assembly_components
    for an assembly linked to this project AND have a cadport_part_id).
    The project-parts page badges these rows. One cheap query; no
    shared-schema change."""
    rows = (
        db.query(CadportAssemblyComponent.catalog_part_id, CadportAssembly.display_name)
        .join(CadportAssembly, CadportAssemblyComponent.assembly_id == CadportAssembly.id)
        .filter(
            CadportAssembly.project_id == project_id,
            CadportAssemblyComponent.catalog_part_id.isnot(None),
        )
        .all()
    )
    by_cp: dict[int, str] = {}
    for cp_id, asm_name in rows:
        by_cp.setdefault(cp_id, asm_name)
    return {"catalog_part_assembly": {str(k): v for k, v in by_cp.items()}}


# ── YAML blob backfill (CADPORT-REBUILD-003 fix #1) ─────────────────
#
# TDD-2 wrote §6 YAML blobs to SUPPLIER_DOC_DIR. With SUPPLIER_DOC_DIR
# unset the default /data/supplier_docs is NOT a mounted volume in the
# ASTRA backend container, so the blobs were ephemeral and lost on a
# container recreate → GET /catalog/documents/{id}/file 500s. The
# infra fix is the persistent SUPPLIER_DOC_DIR mount (docker-compose);
# this endpoint regenerates the lost blobs from the DB columns
# (every §6 field is a queryable column after 0036/0037), writes them
# to the now-persistent path, and repoints supplier_documents.file_path.
# Idempotent + self-healing: only rewrites docs whose file is missing
# (force=true rewrites all).

def _emit_part_yaml_from_db(cp: CatalogPart, db: Session) -> str:
    import yaml as _yaml

    com = {
        "x": cp.center_of_mass_x or 0.0,
        "y": cp.center_of_mass_y or 0.0,
        "z": cp.center_of_mass_z or 0.0,
    }
    pm = []
    try:
        from app.routers.catalog import _principal_moments
        pm = _principal_moments(cp.ixx, cp.iyy, cp.izz, cp.ixy, cp.ixz, cp.iyz)
    except Exception:
        pm = []
    src = "unknown.SLDPRT"
    if cp.description and "extraction from " in cp.description:
        src = cp.description.split("extraction from ", 1)[1].strip()
    doc = {
        "schema_version": "1.0",
        "kind": "part",
        "part_id": str(cp.cadport_part_id) if cp.cadport_part_id else None,
        "source_file": src,
        "content_hash": cp.content_hash,
        "extracted_at": cp.created_at.isoformat() if cp.created_at else None,
        "extracted_by": "cadport-rebuild-003-backfill",
        "solidworks_version": "unknown",
        "display_name": cp.name,
        "configuration": "Default",
        "mass_properties": {
            "units": "SI",
            "coordinate_system": "body_frame",
            "mass_kg": float(cp.mass_kg) if cp.mass_kg is not None else 0.0,
            "volume_m3": cp.volume_m3,
            "surface_area_m2": cp.surface_area_m2,
            "density_kg_m3": cp.density_kg_m3,
            "center_of_mass_m": com,
            "inertia_tensor_kg_m2": {
                "ixx": cp.ixx, "iyy": cp.iyy, "izz": cp.izz,
                "ixy": cp.ixy, "ixz": cp.ixz, "iyz": cp.iyz,
            },
            "principal_moments_kg_m2": pm,
            "products_of_inertia_convention": "positive",
        },
        "material": {
            "name": cp.material_name,
            "density_kg_m3": cp.density_kg_m3,
        },
        "wpn": cp.internal_part_number,
        "catalog_part_id": cp.id,
        # CADPORT-TDD-SUPPLIER-001: read from the part's row, not a
        # hardcoded literal. Falls back to None when the supplier
        # relationship isn't loaded (shouldn't happen in practice).
        "supplier": cp.supplier.name if cp.supplier is not None else None,
    }
    return _yaml.safe_dump(doc, sort_keys=False, allow_unicode=False)


def _emit_assembly_yaml_from_db(asm: CadportAssembly, db: Session) -> str:
    import json as _json

    import yaml as _yaml

    comps = (
        db.query(CadportAssemblyComponent)
        .filter(CadportAssemblyComponent.assembly_id == asm.id)
        .all()
    )
    proj = db.query(Project).filter(Project.id == asm.project_id).first()
    comp_list = []
    for c in comps:
        cp = (
            db.query(CatalogPart).filter(CatalogPart.id == c.catalog_part_id).first()
            if c.catalog_part_id
            else None
        )
        tf = None
        if c.transform_json:
            try:
                tf = _json.loads(c.transform_json)
            except Exception:
                tf = None
        comp_list.append({
            "part_id": str(c.cadport_part_id) if c.cadport_part_id else None,
            "part_yaml": (f"{cp.internal_part_number}.yaml" if cp and cp.internal_part_number else None),
            "instance_name": c.instance_name,
            "quantity": c.quantity,
            "transform_m": tf,
            "suppressed": bool(c.suppressed),
        })
    pm = []
    try:
        from app.routers.catalog import _principal_moments
        pm = _principal_moments(asm.ixx, asm.iyy, asm.izz, asm.ixy, asm.ixz, asm.iyz)
    except Exception:
        pm = []
    doc = {
        "schema_version": "1.0",
        "kind": "assembly",
        "assembly_id": str(asm.assembly_id),
        "source_file": asm.source_file,
        "content_hash": asm.content_hash,
        "extracted_at": asm.created_at.isoformat() if asm.created_at else None,
        "extracted_by": "cadport-rebuild-003-backfill",
        "solidworks_version": asm.solidworks_version or "unknown",
        "display_name": asm.display_name,
        "configuration": "Default",
        "components": comp_list,
        "rollup": {
            "units": "SI",
            "coordinate_system": "body_frame",
            "total_mass_kg": asm.total_mass_kg or 0.0,
            "center_of_mass_m": {
                "x": asm.center_of_mass_x or 0.0,
                "y": asm.center_of_mass_y or 0.0,
                "z": asm.center_of_mass_z or 0.0,
            },
            "inertia_tensor_kg_m2": {
                "ixx": asm.ixx, "iyy": asm.iyy, "izz": asm.izz,
                "ixy": asm.ixy, "ixz": asm.ixz, "iyz": asm.iyz,
            },
            "principal_moments_kg_m2": pm,
        },
        "project_id": asm.project_id,
        "project_code": proj.code if proj else None,
        "vehicle_variant": proj.code if proj else None,
    }
    return _yaml.safe_dump(doc, sort_keys=False, allow_unicode=False)


@router.post("/cadport/backfill-yamls")
def backfill_cadport_yamls(
    force: bool = Query(False, description="Rewrite all blobs, not just missing ones"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict[str, Any]:
    """Regenerate §6 YAML blobs for CADPORT catalog_parts + assemblies
    from the DB columns, writing to the (persistent) SUPPLIER_DOC_DIR
    and repointing supplier_documents.file_path. Run once after the
    SUPPLIER_DOC_DIR persistence fix; safe + idempotent thereafter."""
    SUPPLIER_DOC_DIR.mkdir(parents=True, exist_ok=True)
    out = {"parts": 0, "assemblies": 0, "skipped": 0, "errors": []}

    def _write(doc_id: int, text: str) -> bool:
        sd = db.query(SupplierDocument).filter(SupplierDocument.id == doc_id).first()
        if sd is None:
            return False
        p = Path(sd.file_path) if sd.file_path else None
        if p is not None and p.exists() and not force:
            out["skipped"] += 1
            return False
        content = text.encode("utf-8")
        # Reuse the existing on-disk uuid filename if present, else mint.
        fname = (p.name if p else None) or f"{_uuid.uuid4().hex}.yaml"
        target = SUPPLIER_DOC_DIR / fname
        target.write_bytes(content)
        sd.file_path = str(target)
        sd.file_size_bytes = len(content)
        sd.sha256 = hashlib.sha256(content).hexdigest()
        db.add(sd)
        return True

    for cp in (
        db.query(CatalogPart)
        .filter(CatalogPart.cadport_part_id.isnot(None), CatalogPart.source_document_id.isnot(None))
        .all()
    ):
        try:
            if _write(cp.source_document_id, _emit_part_yaml_from_db(cp, db)):
                out["parts"] += 1
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"part {cp.id}: {exc}")

    for asm in db.query(CadportAssembly).filter(
        CadportAssembly.assembly_yaml_document_id.isnot(None)
    ).all():
        try:
            if _write(asm.assembly_yaml_document_id, _emit_assembly_yaml_from_db(asm, db)):
                out["assemblies"] += 1
        except Exception as exc:  # noqa: BLE001
            out["errors"].append(f"assembly {asm.id}: {exc}")

    db.commit()
    return out


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
    from app.routers.catalog import _principal_moments  # noqa: F401 (lazy, avoids circular)

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
                stl_document_id=cp.stl_document_id if cp else None,
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
        inertia=(
            CadportInertia(
                ixx=asm.ixx or 0.0, iyy=asm.iyy or 0.0, izz=asm.izz or 0.0,
                ixy=asm.ixy or 0.0, ixz=asm.ixz or 0.0, iyz=asm.iyz or 0.0,
            )
            if asm.ixx is not None
            else None
        ),
        principal_moments_kg_m2=_principal_moments(
            asm.ixx, asm.iyy, asm.izz, asm.ixy, asm.ixz, asm.iyz
        ),
        solidworks_version=asm.solidworks_version,
        component_count=asm.component_count,
        assembly_yaml_document_id=asm.assembly_yaml_document_id,
        assembly_yaml_filename=asm_doc.original_filename if asm_doc else None,
        components=comp_results,
    )
