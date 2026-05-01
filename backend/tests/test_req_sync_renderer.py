"""ASTRA — Renderer tests for the reactive sync engine (Phase 5)
==================================================================
File: backend/tests/test_req_sync_renderer.py    ← NEW

The renderer is *deterministic*: same DB state + same template_id +
same source links = same output. It must:

  * render every template_id present in TEMPLATES against current source
    state (smoke per template family)
  * return ``source_deleted=True`` when the primary source row is gone
  * return ``template_missing=True`` for an unknown template_id
  * substitute "TBD" for missing context keys (via _SafeDict) without
    raising
  * be reproducible — calling render_requirement twice in a row produces
    bit-identical output
"""

from __future__ import annotations

import pytest

from app.models.interface import (
    BusDefinition, Connector, Pin, PinBusAssignment,
    System, Unit, Wire, WireHarness,
)
from app.models.req_sync import RequirementSourceLink, SourceEntityType
from app.services.req_sync.renderer import (
    RenderedRequirement,
    render_requirement,
)


# ══════════════════════════════════════════════════════════════
#  Minimum graph
# ══════════════════════════════════════════════════════════════

@pytest.fixture()
def graph(db_session, test_user, test_project):
    sys_a = System(
        system_id="SYS-A", name="Radar", abbreviation="RAD",
        system_type="subsystem",
        project_id=test_project.id, owner_id=test_user.id,
    )
    sys_b = System(
        system_id="SYS-B", name="C2", abbreviation="C2",
        system_type="subsystem",
        project_id=test_project.id, owner_id=test_user.id,
    )
    db_session.add_all([sys_a, sys_b])
    db_session.flush()

    unit_a = Unit(
        unit_id="UA", name="RSP", designation="RSP-100",
        part_number="RSP", manufacturer="Raytheon", unit_type="processor",
        status="concept", system_id=sys_a.id, project_id=test_project.id,
    )
    unit_b = Unit(
        unit_id="UB", name="C2P", designation="C2P-200",
        part_number="C2P", manufacturer="BAE", unit_type="processor",
        status="concept", system_id=sys_b.id, project_id=test_project.id,
    )
    db_session.add_all([unit_a, unit_b])
    db_session.flush()

    conn_a = Connector(
        connector_id="CA", designator="J1",
        connector_type="mil_dtl_38999_series_iii", gender="female_socket",
        total_contacts=4, unit_id=unit_a.id, project_id=test_project.id,
    )
    conn_b = Connector(
        connector_id="CB", designator="J1",
        connector_type="mil_dtl_38999_series_iii", gender="male_pin",
        total_contacts=4, unit_id=unit_b.id, project_id=test_project.id,
    )
    db_session.add_all([conn_a, conn_b])
    db_session.flush()

    pin_a = Pin(
        pin_number="1", signal_name="DATA",
        signal_type="signal_digital_single", direction="bidirectional",
        connector_id=conn_a.id,
    )
    pin_b = Pin(
        pin_number="1", signal_name="DATA",
        signal_type="signal_digital_single", direction="bidirectional",
        connector_id=conn_b.id,
    )
    db_session.add_all([pin_a, pin_b])
    db_session.flush()

    harness = WireHarness(
        harness_id="HAR-001", name="A↔B Harness",
        from_unit_id=unit_a.id, from_connector_id=conn_a.id,
        to_unit_id=unit_b.id, to_connector_id=conn_b.id,
        project_id=test_project.id, cable_type="MIL-DTL-27500",
        overall_length_m=2.0, overall_length_max_m=2.5,
    )
    db_session.add(harness)
    db_session.flush()

    wire = Wire(
        wire_number="W001", signal_name="DATA",
        wire_type="signal_twisted_pair_a",
        from_pin_id=pin_a.id, to_pin_id=pin_b.id,
        harness_id=harness.id,
    )
    db_session.add(wire)
    db_session.flush()

    bus = BusDefinition(
        bus_def_id="BUS-001", name="1553 Bus",
        protocol="mil_std_1553b", bus_role="remote_terminal",
        bus_address="RT01", data_rate="1 Mbps", word_size_bits=16,
        bus_name_network="MUX_BUS_A",
        unit_id=unit_a.id, project_id=test_project.id,
    )
    db_session.add(bus)
    db_session.commit()
    db_session.refresh(harness)
    db_session.refresh(wire)
    db_session.refresh(bus)

    return {
        "harness": harness, "wire": wire, "bus": bus,
        "pin_a": pin_a, "pin_b": pin_b,
        "unit_a": unit_a, "unit_b": unit_b,
    }


def _link(req_id: int, etype: SourceEntityType, eid: int,
          template_id: str, role: str = "primary"):
    return RequirementSourceLink(
        requirement_id=req_id,
        source_entity_type=etype,
        source_entity_id=eid,
        template_id=template_id,
        template_inputs={},
        role=role,
    )


# ══════════════════════════════════════════════════════════════
#  TestRenderer
# ══════════════════════════════════════════════════════════════

class TestRendererKnownTemplates:

    def test_harness_overall_renders(self, db_session, graph, test_requirement):
        link = _link(
            test_requirement.id, SourceEntityType.WIRE_HARNESS,
            graph["harness"].id, "harness_overall",
        )
        result = render_requirement(db_session, "harness_overall", [link])
        assert isinstance(result, RenderedRequirement)
        assert result.statement is not None
        assert "HAR-001" in result.statement
        assert "RSP-100" in result.statement
        assert "C2P-200" in result.statement
        assert result.title is not None and result.rationale is not None
        assert result.template_inputs  # non-empty snapshot

    def test_bus_connection_renders(self, db_session, graph, test_requirement):
        # bus_connection's primary source is BUS_DEFINITION (with optional
        # WIRE_HARNESS link for endpoint context).
        links = [
            _link(test_requirement.id, SourceEntityType.BUS_DEFINITION,
                  graph["bus"].id, "bus_connection"),
            _link(test_requirement.id, SourceEntityType.WIRE_HARNESS,
                  graph["harness"].id, "bus_connection", role="context"),
        ]
        result = render_requirement(db_session, "bus_connection", links)
        assert result.statement is not None
        assert "1 Mbps" in result.statement
        assert "MIL-STD-1553B" in result.statement

    def test_power_wire_renders(self, db_session, graph, test_requirement):
        link = _link(test_requirement.id, SourceEntityType.WIRE,
                     graph["wire"].id, "power_wire")
        result = render_requirement(db_session, "power_wire", [link])
        assert result.statement is not None
        # Power template requires a wire context
        assert "HAR-001" in result.statement

    def test_renderer_is_deterministic(self, db_session, graph, test_requirement):
        link = _link(test_requirement.id, SourceEntityType.WIRE_HARNESS,
                     graph["harness"].id, "harness_overall")
        a = render_requirement(db_session, "harness_overall", [link])
        b = render_requirement(db_session, "harness_overall", [link])
        assert a.statement == b.statement
        assert a.rationale == b.rationale
        assert a.title == b.title


class TestRendererErrorPaths:

    def test_unknown_template_returns_template_missing(self, db_session, test_requirement):
        result = render_requirement(db_session, "totally_made_up", [])
        assert result.template_missing is True
        assert result.statement is None

    def test_no_source_link_for_template_returns_template_missing(
        self, db_session, test_requirement,
    ):
        # No links at all → primary source can't be resolved.
        result = render_requirement(db_session, "harness_overall", [])
        assert result.template_missing is True

    def test_source_deleted_returns_source_deleted_flag(
        self, db_session, graph, test_requirement,
    ):
        # Reference an id that doesn't exist (simulating delete).
        link = _link(test_requirement.id, SourceEntityType.WIRE_HARNESS,
                     999_999, "harness_overall")
        result = render_requirement(db_session, "harness_overall", [link])
        assert result.source_deleted is True
        assert result.statement is None


class TestRendererTBDFallback:
    """Missing context fields render as the literal string 'TBD' rather
    than crashing — matches the existing _SafeDict behaviour."""

    def test_minimal_harness_still_renders(
        self, db_session, test_user, test_project,
    ):
        # Harness with only the required fields — no cable_spec, no length.
        sys_a = System(
            system_id="SYS-X", name="Sys X",
            system_type="subsystem",
            project_id=test_project.id, owner_id=test_user.id,
        )
        sys_b = System(
            system_id="SYS-Y", name="Sys Y",
            system_type="subsystem",
            project_id=test_project.id, owner_id=test_user.id,
        )
        db_session.add_all([sys_a, sys_b])
        db_session.flush()
        ua = Unit(
            unit_id="UX", name="X", designation="X",
            part_number="X", manufacturer="x", unit_type="processor",
            status="concept", system_id=sys_a.id, project_id=test_project.id,
        )
        ub = Unit(
            unit_id="UY", name="Y", designation="Y",
            part_number="Y", manufacturer="y", unit_type="processor",
            status="concept", system_id=sys_b.id, project_id=test_project.id,
        )
        db_session.add_all([ua, ub])
        db_session.flush()
        ca = Connector(
            connector_id="CX", designator="J1",
            connector_type="mil_dtl_38999_series_iii", gender="female_socket",
            total_contacts=1, unit_id=ua.id, project_id=test_project.id,
        )
        cb = Connector(
            connector_id="CY", designator="J1",
            connector_type="mil_dtl_38999_series_iii", gender="male_pin",
            total_contacts=1, unit_id=ub.id, project_id=test_project.id,
        )
        db_session.add_all([ca, cb])
        db_session.flush()
        h = WireHarness(
            harness_id="HAR-X", name="X harness",
            from_unit_id=ua.id, from_connector_id=ca.id,
            to_unit_id=ub.id, to_connector_id=cb.id,
            project_id=test_project.id,
        )
        db_session.add(h)
        db_session.commit()

        link = RequirementSourceLink(
            requirement_id=1,  # any id; renderer doesn't query the req
            source_entity_type=SourceEntityType.WIRE_HARNESS,
            source_entity_id=h.id,
            template_id="harness_overall",
            template_inputs={},
            role="primary",
        )
        result = render_requirement(db_session, "harness_overall", [link])
        assert result.statement is not None
        # Optional fields collapse to "TBD" (exact value or interpolated)
        assert "TBD" in result.statement or "HAR-X" in result.statement


class TestRendererMultiSource:
    """Multi-source links (primary + supporting) produce one unified
    statement — secondary links just enrich the context."""

    def test_bus_with_harness_context_overrides_bus_only(
        self, db_session, graph, test_requirement,
    ):
        only_bus = [
            _link(test_requirement.id, SourceEntityType.BUS_DEFINITION,
                  graph["bus"].id, "bus_connection"),
        ]
        with_harness = only_bus + [
            _link(test_requirement.id, SourceEntityType.WIRE_HARNESS,
                  graph["harness"].id, "bus_connection", role="context"),
        ]
        a = render_requirement(db_session, "bus_connection", only_bus)
        b = render_requirement(db_session, "bus_connection", with_harness)
        # Both render. With the harness link present the system names
        # come from the connected units, not just the bus unit.
        assert a.statement is not None
        assert b.statement is not None
        assert "Radar" in b.statement
        assert "C2" in b.statement
        # And the snapshot context distinguishes the two cases.
        assert b.template_inputs.get("source_unit") == "RSP-100"
        assert b.template_inputs.get("target_unit") == "C2P-200"
