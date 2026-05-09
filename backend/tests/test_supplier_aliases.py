"""TDD-CAT-002 — supplier alias resolution tests.

Verifies the SupplierAlias table behaviour used by the STEP upload
supplier resolver: case-insensitive lookup, unique alias per supplier,
cascade-on-supplier-delete.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.models.catalog import Supplier, SupplierAlias


def _make_supplier(db, user, name="McMaster-Carr") -> Supplier:
    s = Supplier(name=name, is_active=True, created_by_id=user.id)
    db.add(s)
    db.flush()
    return s


def test_alias_resolution_case_insensitive(db_session, test_user):
    sup = _make_supplier(db_session, test_user)
    db_session.add(SupplierAlias(supplier_id=sup.id, alias="McMaster"))
    db_session.commit()

    for needle in ("McMaster", "MCMASTER", "mcmaster"):
        hit = (
            db_session.query(SupplierAlias)
            .filter(func.lower(SupplierAlias.alias) == needle.lower())
            .first()
        )
        assert hit is not None
        assert hit.supplier_id == sup.id


def test_unique_alias_constraint(db_session, test_user):
    sup1 = _make_supplier(db_session, test_user, name="Vendor One")
    sup2 = _make_supplier(db_session, test_user, name="Vendor Two")

    db_session.add(SupplierAlias(supplier_id=sup1.id, alias="dup-alias"))
    db_session.commit()

    db_session.add(SupplierAlias(supplier_id=sup2.id, alias="dup-alias"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_alias_cascade_on_supplier_delete(db_session, test_user):
    sup = _make_supplier(db_session, test_user, name="Doomed Vendor")
    db_session.add(SupplierAlias(supplier_id=sup.id, alias="DV"))
    db_session.add(SupplierAlias(supplier_id=sup.id, alias="DoomedV"))
    db_session.commit()

    pre = db_session.query(SupplierAlias).filter(
        SupplierAlias.supplier_id == sup.id
    ).count()
    assert pre == 2

    db_session.delete(sup)
    db_session.commit()

    post = db_session.query(SupplierAlias).filter(
        SupplierAlias.supplier_id == sup.id
    ).count()
    assert post == 0
