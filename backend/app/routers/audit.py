"""
ASTRA — Audit Log Router
==========================
File: backend/app/routers/audit.py   ← NEW

Provides read-only access to the tamper-evident audit log.
Verify endpoint walks the hash chain and reports any integrity issues.
"""

import csv
import io
import json
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, UserRole
from app.services.auth import get_current_user
from app.services.audit_service import query_audit_log, verify_chain_integrity
from app.models.audit_log import AuditLog

# Only admins and PMs can access the full audit log
try:
    from app.services.rbac import require_any_role
    _audit_dep = require_any_role(UserRole.ADMIN, UserRole.PROJECT_MANAGER)
except ImportError:
    _audit_dep = get_current_user

router = APIRouter(prefix="/audit", tags=["Audit Log"])


# ══════════════════════════════════════
#  Paginated log
# ══════════════════════════════════════

@router.get("/log")
def get_audit_log(
    project_id: Optional[int] = None,
    user_id: Optional[int] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[int] = None,
    event_type: Optional[str] = None,
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(_audit_dep),
):
    """Paginated audit log with filters."""
    df = datetime.fromisoformat(date_from) if date_from else None
    dt = datetime.fromisoformat(date_to) if date_to else None

    return query_audit_log(
        db,
        project_id=project_id,
        user_id=user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        date_from=df,
        date_to=dt,
        skip=skip,
        limit=limit,
    )


# ══════════════════════════════════════
#  Entity trail
# ══════════════════════════════════════

@router.get("/log/entity/{entity_type}/{entity_id}")
def get_entity_audit_trail(
    entity_type: str,
    entity_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Full audit trail for a specific entity (any authenticated user)."""
    return query_audit_log(
        db, entity_type=entity_type, entity_id=entity_id,
        skip=skip, limit=limit,
    )


# ══════════════════════════════════════
#  Chain verification
# ══════════════════════════════════════

@router.get("/verify")
def verify_integrity(
    project_id: Optional[int] = None,
    start_seq: Optional[int] = None,
    end_seq: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(_audit_dep),
):
    """
    Walk the hash chain and verify cryptographic integrity.
    Returns ``is_valid: true`` if no tampering detected.
    """
    return verify_chain_integrity(
        db,
        project_id=project_id,
        start_seq=start_seq,
        end_seq=end_seq,
    )


# ══════════════════════════════════════
#  Export
# ══════════════════════════════════════

@router.get("/export")
def export_audit_log(
    project_id: Optional[int] = None,
    format: str = Query("json", regex="^(json|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_audit_dep),
):
    """Export the full audit log as JSON or CSV for compliance delivery."""
    records = (
        db.query(AuditLog)
        .filter(AuditLog.project_id == project_id if project_id else True)
        .order_by(AuditLog.sequence_number.asc())
        .all()
    )

    rows = []
    for r in records:
        rows.append({
            "sequence_number": r.sequence_number,
            "timestamp": r.timestamp.isoformat() if r.timestamp else "",
            "event_type": r.event_type,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "project_id": r.project_id,
            "user_id": r.user_id,
            "username": r.user.username if r.user else "",
            "user_ip": r.user_ip or "",
            "action_detail": json.dumps(r.action_detail or {}, default=str),
            "previous_hash": r.previous_hash,
            "record_hash": r.record_hash,
        })

    if format == "csv":
        if not rows:
            return StreamingResponse(io.StringIO(""), media_type="text/csv")
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        buf.seek(0)
        return StreamingResponse(
            buf,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=astra_audit_log.csv"},
        )

    # JSON
    return {
        "exported_at": datetime.utcnow().isoformat(),
        "total": len(rows),
        "records": rows,
    }
