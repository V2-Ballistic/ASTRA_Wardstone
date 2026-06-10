"""ASTRA — CADPORT-TDD-ASTRA-BRIDGE-001 Phase 2 source-files tests.

Covers:
  * STEP-only upload → 1 step row in supplier_documents, FK populated.
  * SLDPRT upload → 2 rows (sldprt + step from auto-export), both FKs.
  * GET /catalog/parts/{id}/source-files returns the entries.
  * GET /catalog/parts/{id}/source-files/{kind} streams the bytes;
    sha256 of the body matches the stored sha256.
  * Part with no source files → empty list.
"""

from __future__ import annotations

import base64
import hashlib
import uuid

import pytest

from app.models.catalog import (
    CatalogPart,
    Supplier,
    SupplierDocument,
    SupplierDocumentType,
)
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
        name="VectorNav", short_name="VN", is_active=True,
        is_in_house=False, created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture()
def in_house_supplier(db_session, test_user) -> Supplier:
    s = Supplier(
        name="Wardstone", short_name="WS", is_in_house=True,
        is_active=True, created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


def _encode(b: bytes) -> str:
    return base64.b64encode(b).decode("ascii")


def _payload(**overrides):
    base = {
        "cadport_part_id": str(uuid.uuid4()),
        "content_hash": f"sha256:{uuid.uuid4().hex}",
        "source_filename": "cube_100mm.step",
        "display_name": "Cube 100mm",
        "internal_part_number": None,
        "material": None,
        "configuration": "Default",
        "solidworks_version": None,
        "mass_kg": 0.0,
        "volume_m3": 1.0e-3,
        "surface_area_m2": 0.06,
        "density_kg_m3": 0.0,
        "center_of_mass_m": [0.0, 0.0, 0.0],
        "inertia": {
            "ixx": 0.0, "iyy": 0.0, "izz": 0.0,
            "ixy": 0.0, "ixz": 0.0, "iyz": 0.0,
        },
        "yaml_filename": "cube.yaml",
        "yaml_content": "schema_version: 1.0\nkind: part\n",
        "source_format": "step",
        "mass_source": "cad",
    }
    base.update(overrides)
    return base


class TestSourceFilesPersistence:

    def test_step_only_upload_creates_one_step_supplier_document(
        self, client, db_session, test_user, vectornav,
    ):
        """STEP-path upload → 1 supplier_documents row of kind 'step'
        + the catalog_parts FK populated."""
        step_bytes = b"ISO-10303-21;\nHEADER;...DUMMY STEP BODY...\nEND-ISO-10303-21;\n"
        _, headers = make_user(db_session, "requirements_engineer", "re_step_only")
        payload = _payload(
            supplier_id=vectornav.id,
            source_files=[
                {
                    "kind": "step",
                    "filename": "cube_100mm.step",
                    "sha256": hashlib.sha256(step_bytes).hexdigest(),
                    "content_base64": _encode(step_bytes),
                },
            ],
        )
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=payload, headers=headers,
        )
        assert resp.status_code == 201, resp.text
        part_id = resp.json()["catalog_part_id"]
        part = db_session.query(CatalogPart).filter_by(id=part_id).one()
        assert part.step_document_id is not None
        assert part.sldprt_document_id is None
        assert part.sldasm_document_id is None
        # The supplier_document row holds the right metadata.
        doc = db_session.query(SupplierDocument).filter_by(
            id=part.step_document_id
        ).one()
        assert doc.document_type == SupplierDocumentType.STEP
        assert doc.original_filename == "cube_100mm.step"
        assert doc.sha256 == hashlib.sha256(step_bytes).hexdigest()
        assert doc.mime_type == "application/step"

    def test_sldprt_upload_creates_two_supplier_documents(
        self, client, db_session, test_user, vectornav,
    ):
        """SLDPRT path simulation — payload carries both sldprt and the
        auto-exported step. Both FKs populated, both rows present."""
        sldprt_bytes = b"DUMMY SOLIDWORKS PART BYTES"
        step_bytes = b"ISO-10303-21; DUMMY AUTOEXPORTED STEP"
        _, headers = make_user(db_session, "requirements_engineer", "re_sldprt")
        payload = _payload(
            supplier_id=vectornav.id,
            source_filename="bracket.SLDPRT",
            source_files=[
                {
                    "kind": "sldprt",
                    "filename": "bracket.SLDPRT",
                    "sha256": hashlib.sha256(sldprt_bytes).hexdigest(),
                    "content_base64": _encode(sldprt_bytes),
                },
                {
                    "kind": "step",
                    "filename": "bracket.step",
                    "sha256": hashlib.sha256(step_bytes).hexdigest(),
                    "content_base64": _encode(step_bytes),
                },
            ],
        )
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=payload, headers=headers,
        )
        assert resp.status_code == 201, resp.text
        part_id = resp.json()["catalog_part_id"]
        part = db_session.query(CatalogPart).filter_by(id=part_id).one()
        assert part.sldprt_document_id is not None
        assert part.step_document_id is not None
        assert part.sldasm_document_id is None


class TestSourceFilesEndpoints:

    def _upload_step_part(
        self, client, db_session, test_user, vectornav,
    ) -> tuple[int, bytes]:
        step_bytes = b"ISO-10303-21;\n--SMOKE--\nEND-ISO-10303-21;\n"
        _, headers = make_user(db_session, "requirements_engineer", f"re_dl_{uuid.uuid4().hex[:6]}")
        payload = _payload(
            supplier_id=vectornav.id,
            source_files=[
                {
                    "kind": "step",
                    "filename": "smoke.step",
                    "sha256": hashlib.sha256(step_bytes).hexdigest(),
                    "content_base64": _encode(step_bytes),
                },
            ],
        )
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=payload, headers=headers,
        )
        assert resp.status_code == 201, resp.text
        return int(resp.json()["catalog_part_id"]), step_bytes

    def test_list_source_files(
        self, client, db_session, test_user, vectornav,
    ):
        part_id, _ = self._upload_step_part(client, db_session, test_user, vectornav)
        _, headers = make_user(db_session, "requirements_engineer", "re_list")
        resp = client.get(
            f"/api/v1/catalog/parts/{part_id}/source-files", headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body) == 1
        entry = body[0]
        assert entry["kind"] == "step"
        assert entry["filename"] == "smoke.step"
        assert entry["download_url"] == (
            f"/api/v1/catalog/parts/{part_id}/source-files/step"
        )

    def test_download_returns_correct_bytes(
        self, client, db_session, test_user, vectornav,
    ):
        part_id, step_bytes = self._upload_step_part(
            client, db_session, test_user, vectornav,
        )
        _, headers = make_user(db_session, "requirements_engineer", "re_dl_step")
        resp = client.get(
            f"/api/v1/catalog/parts/{part_id}/source-files/step",
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.content == step_bytes
        # sha256 of the response body matches the stored hash.
        body_sha = hashlib.sha256(resp.content).hexdigest()
        expected_sha = hashlib.sha256(step_bytes).hexdigest()
        assert body_sha == expected_sha

    def test_part_with_no_source_files_returns_empty_list(
        self, client, db_session, test_user, vectornav,
    ):
        """Build a part WITHOUT source_files in the payload —
        legacy-row simulation. The list endpoint returns []."""
        _, headers = make_user(db_session, "requirements_engineer", "re_empty")
        resp = client.post(
            "/api/v1/catalog/parts/from-cadport",
            json=_payload(supplier_id=vectornav.id),  # no source_files key
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        part_id = resp.json()["catalog_part_id"]
        list_resp = client.get(
            f"/api/v1/catalog/parts/{part_id}/source-files", headers=headers,
        )
        assert list_resp.status_code == 200
        assert list_resp.json() == []

    def test_download_unknown_kind_returns_400(
        self, client, db_session, test_user, vectornav,
    ):
        part_id, _ = self._upload_step_part(client, db_session, test_user, vectornav)
        _, headers = make_user(db_session, "requirements_engineer", "re_400_kind")
        resp = client.get(
            f"/api/v1/catalog/parts/{part_id}/source-files/iges",
            headers=headers,
        )
        assert resp.status_code == 400

    def test_download_missing_kind_returns_404(
        self, client, db_session, test_user, vectornav,
    ):
        part_id, _ = self._upload_step_part(client, db_session, test_user, vectornav)
        # The STEP-only upload has no SLDPRT — asking for it 404s.
        _, headers = make_user(db_session, "requirements_engineer", "re_404_kind")
        resp = client.get(
            f"/api/v1/catalog/parts/{part_id}/source-files/sldprt",
            headers=headers,
        )
        assert resp.status_code == 404
