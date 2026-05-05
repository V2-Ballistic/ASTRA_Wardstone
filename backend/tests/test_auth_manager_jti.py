"""
ASTRA — Regression test for BACKLOG F-200
==========================================

Issue: ``services/auth_manager.create_access_token`` did NOT stamp a
``jti`` claim. Tokens minted via SAML / OIDC / PIV / MFA / refresh-rotation
paths therefore bypassed the F-063 revocation list entirely (the check
in ``services/auth.get_current_user`` is gated by ``if jti:``).

This test issues tokens via every public path through ``auth_manager``
and asserts that ``jti`` is present and looks like a 32-char hex.

It fails before the fix and passes after.
"""

from datetime import timedelta

from jose import jwt

from app.config import settings
from app.models import User
from app.services.auth import get_password_hash
from app.services.auth_manager import (
    create_access_token,
    create_refresh_token,
    refresh_access_token,
)


def _decode(token: str) -> dict:
    return jwt.decode(
        token,
        settings.SECRET_KEY.get_secret_value(),
        algorithms=[settings.ALGORITHM],
        options={"verify_exp": False},
    )


def test_auth_manager_create_access_token_stamps_jti():
    token = create_access_token(
        data={"sub": "audit-test-user"},
        expires_delta=timedelta(minutes=5),
    )
    payload = _decode(token)
    assert "jti" in payload, "F-200: auth_manager tokens must include jti"
    assert isinstance(payload["jti"], str)
    assert len(payload["jti"]) == 32, "uuid4().hex is 32 chars"


def test_auth_manager_partial_mfa_token_stamps_jti():
    token = create_access_token(
        data={"sub": "audit-test-user"},
        expires_delta=timedelta(minutes=5),
        partial=True,
    )
    payload = _decode(token)
    assert "jti" in payload, "Partial MFA tokens must also be revocable"
    assert payload.get("mfa_pending") is True


def test_auth_manager_jti_is_unique_across_calls():
    t1 = create_access_token(data={"sub": "u"}, expires_delta=timedelta(minutes=5))
    t2 = create_access_token(data={"sub": "u"}, expires_delta=timedelta(minutes=5))
    assert _decode(t1)["jti"] != _decode(t2)["jti"]


def test_refresh_access_token_returns_token_with_jti(db_session):
    user = User(
        username="jti-refresh-user",
        email="jti-refresh-user@example.com",
        hashed_password=get_password_hash("TestPass123"),
        full_name="Refresh Test",
        role="developer",
        department="Testing",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    raw_refresh = create_refresh_token(db_session, user.id)
    out = refresh_access_token(db_session, raw_refresh)
    assert out is not None, "valid refresh token should produce new pair"

    payload = _decode(out["access_token"])
    assert "jti" in payload, (
        "F-200: refresh-rotated access tokens must include jti so logout works"
    )
    assert len(payload["jti"]) == 32
