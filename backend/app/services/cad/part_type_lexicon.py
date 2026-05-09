"""TDD-CAT-002 — part-type lexicon.

Loads ``backend/catalog_seed/part_type_lexicon.json`` and provides a
most-specific-token-wins lookup. Each entry maps a list of tokens
("socket head cap screw", "shcs", ...) to a `part_class` enum value
plus an optional `part_subtype` finer grain.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SEED_DIR = Path(__file__).resolve().parents[3] / "catalog_seed"
_LEXICON_PATH = _SEED_DIR / "part_type_lexicon.json"


def _load() -> list[dict]:
    try:
        raw = json.loads(_LEXICON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("part_type_lexicon.json missing at %s", _LEXICON_PATH)
        return []
    except json.JSONDecodeError as exc:
        logger.error("part_type_lexicon.json invalid: %s", exc)
        return []
    if not isinstance(raw, list):
        logger.error("part_type_lexicon.json must be a list, got %s", type(raw))
        return []
    return raw


_LEXICON = _load()


@dataclass
class PartTypeMatch:
    part_class: str
    part_subtype: Optional[str] = None
    matched_token: str = ""
    confidence: str = "high"


def match_part_type(text: str) -> Optional[PartTypeMatch]:
    """Longest-token-wins lookup over the lexicon.

    Two-pass:
      1. Walk the lexicon; for each entry, find the longest token that
         appears in the haystack.
      2. Pick the entry with the longest matched token overall — so
         "socket head cap screw" beats "screw" alone.
    """
    if not text:
        return None
    haystack = text.lower()
    best_len = 0
    best: Optional[PartTypeMatch] = None
    for entry in _LEXICON:
        part_class = entry.get("part_class")
        part_subtype = entry.get("part_subtype")
        if not part_class:
            continue
        for tok in entry.get("tokens", []):
            t = tok.lower()
            if t in haystack and len(t) > best_len:
                best_len = len(t)
                best = PartTypeMatch(
                    part_class=part_class,
                    part_subtype=part_subtype,
                    matched_token=tok,
                )
    return best
