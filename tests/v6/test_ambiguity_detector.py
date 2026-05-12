"""Tests for the F2 ambiguity detector.

Per memory bpei_phantom_completion_lessons.md (commemoratively named
after the 2026-04-30 probe incident), the failure pattern must be
reproducible as a regression test: a short acronym question with
candidate snippets covering 2+ unrelated meanings → is_ambiguous=True.
"""

from __future__ import annotations

from polaris_v6.ambiguity_detector import (
    AmbiguityResult,
    CandidateSnippet,
    detect_ambiguity,
)


def test_unambiguous_single_topic_returns_false():
    snippets = [
        CandidateSnippet("s1", "Canadian housing starts rose 3.4% in Q3 2025 across major metros."),
        CandidateSnippet("s2", "CMHC reports housing starts up 3.4% Q3 2025 with regional variation."),
        CandidateSnippet("s3", "Q3 2025 housing starts data confirms a 3.4% national increase."),
    ]
    result = detect_ambiguity(snippets, min_cluster_size=2)
    assert result.is_ambiguous is False


def test_bpei_pattern_detects_ambiguity():
    snippets = [
        CandidateSnippet(
            "med1",
            "BPEI stands for blood pressure end-inspiration index in cardiovascular monitoring.",
        ),
        CandidateSnippet(
            "med2",
            "Clinicians use BPEI as a blood pressure end-inspiration measurement during respiratory cycle.",
        ),
        CandidateSnippet(
            "fin1",
            "BPEI in finance refers to bank-protected enterprise investment instruments.",
        ),
        CandidateSnippet(
            "fin2",
            "Bank-protected enterprise investment (BPEI) products carry sovereign-guarantee structures.",
        ),
    ]
    result = detect_ambiguity(snippets, min_cluster_size=2)
    assert result.is_ambiguous is True
    assert len(result.clusters) >= 2


def test_empty_snippets_returns_unambiguous():
    result = detect_ambiguity([], min_cluster_size=2)
    assert result.is_ambiguous is False
    assert result.clusters == []


def test_min_cluster_size_filter():
    snippets = [
        CandidateSnippet("a", "topic alpha alpha alpha widget widget"),
        CandidateSnippet("b", "topic alpha alpha alpha widget widget"),
        CandidateSnippet("c", "topic beta beta beta gizmo gizmo"),
    ]
    result = detect_ambiguity(snippets, min_cluster_size=2)
    assert result.is_ambiguous is False
    qualifying = [c for c in result.clusters if len(c.member_source_ids) >= 2]
    assert len(qualifying) == 1


def test_max_clusters_surfaced_caps():
    snippets = []
    for i, theme in enumerate(["alpha", "beta", "gamma", "delta", "epsilon"]):
        for j in range(2):
            snippets.append(CandidateSnippet(f"{theme}{j}", f"{theme} content {theme} {theme}"))
    result = detect_ambiguity(
        snippets, min_cluster_size=2, similarity_threshold=0.4, max_clusters_surfaced=3
    )
    assert isinstance(result, AmbiguityResult)
    assert len(result.clusters) <= 3
