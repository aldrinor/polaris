"""I-bug-084 — coverage scorer. Uses BenchmarkQuestion.expected_pico_keywords
when set; falls back to expected_anchors otherwise. Returns 1.0 if all
target tokens are present (case-insensitive substring match) in the
response, 0.0 otherwise. Empty keywords AND empty anchors → 0.0."""

from __future__ import annotations

from polaris_v6.benchmark.schema import BenchmarkQuestion


def score_response_coverage(
    question: BenchmarkQuestion, response_text: str
) -> float:
    targets = question.expected_pico_keywords or question.expected_anchors
    if not targets:
        return 0.0
    lower = response_text.lower()
    return 1.0 if all(t.lower() in lower for t in targets) else 0.0
