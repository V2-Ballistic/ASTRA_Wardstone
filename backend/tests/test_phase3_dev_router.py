"""
ASTRA — Phase 3 dev router hardening tests (F-202, F-216)
==========================================================
File: backend/tests/test_phase3_dev_router.py

Asserts:
  - /dev/seed and /dev/reset reject unauthenticated callers (401).
  - Both endpoints reject non-admin authenticated callers (403).
  - /dev/reset additionally requires X-Dev-Reset-Confirm: I-mean-it.
  - Admin without the header → 400.
  - Admin with the correct header succeeds (200).

The conftest sets ENVIRONMENT=test, so the dev router is mounted.
"""

import pytest

from app.models import User
from app.services.auth import create_access_token, get_password_hash


@pytest.fixture()
def admin_and_dev_user(db_session):
    admin = User(
        username="phase3-admin", email="phase3-admin@example.com",
        hashed_password=get_password_hash("TestPass123"),
        full_name="Phase3 Admin", role="admin",
        department="Eng", is_active=True,
    )
    dev = User(
        username="phase3-dev", email="phase3-dev@example.com",
        hashed_password=get_password_hash("TestPass123"),
        full_name="Phase3 Dev", role="developer",
        department="Eng", is_active=True,
    )
    db_session.add_all([admin, dev])
    db_session.commit()
    db_session.refresh(admin)
    db_session.refresh(dev)
    admin_h = {"Authorization": f"Bearer {create_access_token(data={'sub': admin.username})}"}
    dev_h = {"Authorization": f"Bearer {create_access_token(data={'sub': dev.username})}"}
    return admin, dev, admin_h, dev_h


def test_F202_dev_seed_unauth_rejected(client):
    r = client.post("/api/v1/dev/seed")
    assert r.status_code == 401, r.text


def test_F202_dev_reset_unauth_rejected(client):
    r = client.post("/api/v1/dev/reset")
    assert r.status_code == 401, r.text


def test_F202_dev_seed_non_admin_rejected(client, admin_and_dev_user):
    _, _, _, dev_h = admin_and_dev_user
    r = client.post("/api/v1/dev/seed", headers=dev_h)
    assert r.status_code == 403, r.text


def test_F202_dev_reset_non_admin_rejected(client, admin_and_dev_user):
    _, _, _, dev_h = admin_and_dev_user
    r = client.post(
        "/api/v1/dev/reset", headers={**dev_h, "X-Dev-Reset-Confirm": "I-mean-it"},
    )
    assert r.status_code == 403, r.text


def test_F202_dev_reset_admin_without_header_rejected(client, admin_and_dev_user):
    _, _, admin_h, _ = admin_and_dev_user
    r = client.post("/api/v1/dev/reset", headers=admin_h)
    assert r.status_code == 400, r.text
    assert "X-Dev-Reset-Confirm" in r.text


def test_F202_dev_reset_admin_wrong_header_rejected(client, admin_and_dev_user):
    _, _, admin_h, _ = admin_and_dev_user
    r = client.post(
        "/api/v1/dev/reset", headers={**admin_h, "X-Dev-Reset-Confirm": "wrong"},
    )
    assert r.status_code == 400, r.text


def test_F202_dev_reset_admin_with_header_succeeds(client, admin_and_dev_user):
    _, _, admin_h, _ = admin_and_dev_user
    r = client.post(
        "/api/v1/dev/reset", headers={**admin_h, "X-Dev-Reset-Confirm": "I-mean-it"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("status") in {"seeded", "already_seeded"}
