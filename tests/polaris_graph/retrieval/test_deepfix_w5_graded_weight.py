"""I-deepfix-001 (#1344) w5_graded_weight — offline RED->GREEN tests.

Two W5 content-relevance changes, both WEIGHT-only (§-1.3 weight-not-filter; the FROZEN faithfulness
engine strict_verify / NLI / 4-role D8 / provenance / span-grounding lives in other modules and is
never imported or altered here):

  1. _graded_weight: the near-binary {1.0, demote_w} band becomes a clamped monotone ramp in
     [demote_w, 1.0] — a GLM-SUPPORTED ambiguous passage now carries a GRADED weight, not flat 1.0.
  2. window max-pool: the reranker scores up to N bounded windows of a body and max-pools, so a
     topical span buried after a chrome head is not mis-demoted.

Offline: the reranker + GLM judge are INJECTED via ``reranker_predict_fn`` / ``glm_judge_fn`` — no
model loads, no GPU, no network, no paid LLM.
"""
from __future__ import annotations

from src.polaris_graph.generator.relevance_judge import LABEL_SUPPORTED
from src.polaris_graph.retrieval.content_relevance_judge import (
    LABEL_DEMOTED,
    LABEL_ESCALATED_KEEP,
    LABEL_RELEVANT,
    _DEFAULT_DEMOTE_WEIGHT,
    score_passages,
)


def test_graded_weight_is_monotone_not_binary():
    """Two GLM-SUPPORTED ambiguous passages (rerank 0.20 / 0.60) get GRADED weights
    demote < w_low < w_high < 1.0 (RED pre-fix: both flat 1.0)."""
    passages = [
        (0, "u0", "a short body about the topic in question here"),
        (1, "u1", "another short body about the same topic here"),
    ]
    report = score_passages(
        "does the drug lower blood pressure?",
        passages,
        reranker_predict_fn=lambda pairs: [0.20, 0.60],
        glm_judge_fn=lambda q, span: (LABEL_SUPPORTED, "on topic"),
    )
    by_idx = report.by_idx()
    w_low = by_idx[0].weight
    w_high = by_idx[1].weight
    assert by_idx[0].label == LABEL_ESCALATED_KEEP
    assert by_idx[1].label == LABEL_ESCALATED_KEEP
    assert _DEFAULT_DEMOTE_WEIGHT < w_low < w_high < 1.0


def test_ambiguous_judge_receives_winning_window_not_head_chrome():
    """A body whose 2000-char HEAD window is chrome (scores ~0.01) but whose LATER window is
    topical (scores ~0.60, landing in the ambiguous band [0.05, 0.70)) must have its GLM judge
    called on the WINNING (0.60) window, NOT the raw head.

    RED pre-fix: ``_resolve_ambiguous`` judged ``(body or '')[:passage_chars]`` (the 0.01 head),
    so the topical span was never seen and the paper was GLM-demoted on chrome.
    GREEN: the winning max-pool window (carrying 'TOPICAL') is what the judge receives."""
    judged_spans: list[str] = []

    def _glm(_question: str, span: str) -> tuple[str, str]:
        judged_spans.append(span)
        return (LABEL_SUPPORTED, "on topic")

    # >2000 chars so _body_windows yields 2 windows: head (chrome) + a later topical window.
    head_chrome = "x " * 1100  # 2200 chars of furniture -> fills the first 2000-char window
    body = head_chrome + "TOPICAL clinical finding about blood pressure lowering here."
    passages = [(0, "u0", body)]
    report = score_passages(
        "does the drug lower blood pressure?",
        passages,
        # per-WINDOW reranker score: 0.60 (ambiguous) for the topical window, 0.01 for the head.
        reranker_predict_fn=lambda pairs: [
            0.60 if "TOPICAL" in p[1] else 0.01 for p in pairs
        ],
        glm_judge_fn=_glm,
    )
    assert len(judged_spans) == 1, "the ambiguous passage should be escalated exactly once"
    assert "TOPICAL" in judged_spans[0], (
        "the GLM judge must receive the WINNING 0.60 window (topical span), not the 0.01 chrome head"
    )
    # confirm it went through the ambiguous->escalation path (not high-band auto-keep).
    assert report.by_idx()[0].escalated is True


def test_high_band_saturates_and_junk_floors():
    """Regression guard: a high-confidence passage still saturates to 1.0; junk still floors to
    the demote weight (never dropped)."""
    passages = [
        (0, "u0", "clearly relevant body about the exact topic asked"),
        (1, "u1", "totally unrelated boilerplate junk paragraph here"),
    ]
    report = score_passages(
        "does the drug lower blood pressure?",
        passages,
        reranker_predict_fn=lambda pairs: [0.99, 0.001],
    )
    by_idx = report.by_idx()
    assert by_idx[0].label == LABEL_RELEVANT
    assert by_idx[0].weight == 1.0
    assert by_idx[1].label == LABEL_DEMOTED
    assert by_idx[1].weight == _DEFAULT_DEMOTE_WEIGHT


def test_window_maxpool_rescues_topical_span_after_head_chrome():
    """A body whose first 2000-char head is chrome but which has a topical span AFTER it is
    RESCUED by the window max-pool (RED pre-fix: the single head window scored low -> demoted)."""
    body = ("x " * 1100) + "TOPICAL relevant clinical finding for the question here."
    passages = [(0, "u0", body)]
    # Injected reranker scores per WINDOW: high iff the window contains the buried keyword.
    report = score_passages(
        "does the drug lower blood pressure?",
        passages,
        reranker_predict_fn=lambda pairs: [
            0.95 if "TOPICAL" in p[1] else 0.01 for p in pairs
        ],
    )
    by_idx = report.by_idx()
    assert report.n_demoted == 0
    assert by_idx[0].label == LABEL_RELEVANT
    assert by_idx[0].weight == 1.0
