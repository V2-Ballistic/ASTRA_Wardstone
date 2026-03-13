"""
ASTRA — Dashboard Endpoint Tests (updated)
=============================================
File: backend/tests/test_dashboard.py

Adds assertion for by_level dict in dashboard stats response.
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
        assert isinstance(data["by_level"], dict), "by_level must be a dict"
        assert "verified_count" in data
        assert "avg_quality_score" in data
        assert isinstance(data["avg_quality_score"], (int, float))
        assert "total_trace_links" in data
        assert "orphan_count" in data
        assert isinstance(data["recent_activity"], list)

    def test_dashboard_by_level_counts(
        self, client, auth_headers, test_requirement, test_project
    ):
        """Verify by_level values sum to total_requirements."""
        resp = client.get(
            "/api/v1/dashboard/stats",
            params={"project_id": test_project.id},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        level_sum = sum(data["by_level"].values())
        assert level_sum == data["total_requirements"], (
            f"by_level sum ({level_sum}) != total ({data['total_requirements']})"
        )

    def test_dashboard_excludes_deleted(
        self, client, auth_headers, test_requirement, test_project, db_session
    ):
        """Soft-deleted requirements should not appear in counts."""
        from app.models import Requirement

        # Soft-delete the test requirement
        test_requirement.status = "deleted"
        test_requirement.version += 1
        db_session.commit()

        resp = client.get(
            "/api/v1/dashboard/stats",
            params={"project_id": test_project.id},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_requirements"] == 0
        assert "deleted" not in data["by_status"]

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
        assert data["by_level"] == {}
        assert data["total_trace_links"] == 0
        assert data["orphan_count"] == 0
        assert data["verified_count"] == 0
