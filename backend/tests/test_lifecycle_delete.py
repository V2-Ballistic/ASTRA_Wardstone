"""ASTRA — CADPORT-TDD-LIFECYCLE-001 Phase 3 delete tests.

Covers:
  * Phase 0.2 fix: soft-deleted rows no longer appear in
    GET /parts (list) or GET /parts/{id}.
  * Delete propagates to CADPORT via /sync-delete-from-astra when a
    back-link is set; no-op otherwise.
  * /sync-delete-from-cadport soft-deletes the ASTRA row, stamps
    origin='cadport', and does NOT call CADPORT back (loop-breaker).
  * Re-delete of an already-deleted row is idempotent (returns
    "already_deleted" via /sync-delete-from-cadport).
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


def _make_catalog_part(
    db_session, test_user, supplier: Supplier,
    *, cadport_part_id: str | None = None,
) -> CatalogPart:
    p = CatalogPart(
        supplier_id=supplier.id,
        part_number=f"WS-MH-P{uuid.uuid4().hex[:6]}-A",
        revision=None,
        name=f"delete-test-{uuid.uuid4().hex[:4]}",
        part_class="mechanical_other",
        lifecycle_status="active",
        mass_kg=0.1,
        cadport_part_id=(
            uuid.UUID(cadport_part_id) if cadport_part_id else None
        ),
        created_by_id=test_user.id,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture()
def cadport_base_url() -> str:
    return settings.CADPORT_BASE_URL.rstrip("/")


# ──────────────────────────────────────────────────────────────
#  Phase 0.2 regression — soft-deleted rows hidden from reads
# ──────────────────────────────────────────────────────────────


class TestSoftDeletedRowsHiddenFromReads:

    @respx.mock
    def test_get_part_returns_404_after_delete(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        """Phase 0.2 root-cause fix: the delete handler always set
        deleted_at, but GET /parts/{id} still returned the row. This
        test pins the corrected behaviour."""
        respx.post(
            f"{cadport_base_url}/parts/anything/sync-delete-from-astra"
        )
        part = _make_catalog_part(db_session, test_user, vectornav)
        _, admin_headers = make_user(db_session, "admin", "adm_del_get")
        # Verify present BEFORE delete.
        r0 = client.get(
            f"/api/v1/catalog/parts/{part.id}", headers=admin_headers,
        )
        assert r0.status_code == 200, r0.text
        # Delete.
        r1 = client.delete(
            f"/api/v1/catalog/parts/{part.id}", headers=admin_headers,
        )
        assert r1.status_code == 200, r1.text
        assert r1.json().get("soft_delete") is True
        # After delete, GET 404s — this is the Phase 0.2 bug fix.
        r2 = client.get(
            f"/api/v1/catalog/parts/{part.id}", headers=admin_headers,
        )
        assert r2.status_code == 404

    @respx.mock
    def test_list_parts_hides_soft_deleted(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        respx.post(
            f"{cadport_base_url}/parts/anything/sync-delete-from-astra"
        )
        keep = _make_catalog_part(db_session, test_user, vectornav)
        drop = _make_catalog_part(db_session, test_user, vectornav)
        _, admin_headers = make_user(db_session, "admin", "adm_del_list")
        client.delete(
            f"/api/v1/catalog/parts/{drop.id}", headers=admin_headers,
        )

        r = client.get(
            "/api/v1/catalog/parts", headers=admin_headers,
            params={"supplier_id": vectornav.id},
        )
        assert r.status_code == 200, r.text
        ids = [row["id"] for row in r.json()]
        assert keep.id in ids
        assert drop.id not in ids


# ──────────────────────────────────────────────────────────────
#  Propagation
# ──────────────────────────────────────────────────────────────


class TestDeletePropagation:

    @respx.mock
    def test_astra_delete_propagates_to_cadport_when_linked(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        cadport_uuid = str(uuid.uuid4())
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=cadport_uuid,
        )
        sync = respx.post(
            f"{cadport_base_url}/parts/{cadport_uuid}/sync-delete-from-astra"
        ).mock(return_value=Response(200, json={"status": "deleted"}))

        _, admin_headers = make_user(db_session, "admin", "adm_del_prop")
        r = client.delete(
            f"/api/v1/catalog/parts/{part.id}", headers=admin_headers,
        )
        assert r.status_code == 200, r.text
        assert sync.called

    @respx.mock
    def test_astra_delete_does_not_propagate_when_no_back_link(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=None,
        )
        sync = respx.post(
            f"{cadport_base_url}/parts/anything/sync-delete-from-astra"
        )
        _, admin_headers = make_user(db_session, "admin", "adm_del_noprop")
        r = client.delete(
            f"/api/v1/catalog/parts/{part.id}", headers=admin_headers,
        )
        assert r.status_code == 200, r.text
        assert not sync.called

    @respx.mock
    def test_sync_delete_from_cadport_loop_breaker(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        """Internal endpoint must update the ASTRA row but NOT call
        CADPORT back — that's how the bidirectional sync converges."""
        cadport_uuid = str(uuid.uuid4())
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=cadport_uuid,
        )
        no_outbound = respx.post(
            f"{cadport_base_url}/parts/{cadport_uuid}/sync-delete-from-astra"
        )
        _, headers = make_user(db_session, "requirements_engineer", "re_sdfc")
        r = client.post(
            f"/api/v1/catalog/parts/{part.id}/sync-delete-from-cadport",
            json={}, headers=headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "deleted"
        assert not no_outbound.called
        db_session.expire_all()
        db_session.refresh(part)
        assert part.deleted_at is not None
        assert part.last_sync_origin == "cadport"

    @respx.mock
    def test_sync_delete_from_cadport_idempotent(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        cadport_uuid = str(uuid.uuid4())
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=cadport_uuid,
        )
        respx.post(
            f"{cadport_base_url}/parts/{cadport_uuid}/sync-delete-from-astra"
        )
        _, headers = make_user(db_session, "requirements_engineer", "re_sdfc_i")
        url = f"/api/v1/catalog/parts/{part.id}/sync-delete-from-cadport"
        r1 = client.post(url, json={}, headers=headers)
        assert r1.status_code == 200
        r2 = client.post(url, json={}, headers=headers)
        assert r2.status_code == 200
        assert r2.json()["status"] == "already_deleted"
