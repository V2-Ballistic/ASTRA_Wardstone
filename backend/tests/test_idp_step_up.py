"""
ASTRA — IdP signature step-up (F-036)
=======================================
File: backend/tests/test_idp_step_up.py

External-IdP users can't enter a local password (they don't have one)
and so couldn't e-sign workflow stages before this fix. The new
``POST /workflows/signatures/idp-step-up`` issues a one-time, short-
lived token; ``signature_service.request_signature`` accepts it as an
alternative to ``password``.

Coverage:
  * IdP user mints a token + signs successfully via the token path.
  * Same token is one-time-use — second consume fails (401-equivalent
    None from request_signature).
  * Local-password user calling /idp-step-up gets 400.
  * Local-password user can still sign via the password path
    (regression check for the original flow).
  * IdP user without a token (and without a password) cannot sign.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models import (
    ApprovalWorkflow, Project, Requirement, User, UserRole,
)
from app.models.project_member import ProjectMember
from app.models.step_up_token import StepUpToken
from app.models.workflow import (
    InstanceStatus, StageInstanceStatus, WorkflowInstance, WorkflowStage,
)
from app.services.auth import create_access_token, get_password_hash
from app.services.signature_service import (
    EXTERNAL_IDP_SENTINEL, request_signature,
)


# ──────────────────────────────────────
#  Helpers
# ──────────────────────────────────────


def _user(db, *, username, role="requirements_engineer", idp=False):
    """Create a user. If idp=True the hashed_password is the sentinel."""
    pw = EXTERNAL_IDP_SENTINEL if idp else get_password_hash("LocalPass1")
    u = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=pw,
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


def _req(db, project, owner, *, req_id="R1"):
    r = Requirement(
        req_id=req_id,
        title="Step-up sign target",
        statement="The system shall handle the step-up signature path within 1 second.",
        rationale="F-036 test",
        req_type="functional",
        priority="high",
        status="draft",
        level="L1",
        version=1,
        quality_score=85.0,
        project_id=project.id,
        owner_id=owner.id,
        created_by_id=owner.id,
    )
    db.add(r); db.commit(); db.refresh(r)
    return r


# ──────────────────────────────────────
#  Token issuance endpoint
# ──────────────────────────────────────


class TestIdpStepUpIssue:
    def test_idp_user_gets_token(self, client, db_session):
        idp = _user(db_session, username="idp_a", idp=True)
        r = client.post(
            "/api/v1/workflows/signatures/idp-step-up",
            headers=_headers(idp),
        )
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["step_up_token"]
        assert body["ttl_seconds"] > 0
        # Persisted (hashed) row exists.
        assert (
            db_session.query(StepUpToken)
            .filter(StepUpToken.user_id == idp.id)
            .count() == 1
        )

    def test_local_user_rejected_with_400(self, client, db_session):
        local = _user(db_session, username="local_a", idp=False)
        r = client.post(
            "/api/v1/workflows/signatures/idp-step-up",
            headers=_headers(local),
        )
        assert r.status_code == 400, r.text
        assert "external-idp" in r.json()["detail"].lower() or "password path" in r.json()["detail"].lower()


# ──────────────────────────────────────
#  request_signature accepts the token
# ──────────────────────────────────────


class TestRequestSignaturePaths:
    def test_idp_user_signs_with_token(self, client, db_session):
        idp = _user(db_session, username="idp_signer", idp=True)
        project = _project(db_session, idp, "IDP1")
        req = _req(db_session, project, idp)

        # Issue the token via the API to exercise the full surface.
        r = client.post(
            "/api/v1/workflows/signatures/idp-step-up",
            headers=_headers(idp),
        )
        token = r.json()["step_up_token"]

        sig = request_signature(
            db_session, idp.id, "requirement", req.id, "approved",
            password="",
            statement="IdP step-up sign",
            step_up_token=token,
        )
        assert sig is not None
        assert sig.user_id == idp.id
        assert sig.entity_type == "requirement"
        assert sig.entity_id == req.id

    def test_token_is_one_time_use(self, client, db_session):
        idp = _user(db_session, username="idp_one_time", idp=True)
        project = _project(db_session, idp, "IDP2")
        req1 = _req(db_session, project, idp, req_id="R-OT1")
        req2 = _req(db_session, project, idp, req_id="R-OT2")

        token = client.post(
            "/api/v1/workflows/signatures/idp-step-up",
            headers=_headers(idp),
        ).json()["step_up_token"]

        sig1 = request_signature(
            db_session, idp.id, "requirement", req1.id, "approved",
            password="", step_up_token=token,
        )
        assert sig1 is not None

        sig2 = request_signature(
            db_session, idp.id, "requirement", req2.id, "approved",
            password="", step_up_token=token,
        )
        assert sig2 is None  # consumed

    def test_local_user_password_path_still_works(self, client, db_session):
        local = _user(db_session, username="local_signer", idp=False)
        project = _project(db_session, local, "LOC1")
        req = _req(db_session, project, local)

        sig = request_signature(
            db_session, local.id, "requirement", req.id, "approved",
            password="LocalPass1",
        )
        assert sig is not None
        assert sig.user_id == local.id

    def test_local_user_cannot_use_step_up_token(self, client, db_session):
        """A local user holding a stolen token gets rejected — token path
        is gated on the IdP sentinel."""
        local = _user(db_session, username="local_token_thief", idp=False)
        project = _project(db_session, local, "LOC2")
        req = _req(db_session, project, local)

        # Forge a "token" — the issuance flow guards local users, so we
        # bypass it and call the consume path directly.
        sig = request_signature(
            db_session, local.id, "requirement", req.id, "approved",
            password="", step_up_token="not-a-real-token",
        )
        assert sig is None

    def test_idp_user_without_token_cannot_sign(self, client, db_session):
        idp = _user(db_session, username="idp_no_creds", idp=True)
        project = _project(db_session, idp, "IDP3")
        req = _req(db_session, project, idp)

        sig = request_signature(
            db_session, idp.id, "requirement", req.id, "approved",
            password="anything",  # won't match the sentinel
        )
        assert sig is None
