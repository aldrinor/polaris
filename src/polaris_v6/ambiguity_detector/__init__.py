"""Ambiguity detector — HDBSCAN-based detection of multi-meaning queries
before retrieval. Surfaces a disambiguation modal when ≥2 distinct
concept-clusters share the query's entity space.

Pattern: embed candidate retrievals → HDBSCAN cluster → if ≥2 clusters
with min_cluster_size sources, the question is ambiguous and the UI
shows a disambiguation modal.

``candidate_fetcher`` (I-rdy-009 / #505) supplies the candidate snippets
for a question-only query via one cheap web search — the "Phase 1"
retrieval the detector docstring anticipated.

Historical: this module was originally named ``bpei/`` after the
2026-04-30 'phantom completion' incident where a user typed the literal
string "BPEI" as an adversarial probe and the system fabricated an
answer. The directory carried the commemorative tag through 2026-05-12,
when I-naming-001 (GH#434) renamed it to its descriptive name. See
``memory/bpei_phantom_completion_lessons.md`` (user-level memory at
``~/.claude/projects/C--POLARIS/memory/``) for the incident write-up.
"""
from .ambiguity_detector import (
    AmbiguityCluster,
    AmbiguityResult,
    CandidateSnippet,
    detect_ambiguity,
)
from .candidate_fetcher import CandidateFetchError, fetch_candidate_snippets

__all__ = [
    "AmbiguityCluster",
    "AmbiguityResult",
    "CandidateSnippet",
    "CandidateFetchError",
    "detect_ambiguity",
    "fetch_candidate_snippets",
]
