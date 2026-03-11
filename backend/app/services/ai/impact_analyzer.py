"""
ASTRA — Impact Analysis Engine
=================================
File: backend/app/services/ai/impact_analyzer.py   ← NEW

Core engine for automated impact analysis when a requirement changes.
Uses BFS graph traversal over the trace link network to identify all
directly and transitively affected entities.

Key capabilities:
  - analyze_impact():        full impact report with AI summary
  - get_dependency_chain():  upstream/downstream tree for visualization
  - preview_what_if():       preview before delete/modify
  - classify_risk():         risk level based on impact breadth and depth

Gracefully degrades without AI — graph traversal always works,
LLM summary is optional.
"""

import logging
import time
from collections import deque
from datetime import datetime
from typing import List, Dict, Optional, Set, Tuple, Any

from sqlalchemy.orm import Session
from sqlalchemy import and_

from app.models import (
    Requirement, TraceLink, Verification, Baseline,
    BaselineRequirement, SourceArtifact, RequirementHistory,
)
from app.schemas.impact import (
    ImpactReport, ImpactItem, AffectedVerification, AffectedBaseline,
    DependencyTree, DependencyNode, WhatIfPreview,
)

logger = logging.getLogger("astra.ai.impact")


# ══════════════════════════════════════
#  Helper: enum-safe value extraction
# ══════════════════════════════════════

def _ev(v) -> str:
    """Extract string from potential enum value."""
    return v.value if hasattr(v, "value") else str(v) if v else ""


# ══════════════════════════════════════
#  Graph Traversal Engine
# ══════════════════════════════════════

class _TraceGraph:
    """
    In-memory directed graph of trace link relationships.

    Builds an adjacency list from all trace links involving
    requirements in a project, then supports BFS traversal to
    find all reachable entities from a starting node.
    """

    def __init__(self, db: Session, project_id: int):
        self.db = db
        self.project_id = project_id
        self._adjacency: Dict[str, List[Tuple[str, str, int]]] = {}
        # node_key -> [(neighbor_key, link_type, link_id)]
        self._entity_cache: Dict[str, Dict[str, Any]] = {}
        self._build_graph()

    def _node_key(self, entity_type: str, entity_id: int) -> str:
        return f"{entity_type}:{entity_id}"

    def _build_graph(self):
        """Load all trace links for the project into the adjacency list."""
        # Get all requirement IDs in the project
        reqs = (
            self.db.query(Requirement)
            .filter(
                Requirement.project_id == self.project_id,
                Requirement.status != "deleted",
            )
            .all()
        )
        req_ids = {r.id for r in reqs}

        # Cache requirement metadata
        for r in reqs:
            key = self._node_key("requirement", r.id)
            self._entity_cache[key] = {
                "entity_type": "requirement",
                "entity_id": r.id,
                "identifier": r.req_id,
                "title": r.title,
                "status": _ev(r.status),
                "level": _ev(r.level) if hasattr(r, "level") else "L1",
                "statement": r.statement[:200] if r.statement else "",
            }

        if not req_ids:
            return

        # Load all trace links touching these requirements
        links = (
            self.db.query(TraceLink)
            .filter(
                ((TraceLink.source_type == "requirement") & (TraceLink.source_id.in_(req_ids)))
                | ((TraceLink.target_type == "requirement") & (TraceLink.target_id.in_(req_ids)))
            )
            .all()
        )

        for link in links:
            src_key = self._node_key(link.source_type, link.source_id)
            tgt_key = self._node_key(link.target_type, link.target_id)
            link_type = _ev(link.link_type) if link.link_type else "related"

            # Forward edge: source → target
            self._adjacency.setdefault(src_key, []).append(
                (tgt_key, link_type, link.id)
            )
            # Reverse edge: target → source
            self._adjacency.setdefault(tgt_key, []).append(
                (src_key, f"inv_{link_type}", link.id)
            )

        # Also include parent-child hierarchy as implicit edges
        for r in reqs:
            if r.parent_id and r.parent_id in req_ids:
                parent_key = self._node_key("requirement", r.parent_id)
                child_key = self._node_key("requirement", r.id)
                self._adjacency.setdefault(parent_key, []).append(
                    (child_key, "parent_of", -1)
                )
                self._adjacency.setdefault(child_key, []).append(
                    (parent_key, "child_of", -1)
                )

        # Cache verification metadata
        verifs = (
            self.db.query(Verification)
            .filter(Verification.requirement_id.in_(req_ids))
            .all()
        )
        for v in verifs:
            key = self._node_key("verification", v.id)
            self._entity_cache[key] = {
                "entity_type": "verification",
                "entity_id": v.id,
                "identifier": f"VER-{v.id:03d}",
                "title": f"{_ev(v.method).title()} verification for req {v.requirement_id}",
                "status": _ev(v.status),
                "level": "",
            }
            # Link verification to its requirement
            req_key = self._node_key("requirement", v.requirement_id)
            self._adjacency.setdefault(req_key, []).append(
                (key, "verified_by", -1)
            )
            self._adjacency.setdefault(key, []).append(
                (req_key, "verifies", -1)
            )

    def get_entity(self, key: str) -> Dict[str, Any]:
        """Get cached entity metadata, or a stub if not cached."""
        if key in self._entity_cache:
            return self._entity_cache[key]
        parts = key.split(":", 1)
        return {
            "entity_type": parts[0] if len(parts) > 0 else "unknown",
            "entity_id": int(parts[1]) if len(parts) > 1 else 0,
            "identifier": key,
            "title": "",
            "status": "",
            "level": "",
        }

    def bfs_all_affected(
        self,
        start_type: str,
        start_id: int,
        max_depth: int = 10,
    ) -> List[Tuple[str, int, List[Tuple[str, str]]]]:
        """
        BFS from a starting node. Returns all reachable nodes.

        Returns: [(node_key, hop_count, [(edge_label, through_key), ...]), ...]
        The path records the chain of edges from start to this node.
        """
        start_key = self._node_key(start_type, start_id)
        visited: Set[str] = {start_key}
        # queue items: (node_key, hop_count, path)
        queue: deque = deque([(start_key, 0, [])])
        results: List[Tuple[str, int, List[Tuple[str, str]]]] = []

        while queue:
            current, hops, path = queue.popleft()
            if hops > 0:
                results.append((current, hops, path))
            if hops >= max_depth:
                continue

            for neighbor, link_type, _ in self._adjacency.get(current, []):
                if neighbor not in visited:
                    visited.add(neighbor)
                    new_path = path + [(link_type, current)]
                    queue.append((neighbor, hops + 1, new_path))

        return results

    def get_directed_chain(
        self,
        start_type: str,
        start_id: int,
        direction: str = "downstream",
        max_depth: int = 10,
    ) -> List[Tuple[str, int, str]]:
        """
        Get chain in a specific direction only.
        - downstream: follow forward edges (source → target, parent → child)
        - upstream:   follow inverse edges (target → source, child → parent)

        Returns: [(node_key, hop_count, link_type), ...]
        """
        start_key = self._node_key(start_type, start_id)
        visited: Set[str] = {start_key}
        queue: deque = deque([(start_key, 0, "")])
        results: List[Tuple[str, int, str]] = []

        # Determine which edge types to follow
        forward_prefixes = {"parent_of", "verified_by"}
        inverse_prefixes = {"child_of", "verifies", "inv_"}

        while queue:
            current, hops, via_type = queue.popleft()
            if hops > 0:
                results.append((current, hops, via_type))
            if hops >= max_depth:
                continue

            for neighbor, link_type, _ in self._adjacency.get(current, []):
                if neighbor in visited:
                    continue

                follow = False
                if direction == "downstream":
                    # Follow non-inverse edges
                    follow = not link_type.startswith("inv_") and link_type not in inverse_prefixes
                elif direction == "upstream":
                    # Follow inverse edges
                    follow = link_type.startswith("inv_") or link_type in inverse_prefixes
                else:
                    follow = True  # "both"

                if follow:
                    visited.add(neighbor)
                    queue.append((neighbor, hops + 1, link_type))

        return results


# ══════════════════════════════════════
#  Impact Analysis
# ══════════════════════════════════════

def analyze_impact(
    requirement_id: int,
    change_description: str,
    db: Session,
    max_depth: int = 10,
) -> ImpactReport:
    """
    Run full impact analysis for a requirement change.

    1. Build the trace graph for the project
    2. BFS to find all affected entities
    3. Classify each as direct (1 hop) or indirect (2+ hops)
    4. Identify affected verifications and baselines
    5. Classify risk level
    6. Generate AI summary (optional)
    7. Persist the report
    """
    start_time = time.time()

    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        return ImpactReport(
            change_description=change_description,
            ai_summary="Requirement not found.",
        )

    # Build graph
    graph = _TraceGraph(db, req.project_id)

    # BFS all affected
    affected = graph.bfs_all_affected("requirement", requirement_id, max_depth)

    # Classify into direct (1 hop) and indirect (2+ hops)
    direct_impacts: List[ImpactItem] = []
    indirect_impacts: List[ImpactItem] = []
    max_hops = 0

    for node_key, hops, path in affected:
        entity = graph.get_entity(node_key)
        max_hops = max(max_hops, hops)

        # Build human-readable path
        path_strs = _build_path_strings(path, graph)
        link_types = [p[0] for p in path]

        item = ImpactItem(
            entity_type=entity["entity_type"],
            entity_id=entity["entity_id"],
            entity_identifier=entity.get("identifier", ""),
            entity_title=entity.get("title", ""),
            impact_level="direct" if hops == 1 else "indirect",
            hop_count=hops,
            relationship_path=path_strs,
            link_types_involved=link_types,
            current_status=entity.get("status", ""),
        )

        if hops == 1:
            direct_impacts.append(item)
        else:
            indirect_impacts.append(item)

    # Find affected verifications
    affected_verifications = _find_affected_verifications(
        db, requirement_id, direct_impacts + indirect_impacts
    )

    # Find affected baselines
    affected_baselines = _find_affected_baselines(db, requirement_id)

    # Classify risk
    total_affected = len(direct_impacts) + len(indirect_impacts)
    risk_level, risk_factors = _classify_risk(
        req, direct_impacts, indirect_impacts,
        affected_verifications, affected_baselines, max_hops,
    )

    # Generate AI summary
    ai_summary, ai_available = _generate_ai_summary(
        req, change_description,
        direct_impacts, indirect_impacts,
        affected_verifications, affected_baselines,
        risk_level,
    )

    duration_ms = int((time.time() - start_time) * 1000)

    report = ImpactReport(
        changed_requirement={
            "id": req.id,
            "req_id": req.req_id,
            "title": req.title,
            "statement": req.statement[:200],
            "status": _ev(req.status),
            "level": _ev(req.level) if hasattr(req, "level") else "L1",
            "req_type": _ev(req.req_type),
        },
        change_description=change_description,
        direct_impacts=direct_impacts,
        indirect_impacts=indirect_impacts,
        affected_verifications=affected_verifications,
        affected_baselines=affected_baselines,
        risk_level=risk_level,
        risk_factors=risk_factors,
        ai_summary=ai_summary,
        ai_available=ai_available,
        dependency_depth=max_hops,
        total_affected=total_affected,
        total_direct=len(direct_impacts),
        total_indirect=len(indirect_impacts),
        analyzed_at=datetime.utcnow().isoformat(),
        analysis_duration_ms=duration_ms,
    )

    # Persist the report
    _persist_report(db, requirement_id, change_description, report)

    return report


# ══════════════════════════════════════
#  Dependency Chain
# ══════════════════════════════════════

def get_dependency_chain(
    requirement_id: int,
    db: Session,
    direction: str = "both",
    max_depth: int = 10,
) -> DependencyTree:
    """
    Build a dependency tree showing upstream and/or downstream chains.

    - upstream:   what does this requirement derive from?
    - downstream: what derives from / depends on this requirement?
    """
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        return DependencyTree()

    graph = _TraceGraph(db, req.project_id)

    root_info = {
        "id": req.id,
        "req_id": req.req_id,
        "title": req.title,
        "status": _ev(req.status),
        "level": _ev(req.level) if hasattr(req, "level") else "L1",
    }

    upstream_nodes: List[DependencyNode] = []
    downstream_nodes: List[DependencyNode] = []
    max_up = 0
    max_down = 0

    if direction in ("upstream", "both"):
        upstream_raw = graph.get_directed_chain(
            "requirement", requirement_id, "upstream", max_depth
        )
        upstream_nodes = _build_dependency_nodes(upstream_raw, graph, "upstream")
        max_up = max((n.hop_count for n in upstream_nodes), default=0)

    if direction in ("downstream", "both"):
        downstream_raw = graph.get_directed_chain(
            "requirement", requirement_id, "downstream", max_depth
        )
        downstream_nodes = _build_dependency_nodes(downstream_raw, graph, "downstream")
        max_down = max((n.hop_count for n in downstream_nodes), default=0)

    return DependencyTree(
        root_requirement=root_info,
        upstream=upstream_nodes,
        downstream=downstream_nodes,
        total_upstream=len(upstream_nodes),
        total_downstream=len(downstream_nodes),
        max_depth_up=max_up,
        max_depth_down=max_down,
    )


# ══════════════════════════════════════
#  What-If Preview
# ══════════════════════════════════════

def preview_what_if(
    requirement_id: int,
    action: str,
    db: Session,
) -> WhatIfPreview:
    """
    Preview the impact of deleting or modifying a requirement
    BEFORE the action is taken. Used in confirmation dialogs.
    """
    req = db.query(Requirement).filter(Requirement.id == requirement_id).first()
    if not req:
        return WhatIfPreview(requirement_id=requirement_id, action=action)

    graph = _TraceGraph(db, req.project_id)
    affected = graph.bfs_all_affected("requirement", requirement_id, max_depth=8)

    items: List[ImpactItem] = []
    for node_key, hops, path in affected:
        entity = graph.get_entity(node_key)
        items.append(ImpactItem(
            entity_type=entity["entity_type"],
            entity_id=entity["entity_id"],
            entity_identifier=entity.get("identifier", ""),
            entity_title=entity.get("title", ""),
            impact_level="direct" if hops == 1 else "indirect",
            hop_count=hops,
            relationship_path=_build_path_strings(path, graph),
            link_types_involved=[p[0] for p in path],
            current_status=entity.get("status", ""),
        ))

    direct = [i for i in items if i.impact_level == "direct"]
    indirect = [i for i in items if i.impact_level == "indirect"]

    # Find orphans (children that would lose their parent on delete)
    orphaned: List[Dict[str, Any]] = []
    if action == "delete":
        children = (
            db.query(Requirement)
            .filter(Requirement.parent_id == requirement_id)
            .all()
        )
        for child in children:
            orphaned.append({
                "id": child.id,
                "req_id": child.req_id,
                "title": child.title,
                "level": _ev(child.level) if hasattr(child, "level") else "L1",
            })

    verifs = _find_affected_verifications(db, requirement_id, items)
    baselines = _find_affected_baselines(db, requirement_id)

    risk_level, _ = _classify_risk(
        req, direct, indirect, verifs, baselines, 0,
    )

    requires_cr = risk_level in ("high", "critical")

    # AI summary
    summary, ai_available = "", True
    try:
        from app.services.ai.llm_client import is_ai_available
        ai_available = is_ai_available()
    except ImportError:
        ai_available = False

    action_verb = "Deleting" if action == "delete" else "Modifying"
    summary = (
        f"{action_verb} {req.req_id} ({req.title}) will affect "
        f"{len(direct)} direct and {len(indirect)} indirect items. "
    )
    if verifs:
        rerun_count = sum(1 for v in verifs if v.needs_rerun)
        summary += f"{rerun_count} verification(s) will need re-execution. "
    if orphaned:
        summary += f"{len(orphaned)} child requirement(s) will become orphaned. "
    if baselines:
        summary += f"{len(baselines)} baseline(s) contain this requirement. "

    recommendation = ""
    if requires_cr:
        recommendation = (
            f"This is a {risk_level}-risk change. A formal change request is recommended "
            "before proceeding. Review all affected items and obtain CCB approval."
        )
    elif risk_level == "medium":
        recommendation = (
            "This change has moderate impact. Review affected verifications "
            "and notify downstream requirement owners."
        )

    return WhatIfPreview(
        requirement_id=requirement_id,
        requirement_identifier=req.req_id,
        action=action,
        total_affected=len(items),
        direct_count=len(direct),
        indirect_count=len(indirect),
        orphaned_count=len(orphaned),
        verification_rerun_count=sum(1 for v in verifs if v.needs_rerun),
        baseline_impact_count=len(baselines),
        affected_items=items,
        orphaned_requirements=orphaned,
        verifications_affected=verifs,
        baselines_affected=baselines,
        risk_level=risk_level,
        ai_summary=summary,
        ai_available=ai_available,
        requires_change_request=requires_cr,
        recommendation=recommendation,
    )


# ══════════════════════════════════════
#  Internal Helpers
# ══════════════════════════════════════

def _build_path_strings(
    path: List[Tuple[str, str]],
    graph: _TraceGraph,
) -> List[str]:
    """Convert edge path tuples to human-readable strings."""
    if not path:
        return []

    parts: List[str] = []
    for link_type, through_key in path:
        entity = graph.get_entity(through_key)
        ident = entity.get("identifier", through_key)
        clean_type = link_type.replace("inv_", "←").replace("_", " ")
        parts.append(f"{ident} →{clean_type}→")

    return [" ".join(parts)] if parts else []


def _build_dependency_nodes(
    raw: List[Tuple[str, int, str]],
    graph: _TraceGraph,
    direction: str,
) -> List[DependencyNode]:
    """Convert raw traversal results to DependencyNode list."""
    nodes: List[DependencyNode] = []
    for node_key, hops, link_type in raw:
        entity = graph.get_entity(node_key)
        clean_link = link_type.replace("inv_", "").replace("_", " ")
        nodes.append(DependencyNode(
            entity_type=entity["entity_type"],
            entity_id=entity["entity_id"],
            identifier=entity.get("identifier", ""),
            title=entity.get("title", ""),
            status=entity.get("status", ""),
            level=entity.get("level", ""),
            hop_count=hops,
            link_type=clean_link,
            link_direction=direction,
        ))
    return nodes


def _find_affected_verifications(
    db: Session,
    changed_req_id: int,
    impact_items: List[ImpactItem],
) -> List[AffectedVerification]:
    """Find all verifications that may need re-execution."""
    results: List[AffectedVerification] = []

    # Direct verifications on the changed requirement
    direct_verifs = (
        db.query(Verification)
        .filter(Verification.requirement_id == changed_req_id)
        .all()
    )
    for v in direct_verifs:
        req = db.query(Requirement).filter(Requirement.id == v.requirement_id).first()
        results.append(AffectedVerification(
            verification_id=v.id,
            requirement_id=v.requirement_id,
            requirement_identifier=req.req_id if req else "",
            method=_ev(v.method),
            current_status=_ev(v.status),
            needs_rerun=_ev(v.status) in ("pass", "in_progress"),
            reason="Direct verification of the changed requirement.",
        ))

    # Verifications on impacted requirements
    impacted_req_ids = {
        item.entity_id
        for item in impact_items
        if item.entity_type == "requirement"
    }
    if impacted_req_ids:
        indirect_verifs = (
            db.query(Verification)
            .filter(Verification.requirement_id.in_(impacted_req_ids))
            .all()
        )
        for v in indirect_verifs:
            if any(r.verification_id == v.id for r in results):
                continue
            req = db.query(Requirement).filter(Requirement.id == v.requirement_id).first()
            results.append(AffectedVerification(
                verification_id=v.id,
                requirement_id=v.requirement_id,
                requirement_identifier=req.req_id if req else "",
                method=_ev(v.method),
                current_status=_ev(v.status),
                needs_rerun=_ev(v.status) in ("pass", "in_progress"),
                reason=f"Verification of downstream requirement {req.req_id if req else ''}.",
            ))

    return results


def _find_affected_baselines(
    db: Session,
    requirement_id: int,
) -> List[AffectedBaseline]:
    """Find all baselines containing the changed requirement."""
    results: List[AffectedBaseline] = []

    baseline_reqs = (
        db.query(BaselineRequirement)
        .filter(BaselineRequirement.requirement_id == requirement_id)
        .all()
    )

    for br in baseline_reqs:
        baseline = db.query(Baseline).filter(Baseline.id == br.baseline_id).first()
        if not baseline:
            continue

        results.append(AffectedBaseline(
            baseline_id=baseline.id,
            baseline_name=baseline.name,
            created_at=baseline.created_at.isoformat() if baseline.created_at else None,
            requirements_count=baseline.requirements_count if hasattr(baseline, "requirements_count") else 0,
            reason="This baseline includes the changed requirement and may need updating.",
        ))

    return results


def _classify_risk(
    req: Requirement,
    direct: List[ImpactItem],
    indirect: List[ImpactItem],
    verifications: List[AffectedVerification],
    baselines: List[AffectedBaseline],
    max_depth: int,
) -> Tuple[str, List[str]]:
    """
    Classify overall risk level of the change.

    Factors considered:
      - Number of directly affected items
      - Total transitive spread (depth and breadth)
      - Whether passed verifications need re-run
      - Whether baselines are affected
      - Priority / level of the changed requirement
    """
    factors: List[str] = []
    score = 0

    # Direct impact breadth
    if len(direct) >= 8:
        score += 3
        factors.append(f"High fan-out: {len(direct)} directly affected items")
    elif len(direct) >= 4:
        score += 2
        factors.append(f"Moderate fan-out: {len(direct)} directly affected items")
    elif len(direct) >= 1:
        score += 1

    # Transitive depth
    total = len(direct) + len(indirect)
    if total >= 15:
        score += 3
        factors.append(f"Wide blast radius: {total} total affected entities across {max_depth} levels")
    elif total >= 8:
        score += 2
        factors.append(f"Significant cascade: {total} total affected entities")
    elif total >= 3:
        score += 1

    # Verification impact
    reruns = [v for v in verifications if v.needs_rerun]
    if len(reruns) >= 3:
        score += 2
        factors.append(f"{len(reruns)} passed verifications need re-execution")
    elif reruns:
        score += 1
        factors.append(f"{len(reruns)} verification(s) may need re-execution")

    # Baseline impact
    if baselines:
        score += 1
        factors.append(f"{len(baselines)} baseline(s) affected")

    # Requirement priority and level
    priority = _ev(req.priority)
    if priority in ("critical", "high"):
        score += 1
        factors.append(f"Changed requirement has {priority} priority")

    level = _ev(req.level) if hasattr(req, "level") else "L1"
    if level in ("L1", "L2"):
        score += 1
        factors.append(f"Changed requirement is at {level} (system/subsystem level)")

    # Map score to risk level
    if score >= 8:
        return "critical", factors
    elif score >= 5:
        return "high", factors
    elif score >= 3:
        return "medium", factors
    else:
        return "low", factors


def _generate_ai_summary(
    req: Requirement,
    change_description: str,
    direct: List[ImpactItem],
    indirect: List[ImpactItem],
    verifications: List[AffectedVerification],
    baselines: List[AffectedBaseline],
    risk_level: str,
) -> Tuple[str, bool]:
    """
    Generate a natural-language impact summary using the LLM.
    Falls back to a structured summary if AI is unavailable.
    """
    # Always produce a deterministic summary as fallback
    fallback = _build_fallback_summary(
        req, change_description, direct, indirect, verifications, baselines, risk_level,
    )

    try:
        from app.services.ai.llm_client import is_ai_available, LLMClient

        if not is_ai_available():
            return fallback, False

        # Build context for the LLM
        direct_list = ", ".join(
            f"{i.entity_identifier} ({i.entity_title})"
            for i in direct[:10]
        ) or "none"

        indirect_list = ", ".join(
            f"{i.entity_identifier} ({i.entity_title})"
            for i in indirect[:10]
        ) or "none"

        verif_list = ", ".join(
            f"VER-{v.verification_id} ({v.method}, status: {v.current_status})"
            for v in verifications[:5]
        ) or "none"

        baseline_list = ", ".join(
            b.baseline_name for b in baselines[:5]
        ) or "none"

        prompt = f"""Summarize the impact of changing this systems engineering requirement.

CHANGED REQUIREMENT:
  ID: {req.req_id}
  Title: {req.title}
  Statement: {req.statement[:300]}

CHANGE DESCRIPTION: {change_description or "General modification"}

DIRECTLY AFFECTED (1 hop): {direct_list}
INDIRECTLY AFFECTED (2+ hops): {indirect_list}
AFFECTED VERIFICATIONS: {verif_list}
AFFECTED BASELINES: {baseline_list}
RISK LEVEL: {risk_level}

Write a clear, concise impact summary (3-5 sentences) suitable for a Change Control Board.
Explain WHY downstream items are affected, not just which ones.
Recommend specific actions (re-run tests, update baselines, notify owners).

Respond ONLY with a JSON object: {{"summary": "your summary text"}}"""

        system = (
            "You are a systems engineering change impact analyst. "
            "Produce clear, actionable impact summaries. "
            "Respond ONLY with valid JSON."
        )

        client = LLMClient()
        result = client.complete(system, prompt, temperature=0.2, max_tokens=500)

        if result and isinstance(result.get("summary"), str):
            return result["summary"], True

    except Exception as exc:
        logger.debug("AI summary generation failed: %s", exc)

    return fallback, False


def _build_fallback_summary(
    req: Requirement,
    change_description: str,
    direct: List[ImpactItem],
    indirect: List[ImpactItem],
    verifications: List[AffectedVerification],
    baselines: List[AffectedBaseline],
    risk_level: str,
) -> str:
    """Build a structured fallback summary without AI."""
    parts: List[str] = []

    parts.append(
        f"Changing {req.req_id} ({req.title}) "
        f"will directly affect {len(direct)} item(s)"
    )
    if indirect:
        parts[-1] += f" and indirectly affect {len(indirect)} item(s)"
    parts[-1] += "."

    if direct:
        direct_reqs = [i for i in direct if i.entity_type == "requirement"]
        if direct_reqs:
            ids = ", ".join(i.entity_identifier for i in direct_reqs[:5])
            parts.append(f"Directly affected requirements: {ids}.")

    reruns = [v for v in verifications if v.needs_rerun]
    if reruns:
        ids = ", ".join(
            f"VER-{v.verification_id} ({v.method})" for v in reruns[:3]
        )
        parts.append(f"{len(reruns)} verification(s) need re-execution: {ids}.")

    if baselines:
        names = ", ".join(b.baseline_name for b in baselines[:3])
        parts.append(f"Affected baselines: {names}.")

    parts.append(f"Overall risk level: {risk_level.upper()}.")

    return " ".join(parts)


def _persist_report(
    db: Session,
    requirement_id: int,
    change_description: str,
    report: ImpactReport,
) -> None:
    """Save the impact report to the database."""
    try:
        from app.models.impact import ImpactReport as ImpactReportModel

        stored = ImpactReportModel(
            requirement_id=requirement_id,
            change_description=change_description,
            report_json=report.model_dump(),
            risk_level=report.risk_level,
            total_affected=report.total_affected,
            dependency_depth=report.dependency_depth,
            ai_summary=report.ai_summary[:2000] if report.ai_summary else "",
        )
        db.add(stored)
        db.commit()
    except Exception as exc:
        db.rollback()
        logger.error("Failed to persist impact report: %s", exc)
