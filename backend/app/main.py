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
]:
    try:
        __import__(_model_path)
    except ImportError as exc:
        logger.warning("Failed to import model module %s: %s", _model_path, exc)

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
    yield


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
