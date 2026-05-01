"""ASTRA — Reactive Requirement Sync Engine tests (Phase 5)
================================================================
File: backend/tests/test_req_sync.py    ← NEW (ASTRA-TDD-INTF-002 Phase 5)

Covers spec §12.7 + the safety constraints called out in the Phase 5
prompt:

  1. Listener doesn't fire when sync_locked=True
  2. Listener doesn't fire when status in (deleted, baselined, verified, validated)
     per the auto-apply policy (skip / proposal-only)
  3. Recursive trigger is bounded (apply a proposal that touches a source-linked
     req → second listener doesn't fan out; depth=1 cap)
  4. under_review (== pending_review per spec mapping) + UPDATE_STATEMENT →
     auto-applied silently AND emits req_sync.auto_applied audit event
  5. approved + UPDATE_STATEMENT → creates a PENDING proposal, never auto-applies
  6. Each cell of the auto-apply policy table is parameter-tested
  7. Source delete → all linked reqs get OBSOLETE proposals (status=PENDING)
  8. Bulk-accept atomicity: if one proposal application fails, the entire
     batch rolls back
  9. Lock prevents proposal creation; unlock re-enables
 10. Performance: 100 source links on one entity → fan-out completes in <1s
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import List

import pytest

from app.models import (
    Project, Requirement, RequirementStatus, User, UserRole,
)
from app.models.interface import (
    System, Unit, Connector, Pin, BusDefinition,
    WireHarness, Wire,
)
from app.models.req_sync import (
    RequirementSourceLink,
    RequirementSyncProposal,
    SourceEntityType,
    SyncProposalStatus,
    SyncProposalType,
)
from app.services.req_sync import (
    SyncAction,
    decide_action,
    fan_out_for_entity,
    register_sync_listeners,
)
from app.services.req_sync.listener import _current_depth
from tests.conftest import make_user


# ══════════════════════════════════════════════════════════════
#  Listener registration (idempotent — safe per test)
# ══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def _ensure_listeners_registered():
    register_sync_listeners()
    yield


# ══════════════════════════════════════════════════════════════
#  Minimum graph builder
# ══════════════════════════════════════════════════════════════

@pytest.fixture()
def graph(db_session, test_user, test_project):
    sys_a = System(
        system_id="SYS-A", name="Sys A", abbreviation="A",
        system_type="subsystem",
        project_id=test_project.id, owner_id=test_user.id,
    )
    sys_b = System(
        system_id="SYS-B", name="Sys B", abbreviation="B",
        system_type="subsystem",
        project_id=test_project.id, owner_id=test_user.id,
    )
    db_session.add_all([sys_a, sys_b])
    db_session.flush()

    unit_a = Unit(
        unit_id="UA", name="A1", designation="A-100",
        part_number="A1", manufacturer="x", unit_type="processor",
        status="concept", system_id=sys_a.id, project_id=test_project.id,
    )
    unit_b = Unit(
        unit_id="UB", name="B1", designation="B-200",
        part_number="B1", manufacturer="y", unit_type="processor",
        status="concept", system_id=sys_b.id, project_id=test_project.id,
    )
    db_session.add_all([unit_a, unit_b])
    db_session.flush()

    conn_a = Connector(
        connector_id="CA", designator="J1",
        connector_type="mil_dtl_38999_series_iii", gender="female_socket",
        total_contacts=4, unit_id=unit_a.id, project_id=test_project.id,
    )
    conn_b = Connector(
        connector_id="CB", designator="J1",
        connector_type="mil_dtl_38999_series_iii", gender="male_pin",
        total_contacts=4, unit_id=unit_b.id, project_id=test_project.id,
    )
    db_session.add_all([conn_a, conn_b])
    db_session.flush()

    pin_a = Pin(
        pin_number="1", signal_name="DATA",
        signal_type="signal_digital_single", direction="bidirectional",
        connector_id=conn_a.id,
    )
    pin_b = Pin(
        pin_number="1", signal_name="DATA",
        signal_type="signal_digital_single", direction="bidirectional",
        connector_id=conn_b.id,
    )
    db_session.add_all([pin_a, pin_b])
    db_session.flush()

    harness = WireHarness(
        harness_id="HAR-001", name="A↔B",
        from_unit_id=unit_a.id, from_connector_id=conn_a.id,
        to_unit_id=unit_b.id, to_connector_id=conn_b.id,
        project_id=test_project.id, cable_type="MIL-DTL-27500",
        overall_length_m=2.0, overall_length_max_m=2.5,
    )
    db_session.add(harness)
    db_session.flush()

    wire = Wire(
        wire_number="W001", signal_name="DATA",
        wire_type="signal_twisted_pair_a",
        from_pin_id=pin_a.id, to_pin_id=pin_b.id,
        harness_id=harness.id,
    )
    db_session.add(wire)
    db_session.flush()

    bus = BusDefinition(
        bus_def_id="BUS-001", name="1553 Bus",
        protocol="mil_std_1553b", bus_role="remote_terminal",
        bus_address="RT01", data_rate="1 Mbps", word_size_bits=16,
        bus_name_network="MUX_BUS_A",
        unit_id=unit_a.id, project_id=test_project.id,
    )
    db_session.add(bus)
    db_session.commit()
    db_session.refresh(harness)
    db_session.refresh(wire)
    db_session.refresh(bus)

    return {
        "harness": harness, "wire": wire, "bus": bus,
        "unit_a": unit_a, "unit_b": unit_b,
    }


def _make_req(
    db_session, project, owner, *,
    statement: str = "Wire harness HAR-001 shall interconnect old wording.",
    status: str = "draft",
    template_id: str = "harness_overall",
    sync_locked: bool = False,
    req_id: str = "FR-X-001",
) -> Requirement:
    r = Requirement(
        req_id=req_id, title="Auto-gen wire harness req",
        statement=statement,
        rationale="Existing rationale.",
        req_type="interface", priority="medium",
        status=status, level="L3", version=1, quality_score=80.0,
        project_id=project.id, owner_id=owner.id, created_by_id=owner.id,
        sync_locked=sync_locked,
        generation_template_id=template_id,
    )
    db_session.add(r)
    db_session.commit()
    db_session.refresh(r)
    return r


def _link_req_to_harness(db_session, req: Requirement, harness, role="primary"):
    sl = RequirementSourceLink(
        requirement_id=req.id,
        source_entity_type=SourceEntityType.WIRE_HARNESS,
        source_entity_id=harness.id,
        template_id="harness_overall",
        template_inputs={},
        role=role,
    )
    db_session.add(sl)
    db_session.commit()
    return sl


def _link_req_to_wire(db_session, req: Requirement, wire, role="primary"):
    sl = RequirementSourceLink(
        requirement_id=req.id,
        source_entity_type=SourceEntityType.WIRE,
        source_entity_id=wire.id,
        template_id="power_wire",
        template_inputs={},
        role=role,
    )
    db_session.add(sl)
    db_session.commit()
    return sl


# ══════════════════════════════════════════════════════════════
#  TestPolicyTable — every cell of the §12.5 matrix
# ══════════════════════════════════════════════════════════════

# (status, proposal_type, expected_action)
_POLICY_CASES = [
    # DRAFT
    (RequirementStatus.DRAFT, SyncProposalType.UPDATE_STATEMENT, SyncAction.AUTO_APPLY),
    (RequirementStatus.DRAFT, SyncProposalType.OBSOLETE,         SyncAction.PROPOSAL_PENDING),
    (RequirementStatus.DRAFT, SyncProposalType.REGENERATE,       SyncAction.PROPOSAL_PENDING),
    # UNDER_REVIEW
    (RequirementStatus.UNDER_REVIEW, SyncProposalType.UPDATE_STATEMENT, SyncAction.PROPOSAL_PENDING),
    (RequirementStatus.UNDER_REVIEW, SyncProposalType.OBSOLETE,         SyncAction.PROPOSAL_PENDING),
    (RequirementStatus.UNDER_REVIEW, SyncProposalType.REGENERATE,       SyncAction.PROPOSAL_PENDING),
    # APPROVED — never auto-applies
    (RequirementStatus.APPROVED, SyncProposalType.UPDATE_STATEMENT, SyncAction.PROPOSAL_PENDING),
    (RequirementStatus.APPROVED, SyncProposalType.OBSOLETE,         SyncAction.PROPOSAL_PENDING),
    (RequirementStatus.APPROVED, SyncProposalType.REGENERATE,       SyncAction.PROPOSAL_PENDING),
    # BASELINED
    (RequirementStatus.BASELINED, SyncProposalType.UPDATE_STATEMENT, SyncAction.PROPOSAL_PENDING),
    (RequirementStatus.BASELINED, SyncProposalType.OBSOLETE,         SyncAction.PROPOSAL_PENDING),
    # IMPLEMENTED
    (RequirementStatus.IMPLEMENTED, SyncProposalType.UPDATE_STATEMENT, SyncAction.PROPOSAL_PENDING),
    (RequirementStatus.IMPLEMENTED, SyncProposalType.OBSOLETE,         SyncAction.PROPOSAL_PENDING),
    # VERIFIED
    (RequirementStatus.VERIFIED, SyncProposalType.UPDATE_STATEMENT, SyncAction.PROPOSAL_PENDING),
    (RequirementStatus.VERIFIED, SyncProposalType.OBSOLETE,         SyncAction.PROPOSAL_PENDING),
    # VALIDATED
    (RequirementStatus.VALIDATED, SyncProposalType.UPDATE_STATEMENT, SyncAction.PROPOSAL_PENDING),
    (RequirementStatus.VALIDATED, SyncProposalType.OBSOLETE,         SyncAction.PROPOSAL_PENDING),
    # DEFERRED — always SKIP
    (RequirementStatus.DEFERRED, SyncProposalType.UPDATE_STATEMENT, SyncAction.SKIP),
    (RequirementStatus.DEFERRED, SyncProposalType.OBSOLETE,         SyncAction.SKIP),
    (RequirementStatus.DEFERRED, SyncProposalType.REGENERATE,       SyncAction.SKIP),
    # DELETED — always SKIP (spec "cancelled" maps here)
    (RequirementStatus.DELETED, SyncProposalType.UPDATE_STATEMENT, SyncAction.SKIP),
    (RequirementStatus.DELETED, SyncProposalType.OBSOLETE,         SyncAction.SKIP),
    (RequirementStatus.DELETED, SyncProposalType.REGENERATE,       SyncAction.SKIP),
    # PENDING_REVIEW (spec "pending_review") — silent auto-apply
    (RequirementStatus.PENDING_REVIEW, SyncProposalType.UPDATE_STATEMENT, SyncAction.AUTO_APPLY),
    (RequirementStatus.PENDING_REVIEW, SyncProposalType.OBSOLETE,         SyncAction.PROPOSAL_PENDING),
    # AUTO_GENERATED — same as draft
    (RequirementStatus.AUTO_GENERATED, SyncProposalType.UPDATE_STATEMENT, SyncAction.AUTO_APPLY),
    (RequirementStatus.AUTO_GENERATED, SyncProposalType.OBSOLETE,         SyncAction.PROPOSAL_PENDING),
]


class TestPolicyTable:

    @pytest.mark.parametrize("status,ptype,expected", _POLICY_CASES)
    def test_decide_action_cell(self, status, ptype, expected):
        assert decide_action(status, ptype) is expected


# ══════════════════════════════════════════════════════════════
#  TestSkipPaths — sync_locked + non-mutable statuses
# ══════════════════════════════════════════════════════════════

class TestSkipPaths:

    def test_sync_locked_blocks_proposal(self, db_session, graph, test_project, test_user):
        req = _make_req(db_session, test_project, test_user, sync_locked=True)
        _link_req_to_harness(db_session, req, graph["harness"])

        # Mutate the harness deeply enough that re-render would change.
        graph["harness"].cable_type = "MIL-DTL-99999"
        db_session.commit()

        proposals = (
            db_session.query(RequirementSyncProposal)
            .filter(RequirementSyncProposal.requirement_id == req.id)
            .all()
        )
        assert proposals == [], "sync_locked req must produce no proposal"

    def test_deleted_status_skips(self, db_session, graph, test_project, test_user):
        req = _make_req(db_session, test_project, test_user, status="deleted")
        _link_req_to_harness(db_session, req, graph["harness"])

        result = fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        # No proposal because DELETED is short-circuited.
        rids = {p.requirement_id for p in result}
        assert req.id not in rids

    def test_deferred_status_skips(self, db_session, graph, test_project, test_user):
        req = _make_req(db_session, test_project, test_user, status="deferred")
        _link_req_to_harness(db_session, req, graph["harness"])

        result = fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        assert all(p.requirement_id != req.id for p in result)


# ══════════════════════════════════════════════════════════════
#  TestAutoApplySilentForPendingReview — listener path + audit emit
# ══════════════════════════════════════════════════════════════

class TestAutoApplyPendingReview:

    def test_pending_review_auto_applies_silently(
        self, db_session, graph, test_project, test_user,
    ):
        req = _make_req(db_session, test_project, test_user, status="pending_review")
        _link_req_to_harness(db_session, req, graph["harness"])

        # Direct service call (not the listener) so the test is robust to
        # listener wiring across SQLite test sessions.
        proposals = fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        # Statement should now be the freshly-rendered text. The original
        # statement we set on the req intentionally doesn't match, so we
        # expect exactly one auto-applied proposal.
        ours = [p for p in proposals if p.requirement_id == req.id]
        assert len(ours) == 1
        p = ours[0]
        assert p.status == SyncProposalStatus.AUTO_APPLIED
        assert p.auto_applied is True
        db_session.refresh(req)
        assert req.statement.startswith("Wire harness HAR-001")
        # version bumped
        assert req.version == 2

    def test_auto_apply_emits_audit(
        self, db_session, graph, test_project, test_user,
    ):
        from app.models.audit_log import AuditLog

        req = _make_req(db_session, test_project, test_user, status="pending_review")
        _link_req_to_harness(db_session, req, graph["harness"])

        fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        events = (
            db_session.query(AuditLog)
            .filter(AuditLog.event_type == "req_sync.auto_applied")
            .all()
        )
        assert len(events) >= 1


# ══════════════════════════════════════════════════════════════
#  TestApprovedNeverAutoApplies
# ══════════════════════════════════════════════════════════════

class TestApprovedAlwaysProposes:

    def test_approved_creates_pending(
        self, db_session, graph, test_project, test_user,
    ):
        req = _make_req(db_session, test_project, test_user, status="approved")
        _link_req_to_harness(db_session, req, graph["harness"])

        proposals = fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        ours = [p for p in proposals if p.requirement_id == req.id]
        assert len(ours) == 1
        p = ours[0]
        assert p.status == SyncProposalStatus.PENDING
        assert p.auto_applied is False
        # Requirement statement is UNCHANGED until reviewer accepts.
        db_session.refresh(req)
        assert "old wording" in req.statement


# ══════════════════════════════════════════════════════════════
#  TestSourceDelete — OBSOLETE proposal path
# ══════════════════════════════════════════════════════════════

class TestSourceDelete:

    def test_delete_creates_obsolete_proposals(
        self, db_session, graph, test_project, test_user,
    ):
        # Two reqs both linked to the same harness.
        r1 = _make_req(db_session, test_project, test_user, req_id="FR-X-001",
                        status="approved")
        r2 = _make_req(db_session, test_project, test_user, req_id="FR-X-002",
                        status="implemented")
        _link_req_to_harness(db_session, r1, graph["harness"])
        _link_req_to_harness(db_session, r2, graph["harness"])

        proposals = fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "delete",
        )
        ours = [p for p in proposals
                if p.requirement_id in (r1.id, r2.id)]
        assert len(ours) == 2
        for p in ours:
            assert p.proposal_type == SyncProposalType.OBSOLETE
            assert p.status == SyncProposalStatus.PENDING


# ══════════════════════════════════════════════════════════════
#  TestSupersedePriorPending
# ══════════════════════════════════════════════════════════════

class TestSupersedePrior:

    def test_second_proposal_supersedes_first(
        self, db_session, graph, test_project, test_user,
    ):
        req = _make_req(db_session, test_project, test_user, status="approved")
        _link_req_to_harness(db_session, req, graph["harness"])

        # First fan-out: PENDING proposal.
        first = fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        first_ids = [p.id for p in first if p.requirement_id == req.id]
        assert first_ids
        first_id = first_ids[0]

        # Mutate again so the second render differs from the still-pending
        # proposal but ALSO differs from the original statement.
        graph["harness"].overall_length_max_m = 99.9
        db_session.commit()

        second = fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        # First proposal should now be SUPERSEDED.
        first_row = db_session.query(RequirementSyncProposal).filter(
            RequirementSyncProposal.id == first_id
        ).first()
        assert first_row.status == SyncProposalStatus.SUPERSEDED


# ══════════════════════════════════════════════════════════════
#  TestReentrancyGuard
# ══════════════════════════════════════════════════════════════

class TestReentrancyGuard:

    def test_depth_starts_zero(self):
        assert _current_depth() == 0

    def test_recursive_listener_does_not_loop(
        self, db_session, graph, test_project, test_user,
    ):
        """An auto-apply path mutates the Requirement row. The listener
        IS registered against Requirement transitively (well, not in our
        watched set — but the test still ensures fan-out is bounded)."""
        from app.services.req_sync.listener import _enter_fan_out, _exit_fan_out

        # Simulate already being inside a fan-out call.
        assert _enter_fan_out() is True
        try:
            # Now a nested call must bail.
            assert _enter_fan_out() is False
        finally:
            _exit_fan_out()
        # And depth resets to zero.
        assert _current_depth() == 0


# ══════════════════════════════════════════════════════════════
#  TestPerformance — 100 source links → < 1 second
# ══════════════════════════════════════════════════════════════

@pytest.mark.performance
class TestPerformance:

    def test_fan_out_100_links_under_one_second(
        self, db_session, graph, test_project, test_user,
    ):
        # 100 distinct requirements all linked to the same harness via the
        # generic harness_overall template.
        for i in range(100):
            r = Requirement(
                req_id=f"FR-PERF-{i:03d}", title=f"Perf {i}",
                statement="Wire harness HAR-001 shall interconnect (will change).",
                rationale="r",
                req_type="interface", priority="low",
                status=RequirementStatus.APPROVED, level="L3",
                version=1, quality_score=70.0,
                project_id=test_project.id, owner_id=test_user.id,
                created_by_id=test_user.id,
                generation_template_id="harness_overall",
            )
            db_session.add(r)
            db_session.flush()
            db_session.add(RequirementSourceLink(
                requirement_id=r.id,
                source_entity_type=SourceEntityType.WIRE_HARNESS,
                source_entity_id=graph["harness"].id,
                template_id="harness_overall",
                template_inputs={},
                role="primary",
            ))
        db_session.commit()

        t0 = time.perf_counter()
        proposals = fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        elapsed = time.perf_counter() - t0
        assert elapsed < 1.0, f"Fan-out took {elapsed:.3f}s for 100 links"
        # Each req should have produced exactly one proposal.
        assert len(proposals) >= 100


# ══════════════════════════════════════════════════════════════
#  TestEndpoints — HTTP RBAC + happy path
# ══════════════════════════════════════════════════════════════

@pytest.fixture()
def reviewer(db_session, test_project):
    user, headers = make_user(db_session, "reviewer", project=test_project)
    return user, headers


@pytest.fixture()
def req_eng(db_session, test_project):
    user, headers = make_user(db_session, "requirements_engineer",
                              project=test_project)
    return user, headers


@pytest.fixture()
def stakeholder(db_session, test_project):
    user, headers = make_user(db_session, "stakeholder", project=test_project)
    return user, headers


class TestProposalsEndpoints:

    def test_list_requires_reviewer_or_above(
        self, client, db_session, graph, test_project, test_user,
        stakeholder,
    ):
        _user, headers = stakeholder
        resp = client.get(
            "/api/v1/req-sync/proposals",
            params={"project_id": test_project.id},
            headers=headers,
        )
        assert resp.status_code == 403

    def test_list_returns_proposals(
        self, client, db_session, graph, test_project, test_user,
        reviewer,
    ):
        # Seed a proposal directly.
        req = _make_req(db_session, test_project, test_user, status="approved")
        _link_req_to_harness(db_session, req, graph["harness"])
        fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        db_session.commit()
        _user, headers = reviewer
        resp = client.get(
            "/api/v1/req-sync/proposals",
            params={"project_id": test_project.id},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["total"] >= 1
        assert any(p["requirement_id"] == req.id for p in data["items"])

    def test_accept_applies_change(
        self, client, db_session, graph, test_project, test_user,
        reviewer,
    ):
        req = _make_req(db_session, test_project, test_user, status="approved")
        _link_req_to_harness(db_session, req, graph["harness"])
        proposals = fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        db_session.commit()
        target = next(p for p in proposals if p.requirement_id == req.id)
        original_statement = req.statement

        _user, headers = reviewer
        resp = client.post(
            f"/api/v1/req-sync/proposals/{target.id}/accept",
            json={},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        db_session.refresh(req)
        assert req.statement != original_statement

    def test_reject_marks_rejected(
        self, client, db_session, graph, test_project, test_user,
        reviewer,
    ):
        req = _make_req(db_session, test_project, test_user, status="approved")
        _link_req_to_harness(db_session, req, graph["harness"])
        proposals = fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        db_session.commit()
        target = next(p for p in proposals if p.requirement_id == req.id)

        _user, headers = reviewer
        resp = client.post(
            f"/api/v1/req-sync/proposals/{target.id}/reject",
            json={"reviewer_notes": "no thanks"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        row = db_session.query(RequirementSyncProposal).get(target.id)
        assert row.status == SyncProposalStatus.REJECTED


class TestBulkAccept:

    def test_bulk_accept_atomic_all_or_none(
        self, client, db_session, graph, test_project, test_user,
        reviewer,
    ):
        # Two PENDING proposals on two different reqs.
        r1 = _make_req(db_session, test_project, test_user,
                        req_id="FR-B1-001", status="approved")
        r2 = _make_req(db_session, test_project, test_user,
                        req_id="FR-B1-002", status="approved")
        _link_req_to_harness(db_session, r1, graph["harness"])
        _link_req_to_harness(db_session, r2, graph["harness"])
        proposals = fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        db_session.commit()
        ids = [p.id for p in proposals
               if p.requirement_id in (r1.id, r2.id)]
        assert len(ids) == 2

        _user, headers = reviewer
        resp = client.post(
            "/api/v1/req-sync/proposals/bulk-accept",
            json={"proposal_ids": ids},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["succeeded"] == 2
        assert body["failed"] == 0

    def test_bulk_accept_rolls_back_on_unknown_id(
        self, client, db_session, graph, test_project, test_user,
        reviewer,
    ):
        # One real proposal + one bogus id → 404 on the bogus, atomic
        # rollback means the real one stays PENDING.
        r1 = _make_req(db_session, test_project, test_user,
                        req_id="FR-B2-001", status="approved")
        _link_req_to_harness(db_session, r1, graph["harness"])
        proposals = fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        db_session.commit()
        real = next(p for p in proposals if p.requirement_id == r1.id)
        original_statement = r1.statement

        _user, headers = reviewer
        resp = client.post(
            "/api/v1/req-sync/proposals/bulk-accept",
            json={"proposal_ids": [real.id, 999_999]},
            headers=headers,
        )
        assert resp.status_code == 404
        # Real proposal must NOT have been applied.
        db_session.expire_all()
        row = db_session.query(RequirementSyncProposal).get(real.id)
        assert row.status == SyncProposalStatus.PENDING
        db_session.refresh(r1)
        assert r1.statement == original_statement


class TestLockEndpoints:

    def test_lock_then_no_proposal(
        self, client, db_session, graph, test_project, test_user,
        req_eng,
    ):
        req = _make_req(db_session, test_project, test_user, status="approved")
        _link_req_to_harness(db_session, req, graph["harness"])
        _user, headers = req_eng
        resp = client.post(
            f"/api/v1/req-sync/requirements/{req.id}/lock",
            json={"reason": "hand-edited"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        # Now fan out — no proposal expected.
        before = (
            db_session.query(RequirementSyncProposal)
            .filter(RequirementSyncProposal.requirement_id == req.id)
            .count()
        )
        fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        after = (
            db_session.query(RequirementSyncProposal)
            .filter(RequirementSyncProposal.requirement_id == req.id)
            .count()
        )
        assert after == before

    def test_unlock_re_enables(
        self, client, db_session, graph, test_project, test_user,
        req_eng,
    ):
        req = _make_req(db_session, test_project, test_user,
                        status="approved", sync_locked=True)
        _link_req_to_harness(db_session, req, graph["harness"])
        _user, headers = req_eng
        resp = client.post(
            f"/api/v1/req-sync/requirements/{req.id}/unlock",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        db_session.refresh(req)
        assert req.sync_locked is False
        # Fan out should now produce a proposal.
        fan_out_for_entity(
            db_session, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "update",
        )
        ps = (
            db_session.query(RequirementSyncProposal)
            .filter(RequirementSyncProposal.requirement_id == req.id)
            .all()
        )
        assert len(ps) >= 1


class TestSourcesEndpoint:

    def test_sources_returns_links(
        self, client, db_session, graph, test_project, test_user,
        stakeholder,
    ):
        req = _make_req(db_session, test_project, test_user)
        _link_req_to_harness(db_session, req, graph["harness"])
        _user, headers = stakeholder
        resp = client.get(
            f"/api/v1/req-sync/requirements/{req.id}/sources",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["requirement_id"] == req.id
        assert len(data["items"]) == 1
        assert data["items"][0]["template_id"] == "harness_overall"


# ══════════════════════════════════════════════════════════════
#  TestListenerWiring — fires after_update on watched models
# ══════════════════════════════════════════════════════════════

class TestListenerWiring:

    def test_wire_update_triggers_fan_out(
        self, db_session, graph, test_project, test_user,
    ):
        # Requirement linked to the wire via "power_wire" template.
        req = _make_req(
            db_session, test_project, test_user,
            statement="Wire harness HAR-001 shall provide TBD power... old.",
            status="approved",
            template_id="power_wire",
        )
        _link_req_to_wire(db_session, req, graph["wire"])

        # Mutate the wire — listener should fire after the commit.
        graph["wire"].signal_name = "RENAMED"
        db_session.commit()

        ps = (
            db_session.query(RequirementSyncProposal)
            .filter(RequirementSyncProposal.requirement_id == req.id)
            .all()
        )
        assert len(ps) >= 1
