"""Phase 0 Fix 0a — req_type is editable at any status.

The frontend bug was that the requirement detail page did not render an
edit control for `req_type`. The backend always supported the change.
This test pins the backend behaviour so it can't regress.
"""

from __future__ import annotations


def test_can_change_req_type_after_save(client, auth_headers, test_requirement):
    """test_requirement is created with req_type='functional'."""
    r = client.patch(
        f"/api/v1/requirements/{test_requirement.id}",
        json={"req_type": "performance"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["req_type"] == "performance"


def test_req_type_change_is_recorded_in_history(
    client, auth_headers, test_requirement,
):
    client.patch(
        f"/api/v1/requirements/{test_requirement.id}",
        json={"req_type": "performance"},
        headers=auth_headers,
    )
    h = client.get(
        f"/api/v1/requirements/{test_requirement.id}/history",
        headers=auth_headers,
    )
    assert h.status_code == 200, h.text
    fields = [entry["field_changed"] for entry in h.json()["history"]]
    assert "req_type" in fields


def test_req_type_change_does_not_alter_req_id(
    client, auth_headers, test_requirement,
):
    """The prompt note ('Changing type does not change the requirement ID.')
    is a UI affordance — the backend already preserves req_id on type
    changes. Pin that contract."""
    original_req_id = test_requirement.req_id
    r = client.patch(
        f"/api/v1/requirements/{test_requirement.id}",
        json={"req_type": "interface"},
        headers=auth_headers,
    )
    assert r.status_code == 200
    assert r.json()["req_id"] == original_req_id


def test_req_type_change_allowed_in_non_draft_status(
    client, auth_headers, test_requirement, db_session,
):
    """No business rule locks type after a requirement leaves draft."""
    test_requirement.status = "approved"
    db_session.commit()

    r = client.patch(
        f"/api/v1/requirements/{test_requirement.id}",
        json={"req_type": "safety"},
        headers=auth_headers,
    )
    assert r.status_code == 200, r.text
    assert r.json()["req_type"] == "safety"
