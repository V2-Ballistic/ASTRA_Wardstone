"""
ASTRA — F-063 + F-068 auth/session hardening tests
====================================================
File: backend/tests/test_auth_revocation.py

Covers:
  F-063 — POST /auth/logout writes the access-token jti to the
          revoked_tokens table; subsequent calls with the same token
          return 401.
  F-068 — POST /auth/refresh rotates the refresh token: returns a new
          (access, refresh) pair and the *incoming* refresh token can
          no longer be used.
"""

from __future__ import annotations

import pytest
from app.models.auth_models import RefreshToken, RevokedToken
from app.services.auth import create_access_token


# ══════════════════════════════════════════════════════════════
#  F-063: revocation
# ══════════════════════════════════════════════════════════════

def test_logout_revokes_jti_and_blocks_subsequent_calls(client, auth_headers, db_session):
    # Sanity — the dep accepts the token.
    r = client.get("/api/v1/auth/me", headers=auth_headers)
    assert r.status_code == 200

    # Logout — writes a row to revoked_tokens.
    r = client.post("/api/v1/auth/logout", headers=auth_headers)
    assert r.status_code == 204, r.text

    revoked = db_session.query(RevokedToken).count()
    assert revoked >= 1

    # Same token now fails — F-063's whole point. Pre-fix the in-memory
    # blacklist was per-worker, so a different worker accepting the
    # token after logout was a real failure mode.
    r = client.get("/api/v1/auth/me", headers=auth_headers)
    assert r.status_code == 401


def test_revoked_token_check_survives_token_with_no_jti(client, db_session, test_user):
    # Tokens issued before the F-063 jti-stamping landed don't carry
    # a jti. The dep should still accept them — no jti means nothing to
    # check against the revocation table. (We can't easily forge a
    # tokenless token through the public API, so we mint one directly.)
    import uuid
    from datetime import timedelta
    from jose import jwt
    from app.config import settings

    payload = {
        "sub": test_user.username,
        "exp": __import__("datetime").datetime.utcnow() + timedelta(minutes=10),
        # Deliberately no jti.
    }
    token_no_jti = jwt.encode(
        payload, settings.SECRET_KEY.get_secret_value(),
        algorithm=settings.ALGORITHM,
    )
    r = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token_no_jti}"},
    )
    assert r.status_code == 200


# ══════════════════════════════════════════════════════════════
#  F-068: refresh rotation
# ══════════════════════════════════════════════════════════════

def test_refresh_rotates_and_old_refresh_is_invalidated(client, db_session, test_user):
    from app.services.auth_manager import create_refresh_token

    raw = create_refresh_token(db_session, test_user.id)

    # First refresh succeeds and returns a new pair.
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": raw})
    assert r.status_code == 200, r.text
    body = r.json()
    new_access = body["access_token"]
    new_refresh = body["refresh_token"]
    assert new_access
    assert new_refresh
    assert new_refresh != raw  # actually rotated

    # The OLD refresh token is now revoked — second use with the old
    # token fails. This is the rotation guarantee: a stolen refresh
    # token can be used at most once before the legitimate user's next
    # refresh invalidates it (which is the moment the theft is
    # detectable from the auth side).
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": raw})
    assert r.status_code == 401

    # The NEW refresh token works for at least one rotation.
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": new_refresh})
    assert r.status_code == 200


def test_refresh_rejects_unknown_token(client):
    r = client.post("/api/v1/auth/refresh", json={"refresh_token": "definitely-not-a-real-token"})
    assert r.status_code == 401
