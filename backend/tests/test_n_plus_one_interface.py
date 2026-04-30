"""
ASTRA — N+1 query suppression for interface endpoints (F-039)
==============================================================
File: backend/tests/test_n_plus_one_interface.py

Counts SQL statements emitted by the patched endpoints and asserts
the count is bounded — i.e. doesn't grow with the number of child
rows. Pre-fix `get_unit` issued O(connectors × pins) per-row queries;
post-fix it issues a fixed handful regardless of unit size.

The shape of the assertion is "fewer than N statements regardless of
fixture size" rather than an exact number, because eager-load
behavior may add one extra batch query that the strict-count hides.
"""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import event

from app.models import Project, User
from app.models.interface import (
    BusDefinition, Connector, MessageDefinition, MessageField, Pin,
    PinBusAssignment, System, Unit,
)
from app.models.project_member import ProjectMember
from app.services.auth import create_access_token, get_password_hash


# ──────────────────────────────────────
#  Fixture builders
# ──────────────────────────────────────


def _user(db, *, username, role="admin"):
    u = User(
        username=username, email=f"{username}@example.com",
        hashed_password=get_password_hash("NPlus1Pass"),
        full_name=username.title(), role=role, department="Eng",
        is_active=True,
    )
    db.add(u); db.commit(); db.refresh(u)
    return u


def _project(db, owner, code):
    p = Project(code=code, name=f"P {code}", owner_id=owner.id, status="active")
    db.add(p); db.commit(); db.refresh(p)
    db.add(ProjectMember(project_id=p.id, user_id=owner.id, added_by_id=owner.id))
    db.commit()
    return p


def _build_unit_with_load(db, project, owner, *, n_connectors: int, n_pins_per_connector: int):
    s = System(
        system_id="SYS-001", name="System",
        system_type="subsystem", project_id=project.id, owner_id=owner.id,
    )
    db.add(s); db.commit(); db.refresh(s)
    unit = Unit(
        unit_id="UNIT-001", name="Test LRU", designation="LRU-001",
        part_number="LRU-001-A", manufacturer="Test", unit_type="processor",
        system_id=s.id, project_id=project.id, status="concept",
    )
    db.add(unit); db.commit(); db.refresh(unit)

    for ci in range(n_connectors):
        c = Connector(
            connector_id=f"CONN-{ci+1:03d}",
            designator=f"J{ci+1}",
            name=f"Connector {ci+1}",
            connector_type="mil_dtl_38999_series_iii",
            gender="female_socket",
            total_contacts=n_pins_per_connector,
            unit_id=unit.id, project_id=project.id,
        )
        db.add(c); db.commit(); db.refresh(c)
        for pi in range(n_pins_per_connector):
            db.add(Pin(
                connector_id=c.id,
                pin_number=str(pi + 1),
                signal_name=f"SIG_{ci}_{pi}",
                signal_type="signal_digital_single",
                direction="bidirectional",
            ))
        db.commit()
    return unit


@contextmanager
def _count_queries(engine):
    """Yield a list that fills with each SQL statement issued by *engine*."""
    statements: list[str] = []

    def _on_execute(_conn, _cursor, statement, _params, _ctx, _executemany):
        # Filter out the SAVEPOINT / RELEASE noise that sqlalchemy emits
        # for nested transactions in the test fixtures.
        s = statement.strip().upper()
        if s.startswith(("SAVEPOINT", "RELEASE", "ROLLBACK", "BEGIN", "COMMIT")):
            return
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", _on_execute)
    try:
        yield statements
    finally:
        event.remove(engine, "before_cursor_execute", _on_execute)


# ──────────────────────────────────────
#  Tests
# ──────────────────────────────────────


class TestGetUnitQueryCount:
    @pytest.mark.parametrize(
        "n_connectors,n_pins",
        [(2, 5), (4, 10), (8, 20)],
    )
    def test_query_count_does_not_scale_with_unit_size(
        self, client, db_session, db_engine, n_connectors, n_pins,
    ):
        owner = _user(db_session, username=f"npo_{n_connectors}_{n_pins}")
        project = _project(db_session, owner, f"NPL{n_connectors}{n_pins}")
        unit = _build_unit_with_load(
            db_session, project, owner,
            n_connectors=n_connectors, n_pins_per_connector=n_pins,
        )

        headers = {"Authorization": f"Bearer {create_access_token(data={'sub': owner.username})}"}

        with _count_queries(db_engine) as stmts:
            r = client.get(f"/api/v1/interfaces/units/{unit.id}", headers=headers)

        assert r.status_code == 200, r.text
        n = len(stmts)
        print(f"\n[get_unit] n_connectors={n_connectors} n_pins={n_pins} → {n} statements")
        # Pre-fix: ~3 + connectors + pins + (assignments per pin)
        #          → tens to hundreds depending on size.
        # Post-fix: bounded under 30 regardless of n_connectors / n_pins
        # (a few framework queries + the fixed pre-fetch set).
        assert n < 30, (
            f"get_unit issued {n} queries for "
            f"n_connectors={n_connectors}, n_pins={n_pins} — N+1 regression"
        )


class TestListSystemsQueryCount:
    def test_query_count_is_bounded(self, client, db_session, db_engine):
        owner = _user(db_session, username="npo_systems")
        project = _project(db_session, owner, "NPLSYS")
        for i in range(15):
            db_session.add(System(
                system_id=f"SYS-{i+1:03d}",
                name=f"System {i}",
                system_type="subsystem",
                project_id=project.id,
                owner_id=owner.id,
            ))
        db_session.commit()

        headers = {"Authorization": f"Bearer {create_access_token(data={'sub': owner.username})}"}
        with _count_queries(db_engine) as stmts:
            r = client.get(
                f"/api/v1/interfaces/systems?project_id={project.id}",
                headers=headers,
            )
        assert r.status_code == 200, r.text
        # 15 systems pre-fix would emit ~30 count queries; post-fix uses
        # 1 systems query + 1 unit-count GROUP BY + 2 interface-count
        # GROUP BYs + framework overhead ≈ 10 max.
        assert len(stmts) < 15, (
            f"list_systems issued {len(stmts)} queries for 15 systems — "
            "N+1 regression"
        )
