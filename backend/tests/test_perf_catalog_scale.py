"""ASTRA — Performance Tests at Catalog Scale (Phase 8, ASTRA-TDD-INTF-002)
============================================================================
File: backend/tests/test_perf_catalog_scale.py    ← NEW (Phase 8)

Per spec §18 thresholds. Each test sets up a focused workload, times the
critical operation with ``time.perf_counter()``, and asserts under the
threshold. Marked with ``@pytest.mark.performance`` so they're excluded
from the default suite (``-m 'not performance'``) and selected explicitly
for perf regressions (``-m performance``).

Spec §18 thresholds
-------------------

| Operation                                                  | Threshold  |
|------------------------------------------------------------|------------|
| Catalog list paginated (200 items)                         | < 200 ms   |
| Catalog part detail (with connectors+pins eager)           | < 300 ms   |
| Auto-wire on 100-pin units                                 | < 500 ms   |
| Coverage report (per project)                              | < 1 s      |
| Sync proposal fan-out on CatalogPart edit affecting 50     | < 2 s      |
| placed units                                               |            |

Notes
-----
- Tests use the same SQLite-backed test DB the rest of the suite uses.
  SQLite is an order of magnitude slower than PG for some patterns; if a
  threshold fails by a small margin under SQLite but the equivalent live PG
  query is fast, the threshold here is a *floor* — passing under SQLite
  effectively guarantees passing under PG.
- The test sets are sized to the spec but not to the absolute spec maximum
  (the spec calls out 1000 parts for the catalog-scale envelope). Bulk
  insert via ``Session.bulk_save_objects()`` keeps the setup time bounded
  for CI.
"""

from __future__ import annotations

import time
from typing import List

import pytest
from sqlalchemy.orm import Session

from app.models import (
    Project, Requirement, RequirementStatus, User, UserRole,
)
from app.models.catalog import (
    CatalogConnector,
    CatalogPart,
    CatalogPin,
    ConnectorGender as CatGender,
    LifecycleStatus,
    LRUClass,
    PartClass,
    SignalDirection as CatDirection,
    SignalType as CatSignalType,
    Supplier,
)
from app.models.interface import (
    Connector,
    Interface,
    InterfaceDirection,
    InterfaceStatus,
    Pin,
    System,
    Unit,
    WireHarness,
)
from app.models.req_sync import (
    RequirementSourceLink,
    SourceEntityType,
)
from app.services.coverage.source_validator import validate_project_coverage
from app.services.interface.auto_wire import auto_wire_interface
from app.services.req_sync import fan_out_for_entity, register_sync_listeners
from tests.conftest import make_user


# Mark every test in this module as performance-only.
pytestmark = pytest.mark.performance


@pytest.fixture(autouse=True)
def _ensure_listeners_registered():
    register_sync_listeners()
    yield


# ══════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════


def _bulk_create_parts(
    db: Session, supplier_id: int, owner_id: int, n: int,
) -> List[int]:
    """Bulk-insert `n` minimal CatalogParts under `supplier_id`. Returns ids."""
    parts: list[CatalogPart] = []
    for i in range(n):
        parts.append(CatalogPart(
            supplier_id=supplier_id,
            part_number=f"PERF-PART-{i:05d}",
            revision="A",
            name=f"Perf Part {i}",
            part_class=PartClass.PROCESSOR,
            lru_classification=LRUClass.LRU,
            lifecycle_status=LifecycleStatus.ACTIVE,
            created_by_id=owner_id,
        ))
    db.add_all(parts)
    db.commit()
    return [p.id for p in parts]


def _build_part_with_connectors_and_pins(
    db: Session, supplier_id: int, owner_id: int,
    *, n_connectors: int = 5, n_pins_per_conn: int = 10,
) -> CatalogPart:
    part = CatalogPart(
        supplier_id=supplier_id,
        part_number="PERF-DETAIL",
        revision="A",
        name="Perf detail part",
        part_class=PartClass.PROCESSOR,
        lru_classification=LRUClass.LRU,
        lifecycle_status=LifecycleStatus.ACTIVE,
        created_by_id=owner_id,
    )
    db.add(part)
    db.flush()
    for ci in range(n_connectors):
        conn = CatalogConnector(
            catalog_part_id=part.id,
            reference=f"J{ci+1}",
            position=ci,
            connector_type="MIL-DTL-38999/III",
            gender=CatGender.MALE,
            pin_count=n_pins_per_conn,
        )
        db.add(conn)
        db.flush()
        for pi in range(n_pins_per_conn):
            db.add(CatalogPin(
                catalog_connector_id=conn.id,
                pin_position=str(pi + 1),
                mfr_pin_name=f"SIG_{ci}_{pi}",
                mfr_signal_type=CatSignalType.DIGITAL,
                mfr_direction=CatDirection.BIDIRECTIONAL,
            ))
    db.commit()
    db.refresh(part)
    return part


def _build_unit_with_pins(
    db: Session, project_id: int, system_id: int, owner_id: int,
    designation: str, n_pins: int, *, gender: str = "female_socket",
    suffix: str = "src",
) -> tuple[Unit, Connector, list[Pin]]:
    unit = Unit(
        unit_id=f"PERF-{suffix}-U",
        name=designation,
        designation=designation,
        part_number="PERFPART",
        manufacturer="Perf",
        unit_type="processor",
        status="concept",
        system_id=system_id,
        project_id=project_id,
    )
    db.add(unit)
    db.flush()
    conn = Connector(
        connector_id=f"PERF-{suffix}-C",
        designator="J1",
        connector_type="mil_dtl_38999_series_iii",
        gender=gender,
        total_contacts=n_pins,
        unit_id=unit.id,
        project_id=project_id,
    )
    db.add(conn)
    db.flush()
    pins: list[Pin] = []
    for i in range(n_pins):
        p = Pin(
            pin_number=str(i + 1),
            signal_name=f"DATA_{i:03d}",
            internal_signal_name=f"DATA_{i:03d}",
            mfr_pin_name=f"PIN_{i+1}",
            signal_type="signal_digital_single",
            direction="bidirectional",
            connector_id=conn.id,
        )
        db.add(p)
        pins.append(p)
    db.commit()
    return unit, conn, pins


# ══════════════════════════════════════════════════════════════
#  TestCatalogList — paginated <200ms
# ══════════════════════════════════════════════════════════════


class TestCatalogList:

    def test_catalog_list_200_under_200ms(
        self, client, db_session, test_user, auth_headers,
    ):
        s = Supplier(name="PerfSup-List", cage_code="P0001",
                     is_active=True, created_by_id=test_user.id)
        db_session.add(s)
        db_session.commit()

        # Seed 1000 parts so the LIMIT 200 query has a realistic working set.
        _bulk_create_parts(db_session, s.id, test_user.id, 1000)

        # Warm-up (first request pays import / model-init cost).
        client.get("/api/v1/catalog/parts?limit=200&supplier_id={}".format(s.id),
                   headers=auth_headers)

        t0 = time.perf_counter()
        resp = client.get(
            f"/api/v1/catalog/parts?limit=200&supplier_id={s.id}",
            headers=auth_headers,
        )
        elapsed = time.perf_counter() - t0
        assert resp.status_code == 200, resp.text
        assert len(resp.json()) == 200
        # Threshold per spec §18.
        assert elapsed < 0.200, (
            f"Catalog list (200 items) took {elapsed*1000:.1f}ms; "
            "spec §18 budget is 200ms"
        )


# ══════════════════════════════════════════════════════════════
#  TestCatalogDetail — single part with eager connectors/pins <300ms
# ══════════════════════════════════════════════════════════════


class TestCatalogDetail:

    def test_catalog_detail_50_pins_under_300ms(
        self, client, db_session, test_user, auth_headers,
    ):
        s = Supplier(name="PerfSup-Detail", cage_code="P0002",
                     is_active=True, created_by_id=test_user.id)
        db_session.add(s)
        db_session.commit()
        part = _build_part_with_connectors_and_pins(
            db_session, s.id, test_user.id,
            n_connectors=5, n_pins_per_conn=10,
        )

        # Warm-up
        client.get(f"/api/v1/catalog/parts/{part.id}", headers=auth_headers)

        t0 = time.perf_counter()
        resp = client.get(
            f"/api/v1/catalog/parts/{part.id}",
            headers=auth_headers,
        )
        elapsed = time.perf_counter() - t0
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert len(body.get("connectors", [])) == 5
        assert elapsed < 0.300, (
            f"Catalog detail (5 connectors × 10 pins) took {elapsed*1000:.1f}ms; "
            "spec §18 budget is 300ms"
        )


# ══════════════════════════════════════════════════════════════
#  TestAutoWire100Pins — three-way validation <500ms
# ══════════════════════════════════════════════════════════════


class TestAutoWire100Pins:

    def test_auto_wire_100_pin_units_under_500ms(
        self, db_session, test_user, test_project,
    ):
        sysm = System(
            system_id="SYS-PERF-AW", name="Perf AW",
            abbreviation="AW", system_type="subsystem",
            project_id=test_project.id, owner_id=test_user.id,
        )
        db_session.add(sysm)
        db_session.commit()

        unit_a, conn_a, pins_a = _build_unit_with_pins(
            db_session, test_project.id, sysm.id, test_user.id,
            "AW-A", 100, gender="female_socket", suffix="src",
        )
        unit_b, conn_b, pins_b = _build_unit_with_pins(
            db_session, test_project.id, sysm.id, test_user.id,
            "AW-B", 100, gender="male_pin", suffix="tgt",
        )

        iface = Interface(
            interface_id="IFACE-PERF-AW",
            name="AW perf", description="",
            interface_type="data_digital",
            direction=InterfaceDirection.BIDIRECTIONAL,
            status=InterfaceStatus.PROPOSED,
            source_system_id=sysm.id,
            target_system_id=sysm.id,
            source_unit_id=unit_a.id,
            target_unit_id=unit_b.id,
            project_id=test_project.id,
            owner_id=test_user.id,
        )
        db_session.add(iface)
        db_session.commit()

        t0 = time.perf_counter()
        result = auto_wire_interface(db_session, iface.id)
        elapsed = time.perf_counter() - t0

        assert elapsed < 0.500, (
            f"auto_wire on 100×100 pins took {elapsed*1000:.1f}ms; "
            "spec §18 budget is 500ms"
        )
        # Sanity — every same-name same-direction pair should yield a proposal.
        assert len(result.proposed_wires) >= 100


# ══════════════════════════════════════════════════════════════
#  TestCoverageReport — per-project report <1s
# ══════════════════════════════════════════════════════════════


class TestCoverageReport:

    def test_coverage_report_500_reqs_under_1s(
        self, db_session, test_user, test_project,
    ):
        # Seed 500 requirements directly so the live coverage path can
        # walk every one of them.
        reqs = []
        for i in range(500):
            reqs.append(Requirement(
                req_id=f"COV-{i:04d}",
                title=f"perf req {i}",
                statement="Perf req statement.",
                rationale="r",
                req_type="functional",
                priority="medium",
                status=RequirementStatus.APPROVED,
                level="L3" if i % 3 == 0 else "L4",
                version=1,
                quality_score=70.0,
                project_id=test_project.id,
                owner_id=test_user.id,
                created_by_id=test_user.id,
            ))
        db_session.add_all(reqs)
        db_session.commit()

        # Live mode (MV doesn't exist on SQLite); the live path is the
        # paranoid escape hatch and pays the most cost.
        t0 = time.perf_counter()
        report = validate_project_coverage(
            db_session, test_project.id, use_materialized_view=False,
        )
        elapsed = time.perf_counter() - t0

        assert elapsed < 1.0, (
            f"validate_project_coverage on 500 reqs took {elapsed*1000:.1f}ms; "
            "spec §18 budget is 1000ms"
        )
        assert report is not None
        # All L3/L4 reqs without source links should appear as orphans.
        assert len(report.orphans) >= 1


# ══════════════════════════════════════════════════════════════
#  TestSyncFanOut50Units — CatalogPart edit fan-out <2s
# ══════════════════════════════════════════════════════════════


class TestSyncFanOut50Units:

    def test_fan_out_50_placed_units_under_2s(
        self, db_session, test_user, test_project,
    ):
        # Build 50 source-link rows pointing at a single CatalogPart;
        # then fan-out simulates a CatalogPart edit affecting 50 placed reqs.
        from app.models.catalog import CatalogPart, Supplier

        sup = Supplier(
            name="PerfSup-Fanout", cage_code="P0003",
            is_active=True, created_by_id=test_user.id,
        )
        db_session.add(sup)
        db_session.commit()
        cat_part = CatalogPart(
            supplier_id=sup.id, part_number="FANOUT-PART", revision="A",
            name="fanout part", part_class=PartClass.PROCESSOR,
            lru_classification=LRUClass.LRU,
            lifecycle_status=LifecycleStatus.ACTIVE,
            created_by_id=test_user.id,
        )
        db_session.add(cat_part)
        db_session.commit()

        # 50 distinct requirements, each linked to the catalog part.
        for i in range(50):
            r = Requirement(
                req_id=f"FAN-{i:03d}", title=f"Fan {i}",
                statement="Catalog part FANOUT-PART shall do (will change).",
                rationale="r",
                req_type="interface", priority="medium",
                status=RequirementStatus.APPROVED, level="L3",
                version=1, quality_score=70.0,
                project_id=test_project.id, owner_id=test_user.id,
                created_by_id=test_user.id,
                generation_template_id="harness_overall",
            )
            db_session.add(r)
            db_session.flush()
            db_session.add(RequirementSourceLink(
                requirement_id=r.id,
                source_entity_type=SourceEntityType.CATALOG_PART,
                source_entity_id=cat_part.id,
                template_id="harness_overall",
                template_inputs={},
                role="primary",
            ))
        db_session.commit()

        t0 = time.perf_counter()
        proposals = fan_out_for_entity(
            db_session, SourceEntityType.CATALOG_PART, cat_part.id, "update",
        )
        elapsed = time.perf_counter() - t0

        assert elapsed < 2.0, (
            f"fan_out on 50 placed units took {elapsed*1000:.1f}ms; "
            "spec §18 budget is 2000ms"
        )
        # Every source-linked req should have produced at least a SKIP/PROPOSAL/AUTO_APPLY
        # path; PROPOSAL_PENDING for APPROVED reqs means real RequirementSyncProposal rows.
        assert len(proposals) >= 50
