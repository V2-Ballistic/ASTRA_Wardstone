"""
ASTRA — Engineering Motors router (spec §5.2 / §5.5)
====================================================
File: backend/app/routers/engineering_motors.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §5 — Motors tab backend)

Mounts at ``/api/v1/engineering/motors``. Every create/import path
routes through the strict ``harold_naming`` service (spec §2): HAROLD
is the ONLY source of WPNs — nothing here computes, guesses, or
fabricates an identifier, and HAROLD-down surfaces as **503** (no
fallback). Handlers that talk to HAROLD are ``async def``.

Google-style ``:verb`` collection actions (``:ingestCsv``,
``:design``, ``:previewDesign``, ``revisions:from-csv``,
``revisions:from-design``) are registered as literal path suffixes —
FastAPI concatenates ``prefix + path``, so ``@router.post(":ingestCsv")``
yields the literal route ``/engineering/motors:ingestCsv``.

Immutability: there are NO update endpoints for revisions. A published
``motor_revisions`` row is never mutated — new data means a new HAROLD
``-REV`` and a new row.

RBAC mirrors the catalog router: reads need any authenticated user;
writes need admin / project_manager / requirements_engineer.
"""

from __future__ import annotations

import hashlib
import logging
import re
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.models.catalog import CatalogPart, LRUClass, PartClass, Supplier
from app.models.engineering_motor import Motor, MotorRevision
from app.schemas.engineering_motor import (
    ActiveRevisionUpdate,
    DesignPreviewResponse,
    MotorDesignCreate,
    MotorDesignInputs,
    MotorDesignRevisionCreate,
    MotorIngestResponse,
    MotorListItem,
    MotorResponse,
    MotorRevisionDetail,
    MotorRevisionSummary,
    MotorSummarySheet,
)
from app.services import harold_naming
from app.services.auth import get_current_user
from app.services.engineering.motor_artifact import (
    artifact_sha256,
    build_artifact,
    motor_class_letter,
)
from app.services.engineering.motor_ballistics import (
    BallisticsResult,
    MotorDesignError,
    result_to_artifact_series,
    solve_design,
)
from app.services.engineering.motor_ingest import (
    MotorCsvError,
    MotorIngestResult,
    ingest_motor_csv,
)
from app.services.harold_naming import (
    MTR_CODE,
    HaroldOrphanWpnError,
    HaroldUnavailableError,
)

# Optional audit — same shim pattern as catalog.py.
try:
    from app.services.audit_service import record_event as _audit
except ImportError:  # pragma: no cover - dev test fallback
    def _audit(*a, **kw):
        pass

logger = logging.getLogger("astra.engineering.motors")

router = APIRouter(prefix="/engineering/motors", tags=["Engineering Motors"])

_WPN_INDEX_RE = re.compile(r"-P(\d+)-")


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════

def _user_role(user: User) -> Optional[UserRole]:
    try:
        return UserRole(user.role) if isinstance(user.role, str) else user.role
    except ValueError:
        return None


def _require_req_eng_plus(user: User) -> User:
    """Allow admin / project_manager / requirements_engineer; deny others."""
    if _user_role(user) in (
        UserRole.ADMIN,
        UserRole.PROJECT_MANAGER,
        UserRole.REQUIREMENTS_ENGINEER,
    ):
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Insufficient permissions: engineering motor writes require "
            "admin, project_manager, or requirements_engineer role"
        ),
    )


def _harold_503(exc: HaroldUnavailableError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=(
            "HAROLD naming authority unavailable — engineering-domain "
            f"naming has no local fallback: {exc}"
        ),
    )


def _strip_rev_suffix(wpn: str) -> str:
    """Strip a trailing revision-letter token off a WPN (pure string
    surgery — ``WS-MTR-P000003-A`` → ``WS-MTR-P000003``). A WPN whose
    last token is not purely alphabetic (e.g. ``...-P000003``) is
    already a base WPN and comes back unchanged."""
    head, sep, tail = wpn.rpartition("-")
    if sep and tail.isalpha():
        return head
    return wpn


def _get_motor_or_404(db: Session, wpn: str) -> Motor:
    """Resolve a motor by exact stored WPN, by base WPN (no revision
    letter), or by any-revision WPN sharing the same system code +
    index. ``Motor.wpn`` stores HAROLD's first-issued WPN verbatim
    (e.g. ``WS-MTR-P000003-A``), so ``WS-MTR-P000003`` and a stale
    ``WS-MTR-P000003-C`` both resolve to that motor. Storage is never
    changed here — this is lookup-side normalization only."""
    m = db.query(Motor).filter(Motor.wpn == wpn).first()
    if m is not None:
        return m
    base = _strip_rev_suffix(wpn)
    if base:
        candidates = (
            db.query(Motor)
            .filter(or_(Motor.wpn == base, Motor.wpn.like(f"{base}-%")))
            .order_by(Motor.id)
            .all()
        )
        for c in candidates:
            if c.wpn == base or _strip_rev_suffix(c.wpn) == base:
                return c
    raise HTTPException(404, f"Motor {wpn} not found")


def _get_revision_or_404(db: Session, motor: Motor, rev: str) -> MotorRevision:
    r = (
        db.query(MotorRevision)
        .filter(
            MotorRevision.motor_id == motor.id,
            MotorRevision.rev_letter == rev.upper(),
        )
        .first()
    )
    if r is None:
        raise HTTPException(404, f"Motor {motor.wpn} has no revision {rev!r}")
    return r


def _entry_rev_letter(entry: Dict[str, Any]) -> str:
    """Revision letter from HAROLD's ledger entry (never invented)."""
    rev = entry.get("revision")
    if rev:
        return str(rev)
    wpn = entry.get("wpn") or ""
    return wpn.rsplit("-", 1)[-1] if "-" in wpn else "A"


def _entry_base_index(entry: Dict[str, Any]) -> int:
    """Base index from HAROLD's ledger entry (fallback: parse the WPN
    HAROLD returned — still HAROLD's number, never computed locally)."""
    idx = entry.get("part_number_int")
    if idx is not None:
        return int(idx)
    m = _WPN_INDEX_RE.search(entry.get("wpn") or "")
    if m:
        return int(m.group(1))
    raise HTTPException(
        502, "HAROLD ledger entry carries no parsable base index",
    )


def _canonical_name_from_precheck(verdict: Dict[str, Any], filename: str) -> str:
    """HAROLD decides the canonical name — surface what it returned.
    Falls back to the precheck's iteration stem, then the bare filename
    stem (HAROLD's own stem parse for a token-less name)."""
    for key in ("canonical_name", "canonicalName", "iteration_stem"):
        v = verdict.get(key)
        if v:
            return str(v)
    return Path(filename).stem


def _ensure_inhouse_supplier(db: Session, user: User) -> Supplier:
    """Find-or-create the in-house supplier (Wardstone pattern)."""
    s = (
        db.query(Supplier)
        .filter(Supplier.is_in_house.is_(True))
        .order_by(Supplier.id)
        .first()
    )
    if s is not None:
        return s
    s = Supplier(name="Wardstone", is_in_house=True, created_by_id=user.id)
    db.add(s)
    db.flush()
    return s


def _ensure_catalog_entry(
    db: Session,
    user: User,
    *,
    wpn: str,
    name: str,
    mass_kg: float,
) -> CatalogPart:
    """Find-or-create the motor's catalog row. If a row for this WPN
    already exists, leave it untouched."""
    existing = (
        db.query(CatalogPart)
        .filter(
            or_(
                CatalogPart.internal_part_number == wpn,
                CatalogPart.part_number == wpn,
            ),
            CatalogPart.deleted_at.is_(None),
        )
        .first()
    )
    if existing is not None:
        return existing
    supplier = _ensure_inhouse_supplier(db, user)
    part = CatalogPart(
        supplier_id=supplier.id,
        part_number=wpn,
        internal_part_number=wpn,
        name=name,
        part_class=PartClass.OTHER,
        lru_classification=LRUClass.COMPONENT,
        designation="solid_motor",
        mass_kg=mass_kg,
        created_by_id=user.id,
    )
    db.add(part)
    db.flush()
    return part


# ── Artifact assembly ──────────────────────────────────────────

def _artifact_from_ingest(
    res: MotorIngestResult,
    *,
    wpn: str,
    author: str,
    csv_sha256: str,
) -> Dict[str, Any]:
    return build_artifact(
        origin="csv",
        time_s=res.time_s,
        thrust_n=res.thrust_n,
        mdot_kgps=res.mdot_kgps,
        prop_mass_rem_kg=res.prop_mass_rem_kg,
        prop_mass_init_kg=res.prop_mass_init_kg,
        pchamber_pa=res.pchamber_pa,
        prop_cg_offset_m_b=res.prop_cg_offset_m_b,
        prop_inertia_axial_kgm2=res.prop_inertia_axial_kgm2,
        prop_inertia_transverse_kgm2=res.prop_inertia_transverse_kgm2,
        grain_stack_length_m=res.grain_stack_length_m,
        burn_time_s=res.burn_time_s,
        area_exit_m2=res.area_exit_m2,
        area_throat_m2=res.area_throat_m2,
        thrust_n_by_tgrain=res.thrust_n_by_tgrain,
        mdot_kgps_by_tgrain=res.mdot_kgps_by_tgrain,
        total_impulse_ns=res.total_impulse_ns,
        peak_thrust_n=res.peak_thrust_n,
        isp_s=res.isp_s,
        quality_tier=res.quality_tier,
        defaulted_fields=list(res.defaulted_fields),
        author=author,
        wpn=wpn,
        csv_sha256=csv_sha256,
    )


def _artifact_from_design(
    result: BallisticsResult,
    inputs: MotorDesignInputs,
    *,
    wpn: str,
    author: str,
) -> Dict[str, Any]:
    series = result_to_artifact_series(result)
    return build_artifact(
        origin="design",
        time_s=series["time_s"],
        thrust_n=series["thrust_n"],
        mdot_kgps=series["mdot_kgps"],
        prop_mass_rem_kg=series["prop_mass_rem_kg"],
        prop_mass_init_kg=result.prop_mass_init_kg,
        pchamber_pa=series["pchamber_pa"],
        prop_cg_offset_m_b=series["prop_cg_offset_m_b"],
        prop_inertia_axial_kgm2=series["prop_inertia_axial_kgm2"],
        prop_inertia_transverse_kgm2=series["prop_inertia_transverse_kgm2"],
        grain_stack_length_m=result.grain_stack_length_m,
        burn_time_s=result.burn_time_s,
        area_exit_m2=result.area_exit_m2,
        area_throat_m2=result.area_throat_m2,
        thrust_n_by_tgrain=series["thrust_n_by_tgrain"],
        mdot_kgps_by_tgrain=series["mdot_kgps_by_tgrain"],
        total_impulse_ns=result.total_impulse_ns,
        peak_thrust_n=result.peak_thrust_n,
        isp_s=result.isp_s,
        quality_tier="excellent",
        defaulted_fields=[],
        author=author,
        wpn=wpn,
        design_inputs=inputs.model_dump(),
    )


def _make_revision_row(
    motor_id: Optional[int],
    entry: Dict[str, Any],
    *,
    origin: str,
    artifact: Dict[str, Any],
    user: User,
    design_inputs: Optional[Dict[str, Any]] = None,
    csv_filename: Optional[str] = None,
    csv_sha256: Optional[str] = None,
    csv_text: Optional[str] = None,
    quality_tier: str,
    defaulted_fields: List[str],
    warnings: List[str],
    notes: Optional[str] = None,
) -> MotorRevision:
    return MotorRevision(
        motor_id=motor_id,
        wpn=entry["wpn"],
        rev_letter=_entry_rev_letter(entry),
        origin=origin,
        design_inputs=design_inputs,
        source_csv_filename=csv_filename,
        source_csv_sha256=csv_sha256,
        source_csv_text=csv_text,
        artifact=artifact,
        artifact_sha256=artifact_sha256(artifact),
        total_impulse_ns=artifact["TotalImpulse_Ns"],
        peak_thrust_n=artifact["PeakThrust_N"],
        burn_time_s=artifact["BurnTime_s"],
        isp_s=artifact["Isp_s"],
        quality_tier=quality_tier,
        defaulted_fields=defaulted_fields,
        warnings=warnings,
        notes=notes,
        created_by_id=user.id,
    )


# ── HAROLD revise-then-persist (gapless, mirrors allocate_and_persist) ──

async def _revise_and_persist(
    db: Session,
    base_wpn: str,
    persist_fn: Callable[[Session, Dict[str, Any]], Any],
    *,
    rev_kwargs: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], Any]:
    """``issue_revision`` then persist + commit; on persistence failure
    roll back and RELEASE the freshly issued revision WPN so HAROLD's
    ledger never drifts (spec §2.7)."""
    entry = await harold_naming.issue_revision(base_wpn, **(rev_kwargs or {}))
    wpn = entry.get("wpn") or ""
    try:
        result = persist_fn(db, entry)
        db.commit()
    except Exception as persist_exc:
        db.rollback()
        logger.warning(
            "revise_and_persist: persistence failed for %s (%s); "
            "releasing back to HAROLD",
            wpn, persist_exc,
        )
        try:
            await harold_naming.release(
                wpn, reason=f"persistence failed: {persist_exc!s}",
            )
        except Exception as release_exc:
            logger.critical(
                "ORPHAN WPN %s: persistence failed (%s) AND release "
                "failed (%s). Manual reconciliation required.",
                wpn, persist_exc, release_exc,
            )
            raise HaroldOrphanWpnError(
                f"WPN {wpn} is orphaned: persistence failed "
                f"({persist_exc!s}) and release failed ({release_exc!s})",
                wpn=wpn,
            ) from persist_exc
        raise
    return entry, result


async def _record_use_best_effort(
    wpn: str, metadata: Dict[str, Any], warnings: List[str],
) -> None:
    """Ledger annotation AFTER successful persistence. A HAROLD outage
    here must not fail the request (the record already exists) — it is
    surfaced as a warning instead."""
    try:
        await harold_naming.record_use(wpn, "motor_revision", metadata)
    except HaroldUnavailableError as exc:
        logger.warning("record_use(%s) failed post-persist: %s", wpn, exc)
        warnings.append(
            f"HAROLD ledger annotation (record_use) failed for {wpn}: {exc}"
        )


# ── Response assembly ──────────────────────────────────────────

def _current_rev(motor: Motor) -> Optional[MotorRevision]:
    if motor.active_revision is not None:
        return motor.active_revision
    return motor.revisions[-1] if motor.revisions else None


def _motor_response(motor: Motor) -> MotorResponse:
    resp = MotorResponse.model_validate(motor)
    resp.revisions = [
        MotorRevisionSummary.model_validate(r) for r in motor.revisions
    ]
    return resp


def _list_item(motor: Motor) -> MotorListItem:
    cur = _current_rev(motor)
    return MotorListItem(
        id=motor.id,
        wpn=motor.wpn,
        name=motor.name,
        motor_class=motor.motor_class,
        total_impulse_ns=cur.total_impulse_ns if cur else None,
        quality_tier=cur.quality_tier if cur else None,
        current_rev_letter=cur.rev_letter if cur else None,
        updated_at=motor.updated_at,
    )


# ══════════════════════════════════════════════════════════════
#  Reads
# ══════════════════════════════════════════════════════════════

@router.get("", response_model=List[MotorListItem])
async def list_motors(
    q: Optional[str] = Query(None, description="Search by WPN or name"),
    motor_class: Optional[str] = Query(None, alias="class"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = db.query(Motor)
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Motor.wpn.ilike(like), Motor.name.ilike(like)))
    if motor_class:
        query = query.filter(Motor.motor_class == motor_class)
    motors = query.order_by(Motor.wpn).offset(skip).limit(limit).all()
    return [_list_item(m) for m in motors]


@router.get("/{wpn}", response_model=MotorResponse)
async def get_motor(
    wpn: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _motor_response(_get_motor_or_404(db, wpn))


@router.get("/{wpn}/summary", response_model=MotorSummarySheet)
async def get_motor_summary(
    wpn: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    motor = _get_motor_or_404(db, wpn)
    cur = _current_rev(motor)
    return MotorSummarySheet(
        wpn=motor.wpn,
        name=motor.name,
        motor_class=motor.motor_class,
        rev_letter=cur.rev_letter if cur else None,
        origin=cur.origin if cur else None,
        quality_tier=cur.quality_tier if cur else None,
        total_impulse_ns=cur.total_impulse_ns if cur else None,
        peak_thrust_n=cur.peak_thrust_n if cur else None,
        burn_time_s=cur.burn_time_s if cur else None,
        isp_s=cur.isp_s if cur else None,
        prop_mass_init_kg=(
            (cur.artifact or {}).get("PropMassInit_kg") if cur else None
        ),
        revision_count=len(motor.revisions),
    )


@router.get("/{wpn}/revisions/{rev}", response_model=MotorRevisionDetail)
async def get_motor_revision(
    wpn: str,
    rev: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    motor = _get_motor_or_404(db, wpn)
    return MotorRevisionDetail.model_validate(_get_revision_or_404(db, motor, rev))


@router.get("/{wpn}/revisions/{rev}/artifact")
async def get_motor_revision_artifact(
    wpn: str,
    rev: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Dict[str, Any]:
    motor = _get_motor_or_404(db, wpn)
    return _get_revision_or_404(db, motor, rev).artifact


@router.get("/{wpn}/revisions/{rev}/source")
async def get_motor_revision_source(
    wpn: str,
    rev: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Download the stored source CSV for a csv-origin revision,
    verbatim as uploaded (spec §5.2: source stored with hash AND
    retrievable). Design-origin revisions have no source CSV ⇒ 404.
    The stored sha256 is surfaced in the ``X-Source-Sha256`` header so
    callers can verify integrity without re-hashing."""
    motor = _get_motor_or_404(db, wpn)
    rev_row = _get_revision_or_404(db, motor, rev)
    if rev_row.source_csv_text is None:
        raise HTTPException(
            404,
            f"Motor revision {rev_row.wpn} has no stored source CSV "
            f"(origin {rev_row.origin!r})",
        )
    filename = rev_row.source_csv_filename or f"{rev_row.wpn}.csv"
    # RFC 6266: quote the filename; strip embedded quotes/CRLF so a
    # hostile stored filename cannot break the header.
    safe_filename = re.sub(r'["\r\n\\]', "_", filename)
    return Response(
        content=rev_row.source_csv_text,
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_filename}"',
            "X-Source-Sha256": rev_row.source_csv_sha256 or "",
        },
    )


# ══════════════════════════════════════════════════════════════
#  §5.2 — CSV ingest (auto-named via HAROLD; the user never names it)
# ══════════════════════════════════════════════════════════════

@router.post(":ingestCsv", response_model=MotorIngestResponse, status_code=201)
async def ingest_csv(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Drag-drop CSV → hash → HAROLD precheck (HAROLD decides the
    canonical name) → ingest → allocate (or revise) → persist motor +
    revision + catalog entry → record_use. 503 when HAROLD is down."""
    _require_req_eng_plus(current_user)

    content = await file.read()
    filename = file.filename or "motor.csv"
    sha256 = hashlib.sha256(content).hexdigest()
    try:
        csv_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV is not valid UTF-8 text")

    # Ingest BEFORE any HAROLD allocation: a malformed CSV must never
    # consume (and then release) a ledger index.
    try:
        ingest = ingest_motor_csv(csv_text)
    except MotorCsvError as exc:
        raise HTTPException(422, f"Motor CSV ingest failed: {exc}")

    # HAROLD filename precheck FIRST (spec §2.4) — HAROLD decides the
    # canonical name; the uploader does not name the motor.
    try:
        precheck = await harold_naming.precheck_filename(filename, MTR_CODE)
    except HaroldUnavailableError as exc:
        raise _harold_503(exc)
    canonical_name = _canonical_name_from_precheck(precheck, filename)

    # Existing-motor lineage match: same canonical display name ⇒ this
    # CSV is new data for that motor ⇒ HAROLD issues the next -REV of
    # the SAME base index; otherwise a fresh MTR index.
    existing = db.query(Motor).filter(Motor.name == canonical_name).first()

    if existing is not None:
        def persist_rev(session: Session, entry: Dict[str, Any]) -> MotorRevision:
            artifact = _artifact_from_ingest(
                ingest, wpn=entry["wpn"], author=current_user.username,
                csv_sha256=sha256,
            )
            rev_row = _make_revision_row(
                existing.id, entry,
                origin="csv", artifact=artifact, user=current_user,
                csv_filename=filename, csv_sha256=sha256, csv_text=csv_text,
                quality_tier=ingest.quality_tier,
                defaulted_fields=list(ingest.defaulted_fields),
                warnings=list(ingest.warnings),
            )
            session.add(rev_row)
            session.flush()
            return rev_row

        try:
            entry, rev_row = await _revise_and_persist(
                db, existing.wpn, persist_rev,
                rev_kwargs={
                    "display_name": canonical_name,
                    "metadata": {"source": "csv", "sha256": sha256},
                },
            )
        except HaroldUnavailableError as exc:
            raise _harold_503(exc)
        motor = existing
    else:
        def persist_motor(session: Session, entry: Dict[str, Any]) -> Motor:
            wpn = entry["wpn"]
            artifact = _artifact_from_ingest(
                ingest, wpn=wpn, author=current_user.username,
                csv_sha256=sha256,
            )
            m = Motor(
                wpn=wpn,
                base_index=_entry_base_index(entry),
                system_code=entry.get("system_code") or MTR_CODE,
                name=canonical_name,
                motor_class=motor_class_letter(ingest.total_impulse_ns),
                created_by_id=current_user.id,
            )
            session.add(m)
            session.flush()
            rev_row = _make_revision_row(
                m.id, entry,
                origin="csv", artifact=artifact, user=current_user,
                csv_filename=filename, csv_sha256=sha256, csv_text=csv_text,
                quality_tier=ingest.quality_tier,
                defaulted_fields=list(ingest.defaulted_fields),
                warnings=list(ingest.warnings),
            )
            session.add(rev_row)
            session.flush()
            m.active_revision_id = rev_row.id
            part = _ensure_catalog_entry(
                session, current_user,
                wpn=wpn, name=canonical_name,
                mass_kg=ingest.prop_mass_init_kg,
            )
            m.catalog_part_id = part.id
            return m

        try:
            entry, motor = await harold_naming.allocate_and_persist(
                db, MTR_CODE, persist_motor,
                alloc_kwargs={
                    "display_name": canonical_name,
                    "metadata": {"source": "csv", "sha256": sha256},
                },
            )
        except HaroldUnavailableError as exc:
            raise _harold_503(exc)

    db.refresh(motor)
    response_warnings = list(ingest.warnings)
    await _record_use_best_effort(
        entry["wpn"],
        {
            "motor_id": motor.id,
            "rev_letter": _entry_rev_letter(entry),
            "origin": "csv",
            "csv_sha256": sha256,
            "quality_tier": ingest.quality_tier,
        },
        response_warnings,
    )

    _audit(
        db, "engineering.motor.csv_ingested", "motor", motor.id,
        current_user.id,
        {"wpn": entry["wpn"], "quality_tier": ingest.quality_tier,
         "sha256": sha256},
    )
    return MotorIngestResponse(
        motor=_motor_response(motor),
        wpn=entry["wpn"],
        rev_letter=_entry_rev_letter(entry),
        quality_tier=ingest.quality_tier,
        recommended_fidelity=ingest.recommended_fidelity,
        warnings=response_warnings,
        defaulted_fields=list(ingest.defaulted_fields),
        precheck=precheck,
    )


@router.post(
    "/{wpn}/revisions:from-csv",
    response_model=MotorIngestResponse,
    status_code=201,
)
async def add_revision_from_csv(
    wpn: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """New CSV data for an EXISTING motor ⇒ HAROLD issues the next
    -REV of the same base index; a new immutable revision row."""
    _require_req_eng_plus(current_user)
    motor = _get_motor_or_404(db, wpn)

    content = await file.read()
    filename = file.filename or "motor.csv"
    sha256 = hashlib.sha256(content).hexdigest()
    try:
        csv_text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(422, "CSV is not valid UTF-8 text")
    try:
        ingest = ingest_motor_csv(csv_text)
    except MotorCsvError as exc:
        raise HTTPException(422, f"Motor CSV ingest failed: {exc}")

    def persist_rev(session: Session, entry: Dict[str, Any]) -> MotorRevision:
        artifact = _artifact_from_ingest(
            ingest, wpn=entry["wpn"], author=current_user.username,
            csv_sha256=sha256,
        )
        rev_row = _make_revision_row(
            motor.id, entry,
            origin="csv", artifact=artifact, user=current_user,
            csv_filename=filename, csv_sha256=sha256, csv_text=csv_text,
            quality_tier=ingest.quality_tier,
            defaulted_fields=list(ingest.defaulted_fields),
            warnings=list(ingest.warnings),
        )
        session.add(rev_row)
        session.flush()
        return rev_row

    try:
        entry, rev_row = await _revise_and_persist(
            db, motor.wpn, persist_rev,
            rev_kwargs={"metadata": {"source": "csv", "sha256": sha256}},
        )
    except HaroldUnavailableError as exc:
        raise _harold_503(exc)

    db.refresh(motor)
    response_warnings = list(ingest.warnings)
    await _record_use_best_effort(
        entry["wpn"],
        {"motor_id": motor.id, "rev_letter": _entry_rev_letter(entry),
         "origin": "csv", "csv_sha256": sha256},
        response_warnings,
    )
    return MotorIngestResponse(
        motor=_motor_response(motor),
        wpn=entry["wpn"],
        rev_letter=_entry_rev_letter(entry),
        quality_tier=ingest.quality_tier,
        recommended_fidelity=ingest.recommended_fidelity,
        warnings=response_warnings,
        defaulted_fields=list(ingest.defaulted_fields),
    )


# ══════════════════════════════════════════════════════════════
#  §5.3 — Parametric design
# ══════════════════════════════════════════════════════════════

def _solve_or_422(inputs: MotorDesignInputs) -> BallisticsResult:
    try:
        return solve_design(inputs)
    except MotorDesignError as exc:
        raise HTTPException(422, str(exc))


@router.post(":previewDesign", response_model=DesignPreviewResponse)
async def preview_design(
    inputs: MotorDesignInputs,
    current_user: User = Depends(get_current_user),
):
    """Run the solver WITHOUT persisting or naming — feeds the
    live-updating design-page plots. No HAROLD call, ever."""
    result = _solve_or_422(inputs)
    nom = result.nominal
    return DesignPreviewResponse(
        time_s=nom.time_s,
        thrust_n=nom.thrust_n,
        pchamber_pa=nom.pchamber_pa,
        mdot_kgps=[-v for v in nom.mdot_kgps],
        prop_mass_rem_kg=nom.prop_mass_rem_kg,
        total_impulse_ns=result.total_impulse_ns,
        peak_thrust_n=result.peak_thrust_n,
        burn_time_s=result.burn_time_s,
        isp_s=result.isp_s,
        prop_mass_init_kg=result.prop_mass_init_kg,
        motor_class=result.motor_class,
        max_pchamber_pa=result.max_pchamber_pa,
        warnings=result.warnings,
    )


@router.post(":design", response_model=MotorIngestResponse, status_code=201)
async def create_designed_motor(
    body: MotorDesignCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Create a NEW designed motor: solve, allocate a fresh MTR WPN
    via HAROLD, persist motor + first revision + catalog entry."""
    _require_req_eng_plus(current_user)
    result = _solve_or_422(body.inputs)

    def persist_motor(session: Session, entry: Dict[str, Any]) -> Motor:
        wpn = entry["wpn"]
        artifact = _artifact_from_design(
            result, body.inputs, wpn=wpn, author=current_user.username,
        )
        m = Motor(
            wpn=wpn,
            base_index=_entry_base_index(entry),
            system_code=entry.get("system_code") or MTR_CODE,
            name=body.name,
            motor_class=result.motor_class,
            created_by_id=current_user.id,
        )
        session.add(m)
        session.flush()
        rev_row = _make_revision_row(
            m.id, entry,
            origin="design", artifact=artifact, user=current_user,
            design_inputs=body.inputs.model_dump(),
            quality_tier="excellent",
            defaulted_fields=[],
            warnings=list(result.warnings),
            notes=body.notes,
        )
        session.add(rev_row)
        session.flush()
        m.active_revision_id = rev_row.id
        part = _ensure_catalog_entry(
            session, current_user,
            wpn=wpn, name=body.name, mass_kg=result.prop_mass_init_kg,
        )
        m.catalog_part_id = part.id
        return m

    try:
        entry, motor = await harold_naming.allocate_and_persist(
            db, MTR_CODE, persist_motor,
            alloc_kwargs={
                "display_name": body.name,
                "metadata": {"source": "design"},
            },
        )
    except HaroldUnavailableError as exc:
        raise _harold_503(exc)

    db.refresh(motor)
    response_warnings = list(result.warnings)
    await _record_use_best_effort(
        entry["wpn"],
        {"motor_id": motor.id, "rev_letter": _entry_rev_letter(entry),
         "origin": "design"},
        response_warnings,
    )
    _audit(
        db, "engineering.motor.designed", "motor", motor.id, current_user.id,
        {"wpn": entry["wpn"], "motor_class": result.motor_class},
    )
    return MotorIngestResponse(
        motor=_motor_response(motor),
        wpn=entry["wpn"],
        rev_letter=_entry_rev_letter(entry),
        quality_tier="excellent",
        recommended_fidelity="HiFi",
        warnings=response_warnings,
        defaulted_fields=[],
    )


@router.post(
    "/{wpn}/revisions:from-design",
    response_model=MotorIngestResponse,
    status_code=201,
)
async def add_revision_from_design(
    wpn: str,
    body: MotorDesignRevisionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Re-run of the design solver for an EXISTING motor ⇒ HAROLD
    issues the next -REV; new immutable revision row."""
    _require_req_eng_plus(current_user)
    motor = _get_motor_or_404(db, wpn)
    result = _solve_or_422(body.inputs)

    def persist_rev(session: Session, entry: Dict[str, Any]) -> MotorRevision:
        artifact = _artifact_from_design(
            result, body.inputs, wpn=entry["wpn"], author=current_user.username,
        )
        rev_row = _make_revision_row(
            motor.id, entry,
            origin="design", artifact=artifact, user=current_user,
            design_inputs=body.inputs.model_dump(),
            quality_tier="excellent",
            defaulted_fields=[],
            warnings=list(result.warnings),
            notes=body.notes,
        )
        session.add(rev_row)
        session.flush()
        return rev_row

    try:
        entry, rev_row = await _revise_and_persist(
            db, motor.wpn, persist_rev,
            rev_kwargs={"metadata": {"source": "design"}},
        )
    except HaroldUnavailableError as exc:
        raise _harold_503(exc)

    db.refresh(motor)
    response_warnings = list(result.warnings)
    await _record_use_best_effort(
        entry["wpn"],
        {"motor_id": motor.id, "rev_letter": _entry_rev_letter(entry),
         "origin": "design"},
        response_warnings,
    )
    return MotorIngestResponse(
        motor=_motor_response(motor),
        wpn=entry["wpn"],
        rev_letter=_entry_rev_letter(entry),
        quality_tier="excellent",
        recommended_fidelity="HiFi",
        warnings=response_warnings,
        defaulted_fields=[],
    )


# ══════════════════════════════════════════════════════════════
#  Active-revision selection
# ══════════════════════════════════════════════════════════════

@router.put("/{wpn}/active-revision", response_model=MotorResponse)
async def set_active_revision(
    wpn: str,
    body: ActiveRevisionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Select which immutable revision is the motor's published one.
    Also refreshes the catalog entry's mass to the selected revision's
    PropMassInit. (No HAROLD call — selection is an ASTRA-side pointer.)
    """
    _require_req_eng_plus(current_user)
    motor = _get_motor_or_404(db, wpn)
    rev_row = _get_revision_or_404(db, motor, body.rev_letter)

    motor.active_revision_id = rev_row.id
    if rev_row.total_impulse_ns is not None:
        motor.motor_class = motor_class_letter(rev_row.total_impulse_ns)
    if motor.catalog_part_id is not None:
        part = (
            db.query(CatalogPart)
            .filter(CatalogPart.id == motor.catalog_part_id)
            .first()
        )
        if part is not None:
            prop_mass = (rev_row.artifact or {}).get("PropMassInit_kg")
            if prop_mass is not None:
                part.mass_kg = prop_mass
    db.commit()
    db.refresh(motor)

    _audit(
        db, "engineering.motor.active_revision_set", "motor", motor.id,
        current_user.id,
        {"wpn": motor.wpn, "rev_letter": rev_row.rev_letter},
    )
    return _motor_response(motor)
