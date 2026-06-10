"""ASTRA — CADPORT-TDD-ASTRA-BRIDGE-001 Phase 1 pending-imports tests.

Covers:
  * POST /catalog/pending-imports/from-cadport (happy path id/name).
  * Approve a CADPORT pending → catalog_part lands with the chosen
    supplier; supplier is created on-the-fly when proposed by name.
  * Operator changes supplier choice before approve; final
    catalog_part reflects the change.
  * Old /catalog/parts/from-cadport still works (deprecated but live).
"""

from __future__ import annotations

import uuid

import pytest

from app.models import UserRole
from app.models.catalog import (
    CatalogPart,
    PendingCatalogImport,
    PendingImportStatus,
    Supplier,
)
from app.routers import catalog as catalog_router
from tests.conftest import make_user


@pytest.fixture(autouse=True)
def patch_supplier_doc_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(
        catalog_router, "SUPPLIER_DOC_DIR", tmp_path / "supplier_docs"
    )


@pytest.fixture()
def in_house_supplier(db_session, test_user) -> Supplier:
    s = Supplier(
        name="Wardstone",
        short_name="WS",
        is_in_house=True,
        is_active=True,
        created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture()
def vectornav(db_session, test_user) -> Supplier:
    s = Supplier(
        name="VectorNav",
        short_name="VN",
        is_active=True,
        is_in_house=False,
        created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _payload(**overrides):
    base = {
        "cadport_part_id": str(uuid.uuid4()),
        "content_hash": f"sha256:{uuid.uuid4().hex}",
        "source_filename": "TEBF0818-02A.step",
        "display_name": "UltralTX+ Baseboard",
        "internal_part_number": None,
        "material": None,
        "configuration": "Default",
        "solidworks_version": None,
        "mass_kg": 0.0,
        "volume_m3": 1.28e-4,
        "surface_area_m2": 0.0,
        "density_kg_m3": 0.0,
        "center_of_mass_m": [0.0, 0.0, 0.0],
        "inertia": {
            "ixx": 0.0, "iyy": 0.0, "izz": 0.0,
            "ixy": 0.0, "ixz": 0.0, "iyz": 0.0,
        },
        "yaml_filename": "tebf.yaml",
        "yaml_content": "schema_version: 1.0\nkind: part\n",
        "source_format": "step",
        "mass_source": "cad",
    }
    base.update(overrides)
    return base


# ── §1.7 tests ────────────────────────────────────────────────────────


class TestPendingFromCadport:

    def test_happy_path_existing_supplier_id(
        self, client, db_session, test_user, in_house_supplier, vectornav,
    ):
        _, headers = make_user(db_session, "requirements_engineer", "re_pending_a")
        resp = client.post(
            "/api/v1/catalog/pending-imports/from-cadport",
            json=_payload(supplier_id=vectornav.id),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["status"] == "pending"
        assert body["supplier_id"] == vectornav.id
        assert body["proposed_supplier_name"] is None
        assert body["review_url"].startswith("/catalog/pending-imports/")
        # Row sanity.
        row = db_session.query(PendingCatalogImport).filter_by(id=body["id"]).one()
        assert row.source_kind == "cadport"
        assert row.supplier_id == vectornav.id

    def test_proposes_new_supplier_name(
        self, client, db_session, test_user, in_house_supplier,
    ):
        _, headers = make_user(db_session, "requirements_engineer", "re_pending_b")
        resp = client.post(
            "/api/v1/catalog/pending-imports/from-cadport",
            json=_payload(supplier_name="Aerospace Composites"),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["proposed_supplier_name"] == "Aerospace Composites"
        assert body["supplier_id"] is None
        # No supplier row was created at upload.
        assert (
            db_session.query(Supplier)
            .filter(Supplier.name == "Aerospace Composites")
            .first()
            is None
        )

    def test_neither_supplier_returns_400(
        self, client, db_session, test_user, in_house_supplier,
    ):
        _, headers = make_user(db_session, "requirements_engineer", "re_pending_c")
        resp = client.post(
            "/api/v1/catalog/pending-imports/from-cadport",
            json=_payload(),
            headers=headers,
        )
        assert resp.status_code == 400

    def test_both_supplier_fields_returns_400(
        self, client, db_session, test_user, in_house_supplier, vectornav,
    ):
        _, headers = make_user(db_session, "requirements_engineer", "re_pending_d")
        resp = client.post(
            "/api/v1/catalog/pending-imports/from-cadport",
            json=_payload(supplier_id=vectornav.id, supplier_name="Other"),
            headers=headers,
        )
        assert resp.status_code == 400


class TestApproveCadportPending:

    def _create_pending(
        self, client, db_session, test_user, in_house_supplier, **payload_extra,
    ) -> int:
        _, headers = make_user(db_session, "requirements_engineer", f"re_create_{uuid.uuid4().hex[:6]}")
        resp = client.post(
            "/api/v1/catalog/pending-imports/from-cadport",
            json=_payload(**payload_extra),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return int(resp.json()["id"]), headers

    def test_approve_with_existing_supplier_id_creates_catalog_part(
        self, client, db_session, test_user, in_house_supplier, vectornav,
    ):
        pid, headers = self._create_pending(
            client, db_session, test_user, in_house_supplier,
            supplier_id=vectornav.id,
        )
        # Approve.
        resp = client.post(
            f"/api/v1/catalog/pending-imports/{pid}/approve",
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        part_body = resp.json()
        assert part_body["supplier_id"] == vectornav.id
        assert part_body["name"] == "UltralTX+ Baseboard"
        # Pending row marked APPROVED + linked.
        db_session.expire_all()
        pending = db_session.query(PendingCatalogImport).filter_by(id=pid).one()
        assert pending.status == PendingImportStatus.APPROVED
        assert pending.committed_catalog_part_id == part_body["id"]

    def test_approve_with_proposed_name_creates_supplier_and_part(
        self, client, db_session, test_user, in_house_supplier,
    ):
        pid, headers = self._create_pending(
            client, db_session, test_user, in_house_supplier,
            supplier_name="Brand New Supplier",
        )
        # Pre-approve: supplier doesn't exist yet.
        assert (
            db_session.query(Supplier)
            .filter(Supplier.name == "Brand New Supplier")
            .first()
            is None
        )
        resp = client.post(
            f"/api/v1/catalog/pending-imports/{pid}/approve",
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        part_body = resp.json()
        # Supplier was created.
        new = (
            db_session.query(Supplier)
            .filter(Supplier.name == "Brand New Supplier")
            .first()
        )
        assert new is not None
        assert part_body["supplier_id"] == new.id

    def test_approve_after_operator_changes_supplier_pick(
        self, client, db_session, test_user, in_house_supplier, vectornav,
    ):
        # Upload proposing "Foo" → operator edits to existing VectorNav before approve.
        pid, headers = self._create_pending(
            client, db_session, test_user, in_house_supplier,
            supplier_name="Foo Industries",
        )
        edit = client.patch(
            f"/api/v1/catalog/pending-imports/{pid}",
            json={"supplier_id": vectornav.id, "proposed_supplier_name": None},
            headers=headers,
        )
        assert edit.status_code == 200, edit.text
        approve = client.post(
            f"/api/v1/catalog/pending-imports/{pid}/approve",
            headers=headers,
        )
        assert approve.status_code == 201, approve.text
        part_body = approve.json()
        assert part_body["supplier_id"] == vectornav.id
        # "Foo Industries" was never created.
        assert (
            db_session.query(Supplier)
            .filter(Supplier.name == "Foo Industries")
            .first()
            is None
        )


class TestLegacyFromCadportStillWorks:

    def test_old_endpoint_still_creates_catalog_part_directly(
        self, client, db_session, test_user, in_house_supplier, vectornav,
    ):
        """The original /catalog/parts/from-cadport stays live for
        regression — internal callers / tests still rely on it."""
        _, headers = make_user(db_session, "requirements_engineer", "re_legacy")
        # Build the legacy payload — has the same shape.
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=_payload(supplier_id=vectornav.id),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        # Legacy endpoint returns catalog_part_id (immediate landing).
        assert "catalog_part_id" in body
        assert body["supplier_id"] == vectornav.id
        # The row IS in catalog_parts already (no pending review).
        cp = (
            db_session.query(CatalogPart)
            .filter(CatalogPart.id == body["catalog_part_id"])
            .one()
        )
        assert cp.supplier_id == vectornav.id
