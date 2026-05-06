"""Unit tests for I-f2-001 — HDBSCAN clustering substrate.

Synthetic numpy embeddings only (no real embedding model load) per
CLAUDE.md §8.4: heavy ML is forbidden in autonomous loops.
"""

from __future__ import annotations

import numpy as np
import pytest

from polaris_graph.intake.disambiguation_clusterer import (
    ClusterResult,
    cluster_candidates,
)


def _gaussian_cloud(rng: np.random.Generator, center: tuple[float, ...], n: int, scale: float = 0.05) -> np.ndarray:
    """Make `n` points centered at `center` with small Gaussian noise."""
    centroid = np.array(center, dtype=np.float64)
    noise = rng.normal(loc=0.0, scale=scale, size=(n, len(center)))
    return centroid + noise


def test_three_clear_clusters_ambiguous() -> None:
    rng = np.random.default_rng(seed=42)
    cloud_a = _gaussian_cloud(rng, (0.0, 0.0), 5)
    cloud_b = _gaussian_cloud(rng, (10.0, 10.0), 5)
    cloud_c = _gaussian_cloud(rng, (-10.0, -10.0), 5)
    embeddings = np.vstack([cloud_a, cloud_b, cloud_c])

    result = cluster_candidates(embeddings)

    assert isinstance(result, ClusterResult)
    assert result.num_clusters == 3
    assert result.is_ambiguous is True


def test_single_dense_cluster_unambiguous() -> None:
    rng = np.random.default_rng(seed=7)
    embeddings = _gaussian_cloud(rng, (0.0, 0.0), 10)

    result = cluster_candidates(embeddings)

    assert result.num_clusters == 1
    assert result.is_ambiguous is False


def test_two_clusters_ambiguous() -> None:
    rng = np.random.default_rng(seed=11)
    cloud_a = _gaussian_cloud(rng, (0.0, 0.0), 5)
    cloud_b = _gaussian_cloud(rng, (10.0, 10.0), 5)
    embeddings = np.vstack([cloud_a, cloud_b])

    result = cluster_candidates(embeddings)

    assert result.num_clusters == 2
    assert result.is_ambiguous is True


def test_below_min_cluster_size_returns_noise() -> None:
    embeddings = np.array([[0.5, 0.5]], dtype=np.float64)

    result = cluster_candidates(embeddings, min_cluster_size=2)

    assert result.num_clusters == 0
    assert result.is_ambiguous is False
    assert result.labels == [-1]


def test_empty_input_raises() -> None:
    embeddings = np.empty((0, 384), dtype=np.float64)

    with pytest.raises(ValueError, match="empty embedding array"):
        cluster_candidates(embeddings)
