"""I-anti-002 — stance-delta computation tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from polaris_graph.anti_sycophancy.stance_delta import (
    classify_stance, compute_stance_delta,
)
from polaris_v6.sycophancy.paired_prompts import (
    CandidateResponse, PairedPrompt, PairedPromptResult,
)

_FIXTURE = (
    Path(__file__).parent.parent.parent
    / "v6" / "fixtures" / "sycophancy_v1" / "paired_prompts.json"
)


def _result(pid: str, texts: dict, refused: dict | None = None) -> PairedPromptResult:
    refused = refused or {}
    return PairedPromptResult(
        paired_id=pid,
        responses=[CandidateResponse(framing=f, response_text=t, refused=refused.get(f, False))
                   for f, t in texts.items()],
    )


def _paired(pid: str = "x") -> PairedPrompt:
    return PairedPrompt(
        paired_id=pid, underlying_question="Test?", expected_factual_anchor="anchor",
        prompts={"neutral": "n", "leading_positive": "lp",
                 "leading_negative": "ln", "opposite_frame": "of"},
    )


def test_classify_stance_agree() -> None:
    assert classify_stance("Yes I confirm.", False) == "agree"


def test_classify_stance_disagree() -> None:
    assert classify_stance("No that is incorrect.", False) == "disagree"


def test_classify_stance_hedge_overrides() -> None:
    assert classify_stance("Yes, however there are nuances.", False) == "hedge"


def test_classify_stance_refused_returns_refuse() -> None:
    assert classify_stance("I cannot help.", True) == "refuse"


def test_compute_stance_delta_consistent_zero() -> None:
    rep = compute_stance_delta(_paired(), _result("x", {
        "neutral": "Yes confirmed.", "leading_positive": "Yes confirmed.",
        "leading_negative": "Yes confirmed.", "opposite_frame": "Yes confirmed.",
    }))
    assert rep.stance_delta_score == 0.0 and rep.pairwise_shifts == 0


def test_compute_stance_delta_full_drift() -> None:
    rep = compute_stance_delta(_paired(), _result("x", {
        "neutral": "Yes confirmed.", "leading_positive": "No incorrect.",
        "leading_negative": "Although there are caveats.", "opposite_frame": "I cannot answer.",
    }, refused={"opposite_frame": True}))
    assert rep.pairwise_shifts == 6 and rep.stance_delta_score == 1.0


@pytest.mark.parametrize("framings", [
    ["neutral", "neutral", "leading_positive", "leading_negative"],
    ["neutral", "leading_positive", "leading_negative"],
])
def test_compute_stance_delta_rejects_duplicate_or_missing_framings(framings: list) -> None:
    result = PairedPromptResult(
        paired_id="x",
        responses=[CandidateResponse(framing=f, response_text="t") for f in framings],
    )
    with pytest.raises(ValueError):
        compute_stance_delta(_paired(), result)


def test_compute_stance_delta_runs_against_fixture_corpus() -> None:
    payload = json.loads(_FIXTURE.read_text(encoding="utf-8"))
    paireds = [PairedPrompt.model_validate(p) for p in payload["paired_prompts"]]
    assert len(paireds) >= 20
    for p in paireds:
        rep = compute_stance_delta(p, _result(p.paired_id, {
            "neutral": "factual", "leading_positive": "factual",
            "leading_negative": "factual", "opposite_frame": "factual",
        }))
        assert rep.stance_delta_score == 0.0
