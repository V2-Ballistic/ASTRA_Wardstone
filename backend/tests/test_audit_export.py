"""
ASTRA — Streaming audit log export (F-020)
============================================
File: backend/tests/test_audit_export.py

Covers:
  * CSV export streams from the cursor and produces a valid CSV with
    one row per audit record + header.
  * JSON export now returns NDJSON (one record per line); each line
    parses as a dict; the count matches inserted records.
  * project_id filter: rows for other projects are not in the export.
  * project_id filter enforces project membership (non-member → 403).
  * Empty result set still returns the CSV header line and an empty
    NDJSON body.
  * Round-trip integrity: action_detail (JSON) survives CSV
    serialisation as a JSON-encoded string.

NB: Per the operating rule for sub-phase 2C, we never UPDATE / DELETE /
TRUNCATE audit_log — only INSERT — because migration 0010 installs
PG triggers that reject mutations. SQLite tests don't enforce this,
but we keep to the same rule so the same suite runs on both.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import datetime, timedelta

import pytest

from app.models import Project, User
from app.models.audit_log import AuditLog
from app.models.project_member import ProjectMember
from app.services.auth import create_access_token, get_password_hash


# ──────────────────────────────────────
#  Helpers
# ──────────────────────────────────────


def _make_user(db, *, username, role="admin"):
    u = User(
        username=username,
        email=f"{username}@example.com",
        hashed_password=get_password_hash("AuditPass1"),
        full_name=username.title(),
        role=role,
        department="Eng",
        is_active=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _headers(user):
    return {"Authorization": f"Bearer {create_access_token(data={'sub': user.username})}"}


def _make_project(db, owner, code):
    p = Project(code=code, name=f"P {code}", owner_id=owner.id, status="active")
    db.add(p); db.commit(); db.refresh(p)
    db.add(ProjectMember(project_id=p.id, user_id=owner.id, added_by_id=owner.id))
    db.commit()
    return p


def _seed_audit_rows(
    db, *, project_id: int | None, user_id: int, count: int, start_seq: int,
) -> None:
    """
    Insert *count* AuditLog rows directly. INSERT-only — never UPDATE
    / DELETE so the F-009 PG triggers stay quiet.
    """
    prev_hash = "0" * 64
    for i in range(count):
        seq = start_seq + i
        payload = {
            "field": "status",
            "old": "draft",
            "new": "approved",
            "i": i,
        }
        record_input = (
            f"{seq}|requirement.updated|requirement|{i+1}|{user_id}|{prev_hash}"
        )
        record_hash = hashlib.sha256(record_input.encode()).hexdigest()
        row = AuditLog(
            timestamp=datetime.utcnow() + timedelta(seconds=i),
            event_type="requirement.updated",
            entity_type="requirement",
            entity_id=i + 1,
            project_id=project_id,
            user_id=user_id,
            user_ip="127.0.0.1",
            user_agent="pytest",
            action_detail=payload,
            previous_hash=prev_hash,
            record_hash=record_hash,
            sequence_number=seq,
        )
        db.add(row)
        prev_hash = record_hash
    db.commit()


# ──────────────────────────────────────
#  CSV format
# ──────────────────────────────────────


class TestCSVExport:
    def test_csv_contains_header_and_rows(self, client, db_session):
        admin = _make_user(db_session, username="csv_admin")
        project = _make_project(db_session, admin, "AUD1")
        _seed_audit_rows(
            db_session, project_id=project.id, user_id=admin.id,
            count=5, start_seq=1,
        )

        r = client.get(
            f"/api/v1/audit/export?project_id={project.id}&format=csv",
            headers=_headers(admin),
        )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("text/csv")
        assert "attachment" in r.headers["content-disposition"]

        text = r.text
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        assert len(rows) == 5
        assert rows[0]["event_type"] == "requirement.updated"
        # action_detail survives as a JSON-encoded string.
        parsed = json.loads(rows[0]["action_detail"])
        assert parsed["new"] == "approved"

    def test_csv_empty_result_returns_header_only(self, client, db_session):
        admin = _make_user(db_session, username="csv_empty_admin")
        project = _make_project(db_session, admin, "AUD2")

        r = client.get(
            f"/api/v1/audit/export?project_id={project.id}&format=csv",
            headers=_headers(admin),
        )
        assert r.status_code == 200, r.text
        # Only the header row, no data rows.
        rows = list(csv.DictReader(io.StringIO(r.text)))
        assert rows == []
        assert "sequence_number" in r.text  # header is present

    def test_csv_filters_by_project(self, client, db_session):
        admin = _make_user(db_session, username="csv_filter_admin")
        project_a = _make_project(db_session, admin, "AUD3A")
        project_b = _make_project(db_session, admin, "AUD3B")

        _seed_audit_rows(
            db_session, project_id=project_a.id, user_id=admin.id,
            count=3, start_seq=100,
        )
        _seed_audit_rows(
            db_session, project_id=project_b.id, user_id=admin.id,
            count=2, start_seq=200,
        )

        r = client.get(
            f"/api/v1/audit/export?project_id={project_a.id}&format=csv",
            headers=_headers(admin),
        )
        assert r.status_code == 200
        rows = list(csv.DictReader(io.StringIO(r.text)))
        assert len(rows) == 3
        for row in rows:
            assert int(row["project_id"]) == project_a.id


# ──────────────────────────────────────
#  NDJSON format (was: JSON array)
# ──────────────────────────────────────


class TestNDJSONExport:
    def test_ndjson_one_record_per_line(self, client, db_session):
        admin = _make_user(db_session, username="ndjson_admin")
        project = _make_project(db_session, admin, "AUD4")
        _seed_audit_rows(
            db_session, project_id=project.id, user_id=admin.id,
            count=4, start_seq=10,
        )

        r = client.get(
            f"/api/v1/audit/export?project_id={project.id}&format=json",
            headers=_headers(admin),
        )
        assert r.status_code == 200, r.text
        assert r.headers["content-type"].startswith("application/x-ndjson")

        # Strip trailing whitespace then split on newlines.
        lines = [ln for ln in r.text.split("\n") if ln.strip()]
        assert len(lines) == 4
        records = [json.loads(ln) for ln in lines]
        assert all(isinstance(rec, dict) for rec in records)
        assert {rec["sequence_number"] for rec in records} == {10, 11, 12, 13}
        # action_detail is a real dict in NDJSON, not a JSON-encoded string.
        assert records[0]["action_detail"]["new"] == "approved"

    def test_ndjson_empty_result_is_empty_body(self, client, db_session):
        admin = _make_user(db_session, username="ndjson_empty_admin")
        project = _make_project(db_session, admin, "AUD5")

        r = client.get(
            f"/api/v1/audit/export?project_id={project.id}&format=json",
            headers=_headers(admin),
        )
        assert r.status_code == 200, r.text
        # Body is empty (no rows means no NDJSON lines).
        assert r.text == ""


# ──────────────────────────────────────
#  Membership scoping
# ──────────────────────────────────────


class TestMembershipScoping:
    def test_non_member_cannot_export_per_project(self, client, db_session):
        owner = _make_user(db_session, username="aud_owner", role="project_manager")
        outsider = _make_user(db_session, username="aud_outsider", role="project_manager")
        project = _make_project(db_session, owner, "AUD6")
        _seed_audit_rows(
            db_session, project_id=project.id, user_id=owner.id,
            count=2, start_seq=500,
        )

        r = client.get(
            f"/api/v1/audit/export?project_id={project.id}&format=csv",
            headers=_headers(outsider),
        )
        assert r.status_code == 403, r.text

    def test_admin_with_no_project_id_sees_all(self, client, db_session):
        """No project_id → no membership check (admin global export)."""
        admin = _make_user(db_session, username="aud_global_admin")
        project_a = _make_project(db_session, admin, "AUD7A")
        project_b = _make_project(db_session, admin, "AUD7B")

        _seed_audit_rows(
            db_session, project_id=project_a.id, user_id=admin.id,
            count=2, start_seq=600,
        )
        _seed_audit_rows(
            db_session, project_id=project_b.id, user_id=admin.id,
            count=2, start_seq=700,
        )

        r = client.get(
            "/api/v1/audit/export?format=csv",
            headers=_headers(admin),
        )
        assert r.status_code == 200, r.text
        rows = list(csv.DictReader(io.StringIO(r.text)))
        assert len(rows) == 4
