"""
ASTRA — Test Fixtures
=====================
File: backend/tests/conftest.py
"""

import os

# ── Set env vars BEFORE any app import ──
os.environ["DATABASE_URL"] = "sqlite://"
os.environ["SECRET_KEY"] = "test-secret-key-not-for-production"
os.environ["ALGORITHM"] = "HS256"
os.environ["ACCESS_TOKEN_EXPIRE_MINUTES"] = "60"
os.environ["BACKEND_CORS_ORIGINS"] = "http://localhost:3000"
os.environ["ENVIRONMENT"] = "test"

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

# Patch the production engine immediately — database.py creates one at import
# time with pool_size/max_overflow that are PostgreSQL-only.
import app.database as _db_module                          # noqa: E402

_sqlite_engine = create_engine(
    "sqlite://", connect_args={"check_same_thread": False}
)
_db_module.engine = _sqlite_engine
_db_module.SessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=_sqlite_engine
)

from app.database import Base, get_db                      # noqa: E402
from app.models import User, Project, Requirement          # noqa: E402
from app.services.auth import (                            # noqa: E402
    get_password_hash,
    create_access_token,
)

# Register ProjectMember table when RBAC is present
try:
    from app.models.project_member import ProjectMember    # noqa: F401, E402
except ImportError:
    pass


# ══════════════════════════════════════
#  Core fixtures
# ══════════════════════════════════════

@pytest.fixture(scope="function")
def db_engine():
    """Fresh in-memory SQLite engine for every test function."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}
    )

    @event.listens_for(engine, "connect")
    def _enable_fks(dbapi_conn, _rec):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(bind=engine)
    yield engine
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture(scope="function")
def db_session(db_engine):
    """SQLAlchemy session tied to the per-test engine."""
    Session = sessionmaker(bind=db_engine)
    session = Session()
    yield session
    session.close()


@pytest.fixture(scope="function")
def client(db_session):
    """FastAPI TestClient using the isolated test session."""
    from app.main import app

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


# ══════════════════════════════════════
#  Convenience fixtures
# ══════════════════════════════════════

@pytest.fixture()
def test_user(db_session) -> User:
    """Admin user that can do everything."""
    user = User(
        username="testadmin",
        email="testadmin@astra.test",
        hashed_password=get_password_hash("TestPass123"),
        full_name="Test Admin",
        role="admin",
        department="Testing",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


@pytest.fixture()
def auth_headers(test_user) -> dict:
    """Bearer-token headers for test_user."""
    token = create_access_token(data={"sub": test_user.username})
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def test_project(db_session, test_user) -> Project:
    """Project owned by test_user."""
    project = Project(
        code="TEST",
        name="Test Project",
        description="Automated-test project",
        owner_id=test_user.id,
        status="active",
    )
    db_session.add(project)
    db_session.commit()
    db_session.refresh(project)
    return project


@pytest.fixture()
def test_requirement(db_session, test_user, test_project) -> Requirement:
    """Single draft requirement inside test_project."""
    req = Requirement(
        req_id="FR-001",
        title="Test Requirement",
        statement="The system shall perform automated testing within 5 seconds.",
        rationale="Automated testing improves reliability and speed.",
        req_type="functional",
        priority="high",
        status="draft",
        level="L1",
        version=1,
        quality_score=85.0,
        project_id=test_project.id,
        owner_id=test_user.id,
        created_by_id=test_user.id,
    )
    db_session.add(req)
    db_session.commit()
    db_session.refresh(req)
    return req


# ══════════════════════════════════════
#  RBAC helper — used by test_rbac.py
# ══════════════════════════════════════

def make_user(db_session, role: str, username: str | None = None):
    """Create a user with *role* and return ``(user, headers)``."""
    username = username or f"user_{role}"
    user = User(
        username=username,
        email=f"{username}@astra.test",
        hashed_password=get_password_hash("TestPass123"),
        full_name=f"Test {role.replace('_', ' ').title()}",
        role=role,
        department="Testing",
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    token = create_access_token(data={"sub": user.username})
    return user, {"Authorization": f"Bearer {token}"}
