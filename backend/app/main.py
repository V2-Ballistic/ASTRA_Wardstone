"""
ASTRA — Main Application (Complete)
======================================
File: backend/app/main.py

All routers and models registered, including:
  - Core: auth, projects, requirements, traceability, artifacts, dashboard, baselines
  - Phase 1 add-ons: admin, audit, workflows, reports, integrations
  - AI: ai, impact, ai_writer
  - Import: CSV/XLSX requirement import
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.config import settings
from app.middleware.body_size_limit import BodySizeLimitMiddleware

logger = logging.getLogger("astra")

if hasattr(settings, "enforce_production_guards"):
    settings.enforce_production_guards()

# ── F-069: refuse to start in production if RBAC is unavailable ──
# Multiple routers wrap `from app.services.rbac import require_permission`
# in `try/except ImportError` and fall back to a permissive shim that
# reduces every guarded endpoint to a plain authn check (any logged-in
# user can do anything). That shim is fine — necessary, even — for
# barebones test fixtures, but in production it silently downgrades
# every authorization decision in the app. Pre-fix the failure was
# logged at WARNING from individual modules and easy to miss.
#
# Now: a startup probe imports rbac directly. In production, an
# ImportError is fatal. In dev/test, it's logged as critical so
# operators see it but the app still boots.
_rbac_is_prod = (
    getattr(settings, "is_production", False)
    or settings.ENVIRONMENT == "production"
)
try:
    from app.services import rbac as _rbac  # noqa: F401
except ImportError as _rbac_exc:
    if _rbac_is_prod:
        logger.critical(
            "RBAC module failed to import in production: %s. "
            "Routers fall back to permissive shims that bypass authorization. "
            "Refusing to start.", _rbac_exc,
        )
        raise RuntimeError(
            "RBAC unavailable in production — refusing to start. "
            "See AUDIT_FINDINGS F-069."
        ) from _rbac_exc
    logger.critical(
        "RBAC module not loaded (%s). Per-router permission checks will "
        "fall back to permissive shims. Acceptable in dev/test only.",
        _rbac_exc,
    )

# ── Core Routers (always loaded) ──
from app.routers.auth import router as auth_router
from app.routers.requirements import router as requirements_router
from app.routers.projects import projects_router, traceability_router, artifacts_router
from app.routers.dashboard import router as dashboard_router
from app.routers.baselines import router as baselines_router

# ── Optional Routers (loaded if the module exists) ──
# Failures here are LOGGED, not silently swallowed (AUDIT_FINDINGS F-121).
_optional_routers: list = []
for _mod, _attr in [
    ("app.routers.admin", "router"),
    ("app.routers.audit", "router"),
    ("app.routers.workflows", "router"),
    ("app.routers.reports", "router"),
    ("app.routers.integrations", "router"),
    ("app.routers.ai", "router"),
    ("app.routers.impact", "router"),
    ("app.routers.ai_writer", "router"),
    ("app.routers.imports", "router"),       # CSV/XLSX import
    ("app.routers.interface", "router"),
    ("app.routers.interface_import", "router"),
    ("app.routers.catalog", "router"),
    ("app.routers.req_sync", "router"),
    ("app.routers.coverage", "router"),
]:
    try:
        _m = __import__(_mod, fromlist=[_attr])
        _optional_routers.append(getattr(_m, _attr))
    except (ImportError, AttributeError) as exc:
        logger.warning("Failed to load optional router %s: %s", _mod, exc)

# ── Dev / Seed Routers (non-production only) ──
# AUDIT_FINDINGS F-004: seed_project was previously loaded in core
# routers without auth, allowing any authenticated (or unauthenticated)
# caller to pollute production projects with the SMDS seed data. It is
# now gated behind ENVIRONMENT != production (defence-in-depth alongside
# the projects.create permission check inside the handler).
dev_router = None
seed_project_router = None
is_prod = getattr(settings, "is_production", False) or settings.ENVIRONMENT == "production"
if not is_prod:
    try:
        from app.routers.dev import router as dev_router
    except ImportError as exc:
        logger.warning("Dev router not loaded: %s", exc)
    try:
        from app.routers.seed_project import router as seed_project_router
    except ImportError as exc:
        logger.warning("Seed-project router not loaded: %s", exc)

# ── Import ALL models so SQLAlchemy metadata is populated ──
from app.models import *  # noqa: F401,F403
for _model_path in [
    "app.models.project_member",
    "app.models.audit_log",
    "app.models.auth_models",
    "app.models.security_models",
    "app.models.workflow",
    "app.models.integration",
    "app.models.ai_models",
    "app.models.embedding",
    "app.models.impact",
    "app.models.interface",
    "app.models.report_job",
    "app.models.step_up_token",
    "app.models.id_sequence",
    "app.models.catalog",
    "app.models.req_sync",
    "app.models.coverage_exception",
]:
    try:
        __import__(_model_path)
    except ImportError as exc:
        logger.warning("Failed to import model module %s: %s", _model_path, exc)

# ── INTF-002 Phase 5: register reactive sync listeners ──
# Idempotent — wires after_update/after_delete on every source-entity model.
# Listener errors are logged + swallowed so source edits never abort.
try:
    from app.services.req_sync.listener import register_sync_listeners
    register_sync_listeners()
except Exception as exc:  # pragma: no cover
    logger.warning("req_sync listener registration failed: %s", exc)

# ── Optional Middleware ──
_middlewares: list = []
for _mw_path, _mw_cls in [
    ("app.middleware.security_headers", "SecurityHeadersMiddleware"),
    ("app.middleware.rate_limiter", "RateLimiterMiddleware"),
    ("app.middleware.audit_middleware", "AuditContextMiddleware"),
]:
    try:
        _m = __import__(_mw_path, fromlist=[_mw_cls])
        _middlewares.append((_mw_cls, getattr(_m, _mw_cls)))
    except (ImportError, AttributeError) as exc:
        logger.warning("Failed to load middleware %s.%s: %s", _mw_path, _mw_cls, exc)

# ── Alembic version check ──
def _check_alembic_head() -> None:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        from alembic.runtime.migration import MigrationContext
        from app.database import engine
        alembic_cfg = Config("alembic.ini")
        script = ScriptDirectory.from_config(alembic_cfg)
        head_rev = script.get_current_head()
        with engine.connect() as conn:
            ctx = MigrationContext.configure(conn)
            current_rev = ctx.get_current_revision()
        if current_rev is None:
            logger.warning("No Alembic revision stamp. Run: alembic upgrade head")
        elif current_rev != head_rev:
            logger.warning("DB at '%s', head is '%s'. Run: alembic upgrade head",
                           current_rev, head_rev)
        else:
            logger.info("Database schema up to date (revision: %s)", current_rev)
    except Exception as exc:
        logger.info("Alembic check skipped: %s", exc)


# ── Log AI status at startup ──
from app.services.ai.llm_client import is_ai_available, AI_PROVIDER


@asynccontextmanager
async def lifespan(app: FastAPI):
    _check_alembic_head()
    ai_status = f"AI: {'enabled (' + AI_PROVIDER + ')' if is_ai_available() else 'disabled (regex-only)'}"
    logger.info("ASTRA %s started [env=%s, %s]",
                settings.APP_VERSION, settings.ENVIRONMENT, ai_status)

    # ── INTF-002 Phase 6: schedule the coverage MV refresh ──
    # No-op without APScheduler installed; the bulk-accept path still
    # refreshes on demand. Default cadence is 10 min per spec §13.4.
    _stop_mv_refresh = None
    try:
        from app.services.coverage.refresh import (
            start_periodic_refresh, stop_periodic_refresh,
        )
        start_periodic_refresh(interval_minutes=10)
        _stop_mv_refresh = stop_periodic_refresh
    except Exception as exc:  # pragma: no cover
        logger.warning("Coverage MV scheduler init failed: %s", exc)

    try:
        yield
    finally:
        if _stop_mv_refresh is not None:
            try:
                _stop_mv_refresh()
            except Exception:  # pragma: no cover
                pass


app = FastAPI(
    title="ASTRA — Systems Engineering Platform",
    description="Requirements tracking, traceability, and systems engineering management.",
    version=settings.APP_VERSION,
    lifespan=lifespan,
    docs_url=None if is_prod else "/docs",
    redoc_url=None if is_prod else "/redoc",
)

# ── Middleware ──
# F-066: TrustedHostMiddleware enforces ALLOWED_HOSTS so a Host-header
# attacker can't poison password-reset emails, cache keys, etc. In dev
# (ALLOWED_HOSTS="*") this is effectively a no-op; in production
# config.enforce_production_guards refuses "*" outright (also F-066).
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=settings.allowed_hosts_list or ["*"],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# F-018: BodySizeLimit fires AFTER CORS (so OPTIONS preflights still
# pass) and BEFORE any router runs. Default 50 MB; override via
# MAX_UPLOAD_BYTES env var.
app.add_middleware(BodySizeLimitMiddleware)
for _name, _cls in _middlewares:
    if _name == "SecurityHeadersMiddleware":
        app.add_middleware(_cls, environment=settings.ENVIRONMENT)
    else:
        app.add_middleware(_cls)

# ── Mount Routers ──
API_PREFIX = "/api/v1"
app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(projects_router, prefix=API_PREFIX)
app.include_router(requirements_router, prefix=API_PREFIX)
app.include_router(traceability_router, prefix=API_PREFIX)
app.include_router(artifacts_router, prefix=API_PREFIX)
app.include_router(dashboard_router, prefix=API_PREFIX)
app.include_router(baselines_router, prefix=API_PREFIX)

for r in _optional_routers:
    app.include_router(r, prefix=API_PREFIX)
if dev_router:
    app.include_router(dev_router, prefix=API_PREFIX)
if seed_project_router:
    app.include_router(seed_project_router, prefix=API_PREFIX)


@app.get("/")
def root():
    return {"name": "ASTRA", "version": settings.APP_VERSION, "status": "operational"}


@app.get("/health")
def health():
    return {"status": "healthy"}
