"""Supplier service — get-or-create helper for the CADPORT supplier picker.

CADPORT-TDD-SUPPLIER-001 §3.2. Replaces the legacy ``_wardstone()``
default-supplier fallback that lived in ``routers/cadport.py``: every
CADPORT upload now carries an explicit supplier (``supplier_id`` for
an existing row, or ``supplier_name`` to create a new one).

Matching is case-insensitive (so ``"vectornav"`` reuses an existing
``"VectorNav"`` row); casing on creation is preserved from the
caller's input. The DB-level ``UNIQUE(name)`` constraint guarantees
the lookup either resolves or the create path inserts a single row.
"""

from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.catalog import Supplier
from app.services.audit_service import record_event as _audit


def get_or_create_supplier(
    db: Session,
    name: str,
    *,
    current_user_id: int,
    request=None,
) -> tuple[Supplier, bool]:
    """Return ``(supplier, created)`` for the given name.

    Lookup is case-insensitive. If an existing supplier matches, its
    row is returned with ``created=False``. Otherwise a new row is
    inserted with the caller's casing preserved and ``created=True``.
    On the create path, an audit log entry is emitted under the
    ``supplier.created`` event type.

    Raises ``ValueError`` for blank names — the caller must validate
    first (the upload endpoint returns 400 in that case).
    """
    trimmed = (name or "").strip()
    if not trimmed:
        raise ValueError("supplier name is empty")

    existing = (
        db.query(Supplier)
        .filter(func.lower(Supplier.name) == trimmed.lower())
        .first()
    )
    if existing is not None:
        return existing, False

    supplier = Supplier(
        name=trimmed,
        is_active=True,
        is_in_house=False,
        created_by_id=current_user_id,
    )
    db.add(supplier)
    db.flush()
    db.refresh(supplier)

    _audit(
        db,
        event_type="supplier.created",
        entity_type="supplier",
        entity_id=supplier.id,
        user_id=current_user_id,
        action_detail={"name": supplier.name, "via": "cadport_upload"},
        request=request,
    )
    return supplier, True


def resolve_supplier_choice(
    db: Session,
    *,
    supplier_id: int | None,
    supplier_name: str | None,
    current_user_id: int,
    request=None,
) -> tuple[Supplier, bool]:
    """Apply the spec §3.3 dispatch.

    - ``supplier_id`` set and ``supplier_name`` unset → look up by id;
      raises ``LookupError`` if not found.
    - ``supplier_name`` set and ``supplier_id`` unset →
      ``get_or_create_supplier(name)``.
    - Both set → ``ValueError("both")``.
    - Neither set → ``ValueError("neither")``.

    Returns ``(supplier, created)``. ``created`` is False unless the
    name path created a new row.
    """
    has_id = supplier_id is not None
    has_name = bool((supplier_name or "").strip())
    if has_id and has_name:
        raise ValueError("both")
    if not has_id and not has_name:
        raise ValueError("neither")
    if has_id:
        supplier = (
            db.query(Supplier).filter(Supplier.id == supplier_id).first()
        )
        if supplier is None:
            raise LookupError(f"supplier_id={supplier_id} not found")
        return supplier, False
    return get_or_create_supplier(
        db,
        supplier_name or "",
        current_user_id=current_user_id,
        request=request,
    )
