"""
ASTRA-TDD-PROJPARTS-001 (Path C) — project_parts as canonical BOM
==================================================================
File: backend/tests/test_project_part_instances.py

Covers the Phase-2 backend extensions on the (renamed-in-concept)
project_parts → BOM surface:

  1. POST with catalog_part_id (no library_part_id) succeeds.
  2. Fractional quantities (Decimal) are accepted and round-trip.
  3. (project_id, bom_position) is partial-unique when bom_position
     is supplied; NULL positions never collide.
  4. Self-referencing parent_bom_id on PATCH is rejected.
  5. GET ?part_class=… joins to catalog_parts and filters correctly.
  6. PATCH that sets unit_id emits `bom.linked_to_unit` once.
  7. GET /stats returns total + by_status + by_part_class buckets.
  8. Non-member callers get 403 on every BOM endpoint.

The fixtures (client / db_session / test_user / test_project / auth_headers)
come from conftest.py. The make_user helper provides the no-membership
caller used in the 403 test.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.models.catalog import (
    CatalogPart, LifecycleStatus, LRUClass, PartClass, Supplier,
)
from app.models.interface import (
    System, SystemStatus, SystemType, Unit, UnitStatus, UnitType,
)
from app.models.parts_library import BomStatus, ProjectPart
from tests.conftest import make_user


# ─────────────────────────────────────────────────────────────────
#  Fixtures (builders)
# ─────────────────────────────────────────────────────────────────

def _mk_supplier(db: Session, owner_id: int, *, name: str = "Acme") -> Supplier:
    s = Supplier(name=name, is_active=True, is_in_house=False, created_by_id=owner_id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _mk_catalog_part(
    db: Session, owner_id: int, *,
    supplier: Supplier,
    part_number: str,
    part_class: PartClass = PartClass.PROCESSOR,
    name: str | None = None,
) -> CatalogPart:
    cp = CatalogPart(
        supplier_id=supplier.id,
        part_number=part_number,
        name=name or f"Catalog part {part_number}",
        part_class=part_class,
        lru_classification=LRUClass.LRU,
        lifecycle_status=LifecycleStatus.ACTIVE,
        mass_kg=Decimal("0.250"),
        created_by_id=owner_id,
    )
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp


def _mk_system(db: Session, project_id: int, owner_id: int) -> System:
    s = System(
        system_id="SYS-BOM-001",
        name="BOM Test System",
        abbreviation="BTS",
        system_type=SystemType.SUBSYSTEM,
        status=SystemStatus.CONCEPT,
        project_id=project_id,
        owner_id=owner_id,
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _mk_unit(db: Session, project_id: int, system_id: int, *, designation: str = "U-001") -> Unit:
    u = Unit(
        unit_id=designation,
        name=f"Unit {designation}",
        designation=designation,
        part_number=designation,
        manufacturer="Test Mfg",
        unit_type=UnitType.LRU,
        status=UnitStatus.CONCEPT,
        system_id=system_id,
        project_id=project_id,
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


def _bom_events(db: Session, project_part_id: int, event_type: str) -> list[AuditLog]:
    return (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_type == "project_part",
            AuditLog.entity_id == project_part_id,
            AuditLog.event_type == event_type,
        )
        .order_by(AuditLog.id)
        .all()
    )


# ═════════════════════════════════════════════════════════════════
#  Tests
# ═════════════════════════════════════════════════════════════════

class TestPathCBomSurface:
    # ── 1. catalog_part_id-only create ──
    def test_create_with_catalog_part_id_only(
        self, client: TestClient, db_session: Session,
        test_user, test_project, auth_headers,
    ):
        sup = _mk_supplier(db_session, test_user.id, name="McMaster")
        cp = _mk_catalog_part(
            db_session, test_user.id, supplier=sup, part_number="WS-CPU-001",
        )
        r = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={
                "catalog_part_id": cp.id,
                "quantity": 1,
                "designation": "Primary CPU",
                "bom_position": "1.A.1",
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["library_part_id"] is None
        assert body["catalog_part_id"] == cp.id
        assert body["catalog_part_summary"]["part_number"] == "WS-CPU-001"
        assert body["catalog_part_summary"]["supplier_name"] == "McMaster"
        assert body["status"] == BomStatus.PLANNED.value
        assert body["bom_position"] == "1.A.1"
        # `bom.created` event must have been recorded
        assert _bom_events(db_session, body["id"], "bom.created"), "no bom.created"

    # ── 2. fractional quantity ──
    def test_fractional_quantity_round_trips(
        self, client: TestClient, db_session: Session,
        test_user, test_project, auth_headers,
    ):
        sup = _mk_supplier(db_session, test_user.id)
        cp = _mk_catalog_part(
            db_session, test_user.id, supplier=sup, part_number="WS-CABLE-001",
            part_class=PartClass.HARNESS,
        )
        r = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={
                "catalog_part_id": cp.id,
                "quantity": "3.5",
                "quantity_unit": "m",
                "designation": "Power cable run 1",
            },
            headers=auth_headers,
        )
        assert r.status_code == 201, r.text
        body = r.json()
        # JSON serializes Decimal as string in our responses
        assert Decimal(str(body["quantity"])) == Decimal("3.5")
        assert body["quantity_unit"] == "m"

    # ── 3. partial unique on (project_id, bom_position) ──
    def test_bom_position_partial_unique(
        self, client: TestClient, db_session: Session,
        test_user, test_project, auth_headers,
    ):
        sup = _mk_supplier(db_session, test_user.id)
        cp = _mk_catalog_part(
            db_session, test_user.id, supplier=sup, part_number="WS-BR-001",
            part_class=PartClass.STRUCTURAL_MEMBER,
        )

        # First write with explicit position succeeds.
        r1 = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={"catalog_part_id": cp.id, "bom_position": "2.B.1"},
            headers=auth_headers,
        )
        assert r1.status_code == 201, r1.text

        # Two rows with NULL bom_position must coexist (partial UNIQUE
        # only enforces uniqueness where bom_position IS NOT NULL).
        for _ in range(2):
            r_null = client.post(
                f"/api/v1/projects/{test_project.id}/parts/",
                json={"catalog_part_id": cp.id},
                headers=auth_headers,
            )
            assert r_null.status_code == 201, r_null.text

        # SQLite enforces partial unique indexes when expressed via the
        # WHERE clause in CREATE INDEX. The Alembic migration emits the
        # exact partial syntax; under SQLite the test substrate the
        # constraint is created via Base.metadata so we assert at the
        # ORM-level by attempting a direct DB insert with the same
        # bom_position and expecting an IntegrityError.
        from sqlalchemy.exc import IntegrityError
        dup = ProjectPart(
            project_id=test_project.id,
            catalog_part_id=cp.id,
            bom_position="2.B.1",
            quantity=Decimal("1"),
            quantity_unit="each",
            status=BomStatus.PLANNED,
            added_by_id=test_user.id,
        )
        db_session.add(dup)
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    # ── 4. self-referencing parent_bom_id rejected ──
    def test_parent_bom_self_reference_rejected(
        self, client: TestClient, db_session: Session,
        test_user, test_project, auth_headers,
    ):
        sup = _mk_supplier(db_session, test_user.id)
        cp = _mk_catalog_part(
            db_session, test_user.id, supplier=sup, part_number="WS-ASM-001",
        )
        r = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={"catalog_part_id": cp.id, "designation": "Top assy"},
            headers=auth_headers,
        )
        assert r.status_code == 201
        pp_id = r.json()["id"]
        bad = client.patch(
            f"/api/v1/projects/{test_project.id}/parts/{pp_id}",
            json={"parent_bom_id": pp_id},
            headers=auth_headers,
        )
        assert bad.status_code == 422
        detail = bad.json().get("detail", {})
        code = detail.get("code") if isinstance(detail, dict) else None
        assert code == "PARENT_BOM_SELF_REF"

    # ── 5. part_class filter joins through catalog_parts ──
    def test_list_filter_by_part_class(
        self, client: TestClient, db_session: Session,
        test_user, test_project, auth_headers,
    ):
        sup = _mk_supplier(db_session, test_user.id)
        cp_a = _mk_catalog_part(
            db_session, test_user.id, supplier=sup, part_number="WS-A",
            part_class=PartClass.PROCESSOR,
        )
        cp_b = _mk_catalog_part(
            db_session, test_user.id, supplier=sup, part_number="WS-B",
            part_class=PartClass.HARNESS,
        )
        for cp in (cp_a, cp_b):
            r = client.post(
                f"/api/v1/projects/{test_project.id}/parts/",
                json={"catalog_part_id": cp.id},
                headers=auth_headers,
            )
            assert r.status_code == 201

        r_cpu = client.get(
            f"/api/v1/projects/{test_project.id}/parts/"
            f"?part_class={PartClass.PROCESSOR.value}",
            headers=auth_headers,
        )
        assert r_cpu.status_code == 200, r_cpu.text
        ids = [row["catalog_part_id"] for row in r_cpu.json()]
        assert cp_a.id in ids
        assert cp_b.id not in ids

    # ── 6. unit-link emits bom.linked_to_unit ──
    def test_link_to_unit_emits_audit_event(
        self, client: TestClient, db_session: Session,
        test_user, test_project, auth_headers,
    ):
        sysrow = _mk_system(db_session, test_project.id, test_user.id)
        unit = _mk_unit(db_session, test_project.id, sysrow.id)
        sup = _mk_supplier(db_session, test_user.id)
        cp = _mk_catalog_part(
            db_session, test_user.id, supplier=sup, part_number="WS-LINK-001",
        )
        r = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={"catalog_part_id": cp.id, "designation": "Bay 1 mount"},
            headers=auth_headers,
        )
        pp_id = r.json()["id"]

        # No unit link yet → no bom.linked_to_unit event on create
        assert not _bom_events(db_session, pp_id, "bom.linked_to_unit")

        p = client.patch(
            f"/api/v1/projects/{test_project.id}/parts/{pp_id}",
            json={"unit_id": unit.id},
            headers=auth_headers,
        )
        assert p.status_code == 200, p.text
        assert p.json()["linked_unit"]["id"] == unit.id

        events = _bom_events(db_session, pp_id, "bom.linked_to_unit")
        assert len(events) == 1, f"expected 1 link event, got {len(events)}"

    # ── 7. /stats aggregates by status and part_class ──
    def test_stats_endpoint(
        self, client: TestClient, db_session: Session,
        test_user, test_project, auth_headers,
    ):
        sup = _mk_supplier(db_session, test_user.id)
        cpu = _mk_catalog_part(
            db_session, test_user.id, supplier=sup, part_number="WS-CPU-S",
            part_class=PartClass.PROCESSOR,
        )
        cbl = _mk_catalog_part(
            db_session, test_user.id, supplier=sup, part_number="WS-CBL-S",
            part_class=PartClass.HARNESS,
        )

        # 2× CPU (planned), 1× cable (released)
        for _ in range(2):
            client.post(
                f"/api/v1/projects/{test_project.id}/parts/",
                json={"catalog_part_id": cpu.id},
                headers=auth_headers,
            )
        client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={
                "catalog_part_id": cbl.id,
                "status": BomStatus.RELEASED.value,
            },
            headers=auth_headers,
        )

        r = client.get(
            f"/api/v1/projects/{test_project.id}/parts/stats",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        stats = r.json()
        assert stats["total"] == 3
        assert stats["by_status"][BomStatus.PLANNED.value] == 2
        assert stats["by_status"][BomStatus.RELEASED.value] == 1
        assert stats["by_part_class"][PartClass.PROCESSOR.value] == 2
        assert stats["by_part_class"][PartClass.HARNESS.value] == 1

    # ── 8. non-member is 403 on every endpoint ──
    def test_non_member_forbidden(
        self, client: TestClient, db_session: Session,
        test_user, test_project,
    ):
        # Stranger: created with no ProjectMember row → must hit F-014.
        _, stranger_headers = make_user(
            db_session, "developer", username="stranger", project=None,
        )

        sup = _mk_supplier(db_session, test_user.id)
        cp = _mk_catalog_part(
            db_session, test_user.id, supplier=sup, part_number="WS-403-001",
        )

        get_resp = client.get(
            f"/api/v1/projects/{test_project.id}/parts/",
            headers=stranger_headers,
        )
        assert get_resp.status_code == 403

        stats_resp = client.get(
            f"/api/v1/projects/{test_project.id}/parts/stats",
            headers=stranger_headers,
        )
        assert stats_resp.status_code == 403

        post_resp = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={"catalog_part_id": cp.id},
            headers=stranger_headers,
        )
        assert post_resp.status_code == 403
