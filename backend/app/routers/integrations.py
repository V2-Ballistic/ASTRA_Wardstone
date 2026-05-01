"""
ASTRA — Integrations Router
==============================
File: backend/app/routers/integrations.py   ← NEW

CRUD for integration configs, manual sync triggers, sync history,
and webhook receivers for Jira and Azure DevOps.
"""

import base64
import hashlib
import hmac
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.project_access import (
    _check_membership,
    project_member_required,
)
from app.models import Project, User, UserRole
from app.models.integration import IntegrationConfig, SyncLog
from app.services.auth import get_current_user
from app.services.integrations import CONNECTOR_REGISTRY

# Encryption — use if available, fall back to plaintext for dev
try:
    from app.services.encryption import encrypt_field, decrypt_field
except ImportError:
    def encrypt_field(v):
        return v
    def decrypt_field(v):
        return v

# Audit
try:
    from app.services.audit_service import record_event as _audit
except ImportError:
    def _audit(*a, **kw):
        pass

try:
    from app.services.rbac import require_any_role
except ImportError:
    def require_any_role(*roles):
        return get_current_user


router = APIRouter(prefix="/integrations", tags=["Integrations"])


# ══════════════════════════════════════
#  Schemas
# ══════════════════════════════════════

class IntegrationCreate(BaseModel):
    project_id: int
    integration_type: str = Field(..., pattern="^(jira|azure_devops|doors)$")
    display_name: str = ""
    config: dict = Field(default_factory=dict)        # raw connection config (will be encrypted)
    field_mapping: dict = Field(default_factory=dict)
    external_project: str = ""
    sync_direction: str = Field("import", pattern="^(import|export|bidirectional)$")
    sync_schedule: str = ""

class IntegrationUpdate(BaseModel):
    display_name: Optional[str] = None
    config: Optional[dict] = None       # if provided, re-encrypts
    field_mapping: Optional[dict] = None
    external_project: Optional[str] = None
    sync_direction: Optional[str] = None
    sync_schedule: Optional[str] = None
    is_active: Optional[bool] = None


# ══════════════════════════════════════
#  Helpers
# ══════════════════════════════════════

def _decrypt_config(ic: IntegrationConfig) -> dict:
    """Decrypt the stored config JSON."""
    raw = decrypt_field(ic.config_encrypted) if ic.config_encrypted else "{}"
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _get_connector(ic: IntegrationConfig):
    """Instantiate the correct connector from a config record."""
    cls = CONNECTOR_REGISTRY.get(ic.integration_type)
    if not cls:
        raise HTTPException(400, f"Unknown integration type: {ic.integration_type}")
    config = _decrypt_config(ic)
    config["field_mapping"] = ic.field_mapping or {}
    return cls(config)


# ══════════════════════════════════════
#  Webhook auth helpers (AUDIT_FINDINGS F-017)
# ══════════════════════════════════════
#
# Webhook secrets live inside the encrypted config blob under the key
# ``webhook_secret`` so we don't need a schema migration. Set it the
# same way you set any other connector field:
#
#     POST /api/v1/integrations/
#     {
#       "project_id": 1,
#       "integration_type": "jira",
#       "config": {"url": "...", "api_token": "...", "webhook_secret": "..."}
#     }
#
# Webhook providers should be configured to deliver events to:
#
#   POST /api/v1/integrations/{config_id}/jira/webhook
#       header: X-Webhook-Signature: sha256=<hmac-sha256(secret, raw_body)>
#
#   POST /api/v1/integrations/{config_id}/azure/webhook
#       header: Authorization: Basic <base64("anything:<webhook_secret>")>
#       (Azure DevOps Service Hooks call this "Basic Auth username/password".
#        We ignore the username and only compare the password.)


def _load_webhook_config(
    db: Session, config_id: int, expected_type: str,
) -> tuple[IntegrationConfig, str]:
    """
    Load an IntegrationConfig + return its decrypted webhook_secret.

    Raises 401 if the config is missing, the integration_type doesn't
    match, the config is inactive, or no webhook_secret is configured —
    all four cases return 401 with the SAME message so the caller can't
    enumerate which configs exist or which have webhook auth disabled.
    """
    generic_401 = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Webhook authentication failed",
    )

    ic = db.query(IntegrationConfig).filter(
        IntegrationConfig.id == config_id,
    ).first()
    if not ic or ic.integration_type != expected_type or not ic.is_active:
        raise generic_401

    cfg = _decrypt_config(ic)
    secret = cfg.get("webhook_secret") or ""
    if not secret:
        raise generic_401
    return ic, secret


def _verify_jira_signature(raw_body: bytes, secret: str, header: str | None) -> bool:
    """
    Validate `X-Webhook-Signature: sha256=<hex>` against
    HMAC-SHA256(secret, raw_body). Constant-time comparison.
    """
    if not header or not header.startswith("sha256="):
        return False
    provided = header.split("=", 1)[1].strip().lower()
    expected = hmac.new(
        secret.encode("utf-8"), raw_body, hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(provided, expected)


def _verify_azure_basic(secret: str, header: str | None) -> bool:
    """
    Validate `Authorization: Basic <base64(user:pass)>` where the
    decoded password matches the configured webhook_secret. Username
    is ignored. Constant-time comparison.
    """
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        encoded = header.split(" ", 1)[1].strip()
        decoded = base64.b64decode(encoded).decode("utf-8", errors="strict")
    except (ValueError, UnicodeDecodeError):
        return False
    if ":" not in decoded:
        return False
    _, _, provided = decoded.partition(":")
    return hmac.compare_digest(provided, secret)


def _config_to_dict(ic: IntegrationConfig, hide_secrets: bool = True) -> dict:
    """Serialise a config record for API responses."""
    d = {
        "id": ic.id,
        "project_id": ic.project_id,
        "integration_type": ic.integration_type,
        "display_name": ic.display_name,
        "external_project": ic.external_project,
        "field_mapping": ic.field_mapping,
        "sync_direction": ic.sync_direction,
        "sync_schedule": ic.sync_schedule,
        "last_sync_at": ic.last_sync_at.isoformat() if ic.last_sync_at else None,
        "is_active": ic.is_active,
        "created_at": ic.created_at.isoformat() if ic.created_at else None,
    }
    if not hide_secrets:
        d["config"] = _decrypt_config(ic)
    else:
        # Show which keys are configured without revealing values
        cfg = _decrypt_config(ic)
        d["config_keys"] = list(cfg.keys())
    return d


def _log_to_dict(log: SyncLog) -> dict:
    user = log.triggered_by
    return {
        "id": log.id,
        "direction": log.direction,
        "status": log.status,
        "created_count": log.created_count,
        "updated_count": log.updated_count,
        "skipped_count": log.skipped_count,
        "error_count": log.error_count,
        "details": log.details,
        "triggered_by": user.full_name if user else "System",
        "started_at": log.started_at.isoformat() if log.started_at else None,
        "completed_at": log.completed_at.isoformat() if log.completed_at else None,
    }


# ══════════════════════════════════════
#  CRUD
# ══════════════════════════════════════

@router.get("/")
def list_integrations(
    project_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    project: Project = Depends(project_member_required),
):
    configs = db.query(IntegrationConfig).filter(
        IntegrationConfig.project_id == project_id,
    ).order_by(IntegrationConfig.created_at.desc()).all()
    return [_config_to_dict(c) for c in configs]


@router.post("/", status_code=201)
def create_integration(
    data: IntegrationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
):
    # AUDIT_FINDINGS F-014: scope role check to actual project membership
    # so a global PM can't create integrations (with stored credentials)
    # for projects they don't belong to.
    _check_membership(db, data.project_id, current_user)
    encrypted = encrypt_field(json.dumps(data.config))
    ic = IntegrationConfig(
        project_id=data.project_id,
        integration_type=data.integration_type,
        display_name=data.display_name or f"{data.integration_type.title()} Integration",
        config_encrypted=encrypted,
        field_mapping=data.field_mapping or {
            "title": "title", "description": "statement",
            "priority": "priority", "status": "status", "type": "req_type",
        },
        external_project=data.external_project,
        sync_direction=data.sync_direction,
        sync_schedule=data.sync_schedule,
        created_by_id=current_user.id,
    )
    db.add(ic)
    db.commit()
    db.refresh(ic)

    _audit(db, "integration.created", "integration", ic.id, current_user.id,
           {"type": ic.integration_type, "project_id": ic.project_id},
           project_id=ic.project_id)
    return _config_to_dict(ic)


@router.get("/{config_id}")
def get_integration(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ic = db.query(IntegrationConfig).filter(IntegrationConfig.id == config_id).first()
    if not ic:
        raise HTTPException(404, "Integration config not found")
    _check_membership(db, ic.project_id, current_user)
    return _config_to_dict(ic)


@router.patch("/{config_id}")
def update_integration(
    config_id: int,
    data: IntegrationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
):
    ic = db.query(IntegrationConfig).filter(IntegrationConfig.id == config_id).first()
    if not ic:
        raise HTTPException(404, "Integration config not found")
    _check_membership(db, ic.project_id, current_user)

    update = data.model_dump(exclude_unset=True)
    if "config" in update and update["config"] is not None:
        ic.config_encrypted = encrypt_field(json.dumps(update.pop("config")))
    for field, val in update.items():
        setattr(ic, field, val)
    db.commit()
    db.refresh(ic)
    return _config_to_dict(ic)


@router.delete("/{config_id}", status_code=200)
def delete_integration(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)),
):
    ic = db.query(IntegrationConfig).filter(IntegrationConfig.id == config_id).first()
    if not ic:
        raise HTTPException(404, "Integration config not found")
    _check_membership(db, ic.project_id, current_user)
    db.delete(ic)
    db.commit()
    return {"status": "deleted", "id": config_id}


# ══════════════════════════════════════
#  Test Connection
# ══════════════════════════════════════

@router.post("/{config_id}/test")
def test_integration(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ic = db.query(IntegrationConfig).filter(IntegrationConfig.id == config_id).first()
    if not ic:
        raise HTTPException(404, "Integration config not found")
    _check_membership(db, ic.project_id, current_user)

    connector = _get_connector(ic)
    success = connector.test_connection()
    return {"success": success, "integration_type": ic.integration_type}


@router.get("/{config_id}/projects")
def list_external_projects(
    config_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ic = db.query(IntegrationConfig).filter(IntegrationConfig.id == config_id).first()
    if not ic:
        raise HTTPException(404, "Integration config not found")
    _check_membership(db, ic.project_id, current_user)
    connector = _get_connector(ic)
    return connector.get_available_projects()


# ══════════════════════════════════════
#  Manual Sync
# ══════════════════════════════════════

@router.post("/{config_id}/sync")
def trigger_sync(
    config_id: int,
    direction: str = Query("import", pattern="^(import|export)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ic = db.query(IntegrationConfig).filter(IntegrationConfig.id == config_id).first()
    if not ic:
        raise HTTPException(404, "Integration config not found")
    _check_membership(db, ic.project_id, current_user)
    if not ic.is_active:
        raise HTTPException(400, "Integration is inactive")

    connector = _get_connector(ic)

    # Create sync log
    log = SyncLog(
        integration_config_id=ic.id,
        direction=direction,
        status="running",
        triggered_by_id=current_user.id,
    )
    db.add(log)
    db.commit()
    db.refresh(log)

    # F-057: connector call inside a SAVEPOINT. If it raises, only
    # the connector's partial inserts roll back — the SyncLog row
    # (created above and committed) survives, so the failure is
    # visible in /sync/logs. Pre-fix the connector's writes
    # accumulated in the outer transaction; the catch-all `except`
    # then committed `last_sync_at = now` AND every partially-added
    # ORM object together. A "failed" sync could leave half-imported
    # requirements behind.
    sp = db.begin_nested()
    try:
        if direction == "import":
            result = connector.sync_requirements_from(
                db, ic.project_id, ic.external_project, current_user.id,
            )
        else:
            result = connector.sync_requirements_to(
                db, ic.project_id, ic.external_project, current_user.id,
            )

        sp.commit()  # release SAVEPOINT — connector's writes durable

        log.created_count = result.created
        log.updated_count = result.updated
        log.skipped_count = result.skipped
        log.error_count = len(result.errors)
        log.details = {"errors": result.errors[:50]}
        log.status = "failed" if result.errors and not result.created and not result.updated \
                     else "partial" if result.errors else "success"

    except Exception as exc:
        sp.rollback()  # F-057: discard connector's partial writes
        log.status = "failed"
        log.error_count = 1
        log.details = {"errors": [str(exc)]}

    log.completed_at = datetime.utcnow()
    ic.last_sync_at = datetime.utcnow()
    db.commit()

    _audit(db, f"integration.sync_{direction}", "integration", ic.id,
           current_user.id,
           {"created": log.created_count, "updated": log.updated_count,
            "errors": log.error_count, "status": log.status},
           project_id=ic.project_id)

    return _log_to_dict(log)


# ══════════════════════════════════════
#  Sync Logs
# ══════════════════════════════════════

@router.get("/{config_id}/logs")
def get_sync_logs(
    config_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ic = db.query(IntegrationConfig).filter(IntegrationConfig.id == config_id).first()
    if not ic:
        raise HTTPException(404, "Integration config not found")
    _check_membership(db, ic.project_id, current_user)

    logs = (
        db.query(SyncLog)
        .filter(SyncLog.integration_config_id == config_id)
        .order_by(SyncLog.started_at.desc())
        .offset(skip).limit(limit)
        .all()
    )
    total = db.query(SyncLog).filter(
        SyncLog.integration_config_id == config_id
    ).count()
    return {"total": total, "items": [_log_to_dict(l) for l in logs]}


# ══════════════════════════════════════
#  Webhooks
# ══════════════════════════════════════

@router.post("/{config_id}/jira/webhook")
async def jira_webhook(
    config_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receive Jira webhook events for a specific IntegrationConfig.

    AUDIT_FINDINGS F-017:
      - integration_config_id is now resolved from the URL path, not
        hardcoded to 0.
      - HMAC-SHA256 signature in the `X-Webhook-Signature: sha256=...`
        header is validated against the per-config `webhook_secret`
        BEFORE any DB write. 401 on miss.
      - Failure paths return a generic 401 to prevent config enumeration.
    """
    ic, secret = _load_webhook_config(db, config_id, "jira")

    raw_body = await request.body()
    sig_header = request.headers.get("x-webhook-signature")
    if not _verify_jira_signature(raw_body, secret, sig_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook authentication failed",
        )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise HTTPException(400, "Invalid JSON payload")

    from app.services.integrations.jira import JiraConnector
    connector = JiraConnector(_decrypt_config(ic))
    summary = connector.receive_webhook(payload)

    log = SyncLog(
        integration_config_id=ic.id,        # F-017: real id, not 0
        direction="import",
        status="success",
        details={"webhook": summary},
    )
    db.add(log)
    db.commit()

    return {"status": "received", "summary": summary}


@router.post("/{config_id}/azure/webhook")
async def azure_webhook(
    config_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receive Azure DevOps Service Hook events for a specific
    IntegrationConfig.

    AUDIT_FINDINGS F-017:
      - integration_config_id is resolved from the URL path.
      - HTTP Basic Auth password (Azure DevOps's standard webhook
        scheme) is matched against the per-config `webhook_secret`
        BEFORE any DB write. 401 on miss.
    """
    ic, secret = _load_webhook_config(db, config_id, "azure_devops")

    auth_header = request.headers.get("authorization")
    if not _verify_azure_basic(secret, auth_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Webhook authentication failed",
        )

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(400, "Invalid JSON payload")

    from app.services.integrations.azure_devops import AzureDevOpsConnector
    connector = AzureDevOpsConnector(_decrypt_config(ic))
    summary = connector.receive_webhook(payload)

    log = SyncLog(
        integration_config_id=ic.id,
        direction="import",
        status="success",
        details={"webhook": summary},
    )
    db.add(log)
    db.commit()

    return {"status": "received", "summary": summary}


# ══════════════════════════════════════
#  Available Types (for frontend catalog)
# ══════════════════════════════════════

@router.get("/catalog")
def get_integration_catalog(current_user: User = Depends(get_current_user)):
    return [
        {
            "type": "jira",
            "name": "Jira",
            "description": "Atlassian Jira Cloud or Server. Sync epics, stories, and tasks as requirements with bidirectional updates.",
            "config_fields": [
                {"key": "url", "label": "Jira URL", "type": "url", "placeholder": "https://company.atlassian.net"},
                {"key": "email", "label": "Email", "type": "email", "placeholder": "user@company.com"},
                {"key": "api_token", "label": "API Token", "type": "password", "placeholder": "Your Jira API token"},
            ],
            "supports_webhook": True,
            "webhook_url": "/api/v1/integrations/jira/webhook",
        },
        {
            "type": "azure_devops",
            "name": "Azure DevOps",
            "description": "Azure DevOps Services or Server. Map work items (Features, User Stories, Tasks) to ASTRA requirements.",
            "config_fields": [
                {"key": "url", "label": "Organization URL", "type": "url", "placeholder": "https://dev.azure.com/myorg"},
                {"key": "pat", "label": "Personal Access Token", "type": "password", "placeholder": "PAT with Work Items read/write"},
                {"key": "org", "label": "Organization", "type": "text", "placeholder": "myorg"},
            ],
            "supports_webhook": True,
            "webhook_url": "/api/v1/integrations/azure/webhook",
        },
        {
            "type": "doors",
            "name": "IBM DOORS Next",
            "description": "IBM DOORS Next Generation (DNG) via OSLC API. Import modules and objects with preserved attributes and links.",
            "config_fields": [
                {"key": "url", "label": "DOORS Server URL", "type": "url", "placeholder": "https://doors.company.com"},
                {"key": "username", "label": "Username", "type": "text", "placeholder": "DOORS username"},
                {"key": "password", "label": "Password", "type": "password", "placeholder": "DOORS password"},
                {"key": "project_area", "label": "Project Area URI", "type": "text", "placeholder": "Project area resource URI"},
            ],
            "supports_webhook": False,
        },
    ]
