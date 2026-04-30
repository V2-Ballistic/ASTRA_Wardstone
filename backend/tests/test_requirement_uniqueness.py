"""
ASTRA — Requirement uniqueness (F-075)
========================================
File: backend/tests/test_requirement_uniqueness.py

Coverage:
  * Duplicate (project_id, req_id) pair raises IntegrityError.
  * Same req_id permitted across different projects.
  * The composite indexes show up in Base.metadata for the model.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError

from app.models import Project, Requirement, User
from app.models.project_member import ProjectMember
from app.services.auth import get_password_hash


def _user(db, *, username, role="admin"):
    u = User(
        username=username, email=f"{username}@example.com",
        hashed_password=get_password_hash("UniqPass1"),
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


def _req(*, project, owner, req_id):
    return Requirement(
        req_id=req_id,
        title=f"Req {req_id}",
        statement="The system shall handle the uniqueness test within 1 second.",
        rationale="F-075 test",
        req_type="functional",
        priority="medium",
        status="draft",
        level="L1",
        version=1,
        quality_score=80.0,
        project_id=project.id,
        owner_id=owner.id,
        created_by_id=owner.id,
    )


class TestRequirementUniqueness:
    def test_duplicate_in_same_project_rejected(self, db_session):
        owner = _user(db_session, username="uq_owner")
        project = _project(db_session, owner, "UQ1")

        db_session.add(_req(project=project, owner=owner, req_id="FR-001"))
        db_session.commit()

        db_session.add(_req(project=project, owner=owner, req_id="FR-001"))
        with pytest.raises(IntegrityError):
            db_session.commit()
        db_session.rollback()

    def test_same_req_id_in_different_projects_allowed(self, db_session):
        owner = _user(db_session, username="uq_xproj")
        project_a = _project(db_session, owner, "UQA")
        project_b = _project(db_session, owner, "UQB")

        db_session.add(_req(project=project_a, owner=owner, req_id="FR-001"))
        db_session.add(_req(project=project_b, owner=owner, req_id="FR-001"))
        db_session.commit()  # must succeed

        n = (
            db_session.query(Requirement)
            .filter(Requirement.req_id == "FR-001")
            .count()
        )
        assert n == 2

    def test_metadata_has_composite_indexes(self):
        """Sanity check: the model's __table_args__ declared the
        (project_id, status), (project_id, req_type),
        (project_id, owner_id) composites and the
        uq_req_per_project UniqueConstraint."""
        from sqlalchemy import Index, UniqueConstraint
        tbl = Requirement.__table__
        ix_names = {ix.name for ix in tbl.indexes}
        uq_names = {
            c.name for c in tbl.constraints
            if isinstance(c, UniqueConstraint)
        }
        assert "ix_req_project_status" in ix_names
        assert "ix_req_project_type" in ix_names
        assert "ix_req_project_owner" in ix_names
        assert "uq_req_per_project" in uq_names
