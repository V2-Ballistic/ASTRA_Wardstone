"""
ASTRA — ICD Extraction Pipeline Tests
======================================
File: backend/tests/test_icd_extraction.py   ← NEW (Phase 7, ASTRA-TDD-INTF-002)

Mocks the Anthropic / LLM call; no live API tokens are spent.

Coverage (10 cases per phase prompt):

 1. Synthetic ICD fixture: tiny PDF + mocked extraction returns the same
    schema → trigger_extraction creates PENDING_REVIEW PendingCatalogImport.
 2. Schema validation: malformed AI response → PendingCatalogImport
    NOT created; SupplierDocument.extraction_status=FAILED with error in
    extraction_log.
 3. Approve flow: pending → POST /approve → Supplier + CatalogPart +
    Connectors + Pins exist atomically. Counts verified.
 4. Approve with existing supplier (name match): re-uses, doesn't dup.
 5. Reject flow: status=REJECTED, no catalog rows.
 6. Re-uploading the same SHA-256 to the same supplier returns 409
    (Phase 2 dedup behaviour, regression-test).
 7. RBAC: stakeholder cannot approve (403); req_eng / admin / pm can.
 8. Atomicity: pin creation fails mid-way → whole transaction rolls back.
 9. Status guard: approving an already-APPROVED or REJECTED pending → 409.
10. Document status linkage: after approve SupplierDocument is APPROVED.
"""

from __future__ import annotations

import io
from copy import deepcopy
from unittest.mock import patch

import pytest
from reportlab.pdfgen import canvas

from app.models import UserRole
from app.models.catalog import (
    CatalogConnector,
    CatalogPart,
    CatalogPin,
    ExtractionStatus,
    PendingCatalogImport,
    PendingImportStatus,
    Supplier,
    SupplierDocument,
    SupplierDocumentType,
)
from app.routers import catalog as catalog_router
from app.services.catalog import icd_extractor
from tests.conftest import make_user


# ──────────────────────────────────────────────────────────────
#  Fixtures
# ──────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def patch_supplier_doc_dir(monkeypatch, tmp_path):
    """Per-test storage so we never write to /data/supplier_docs/."""
    monkeypatch.setattr(catalog_router, "SUPPLIER_DOC_DIR", tmp_path / "supplier_docs")


@pytest.fixture
def synthetic_pdf_bytes() -> bytes:
    """Tiny in-memory PDF made via reportlab — guaranteed parseable by PyMuPDF."""
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    c.drawString(72, 720, "ASTRA Synthetic ICD — RSP-100")
    c.drawString(72, 700, "Manufacturer: Acme Avionics")
    c.drawString(72, 680, "Pin 1: VCC_28V (POWER, 28V)")
    c.drawString(72, 660, "Pin 2: GND (GROUND)")
    c.showPage()
    c.save()
    buf.seek(0)
    return buf.getvalue()


@pytest.fixture
def supplier(db_session, test_user) -> Supplier:
    s = Supplier(
        name="Acme Avionics",
        cage_code="0ACME",
        country="USA",
        is_active=True,
        created_by_id=test_user.id,
    )
    db_session.add(s)
    db_session.commit()
    db_session.refresh(s)
    return s


@pytest.fixture
def uploaded_document(db_session, supplier, test_user, tmp_path, synthetic_pdf_bytes):
    """A SupplierDocument row pointing at a real on-disk PDF (so PyMuPDF works)."""
    storage = tmp_path / "supplier_docs"
    storage.mkdir(exist_ok=True)
    pdf_path = storage / "synthetic.pdf"
    pdf_path.write_bytes(synthetic_pdf_bytes)

    doc = SupplierDocument(
        supplier_id=supplier.id,
        title="RSP-100 Datasheet",
        document_type=SupplierDocumentType.DATASHEET,
        file_path=str(pdf_path),
        file_size_bytes=len(synthetic_pdf_bytes),
        sha256="a" * 64,
        mime_type="application/pdf",
        page_count=None,
        extraction_status=ExtractionStatus.UPLOADED,
        uploaded_by_id=test_user.id,
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)
    return doc


def _good_extraction_payload(**overrides) -> dict:
    """Returns a minimal-but-complete payload matching IcdExtractionResultSchema."""
    payload = {
        "supplier": {
            "name": "Acme Avionics",
            "cage_code": "0ACME",
            "country": "USA",
            "source_page": 1,
        },
        "part_number": "RSP-100",
        "revision": "A",
        "name": "Radar Signal Processor",
        "designation": "RSP-100",
        "description": "Synthetic test part",
        "part_class": "processor",
        "lru_classification": "lru",
        "mass_kg": 2.3,
        "power_watts_nominal": 45.0,
        "temp_operating_min_c": -40.0,
        "temp_operating_max_c": 85.0,
        "lifecycle_status": "active",
        "connectors": [
            {
                "reference": "J1",
                "connector_type": "MIL-DTL-38999/III",
                "gender": "female",
                "pin_count": 2,
                "pins": [
                    {
                        "pin_position": "1",
                        "mfr_pin_name": "VCC_28V",
                        "mfr_signal_type": "power",
                        "mfr_direction": "power",
                        "mfr_voltage_min_v": 22.0,
                        "mfr_voltage_max_v": 32.0,
                    },
                    {
                        "pin_position": "2",
                        "mfr_pin_name": "GND",
                        "mfr_signal_type": "ground",
                        "mfr_direction": "ground",
                    },
                ],
            },
        ],
        "extraction_warnings": [],
        "extraction_confidence": 0.92,
    }
    payload.update(overrides)
    return payload


def _patch_ai(payload: dict | None = None):
    """Convenience: yields a context that mocks the AI client to return ``payload``.

    Patches both ``is_ai_available`` (force True so the orchestrator doesn't
    fail at the gating step) and ``LLMClient.complete`` (returns ``payload``).
    The patches are applied at the import path used inside icd_extractor —
    that module does its OWN ``from app.services.ai.llm_client import ...`` at
    call time, so we patch the source module.
    """
    from contextlib import ExitStack
    stack = ExitStack()
    stack.enter_context(patch("app.services.ai.llm_client.is_ai_available", return_value=True))
    stack.enter_context(patch.object(icd_extractor, "__name__", icd_extractor.__name__))
    # Patch the LLMClient.complete method on the class so any instance the
    # orchestrator creates will return our payload.
    stack.enter_context(patch(
        "app.services.ai.llm_client.LLMClient.complete",
        return_value=deepcopy(payload) if payload is not None else None,
    ))
    return stack


# ──────────────────────────────────────────────────────────────
#  Group A — orchestrator (services/catalog/icd_extractor.py)
# ──────────────────────────────────────────────────────────────

class TestTriggerExtraction:

    def test_happy_path_creates_pending_review(self, db_session, uploaded_document):
        """Case 1: synthetic PDF + mocked AI → PendingCatalogImport(PENDING)."""
        with _patch_ai(_good_extraction_payload()):
            pending_id = icd_extractor.trigger_extraction(db_session, uploaded_document.id)

        assert pending_id is not None

        db_session.expire_all()
        doc = db_session.query(SupplierDocument).get(uploaded_document.id)
        assert doc.extraction_status == ExtractionStatus.PENDING_REVIEW
        assert doc.page_count == 1
        assert doc.extraction_log is not None
        assert doc.extraction_log.get("code") == "ok"

        pending = db_session.query(PendingCatalogImport).get(pending_id)
        assert pending is not None
        assert pending.status == PendingImportStatus.PENDING
        assert pending.supplier_id == uploaded_document.supplier_id
        assert pending.extracted_data["part_number"] == "RSP-100"
        assert len(pending.extracted_data["connectors"]) == 1
        assert len(pending.extracted_data["connectors"][0]["pins"]) == 2

    def test_schema_validation_rejection_marks_failed(self, db_session, uploaded_document):
        """Case 2: AI returns malformed JSON → status=FAILED, no PendingCatalogImport."""
        # Missing required `supplier` block AND `part_number` AND `name`.
        bad = {"description": "Just some text", "connectors": []}

        with _patch_ai(bad):
            result = icd_extractor.trigger_extraction(db_session, uploaded_document.id)

        assert result is None
        db_session.expire_all()
        doc = db_session.query(SupplierDocument).get(uploaded_document.id)
        assert doc.extraction_status == ExtractionStatus.FAILED
        assert doc.extraction_log["code"] == "schema_invalid"
        assert "errors" in doc.extraction_log["detail"]
        # No PendingCatalogImport created.
        assert db_session.query(PendingCatalogImport).count() == 0

    def test_ai_unavailable_marks_failed(self, db_session, uploaded_document):
        """No AI provider configured → FAILED with code=ai_unavailable."""
        # Force is_ai_available → False (don't patch LLMClient.complete).
        with patch("app.services.ai.llm_client.is_ai_available", return_value=False):
            result = icd_extractor.trigger_extraction(db_session, uploaded_document.id)

        assert result is None
        db_session.expire_all()
        doc = db_session.query(SupplierDocument).get(uploaded_document.id)
        assert doc.extraction_status == ExtractionStatus.FAILED
        assert doc.extraction_log["code"] == "ai_unavailable"

    def test_ai_returns_none_marks_failed(self, db_session, uploaded_document):
        """LLMClient.complete returning None (network/parse failure) → FAILED."""
        with _patch_ai(None):
            result = icd_extractor.trigger_extraction(db_session, uploaded_document.id)

        assert result is None
        db_session.expire_all()
        doc = db_session.query(SupplierDocument).get(uploaded_document.id)
        assert doc.extraction_status == ExtractionStatus.FAILED
        assert doc.extraction_log["code"] == "ai_returned_null"

    def test_already_pending_review_is_idempotent_skip(self, db_session, uploaded_document):
        """Re-running on a doc already PENDING_REVIEW returns None immediately."""
        uploaded_document.extraction_status = ExtractionStatus.PENDING_REVIEW
        db_session.commit()
        with _patch_ai(_good_extraction_payload()):
            result = icd_extractor.trigger_extraction(db_session, uploaded_document.id)
        assert result is None
        # Doc status unchanged — orchestrator skipped without touching it.
        db_session.expire_all()
        doc = db_session.query(SupplierDocument).get(uploaded_document.id)
        assert doc.extraction_status == ExtractionStatus.PENDING_REVIEW


# ──────────────────────────────────────────────────────────────
#  Group B — Approve / Reject endpoints (HTTP layer)
# ──────────────────────────────────────────────────────────────

@pytest.fixture
def pending_import(db_session, uploaded_document):
    """A PendingCatalogImport ready for approval."""
    pending = PendingCatalogImport(
        source_document_id=uploaded_document.id,
        supplier_id=uploaded_document.supplier_id,
        extracted_data=_good_extraction_payload(),
        extraction_warnings=None,
        extraction_confidence=0.92,
        status=PendingImportStatus.PENDING,
    )
    db_session.add(pending)
    uploaded_document.extraction_status = ExtractionStatus.PENDING_REVIEW
    db_session.commit()
    db_session.refresh(pending)
    return pending


class TestApproveEndpoint:

    def test_approve_creates_supplier_part_connectors_pins(
        self, client, db_session, pending_import,
    ):
        """Case 3: approve creates the full tree atomically."""
        _, headers = make_user(db_session, "admin", "approver_admin")
        # Acme Avionics already exists from the fixture — but the
        # orchestrator should match it by name.
        baseline_suppliers = db_session.query(Supplier).count()
        baseline_parts = db_session.query(CatalogPart).count()

        resp = client.post(
            f"/api/v1/catalog/pending-imports/{pending_import.id}/approve",
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["part_number"] == "RSP-100"
        assert body["supplier_name"] == "Acme Avionics"
        assert len(body["connectors"]) == 1
        assert len(body["connectors"][0]["pins"]) == 2

        # Supplier was matched, not duplicated.
        assert db_session.query(Supplier).count() == baseline_suppliers
        assert db_session.query(CatalogPart).count() == baseline_parts + 1
        assert db_session.query(CatalogConnector).count() == 1
        assert db_session.query(CatalogPin).count() == 2

        # Pending row marked APPROVED + linked.
        db_session.expire_all()
        pi = db_session.query(PendingCatalogImport).get(pending_import.id)
        assert pi.status == PendingImportStatus.APPROVED
        assert pi.committed_catalog_part_id == body["id"]
        assert pi.reviewed_by_id is not None

    def test_approve_with_brand_new_supplier_creates_supplier(
        self, client, db_session, uploaded_document,
    ):
        """Case 4: AI extraction names a never-seen-before supplier → create one."""
        new_payload = _good_extraction_payload()
        new_payload["supplier"]["name"] = "Brand-New Vendor LLC"
        new_payload["supplier"]["cage_code"] = "ZNEW1"
        # Different part number to avoid the (supplier, pn, rev) duplicate guard.
        new_payload["part_number"] = "BNV-200"
        pending = PendingCatalogImport(
            source_document_id=uploaded_document.id,
            supplier_id=uploaded_document.supplier_id,
            extracted_data=new_payload,
            status=PendingImportStatus.PENDING,
        )
        db_session.add(pending)
        db_session.commit()

        baseline_suppliers = db_session.query(Supplier).count()
        _, headers = make_user(db_session, "admin", "brand_new_supplier_admin")

        resp = client.post(
            f"/api/v1/catalog/pending-imports/{pending.id}/approve",
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        # Brand-new supplier created.
        assert db_session.query(Supplier).count() == baseline_suppliers + 1
        new_supplier = db_session.query(Supplier).filter(
            Supplier.name == "Brand-New Vendor LLC"
        ).first()
        assert new_supplier is not None
        assert new_supplier.cage_code == "ZNEW1"

    def test_approve_status_guard_rejects_already_approved(
        self, client, db_session, pending_import,
    ):
        """Case 9 (part 1): approving an already-APPROVED pending → 409."""
        pending_import.status = PendingImportStatus.APPROVED
        db_session.commit()
        _, headers = make_user(db_session, "admin", "double_approve_admin")
        resp = client.post(
            f"/api/v1/catalog/pending-imports/{pending_import.id}/approve",
            headers=headers,
        )
        assert resp.status_code == 409, resp.text

    def test_approve_status_guard_rejects_already_rejected(
        self, client, db_session, pending_import,
    ):
        """Case 9 (part 2): approving an already-REJECTED pending → 409."""
        pending_import.status = PendingImportStatus.REJECTED
        db_session.commit()
        _, headers = make_user(db_session, "admin", "approve_rejected_admin")
        resp = client.post(
            f"/api/v1/catalog/pending-imports/{pending_import.id}/approve",
            headers=headers,
        )
        assert resp.status_code == 409, resp.text

    def test_approve_marks_source_document_approved(
        self, client, db_session, pending_import, uploaded_document,
    ):
        """Case 10: source SupplierDocument transitions to APPROVED."""
        _, headers = make_user(db_session, "admin", "doc_status_admin")
        resp = client.post(
            f"/api/v1/catalog/pending-imports/{pending_import.id}/approve",
            headers=headers,
        )
        assert resp.status_code == 201, resp.text
        db_session.expire_all()
        doc = db_session.query(SupplierDocument).get(uploaded_document.id)
        assert doc.extraction_status == ExtractionStatus.APPROVED

    def test_approve_atomicity_rolls_back_on_pin_failure(
        self, client, db_session, pending_import,
    ):
        """Case 8: pin creation fails mid-way → no Supplier/Part/Connector survives."""
        baseline_suppliers = db_session.query(Supplier).count()
        baseline_parts = db_session.query(CatalogPart).count()
        baseline_connectors = db_session.query(CatalogConnector).count()
        baseline_pins = db_session.query(CatalogPin).count()

        # Patch CatalogPin.__init__ on the class to raise the second time it's called.
        call_count = {"n": 0}
        original_init = CatalogPin.__init__

        def boom(self, *args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 2:
                raise RuntimeError("simulated pin failure")
            return original_init(self, *args, **kwargs)

        _, headers = make_user(db_session, "admin", "rollback_admin")
        with patch.object(CatalogPin, "__init__", boom):
            resp = client.post(
                f"/api/v1/catalog/pending-imports/{pending_import.id}/approve",
                headers=headers,
            )
        # The endpoint catches the unexpected exception, rolls back, and returns 500.
        assert resp.status_code == 500, resp.text

        db_session.expire_all()
        # Counts unchanged — full rollback.
        assert db_session.query(Supplier).count() == baseline_suppliers
        assert db_session.query(CatalogPart).count() == baseline_parts
        assert db_session.query(CatalogConnector).count() == baseline_connectors
        assert db_session.query(CatalogPin).count() == baseline_pins
        # Pending row remains PENDING (NOT marked APPROVED).
        pi = db_session.query(PendingCatalogImport).get(pending_import.id)
        assert pi.status == PendingImportStatus.PENDING


class TestRejectEndpoint:

    def test_reject_marks_rejected_no_catalog_data(
        self, client, db_session, pending_import, uploaded_document,
    ):
        """Case 5: reject creates no Supplier/CatalogPart and links source doc."""
        baseline_parts = db_session.query(CatalogPart).count()
        _, headers = make_user(db_session, "admin", "rejecter_admin")
        resp = client.post(
            f"/api/v1/catalog/pending-imports/{pending_import.id}/reject",
            json={"reason": "Datasheet was for the wrong revision"},
            headers=headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == PendingImportStatus.REJECTED.value
        assert body["rejection_reason"] == "Datasheet was for the wrong revision"

        db_session.expire_all()
        doc = db_session.query(SupplierDocument).get(uploaded_document.id)
        assert doc.extraction_status == ExtractionStatus.REJECTED
        # No catalog rows created.
        assert db_session.query(CatalogPart).count() == baseline_parts

    def test_reject_status_guard_rejects_already_approved(
        self, client, db_session, pending_import,
    ):
        """Rejecting an already-APPROVED pending → 409."""
        pending_import.status = PendingImportStatus.APPROVED
        db_session.commit()
        _, headers = make_user(db_session, "admin", "reject_approved_admin")
        resp = client.post(
            f"/api/v1/catalog/pending-imports/{pending_import.id}/reject",
            json={"reason": "ignored"},
            headers=headers,
        )
        assert resp.status_code == 409, resp.text


# ──────────────────────────────────────────────────────────────
#  Group C — RBAC + regression
# ──────────────────────────────────────────────────────────────

class TestRBAC:

    def test_stakeholder_cannot_approve(self, client, db_session, pending_import):
        """Case 7: stakeholder gets 403 on approve."""
        _, headers = make_user(db_session, "stakeholder", "stake_approve")
        resp = client.post(
            f"/api/v1/catalog/pending-imports/{pending_import.id}/approve",
            headers=headers,
        )
        assert resp.status_code == 403, resp.text

    def test_req_eng_can_approve(self, client, db_session, pending_import):
        _, headers = make_user(db_session, "requirements_engineer", "re_approver")
        resp = client.post(
            f"/api/v1/catalog/pending-imports/{pending_import.id}/approve",
            headers=headers,
        )
        assert resp.status_code == 201, resp.text

    def test_stakeholder_cannot_reject(self, client, db_session, pending_import):
        _, headers = make_user(db_session, "stakeholder", "stake_reject")
        resp = client.post(
            f"/api/v1/catalog/pending-imports/{pending_import.id}/reject",
            json={"reason": "no"},
            headers=headers,
        )
        assert resp.status_code == 403, resp.text

    def test_stakeholder_cannot_trigger_extraction(self, client, db_session, uploaded_document):
        _, headers = make_user(db_session, "stakeholder", "stake_extract")
        resp = client.post(
            f"/api/v1/catalog/documents/{uploaded_document.id}/extract",
            headers=headers,
        )
        assert resp.status_code == 403, resp.text


class TestRegression:

    def test_resha_dedup_per_supplier(self, client, db_session, supplier, synthetic_pdf_bytes):
        """Case 6: re-uploading same SHA-256 to same supplier → 409 (Phase 2 behaviour)."""
        _, headers = make_user(db_session, "admin", "resha_admin")
        # First upload — should succeed.
        resp1 = client.post(
            f"/api/v1/catalog/suppliers/{supplier.id}/documents/upload",
            files={"file": ("synth.pdf", synthetic_pdf_bytes, "application/pdf")},
            data={"title": "RSP-100 Datasheet", "document_type": "datasheet"},
            headers=headers,
        )
        assert resp1.status_code == 201, resp1.text

        # Second upload of identical bytes — same SHA → 409.
        resp2 = client.post(
            f"/api/v1/catalog/suppliers/{supplier.id}/documents/upload",
            files={"file": ("synth.pdf", synthetic_pdf_bytes, "application/pdf")},
            data={"title": "RSP-100 Datasheet (re-uploaded)", "document_type": "datasheet"},
            headers=headers,
        )
        assert resp2.status_code == 409, resp2.text


# ──────────────────────────────────────────────────────────────
#  Group D — Trigger endpoint state-machine
# ──────────────────────────────────────────────────────────────

class TestTriggerEndpoint:

    def test_extract_endpoint_returns_202_and_flips_status(
        self, client, db_session, uploaded_document,
    ):
        """Endpoint returns 202 + flips doc to EXTRACTING immediately.
        We mock the BackgroundTask so we can inspect mid-flight state."""
        _, headers = make_user(db_session, "admin", "trigger_admin")
        with patch("app.routers.catalog._run_extraction_in_background") as bg_mock:
            resp = client.post(
                f"/api/v1/catalog/documents/{uploaded_document.id}/extract",
                headers=headers,
            )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["job_id"] == uploaded_document.id
        assert body["status"] == ExtractionStatus.EXTRACTING.value
        bg_mock.assert_called_once_with(uploaded_document.id)

        db_session.expire_all()
        doc = db_session.query(SupplierDocument).get(uploaded_document.id)
        assert doc.extraction_status == ExtractionStatus.EXTRACTING

    def test_extract_endpoint_409s_on_in_flight(
        self, client, db_session, uploaded_document,
    ):
        uploaded_document.extraction_status = ExtractionStatus.EXTRACTING
        db_session.commit()
        _, headers = make_user(db_session, "admin", "in_flight_admin")
        resp = client.post(
            f"/api/v1/catalog/documents/{uploaded_document.id}/extract",
            headers=headers,
        )
        assert resp.status_code == 409, resp.text

    def test_extract_endpoint_404_on_missing_doc(self, client, db_session):
        _, headers = make_user(db_session, "admin", "missing_doc_admin")
        resp = client.post(
            "/api/v1/catalog/documents/99999/extract",
            headers=headers,
        )
        assert resp.status_code == 404, resp.text
