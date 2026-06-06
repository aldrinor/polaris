"""FX-12 (I-ready-017 #1130): eval_gate judge_skipped_d8_binding audit-trail reason.

When the legacy judge is intentionally SKIPPED because the 4-role seam (D8) is the binding gate, the
call site passes judge_result=None. Without FX-12 that emitted 'judge_parse_failed' + the #1055
fail-closed (implying the judge RAN and CRASHED). FX-12 adds judge_skipped: a skip emits the distinct
'judge_skipped_d8_binding' code, keeps judge_parse_ok True, and does NOT fail closed. The genuine
parse-failure path (judge_skipped=False) is unchanged. Offline, pure.
"""
from __future__ import annotations

from types import SimpleNamespace

from src.polaris_graph.evaluator.evaluator_gate import compute_evaluator_gate


def _ev_out(rule_checks=None, contradictions_missing=None):
    return SimpleNamespace(
        rule_checks=rule_checks or [],
        contradictions_missing=contradictions_missing or [],
    )


def test_judge_skipped_emits_distinct_reason_and_does_not_fail_closed():
    g = compute_evaluator_gate(_ev_out(), judge_result=None, judge_skipped=True)
    assert "judge_skipped_d8_binding" in g.reasons
    assert "judge_parse_failed" not in g.reasons
    assert g.judge_parse_ok is True
    # the #1055 fail-closed (advisory_unavailable + release withheld) must NOT fire on a skip
    assert g.gate_class != "advisory_unavailable"
    assert g.release_allowed is True


def test_genuine_parse_failure_unchanged_when_not_skipped():
    """judge_skipped defaults False → None still means judge_parse_failed + #1055 fail-closed."""
    g = compute_evaluator_gate(_ev_out(), judge_result=None)
    assert "judge_parse_failed" in g.reasons
    assert "judge_skipped_d8_binding" not in g.reasons
    assert g.judge_parse_ok is False
    assert g.gate_class == "advisory_unavailable"
    assert g.release_allowed is False


def test_judge_skipped_default_is_false_byte_identical():
    """Explicit judge_skipped=False == the default (the genuine-failure path) — byte-identical."""
    a = compute_evaluator_gate(_ev_out(), judge_result=None)
    b = compute_evaluator_gate(_ev_out(), judge_result=None, judge_skipped=False)
    assert a.reasons == b.reasons
    assert a.gate_class == b.gate_class
    assert a.judge_parse_ok == b.judge_parse_ok
    assert a.release_allowed == b.release_allowed


def test_real_judge_parse_failure_not_masked_by_skip_flag():
    """A judge that RAN but failed to parse (parse_ok=False) is still judge_parse_failed even if the
    skip flag is on — the skip branch only applies when judge_result is None."""
    bad = SimpleNamespace(parse_ok=False, verdicts={})
    g = compute_evaluator_gate(_ev_out(), judge_result=bad, judge_skipped=True)
    assert "judge_parse_failed" in g.reasons
    assert "judge_skipped_d8_binding" not in g.reasons
    assert g.judge_parse_ok is False
