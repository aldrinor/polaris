"""I-cred-012 (#1162) — credibility-pass ORCHESTRATOR. Offline, deterministic, no network.

Exercises the full P4→P3→P2→P5→P6 chain over the effective pool, plus the fail-loud posture
(missing evidence_id / judge_error → abort_credibility_pass_error, never a silent false-green)."""
from __future__ import annotations

import pytest

from src.polaris_graph.synthesis.credibility_pass import (
    CredibilityAnalysis,
    CredibilityPassError,
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
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
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


def test_fail_loud_judge_error():
    # a judge that returns a non-dict -> P2 marks judge_error -> the orchestrator ABORTS (no false-green)
    def bad_judge(question, payload):
        return "not-a-dict"

    with pytest.raises(CredibilityPassError) as exc:
        run_credibility_analysis("q", [_row("e1", "https://www.nature.com/a")], gov_suffixes=GOV, judge=bad_judge)
    assert "judge" in str(exc.value).lower()


def test_fail_loud_judge_absent():
    # Codex iter-5 P1: master-on activation with NO production judge must ABORT, not run priors-only
    # (which P2 reports as judge_error=False -> a false-green advisory).
    with pytest.raises(CredibilityPassError) as exc:
        run_credibility_analysis("q", [_row("e1", "https://www.nature.com/a")], gov_suffixes=GOV, judge=None)
    assert "judge" in str(exc.value).lower() and "abort_credibility_pass_error" in str(exc.value)


def test_no_mutation_of_input_rows():
    rows = [_row("e1", "https://www.nature.com/a"), _row("e2", "https://www.who.int/b")]
    run_credibility_analysis("q", rows, gov_suffixes=GOV, judge=_good_judge)
    assert "origin_cluster_id" not in rows[0] and "is_canonical_origin" not in rows[0]
