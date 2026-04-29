"""
ASTRA — Record Content Hash Helper (e-signature record binding)
================================================================
File: backend/app/services/security/record_hash.py

Produces a canonical SHA-256 hash of an entity's content so electronic
signatures can be bound to the specific record state at sign time.
21 CFR Part 11 §11.70 binding requirement.

Covers AUDIT_FINDINGS F-008.

Usage::

    from app.services.security.record_hash import compute_record_hash
    rec_hash = compute_record_hash("requirement", req)

The registry is pluggable — register a hasher for a new entity_type with
``@register_entity_hasher("my_type")``. The supplied hasher receives the
entity object (any attribute-bearing object) and must return a hex SHA-256.
"""

import hashlib
from typing import Any, Callable, Dict


# Registry of entity_type → hasher
_HASHERS: Dict[str, Callable[[Any], str]] = {}


def register_entity_hasher(entity_type: str) -> Callable:
    """Decorator: register a content hasher for *entity_type*."""

    def _wrap(fn: Callable[[Any], str]) -> Callable[[Any], str]:
        _HASHERS[entity_type] = fn
        return fn

    return _wrap


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ══════════════════════════════════════
#  Built-in hashers
# ══════════════════════════════════════


@register_entity_hasher("requirement")
def _hash_requirement(entity: Any) -> str:
    """Canonical hash of a Requirement: req_id|version|title|statement|rationale."""
    parts = [
        str(getattr(entity, "req_id", "")),
        str(getattr(entity, "version", "")),
        str(getattr(entity, "title", "")),
        str(getattr(entity, "statement", "")),
        str(getattr(entity, "rationale", "") or ""),
    ]
    return _sha256("|".join(parts))


@register_entity_hasher("baseline")
def _hash_baseline(entity: Any) -> str:
    """Canonical hash of a Baseline: name|requirements_count|created_at."""
    parts = [
        str(getattr(entity, "name", "")),
        str(getattr(entity, "requirements_count", "")),
        str(getattr(entity, "created_at", "")),
    ]
    return _sha256("|".join(parts))


# ══════════════════════════════════════
#  Public API
# ══════════════════════════════════════


def compute_record_hash(entity_type: str, entity: Any) -> str:
    """
    Compute the canonical content hash of *entity*.

    Raises ``ValueError`` if no hasher is registered for *entity_type*.
    Returned hash is hex-encoded SHA-256 (64 chars).
    """
    hasher = _HASHERS.get(entity_type)
    if hasher is None:
        raise ValueError(
            f"No record-hash registered for entity_type='{entity_type}'. "
            f"Use @register_entity_hasher to add one."
        )
    return hasher(entity)


def supported_entity_types() -> list[str]:
    """Return the list of entity_types with a registered hasher."""
    return sorted(_HASHERS.keys())
