"""
ASTRA — CITADEL config-bundle export (spec §9)
===============================================
File: backend/app/services/engineering/bundle_export.py   ← NEW

Renders an immutable config revision into a ``citadel-config-bundle/
1.0`` directory + zip and records a ``config_bundle_exports`` row.

Artifacts (content-addressed ``artifacts/<sha256>.<suffix>``):
  * per component — the part's §6 CADPORT YAML pass-through bytes,
    read back verbatim from its SupplierDocument file
    (``type=mass_props_yaml``, ``sourceSystem=CADPORT``);
  * aero — ``canonical_json`` of the bound deck revision's deck JSON
    (``type=aero_deck``, ``sourceSystem=AstraAero``);
  * per stage — ``canonical_json`` of the motor revision's artifact
    (``type=motor_curve``, ``sourceSystem=AstraMotor``).
Identical sha256s are stored once (dedup).

Determinism (load-bearing, spec §1)
-----------------------------------
``bundleHash`` = sha256 of ``canonical_json`` of the manifest with
volatile fields NORMALIZED: ``bundle.id`` / ``bundle.createdUtc`` /
``bundle.createdBy`` / ``bundle.bundleHash`` nulled AND the whole
``provenance`` block nulled. The hash therefore covers config
identity, frame, massProperties, components, aero, propulsion and
dependencies — re-export of the same revision yields the SAME
``bundleHash`` even though ``createdUtc`` (and the provenance block)
differ. See :func:`compute_deterministic_bundle_hash`. (This module
deliberately does NOT touch ``bundle_schema.compute_bundle_hash``,
which only nulls ``bundle.bundleHash`` — that helper stays the
shared verification primitive; the *deterministic* normalization
lives here.)

Zip stability: entries are written in sorted arcname order with fixed
(1980, 1, 1) timestamps and the manifest serialized as canonical JSON,
so re-rendering the same revision produces byte-stable zip content.

Idempotency: ``config_bundle_exports`` is UNIQUE(config_wpn,
rev_letter, bundle_hash) — re-exporting identical content returns the
existing row (files re-rendered if missing on disk) instead of
inserting a duplicate, keeping lookup-by-hash unambiguous for the
retrieval endpoints.

Exports root: ``$CITADEL_BUNDLE_DIR`` if set, else
``$UPLOAD_DIR/citadel_bundles`` (UPLOAD_DIR defaults to
``/tmp/astra_uploads`` — same env-driven convention as the other
upload roots).
"""

from __future__ import annotations

import copy
import logging
import os
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models import User
from app.models.catalog import CatalogPart
from app.models.engineering_config import (
    ConfigBundleExport,
    VehicleConfig,
    VehicleConfigRevision,
)
from app.models.engineering_frame import FrameIcd, FrameIcdRevision
from app.services import harold_naming
from app.services.engineering import config_service
from app.services.engineering.bundle_schema import (
    AeroBlock,
    ArtifactRef,
    AstraProvenance,
    BundleBlock,
    ComponentEntry,
    ConfigBlock,
    Dependency,
    FrameBlock,
    Manifest,
    MassPropertiesBlock,
    PropulsionStage,
    ProvenanceBlock,
    ValidityEnvelope,
    artifact_filename,
    bundle_dirname,
    canonical_json,
    manifest_to_dict,
    sha256_bytes,
)
from app.services.engineering.config_rollup import part_inertia_matrix

logger = logging.getLogger("astra.engineering.bundle_export")


class BundleExportError(Exception):
    """Fatal export problem (caller surfaces 422)."""

    def __init__(self, message: str, **context: Any):
        self.message = message
        self.context = context
        super().__init__(message)

    def detail(self) -> Dict[str, Any]:
        return {"message": self.message, **self.context}


# ── Exports root ────────────────────────────────────────────────────


def exports_root() -> Path:
    """Settings-driven exports root, resolved at call time so tests
    can point it at a tmp dir via the environment."""
    explicit = os.environ.get("CITADEL_BUNDLE_DIR")
    if explicit:
        return Path(explicit)
    uploads = os.environ.get("UPLOAD_DIR", "/tmp/astra_uploads")
    return Path(uploads) / "citadel_bundles"


# ── Determinism ─────────────────────────────────────────────────────

#: ``bundle.*`` fields nulled for the deterministic hash.
_VOLATILE_BUNDLE_FIELDS = ("id", "createdUtc", "createdBy", "bundleHash")


def compute_deterministic_bundle_hash(manifest_dict: Dict[str, Any]) -> str:
    """sha256 of ``canonical_json`` of *manifest_dict* with the
    volatile fields normalized:

      * ``bundle.id`` / ``bundle.createdUtc`` / ``bundle.createdBy`` /
        ``bundle.bundleHash`` → null
      * ``provenance`` (entire block) → null

    The hash covers: config identity, frame, massProperties,
    components, aero, propulsion, dependencies. Re-export of the same
    revision yields the SAME bundleHash even though createdUtc / the
    provenance block differ. Input is not mutated.
    """
    scrubbed = copy.deepcopy(manifest_dict)
    bundle = scrubbed.get("bundle")
    if isinstance(bundle, dict):
        for fld in _VOLATILE_BUNDLE_FIELDS:
            bundle[fld] = None
    scrubbed["provenance"] = None
    return sha256_bytes(canonical_json(scrubbed))


# ── Helpers ─────────────────────────────────────────────────────────


def _iso(dt: Optional[datetime]) -> str:
    if dt is None:
        return ""
    return dt.isoformat()


def _component_rev(comp: Dict[str, Any]) -> str:
    """Component revision: explicit ``rev``, else the trailing letter
    of the component WPN (HAROLD format ``WS-XX-Pnnnnnn-R``), else 'A'."""
    if comp.get("rev"):
        return str(comp["rev"])
    wpn = comp.get("wpn") or ""
    tail = wpn.rsplit("-", 1)[-1] if "-" in wpn else ""
    if tail and tail.isalpha() and len(tail) <= 4:
        return tail
    return "A"


def _part_yaml_bytes(part: CatalogPart) -> bytes:
    """The §6 CADPORT YAML pass-through bytes for *part*, read back
    verbatim from its SupplierDocument file."""
    doc = part.source_document
    if doc is None:
        raise BundleExportError(
            f"component {part.internal_part_number} ({part.name}) has no "
            "source mass-properties YAML document in the catalog",
            wpn=part.internal_part_number,
        )
    path = Path(doc.file_path)
    if not path.is_file():
        raise BundleExportError(
            f"component {part.internal_part_number} ({part.name}): "
            f"mass-properties YAML file missing on disk ({doc.file_path})",
            wpn=part.internal_part_number,
        )
    return path.read_bytes()


def _inertia_rows(part: CatalogPart) -> List[List[float]]:
    matrix = part_inertia_matrix(part)
    if matrix is None:
        return [[0.0, 0.0, 0.0], [0.0, 0.0, 0.0], [0.0, 0.0, 0.0]]
    return [[float(v) for v in row] for row in matrix]


def _dedup_dependencies(deps: List[Dependency]) -> List[Dependency]:
    seen: set = set()
    out: List[Dependency] = []
    for d in deps:
        key = (d.wpn, d.rev, d.sha256)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


async def _harold_provenance(config: VehicleConfig) -> Tuple[Dict[str, Any], List[str]]:
    """Best-effort HAROLD ledger summary. HAROLD down ⇒ omit ({}) with
    a warning — never fails the export."""
    try:
        ledger = await harold_naming.ledger_query(
            system_code=config.system_code, q=config.wpn,
        )
        items = ledger.get("items") or []
        return {
            "systemCode": config.system_code,
            "query": config.wpn,
            "total": ledger.get("total", len(items)),
            "entries": [
                {
                    "wpn": e.get("wpn"),
                    "revision": e.get("revision"),
                    "status": e.get("status"),
                }
                for e in items
            ],
        }, []
    except Exception as exc:  # noqa: BLE001 — advisory path, never fatal
        warning = (
            f"HAROLD ledger unavailable at export time ({exc}); "
            "provenance.harold omitted"
        )
        logger.warning(warning)
        return {}, [warning]


# ── Export ──────────────────────────────────────────────────────────


async def export_bundle(
    db: Session,
    config: VehicleConfig,
    revision: VehicleConfigRevision,
    user: User,
) -> Tuple[ConfigBundleExport, List[str], bool]:
    """Render *revision* into a CITADEL bundle, write the directory +
    zip under :func:`exports_root`, and record (or idempotently reuse)
    a ``config_bundle_exports`` row.

    Returns ``(export_row, warnings, reused)``.
    """
    warnings: List[str] = []
    # filename → bytes; identical sha256 artifacts collapse naturally
    # because the filename is content-addressed.
    artifacts: Dict[str, bytes] = {}

    def _add_artifact(data: bytes, suffix: str) -> Tuple[str, str]:
        sha = sha256_bytes(data)
        fname = artifact_filename(sha, suffix)
        artifacts[fname] = data
        return sha, fname

    # ── 1) Components: §6 YAML pass-through ────────────────────────
    comp_wpns = [c["wpn"] for c in (revision.components or [])]
    parts_by_wpn = config_service.resolve_catalog_parts(db, comp_wpns)

    component_entries: List[ComponentEntry] = []
    dependencies: List[Dependency] = []
    for comp in revision.components or []:
        part = parts_by_wpn.get(comp["wpn"])
        if part is None:
            raise BundleExportError(
                f"component WPN {comp['wpn']!r} no longer resolves in the "
                "catalog — cannot export",
                wpn=comp["wpn"],
            )
        data = _part_yaml_bytes(part)
        sha, fname = _add_artifact(data, "massprops.yaml")
        rev_letter = _component_rev(comp)
        placement = comp.get("placement")
        component_entries.append(ComponentEntry(
            role=comp["role"],
            wpn=comp["wpn"],
            rev=rev_letter,
            name=comp.get("name") or part.name,
            mass_kg=float(part.mass_kg),
            cg_m_B=[
                float(part.center_of_mass_x),
                float(part.center_of_mass_y),
                float(part.center_of_mass_z),
            ],
            inertia_kgm2_B=_inertia_rows(part),
            placement=(
                {"matrix4x4": placement} if placement is not None else None
            ),
            artifact=ArtifactRef(
                type="mass_props_yaml",
                file=f"artifacts/{fname}",
                sha256=sha,
                sourceSystem="CADPORT",
                ingestUtc=_iso(part.source_document.uploaded_at),
            ),
        ))
        dependencies.append(
            Dependency(wpn=comp["wpn"], rev=rev_letter, sha256=sha)
        )

    # ── 2) Aero block ───────────────────────────────────────────────
    aero_block: Optional[AeroBlock] = None
    if revision.aero_binding:
        resolved = config_service.resolve_aero_revision(
            db, revision.aero_binding["wpn"],
            revision.aero_binding["rev_letter"],
        )
        if resolved is None:
            raise BundleExportError(
                f"bound aero deck {revision.aero_binding['wpn']!r} rev "
                f"{revision.aero_binding['rev_letter']!r} no longer "
                "resolves — cannot export",
            )
        deck, deck_rev = resolved
        deck_json = deck_rev.deck or {}
        data = canonical_json(deck_json)
        sha, fname = _add_artifact(data, "aero.json")
        env = deck_json.get("validityEnvelope") or {}
        aero_block = AeroBlock(
            wpn=deck.wpn,
            rev=deck_rev.rev_letter,
            omlWpn=deck_json.get("omlWpn") or deck.oml_wpn or "",
            Sref_m2=float(deck_json.get("Sref_m2", deck_rev.sref_m2 or 0.0)),
            Lref_m=float(deck_json.get("Lref_m", deck_rev.lref_m or 0.0)),
            refPoint_m_B=[
                float(x) for x in deck_json.get("refPoint_m_B", [0, 0, 0])
            ],
            validityEnvelope=ValidityEnvelope(
                machRange=env.get("machRange", [0.0, 0.0]),
                alphaRange_deg=env.get("alphaRange_deg", [0.0, 0.0]),
                betaRange_deg=env.get("betaRange_deg", [0.0, 0.0]),
            ),
            artifact=ArtifactRef(
                type="aero_deck",
                file=f"artifacts/{fname}",
                sha256=sha,
                sourceSystem="AstraAero",
                ingestUtc=_iso(deck_rev.created_utc),
            ),
        )
        dependencies.append(
            Dependency(wpn=deck.wpn, rev=deck_rev.rev_letter, sha256=sha)
        )

    # ── 3) Propulsion stages ────────────────────────────────────────
    stages: List[PropulsionStage] = []
    motor_tiers: List[str] = []
    for stage in revision.stage_map or []:
        resolved = config_service.resolve_motor_revision(
            db, stage["motorWpn"], stage["motorRevLetter"],
        )
        if resolved is None:
            raise BundleExportError(
                f"stage {stage['stageNum']}: motor {stage['motorWpn']!r} "
                f"rev {stage['motorRevLetter']!r} no longer resolves — "
                "cannot export",
            )
        motor, motor_rev = resolved
        data = canonical_json(motor_rev.artifact)
        sha, fname = _add_artifact(data, "motor.json")
        motor_tiers.append(motor_rev.quality_tier)
        stages.append(PropulsionStage(
            stageNum=int(stage["stageNum"]),
            motorWpn=stage["motorWpn"],
            motorRev=stage["motorRevLetter"],
            ignitionTime_s=float(stage["ignitionTime_s"]),
            thrustAxis_B=[float(x) for x in stage["thrustAxis_B"]],
            mcTrialId=stage.get("mcTrialId"),
            artifact=ArtifactRef(
                type="motor_curve",
                file=f"artifacts/{fname}",
                sha256=sha,
                sourceSystem="AstraMotor",
                qualityTier=motor_rev.quality_tier,
                origin=motor_rev.origin,
                ingestUtc=_iso(motor_rev.created_utc),
            ),
        ))
        dependencies.append(Dependency(
            wpn=stage["motorWpn"], rev=stage["motorRevLetter"], sha256=sha,
        ))

    # ── 4) Manifest ────────────────────────────────────────────────
    frame_icd = db.query(FrameIcd).filter(
        FrameIcd.id == revision.frame_icd_id).first()
    frame_rev = db.query(FrameIcdRevision).filter(
        FrameIcdRevision.frame_icd_id == revision.frame_icd_id,
        FrameIcdRevision.rev == revision.frame_icd_rev,
    ).first()
    if frame_icd is None or frame_rev is None:
        raise BundleExportError(
            "stamped frame ICD revision no longer resolves — cannot export",
        )

    rollup = revision.rollup or {}
    harold_prov, harold_warnings = await _harold_provenance(config)
    warnings.extend(harold_warnings)

    # recommendedFidelity (schema field is a string): propulsion is
    # 'HiFi' only when every bound motor revision is 'excellent'.
    recommended: Optional[str] = None
    if stages:
        recommended = (
            "HiFi" if all(t == "excellent" for t in motor_tiers)
            else "Nominal"
        )

    now_utc = datetime.now(timezone.utc).isoformat()
    manifest = Manifest(
        bundle=BundleBlock(
            id=uuid.uuid4().hex,
            createdUtc=now_utc,
            createdBy=user.username,
            astraBaselineId=revision.astra_baseline_id,
            bundleHash=None,
        ),
        config=ConfigBlock(
            wpn=config.wpn,
            name=config.name,
            rev=revision.rev_letter,
            description=revision.description,
            topAssemblyWpn=revision.top_assembly_wpn,
        ),
        frame=FrameBlock(
            icdId=frame_icd.key,
            icdRev=frame_rev.rev,
            datum=frame_rev.datum,
            axes=frame_rev.axes,
            units=frame_rev.units,
        ),
        massProperties=MassPropertiesBlock(
            totalMass_kg=rollup["totalMass_kg"],
            cg_m_B=rollup["cg_m_B"],
            inertia_kgm2_B=rollup["inertia_kgm2_B"],
            referencePoint_m_B=rollup["referencePoint_m_B"],
        ),
        components=component_entries,
        aero=aero_block,
        propulsion=stages or None,
        recommendedFidelity=recommended,
        dependencies=_dedup_dependencies(dependencies),
        provenance=ProvenanceBlock(
            harold=harold_prov,
            astra=AstraProvenance(
                baselineId=revision.astra_baseline_id,
                exportedBy=user.username,
                exportedUtc=now_utc,
            ),
        ),
    )

    # ── 5) Deterministic hash → stamp into the manifest ───────────
    manifest_dict = manifest_to_dict(manifest)
    bundle_hash = compute_deterministic_bundle_hash(manifest_dict)
    manifest_dict["bundle"]["bundleHash"] = bundle_hash

    # ── 6) Record (or idempotently reuse) the row; write files ────
    dirname = bundle_dirname(config.wpn, revision.rev_letter, bundle_hash)
    bundle_dir = exports_root() / dirname
    zip_path = exports_root() / f"{dirname}.zip"

    existing = (
        db.query(ConfigBundleExport)
        .filter(
            ConfigBundleExport.config_wpn == config.wpn,
            ConfigBundleExport.rev_letter == revision.rev_letter,
            ConfigBundleExport.bundle_hash == bundle_hash,
        )
        .first()
    )
    if existing is not None:
        # Identical content already recorded — idempotent reuse (the
        # UNIQUE constraint keeps lookup-by-hash unambiguous). The
        # on-disk bundle stays byte-identical to the STORED manifest;
        # it is only re-rendered (from that stored manifest) if the
        # zip went missing on disk.
        if not Path(existing.zip_path).is_file():
            _write_bundle_files(
                exports_root() / existing.bundle_dirname,
                Path(existing.zip_path),
                existing.manifest,
                artifacts,
            )
        return existing, warnings, True

    _write_bundle_files(bundle_dir, zip_path, manifest_dict, artifacts)

    export = ConfigBundleExport(
        vehicle_config_revision_id=revision.id,
        config_wpn=config.wpn,
        rev_letter=revision.rev_letter,
        bundle_hash=bundle_hash,
        bundle_dirname=dirname,
        manifest=manifest_dict,
        zip_path=str(zip_path),
        artifact_count=len(artifacts),
        created_by_id=user.id,
    )
    db.add(export)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(export)
    return export, warnings, False


def _write_bundle_files(
    bundle_dir: Path,
    zip_path: Path,
    manifest_dict: Dict[str, Any],
    artifacts: Dict[str, bytes],
) -> None:
    """Write ``<dir>/manifest.json`` + ``<dir>/artifacts/*`` and the
    sibling zip. Deterministic: canonical-JSON manifest bytes, sorted
    arcnames, fixed (1980,1,1) zip timestamps — re-rendering the same
    revision produces byte-stable zip content."""
    manifest_bytes = canonical_json(manifest_dict)

    artifacts_dir = bundle_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    (bundle_dir / "manifest.json").write_bytes(manifest_bytes)
    for fname, data in artifacts.items():
        (artifacts_dir / fname).write_bytes(data)

    entries: List[Tuple[str, bytes]] = [("manifest.json", manifest_bytes)]
    entries.extend(
        (f"artifacts/{fname}", data)
        for fname, data in sorted(artifacts.items())
    )
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for arcname, data in entries:
            info = zipfile.ZipInfo(
                filename=arcname, date_time=(1980, 1, 1, 0, 0, 0),
            )
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, data)
