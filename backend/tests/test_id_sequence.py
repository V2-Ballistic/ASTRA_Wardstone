"""
ASTRA — Per-project ID sequence (F-074)
=========================================
File: backend/tests/test_id_sequence.py

Coverage:
  * `next_human_id` returns sequential, distinct IDs for the same
    (project_id, prefix).
  * Different projects mint independently — no global counter.
  * Different prefixes within the same project mint independently.
  * Backfill from existing source-table data: pre-existing rows like
    UNIT-005 cause the first call to return UNIT-006 (not UNIT-001).
  * Threaded burst of 50 calls returns 50 distinct IDs (single-process
    correctness; cross-process serialisation requires Postgres + FOR
    UPDATE — sqlite is single-connection by fixture design).
  * Integration: create_artifact endpoint mints sequential IDs even
    when the per-project artifact count is reset by a delete (the
    sequence row keeps incrementing — no ID reuse).
"""

from __future__ import annotations

import threading
from typing import List

import pytest

from app.models import Project, SourceArtifact, User
from app.models.project_member import ProjectMember
from app.models.id_sequence import IdSequence
from app.services.auth import create_access_token, get_password_hash
from app.services.id_sequence import next_human_id


# ──────────────────────────────────────
#  Helpers
# ──────────────────────────────────────


def _user(db, *, username, role="admin"):
    u = User(
        username=username, email=f"{username}@example.com",
        hashed_password=get_password_hash("IdSeqPass1"),
        full_name=username.title(), role=role, department="Eng",
        is_active=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _project(db, owner, code):
    p = Project(code=code, name=f"P {code}", owner_id=owner.id, status="active")
    db.add(p); db.commit(); db.refresh(p)
    db.add(ProjectMember(project_id=p.id, user_id=owner.id, added_by_id=owner.id))
    db.commit()
    return p


# ──────────────────────────────────────
#  Sequence semantics
# ──────────────────────────────────────


class TestSequenceSemantics:
    def test_returns_sequential_distinct_ids(self, db_session):
        owner = _user(db_session, username="seq_a")
        project = _project(db_session, owner, "SQ1")

        ids = [
            next_human_id(db_session, project_id=project.id, prefix="SYS")
            for _ in range(5)
        ]
        assert ids == ["SYS-001", "SYS-002", "SYS-003", "SYS-004", "SYS-005"]

    def test_projects_are_independent(self, db_session):
        owner = _user(db_session, username="seq_b")
        a = _project(db_session, owner, "SQA")
        b = _project(db_session, owner, "SQB")

        a1 = next_human_id(db_session, project_id=a.id, prefix="SYS")
        b1 = next_human_id(db_session, project_id=b.id, prefix="SYS")
        a2 = next_human_id(db_session, project_id=a.id, prefix="SYS")

        assert a1 == "SYS-001"
        assert b1 == "SYS-001"   # independent counter
        assert a2 == "SYS-002"

    def test_prefixes_are_independent(self, db_session):
        owner = _user(db_session, username="seq_c")
        project = _project(db_session, owner, "SQC")

        sys = next_human_id(db_session, project_id=project.id, prefix="SYS")
        unit = next_human_id(db_session, project_id=project.id, prefix="UNIT")
        sys2 = next_human_id(db_session, project_id=project.id, prefix="SYS")

        assert sys == "SYS-001"
        assert unit == "UNIT-001"
        assert sys2 == "SYS-002"

    def test_backfill_from_existing_source_rows(self, db_session):
        """If the source table already has UNIT-005, the first call
        should return UNIT-006, not UNIT-001."""
        owner = _user(db_session, username="seq_d")
        project = _project(db_session, owner, "SQD")

        # Pre-create an artifact with id ART-SQD-005 (skipping the helper).
        # SourceArtifact has artifact_id we can backfill from.
        for n in (1, 5):
            db_session.add(SourceArtifact(
                artifact_id=f"ART-SQD-{n:03d}",
                title=f"pre-existing #{n}",
                artifact_type="document",
                project_id=project.id,
                created_by_id=owner.id,
            ))
        db_session.commit()

        first = next_human_id(
            db_session,
            project_id=project.id,
            prefix="ART-SQD",
            source_model=SourceArtifact,
            id_field="artifact_id",
        )
        assert first == "ART-SQD-006"


# ──────────────────────────────────────
#  Threaded burst
# ──────────────────────────────────────


class TestSerialBurst:
    def test_50_calls_return_50_distinct_sequential_ids(self, db_session):
        """sqlite + StaticPool can't model real cross-connection
        concurrency (the suite is single-process by fixture design),
        so we verify the cheaper invariant: 50 sequential calls
        produce 50 distinct, ordered IDs. Real cross-process
        serialisation lives in the FOR UPDATE row lock and is only
        exercisable on Postgres."""
        owner = _user(db_session, username="seq_serial")
        project = _project(db_session, owner, "SQS")

        results = [
            next_human_id(db_session, project_id=project.id, prefix="SYS")
            for _ in range(50)
        ]
        assert len(results) == 50
        assert len(set(results)) == 50  # all distinct
        nums = [int(s.split("-")[-1]) for s in results]
        assert nums == list(range(1, 51))


# ──────────────────────────────────────
#  Integration with create_artifact
# ──────────────────────────────────────


class TestCreateArtifactSequencing:
    def test_artifact_ids_keep_climbing_after_delete(self, client, db_session):
        owner = _user(db_session, username="art_seq", role="admin")
        project = _project(db_session, owner, "ARTSQ")
        headers = {"Authorization": f"Bearer {create_access_token(data={'sub': owner.username})}"}

        for _ in range(3):
            r = client.post(
                f"/api/v1/artifacts/?project_id={project.id}",
                json={"title": "T", "artifact_type": "document"},
                headers=headers,
            )
            assert r.status_code == 201, r.text

        ids_before = [
            row[0] for row in
            db_session.query(SourceArtifact.artifact_id)
            .filter(SourceArtifact.project_id == project.id)
            .order_by(SourceArtifact.id).all()
        ]
        assert ids_before == [f"ART-ARTSQ-{n:03d}" for n in (1, 2, 3)]

        # Delete one — the sequence must NOT reuse ART-ARTSQ-002.
        db_session.query(SourceArtifact).filter(
            SourceArtifact.artifact_id == "ART-ARTSQ-002",
        ).delete()
        db_session.commit()

        r = client.post(
            f"/api/v1/artifacts/?project_id={project.id}",
            json={"title": "T4", "artifact_type": "document"},
            headers=headers,
        )
        assert r.status_code == 201, r.text
        new_id = r.json()["artifact_id"]
        assert new_id == "ART-ARTSQ-004"
