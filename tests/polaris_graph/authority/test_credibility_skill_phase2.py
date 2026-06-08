"""I-cred-002 (Phase 2) — adaptive credibility skill. Offline, deterministic fake judges, no network,
no live data, no LLM client. Each test maps to a brief acceptance criterion (AC-1..AC-11)."""
from __future__ import annotations

import copy

import pytest

from src.polaris_graph.authority.credibility_skill import (
    CredibilityJudgment,
    _build_judge_payload,
    credibility_skill_enabled,
    score_source_credibility,
)


def _row(eid, **kw):
    row = {"evidence_id": eid}
    row.update(kw)
    return row


# ── AC-1: flag default-OFF ────────────────────────────────────────────────────
def test_flag_default_off(monkeypatch):
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_SKILL", raising=False)
    assert credibility_skill_enabled() is False


@pytest.mark.parametrize("off", ["", "0", "false", "off", "no", "  ", "FALSE", "Off"])
def test_flag_off_values(monkeypatch, off):
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_SKILL", off)
    assert credibility_skill_enabled() is False


@pytest.mark.parametrize("on", ["1", "true", "on", "yes", "TRUE"])
def test_flag_on_values(monkeypatch, on):
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_SKILL", on)
    assert credibility_skill_enabled() is True


# ── AC-2: judge=None => priors-only (total, offline) ──────────────────────────
def test_judge_none_priors_only():
    rows = [
        _row("e1", authority_score=0.7, signal_scores={"signal_a_scholarly": 0.8}),
        _row("e2"),  # no authority at all
    ]
    out = score_source_credibility("q", rows)
    assert len(out) == 2
    assert out[0].reliability_score == 0.7 and out[0].relevance_score == 1.0
    assert out[0].credibility_weight == 0.7 and out[0].judge_error is False
    assert out[1].reliability_score == 0.0  # no authority -> 0.0, never crashes


# ── AC-3: injected judge flows through; weight is the fixed product ───────────
def test_injected_judge_flows_through():
    def judge(q, payload):
        return {"reliability_score": 0.8, "relevance_score": 0.5, "rationale": "r", "query_need": "n"}

    rows = [_row("e1", authority_score=0.6, authority_confidence="HIGH", signal_scores={"x": 1})]
    j = score_source_credibility("q", rows, judge=judge)[0]
    assert j.reliability_score == 0.8 and j.relevance_score == 0.5
    assert abs(j.credibility_weight - 0.4) < 1e-9
    assert j.rationale == "r" and j.query_need == "n" and j.judge_error is False


# ── AC-4: anti-fabrication cap (exact) + judge may down-rate ──────────────────
def test_anti_fabrication_cap_low_thin():
    def overclaim(q, p):
        return {"reliability_score": 0.99, "relevance_score": 1.0}

    rows = [_row("low", authority_score=0.30, authority_confidence="LOW", signal_scores={"x": 1})]
    out = score_source_credibility("q", rows, judge=overclaim)
    assert abs(out[0].reliability_score - 0.45) < 1e-9  # 0.30 + 0.15 default uplift


def test_judge_may_downrate_high_authority():
    def downrate(q, p):
        return {"reliability_score": 0.10, "relevance_score": 1.0}

    rows = [_row("hi", authority_score=0.95, authority_confidence="HIGH", signal_scores={"x": 1})]
    out = score_source_credibility("q", rows, judge=downrate)
    assert out[0].reliability_score == 0.10  # the prior is NOT a lower bound


# ── AC-5: signals_cited subset of present ────────────────────────────────────
def test_signals_cited_subset_of_present():
    def judge(q, p):
        return {"reliability_score": 0.5, "relevance_score": 1.0,
                "signals_cited": ["authority_score", "junk_class", "not_a_signal", "predatory_oa"]}

    rows = [_row("e1", authority_score=0.5, authority_confidence="HIGH", signal_scores={"x": 1})]
    out = score_source_credibility("q", rows, judge=judge)
    assert out[0].signals_cited == ["authority_score"]  # only the present, valid one survives


# ── AC-6: malformed judge output ─────────────────────────────────────────────
def test_out_of_range_clamped():
    def judge(q, p):
        return {"reliability_score": 1.7, "relevance_score": -0.2}

    rows = [_row("e1", authority_score=0.5, authority_confidence="HIGH", signal_scores={"x": 1})]
    out = score_source_credibility("q", rows, judge=judge)
    assert out[0].reliability_score == 1.0 and out[0].relevance_score == 0.0


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_nan_inf_reliability_is_judge_error(bad):
    def judge(q, p):
        return {"reliability_score": bad, "relevance_score": 1.0}

    rows = [_row("e1", authority_score=0.4, authority_confidence="HIGH", signal_scores={"x": 1})]
    out = score_source_credibility("q", rows, judge=judge)
    assert out[0].judge_error is True and out[0].reliability_score == 0.4  # priors fallback


def test_malformed_non_dict_is_judge_error():
    def judge(q, p):
        return "not a dict"

    rows = [_row("e1", authority_score=0.4, authority_confidence="HIGH", signal_scores={"x": 1})]
    out = score_source_credibility("q", rows, judge=judge)
    assert out[0].judge_error is True and out[0].reliability_score == 0.4


# ── AC-7: judge error isolated per row ───────────────────────────────────────
def test_judge_error_isolated_per_row():
    def judge(q, p):
        if p["evidence_id"] == "boom":
            raise RuntimeError("nope")
        return {"reliability_score": 0.6, "relevance_score": 1.0}

    rows = [
        _row("ok", authority_score=0.5, authority_confidence="HIGH", signal_scores={"x": 1}),
        _row("boom", authority_score=0.2),
    ]
    out = score_source_credibility("q", rows, judge=judge)
    assert out[0].judge_error is False and out[0].reliability_score == 0.6
    assert out[1].judge_error is True and out[1].reliability_score == 0.2


# ── AC-8: domain is a HINT, not a branch ─────────────────────────────────────
def test_domain_is_hint_not_branch():
    captured = []

    def judge(q, p):
        captured.append(p["domain_hint"])
        return {"reliability_score": 0.5, "relevance_score": 0.5}

    rows = [_row("e1", authority_score=0.6, authority_confidence="HIGH", signal_scores={"x": 1})]
    a = score_source_credibility("q", rows, domain="clinical", judge=judge)
    b = score_source_credibility("q", rows, domain="policy", judge=judge)
    assert a[0].credibility_weight == b[0].credibility_weight  # identical control flow + result
    assert a[0].reliability_score == b[0].reliability_score
    assert captured == ["clinical", "policy"]  # only the hint string differs


# ── AC-9: env knob scoped to the cap, product fixed ──────────────────────────
def test_max_uplift_env_knob(monkeypatch):
    def overclaim(q, p):
        return {"reliability_score": 0.99, "relevance_score": 1.0}

    monkeypatch.setenv("PG_CREDIBILITY_MAX_UPLIFT", "0.05")
    low = [_row("low", authority_score=0.30, authority_confidence="LOW", signal_scores={"x": 1})]
    assert abs(score_source_credibility("q", low, judge=overclaim)[0].reliability_score - 0.35) < 1e-9
    hi = [_row("hi", authority_score=0.60, authority_confidence="HIGH", signal_scores={"x": 1})]
    assert score_source_credibility("q", hi, judge=overclaim)[0].reliability_score == 0.99  # unaffected


# ── AC-10: purity — no row mutation ──────────────────────────────────────────
def test_no_row_mutation():
    def judge(q, p):
        p["mutated"] = True  # mutate the PAYLOAD, not the row
        return {"reliability_score": 0.5, "relevance_score": 1.0}

    row = _row("e1", authority_score=0.5, authority_confidence="HIGH", signal_scores={"x": 1},
               direct_quote="hello")
    before = copy.deepcopy(row)
    score_source_credibility("q", [row], judge=judge)
    assert row == before


# ── AC-11: judge payload shape ───────────────────────────────────────────────
def test_judge_payload_shape(monkeypatch):
    monkeypatch.setenv("PG_CREDIBILITY_SNIPPET_CHARS", "10")
    row = _row("e1", authority_score=0.5, source_class="PRIMARY_SCHOLARLY", corroboration_count=3,
               authority_confidence="HIGH", signal_scores={"signal_a_scholarly": 0.9}, junk_class="",
               predatory_oa=False, title="T", source_url="https://x", direct_quote="0123456789ABCDEF")
    payload = _build_judge_payload("the question", row, "clinical")
    for key in ("research_question", "evidence_id", "title", "url", "snippet", "authority_score",
                "source_class", "corroboration_count", "authority_confidence", "signal_scores",
                "junk_class", "predatory_oa", "origin_cluster_id", "domain_hint"):
        assert key in payload
    assert len(payload["snippet"]) == 10 and payload["domain_hint"] == "clinical"
    assert "mutated" not in row
    assert _build_judge_payload("q", row, None)["domain_hint"] == ""
