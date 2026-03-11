"""
ASTRA — Embedding Generation Service
========================================
File: backend/app/services/ai/embeddings.py   ← NEW

Generates text embeddings for requirement statements to power:
  - Semantic duplicate detection
  - Trace link suggestion
  - Coverage gap analysis

Supports multiple embedding providers:
  - OpenAI text-embedding-3-small (cloud, 1536 dims)
  - Local sentence-transformers all-MiniLM-L6-v2 (air-gapped, 384 dims)

Embeddings are cached in the database (RequirementEmbedding table) and
only recomputed when the statement text changes (detected by SHA-256 hash).

Config env vars:
  EMBEDDING_PROVIDER  — "openai" | "local" | "" (disabled)
  AI_API_KEY          — Reuses the main AI API key for OpenAI embeddings
  EMBEDDING_MODEL     — Override model name (optional)
"""

import hashlib
import json
import logging
import math
import os
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

logger = logging.getLogger("astra.ai.embeddings")

# ── Configuration ──

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "").lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "")
AI_API_KEY = os.getenv("AI_API_KEY", "")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")

# Provider defaults
_PROVIDER_DEFAULTS = {
    "openai": {"model": "text-embedding-3-small", "dimensions": 1536},
    "local":  {"model": "all-MiniLM-L6-v2", "dimensions": 384},
}

# Lazy-loaded local model
_local_model = None
_local_model_loaded = False


def _get_config() -> dict:
    """Return provider config with defaults."""
    defaults = _PROVIDER_DEFAULTS.get(EMBEDDING_PROVIDER, {"model": "", "dimensions": 384})
    return {
        "provider": EMBEDDING_PROVIDER,
        "model": EMBEDDING_MODEL or defaults["model"],
        "dimensions": defaults["dimensions"],
    }


def is_embedding_available() -> bool:
    """Check if an embedding provider is configured."""
    return EMBEDDING_PROVIDER in ("openai", "local")


def get_embedding_info() -> dict:
    """Return embedding provider info for API responses."""
    cfg = _get_config()
    return {
        "available": is_embedding_available(),
        "provider": cfg["provider"],
        "model": cfg["model"],
        "dimensions": cfg["dimensions"],
    }


# ══════════════════════════════════════
#  Statement Hashing
# ══════════════════════════════════════

def hash_statement(text: str) -> str:
    """SHA-256 hash of normalized statement text for change detection."""
    normalized = " ".join(text.lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ══════════════════════════════════════
#  Embedding Generation
# ══════════════════════════════════════

def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate a vector embedding for a single text string.
    Returns None if embedding is unavailable or fails.
    """
    if not is_embedding_available():
        return None

    try:
        if EMBEDDING_PROVIDER == "openai":
            return _embed_openai([text])[0]
        elif EMBEDDING_PROVIDER == "local":
            return _embed_local([text])[0]
    except Exception as exc:
        logger.error("Embedding generation failed: %s", exc)
        return None


def batch_generate_embeddings(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Generate embeddings for a batch of texts.
    Returns a list of embeddings (or None for failures) in the same order.
    """
    if not texts:
        return []
    if not is_embedding_available():
        return [None] * len(texts)

    try:
        if EMBEDDING_PROVIDER == "openai":
            return _embed_openai(texts)
        elif EMBEDDING_PROVIDER == "local":
            return _embed_local(texts)
    except Exception as exc:
        logger.error("Batch embedding failed: %s", exc)
        return [None] * len(texts)


# ── OpenAI Embeddings ──

def _embed_openai(texts: List[str]) -> List[List[float]]:
    """Call OpenAI embeddings API. Handles batching for large lists."""
    import httpx

    cfg = _get_config()
    base_url = AI_BASE_URL or "https://api.openai.com/v1"
    headers = {
        "Authorization": f"Bearer {AI_API_KEY}",
        "Content-Type": "application/json",
    }

    all_embeddings: List[List[float]] = []
    batch_size = 100  # OpenAI limit per request

    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        payload = {
            "input": batch,
            "model": cfg["model"],
        }

        with httpx.Client(timeout=60) as client:
            resp = client.post(
                f"{base_url}/embeddings",
                headers=headers,
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()

        # Sort by index to maintain order
        sorted_data = sorted(data["data"], key=lambda x: x["index"])
        all_embeddings.extend([item["embedding"] for item in sorted_data])

    return all_embeddings


# ── Local Sentence-Transformers ──

def _embed_local(texts: List[str]) -> List[List[float]]:
    """Generate embeddings using local sentence-transformers model."""
    global _local_model, _local_model_loaded

    if not _local_model_loaded:
        try:
            from sentence_transformers import SentenceTransformer
            cfg = _get_config()
            logger.info("Loading local embedding model: %s", cfg["model"])
            _local_model = SentenceTransformer(cfg["model"])
            _local_model_loaded = True
            logger.info("Local embedding model loaded successfully")
        except ImportError:
            logger.error(
                "sentence-transformers not installed. "
                "Install with: pip install sentence-transformers"
            )
            raise RuntimeError("sentence-transformers not installed")
        except Exception as exc:
            logger.error("Failed to load local embedding model: %s", exc)
            raise

    embeddings = _local_model.encode(texts, show_progress_bar=False)
    return [emb.tolist() for emb in embeddings]


# ══════════════════════════════════════
#  Database Caching
# ══════════════════════════════════════

def get_or_create_embedding(
    db: Session,
    requirement_id: int,
    statement: str,
    force: bool = False,
) -> Optional[List[float]]:
    """
    Get cached embedding or generate a new one.

    Returns the embedding vector, or None if embedding is unavailable.
    Caches the result in the database for future use.
    """
    from app.models.embedding import RequirementEmbedding

    current_hash = hash_statement(statement)
    cfg = _get_config()

    # Check cache
    cached = (
        db.query(RequirementEmbedding)
        .filter(RequirementEmbedding.requirement_id == requirement_id)
        .first()
    )

    if cached and not force:
        # Return cached if statement hasn't changed and model matches
        if (cached.statement_hash == current_hash
                and cached.model_version == cfg["model"]
                and cached.embedding):
            return cached.embedding

    # Generate new embedding
    embedding = generate_embedding(statement)
    if embedding is None:
        return None

    # Upsert into database
    if cached:
        cached.embedding = embedding
        cached.dimensions = len(embedding)
        cached.model_version = cfg["model"]
        cached.statement_hash = current_hash
    else:
        cached = RequirementEmbedding(
            requirement_id=requirement_id,
            embedding=embedding,
            dimensions=len(embedding),
            model_version=cfg["model"],
            statement_hash=current_hash,
        )
        db.add(cached)

    try:
        db.commit()
    except Exception:
        db.rollback()
        logger.error("Failed to cache embedding for requirement %d", requirement_id)

    return embedding


def get_project_embeddings(
    db: Session,
    project_id: int,
    force: bool = False,
) -> List[Tuple[int, str, str, List[float]]]:
    """
    Get embeddings for all requirements in a project.

    Returns list of (requirement_id, req_id, statement, embedding) tuples.
    Generates missing embeddings as needed.
    """
    from app.models import Requirement
    from app.models.embedding import RequirementEmbedding

    # Get all requirements in project
    requirements = (
        db.query(Requirement)
        .filter(
            Requirement.project_id == project_id,
            Requirement.status != "deleted",
        )
        .all()
    )

    if not requirements:
        return []

    results: List[Tuple[int, str, str, List[float]]] = []
    to_embed: List[Tuple[int, str]] = []  # (req_id_pk, statement)

    # Load existing embeddings
    existing = {
        e.requirement_id: e
        for e in db.query(RequirementEmbedding)
        .filter(RequirementEmbedding.requirement_id.in_([r.id for r in requirements]))
        .all()
    }

    cfg = _get_config()

    for req in requirements:
        cached = existing.get(req.id)
        current_hash = hash_statement(req.statement)

        if (cached and not force
                and cached.statement_hash == current_hash
                and cached.model_version == cfg["model"]
                and cached.embedding):
            results.append((req.id, req.req_id, req.statement, cached.embedding))
        else:
            to_embed.append((req.id, req.statement))

    # Batch-embed missing requirements
    if to_embed and is_embedding_available():
        texts = [t[1] for t in to_embed]
        embeddings = batch_generate_embeddings(texts)

        for (req_id_pk, statement), embedding in zip(to_embed, embeddings):
            if embedding is None:
                continue

            # Find matching requirement for req_id string
            req_obj = next((r for r in requirements if r.id == req_id_pk), None)
            req_id_str = req_obj.req_id if req_obj else ""

            results.append((req_id_pk, req_id_str, statement, embedding))

            # Cache in DB
            cached = existing.get(req_id_pk)
            if cached:
                cached.embedding = embedding
                cached.dimensions = len(embedding)
                cached.model_version = cfg["model"]
                cached.statement_hash = hash_statement(statement)
            else:
                new_embed = RequirementEmbedding(
                    requirement_id=req_id_pk,
                    embedding=embedding,
                    dimensions=len(embedding),
                    model_version=cfg["model"],
                    statement_hash=hash_statement(statement),
                )
                db.add(new_embed)

        try:
            db.commit()
        except Exception:
            db.rollback()
            logger.error("Failed to cache batch embeddings for project %d", project_id)

    return results


# ══════════════════════════════════════
#  Cosine Similarity
# ══════════════════════════════════════

def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if len(a) != len(b) or not a:
        return 0.0

    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))

    if norm_a == 0 or norm_b == 0:
        return 0.0

    return dot / (norm_a * norm_b)
