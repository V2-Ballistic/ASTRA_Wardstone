"""
ASTRA — System Architecture router (TDD-SYSARCH-002 Phase 1)
=============================================================

Mounts at ``/api/v1/system-architecture``. Single endpoint:

    GET /system-architecture/graph?project_id=N

Returns a single round-trip payload of all the systems, units, and
edges (parent_of / contains / connects_to) the new System Architecture
page needs to render its force graph.

Coexists with ``/api/v1/interfaces/block-diagram`` — that endpoint
stays unchanged and remains the system-level data source for the
existing Interface Management views.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.dependencies.project_access import project_member_required
from app.models import Project, User
from app.models.catalog import CatalogPart
from app.models.interface import Interface, System, Unit, WireHarness


logger = logging.getLogger("astra.system_architecture")
router = APIRouter(prefix="/system-architecture", tags=["System Architecture"])


# ─────────────────────────────────────────────────────────────────
#  Limits — page rendering performance budget
# ─────────────────────────────────────────────────────────────────

MAX_SYSTEMS_PER_PROJECT = 200
MAX_UNITS_PER_PROJECT = 1000


# ─────────────────────────────────────────────────────────────────
#  Color hints — the same palette the existing /interfaces views use
#  so the new graph stays visually consistent. Add system_type rows as
#  the page picks up more of the SystemType enum.
# ─────────────────────────────────────────────────────────────────

_SYSTEM_TYPE_COLORS: Dict[str, str] = {
    "vehicle":              "#3B82F6",  # blue
    "payload":              "#A78BFA",  # violet
    "ground_segment":       "#10B981",  # emerald
    "communication":        "#22D3EE",  # cyan
    "data_handling":        "#06B6D4",  # cyan-600
    "guidance_nav_control": "#F59E0B",  # amber
    "propulsion":           "#EF4444",  # red
    "power_system":         "#FBBF24",  # yellow
    "thermal_system":       "#F97316",  # orange
    "structural":           "#94A3B8",  # slate
    "sensor_suite":         "#84CC16",  # lime
    "actuator_assembly":    "#EC4899",  # pink
    "processor_unit":       "#8B5CF6",  # violet-500
    "antenna_system":       "#14B8A6",  # teal
    "ordnance":             "#DC2626",  # red-600
    "test_equipment":       "#64748B",  # slate-500
    "external_system":      "#6B7280",  # grey
    "software":             "#0EA5E9",  # sky
    "firmware":             "#0369A1",  # sky-700
    "lru":                  "#3B82F6",
    "sru":                  "#60A5FA",
    "wru":                  "#1D4ED8",
    "subsystem":            "#7C3AED",
    "custom":               "#94A3B8",
}

_UNIT_TYPE_COLORS: Dict[str, str] = {
    "lru":               "#3B82F6",
    "sru":               "#60A5FA",
    "wru":               "#1D4ED8",
    "cca":               "#22D3EE",
    "pcb":               "#06B6D4",
    "processor":         "#8B5CF6",
    "fpga":              "#A78BFA",
    "asic":              "#7C3AED",
    "sensor":            "#84CC16",
    "actuator":          "#EC4899",
    "motor":             "#EF4444",
    "power_supply":      "#FBBF24",
    "battery":           "#F59E0B",
    "antenna":           "#14B8A6",
    "transmitter":       "#10B981",
    "receiver":          "#22C55E",
    "transceiver":       "#0EA5E9",
    "cable_assembly":    "#94A3B8",
    "connector_assembly": "#64748B",
}


def _color_for_system(system_type: Optional[str]) -> str:
    if not system_type:
        return "#94A3B8"
    return _SYSTEM_TYPE_COLORS.get(system_type.lower(), "#94A3B8")


def _color_for_unit(unit_type: Optional[str]) -> str:
    if not unit_type:
        return "#94A3B8"
    return _UNIT_TYPE_COLORS.get(unit_type.lower(), "#94A3B8")


# ─────────────────────────────────────────────────────────────────
#  Response schemas
# ─────────────────────────────────────────────────────────────────

class SystemArchGraphNode(BaseModel):
    id: int
    type: Literal["system", "unit"]
    label: str
    parent_id: Optional[int] = None
    badge: Optional[str] = None
    status: Optional[str] = None
    color_hint: Optional[str] = None
    catalog_part_id: Optional[int] = None
    catalog_part_wpn: Optional[str] = None  # the catalog part_number for units


class SystemArchGraphEdge(BaseModel):
    source: int
    target: int
    source_type: Literal["system", "unit"]
    target_type: Literal["system", "unit"]
    edge_type: Literal["contains", "parent_of", "connects_to"]
    label: Optional[str] = None
    color_hint: Optional[str] = None


class SystemArchGraphResponse(BaseModel):
    systems: List[SystemArchGraphNode] = Field(default_factory=list)
    units: List[SystemArchGraphNode] = Field(default_factory=list)
    edges: List[SystemArchGraphEdge] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────
#  GET /system-architecture/graph
# ─────────────────────────────────────────────────────────────────

@router.get("/graph", response_model=SystemArchGraphResponse)
def get_graph(
    project_id: int = Query(..., description="Project to render"),
    db: Session = Depends(get_db),
    project: Project = Depends(project_member_required),
) -> SystemArchGraphResponse:
    """Single round-trip graph dataset for the System Architecture page.

    Project membership is enforced by ``project_member_required``.
    Returns 200 with empty arrays when the project has zero systems
    (do NOT 404 — UI prefers the empty-state branch).
    Returns 413 when system or unit counts exceed the rendering budget.
    """
    # ── Systems for the project ──
    systems: List[System] = (
        db.query(System)
        .filter(System.project_id == project_id)
        .order_by(System.id)
        .all()
    )
    if len(systems) > MAX_SYSTEMS_PER_PROJECT:
        raise HTTPException(
            413,
            f"Project has {len(systems)} systems (limit "
            f"{MAX_SYSTEMS_PER_PROJECT}). Filter or paginate at the UI.",
        )

    # ── Units, with catalog_part eagerly loaded for the WPN badge ──
    units: List[Unit] = (
        db.query(Unit)
        .options(joinedload(Unit.catalog_part))
        .filter(Unit.project_id == project_id)
        .order_by(Unit.id)
        .all()
    )
    if len(units) > MAX_UNITS_PER_PROJECT:
        raise HTTPException(
            413,
            f"Project has {len(units)} units (limit "
            f"{MAX_UNITS_PER_PROJECT}). Filter or paginate at the UI.",
        )

    unit_ids: List[int] = [u.id for u in units]

    # ── Build node lists ──
    sys_nodes: List[SystemArchGraphNode] = []
    for s in systems:
        s_type_str = s.system_type.value if hasattr(s.system_type, "value") else str(s.system_type)
        s_status_str = (
            s.status.value if (s.status is not None and hasattr(s.status, "value")) else str(s.status or "")
        )
        sys_nodes.append(SystemArchGraphNode(
            id=s.id,
            type="system",
            label=s.name,
            parent_id=s.parent_system_id,
            badge=s.abbreviation or s_type_str.upper()[:3],
            status=s_status_str or None,
            color_hint=_color_for_system(s_type_str),
        ))

    unit_nodes: List[SystemArchGraphNode] = []
    for u in units:
        u_type_str = u.unit_type.value if hasattr(u.unit_type, "value") else str(u.unit_type)
        u_status_str = (
            u.status.value if (u.status is not None and hasattr(u.status, "value")) else str(u.status or "")
        )
        cp: Optional[CatalogPart] = u.catalog_part
        unit_nodes.append(SystemArchGraphNode(
            id=u.id,
            type="unit",
            label=u.designation or u.name or f"unit-{u.id}",
            parent_id=u.system_id,
            badge=u_type_str.upper()[:3] if u_type_str else None,
            status=u_status_str or None,
            color_hint=_color_for_unit(u_type_str),
            catalog_part_id=u.catalog_part_id,
            catalog_part_wpn=cp.part_number if cp is not None else None,
        ))

    # ── Edges ──
    edges: List[SystemArchGraphEdge] = []

    # parent_of (system → child system)
    for s in systems:
        if s.parent_system_id is not None:
            edges.append(SystemArchGraphEdge(
                source=s.parent_system_id,
                target=s.id,
                source_type="system",
                target_type="system",
                edge_type="parent_of",
                color_hint="#475569",
            ))

    # contains (system → unit)
    for u in units:
        edges.append(SystemArchGraphEdge(
            source=u.system_id,
            target=u.id,
            source_type="system",
            target_type="unit",
            edge_type="contains",
            color_hint="#334155",
        ))

    # connects_to — dedup by ordered (source, target) unit pair so a
    # logical Interface and a physical WireHarness between the same
    # two units render as a single edge. Interface label wins (more
    # specific).
    if unit_ids:
        unit_id_set = set(unit_ids)

        connects_seen: Dict[Tuple[int, int], SystemArchGraphEdge] = {}

        # Logical interfaces (preferred label source)
        ifaces: List[Interface] = (
            db.query(Interface)
            .filter(
                Interface.project_id == project_id,
                Interface.source_unit_id.isnot(None),
                Interface.target_unit_id.isnot(None),
            )
            .all()
        )
        for iface in ifaces:
            su, tu = iface.source_unit_id, iface.target_unit_id
            if su not in unit_id_set or tu not in unit_id_set:
                continue
            key = (min(su, tu), max(su, tu))
            if key in connects_seen:
                continue
            it_str = (
                iface.interface_type.value
                if hasattr(iface.interface_type, "value")
                else str(iface.interface_type)
            )
            connects_seen[key] = SystemArchGraphEdge(
                source=su,
                target=tu,
                source_type="unit",
                target_type="unit",
                edge_type="connects_to",
                label=iface.name or it_str,
                color_hint="#3B82F6",
            )

        # Physical wire harnesses — only fill in pairs not already
        # claimed by a logical interface above. The harness label is
        # the harness name.
        harnesses: List[WireHarness] = (
            db.query(WireHarness)
            .filter(WireHarness.project_id == project_id)
            .all()
        )
        for h in harnesses:
            su, tu = h.from_unit_id, h.to_unit_id
            if su not in unit_id_set or tu not in unit_id_set:
                continue
            key = (min(su, tu), max(su, tu))
            if key in connects_seen:
                continue
            connects_seen[key] = SystemArchGraphEdge(
                source=su,
                target=tu,
                source_type="unit",
                target_type="unit",
                edge_type="connects_to",
                label=h.name,
                color_hint="#94A3B8",
            )

        edges.extend(connects_seen.values())

    return SystemArchGraphResponse(
        systems=sys_nodes,
        units=unit_nodes,
        edges=edges,
    )
