"""Unit + eval tests for the opaque-clause eligibility judge (Kimi §2/§5).

Covers: the deterministic named-host leg, the schema-constrained LLM leg parsing,
fail-open vs fail-closed on UNKNOWN, malformed/raising LLM robustness, the
aggregation into a citable-eligibility plan, the no-op (byte-identical) contract,
and the end-to-end precision/recall eval over the labeled fixture corpus.
"""

from __future__ import annotations

import json
from pathlib import Path

from src.polaris_graph.planning.eligibility_judge import (
    STAGE_OPAQUE,
    build_opaque_eligibility,
    judge_source,
)
from src.polaris_graph.retrieval.quality_eligibility import FAIL, PASS, UNKNOWN


class _Policy:
    def __init__(self, opaque, force=None, chash="h"):
        self.opaque_eligibility = opaque
        self.predicate_force = force or {"opaque_eligibility": "hard"}
        self.contract_hash = chash


# --- deterministic named-host leg (no LLM) ---------------------------------


def test_named_host_pass_without_llm():
    recs = judge_source({"source_url": "https://www.reuters.com/x"}, ["use reuters.com only"], llm=None)
    assert [r.verdict for r in recs] == [PASS]
    assert recs[0].stage == STAGE_OPAQUE


def test_named_host_fail_without_llm():
    recs = judge_source({"source_url": "https://blog.foo.org/x"}, ["use reuters.com only"], llm=None)
    assert [r.verdict for r in recs] == [FAIL]


# --- LLM leg + no-silent-fallback ------------------------------------------


def test_opaque_kind_without_llm_is_unknown_not_fabricated():
    recs = judge_source({"source_url": "https://x.com/a"}, ["company press releases only"], llm=None)
    assert [r.verdict for r in recs] == [UNKNOWN]
    assert "no LLM judge" in recs[0].basis


def test_llm_leg_parses_schema_json():
    def _llm(meta, clauses):
        return json.dumps({"verdicts": [{"clause_index": 0, "verdict": "pass", "basis": "is a press release"}]})

    recs = judge_source({"source_url": "https://x.com/a"}, ["company press releases only"], llm=_llm)
    assert recs[0].verdict == PASS


def test_malformed_llm_output_is_unknown_never_crashes():
    recs = judge_source({"source_url": "https://x.com/a"}, ["c"], llm=lambda m, c: "not json at all")
    assert recs[0].verdict == UNKNOWN


def test_raising_llm_is_unknown_fail_open():
    def _boom(meta, clauses):
        raise RuntimeError("boom")

    recs = judge_source({"source_url": "https://x.com/a"}, ["c"], llm=_boom)
    assert recs[0].verdict == UNKNOWN


# --- aggregation: fail-open vs fail-closed on UNKNOWN under HARD ------------


def test_unknown_fail_open_does_not_exclude():
    plan = build_opaque_eligibility(
        _Policy(["company press releases only"]),
        [{"source_url": "https://x.com/a"}],
        llm=None, fail_open_on_unknown=True,
    )
    assert plan.eligibility_excluded_ids == set()


def test_unknown_fail_closed_excludes():
    plan = build_opaque_eligibility(
        _Policy(["company press releases only"]),
        [{"source_url": "https://x.com/a"}],
        llm=None, fail_open_on_unknown=False,
    )
    assert plan.eligibility_excluded_ids == {"https://x.com/a"}


def test_hard_fail_excludes_soft_fail_only_demotes():
    def _llm(meta, clauses):
        return json.dumps({"verdicts": [{"clause_index": 0, "verdict": "fail", "basis": "blog"}]})

    hard = build_opaque_eligibility(_Policy(["no blogs"], {"opaque_eligibility": "hard"}),
                                    [{"source_url": "https://b.com/x"}], llm=_llm)
    soft = build_opaque_eligibility(_Policy(["no blogs"], {"opaque_eligibility": "soft"}),
                                    [{"source_url": "https://b.com/x"}], llm=_llm)
    assert hard.eligibility_excluded_ids == {"https://b.com/x"}
    assert soft.eligibility_excluded_ids == set()
    assert "https://b.com/x" in soft.url_to_weight


# --- no-op / byte-identical contract ---------------------------------------


def test_empty_opaque_is_noop():
    plan = build_opaque_eligibility(_Policy([]), [{"source_url": "https://x.com/a"}], llm=lambda m, c: "{}")
    assert plan.is_empty()
    assert plan.receipts == []


# --- end-to-end precision/recall eval over the labeled corpus --------------


def test_eval_harness_all_contracts_perfect():
    import sys
    repo = Path(__file__).resolve().parents[2]
    if str(repo) not in sys.path:
        sys.path.insert(0, str(repo))
    from scripts.eval_eligibility_judge import evaluate_contract

    corpus = json.loads(
        (repo / "tests" / "planning" / "fixtures" / "eligibility_corpus.json").read_text(encoding="utf-8")
    )
    for name, spec in corpus["contracts"].items():
        r = evaluate_contract(corpus, name, spec)
        assert r["admit"]["f1"] >= 0.90, f"{name}: admit F1 {r['admit']['f1']}"
        assert not r["misadmitted_ids"], f"{name}: leaked into citable menu: {r['misadmitted_ids']}"
