"""I-bug-084 — coverage scorer. Uses BenchmarkQuestion.expected_pico_keywords
when set; falls back to expected_anchors otherwise. Returns 1.0 if all
target tokens are present (case-insensitive substring match) in the
response, 0.0 otherwise. Empty keywords AND empty anchors → 0.0."""

from __future__ import annotations

from polaris_v6.benchmark.schema import BenchmarkQuestion


def score_response_coverage(
    question: BenchmarkQuestion, response_text: str
) -> float:
    """Score whether a response covers a question's expected target tokens.

    Prefers ``expected_pico_keywords`` when non-empty, else falls back to
    ``expected_anchors``. Matching is all-or-nothing: every target must appear
    as a case-insensitive substring of ``response_text``.

    Args:
        question: The benchmark question supplying the target token list.
        response_text: The system response to check for coverage.

    Returns:
        ``1.0`` if every target token is present in the response, else ``0.0``.
        Returns ``0.0`` when both keyword and anchor lists are empty.
    """
    targets = question.expected_pico_keywords or question.expected_anchors
    if not targets:
        return 0.0
    lower = response_text.lower()
    return 1.0 if all(t.lower() in lower for t in targets) else 0.0
