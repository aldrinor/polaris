"""LLM cluster-labeling per primary entity (F2 substrate, I-f2-002).

Given disambiguation clusters from `cluster_candidates` (I-f2-001),
ask an LLM for a one-line label per cluster naming the primary entity
(e.g. BPEI → syndrome / institute / chemical). Uses a Protocol so unit
tests stub without httpx + API key; integration adapter wires the real
OpenRouter client at I-f2-003.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from polaris_graph.intake.disambiguation_clusterer import ClusterResult

MAX_LABEL_WORDS = 8


@dataclass(frozen=True)
class LabeledCluster:
    cluster_id: int
    label: str
    sample_snippets: list[str]


class ClusterLabelClient(Protocol):
    def complete(self, prompt: str, *, max_tokens: int = 50) -> str: ...


def _truncate_label(text: str) -> str:
    words = text.strip().split()
    if len(words) > MAX_LABEL_WORDS:
        words = words[:MAX_LABEL_WORDS]
    return " ".join(words)


def _build_prompt(snippets: list[str]) -> str:
    snippet_block = "\n".join(f"- {s}" for s in snippets)
    return (
        "What entity is described by these snippets? "
        "Reply with ONE short noun phrase only (≤ 8 words). "
        "No quotes, no explanation, no trailing punctuation.\n\n"
        f"{snippet_block}"
    )


def label_clusters(
    cluster_result: ClusterResult,
    candidate_snippets: list[str],
    client: ClusterLabelClient,
    max_snippets_per_cluster: int = 3,
) -> list[LabeledCluster]:
    """Generate a one-line label per non-noise cluster.

    Validation order (per Codex iter-1 brief P2): length-mismatch check
    fires BEFORE the num_clusters == 0 early return so malformed
    all-noise inputs do not silently slip through (LAW II).
    """
    if len(candidate_snippets) != len(cluster_result.labels):
        raise ValueError(
            f"label_clusters: candidate_snippets length ({len(candidate_snippets)}) "
            f"does not match cluster_result.labels ({len(cluster_result.labels)})"
        )
    if cluster_result.num_clusters == 0:
        return []

    distinct_ids = sorted({lbl for lbl in cluster_result.labels if lbl != -1})
    out: list[LabeledCluster] = []
    for cid in distinct_ids:
        snippets_for_cluster = [
            candidate_snippets[i]
            for i, lbl in enumerate(cluster_result.labels)
            if lbl == cid
        ][:max_snippets_per_cluster]
        raw = client.complete(_build_prompt(snippets_for_cluster))
        label = _truncate_label(raw)
        if not label:
            raise ValueError(
                f"label_clusters: LLM returned empty label for cluster {cid}"
            )
        out.append(
            LabeledCluster(
                cluster_id=cid,
                label=label,
                sample_snippets=snippets_for_cluster,
            )
        )
    return out
