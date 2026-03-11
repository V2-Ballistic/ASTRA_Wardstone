"""
ASTRA — Baselines Endpoint Tests
=================================
File: backend/tests/test_baselines.py
"""

import pytest


class TestCreateBaseline:

    def test_create_baseline(self, client, auth_headers, test_requirement, test_project):
        resp = client.post("/api/v1/baselines/", json={
            "name": "v1.0 Baseline",
            "description": "First baseline",
            "project_id": test_project.id,
        }, headers=auth_headers)
        assert resp.status_code == 201, f"Create baseline failed: {resp.text}"
        data = resp.json()
        assert data["name"] == "v1.0 Baseline"
        assert data["requirements_count"] >= 1, "Snapshot must capture the test requirement"

    def test_create_duplicate_baseline_name(
        self, client, auth_headers, test_requirement, test_project
    ):
        payload = {
            "name": "Duplicate",
            "project_id": test_project.id,
        }
        first = client.post("/api/v1/baselines/", json=payload, headers=auth_headers)
        assert first.status_code == 201

        second = client.post("/api/v1/baselines/", json=payload, headers=auth_headers)
        assert second.status_code == 400, "Duplicate baseline name must be rejected"


class TestCompare:

    def test_compare_baselines(
        self, client, auth_headers, test_requirement, test_project
    ):
        # baseline A
        a = client.post("/api/v1/baselines/", json={
            "name": "Before", "project_id": test_project.id,
        }, headers=auth_headers)
        a_id = a.json()["id"]

        # change the requirement
        client.patch(
            f"/api/v1/requirements/{test_requirement.id}",
            json={"title": "Changed After Baseline A"},
            headers=auth_headers,
        )

        # baseline B
        b = client.post("/api/v1/baselines/", json={
            "name": "After", "project_id": test_project.id,
        }, headers=auth_headers)
        b_id = b.json()["id"]

        resp = client.get(
            f"/api/v1/baselines/compare/{a_id}/{b_id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "summary" in data
        assert data["summary"]["modified"] >= 1, "Title change should appear as modified"


class TestSnapshotFrozen:

    def test_baseline_snapshots_frozen(
        self, client, auth_headers, test_requirement, test_project
    ):
        # snapshot
        bl = client.post("/api/v1/baselines/", json={
            "name": "Frozen Check", "project_id": test_project.id,
        }, headers=auth_headers)
        bl_id = bl.json()["id"]

        original_title = test_requirement.title

        # mutate the requirement AFTER the baseline
        client.patch(
            f"/api/v1/requirements/{test_requirement.id}",
            json={"title": "Mutated Title"},
            headers=auth_headers,
        )

        # read the baseline — snapshot must still have the old title
        resp = client.get(f"/api/v1/baselines/{bl_id}", headers=auth_headers)
        assert resp.status_code == 200
        snap_titles = [r["title"] for r in resp.json()["requirements"]]
        assert original_title in snap_titles, "Snapshot must be frozen to pre-change values"
        assert "Mutated Title" not in snap_titles


class TestDeleteBaseline:

    def test_delete_baseline(
        self, client, auth_headers, test_requirement, test_project
    ):
        bl = client.post("/api/v1/baselines/", json={
            "name": "To Delete", "project_id": test_project.id,
        }, headers=auth_headers)
        bl_id = bl.json()["id"]

        resp = client.delete(f"/api/v1/baselines/{bl_id}", headers=auth_headers)
        assert resp.status_code == 204

        # confirm it's gone
        resp2 = client.get(f"/api/v1/baselines/{bl_id}", headers=auth_headers)
        assert resp2.status_code == 404
