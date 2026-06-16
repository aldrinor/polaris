"""I-cred-012 (#1162) — credibility-pass ORCHESTRATOR. Offline, deterministic, no network.

Exercises the full P4→P3→P2→P5→P6 chain over the effective pool, plus the fail-loud posture
(missing evidence_id / judge_error → abort_credibility_pass_error, never a silent false-green)."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.polaris_graph.generator.provenance_generator import SentenceVerification
from src.polaris_graph.synthesis.credibility_pass import (
    CredibilityAnalysis,
    CredibilityPassError,
    apply_disclosure_to_svs,
    credibility_redesign_enabled,
    run_credibility_analysis,
)

GOV = ("gov.uk", "who.int")


def _row(eid, url, *, auth=0.7, conf="HIGH", text="claim text", sig=None):
    return {
        "evidence_id": eid, "source_url": url, "authority_score": auth,
        "authority_confidence": conf, "signal_scores": sig or {"signal_scholarly": 0.8},
        "title": "T", "text": text, "snippet": text, "published_date": "2023-01-01",
    }


def _good_judge(question, payload):
    return {"reliability_score": 0.8, "relevance_score": 0.9, "rationale": "ok", "query_need": ""}


def test_flag_default_off(monkeypatch):
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    assert credibility_redesign_enabled() is False


@pytest.mark.parametrize("on", ["1", "true", "on", "yes", "TRUE"])
def test_flag_on(monkeypatch, on):
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", on)
    assert credibility_redesign_enabled() is True


def test_empty_rows_empty_analysis():
    a = run_credibility_analysis("q", [], gov_suffixes=GOV)
    assert isinstance(a, CredibilityAnalysis) and a.credibility_by_evidence == {} and a.claims == []


def test_happy_path_full_chain():
    rows = [
        _row("e1", "https://www.nature.com/a", text="Vaccine reduced hospitalization by 50 percent."),
        _row("e2", "https://www.who.int/b", text="Vaccine showed no effect on hospitalization."),
    ]
    a = run_credibility_analysis("vaccine hospitalization", rows, gov_suffixes=GOV, judge=_good_judge)
    assert set(a.credibility_by_evidence) == {"e1", "e2"}
    assert set(a.origin_by_evidence) == {"e1", "e2"}
    ec = a.credibility_by_evidence["e1"]
    assert 0.0 <= ec.credibility_weight <= 1.0 and ec.origin_cluster_id
    assert a.weight_mass is not None  # P6 ran over the post-P3 judgments


def test_fail_loud_missing_evidence_id():
    with pytest.raises(CredibilityPassError) as exc:
        run_credibility_analysis("q", [_row("", "https://www.nature.com/a")], gov_suffixes=GOV, judge=_good_judge)
    assert "abort_credibility_pass_error" in str(exc.value)


def test_per_source_judge_error_labels_credibility_unscored_never_aborts():
    # I-arch-005 B12 (#1257, operator-locked 2026-06-14 "VERIFY = LABEL, NEVER HOLD"): a per-source
    # judge_error no longer ABORTS the whole report. The source is LABELED credibility_unscored
    # (priors-only weight) and the rest keep scoring. A judge that returns a non-dict -> P2 marks
    # judge_error for THAT row -> the pass labels it + continues (no CredibilityPassError).
    def bad_judge(question, payload):
        return "not-a-dict"

    a = run_credibility_analysis(
        "q", [_row("e1", "https://www.nature.com/a")], gov_suffixes=GOV, judge=bad_judge,
    )
    ec = a.credibility_by_evidence["e1"]
    assert ec.credibility_unscored is True        # the disclosed gap label is set
    # priors-only weight is the source's deterministic authority (0.7), never fabricated, never NaN
    assert 0.0 <= ec.credibility_weight <= 1.0


def test_partial_judge_error_labels_only_the_errored_source_scores_the_rest():
    # 1-of-2 judge_error: the errored source is labeled credibility_unscored; the OTHER keeps its
    # LLM judgment; the report does NOT abort the basket.
    def flaky_judge(question, payload):
        # error ONLY for e1; e2 gets a normal judgment.
        if payload.get("evidence_id") == "e1":
            return "not-a-dict"
        return {"reliability_score": 0.8, "relevance_score": 0.9, "rationale": "ok", "query_need": ""}

    rows = [
        _row("e1", "https://www.nature.com/a", text="Vaccine reduced hospitalization by 50 percent."),
        _row("e2", "https://www.who.int/b", text="Vaccine showed no effect on hospitalization."),
    ]
    a = run_credibility_analysis("q", rows, gov_suffixes=GOV, judge=flaky_judge)
    assert a.credibility_by_evidence["e1"].credibility_unscored is True
    assert a.credibility_by_evidence["e2"].credibility_unscored is False
    # both sources are still present (CONSOLIDATE, don't DROP) — the errored one is labeled, not removed
    assert set(a.credibility_by_evidence) == {"e1", "e2"}


def test_two_of_n_judge_error_labels_only_the_two_scores_the_rest_no_abort():
    # P2.1 (I-arch-005 B12-P1): TWO of N sources error -> those TWO are labeled credibility_unscored
    # (priors-only weight), the REST keep their LLM judgments, and the report does NOT abort the basket.
    errored = {"e2", "e4"}

    def flaky_judge(question, payload):
        # error for e2 + e4; e1 / e3 / e5 get a normal judgment.
        if payload.get("evidence_id") in errored:
            return "not-a-dict"
        return {"reliability_score": 0.8, "relevance_score": 0.9, "rationale": "ok", "query_need": ""}

    rows = [
        _row("e1", "https://www.nature.com/a", auth=0.7),
        _row("e2", "https://www.who.int/b", auth=0.6),
        _row("e3", "https://www.cdc.gov/c", auth=0.8),
        _row("e4", "https://www.science.org/d", auth=0.5),
        _row("e5", "https://www.nih.gov/e", auth=0.9),
    ]
    a = run_credibility_analysis("q", rows, gov_suffixes=GOV, judge=flaky_judge)
    # all five present (CONSOLIDATE, don't DROP) — nothing removed
    assert set(a.credibility_by_evidence) == {"e1", "e2", "e3", "e4", "e5"}
    # exactly the two errored sources are labeled credibility_unscored
    labeled = {eid for eid, ec in a.credibility_by_evidence.items() if ec.credibility_unscored}
    assert labeled == errored
    # the labeled two carry their real DETERMINISTIC priors-only weight (== clamp01(authority_score))
    assert a.credibility_by_evidence["e2"].credibility_weight == pytest.approx(0.6)
    assert a.credibility_by_evidence["e4"].credibility_weight == pytest.approx(0.5)
    # the other three kept their LLM judgment (0.8 * 0.9 = 0.72), NOT priors
    assert a.credibility_by_evidence["e1"].credibility_unscored is False
    assert a.credibility_by_evidence["e1"].credibility_weight == pytest.approx(0.72)


def _sv(sentence, eids, *, is_verified=True):
    return SentenceVerification(
        sentence=sentence,
        tokens=[SimpleNamespace(evidence_id=e, start=0, end=1) for e in eids],
        is_verified=is_verified,
    )


def test_true_coverage_gap_cited_eid_with_no_credibility_row_fails_loud_with_disclosed_reason():
    # P2.2 (I-arch-005 B12-P1): the GENUINE provenance hole stays fail-loud (it is NOT a recoverable
    # infra condition). A CITED evidence_id ("e_missing") emitted by the resolver that has NO credibility
    # row at all is a real coverage gap: refusing to disclose a claim whose source the activated pass
    # never scored. It must FAIL LOUD with the DISCLOSED reason (abort_credibility_coverage_gap) — never
    # a silent skip, never a content-free stub. "e0" is covered; "e_missing" is not.
    rows = [_row("e0", "https://www.nature.com/a")]
    analysis = run_credibility_analysis("q", rows, gov_suffixes=GOV, judge=_good_judge)
    assert "e0" in analysis.credibility_by_evidence and "e_missing" not in analysis.credibility_by_evidence
    sv = _sv("The vaccine reduced hospitalization.", ["e0", "e_missing"])
    with pytest.raises(CredibilityPassError) as exc:
        apply_disclosure_to_svs([sv], analysis)
    # the disclosed reason is present (a LABELED/disclosed artifact, never a silent or content-free stub)
    assert "abort_credibility_coverage_gap" in str(exc.value)
    assert "e_missing" in str(exc.value)


def test_coverage_holds_when_all_cited_eids_are_scored():
    # The mirror of P2.2: when EVERY cited evidence_id has a credibility row, apply_disclosure_to_svs
    # does NOT raise (no false coverage gap) — proving the fail-loud is scoped to the genuine hole only.
    rows = [
        _row("e0", "https://www.nature.com/a", text="Vaccine reduced hospitalization by 50 percent."),
        _row("e1", "https://www.who.int/b", text="Vaccine reduced hospitalization by 50 percent."),
    ]
    analysis = run_credibility_analysis("q", rows, gov_suffixes=GOV, judge=_good_judge)
    out = apply_disclosure_to_svs([_sv("s", ["e0", "e1"])], analysis)
    assert len(out) == 1  # ships, no raise


def test_real_integrity_holes_still_fail_loud():
    # B12 keeps fail-loud for the UNRECOVERABLE integrity holes (real provenance / data holes), e.g. a
    # missing evidence_id (cannot disclose a claim whose source can't be identified). NOTE (I-arch-005
    # B12-P1): judge=None is NO LONGER such a hole — it is an INFRA condition that LABELS, not HOLDS;
    # see test_judge_absent_labels_credibility_unscored_never_aborts below.
    with pytest.raises(CredibilityPassError):
        run_credibility_analysis(
            "q", [_row("", "https://www.nature.com/a")], gov_suffixes=GOV, judge=_good_judge,
        )


def test_judge_absent_labels_credibility_unscored_never_aborts():
    # I-arch-005 B12-P1 (#1257, operator-locked 2026-06-14 "nothing shall hold the report"): a MISSING
    # production credibility judge is an INFRA/config condition (the pass is ADVISORY), NOT a faithfulness
    # finding. It must NOT abort the whole report. The chain runs priors-only and LABELS EVERY source
    # credibility_unscored (a disclosed gap) — never a hold, never a silent priors-only false-green.
    rows = [
        _row("e1", "https://www.nature.com/a", auth=0.7),
        _row("e2", "https://www.who.int/b", auth=0.9),
    ]
    a = run_credibility_analysis("q", rows, gov_suffixes=GOV, judge=None)  # must NOT raise
    assert set(a.credibility_by_evidence) == {"e1", "e2"}                  # all sources present, none dropped
    # EVERY source is labeled credibility_unscored — the explicit `or judge_missing` (not errored_ids,
    # which is EMPTY when judge=None because priors-only judgments carry judge_error=False).
    assert a.credibility_by_evidence["e1"].credibility_unscored is True
    assert a.credibility_by_evidence["e2"].credibility_unscored is True
    # each ships its real DETERMINISTIC priors-only weight (== clamp01(authority_score)), never fabricated.
    assert a.credibility_by_evidence["e1"].credibility_weight == pytest.approx(0.7)
    assert a.credibility_by_evidence["e2"].credibility_weight == pytest.approx(0.9)


def test_no_mutation_of_input_rows():
    rows = [_row("e1", "https://www.nature.com/a"), _row("e2", "https://www.who.int/b")]
    run_credibility_analysis("q", rows, gov_suffixes=GOV, judge=_good_judge)
    assert "origin_cluster_id" not in rows[0] and "is_canonical_origin" not in rows[0]


def test_budget_breach_escapes_as_budget_error_not_credibility_error():
    # Codex #012a iter-3 P1: a cap breach in the judge must propagate ALL THE WAY OUT as
    # BudgetExceededError (-> sweep abort_budget_exceeded), NOT be masked into judge_error/CredibilityPassError.
    from src.polaris_graph.llm.openrouter_client import BudgetExceededError

    def budget_judge(question, payload):
        raise BudgetExceededError("cap breached")

    rows = [_row("e1", "https://www.nature.com/a")]
    with pytest.raises(BudgetExceededError):
        run_credibility_analysis("q", rows, gov_suffixes=GOV, judge=budget_judge)
