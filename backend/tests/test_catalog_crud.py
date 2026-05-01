"""
ASTRA — Catalog CRUD + Placement Tests
========================================
File: backend/tests/test_catalog_crud.py   ← NEW (Phase 2, ASTRA-TDD-INTF-002)

Covers spec §17 Phase 2 acceptance for the catalog router + placement
service. Each class corresponds to one acceptance criterion or a tightly
related cluster.

Test fixtures use enum constants (PartClass.PROCESSOR etc.) per the
phase prompt — no raw strings for catalog enum payloads.

Test isolation: every supplier-document upload uses ``tmp_path`` via the
``patch_supplier_doc_dir`` fixture so we never write into the real
``/data/supplier_docs/`` directory and tests don't interfere with each
other on a shared volume.
"""

from __future__ import annotations

import io
import uuid
from pathlib import Path

import pytest

from app.models import UserRole
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
    SupplierDocument,
    SupplierDocumentType,
)
from app.models.interface import Connector, Pin, Unit
from app.routers import catalog as catalog_router
from tests.conftest import make_user


# ══════════════════════════════════════════════════════════════
#  Shared fixtures
# ══════════════════════════════════════════════════════════════

@pytest.fixture(autouse=True)
def patch_supplier_doc_dir(monkeypatch, tmp_path):
    """Redirect supplier-document storage to a per-test tmp directory."""
    monkeypatch.setattr(catalog_router, "SUPPLIER_DOC_DIR", tmp_path / "supplier_docs")


@pytest.fixture()
def supplier(db_session, test_user) -> Supplier:
    s = Supplier(
        name="Raytheon Test",
        short_name="RTN",
        cage_code="00ABC",
        country="USA",
        is_active=True,
        created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture()
def catalog_part(db_session, test_user, supplier) -> CatalogPart:
    """A simple ACTIVE part with one connector (2 pins) — enough for placement."""
    part = CatalogPart(
        supplier_id=supplier.id,
        part_number="RSP-100",
        revision="A",
        name="Radar Signal Processor",
        designation="RSP-100",
        part_class=PartClass.PROCESSOR,
        lru_classification=LRUClass.LRU,
        lifecycle_status=LifecycleStatus.ACTIVE,
        mass_kg=2.3,
        power_watts_nominal=45.0,
        temp_operating_min_c=-40.0,
        temp_operating_max_c=85.0,
        created_by_id=test_user.id,
    )
    db_session.add(part)
    db_session.flush()
    conn = CatalogConnector(
        catalog_part_id=part.id,
        reference="J1",
        position=0,
        description="Primary IO",
        connector_type="MIL-DTL-38999/III",
        gender=CatGender.FEMALE,
        pin_count=2,
    )
    db_session.add(conn)
    db_session.flush()
    pins = [
        CatalogPin(
            catalog_connector_id=conn.id,
            pin_position="1",
            mfr_pin_name="VCC_28V",
            mfr_signal_type=CatSignalType.POWER,
            mfr_direction=CatDirection.POWER,
            mfr_voltage_min_v=22.0,
            mfr_voltage_max_v=32.0,
        ),
        CatalogPin(
            catalog_connector_id=conn.id,
            pin_position="2",
            mfr_pin_name="GND",
            mfr_signal_type=CatSignalType.GROUND,
            mfr_direction=CatDirection.GROUND,
        ),
    ]
    for p in pins:
        db_session.add(p)
    db_session.commit()
    db_session.refresh(part)
    return part


@pytest.fixture()
def system_in_project(db_session, test_user, test_project):
    from app.models.interface import System
    s = System(
        system_id="SYS-001",
        name="Radar",
        abbreviation="RDR",
        system_type="subsystem",
        project_id=test_project.id,
        owner_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


# ══════════════════════════════════════════════════════════════
#  1. Supplier RBAC + CRUD
# ══════════════════════════════════════════════════════════════

class TestSupplierRBAC:

    def test_project_manager_can_create_supplier(self, client, db_session):
        _, headers = make_user(db_session, "project_manager", "pm_user")
        resp = client.post(
            "/api/v1/catalog/suppliers",
            json={"name": "Lockheed Martin", "cage_code": "10ABC"},
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["name"] == "Lockheed Martin"
        assert body["catalog_part_count"] == 0

    def test_stakeholder_cannot_create_supplier(self, client, db_session):
        _, headers = make_user(db_session, "stakeholder", "sh_user")
        resp = client.post(
            "/api/v1/catalog/suppliers",
            json={"name": "BAE Systems"},
            headers=headers,
        )
        assert resp.status_code == 403, resp.text

    def test_admin_can_delete_supplier(self, client, db_session, supplier):
        _, headers = make_user(db_session, "admin", "admin_user")
        resp = client.delete(
            f"/api/v1/catalog/suppliers/{supplier.id}",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    def test_project_manager_cannot_delete_supplier(self, client, db_session, supplier):
        _, headers = make_user(db_session, "project_manager", "pm_killer")
        resp = client.delete(
            f"/api/v1/catalog/suppliers/{supplier.id}",
            headers=headers,
        )
        assert resp.status_code == 403, resp.text

    def test_supplier_with_parts_refuses_delete_without_admin_force(
        self, client, db_session, catalog_part, supplier
    ):
        _, headers = make_user(db_session, "admin", "admin_force_off")
        resp = client.delete(
            f"/api/v1/catalog/suppliers/{supplier.id}",
            headers=headers,
        )
        assert resp.status_code == 409, resp.text

    def test_supplier_with_parts_admin_force_succeeds(
        self, client, db_session, catalog_part, supplier
    ):
        _, headers = make_user(db_session, "admin", "admin_force_on")
        resp = client.delete(
            f"/api/v1/catalog/suppliers/{supplier.id}?admin_force=true",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text


# ══════════════════════════════════════════════════════════════
#  2. CatalogPart create + cascade
# ══════════════════════════════════════════════════════════════

class TestCatalogPartCreate:

    def test_create_part_with_connectors_and_pins(
        self, client, db_session, test_user
    ):
        # Need a supplier first.
        s = Supplier(name="Honeywell Test", created_by_id=test_user.id)
        db_session.add(s)
        db_session.commit()

        _, headers = make_user(db_session, "requirements_engineer", "re_create")
        body = {
            "supplier_id": s.id,
            "part_number": "HW-200",
            "revision": "A",
            "name": "INS Module",
            "part_class": PartClass.SENSOR.value,
            "lru_classification": LRUClass.LRU.value,
            "lifecycle_status": LifecycleStatus.ACTIVE.value,
            "connectors": [
                {
                    "reference": "J1",
                    "position": 0,
                    "gender": CatGender.MALE.value,
                    "pin_count": 3,
                    "pins": [
                        {
                            "pin_position": "1",
                            "mfr_pin_name": "PWR",
                            "mfr_signal_type": CatSignalType.POWER.value,
                            "mfr_direction": CatDirection.POWER.value,
                        },
                        {
                            "pin_position": "2",
                            "mfr_pin_name": "RX",
                            "mfr_signal_type": CatSignalType.DIGITAL.value,
                            "mfr_direction": CatDirection.INPUT.value,
                        },
                        {
                            "pin_position": "3",
                            "mfr_pin_name": "TX",
                            "mfr_signal_type": CatSignalType.DIGITAL.value,
                            "mfr_direction": CatDirection.OUTPUT.value,
                        },
                    ],
                }
            ],
        }
        resp = client.post("/api/v1/catalog/parts", json=body, headers=headers)
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert data["part_number"] == "HW-200"
        assert len(data["connectors"]) == 1
        assert len(data["connectors"][0]["pins"]) == 3
        # Cascade: delete the part, expect connectors and pins to vanish.
        part_id = data["id"]
        _, admin_headers = make_user(db_session, "admin", "admin_cascade")
        del_resp = client.delete(
            f"/api/v1/catalog/parts/{part_id}", headers=admin_headers
        )
        assert del_resp.status_code == 200, del_resp.text
        # Direct DB verify cascade
        assert db_session.query(CatalogPart).filter(CatalogPart.id == part_id).first() is None
        assert db_session.query(CatalogConnector).filter(
            CatalogConnector.catalog_part_id == part_id
        ).count() == 0
        assert db_session.query(CatalogPin).count() == 0

    def test_pagination_cap_limit_300_returns_422(
        self, client, db_session, supplier
    ):
        _, headers = make_user(db_session, "admin", "admin_pag")
        resp = client.get(
            "/api/v1/catalog/parts?limit=300",
            headers=headers,
        )
        assert resp.status_code == 422, resp.text

    def test_list_parts_filters_by_supplier_and_class(
        self, client, db_session, catalog_part, supplier
    ):
        _, headers = make_user(db_session, "admin", "admin_list")
        resp = client.get(
            f"/api/v1/catalog/parts?supplier_id={supplier.id}&part_class={PartClass.PROCESSOR.value}",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        items = resp.json()
        assert any(item["id"] == catalog_part.id for item in items)
        # No SENSOR-class parts exist → filtering by SENSOR yields []
        resp_sensor = client.get(
            f"/api/v1/catalog/parts?supplier_id={supplier.id}&part_class={PartClass.SENSOR.value}",
            headers=headers,
        )
        assert resp_sensor.status_code == 200
        assert resp_sensor.json() == []


# ══════════════════════════════════════════════════════════════
#  3. Placement
# ══════════════════════════════════════════════════════════════

class TestCatalogPartPlacement:

    def test_place_creates_unit_with_catalog_link(
        self, client, db_session, catalog_part, system_in_project, test_project
    ):
        _, headers = make_user(
            db_session, "requirements_engineer", "re_place", project=test_project,
        )
        body = {
            "project_id": test_project.id,
            "system_id": system_in_project.id,
            "unit_id_tag": "RSP-100-A",
            "location_zone": "Bay 3",
            "serial_number": "SN-12345",
        }
        resp = client.post(
            f"/api/v1/catalog/parts/{catalog_part.id}/place",
            json=body,
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        unit_data = resp.json()
        unit_id = unit_data["id"]

        # Verify Unit links back to catalog and copies project-side fields.
        unit = db_session.query(Unit).filter(Unit.id == unit_id).first()
        assert unit is not None
        assert unit.catalog_part_id == catalog_part.id
        assert unit.location_zone == "Bay 3"
        assert unit.serial_number == "SN-12345"
        assert unit.project_id == test_project.id
        assert unit.system_id == system_in_project.id

        # Verify Connector cloned.
        conns = db_session.query(Connector).filter(Connector.unit_id == unit.id).all()
        assert len(conns) == 1
        assert conns[0].designator == "J1"

        # Verify Pins cloned with mfr/internal name parity + catalog_pin_id set.
        pins = db_session.query(Pin).filter(Pin.connector_id == conns[0].id).all()
        assert len(pins) == 2
        for pin in pins:
            assert pin.catalog_pin_id is not None
            assert pin.mfr_pin_name == pin.internal_signal_name
            assert pin.mfr_pin_name in {"VCC_28V", "GND"}
            assert pin.direction_override is None  # falls back to catalog at read time

    def test_place_restricted_part_blocks_non_admin(
        self, client, db_session, catalog_part, system_in_project, test_project
    ):
        catalog_part.lifecycle_status = LifecycleStatus.RESTRICTED
        db_session.commit()

        _, headers = make_user(
            db_session, "requirements_engineer", "re_restricted", project=test_project,
        )
        body = {
            "project_id": test_project.id,
            "system_id": system_in_project.id,
            "unit_id_tag": "RSP-100-R",
        }
        resp = client.post(
            f"/api/v1/catalog/parts/{catalog_part.id}/place",
            json=body,
            headers=headers,
        )
        assert resp.status_code == 403, resp.text

    def test_place_restricted_part_admin_succeeds(
        self, client, db_session, catalog_part, system_in_project, test_project
    ):
        catalog_part.lifecycle_status = LifecycleStatus.RESTRICTED
        db_session.commit()

        _, headers = make_user(db_session, "admin", "admin_restricted")
        body = {
            "project_id": test_project.id,
            "system_id": system_in_project.id,
            "unit_id_tag": "RSP-100-R",
        }
        resp = client.post(
            f"/api/v1/catalog/parts/{catalog_part.id}/place",
            json=body,
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

    def test_non_member_cannot_place_in_other_project(
        self, client, db_session, catalog_part, test_user, test_project,
    ):
        # Build a separate project the user is a member of.
        from app.models import Project
        other = Project(
            code="OTHER", name="Other Project", owner_id=test_user.id, status="active",
        )
        db_session.add(other)
        db_session.commit()

        # User is a member of `other` but NOT of `test_project`.
        # Place into test_project.id → expect 403 (membership denial).
        from app.models.interface import System
        s = System(
            system_id="SYS-OTHER", name="Sys", abbreviation="SY",
            system_type="subsystem", project_id=test_project.id,
            owner_id=test_user.id,
        )
        db_session.add(s)
        db_session.commit()

        _, headers = make_user(
            db_session, "requirements_engineer", "re_outsider", project=other,
        )
        body = {
            "project_id": test_project.id,
            "system_id": s.id,
            "unit_id_tag": "RSP-100-X",
        }
        resp = client.post(
            f"/api/v1/catalog/parts/{catalog_part.id}/place",
            json=body,
            headers=headers,
        )
        assert resp.status_code == 403, resp.text

    def test_delete_placed_part_refuses_without_admin_force(
        self, client, db_session, catalog_part, system_in_project, test_project
    ):
        # Place the part.
        _, re_headers = make_user(
            db_session, "requirements_engineer", "re_pre_delete", project=test_project,
        )
        place_resp = client.post(
            f"/api/v1/catalog/parts/{catalog_part.id}/place",
            json={
                "project_id": test_project.id,
                "system_id": system_in_project.id,
                "unit_id_tag": "RSP-100-D",
            },
            headers=re_headers,
        )
        assert place_resp.status_code == 201, place_resp.text

        _, admin_headers = make_user(db_session, "admin", "admin_no_force")
        resp = client.delete(
            f"/api/v1/catalog/parts/{catalog_part.id}",
            headers=admin_headers,
        )
        assert resp.status_code == 409, resp.text

        force_resp = client.delete(
            f"/api/v1/catalog/parts/{catalog_part.id}?admin_force=true",
            headers=admin_headers,
        )
        assert force_resp.status_code == 200, force_resp.text


# ══════════════════════════════════════════════════════════════
#  4. Brand-new placement (the catalog-create + place flow)
# ══════════════════════════════════════════════════════════════

class TestBrandNewPlacement:

    def test_brand_new_part_visible_in_global_catalog(
        self, client, db_session, supplier, system_in_project, test_project,
    ):
        """Service-level test: place_brand_new_part creates a global CatalogPart
        that's visible from another project's perspective via the same
        global catalog endpoints."""
        from app.services.catalog.placement import place_brand_new_part
        # Use admin user so RBAC is not the gate under test.
        from app.models import User
        admin = User(
            username="brand_new_admin",
            email="brand_new@example.com",
            hashed_password="x",
            full_name="Admin",
            role="admin",
            is_active=True,
        )
        db_session.add(admin)
        db_session.commit()
        db_session.refresh(admin)

        new_part, placed_unit = place_brand_new_part(
            db_session,
            user=admin,
            supplier_id=supplier.id,
            catalog_part_data={
                "part_number": "NEWPART-001",
                "name": "Brand New Module",
                "part_class": PartClass.COMPUTE_MODULE,
                "lifecycle_status": LifecycleStatus.ACTIVE,
                "lru_classification": LRUClass.LRU,
            },
            connectors_data=[
                {
                    "reference": "J1",
                    "position": 0,
                    "gender": CatGender.UNKNOWN,
                    "pins": [
                        {
                            "pin_position": "1",
                            "mfr_pin_name": "PWR",
                        },
                    ],
                }
            ],
            placement={
                "project_id": test_project.id,
                "system_id": system_in_project.id,
                "designation": "NEWPART-001-A",
            },
        )
        db_session.commit()
        assert new_part.id is not None
        assert placed_unit is not None
        assert placed_unit.catalog_part_id == new_part.id

        # Visible from another project context (global GET /parts).
        _, headers = make_user(db_session, "stakeholder", "sh_browse_global")
        resp = client.get(f"/api/v1/catalog/parts/{new_part.id}", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["part_number"] == "NEWPART-001"
        # used_in_project_count should reflect the placement we just did.
        assert body["used_in_project_count"] == 1


# ══════════════════════════════════════════════════════════════
#  5. Document upload (sha256 dedup)
# ══════════════════════════════════════════════════════════════

class TestSupplierDocumentUpload:

    def _upload(self, client, supplier_id, content, headers, *, title="ICD doc"):
        files = {"file": ("test.pdf", io.BytesIO(content), "application/pdf")}
        data = {"title": title, "document_type": SupplierDocumentType.ICD.value}
        return client.post(
            f"/api/v1/catalog/suppliers/{supplier_id}/documents/upload",
            files=files, data=data, headers=headers,
        )

    def test_upload_creates_file_and_records_sha256(
        self, client, db_session, supplier
    ):
        _, headers = make_user(db_session, "requirements_engineer", "re_upload")
        content = b"PDF-CONTENT-" + uuid.uuid4().bytes
        resp = self._upload(client, supplier.id, content, headers)
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["sha256"] != ""
        assert body["file_size_bytes"] == len(content)
        assert body["extraction_status"] == "uploaded"

        # File written to the patched dir.
        file_path = Path(body["file_path"])
        assert file_path.exists(), f"File missing on disk: {file_path}"
        assert file_path.read_bytes() == content

    def test_duplicate_sha256_same_supplier_rejected(
        self, client, db_session, supplier
    ):
        _, headers = make_user(db_session, "requirements_engineer", "re_dup_same")
        content = b"DUP-PDF-" + uuid.uuid4().bytes
        first = self._upload(client, supplier.id, content, headers)
        assert first.status_code == 201, first.text
        second = self._upload(client, supplier.id, content, headers, title="dup")
        assert second.status_code == 409, second.text

    def test_duplicate_sha256_different_supplier_allowed(
        self, client, db_session, supplier, test_user
    ):
        other = Supplier(name="Other Vendor", created_by_id=test_user.id)
        db_session.add(other)
        db_session.commit()

        _, headers = make_user(db_session, "requirements_engineer", "re_dup_diff")
        content = b"PDF-CROSS-VENDOR-" + uuid.uuid4().bytes
        a = self._upload(client, supplier.id, content, headers)
        assert a.status_code == 201
        b = self._upload(client, other.id, content, headers, title="re-upload")
        assert b.status_code == 201, b.text
