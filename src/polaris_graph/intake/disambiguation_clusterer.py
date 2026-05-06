"""HDBSCAN clustering on top-K retrieval candidate embeddings (F2 substrate).

Per Carney v6.2 §F2 Diversify-then-Verify: cluster the top-K candidate
embeddings; if HDBSCAN finds more than one dense cluster the user query
is ambiguous (e.g. "BPEI" → syndrome / institute / chemical clusters),
and the disambiguation modal should fire. A single dense cluster (or
one-cluster-allowed result) means the query is unambiguous (e.g.
"tirzepatide" → all candidates about the drug).

This module is substrate-only:
- Consumes pre-computed `np.ndarray` of shape (K, D); does NOT call
  any embedding model at runtime (per CLAUDE.md §8.4 "no heavy ML in
  autonomous loops"). Wiring into `live_retriever.py` is I-f2-003.
- Wraps `hdbscan.HDBSCAN` with `allow_single_cluster=True` so a
  tightly-packed candidate set returns 1 cluster rather than 0.

Pre-condition: `embeddings` should be L2-normalized for euclidean
metric to be monotonic with cosine distance.
"""

from __future__ import annotations

from dataclasses import dataclass

import hdbscan
import numpy as np


@dataclass(frozen=True)
class ClusterResult:
    """Result of HDBSCAN clustering on candidate embeddings.

    Attributes:
        labels: HDBSCAN cluster id per candidate (-1 = noise/outlier).
        num_clusters: Count of distinct non-noise cluster ids.
        is_ambiguous: True iff num_clusters > 1.
    """

    labels: list[int]
    num_clusters: int
    is_ambiguous: bool


def cluster_candidates(
    embeddings: np.ndarray,
    min_cluster_size: int = 2,
) -> ClusterResult:
    """Cluster candidate embeddings with HDBSCAN.

    Args:
        embeddings: Shape (K, D) float array of candidate embeddings.
        min_cluster_size: HDBSCAN minimum cluster size (default 2 per
            Carney v6.2 §F2 spec).

    Returns:
        ClusterResult with labels, num_clusters, is_ambiguous.

    Raises:
        ValueError: If `embeddings` is empty (LAW II — fail loudly).

    Edge cases:
        - K < min_cluster_size: HDBSCAN cannot cluster; returns
          num_clusters=0, is_ambiguous=False, labels all -1.
    """
    if embeddings.size == 0:
        raise ValueError(
            "cluster_candidates: empty embedding array; cannot cluster"
        )

    n_candidates = embeddings.shape[0]
    if n_candidates < min_cluster_size:
        return ClusterResult(
            labels=[-1] * n_candidates,
            num_clusters=0,
            is_ambiguous=False,
        )

    clusterer = hdbscan.HDBSCAN(
        min_cluster_size=min_cluster_size,
        metric="euclidean",
        allow_single_cluster=True,
    )
    raw_labels = clusterer.fit_predict(embeddings)
    labels = [int(label) for label in raw_labels]
    distinct_clusters = set(labels) - {-1}
    num_clusters = len(distinct_clusters)
    return ClusterResult(
        labels=labels,
        num_clusters=num_clusters,
        is_ambiguous=num_clusters > 1,
    )
