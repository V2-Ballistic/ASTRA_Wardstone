"""
ASTRA — Reactive Requirement Sync — Fan-Out Service
====================================================
File: backend/app/services/req_sync/fan_out.py    ← NEW (Phase 5)

Walks every requirement linked to a changed source entity, decides whether
the change should auto-apply or surface as a proposal, and writes the
resulting RequirementSyncProposal rows.

The auto-apply policy lives in :func:`decide_action` so it can be unit-
tested cell-by-cell against the spec's §12.5 table.

Anomaly notes (digest §6, §11)
------------------------------
* Spec §12.5 references statuses ``cancelled`` and ``superseded`` that do
  NOT exist in the actual ``RequirementStatus`` enum. Mapping:
    - "cancelled"  → ``DELETED``        → SKIP
    - "superseded" → not modelled       → treat as no-op (SKIP)
* Spec §12.5 lists ``pending_review`` reqs as silent auto-apply. We keep
  the silent update but ALWAYS emit ``req_sync.auto_applied`` to audit so
  the change is recoverable / reviewable post-hoc.
* ``RequirementSourceLink.template_inputs`` is NOT NULL — the snapshot
  must always populate it (digest #11). We pass ``ctx or {}`` everywhere.
"""

from __future__ import annotations

import enum
import logging
from datetime import datetime
from typing import Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import Requirement, RequirementStatus, RequirementHistory
from app.models.req_sync import (
    RequirementSourceLink,
    RequirementSyncProposal,
    SourceEntityType,
    SyncProposalStatus,
    SyncProposalType,
)
from app.services.req_sync.renderer import (
    RenderedRequirement,
    render_requirement,
)

logger = logging.getLogger("astra.req_sync.fan_out")


# ══════════════════════════════════════════════════════════════
#  Auto-apply policy (spec §12.5 + digest anomaly resolutions)
# ══════════════════════════════════════════════════════════════

class SyncAction(str, enum.Enum):
    """Outcome of applying the policy table to a (status, proposal_type) pair."""
    AUTO_APPLY        = "auto_apply"
    PROPOSAL_PENDING  = "proposal_pending"
    SKIP              = "skip"


# Statuses where the requirement is considered immutable history — the
# fan-out engine must never write through them. (spec §12.5 + digest §6).
_NON_MUTABLE_STATUSES = frozenset({
    RequirementStatus.DELETED,
    # Approved + locked workflows — verified/validated need a manual review
    # before any sync touches them. The policy table still creates a
    # PROPOSAL_PENDING row; this set is the "skip even creating a proposal"
    # short-circuit used only for DELETED.
})


def decide_action(
    req_status: RequirementStatus,
    proposal_type: SyncProposalType,
) -> SyncAction:
    """Return the auto-apply outcome for a (status, proposal_type) cell.

    Per spec §12.5 (with digest §6 anomaly resolutions):

    | status               | UPDATE_STATEMENT  | OBSOLETE         | REGENERATE       |
    |----------------------|-------------------|------------------|------------------|
    | DRAFT                | AUTO_APPLY        | PROPOSAL_PENDING | PROPOSAL_PENDING |
    | UNDER_REVIEW         | PROPOSAL_PENDING  | PROPOSAL_PENDING | PROPOSAL_PENDING |
    | APPROVED             | PROPOSAL_PENDING  | PROPOSAL_PENDING | PROPOSAL_PENDING |
    | BASELINED            | PROPOSAL_PENDING  | PROPOSAL_PENDING | PROPOSAL_PENDING |
    | IMPLEMENTED          | PROPOSAL_PENDING  | PROPOSAL_PENDING | PROPOSAL_PENDING |
    | VERIFIED             | PROPOSAL_PENDING  | PROPOSAL_PENDING | PROPOSAL_PENDING |
    | VALIDATED            | PROPOSAL_PENDING  | PROPOSAL_PENDING | PROPOSAL_PENDING |
    | DEFERRED             | SKIP              | SKIP             | SKIP             |
    | DELETED              | SKIP              | SKIP             | SKIP             |
    | PENDING_REVIEW       | AUTO_APPLY        | PROPOSAL_PENDING | PROPOSAL_PENDING |
    | AUTO_GENERATED       | AUTO_APPLY        | PROPOSAL_PENDING | PROPOSAL_PENDING |

    DELETED + DEFERRED short-circuit to SKIP. PENDING_REVIEW emits an
    audit event on auto-apply so the action is still traceable.
    """
    # Spec "cancelled" maps to DELETED; spec "superseded" is not in the
    # enum (treated as immutable history → SKIP).
    if req_status in (RequirementStatus.DELETED, RequirementStatus.DEFERRED):
        return SyncAction.SKIP

    if proposal_type in (SyncProposalType.OBSOLETE, SyncProposalType.REGENERATE):
        # Catastrophic edits always require human review.
        return SyncAction.PROPOSAL_PENDING

    # UPDATE_STATEMENT cells:
    if req_status in (
        RequirementStatus.DRAFT,
        RequirementStatus.PENDING_REVIEW,
        RequirementStatus.AUTO_GENERATED,
    ):
        return SyncAction.AUTO_APPLY

    # under_review, approved, baselined, implemented, verified, validated
    return SyncAction.PROPOSAL_PENDING


# ══════════════════════════════════════════════════════════════
#  Fan-out service
# ══════════════════════════════════════════════════════════════

def _supersede_prior_pending(
    db: Session,
    requirement_id: int,
) -> int:
    """Mark every PENDING proposal for *requirement_id* as SUPERSEDED.

    Returns the number of rows affected. Caller is responsible for the
    surrounding transaction.
    """
    rows = (
        db.query(RequirementSyncProposal)
        .filter(
            RequirementSyncProposal.requirement_id == requirement_id,
            RequirementSyncProposal.status == SyncProposalStatus.PENDING,
        )
        .all()
    )
    for row in rows:
        row.status = SyncProposalStatus.SUPERSEDED
        row.reviewed_at = datetime.utcnow()
    return len(rows)


def _diff_fields(
    old_statement: str,
    new_statement: Optional[str],
    old_rationale: Optional[str],
    new_rationale: Optional[str],
) -> Dict[str, Dict[str, Optional[str]]]:
    """Build the field_diffs blob stored on RequirementSyncProposal."""
    diffs: Dict[str, Dict[str, Optional[str]]] = {}
    if (old_statement or "") != (new_statement or ""):
        diffs["statement"] = {"old": old_statement, "new": new_statement}
    if (old_rationale or "") != (new_rationale or ""):
        diffs["rationale"] = {"old": old_rationale, "new": new_rationale}
    return diffs


def _emit_audit(db: Session, event_type: str, requirement: Requirement,
                detail: Dict) -> None:
    """Best-effort audit emit. Audit failures must never abort fan-out."""
    try:
        from app.services.audit_service import record_event
        record_event(
            db,
            event_type=event_type,
            entity_type="requirement",
            entity_id=requirement.id,
            user_id=requirement.owner_id or 0,
            project_id=requirement.project_id,
            action_detail=detail,
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("audit emit failed for %s: %s", event_type, exc)


def _bulk_load_source_links(
    db: Session,
    requirement_ids: List[int],
) -> Dict[int, List[RequirementSourceLink]]:
    """Return ``{requirement_id: [links]}`` in one query (no N+1)."""
    if not requirement_ids:
        return {}
    rows = (
        db.query(RequirementSourceLink)
        .filter(RequirementSourceLink.requirement_id.in_(requirement_ids))
        .all()
    )
    out: Dict[int, List[RequirementSourceLink]] = {rid: [] for rid in requirement_ids}
    for row in rows:
        out.setdefault(row.requirement_id, []).append(row)
    return out


def fan_out_for_entity(
    db: Session,
    entity_type: SourceEntityType,
    entity_id: int,
    trigger_event: str,
) -> List[RequirementSyncProposal]:
    """For every requirement linked to ``(entity_type, entity_id)``, decide
    auto-apply vs proposal vs skip per :func:`decide_action`.

    Returns the list of proposal rows that were either created (PENDING) or
    auto-applied (AUTO_APPLIED). The caller flushes/commits the surrounding
    transaction; this function only ``db.add(...)`` and never commits.

    ``trigger_event`` is one of ``"update"``, ``"delete"``, ``"insert"``.
    A delete trigger forces every linked requirement onto the OBSOLETE
    proposal path regardless of whether the renderer thinks it could
    re-render.
    """
    # 1. Find every link pointing at this entity. (Indexed by
    #    (source_entity_type, source_entity_id) — single seek.)
    direct_links = (
        db.query(RequirementSourceLink)
        .filter(
            RequirementSourceLink.source_entity_type == entity_type,
            RequirementSourceLink.source_entity_id == entity_id,
        )
        .all()
    )
    if not direct_links:
        return []

    requirement_ids = list({sl.requirement_id for sl in direct_links})
    requirements = (
        db.query(Requirement)
        .filter(Requirement.id.in_(requirement_ids))
        .all()
    )
    req_by_id = {r.id: r for r in requirements}

    # 2. Bulk-load every source link for those requirements (no N+1).
    all_links_by_req = _bulk_load_source_links(db, requirement_ids)

    proposals: List[RequirementSyncProposal] = []

    for rid in requirement_ids:
        req = req_by_id.get(rid)
        if req is None:
            continue

        # 3. Hard short-circuits.
        if bool(req.sync_locked):
            logger.info("fan_out: skip req %s — sync_locked", req.req_id)
            continue
        # Spec maps "cancelled" → DELETED; "superseded" → no-op.
        if req.status == RequirementStatus.DELETED:
            continue

        all_links = all_links_by_req.get(rid, [])
        template_id = req.generation_template_id

        # 4. Determine proposal_type and re-render.
        if trigger_event == "delete":
            proposal_type = SyncProposalType.OBSOLETE
            new_render = RenderedRequirement(source_deleted=True)
        else:
            proposal_type = SyncProposalType.UPDATE_STATEMENT
            new_render = RenderedRequirement()
            if template_id:
                try:
                    new_render = render_requirement(db, template_id, all_links)
                except Exception as exc:
                    logger.error(
                        "fan_out: renderer raised for req %s template %s: %s",
                        req.req_id, template_id, exc,
                    )
                    proposal_type = SyncProposalType.REGENERATE
            if new_render.source_deleted:
                proposal_type = SyncProposalType.OBSOLETE
            elif new_render.template_missing and template_id:
                proposal_type = SyncProposalType.REGENERATE

        # 5. Skip when nothing actually changed (only meaningful for
        #    UPDATE_STATEMENT — OBSOLETE / REGENERATE are always
        #    surfaced).
        if proposal_type == SyncProposalType.UPDATE_STATEMENT:
            no_template = template_id is None
            unchanged = (
                new_render.statement is not None
                and (req.statement or "") == (new_render.statement or "")
                and (req.rationale or "") == (new_render.rationale or "")
            )
            if no_template or unchanged:
                continue

        # 6. Apply the policy.
        action = decide_action(req.status, proposal_type)
        if action == SyncAction.SKIP:
            continue

        # Always supersede prior PENDING proposals on this requirement
        # (a fresher decision wins).
        _supersede_prior_pending(db, rid)

        diffs = _diff_fields(
            req.statement, new_render.statement,
            req.rationale, new_render.rationale,
        )

        proposal = RequirementSyncProposal(
            requirement_id=rid,
            triggered_by_entity_type=entity_type,
            triggered_by_entity_id=entity_id,
            trigger_event=trigger_event,
            old_statement=req.statement or "",
            new_statement=new_render.statement,
            old_rationale=req.rationale,
            new_rationale=new_render.rationale,
            field_diffs=diffs,
            proposal_type=proposal_type,
            status=(
                SyncProposalStatus.AUTO_APPLIED
                if action == SyncAction.AUTO_APPLY
                else SyncProposalStatus.PENDING
            ),
            auto_applied=(action == SyncAction.AUTO_APPLY),
            reviewed_at=(
                datetime.utcnow() if action == SyncAction.AUTO_APPLY else None
            ),
        )
        db.add(proposal)

        if action == SyncAction.AUTO_APPLY:
            # Apply to the live row right now.
            old_statement = req.statement
            old_rationale = req.rationale
            req.statement = new_render.statement or req.statement
            req.rationale = new_render.rationale
            req.version = (req.version or 1) + 1
            req.updated_at = datetime.utcnow()

            # Refresh the snapshot stored on each source link so the
            # next render comparison starts from current values.
            for sl in all_links:
                sl.template_inputs = new_render.template_inputs or {}
                sl.last_synced_at = datetime.utcnow()

            # Record history (mirrors the rest of the requirement
            # lifecycle).
            try:
                hist = RequirementHistory(
                    requirement_id=rid,
                    version=req.version,
                    field_changed="statement",
                    old_value=old_statement,
                    new_value=req.statement,
                    changed_by_id=req.owner_id,
                    change_description=(
                        f"Auto-sync from {entity_type.value} #{entity_id} "
                        f"({trigger_event})"
                    ),
                )
                db.add(hist)
            except Exception as exc:  # pragma: no cover
                logger.warning("history insert failed: %s", exc)

            _emit_audit(
                db, "req_sync.auto_applied", req,
                detail={
                    "entity_type": entity_type.value,
                    "entity_id": entity_id,
                    "trigger_event": trigger_event,
                    "old_statement": old_statement,
                    "new_statement": req.statement,
                },
            )

        proposals.append(proposal)

    if proposals:
        # Flush so caller sees IDs / counts before commit.
        db.flush()

    return proposals
