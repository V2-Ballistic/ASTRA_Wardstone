"""
ASTRA — F-205 regression: raw-SQL project DELETE cascades to
requirements and baselines.
============================================================
File: backend/tests/test_project_cascade_delete.py

Pre-F-205 these FKs defaulted to NO ACTION; a `DELETE FROM projects
WHERE id=:pid` raised a constraint violation. Now they CASCADE.

We hard-delete via SQLAlchemy `text()` so we exercise the DB
constraint, not the ORM relationship's cascade="all, delete-orphan"
side. The ORM cascade has always worked.
"""

from sqlalchemy import text

from app.models import Baseline, Project, Requirement, User
from app.services.auth import get_password_hash


def test_F205_raw_sql_project_delete_cascades_to_requirements_and_baselines(db_session):
    user = User(
        username="cascade-user", email="cascade-user@example.com",
        hashed_password=get_password_hash("TestPass123"),
        full_name="Cascade", role="admin",
        department="Eng", is_active=True,
    )
    db_session.add(user)
    db_session.commit()

    project = Project(
        code="CSCD", name="Cascade Project", description="-",
        owner_id=user.id, status="active",
    )
    db_session.add(project)
    db_session.commit()

    req = Requirement(
        req_id="FR-001", title="cascade me",
        statement="The req shall be cascade-deleted with its project.",
        rationale="-",
        req_type="functional", priority="medium", level="L1",
        status="draft", project_id=project.id,
        owner_id=user.id, created_by_id=user.id,
        quality_score=50.0, version=1,
    )
    base = Baseline(
        name="cascade base", description="-",
        project_id=project.id, requirements_count=0,
        created_by_id=user.id,
    )
    db_session.add_all([req, base])
    db_session.commit()
    req_id, base_id, project_id = req.id, base.id, project.id

    # Bypass the ORM cascade entirely — exercise the FK constraint.
    db_session.execute(text("DELETE FROM projects WHERE id = :pid"), {"pid": project_id})
    db_session.commit()

    assert db_session.query(Project).filter(Project.id == project_id).first() is None
    # The cascade should have removed both rows.
    assert db_session.query(Requirement).filter(Requirement.id == req_id).first() is None
    assert db_session.query(Baseline).filter(Baseline.id == base_id).first() is None
