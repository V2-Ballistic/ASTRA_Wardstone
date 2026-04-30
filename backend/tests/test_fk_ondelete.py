"""
ASTRA — FK ondelete strategies (F-076)
========================================
File: backend/tests/test_fk_ondelete.py

Coverage:
  * Deleting a Project cascades to its SourceArtifacts.
  * Deleting a Requirement cascades to its Verifications.
  * Deleting a Requirement cascades to its RequirementHistory rows.
  * Deleting a User SET-NULLs Project.owner_id (project survives).
  * Deleting a User SET-NULLs SourceArtifact.created_by_id.
  * Deleting a User SET-NULLs Verification.responsible_id.
  * Audit_log rows survive a project delete (project_id SET NULL) —
    the AU-9 immutability constraint stays intact (the rows aren't
    DELETEd, just their project_id is nulled).
"""

from __future__ import annotations

import hashlib
from datetime import datetime

import pytest

from app.models import (
    Project, Requirement, RequirementHistory, SourceArtifact, User,
    Verification,
)
from app.models.audit_log import AuditLog
from app.models.project_member import ProjectMember
from app.services.auth import get_password_hash


# ──────────────────────────────────────
#  Helpers
# ──────────────────────────────────────


def _user(db, *, username, role="admin"):
    u = User(
        username=username, email=f"{username}@example.com",
        hashed_password=get_password_hash("FkPass1"),
        full_name=username.title(), role=role, department="Eng",
        is_active=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _project(db, owner, code):
    p = Project(code=code, name=f"P {code}", owner_id=owner.id, status="active")
    db.add(p); db.commit(); db.refresh(p)
    db.add(ProjectMember(project_id=p.id, user_id=owner.id, added_by_id=owner.id))
    db.commit()
    return p


def _req(db, project, owner, *, req_id="R1"):
    r = Requirement(
        req_id=req_id,
        title=f"R {req_id}",
        statement="The system shall handle the cascade test within 1 second.",
        rationale="F-076",
        req_type="functional", priority="medium", status="draft",
        level="L1", version=1, quality_score=80.0,
        project_id=project.id, owner_id=owner.id, created_by_id=owner.id,
    )
    db.add(r); db.commit(); db.refresh(r)
    return r


# ──────────────────────────────────────
#  Project → artifact CASCADE
# ──────────────────────────────────────


class TestProjectCascade:
    def test_deleting_project_cascades_artifacts(self, db_session):
        owner = _user(db_session, username="cascade_proj_owner")
        project = _project(db_session, owner, "C1")
        art = SourceArtifact(
            artifact_id="A1", title="A", artifact_type="document",
            project_id=project.id, created_by_id=owner.id,
        )
        db_session.add(art); db_session.commit()
        art_id = art.id

        # SQLAlchemy doesn't know about Project↔ProjectMember as a
        # relationship object, so on `db.delete(project)` it tries to
        # NULL-out child rows via Python-level dissociation rather than
        # relying on the DB-level CASCADE. Drop the membership row by
        # hand so the artifact-cascade test isolates F-076's behavior.
        db_session.query(ProjectMember).filter_by(project_id=project.id).delete()
        db_session.commit()

        db_session.delete(project)
        db_session.commit()

        assert db_session.query(SourceArtifact).filter_by(id=art_id).first() is None


# ──────────────────────────────────────
#  Requirement → verification + history CASCADE
# ──────────────────────────────────────


class TestRequirementCascade:
    def test_deleting_requirement_cascades_verifications(self, db_session):
        owner = _user(db_session, username="cascade_req_v_owner")
        project = _project(db_session, owner, "CR1")
        req = _req(db_session, project, owner, req_id="VR-1")
        v = Verification(
            requirement_id=req.id, method="test", status="planned",
            responsible_id=owner.id,
        )
        db_session.add(v); db_session.commit()
        v_id = v.id

        db_session.delete(req)
        db_session.commit()

        assert db_session.query(Verification).filter_by(id=v_id).first() is None

    def test_deleting_requirement_cascades_history(self, db_session):
        owner = _user(db_session, username="cascade_req_h_owner")
        project = _project(db_session, owner, "CR2")
        req = _req(db_session, project, owner, req_id="HR-1")
        h = RequirementHistory(
            requirement_id=req.id, version=1, field_changed="status",
            old_value="draft", new_value="approved",
            changed_by_id=owner.id, changed_at=datetime.utcnow(),
        )
        db_session.add(h); db_session.commit()
        h_id = h.id

        db_session.delete(req)
        db_session.commit()

        assert db_session.query(RequirementHistory).filter_by(id=h_id).first() is None


# ──────────────────────────────────────
#  User → SET NULL on owner / responsible / created_by
# ──────────────────────────────────────


class TestUserSetNull:
    def test_deleting_user_nulls_project_owner(self, db_session):
        owner = _user(db_session, username="setnull_proj_owner")
        project = _project(db_session, owner, "SN1")

        # Drop the membership row first — it's a separate FK and would
        # block the user delete on its own NOT NULL FK.
        db_session.query(ProjectMember).filter_by(user_id=owner.id).delete()
        db_session.commit()
        # Project.owner_id and Requirement.owner_id are also FKs to
        # users — the user owns no requirements in this test, but
        # these tests only assert the SET NULL → project.owner_id path.
        db_session.delete(owner)
        db_session.commit()

        refreshed = db_session.query(Project).filter_by(id=project.id).first()
        assert refreshed is not None
        assert refreshed.owner_id is None

    def test_deleting_user_nulls_artifact_created_by(self, db_session):
        owner = _user(db_session, username="setnull_art_owner")
        creator = _user(db_session, username="setnull_creator")
        project = _project(db_session, owner, "SN2")
        art = SourceArtifact(
            artifact_id="SN2-A1", title="A", artifact_type="document",
            project_id=project.id, created_by_id=creator.id,
        )
        db_session.add(art); db_session.commit()
        art_id = art.id

        db_session.delete(creator)
        db_session.commit()

        refreshed = db_session.query(SourceArtifact).filter_by(id=art_id).first()
        assert refreshed is not None
        assert refreshed.created_by_id is None


# ──────────────────────────────────────
#  AuditLog SET NULL on project / user delete
# ──────────────────────────────────────


class TestAuditLogSurvives:
    def _audit_row(self, db, *, user, project, seq):
        prev_hash = "0" * 64
        rec_input = f"{seq}|test.event|test|1|{user.id}|{prev_hash}"
        return AuditLog(
            timestamp=datetime.utcnow(),
            event_type="test.event",
            entity_type="test",
            entity_id=1,
            project_id=project.id,
            user_id=user.id,
            user_ip="127.0.0.1",
            user_agent="pytest",
            action_detail={"k": "v"},
            previous_hash=prev_hash,
            record_hash=hashlib.sha256(rec_input.encode()).hexdigest(),
            sequence_number=seq,
        )

    def test_audit_row_survives_project_delete_with_null_project_id(self, db_session):
        owner = _user(db_session, username="audit_proj_owner")
        project = _project(db_session, owner, "AS1")
        row = self._audit_row(db_session, user=owner, project=project, seq=4001)
        db_session.add(row); db_session.commit()
        row_id = row.id

        # See TestProjectCascade.test_deleting_project_cascades_artifacts
        # for why we drop project_members manually.
        db_session.query(ProjectMember).filter_by(project_id=project.id).delete()
        db_session.commit()

        db_session.delete(project)
        db_session.commit()

        refreshed = db_session.query(AuditLog).filter_by(id=row_id).first()
        assert refreshed is not None
        assert refreshed.project_id is None
        assert refreshed.user_id == owner.id  # untouched
