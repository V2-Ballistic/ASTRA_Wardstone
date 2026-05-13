"""
ASTRA-CLEANUP-002 Phase 4 — catalog deletion + pending-import deletion
========================================================================
File: backend/tests/test_catalog_deletion.py

Coverage (matching the design report §4 + Q5 fixture decision):

  1. DELETE /pending-imports/{id} hard-deletes the row and cascade-
     deletes the linked supplier_document iff no other live ref holds.
  2. DELETE /pending-imports/{id} cascades to delete the supplier_document
     only when no other pending_import + no live catalog_part references it.
  3. GET /parts/{id}/usage-report on an unused part → deletable=True,
     total_references=0.
  4. GET /parts/{id}/usage-report on a part with project_parts →
     deletable=False, projects list populated.
  5. DELETE /parts/{id} on an unused part → 200, soft_delete=True,
     deleted_at is set.
  6. DELETE /parts/{id} on a part with project_parts → 409 + structured
     usage detail (code='part_in_use').
  7. DELETE /parts/{id} on a part with mechanical_joints reaching it
     transitively (catalog_part ← project_parts ← mechanical_joints
     via part_a_id) → 409. Q5: real Project + ProjectPart + MechanicalJoint
     chain — no mocking, no skipping. Mechanical joint stays in a row
     until teardown via the per-test SQLite engine teardown.

catalog_assembly_components is intentionally NOT covered — Phase 0
confirmed the table does not exist in the live schema (gotcha #8).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.catalog import (
    CatalogPart,
    LifecycleStatus,
    LRUClass,
    PartClass,
    PendingCatalogImport,
    PendingImportStatus,
    Supplier,
    SupplierDocument,
    SupplierDocumentType,
)
from app.models.parts_library import (
    BomStatus,
    JointStatus,
    JointType,
    MechanicalJoint,
    ProjectPart,
)


# ══════════════════════════════════════════════════════════════
#  Builders — direct ORM inserts (no router hops)
# ══════════════════════════════════════════════════════════════

def _mk_supplier(db: Session, owner_id: int, name: str = "TestSup") -> Supplier:
    s = Supplier(name=name, is_active=True, created_by_id=owner_id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _mk_supplier_doc(
    db: Session, supplier_id: int, uploader_id: int,
    sha256: str = "a" * 64, title: str = "doc.step",
) -> SupplierDocument:
    doc = SupplierDocument(
        supplier_id=supplier_id,
        title=title,
        document_type=SupplierDocumentType.OTHER,
        file_path=f"/tmp/{title}",
        file_size_bytes=1024,
        sha256=sha256,
        mime_type="application/octet-stream",
        uploaded_by_id=uploader_id,
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def _mk_pending_import(
    db: Session, supplier_id: int, source_doc_id: int,
    status: PendingImportStatus = PendingImportStatus.PENDING,
) -> PendingCatalogImport:
    pi = PendingCatalogImport(
        supplier_id=supplier_id,
        source_document_id=source_doc_id,
        extracted_data={"part_number": "T-001", "name": "Test part"},
        status=status,
    )
    db.add(pi)
    db.commit()
    db.refresh(pi)
    return pi


def _mk_catalog_part(
    db: Session, owner_id: int, supplier_id: int,
    part_number: str = "CP-001", source_document_id: int | None = None,
) -> CatalogPart:
    cp = CatalogPart(
        supplier_id=supplier_id,
        part_number=part_number,
        name=f"Part {part_number}",
        part_class=PartClass.PROCESSOR,
        lru_classification=LRUClass.LRU,
        lifecycle_status=LifecycleStatus.ACTIVE,
        created_by_id=owner_id,
        source_document_id=source_document_id,
    )
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp


def _mk_project_part(
    db: Session, project_id: int, catalog_part_id: int, owner_id: int,
    bom_position: str | None = None,
) -> ProjectPart:
    pp = ProjectPart(
        project_id=project_id,
        catalog_part_id=catalog_part_id,
        quantity=Decimal("1.0"),
        quantity_unit="each",
        status=BomStatus.PLANNED,
        bom_position=bom_position,
        added_by_id=owner_id,
    )
    db.add(pp)
    db.commit()
    db.refresh(pp)
    return pp


def _mk_mechanical_joint(
    db: Session, project_id: int, part_a_id: int, part_b_id: int, owner_id: int,
    joint_id: str = "J-001",
) -> MechanicalJoint:
    mj = MechanicalJoint(
        joint_id=joint_id,
        project_id=project_id,
        joint_type=JointType.BOLTED,
        part_a_id=part_a_id,
        part_b_id=part_b_id,
        status=JointStatus.DRAFT,
        created_by_id=owner_id,
    )
    db.add(mj)
    db.commit()
    db.refresh(mj)
    return mj


# ══════════════════════════════════════════════════════════════
#  Pending-import deletion (AD-6)
# ══════════════════════════════════════════════════════════════

class TestDeletePendingImport:

    def test_delete_pending_import_cascades_supplier_doc_when_orphan(
        self, client: TestClient, db_session: Session, test_user, auth_headers,
    ):
        sup = _mk_supplier(db_session, test_user.id)
        doc = _mk_supplier_doc(db_session, sup.id, test_user.id, sha256="b" * 64)
        pi = _mk_pending_import(db_session, sup.id, doc.id)
        # Capture as ints up front. The endpoint runs against the same
        # session via the dep override, and its bulk DELETE on supplier_doc
        # doesn't sync the identity map — accessing doc.id afterward would
        # trip ObjectDeletedError.
        pi_id, doc_id = pi.id, doc.id

        resp = client.delete(
            f"/api/v1/catalog/pending-imports/{pi_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["deleted"] is True
        assert body["id"] == pi_id
        assert body["supplier_document_deleted"] is True

        db_session.expire_all()
        assert (
            db_session.query(PendingCatalogImport)
            .filter(PendingCatalogImport.id == pi_id).first()
        ) is None
        assert (
            db_session.query(SupplierDocument)
            .filter(SupplierDocument.id == doc_id).first()
        ) is None

    def test_delete_pending_import_keeps_supplier_doc_when_referenced_by_catalog_part(
        self, client: TestClient, db_session: Session, test_user, auth_headers,
    ):
        sup = _mk_supplier(db_session, test_user.id)
        doc = _mk_supplier_doc(db_session, sup.id, test_user.id, sha256="c" * 64)
        # An approved catalog_part sourced from the same supplier_document.
        # That part is LIVE (deleted_at IS NULL), so deleting the pending
        # row must not cascade-delete the supplier_document.
        _mk_catalog_part(
            db_session, test_user.id, sup.id, "CP-RTN",
            source_document_id=doc.id,
        )
        pi = _mk_pending_import(db_session, sup.id, doc.id)

        resp = client.delete(
            f"/api/v1/catalog/pending-imports/{pi.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["deleted"] is True
        assert body["supplier_document_deleted"] is False

        assert (
            db_session.query(SupplierDocument)
            .filter(SupplierDocument.id == doc.id).first()
        ) is not None

    def test_delete_missing_pending_import_returns_404(
        self, client: TestClient, auth_headers,
    ):
        resp = client.delete(
            "/api/v1/catalog/pending-imports/999999",
            headers=auth_headers,
        )
        assert resp.status_code == 404, resp.text


# ══════════════════════════════════════════════════════════════
#  Usage report (AD-8)
# ══════════════════════════════════════════════════════════════

class TestCatalogPartUsageReport:

    def test_unused_part_is_deletable(
        self, client: TestClient, db_session: Session, test_user, auth_headers,
    ):
        sup = _mk_supplier(db_session, test_user.id)
        part = _mk_catalog_part(db_session, test_user.id, sup.id, "UNUSED-1")

        resp = client.get(
            f"/api/v1/catalog/parts/{part.id}/usage-report",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["part_id"] == part.id
        assert body["deletable"] is True
        assert body["total_references"] == 0
        assert body["projects"] == []

    def test_part_with_project_part_is_not_deletable(
        self, client: TestClient, db_session: Session,
        test_user, test_project, auth_headers,
    ):
        sup = _mk_supplier(db_session, test_user.id)
        part = _mk_catalog_part(db_session, test_user.id, sup.id, "USED-1")
        _mk_project_part(db_session, test_project.id, part.id, test_user.id, "1.1")

        resp = client.get(
            f"/api/v1/catalog/parts/{part.id}/usage-report",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["deletable"] is False
        assert body["total_references"] == 1
        assert len(body["projects"]) == 1
        proj = body["projects"][0]
        assert proj["project_id"] == test_project.id
        assert proj["project_code"] == test_project.code
        assert proj["project_part_count"] == 1
        assert proj["mechanical_joint_count"] == 0


# ══════════════════════════════════════════════════════════════
#  Catalog part deletion (AD-7)
# ══════════════════════════════════════════════════════════════

class TestDeleteCatalogPart:

    def test_delete_unused_part_soft_deletes(
        self, client: TestClient, db_session: Session, test_user, auth_headers,
    ):
        sup = _mk_supplier(db_session, test_user.id)
        part = _mk_catalog_part(db_session, test_user.id, sup.id, "DEL-1")

        resp = client.delete(
            f"/api/v1/catalog/parts/{part.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "deleted"
        assert body["id"] == part.id
        assert body.get("soft_delete") is True

        db_session.expire_all()
        refreshed = db_session.query(CatalogPart).filter(CatalogPart.id == part.id).first()
        assert refreshed is not None
        assert refreshed.deleted_at is not None
        assert isinstance(refreshed.deleted_at, datetime)

    def test_delete_part_with_project_part_is_blocked_with_usage(
        self, client: TestClient, db_session: Session,
        test_user, test_project, auth_headers,
    ):
        sup = _mk_supplier(db_session, test_user.id)
        part = _mk_catalog_part(db_session, test_user.id, sup.id, "BLOCK-1")
        _mk_project_part(db_session, test_project.id, part.id, test_user.id, "2.1")

        resp = client.delete(
            f"/api/v1/catalog/parts/{part.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "part_in_use"
        assert "usage" in detail
        usage = detail["usage"]
        assert usage["deletable"] is False
        assert usage["total_references"] >= 1
        assert any(p["project_id"] == test_project.id for p in usage["projects"])

        # Part still alive (not soft-deleted) — 409 must not silently soft-delete.
        db_session.expire_all()
        refreshed = db_session.query(CatalogPart).filter(CatalogPart.id == part.id).first()
        assert refreshed is not None
        assert refreshed.deleted_at is None

    def test_delete_part_with_transitive_mechanical_joint_is_blocked(
        self, client: TestClient, db_session: Session,
        test_user, test_project, auth_headers,
    ):
        """Q5 (option a): real catalog_part ← project_part ← mechanical_joint
        chain. The transitive count surfaces in the usage report through
        part_a_id; the part must 409 on delete."""
        sup = _mk_supplier(db_session, test_user.id)
        part_used = _mk_catalog_part(db_session, test_user.id, sup.id, "JOINT-A")
        # The joint needs TWO project_parts (part_a + part_b). Only one
        # of them is linked back to the catalog_part under test — that's
        # enough to exercise the transitive count.
        pp_a = _mk_project_part(
            db_session, test_project.id, part_used.id, test_user.id, "3.1",
        )
        # Second project_part for joint.part_b — any catalog_part will do.
        part_other = _mk_catalog_part(db_session, test_user.id, sup.id, "JOINT-B")
        pp_b = _mk_project_part(
            db_session, test_project.id, part_other.id, test_user.id, "3.2",
        )
        _mk_mechanical_joint(
            db_session, test_project.id, pp_a.id, pp_b.id, test_user.id,
            joint_id="MJ-TRANSITIVE-1",
        )

        # Usage report surfaces both the direct (BOM line) AND the
        # transitive (joint) count for part_used.
        usage = client.get(
            f"/api/v1/catalog/parts/{part_used.id}/usage-report",
            headers=auth_headers,
        ).json()
        assert usage["deletable"] is False
        proj = next(p for p in usage["projects"] if p["project_id"] == test_project.id)
        assert proj["project_part_count"] == 1
        assert proj["mechanical_joint_count"] == 1

        # Delete is blocked with the structured 409.
        resp = client.delete(
            f"/api/v1/catalog/parts/{part_used.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "part_in_use"
        assert detail["usage"]["deletable"] is False
