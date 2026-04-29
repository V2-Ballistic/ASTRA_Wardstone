"""
ASTRA — Webhook signature verification tests (F-017)
=====================================================
File: backend/tests/test_webhooks.py

POST /api/v1/integrations/{config_id}/jira/webhook   — HMAC-SHA256
POST /api/v1/integrations/{config_id}/azure/webhook  — Basic Auth secret

Each webhook is verified against the per-config `webhook_secret` stored
inside the encrypted config blob. All failure paths return a generic
401 to prevent config enumeration.
"""

import base64
import hashlib
import hmac
import json

import pytest

from app.models import Project, User
from app.models.integration import IntegrationConfig, SyncLog
from app.models.project_member import ProjectMember
from app.services.auth import create_access_token, get_password_hash
from app.services.encryption import encrypt_field


WEBHOOK_SECRET = "shared-webhook-secret-32chars-min-aaaaaa"


def _make_user(db_session, username, role="project_manager"):
    u = User(
        username=username, email=f"{username}@example.com",
        hashed_password=get_password_hash("TestPass123"),
        full_name=username.title(),
        role=role, department="Eng", is_active=True,
    )
    db_session.add(u); db_session.commit(); db_session.refresh(u)
    return u


def _make_project_with_owner(db_session, owner: User, code="WHK"):
    p = Project(code=code, name="Webhook Project", owner_id=owner.id, status="active")
    db_session.add(p); db_session.commit(); db_session.refresh(p)
    db_session.add(ProjectMember(project_id=p.id, user_id=owner.id, added_by_id=owner.id))
    db_session.commit()
    return p


def _make_integration(db_session, project: Project, owner: User, *,
                      integration_type: str, webhook_secret: str | None) -> IntegrationConfig:
    config = {"url": "https://example.com", "api_token": "irrelevant"}
    if webhook_secret is not None:
        config["webhook_secret"] = webhook_secret
    ic = IntegrationConfig(
        project_id=project.id,
        integration_type=integration_type,
        display_name=f"{integration_type} test",
        config_encrypted=encrypt_field(json.dumps(config)),
        field_mapping={},
        sync_direction="import",
        is_active=True,
        created_by_id=owner.id,
    )
    db_session.add(ic); db_session.commit(); db_session.refresh(ic)
    return ic


def _jira_signature(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256,
    ).hexdigest()


def _azure_basic(secret: str, user: str = "astra") -> str:
    return "Basic " + base64.b64encode(f"{user}:{secret}".encode("utf-8")).decode("ascii")


# ══════════════════════════════════════
#  Jira
# ══════════════════════════════════════


class TestJiraWebhook:

    def test_unsigned_returns_401_no_db_write(self, client, db_session):
        owner = _make_user(db_session, "owner_jira1")
        project = _make_project_with_owner(db_session, owner, code="WJ1")
        ic = _make_integration(db_session, project, owner,
                               integration_type="jira",
                               webhook_secret=WEBHOOK_SECRET)
        before_logs = db_session.query(SyncLog).count()

        r = client.post(
            f"/api/v1/integrations/{ic.id}/jira/webhook",
            json={"event": "test"},
        )
        assert r.status_code == 401, r.text

        after_logs = db_session.query(SyncLog).count()
        assert after_logs == before_logs, (
            "401 must reject BEFORE any SyncLog write"
        )

    def test_wrong_signature_returns_401(self, client, db_session):
        owner = _make_user(db_session, "owner_jira2")
        project = _make_project_with_owner(db_session, owner, code="WJ2")
        ic = _make_integration(db_session, project, owner,
                               integration_type="jira",
                               webhook_secret=WEBHOOK_SECRET)
        body = json.dumps({"event": "test"}).encode("utf-8")
        wrong_sig = _jira_signature("the-wrong-secret", body)

        r = client.post(
            f"/api/v1/integrations/{ic.id}/jira/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": wrong_sig,
            },
        )
        assert r.status_code == 401, r.text

    def test_correct_signature_returns_200_and_writes_log(self, client, db_session):
        owner = _make_user(db_session, "owner_jira3")
        project = _make_project_with_owner(db_session, owner, code="WJ3")
        ic = _make_integration(db_session, project, owner,
                               integration_type="jira",
                               webhook_secret=WEBHOOK_SECRET)
        body = json.dumps({"event": "test"}).encode("utf-8")
        sig = _jira_signature(WEBHOOK_SECRET, body)

        before_logs = db_session.query(SyncLog).filter(
            SyncLog.integration_config_id == ic.id,
        ).count()

        r = client.post(
            f"/api/v1/integrations/{ic.id}/jira/webhook",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Webhook-Signature": sig,
            },
        )
        assert r.status_code == 200, r.text

        after_logs = db_session.query(SyncLog).filter(
            SyncLog.integration_config_id == ic.id,
        ).count()
        assert after_logs == before_logs + 1, (
            f"Successful webhook must write exactly one SyncLog row "
            f"to integration_config_id={ic.id} (was {before_logs}, now {after_logs})"
        )

    def test_missing_config_returns_401_not_404(self, client):
        """Enumeration-resistance: unknown config_id returns the same 401."""
        r = client.post(
            "/api/v1/integrations/999999/jira/webhook",
            json={"event": "test"},
            headers={"X-Webhook-Signature": "sha256=deadbeef"},
        )
        assert r.status_code == 401

    def test_wrong_integration_type_returns_401(self, client, db_session):
        """Posting to /jira/webhook on an azure_devops config returns 401."""
        owner = _make_user(db_session, "owner_jira4")
        project = _make_project_with_owner(db_session, owner, code="WJ4")
        ic = _make_integration(db_session, project, owner,
                               integration_type="azure_devops",
                               webhook_secret=WEBHOOK_SECRET)
        body = json.dumps({"event": "test"}).encode("utf-8")
        sig = _jira_signature(WEBHOOK_SECRET, body)

        r = client.post(
            f"/api/v1/integrations/{ic.id}/jira/webhook",
            content=body,
            headers={"X-Webhook-Signature": sig},
        )
        assert r.status_code == 401

    def test_no_webhook_secret_configured_returns_401(self, client, db_session):
        """Config with no webhook_secret means webhooks are disabled → 401."""
        owner = _make_user(db_session, "owner_jira5")
        project = _make_project_with_owner(db_session, owner, code="WJ5")
        ic = _make_integration(db_session, project, owner,
                               integration_type="jira",
                               webhook_secret=None)

        r = client.post(
            f"/api/v1/integrations/{ic.id}/jira/webhook",
            json={"event": "test"},
            headers={"X-Webhook-Signature": "sha256=abc"},
        )
        assert r.status_code == 401


# ══════════════════════════════════════
#  Azure DevOps
# ══════════════════════════════════════


class TestAzureWebhook:

    def test_unsigned_returns_401_no_db_write(self, client, db_session):
        owner = _make_user(db_session, "owner_az1")
        project = _make_project_with_owner(db_session, owner, code="WA1")
        ic = _make_integration(db_session, project, owner,
                               integration_type="azure_devops",
                               webhook_secret=WEBHOOK_SECRET)
        before_logs = db_session.query(SyncLog).count()

        r = client.post(
            f"/api/v1/integrations/{ic.id}/azure/webhook",
            json={"eventType": "workitem.created"},
        )
        assert r.status_code == 401, r.text

        after_logs = db_session.query(SyncLog).count()
        assert after_logs == before_logs

    def test_wrong_basic_secret_returns_401(self, client, db_session):
        owner = _make_user(db_session, "owner_az2")
        project = _make_project_with_owner(db_session, owner, code="WA2")
        ic = _make_integration(db_session, project, owner,
                               integration_type="azure_devops",
                               webhook_secret=WEBHOOK_SECRET)
        bad = _azure_basic("the-wrong-secret")

        r = client.post(
            f"/api/v1/integrations/{ic.id}/azure/webhook",
            json={"eventType": "workitem.created"},
            headers={"Authorization": bad},
        )
        assert r.status_code == 401

    def test_correct_basic_secret_returns_200(self, client, db_session):
        owner = _make_user(db_session, "owner_az3")
        project = _make_project_with_owner(db_session, owner, code="WA3")
        ic = _make_integration(db_session, project, owner,
                               integration_type="azure_devops",
                               webhook_secret=WEBHOOK_SECRET)
        good = _azure_basic(WEBHOOK_SECRET)

        before_logs = db_session.query(SyncLog).filter(
            SyncLog.integration_config_id == ic.id,
        ).count()

        r = client.post(
            f"/api/v1/integrations/{ic.id}/azure/webhook",
            json={"eventType": "workitem.created"},
            headers={"Authorization": good},
        )
        assert r.status_code == 200, r.text

        after_logs = db_session.query(SyncLog).filter(
            SyncLog.integration_config_id == ic.id,
        ).count()
        assert after_logs == before_logs + 1

    def test_non_basic_auth_header_returns_401(self, client, db_session):
        owner = _make_user(db_session, "owner_az4")
        project = _make_project_with_owner(db_session, owner, code="WA4")
        ic = _make_integration(db_session, project, owner,
                               integration_type="azure_devops",
                               webhook_secret=WEBHOOK_SECRET)
        # Bearer instead of Basic
        r = client.post(
            f"/api/v1/integrations/{ic.id}/azure/webhook",
            json={"eventType": "x"},
            headers={"Authorization": f"Bearer {WEBHOOK_SECRET}"},
        )
        assert r.status_code == 401
