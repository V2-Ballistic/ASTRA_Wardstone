"""
ASTRA — enforce_production_guards tests
========================================
File: backend/tests/test_production_guards.py

Covers AUDIT_FINDINGS:
  - F-001 / F-003 / F-067 (already in place pre-Phase-2)
  - F-066: ALLOWED_HOSTS="*" must be refused in production.

The guard works by reading env vars at Settings() construction time and
exiting via sys.exit(1) — so each test constructs a fresh Settings
under a controlled os.environ patch and asserts SystemExit.
"""

import os
import pytest

from app.config import Settings


# A real-looking strong key — long enough and not in the weak set.
_REAL_SECRET = "a" * 64
_REAL_ENC_KEY = "b" * 64


def _build_settings(env: dict) -> Settings:
    """Construct a Settings reading from `env` only, isolated from os.environ."""
    # Pydantic-settings reads from os.environ; patch it for the call.
    saved = {k: os.environ.get(k) for k in env.keys()}
    try:
        for k, v in env.items():
            os.environ[k] = v
        return Settings()
    finally:
        for k, prev in saved.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


def test_dev_environment_skips_guards():
    """In non-production, the guard is a no-op even with weak values."""
    s = _build_settings({
        "ENVIRONMENT": "development",
        "SECRET_KEY": "changeme",            # known-weak
        "ENCRYPTION_KEY": "",                # empty
        "ALLOWED_HOSTS": "*",                # wildcard
    })
    # Should NOT exit.
    s.enforce_production_guards()


def test_prod_with_wildcard_allowed_hosts_refuses_to_start():
    """F-066: ALLOWED_HOSTS='*' in production must SystemExit."""
    s = _build_settings({
        "ENVIRONMENT": "production",
        "SECRET_KEY": _REAL_SECRET,
        "ENCRYPTION_KEY": _REAL_ENC_KEY,
        "ALLOWED_HOSTS": "*",
    })
    with pytest.raises(SystemExit) as exc:
        s.enforce_production_guards()
    assert exc.value.code == 1


def test_prod_with_empty_allowed_hosts_refuses_to_start():
    """Empty ALLOWED_HOSTS in prod is also rejected (F-066)."""
    s = _build_settings({
        "ENVIRONMENT": "production",
        "SECRET_KEY": _REAL_SECRET,
        "ENCRYPTION_KEY": _REAL_ENC_KEY,
        "ALLOWED_HOSTS": "",
    })
    with pytest.raises(SystemExit) as exc:
        s.enforce_production_guards()
    assert exc.value.code == 1


def test_prod_with_concrete_allowed_hosts_starts():
    """A real comma-separated host list is accepted."""
    s = _build_settings({
        "ENVIRONMENT": "production",
        "SECRET_KEY": _REAL_SECRET,
        "ENCRYPTION_KEY": _REAL_ENC_KEY,
        "ALLOWED_HOSTS": "astra.example.com,api.astra.example.com",
    })
    s.enforce_production_guards()


def test_prod_with_weak_secret_key_refuses_to_start():
    """Existing F-001/F-003 guard remains: weak SECRET_KEY in prod = exit."""
    s = _build_settings({
        "ENVIRONMENT": "production",
        "SECRET_KEY": "changeme",
        "ENCRYPTION_KEY": _REAL_ENC_KEY,
        "ALLOWED_HOSTS": "astra.example.com",
    })
    with pytest.raises(SystemExit):
        s.enforce_production_guards()


def test_prod_with_empty_encryption_key_refuses_to_start():
    """F-003+F-067 guard: empty ENCRYPTION_KEY in prod = exit."""
    s = _build_settings({
        "ENVIRONMENT": "production",
        "SECRET_KEY": _REAL_SECRET,
        "ENCRYPTION_KEY": "",
        "ALLOWED_HOSTS": "astra.example.com",
    })
    with pytest.raises(SystemExit):
        s.enforce_production_guards()
