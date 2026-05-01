"""HDBSCAN-based ambiguity detector for research questions.

Per docs/carney_delivery_plan_FINAL.md F2 (ambiguity detector backend) and
memory bpei_phantom_completion_lessons.md, the BPEI failure happened
because the scope gate has no way to detect when a short acronym question
maps to multiple unrelated source clusters. This module fixes that by:

1. Running a cheap candidate retrieval (top-K from search providers).
2. Embedding the candidate snippets via a deterministic encoder.
3. Clustering with HDBSCAN.
4. If ≥2 clusters meet min_cluster_size, return AmbiguityResult with
   per-cluster representative snippets so the UI can render a
   disambiguation modal.

Phase 0 ships the API surface + a pure-Python fallback that uses character
3-gram cosine + a simple density-based grouping when scikit-learn /
hdbscan are not installed (so this code can be unit-tested without the
heavy ML stack). Phase 1 wires the real HDBSCAN path once the backend
venv is provisioned.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Sequence


@dataclass
class CandidateSnippet:
    """One candidate retrieval result feeding the disambiguation pass."""

    source_id: str
    text: str


@dataclass
class AmbiguityCluster:
    """A discovered semantic cluster of candidates."""

    cluster_id: int
    representative_text: str
    member_source_ids: list[str] = field(default_factory=list)


@dataclass
class AmbiguityResult:
    """Detector verdict.

    `is_ambiguous` is True iff there are ≥2 clusters each with at least
    `min_cluster_size` members. Each cluster's representative snippet is
    surfaced to the user via the F2 disambiguation modal.
    """

    is_ambiguous: bool
    clusters: list[AmbiguityCluster]
    fallback_used: bool = False


_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _trigrams(text: str) -> Counter[str]:
    text_lower = text.lower()
    counts: Counter[str] = Counter()
    for token in _TOKEN_RE.findall(text_lower):
        padded = f"  {token}  "
        for i in range(len(padded) - 2):
            counts[padded[i : i + 3]] += 1
    return counts


def _cosine(a: Counter[str], b: Counter[str]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(a[k] * b[k] for k in a.keys() & b.keys())
    norm_a = math.sqrt(sum(v * v for v in a.values()))
    norm_b = math.sqrt(sum(v * v for v in b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _greedy_cluster(
    snippets: Sequence[CandidateSnippet], *, similarity_threshold: float
) -> list[list[int]]:
    if not snippets:
        return []
    grams = [_trigrams(s.text) for s in snippets]
    unassigned = list(range(len(snippets)))
    clusters: list[list[int]] = []
    while unassigned:
        seed = unassigned.pop(0)
        members = [seed]
        remaining: list[int] = []
        for idx in unassigned:
            if _cosine(grams[seed], grams[idx]) >= similarity_threshold:
                members.append(idx)
            else:
                remaining.append(idx)
        unassigned = remaining
        clusters.append(members)
    return clusters


def detect_ambiguity(
    snippets: Sequence[CandidateSnippet],
    *,
    min_cluster_size: int = 2,
    similarity_threshold: float = 0.5,
    max_clusters_surfaced: int = 4,
) -> AmbiguityResult:
    """Detect whether a candidate set has ≥2 distinct semantic clusters.

    Args:
        snippets: candidate retrieval snippets.
        min_cluster_size: a cluster must have at least this many members
            to count toward the ambiguity verdict.
        similarity_threshold: trigram-cosine cutoff for the fallback
            clusterer.
        max_clusters_surfaced: cap on clusters returned to UI.
    """
    if not snippets:
        return AmbiguityResult(is_ambiguous=False, clusters=[], fallback_used=True)

    raw_clusters = _greedy_cluster(snippets, similarity_threshold=similarity_threshold)
    qualifying = [c for c in raw_clusters if len(c) >= min_cluster_size]
    qualifying.sort(key=len, reverse=True)
    qualifying = qualifying[:max_clusters_surfaced]

    out_clusters = [
        AmbiguityCluster(
            cluster_id=i,
            representative_text=snippets[member_indices[0]].text,
            member_source_ids=[snippets[idx].source_id for idx in member_indices],
        )
        for i, member_indices in enumerate(qualifying)
    ]

    return AmbiguityResult(
        is_ambiguous=len(out_clusters) >= 2,
        clusters=out_clusters,
        fallback_used=True,
    )
