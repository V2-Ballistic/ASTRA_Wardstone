"""
ASTRA — Traceability Endpoint Tests
====================================
File: backend/tests/test_traceability.py
"""

import pytest
from app.models import Requirement


@pytest.fixture()
def two_requirements(db_session, test_user, test_project):
    """Two requirements for linking."""
    a = Requirement(
        req_id="FR-T01", title="Source Req",
        statement="The system shall do X within 10 seconds.",
        req_type="functional", priority="high", status="draft", level="L1",
        project_id=test_project.id, owner_id=test_user.id,
        created_by_id=test_user.id, quality_score=80.0,
    )
    b = Requirement(
        req_id="FR-T02", title="Target Req",
        statement="The system shall do Y within 5 seconds.",
        req_type="functional", priority="medium", status="draft", level="L2",
        project_id=test_project.id, owner_id=test_user.id,
        created_by_id=test_user.id, quality_score=75.0,
    )
    db_session.add_all([a, b])
    db_session.commit()
    db_session.refresh(a)
    db_session.refresh(b)
    return a, b


class TestTraceLinks:

    def test_create_trace_link(self, client, auth_headers, two_requirements):
        a, b = two_requirements
        resp = client.post("/api/v1/traceability/links", json={
            "source_type": "requirement", "source_id": a.id,
            "target_type": "requirement", "target_id": b.id,
            "link_type": "decomposition",
        }, headers=auth_headers)
        assert resp.status_code == 201, f"Create link failed: {resp.text}"
        data = resp.json()
        assert data["source_id"] == a.id
        assert data["target_id"] == b.id

    def test_delete_trace_link(self, client, auth_headers, two_requirements):
        a, b = two_requirements
        create = client.post("/api/v1/traceability/links", json={
            "source_type": "requirement", "source_id": a.id,
            "target_type": "requirement", "target_id": b.id,
            "link_type": "satisfaction",
        }, headers=auth_headers)
        link_id = create.json()["id"]

        resp = client.delete(
            f"/api/v1/traceability/links/{link_id}", headers=auth_headers
        )
        assert resp.status_code == 204


class TestMatrix:

    def test_traceability_matrix(self, client, auth_headers, two_requirements, test_project):
        resp = client.get(
            "/api/v1/traceability/matrix",
            params={"project_id": test_project.id},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["requirements_count"] == 2
        assert isinstance(data["matrix"], list)
        assert "total_links" in data["matrix"][0]


class TestGraph:

    def test_traceability_graph(self, client, auth_headers, two_requirements, test_project):
        resp = client.get(
            "/api/v1/traceability/graph",
            params={"project_id": test_project.id},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "nodes" in data and "edges" in data
        assert len(data["nodes"]) == 2, "Should have one node per requirement"


class TestCoverage:

    def test_coverage_stats(self, client, auth_headers, two_requirements, test_project):
        resp = client.get(
            "/api/v1/traceability/coverage",
            params={"project_id": test_project.id},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requirements"] == 2
        assert data["forward_traced"] == 0, "No links → nothing forward-traced"
        assert data["forward_coverage"] == 0.0
