"""
ASTRA — Regression test for AUDIT_FINDINGS F-001
=================================================

Issue: ``services/auth_manager.create_access_token`` was passing the
SecretStr *wrapper* object to ``jwt.encode`` instead of its value.
python-jose coerced it via ``str()``, yielding the literal mask
``"**********"`` — every token issued through auth_manager (MFA partial
path, refresh flow) was signed with a non-secret value, which is a
complete forge-anyone's-token bypass on those code paths.

This test issues a token via auth_manager and decodes it with the
*intended* key. It fails before the fix (signature mismatch) and passes
after.
"""

from datetime import timedelta

import pytest
from jose import jwt

from app.config import settings
from app.services.auth_manager import create_access_token


def test_create_access_token_uses_real_secret_not_secretstr_repr():
    token = create_access_token(
        data={"sub": "audit-test-user"},
        expires_delta=timedelta(minutes=5),
    )

    real_key = settings.SECRET_KEY.get_secret_value()
    decoded = jwt.decode(token, real_key, algorithms=[settings.ALGORITHM])
    assert decoded["sub"] == "audit-test-user"

    # And confirm decoding with the SecretStr's str() repr would NOT have worked
    # (the bug's behaviour). Fail loudly if the token happens to verify against
    # the mask string — that would mean we're back in the bug.
    mask = str(settings.SECRET_KEY)
    if mask != real_key:
        with pytest.raises(jwt.JWTError):
            jwt.decode(token, mask, algorithms=[settings.ALGORITHM])


def test_partial_mfa_token_uses_real_secret():
    token = create_access_token(
        data={"sub": "audit-test-user"},
        expires_delta=timedelta(minutes=5),
        partial=True,
    )
    real_key = settings.SECRET_KEY.get_secret_value()
    decoded = jwt.decode(token, real_key, algorithms=[settings.ALGORITHM])
    assert decoded["sub"] == "audit-test-user"
    assert decoded.get("mfa_pending") is True
