"""ASTRA — CADPORT-TDD-ASTRA-BRIDGE-001 Phase 3 bidirectional-sync tests.

The CADPORT side is mocked at the network boundary (httpx) — these
tests assert that:
  * The public PATCH /mass propagates to CADPORT when a back-link
    exists, and stamps last_sync_origin='astra'.
  * The internal /sync-from-cadport endpoint updates the row, stamps
    last_sync_origin='cadport', and does NOT call CADPORT back —
    that's the loop-breaker.
  * A propagation failure (ASTRA -> CADPORT) logs but does not roll
    back the local commit.
  * No back-link → no outbound call.
  * The general-purpose PATCH /parts/{id} also propagates when the
    update touches step_material_key (material edits).
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
    db_session,
    test_user,
    supplier: Supplier,
    *,
    cadport_part_id: str | None = None,
    mass_kg: float = 0.05,
    source_format: str = "step",
    mass_source: str = "user_override",
) -> CatalogPart:
    p = CatalogPart(
        supplier_id=supplier.id,
        part_number=f"WS-MH-P{uuid.uuid4().hex[:6]}-A",
        revision=None,
        name="phase3 sync test",
        part_class="mechanical_other",
        lifecycle_status="active",
        mass_kg=mass_kg,
        volume_m3=1.0e-4,
        density_kg_m3=500.0,
        cadport_part_id=(
            uuid.UUID(cadport_part_id) if cadport_part_id else None
        ),
        source_format=source_format,
        mass_source=mass_source,
        created_by_id=test_user.id,
    )
    db_session.add(p)
    db_session.commit()
    db_session.refresh(p)
    return p


@pytest.fixture()
def cadport_base_url() -> str:
    return settings.CADPORT_BASE_URL.rstrip("/")


class TestAstraMassEditPropagates:

    @respx.mock
    def test_patch_mass_propagates_to_cadport_when_linked(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        cadport_uuid = str(uuid.uuid4())
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=cadport_uuid,
        )
        sync_route = respx.post(
            f"{cadport_base_url}/parts/{cadport_uuid}/sync-from-astra"
        ).mock(return_value=Response(200, json={"ok": True}))

        _, headers = make_user(db_session, "requirements_engineer", "re_propagate")
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/mass",
            json={"mass_kg": 0.123},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert sync_route.called
        call = sync_route.calls.last
        body = call.request.read()
        import json as _json
        assert _json.loads(body) == {"mass_kg": 0.123}

        db_session.expire_all()
        db_session.refresh(part)
        assert part.last_sync_origin == "astra"
        assert part.last_sync_at is not None
        assert float(part.mass_kg) == pytest.approx(0.123)

    @respx.mock
    def test_patch_mass_does_not_propagate_when_no_back_link(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        # No cadport_part_id → no outbound call.
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=None,
        )
        sync_route = respx.post(
            f"{cadport_base_url}/parts/anything/sync-from-astra",
        )
        _, headers = make_user(db_session, "requirements_engineer", "re_no_link")
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/mass",
            json={"mass_kg": 0.456},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert not sync_route.called

    @respx.mock
    def test_patch_mass_local_commit_survives_propagation_failure(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        cadport_uuid = str(uuid.uuid4())
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=cadport_uuid,
        )
        # CADPORT returns 503 — local commit must NOT roll back.
        sync_route = respx.post(
            f"{cadport_base_url}/parts/{cadport_uuid}/sync-from-astra"
        ).mock(return_value=Response(503, text="upstream down"))
        _, headers = make_user(
            db_session, "requirements_engineer", "re_fail_soft",
        )
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}/mass",
            json={"mass_kg": 0.789},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert sync_route.called
        db_session.expire_all()
        db_session.refresh(part)
        assert float(part.mass_kg) == pytest.approx(0.789)


class TestSyncFromCadportEndpoint:

    @respx.mock
    def test_sync_from_cadport_updates_row_does_not_propagate_back(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        cadport_uuid = str(uuid.uuid4())
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=cadport_uuid,
        )
        # If the sync handler propagated back, this would fire.
        no_call = respx.post(
            f"{cadport_base_url}/parts/{cadport_uuid}/sync-from-astra"
        )

        _, headers = make_user(db_session, "requirements_engineer", "re_sync_in")
        resp = client.post(
            f"/api/v1/catalog/parts/{part.id}/sync-from-cadport",
            json={"mass_kg": 0.999},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["mass_kg"] == pytest.approx(0.999)
        assert body["last_sync_origin"] == "cadport"
        # Loop-breaker: outgoing call did NOT fire.
        assert not no_call.called

        db_session.expire_all()
        db_session.refresh(part)
        assert float(part.mass_kg) == pytest.approx(0.999)
        assert part.last_sync_origin == "cadport"

    @respx.mock
    def test_sync_from_cadport_material_only(
        self, client, db_session, test_user, vectornav,
    ):
        part = _make_catalog_part(db_session, test_user, vectornav)
        _, headers = make_user(db_session, "requirements_engineer", "re_sync_mat")
        resp = client.post(
            f"/api/v1/catalog/parts/{part.id}/sync-from-cadport",
            json={"material": "al_6061_t6", "density_kg_m3": 2700.0},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        db_session.expire_all()
        db_session.refresh(part)
        assert part.step_material_key == "al_6061_t6"
        assert float(part.density_kg_m3) == pytest.approx(2700.0)
        assert part.last_sync_origin == "cadport"


class TestMaterialPatchPropagates:

    @respx.mock
    def test_patch_step_material_key_propagates_to_cadport(
        self, client, db_session, test_user, vectornav, cadport_base_url,
    ):
        cadport_uuid = str(uuid.uuid4())
        part = _make_catalog_part(
            db_session, test_user, vectornav, cadport_part_id=cadport_uuid,
        )
        sync_route = respx.post(
            f"{cadport_base_url}/parts/{cadport_uuid}/sync-from-astra"
        ).mock(return_value=Response(200, json={"ok": True}))

        _, headers = make_user(
            db_session, "requirements_engineer", "re_mat_patch",
        )
        resp = client.patch(
            f"/api/v1/catalog/parts/{part.id}",
            json={"step_material_key": "steel_4130"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert sync_route.called
        import json as _json
        body = _json.loads(sync_route.calls.last.request.read())
        assert body["material"] == "steel_4130"

        db_session.expire_all()
        db_session.refresh(part)
        assert part.step_material_key == "steel_4130"
        assert part.last_sync_origin == "astra"
