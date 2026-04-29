"""
ASTRA — Auto-Grow Harness Engine (Phase 2a)
==========================================
File: backend/app/services/interface/auto_grow.py
Path: C:\\Users\\Mason\\Documents\\ASTRA\\backend\\app\\services\\interface\\auto_grow.py

Purpose
-------
Given a batch of proposed wires (each: from_lru_pin + to_lru_pin), figure out
which harness each wire should land on. Create new harnesses, extend existing
ones, or surface ambiguities to the caller for user resolution.

This is the core of the multi-endpoint trunk-with-branches model. It replaces
the implicit "one harness, fixed from/to" assumption that was baked into the
old auto-wire code with explicit per-pair harness decisions.

Decision tree per pair
----------------------
For each (from_lru_pin, to_lru_pin):

    Does either LRU already belong to a harness?
    ├── Neither → create a new harness, add 2 endpoints (one per LRU)
    ├── Only the from-side LRU → add a new endpoint for the to-side LRU to
    │                             from-side's harness
    ├── Only the to-side LRU → add a new endpoint for the from-side LRU to
    │                           to-side's harness
    ├── Both, same harness → no new endpoints needed, wire joins harness
    └── Both, different harnesses → AMBIGUITY (surface to user for merge-or-split)

"Does the LRU already belong to a harness?"
    = "Is any Connector belonging to this LRU registered as the lru_connector
       on a HarnessEndpoint row?"

Mating connector creation
-------------------------
When a new endpoint is created, a mating Connector is cloned from the LRU's
connector: all specs copied, gender flipped (male_pin ↔ female_socket), pins
cloned 1:1 with the same pin_number mapping. This mirrors the Phase 1
migration's SQL cloning logic, applied at runtime for new endpoints.

Mating pin direction: stays IDENTICAL to the LRU side (per Mason's spec).

Connection rollup
-----------------
After wires are created, Connection rows (bidirectional LRU-pair rollups)
are auto-maintained. Canonical order: lru_a_id < lru_b_id.

Usage from the router
---------------------
    from app.services.interface.auto_grow import AutoGrowEngine

    engine = AutoGrowEngine(db, project_id, current_user)
    result = engine.run(pairs=[...], decisions=[...])

    if result.ambiguities:
        # Surface to user, gather their AmbiguityDecision list, call run() again
        return result
    # else: wires were created — result.new_wire_ids has them
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.interface import (
    Connector, Pin, Wire, WireHarness, HarnessEndpoint, Connection,
)

logger = logging.getLogger("astra")


# ══════════════════════════════════════════════════════════════
#  Input / Output shapes (plain dataclasses — router maps to/from Pydantic)
# ══════════════════════════════════════════════════════════════

@dataclass
class AutoGrowPair:
    from_lru_pin_id: int
    to_lru_pin_id: int
    signal_name: Optional[str] = None
    wire_type: Optional[str] = None
    wire_gauge: Optional[str] = None


@dataclass
class AmbiguityDecision:
    pair_index: int
    action: str  # 'merge_into_a' | 'merge_into_b' | 'new_harness' | 'cancel'
    new_harness_name: Optional[str] = None


@dataclass
class AutoGrowAmbiguity:
    pair_index: int
    from_lru_pin_id: int
    to_lru_pin_id: int
    from_lru_unit_id: int
    from_lru_unit_designation: str
    to_lru_unit_id: int
    to_lru_unit_designation: str
    harness_a_id: int
    harness_a_name: str
    harness_a_wire_count: int
    harness_a_endpoint_count: int
    harness_b_id: int
    harness_b_name: str
    harness_b_wire_count: int
    harness_b_endpoint_count: int
    # Phase 2a enrichments: let the UI render a richer modal without follow-up
    # round-trips. Each harness's LRU-span is the set of unique LRU
    # designations plugged into it — so the modal can say "A spans {DG3,
    # DG4}; B spans {SD1, IMU}".
    harness_a_lru_designations: List[str] = field(default_factory=list)
    harness_b_lru_designations: List[str] = field(default_factory=list)
    # Which actions are physically valid for this ambiguity. The engine
    # trims 'new_harness' when both LRU connectors are already claimed by
    # other harness endpoints (UNIQUE constraint on lru_connector_id).
    # The UI hides options not in this list. 'cancel' is always present.
    valid_actions: List[str] = field(default_factory=list)
    # Human-readable explanation when new_harness is disallowed, so the UI
    # can show a greyed-out option with a tooltip rather than silently
    # omitting it.
    new_harness_disallowed_reason: Optional[str] = None


@dataclass
class SkippedPair:
    """A pair the engine couldn't process. Surfaced in AutoGrowResult so
    the UI can tell the user WHY nothing happened for that pair, rather
    than silently returning wires_created=0."""
    pair_index: int
    from_lru_pin_id: int
    to_lru_pin_id: int
    reason: str


@dataclass
class AutoGrowResult:
    wires_created: int = 0
    harnesses_created: int = 0
    endpoints_added: int = 0
    ambiguities: List[AutoGrowAmbiguity] = field(default_factory=list)
    connections_touched: List[int] = field(default_factory=list)
    new_wire_ids: List[int] = field(default_factory=list)
    new_harness_ids: List[int] = field(default_factory=list)
    # Phase 2b — pairs that were skipped and why (bad pin ids, same LRU,
    # already-wired duplicate, etc.). Empty means every pair was processed.
    skipped: List[SkippedPair] = field(default_factory=list)


# ══════════════════════════════════════════════════════════════
#  Internal helpers
# ══════════════════════════════════════════════════════════════

def _flip_gender(g) -> Optional[str]:
    """Mating connector gender rule.

    male_pin ↔ female_socket (swapped)
    hermaphroditic → hermaphroditic (self-mating)
    genderless → genderless
    NULL → NULL

    Accepts either a string or a SQLAlchemy enum object. Converting a
    SQLAlchemy enum via str() gives "ConnectorGender.FEMALE_SOCKET", not
    "female_socket" — which then fails as an enum value at insert time.
    The fix: prefer .value when it exists, else str(), then lowercase as a
    final belt-and-suspenders guard against inconsistent casing.
    """
    if g is None:
        return None
    # SQLAlchemy enum objects expose .value; strings don't have that attr.
    raw = getattr(g, "value", None) or str(g)
    # Strip any "ClassName." prefix that str() on a raw Python Enum would add
    if "." in raw:
        raw = raw.rsplit(".", 1)[-1]
    raw = raw.lower()
    if raw == "male_pin":
        return "female_socket"
    if raw == "female_socket":
        return "male_pin"
    return raw


def _next_wire_number(db: Session, harness_id: int, starting_counter: int = 1) -> str:
    """Find the next available wire number (W001, W002, ...) in a harness."""
    existing = set(
        r[0] for r in db.query(Wire.wire_number).filter(Wire.harness_id == harness_id).all()
    )
    counter = starting_counter
    while f"W{counter:03d}" in existing:
        counter += 1
    return f"W{counter:03d}"


def _pair_key(a: int, b: int) -> Tuple[int, int]:
    """Canonical ordering for LRU pairs — always (lower, higher) so that
    {FCC, IMU} and {IMU, FCC} produce the same key."""
    return (a, b) if a < b else (b, a)


# ══════════════════════════════════════════════════════════════
#  Engine
# ══════════════════════════════════════════════════════════════

class AutoGrowEngine:
    """Stateful engine for processing an auto-grow batch.

    Not thread-safe. Create a fresh instance per request.
    """

    def __init__(self, db: Session, project_id: int, current_user):
        self.db = db
        self.project_id = project_id
        self.current_user = current_user
        # Cache: unit_id -> current harness_id (if it belongs to one)
        # Populated lazily during the run() and updated as we create/extend.
        self._unit_to_harness: Dict[int, int] = {}

    # ── Public entry point ────────────────────────────────────────────────

    def run(
        self,
        pairs: List[AutoGrowPair],
        decisions: Optional[List[AmbiguityDecision]] = None,
    ) -> AutoGrowResult:
        """Process an auto-grow batch.

        If `decisions` is empty and any pair is ambiguous, returns a result
        with `ambiguities` populated and no changes committed. The caller
        re-submits with decisions resolved.

        If `decisions` is provided, each decision's pair_index must match
        exactly what was surfaced in a prior call — the engine trusts the
        caller to echo them back correctly.
        """
        decisions = decisions or []
        decision_map = {d.pair_index: d for d in decisions}
        result = AutoGrowResult()

        # Phase 2b: no more cache. Classification now calls _harness_for_pin
        # per pair, which reads fresh from the DB. Within a single batch,
        # earlier pair executions flush their new endpoints, and subsequent
        # classifications see them.
        #
        # We do classification+execution PER PAIR inline (not in two passes)
        # because a pair's classification can depend on a previous pair's
        # harness creation. For example, a batch with 8 pairs all between
        # LRUs A and B: pair 0 creates the harness, pairs 1-7 see it as an
        # existing_harness case. That only works if classification is
        # fresh per-pair.
        #
        # Ambiguity handling: we still need to collect ALL ambiguities
        # before committing anything, because the user resolves them
        # sequentially and we want to roll back the whole batch if any
        # remain unresolved. So we classify in two phases:
        #   phase A — classify each pair, collect ambiguities. No DB writes.
        #   phase B — if no pending ambiguities, execute each pair inline.
        # Between A and B, nothing has been committed. If any ambiguity
        # remains, we return it and exit without touching the DB.

        # ── Phase A: classify-only pass to detect ambiguities ──
        pending_ambiguities: List[AutoGrowAmbiguity] = []
        for idx, pair in enumerate(pairs):
            cls = self._classify_pair(idx, pair, decision_map.get(idx))
            if cls["kind"] == "ambiguous" and idx not in decision_map:
                pending_ambiguities.append(cls["ambiguity"])

        if pending_ambiguities:
            result.ambiguities = pending_ambiguities
            return result

        # ── Phase B: re-classify and execute per-pair ──
        # We re-classify each pair inline so earlier executions influence
        # later decisions (e.g., harness created in pair 0 is visible to
        # pair 1's classification).
        touched_lru_pairs: Set[Tuple[int, int]] = set()

        for idx, pair in enumerate(pairs):
            cls = self._classify_pair(idx, pair, decision_map.get(idx))

            if cls["kind"] == "cancelled":
                # Phase 2b: surface why we skipped, instead of silently
                # dropping the pair. UI shows "Skipped 2 of 8 pairs" with
                # reasons.
                result.skipped.append(SkippedPair(
                    pair_index=idx,
                    from_lru_pin_id=pair.from_lru_pin_id,
                    to_lru_pin_id=pair.to_lru_pin_id,
                    reason=cls.get("reason", "unknown"),
                ))
                continue

            # Shouldn't happen — Phase A would have bailed. But defensive.
            if cls["kind"] == "ambiguous":
                raise RuntimeError(
                    f"Pair {idx} became ambiguous during Phase B execution. "
                    f"This suggests a concurrent modification raced our classification."
                )

            wire_id, harness_id, endpoints_added_this_pair, new_harness_id = \
                self._execute_pair(pair, cls)

            if wire_id:
                result.new_wire_ids.append(wire_id)
                result.wires_created += 1
            else:
                # _create_wire returned None (e.g., pin already wired). Surface.
                result.skipped.append(SkippedPair(
                    pair_index=idx,
                    from_lru_pin_id=pair.from_lru_pin_id,
                    to_lru_pin_id=pair.to_lru_pin_id,
                    reason="one or both pins already wired on the target harness",
                ))
            if new_harness_id:
                result.new_harness_ids.append(new_harness_id)
                result.harnesses_created += 1
            result.endpoints_added += endpoints_added_this_pair

            # Track the LRU pair this wire touched for connection rollup
            from_unit_id, to_unit_id = self._pin_units(pair.from_lru_pin_id, pair.to_lru_pin_id)
            if from_unit_id and to_unit_id and from_unit_id != to_unit_id:
                touched_lru_pairs.add(_pair_key(from_unit_id, to_unit_id))

        # Connection rollup: ensure a Connection row exists for each touched
        # LRU pair. Creates rows that aren't there, updates updated_at on
        # ones that already exist.
        for (a, b) in touched_lru_pairs:
            conn_id = self._upsert_connection(a, b)
            if conn_id:
                result.connections_touched.append(conn_id)

        self.db.commit()
        return result

    # ── Classification (decide what each pair should do) ──────────────────

    def _classify_pair(
        self,
        idx: int,
        pair: AutoGrowPair,
        decision: Optional[AmbiguityDecision],
    ) -> dict:
        """Classify one pair into one of the action types.

        Returns a dict with at minimum {"kind": "..."} and action-specific
        payload. Does not mutate the DB.
        """
        from_unit_id, to_unit_id = self._pin_units(pair.from_lru_pin_id, pair.to_lru_pin_id)
        if from_unit_id is None and to_unit_id is None:
            return {"kind": "cancelled",
                    "reason": f"neither pin exists or neither is on an LRU-side connector "
                              f"(from_lru_pin_id={pair.from_lru_pin_id}, "
                              f"to_lru_pin_id={pair.to_lru_pin_id})"}
        if from_unit_id is None:
            return {"kind": "cancelled",
                    "reason": f"from_lru_pin_id={pair.from_lru_pin_id} doesn't exist or isn't on an LRU connector"}
        if to_unit_id is None:
            return {"kind": "cancelled",
                    "reason": f"to_lru_pin_id={pair.to_lru_pin_id} doesn't exist or isn't on an LRU connector"}
        if from_unit_id == to_unit_id:
            return {"kind": "cancelled",
                    "reason": f"both pins are on the same LRU (unit_id={from_unit_id}); "
                              f"a wire connects two different LRUs"}

        # Phase 2b: classification used to read from a unit→harness cache,
        # which collapsed the "LRU SD1 is on multiple harnesses via different
        # connectors" reality into a single arbitrary choice. Now we look up
        # the harness per PIN: which harness (if any) is this pin's specific
        # connector plugged into? That correctly handles per-connector
        # distinctions on multi-harness LRUs.
        ha = self._harness_for_pin(pair.from_lru_pin_id)
        hb = self._harness_for_pin(pair.to_lru_pin_id)

        # Case 1 — neither LRU has a harness
        if ha is None and hb is None:
            return {
                "kind": "new_harness",
                "from_unit_id": from_unit_id,
                "to_unit_id": to_unit_id,
            }

        # Case 2 — both LRUs on same harness
        if ha is not None and hb is not None and ha == hb:
            return {
                "kind": "existing_harness",
                "harness_id": ha,
                "from_unit_id": from_unit_id,
                "to_unit_id": to_unit_id,
            }

        # Case 3 — one side has a harness, other doesn't (extend that harness)
        if ha is not None and hb is None:
            return {
                "kind": "extend_harness",
                "harness_id": ha,
                "existing_side_unit_id": from_unit_id,
                "new_side_unit_id": to_unit_id,
                "from_unit_id": from_unit_id,
                "to_unit_id": to_unit_id,
            }
        if hb is not None and ha is None:
            return {
                "kind": "extend_harness",
                "harness_id": hb,
                "existing_side_unit_id": to_unit_id,
                "new_side_unit_id": from_unit_id,
                "from_unit_id": from_unit_id,
                "to_unit_id": to_unit_id,
            }

        # Case 4 — both LRUs on DIFFERENT harnesses. This is the ambiguity.
        # Build the decision context first so we know which actions are
        # physically valid. 'new_harness' requires BOTH LRU-side connectors
        # involved in the pair to be un-claimed (i.e., this pair's specific
        # connectors aren't already plugged into some harness) — otherwise
        # the DB UNIQUE(lru_connector_id) would block it anyway.
        ambig = self._build_ambiguity(idx, pair, from_unit_id, to_unit_id, ha, hb)

        if decision is None:
            return {"kind": "ambiguous", "ambiguity": ambig}

        # Decision already provided — translate to action, validating against
        # the list of valid_actions we just computed. Invalid decisions get
        # rejected loudly so the caller knows the client sent something the
        # backend wouldn't permit (avoids the mystery 500s we saw earlier).
        if decision.action not in ambig.valid_actions and decision.action != "cancel":
            raise ValueError(
                f"Decision action '{decision.action}' is not valid for pair {idx}. "
                f"Valid actions: {ambig.valid_actions}. "
                f"Reason: {ambig.new_harness_disallowed_reason or 'n/a'}"
            )

        if decision.action == "merge_into_a":
            # A = the from-side's harness
            return {"kind": "merge", "keep_harness_id": ha, "fold_harness_id": hb,
                    "from_unit_id": from_unit_id, "to_unit_id": to_unit_id}
        if decision.action == "merge_into_b":
            return {"kind": "merge", "keep_harness_id": hb, "fold_harness_id": ha,
                    "from_unit_id": from_unit_id, "to_unit_id": to_unit_id}
        if decision.action == "new_harness":
            return {"kind": "new_harness", "name_hint": decision.new_harness_name,
                    "from_unit_id": from_unit_id, "to_unit_id": to_unit_id}
        if decision.action == "cancel":
            return {"kind": "cancelled", "reason": "user cancelled"}

        return {"kind": "cancelled", "reason": f"unknown decision action: {decision.action}"}

    # ── Helper: "is this LRU connector free to join a new harness?" ──────

    def _is_connector_unclaimed(self, connector_id: int) -> bool:
        """True if this LRU-side connector is NOT currently on any harness
        endpoint. The UNIQUE constraint on harness_endpoints.lru_connector_id
        enforces this at the DB level; this check lets us surface the
        situation to users before they hit a 500."""
        claimed = (self.db.query(HarnessEndpoint.id)
                   .filter(HarnessEndpoint.lru_connector_id == connector_id)
                   .first())
        return claimed is None

    def _harness_lru_designations(self, harness_id: int) -> List[str]:
        """Return unique list of LRU designations spanned by this harness,
        for display in the ambiguity modal."""
        from app.models.interface import Unit
        rows = (self.db.query(Unit.designation)
                .join(Connector, Connector.unit_id == Unit.id)
                .join(HarnessEndpoint, HarnessEndpoint.lru_connector_id == Connector.id)
                .filter(HarnessEndpoint.harness_id == harness_id)
                .distinct()
                .all())
        return sorted([r[0] for r in rows if r[0]])

    def _build_ambiguity(
        self, idx: int, pair: AutoGrowPair,
        from_unit_id: int, to_unit_id: int,
        ha: int, hb: int,
    ) -> AutoGrowAmbiguity:
        """Build the ambiguity record, computing which actions are valid.

        'new_harness' requires BOTH of this pair's LRU-side connectors to
        be un-claimed (not plugged into any harness endpoint). In the real
        test case, DG3's "Black Plastic" connector is already on harness 12
        and SD1's J3 is already on harness 4 — so new_harness is physically
        impossible and gets stripped from valid_actions.

        The UI uses valid_actions to decide which radio buttons to show.
        """
        from app.models.interface import Unit
        from_unit = self.db.query(Unit).filter(Unit.id == from_unit_id).first()
        to_unit = self.db.query(Unit).filter(Unit.id == to_unit_id).first()
        h_a = self.db.query(WireHarness).filter(WireHarness.id == ha).first()
        h_b = self.db.query(WireHarness).filter(WireHarness.id == hb).first()

        wc_a = self.db.query(func.count(Wire.id)).filter(Wire.harness_id == ha).scalar() or 0
        wc_b = self.db.query(func.count(Wire.id)).filter(Wire.harness_id == hb).scalar() or 0
        ec_a = self.db.query(func.count(HarnessEndpoint.id)).filter(HarnessEndpoint.harness_id == ha).scalar() or 0
        ec_b = self.db.query(func.count(HarnessEndpoint.id)).filter(HarnessEndpoint.harness_id == hb).scalar() or 0

        # LRU spans for display (so modal can say "A spans {DG3, DG4}")
        a_spans = self._harness_lru_designations(ha)
        b_spans = self._harness_lru_designations(hb)

        # Check whether new_harness is physically possible for THIS pair.
        # Gate: both LRU-side connectors on this pair must be un-claimed.
        from_conn = self._connector_of_pin(pair.from_lru_pin_id)
        to_conn = self._connector_of_pin(pair.to_lru_pin_id)
        from_free = from_conn is not None and self._is_connector_unclaimed(from_conn.id)
        to_free = to_conn is not None and self._is_connector_unclaimed(to_conn.id)

        valid_actions = ["merge_into_a", "merge_into_b", "cancel"]
        new_harness_reason: Optional[str] = None
        if from_free and to_free:
            valid_actions.insert(2, "new_harness")  # between merges and cancel
        else:
            # Build a precise explanation: which LRU connector is blocked and
            # which harness it's currently on.
            blocked_parts = []
            if from_conn and not from_free:
                existing_ep = (self.db.query(HarnessEndpoint)
                               .filter(HarnessEndpoint.lru_connector_id == from_conn.id)
                               .first())
                blocked_parts.append(
                    f"{from_unit.designation if from_unit else '?'}.{from_conn.designator} is plugged into harness {existing_ep.harness_id}"
                )
            if to_conn and not to_free:
                existing_ep = (self.db.query(HarnessEndpoint)
                               .filter(HarnessEndpoint.lru_connector_id == to_conn.id)
                               .first())
                blocked_parts.append(
                    f"{to_unit.designation if to_unit else '?'}.{to_conn.designator} is plugged into harness {existing_ep.harness_id}"
                )
            new_harness_reason = (
                "Can't create a new harness for this wire because "
                + " and ".join(blocked_parts)
                + ". A physical connector can only be on one harness at a time. "
                  "Merge, cancel, or use a different connector on the LRU."
            )

        return AutoGrowAmbiguity(
            pair_index=idx,
            from_lru_pin_id=pair.from_lru_pin_id,
            to_lru_pin_id=pair.to_lru_pin_id,
            from_lru_unit_id=from_unit_id,
            from_lru_unit_designation=from_unit.designation if from_unit else str(from_unit_id),
            to_lru_unit_id=to_unit_id,
            to_lru_unit_designation=to_unit.designation if to_unit else str(to_unit_id),
            harness_a_id=ha,
            harness_a_name=h_a.name if h_a else f"Harness {ha}",
            harness_a_wire_count=wc_a,
            harness_a_endpoint_count=ec_a,
            harness_b_id=hb,
            harness_b_name=h_b.name if h_b else f"Harness {hb}",
            harness_b_wire_count=wc_b,
            harness_b_endpoint_count=ec_b,
            harness_a_lru_designations=a_spans,
            harness_b_lru_designations=b_spans,
            valid_actions=valid_actions,
            new_harness_disallowed_reason=new_harness_reason,
        )

    # ── Execution (mutate DB per classification) ──────────────────────────

    def _execute_pair(self, pair: AutoGrowPair, cls: dict):
        """Execute one classified pair. Returns (wire_id, harness_id, endpoints_added, new_harness_id)."""
        kind = cls["kind"]

        if kind == "new_harness":
            # Belt-and-suspenders guard: even if classification allowed
            # new_harness, double-check both LRU connectors are unclaimed
            # before attempting creation. Catches any concurrent-modification
            # race (another user creating an endpoint between classify and
            # execute) and any logic bug in the classify path.
            from_conn = self._connector_of_pin(pair.from_lru_pin_id)
            to_conn = self._connector_of_pin(pair.to_lru_pin_id)
            if from_conn and not self._is_connector_unclaimed(from_conn.id):
                raise ValueError(
                    f"Cannot create new harness: connector {from_conn.designator} "
                    f"(id {from_conn.id}) is already plugged into another harness. "
                    f"Use merge or choose a different connector."
                )
            if to_conn and not self._is_connector_unclaimed(to_conn.id):
                raise ValueError(
                    f"Cannot create new harness: connector {to_conn.designator} "
                    f"(id {to_conn.id}) is already plugged into another harness. "
                    f"Use merge or choose a different connector."
                )

            harness = self._create_harness_with_endpoints(
                cls["from_unit_id"], cls["to_unit_id"],
                name_hint=cls.get("name_hint"),
                from_pin_id=pair.from_lru_pin_id,
                to_pin_id=pair.to_lru_pin_id,
            )
            # _create_harness_with_endpoints adds 2 endpoints
            wire_id = self._create_wire(harness.id, pair)
            return (wire_id, harness.id, 2, harness.id)

        if kind == "existing_harness":
            wire_id = self._create_wire(cls["harness_id"], pair)
            return (wire_id, cls["harness_id"], 0, None)

        if kind == "extend_harness":
            # One side's connector is new to this harness. Add an endpoint.
            new_side_unit_id = cls["new_side_unit_id"]
            new_side_pin_id = (pair.to_lru_pin_id
                               if cls["to_unit_id"] == new_side_unit_id
                               else pair.from_lru_pin_id)
            self._add_endpoint_for_new_side(cls["harness_id"], new_side_pin_id)
            wire_id = self._create_wire(cls["harness_id"], pair)
            return (wire_id, cls["harness_id"], 1, None)

        if kind == "merge":
            # Fold fold_harness into keep_harness. All endpoints, wires, etc.
            # reparent. fold_harness gets deleted at the end.
            self._merge_harness(cls["keep_harness_id"], cls["fold_harness_id"])
            # After merge, both units are on keep_harness.
            wire_id = self._create_wire(cls["keep_harness_id"], pair)
            return (wire_id, cls["keep_harness_id"], 0, None)

        if kind == "cancelled":
            return (None, None, 0, None)

        raise RuntimeError(f"Unknown classification kind: {kind}")

    # ── Primitive operations ──────────────────────────────────────────────

    def _pin_units(self, from_pin_id: int, to_pin_id: int) -> Tuple[Optional[int], Optional[int]]:
        """Return (from_unit_id, to_unit_id) for a pair of LRU pins. None if
        the pin doesn't exist or its connector has no unit (e.g., it's a
        harness-owned mating pin, which shouldn't be passed here but we
        handle gracefully)."""
        def _unit_of(pin_id: int) -> Optional[int]:
            row = (self.db.query(Connector.unit_id)
                   .join(Pin, Pin.connector_id == Connector.id)
                   .filter(Pin.id == pin_id).first())
            return row[0] if row else None
        return (_unit_of(from_pin_id), _unit_of(to_pin_id))

    def _harness_for_pin(self, lru_pin_id: int) -> Optional[int]:
        """Return the harness_id (if any) whose endpoint is plugged into
        THIS pin's specific connector. Returns None if the pin's connector
        is not currently on any harness.

        This replaces the old cache-based unit→harness lookup, which picked
        arbitrary harnesses for LRUs that span multiple (e.g., SD1 has J1,
        J2, J3, J4, J5 each potentially on different harnesses).
        """
        row = (self.db.query(HarnessEndpoint.harness_id)
               .join(Pin, Pin.connector_id == HarnessEndpoint.lru_connector_id)
               .filter(Pin.id == lru_pin_id)
               .first())
        return row[0] if row else None

    def _load_unit_to_harness_cache(self) -> Dict[int, int]:
        """Build a map of unit_id -> harness_id for all units in this project
        that currently belong to a harness.

        An LRU belongs to harness H if any of its connectors is the
        lru_connector on one of H's endpoints.
        """
        # JOIN: HarnessEndpoint → Connector (lru_connector) → Unit
        rows = (
            self.db.query(Connector.unit_id, HarnessEndpoint.harness_id)
            .join(HarnessEndpoint, HarnessEndpoint.lru_connector_id == Connector.id)
            .filter(Connector.unit_id.isnot(None))
            .all()
        )
        # If somehow a unit appears on multiple harnesses (shouldn't happen
        # — UNIQUE on lru_connector_id prevents it per connector), the last
        # one wins. That's fine; each call only needs one to trigger the
        # "both sides on a harness" path, and consistency is re-checked
        # at execute time.
        return {u: h for (u, h) in rows}

    def _create_harness_with_endpoints(
        self,
        from_unit_id: int,
        to_unit_id: int,
        name_hint: Optional[str],
        from_pin_id: int,
        to_pin_id: int,
    ) -> WireHarness:
        """Create a new harness + 2 endpoints + 2 mating connectors + clone pins."""
        from app.models.interface import Unit
        from_unit = self.db.query(Unit).filter(Unit.id == from_unit_id).first()
        to_unit = self.db.query(Unit).filter(Unit.id == to_unit_id).first()
        from_conn = self._connector_of_pin(from_pin_id)
        to_conn = self._connector_of_pin(to_pin_id)

        # Name: user hint first, otherwise designation-concat (per Mason's spec)
        default_name = f"{from_unit.designation}-{to_unit.designation}" if from_unit and to_unit else "Harness"
        harness_name = name_hint or default_name

        harness = WireHarness(
            project_id=self.project_id,
            name=harness_name,
            description=f"Auto-created by auto-grow between {from_unit.designation if from_unit else '?'} and {to_unit.designation if to_unit else '?'}",
            # Legacy fields — kept in sync for back-compat with any existing
            # code/reports that still read from them. Mating connectors get
            # created below, then these get filled in.
            from_unit_id=from_unit_id,
            from_connector_id=from_conn.id if from_conn else None,
            to_unit_id=to_unit_id,
            to_connector_id=to_conn.id if to_conn else None,
        )
        self.db.add(harness)
        self.db.flush()  # assign harness.id

        # Create 2 endpoints — one per LRU connector
        if from_conn:
            self._create_endpoint(harness.id, from_conn, label="P1")
        if to_conn:
            self._create_endpoint(harness.id, to_conn, label="P2")

        return harness

    def _add_endpoint_for_new_side(self, harness_id: int, lru_pin_id: int):
        """Extend an existing harness with a new endpoint for the LRU side
        that isn't yet represented on the harness."""
        conn = self._connector_of_pin(lru_pin_id)
        if not conn:
            raise RuntimeError(f"Pin {lru_pin_id} has no LRU connector")
        # Figure out the next endpoint label (P3, P4, ...)
        count = self.db.query(func.count(HarnessEndpoint.id)).filter(HarnessEndpoint.harness_id == harness_id).scalar() or 0
        label = f"P{count + 1}"
        self._create_endpoint(harness_id, conn, label=label)

    def _create_endpoint(self, harness_id: int, lru_connector: Connector, label: str) -> HarnessEndpoint:
        """Clone LRU connector to create a mating connector, clone its pins,
        and insert a HarnessEndpoint row pointing at both."""
        # Clone connector spec (owner_type='harness', unit_id=NULL, gender flipped)
        mating = Connector(
            project_id=lru_connector.project_id,
            designator=(lru_connector.designator or "MATE") + "-MATE",
            name=f"{lru_connector.name} (mate)" if lru_connector.name else None,
            description="Harness-side mating connector (auto-created by auto-grow)",
            connector_type=lru_connector.connector_type,
            connector_type_custom=lru_connector.connector_type_custom,
            gender=_flip_gender(lru_connector.gender),
            mounting=lru_connector.mounting,
            mounting_custom=lru_connector.mounting_custom,
            shell_size=lru_connector.shell_size,
            insert_arrangement=lru_connector.insert_arrangement,
            total_contacts=lru_connector.total_contacts,
            signal_contacts=lru_connector.signal_contacts,
            power_contacts=lru_connector.power_contacts,
            coax_contacts=lru_connector.coax_contacts,
            fiber_contacts=lru_connector.fiber_contacts,
            spare_contacts=lru_connector.spare_contacts,
            keying=lru_connector.keying,
            polarization=lru_connector.polarization,
            coupling=lru_connector.coupling,
            ip_rating=lru_connector.ip_rating,
            operating_temp_min_c=lru_connector.operating_temp_min_c,
            operating_temp_max_c=lru_connector.operating_temp_max_c,
            mating_cycles=lru_connector.mating_cycles,
            shell_material=lru_connector.shell_material,
            shell_finish=lru_connector.shell_finish,
            contact_finish=lru_connector.contact_finish,
            mil_spec=lru_connector.mil_spec,
            connector_manufacturer=lru_connector.connector_manufacturer,
            backshell_type=lru_connector.backshell_type,
            unit_id=None,
            owner_type="harness",
        )
        self.db.add(mating)
        self.db.flush()

        # Clone pins 1:1. Direction stays IDENTICAL (Mason's spec). Mating
        # pin's mating_unit_id points at the LRU this mating connector faces,
        # so the mating connector "knows" its LRU partner.
        lru_pins = self.db.query(Pin).filter(Pin.connector_id == lru_connector.id).all()
        for p in lru_pins:
            self.db.add(Pin(
                connector_id=mating.id,
                pin_number=p.pin_number,
                pin_label=p.pin_label,
                signal_name=p.signal_name,
                signal_type=p.signal_type,
                signal_type_custom=p.signal_type_custom,
                direction=p.direction,
                pin_size=p.pin_size,
                contact_type=p.contact_type,
                voltage_nominal=p.voltage_nominal,
                voltage_min=p.voltage_min,
                voltage_max=p.voltage_max,
                voltage_dc_bias=p.voltage_dc_bias,
                current_nominal_amps=p.current_nominal_amps,
                current_max_amps=p.current_max_amps,
                impedance_ohms=p.impedance_ohms,
                frequency_mhz=p.frequency_mhz,
                rise_time_ns=p.rise_time_ns,
                termination=p.termination,
                pull_up_down=p.pull_up_down,
                esd_protection=p.esd_protection,
                description=p.description,
                notes=p.notes,
                mating_unit_id=lru_connector.unit_id,
            ))
        self.db.flush()

        endpoint = HarnessEndpoint(
            harness_id=harness_id,
            mating_connector_id=mating.id,
            lru_connector_id=lru_connector.id,
            label=label,
        )
        self.db.add(endpoint)
        self.db.flush()
        return endpoint

    def _connector_of_pin(self, pin_id: int) -> Optional[Connector]:
        pin = self.db.query(Pin).filter(Pin.id == pin_id).first()
        if not pin:
            return None
        return self.db.query(Connector).filter(Connector.id == pin.connector_id).first()

    def _create_wire(self, harness_id: int, pair: AutoGrowPair) -> int:
        """Create the wire row plus populate mating pin refs.

        Raises on conflict (pin already wired, wire number collision).
        """
        # Guard against double-wiring the same pin on the same harness
        existing = self.db.query(Wire).filter(
            Wire.harness_id == harness_id,
            (Wire.from_pin_id == pair.from_lru_pin_id) |
            (Wire.to_pin_id == pair.from_lru_pin_id) |
            (Wire.from_pin_id == pair.to_lru_pin_id) |
            (Wire.to_pin_id == pair.to_lru_pin_id),
        ).first()
        if existing:
            # Already wired — skip silently. This is expected if the same
            # auto-grow batch has redundant pairs.
            logger.info(f"auto-grow: skipping pair ({pair.from_lru_pin_id},{pair.to_lru_pin_id}) — already wired")
            return None

        # Resolve mating pins: find HarnessEndpoints whose lru_connector
        # matches each pin's connector, then find matching pin_number on
        # the mating connector.
        from_mating_pin = self._resolve_mating_pin(harness_id, pair.from_lru_pin_id)
        to_mating_pin = self._resolve_mating_pin(harness_id, pair.to_lru_pin_id)

        signal_name = pair.signal_name or self._default_signal_name(pair.from_lru_pin_id, pair.to_lru_pin_id)
        wire = Wire(
            harness_id=harness_id,
            wire_number=_next_wire_number(self.db, harness_id),
            signal_name=signal_name,
            wire_type=pair.wire_type or "discrete",
            wire_gauge=pair.wire_gauge,
            from_pin_id=pair.from_lru_pin_id,
            to_pin_id=pair.to_lru_pin_id,
            from_mating_pin_id=from_mating_pin.id if from_mating_pin else None,
            to_mating_pin_id=to_mating_pin.id if to_mating_pin else None,
        )
        self.db.add(wire)
        self.db.flush()
        return wire.id

    def _resolve_mating_pin(self, harness_id: int, lru_pin_id: int) -> Optional[Pin]:
        """Given a harness and an LRU pin, find the corresponding mating pin
        on the harness's mating connector (matched by pin_number)."""
        lru_pin = self.db.query(Pin).filter(Pin.id == lru_pin_id).first()
        if not lru_pin:
            return None

        endpoint = (self.db.query(HarnessEndpoint)
                    .filter(HarnessEndpoint.harness_id == harness_id,
                            HarnessEndpoint.lru_connector_id == lru_pin.connector_id)
                    .first())
        if not endpoint:
            return None

        return (self.db.query(Pin)
                .filter(Pin.connector_id == endpoint.mating_connector_id,
                        Pin.pin_number == lru_pin.pin_number)
                .first())

    def _default_signal_name(self, from_pin_id: int, to_pin_id: int) -> str:
        """Best effort signal name when none was supplied. Prefer the from
        side's signal_name; fall back to "SIGNAL_<from>_<to>"."""
        fp = self.db.query(Pin).filter(Pin.id == from_pin_id).first()
        if fp and fp.signal_name:
            return fp.signal_name
        tp = self.db.query(Pin).filter(Pin.id == to_pin_id).first()
        if tp and tp.signal_name:
            return tp.signal_name
        return f"SIGNAL_{from_pin_id}_{to_pin_id}"

    def _merge_harness(self, keep_id: int, fold_id: int):
        """Reparent everything from fold_id → keep_id, then delete fold_id.

        Order matters: wires first (they reference harness_id), then
        endpoints (they reference harness_id via FK), then the harness row.
        """
        # Reparent wires
        self.db.query(Wire).filter(Wire.harness_id == fold_id).update(
            {Wire.harness_id: keep_id}, synchronize_session="fetch"
        )
        # Reparent endpoints
        self.db.query(HarnessEndpoint).filter(HarnessEndpoint.harness_id == fold_id).update(
            {HarnessEndpoint.harness_id: keep_id}, synchronize_session="fetch"
        )
        # Delete the empty fold harness
        self.db.query(WireHarness).filter(WireHarness.id == fold_id).delete(synchronize_session="fetch")
        self.db.flush()

    def _upsert_connection(self, unit_a_id: int, unit_b_id: int) -> Optional[int]:
        """Ensure a Connection row exists for this unordered LRU pair.
        Returns the Connection.id. Canonical order: a < b."""
        a, b = _pair_key(unit_a_id, unit_b_id)
        existing = (self.db.query(Connection)
                    .filter(Connection.lru_a_id == a, Connection.lru_b_id == b)
                    .first())
        if existing:
            # Force updated_at to bump by reassigning — SQLAlchemy will pick
            # this up as a change and run the onupdate() trigger.
            existing.lru_a_id = a  # no-op assignment; triggers dirty flag
            self.db.flush()
            return existing.id
        conn = Connection(project_id=self.project_id, lru_a_id=a, lru_b_id=b)
        self.db.add(conn)
        self.db.flush()
        return conn.id


# ══════════════════════════════════════════════════════════════
#  Wire-delete hook: tear down Connection row if last wire gone
# ══════════════════════════════════════════════════════════════

def maybe_delete_connection_for_wire(db: Session, wire: Wire) -> bool:
    """Called AFTER a wire is deleted (or right before, if you're inside a
    transaction that will flush the delete). If no wires remain between the
    two LRUs, the Connection row gets removed.

    Returns True if a connection was deleted.
    """
    # Resolve the two LRUs from the wire's LRU-side pins
    from_conn = (db.query(Connector)
                 .join(Pin, Pin.connector_id == Connector.id)
                 .filter(Pin.id == wire.from_pin_id).first())
    to_conn = (db.query(Connector)
               .join(Pin, Pin.connector_id == Connector.id)
               .filter(Pin.id == wire.to_pin_id).first())
    if not from_conn or not to_conn or from_conn.unit_id is None or to_conn.unit_id is None:
        return False
    if from_conn.unit_id == to_conn.unit_id:
        return False

    a, b = _pair_key(from_conn.unit_id, to_conn.unit_id)

    # Count remaining wires between these two LRUs (excluding the one being
    # deleted). The query: for each remaining wire, resolve its from-pin's
    # unit and to-pin's unit, and check they form the same {a,b} pair. Using
    # a subquery with aliases to keep the SQL readable.
    from sqlalchemy.orm import aliased
    FromPin = aliased(Pin)
    ToPin = aliased(Pin)
    FromConn = aliased(Connector)
    ToConn = aliased(Connector)

    remaining = (
        db.query(func.count(Wire.id))
        .join(FromPin, FromPin.id == Wire.from_pin_id)
        .join(FromConn, FromConn.id == FromPin.connector_id)
        .join(ToPin, ToPin.id == Wire.to_pin_id)
        .join(ToConn, ToConn.id == ToPin.connector_id)
        .filter(
            Wire.id != wire.id,
            (
                ((FromConn.unit_id == a) & (ToConn.unit_id == b)) |
                ((FromConn.unit_id == b) & (ToConn.unit_id == a))
            )
        )
        .scalar()
    ) or 0

    if remaining == 0:
        conn = (db.query(Connection)
                .filter(Connection.lru_a_id == a, Connection.lru_b_id == b)
                .first())
        if conn:
            db.delete(conn)
            return True
    return False
