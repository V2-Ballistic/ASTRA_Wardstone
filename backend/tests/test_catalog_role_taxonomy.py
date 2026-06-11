"""Config-ecosystem deltas (spec §7.2) — catalog role taxonomy tests.

Covers:
  * from-cadport with a role → persisted on catalog_parts.role and
    echoed in CatalogPartImportResult (round-trip).
  * from-cadport with an invalid role → 422 (pydantic field validator).
  * role exposed on catalog part detail + list responses.
  * PATCH /api/v1/catalog/parts/{id}/role — set / clear / 422 on a
    bad value (mirrors the PATCH /mass auth pattern).
  * Taxonomy constant parity with CADPORT's services/roles.py.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.catalog import CATALOG_PART_ROLE_TAXONOMY, CatalogPart, Supplier
from app.routers import catalog as catalog_router
from tests.conftest import make_user


@pytest.fixture(autouse=True)
def patch_supplier_doc_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(
        catalog_router, "SUPPLIER_DOC_DIR", tmp_path / "supplier_docs",
        raising=False,
    )
    from app.routers import cadport as cadport_router
    monkeypatch.setattr(
        cadport_router, "SUPPLIER_DOC_DIR", tmp_path / "supplier_docs"
    )


@pytest.fixture()
def supplier(db_session, test_user) -> Supplier:
    s = Supplier(
        name="Wardstone Machining",
        short_name="WM",
        is_active=True,
        is_in_house=True,
        created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _from_cadport_payload(**overrides) -> dict:
    base = {
        "cadport_part_id": str(uuid.uuid4()),
        "content_hash": f"sha256:{uuid.uuid4().hex}",
        "source_filename": f"part_{uuid.uuid4().hex[:6]}.step",
        "display_name": "Nose Cone",
        "internal_part_number": None,
        "material": "al_6061_t6",
        "configuration": "Default",
        "solidworks_version": None,
        "mass_kg": 0.34,
        "volume_m3": 1.25e-4,
        "surface_area_m2": 0.015,
        "density_kg_m3": 2700.0,
        "center_of_mass_m": [0.025, 0.025, 0.025],
        "inertia": {
            "ixx": 1.0e-5, "iyy": 1.0e-5, "izz": 1.0e-5,
            "ixy": 0.0, "ixz": 0.0, "iyz": 0.0,
        },
        "yaml_filename": "nose_cone.yaml",
        "yaml_content": "schema_version: '1.0'\nkind: part\n",
    }
    base.update(overrides)
    return base


def test_taxonomy_constant_matches_cadport():
    """Mirror guard: keep identical to CADPORT's
    cadport/services/roles.py::ROLE_TAXONOMY."""
    assert CATALOG_PART_ROLE_TAXONOMY == (
        "oml", "structure", "avionics", "payload",
        "propulsion", "recovery", "ballast", "other",
    )


class TestFromCadportRole:

    def test_role_round_trip(self, client, db_session, test_user, supplier):
        _, headers = make_user(db_session, "requirements_engineer", "re_role")
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=_from_cadport_payload(supplier_id=supplier.id, role="oml"),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["role"] == "oml"

        # Persisted on the row.
        row = (
            db_session.query(CatalogPart)
            .filter(CatalogPart.id == body["catalog_part_id"])
            .first()
        )
        assert row is not None and row.role == "oml"

        # Exposed on detail + list responses.
        detail = client.get(
            f"/api/v1/catalog/parts/{body['catalog_part_id']}", headers=headers
        )
        assert detail.status_code == 200, detail.text
        assert detail.json()["role"] == "oml"

        listing = client.get("/api/v1/catalog/parts", headers=headers)
        assert listing.status_code == 200, listing.text
        payload = listing.json()
        items = payload["items"] if isinstance(payload, dict) else payload
        ours = [i for i in items if i["id"] == body["catalog_part_id"]]
        assert ours and ours[0]["role"] == "oml"

    def test_role_omitted_is_null(self, client, db_session, test_user, supplier):
        _, headers = make_user(db_session, "requirements_engineer", "re_norole")
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=_from_cadport_payload(supplier_id=supplier.id),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["role"] is None

    def test_invalid_role_422(self, client, db_session, test_user, supplier):
        _, headers = make_user(db_session, "requirements_engineer", "re_badrole")
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=_from_cadport_payload(supplier_id=supplier.id, role="fuselage"),
            headers=headers,
        )
        assert resp.status_code == 422, resp.text
        # No row created.
        assert (
            db_session.query(CatalogPart)
            .filter(CatalogPart.name == "Nose Cone")
            .count()
            == 0
        )


class TestPatchRole:

    def _create_part(self, client, db_session, supplier, headers) -> int:
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=_from_cadport_payload(supplier_id=supplier.id),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return resp.json()["catalog_part_id"]

    def test_patch_sets_and_clears(self, client, db_session, test_user, supplier):
        _, headers = make_user(db_session, "requirements_engineer", "re_patch")
        part_id = self._create_part(client, db_session, supplier, headers)

        resp = client.patch(
            f"/api/v1/catalog/parts/{part_id}/role",
            json={"role": "oml"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["role"] == "oml"
        assert body["is_airframe"] is True

        # Detail reflects it.
        detail = client.get(f"/api/v1/catalog/parts/{part_id}", headers=headers)
        assert detail.json()["role"] == "oml"

        # Non-airframe role.
        resp = client.patch(
            f"/api/v1/catalog/parts/{part_id}/role",
            json={"role": "avionics"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] == "avionics"
        assert resp.json()["is_airframe"] is False

        # null clears.
        resp = client.patch(
            f"/api/v1/catalog/parts/{part_id}/role",
            json={"role": None},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["role"] is None

    def test_patch_invalid_role_422(self, client, db_session, test_user, supplier):
        _, headers = make_user(db_session, "requirements_engineer", "re_patch422")
        part_id = self._create_part(client, db_session, supplier, headers)

        resp = client.patch(
            f"/api/v1/catalog/parts/{part_id}/role",
            json={"role": "wing"},
            headers=headers,
        )
        assert resp.status_code == 422, resp.text
        assert "Invalid role" in resp.text

    def test_patch_unknown_part_404(self, client, db_session, test_user):
        _, headers = make_user(db_session, "requirements_engineer", "re_patch404")
        resp = client.patch(
            "/api/v1/catalog/parts/999999/role",
            json={"role": "oml"},
            headers=headers,
        )
        assert resp.status_code == 404, resp.text

    def test_patch_requires_req_eng_plus(self, client, db_session, test_user, supplier):
        _, re_headers = make_user(db_session, "requirements_engineer", "re_creator2")
        part_id = self._create_part(client, db_session, supplier, re_headers)
        _, viewer_headers = make_user(db_session, "stakeholder", "stakeholder_role")
        resp = client.patch(
            f"/api/v1/catalog/parts/{part_id}/role",
            json={"role": "oml"},
            headers=viewer_headers,
        )
        assert resp.status_code == 403, resp.text
