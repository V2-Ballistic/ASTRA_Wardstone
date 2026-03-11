"""
ASTRA — Alembic Environment Configuration
============================================
File: backend/alembic/env.py   ← NEW

Configures Alembic to:
  - Pull DATABASE_URL from the app's Settings (supports both str and SecretStr)
  - Import ALL model modules so autogenerate sees every table
  - Support online (connected) and offline (SQL-script) migration modes
  - Render enums correctly for PostgreSQL

Run migrations from the backend/ directory:
  alembic upgrade head
  alembic revision --autogenerate -m "description"
"""

import os
import sys
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# ── Ensure the app package is importable ──
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))  # backend/

# ── Import app config and database ──
from app.config import settings
from app.database import Base

# ── Import ALL models so metadata is populated ──
# Core models
from app.models import (                        # noqa: F401
    User, Project, Requirement, SourceArtifact,
    TraceLink, Verification, RequirementHistory,
    Baseline, BaselineRequirement, Comment,
)

# Phase-1 addon models (import silently if they exist)
_optional_models = [
    "app.models.project_member",       # RBAC
    "app.models.audit_log",            # Tamper-evident audit
    "app.models.auth_models",          # MFA / refresh tokens
    "app.models.security_models",      # Account lockout
    "app.models.workflow",             # Approval workflows + e-signatures
]
for _mod in _optional_models:
    try:
        __import__(_mod)
    except ImportError:
        pass

# ── Alembic config object (reads alembic.ini) ──
config = context.config

# Override the sqlalchemy.url from the app's settings
_db_url = settings.DATABASE_URL
# Handle pydantic SecretStr (security-hardened config)
if hasattr(_db_url, "get_secret_value"):
    _db_url = _db_url.get_secret_value()
config.set_main_option("sqlalchemy.url", str(_db_url))

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Metadata target for autogenerate
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """
    Generate SQL script without connecting to the database.
    Useful for generating migration SQL to review before applying.

    Usage: alembic upgrade head --sql
    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        render_as_batch=False,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """
    Connect to the database and run migrations directly.
    This is the normal operational mode.
    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            render_as_batch=False,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
