"""
ASTRA — Audit Log Router
==========================
File: backend/app/routers/audit.py   ← NEW

Provides read-only access to the tamper-evident audit log.
Verify endpoint walks the hash chain and reports any integrity issues.
Export endpoint streams from a server-side cursor (F-020) so a
real-world 100k+ row audit log no longer OOMs the worker.
"""

import csv
import io
import json
from datetime import datetime
from typing import Iterator, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.project_access import _check_membership
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
#  Export (F-020 — streaming)
# ══════════════════════════════════════


_EXPORT_FIELDS = (
    "sequence_number", "timestamp", "event_type", "entity_type",
    "entity_id", "project_id", "user_id", "username", "user_ip",
    "action_detail", "previous_hash", "record_hash",
)

# Server-side fetch size for the streaming cursor. Tuned to keep the
# per-yield batch small enough that we never materialise more than this
# many rows at once, while keeping per-row overhead amortised.
_STREAM_CHUNK = 500


def _row_to_dict(r: AuditLog) -> dict:
    return {
        "sequence_number": r.sequence_number,
        "timestamp": r.timestamp.isoformat() if r.timestamp else "",
        "event_type": r.event_type,
        "entity_type": r.entity_type,
        "entity_id": r.entity_id,
        "project_id": r.project_id,
        "user_id": r.user_id,
        "username": r.user.username if r.user else "",
        "user_ip": r.user_ip or "",
        "action_detail": r.action_detail or {},
        "previous_hash": r.previous_hash,
        "record_hash": r.record_hash,
    }


def _iter_audit_rows(
    db: Session, project_id: Optional[int],
) -> Iterator[AuditLog]:
    """
    Yield AuditLog rows one at a time from a server-side-batched query.

    `yield_per` releases each batch to the consumer before pulling the
    next one — bounded memory regardless of row count.
    """
    q = db.query(AuditLog).order_by(AuditLog.sequence_number.asc())
    if project_id is not None:
        q = q.filter(AuditLog.project_id == project_id)
    yield from q.yield_per(_STREAM_CHUNK)


def _stream_csv(db: Session, project_id: Optional[int]) -> Iterator[bytes]:
    """Generator that yields CSV bytes — header first, then rows."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_EXPORT_FIELDS)
    writer.writeheader()
    yield buf.getvalue().encode("utf-8")
    buf.seek(0); buf.truncate(0)

    for r in _iter_audit_rows(db, project_id):
        row = _row_to_dict(r)
        # action_detail is a dict — dump to JSON string for CSV safety.
        row["action_detail"] = json.dumps(row["action_detail"], default=str)
        writer.writerow(row)
        yield buf.getvalue().encode("utf-8")
        buf.seek(0); buf.truncate(0)


def _stream_ndjson(db: Session, project_id: Optional[int]) -> Iterator[bytes]:
    """Generator that yields one JSON object per line (NDJSON)."""
    for r in _iter_audit_rows(db, project_id):
        line = json.dumps(_row_to_dict(r), default=str)
        yield (line + "\n").encode("utf-8")


@router.get("/export")
def export_audit_log(
    project_id: Optional[int] = None,
    format: str = Query("json", pattern="^(json|csv)$"),
    db: Session = Depends(get_db),
    current_user: User = Depends(_audit_dep),
):
    """
    Export the audit log as **NDJSON** or CSV. Streams from a
    server-side cursor so an arbitrarily large log no longer
    materialises in worker memory (F-020).

    NOTE: ``format=json`` now returns ``application/x-ndjson``
    (one JSON object per line) instead of the prior single-array
    payload. The frontend audit page treats the body as a blob and
    writes it directly to disk — file is valid JSON Lines and any
    standards-aware tool (jq -s, pandas read_json(lines=True), etc.)
    parses it. The token "json" is preserved on the URL so existing
    bookmarks keep working.

    When ``project_id`` is supplied, project membership is enforced
    (F-014 alignment) so a per-project export can't leak across
    projects even if the caller is a PM with cross-project view.
    """
    if project_id is not None:
        _check_membership(db, project_id, current_user)

    if format == "csv":
        filename = (
            f"astra_audit_log_{project_id}.csv" if project_id else "astra_audit_log.csv"
        )
        return StreamingResponse(
            _stream_csv(db, project_id),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    filename = (
        f"astra_audit_log_{project_id}.ndjson"
        if project_id else "astra_audit_log.ndjson"
    )
    return StreamingResponse(
        _stream_ndjson(db, project_id),
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
