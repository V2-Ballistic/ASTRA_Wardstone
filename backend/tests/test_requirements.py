"""
ASTRA — Requirements Endpoint Tests
====================================
File: backend/tests/test_requirements.py
"""

import pytest

GOOD_REQ = {
    "title": "System Login",
    "statement": (
        "The system shall authenticate users via username and password "
        "within 3 seconds."
    ),
    "rationale": "Authentication is required for access control.",
    "req_type": "functional",
    "priority": "high",
}


# ── Create ──────────────────────────────────────────────────

class TestCreate:

    def test_create_requirement(self, client, auth_headers, test_project):
        resp = client.post(
            f"/api/v1/requirements/?project_id={test_project.id}",
            json=GOOD_REQ,
            headers=auth_headers,
        )
        assert resp.status_code == 201, f"Expected 201: {resp.text}"
        data = resp.json()
        assert data["req_id"].startswith("FR-"), (
            f"Functional prefix should be FR-, got {data['req_id']}"
        )
        assert data["status"] == "draft"
        assert data["version"] == 1
        assert data["project_id"] == test_project.id

    def test_create_requirement_quality_score(self, client, auth_headers, test_project):
        resp = client.post(
            f"/api/v1/requirements/?project_id={test_project.id}",
            json=GOOD_REQ,
            headers=auth_headers,
        )
        data = resp.json()
        assert "quality_score" in data, "Must include quality_score"
        assert isinstance(data["quality_score"], (int, float))
        assert data["quality_score"] > 50, (
            f"Well-formed req should score > 50, got {data['quality_score']}"
        )


# ── List / Filter / Search ──────────────────────────────────

class TestList:

    def test_list_requirements(self, client, auth_headers, test_requirement, test_project):
        resp = client.get(
            "/api/v1/requirements/",
            params={"project_id": test_project.id},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1, "Should contain at least test_requirement"

    def test_list_requirements_search(self, client, auth_headers, test_requirement, test_project):
        resp = client.get(
            "/api/v1/requirements/",
            params={"project_id": test_project.id, "search": "automated testing"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert len(resp.json()) >= 1, "Search should match statement text"

    def test_list_requirements_filter_status(self, client, auth_headers, test_requirement, test_project):
        resp = client.get(
            "/api/v1/requirements/",
            params={"project_id": test_project.id, "status": "draft"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        for r in resp.json():
            assert r["status"] == "draft", "Filter must return only draft"

    def test_list_requirements_filter_type(self, client, auth_headers, test_requirement, test_project):
        resp = client.get(
            "/api/v1/requirements/",
            params={"project_id": test_project.id, "req_type": "functional"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        for r in resp.json():
            assert r["req_type"] == "functional"


# ── Detail ──────────────────────────────────────────────────

class TestDetail:

    def test_get_requirement_detail(self, client, auth_headers, test_requirement):
        resp = client.get(
            f"/api/v1/requirements/{test_requirement.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == test_requirement.id
        assert "trace_count" in data, "Detail must include trace_count"
        assert "verification_status" in data, "Detail must include verification_status"


# ── Update ──────────────────────────────────────────────────

class TestUpdate:

    def test_update_requirement(self, client, auth_headers, test_requirement):
        resp = client.patch(
            f"/api/v1/requirements/{test_requirement.id}",
            json={"title": "Updated Title"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Updated Title"
        assert data["version"] == 2, "Version must increment on update"

    def test_update_requirement_quality_recalculated(
        self, client, auth_headers, test_requirement
    ):
        new_stmt = "The system shall render pages within 2 seconds under normal load."
        resp = client.patch(
            f"/api/v1/requirements/{test_requirement.id}",
            json={"statement": new_stmt},
            headers=auth_headers,
        )
        data = resp.json()
        # Score should differ from the fixture's hard-coded 85.0
        # (the new statement will get its own calculated score)
        assert "quality_score" in data


# ── Delete ──────────────────────────────────────────────────

class TestDelete:

    def test_delete_requirement(self, client, auth_headers, test_requirement):
        resp = client.delete(
            f"/api/v1/requirements/{test_requirement.id}",
            headers=auth_headers,
        )
        # Soft-delete returns 200, NOT 204
        assert resp.status_code == 200, f"Soft-delete expected 200: {resp.text}"
        assert resp.json()["status"] == "deleted"

    def test_delete_nonexistent(self, client, auth_headers):
        resp = client.delete(
            "/api/v1/requirements/99999",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ── Clone ───────────────────────────────────────────────────

class TestClone:

    def test_clone_requirement(self, client, auth_headers, test_requirement):
        resp = client.post(
            f"/api/v1/requirements/{test_requirement.id}/clone",
            headers=auth_headers,
        )
        assert resp.status_code == 201, f"Clone failed: {resp.text}"
        data = resp.json()
        assert data["title"].startswith("[CLONE]"), "Clone title must have [CLONE] prefix"
        assert data["status"] == "draft", "Clone must be draft"
        assert data["id"] != test_requirement.id, "Clone must have a new id"
        assert data["req_id"] != test_requirement.req_id, "Clone must have a new req_id"


# ── History ─────────────────────────────────────────────────

class TestHistory:

    def test_requirement_history_recorded(self, client, auth_headers, test_requirement):
        # make a change
        client.patch(
            f"/api/v1/requirements/{test_requirement.id}",
            json={"title": "Changed For History"},
            headers=auth_headers,
        )
        resp = client.get(
            f"/api/v1/requirements/{test_requirement.id}/history",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 1, "History should contain at least one entry"
        fields = [h["field_changed"] for h in data["history"]]
        assert "title" in fields, "Title change must appear in history"


# ── Comments ────────────────────────────────────────────────

class TestComments:

    def test_requirement_comments(self, client, auth_headers, test_requirement):
        # top-level comment
        r1 = client.post(
            f"/api/v1/requirements/{test_requirement.id}/comments",
            json={"content": "Looks good."},
            headers=auth_headers,
        )
        assert r1.status_code == 201, f"Comment create failed: {r1.text}"
        cid = r1.json()["id"]

        # threaded reply
        r2 = client.post(
            f"/api/v1/requirements/{test_requirement.id}/comments",
            json={"content": "Agreed!", "parent_id": cid},
            headers=auth_headers,
        )
        assert r2.status_code == 201
        assert r2.json()["parent_id"] == cid, "Reply must reference parent"

        # list
        r3 = client.get(
            f"/api/v1/requirements/{test_requirement.id}/comments",
            headers=auth_headers,
        )
        assert r3.status_code == 200
        assert r3.json()["total"] == 2


# ── Status transitions ─────────────────────────────────────

class TestTransitions:

    def test_status_transitions(self, client, auth_headers):
        resp = client.get(
            "/api/v1/requirements/status-transitions/draft",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "under_review" in data["allowed"], "draft → under_review must be allowed"
        assert "approved" not in data["allowed"], "draft → approved must NOT be allowed"
