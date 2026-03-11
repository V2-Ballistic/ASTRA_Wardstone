"""
ASTRA — Main Application (AI-Enhanced)
=========================================
File: backend/app/main.py   ← REPLACES existing

Adds:
  - AIAnalysisCache + AIFeedback model imports
  - All prior integrations preserved via optional imports
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings

if hasattr(settings, "enforce_production_guards"):
    settings.enforce_production_guards()

# ── Routers ──
from app.routers.auth import router as auth_router
from app.routers.requirements import router as requirements_router
from app.routers.projects import projects_router, traceability_router, artifacts_router
from app.routers.dashboard import router as dashboard_router
from app.routers.baselines import router as baselines_router

# Conditional routers
_optional_routers: list = []
for _mod, _attr in [
    ("app.routers.admin", "router"),
    ("app.routers.audit", "router"),
    ("app.routers.workflows", "router"),
    ("app.routers.reports", "router"),
    ("app.routers.integrations", "router"),
]:
    try:
        _m = __import__(_mod, fromlist=[_attr])
        _optional_routers.append(getattr(_m, _attr))
    except (ImportError, AttributeError):
        pass

dev_router = None
is_prod = getattr(settings, "is_production", False) or settings.ENVIRONMENT == "production"
if not is_prod:
    try:
        from app.routers.dev import router as dev_router
    except ImportError:
        pass

# ── Import all models ──
from app.models import *  # noqa: F401,F403
for _model_path in [
    "app.models.project_member",
    "app.models.audit_log",
    "app.models.auth_models",
    "app.models.security_models",
    "app.models.workflow",
    "app.models.integration",
    "app.models.ai_models",             # ← NEW
]:
    try:
        __import__(_model_path)
    except ImportError:
        pass

# ── Optional middleware ──
_middlewares: list = []
for _mw_path, _mw_cls in [
    ("app.middleware.security_headers", "SecurityHeadersMiddleware"),
    ("app.middleware.rate_limiter", "RateLimiterMiddleware"),
    ("app.middleware.audit_middleware", "AuditContextMiddleware"),
]:
    try:
        _m = __import__(_mw_path, fromlist=[_mw_cls])
        _middlewares.append((_mw_cls, getattr(_m, _mw_cls)))
    except (ImportError, AttributeError):
        pass

# Alembic check
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

logger = logging.getLogger("astra")

# Log AI status at startup
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

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
for _name, _cls in _middlewares:
    if _name == "SecurityHeadersMiddleware":
        app.add_middleware(_cls, environment=settings.ENVIRONMENT)
    else:
        app.add_middleware(_cls)

# Mount routers
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


@app.get("/")
def root():
    return {"name": "ASTRA", "version": settings.APP_VERSION, "status": "operational"}


@app.get("/health")
def health():
    return {"status": "healthy"}
