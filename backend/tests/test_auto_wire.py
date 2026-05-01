"""ASTRA — Auto-Wire Engine Tests (INTF-002 Phase 4)
=====================================================
File: backend/tests/test_auto_wire.py   ← NEW (Phase 4, ASTRA-TDD-INTF-002)

Covers spec §17 Phase 4 acceptance for the three-way auto-wire engine and
the Connection Builder backend endpoints.

Test layout
-----------
- ``TestDirectionMatrix``  — every cell of the 6×6 SignalDirection matrix
                              (parameterized) per digest §6
- ``TestNameMatching``     — Check #1 cases: hit, miss, ambiguous
- ``TestDirectionConflict``— Check #2 cases: output↔output, power↔ground, etc.
- ``TestLruValidation``    — Check #3 cases: NULL endpoints, cross-project
- ``TestSignalTypeFilter`` — optional Check #4
- ``TestUnknownPermissive``— UNKNOWN direction emits a warning but proposes
- ``TestConnectionBuilderRouter`` — three POST endpoints end-to-end

Each test creates the minimum (System, Unit, Connector, Pin × N, Interface)
graph it needs. Database isolation is per-function via the conftest ``db_session``.
"""

from __future__ import annotations

import pytest

from app.models import Project, User, UserRole
from app.models.catalog import SignalDirection
from app.models.interface import (
    Connector,
    ConnectorGender,
    ConnectorType,
    Interface,
    InterfaceCriticality,
    InterfaceDirection,
    InterfaceStatus,
    InterfaceType,
    Pin,
    PinDirection,
    SignalType,
    System,
    SystemStatus,
    SystemType,
    Unit,
    UnitStatus,
    UnitType,
)
from app.services.interface.auto_wire import (
    AutoWireOptions,
    auto_wire_interface,
)
from app.services.interface.direction_matrix import is_direction_compatible
from tests.conftest import make_user


# ══════════════════════════════════════════════════════════════
#  Fixtures — minimum graph builder
# ══════════════════════════════════════════════════════════════


def _mk_system(db, project, name: str) -> System:
    s = System(
        system_id=f"SYS-{name[:3].upper()}",
        name=name,
        abbreviation=name[:3].upper(),
        system_type=SystemType.SUBSYSTEM,
        status=SystemStatus.CONCEPT,
        project_id=project.id,
        owner_id=project.owner_id,
    )
    db.add(s)
    db.flush()
    return s


def _mk_unit(db, project, system, name: str) -> Unit:
    u = Unit(
        unit_id=f"U-{name[:3].upper()}",
        name=name,
        designation=name,
        part_number=f"PN-{name}",
        manufacturer="ACME",
        unit_type=UnitType.LRU,
        status=UnitStatus.CONCEPT,
        system_id=system.id,
        project_id=project.id,
    )
    db.add(u)
    db.flush()
    return u


def _mk_connector(db, unit, designator: str, contacts: int = 4) -> Connector:
    c = Connector(
        connector_id=f"CN-{designator}",
        designator=designator,
        connector_type=ConnectorType.MIL_DTL_38999_SERIES_III,
        gender=ConnectorGender.MALE_PIN,
        total_contacts=contacts,
        unit_id=unit.id,
        project_id=unit.project_id,
        owner_type="unit",
    )
    db.add(c)
    db.flush()
    return c


def _mk_pin(
    db,
    connector,
    pin_number: str,
    internal_name: str,
    *,
    direction: SignalDirection = SignalDirection.UNKNOWN,
    signal_type: SignalType = SignalType.SIGNAL_DIGITAL_SINGLE,
    legacy_direction: PinDirection = PinDirection.BIDIRECTIONAL,
) -> Pin:
    """Create a Pin row.

    The legacy ``PinDirection`` column is required (NOT NULL); we set it to
    BIDIRECTIONAL by default and use ``direction_override`` (the catalog-side
    SignalDirection enum) to drive the auto-wire decision.
    """
    p = Pin(
        pin_number=pin_number,
        signal_name=internal_name,
        internal_signal_name=internal_name,
        mfr_pin_name=internal_name,
        signal_type=signal_type,
        direction=legacy_direction,
        direction_override=direction,
        connector_id=connector.id,
    )
    db.add(p)
    db.flush()
    return p


def _mk_interface(
    db,
    project,
    src_unit,
    tgt_unit,
    *,
    status: InterfaceStatus = InterfaceStatus.PROPOSED,
) -> Interface:
    iface = Interface(
        interface_id=f"IF-{src_unit.id}-{tgt_unit.id}",
        name=f"{src_unit.designation} ↔ {tgt_unit.designation}",
        interface_type=InterfaceType.DATA_DIGITAL,
        direction=InterfaceDirection.BIDIRECTIONAL,
        source_system_id=src_unit.system_id,
        target_system_id=tgt_unit.system_id,
        source_unit_id=src_unit.id,
        target_unit_id=tgt_unit.id,
        status=status,
        criticality=InterfaceCriticality.NON_CRITICAL,
        project_id=project.id,
        owner_id=project.owner_id,
    )
    db.add(iface)
    db.commit()
    db.refresh(iface)
    return iface


@pytest.fixture()
def graph(db_session, test_user, test_project):
    """Two units (Radar, C2), one project. No pins yet."""
    sys_radar = _mk_system(db_session, test_project, "Radar")
    sys_c2    = _mk_system(db_session, test_project, "C2")
    unit_radar = _mk_unit(db_session, test_project, sys_radar, "RADAR")
    unit_c2    = _mk_unit(db_session, test_project, sys_c2, "C2")
    conn_radar = _mk_connector(db_session, unit_radar, "J1")
    conn_c2    = _mk_connector(db_session, unit_c2, "J1")
    db_session.commit()
    return {
        "project": test_project,
        "user": test_user,
        "src_unit": unit_radar,
        "tgt_unit": unit_c2,
        "src_connector": conn_radar,
        "tgt_connector": conn_c2,
    }


# ══════════════════════════════════════════════════════════════
#  TestDirectionMatrix — every cell of the 6×6
# ══════════════════════════════════════════════════════════════

# (src, tgt, expected_compatible) — the verbatim matrix from digest §6
_MATRIX_CASES: list[tuple[SignalDirection, SignalDirection, bool]] = []
_DIRECTIONS = list(SignalDirection)  # INPUT, OUTPUT, BIDIR, POWER, GROUND, UNKNOWN

# Compatible cells (per digest §6 — every other cell is False)
_COMPAT = {
    (SignalDirection.INPUT, SignalDirection.OUTPUT),
    (SignalDirection.OUTPUT, SignalDirection.INPUT),
    (SignalDirection.INPUT, SignalDirection.BIDIRECTIONAL),
    (SignalDirection.BIDIRECTIONAL, SignalDirection.INPUT),
    (SignalDirection.OUTPUT, SignalDirection.BIDIRECTIONAL),
    (SignalDirection.BIDIRECTIONAL, SignalDirection.OUTPUT),
    (SignalDirection.BIDIRECTIONAL, SignalDirection.BIDIRECTIONAL),
    (SignalDirection.POWER, SignalDirection.POWER),
    (SignalDirection.GROUND, SignalDirection.GROUND),
}
for s in _DIRECTIONS:
    for t in _DIRECTIONS:
        # UNKNOWN-permissive overrides everything.
        if s == SignalDirection.UNKNOWN or t == SignalDirection.UNKNOWN:
            _MATRIX_CASES.append((s, t, True))
        else:
            _MATRIX_CASES.append((s, t, (s, t) in _COMPAT))


class TestDirectionMatrix:
    """Parameterized walk of every cell of the 6×6 matrix per digest §6."""

    @pytest.mark.parametrize("src,tgt,expected", _MATRIX_CASES)
    def test_matrix_cell(self, src, tgt, expected):
        compat, reason = is_direction_compatible(src, tgt)
        assert compat is expected, (
            f"({src.value},{tgt.value}) expected={expected} got={compat} reason={reason}"
        )
        if compat and (src == SignalDirection.UNKNOWN or tgt == SignalDirection.UNKNOWN):
            # UNKNOWN-permissive must include a warning string
            assert reason is not None
        if not compat:
            assert reason is not None and len(reason) > 0


# ══════════════════════════════════════════════════════════════
#  TestNameMatching — Check #1
# ══════════════════════════════════════════════════════════════


class TestNameMatching:

    def test_all_three_checks_pass(self, db_session, graph):
        # Single matching name, INPUT↔OUTPUT, same project
        _mk_pin(
            db_session, graph["src_connector"], "1", "DATA_TX",
            direction=SignalDirection.OUTPUT,
        )
        _mk_pin(
            db_session, graph["tgt_connector"], "1", "DATA_TX",
            direction=SignalDirection.INPUT,
        )
        iface = _mk_interface(
            db_session, graph["project"], graph["src_unit"], graph["tgt_unit"]
        )

        result = auto_wire_interface(db_session, iface.id)
        assert result.lru_validation_errors == []
        assert len(result.proposed_wires) == 1
        proposed = result.proposed_wires[0]
        assert proposed.matched_signal_name == "data_tx"
        assert proposed.suggestion.gauge in {"awg_22", "awg_24", "awg_26"}
        assert proposed.suggestion.color in {"white", "blue"}
        # Direction pair preserved
        assert proposed.direction_pair == ("output", "input")

    def test_unmatched_source_when_no_target(self, db_session, graph):
        _mk_pin(
            db_session, graph["src_connector"], "1", "ORPHAN_SIGNAL",
            direction=SignalDirection.OUTPUT,
        )
        # Target has a totally unrelated pin
        _mk_pin(
            db_session, graph["tgt_connector"], "1", "OTHER_PIN",
            direction=SignalDirection.INPUT,
        )
        iface = _mk_interface(
            db_session, graph["project"], graph["src_unit"], graph["tgt_unit"]
        )

        result = auto_wire_interface(db_session, iface.id)
        assert len(result.proposed_wires) == 0
        assert len(result.unmatched_source) == 1
        assert result.unmatched_source[0].internal_signal_name == "ORPHAN_SIGNAL"
        assert len(result.unmatched_target) == 1
        assert result.unmatched_target[0].internal_signal_name == "OTHER_PIN"

    def test_ambiguous_match_never_paired(self, db_session, graph):
        _mk_pin(
            db_session, graph["src_connector"], "1", "CLK",
            direction=SignalDirection.OUTPUT,
        )
        # Two target pins with the same internal_signal_name → ambiguous
        _mk_pin(
            db_session, graph["tgt_connector"], "1", "CLK",
            direction=SignalDirection.INPUT,
        )
        _mk_pin(
            db_session, graph["tgt_connector"], "2", "CLK",
            direction=SignalDirection.INPUT,
        )
        iface = _mk_interface(
            db_session, graph["project"], graph["src_unit"], graph["tgt_unit"]
        )

        result = auto_wire_interface(db_session, iface.id)
        assert len(result.proposed_wires) == 0, (
            "Ambiguous match must NEVER auto-pair"
        )
        assert len(result.ambiguous) == 1
        assert len(result.ambiguous[0].candidates) == 2


# ══════════════════════════════════════════════════════════════
#  TestDirectionConflict — Check #2
# ══════════════════════════════════════════════════════════════


class TestDirectionConflict:

    def test_output_to_output_rejected(self, db_session, graph):
        _mk_pin(
            db_session, graph["src_connector"], "1", "BUS_A",
            direction=SignalDirection.OUTPUT,
        )
        _mk_pin(
            db_session, graph["tgt_connector"], "1", "BUS_A",
            direction=SignalDirection.OUTPUT,
        )
        iface = _mk_interface(
            db_session, graph["project"], graph["src_unit"], graph["tgt_unit"]
        )
        result = auto_wire_interface(db_session, iface.id)
        assert len(result.proposed_wires) == 0
        assert len(result.direction_conflicts) == 1
        assert result.direction_conflicts[0].src_direction == "output"
        assert result.direction_conflicts[0].tgt_direction == "output"
        assert "contention" in result.direction_conflicts[0].reason.lower()

    def test_power_to_ground_rejected(self, db_session, graph):
        _mk_pin(
            db_session, graph["src_connector"], "1", "VCC_28V",
            direction=SignalDirection.POWER, signal_type=SignalType.POWER_PRIMARY,
        )
        _mk_pin(
            db_session, graph["tgt_connector"], "1", "VCC_28V",
            direction=SignalDirection.GROUND, signal_type=SignalType.SIGNAL_GROUND,
        )
        iface = _mk_interface(
            db_session, graph["project"], graph["src_unit"], graph["tgt_unit"]
        )
        result = auto_wire_interface(db_session, iface.id)
        assert len(result.proposed_wires) == 0
        assert len(result.direction_conflicts) == 1
        reason = result.direction_conflicts[0].reason.lower()
        assert (
            "short" in reason or "rail" in reason or "polarity" in reason
        ), f"unexpected reason: {reason!r}"

    def test_bidirectional_pairs_all_compatible(self, db_session, graph):
        # BIDI ↔ INPUT, BIDI ↔ OUTPUT, BIDI ↔ BIDI
        for i, (src_dir, tgt_dir, name) in enumerate([
            (SignalDirection.BIDIRECTIONAL, SignalDirection.INPUT, "BIDI_TO_IN"),
            (SignalDirection.BIDIRECTIONAL, SignalDirection.OUTPUT, "BIDI_TO_OUT"),
            (SignalDirection.BIDIRECTIONAL, SignalDirection.BIDIRECTIONAL, "BIDI_TO_BIDI"),
        ]):
            _mk_pin(db_session, graph["src_connector"], str(i + 1), name, direction=src_dir)
            _mk_pin(db_session, graph["tgt_connector"], str(i + 1), name, direction=tgt_dir)
        iface = _mk_interface(
            db_session, graph["project"], graph["src_unit"], graph["tgt_unit"]
        )
        result = auto_wire_interface(db_session, iface.id)
        assert len(result.proposed_wires) == 3
        assert len(result.direction_conflicts) == 0


# ══════════════════════════════════════════════════════════════
#  TestLruValidation — Check #3
# ══════════════════════════════════════════════════════════════


class TestLruValidation:

    def test_null_source_unit_rejected(self, db_session, graph):
        # Build interface but null out source_unit_id
        iface = _mk_interface(
            db_session, graph["project"], graph["src_unit"], graph["tgt_unit"]
        )
        iface.source_unit_id = None
        db_session.commit()
        result = auto_wire_interface(db_session, iface.id)
        assert any("source_unit_id" in e for e in result.lru_validation_errors)
        assert len(result.proposed_wires) == 0

    def test_cross_project_units_rejected(self, db_session, test_user, graph):
        # Build a separate project + unit
        other_project = Project(
            code="OTHR",
            name="Other Project",
            description="Cross-project test",
            owner_id=test_user.id,
            status="active",
        )
        db_session.add(other_project)
        db_session.commit()
        sys_other = _mk_system(db_session, other_project, "OtherSys")
        unit_other = _mk_unit(db_session, other_project, sys_other, "OTHER")
        db_session.commit()

        iface = _mk_interface(
            db_session, graph["project"], graph["src_unit"], graph["tgt_unit"]
        )
        iface.target_unit_id = unit_other.id
        db_session.commit()

        result = auto_wire_interface(db_session, iface.id)
        assert any("cross-project" in e.lower() for e in result.lru_validation_errors)
        assert len(result.proposed_wires) == 0

    def test_enforce_lru_endpoints_false_allows_cross_project(
        self, db_session, test_user, graph, caplog
    ):
        """Dev-only escape hatch: cross-project allowed but must log a warning."""
        other_project = Project(
            code="OTH2",
            name="Other Project 2",
            description="Cross-project bypass test",
            owner_id=test_user.id,
            status="active",
        )
        db_session.add(other_project)
        db_session.commit()
        sys_other = _mk_system(db_session, other_project, "OtherSys2")
        unit_other = _mk_unit(db_session, other_project, sys_other, "OTHER2")
        conn_other = _mk_connector(db_session, unit_other, "J1")
        _mk_pin(
            db_session, graph["src_connector"], "1", "TEST",
            direction=SignalDirection.OUTPUT,
        )
        _mk_pin(
            db_session, conn_other, "1", "TEST",
            direction=SignalDirection.INPUT,
        )
        db_session.commit()

        iface = _mk_interface(
            db_session, graph["project"], graph["src_unit"], graph["tgt_unit"]
        )
        iface.target_unit_id = unit_other.id
        db_session.commit()

        opts = AutoWireOptions(enforce_lru_endpoints=False)
        import logging
        caplog.set_level(logging.WARNING, logger="app.services.interface.auto_wire")
        result = auto_wire_interface(db_session, iface.id, opts)
        assert any("enforce_lru_endpoints=False" in r.message for r in caplog.records)
        # Wire still proposed in dev-mode bypass
        assert len(result.proposed_wires) == 1


# ══════════════════════════════════════════════════════════════
#  TestUnknownPermissive — UNKNOWN escape hatch
# ══════════════════════════════════════════════════════════════


class TestUnknownPermissive:

    def test_unknown_both_sides_proposed_with_warning(self, db_session, graph):
        _mk_pin(
            db_session, graph["src_connector"], "1", "UNKWN",
            direction=SignalDirection.UNKNOWN,
        )
        _mk_pin(
            db_session, graph["tgt_connector"], "1", "UNKWN",
            direction=SignalDirection.UNKNOWN,
        )
        iface = _mk_interface(
            db_session, graph["project"], graph["src_unit"], graph["tgt_unit"]
        )
        result = auto_wire_interface(db_session, iface.id)
        assert len(result.proposed_wires) == 1
        proposed = result.proposed_wires[0]
        assert proposed.warning is not None
        assert "UNKNOWN" in proposed.warning
        assert proposed.confidence == "low"


# ══════════════════════════════════════════════════════════════
#  TestNoConnect / Chassis filters
# ══════════════════════════════════════════════════════════════


class TestPreFilters:

    def test_no_connect_pins_skipped_by_default(self, db_session, graph):
        _mk_pin(
            db_session, graph["src_connector"], "1", "NC",
            direction=SignalDirection.UNKNOWN,
            signal_type=SignalType.NO_CONNECT,
        )
        _mk_pin(
            db_session, graph["tgt_connector"], "1", "NC",
            direction=SignalDirection.UNKNOWN,
            signal_type=SignalType.NO_CONNECT,
        )
        iface = _mk_interface(
            db_session, graph["project"], graph["src_unit"], graph["tgt_unit"]
        )
        result = auto_wire_interface(db_session, iface.id)
        assert len(result.proposed_wires) == 0


# ══════════════════════════════════════════════════════════════
#  TestConnectionBuilderRouter — three POST endpoints end-to-end
# ══════════════════════════════════════════════════════════════


class TestConnectionBuilderRouter:

    def _seed_units(self, db_session, test_user, test_project):
        """Two units, one connector each, paired pins."""
        from app.models.project_member import ProjectMember
        sys_a = _mk_system(db_session, test_project, "SysA")
        sys_b = _mk_system(db_session, test_project, "SysB")
        ua = _mk_unit(db_session, test_project, sys_a, "UA")
        ub = _mk_unit(db_session, test_project, sys_b, "UB")
        ca = _mk_connector(db_session, ua, "J1")
        cb = _mk_connector(db_session, ub, "J1")
        _mk_pin(db_session, ca, "1", "DATA",  direction=SignalDirection.OUTPUT)
        _mk_pin(db_session, ca, "2", "CLK",   direction=SignalDirection.OUTPUT)
        _mk_pin(db_session, cb, "1", "DATA",  direction=SignalDirection.INPUT)
        _mk_pin(db_session, cb, "2", "CLK",   direction=SignalDirection.INPUT)
        db_session.commit()
        return ua, ub

    def test_cb_start_creates_draft_interface(
        self, client, db_session, test_user, test_project, auth_headers
    ):
        ua, ub = self._seed_units(db_session, test_user, test_project)
        resp = client.post(
            "/api/v1/interfaces/connection-builder/start",
            json={
                "project_id": test_project.id,
                "source_unit_id": ua.id,
                "target_unit_id": ub.id,
            },
            headers=auth_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["source_unit_id"] == ua.id
        assert body["target_unit_id"] == ub.id
        assert body["status"] == "proposed"

    def test_cb_auto_suggest_returns_proposed_wires(
        self, client, db_session, test_user, test_project, auth_headers
    ):
        ua, ub = self._seed_units(db_session, test_user, test_project)
        # Start
        start = client.post(
            "/api/v1/interfaces/connection-builder/start",
            json={
                "project_id": test_project.id,
                "source_unit_id": ua.id,
                "target_unit_id": ub.id,
            },
            headers=auth_headers,
        )
        iface_id = start.json()["interface_id"]
        # Suggest
        suggest = client.post(
            f"/api/v1/interfaces/connection-builder/{iface_id}/auto-suggest-wires",
            json={},
            headers=auth_headers,
        )
        assert suggest.status_code == 200, suggest.text
        body = suggest.json()
        assert body["interface_id"] == iface_id
        assert body["summary"]["proposed"] == 2
        assert body["summary"]["direction_conflicts"] == 0
        assert len(body["proposed_wires"]) == 2

    def test_cb_commit_creates_harness_and_wires(
        self, client, db_session, test_user, test_project, auth_headers
    ):
        ua, ub = self._seed_units(db_session, test_user, test_project)
        start = client.post(
            "/api/v1/interfaces/connection-builder/start",
            json={
                "project_id": test_project.id,
                "source_unit_id": ua.id,
                "target_unit_id": ub.id,
            },
            headers=auth_headers,
        )
        iface_id = start.json()["interface_id"]
        suggest = client.post(
            f"/api/v1/interfaces/connection-builder/{iface_id}/auto-suggest-wires",
            json={},
            headers=auth_headers,
        )
        proposed = suggest.json()["proposed_wires"]
        accepted = [
            {
                "source_pin_id": pw["source_pin"]["id"],
                "target_pin_id": pw["target_pin"]["id"],
                "wire_gauge": pw["suggestion"]["gauge"],
                "wire_color": pw["suggestion"]["color"],
            }
            for pw in proposed
        ]
        commit = client.post(
            f"/api/v1/interfaces/connection-builder/{iface_id}/commit",
            json={
                "accepted_wires": accepted,
                "harness": {
                    "name": "Test Harness",
                    "cable_type": "MIL-C-27500",
                    "overall_length_m": 1.5,
                },
            },
            headers=auth_headers,
        )
        assert commit.status_code == 201, commit.text
        body = commit.json()
        assert body["wires_created"] == 2
        assert len(body["wire_ids"]) == 2

    def test_cb_commit_atomic_on_validation_failure(
        self, client, db_session, test_user, test_project, auth_headers
    ):
        """Mismatched pin id (not on either unit) should 400 and create nothing."""
        ua, ub = self._seed_units(db_session, test_user, test_project)
        start = client.post(
            "/api/v1/interfaces/connection-builder/start",
            json={
                "project_id": test_project.id,
                "source_unit_id": ua.id,
                "target_unit_id": ub.id,
            },
            headers=auth_headers,
        )
        iface_id = start.json()["interface_id"]
        # Pin id 99999 is not on either unit
        commit = client.post(
            f"/api/v1/interfaces/connection-builder/{iface_id}/commit",
            json={
                "accepted_wires": [
                    {"source_pin_id": 99999, "target_pin_id": 99998}
                ],
                "harness": {"name": "BadHarness"},
            },
            headers=auth_headers,
        )
        assert commit.status_code == 400
        # No harness should have been created
        from app.models.interface import WireHarness
        assert (
            db_session.query(WireHarness)
            .filter(WireHarness.name == "BadHarness")
            .count() == 0
        )
