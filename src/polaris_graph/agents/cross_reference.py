"""
Cross-Reference Scoring via Embedding Cosine Similarity
========================================================
Identifies claims corroborated by multiple independent sources by computing
pairwise cosine similarity on evidence statement embeddings and grouping
evidence that exceeds a similarity threshold from distinct source URLs.

Algorithm:
    1. Extract embeddable text (statement field) from each evidence dict.
    2. Compute embeddings via the shared EmbeddingService singleton.
    3. Build an (n x n) cosine similarity matrix using normalized embeddings
       (dot product = cosine similarity when embeddings are L2-normalized).
    4. For each evidence pair (i, j) where sim(i, j) > threshold AND
       source_url(i) != source_url(j), record an edge.
    5. Connected-component discovery via union-find produces cross-reference
       groups.  Groups with fewer than min_sources unique URLs are discarded.
    6. Each surviving group is emitted with an agreement_score (mean pairwise
       similarity of group members) and cross_ref_count (unique source URLs).

Configuration (env vars, LAW VI):
    PG_CROSS_REF_MIN_SOURCES   - Minimum distinct sources per group (default 3)
    PG_CROSS_REF_SIM_THRESHOLD - Cosine similarity threshold (default 0.65)
    PG_CROSS_REF_MAX_EVIDENCE  - Evidence cap before processing (default 1500)
"""

import logging
import os
from typing import Optional

import numpy as np

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration helpers (LAW VI: no hard-coded values)
# ---------------------------------------------------------------------------

def _get_min_sources() -> int:
    """Read minimum unique-source count from env or use default."""
    return int(os.getenv("PG_CROSS_REF_MIN_SOURCES", "3"))


def _get_sim_threshold() -> float:
    """Read cosine-similarity threshold from env or use default."""
    return float(os.getenv("PG_CROSS_REF_SIM_THRESHOLD", "0.65"))


def _get_max_evidence() -> int:
    """Read evidence cap from env or use default."""
    return int(os.getenv("PG_CROSS_REF_MAX_EVIDENCE", "1500"))


# ---------------------------------------------------------------------------
# Union-Find (Disjoint Set Union) for connected-component discovery
# ---------------------------------------------------------------------------

class _UnionFind:
    """Lightweight union-find with path compression and union-by-rank."""

    def __init__(self, n: int) -> None:
        self._parent = list(range(n))
        self._rank = [0] * n

    def find(self, x: int) -> int:
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]  # path halving
            x = self._parent[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1

    def components(self) -> dict[int, list[int]]:
        """Return mapping of root -> list of member indices."""
        groups: dict[int, list[int]] = {}
        for i in range(len(self._parent)):
            root = self.find(i)
            groups.setdefault(root, []).append(i)
        return groups


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_text(evidence: dict) -> str:
    """
    Extract the embeddable text from an evidence dict.

    Prefers ``statement`` (the atomic fact).  Falls back to ``direct_quote``
    if statement is absent or empty.
    """
    text = (evidence.get("statement") or "").strip()
    if not text:
        text = (evidence.get("direct_quote") or "").strip()
    return text


def _compute_similarity_matrix(embeddings: np.ndarray) -> np.ndarray:
    """
    Compute the full pairwise cosine-similarity matrix.

    Because the EmbeddingService returns L2-normalized vectors, cosine
    similarity equals the dot product.  The result is an (n x n) float32
    matrix.
    """
    # embeddings shape: (n, d) — already L2-normalized
    return embeddings @ embeddings.T  # (n, n)


def _build_groups(
    sim_matrix: np.ndarray,
    source_urls: list[str],
    sim_threshold: float,
    min_sources: int,
) -> list[tuple[list[int], float]]:
    """
    Discover cross-reference groups from the similarity matrix.

    Returns a list of (member_indices, mean_pairwise_similarity) tuples
    for groups that meet the min_sources requirement.
    """
    n = sim_matrix.shape[0]
    uf = _UnionFind(n)

    # --- Build edges: sim > threshold AND different source ---
    # Use upper triangle to avoid duplicate work
    row_indices, col_indices = np.triu_indices(n, k=1)
    upper_sims = sim_matrix[row_indices, col_indices]
    above_threshold = upper_sims > sim_threshold

    for idx in np.where(above_threshold)[0]:
        i_val = int(row_indices[idx])
        j_val = int(col_indices[idx])
        if source_urls[i_val] != source_urls[j_val]:
            uf.union(i_val, j_val)

    # --- Extract qualifying groups ---
    results: list[tuple[list[int], float]] = []
    for members in uf.components().values():
        if len(members) < 2:
            continue

        unique_urls = {source_urls[m] for m in members}
        if len(unique_urls) < min_sources:
            continue

        # Mean pairwise similarity within the group
        if len(members) == 2:
            mean_sim = float(sim_matrix[members[0], members[1]])
        else:
            member_arr = np.array(members, dtype=int)
            pair_sims = sim_matrix[np.ix_(member_arr, member_arr)]
            triu_vals = pair_sims[np.triu_indices_from(pair_sims, k=1)]
            mean_sim = float(np.mean(triu_vals))

        results.append((members, mean_sim))

    return results


def _select_representative_claim(
    members: list[int],
    texts: list[str],
    embeddings: np.ndarray,
) -> str:
    """
    Pick the evidence text closest to the group centroid as the
    representative claim statement.
    """
    member_arr = np.array(members, dtype=int)
    group_embeddings = embeddings[member_arr]  # (k, d)
    centroid = group_embeddings.mean(axis=0)    # (d,)
    # Normalize centroid so dot product = cosine similarity
    norm = np.linalg.norm(centroid)
    if norm > 0:
        centroid /= norm
    sims_to_centroid = group_embeddings @ centroid  # (k,)
    best_local_idx = int(np.argmax(sims_to_centroid))
    return texts[members[best_local_idx]]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def compute_cross_references(
    evidence: list[dict],
    min_sources: Optional[int] = None,
    sim_threshold: Optional[float] = None,
) -> list[dict]:
    """
    Compute cross-reference groups from a list of evidence dicts.

    Each returned group represents a claim corroborated by multiple
    independent sources whose evidence statements are semantically similar.

    Args:
        evidence:      List of evidence dicts (must contain ``evidence_id``,
                       ``source_url``, and ``statement`` or ``direct_quote``).
        min_sources:   Minimum number of distinct source URLs required for a
                       group to qualify (env: ``PG_CROSS_REF_MIN_SOURCES``,
                       default 3).
        sim_threshold: Cosine-similarity threshold for considering two pieces
                       of evidence as semantically equivalent (env:
                       ``PG_CROSS_REF_SIM_THRESHOLD``, default 0.65).

    Returns:
        List of cross-reference group dicts, each containing::

            {
                "claim":            str,   # representative statement
                "evidence_ids":     list[str],
                "source_urls":      list[str],
                "agreement_score":  float, # mean pairwise cosine similarity
                "cross_ref_count":  int,   # number of unique source URLs
            }

        Sorted descending by ``agreement_score``.
        Returns an empty list if embedding fails or no groups qualify.
    """
    # --- Resolve configuration ---
    if min_sources is None:
        min_sources = _get_min_sources()
    if sim_threshold is None:
        sim_threshold = _get_sim_threshold()
    max_evidence = _get_max_evidence()

    if not evidence:
        logger.debug("compute_cross_references: empty evidence list, returning []")
        return []

    # --- Cap evidence to avoid excessive memory / compute ---
    if len(evidence) > max_evidence:
        logger.info(
            "Cross-reference: capping evidence from %d to %d (PG_CROSS_REF_MAX_EVIDENCE)",
            len(evidence),
            max_evidence,
        )
        evidence = evidence[:max_evidence]

    n = len(evidence)
    logger.info(
        "Computing cross-references for %d evidence pieces "
        "(sim_threshold=%.2f, min_sources=%d)",
        n,
        sim_threshold,
        min_sources,
    )

    # --- Extract texts and source URLs ---
    texts: list[str] = []
    source_urls: list[str] = []
    evidence_ids: list[str] = []
    valid_indices: list[int] = []

    for idx, ev in enumerate(evidence):
        text = _extract_text(ev)
        if not text:
            continue
        texts.append(text)
        source_urls.append(ev.get("source_url", ""))
        evidence_ids.append(ev.get("evidence_id", f"unknown_{idx}"))
        valid_indices.append(idx)

    if len(texts) < min_sources:
        logger.debug(
            "Cross-reference: only %d valid evidence pieces, need at least %d sources",
            len(texts),
            min_sources,
        )
        return []

    # --- Compute embeddings (graceful fallback on failure) ---
    try:
        from src.utils.embedding_service import embed_texts as _embed_texts

        raw_embeddings = _embed_texts(texts)
        embeddings = np.array(raw_embeddings, dtype=np.float32)
    except Exception:
        logger.exception(
            "Cross-reference: embedding computation failed, returning empty list"
        )
        return []

    if embeddings.shape[0] == 0:
        return []

    # --- Build similarity matrix ---
    sim_matrix = _compute_similarity_matrix(embeddings)

    # --- Discover groups ---
    groups = _build_groups(sim_matrix, source_urls, sim_threshold, min_sources)

    if not groups:
        logger.info("Cross-reference: no qualifying groups found")
        return []

    # --- Format output ---
    results: list[dict] = []
    for members, agreement_score in groups:
        group_evidence_ids = [evidence_ids[m] for m in members]
        group_source_urls = sorted({source_urls[m] for m in members})
        claim = _select_representative_claim(members, texts, embeddings)

        results.append({
            "claim": claim,
            "evidence_ids": group_evidence_ids,
            "source_urls": group_source_urls,
            "agreement_score": round(agreement_score, 4),
            "cross_ref_count": len(group_source_urls),
        })

    # Sort by agreement_score descending
    results.sort(key=lambda g: g["agreement_score"], reverse=True)

    logger.info(
        "Cross-reference: found %d groups (top agreement=%.3f, top sources=%d)",
        len(results),
        results[0]["agreement_score"] if results else 0.0,
        results[0]["cross_ref_count"] if results else 0,
    )

    return results
