"""TDD-SYSARCH-002 Phase 2 — UnitResponse.catalog_part_summary +
audit events on link change.
"""

from __future__ import annotations

import pytest

from app.models import User
from app.models.audit_log import AuditLog
from app.models.catalog import (
    CatalogPart,
    LifecycleStatus,
    LRUClass,
    PartClass,
    Supplier,
)
from app.models.interface import (
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

def _mk_system(db, project_id: int, owner_id: int, name: str = "Avionics") -> System:
    s = System(
        system_id="SYS-001",
        name=name,
        abbreviation="AVN",
        system_type=SystemType.SUBSYSTEM,
        status=SystemStatus.CONCEPT,
        project_id=project_id,
        owner_id=owner_id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _mk_supplier(db, owner_id: int, *, name: str = "Acme Corp", in_house: bool = False) -> Supplier:
    s = Supplier(
        name=name,
        is_active=True,
        is_in_house=in_house,
        created_by_id=owner_id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _mk_catalog_part(db, owner_id: int, *, supplier: Supplier, part_number: str) -> CatalogPart:
    cp = CatalogPart(
        supplier_id=supplier.id,
        part_number=part_number,
        name=f"Catalog part {part_number}",
        part_class=PartClass.PROCESSOR,
        lru_classification=LRUClass.LRU,
        lifecycle_status=LifecycleStatus.ACTIVE,
        mass_kg=0.5,
        created_by_id=owner_id,
    )
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp


def _mk_unit(
    db, project_id: int, system_id: int, *,
    designation: str = "RSP-100", catalog_part_id: int | None = None,
) -> Unit:
    u = Unit(
        unit_id=designation,
        name=designation,
        designation=designation,
        part_number=designation,
        manufacturer="Test Mfg",
        unit_type=UnitType.LRU,
        status=UnitStatus.CONCEPT,
        system_id=system_id,
        project_id=project_id,
        catalog_part_id=catalog_part_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


# ─────────────────────────────────────────────────────────────────
#  catalog_part_summary on Unit responses
# ─────────────────────────────────────────────────────────────────

def test_unit_response_includes_catalog_summary_when_linked(
    client, auth_headers, db_session, test_user, test_project,
):
    sysrow = _mk_system(db_session, test_project.id, test_user.id)
    sup = _mk_supplier(db_session, test_user.id, name="McMaster-Carr")
    cp = _mk_catalog_part(db_session, test_user.id, supplier=sup, part_number="WS-PROC-001")
    u = _mk_unit(db_session, test_project.id, sysrow.id, catalog_part_id=cp.id)

    r = client.get(f"/api/v1/interfaces/units/{u.id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()

    assert body["catalog_part_id"] == cp.id
    summary = body["catalog_part_summary"]
    assert summary is not None
    assert summary["id"] == cp.id
    assert summary["part_number"] == "WS-PROC-001"
    assert summary["name"] == cp.name
    assert summary["mass_kg"] == 0.5
    assert summary["supplier_name"] == "McMaster-Carr"
    assert summary["supplier_is_in_house"] is False


def test_unit_response_summary_is_null_when_unlinked(
    client, auth_headers, db_session, test_user, test_project,
):
    sysrow = _mk_system(db_session, test_project.id, test_user.id)
    u = _mk_unit(db_session, test_project.id, sysrow.id)

    r = client.get(f"/api/v1/interfaces/units/{u.id}", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["catalog_part_id"] is None
    assert body["catalog_part_summary"] is None


# ─────────────────────────────────────────────────────────────────
#  Audit events on link change
# ─────────────────────────────────────────────────────────────────

def _audit_actions_for_unit(db, unit_id: int) -> list[str]:
    """AuditLog uses ``event_type`` (not ``action``) — see column list."""
    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "unit",
            AuditLog.entity_id == unit_id,
        )
        .order_by(AuditLog.id)
        .all()
    )
    return [r.event_type for r in rows]


def test_audit_emits_link_event_on_first_link(
    client, auth_headers, db_session, test_user, test_project,
):
    sysrow = _mk_system(db_session, test_project.id, test_user.id)
    sup = _mk_supplier(db_session, test_user.id)
    cp = _mk_catalog_part(db_session, test_user.id, supplier=sup, part_number="WS-PROC-002")
    u = _mk_unit(db_session, test_project.id, sysrow.id)
    assert u.catalog_part_id is None

    r = client.patch(
        f"/api/v1/interfaces/units/{u.id}",
        json={"catalog_part_id": cp.id},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    actions = _audit_actions_for_unit(db_session, u.id)
    assert "unit.linked_to_catalog" in actions


def test_audit_emits_change_event_on_relink(
    client, auth_headers, db_session, test_user, test_project,
):
    sysrow = _mk_system(db_session, test_project.id, test_user.id)
    sup = _mk_supplier(db_session, test_user.id)
    cp1 = _mk_catalog_part(db_session, test_user.id, supplier=sup, part_number="WS-PROC-AAA")
    cp2 = _mk_catalog_part(db_session, test_user.id, supplier=sup, part_number="WS-PROC-BBB")
    u = _mk_unit(db_session, test_project.id, sysrow.id, catalog_part_id=cp1.id)

    r = client.patch(
        f"/api/v1/interfaces/units/{u.id}",
        json={"catalog_part_id": cp2.id},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text

    actions = _audit_actions_for_unit(db_session, u.id)
    assert "unit.catalog_link_changed" in actions


def test_audit_emits_unlink_event_on_clear(
    client, auth_headers, db_session, test_user, test_project,
):
    sysrow = _mk_system(db_session, test_project.id, test_user.id)
    sup = _mk_supplier(db_session, test_user.id)
    cp = _mk_catalog_part(db_session, test_user.id, supplier=sup, part_number="WS-PROC-Z")
    u = _mk_unit(db_session, test_project.id, sysrow.id, catalog_part_id=cp.id)

    r = client.patch(
        f"/api/v1/interfaces/units/{u.id}",
        json={"catalog_part_id": None},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["catalog_part_id"] is None
    assert body["catalog_part_summary"] is None

    actions = _audit_actions_for_unit(db_session, u.id)
    assert "unit.unlinked_from_catalog" in actions


# ─────────────────────────────────────────────────────────────────
#  linked_to_catalog filter
# ─────────────────────────────────────────────────────────────────

def test_units_list_filter_linked_to_catalog_true(
    client, auth_headers, db_session, test_user, test_project,
):
    sysrow = _mk_system(db_session, test_project.id, test_user.id)
    sup = _mk_supplier(db_session, test_user.id)
    cp = _mk_catalog_part(db_session, test_user.id, supplier=sup, part_number="WS-LINKED-1")
    linked = _mk_unit(db_session, test_project.id, sysrow.id,
                      designation="LINKED-1", catalog_part_id=cp.id)
    _mk_unit(db_session, test_project.id, sysrow.id, designation="UNLINKED-1")

    r = client.get(
        f"/api/v1/interfaces/units"
        f"?project_id={test_project.id}&linked_to_catalog=true",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()}
    assert linked.id in ids
    # Only linked units appear
    for row in r.json():
        assert row["catalog_part_id"] is not None


def test_units_list_filter_linked_to_catalog_false(
    client, auth_headers, db_session, test_user, test_project,
):
    sysrow = _mk_system(db_session, test_project.id, test_user.id)
    sup = _mk_supplier(db_session, test_user.id)
    cp = _mk_catalog_part(db_session, test_user.id, supplier=sup, part_number="WS-LINKED-2")
    _mk_unit(db_session, test_project.id, sysrow.id,
             designation="LINKED-A", catalog_part_id=cp.id)
    unlinked = _mk_unit(db_session, test_project.id, sysrow.id, designation="UNLINKED-A")

    r = client.get(
        f"/api/v1/interfaces/units"
        f"?project_id={test_project.id}&linked_to_catalog=false",
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    ids = {row["id"] for row in r.json()}
    assert unlinked.id in ids
    for row in r.json():
        assert row["catalog_part_id"] is None
