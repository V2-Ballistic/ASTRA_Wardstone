"""ASTRA-TDD-HAROLD-001 Phase 3 — outbound designator-feed contract test.

`GET /api/v1/catalog/designators` is consumed by HAROLD (peer service)
to know what WPNs ASTRA has already issued. Verifies:
  * `?system=AV` filters via `WS-AV-P%` LIKE pattern
  * Case-insensitive `system=av` upper-cases internally
  * No filter returns everything (paginated)
  * Soft-deleted parts (`deleted_at` not null) are excluded
  * `limit ≤ 200` cap enforced (FastAPI Query validation)
  * Auth-free per AD-8 (HAROLD is a peer service, not a user)
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.models.catalog import (
    CatalogPart, LifecycleStatus, LRUClass, PartClass, Supplier,
)


def _mk_supplier(db, owner_id: int, *, name: str = "Acme") -> Supplier:
    s = Supplier(name=name, is_active=True, is_in_house=False, created_by_id=owner_id)
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def _mk_part(db, owner_id: int, supplier_id: int, part_number: str,
             *, deleted: bool = False) -> CatalogPart:
    cp = CatalogPart(
        supplier_id=supplier_id,
        part_number=part_number,
        name=f"Catalog {part_number}",
        part_class=PartClass.PROCESSOR,
        lru_classification=LRUClass.LRU,
        lifecycle_status=LifecycleStatus.ACTIVE,
        created_by_id=owner_id,
    )
    if deleted:
        cp.deleted_at = datetime.utcnow()
    db.add(cp)
    db.commit()
    db.refresh(cp)
    return cp


@pytest.fixture
def seeded_catalog(db_session, test_user):
    sup = _mk_supplier(db_session, test_user.id)
    _mk_part(db_session, test_user.id, sup.id, "WS-AV-P0001-A")
    _mk_part(db_session, test_user.id, sup.id, "WS-AV-P0002-B")
    _mk_part(db_session, test_user.id, sup.id, "WS-ST-P0001-A")
    _mk_part(db_session, test_user.id, sup.id, "92196A196")
    _mk_part(db_session, test_user.id, sup.id, "WS-AV-P9999-X", deleted=True)
    return sup


def test_filter_by_system_av(client, seeded_catalog):
    r = client.get("/api/v1/catalog/designators?system=AV")
    assert r.status_code == 200
    body = r.json()
    assert body["system_filter"] == "AV"
    assert body["total"] == 2
    assert set(body["designators"]) == {"WS-AV-P0001-A", "WS-AV-P0002-B"}


def test_filter_by_system_st(client, seeded_catalog):
    r = client.get("/api/v1/catalog/designators?system=ST")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["designators"] == ["WS-ST-P0001-A"]


def test_filter_is_case_insensitive(client, seeded_catalog):
    """Lowercase `av` is upper-cased internally so the LIKE pattern hits."""
    r = client.get("/api/v1/catalog/designators?system=av")
    assert r.status_code == 200
    body = r.json()
    assert body["system_filter"] == "AV"
    assert body["total"] == 2


def test_no_filter_returns_all_non_deleted(client, seeded_catalog):
    r = client.get("/api/v1/catalog/designators")
    assert r.status_code == 200
    body = r.json()
    # 4 live rows; soft-deleted WS-AV-P9999-X is excluded.
    assert body["total"] == 4
    assert "WS-AV-P9999-X" not in body["designators"]
    assert "92196A196"     in body["designators"]
    assert body["system_filter"] is None


def test_soft_deleted_parts_excluded_from_system_filter(client, seeded_catalog):
    """The soft-deleted WS-AV-P9999-X must not show up under ?system=AV."""
    r = client.get("/api/v1/catalog/designators?system=AV")
    assert "WS-AV-P9999-X" not in r.json()["designators"]


def test_pagination_limit_enforced(client, seeded_catalog):
    # Limit > 200 is rejected by FastAPI's Query(..., le=200).
    r = client.get("/api/v1/catalog/designators?limit=500")
    assert r.status_code == 422


def test_pagination_skip_and_limit(client, seeded_catalog):
    r1 = client.get("/api/v1/catalog/designators?limit=2")
    r2 = client.get("/api/v1/catalog/designators?skip=2&limit=2")
    assert r1.status_code == 200 and r2.status_code == 200
    assert len(r1.json()["designators"]) == 2
    # No overlap between the first 2 and the next 2.
    overlap = set(r1.json()["designators"]) & set(r2.json()["designators"])
    assert overlap == set()


def test_endpoint_is_auth_free(client, seeded_catalog):
    """AD-8 v1 stance: peer-service endpoint, no auth required."""
    r = client.get("/api/v1/catalog/designators")
    assert r.status_code == 200
