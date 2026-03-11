"""
ASTRA — Duplicate Requirement Detector
==========================================
File: backend/app/services/ai/duplicate_detector.py   ← NEW

Uses embedding-based cosine similarity to find:
  - Near-duplicate requirements within a project
  - Similar existing requirements when creating a new one

Results are grouped and scored for frontend display.
"""

import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.services.ai.embeddings import (
    is_embedding_available,
    generate_embedding,
    get_project_embeddings,
    cosine_similarity,
    get_embedding_info,
)
from app.schemas.ai_embeddings import (
    SimilarRequirement,
    DuplicateGroup,
    ProjectDuplicatesResponse,
    DuplicateCheckResponse,
)

logger = logging.getLogger("astra.ai.duplicates")


def find_duplicates(
    db: Session,
    project_id: int,
    threshold: float = 0.85,
) -> ProjectDuplicatesResponse:
    """
    Find all groups of near-duplicate requirements in a project.

    Computes pairwise cosine similarity between all requirement
    embeddings and groups those above the threshold.
    """
    if not is_embedding_available():
        return ProjectDuplicatesResponse(
            project_id=project_id,
            ai_available=False,
        )

    # Get all embeddings for the project
    embeddings = get_project_embeddings(db, project_id)

    if not embeddings:
        return ProjectDuplicatesResponse(
            project_id=project_id,
            total_requirements=0,
        )

    n = len(embeddings)

    # Build adjacency: pairs above threshold
    pairs: List[tuple] = []  # (i, j, similarity)
    for i in range(n):
        for j in range(i + 1, n):
            sim = cosine_similarity(embeddings[i][3], embeddings[j][3])
            if sim >= threshold:
                pairs.append((i, j, sim))

    if not pairs:
        return ProjectDuplicatesResponse(
            project_id=project_id,
            total_requirements=n,
            threshold=threshold,
        )

    # Union-Find to group connected duplicates
    parent = list(range(n))

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(x, y):
        px, py = find(x), find(y)
        if px != py:
            parent[px] = py

    for i, j, _ in pairs:
        union(i, j)

    # Collect groups
    groups_map: dict[int, list] = {}
    for idx in range(n):
        root = find(idx)
        groups_map.setdefault(root, []).append(idx)

    # Build DuplicateGroup objects (only groups with 2+ members)
    duplicate_groups: List[DuplicateGroup] = []
    group_counter = 0

    for root, members in groups_map.items():
        if len(members) < 2:
            continue

        group_counter += 1
        group_reqs: List[SimilarRequirement] = []
        similarities: List[float] = []

        # Compute pairwise similarities within the group
        for i in range(len(members)):
            idx_i = members[i]
            max_sim = 0.0
            for j in range(len(members)):
                if i == j:
                    continue
                idx_j = members[j]
                sim = cosine_similarity(embeddings[idx_i][3], embeddings[idx_j][3])
                max_sim = max(max_sim, sim)
                if j > i:
                    similarities.append(sim)

            req_id_pk, req_id_str, statement, _ = embeddings[idx_i]
            group_reqs.append(SimilarRequirement(
                requirement_id=req_id_pk,
                req_id=req_id_str,
                statement=statement[:200],
                similarity_score=round(max_sim, 4),
            ))

        duplicate_groups.append(DuplicateGroup(
            group_id=group_counter,
            requirements=group_reqs,
            max_similarity=round(max(similarities) if similarities else 0.0, 4),
            avg_similarity=round(
                sum(similarities) / len(similarities) if similarities else 0.0, 4
            ),
        ))

    # Sort by highest similarity first
    duplicate_groups.sort(key=lambda g: g.max_similarity, reverse=True)

    return ProjectDuplicatesResponse(
        project_id=project_id,
        total_requirements=n,
        duplicate_groups=duplicate_groups,
        threshold=threshold,
    )


def check_new_requirement(
    db: Session,
    statement: str,
    project_id: int,
    title: str = "",
    threshold: float = 0.75,
    top_k: int = 5,
) -> DuplicateCheckResponse:
    """
    Check if a new requirement statement is similar to existing ones.

    Called before creating a requirement to warn about potential duplicates.
    Returns the top-K most similar existing requirements above threshold.
    """
    if not is_embedding_available():
        return DuplicateCheckResponse(ai_available=False)

    # Generate embedding for the new statement
    new_embedding = generate_embedding(statement)
    if new_embedding is None:
        return DuplicateCheckResponse(ai_available=False)

    # Get all existing embeddings
    existing = get_project_embeddings(db, project_id)
    if not existing:
        return DuplicateCheckResponse()

    # Compute similarities
    scored: List[SimilarRequirement] = []
    for req_id_pk, req_id_str, req_statement, emb in existing:
        sim = cosine_similarity(new_embedding, emb)
        if sim >= threshold:
            scored.append(SimilarRequirement(
                requirement_id=req_id_pk,
                req_id=req_id_str,
                statement=req_statement[:200],
                similarity_score=round(sim, 4),
                explanation=_similarity_explanation(sim),
            ))

    # Sort by similarity, take top K
    scored.sort(key=lambda s: s.similarity_score, reverse=True)
    top_results = scored[:top_k]

    is_duplicate = any(s.similarity_score >= 0.90 for s in top_results)

    return DuplicateCheckResponse(
        is_likely_duplicate=is_duplicate,
        similar_requirements=top_results,
    )


def _similarity_explanation(score: float) -> str:
    """Generate a human-readable explanation for a similarity score."""
    if score >= 0.95:
        return "Near-identical statement — very likely a duplicate."
    elif score >= 0.90:
        return "Extremely similar — likely the same requirement worded differently."
    elif score >= 0.85:
        return "Highly similar — may cover the same functionality with minor differences."
    elif score >= 0.80:
        return "Moderately similar — overlapping scope, consider linking or merging."
    elif score >= 0.75:
        return "Somewhat similar — related topic, worth reviewing for overlap."
    else:
        return "Low similarity — likely a different requirement."
