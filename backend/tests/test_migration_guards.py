"""
ASTRA — Destructive-downgrade production guard tests (F-022)
=============================================================
File: backend/tests/test_migration_guards.py

Verifies that downgrade() on the two destructive migrations refuses
to run when ENVIRONMENT=production and ASTRA_ALLOW_DESTRUCTIVE_DOWNGRADE
is not set. Without those env vars (i.e. in dev / test) the original
behaviour is unchanged.

We don't actually run the downgrade against a DB — the guard fires
BEFORE any `op.execute` call, so the test just imports each migration
module via importlib (filename starts with a digit so plain `import`
won't work) and calls downgrade() under three env-var combinations.
"""

import importlib.util
import os
import pathlib

import pytest


_MIGRATIONS_DIR = pathlib.Path("/app/alembic/versions")


def _load_migration(filename: str):
    """Load a numbered Alembic migration as an unnamed module."""
    path = _MIGRATIONS_DIR / filename
    spec = importlib.util.spec_from_file_location(
        filename.replace(".py", ""), path,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def clean_env(monkeypatch):
    """Remove the relevant env vars so each test starts from a known state."""
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("ASTRA_ALLOW_DESTRUCTIVE_DOWNGRADE", raising=False)


@pytest.mark.parametrize("migration_file,table_drop_count", [
    ("0001_initial_schema.py", 21),
    ("0007_interface_module.py", 15),
])
def test_downgrade_refuses_in_production(
    monkeypatch, clean_env, migration_file, table_drop_count,
):
    """
    With ENVIRONMENT=production and no override, downgrade() must raise
    NotImplementedError BEFORE attempting any op.* call.
    """
    monkeypatch.setenv("ENVIRONMENT", "production")
    mig = _load_migration(migration_file)

    with pytest.raises(NotImplementedError) as exc:
        mig.downgrade()
    assert "production" in str(exc.value).lower()
    assert "ASTRA_ALLOW_DESTRUCTIVE_DOWNGRADE" in str(exc.value)


@pytest.mark.parametrize("migration_file", [
    "0001_initial_schema.py",
    "0007_interface_module.py",
])
def test_downgrade_with_override_proceeds_past_guard(
    monkeypatch, clean_env, migration_file,
):
    """
    With the override env var, the guard does NOT raise. The op.*
    calls that follow will fail because there is no Alembic context
    — that's expected; we only care that NotImplementedError did NOT
    fire from the guard.
    """
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("ASTRA_ALLOW_DESTRUCTIVE_DOWNGRADE", "true")
    mig = _load_migration(migration_file)

    # The guard does not raise → we proceed and op.drop_table fails
    # because there's no Alembic MigrationContext. We accept ANY
    # exception class OTHER than NotImplementedError (which would
    # signal the guard had fired).
    with pytest.raises(Exception) as exc:
        mig.downgrade()
    assert not isinstance(exc.value, NotImplementedError), (
        "Guard should have allowed downgrade past the env-var check; "
        f"NotImplementedError indicates the guard still tripped: {exc.value}"
    )


@pytest.mark.parametrize("migration_file", [
    "0001_initial_schema.py",
    "0007_interface_module.py",
])
def test_downgrade_in_dev_does_not_trip_guard(
    monkeypatch, clean_env, migration_file,
):
    """
    Without ENVIRONMENT=production, the guard is a no-op. As above,
    the subsequent op.drop_table fails for lack of Alembic context —
    that's the expected NON-guard error.
    """
    # Either don't set ENVIRONMENT, or set to dev — both should bypass.
    monkeypatch.setenv("ENVIRONMENT", "development")
    mig = _load_migration(migration_file)

    with pytest.raises(Exception) as exc:
        mig.downgrade()
    assert not isinstance(exc.value, NotImplementedError), (
        "Dev environment must not trip the F-022 guard. "
        f"Got NotImplementedError: {exc.value}"
    )
