"""
ASTRA — Tamper-Evident Audit Service
======================================
File: backend/app/services/audit_service.py   ← NEW

Core operations:
  record_event()           — append a hash-chained audit record
  verify_chain_integrity() — walk the chain and report any tampering
  query_audit_log()        — paginated, filtered reads
"""

import hashlib
import json
from datetime import datetime
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog
from app.middleware.audit_middleware import get_request_context

# Genesis hash — the "previous_hash" for the very first record
GENESIS_HASH = hashlib.sha256(b"ASTRA_GENESIS_BLOCK").hexdigest()


# ══════════════════════════════════════
#  Hashing
# ══════════════════════════════════════

def _compute_hash(
    sequence_number: int,
    timestamp: str,
    event_type: str,
    entity_type: str,
    entity_id: int,
    user_id: int,
    action_detail: dict,
    previous_hash: str,
) -> str:
    """
    SHA-256( seq || ts || event_type || entity_type || entity_id
             || user_id || json(detail) || previous_hash )
    """
    payload = (
        f"{sequence_number}|{timestamp}|{event_type}|{entity_type}"
        f"|{entity_id}|{user_id}|{json.dumps(action_detail, sort_keys=True, default=str)}"
        f"|{previous_hash}"
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ══════════════════════════════════════
#  Record
# ══════════════════════════════════════

def record_event(
    db: Session,
    event_type: str,
    entity_type: str,
    entity_id: int,
    user_id: int,
    action_detail: dict | None = None,
    project_id: int | None = None,
    request=None,
) -> AuditLog:
    """
    Append a tamper-evident audit record.

    Uses ``SELECT ... FOR UPDATE`` on the latest row to serialise
    concurrent writers so the sequence stays monotonic and the hash
    chain never forks.
    """
    action_detail = action_detail or {}

    # Pull IP / UA from middleware context (or from explicit request)
    ctx = get_request_context()
    user_ip = ctx.get("ip", "")
    user_agent = ctx.get("user_agent", "")
    if request is not None:
        user_ip = user_ip or (request.client.host if request.client else "")
        user_agent = user_agent or request.headers.get("user-agent", "")

    # ── Serialised read of the last record ──
    # FOR UPDATE SKIP LOCKED is not appropriate here — we WANT to wait
    # so the chain is strictly ordered.  Plain FOR UPDATE is correct.
    prev = (
        db.query(AuditLog)
        .order_by(AuditLog.sequence_number.desc())
        .with_for_update()
        .first()
    )
    if prev:
        previous_hash = prev.record_hash
        next_seq = prev.sequence_number + 1
    else:
        previous_hash = GENESIS_HASH
        next_seq = 1

    now = datetime.utcnow()
    ts_str = now.isoformat()

    record_hash = _compute_hash(
        next_seq, ts_str, event_type, entity_type,
        entity_id, user_id, action_detail, previous_hash,
    )

    entry = AuditLog(
        timestamp=now,
        event_type=event_type,
        entity_type=entity_type,
        entity_id=entity_id,
        project_id=project_id,
        user_id=user_id,
        user_ip=user_ip,
        user_agent=user_agent,
        action_detail=action_detail,
        previous_hash=previous_hash,
        record_hash=record_hash,
        sequence_number=next_seq,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


# ══════════════════════════════════════
#  Verify
# ══════════════════════════════════════

def verify_chain_integrity(
    db: Session,
    project_id: int | None = None,
    start_seq: int | None = None,
    end_seq: int | None = None,
) -> dict:
    """
    Walk every record in sequence order, recompute each hash, and
    compare against the stored value.

    Returns:
        {
            "total_records": int,
            "verified_count": int,
            "is_valid": bool,
            "first_invalid": None | {"sequence_number": ..., "reason": ...},
        }
    """
    query = db.query(AuditLog).order_by(AuditLog.sequence_number.asc())
    if project_id is not None:
        query = query.filter(AuditLog.project_id == project_id)
    if start_seq is not None:
        query = query.filter(AuditLog.sequence_number >= start_seq)
    if end_seq is not None:
        query = query.filter(AuditLog.sequence_number <= end_seq)

    records = query.all()
    total = len(records)
    verified = 0
    first_invalid = None

    expected_prev = GENESIS_HASH
    expected_seq = 1

    for rec in records:
        # When filtering by project, sequence gaps are expected — skip gap checks
        if project_id is None:
            if rec.sequence_number != expected_seq:
                if first_invalid is None:
                    first_invalid = {
                        "sequence_number": expected_seq,
                        "expected_sequence": expected_seq,
                        "found_sequence": rec.sequence_number,
                        "reason": "Missing record — sequence gap detected",
                    }
                break

        # Verify previous_hash linkage (only meaningful without project filter)
        if project_id is None and rec.previous_hash != expected_prev:
            if first_invalid is None:
                first_invalid = {
                    "sequence_number": rec.sequence_number,
                    "reason": "previous_hash mismatch — chain is broken",
                }
            break

        # Recompute record hash
        recomputed = _compute_hash(
            rec.sequence_number,
            rec.timestamp.isoformat(),
            rec.event_type,
            rec.entity_type,
            rec.entity_id,
            rec.user_id,
            rec.action_detail or {},
            rec.previous_hash,
        )
        if recomputed != rec.record_hash:
            if first_invalid is None:
                first_invalid = {
                    "sequence_number": rec.sequence_number,
                    "reason": "record_hash mismatch — record content was tampered with",
                    "expected_hash": recomputed,
                    "stored_hash": rec.record_hash,
                }
            break

        verified += 1
        expected_prev = rec.record_hash
        expected_seq = rec.sequence_number + 1

    return {
        "total_records": total,
        "verified_count": verified,
        "is_valid": first_invalid is None,
        "first_invalid": first_invalid,
    }


# ══════════════════════════════════════
#  Query
# ══════════════════════════════════════

def query_audit_log(
    db: Session,
    project_id: int | None = None,
    user_id: int | None = None,
    entity_type: str | None = None,
    entity_id: int | None = None,
    event_type: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    skip: int = 0,
    limit: int = 50,
) -> dict:
    """Paginated, filtered query over the audit log."""
    query = db.query(AuditLog)

    if project_id is not None:
        query = query.filter(AuditLog.project_id == project_id)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if entity_id is not None:
        query = query.filter(AuditLog.entity_id == entity_id)
    if event_type:
        query = query.filter(AuditLog.event_type == event_type)
    if date_from:
        query = query.filter(AuditLog.timestamp >= date_from)
    if date_to:
        query = query.filter(AuditLog.timestamp <= date_to)

    total = query.count()
    records = (
        query.order_by(AuditLog.timestamp.desc())
        .offset(skip)
        .limit(limit)
        .all()
    )

    items = []
    for r in records:
        items.append({
            "id": r.id,
            "sequence_number": r.sequence_number,
            "timestamp": r.timestamp.isoformat() if r.timestamp else None,
            "event_type": r.event_type,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "project_id": r.project_id,
            "user_id": r.user_id,
            "username": r.user.username if r.user else None,
            "user_full_name": r.user.full_name if r.user else None,
            "user_ip": r.user_ip,
            "action_detail": r.action_detail,
            "record_hash": r.record_hash[:12] + "…",  # truncated for display
        })

    return {"total": total, "skip": skip, "limit": limit, "items": items}
