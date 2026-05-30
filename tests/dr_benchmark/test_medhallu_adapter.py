"""The 9 scorer fixtures Codex mandated before any MedHallu model run (I-safety-002a / #924).

These validate the pure scoring logic with NO model load and NO spend. They must be green
before `medhallu_runner` is allowed to load the NLI model. See
.codex/I-safety-002a/codex_medhallu_design.txt.
"""

from __future__ import annotations

import pytest

from scripts.dr_benchmark.medhallu_adapter import (
    Candidate,
    Confusion,
    RunGuards,
    StrictVerifyMisuseError,
    add_prediction,
    aggregate_answer_verdict,
    assert_source_isolated,
    build_evidence_object,
    build_source_text,
    claim_is_faithful,
    expected_candidate_count,
    metrics,
    pair_row,
)

_ROW = {
    "row_id": "42",
    "question": "Does drug X reduce mortality in condition Y?",
    "knowledge": "In trial Z, drug X reduced 30-day mortality from 12% to 9% (p=0.04).",
    "ground_truth": "Drug X reduced 30-day mortality from 12% to 9%.",
    "hallucinated_answer": "Drug X eliminated mortality entirely in all patients.",
}


# Fixture 1 — pairing: one row -> exactly two candidates, one negative one positive.
def test_pairing_one_row_two_candidates() -> None:
    cands = pair_row(_ROW, split="pqa_labeled")
    assert len(cands) == 2
    kinds = {c.candidate_kind for c in cands}
    assert kinds == {"ground_truth", "hallucinated"}
    gt = next(c for c in cands if c.candidate_kind == "ground_truth")
    hl = next(c for c in cands if c.candidate_kind == "hallucinated")
    assert gt.gold_hallucinated is False
    assert hl.gold_hallucinated is True
    assert all(c.row_id == "42" and c.split == "pqa_labeled" for c in cands)


# Fixture 2 — source isolation: source = Question + Knowledge only; no candidate leaks.
def test_source_isolation_no_candidate_leak() -> None:
    src = build_source_text(_ROW["question"], _ROW["knowledge"])
    assert _ROW["question"] in src and _ROW["knowledge"] in src
    assert _ROW["ground_truth"] not in src
    assert _ROW["hallucinated_answer"] not in src
    # building the evidence object must not embed the candidate answer either
    for cand in pair_row(_ROW, "pqa_labeled"):
        ev = build_evidence_object("some claim", _ROW["question"], _ROW["knowledge"], cand)
        assert _ROW["ground_truth"] not in ev["direct_quote"]
        assert _ROW["hallucinated_answer"] not in ev["direct_quote"]


def test_source_isolation_raises_on_leak() -> None:
    leaky_cand = Candidate("42", "pqa_labeled", "Knowledge: leaked answer", False, "ground_truth")
    leaky_source = "Question: q\n\nKnowledge: Knowledge: leaked answer"
    with pytest.raises(ValueError):
        assert_source_isolated(leaky_source, leaky_cand)


# Fixture 3 — strict-verify guard: raw answers carry no provenance tokens; strict_verify
# cannot score them, and the adapter exposes the misuse guard (never a strict_verify path).
def test_strict_verify_not_applicable_to_raw_answers() -> None:
    from src.polaris_graph.clinical_generator.strict_verify import extract_tokens

    assert extract_tokens(_ROW["ground_truth"]) == []
    assert extract_tokens(_ROW["hallucinated_answer"]) == []
    # the guard symbol exists so any future misuse is fail-closed
    assert issubclass(StrictVerifyMisuseError, RuntimeError)


# Fixture 4 — aggregation: all-faithful -> faithful; any-unsupported -> hallucinated.
def test_aggregation_rule() -> None:
    assert aggregate_answer_verdict([True, True]) == "faithful"
    assert aggregate_answer_verdict([True, False]) == "hallucinated"
    assert aggregate_answer_verdict([False]) == "hallucinated"
    assert aggregate_answer_verdict([]) == "invalid"


# Fixture 5 — threshold boundary: 0.65 passes with >=, 0.6499 fails (entailed label).
def test_threshold_boundary() -> None:
    assert claim_is_faithful(0.65, label=1) is True
    assert claim_is_faithful(0.6499, label=1) is False
    # not entailed -> never faithful regardless of prob
    assert claim_is_faithful(0.99, label=0) is False


# Fixture 6 — confusion matrix -> known F1 (positive class = hallucinated).
def test_confusion_to_known_f1() -> None:
    conf = Confusion()
    # 3 TP, 1 FP, 1 FN, 3 TN  -> P=0.75, R=0.75, F1=0.75, specificity=0.75
    for _ in range(3):
        add_prediction(conf, "hallucinated", gold_hallucinated=True)   # TP
    add_prediction(conf, "hallucinated", gold_hallucinated=False)      # FP
    add_prediction(conf, "faithful", gold_hallucinated=True)          # FN
    for _ in range(3):
        add_prediction(conf, "faithful", gold_hallucinated=False)      # TN
    m = metrics(conf)
    assert (conf.tp, conf.fp, conf.fn, conf.tn) == (3, 1, 1, 3)
    assert m["precision"] == pytest.approx(0.75)
    assert m["recall"] == pytest.approx(0.75)
    assert m["f1"] == pytest.approx(0.75)
    assert m["specificity"] == pytest.approx(0.75)
    assert m["balanced_accuracy"] == pytest.approx(0.75)


def test_invalid_counted_aside_not_scored() -> None:
    conf = Confusion()
    add_prediction(conf, "invalid", gold_hallucinated=True)
    assert conf.invalid == 1 and conf.tp == 0 and conf.fn == 0


# Fixture 7 — split counts: 1k pqa_labeled + 9k pqa_artificial -> 2k + 18k candidates.
def test_split_candidate_counts() -> None:
    counts = expected_candidate_count(n_labeled=1000, n_artificial=9000)
    assert counts["pqa_labeled"] == 2000
    assert counts["pqa_artificial"] == 18000
    assert counts["total"] == 20000


# Fixture 8 — NLI unavailable -> abort the headline, never silently fall back.
def test_nli_unavailable_aborts_headline() -> None:
    with pytest.raises(RuntimeError, match="NLI model unavailable"):
        RunGuards(nli_model_available=False).assert_headline_valid()


# Fixture 9 — negative-control run cannot be recorded as the headline artifact.
def test_negative_control_cannot_be_headline() -> None:
    with pytest.raises(RuntimeError, match="negative-control"):
        RunGuards(nli_model_available=True, negative_control=True).assert_headline_valid()


def test_clean_headline_guard_passes() -> None:
    RunGuards(nli_model_available=True, negative_control=False).assert_headline_valid()
