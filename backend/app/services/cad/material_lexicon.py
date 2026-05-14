"""TDD-CAT-002 — material lexicon.

Loads ``backend/catalog_seed/material_lexicon.json`` and provides a
longest-match lookup against a free-text blob (typically the STEP
filename + product name).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_SEED_DIR = Path(__file__).resolve().parents[3] / "catalog_seed"
_MATERIAL_LEXICON_PATH = _SEED_DIR / "material_lexicon.json"


def _load() -> dict[str, dict]:
    try:
        return json.loads(_MATERIAL_LEXICON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("material_lexicon.json missing at %s", _MATERIAL_LEXICON_PATH)
        return {}
    except json.JSONDecodeError as exc:
        logger.error("material_lexicon.json invalid: %s", exc)
        return {}


_LEXICON = _load()


@dataclass
class MaterialMatch:
    material_class: str       # e.g. "stainless_steel"
    material_name: str        # original alias text, e.g. "18-8 Stainless Steel"
    density_g_per_mm3: Optional[float] = None
    confidence: str = "high"


def match_material(text: str) -> Optional[MaterialMatch]:
    """Longest-alias-wins lookup. Common-noun aliases like "Stainless"
    are deliberately last so the more specific "18-8 Stainless Steel"
    binds first when both are present.
    """
    if not text:
        return None
    haystack = text.lower()
    best_len = 0
    best: Optional[MaterialMatch] = None
    for cls, info in _LEXICON.items():
        density = info.get("density_g_per_mm3")
        for alias in info.get("aliases", []):
            al = alias.lower()
            if al in haystack and len(al) > best_len:
                best_len = len(al)
                best = MaterialMatch(
                    material_class=cls,
                    material_name=alias,
                    density_g_per_mm3=density,
                )
    return best


def density_for(material_class: str) -> Optional[float]:
    return (_LEXICON.get(material_class) or {}).get("density_g_per_mm3")
