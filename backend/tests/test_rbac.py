"""
ASTRA — RBAC Permission Tests
===============================
Requires the RBAC implementation (rbac.py + patched routers).
If RBAC is not yet installed, these tests will be skipped.

File: backend/tests/test_rbac.py
"""

import pytest
from tests.conftest import make_user

# Skip the entire module if rbac.py doesn't exist yet
pytest.importorskip("app.services.rbac")

GOOD_REQ = {
    "title": "RBAC Test Req",
    "statement": "The system shall enforce role-based access control within 1 second.",
    "rationale": "RBAC prevents unauthorized modifications.",
    "req_type": "functional",
    "priority": "high",
}


class TestRBAC:

    def test_admin_can_create_requirement(
        self, client, db_session, test_project
    ):
        _user, headers = make_user(db_session, "admin", "rbac_admin")
        resp = client.post(
            f"/api/v1/requirements/?project_id={test_project.id}",
            json=GOOD_REQ,
            headers=headers,
        )
        assert resp.status_code == 201, (
            f"Admin must be able to create requirements, got {resp.status_code}: {resp.text}"
        )

    def test_reviewer_cannot_create_requirement(
        self, client, db_session, test_project
    ):
        _user, headers = make_user(db_session, "reviewer", "rbac_reviewer")
        resp = client.post(
            f"/api/v1/requirements/?project_id={test_project.id}",
            json=GOOD_REQ,
            headers=headers,
        )
        assert resp.status_code == 403, (
            f"Reviewer must NOT create requirements, got {resp.status_code}"
        )

    def test_stakeholder_read_only(
        self, client, db_session, test_project, test_requirement
    ):
        _user, headers = make_user(db_session, "stakeholder", "rbac_stakeholder")

        # read should work
        read = client.get(
            "/api/v1/requirements/",
            params={"project_id": test_project.id},
            headers=headers,
        )
        assert read.status_code == 200, "Stakeholder must be able to read"

        # write should fail
        write = client.post(
            f"/api/v1/requirements/?project_id={test_project.id}",
            json=GOOD_REQ,
            headers=headers,
        )
        assert write.status_code == 403, (
            f"Stakeholder must NOT create requirements, got {write.status_code}"
        )

    def test_engineer_can_update_requirement(
        self, client, db_session, test_project, test_requirement
    ):
        _user, headers = make_user(
            db_session, "requirements_engineer", "rbac_engineer"
        )
        resp = client.patch(
            f"/api/v1/requirements/{test_requirement.id}",
            json={"title": "Engineer Updated"},
            headers=headers,
        )
        assert resp.status_code == 200, (
            f"Requirements engineer must be able to update, got {resp.status_code}: {resp.text}"
        )
        assert resp.json()["title"] == "Engineer Updated"
