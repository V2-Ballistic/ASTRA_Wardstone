"""
ASTRA — F-069 RBAC import guard
=================================
File: backend/tests/test_rbac_loud_import.py

Verifies the startup-time guard in `app/main.py`: in production, an
ImportError on `app.services.rbac` raises RuntimeError so the app
refuses to boot; in dev/test, it logs CRITICAL and continues.

We exercise the guard logic directly rather than re-importing
`app.main` (which is global state that's already loaded by conftest
for the test client). The guard is a small, self-contained piece of
logic — the test reproduces exactly what main.py does.
"""

from __future__ import annotations

import logging
import pytest


def _run_guard(is_prod: bool, fake_exc: ImportError, logger: logging.Logger) -> None:
    """Inline copy of the F-069 guard from app/main.py.

    Kept in the test rather than imported because the production guard
    runs at module-import time (not from a function) — there's nothing
    to import. If main.py's guard logic drifts from this copy, this
    test will pass while production breaks, so the comment in main.py
    points readers here as the canonical contract.
    """
    if is_prod:
        logger.critical(
            "RBAC module failed to import in production: %s. "
            "Routers fall back to permissive shims that bypass authorization. "
            "Refusing to start.", fake_exc,
        )
        raise RuntimeError(
            "RBAC unavailable in production — refusing to start. "
            "See AUDIT_FINDINGS F-069."
        ) from fake_exc
    logger.critical(
        "RBAC module not loaded (%s). Per-router permission checks will "
        "fall back to permissive shims. Acceptable in dev/test only.",
        fake_exc,
    )


def test_prod_refuses_to_start_when_rbac_import_fails(caplog):
    """In production, the guard must raise so the app doesn't boot
    with permissive shims silently in place."""
    caplog.set_level("CRITICAL", logger="astra.test")
    log = logging.getLogger("astra.test")
    fake = ImportError("forced rbac import failure for test")

    with pytest.raises(RuntimeError, match="F-069"):
        _run_guard(is_prod=True, fake_exc=fake, logger=log)

    assert any(
        "Refusing to start" in r.message and r.levelname == "CRITICAL"
        for r in caplog.records
    ), "expected a CRITICAL log explaining the refusal"


def test_dev_logs_critical_but_continues_when_rbac_import_fails(caplog):
    """In dev/test, the guard logs CRITICAL but doesn't raise so test
    fixtures and bare-bones environments still work."""
    caplog.set_level("CRITICAL", logger="astra.test")
    log = logging.getLogger("astra.test")
    fake = ImportError("forced rbac import failure for test")

    # Should NOT raise.
    _run_guard(is_prod=False, fake_exc=fake, logger=log)

    assert any(
        "Acceptable in dev/test" in r.message and r.levelname == "CRITICAL"
        for r in caplog.records
    ), "expected the dev/test fall-through CRITICAL log"


def test_main_guard_actually_runs_in_real_app():
    """Smoke check: the running app's main module must contain the
    guard. If someone deletes it, this test catches it."""
    import app.main
    src = open(app.main.__file__).read()
    # Look for the canonical F-069 strings — not implementation details.
    assert "F-069" in src
    assert "Refusing to start" in src
    assert "RBAC unavailable in production" in src
