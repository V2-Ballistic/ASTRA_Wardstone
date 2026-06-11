"""
ASTRA — Configurations tracker service (spec §8)
=================================================
File: backend/app/services/engineering/config_service.py   ← NEW

Save-time validation + immutable-revision content assembly for the
Configurations tracker. The router calls
``validate_and_build_revision_content`` BEFORE asking HAROLD for a
WPN, so an invalid config never burns a ledger index.

Validation rules (spec §8) — failures raise
:class:`ConfigValidationError` with a STRUCTURED error list (the
router maps it to 422):

  1. every component WPN exists in the catalog
     (``CatalogPart.internal_part_number``, not soft-deleted);
  2. at most one component with role 'oml'; EXACTLY one when an aero
     deck is bound;
  3. aero binding (if present): the deck wpn + rev_letter exist, AND
     the deck's oml_wpn equals the wpn of the 'oml' component (when
     both are present — mismatch lists both);
  4. every stage-map motor wpn + rev letter exists;
  5. the frame ICD is stamped (id + current rev) via
     ``get_or_register_default_frame``;
  6. the mass-properties roll-up is computable (every component has
     mass + CG in the catalog).

Also provides the structured revision diff used by
``GET /engineering/configs/{wpn}/diff``.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from app.models.catalog import CatalogPart
from app.models.engineering_aero import AeroDeck, AeroDeckRevision
from app.models.engineering_motor import Motor, MotorRevision
from app.models.engineering_config import VehicleConfigRevision
from app.services.engineering.config_rollup import rollup_components
from app.services.engineering.frame import get_or_register_default_frame


class ConfigValidationError(Exception):
    """Save-time validation failure; ``errors`` is the structured list
    the router returns in the 422 body."""

    def __init__(self, errors: List[Dict[str, Any]]):
        self.errors = errors
        super().__init__(
            "config validation failed: "
            + "; ".join(e.get("message", e.get("code", "?")) for e in errors)
        )

    def detail(self) -> Dict[str, Any]:
        return {"message": "config validation failed", "errors": self.errors}


# ── Lookups ─────────────────────────────────────────────────────────


def resolve_catalog_parts(
    db: Session, wpns: List[str],
) -> Dict[str, CatalogPart]:
    """Catalog parts by WPN (= internal_part_number), excluding
    soft-deleted rows."""
    if not wpns:
        return {}
    rows = (
        db.query(CatalogPart)
        .filter(
            CatalogPart.internal_part_number.in_(wpns),
            CatalogPart.deleted_at.is_(None),
        )
        .all()
    )
    return {p.internal_part_number: p for p in rows}


def resolve_aero_revision(
    db: Session, wpn: str, rev_letter: str,
) -> Optional[Tuple[AeroDeck, AeroDeckRevision]]:
    """Aero deck + revision by base WPN (or any revision's full WPN)
    and revision letter."""
    deck = db.query(AeroDeck).filter(AeroDeck.wpn == wpn).first()
    if deck is None:
        rev = (
            db.query(AeroDeckRevision)
            .filter(AeroDeckRevision.wpn == wpn)
            .first()
        )
        deck = rev.deck_parent if rev is not None else None
    if deck is None:
        return None
    for r in deck.revisions:
        if r.rev_letter == rev_letter:
            return deck, r
    return None


def resolve_motor_revision(
    db: Session, wpn: str, rev_letter: str,
) -> Optional[Tuple[Motor, MotorRevision]]:
    """Motor + revision by base WPN (or any revision's full WPN) and
    revision letter."""
    motor = db.query(Motor).filter(Motor.wpn == wpn).first()
    if motor is None:
        rev = (
            db.query(MotorRevision)
            .filter(MotorRevision.wpn == wpn)
            .first()
        )
        motor = rev.motor if rev is not None else None
    if motor is None:
        return None
    for r in motor.revisions:
        if r.rev_letter == rev_letter:
            return motor, r
    return None


# ── Save-time validation + content assembly ─────────────────────────


def validate_and_build_revision_content(
    db: Session,
    *,
    components: List[Dict[str, Any]],
    aero_binding: Optional[Dict[str, Any]],
    stage_map: List[Dict[str, Any]],
    user_id: int,
) -> Dict[str, Any]:
    """Run the full §8 save-time validation and return the validated
    revision content::

        {components, aero_binding, stage_map, rollup, validation,
         frame_icd_id, frame_icd_rev}

    Component dicts are normalized (name defaulted from the catalog).
    Raises :class:`ConfigValidationError` on any fatal finding —
    NOTHING is allocated or persisted by this function (the frame ICD
    ensure is idempotent and commits independently).
    """
    errors: List[Dict[str, Any]] = []
    warnings: List[str] = []

    # 1) every component WPN exists in the catalog (not deleted).
    wpns = [c["wpn"] for c in components]
    parts_by_wpn = resolve_catalog_parts(db, wpns)
    for c in components:
        if c["wpn"] not in parts_by_wpn:
            errors.append({
                "code": "unknown_component_wpn",
                "wpn": c["wpn"],
                "message": (
                    f"component WPN {c['wpn']!r} not found in the catalog "
                    "(internal_part_number) or is deleted"
                ),
            })

    # Normalize: default component name from the catalog.
    norm_components: List[Dict[str, Any]] = []
    for c in components:
        part = parts_by_wpn.get(c["wpn"])
        comp = dict(c)
        if not comp.get("name") and part is not None:
            comp["name"] = part.name
        norm_components.append(comp)

    # 2) OML cardinality.
    oml_comps = [c for c in norm_components if c.get("role") == "oml"]
    if len(oml_comps) > 1:
        errors.append({
            "code": "multiple_oml_components",
            "wpns": [c["wpn"] for c in oml_comps],
            "message": (
                "at most one component may have role 'oml'; got "
                + ", ".join(c["wpn"] for c in oml_comps)
            ),
        })
    if aero_binding is not None and len(oml_comps) == 0:
        errors.append({
            "code": "missing_oml_component",
            "message": (
                "an aero deck is bound but no component has role 'oml' — "
                "exactly one is required"
            ),
        })

    # 3) aero binding resolves + OML↔deck consistency.
    if aero_binding is not None:
        resolved = resolve_aero_revision(
            db, aero_binding["wpn"], aero_binding["rev_letter"],
        )
        if resolved is None:
            errors.append({
                "code": "unknown_aero_deck",
                "wpn": aero_binding["wpn"],
                "rev_letter": aero_binding["rev_letter"],
                "message": (
                    f"aero deck {aero_binding['wpn']!r} revision "
                    f"{aero_binding['rev_letter']!r} not found"
                ),
            })
        elif len(oml_comps) == 1:
            deck, deck_rev = resolved
            deck_oml = (deck_rev.deck or {}).get("omlWpn") or deck.oml_wpn
            comp_oml = oml_comps[0]["wpn"]
            if deck_oml and deck_oml != comp_oml:
                errors.append({
                    "code": "oml_aero_mismatch",
                    "deck_oml_wpn": deck_oml,
                    "component_oml_wpn": comp_oml,
                    "message": (
                        f"aero deck {aero_binding['wpn']} is for OML "
                        f"{deck_oml!r} but the config's 'oml' component is "
                        f"{comp_oml!r}"
                    ),
                })

    # 4) stage-map motors resolve.
    for stage in stage_map:
        if resolve_motor_revision(
            db, stage["motorWpn"], stage["motorRevLetter"],
        ) is None:
            errors.append({
                "code": "unknown_motor",
                "stageNum": stage["stageNum"],
                "motorWpn": stage["motorWpn"],
                "motorRevLetter": stage["motorRevLetter"],
                "message": (
                    f"stage {stage['stageNum']}: motor "
                    f"{stage['motorWpn']!r} revision "
                    f"{stage['motorRevLetter']!r} not found"
                ),
            })

    # 5) frame stamp (idempotent ensure; commits independently).
    icd, frame_rev = get_or_register_default_frame(db, user_id)

    # 6) roll-up computable.
    outcome = rollup_components(norm_components, parts_by_wpn)
    errors.extend(outcome.errors)
    warnings.extend(outcome.warnings)

    if errors:
        raise ConfigValidationError(errors)

    return {
        "components": norm_components,
        "aero_binding": aero_binding,
        "stage_map": stage_map,
        "rollup": outcome.rollup,
        "validation": {"warnings": warnings},
        "frame_icd_id": icd.id,
        "frame_icd_rev": frame_rev.rev,
    }


# ── Structured revision diff ────────────────────────────────────────


def _placement_equal(a: Any, b: Any) -> bool:
    return a == b


def diff_revisions(
    rev_from: VehicleConfigRevision,
    rev_to: VehicleConfigRevision,
) -> Dict[str, Any]:
    """Structured diff between two revisions of the same config:
    components added / removed / changed (rev or placement), aero
    binding change, stage-map changes, roll-up delta."""
    comps_a = {c["wpn"]: c for c in (rev_from.components or [])}
    comps_b = {c["wpn"]: c for c in (rev_to.components or [])}

    added = [comps_b[w] for w in comps_b if w not in comps_a]
    removed = [comps_a[w] for w in comps_a if w not in comps_b]
    changed: List[Dict[str, Any]] = []
    for w in comps_a:
        if w not in comps_b:
            continue
        a, b = comps_a[w], comps_b[w]
        fields_changed = []
        if (a.get("rev") or None) != (b.get("rev") or None):
            fields_changed.append("rev")
        if not _placement_equal(a.get("placement"), b.get("placement")):
            fields_changed.append("placement")
        if (a.get("role") or None) != (b.get("role") or None):
            fields_changed.append("role")
        if fields_changed:
            changed.append({
                "wpn": w,
                "fields": fields_changed,
                "from": {k: a.get(k) for k in ("rev", "placement", "role")},
                "to": {k: b.get(k) for k in ("rev", "placement", "role")},
            })

    aero_change: Optional[Dict[str, Any]] = None
    if (rev_from.aero_binding or None) != (rev_to.aero_binding or None):
        aero_change = {
            "from": rev_from.aero_binding,
            "to": rev_to.aero_binding,
        }

    stages_a = {s["stageNum"]: s for s in (rev_from.stage_map or [])}
    stages_b = {s["stageNum"]: s for s in (rev_to.stage_map or [])}
    stage_added = [stages_b[n] for n in sorted(stages_b) if n not in stages_a]
    stage_removed = [stages_a[n] for n in sorted(stages_a) if n not in stages_b]
    stage_changed = [
        {"stageNum": n, "from": stages_a[n], "to": stages_b[n]}
        for n in sorted(set(stages_a) & set(stages_b))
        if stages_a[n] != stages_b[n]
    ]

    ra, rb = rev_from.rollup or {}, rev_to.rollup or {}
    rollup_delta: Dict[str, Any] = {}
    if "totalMass_kg" in ra and "totalMass_kg" in rb:
        rollup_delta["totalMass_kg"] = rb["totalMass_kg"] - ra["totalMass_kg"]
    if "cg_m_B" in ra and "cg_m_B" in rb:
        rollup_delta["cg_m_B"] = [
            float(x2) - float(x1) for x1, x2 in zip(ra["cg_m_B"], rb["cg_m_B"])
        ]

    return {
        "config_wpn": rev_from.config.wpn,
        "from_rev": rev_from.rev_letter,
        "to_rev": rev_to.rev_letter,
        "components": {
            "added": added,
            "removed": removed,
            "changed": changed,
        },
        "aero_binding": aero_change,
        "stage_map": {
            "added": stage_added,
            "removed": stage_removed,
            "changed": stage_changed,
        },
        "rollup_delta": rollup_delta,
    }
