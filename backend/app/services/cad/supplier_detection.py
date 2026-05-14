"""TDD-CAT-002 — vendor pattern detection.

Loads ``backend/catalog_seed/vendor_patterns.json`` once at import time
and exposes ``detect_supplier_from_filename`` for the STEP parser. Each
vendor entry maps a filename regex to a canonical supplier name +
known-alias list (for the supplier_aliases dedup table).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)


_SEED_DIR = Path(__file__).resolve().parents[3] / "catalog_seed"
_VENDOR_PATTERNS_PATH = _SEED_DIR / "vendor_patterns.json"


def _load_patterns() -> list[dict[str, Any]]:
    try:
        raw = json.loads(_VENDOR_PATTERNS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        logger.warning("vendor_patterns.json missing at %s", _VENDOR_PATTERNS_PATH)
        return []
    except json.JSONDecodeError as exc:
        logger.error("vendor_patterns.json invalid: %s", exc)
        return []

    out: list[dict[str, Any]] = []
    for vp in raw.get("patterns", []):
        try:
            out.append({
                "supplier_canonical": vp["supplier_canonical"],
                "regex": re.compile(vp["filename_regex"]),
                "mpn_capture_group": vp.get("mpn_capture_group", 1),
                "aliases": list(vp.get("aliases", [])),
            })
        except (re.error, KeyError) as exc:
            logger.warning(
                "Skipping invalid vendor pattern %s: %s",
                vp.get("supplier_canonical", "<unknown>"), exc,
            )
    return out


_VENDOR_PATTERNS = _load_patterns()


@dataclass
class SupplierMatch:
    canonical: str
    mpn: Optional[str]
    aliases: list[str] = field(default_factory=list)
    confidence: str = "high"


def detect_supplier_from_filename(filename: str) -> Optional[SupplierMatch]:
    """Match the basename against the loaded vendor regexes.

    First match wins; ordering of vendor_patterns.json controls precedence.
    Returns None when no pattern hits — callers default to Wardstone for
    in-house parts.
    """
    if not filename:
        return None
    basename = Path(filename).name
    for vp in _VENDOR_PATTERNS:
        m = vp["regex"].search(basename)
        if not m:
            continue
        try:
            mpn = m.group(vp["mpn_capture_group"])
        except IndexError:
            mpn = None
        # The canonical name itself counts as an alias (uniqueness in the
        # supplier_aliases table is enforced by the DB constraint).
        aliases = list(dict.fromkeys([vp["supplier_canonical"], *vp["aliases"]]))
        return SupplierMatch(
            canonical=vp["supplier_canonical"],
            mpn=mpn,
            aliases=aliases,
            confidence="high",
        )
    return None
