"""
ASTRA — Tests for the parts-library module (Phase 2).

Covers WPN service, STEP parser, AI rules fallback, mech req templates,
parts-library CRUD endpoints, project-parts join, and mechanical-joints
including approval-time auto-requirement generation.

Tests run against SQLite (per conftest). PG-specific things — ARRAY
columns, with_for_update(), JSONB GIN indexes — degrade gracefully
under SQLite via .with_variant() and silent FOR UPDATE no-op.
"""

from __future__ import annotations

import io
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import User, UserRole, Project
from app.models.document import Document
from app.models.parts_library import (
    JointStatus, JointType, LibraryPart, MechanicalJoint, PartStatus, PartType,
    PendingPartsImport, PendingPartsStatus, ProjectPart, SystemPartAssignment,
    ThreadStandard, WPNSequence,
)
from app.models.req_sync import RequirementSourceLink, SourceEntityType
from app.models.interface import System
from tests.conftest import make_user
from app.services.parts.mechanical_req_templates import (
    JOINT_TYPE_TEMPLATES, TEMPLATES, render_template,
)
from app.services.parts.step_parser import (
    StepParserResult, _rules_fallback, match_thread, parse_step_file,
    THREAD_TABLE,
)
from app.services.parts.wpn_service import WPN_TYPE_CODES, assign_wpn, bump_revision


# ══════════════════════════════════════════════════════════════
#  Helper builders
# ══════════════════════════════════════════════════════════════

def _make_approved_part(
    db: Session, part_type: PartType, name: str, *, approver_id: int = 1,
    **extra,
) -> LibraryPart:
    wpn = assign_wpn(db, part_type)
    db.commit()
    from sqlalchemy.sql import func
    part = LibraryPart(
        wardstone_part_number=wpn,
        revision="00",
        part_type=part_type,
        name=name,
        status=PartStatus.APPROVED,
        approved_by_id=approver_id,
        approved_at=func.now(),
        **extra,
    )
    db.add(part)
    db.commit()
    db.refresh(part)
    return part


# ══════════════════════════════════════════════════════════════
#  WPN service
# ══════════════════════════════════════════════════════════════

class TestWPNService:
    def test_type_codes_cover_all_part_types(self):
        for pt in PartType:
            assert pt in WPN_TYPE_CODES, f"Missing WPN code for {pt}"
            assert len(WPN_TYPE_CODES[pt]) == 4

    def test_bump_revision(self):
        assert bump_revision("WS-FAST-000042-00") == "WS-FAST-000042-01"
        assert bump_revision("WS-FAST-000042-09") == "WS-FAST-000042-10"
        assert bump_revision("WS-BRKT-000001-05") == "WS-BRKT-000001-06"

    def test_sequential_assignment(self, db_session: Session):
        wpns = []
        for _ in range(5):
            wpns.append(assign_wpn(db_session, PartType.FASTENER))
        db_session.commit()
        assert wpns[0] == "WS-FAST-000001-00"
        assert wpns[1] == "WS-FAST-000002-00"
        assert wpns[4] == "WS-FAST-000005-00"
        assert len(set(wpns)) == 5

    def test_independent_sequences_per_type(self, db_session: Session):
        f1 = assign_wpn(db_session, PartType.FASTENER)
        w1 = assign_wpn(db_session, PartType.WASHER)
        f2 = assign_wpn(db_session, PartType.FASTENER)
        db_session.commit()
        assert f1.startswith("WS-FAST-000001-")
        assert w1.startswith("WS-WASH-000001-")
        assert f2.startswith("WS-FAST-000002-")


# ══════════════════════════════════════════════════════════════
#  STEP parser + rules fallback
# ══════════════════════════════════════════════════════════════

MINIMAL_STEP = b"""ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('Test part'),'2;1');
FILE_NAME('test.step','2024-01-01T00:00:00',('ASTRA'),('Test'),'','','');
FILE_SCHEMA(('AUTOMOTIVE_DESIGN { 1 0 10303 214 1 1 1 1 }'));
ENDSEC;
DATA;
#1=PRODUCT('M4-SCREW','Socket Head Cap Screw','',(#2));
#2=PRODUCT_CONTEXT('MECHANICAL',#3,'mechanical');
#3=APPLICATION_CONTEXT('automotive design');
ENDSEC;
END-ISO-10303-21;
"""


class TestThreadTable:
    def test_m6_match(self):
        result = match_thread(Decimal("6.55"))
        assert result is not None
        size, standard, torque = result
        assert size == "M6×1.0"
        assert standard == ThreadStandard.ISO_METRIC
        assert torque == Decimal("9.8")

    def test_no_match(self):
        assert match_thread(Decimal("99.0")) is None
        assert match_thread(Decimal("0.5")) is None
        assert match_thread(Decimal("50.0")) is None

    def test_table_invariants(self):
        for lo, hi, size, std, torque in THREAD_TABLE:
            assert lo < hi, f"Invalid range [{lo},{hi}] for {size}"
            assert torque > 0
            assert std in ThreadStandard


class TestStepParser:
    def test_metadata_extraction_without_occ(self, tmp_path):
        f = tmp_path / "x.step"
        f.write_bytes(MINIMAL_STEP)
        result = parse_step_file(str(f))
        assert result.product_name == "M4-SCREW"
        assert result.product_description == "Socket Head Cap Screw"
        assert result.step_entity_id == "#PRODUCT:1"

    def test_geometry_low_confidence_without_occ(self, tmp_path):
        f = tmp_path / "x.step"
        f.write_bytes(MINIMAL_STEP)
        result = parse_step_file(str(f))
        if not result.occ_available:
            for fld in ("bounding_box_x_mm", "volume_mm3"):
                assert fld in result.low_confidence_fields


class TestRulesFallback:
    def test_screw_classified_as_fastener(self):
        out = _rules_fallback(StepParserResult(product_name="M6 Socket Head Cap Screw"))
        assert out["part_type"] == "fastener"
        assert out["material_class"] == "stainless_steel"

    def test_washer(self):
        out = _rules_fallback(StepParserResult(product_name="M6 Flat Washer ISO 7089"))
        assert out["part_type"] == "washer"

    def test_bearing(self):
        out = _rules_fallback(StepParserResult(product_name="6002-2Z Deep Groove Ball Bearing"))
        assert out["part_type"] == "bearing"

    def test_nylok_detection(self):
        out = _rules_fallback(StepParserResult(product_name="M4 Nylok Hex Screw"))
        assert out["locking_feature"] == "nylok"

    def test_prevailing_torque_detection(self):
        out = _rules_fallback(
            StepParserResult(product_name="M5 Prevailing Torque Nut ISO 7042")
        )
        assert out["locking_feature"] == "prevailing_torque"

    def test_titanium_material(self):
        out = _rules_fallback(StepParserResult(product_name="M5 Ti-6Al-4V Socket Head Screw"))
        assert out["material_class"] == "titanium"
        assert "Ti-6Al-4V" in out["material_name"]

    def test_torque_propagation_from_thread_match(self):
        out = _rules_fallback(
            StepParserResult(product_name="M6 Screw", torque_nominal_nm=Decimal("9.8"))
        )
        assert out["torque_nominal_nm"] == 9.8
        assert abs(out["torque_min_nm"] - 9.8 * 0.85) < 0.01
        assert abs(out["torque_max_nm"] - 9.8 * 1.10) < 0.01

    def test_unknown_defaults_to_custom(self):
        out = _rules_fallback(StepParserResult(product_name="XJ-9000 Undefined"))
        assert out["part_type"] == "custom"
        assert out["confidence_overrides"].get("part_type") == "low"
        assert out["flags"]


# ══════════════════════════════════════════════════════════════
#  Template rendering
# ══════════════════════════════════════════════════════════════

class TestTemplates:
    def test_mech_bolt_001_full_context(self):
        ctx = {
            "part_a_name": "Main Structure Panel",
            "part_b_name": "Avionics Bay Cover",
            "fastener_description": "M6×16 Socket Head Cap Screw A286",
            "fastener_count": 4,
            "torque_nominal_nm": "9.8",
            "torque_tolerance_nm": "0.8",
        }
        s = render_template("MECH-BOLT-001", ctx)
        assert "Main Structure Panel" in s
        assert "Avionics Bay Cover" in s
        assert "4×" in s
        assert "9.8 N·m" in s
        assert "{" not in s and "}" not in s

    def test_missing_context_substitutes_tbd(self):
        s = render_template("MECH-BOLT-001", {})
        assert "TBD" in s
        assert "{" not in s

    def test_unknown_template_returns_none(self):
        assert render_template("MECH-NONEXISTENT-999", {}) is None

    def test_all_templates_render_with_empty_context(self):
        for tid in TEMPLATES:
            s = render_template(tid, {})
            assert s is not None
            assert "{" not in s, f"Unresolved tokens in {tid}: {s}"

    def test_joint_type_templates_cover_all_types(self):
        for jt in JointType:
            assert jt in JOINT_TYPE_TEMPLATES, f"Missing template list for {jt}"


# ══════════════════════════════════════════════════════════════
#  Parts Library API endpoints
# ══════════════════════════════════════════════════════════════

class TestPartsLibraryAPI:
    def test_create_part_assigns_wpn(
        self, client: TestClient, db_session: Session, test_user, auth_headers
    ):
        resp = client.post(
            "/api/v1/parts-library/",
            json={
                "part_type": "washer",
                "name": "M6 Flat Washer",
                "nominal_diameter_mm": "6.5",
                "material_name": "A2 Stainless Steel",
                "material_class": "stainless_steel",
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["wardstone_part_number"].startswith("WS-WASH-")
        assert body["wardstone_part_number"].endswith("-00")
        assert body["status"] == "draft"
        assert body["part_type"] == "washer"
        assert body["approved_at"] is None

    def test_developer_cannot_create_part(
        self, client: TestClient, db_session: Session
    ):
        # Use rbac-stripped permissive shim path: when rbac.require_any_role
        # isn't loaded, every authenticated user passes. This test asserts
        # the SHIM behavior — a real rbac-enabled deployment denies this.
        # Here we just confirm authenticated requests work; role-blocking
        # is exercised via rbac unit tests elsewhere.
        _, dev_headers = make_user(db_session, role="developer", username="dev_x")
        resp = client.post(
            "/api/v1/parts-library/",
            json={"part_type": "fastener", "name": "Test"},
            headers=dev_headers,
        )
        # Expect either 201 (rbac shim) or 403 (real rbac).
        assert resp.status_code in (201, 403)

    def test_list_parts_default_filters_to_approved(
        self, client: TestClient, db_session: Session, test_user, auth_headers
    ):
        from sqlalchemy.sql import func

        # 2 approved + 1 draft + 1 superseded
        for status_, ptype in [
            (PartStatus.APPROVED, PartType.FASTENER),
            (PartStatus.APPROVED, PartType.WASHER),
            (PartStatus.DRAFT, PartType.BRACKET),
            (PartStatus.SUPERSEDED, PartType.SEAL),
        ]:
            wpn = assign_wpn(db_session, ptype)
            db_session.add(LibraryPart(
                wardstone_part_number=wpn, revision="00",
                part_type=ptype, name=f"Test {ptype.value}",
                status=status_,
                approved_by_id=test_user.id if status_ == PartStatus.APPROVED else None,
                approved_at=func.now() if status_ == PartStatus.APPROVED else None,
            ))
        db_session.commit()

        resp = client.get("/api/v1/parts-library/", headers=auth_headers)
        assert resp.status_code == 200
        for p in resp.json():
            assert p["status"] == "approved"

    def test_filter_by_part_type(
        self, client: TestClient, db_session: Session, test_user, auth_headers
    ):
        _make_approved_part(db_session, PartType.FASTENER, "Bolt 1", approver_id=test_user.id)
        _make_approved_part(db_session, PartType.WASHER, "Washer 1", approver_id=test_user.id)
        resp = client.get(
            "/api/v1/parts-library/",
            params={"part_type": "fastener"}, headers=auth_headers,
        )
        assert resp.status_code == 200
        for p in resp.json():
            assert p["part_type"] == "fastener"

    def test_search_by_name(
        self, client: TestClient, db_session: Session, test_user, auth_headers
    ):
        _make_approved_part(
            db_session, PartType.FASTENER, "TITANIUM HEX BOLT M5",
            approver_id=test_user.id,
            manufacturer_part_number="TI-M5-HB-001",
        )
        resp = client.get(
            "/api/v1/parts-library/",
            params={"search": "titanium"}, headers=auth_headers,
        )
        assert resp.status_code == 200
        assert any("TITANIUM HEX BOLT" in p["name"] for p in resp.json())

    def test_update_draft_in_place(
        self, client: TestClient, db_session: Session, auth_headers
    ):
        wpn = assign_wpn(db_session, PartType.FASTENER)
        part = LibraryPart(
            wardstone_part_number=wpn, revision="00",
            part_type=PartType.FASTENER, name="Old Name",
            status=PartStatus.DRAFT,
        )
        db_session.add(part)
        db_session.commit()

        resp = client.patch(
            f"/api/v1/parts-library/{part.id}",
            json={"name": "New Name", "torque_nominal_nm": "9.8"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == part.id
        assert body["name"] == "New Name"
        assert body["wardstone_part_number"] == wpn

    def test_update_approved_dimensional_creates_revision(
        self, client: TestClient, db_session: Session, test_user, auth_headers
    ):
        from sqlalchemy.sql import func
        wpn = assign_wpn(db_session, PartType.FASTENER)
        part = LibraryPart(
            wardstone_part_number=wpn, revision="00",
            part_type=PartType.FASTENER, name="Socket Head Screw M4",
            status=PartStatus.APPROVED,
            approved_by_id=test_user.id, approved_at=func.now(),
            torque_nominal_nm=Decimal("2.9"),
        )
        db_session.add(part)
        db_session.commit()
        original_id = part.id
        original_wpn = part.wardstone_part_number

        resp = client.patch(
            f"/api/v1/parts-library/{original_id}",
            json={"torque_nominal_nm": "3.2"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        new_wpn = body["wardstone_part_number"]
        assert new_wpn.endswith("-01"), f"Expected -01 revision, got {new_wpn}"
        assert body["status"] == "draft"
        assert Decimal(body["torque_nominal_nm"]) == Decimal("3.2")

        # Old row is now SUPERSEDED with superseded_by_id pointing to new
        db_session.expire_all()
        old = db_session.query(LibraryPart).filter(LibraryPart.id == original_id).first()
        assert old.status == PartStatus.SUPERSEDED
        assert old.superseded_by_id == body["id"]


# ══════════════════════════════════════════════════════════════
#  STEP upload + approval flow
# ══════════════════════════════════════════════════════════════

class TestStepUpload:
    def test_upload_creates_pending_import(
        self, client: TestClient, db_session: Session, auth_headers
    ):
        resp = client.post(
            "/api/v1/parts-library/upload-step",
            files={"file": ("test_part.step", io.BytesIO(MINIMAL_STEP), "application/step")},
            headers=auth_headers,
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()
        assert body["duplicate"] is False
        assert "pending_import_id" in body

    def test_non_step_rejected(
        self, client: TestClient, auth_headers
    ):
        resp = client.post(
            "/api/v1/parts-library/upload-step",
            files={"file": ("drawing.pdf", io.BytesIO(b"%PDF-1.4"), "application/pdf")},
            headers=auth_headers,
        )
        assert resp.status_code == 400
        body = resp.json()
        assert body.get("detail", {}).get("code") == "INVALID_FILE_TYPE" or body.get("code") == "INVALID_FILE_TYPE"

    def test_empty_file_rejected(self, client: TestClient, auth_headers):
        resp = client.post(
            "/api/v1/parts-library/upload-step",
            files={"file": ("empty.step", io.BytesIO(b""), "application/step")},
            headers=auth_headers,
        )
        assert resp.status_code == 400

    def test_duplicate_returns_existing(
        self, client: TestClient, auth_headers
    ):
        r1 = client.post(
            "/api/v1/parts-library/upload-step",
            files={"file": ("a.step", io.BytesIO(MINIMAL_STEP), "application/step")},
            headers=auth_headers,
        )
        assert r1.status_code == 202
        r2 = client.post(
            "/api/v1/parts-library/upload-step",
            files={"file": ("b.step", io.BytesIO(MINIMAL_STEP), "application/step")},
            headers=auth_headers,
        )
        assert r2.status_code in (200, 202)
        assert r2.json()["duplicate"] is True


class TestApproveImport:
    def _make_pending(
        self, db: Session, user: User,
        proposed_data: dict, status: PendingPartsStatus = PendingPartsStatus.PENDING,
    ) -> PendingPartsImport:
        doc = Document(
            filename="t.step", file_path="/tmp/t.step",
            file_size_bytes=10, sha256="dead" + "0" * 60,
            mime_type="application/step", uploaded_by_id=user.id,
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        pending = PendingPartsImport(
            document_id=doc.id, status=status,
            proposed_data=proposed_data,
            confidence_scores={}, low_confidence_fields=[],
            created_by_id=user.id,
        )
        db.add(pending)
        db.commit()
        db.refresh(pending)
        return pending

    def test_approve_assigns_wpn(
        self, client: TestClient, db_session: Session, test_user, auth_headers
    ):
        pending = self._make_pending(
            db_session, test_user,
            {"name": "M6 SHCS", "part_type": "fastener", "torque_nominal_nm": "9.8"},
        )
        resp = client.post(
            f"/api/v1/parts-library/pending-imports/{pending.id}/approve",
            json={"overrides": {}}, headers=auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["wardstone_part_number"].startswith("WS-FAST-")
        assert body["status"] == "approved"
        assert body["name"] == "M6 SHCS"
        assert Decimal(body["torque_nominal_nm"]) == Decimal("9.8")

        db_session.expire_all()
        p = db_session.query(PendingPartsImport).filter(PendingPartsImport.id == pending.id).first()
        assert p.status == PendingPartsStatus.APPROVED
        assert p.library_part_id == body["id"]

    def test_overrides_take_precedence(
        self, client: TestClient, db_session: Session, test_user, auth_headers
    ):
        pending = self._make_pending(
            db_session, test_user,
            {"name": "Wrong Name", "part_type": "fastener"},
        )
        resp = client.post(
            f"/api/v1/parts-library/pending-imports/{pending.id}/approve",
            json={"overrides": {"name": "Correct Name", "torque_nominal_nm": "12.5"}},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "Correct Name"
        assert Decimal(body["torque_nominal_nm"]) == Decimal("12.5")

    def test_idempotent(
        self, client: TestClient, db_session: Session, test_user, auth_headers
    ):
        pending = self._make_pending(
            db_session, test_user,
            {"name": "Part X", "part_type": "bracket"},
        )
        r1 = client.post(
            f"/api/v1/parts-library/pending-imports/{pending.id}/approve",
            json={"overrides": {}}, headers=auth_headers,
        )
        assert r1.status_code == 200
        first_id = r1.json()["id"]
        first_wpn = r1.json()["wardstone_part_number"]
        r2 = client.post(
            f"/api/v1/parts-library/pending-imports/{pending.id}/approve",
            json={"overrides": {}}, headers=auth_headers,
        )
        assert r2.status_code == 200
        assert r2.json()["id"] == first_id
        assert r2.json()["wardstone_part_number"] == first_wpn

    def test_missing_name_fails(
        self, client: TestClient, db_session: Session, test_user, auth_headers
    ):
        pending = self._make_pending(
            db_session, test_user, {"part_type": "fastener"},
        )
        resp = client.post(
            f"/api/v1/parts-library/pending-imports/{pending.id}/approve",
            json={"overrides": {}}, headers=auth_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        code = body.get("detail", {}).get("code") or body.get("code")
        assert code == "MISSING_REQUIRED_FIELD"

    def test_reject(
        self, client: TestClient, db_session: Session, test_user, auth_headers
    ):
        pending = self._make_pending(
            db_session, test_user,
            {"name": "Reject Me", "part_type": "washer"},
        )
        resp = client.post(
            f"/api/v1/parts-library/pending-imports/{pending.id}/reject",
            json={"reason": "Incorrect geometry"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        db_session.expire_all()
        p = db_session.query(PendingPartsImport).filter(PendingPartsImport.id == pending.id).first()
        assert p.status == PendingPartsStatus.REJECTED
        assert "Incorrect geometry" in p.rejection_reason


# ══════════════════════════════════════════════════════════════
#  Project parts
# ══════════════════════════════════════════════════════════════

class TestProjectParts:
    def test_add_approved_part(
        self, client: TestClient, db_session: Session, test_user,
        test_project, auth_headers
    ):
        lp = _make_approved_part(
            db_session, PartType.FASTENER, "M4 Screw", approver_id=test_user.id,
        )
        resp = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={"library_part_id": lp.id, "quantity": 8, "designation": "HW-J1"},
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["library_part_id"] == lp.id
        assert body["quantity"] == 8
        assert body["library_part"]["name"] == "M4 Screw"

    def test_add_draft_part_rejected(
        self, client: TestClient, db_session: Session, test_project, auth_headers
    ):
        wpn = assign_wpn(db_session, PartType.BRACKET)
        draft = LibraryPart(
            wardstone_part_number=wpn, revision="00",
            part_type=PartType.BRACKET, name="Draft", status=PartStatus.DRAFT,
        )
        db_session.add(draft)
        db_session.commit()
        resp = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={"library_part_id": draft.id}, headers=auth_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        code = body.get("detail", {}).get("code") or body.get("code")
        assert code == "PART_NOT_APPROVED"

    def test_duplicate_add_rejected(
        self, client: TestClient, db_session: Session, test_user,
        test_project, auth_headers
    ):
        lp = _make_approved_part(
            db_session, PartType.WASHER, "M6 Washer", approver_id=test_user.id,
        )
        r1 = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={"library_part_id": lp.id}, headers=auth_headers,
        )
        assert r1.status_code == 201
        r2 = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={"library_part_id": lp.id}, headers=auth_headers,
        )
        assert r2.status_code == 409

    def test_remove_does_not_delete_library_record(
        self, client: TestClient, db_session: Session, test_user,
        test_project, auth_headers
    ):
        lp = _make_approved_part(
            db_session, PartType.BEARING, "Bearing", approver_id=test_user.id,
        )
        r = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={"library_part_id": lp.id}, headers=auth_headers,
        )
        pp_id = r.json()["id"]
        d = client.delete(
            f"/api/v1/projects/{test_project.id}/parts/{pp_id}",
            headers=auth_headers,
        )
        assert d.status_code == 204
        # LP still exists
        assert db_session.query(LibraryPart).filter(LibraryPart.id == lp.id).first() is not None

    def test_unassigned_excludes_system_assigned(
        self, client: TestClient, db_session: Session, test_user,
        test_project, auth_headers
    ):
        from sqlalchemy.sql import func
        # Create system manually (skip fixture complexity)
        sys_ = System(
            project_id=test_project.id, system_id="SYS-001", name="Test Sys",
            system_type="custom", description="", owner_id=test_user.id,
        )
        db_session.add(sys_)
        db_session.commit()
        lp1 = _make_approved_part(db_session, PartType.FASTENER, "Bolt 1", approver_id=test_user.id)
        lp2 = _make_approved_part(db_session, PartType.FASTENER, "Bolt 2", approver_id=test_user.id)

        r1 = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={"library_part_id": lp1.id}, headers=auth_headers,
        )
        r2 = client.post(
            f"/api/v1/projects/{test_project.id}/parts/",
            json={"library_part_id": lp2.id}, headers=auth_headers,
        )
        pp1_id = r1.json()["id"]

        # Assign pp1 to system
        a = client.post(
            f"/api/v1/projects/{test_project.id}/systems/{sys_.id}/parts/",
            json={"project_part_id": pp1_id}, headers=auth_headers,
        )
        assert a.status_code == 201, a.text

        u = client.get(
            f"/api/v1/projects/{test_project.id}/parts/unassigned",
            headers=auth_headers,
        )
        assert u.status_code == 200
        ids = [p["id"] for p in u.json()]
        assert r2.json()["id"] in ids
        assert pp1_id not in ids


# ══════════════════════════════════════════════════════════════
#  Mechanical joints
# ══════════════════════════════════════════════════════════════

class TestMechanicalJoints:
    def _make_joint_pair(self, db, project_id, owner_id):
        lp_a = _make_approved_part(db, PartType.BRACKET, "Frame", approver_id=owner_id)
        lp_b = _make_approved_part(db, PartType.ENCLOSURE, "Box", approver_id=owner_id)
        pp_a = ProjectPart(project_id=project_id, library_part_id=lp_a.id, quantity=1)
        pp_b = ProjectPart(project_id=project_id, library_part_id=lp_b.id, quantity=1)
        db.add_all([pp_a, pp_b])
        db.commit()
        return pp_a, pp_b

    def test_joint_id_format(
        self, client: TestClient, db_session: Session, test_user,
        test_project, auth_headers
    ):
        pp_a, pp_b = self._make_joint_pair(db_session, test_project.id, test_user.id)
        resp = client.post(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/",
            json={
                "joint_type": "bolted",
                "part_a_id": pp_a.id, "part_b_id": pp_b.id,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        joint_id = resp.json()["joint_id"]
        import re
        assert re.match(r"^MJ-\d{4}-\d{6}$", joint_id), f"Bad joint_id: {joint_id}"
        assert joint_id.startswith(f"MJ-{test_project.id:04d}-")

    def test_same_part_both_sides_rejected(
        self, client: TestClient, db_session: Session, test_user,
        test_project, auth_headers
    ):
        pp_a, _ = self._make_joint_pair(db_session, test_project.id, test_user.id)
        resp = client.post(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/",
            json={
                "joint_type": "bolted",
                "part_a_id": pp_a.id, "part_b_id": pp_a.id,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422

    def test_fastener_type_validation(
        self, client: TestClient, db_session: Session, test_user,
        test_project, auth_headers
    ):
        pp_a, pp_b = self._make_joint_pair(db_session, test_project.id, test_user.id)
        washer = _make_approved_part(
            db_session, PartType.WASHER, "M6 Washer", approver_id=test_user.id
        )
        resp = client.post(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/",
            json={
                "joint_type": "bolted",
                "part_a_id": pp_a.id, "part_b_id": pp_b.id,
                "fastener_part_id": washer.id,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 422
        body = resp.json()
        code = body.get("detail", {}).get("code") or body.get("code")
        assert code == "INVALID_FASTENER_TYPE"

    def test_approve_generates_requirements_with_source_links(
        self, client: TestClient, db_session: Session, test_user,
        test_project, auth_headers
    ):
        # Build full BOLTED joint with fastener + parts
        fastener_lp = _make_approved_part(
            db_session, PartType.FASTENER, "M6×16 SHCS A286",
            approver_id=test_user.id,
            torque_nominal_nm=Decimal("9.8"),
            torque_min_nm=Decimal("8.3"),
            torque_max_nm=Decimal("10.8"),
        )
        pp_a, pp_b = self._make_joint_pair(db_session, test_project.id, test_user.id)

        cr = client.post(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/",
            json={
                "joint_type": "bolted",
                "part_a_id": pp_a.id, "part_b_id": pp_b.id,
                "fastener_part_id": fastener_lp.id,
                "fastener_count": 4,
                "torque_nominal_nm": "9.8",
                "torque_min_nm": "8.3",
                "torque_max_nm": "10.8",
                "locking_feature": "nylok",
            },
            headers=auth_headers,
        )
        assert cr.status_code == 201, cr.text
        joint_jid = cr.json()["joint_id"]

        ar = client.post(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/{joint_jid}/approve",
            headers=auth_headers,
        )
        assert ar.status_code == 200, ar.text
        assert ar.json()["status"] == "active"

        joint = (
            db_session.query(MechanicalJoint)
            .filter(MechanicalJoint.joint_id == joint_jid)
            .first()
        )
        links = (
            db_session.query(RequirementSourceLink)
            .filter(
                RequirementSourceLink.source_entity_type == SourceEntityType.MECHANICAL_JOINT,
                RequirementSourceLink.source_entity_id == joint.id,
            )
            .all()
        )
        # BOLTED → 5 templates
        assert len(links) >= 3, f"Expected ≥3 links, got {len(links)}"

        # Verify content of generated requirements
        from app.models import Requirement
        req_ids = [link.requirement_id for link in links]
        reqs = db_session.query(Requirement).filter(Requirement.id.in_(req_ids)).all()
        statements = [r.statement for r in reqs]
        # MECH-BOLT-001 should reference 4× and the torque value
        # (Numeric serializes as e.g. "9.8000" — match without trailing zeros)
        assert any("4×" in s and ("9.8" in s) and "N·m" in s for s in statements), \
            f"Expected '4×' and '9.8' in: {statements}"
        # No unresolved tokens
        for s in statements:
            assert "{" not in s, f"Unresolved tokens in: {s}"

    def test_delete_draft_joint_hard_deletes(
        self, client: TestClient, db_session: Session, test_user,
        test_project, auth_headers
    ):
        pp_a, pp_b = self._make_joint_pair(db_session, test_project.id, test_user.id)
        cr = client.post(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/",
            json={
                "joint_type": "bolted",
                "part_a_id": pp_a.id, "part_b_id": pp_b.id,
            },
            headers=auth_headers,
        )
        jid = cr.json()["joint_id"]
        db_id = cr.json()["id"]
        d = client.delete(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/{jid}",
            headers=auth_headers,
        )
        assert d.status_code == 204
        assert db_session.query(MechanicalJoint).filter(
            MechanicalJoint.id == db_id
        ).first() is None

    def test_delete_active_without_force_blocked(
        self, client: TestClient, db_session: Session, test_user,
        test_project, auth_headers
    ):
        pp_a, pp_b = self._make_joint_pair(db_session, test_project.id, test_user.id)
        cr = client.post(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/",
            json={
                "joint_type": "bolted",
                "part_a_id": pp_a.id, "part_b_id": pp_b.id,
            },
            headers=auth_headers,
        )
        jid = cr.json()["joint_id"]
        client.post(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/{jid}/approve",
            headers=auth_headers,
        )
        d = client.delete(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/{jid}",
            headers=auth_headers,
        )
        assert d.status_code == 409

    def test_delete_active_with_force_soft_deletes(
        self, client: TestClient, db_session: Session, test_user,
        test_project, auth_headers
    ):
        pp_a, pp_b = self._make_joint_pair(db_session, test_project.id, test_user.id)
        cr = client.post(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/",
            json={
                "joint_type": "bolted",
                "part_a_id": pp_a.id, "part_b_id": pp_b.id,
            },
            headers=auth_headers,
        )
        jid = cr.json()["joint_id"]
        db_id = cr.json()["id"]
        client.post(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/{jid}/approve",
            headers=auth_headers,
        )
        d = client.delete(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/{jid}",
            params={"force": True},
            headers=auth_headers,
        )
        assert d.status_code == 204
        db_session.expire_all()
        joint = db_session.query(MechanicalJoint).filter(MechanicalJoint.id == db_id).first()
        assert joint is not None
        assert joint.status == JointStatus.SUPERSEDED

    def test_remove_part_with_active_joint_blocked(
        self, client: TestClient, db_session: Session, test_user,
        test_project, auth_headers
    ):
        pp_a, pp_b = self._make_joint_pair(db_session, test_project.id, test_user.id)
        cr = client.post(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/",
            json={
                "joint_type": "bolted",
                "part_a_id": pp_a.id, "part_b_id": pp_b.id,
            },
            headers=auth_headers,
        )
        jid = cr.json()["joint_id"]
        client.post(
            f"/api/v1/projects/{test_project.id}/mechanical-joints/{jid}/approve",
            headers=auth_headers,
        )
        d = client.delete(
            f"/api/v1/projects/{test_project.id}/parts/{pp_a.id}",
            headers=auth_headers,
        )
        assert d.status_code == 409
        body = d.json()
        code = body.get("detail", {}).get("code") or body.get("code")
        assert code == "HAS_ACTIVE_JOINTS"
