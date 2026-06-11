"""
ASTRA — Engineering Frame ICD tests
====================================
File: backend/tests/test_engineering_frame.py   ← NEW
(ASTRA_CONFIG_ECOSYSTEM_BUILD_SPEC §3)

Covers:
  * auth required (401 without token)
  * GET 404 until registered
  * POST idempotent ensure/register (double POST → same icd, rev 1)
  * revision bump on changed datum (immutable history; current = highest)
  * GET /revisions history
  * the get_or_register_default_frame service helper
"""

from __future__ import annotations

# Imported at module (collection) time so Base.metadata knows the
# frame tables before the per-test create_all in conftest.db_engine.
import app.models.engineering_frame  # noqa: F401

from app.models.engineering_frame import (
    CITADEL_FRAME_KEY,
    FrameIcd,
    FrameIcdRevision,
)
from app.services.engineering import frame as frame_svc

BASE = "/api/v1/engineering/frame-icd/"


# ── Auth ────────────────────────────────────────────────────────────

class TestAuthRequired:
    def test_get_requires_token(self, client):
        assert client.get(BASE).status_code == 401

    def test_revisions_requires_token(self, client):
        assert client.get(f"{BASE}revisions").status_code == 401

    def test_post_requires_token(self, client):
        assert client.post(BASE, json={}).status_code == 401


# ── 404 until registered ────────────────────────────────────────────

class TestUnregistered:
    def test_get_current_404(self, client, auth_headers):
        r = client.get(BASE, headers=auth_headers)
        assert r.status_code == 404

    def test_revisions_404(self, client, auth_headers):
        r = client.get(f"{BASE}revisions", headers=auth_headers)
        assert r.status_code == 404


# ── Register / idempotency ──────────────────────────────────────────

class TestRegister:
    def test_register_with_defaults(self, client, auth_headers):
        r = client.post(BASE, json={}, headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["key"] == CITADEL_FRAME_KEY
        assert body["name"] == "CITADEL Vehicle Body Frame"
        assert body["current_rev"] == 1
        rev = body["revision"]
        assert rev["rev"] == 1
        assert rev["datum"] == "OML_nose_tip"  # PARAMETERIZED default
        assert rev["axes"] == "x_fwd_y_right_z_down"
        assert rev["units"] == "SI"
        # The rules text ties every numeric surface to the one datum.
        for needle in (
            "referencePoint_m_B", "cg_m_B", "Motor CG", "refPoint_m_B",
        ):
            assert needle in rev["rules"]

    def test_double_post_is_idempotent(self, client, auth_headers):
        first = client.post(BASE, json={}, headers=auth_headers).json()
        second = client.post(BASE, json={}, headers=auth_headers).json()
        assert second["id"] == first["id"]
        assert second["current_rev"] == 1
        assert second["revision"]["id"] == first["revision"]["id"]

    def test_post_matching_current_values_no_new_rev(self, client, auth_headers):
        first = client.post(BASE, json={}, headers=auth_headers).json()
        again = client.post(
            BASE,
            json={"datum": "OML_nose_tip", "axes": "x_fwd_y_right_z_down",
                  "units": "SI"},
            headers=auth_headers,
        ).json()
        assert again["current_rev"] == 1
        assert again["revision"]["id"] == first["revision"]["id"]

    def test_register_with_override_datum(self, client, auth_headers):
        r = client.post(
            BASE, json={"datum": "aft_closure_face"}, headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["current_rev"] == 1
        assert body["revision"]["datum"] == "aft_closure_face"


# ── Revision bump ───────────────────────────────────────────────────

class TestRevisionBump:
    def test_changed_datum_creates_new_revision(self, client, auth_headers):
        client.post(BASE, json={}, headers=auth_headers)
        r = client.post(
            BASE, json={"datum": "stakeholder_confirmed_nose_tip"},
            headers=auth_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert body["current_rev"] == 2
        assert body["revision"]["rev"] == 2
        assert body["revision"]["datum"] == "stakeholder_confirmed_nose_tip"
        # Unspecified fields carry forward from the current revision.
        assert body["revision"]["axes"] == "x_fwd_y_right_z_down"
        assert body["revision"]["units"] == "SI"

    def test_get_current_returns_highest_rev(self, client, auth_headers):
        client.post(BASE, json={}, headers=auth_headers)
        client.post(BASE, json={"datum": "datum_v2"}, headers=auth_headers)
        client.post(BASE, json={"units": "SI_mm"}, headers=auth_headers)
        r = client.get(BASE, headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["current_rev"] == 3
        assert body["revision"]["datum"] == "datum_v2"   # carried forward
        assert body["revision"]["units"] == "SI_mm"

    def test_revision_history_is_immutable_and_complete(
        self, client, auth_headers, db_session,
    ):
        client.post(BASE, json={}, headers=auth_headers)
        client.post(BASE, json={"datum": "datum_v2"}, headers=auth_headers)
        r = client.get(f"{BASE}revisions", headers=auth_headers)
        assert r.status_code == 200
        body = r.json()
        assert body["key"] == CITADEL_FRAME_KEY
        assert body["total"] == 2
        revs = body["revisions"]
        assert [x["rev"] for x in revs] == [1, 2]
        # Rev 1 keeps its original datum — append-only, never edited.
        assert revs[0]["datum"] == "OML_nose_tip"
        assert revs[1]["datum"] == "datum_v2"
        # One header row, two revision rows in the DB.
        assert db_session.query(FrameIcd).count() == 1
        assert db_session.query(FrameIcdRevision).count() == 2


# ── Service helper ──────────────────────────────────────────────────

class TestServiceHelper:
    def test_get_or_register_default_frame_creates_then_reuses(
        self, db_session, test_user,
    ):
        icd, rev = frame_svc.get_or_register_default_frame(
            db_session, test_user.id,
        )
        assert icd.key == CITADEL_FRAME_KEY
        assert rev.rev == 1
        assert rev.datum == frame_svc.DEFAULT_DATUM

        icd2, rev2 = frame_svc.get_or_register_default_frame(
            db_session, test_user.id,
        )
        assert icd2.id == icd.id
        assert rev2.id == rev.id
        assert db_session.query(FrameIcdRevision).count() == 1

    def test_ensure_frame_bumps_only_on_change(self, db_session, test_user):
        icd, rev1, created_icd, created_rev = frame_svc.ensure_frame(
            db_session, test_user.id,
        )
        assert (created_icd, created_rev) == (True, True)

        _, rev_same, created_icd2, created_rev2 = frame_svc.ensure_frame(
            db_session, test_user.id, datum=frame_svc.DEFAULT_DATUM,
        )
        assert (created_icd2, created_rev2) == (False, False)
        assert rev_same.id == rev1.id

        _, rev2, _, created_rev3 = frame_svc.ensure_frame(
            db_session, test_user.id, datum="confirmed_datum",
        )
        assert created_rev3 is True
        assert rev2.rev == 2
        assert rev2.datum == "confirmed_datum"
        assert rev2.rules == rev1.rules  # carried forward
