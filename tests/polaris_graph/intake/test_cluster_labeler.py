"""Unit tests for I-f2-002 — cluster_labeler.

Uses a FakeClient stub (regular class, NOT unittest.mock per CLAUDE.md §9.4)
so tests do not require httpx + API key.
"""

from __future__ import annotations

import pytest

from polaris_graph.intake.cluster_labeler import (
    LabeledCluster,
    label_clusters,
)
from polaris_graph.intake.disambiguation_clusterer import ClusterResult


class FakeClient:
    """Minimal sync LLM stub returning a fixed string per call.

    `responses` is consumed in order; if exhausted, returns final string.
    """

    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.calls: list[str] = []

    def complete(self, prompt: str, *, max_tokens: int = 50) -> str:
        self.calls.append(prompt)
        if self._responses:
            return self._responses.pop(0)
        return "fallback"


def test_labels_one_per_cluster() -> None:
    cluster_result = ClusterResult(
        labels=[0, 0, 0, 1, 1, 1],
        num_clusters=2,
        is_ambiguous=True,
    )
    snippets = ["a1", "a2", "a3", "b1", "b2", "b3"]
    client = FakeClient(["syndrome", "institute"])

    out = label_clusters(cluster_result, snippets, client)

    assert len(out) == 2
    assert out[0] == LabeledCluster(cluster_id=0, label="syndrome", sample_snippets=["a1", "a2", "a3"])
    assert out[1] == LabeledCluster(cluster_id=1, label="institute", sample_snippets=["b1", "b2", "b3"])


def test_no_clusters_returns_empty() -> None:
    cluster_result = ClusterResult(labels=[-1, -1], num_clusters=0, is_ambiguous=False)
    client = FakeClient(["unused"])

    out = label_clusters(cluster_result, ["x", "y"], client)

    assert out == []
    assert client.calls == []


def test_mismatched_lengths_raises() -> None:
    cluster_result = ClusterResult(labels=[0, 0, 1], num_clusters=2, is_ambiguous=True)
    client = FakeClient(["a", "b"])

    with pytest.raises(ValueError, match="does not match"):
        label_clusters(cluster_result, ["only_one_snippet"], client)


def test_empty_llm_response_raises() -> None:
    cluster_result = ClusterResult(labels=[0, 0], num_clusters=1, is_ambiguous=False)
    client = FakeClient(["   "])

    with pytest.raises(ValueError, match="empty label"):
        label_clusters(cluster_result, ["s1", "s2"], client)


def test_long_label_truncated() -> None:
    cluster_result = ClusterResult(labels=[0, 0], num_clusters=1, is_ambiguous=False)
    long_response = " ".join(f"word{i}" for i in range(20))
    client = FakeClient([long_response])

    out = label_clusters(cluster_result, ["s1", "s2"], client)

    assert len(out) == 1
    assert len(out[0].label.split()) == 8
    assert out[0].label == " ".join(f"word{i}" for i in range(8))


def test_skip_noise_label() -> None:
    cluster_result = ClusterResult(
        labels=[-1, 0, 0, -1, 1, 1],
        num_clusters=2,
        is_ambiguous=True,
    )
    snippets = ["noise1", "a1", "a2", "noise2", "b1", "b2"]
    client = FakeClient(["cluster_zero", "cluster_one"])

    out = label_clusters(cluster_result, snippets, client)

    assert [lc.cluster_id for lc in out] == [0, 1]
    assert out[0].sample_snippets == ["a1", "a2"]
    assert out[1].sample_snippets == ["b1", "b2"]
    assert len(client.calls) == 2
