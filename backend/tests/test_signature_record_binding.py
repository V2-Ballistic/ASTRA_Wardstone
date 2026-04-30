"""
ASTRA — Signature record-binding tests (F-008) + workflow enum tests (F-007)
============================================================================
File: backend/tests/test_signature_record_binding.py

F-008 (21 CFR Part 11 §11.70): the signature must bind to the signed
record's content at sign time. Mutating the record after signing
invalidates the signature on verify.

F-007: the three workflow SQLEnum columns (WorkflowStatus,
InstanceStatus, SignatureMeaning) must accept lowercase enum-value
inputs without raising InvalidTextRepresentation.
"""

from datetime import datetime

import pytest

from app.models import (
    Project, Requirement, User,
    RequirementType, RequirementPriority, RequirementStatus, RequirementLevel,
    UserRole,
)
from app.models.workflow import (
    ApprovalWorkflow, WorkflowInstance, ElectronicSignature,
    WorkflowStatus, InstanceStatus, SignatureMeaning,
)
from app.services.auth import get_password_hash
from app.services.signature_service import (
    request_signature, verify_signature,
)


# ══════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════


def _make_user(db_session, username="signer"):
    u = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("SignerPass1"),
        full_name=username.title(),
        role=UserRole.PROJECT_MANAGER,
        department="Eng",
        is_active=True,
    )
    db_session.add(u); db_session.commit(); db_session.refresh(u)
    return u


def _make_project(db_session, owner: User, code="SIG"):
    p = Project(code=code, name="Signature project",
                owner_id=owner.id, status="active")
    db_session.add(p); db_session.commit(); db_session.refresh(p)
    return p


def _make_requirement(db_session, project, owner, *, statement, title="Req"):
    r = Requirement(
        req_id="FR-SIG-001", title=title, statement=statement,
        rationale="r", req_type=RequirementType.FUNCTIONAL,
        priority=RequirementPriority.HIGH,
        status=RequirementStatus.DRAFT,
        level=RequirementLevel.L1,
        version=1, quality_score=80.0,
        project_id=project.id, owner_id=owner.id, created_by_id=owner.id,
    )
    db_session.add(r); db_session.commit(); db_session.refresh(r)
    return r


# ══════════════════════════════════════
#  F-008 — record-hash binding
# ══════════════════════════════════════


class TestSignatureRecordBinding:

    def test_sign_then_verify_unmodified_record_passes(self, db_session):
        owner = _make_user(db_session, "signer1")
        project = _make_project(db_session, owner, code="S1")
        req = _make_requirement(
            db_session, project, owner,
            statement="The system shall do X within 5 seconds.",
        )

        sig = request_signature(
            db_session, owner.id, "requirement", req.id,
            SignatureMeaning.APPROVED.value, "SignerPass1",
        )
        assert sig is not None, "Signature must be created on valid password"
        assert sig.record_hash, "F-008: record_hash must be persisted on the row"

        result = verify_signature(db_session, sig.id)
        assert result["valid"] is True, result

    def test_sign_then_mutate_statement_then_verify_fails(self, db_session):
        owner = _make_user(db_session, "signer2")
        project = _make_project(db_session, owner, code="S2")
        req = _make_requirement(
            db_session, project, owner,
            statement="The system shall do X within 5 seconds.",
        )

        sig = request_signature(
            db_session, owner.id, "requirement", req.id,
            SignatureMeaning.APPROVED.value, "SignerPass1",
        )
        assert sig is not None

        # Mutate the signed record AFTER signing.
        req.statement = "The system shall do Y within 999 seconds."
        req.version = (req.version or 1) + 1
        db_session.commit()

        result = verify_signature(db_session, sig.id)
        assert result["valid"] is False, result
        assert result["reason"] == "record_mismatch", (
            f"Expected reason=record_mismatch on post-sign edit, got {result!r}"
        )

    def test_sign_then_mutate_title_also_fails(self, db_session):
        """The hasher includes title — title-only edits also break the seal."""
        owner = _make_user(db_session, "signer3")
        project = _make_project(db_session, owner, code="S3")
        req = _make_requirement(
            db_session, project, owner,
            statement="S", title="Original title",
        )

        sig = request_signature(
            db_session, owner.id, "requirement", req.id,
            SignatureMeaning.APPROVED.value, "SignerPass1",
        )
        assert sig is not None

        req.title = "Quietly renamed"
        db_session.commit()

        result = verify_signature(db_session, sig.id)
        assert result["valid"] is False
        assert result["reason"] == "record_mismatch"

    def test_signature_row_tampering_returns_hash_mismatch(self, db_session):
        """Editing the signature row itself (not the entity) yields hash_mismatch."""
        owner = _make_user(db_session, "signer4")
        project = _make_project(db_session, owner, code="S4")
        req = _make_requirement(
            db_session, project, owner, statement="S",
        )

        sig = request_signature(
            db_session, owner.id, "requirement", req.id,
            SignatureMeaning.APPROVED.value, "SignerPass1",
        )
        assert sig is not None

        # Tamper with the meaning so the recomputed signature_hash differs.
        sig.signature_meaning = SignatureMeaning.REJECTED
        db_session.commit()

        result = verify_signature(db_session, sig.id)
        assert result["valid"] is False
        assert result["reason"] == "hash_mismatch"

    def test_deleted_entity_returns_entity_missing(self, db_session):
        owner = _make_user(db_session, "signer5")
        project = _make_project(db_session, owner, code="S5")
        req = _make_requirement(db_session, project, owner, statement="S")

        sig = request_signature(
            db_session, owner.id, "requirement", req.id,
            SignatureMeaning.APPROVED.value, "SignerPass1",
        )
        assert sig is not None
        sig_id = sig.id

        db_session.delete(req)
        db_session.commit()

        result = verify_signature(db_session, sig_id)
        assert result["valid"] is False
        assert result["reason"] == "entity_missing"

    def test_sign_with_unknown_entity_type_refuses(self, db_session):
        """No record-hasher registered → request_signature returns None."""
        owner = _make_user(db_session, "signer6")
        sig = request_signature(
            db_session, owner.id, "no_such_type", 999,
            SignatureMeaning.APPROVED.value, "SignerPass1",
        )
        assert sig is None, (
            "request_signature must refuse to sign when no record-hasher is "
            "registered for the entity_type — otherwise the signature would "
            "be record-unbound (defeats F-008)."
        )

    def test_sign_with_wrong_password_returns_none(self, db_session):
        owner = _make_user(db_session, "signer7")
        project = _make_project(db_session, owner, code="S7")
        req = _make_requirement(db_session, project, owner, statement="S")
        sig = request_signature(
            db_session, owner.id, "requirement", req.id,
            SignatureMeaning.APPROVED.value, "WRONG_PASSWORD",
        )
        assert sig is None


# ══════════════════════════════════════
#  F-007 — values_callable on the three workflow enums
# ══════════════════════════════════════


class TestWorkflowEnumLowercase:

    def test_insert_approval_workflow_with_lowercase_status(self, db_session):
        owner = _make_user(db_session, "wfowner1")
        project = _make_project(db_session, owner, code="W1")
        # Use the enum member; SA must serialize to its lowercase .value.
        wf = ApprovalWorkflow(
            name="WF1", project_id=project.id,
            status=WorkflowStatus.ACTIVE,
            entity_type="requirement",
            created_by_id=owner.id,
        )
        db_session.add(wf); db_session.commit(); db_session.refresh(wf)
        # Round-trip via fresh query to confirm DB accepted the value.
        again = db_session.query(ApprovalWorkflow).filter(
            ApprovalWorkflow.id == wf.id,
        ).first()
        assert again is not None
        assert (
            again.status == WorkflowStatus.ACTIVE
            or str(again.status).endswith("active")
        )

    def test_insert_workflow_instance_with_lowercase_status(self, db_session):
        owner = _make_user(db_session, "wfowner2")
        project = _make_project(db_session, owner, code="W2")
        wf = ApprovalWorkflow(
            name="WF2", project_id=project.id,
            status=WorkflowStatus.ACTIVE,
            entity_type="requirement",
            created_by_id=owner.id,
        )
        db_session.add(wf); db_session.commit(); db_session.refresh(wf)

        inst = WorkflowInstance(
            workflow_id=wf.id,
            entity_type="requirement", entity_id=1,
            project_id=project.id,
            status=InstanceStatus.IN_PROGRESS,
            current_stage_number=1,
            submitted_by_id=owner.id,
        )
        db_session.add(inst); db_session.commit(); db_session.refresh(inst)
        assert inst.id is not None

    def test_insert_signature_with_lowercase_meaning(self, db_session):
        """Direct ElectronicSignature insert exercising SignatureMeaning serialization."""
        owner = _make_user(db_session, "wfowner3")
        project = _make_project(db_session, owner, code="W3")
        req = _make_requirement(db_session, project, owner, statement="S")

        sig = request_signature(
            db_session, owner.id, "requirement", req.id,
            SignatureMeaning.REVIEWED.value, "SignerPass1",
        )
        assert sig is not None
        assert (
            sig.signature_meaning == SignatureMeaning.REVIEWED
            or str(sig.signature_meaning).endswith("reviewed")
        )
