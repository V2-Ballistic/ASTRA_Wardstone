"""
ASTRA — Cross-project membership negative test (F-014 verification)
====================================================================
File: backend/tests/test_project_membership.py

Per remediation plan §3.7 / §8: creates two projects A and B with
disjoint memberships and asserts that a caller who is only a member of
A receives 403 Forbidden from every endpoint that takes project_id=B.id
(or an entity belonging to B).

Covers the AUDIT_FINDINGS F-014 endpoint list across every router that
was hardened in commits 449d6ad / d5e3bd2 / e0eeaa9 / a8cbbd1 / ff7e07c
/ 260058e / ac5d2e9 / cd2b794 / a26c5c1.

We assert on the exact response code 403 — not just `>= 400` — because
a bug that returns 404 (entity not found) instead of 403 (forbidden)
would be an information-disclosure leak (the caller learns that B's
entity doesn't exist *to them* vs *at all*).
"""

from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.models import (
    Baseline, Project, Requirement, SourceArtifact, TraceLink, User,
)
from app.models.project_member import ProjectMember
from app.models.interface import (
    BusDefinition, Connector, MessageDefinition, MessageField, Pin,
    PinBusAssignment, System, Unit, Wire, WireHarness,
    HarnessEndpoint, Connection, InterfaceRequirementLink,
)
from app.services.auth import create_access_token, get_password_hash


# ══════════════════════════════════════
#  Two-project fixture
# ══════════════════════════════════════


@pytest.fixture()
def two_projects(db_session):
    """
    Build two fully-populated projects A and B with disjoint
    memberships so cross-project leakage can be tested.

    Returns a dict::
        {
          "alice": (User in A only, auth headers),
          "bob_admin": (User with role=admin, auth headers),
          "carol": (User in B only, auth headers),
          "project_a": Project,
          "project_b": Project,
          "b_entities": dict of one entity per type, all in project B,
        }
    """
    # ── Users ──
    alice = User(
        username="alice", email="alice@example.com",
        hashed_password=get_password_hash("TestPass123"),
        full_name="Alice (member of A only)",
        role="requirements_engineer", department="Eng",
        is_active=True,
    )
    bob_admin = User(
        username="bob_admin", email="bob@example.com",
        hashed_password=get_password_hash("TestPass123"),
        full_name="Bob (admin — bypasses checks)",
        role="admin", department="Eng",
        is_active=True,
    )
    carol = User(
        username="carol", email="carol@example.com",
        hashed_password=get_password_hash("TestPass123"),
        full_name="Carol (member of B only)",
        role="project_manager", department="Eng",
        is_active=True,
    )
    db_session.add_all([alice, bob_admin, carol])
    db_session.commit()
    for u in (alice, bob_admin, carol):
        db_session.refresh(u)

    # ── Projects ──
    project_a = Project(code="PA", name="Project A", owner_id=alice.id, status="active")
    project_b = Project(code="PB", name="Project B", owner_id=carol.id, status="active")
    db_session.add_all([project_a, project_b])
    db_session.commit()
    db_session.refresh(project_a)
    db_session.refresh(project_b)

    # ── ProjectMember memberships ──
    db_session.add_all([
        ProjectMember(project_id=project_a.id, user_id=alice.id, added_by_id=alice.id),
        ProjectMember(project_id=project_b.id, user_id=carol.id, added_by_id=carol.id),
    ])
    db_session.commit()

    # ── One entity of every type, all in project B ──
    b_req = Requirement(
        req_id="FR-B-001", title="B Req", statement="The system shall do B within 5 seconds.",
        rationale="r", req_type="functional", priority="high", status="draft", level="L1",
        version=1, project_id=project_b.id, owner_id=carol.id, created_by_id=carol.id,
        quality_score=80.0,
    )
    b_artifact = SourceArtifact(
        artifact_id="ART-B-001", title="B Artifact", artifact_type="document",
        description="d", participants=[], project_id=project_b.id,
    )
    b_baseline = Baseline(
        name="B Baseline 1", description="d", project_id=project_b.id,
        requirements_count=0, created_by_id=carol.id,
    )
    db_session.add_all([b_req, b_artifact, b_baseline])
    db_session.commit()

    # Interface entities for B
    b_system = System(
        system_id="SYS-001", name="B System", system_type="electrical",
        project_id=project_b.id, owner_id=carol.id,
    )
    db_session.add(b_system); db_session.commit(); db_session.refresh(b_system)

    b_unit = Unit(
        unit_id="UNT-001", name="B Unit", designation="LRU-1",
        part_number="PN", manufacturer="MFG", unit_type="lru",
        system_id=b_system.id, project_id=project_b.id,
    )
    db_session.add(b_unit); db_session.commit(); db_session.refresh(b_unit)

    b_conn = Connector(
        designator="J1", connector_type="circular_plug", gender="male",
        total_contacts=4, unit_id=b_unit.id, project_id=project_b.id,
    )
    db_session.add(b_conn); db_session.commit(); db_session.refresh(b_conn)

    b_pin = Pin(
        pin_number="1", signal_name="POWER", signal_type="power",
        direction="bidirectional", connector_id=b_conn.id,
    )
    db_session.add(b_pin); db_session.commit(); db_session.refresh(b_pin)

    b_bus = BusDefinition(
        bus_id="BUS-001", name="B Bus", protocol="can_2_0b", bus_role="primary",
        unit_id=b_unit.id, project_id=project_b.id,
    )
    db_session.add(b_bus); db_session.commit(); db_session.refresh(b_bus)

    b_pa = PinBusAssignment(pin_id=b_pin.id, bus_def_id=b_bus.id, pin_role="data_high")
    db_session.add(b_pa); db_session.commit(); db_session.refresh(b_pa)

    b_msg = MessageDefinition(
        message_id="MSG-001", name="B Message", direction="transmit",
        bus_def_id=b_bus.id, project_id=project_b.id,
    )
    db_session.add(b_msg); db_session.commit(); db_session.refresh(b_msg)

    b_field = MessageField(
        field_name="payload", data_type="uint8", start_bit=0, length_bits=8,
        message_id=b_msg.id,
    )
    db_session.add(b_field); db_session.commit(); db_session.refresh(b_field)

    b_harness = WireHarness(
        harness_id="HAR-001", name="B Harness",
        from_unit_id=b_unit.id, to_unit_id=b_unit.id,
        from_connector_id=b_conn.id, to_connector_id=b_conn.id,
        project_id=project_b.id,
    )
    db_session.add(b_harness); db_session.commit(); db_session.refresh(b_harness)

    b_wire = Wire(
        wire_number="W001", from_pin_id=b_pin.id, to_pin_id=b_pin.id,
        wire_type="signal", harness_id=b_harness.id,
    )
    db_session.add(b_wire); db_session.commit(); db_session.refresh(b_wire)

    b_ep = HarnessEndpoint(
        harness_id=b_harness.id, mating_connector_id=b_conn.id,
    )
    db_session.add(b_ep); db_session.commit(); db_session.refresh(b_ep)

    b_link = InterfaceRequirementLink(
        requirement_id=b_req.id, entity_type="harness", entity_id=b_harness.id,
        link_type="satisfies", project_id=project_b.id, created_by_id=carol.id,
    )
    db_session.add(b_link); db_session.commit(); db_session.refresh(b_link)

    # Auth headers for the three users
    def _hdrs(user: User) -> dict:
        return {"Authorization": f"Bearer {create_access_token(data={'sub': user.username})}"}

    return {
        "alice": (alice, _hdrs(alice)),
        "bob_admin": (bob_admin, _hdrs(bob_admin)),
        "carol": (carol, _hdrs(carol)),
        "project_a": project_a,
        "project_b": project_b,
        "b_entities": {
            "req": b_req, "artifact": b_artifact, "baseline": b_baseline,
            "system": b_system, "unit": b_unit, "conn": b_conn, "pin": b_pin,
            "bus": b_bus, "pa": b_pa, "msg": b_msg, "field": b_field,
            "harness": b_harness, "wire": b_wire, "ep": b_ep, "link": b_link,
        },
    }


# ══════════════════════════════════════
#  Tests
# ══════════════════════════════════════


def _assert_forbidden(client: TestClient, method: str, path: str,
                      headers: dict, label: str, **kwargs):
    """Send a request and assert exactly 403 (not 404, not 422 alone)."""
    r = client.request(method, path, headers=headers, **kwargs)
    # 422 (validation error) is acceptable ONLY if the membership check
    # cannot run because of a missing required field — but for the
    # tested endpoints we always supply a valid path / query / body, so
    # 403 is the only acceptable response when the caller is not a member.
    assert r.status_code == 403, (
        f"{label}: expected 403 Forbidden, got {r.status_code} "
        f"(body={r.text[:200]})"
    )


@pytest.mark.parametrize("method,path,body_kw_factory,label", [
    # ── projects.py ──
    ("GET",    "/api/v1/projects/{B}",                                          None,  "get_project(B)"),
    ("GET",    "/api/v1/traceability/links?project_id={B}",                     None,  "list_trace_links(B)"),
    ("GET",    "/api/v1/traceability/matrix?project_id={B}",                    None,  "traceability matrix(B)"),
    ("GET",    "/api/v1/traceability/graph?project_id={B}",                     None,  "traceability graph(B)"),
    ("GET",    "/api/v1/traceability/coverage?project_id={B}",                  None,  "coverage(B)"),
    ("GET",    "/api/v1/artifacts/?project_id={B}",                             None,  "list_artifacts(B)"),
    # ── requirements.py ──
    ("GET",    "/api/v1/requirements/?project_id={B}",                          None,  "list_requirements(B)"),
    ("GET",    "/api/v1/requirements/{REQ_B}",                                  None,  "get_requirement(B-req)"),
    ("PATCH",  "/api/v1/requirements/{REQ_B}",                                  "req_update", "update_requirement(B-req)"),
    ("DELETE", "/api/v1/requirements/{REQ_B}",                                  None,  "delete_requirement(B-req)"),
    ("GET",    "/api/v1/requirements/{REQ_B}/history",                          None,  "get_history(B-req)"),
    ("GET",    "/api/v1/requirements/{REQ_B}/comments",                         None,  "get_comments(B-req)"),
    # ── baselines.py ──
    ("GET",    "/api/v1/baselines/?project_id={B}",                             None,  "list_baselines(B)"),
    ("GET",    "/api/v1/baselines/{BASELINE_B}",                                None,  "get_baseline(B-baseline)"),
    ("DELETE", "/api/v1/baselines/{BASELINE_B}",                                None,  "delete_baseline(B-baseline)"),
    # ── dashboard / impact / reports ──
    ("GET",    "/api/v1/dashboard/stats?project_id={B}",                        None,  "dashboard(B)"),
    ("GET",    "/api/v1/impact/project-risk?project_id={B}",                    None,  "project_risk(B)"),
    ("GET",    "/api/v1/impact/analyze?requirement_id={REQ_B}",                 None,  "impact analyze(B-req)"),
    ("GET",    "/api/v1/reports/traceability-matrix?project_id={B}",            None,  "report traceability(B)"),
    ("GET",    "/api/v1/reports/quality?project_id={B}",                        None,  "report quality(B)"),
    ("GET",    "/api/v1/reports/history?project_id={B}",                        None,  "report history(B)"),
    # ── interface.py — project_id-query (covered by _require_project) ──
    ("GET",    "/api/v1/interfaces/systems?project_id={B}",                     None,  "list_systems(B)"),
    ("GET",    "/api/v1/interfaces/units?project_id={B}",                       None,  "list_units(B)"),
    ("GET",    "/api/v1/interfaces/harnesses?project_id={B}",                   None,  "list_harnesses(B)"),
    ("GET",    "/api/v1/interfaces/coverage?project_id={B}",                    None,  "interface coverage(B)"),
    # ── interface.py — entity-keyed (covered in clusters A-G) ──
    ("GET",    "/api/v1/interfaces/systems/{SYS_B}",                            None,  "get_system(B-sys)"),
    ("DELETE", "/api/v1/interfaces/systems/{SYS_B}",                            None,  "delete_system(B-sys)"),
    ("GET",    "/api/v1/interfaces/units/{UNIT_B}",                             None,  "get_unit(B-unit)"),
    ("DELETE", "/api/v1/interfaces/units/{UNIT_B}",                             None,  "delete_unit(B-unit)"),
    ("GET",    "/api/v1/interfaces/connectors/{CONN_B}",                        None,  "get_connector(B-conn)"),
    ("DELETE", "/api/v1/interfaces/connectors/{CONN_B}",                        None,  "delete_connector(B-conn)"),
    ("DELETE", "/api/v1/interfaces/pins/{PIN_B}",                               None,  "delete_pin(B-pin)"),
    ("GET",    "/api/v1/interfaces/buses/{BUS_B}",                              None,  "get_bus(B-bus)"),
    ("DELETE", "/api/v1/interfaces/buses/{BUS_B}",                              None,  "delete_bus(B-bus)"),
    ("DELETE", "/api/v1/interfaces/buses/pin-assignments/{PA_B}",               None,  "remove_pin_assignment(B-pa)"),
    ("GET",    "/api/v1/interfaces/messages/{MSG_B}",                           None,  "get_message(B-msg)"),
    ("DELETE", "/api/v1/interfaces/messages/{MSG_B}",                           None,  "delete_message(B-msg)"),
    ("DELETE", "/api/v1/interfaces/fields/{FIELD_B}",                           None,  "delete_field(B-field)"),
    ("GET",    "/api/v1/interfaces/harnesses/{HAR_B}",                          None,  "get_harness(B-har)"),
    ("DELETE", "/api/v1/interfaces/harnesses/{HAR_B}",                          None,  "delete_harness(B-har)"),
    ("DELETE", "/api/v1/interfaces/wires/{WIRE_B}",                             None,  "delete_wire(B-wire)"),
    ("DELETE", "/api/v1/interfaces/endpoints/{EP_B}",                           None,  "delete_endpoint(B-ep)"),
    ("DELETE", "/api/v1/interfaces/req-links/{LINK_B}",                         None,  "delete_req_link(B-link)"),
])
def test_alice_cannot_touch_project_b(two_projects, client, method, path, body_kw_factory, label):
    """
    Alice is a member of project A only. Every endpoint that acts on
    project B (or an entity in B) must return 403 Forbidden.
    """
    _, alice_hdrs = two_projects["alice"]
    project_b = two_projects["project_b"]
    e = two_projects["b_entities"]

    # Substitute placeholders with real IDs from project B
    fmt = path.format(
        B=project_b.id,
        REQ_B=e["req"].id, BASELINE_B=e["baseline"].id,
        SYS_B=e["system"].id, UNIT_B=e["unit"].id, CONN_B=e["conn"].id,
        PIN_B=e["pin"].id, BUS_B=e["bus"].id, PA_B=e["pa"].id,
        MSG_B=e["msg"].id, FIELD_B=e["field"].id, HAR_B=e["harness"].id,
        WIRE_B=e["wire"].id, EP_B=e["ep"].id, LINK_B=e["link"].id,
    )

    body_kwargs = {}
    if body_kw_factory == "req_update":
        body_kwargs = {"json": {"title": "hacked"}}

    _assert_forbidden(client, method, fmt, alice_hdrs, label, **body_kwargs)


def test_admin_bob_bypasses_membership(two_projects, client):
    """Admin role bypasses project-membership for any project."""
    _, bob_hdrs = two_projects["bob_admin"]
    project_b = two_projects["project_b"]
    r = client.get(f"/api/v1/projects/{project_b.id}", headers=bob_hdrs)
    assert r.status_code == 200, r.text


def test_alice_can_touch_her_own_project_a(two_projects, client):
    """Sanity check: alice CAN access project A she's a member of."""
    _, alice_hdrs = two_projects["alice"]
    project_a = two_projects["project_a"]
    r = client.get(f"/api/v1/projects/{project_a.id}", headers=alice_hdrs)
    assert r.status_code == 200, r.text


def test_create_trace_link_rejects_cross_project_source(two_projects, client):
    """
    Alice tries to create a trace_link whose source is a requirement in
    project B. Must return 403 (membership check on source's project).
    """
    _, alice_hdrs = two_projects["alice"]
    e = two_projects["b_entities"]
    payload = {
        "source_type": "requirement", "source_id": e["req"].id,
        "target_type": "requirement", "target_id": e["req"].id,
        "link_type": "satisfaction",
    }
    r = client.post("/api/v1/traceability/links", json=payload, headers=alice_hdrs)
    assert r.status_code == 403, r.text


def test_bulk_delete_skips_non_member_requirements(two_projects, client):
    """
    Bulk delete with a mix of A-owned and B-owned requirement IDs:
    A-owned reqs should be processed; B-owned should be reported in
    `forbidden`. Endpoint MUST NOT 403 the whole batch — that's the
    documented behaviour from F-014 part 1.
    """
    db_session = two_projects["alice"][0].owned_projects[0].requirements  # touch ORM
    _, alice_hdrs = two_projects["alice"]
    e = two_projects["b_entities"]

    payload = {"requirement_ids": [e["req"].id]}
    r = client.post("/api/v1/requirements/bulk-delete",
                    json=payload, headers=alice_hdrs)
    # Alice has no reqs in A in this fixture — every id is from B → all forbidden
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] == 0
    assert body["forbidden"] == 1
