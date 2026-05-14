"""Tests for backend/app/services/cad/part_type_lexicon.py.

Targets two behaviours that the McMaster 92196A196 misclassification
exposed:
  1. McMaster's plain "Socket Head Screw" wording must resolve to the
     same subtype as the full "Socket Head Cap Screw" form.
  2. The new plain fallback tokens ("screw", "bolt", ...) must NOT
     shadow more specific entries — "machine screw" still wins over
     the bare "screw" fallback because the matcher is
     longest-token-wins, not JSON-order-wins.
"""

from __future__ import annotations

from app.services.cad.part_type_lexicon import match_part_type


def test_socket_head_screw_matches_socket_head_cap_screw_subtype():
    m = match_part_type("Socket Head Screw")
    assert m is not None
    assert m.part_class == "fastener_screw"
    assert m.part_subtype == "socket_head_cap_screw"


def test_machine_screw_beats_plain_screw_fallback():
    m = match_part_type("machine screw")
    assert m is not None
    assert m.part_class == "fastener_screw"
    assert m.part_subtype == "machine_screw"


def test_plain_screw_fallback_still_classifies_unknown_screw():
    m = match_part_type("Some Mystery Screw")
    assert m is not None
    assert m.part_class == "fastener_screw"
    assert m.part_subtype is None
