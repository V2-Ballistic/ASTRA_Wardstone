"""ASTRA — CADPORT-TDD-LIFECYCLE-001 Phase 2 edit-supplier / edit-name tests.

Covers:
  * PATCH /catalog/parts/{id}/supplier with existing supplier_id
  * PATCH /catalog/parts/{id}/supplier with proposed_supplier_name
    (create-or-reuse — verifies the new supplier row lands)
  * PATCH /catalog/parts/{id}/name updates name
  * Propagation to CADPORT fires on both endpoints when a back-link
    is set (and does not fire when not)
  * /sync-from-cadport extended path: supplier_id + display_name
    write through and stamp last_sync_origin='cadport'
"""

from __future__ import annotations

import uuid

import pytest
import respx
from httpx import Response

from app.config import settings
from app.models.catalog import CatalogPart, Supplier
from tests.conftest import make_user


@pytest.fixture()
def vectornav(db_session, test_user) -> Supplier:
    s = Supplier(
        name="VectorNav", short_name="VN", is_active=True,
        is_in_house=False, created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture()
def trenz_supplier_exists(db_session, test_user) -> Supplier:
    s = Supplier(
        name="Trenz Electronic", short_name="Trenz", is_active=True,
        is_in_house=False, created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _make_catalog_part(
    db_session, test_user, supplier: Supplier,
    *, cadport_part_id: str | None = None, name: str = "UltralTX+ Baseboard",
) -> CatalogPart:
    p = CatalogPart(
        supplier_id=supplier.id,
        part_number=f"WS-EH-P{uuid.uuid4().hex[:6]}-A",
        revision=None,
        name=name,
        part_class="mechanical_other",
        lifecycle_status="active",
        mass_kg=0.0972,
        volume_m3=3.6e-5,
        density_kg_m3=2700.0,
        cadport_part_id=(
            uuid.UUID(cadport_part_id) if cadport_part_id else None
        ),
        source_format="step",
        mass_source="user_override",
        created_by_id=test_user.id,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture()
def cadport_base_url() -> str:
    return settings.CADPORT_BASE_URL.rstrip("/")


class TestPatchSupplier:

    @respx.mock
    def test_patch_supplier_with_existing_id_propagates(
        self, client, db_session, test_user, vectornav, trenz_supplier_exists,
        cadport_base_url,
    ):
        cadport_uuid = str(uuid.uuid4())
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=cadport_uuid,
        )
        sync = respx.post(
            f"{cadport_base_url}/parts/{cadport_uuid}/sync-from-astra"
        ).mock(return_value=Response(200, json={"ok": True}))

        _, headers = make_user(
            db_session, "requirements_engineer", "re_sup_id",
        )
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/supplier",
            json={"supplier_id": trenz_supplier_exists.id},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert sync.called
        import json as _json
        body = _json.loads(sync.calls.last.request.read())
        assert body == {
            "supplier_id": trenz_supplier_exists.id,
            "supplier_name": "Trenz Electronic",
        }
        db_session.expire_all()
        db_session.refresh(part)
        assert part.supplier_id == trenz_supplier_exists.id
        assert part.last_sync_origin == "astra"

    @respx.mock
    def test_patch_supplier_with_proposed_name_creates_supplier(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        cadport_uuid = str(uuid.uuid4())
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=cadport_uuid,
        )
        respx.post(
            f"{cadport_base_url}/parts/{cadport_uuid}/sync-from-astra"
        ).mock(return_value=Response(200, json={"ok": True}))

        _, headers = make_user(
            db_session, "requirements_engineer", "re_sup_new",
        )
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/supplier",
            json={"proposed_supplier_name": "Brand New Supplier Co"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        # Newly-created supplier exists in the DB now.
        new_supp = (
            db_session.query(Supplier)
            .filter(Supplier.name == "Brand New Supplier Co")
            .first()
        )
        assert new_supp is not None
        db_session.expire_all()
        db_session.refresh(part)
        assert part.supplier_id == new_supp.id

    @respx.mock
    def test_patch_supplier_no_back_link_no_propagation(
        self, client, db_session, test_user, vectornav, trenz_supplier_exists,
        cadport_base_url,
    ):
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=None,
        )
        sync = respx.post(
            f"{cadport_base_url}/parts/whatever/sync-from-astra"
        )
        _, headers = make_user(
            db_session, "requirements_engineer", "re_sup_nolink",
        )
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/supplier",
            json={"supplier_id": trenz_supplier_exists.id},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert not sync.called


class TestPatchName:

    @respx.mock
    def test_patch_name_propagates(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        cadport_uuid = str(uuid.uuid4())
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=cadport_uuid,
        )
        sync = respx.post(
            f"{cadport_base_url}/parts/{cadport_uuid}/sync-from-astra"
        ).mock(return_value=Response(200, json={"ok": True}))

        _, headers = make_user(
            db_session, "requirements_engineer", "re_name",
        )
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/name",
            json={"display_name": "Renamed Part v2"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert sync.called
        import json as _json
        body = _json.loads(sync.calls.last.request.read())
        assert body == {"display_name": "Renamed Part v2"}
        db_session.expire_all()
        db_session.refresh(part)
        assert part.name == "Renamed Part v2"

    def test_patch_name_rejects_empty(
        self, client, db_session, test_user, vectornav,
    ):
        part = _make_catalog_part(db_session, test_user, vectornav)
        _, headers = make_user(
            db_session, "requirements_engineer", "re_name_empty",
        )
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/name",
            json={"display_name": ""},
            headers=headers,
        )
        # Pydantic min_length=1 surfaces 422; a stripped-empty would
        # surface as 400 from the handler. Either way it's a 4xx.
        assert resp.status_code in (400, 422)


class TestSyncFromCadportExtended:

    @respx.mock
    def test_sync_from_cadport_supplier_and_name(
        self, client, db_session, test_user, vectornav, trenz_supplier_exists,
        cadport_base_url,
    ):
        """The CADPORT side calls /sync-from-cadport with supplier_id
        + display_name; ASTRA updates the row and stamps
        last_sync_origin='cadport' WITHOUT calling back."""
        cadport_uuid = str(uuid.uuid4())
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=cadport_uuid,
        )
        no_outbound = respx.post(
            f"{cadport_base_url}/parts/{cadport_uuid}/sync-from-astra"
        )
        _, headers = make_user(
            db_session, "requirements_engineer", "re_sync_in_supp",
        )
        resp = client.post(
            f"/api/v1/catalog/parts/{part.id}/sync-from-cadport",
            json={
                "supplier_id": trenz_supplier_exists.id,
                "display_name": "Synced From CADPORT",
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert "supplier_id" in resp.json()["updated_fields"]
        assert "name" in resp.json()["updated_fields"]
        assert resp.json()["last_sync_origin"] == "cadport"
        # Loop-breaker: did NOT propagate back.
        assert not no_outbound.called
        db_session.expire_all()
        db_session.refresh(part)
        assert part.supplier_id == trenz_supplier_exists.id
        assert part.name == "Synced From CADPORT"
