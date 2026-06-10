"""ASTRA — CADPORT-TDD-SUPPLIER-001 §3.4 supplier-picker tests.

Covers:
  * GET /catalog/suppliers — sorted, includes part counts (reuses
    the existing endpoint; this asserts behaviour, not adds new code).
  * from-cadport with supplier_id (happy path).
  * from-cadport with supplier_name → creates new supplier.
  * from-cadport with case-mismatched name → reuses existing row.
  * from-cadport with neither → 400.
  * from-cadport with both → 400.
  * Live grep: no row gets supplier_name="Wardstone" by default —
    every row's supplier is the explicit choice.
"""

from __future__ import annotations

import uuid

import pytest

from app.models import UserRole
from app.models.catalog import Supplier
from app.routers import catalog as catalog_router
from tests.conftest import make_user


@pytest.fixture(autouse=True)
def patch_supplier_doc_dir(monkeypatch, tmp_path):
    monkeypatch.setattr(
        catalog_router, "SUPPLIER_DOC_DIR", tmp_path / "supplier_docs"
    )


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


@pytest.fixture()
def honeywell(db_session, test_user) -> Supplier:
    s = Supplier(
        name="Honeywell",
        short_name="HW",
        is_active=True,
        is_in_house=False,
        created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _from_cadport_payload(**overrides) -> dict:
    """Minimal valid CADPORT import payload; override fields as needed."""
    base = {
        "cadport_part_id": str(uuid.uuid4()),
        "content_hash": f"sha256:{uuid.uuid4().hex}",
        "source_filename": f"part_{uuid.uuid4().hex[:6]}.step",
        "display_name": "Cube 50mm",
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
        "yaml_filename": "cube_50mm.yaml",
        "yaml_content": "schema_version: '1.0'\nkind: part\n",
    }
    base.update(overrides)
    return base


# ── §3.1 list endpoint sorting + part counts ─────────────────────────


class TestSupplierListEndpoint:

    def test_returns_sorted_with_part_counts(
        self, client, db_session, test_user, vectornav, honeywell
    ):
        _, headers = make_user(db_session, "admin", "list_admin")
        resp = client.get("/api/v1/catalog/suppliers", headers=headers)
        assert resp.status_code == 200, resp.text
        body = resp.json()
        names = [s["name"] for s in body]
        # Honeywell ('H') sorts before VectorNav ('V').
        assert names.index("Honeywell") < names.index("VectorNav")
        # part_count is exposed (0 for the freshly-created fixtures).
        for s in body:
            assert "catalog_part_count" in s
            if s["name"] in ("Honeywell", "VectorNav"):
                assert s["catalog_part_count"] == 0


# ── §3.3 from-cadport dispatch ────────────────────────────────────────


class TestFromCadportSupplierDispatch:

    def test_supplier_id_happy_path(
        self, client, db_session, test_user, vectornav
    ):
        _, headers = make_user(db_session, "requirements_engineer", "re_id")
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=_from_cadport_payload(supplier_id=vectornav.id),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["supplier_id"] == vectornav.id
        assert body["supplier_name"] == "VectorNav"
        assert body["supplier_created"] is False
        assert body["deduped"] is False

    def test_supplier_name_creates_new_supplier(
        self, client, db_session, test_user
    ):
        _, headers = make_user(db_session, "requirements_engineer", "re_create")
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=_from_cadport_payload(supplier_name="Aerospace Composites"),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["supplier_name"] == "Aerospace Composites"
        assert body["supplier_created"] is True
        # Confirm a row landed in the suppliers table.
        new = (
            db_session.query(Supplier)
            .filter(Supplier.name == "Aerospace Composites")
            .first()
        )
        assert new is not None and new.id == body["supplier_id"]

    def test_supplier_name_case_insensitive_reuses(
        self, client, db_session, test_user, vectornav
    ):
        _, headers = make_user(db_session, "requirements_engineer", "re_case")
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=_from_cadport_payload(supplier_name="vectornav"),
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["supplier_id"] == vectornav.id
        # Original casing preserved on the existing row.
        assert body["supplier_name"] == "VectorNav"
        assert body["supplier_created"] is False
        # No duplicate supplier row created.
        rows = (
            db_session.query(Supplier)
            .filter(Supplier.name.ilike("vectornav"))
            .all()
        )
        assert len(rows) == 1

    def test_without_supplier_returns_400(
        self, client, db_session, test_user
    ):
        _, headers = make_user(db_session, "requirements_engineer", "re_neither")
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=_from_cadport_payload(),
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        assert "supplier" in resp.json()["detail"].lower()

    def test_with_both_returns_400(
        self, client, db_session, test_user, vectornav
    ):
        _, headers = make_user(db_session, "requirements_engineer", "re_both")
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=_from_cadport_payload(
                supplier_id=vectornav.id, supplier_name="Honeywell"
            ),
            headers=headers,
        )
        assert resp.status_code == 400, resp.text
        assert "both" in resp.json()["detail"].lower()

    def test_supplier_id_missing_returns_404(
        self, client, db_session, test_user
    ):
        _, headers = make_user(db_session, "requirements_engineer", "re_404")
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=_from_cadport_payload(supplier_id=99999),
            headers=headers,
        )
        assert resp.status_code == 404, resp.text


# ── §3.4 'Wardstone' absent from the import flow ─────────────────────


class TestWardstoneAbsent:

    def test_no_part_lands_with_default_wardstone(
        self, client, db_session, test_user, vectornav
    ):
        """Every part created via from-cadport carries the supplier the
        upload explicitly chose. No silent Wardstone default any more."""
        _, headers = make_user(db_session, "requirements_engineer", "re_no_ws")
        # Upload three parts to VectorNav.
        for i in range(3):
            resp = client.post(
                "/api/v1/catalog/parts/from-cadport",
                json=_from_cadport_payload(supplier_id=vectornav.id),
                headers=headers,
            )
            assert resp.status_code == 201, resp.text
        # No catalog_parts row references a "Wardstone"-named supplier.
        wardstone_count = (
            db_session.query(Supplier)
            .filter(Supplier.name == "Wardstone")
            .count()
        )
        # Pre-existing Wardstone fixtures (if any) are out of scope —
        # we assert NO part row links to one even when one exists.
        ws_id = (
            db_session.query(Supplier.id)
            .filter(Supplier.name == "Wardstone")
            .scalar()
        )
        if ws_id is not None:
            from app.models.catalog import CatalogPart
            n = (
                db_session.query(CatalogPart)
                .filter(CatalogPart.supplier_id == ws_id)
                .count()
            )
            assert n == 0, (
                f"{n} catalog_parts auto-assigned to Wardstone — the fallback "
                f"should be deleted."
            )
        # Sanity: the three rows landed on VectorNav.
        from app.models.catalog import CatalogPart
        vn_count = (
            db_session.query(CatalogPart)
            .filter(CatalogPart.supplier_id == vectornav.id)
            .count()
        )
        assert vn_count == 3
