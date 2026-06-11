"""
ASTRA — Engineering hub: Aero Decks router (spec §6)
====================================================
Mounts at ``/api/v1/engineering/aero``. HAROLD-named (system code
``AER``) aero-deck identities with immutable revisions and the
drag-drop "upload it and it's named + ingested automatically" flow.

Router prefix note: FastAPI route paths must start with "/", so the
router uses ``prefix="/engineering"`` with every path under ``/aero``
— this is what lets the Google-style custom verb
``/engineering/aero:ingestSource`` (colon, no slash) exist alongside
``/engineering/aero/{wpn}``.

Naming contract (spec §2 — strict):
  * EVERY WPN comes from HAROLD verbatim via
    ``app.services.harold_naming``. Nothing here computes an index.
  * create path uses ``allocate_and_persist`` so a failed local
    persist releases the WPN back to HAROLD (gapless sequence).
  * revision path uses ``issue_revision`` + manual release-on-failure
    mirroring the same guarantee.
  * HAROLD down / disabled → 503, no fallback.
  * The uploader does NOT name the deck — HAROLD's filename precheck
    decides the canonical name; the optional ``name`` form field is
    only a fallback hint when HAROLD's verdict carries no name.

Auth follows the catalog router: read = any authenticated user,
write = admin / project_manager / requirements_engineer.

Deviation (documented): aero decks get NO ``catalog_parts`` row —
they are engineering data products, not procurable parts.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

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
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models import User, UserRole
from app.models.engineering_aero import AeroDeck, AeroDeckRevision
from app.schemas.engineering_aero import (
    AeroActiveRevisionUpdate,
    AeroDeckDetail,
    AeroDeckRevisionDetail,
    AeroDeckRevisionSummary,
    AeroDeckSummary,
    AeroEnvelope,
    AeroIngestResponse,
    AeroPreviewResponse,
)
from app.services import harold_naming
from app.services.auth import get_current_user
from app.services.engineering import aero_deck as deck_svc
from app.services.engineering.aero_deck import (
    AeroDeckError,
    ParsedSource,
)
from app.services.harold_naming import (
    AER_CODE,
    HaroldError,
    HaroldUnavailableError,
)

# Optional audit (same pattern as the catalog router).
try:
    from app.services.audit_service import record_event as _audit
except ImportError:  # pragma: no cover - dev test fallback
    def _audit(*a, **kw):
        pass

logger = logging.getLogger("astra.engineering.aero")

router = APIRouter(prefix="/engineering", tags=["Engineering — Aero"])


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
            "Insufficient permissions: aero-deck write requires admin, "
            "project_manager, or requirements_engineer role"
        ),
    )


def _422(exc: AeroDeckError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        detail=exc.detail(),
    )


def _503(exc: HaroldUnavailableError) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"HAROLD naming authority unavailable: {exc}",
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


def _get_deck_or_404(db: Session, wpn: str) -> AeroDeck:
    """Resolve a deck by base WPN, by any revision's full WPN, or by
    the base obtained by stripping a trailing revision token."""
    deck = db.query(AeroDeck).filter(AeroDeck.wpn == wpn).first()
    if deck is not None:
        return deck
    rev = (
        db.query(AeroDeckRevision)
        .filter(AeroDeckRevision.wpn == wpn)
        .first()
    )
    if rev is not None:
        return rev.deck_parent
    if "-" in wpn:
        base = wpn.rsplit("-", 1)[0]
        deck = db.query(AeroDeck).filter(AeroDeck.wpn == base).first()
        if deck is not None:
            return deck
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Aero deck {wpn!r} not found",
    )


def _current_revision(deck: AeroDeck) -> Optional[AeroDeckRevision]:
    if deck.active_revision is not None:
        return deck.active_revision
    return deck.revisions[-1] if deck.revisions else None


def _deck_summary(deck: AeroDeck) -> AeroDeckSummary:
    rev = _current_revision(deck)
    return AeroDeckSummary(
        id=deck.id,
        wpn=deck.wpn,
        name=deck.name,
        oml_wpn=deck.oml_wpn,
        system_code=deck.system_code,
        current_rev=rev.rev_letter if rev else None,
        revision_count=len(deck.revisions),
        mach_min=rev.mach_min if rev else None,
        mach_max=rev.mach_max if rev else None,
        alpha_min_deg=rev.alpha_min_deg if rev else None,
        alpha_max_deg=rev.alpha_max_deg if rev else None,
        updated_at=deck.updated_at,
    )


def _deck_detail(deck: AeroDeck) -> AeroDeckDetail:
    summary = _deck_summary(deck)
    return AeroDeckDetail(
        **summary.model_dump(),
        base_index=deck.base_index,
        created_at=deck.created_at,
        revisions=[
            AeroDeckRevisionSummary.model_validate(r)
            for r in deck.revisions
        ],
    )


def _get_revision_or_404(
    db: Session, deck: AeroDeck, rev: str,
) -> AeroDeckRevision:
    """``rev`` may be a revision letter ("B") or a full WPN."""
    for r in deck.revisions:
        if r.rev_letter == rev or r.wpn == rev:
            return r
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Aero deck {deck.wpn} has no revision {rev!r}",
    )


async def _read_and_parse_uploads(
    files: List[UploadFile],
) -> Tuple[List[ParsedSource], List[dict], List[str]]:
    """Read + sha256 + parse every uploaded source file.
    Returns (parsed sources, provenance sourceFiles entries, raw texts).
    """
    if not files:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="at least one source file is required",
        )
    parsed: List[ParsedSource] = []
    prov: List[dict] = []
    raw_texts: List[str] = []
    for f in files:
        content = await f.read()
        filename = f.filename or "upload.csv"
        sha = hashlib.sha256(content).hexdigest()
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{filename}: not valid UTF-8 text ({exc})",
            )
        try:
            parsed.append(deck_svc.parse_source(filename, text))
        except AeroDeckError as exc:
            raise _422(exc)
        prov.append({"filename": filename, "sha256": sha})
        raw_texts.append(text)
    return parsed, prov, raw_texts


def _parse_ref_point_form(value: Optional[str]) -> Optional[List[float]]:
    if value is None or not value.strip():
        return None
    try:
        return deck_svc._parse_ref_point(value)
    except AeroDeckError as exc:
        raise _422(exc)


def _build_deck_or_422(
    parsed: List[ParsedSource],
    *,
    sref_m2: Optional[float],
    lref_m: Optional[float],
    ref_point: Optional[List[float]],
    oml_wpn: Optional[str],
    author: Optional[str],
    source_files: List[dict],
) -> deck_svc.BuiltDeck:
    try:
        return deck_svc.merge_decks(
            parsed,
            sref_m2=sref_m2,
            lref_m=lref_m,
            ref_point_m_b=ref_point,
            oml_wpn=oml_wpn,
            author=author,
            ingest_utc=datetime.now(timezone.utc).isoformat(),
            source_files=source_files,
        )
    except AeroDeckError as exc:
        raise _422(exc)


def _finalize_deck(built: deck_svc.BuiltDeck, wpn: str) -> Tuple[dict, str]:
    """Stamp the HAROLD-issued WPN into provenance and hash the
    canonical JSON. Called only AFTER HAROLD has issued the WPN."""
    deck = built.deck
    deck["provenance"]["wpn"] = wpn
    return deck, deck_svc.deck_sha256(deck)


def _make_revision_row(
    deck_row: AeroDeck,
    entry: Dict[str, Any],
    built: deck_svc.BuiltDeck,
    *,
    prov: List[dict],
    raw_texts: List[str],
    notes: Optional[str],
    user_id: Optional[int],
) -> AeroDeckRevision:
    deck_json, sha = _finalize_deck(built, entry["wpn"])
    env = deck_json["validityEnvelope"]
    return AeroDeckRevision(
        deck_parent=deck_row,
        wpn=entry["wpn"],
        rev_letter=_rev_letter(entry),
        source_filenames=[p["filename"] for p in prov],
        source_sha256s=[p["sha256"] for p in prov],
        source_text=json.dumps(raw_texts),
        deck=deck_json,
        deck_sha256=sha,
        mach_min=env["machRange"][0],
        mach_max=env["machRange"][1],
        alpha_min_deg=env["alphaRange_deg"][0],
        alpha_max_deg=env["alphaRange_deg"][1],
        sref_m2=deck_json["Sref_m2"],
        lref_m=deck_json["Lref_m"],
        defaulted_fields=built.defaulted_fields,
        warnings=built.warnings,
        notes=notes,
        created_by_id=user_id,
    )


def _ingest_response(
    deck_row: AeroDeck,
    rev_row: AeroDeckRevision,
    built: deck_svc.BuiltDeck,
    *,
    is_new_deck: bool,
) -> AeroIngestResponse:
    return AeroIngestResponse(
        deck_id=deck_row.id,
        deck_wpn=deck_row.wpn,
        wpn=rev_row.wpn,
        rev_letter=rev_row.rev_letter,
        name=deck_row.name,
        deck_sha256=rev_row.deck_sha256,
        is_new_deck=is_new_deck,
        envelope=AeroEnvelope(
            mach_min=rev_row.mach_min,
            mach_max=rev_row.mach_max,
            alpha_min_deg=rev_row.alpha_min_deg,
            alpha_max_deg=rev_row.alpha_max_deg,
        ),
        warnings=built.warnings,
        defaulted_fields=built.defaulted_fields,
    )


async def _record_use_best_effort(wpn: str, metadata: dict) -> None:
    """Annotate HAROLD's ledger. The local row is already committed by
    the time this runs, so a HAROLD hiccup here must not fail the
    request — log and move on (the ledger annotation is advisory)."""
    try:
        await harold_naming.record_use(wpn, "aero_revision", metadata)
    except HaroldError as exc:  # pragma: no cover - advisory path
        logger.warning("record_use(%s) failed post-persist: %s", wpn, exc)


# ══════════════════════════════════════════════════════════════
#  Reads
# ══════════════════════════════════════════════════════════════

@router.get("/aero", response_model=List[AeroDeckSummary])
async def list_aero_decks(
    q: Optional[str] = Query(None, description="Search wpn / name / oml_wpn"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Deck list: wpn, name, oml_wpn, mach/alpha envelope, current
    revision, updated timestamp."""
    query = db.query(AeroDeck).options(selectinload(AeroDeck.revisions))
    if q:
        like = f"%{q}%"
        from sqlalchemy import or_
        query = query.filter(or_(
            AeroDeck.wpn.ilike(like),
            AeroDeck.name.ilike(like),
            AeroDeck.oml_wpn.ilike(like),
        ))
    decks = query.order_by(AeroDeck.wpn).offset(skip).limit(limit).all()
    return [_deck_summary(d) for d in decks]


@router.get("/aero/{wpn}", response_model=AeroDeckDetail)
async def get_aero_deck(
    wpn: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _deck_detail(_get_deck_or_404(db, wpn))


@router.get(
    "/aero/{wpn}/revisions/{rev}",
    response_model=AeroDeckRevisionDetail,
)
async def get_aero_deck_revision(
    wpn: str,
    rev: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    deck = _get_deck_or_404(db, wpn)
    return AeroDeckRevisionDetail.model_validate(
        _get_revision_or_404(db, deck, rev)
    )


@router.get("/aero/{wpn}/revisions/{rev}/artifact")
async def get_aero_deck_artifact(
    wpn: str,
    rev: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """The normalized deck JSON — this IS the ``*.aero.json``
    artifact, served verbatim from the immutable revision row."""
    deck = _get_deck_or_404(db, wpn)
    revision = _get_revision_or_404(db, deck, rev)
    return JSONResponse(
        content=revision.deck,
        headers={
            "Content-Disposition":
                f'attachment; filename="{revision.wpn}.aero.json"',
        },
    )


@router.get("/aero/{wpn}/preview", response_model=AeroPreviewResponse)
async def preview_aero_deck(
    wpn: str,
    mach: float = Query(...),
    alpha: float = Query(..., description="alpha in degrees"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Interpolated coefficient values at (mach, alpha) on the
    beta≈0 / delta≈0 slice of the current revision — UI preview."""
    deck = _get_deck_or_404(db, wpn)
    revision = _current_revision(deck)
    if revision is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Aero deck {deck.wpn} has no revisions",
        )
    try:
        values = deck_svc.interpolate_point(revision.deck, mach, alpha)
    except AeroDeckError as exc:
        raise _422(exc)
    bp = revision.deck["breakpoints"]
    return AeroPreviewResponse(
        wpn=deck.wpn,
        rev_letter=revision.rev_letter,
        mach=mach,
        alpha_deg=alpha,
        beta_deg=min(bp["beta_deg"], key=abs),
        delta_deg=min(bp["delta_deg"], key=abs),
        values=values,
    )


# ══════════════════════════════════════════════════════════════
#  Ingest (auto-name flow) — POST /engineering/aero:ingestSource
# ══════════════════════════════════════════════════════════════

@router.post(
    "/aero:ingestSource",
    response_model=AeroIngestResponse,
    status_code=201,
)
async def ingest_aero_source(
    files: List[UploadFile] = File(...),
    name: Optional[str] = Form(None),
    oml_wpn: Optional[str] = Form(None),
    sref_m2: Optional[float] = Form(None),
    lref_m: Optional[float] = Form(None),
    ref_point_m_b: Optional[str] = Form(
        None, description="3 floats, comma/space separated",
    ),
    notes: Optional[str] = Form(None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Drag-drop ingest: upload 1..N coefficient CSVs and the deck is
    named + ingested automatically. The uploader does NOT name it —
    HAROLD's filename precheck decides the canonical name; if the
    canonical name / lineage matches an existing deck this lands as
    that deck's next revision, otherwise HAROLD issues a fresh WPN via
    ``allocate_and_persist`` (which releases the WPN if local
    persistence fails — the AER sequence stays gapless)."""
    _require_req_eng_plus(current_user)

    parsed, prov, raw_texts = await _read_and_parse_uploads(files)
    ref_point = _parse_ref_point_form(ref_point_m_b)

    # ── HAROLD decides the canonical name ──────────────────────────
    first_filename = prov[0]["filename"]
    try:
        verdict = await harold_naming.precheck_filename(
            first_filename, AER_CODE,
        )
    except HaroldUnavailableError as exc:
        raise _503(exc)

    # HAROLD's precheck verdict carries ``iteration_stem`` (its parse
    # of the filename); ``canonical_name``/``canonicalName`` are kept
    # first for forward compatibility — same chain as the motors
    # router's ``_canonical_name_from_precheck``. The form ``name`` is
    # only a fallback hint when HAROLD's verdict carries no name.
    canonical_name = (
        verdict.get("canonical_name")
        or verdict.get("canonicalName")
        or verdict.get("iteration_stem")
        or name
        or Path(first_filename).stem
    )

    # ── lineage match → revision of the existing deck ──────────────
    # (HAROLD's precheck returns no WPN key — lineage matching is by
    # canonical name only, mirroring the motors router.)
    existing: Optional[AeroDeck] = None
    if canonical_name:
        existing = db.query(AeroDeck).filter(
            AeroDeck.name == canonical_name).first()

    if existing is not None:
        rev_row, built = await _create_revision(
            db, existing, parsed, prov, raw_texts,
            sref_m2=sref_m2, lref_m=lref_m, ref_point=ref_point,
            oml_wpn=oml_wpn, notes=notes, user=current_user,
            request=request,
        )
        return _ingest_response(existing, rev_row, built,
                                is_new_deck=False)

    # ── new identity: allocate_and_persist (gapless on failure) ────
    built = _build_deck_or_422(
        parsed,
        sref_m2=sref_m2, lref_m=lref_m, ref_point=ref_point,
        oml_wpn=oml_wpn, author=current_user.username,
        source_files=prov,
    )

    holder: Dict[str, Any] = {}

    def _persist(session: Session, entry: Dict[str, Any]):
        deck_row = AeroDeck(
            wpn=_base_wpn(entry),
            base_index=entry.get("part_number_int"),
            system_code=entry.get("system_code") or AER_CODE,
            name=canonical_name,
            oml_wpn=built.deck.get("omlWpn"),
            created_by_id=current_user.id,
        )
        session.add(deck_row)
        rev_row = _make_revision_row(
            deck_row, entry, built,
            prov=prov, raw_texts=raw_texts, notes=notes,
            user_id=current_user.id,
        )
        session.add(rev_row)
        session.flush()
        deck_row.active_revision_id = rev_row.id
        session.flush()
        holder["deck"], holder["rev"] = deck_row, rev_row
        return deck_row, rev_row

    try:
        entry, _ = await harold_naming.allocate_and_persist(
            db, AER_CODE, _persist,
            alloc_kwargs={
                "display_name": canonical_name,
                "description": f"Aero deck ingested from {first_filename}",
                "metadata": {"domain": "aero_deck"},
            },
        )
    except HaroldUnavailableError as exc:
        raise _503(exc)
    except IntegrityError as exc:
        # WPN already released back to HAROLD by allocate_and_persist.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"aero deck persistence conflict: {exc.orig}",
        )

    deck_row, rev_row = holder["deck"], holder["rev"]

    await _record_use_best_effort(rev_row.wpn, {
        "aero_deck_id": deck_row.id,
        "revision_id": rev_row.id,
        "deck_sha256": rev_row.deck_sha256,
        "source_filenames": [p["filename"] for p in prov],
    })

    _audit(
        db, "aero_deck.created", "aero_deck", deck_row.id,
        current_user.id,
        {"wpn": rev_row.wpn, "name": deck_row.name,
         "sources": [p["filename"] for p in prov]},
        request=request,
    )
    return _ingest_response(deck_row, rev_row, built, is_new_deck=True)


# ══════════════════════════════════════════════════════════════
#  New revision — POST /engineering/aero/{wpn}/revisions:from-source
# ══════════════════════════════════════════════════════════════

async def _create_revision(
    db: Session,
    deck: AeroDeck,
    parsed: List[ParsedSource],
    prov: List[dict],
    raw_texts: List[str],
    *,
    sref_m2: Optional[float],
    lref_m: Optional[float],
    ref_point: Optional[List[float]],
    oml_wpn: Optional[str],
    notes: Optional[str],
    user: User,
    request: Optional[Request],
) -> Tuple[AeroDeckRevision, deck_svc.BuiltDeck]:
    """Shared revision path: HAROLD ``issue_revision`` on the latest
    revision's full WPN (same index, next letter), persist the new
    immutable row, release the WPN on persistence failure."""
    latest = deck.revisions[-1] if deck.revisions else None
    if latest is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Aero deck {deck.wpn} has no revisions to revise",
        )

    # Sref/Lref may be inherited from the previous revision for a
    # follow-on revision (recorded in defaulted_fields).
    defaulted_extra: List[str] = []
    eff_sref, eff_lref = sref_m2, lref_m
    have_meta_sref = any("Sref_m2" in p.metadata for p in parsed)
    have_meta_lref = any("Lref_m" in p.metadata for p in parsed)
    if eff_sref is None and not have_meta_sref and latest.sref_m2 is not None:
        eff_sref = latest.sref_m2
        defaulted_extra.append("Sref_m2")
    if eff_lref is None and not have_meta_lref and latest.lref_m is not None:
        eff_lref = latest.lref_m
        defaulted_extra.append("Lref_m")

    built = _build_deck_or_422(
        parsed,
        sref_m2=eff_sref, lref_m=eff_lref, ref_point=ref_point,
        oml_wpn=oml_wpn if oml_wpn is not None else deck.oml_wpn,
        author=user.username, source_files=prov,
    )
    built.defaulted_fields.extend(defaulted_extra)

    try:
        entry = await harold_naming.issue_revision(
            latest.wpn,
            display_name=deck.name,
            origin_record_id=str(deck.id),
            metadata={"domain": "aero_deck"},
        )
    except HaroldUnavailableError as exc:
        raise _503(exc)

    try:
        rev_row = _make_revision_row(
            deck, entry, built,
            prov=prov, raw_texts=raw_texts, notes=notes,
            user_id=user.id,
        )
        db.add(rev_row)
        db.flush()
        deck.active_revision_id = rev_row.id
        if oml_wpn is not None:
            deck.oml_wpn = oml_wpn
        db.commit()
    except Exception as persist_exc:
        db.rollback()
        logger.warning(
            "aero revision persistence failed for %s (%s); releasing",
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
                detail=f"aero revision persistence conflict: "
                       f"{persist_exc.orig}",
            )
        raise

    await _record_use_best_effort(rev_row.wpn, {
        "aero_deck_id": deck.id,
        "revision_id": rev_row.id,
        "deck_sha256": rev_row.deck_sha256,
        "source_filenames": [p["filename"] for p in prov],
    })

    _audit(
        db, "aero_deck.revision_created", "aero_deck_revision",
        rev_row.id, user.id,
        {"wpn": rev_row.wpn, "deck_wpn": deck.wpn,
         "rev_letter": rev_row.rev_letter},
        request=request,
    )
    return rev_row, built


@router.post(
    "/aero/{wpn}/revisions:from-source",
    response_model=AeroIngestResponse,
    status_code=201,
)
async def create_aero_revision_from_source(
    wpn: str,
    files: List[UploadFile] = File(...),
    oml_wpn: Optional[str] = Form(None),
    sref_m2: Optional[float] = Form(None),
    lref_m: Optional[float] = Form(None),
    ref_point_m_b: Optional[str] = Form(None),
    notes: Optional[str] = Form(None),
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Explicit new revision of an existing deck from fresh source
    files. HAROLD keeps the index and bumps the letter."""
    _require_req_eng_plus(current_user)
    deck = _get_deck_or_404(db, wpn)
    parsed, prov, raw_texts = await _read_and_parse_uploads(files)
    ref_point = _parse_ref_point_form(ref_point_m_b)
    rev_row, built = await _create_revision(
        db, deck, parsed, prov, raw_texts,
        sref_m2=sref_m2, lref_m=lref_m, ref_point=ref_point,
        oml_wpn=oml_wpn, notes=notes, user=current_user,
        request=request,
    )
    return _ingest_response(deck, rev_row, built, is_new_deck=False)


# ══════════════════════════════════════════════════════════════
#  Active revision
# ══════════════════════════════════════════════════════════════

@router.put("/aero/{wpn}/active-revision", response_model=AeroDeckDetail)
async def set_active_revision(
    wpn: str,
    data: AeroActiveRevisionUpdate,
    request: Request = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _require_req_eng_plus(current_user)
    deck = _get_deck_or_404(db, wpn)
    revision = _get_revision_or_404(db, deck, data.rev_letter)
    deck.active_revision_id = revision.id
    db.commit()
    db.refresh(deck)
    _audit(
        db, "aero_deck.active_revision_changed", "aero_deck", deck.id,
        current_user.id,
        {"wpn": deck.wpn, "rev_letter": revision.rev_letter},
        request=request,
    )
    return _deck_detail(deck)
