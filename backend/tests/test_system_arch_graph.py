"""TDD-SYSARCH-002 Phase 1 — backend graph endpoint tests.

Covers the five test cases from the prompt:
  1. test_empty_project_returns_empty_graph
  2. test_two_systems_three_units_renders_correctly
  3. test_unit_to_unit_interface_renders_as_connects_to_edge
  4. test_unauthorized_project_returns_403
  5. test_unit_with_catalog_link_includes_wpn_in_node
"""

from __future__ import annotations

from typing import Any

import pytest

from app.models import Project, User
from app.models.catalog import (
    CatalogPart,
    LifecycleStatus,
    LRUClass,
    PartClass,
    Supplier,
)
from app.models.interface import (
    Interface,
    InterfaceDirection,
    InterfaceType,
    System,
    SystemStatus,
    SystemType,
    Unit,
    UnitStatus,
    UnitType,
)


# ─────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────

def _mk_system(
    db, project_id: int, owner_id: int, *,
    name: str, sys_id: str, parent_system_id: int | None = None,
    system_type: SystemType = SystemType.SUBSYSTEM,
) -> System:
    s = System(
        system_id=sys_id,
        name=name,
        abbreviation=sys_id,
        system_type=system_type,
        status=SystemStatus.CONCEPT,
        parent_system_id=parent_system_id,
        project_id=project_id,
        owner_id=owner_id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _mk_unit(
    db, project_id: int, system_id: int, *,
    designation: str, name: str | None = None,
    unit_type: UnitType = UnitType.LRU,
    catalog_part_id: int | None = None,
) -> Unit:
    u = Unit(
        unit_id=designation,
        name=name or designation,
        designation=designation,
        part_number=designation,
        manufacturer="Test Mfg",
        unit_type=unit_type,
        status=UnitStatus.CONCEPT,
        system_id=system_id,
        project_id=project_id,
        catalog_part_id=catalog_part_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _mk_catalog_part(db, owner_id: int, *, part_number: str = "CP-12345") -> CatalogPart:
    sup = Supplier(name=f"Test Supplier for {part_number}", created_by_id=owner_id)
    db.add(sup)
    db.commit()
    cp = CatalogPart(
        supplier_id=sup.id,
        part_number=part_number,
        name=f"Catalog part {part_number}",
        part_class=PartClass.PROCESSOR,
        lru_classification=LRUClass.LRU,
        lifecycle_status=LifecycleStatus.ACTIVE,
        created_by_id=owner_id,
    )
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp


# ─────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────

def test_empty_project_returns_empty_graph(client, auth_headers, test_project):
    r = client.get(
        f"/api/v1/system-architecture/graph?project_id={test_project.id}",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body == {"systems": [], "units": [], "edges": []}


def test_two_systems_three_units_renders_correctly(
    client, auth_headers, db_session, test_user, test_project,
):
    avn = _mk_system(db_session, test_project.id, test_user.id,
                     name="Avionics", sys_id="AVN")
    pwr = _mk_system(db_session, test_project.id, test_user.id,
                     name="Power", sys_id="PWR")
    u1 = _mk_unit(db_session, test_project.id, avn.id, designation="RSP-100")
    u2 = _mk_unit(db_session, test_project.id, avn.id, designation="GPS-200")
    u3 = _mk_unit(db_session, test_project.id, pwr.id, designation="PSU-300")

    r = client.get(
        f"/api/v1/system-architecture/graph?project_id={test_project.id}",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    sys_ids = {s["id"] for s in body["systems"]}
    unit_ids = {u["id"] for u in body["units"]}
    assert sys_ids == {avn.id, pwr.id}
    assert unit_ids == {u1.id, u2.id, u3.id}

    contains_edges = [e for e in body["edges"] if e["edge_type"] == "contains"]
    assert len(contains_edges) == 3
    pairs = {(e["source"], e["target"]) for e in contains_edges}
    assert pairs == {(avn.id, u1.id), (avn.id, u2.id), (pwr.id, u3.id)}


def test_unit_to_unit_interface_renders_as_connects_to_edge(
    client, auth_headers, db_session, test_user, test_project,
):
    avn = _mk_system(db_session, test_project.id, test_user.id,
                     name="Avionics", sys_id="AVN")
    pwr = _mk_system(db_session, test_project.id, test_user.id,
                     name="Power", sys_id="PWR")
    u1 = _mk_unit(db_session, test_project.id, avn.id, designation="A1")
    u2 = _mk_unit(db_session, test_project.id, pwr.id, designation="P1")

    iface = Interface(
        interface_id="IF-001",
        name="DC supply",
        interface_type=InterfaceType.ELECTRICAL_POWER,
        direction=InterfaceDirection.BIDIRECTIONAL,
        source_system_id=pwr.id,
        target_system_id=avn.id,
        source_unit_id=u2.id,
        target_unit_id=u1.id,
        project_id=test_project.id,
        owner_id=test_user.id,
    )
    db_session.add(iface)
    db_session.commit()

    r = client.get(
        f"/api/v1/system-architecture/graph?project_id={test_project.id}",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    connects = [e for e in body["edges"] if e["edge_type"] == "connects_to"]
    assert len(connects) == 1
    edge = connects[0]
    assert {edge["source"], edge["target"]} == {u1.id, u2.id}
    assert edge["source_type"] == "unit"
    assert edge["target_type"] == "unit"
    assert edge["label"] == "DC supply"


def test_parent_of_edge_appears_for_system_hierarchy(
    client, auth_headers, db_session, test_user, test_project,
):
    parent = _mk_system(db_session, test_project.id, test_user.id,
                        name="Vehicle", sys_id="VEH",
                        system_type=SystemType.VEHICLE)
    child = _mk_system(db_session, test_project.id, test_user.id,
                       name="Avionics", sys_id="AVN",
                       parent_system_id=parent.id)

    r = client.get(
        f"/api/v1/system-architecture/graph?project_id={test_project.id}",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    parent_edges = [e for e in body["edges"] if e["edge_type"] == "parent_of"]
    assert len(parent_edges) == 1
    e = parent_edges[0]
    assert e["source"] == parent.id
    assert e["target"] == child.id


def test_unauthorized_project_returns_403(
    client, db_session, test_user, test_project,
):
    """A non-admin, non-member must get 403 from project_member_required."""
    from tests.conftest import make_user
    other_user, other_headers = make_user(
        db_session, "developer", username="outsider",
    )
    # Note: project=None — outsider is NOT a member of test_project.
    r = client.get(
        f"/api/v1/system-architecture/graph?project_id={test_project.id}",
        headers=other_headers,
    )
    assert r.status_code == 403, r.text


def test_unit_with_catalog_link_includes_wpn_in_node(
    client, auth_headers, db_session, test_user, test_project,
):
    avn = _mk_system(db_session, test_project.id, test_user.id,
                     name="Avionics", sys_id="AVN")
    cp = _mk_catalog_part(db_session, test_user.id, part_number="WS-PROC-001")
    u1 = _mk_unit(
        db_session, test_project.id, avn.id,
        designation="RSP-100",
        catalog_part_id=cp.id,
    )

    r = client.get(
        f"/api/v1/system-architecture/graph?project_id={test_project.id}",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()

    matching = [u for u in body["units"] if u["id"] == u1.id]
    assert len(matching) == 1
    node = matching[0]
    assert node["catalog_part_id"] == cp.id
    assert node["catalog_part_wpn"] == "WS-PROC-001"
