"""ASTRA — Source Coverage Validator tests (Phase 6)
================================================================
File: backend/tests/test_coverage.py    ← NEW (ASTRA-TDD-INTF-002 Phase 6)

Covers spec §13.7 acceptance:

  1.  L1 orphan                                 → severity ok
  2.  L2 orphan (no parent trace)               → severity warning
  3.  L3 orphan                                 → severity error
  4.  L4 with parent traced to L3 covered       → severity ok
  5.  L4 orphan no parent trace                 → severity error
  6.  L5 with active admin-cosigned exception   → severity ok
  7.  L5 with exception but no admin co-sign    → severity warning
  8.  L5 with expired exception                 → severity error
  9.  Bulk-accept of sync proposals triggers MV refresh (mock)
 10.  Suggestion engine: "voltage" text         → SourceEntityType.PIN
 11.  RBAC: stakeholder cannot file exception (403); proj_mgr can; non-admin cannot cosign
 12.  Project membership: non-member of project A cannot view its coverage report (403)
 13.  Direct source link → severity ok regardless of level

Tests run on the SQLite in-memory test harness; the validator falls back to
its live computation path because the materialized view is PostgreSQL-only.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Tuple

import pytest

from app.models import (
    Project, Requirement, RequirementLevel, RequirementStatus, RequirementType,
    TraceLink, TraceLinkType, User, UserRole,
)
from app.models.coverage_exception import CoverageException
from app.models.project_member import ProjectMember
from app.models.req_sync import RequirementSourceLink, SourceEntityType
from app.services.auth import create_access_token, get_password_hash
from app.services.coverage import (
    suggest_source_type,
    validate_project_coverage,
)
from tests.conftest import make_user


# ══════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════

def _make_req(
    db, project, owner, *,
    req_id: str, level: str, status: str = "draft",
    parent_id=None, statement: str = "The system shall do something useful.",
    title: str = "Test req",
) -> Requirement:
    r = Requirement(
        req_id=req_id,
        title=title,
        statement=statement,
        rationale="coverage test",
        req_type="functional",
        priority="medium",
        status=status,
        level=level,
        version=1,
        quality_score=80.0,
        project_id=project.id,
        owner_id=owner.id,
        parent_id=parent_id,
        created_by_id=owner.id,
    )
    db.add(r); db.commit(); db.refresh(r)
    return r


def _add_source_link(db, requirement: Requirement,
                     entity_type=SourceEntityType.SYSTEM,
                     entity_id: int = 1) -> RequirementSourceLink:
    link = RequirementSourceLink(
        requirement_id=requirement.id,
        source_entity_type=entity_type,
        source_entity_id=entity_id,
        template_id="L1.SYSTEM_OVERVIEW",
        template_inputs={},
        role="primary",
    )
    db.add(link); db.commit(); db.refresh(link)
    return link


def _add_trace_link(db, project, source_req: Requirement, target_req: Requirement,
                    link_type: TraceLinkType = TraceLinkType.DECOMPOSITION,
                    creator: User = None) -> TraceLink:
    tl = TraceLink(
        project_id=project.id,
        source_type="requirement",
        source_id=source_req.id,
        target_type="requirement",
        target_id=target_req.id,
        link_type=link_type,
        status="active",
        created_by_id=(creator or source_req.owner).id,
    )
    db.add(tl); db.commit(); db.refresh(tl)
    return tl


# ══════════════════════════════════════════════════════════════
#  Severity rule cases (live path — MV not present on SQLite)
# ══════════════════════════════════════════════════════════════

class TestSeverityRules:
    """Each test creates one fresh requirement and asserts the severity."""

    def test_L1_orphan_is_ok(self, db_session, test_project, test_user):
        r = _make_req(db_session, test_project, test_user, req_id="FR-L1", level="L1")
        report = validate_project_coverage(db_session, test_project.id)
        orphans = {o.req_id: o for o in report.orphans}
        # L1 orphans never appear in the orphan list (they're 'ok').
        assert r.id not in orphans
        assert report.summary["L1"].total == 1
        assert report.summary["L1"].ok == 1

    def test_L2_orphan_no_parent_is_warning(self, db_session, test_project, test_user):
        r = _make_req(db_session, test_project, test_user, req_id="FR-L2", level="L2")
        report = validate_project_coverage(db_session, test_project.id)
        orphan = next(o for o in report.orphans if o.req_id == r.id)
        assert orphan.severity == "warning"
        assert report.summary["L2"].warning == 1

    def test_L3_orphan_is_error(self, db_session, test_project, test_user):
        r = _make_req(db_session, test_project, test_user, req_id="FR-L3", level="L3")
        report = validate_project_coverage(db_session, test_project.id)
        orphan = next(o for o in report.orphans if o.req_id == r.id)
        assert orphan.severity == "error"
        assert report.summary["L3"].error == 1

    def test_L4_with_traced_parent_is_ok(self, db_session, test_project, test_user):
        # L3 with a direct source — covered.
        l3 = _make_req(db_session, test_project, test_user, req_id="FR-L3p", level="L3")
        _add_source_link(db_session, l3)
        # L4 that decomposition-links to L3 — should be 'ok' via traced parent.
        l4 = _make_req(db_session, test_project, test_user, req_id="FR-L4c", level="L4")
        _add_trace_link(db_session, test_project, l4, l3,
                        link_type=TraceLinkType.DECOMPOSITION)
        report = validate_project_coverage(db_session, test_project.id)
        l4_orphans = [o for o in report.orphans if o.req_id == l4.id]
        assert l4_orphans == [], f"L4 with traced parent should be ok, got {l4_orphans}"
        assert report.summary["L4"].ok == 1

    def test_L4_orphan_is_error(self, db_session, test_project, test_user):
        r = _make_req(db_session, test_project, test_user, req_id="FR-L4o", level="L4")
        report = validate_project_coverage(db_session, test_project.id)
        orphan = next(o for o in report.orphans if o.req_id == r.id)
        assert orphan.severity == "error"

    def test_L5_with_cosigned_exception_is_ok(
        self, db_session, test_project, test_user,
    ):
        r = _make_req(db_session, test_project, test_user, req_id="FR-L5x", level="L5")
        ex = CoverageException(
            project_id=test_project.id,
            requirement_id=r.id,
            reason="No source — manually verified.",
            is_active=True,
            created_by_id=test_user.id,
            approved_by_id=test_user.id,                           # admin co-sign
            approved_at=datetime.now(timezone.utc),
        )
        db_session.add(ex); db_session.commit()
        report = validate_project_coverage(db_session, test_project.id)
        assert all(o.req_id != r.id for o in report.orphans)
        assert report.summary["L5"].ok == 1

    def test_L5_with_uncosigned_exception_is_warning(
        self, db_session, test_project, test_user,
    ):
        r = _make_req(db_session, test_project, test_user, req_id="FR-L5w", level="L5")
        ex = CoverageException(
            project_id=test_project.id,
            requirement_id=r.id,
            reason="Pending admin review.",
            is_active=True,
            created_by_id=test_user.id,
            approved_by_id=None,
        )
        db_session.add(ex); db_session.commit()
        report = validate_project_coverage(db_session, test_project.id)
        orphan = next(o for o in report.orphans if o.req_id == r.id)
        assert orphan.severity == "warning"
        assert orphan.has_active_exception is True

    def test_L5_with_expired_exception_is_error(
        self, db_session, test_project, test_user,
    ):
        r = _make_req(db_session, test_project, test_user, req_id="FR-L5e", level="L5")
        ex = CoverageException(
            project_id=test_project.id,
            requirement_id=r.id,
            reason="Expired exception.",
            is_active=True,
            created_by_id=test_user.id,
            approved_by_id=test_user.id,
            approved_at=datetime.now(timezone.utc) - timedelta(days=10),
            expires_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
        db_session.add(ex); db_session.commit()
        report = validate_project_coverage(db_session, test_project.id)
        orphan = next(o for o in report.orphans if o.req_id == r.id)
        assert orphan.severity == "error"

    def test_direct_source_link_makes_any_level_ok(
        self, db_session, test_project, test_user,
    ):
        for level in ["L2", "L3", "L4", "L5"]:
            r = _make_req(
                db_session, test_project, test_user,
                req_id=f"FR-{level}d", level=level,
            )
            _add_source_link(db_session, r)
        report = validate_project_coverage(db_session, test_project.id)
        for level in ["L2", "L3", "L4", "L5"]:
            assert report.summary[level].ok == 1
            assert report.summary[level].error == 0


# ══════════════════════════════════════════════════════════════
#  Suggestion engine
# ══════════════════════════════════════════════════════════════

class TestSuggestionEngine:

    def test_voltage_keyword_returns_pin(self, db_session, test_project, test_user):
        r = _make_req(
            db_session, test_project, test_user, req_id="FR-V", level="L3",
            statement="The unit shall accept 5V supply voltage at the input pin.",
        )
        result = suggest_source_type(r)
        assert result == SourceEntityType.PIN

    def test_data_rate_returns_wire(self, db_session, test_project, test_user):
        r = _make_req(
            db_session, test_project, test_user, req_id="FR-DR", level="L3",
            statement="The bus shall sustain a data rate of 1 Mbps under load.",
        )
        # 'data rate' matches first → WIRE
        assert suggest_source_type(r) == SourceEntityType.WIRE

    def test_temperature_returns_unit_env_spec(self, db_session, test_project, test_user):
        r = _make_req(
            db_session, test_project, test_user, req_id="FR-T", level="L3",
            statement="The unit shall operate over the range -40C to +85C ambient temperature.",
        )
        assert suggest_source_type(r) == SourceEntityType.UNIT_ENV_SPEC

    def test_pin_assignment_returns_pin(self, db_session, test_project, test_user):
        r = _make_req(
            db_session, test_project, test_user, req_id="FR-PA", level="L3",
            statement="The harness shall implement the pin assignment defined in Table 3.",
        )
        assert suggest_source_type(r) == SourceEntityType.PIN

    def test_no_pattern_returns_none(self, db_session, test_project, test_user):
        r = _make_req(
            db_session, test_project, test_user, req_id="FR-X", level="L3",
            statement="The system shall comply with regulatory requirements.",
        )
        assert suggest_source_type(r) is None


# ══════════════════════════════════════════════════════════════
#  HTTP — RBAC and project membership
# ══════════════════════════════════════════════════════════════

class TestRouterRBAC:
    """Integration tests against the FastAPI router."""

    def test_stakeholder_cannot_file_exception(
        self, client, db_session, test_project, test_user, test_requirement,
    ):
        sh, headers = make_user(
            db_session, "stakeholder", username="sh1", project=test_project,
        )
        body = {
            "project_id": test_project.id,
            "requirement_id": test_requirement.id,
            "reason": "Stakeholder filing test.",
        }
        r = client.post("/api/v1/coverage/exception", json=body, headers=headers)
        assert r.status_code == 403, r.text

    def test_proj_mgr_can_file_exception(
        self, client, db_session, test_project, test_user, test_requirement,
    ):
        pm, headers = make_user(
            db_session, "project_manager", username="pm1", project=test_project,
        )
        body = {
            "project_id": test_project.id,
            "requirement_id": test_requirement.id,
            "reason": "Filed by PM.",
        }
        r = client.post("/api/v1/coverage/exception", json=body, headers=headers)
        assert r.status_code == 201, r.text
        assert r.json()["approved_by_id"] is None        # not yet cosigned
        assert r.json()["is_active"] is True

    def test_non_admin_cannot_cosign(
        self, client, db_session, test_project, test_user, test_requirement,
    ):
        # File the exception first via direct DB to skip the proj-mgr step.
        ex = CoverageException(
            project_id=test_project.id,
            requirement_id=test_requirement.id,
            reason="x",
            is_active=True,
            created_by_id=test_user.id,
        )
        db_session.add(ex); db_session.commit(); db_session.refresh(ex)

        pm, headers = make_user(
            db_session, "project_manager", username="pm2", project=test_project,
        )
        r = client.post(
            f"/api/v1/coverage/exceptions/{ex.id}/cosign",
            headers=headers,
        )
        assert r.status_code == 403

    def test_admin_can_cosign(
        self, client, db_session, test_project, test_user, test_requirement,
        auth_headers,
    ):
        ex = CoverageException(
            project_id=test_project.id,
            requirement_id=test_requirement.id,
            reason="x",
            is_active=True,
            created_by_id=test_user.id,
        )
        db_session.add(ex); db_session.commit(); db_session.refresh(ex)
        r = client.post(
            f"/api/v1/coverage/exceptions/{ex.id}/cosign",
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["approved_by_id"] is not None


# ══════════════════════════════════════════════════════════════
#  HTTP — Project membership enforcement
# ══════════════════════════════════════════════════════════════

class TestProjectMembership:

    def test_non_member_blocked_from_coverage_report(
        self, client, db_session, test_user,
    ):
        # Two projects: A (test_user owns, ProjectAlpha) and B (other_user owns).
        proj_a = Project(
            code="PRJ-A", name="A", owner_id=test_user.id, status="active",
        )
        db_session.add(proj_a); db_session.commit(); db_session.refresh(proj_a)
        db_session.add(ProjectMember(
            project_id=proj_a.id, user_id=test_user.id, added_by_id=test_user.id,
        ))
        db_session.commit()

        # other_user is not a member of proj_a (and is also not admin).
        other, headers = make_user(
            db_session, "requirements_engineer", username="otheruser",
            project=None,
        )
        r = client.get(
            f"/api/v1/coverage/source/{proj_a.id}", headers=headers,
        )
        assert r.status_code == 403


# ══════════════════════════════════════════════════════════════
#  HTTP — happy path
# ══════════════════════════════════════════════════════════════

class TestRouterHappyPath:

    def test_coverage_report_summary_shape(
        self, client, db_session, test_project, test_user, auth_headers,
    ):
        # One req per level — predictable totals.
        for lvl in ["L1", "L2", "L3", "L4", "L5"]:
            _make_req(
                db_session, test_project, test_user,
                req_id=f"FR-{lvl}-S", level=lvl,
            )
        r = client.get(
            f"/api/v1/coverage/source/{test_project.id}",
            headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["project_id"] == test_project.id
        # L1 → ok, L2 → warning, L3 → error, L4 → error, L5 → error
        assert body["summary"]["L1"]["ok"] == 1
        assert body["summary"]["L2"]["warning"] == 1
        assert body["summary"]["L3"]["error"] == 1
        assert body["summary"]["L4"]["error"] == 1
        assert body["summary"]["L5"]["error"] == 1

    def test_orphan_endpoint_filters_severity(
        self, client, db_session, test_project, test_user, auth_headers,
    ):
        _make_req(db_session, test_project, test_user, req_id="W1", level="L2")  # warning
        _make_req(db_session, test_project, test_user, req_id="E1", level="L3")  # error
        # Default (no severity filter) returns both warning + error orphans.
        r = client.get(
            f"/api/v1/coverage/source/{test_project.id}/orphans",
            headers=auth_headers,
        )
        assert r.status_code == 200
        assert r.json()["total"] == 2
        # Filtered to error only.
        r2 = client.get(
            f"/api/v1/coverage/source/{test_project.id}/orphans?severity=error",
            headers=auth_headers,
        )
        assert r2.status_code == 200
        assert r2.json()["total"] == 1
        assert r2.json()["items"][0]["severity"] == "error"

    def test_filing_then_cosigning_flips_severity_to_ok(
        self, client, db_session, test_project, test_user, auth_headers,
    ):
        l5 = _make_req(
            db_session, test_project, test_user, req_id="FR-L5flip", level="L5",
        )
        # File via the proj-mgr (admin can also file — auth_headers IS admin).
        body = {
            "project_id": test_project.id,
            "requirement_id": l5.id,
            "reason": "Manually verified by chief engineer.",
        }
        f = client.post("/api/v1/coverage/exception", json=body, headers=auth_headers)
        assert f.status_code == 201
        ex_id = f.json()["id"]
        # Pre-cosign: severity should be 'warning'.
        rep = client.get(
            f"/api/v1/coverage/source/{test_project.id}", headers=auth_headers,
        ).json()
        assert rep["summary"]["L5"]["warning"] == 1

        # Cosign — admin can.
        c = client.post(
            f"/api/v1/coverage/exceptions/{ex_id}/cosign", headers=auth_headers,
        )
        assert c.status_code == 200, c.text
        # Post-cosign: severity flips to ok.
        rep2 = client.get(
            f"/api/v1/coverage/source/{test_project.id}", headers=auth_headers,
        ).json()
        assert rep2["summary"]["L5"]["ok"] == 1
        assert rep2["summary"]["L5"]["warning"] == 0


# ══════════════════════════════════════════════════════════════
#  Bulk-accept hook → MV refresh
# ══════════════════════════════════════════════════════════════

class TestBulkAcceptRefreshHook:
    """Spec calls for ONE refresh per batch, not N. We monkeypatch the refresh
    function and assert call count after a bulk-accept of multiple proposals.
    """

    def test_single_refresh_per_batch(
        self, client, db_session, test_project, test_user, auth_headers,
        monkeypatch,
    ):
        from app.services.req_sync import fan_out_for_entity
        from app.services.coverage import refresh as refresh_mod

        # Build two minimal source-linked requirements + two pending proposals.
        from app.models.req_sync import (
            RequirementSyncProposal, SyncProposalType, SyncProposalStatus,
        )

        r1 = _make_req(
            db_session, test_project, test_user,
            req_id="FR-B1", level="L3", status="approved",
            statement="Old statement 1.",
        )
        r2 = _make_req(
            db_session, test_project, test_user,
            req_id="FR-B2", level="L3", status="approved",
            statement="Old statement 2.",
        )
        for r in (r1, r2):
            p = RequirementSyncProposal(
                requirement_id=r.id,
                triggered_by_entity_type=SourceEntityType.SYSTEM,
                triggered_by_entity_id=1,
                trigger_event="update",
                proposal_type=SyncProposalType.UPDATE_STATEMENT,
                old_statement=r.statement,
                new_statement="New statement.",
                old_rationale=None,
                new_rationale=None,
                field_diffs={},
                status=SyncProposalStatus.PENDING,
            )
            db_session.add(p)
        db_session.commit()

        proposal_ids = [
            p.id for p in db_session.query(RequirementSyncProposal).all()
        ]

        call_count = {"n": 0}

        def _spy(*args, **kw):
            call_count["n"] += 1
            return False

        monkeypatch.setattr(refresh_mod, "refresh_coverage_mv", _spy)
        # The router imports refresh_coverage_mv lazily inside the handler, so
        # we also need to patch the module-level name where it'll be looked up.
        from app.services.coverage import refresh as _refresh_pkg
        monkeypatch.setattr(_refresh_pkg, "refresh_coverage_mv", _spy)

        body = {"proposal_ids": proposal_ids}
        r = client.post(
            "/api/v1/req-sync/proposals/bulk-accept",
            json=body, headers=auth_headers,
        )
        assert r.status_code == 200, r.text
        assert r.json()["succeeded"] == len(proposal_ids)
        # ONE refresh per batch — not one per proposal.
        assert call_count["n"] == 1, (
            f"Expected exactly 1 MV refresh per batch, got {call_count['n']}"
        )
