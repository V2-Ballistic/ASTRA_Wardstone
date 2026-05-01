"""
ASTRA — Audit-emission cluster tests (Phase 3C: F-049 + F-050 + F-080)
=======================================================================
File: backend/tests/test_audit_emission_3c.py

Covers the three behaviour changes that landed under the 3C audit-emission
cluster. Pre-fix all three were silent failures: they did the right thing
to the row but left no breadcrumb for forensics.

  F-049 — patching a wire's pin endpoints emits ``wire.endpoints_changed``
  F-050 — creating/deleting an interface_req_link emits the matching
          ``interface_req_link.created`` / ``.deleted`` event
  F-080 — record_event called outside an HTTP request stamps
          ``action_detail.context = "cron"`` and the host name
"""

from __future__ import annotations

import pytest
from app.models.audit_log import AuditLog
from app.models.interface import (
    System, Unit, Connector, Pin, WireHarness, Wire,
    InterfaceRequirementLink,
)
from app.services.audit_service import record_event


# ══════════════════════════════════════════════════════════════
#  Fixtures (minimal — re-used across the three tests)
# ══════════════════════════════════════════════════════════════

@pytest.fixture()
def two_units_with_pins(db_session, test_user, test_project):
    """Two units with one connector each, two pins per connector. Returns
    (unit_a, unit_b, conn_a, conn_b, pins_a, pins_b)."""
    sys_ = System(
        system_id="SYS-AE", name="Audit-Emit Sys", system_type="subsystem",
        project_id=test_project.id, owner_id=test_user.id,
    )
    db_session.add(sys_)
    db_session.commit()

    units = []
    conns = []
    pin_groups = []
    for ix, designation in enumerate(["UNIT-A", "UNIT-B"]):
        u = Unit(
            unit_id=f"UNIT-{ix:03d}", project_id=test_project.id,
            system_id=sys_.id, name=f"Unit {designation}",
            designation=designation, part_number=f"PN-{ix}",
            manufacturer="Test", unit_type="lru",
        )
        db_session.add(u)
        db_session.flush()

        c = Connector(
            unit_id=u.id, project_id=test_project.id,
            designator=f"J{ix+1}", connector_type="d_sub_9",
            gender="female_socket", total_contacts=2,
        )
        db_session.add(c)
        db_session.flush()

        pins = []
        for n in (1, 2):
            p = Pin(connector_id=c.id, pin_number=str(n), signal_name=f"S{ix}{n}",
                    signal_type="signal_digital_single", direction="output")
            db_session.add(p)
            pins.append(p)
        db_session.flush()

        units.append(u)
        conns.append(c)
        pin_groups.append(pins)

    db_session.commit()
    return (units[0], units[1], conns[0], conns[1], pin_groups[0], pin_groups[1])


@pytest.fixture()
def harness_with_wire(db_session, test_user, test_project, two_units_with_pins):
    unit_a, unit_b, conn_a, conn_b, pins_a, pins_b = two_units_with_pins
    h = WireHarness(
        harness_id="HAR-AE", project_id=test_project.id,
        name="Test Harness", from_unit_id=unit_a.id,
        from_connector_id=conn_a.id, to_unit_id=unit_b.id,
        to_connector_id=conn_b.id, status="concept",
    )
    db_session.add(h)
    db_session.flush()

    w = Wire(
        harness_id=h.id, wire_number="W001", signal_name="SIG_1",
        wire_type="signal_single",
        from_pin_id=pins_a[0].id, to_pin_id=pins_b[0].id,
    )
    db_session.add(w)
    db_session.commit()
    db_session.refresh(w)
    return (h, w, pins_a, pins_b)


# ══════════════════════════════════════════════════════════════
#  F-049: wire endpoint change emits audit
# ══════════════════════════════════════════════════════════════

def test_wire_pin_change_emits_audit(client, auth_headers, db_session, harness_with_wire):
    h, w, pins_a, pins_b = harness_with_wire
    before = db_session.query(AuditLog).filter(AuditLog.event_type == "wire.endpoints_changed").count()

    resp = client.patch(
        f"/api/v1/interfaces/wires/{w.id}",
        json={"from_pin_id": pins_a[1].id},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    after = db_session.query(AuditLog).filter(AuditLog.event_type == "wire.endpoints_changed").count()
    assert after == before + 1


def test_wire_non_pin_update_does_not_emit_endpoint_audit(
    client, auth_headers, db_session, harness_with_wire,
):
    h, w, pins_a, pins_b = harness_with_wire
    before = db_session.query(AuditLog).filter(AuditLog.event_type == "wire.endpoints_changed").count()

    # Change a non-pin field — the rollup is unaffected so no audit row.
    resp = client.patch(
        f"/api/v1/interfaces/wires/{w.id}",
        json={"signal_name": "RENAMED_SIG"},
        headers=auth_headers,
    )
    assert resp.status_code == 200, resp.text

    after = db_session.query(AuditLog).filter(AuditLog.event_type == "wire.endpoints_changed").count()
    assert after == before


# ══════════════════════════════════════════════════════════════
#  F-050: interface_req_link create/delete audit
# ══════════════════════════════════════════════════════════════

def test_req_link_create_and_delete_emit_audit(
    client, auth_headers, db_session, test_requirement, two_units_with_pins,
):
    unit_a, *_ = two_units_with_pins

    before_create = db_session.query(AuditLog).filter(
        AuditLog.event_type == "interface_req_link.created"
    ).count()
    before_delete = db_session.query(AuditLog).filter(
        AuditLog.event_type == "interface_req_link.deleted"
    ).count()

    resp = client.post(
        "/api/v1/interfaces/req-links",
        json={
            "requirement_id": test_requirement.id,
            "entity_type": "unit",
            "entity_id": unit_a.id,
            "link_type": "satisfies",
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, resp.text
    link_id = resp.json()["id"]

    after_create = db_session.query(AuditLog).filter(
        AuditLog.event_type == "interface_req_link.created"
    ).count()
    assert after_create == before_create + 1

    resp = client.delete(f"/api/v1/interfaces/req-links/{link_id}", headers=auth_headers)
    assert resp.status_code == 200, resp.text

    after_delete = db_session.query(AuditLog).filter(
        AuditLog.event_type == "interface_req_link.deleted"
    ).count()
    assert after_delete == before_delete + 1

    # The deleted-link audit row carries the snapshot fields so a
    # forensic reader can reconstruct what was broken.
    last = (
        db_session.query(AuditLog)
        .filter(AuditLog.event_type == "interface_req_link.deleted")
        .order_by(AuditLog.id.desc())
        .first()
    )
    assert last.action_detail["entity_type"] == "unit"
    assert last.action_detail["entity_id"] == unit_a.id


# ══════════════════════════════════════════════════════════════
#  F-080: cron-driven record_event stamps context+host
# ══════════════════════════════════════════════════════════════

def test_record_event_outside_request_stamps_cron_context(db_session, test_user, test_project):
    # Calling record_event without an HTTP request and without a stashed
    # request context (i.e. from a cron worker) — both user_ip and
    # user_agent end up empty, which is the trigger for the F-080 stamp.
    entry = record_event(
        db_session, "test.cron_event", "project", test_project.id, test_user.id,
        action_detail={"foo": "bar"}, project_id=test_project.id, request=None,
    )
    assert entry.action_detail["context"] == "cron"
    assert entry.action_detail.get("host"), "host should be the gethostname() value"
    # The original keys still survive the stamping.
    assert entry.action_detail["foo"] == "bar"
