"""
ASTRA — Phase 2 Membership Sweep negative tests
===============================================
File: backend/tests/test_phase2_membership_sweep.py

Covers the F-201 / F-208 / F-210 / F-211 cluster: every router that
was missing a `_check_membership` gate in BACKLOG.md must now reject
non-member callers with HTTP 403 (not 404, not 200).

We assert the exact 403 status. A 404 for a project the user can
*provably* see exists (we set it up in the fixture) would be an
information-disclosure leak; a 200 means the gate didn't fire.

A non-member is any authenticated user who is not the project owner,
not a row in `project_members`, and not a global ADMIN. We use a
PROJECT_MANAGER (not ADMIN) so RBAC clears the role check and the
membership gate is what decides the outcome.
"""

import pytest

from app.models import Project, Requirement, User
from app.models.embedding import AISuggestion
from app.models.project_member import ProjectMember
from app.models.workflow import (
    ApprovalWorkflow, WorkflowInstance, WorkflowStage, WorkflowStatus,
)
from app.services.auth import create_access_token, get_password_hash


# ══════════════════════════════════════
#  Fixture
# ══════════════════════════════════════


@pytest.fixture()
def two_projects_phase2(db_session):
    """
    Two projects A and B with disjoint memberships.

    - alice  : project_manager, member of A only
    - bob    : owner of project B (so it has a non-mason owner)
    - mason  : ADMIN (sees everything — used as the seeded owner)
    """
    alice = User(
        username="alice", email="alice@example.com",
        hashed_password=get_password_hash("TestPass123"),
        full_name="Alice", role="project_manager",
        department="Eng", is_active=True,
    )
    bob = User(
        username="bob", email="bob@example.com",
        hashed_password=get_password_hash("TestPass123"),
        full_name="Bob", role="project_manager",
        department="Eng", is_active=True,
    )
    db_session.add_all([alice, bob])
    db_session.commit()
    db_session.refresh(alice)
    db_session.refresh(bob)

    project_a = Project(
        code="A", name="Project A", description="alice-owned",
        owner_id=alice.id, status="active",
    )
    project_b = Project(
        code="B", name="Project B", description="bob-owned",
        owner_id=bob.id, status="active",
    )
    db_session.add_all([project_a, project_b])
    db_session.commit()
    db_session.refresh(project_a)
    db_session.refresh(project_b)

    # Make alice a member of A only.
    db_session.add(ProjectMember(
        project_id=project_a.id, user_id=alice.id, added_by_id=alice.id,
    ))
    db_session.commit()

    alice_headers = {
        "Authorization": f"Bearer {create_access_token(data={'sub': alice.username})}"
    }
    bob_headers = {
        "Authorization": f"Bearer {create_access_token(data={'sub': bob.username})}"
    }

    return {
        "alice": alice,
        "bob": bob,
        "alice_headers": alice_headers,
        "bob_headers": bob_headers,
        "project_a": project_a,
        "project_b": project_b,
    }


# ══════════════════════════════════════
#  F-208 — audit.get_audit_log
# ══════════════════════════════════════


def test_F208_audit_log_filtered_by_other_project_403(client, two_projects_phase2):
    """alice (member of A only) cannot read B's audit trail."""
    h = two_projects_phase2["alice_headers"]
    pid = two_projects_phase2["project_b"].id
    r = client.get(f"/api/v1/audit/log?project_id={pid}", headers=h)
    assert r.status_code == 403, r.text


def test_F208_audit_log_own_project_ok(client, two_projects_phase2):
    """alice can read A's audit trail."""
    h = two_projects_phase2["alice_headers"]
    pid = two_projects_phase2["project_a"].id
    r = client.get(f"/api/v1/audit/log?project_id={pid}", headers=h)
    assert r.status_code == 200, r.text


# ══════════════════════════════════════
#  F-210 — seed_project
# ══════════════════════════════════════


def test_F210_seed_project_other_project_403(client, two_projects_phase2):
    """alice cannot seed project B."""
    h = two_projects_phase2["alice_headers"]
    pid = two_projects_phase2["project_b"].id
    r = client.post(f"/api/v1/admin/seed-project/{pid}", headers=h)
    assert r.status_code == 403, r.text


# ══════════════════════════════════════
#  F-211 — imports.confirm_import
# ══════════════════════════════════════


def test_F211_confirm_import_other_project_403(client, two_projects_phase2):
    """alice cannot confirm an import into project B."""
    h = two_projects_phase2["alice_headers"]
    pid = two_projects_phase2["project_b"].id
    body = {"project_id": pid, "rows": []}
    r = client.post("/api/v1/imports/requirements/confirm", headers=h, json=body)
    assert r.status_code == 403, r.text


# ══════════════════════════════════════
#  F-201 — workflows
# ══════════════════════════════════════


def test_F201_workflows_create_other_project_403(client, two_projects_phase2):
    """alice cannot create a workflow scoped to project B."""
    h = two_projects_phase2["alice_headers"]
    pid = two_projects_phase2["project_b"].id
    r = client.post(
        "/api/v1/workflows/",
        headers=h,
        json={"name": "wf", "description": "", "project_id": pid, "entity_type": "requirement"},
    )
    assert r.status_code == 403, r.text


def test_F201_workflows_list_other_project_403(client, two_projects_phase2):
    h = two_projects_phase2["alice_headers"]
    pid = two_projects_phase2["project_b"].id
    r = client.get(f"/api/v1/workflows/?project_id={pid}", headers=h)
    assert r.status_code == 403, r.text


def test_F201_workflows_get_by_id_other_project_403(
    client, db_session, two_projects_phase2
):
    """GET /workflows/{id} where the workflow belongs to project B → 403 for alice."""
    pid = two_projects_phase2["project_b"].id
    wf = ApprovalWorkflow(
        name="wfB", project_id=pid, entity_type="requirement",
        created_by_id=two_projects_phase2["bob"].id,
        status=WorkflowStatus.ACTIVE,
    )
    db_session.add(wf)
    db_session.commit()

    h = two_projects_phase2["alice_headers"]
    r = client.get(f"/api/v1/workflows/{wf.id}", headers=h)
    assert r.status_code == 403, r.text


def test_F201_workflows_instance_other_project_403(
    client, db_session, two_projects_phase2
):
    """Instance lookup follows instance.project_id."""
    pid = two_projects_phase2["project_b"].id
    bob = two_projects_phase2["bob"]
    wf = ApprovalWorkflow(
        name="wfB2", project_id=pid, entity_type="requirement",
        created_by_id=bob.id, status=WorkflowStatus.ACTIVE,
    )
    db_session.add(wf)
    db_session.commit()
    inst = WorkflowInstance(
        workflow_id=wf.id, entity_type="requirement", entity_id=1,
        project_id=pid, submitted_by_id=bob.id,
    )
    db_session.add(inst)
    db_session.commit()

    h = two_projects_phase2["alice_headers"]
    r = client.get(f"/api/v1/workflows/instances/{inst.id}", headers=h)
    assert r.status_code == 403, r.text


# ══════════════════════════════════════
#  F-201 — ai router
# ══════════════════════════════════════


def test_F201_ai_duplicates_other_project_403(client, two_projects_phase2):
    h = two_projects_phase2["alice_headers"]
    pid = two_projects_phase2["project_b"].id
    r = client.get(f"/api/v1/ai/duplicates?project_id={pid}", headers=h)
    assert r.status_code == 403, r.text


def test_F201_ai_check_duplicate_other_project_403(client, two_projects_phase2):
    h = two_projects_phase2["alice_headers"]
    pid = two_projects_phase2["project_b"].id
    r = client.post(
        "/api/v1/ai/check-duplicate",
        headers=h,
        json={"statement": "The system shall foo.", "project_id": pid, "title": "t"},
    )
    assert r.status_code == 403, r.text


def test_F201_ai_stats_other_project_403(client, two_projects_phase2):
    h = two_projects_phase2["alice_headers"]
    pid = two_projects_phase2["project_b"].id
    r = client.get(f"/api/v1/ai/stats?project_id={pid}", headers=h)
    assert r.status_code == 403, r.text


def test_F201_ai_reindex_other_project_403(client, two_projects_phase2):
    h = two_projects_phase2["alice_headers"]
    pid = two_projects_phase2["project_b"].id
    r = client.post(
        "/api/v1/ai/reindex",
        headers=h,
        json={"project_id": pid, "force": False},
    )
    assert r.status_code == 403, r.text


# ══════════════════════════════════════
#  F-201 — ai_writer router
# ══════════════════════════════════════


def test_F201_ai_writer_convert_prose_other_project_403(client, two_projects_phase2):
    """When project_id is supplied and points at someone else's project → 403."""
    h = two_projects_phase2["alice_headers"]
    pid = two_projects_phase2["project_b"].id
    r = client.post(
        "/api/v1/ai/writer/convert-prose",
        headers=h,
        json={
            "prose": "The system needs to do something useful for users.",
            "project_id": pid,
        },
    )
    assert r.status_code == 403, r.text


def test_F201_ai_writer_convert_prose_no_project_passes(client, two_projects_phase2):
    """When no project_id is supplied (legacy callers) the gate is a no-op."""
    h = two_projects_phase2["alice_headers"]
    r = client.post(
        "/api/v1/ai/writer/convert-prose",
        headers=h,
        json={"prose": "The system shall enable users to log in."},
    )
    assert r.status_code == 200, r.text
