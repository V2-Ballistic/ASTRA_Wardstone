"""
ASTRA — Engineering hub: Configurations tracker router (spec §8/§9)
===================================================================
Mounts at ``/api/v1/engineering/configs``. HAROLD-named (system code
``CFG``) vehicle-configuration identities with IMMUTABLE revisions,
the structured revision diff, and the CITADEL bundle export (§9).

Naming contract (spec §2 — strict):
  * EVERY WPN comes from HAROLD verbatim via
    ``app.services.harold_naming``. Nothing here computes an index.
  * create / clone use ``allocate_and_persist`` so a failed local
    persist releases the WPN back to HAROLD (gapless sequence).
  * the revision path uses ``issue_revision`` + a manual
    release-on-failure mirror (same as the aero router).
  * HAROLD down / disabled → 503, no fallback.

Auth follows the catalog router: read = any authenticated user,
write = admin / project_manager / requirements_engineer.

Save-time validation (§8) lives in
``app.services.engineering.config_service`` — failures surface as 422
with a structured error list; an invalid config never reaches HAROLD.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import User, UserRole
from app.models.engineering_config import (
    ConfigBundleExport,
    VehicleConfig,
    VehicleConfigRevision,
)
from app.schemas.engineering_config import (
    BundleExportResponse,
    BundleExportSummary,
    ConfigActiveRevisionUpdate,
    ConfigCloneRequest,
    ConfigCreate,
    ConfigCreateResponse,
    ConfigDetail,
    ConfigRevisionCreate,
    ConfigRevisionDetail,
    ConfigRevisionSummary,
    ConfigSummary,
)
from app.services import harold_naming
from app.services.auth import get_current_user
from app.services.engineering import bundle_export as bundle_export_svc
from app.services.engineering import config_service
from app.services.engineering.bundle_export import BundleExportError
from app.services.engineering.config_service import ConfigValidationError
from app.services.harold_naming import (
    CFG_CODE,
    HaroldError,
    HaroldUnavailableError,
)

# Optional audit (same pattern as the catalog / aero routers).
try:
    from app.services.audit_service import record_event as _audit
except ImportError:  # pragma: no cover - dev test fallback
    def _audit(*a, **kw):
        pass

logger = logging.getLogger("astra.engineering.configs")

router = APIRouter(prefix="/engineering", tags=["Engineering — Configs"])


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════

def _require_req_eng_plus(user: User) -> User:
    """Allow admin / project_manager / requirements_engineer."""
    try:
        role = UserRole(user.role) if isinstance(user.role, str) else user.role
    except ValueError:
        role = None
    if role in (
        UserRole.ADMIN,
        UserRole.PROJECT_MANAGER,
        UserRole.REQUIREMENTS_ENGINEER,
    ):
        return user
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=(
            "Insufficient permissions: config write requires admin, "
            "project_manager, or requirements_engineer role"
        ),
    )


def _503(exc: HaroldUnavailableError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"HAROLD naming authority unavailable: {exc}",
    )


def _422_validation(exc: ConfigValidationError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=exc.detail(),
    )


def _base_wpn(entry: Dict[str, Any]) -> str:
    """Strip HAROLD's OWN revision letter off HAROLD's OWN issued WPN.
    Pure string surgery on HAROLD's response — never index math."""
    wpn = entry.get("wpn") or ""
    rev = entry.get("revision") or ""
    suffix = f"-{rev}"
    if rev and wpn.endswith(suffix):
        return wpn[: -len(suffix)]
    return wpn


def _rev_letter(entry: Dict[str, Any]) -> str:
    rev = entry.get("revision")
    if rev:
        return str(rev)
    wpn = entry.get("wpn") or ""
    return wpn.rsplit("-", 1)[-1] if "-" in wpn else "A"


def _get_config_or_404(db: Session, wpn: str) -> VehicleConfig:
    """Resolve by base WPN, by any revision's full WPN, or by the
    base obtained by stripping a trailing revision token."""
    cfg = db.query(VehicleConfig).filter(VehicleConfig.wpn == wpn).first()
    if cfg is not None:
        return cfg
    rev = (
        db.query(VehicleConfigRevision)
        .filter(VehicleConfigRevision.wpn == wpn)
        .first()
    )
    if rev is not None:
        return rev.config
    if "-" in wpn:
        base = wpn.rsplit("-", 1)[0]
        cfg = db.query(VehicleConfig).filter(
            VehicleConfig.wpn == base).first()
        if cfg is not None:
            return cfg
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Config {wpn!r} not found",
    )


def _get_revision_or_404(
    config: VehicleConfig, rev: str,
) -> VehicleConfigRevision:
    """``rev`` may be a revision letter ('B') or a full WPN."""
    for r in config.revisions:
        if r.rev_letter == rev or r.wpn == rev:
            return r
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Config {config.wpn} has no revision {rev!r}",
    )


def _current_revision(config: VehicleConfig) -> Optional[VehicleConfigRevision]:
    if config.active_revision is not None:
        return config.active_revision
    return config.revisions[-1] if config.revisions else None


def _config_summary(config: VehicleConfig) -> ConfigSummary:
    rev = _current_revision(config)
    rollup = (rev.rollup or {}) if rev else {}
    return ConfigSummary(
        id=config.id,
        wpn=config.wpn,
        name=config.name,
        system_code=config.system_code,
        revision_count=len(config.revisions),
        current_rev=rev.rev_letter if rev else None,
        total_mass_kg=rollup.get("totalMass_kg"),
        component_count=len(rev.components or []) if rev else 0,
        astra_baseline_id=rev.astra_baseline_id if rev else None,
        updated_at=config.updated_at,
    )


def _rev_summary(rev: VehicleConfigRevision) -> ConfigRevisionSummary:
    return ConfigRevisionSummary(
        id=rev.id,
        wpn=rev.wpn,
        rev_letter=rev.rev_letter,
        description=rev.description,
        total_mass_kg=(rev.rollup or {}).get("totalMass_kg"),
        component_count=len(rev.components or []),
        astra_baseline_id=rev.astra_baseline_id,
        created_utc=rev.created_utc,
    )


def _config_detail(config: VehicleConfig) -> ConfigDetail:
    summary = _config_summary(config)
    return ConfigDetail(
        **summary.model_dump(),
        base_index=config.base_index,
        created_at=config.created_at,
        revisions=[_rev_summary(r) for r in config.revisions],
    )


def _rev_detail(
    config: VehicleConfig, rev: VehicleConfigRevision,
) -> ConfigRevisionDetail:
    return ConfigRevisionDetail(
        id=rev.id,
        wpn=rev.wpn,
        rev_letter=rev.rev_letter,
        config_wpn=config.wpn,
        config_name=config.name,
        description=rev.description,
        top_assembly_wpn=rev.top_assembly_wpn,
        frame_icd_id=rev.frame_icd_id,
        frame_icd_rev=rev.frame_icd_rev,
        astra_baseline_id=rev.astra_baseline_id,
        components=rev.components or [],
        aero_binding=rev.aero_binding,
        stage_map=rev.stage_map or [],
        rollup=rev.rollup or {},
        validation=rev.validation or {},
        notes=rev.notes,
        created_utc=rev.created_utc,
    )


def _validate_or_422(
    db: Session,
    body: ConfigCreate | ConfigRevisionCreate,
    user: User,
) -> Dict[str, Any]:
    try:
        return config_service.validate_and_build_revision_content(
            db,
            components=[c.model_dump() for c in body.components],
            aero_binding=(
                body.aero_binding.model_dump() if body.aero_binding else None
            ),
            stage_map=[s.model_dump() for s in body.stage_map],
            user_id=user.id,
        )
    except ConfigValidationError as exc:
        raise _422_validation(exc)


def _make_revision_row(
    config: VehicleConfig,
    entry: Dict[str, Any],
    content: Dict[str, Any],
    *,
    description: Optional[str],
    top_assembly_wpn: Optional[str],
    astra_baseline_id: Optional[int],
    notes: Optional[str],
    user_id: int,
) -> VehicleConfigRevision:
    return VehicleConfigRevision(
        config=config,
        wpn=entry["wpn"],
        rev_letter=_rev_letter(entry),
        description=description,
        top_assembly_wpn=top_assembly_wpn,
        frame_icd_id=content["frame_icd_id"],
        frame_icd_rev=content["frame_icd_rev"],
        astra_baseline_id=astra_baseline_id,
        components=content["components"],
        aero_binding=content["aero_binding"],
        stage_map=content["stage_map"],
        rollup=content["rollup"],
        validation=content["validation"],
        notes=notes,
        created_by_id=user_id,
    )


async def _record_use_best_effort(wpn: str, metadata: dict) -> None:
    """Annotate HAROLD's ledger post-commit. Advisory — a HAROLD
    hiccup here must not fail the already-persisted request."""
    try:
        await harold_naming.record_use(wpn, "config_revision", metadata)
    except HaroldError as exc:  # pragma: no cover - advisory path
        logger.warning("record_use(%s) failed post-persist: %s", wpn, exc)


async def _allocate_and_create_config(
    db: Session,
    *,
    name: str,
    content: Dict[str, Any],
    description: Optional[str],
    top_assembly_wpn: Optional[str],
    astra_baseline_id: Optional[int],
    notes: Optional[str],
    user: User,
    alloc_description: str,
) -> Tuple[VehicleConfig, VehicleConfigRevision]:
    """Shared create/clone path: HAROLD allocate_and_persist (gapless
    on failure) → new config identity + revision A."""
    holder: Dict[str, Any] = {}

    def _persist(session: Session, entry: Dict[str, Any]):
        cfg = VehicleConfig(
            wpn=_base_wpn(entry),
            base_index=entry.get("part_number_int"),
            system_code=entry.get("system_code") or CFG_CODE,
            name=name,
            created_by_id=user.id,
        )
        session.add(cfg)
        rev = _make_revision_row(
            cfg, entry, content,
            description=description,
            top_assembly_wpn=top_assembly_wpn,
            astra_baseline_id=astra_baseline_id,
            notes=notes,
            user_id=user.id,
        )
        session.add(rev)
        session.flush()
        cfg.active_revision_id = rev.id
        session.flush()
        holder["config"], holder["rev"] = cfg, rev
        return cfg, rev

    try:
        await harold_naming.allocate_and_persist(
            db, CFG_CODE, _persist,
            alloc_kwargs={
                "display_name": name,
                "description": alloc_description,
                "metadata": {"domain": "vehicle_config"},
            },
        )
    except HaroldUnavailableError as exc:
        raise _503(exc)
    except IntegrityError as exc:
        # WPN already released back to HAROLD by allocate_and_persist.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"config persistence conflict: {exc.orig}",
        )
    return holder["config"], holder["rev"]


# ══════════════════════════════════════════════════════════════
#  Reads
# ══════════════════════════════════════════════════════════════

@router.get("/configs", response_model=List[ConfigSummary])
async def list_configs(
    q: Optional[str] = Query(None, description="Search wpn / name"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Config list: wpn, name, revision count, current/active rev,
    total mass, component count, baseline id."""
    query = db.query(VehicleConfig).options(
        selectinload(VehicleConfig.revisions))
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_
        query = query.filter(or_(
            VehicleConfig.wpn.ilike(like),
            VehicleConfig.name.ilike(like),
        ))
    configs = query.order_by(VehicleConfig.wpn).offset(skip).limit(limit).all()
    return [_config_summary(c) for c in configs]


@router.get("/configs/{wpn}", response_model=ConfigDetail)
async def get_config(
    wpn: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _config_detail(_get_config_or_404(db, wpn))


@router.get("/configs/{wpn}/diff")
async def diff_config_revisions(
    wpn: str,
    from_rev: str = Query(..., alias="from"),
    to_rev: str = Query(..., alias="to"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Structured diff between two revisions: components added /
    removed / changed (rev or placement), aero-binding change,
    stage-map changes, roll-up delta."""
    config = _get_config_or_404(db, wpn)
    rev_a = _get_revision_or_404(config, from_rev)
    rev_b = _get_revision_or_404(config, to_rev)
    return config_service.diff_revisions(rev_a, rev_b)


@router.get(
    "/configs/{wpn}/revisions/{rev}",
    response_model=ConfigRevisionDetail,
)
async def get_config_revision(
    wpn: str,
    rev: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full resolved revision detail incl. the stored roll-up — the
    on-screen flight card."""
    config = _get_config_or_404(db, wpn)
    return _rev_detail(config, _get_revision_or_404(config, rev))


# ══════════════════════════════════════════════════════════════
#  Create — POST /engineering/configs
# ══════════════════════════════════════════════════════════════

@router.post(
    "/configs", response_model=ConfigCreateResponse, status_code=201,
)
async def create_config(
    body: ConfigCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Validate → roll up → allocate a CFG WPN via
    ``allocate_and_persist`` → config identity + revision A. An
    invalid config never reaches HAROLD; a failed persist releases
    the WPN (gapless)."""
    _require_req_eng_plus(current_user)
    content = _validate_or_422(db, body, current_user)

    config, rev = await _allocate_and_create_config(
        db,
        name=body.name,
        content=content,
        description=body.description,
        top_assembly_wpn=body.top_assembly_wpn,
        astra_baseline_id=body.astra_baseline_id,
        notes=body.notes,
        user=current_user,
        alloc_description=f"Vehicle configuration {body.name!r}",
    )

    await _record_use_best_effort(rev.wpn, {
        "vehicle_config_id": config.id,
        "revision_id": rev.id,
        "component_count": len(rev.components or []),
    })
    _audit(
        db, "vehicle_config.created", "vehicle_config", config.id,
        current_user.id,
        {"wpn": rev.wpn, "name": config.name},
        request=request,
    )
    return ConfigCreateResponse(
        config_id=config.id,
        config_wpn=config.wpn,
        wpn=rev.wpn,
        rev_letter=rev.rev_letter,
        name=config.name,
        rollup=rev.rollup,
        validation=rev.validation or {},
        is_new_config=True,
    )


# ══════════════════════════════════════════════════════════════
#  New revision — POST /engineering/configs/{wpn}/revisions
# ══════════════════════════════════════════════════════════════

@router.post(
    "/configs/{wpn}/revisions",
    response_model=ConfigCreateResponse,
    status_code=201,
)
async def create_config_revision(
    wpn: str,
    body: ConfigRevisionCreate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """New IMMUTABLE revision: HAROLD ``issue_revision`` on the latest
    revision's full WPN (index stable, next letter). Persistence
    failure releases the issued WPN back to HAROLD (manual mirror of
    ``allocate_and_persist`` — same as the aero router)."""
    _require_req_eng_plus(current_user)
    config = _get_config_or_404(db, wpn)
    latest = config.revisions[-1] if config.revisions else None
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Config {config.wpn} has no revisions to revise",
        )

    content = _validate_or_422(db, body, current_user)

    try:
        entry = await harold_naming.issue_revision(
            latest.wpn,
            display_name=config.name,
            origin_record_id=str(config.id),
            metadata={"domain": "vehicle_config"},
        )
    except HaroldUnavailableError as exc:
        raise _503(exc)

    try:
        rev = _make_revision_row(
            config, entry, content,
            description=body.description,
            top_assembly_wpn=body.top_assembly_wpn,
            astra_baseline_id=body.astra_baseline_id,
            notes=body.notes,
            user_id=current_user.id,
        )
        db.add(rev)
        db.flush()
        config.active_revision_id = rev.id
        db.commit()
    except Exception as persist_exc:
        db.rollback()
        logger.warning(
            "config revision persistence failed for %s (%s); releasing",
            entry.get("wpn"), persist_exc,
        )
        try:
            await harold_naming.release(
                entry["wpn"],
                reason=f"persistence failed: {persist_exc!s}",
            )
        except HaroldError as release_exc:
            logger.critical(
                "ORPHAN WPN %s: revision persistence failed (%s) AND "
                "release failed (%s) — manual reconciliation required.",
                entry.get("wpn"), persist_exc, release_exc,
            )
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"orphan WPN {entry.get('wpn')}: see server logs",
            )
        if isinstance(persist_exc, IntegrityError):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"config revision persistence conflict: "
                       f"{persist_exc.orig}",
            )
        raise

    await _record_use_best_effort(rev.wpn, {
        "vehicle_config_id": config.id,
        "revision_id": rev.id,
        "component_count": len(rev.components or []),
    })
    _audit(
        db, "vehicle_config.revision_created", "vehicle_config_revision",
        rev.id, current_user.id,
        {"wpn": rev.wpn, "config_wpn": config.wpn,
         "rev_letter": rev.rev_letter},
        request=request,
    )
    return ConfigCreateResponse(
        config_id=config.id,
        config_wpn=config.wpn,
        wpn=rev.wpn,
        rev_letter=rev.rev_letter,
        name=config.name,
        rollup=rev.rollup,
        validation=rev.validation or {},
        is_new_config=False,
    )


# ══════════════════════════════════════════════════════════════
#  Clone — POST /engineering/configs/{wpn}:clone
# ══════════════════════════════════════════════════════════════

@router.post(
    "/configs/{wpn}:clone",
    response_model=ConfigCreateResponse,
    status_code=201,
)
async def clone_config(
    wpn: str,
    body: ConfigCloneRequest,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Clone the latest revision's content into a NEW config identity
    (fresh CFG WPN via ``allocate_and_persist``). The content was
    validated when the source revision persisted and is copied
    verbatim (incl. its frame stamp and roll-up)."""
    _require_req_eng_plus(current_user)
    source = _get_config_or_404(db, wpn)
    latest = source.revisions[-1] if source.revisions else None
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Config {source.wpn} has no revisions to clone",
        )

    content = {
        "components": latest.components,
        "aero_binding": latest.aero_binding,
        "stage_map": latest.stage_map,
        "rollup": latest.rollup,
        "validation": latest.validation or {},
        "frame_icd_id": latest.frame_icd_id,
        "frame_icd_rev": latest.frame_icd_rev,
    }
    config, rev = await _allocate_and_create_config(
        db,
        name=body.name,
        content=content,
        description=latest.description,
        top_assembly_wpn=latest.top_assembly_wpn,
        astra_baseline_id=latest.astra_baseline_id,
        notes=latest.notes,
        user=current_user,
        alloc_description=(
            f"Vehicle configuration {body.name!r} "
            f"(cloned from {latest.wpn})"
        ),
    )

    await _record_use_best_effort(rev.wpn, {
        "vehicle_config_id": config.id,
        "revision_id": rev.id,
        "cloned_from": latest.wpn,
    })
    _audit(
        db, "vehicle_config.cloned", "vehicle_config", config.id,
        current_user.id,
        {"wpn": rev.wpn, "name": config.name, "cloned_from": latest.wpn},
        request=request,
    )
    return ConfigCreateResponse(
        config_id=config.id,
        config_wpn=config.wpn,
        wpn=rev.wpn,
        rev_letter=rev.rev_letter,
        name=config.name,
        rollup=rev.rollup,
        validation=rev.validation or {},
        is_new_config=True,
    )


# ══════════════════════════════════════════════════════════════
#  Active revision
# ══════════════════════════════════════════════════════════════

@router.put("/configs/{wpn}/active-revision", response_model=ConfigDetail)
async def set_active_revision(
    wpn: str,
    data: ConfigActiveRevisionUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_req_eng_plus(current_user)
    config = _get_config_or_404(db, wpn)
    revision = _get_revision_or_404(config, data.rev_letter)
    config.active_revision_id = revision.id
    db.commit()
    db.refresh(config)
    _audit(
        db, "vehicle_config.active_revision_changed", "vehicle_config",
        config.id, current_user.id,
        {"wpn": config.wpn, "rev_letter": revision.rev_letter},
        request=request,
    )
    return _config_detail(config)


# ══════════════════════════════════════════════════════════════
#  §9 — CITADEL bundle export
# ══════════════════════════════════════════════════════════════

def _export_response(
    export: ConfigBundleExport, *, reused: bool, warnings: List[str],
) -> BundleExportResponse:
    return BundleExportResponse(
        id=export.id,
        config_wpn=export.config_wpn,
        rev_letter=export.rev_letter,
        bundle_hash=export.bundle_hash,
        bundle_dirname=export.bundle_dirname,
        artifact_count=export.artifact_count,
        created_utc=export.created_utc,
        manifest=export.manifest,
        reused=reused,
        warnings=warnings,
    )


@router.post(
    "/configs/{wpn}/{rev}:exportBundle",
    response_model=BundleExportResponse,
    status_code=201,
)
async def export_config_bundle(
    wpn: str,
    rev: str,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export the revision as a ``citadel-config-bundle/1.0``
    directory + zip. Deterministic: re-export of the same revision
    yields the SAME ``bundle_hash`` (volatile manifest fields are
    normalized out of the hash) and idempotently reuses the recorded
    export row."""
    _require_req_eng_plus(current_user)
    config = _get_config_or_404(db, wpn)
    revision = _get_revision_or_404(config, rev)
    try:
        export, warnings, reused = await bundle_export_svc.export_bundle(
            db, config, revision, current_user,
        )
    except BundleExportError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=exc.detail(),
        )
    _audit(
        db, "vehicle_config.bundle_exported", "config_bundle_export",
        export.id, current_user.id,
        {"config_wpn": export.config_wpn, "rev_letter": export.rev_letter,
         "bundle_hash": export.bundle_hash, "reused": reused},
        request=request,
    )
    return _export_response(export, reused=reused, warnings=warnings)


def _get_export_or_404(
    db: Session,
    config: VehicleConfig,
    revision: VehicleConfigRevision,
    bundle_hash: str,
) -> ConfigBundleExport:
    export = (
        db.query(ConfigBundleExport)
        .filter(
            ConfigBundleExport.config_wpn == config.wpn,
            ConfigBundleExport.rev_letter == revision.rev_letter,
            ConfigBundleExport.bundle_hash == bundle_hash,
        )
        .first()
    )
    if export is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No bundle export {bundle_hash!r} for "
                f"{config.wpn} rev {revision.rev_letter}"
            ),
        )
    return export


@router.get(
    "/configs/{wpn}/{rev}/bundles",
    response_model=List[BundleExportSummary],
)
async def list_config_bundles(
    wpn: str,
    rev: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Export history for a config revision — retrievable WITHOUT
    re-export."""
    config = _get_config_or_404(db, wpn)
    revision = _get_revision_or_404(config, rev)
    exports = (
        db.query(ConfigBundleExport)
        .filter(
            ConfigBundleExport.vehicle_config_revision_id == revision.id,
        )
        .order_by(ConfigBundleExport.id)
        .all()
    )
    return [BundleExportSummary.model_validate(e) for e in exports]


@router.get("/configs/{wpn}/{rev}/bundles/{bundle_hash}/manifest")
async def get_config_bundle_manifest(
    wpn: str,
    rev: str,
    bundle_hash: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The stored manifest JSON of a historical export — served from
    the DB row, no disk access, no re-export."""
    config = _get_config_or_404(db, wpn)
    revision = _get_revision_or_404(config, rev)
    export = _get_export_or_404(db, config, revision, bundle_hash)
    return JSONResponse(content=export.manifest)


@router.get("/configs/{wpn}/{rev}/bundles/{bundle_hash}/download")
async def download_config_bundle(
    wpn: str,
    rev: str,
    bundle_hash: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The bundle zip of a historical export (FileResponse)."""
    config = _get_config_or_404(db, wpn)
    revision = _get_revision_or_404(config, rev)
    export = _get_export_or_404(db, config, revision, bundle_hash)
    zip_path = Path(export.zip_path)
    if not zip_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Bundle zip missing on disk ({export.zip_path}) — "
                "re-export to regenerate"
            ),
        )
    return FileResponse(
        path=str(zip_path),
        media_type="application/zip",
        filename=f"{export.bundle_dirname}.zip",
    )
