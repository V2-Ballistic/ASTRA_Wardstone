"""
ASTRA — Database Engine & Session
===================================
File: backend/app/database.py   ← REPLACES existing

Changes:
  - Tuned connection pool: pool_size=20, max_overflow=30
  - pool_timeout=30s, pool_recycle=1800s (recycle before PG kills idle conns)
  - pool_pre_ping=True (detect stale connections)
  - Handles both plain-str and SecretStr DATABASE_URL from config
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from app.config import settings


def _get_db_url() -> str:
    """Extract the database URL as a plain string, handling SecretStr."""
    url = settings.DATABASE_URL
    if hasattr(url, "get_secret_value"):
        return url.get_secret_value()
    return str(url)


_db_url = _get_db_url()
_pool_kwargs = {}
if not _db_url.startswith("sqlite"):
    _pool_kwargs = dict(
        pool_size=20,
        max_overflow=30,
        pool_timeout=30,
        pool_recycle=1800,
        pool_pre_ping=True,
    )

engine = create_engine(_db_url, **_pool_kwargs)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    """FastAPI dependency that yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
