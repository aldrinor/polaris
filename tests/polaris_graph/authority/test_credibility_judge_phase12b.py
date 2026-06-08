"""I-cred-012b — production credibility judge factory. Offline, deterministic, no network."""
from __future__ import annotations

import pytest

from src.polaris_graph.authority.credibility_judge import (
    build_credibility_prompt,
    make_credibility_judge,
    parse_credibility_response,
)
from src.polaris_graph.authority.credibility_skill import score_source_credibility


def test_requires_call_llm():
    with pytest.raises(ValueError):
        make_credibility_judge(None)


def test_happy_path_parses_json():
    judge = make_credibility_judge(
        lambda p: '{"reliability_score": 0.8, "relevance_score": 0.9, "rationale": "ok"}'
    )
    out = judge("q", {"title": "t", "url": "u"})
    assert out["reliability_score"] == 0.8 and out["relevance_score"] == 0.9


def test_code_fence_and_prose_tolerated():
    judge = make_credibility_judge(lambda p: 'Sure:\n```json\n{"reliability_score": 0.5}\n```')
    assert judge("q", {})["reliability_score"] == 0.5


def test_malformed_returns_empty_dict():
    assert make_credibility_judge(lambda p: "no json here")("q", {}) == {}
    assert make_credibility_judge(lambda p: "[1,2,3]")("q", {}) == {}  # non-dict JSON


def test_transport_failure_returns_empty():
    def boom(prompt):
        raise RuntimeError("503 upstream")

    assert make_credibility_judge(boom)("q", {}) == {}


def test_prompt_surfaces_ALL_required_deterministic_signals():
    # Codex #012b P1: the judge must reason from the full P2 signal set, not just title/url/authority.
    from src.polaris_graph.authority.credibility_judge import REQUIRED_SIGNAL_FIELDS
    payload = {
        "title": "Study A", "url": "http://a", "snippet": "snip", "authority_score": 0.8,
        "authority_confidence": "HIGH", "source_class": "journal", "corroboration_count": 4,
        "signal_scores": {"scholarly": 0.9}, "junk_class": "none", "predatory_oa": False,
        "origin_cluster_id": "oc1", "domain_hint": "clinical",
    }
    p = build_credibility_prompt("does X work?", payload)
    assert "does X work?" in p and "Study A" in p and "http://a" in p
    for field in REQUIRED_SIGNAL_FIELDS:
        assert field in p, f"prompt must surface the deterministic signal {field!r} (plan §9.1)"
    assert "corroboration_count" in p and "4" in p and "journal" in p


def test_parse_helper_direct_and_trailing_prose():
    assert parse_credibility_response('{"a": 1}') == {"a": 1}
    assert parse_credibility_response("") == {}
    assert parse_credibility_response("nope") == {}
    # FIRST object only — trailing prose / a second object must not break the valid first one (P2-1)
    assert parse_credibility_response('{"reliability_score": 0.6} then some chatter {"x": 9}') == {"reliability_score": 0.6}
    # a brace inside a string value must not prematurely close the object
    assert parse_credibility_response('{"rationale": "uses a { brace", "reliability_score": 0.5}') == {
        "rationale": "uses a { brace", "reliability_score": 0.5}


def test_flows_through_p2_as_non_error_judgment():
    judge = make_credibility_judge(lambda p: '{"reliability_score": 0.7, "relevance_score": 1.0}')
    rows = [{"evidence_id": "e1", "authority_score": 0.6, "authority_confidence": "HIGH", "signal_scores": {"x": 1}}]
    out = score_source_credibility("q", rows, judge=judge)[0]
    assert out.judge_error is False and out.reliability_score == 0.7


def test_malformed_judge_marks_p2_judge_error():
    judge = make_credibility_judge(lambda p: "garbage, no json")
    rows = [{"evidence_id": "e1", "authority_score": 0.6, "authority_confidence": "HIGH", "signal_scores": {"x": 1}}]
    out = score_source_credibility("q", rows, judge=judge)[0]
    assert out.judge_error is True
