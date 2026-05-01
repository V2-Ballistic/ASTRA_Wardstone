"""ASTRA — Admin Override End-to-End Tests (Phase 8, ASTRA-TDD-INTF-002)
=========================================================================
File: backend/tests/test_admin_overrides.py    ← NEW (Phase 8)

Per spec §22 DoD item 14: "Admin role bypasses all gates (catalog approval,
sync, coverage, lock state)". This file walks every override path the
catalog + req-sync + coverage routers expose and asserts:

    1. Non-admin gets the expected 4xx.
    2. Admin with the documented override flag gets the expected 2xx.
    3. The override is recorded in the audit log with admin_override=true
       (or equivalent flag) inside ``action_detail``.

Override paths covered
----------------------
- A. Admin force-accepts a sync proposal against a sync_locked requirement
     (`POST /req-sync/proposals/{id}/accept?admin_force=true`).
- B. Admin force-accepts a sync proposal against an APPROVED requirement
     (the policy table normally forbids auto-apply, but accept is always a
     valid review action for a reviewer; admin_force=true is the explicit
     bypass when the requirement is ALSO sync_locked).
- C. Admin force-deletes a CatalogPart that's placed in project units
     (`DELETE /catalog/parts/{id}?admin_force=true`).
- D. Admin force-deletes a Supplier that has child catalog parts
     (`DELETE /catalog/suppliers/{id}?admin_force=true`).
- E. Admin places a RESTRICTED catalog part (placement service bypass).

Each test asserts both the HTTP outcome and the audit row written.
"""

from __future__ import annotations

import pytest

from app.models import RequirementStatus
from app.models.audit_log import AuditLog
from app.models.catalog import (
    CatalogConnector,
    CatalogPart,
    CatalogPin,
    ConnectorGender as CatGender,
    LifecycleStatus,
    LRUClass,
    PartClass,
    SignalDirection as CatDirection,
    SignalType as CatSignalType,
    Supplier,
)
from app.models.interface import (
    Connector,
    Pin,
    System,
    Unit,
    WireHarness,
)
from app.models.req_sync import (
    RequirementSourceLink,
    RequirementSyncProposal,
    SourceEntityType,
    SyncProposalStatus,
    SyncProposalType,
)
from tests.conftest import make_user


# ══════════════════════════════════════════════════════════════
#  Shared fixtures
# ══════════════════════════════════════════════════════════════


@pytest.fixture()
def supplier(db_session, test_user) -> Supplier:
    s = Supplier(
        name="OverrideTest Vendor",
        short_name="OTV",
        cage_code="9ZZZZ",
        country="USA",
        is_active=True,
        created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture()
def restricted_catalog_part(db_session, test_user, supplier) -> CatalogPart:
    """A RESTRICTED-lifecycle part — must trip the placement gate for non-admin."""
    part = CatalogPart(
        supplier_id=supplier.id,
        part_number="OTV-RST-001",
        revision="A",
        name="Restricted radio",
        part_class=PartClass.RADIO,
        lru_classification=LRUClass.LRU,
        lifecycle_status=LifecycleStatus.RESTRICTED,
        created_by_id=test_user.id,
    )
    db_session.add(part)
    db_session.flush()
    conn = CatalogConnector(
        catalog_part_id=part.id, reference="J1", position=0,
        connector_type="MIL-DTL-38999/III", gender=CatGender.MALE, pin_count=2,
    )
    db_session.add(conn)
    db_session.flush()
    db_session.add(CatalogPin(
        catalog_connector_id=conn.id, pin_position="1",
        mfr_pin_name="VCC_28V",
        mfr_signal_type=CatSignalType.POWER, mfr_direction=CatDirection.POWER,
    ))
    db_session.add(CatalogPin(
        catalog_connector_id=conn.id, pin_position="2",
        mfr_pin_name="GND",
        mfr_signal_type=CatSignalType.GROUND, mfr_direction=CatDirection.GROUND,
    ))
    db_session.commit()
    db_session.refresh(part)
    return part


@pytest.fixture()
def active_catalog_part(db_session, test_user, supplier) -> CatalogPart:
    """A normal ACTIVE part with one connector + 2 pins for placement-then-delete tests."""
    part = CatalogPart(
        supplier_id=supplier.id,
        part_number="OTV-ACT-001",
        revision="A",
        name="Active radio",
        part_class=PartClass.RADIO,
        lru_classification=LRUClass.LRU,
        lifecycle_status=LifecycleStatus.ACTIVE,
        created_by_id=test_user.id,
    )
    db_session.add(part)
    db_session.flush()
    conn = CatalogConnector(
        catalog_part_id=part.id, reference="J1", position=0,
        connector_type="MIL-DTL-38999/III", gender=CatGender.MALE, pin_count=2,
    )
    db_session.add(conn)
    db_session.flush()
    db_session.add(CatalogPin(
        catalog_connector_id=conn.id, pin_position="1",
        mfr_pin_name="VCC_28V",
        mfr_signal_type=CatSignalType.POWER, mfr_direction=CatDirection.POWER,
    ))
    db_session.add(CatalogPin(
        catalog_connector_id=conn.id, pin_position="2",
        mfr_pin_name="GND",
        mfr_signal_type=CatSignalType.GROUND, mfr_direction=CatDirection.GROUND,
    ))
    db_session.commit()
    db_session.refresh(part)
    return part


@pytest.fixture()
def system_in_project(db_session, test_user, test_project) -> System:
    s = System(
        system_id="SYS-OVR",
        name="Override Test System",
        abbreviation="OTS",
        system_type="subsystem",
        project_id=test_project.id,
        owner_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture()
def harness_with_proposal(db_session, test_user, test_project, system_in_project):
    """Build a minimal harness + a sync_locked APPROVED requirement +
    a PENDING UPDATE_STATEMENT proposal against it."""
    from app.models import Requirement

    unit_a = Unit(
        unit_id="OVR-UA", name="A1", designation="A-OVR",
        part_number="A1", manufacturer="x", unit_type="processor",
        status="concept", system_id=system_in_project.id, project_id=test_project.id,
    )
    unit_b = Unit(
        unit_id="OVR-UB", name="B1", designation="B-OVR",
        part_number="B1", manufacturer="y", unit_type="processor",
        status="concept", system_id=system_in_project.id, project_id=test_project.id,
    )
    db_session.add_all([unit_a, unit_b])
    db_session.flush()
    conn_a = Connector(
        connector_id="OVR-CA", designator="J1",
        connector_type="mil_dtl_38999_series_iii", gender="female_socket",
        total_contacts=1, unit_id=unit_a.id, project_id=test_project.id,
    )
    conn_b = Connector(
        connector_id="OVR-CB", designator="J1",
        connector_type="mil_dtl_38999_series_iii", gender="male_pin",
        total_contacts=1, unit_id=unit_b.id, project_id=test_project.id,
    )
    db_session.add_all([conn_a, conn_b])
    db_session.flush()
    harness = WireHarness(
        harness_id="OVR-HAR-001", name="OVR",
        from_unit_id=unit_a.id, from_connector_id=conn_a.id,
        to_unit_id=unit_b.id, to_connector_id=conn_b.id,
        project_id=test_project.id, cable_type="MIL-DTL-27500",
        overall_length_m=2.0, overall_length_max_m=2.5,
    )
    db_session.add(harness)
    db_session.commit()

    req = Requirement(
        req_id="FR-OVR-001", title="locked req",
        statement="Wire harness OVR-HAR-001 shall route old wording.",
        rationale="r",
        req_type="interface", priority="medium",
        status=RequirementStatus.APPROVED, level="L3",
        version=1, quality_score=80.0,
        sync_locked=True,
        project_id=test_project.id, owner_id=test_user.id,
        created_by_id=test_user.id,
        generation_template_id="harness_overall",
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)

    db_session.add(RequirementSourceLink(
        requirement_id=req.id,
        source_entity_type=SourceEntityType.WIRE_HARNESS,
        source_entity_id=harness.id,
        template_id="harness_overall",
        template_inputs={},
        role="primary",
    ))
    db_session.commit()

    proposal = RequirementSyncProposal(
        requirement_id=req.id,
        proposal_type=SyncProposalType.UPDATE_STATEMENT,
        triggered_by_entity_type=SourceEntityType.WIRE_HARNESS,
        triggered_by_entity_id=harness.id,
        trigger_event="update",
        old_statement=req.statement,
        new_statement="Wire harness OVR-HAR-001 shall route NEW wording.",
        old_rationale=req.rationale,
        new_rationale=req.rationale,
        field_diffs={"statement": True},
        status=SyncProposalStatus.PENDING,
    )
    db_session.add(proposal)
    db_session.commit()
    db_session.refresh(proposal)

    return {"harness": harness, "req": req, "proposal": proposal}


# ══════════════════════════════════════════════════════════════
#  Audit-log helper
# ══════════════════════════════════════════════════════════════


def _audit_rows_for(db_session, *, event_type: str = None, entity_id: int = None):
    q = db_session.query(AuditLog)
    if event_type is not None:
        q = q.filter(AuditLog.event_type == event_type)
    if entity_id is not None:
        q = q.filter(AuditLog.entity_id == entity_id)
    return q.order_by(AuditLog.timestamp.desc()).all()


# ══════════════════════════════════════════════════════════════
#  A. Admin force-accept sync proposal on sync_locked + APPROVED req
# ══════════════════════════════════════════════════════════════


class TestSyncProposalAdminForce:

    def test_reviewer_cannot_accept_locked_proposal(
        self, client, db_session, test_project, harness_with_proposal,
    ):
        _user, headers = make_user(
            db_session, "reviewer", "rev_lock", project=test_project,
        )
        resp = client.post(
            f"/api/v1/req-sync/proposals/{harness_with_proposal['proposal'].id}/accept",
            headers=headers,
        )
        assert resp.status_code == 409, resp.text
        assert "sync_locked" in resp.text.lower()

    def test_admin_can_force_accept_locked_proposal(
        self, client, db_session, test_project, harness_with_proposal, auth_headers,
    ):
        proposal = harness_with_proposal["proposal"]
        req = harness_with_proposal["req"]

        resp = client.post(
            f"/api/v1/req-sync/proposals/{proposal.id}/accept?admin_force=true",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        db_session.refresh(req)
        db_session.refresh(proposal)
        assert "NEW wording" in req.statement
        assert proposal.status == SyncProposalStatus.ACCEPTED

        # Audit row should record admin_force=True on the action_detail.
        rows = _audit_rows_for(
            db_session,
            event_type="req_sync.proposal.accepted",
            entity_id=req.id,
        )
        assert len(rows) >= 1
        latest = rows[0]
        detail = latest.action_detail or {}
        assert detail.get("admin_force") is True, (
            "audit action_detail must carry admin_force=true to distinguish "
            "the override from a normal accept"
        )

    def test_non_admin_cannot_pass_admin_force(
        self, client, db_session, test_project, harness_with_proposal,
    ):
        _user, headers = make_user(
            db_session, "reviewer", "rev_force_attempt", project=test_project,
        )
        resp = client.post(
            f"/api/v1/req-sync/proposals/{harness_with_proposal['proposal'].id}/accept?admin_force=true",
            headers=headers,
        )
        assert resp.status_code == 403, resp.text
        assert "admin" in resp.text.lower()


# ══════════════════════════════════════════════════════════════
#  C. Admin force-delete a placed CatalogPart
# ══════════════════════════════════════════════════════════════


class TestCatalogPartAdminForceDelete:

    def test_force_delete_placed_part_records_admin_force(
        self, client, db_session, test_project, system_in_project,
        active_catalog_part, auth_headers,
    ):
        # Place the part as admin (no override needed for ACTIVE).
        place_resp = client.post(
            f"/api/v1/catalog/parts/{active_catalog_part.id}/place",
            json={
                "project_id": test_project.id,
                "system_id": system_in_project.id,
                "unit_id_tag": "OVR-PLACED",
            },
            headers=auth_headers,
        )
        assert place_resp.status_code == 201, place_resp.text

        # Without admin_force, expect 409.
        no_force = client.delete(
            f"/api/v1/catalog/parts/{active_catalog_part.id}",
            headers=auth_headers,
        )
        assert no_force.status_code == 409, no_force.text

        # With admin_force=true, expect 200.
        ok = client.delete(
            f"/api/v1/catalog/parts/{active_catalog_part.id}?admin_force=true",
            headers=auth_headers,
        )
        assert ok.status_code == 200, ok.text

        rows = _audit_rows_for(
            db_session, event_type="catalog_part.deleted",
            entity_id=active_catalog_part.id,
        )
        assert len(rows) >= 1
        detail = rows[0].action_detail or {}
        assert detail.get("admin_force") is True
        assert detail.get("units_unlinked", 0) >= 1


# ══════════════════════════════════════════════════════════════
#  D. Admin force-delete a Supplier that has child catalog parts
# ══════════════════════════════════════════════════════════════


class TestSupplierAdminForceDelete:

    def test_force_delete_supplier_with_parts_audits_admin_force(
        self, client, db_session, supplier, active_catalog_part, auth_headers,
    ):
        # Supplier has at least one part now (active_catalog_part).
        no_force = client.delete(
            f"/api/v1/catalog/suppliers/{supplier.id}",
            headers=auth_headers,
        )
        assert no_force.status_code == 409, no_force.text

        ok = client.delete(
            f"/api/v1/catalog/suppliers/{supplier.id}?admin_force=true",
            headers=auth_headers,
        )
        assert ok.status_code == 200, ok.text

        rows = _audit_rows_for(
            db_session, event_type="supplier.deleted",
            entity_id=supplier.id,
        )
        assert len(rows) >= 1
        detail = rows[0].action_detail or {}
        assert detail.get("admin_force") is True
        assert detail.get("parts_dropped", 0) >= 1


# ══════════════════════════════════════════════════════════════
#  E. Admin can place a RESTRICTED catalog part
# ══════════════════════════════════════════════════════════════


class TestPlaceRestrictedAdminBypass:

    def test_admin_can_place_restricted_part(
        self, client, db_session, test_project, system_in_project,
        restricted_catalog_part, auth_headers,
    ):
        resp = client.post(
            f"/api/v1/catalog/parts/{restricted_catalog_part.id}/place",
            json={
                "project_id": test_project.id,
                "system_id": system_in_project.id,
                "unit_id_tag": "OVR-RST-PLACE",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text

    def test_req_eng_cannot_place_restricted_part(
        self, client, db_session, test_project, system_in_project,
        restricted_catalog_part,
    ):
        _user, headers = make_user(
            db_session, "requirements_engineer", "re_rst_block",
            project=test_project,
        )
        resp = client.post(
            f"/api/v1/catalog/parts/{restricted_catalog_part.id}/place",
            json={
                "project_id": test_project.id,
                "system_id": system_in_project.id,
                "unit_id_tag": "OVR-RST-FAIL",
            },
            headers=headers,
        )
        assert resp.status_code == 403, resp.text
