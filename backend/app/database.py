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


engine = create_engine(
    _get_db_url(),
    pool_size=20,              # Steady-state connections in the pool
    max_overflow=30,           # Extra connections under burst load
    pool_timeout=30,           # Seconds to wait for a connection before raising
    pool_recycle=1800,         # Recycle connections every 30 min (PG default idle timeout)
    pool_pre_ping=True,        # Verify connection is alive before handing it out
)

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
