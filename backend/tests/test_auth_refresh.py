"""Phase 0 Fix 0b — Cookie-based refresh-token rotation.

The codebase already had refresh-token rotation in `auth_manager`
(F-068). Phase 0 wires it through the login response as an httpOnly
cookie + extends logout to revoke ALL outstanding refresh tokens.

NOTE: the prompt mentions migration 0029 for a new `refresh_tokens`
table. The table already exists from migration 0001. We reuse it.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.models.auth_models import RefreshToken
from app.services.auth import get_password_hash


@pytest.fixture()
def login_user(db_session):
    """Create a user with a known plaintext password and return them."""
    from app.models import User
    u = User(
        username="phase0user",
        email="phase0@example.com",
        hashed_password=get_password_hash("password123"),
        full_name="Phase 0 User",
        role="developer",
        department="Test",
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    db_session.refresh(u)
    return u


def _do_login(client, username="phase0user", password="password123"):
    """Login flow uses OAuth2PasswordRequestForm — application/x-www-form-urlencoded."""
    return client.post(
        "/api/v1/auth/login",
        data={"username": username, "password": password},
    )


def test_login_sets_refresh_cookie(client, login_user):
    r = _do_login(client)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "access_token" in body
    # Cookie present in the response
    assert "refresh_token" in r.cookies, r.cookies
    raw_cookie = r.cookies["refresh_token"]
    assert isinstance(raw_cookie, str) and len(raw_cookie) >= 32


def test_refresh_via_cookie_rotates(client, login_user):
    r = _do_login(client)
    assert r.status_code == 200
    first_cookie = r.cookies["refresh_token"]

    # Call /refresh — TestClient persists cookies via client.cookies.
    r2 = client.post("/api/v1/auth/refresh")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert "access_token" in body
    second_cookie = r2.cookies["refresh_token"]
    assert second_cookie and second_cookie != first_cookie


def test_replay_of_old_refresh_fails(client, login_user):
    r = _do_login(client)
    first_cookie = r.cookies["refresh_token"]

    r2 = client.post("/api/v1/auth/refresh")
    assert r2.status_code == 200

    # Reset to the OLD cookie and try again — must fail.
    client.cookies.clear()
    client.cookies.set("refresh_token", first_cookie)
    r3 = client.post("/api/v1/auth/refresh")
    assert r3.status_code == 401


def test_refresh_via_body_still_works_for_legacy_clients(client, login_user):
    """Backwards compat: pre-Phase 0 clients pass the refresh token in the
    JSON body. The endpoint must keep accepting that path."""
    # Login + grab raw cookie (which IS the raw refresh)
    r = _do_login(client)
    raw = r.cookies["refresh_token"]

    # Clear cookies so we exercise the body path.
    client.cookies.clear()
    r2 = client.post("/api/v1/auth/refresh", json={"refresh_token": raw})
    assert r2.status_code == 200, r2.text


def test_refresh_with_no_token_returns_401(client):
    client.cookies.clear()
    r = client.post("/api/v1/auth/refresh")
    assert r.status_code == 401


def test_logout_revokes_all_refresh_tokens(
    client, login_user, db_session,
):
    """Logout must revoke EVERY active refresh token for the user — not
    only the current cookie. Phase 0 Fix 0b extends F-063."""
    # Login twice to mint 2 refresh tokens
    _do_login(client)
    _do_login(client)

    pre_active = (
        db_session.query(RefreshToken)
        .filter(
            RefreshToken.user_id == login_user.id,
            RefreshToken.revoked.is_(False),
        )
        .count()
    )
    assert pre_active >= 2

    # /auth/logout requires Authorization: Bearer <access>
    access = client.post(
        "/api/v1/auth/login",
        data={"username": "phase0user", "password": "password123"},
    ).json()["access_token"]
    r = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {access}"},
    )
    assert r.status_code == 204

    post_active = (
        db_session.query(RefreshToken)
        .filter(
            RefreshToken.user_id == login_user.id,
            RefreshToken.revoked.is_(False),
        )
        .count()
    )
    assert post_active == 0

    # Subsequent refresh must fail.
    r2 = client.post("/api/v1/auth/refresh")
    assert r2.status_code == 401
