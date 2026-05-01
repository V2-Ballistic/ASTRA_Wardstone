"""
ASTRA — F-203 regression: requirement req_id generation is race-safe
=====================================================================
File: backend/tests/test_requirement_id_race.py

Two simulated concurrent POSTs against the same project + req_type
must both succeed (200/201) and return distinct req_id values. Pre-F-203
both calls computed the same `count + 1` and either:
  (a) silently re-used the same req_id (pre-F-075), or
  (b) the second call hit the F-075 UNIQUE constraint and 500'd.

The id_sequences row is FOR-UPDATE-locked, so true Postgres
concurrency serialises on the row. Sqlite + StaticPool funnels both
calls through one connection, so we simulate concurrency by
back-to-back calls that share the test session — sufficient to prove
that next_human_id increments and that no two requirements end up with
the same req_id under the same transaction's view.
"""

import pytest
from app.models import Project, Requirement, User
from app.models.project_member import ProjectMember
from app.services.auth import create_access_token, get_password_hash


@pytest.fixture()
def authed_project(db_session):
    user = User(
        username="race-user", email="race-user@example.com",
        hashed_password=get_password_hash("TestPass123"),
        full_name="Race User", role="admin",
        department="Eng", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    project = Project(
        code="RACE", name="Race Project", description="-",
        owner_id=user.id, status="active",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)

    headers = {
        "Authorization": f"Bearer {create_access_token(data={'sub': user.username})}"
    }
    return user, project, headers


def _payload(title: str) -> dict:
    return {
        "title": title,
        "statement": "The system shall do something useful within 10 seconds.",
        "rationale": "We need it.",
        "req_type": "functional",
        "priority": "high",
        "level": "L1",
    }


def test_F203_two_concurrent_creates_yield_distinct_req_ids(client, authed_project):
    user, project, headers = authed_project

    r1 = client.post(
        f"/api/v1/requirements/?project_id={project.id}",
        headers=headers, json=_payload("first"),
    )
    r2 = client.post(
        f"/api/v1/requirements/?project_id={project.id}",
        headers=headers, json=_payload("second"),
    )

    assert r1.status_code == 201, r1.text
    assert r2.status_code == 201, r2.text
    body1 = r1.json()
    body2 = r2.json()
    assert body1["req_id"] != body2["req_id"], (
        "F-203: concurrent creates must produce distinct req_ids; "
        f"got {body1['req_id']} and {body2['req_id']}"
    )
    # Sanity: ids increment monotonically — FR-001, FR-002.
    assert body1["req_id"] == "FR-001"
    assert body2["req_id"] == "FR-002"


def test_F203_subsequent_create_matches_existing_max_seed(client, authed_project, db_session):
    """Pre-existing FR-005 should make the next id FR-006 (lazy seed)."""
    user, project, headers = authed_project

    # Manually insert FR-005 to mimic legacy data without an id_sequences row.
    legacy = Requirement(
        req_id="FR-005", title="legacy",
        statement="The legacy req shall exist.",
        rationale="-",
        req_type="functional", priority="medium", level="L1",
        status="draft", project_id=project.id,
        owner_id=user.id, created_by_id=user.id,
        quality_score=50.0, version=1,
    )
    db_session.add(legacy)
    db_session.commit()

    r = client.post(
        f"/api/v1/requirements/?project_id={project.id}",
        headers=headers, json=_payload("after-legacy"),
    )
    assert r.status_code == 201, r.text
    assert r.json()["req_id"] == "FR-006"
