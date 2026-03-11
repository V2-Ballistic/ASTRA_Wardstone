"""
ASTRA — Dashboard Endpoint Tests
==================================
File: backend/tests/test_dashboard.py
"""

import pytest
from app.models import Project


class TestDashboard:

    def test_dashboard_stats(
        self, client, auth_headers, test_requirement, test_project
    ):
        resp = client.get(
            "/api/v1/dashboard/stats",
            params={"project_id": test_project.id},
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Dashboard failed: {resp.text}"
        data = resp.json()

        assert data["total_requirements"] >= 1
        assert isinstance(data["by_status"], dict), "by_status must be a dict"
        assert isinstance(data["by_type"], dict), "by_type must be a dict"
        assert "verified_count" in data
        assert "avg_quality_score" in data
        assert isinstance(data["avg_quality_score"], (int, float))
        assert "total_trace_links" in data
        assert "orphan_count" in data
        assert isinstance(data["recent_activity"], list)

    def test_dashboard_empty_project(
        self, client, auth_headers, db_session, test_user
    ):
        # create a project with zero requirements
        empty = Project(
            code="EMPTY",
            name="Empty Project",
            owner_id=test_user.id,
            status="active",
        )
        db_session.add(empty)
        db_session.commit()
        db_session.refresh(empty)

        resp = client.get(
            "/api/v1/dashboard/stats",
            params={"project_id": empty.id},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requirements"] == 0
        assert data["total_trace_links"] == 0
        assert data["orphan_count"] == 0
        assert data["verified_count"] == 0
