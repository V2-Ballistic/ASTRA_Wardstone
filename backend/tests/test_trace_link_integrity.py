"""
ASTRA — TraceLink integrity (F-035)
=====================================
File: backend/tests/test_trace_link_integrity.py

Covers:
  * project_id is auto-resolved from the source entity and persisted
    on the link.
  * Cross-project links are rejected with 400 (source pid != target pid).
  * Dangling source / dangling target rejected with 400.
  * Duplicate (source, target, link_type) tuple rejected with 409.
  * Project membership enforced (non-member → 403).
  * Verification entities resolve project via parent requirement.
"""

from __future__ import annotations

import pytest

from app.models import (
    Project, Requirement, SourceArtifact, TraceLink, User, Verification,
)
from app.models.project_member import ProjectMember
from app.services.auth import create_access_token, get_password_hash


# ──────────────────────────────────────
#  Helpers
# ──────────────────────────────────────


def _user(db, *, username, role="admin"):
    u = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("TraceLinkPass1"),
        full_name=username.title(),
        role=role,
        department="Eng",
        is_active=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': user.username})}"}


def _project(db, owner, code):
    p = Project(code=code, name=f"P {code}", owner_id=owner.id, status="active")
    db.add(p); db.commit(); db.refresh(p)
    db.add(ProjectMember(project_id=p.id, user_id=owner.id, added_by_id=owner.id))
    db.commit()
    return p


def _req(db, project, owner, *, req_id):
    r = Requirement(
        req_id=req_id,
        title=f"Req {req_id}",
        statement=f"The system shall handle {req_id} within 1 second.",
        rationale="trace-link integrity test",
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
    db.add(r); db.commit(); db.refresh(r)
    return r


def _artifact(db, project, owner, *, artifact_id):
    a = SourceArtifact(
        artifact_id=artifact_id,
        title=f"Artifact {artifact_id}",
        artifact_type="document",
        project_id=project.id,
        created_by_id=owner.id,
    )
    db.add(a); db.commit(); db.refresh(a)
    return a


def _verification(db, requirement, owner):
    v = Verification(
        requirement_id=requirement.id,
        method="test",
        status="planned",
        responsible_id=owner.id,
        criteria="passes integration test",
    )
    db.add(v); db.commit(); db.refresh(v)
    return v


# ──────────────────────────────────────
#  Happy path + project_id persistence
# ──────────────────────────────────────


class TestHappyPath:
    def test_create_link_persists_project_id(self, client, db_session):
        owner = _user(db_session, username="tl_owner")
        project = _project(db_session, owner, "TL1")
        req = _req(db_session, project, owner, req_id="R1")
        art = _artifact(db_session, project, owner, artifact_id="A1")

        r = client.post(
            "/api/v1/traceability/links",
            json={
                "source_type": "requirement",
                "source_id": req.id,
                "target_type": "source_artifact",
                "target_id": art.id,
                "link_type": "satisfaction",
            },
            headers=_headers(owner),
        )
        assert r.status_code == 201, r.text
        link_id = r.json()["id"]
        link = db_session.query(TraceLink).get(link_id)
        assert link.project_id == project.id

    def test_verification_source_resolves_via_parent_requirement(
        self, client, db_session,
    ):
        owner = _user(db_session, username="tl_verif_owner")
        project = _project(db_session, owner, "TL2")
        req = _req(db_session, project, owner, req_id="R2")
        verif = _verification(db_session, req, owner)
        target_req = _req(db_session, project, owner, req_id="R2T")

        r = client.post(
            "/api/v1/traceability/links",
            json={
                "source_type": "verification",
                "source_id": verif.id,
                "target_type": "requirement",
                "target_id": target_req.id,
                "link_type": "verification",
            },
            headers=_headers(owner),
        )
        assert r.status_code == 201, r.text


# ──────────────────────────────────────
#  Cross-project rejection
# ──────────────────────────────────────


class TestCrossProjectRejected:
    def test_source_in_a_target_in_b_returns_400(self, client, db_session):
        owner = _user(db_session, username="tl_xproj_owner")
        project_a = _project(db_session, owner, "TLA")
        project_b = _project(db_session, owner, "TLB")
        req_a = _req(db_session, project_a, owner, req_id="RA")
        req_b = _req(db_session, project_b, owner, req_id="RB")

        r = client.post(
            "/api/v1/traceability/links",
            json={
                "source_type": "requirement",
                "source_id": req_a.id,
                "target_type": "requirement",
                "target_id": req_b.id,
                "link_type": "satisfaction",
            },
            headers=_headers(owner),
        )
        assert r.status_code == 400, r.text
        assert "span projects" in r.json()["detail"].lower() or "cross" in r.json()["detail"].lower()


# ──────────────────────────────────────
#  Dangling references rejected
# ──────────────────────────────────────


class TestDanglingRejected:
    def test_dangling_source_returns_400(self, client, db_session):
        owner = _user(db_session, username="tl_dangle_src")
        project = _project(db_session, owner, "TLD1")
        req = _req(db_session, project, owner, req_id="RD1")

        r = client.post(
            "/api/v1/traceability/links",
            json={
                "source_type": "requirement",
                "source_id": 99999,        # does not exist
                "target_type": "requirement",
                "target_id": req.id,
                "link_type": "satisfaction",
            },
            headers=_headers(owner),
        )
        assert r.status_code == 400, r.text

    def test_dangling_target_returns_400(self, client, db_session):
        owner = _user(db_session, username="tl_dangle_tgt")
        project = _project(db_session, owner, "TLD2")
        req = _req(db_session, project, owner, req_id="RD2")

        r = client.post(
            "/api/v1/traceability/links",
            json={
                "source_type": "requirement",
                "source_id": req.id,
                "target_type": "requirement",
                "target_id": 99999,        # does not exist
                "link_type": "satisfaction",
            },
            headers=_headers(owner),
        )
        assert r.status_code == 400, r.text


# ──────────────────────────────────────
#  Duplicate rejected
# ──────────────────────────────────────


class TestDuplicateRejected:
    def test_same_source_target_link_type_returns_409(self, client, db_session):
        owner = _user(db_session, username="tl_dup_owner")
        project = _project(db_session, owner, "TLDUP")
        req_a = _req(db_session, project, owner, req_id="RDA")
        req_b = _req(db_session, project, owner, req_id="RDB")

        body = {
            "source_type": "requirement",
            "source_id": req_a.id,
            "target_type": "requirement",
            "target_id": req_b.id,
            "link_type": "satisfaction",
        }
        r1 = client.post("/api/v1/traceability/links", json=body, headers=_headers(owner))
        assert r1.status_code == 201, r1.text

        r2 = client.post("/api/v1/traceability/links", json=body, headers=_headers(owner))
        assert r2.status_code == 409, r2.text
        assert "already exists" in r2.json()["detail"].lower()


# ──────────────────────────────────────
#  Membership enforced
# ──────────────────────────────────────


class TestMembershipEnforced:
    def test_non_member_cannot_create_link(self, client, db_session):
        owner = _user(db_session, username="tl_member_owner", role="project_manager")
        outsider = _user(
            db_session, username="tl_member_outsider", role="project_manager",
        )
        project = _project(db_session, owner, "TLM")
        req_a = _req(db_session, project, owner, req_id="RM1")
        req_b = _req(db_session, project, owner, req_id="RM2")

        r = client.post(
            "/api/v1/traceability/links",
            json={
                "source_type": "requirement",
                "source_id": req_a.id,
                "target_type": "requirement",
                "target_id": req_b.id,
                "link_type": "satisfaction",
            },
            headers=_headers(outsider),
        )
        assert r.status_code == 403, r.text
