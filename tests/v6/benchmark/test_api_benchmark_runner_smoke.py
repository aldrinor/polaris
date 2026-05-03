"""Smoke tests for scripts/v6/benchmark/api_benchmark_runner.py (Phase 0 substrate, Phase 3 invocation).

Tests the dry-run path and the deterministic scorers — no live API calls.
Per docs/benchmark/scoring_rubric.md §3, scorers must be deterministic
and signal-anchored (NOT LLM-as-judge), so they're directly unit-testable.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
from pathlib import Path

import pytest

POLARIS_ROOT = Path(__file__).resolve().parents[3]
RUNNER_PATH = POLARIS_ROOT / "scripts" / "v6" / "benchmark" / "api_benchmark_runner.py"


def _load_runner_module():
    """Load the runner via importlib + register in sys.modules.

    The runner uses `from __future__ import annotations` + dataclass fields
    typed as `str | None`. dataclass field-resolution looks up the module's
    namespace via sys.modules[cls.__module__] — so the module MUST be
    registered there before exec_module fires.
    """
    spec = importlib.util.spec_from_file_location("api_benchmark_runner", RUNNER_PATH)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["api_benchmark_runner"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def runner():
    return _load_runner_module()


# ---- BenchmarkQuestion schema ----------------------------------------------

def test_question_schema_accepts_all_rubric_fields(runner):
    """Per rubric §5, BenchmarkQuestion must accept expected_anchors,
    expected_refusal_patterns, expected_frames, has_known_contradictions,
    paired_prompt_id."""
    q = runner.BenchmarkQuestion(
        question_id="t-001", template="clinical",
        text="What is X?", difficulty="routine",
        expected_anchors=["foo"],
        expected_refusal_patterns=["I cannot"],
        expected_frames=["mechanism", "outcome"],
        has_known_contradictions=True,
        paired_prompt_id="t-001-paired",
    )
    assert q.expected_anchors == ["foo"]
    assert q.expected_refusal_patterns == ["I cannot"]
    assert q.expected_frames == ["mechanism", "outcome"]
    assert q.has_known_contradictions is True
    assert q.paired_prompt_id == "t-001-paired"


# ---- D1 factual_accuracy ---------------------------------------------------

def test_factual_accuracy_full_match(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="routine", expected_anchors=["alpha", "beta"])
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="discussion of alpha and beta dynamics",
        citation_count=0, timestamp="t", cost_usd=0.0)
    s = runner.score_factual_accuracy(q, resp)
    assert s.score == 1.0
    assert s.dimension == "factual_accuracy"


def test_factual_accuracy_partial_match(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="routine", expected_anchors=["alpha", "beta", "gamma"])
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="alpha appears here but no others", citation_count=0,
        timestamp="t", cost_usd=0.0)
    s = runner.score_factual_accuracy(q, resp)
    assert abs(s.score - 1/3) < 0.001


def test_factual_accuracy_error_returns_zero(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="routine", expected_anchors=["alpha"])
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="", citation_count=0, timestamp="t", cost_usd=0.0,
        error="api_timeout")
    s = runner.score_factual_accuracy(q, resp)
    assert s.score == 0.0
    assert "api_timeout" in s.rationale


# ---- D2 citation_health ----------------------------------------------------

def test_citation_health_at_threshold(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="trade",
        text="?", difficulty="routine")
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="ok", citation_count=5, timestamp="t", cost_usd=0.0)
    s = runner.score_citation_health(q, resp)
    assert s.score == 1.0


def test_citation_health_below_threshold(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="defense",
        text="?", difficulty="adversarial")
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="ok", citation_count=9, timestamp="t", cost_usd=0.0)
    s = runner.score_citation_health(q, resp)
    assert abs(s.score - 9/18) < 0.001


# ---- D3 frame_coverage -----------------------------------------------------

def test_frame_coverage_underscore_normalized(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="routine",
        expected_frames=["mechanism_of_action", "indication"])
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="The mechanism of action is X. The indication is Y.",
        citation_count=0, timestamp="t", cost_usd=0.0)
    s = runner.score_frame_coverage(q, resp)
    assert s.score == 1.0


# ---- D4 contradiction_handling --------------------------------------------

def test_contradiction_handling_correct_surface(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="climate",
        text="?", difficulty="novel_synthesis", has_known_contradictions=True)
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="Sources disagree on this point.",
        citation_count=0, timestamp="t", cost_usd=0.0)
    s = runner.score_contradiction_handling(q, resp)
    assert s.score == 1.0


def test_contradiction_handling_silent_suppression(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="climate",
        text="?", difficulty="novel_synthesis", has_known_contradictions=True)
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="The clear answer is X.",
        citation_count=0, timestamp="t", cost_usd=0.0)
    s = runner.score_contradiction_handling(q, resp)
    assert s.score == 0.0


# ---- D5 refusal_calibration ------------------------------------------------

def test_refusal_calibration_correct_refusal(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="defense",
        text="?", difficulty="adversarial",
        expected_refusal_patterns=["cannot provide", "out of scope"])
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="I cannot provide that information.",
        citation_count=0, timestamp="t", cost_usd=0.0)
    s = runner.score_refusal_calibration(q, resp)
    assert s.score == 1.0


def test_refusal_calibration_under_refusal(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="defense",
        text="?", difficulty="adversarial",
        expected_refusal_patterns=["cannot provide"])
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="Here is the information.",
        citation_count=0, timestamp="t", cost_usd=0.0)
    s = runner.score_refusal_calibration(q, resp)
    assert s.score == 0.0


# ---- D6 user_traceability --------------------------------------------------

def test_user_traceability_polaris_provenance_tokens(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="routine")
    text = "Claim one [#ev:abc123:0-50]. Claim two [#ev:def456:10-60]. Claim three [#ev:ghi789]."
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text=text, citation_count=3, timestamp="t", cost_usd=0.0)
    s = runner.score_user_traceability(q, resp)
    assert s.score == 1.0


def test_user_traceability_chatgpt_footnotes(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="routine")
    text = "Claim one [1]. Claim two [2]. Claim three [Source 3]."
    resp = runner.SystemResponse(system="chatgpt_5_5_pro_dr", question_id="t",
        response_text=text, citation_count=3, timestamp="t", cost_usd=0.0)
    s = runner.score_user_traceability(q, resp)
    # Should still detect footnotes ≈ density ≈ 1.0
    assert s.score >= 0.5


# ---- D7 two_family_agreement (POLARIS-unique) ------------------------------

def test_two_family_na_for_chatgpt(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="routine", has_known_contradictions=True)
    resp = runner.SystemResponse(system="chatgpt_5_5_pro_dr", question_id="t",
        response_text="answer", citation_count=0, timestamp="t", cost_usd=0.0)
    s = runner.score_two_family_agreement(q, resp)
    # NaN score indicates N/A
    assert s.score != s.score   # NaN check


def test_two_family_polaris_surfaces_signal_when_expected(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="novel_synthesis", has_known_contradictions=True)
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="The internal evaluator flagged a disagreement on this claim.",
        citation_count=0, timestamp="t", cost_usd=0.0)
    s = runner.score_two_family_agreement(q, resp)
    assert s.score == 1.0


# ---- D8 sycophancy_resistance ----------------------------------------------

def test_sycophancy_resistance_resists_leading(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="climate",
        text="?", difficulty="adversarial", paired_prompt_id="t-paired")
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="The evidence is mixed and I disagree with the framing.",
        citation_count=0, timestamp="t", cost_usd=0.0)
    s = runner.score_sycophancy_resistance(q, resp)
    assert s.score == 1.0


def test_sycophancy_resistance_caves_to_leading(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="climate",
        text="?", difficulty="adversarial", paired_prompt_id="t-paired")
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="You're absolutely right that X is true.",
        citation_count=0, timestamp="t", cost_usd=0.0)
    s = runner.score_sycophancy_resistance(q, resp)
    assert s.score == 0.0


def test_sycophancy_na_when_not_paired(runner):
    """No paired_prompt_id → not a sycophancy fixture → N/A."""
    q = runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="routine")  # no paired_prompt_id
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="answer", citation_count=0, timestamp="t", cost_usd=0.0)
    s = runner.score_sycophancy_resistance(q, resp)
    assert s.score != s.score   # NaN check


# ---- score_question covers all 8 ------------------------------------------

def test_score_question_returns_eight_dimensions(runner):
    q = runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="routine", expected_anchors=["x"])
    resp = runner.SystemResponse(system="polaris_v6", question_id="t",
        response_text="x", citation_count=0, timestamp="t", cost_usd=0.0)
    scores = runner.score_question(q, resp)
    dims = {s.dimension for s in scores}
    assert dims == {
        "factual_accuracy", "citation_health", "frame_coverage",
        "contradiction_handling", "refusal_calibration", "user_traceability",
        "two_family_agreement", "sycophancy_resistance",
    }


# ---- Cost cap behavior: continue, don't break loop -------------------------

def test_cost_cap_records_error_continues_other_systems(runner, monkeypatch):
    """Per Plan v13 §F: when a system hits cost cap, record cost_cap_reached
    error and continue evaluating other systems. NOT silent skip, NOT break."""
    # Force runner to think POLARIS already exceeded cap on first question
    monkeypatch.setattr(runner, "PER_SYSTEM_USD_CAP", 0.001)

    # Patch system adapters to return non-zero cost so cap fires
    def stub_polaris(q):
        return runner.SystemResponse(system="polaris_v6", question_id=q.question_id,
            response_text="ok", citation_count=1, timestamp="t", cost_usd=0.10)
    def stub_chatgpt(q):
        return runner.SystemResponse(system="chatgpt_5_5_pro_dr", question_id=q.question_id,
            response_text="ok", citation_count=1, timestamp="t", cost_usd=0.0)
    def stub_gemini(q):
        return runner.SystemResponse(system="gemini_3_1_pro_dr", question_id=q.question_id,
            response_text="ok", citation_count=1, timestamp="t", cost_usd=0.0)

    monkeypatch.setitem(runner.SYSTEMS, "polaris_v6", stub_polaris)
    monkeypatch.setitem(runner.SYSTEMS, "chatgpt_5_5_pro_dr", stub_chatgpt)
    monkeypatch.setitem(runner.SYSTEMS, "gemini_3_1_pro_dr", stub_gemini)

    qs = [
        runner.BenchmarkQuestion(question_id=f"q-{i}", template="clinical",
            text="?", difficulty="routine") for i in range(3)
    ]
    results = runner.run_benchmark(qs, ["polaris_v6", "chatgpt_5_5_pro_dr", "gemini_3_1_pro_dr"])

    # 3 questions × 3 systems = 9 responses, all present (no break)
    total_responses = sum(len(r.responses) for r in results.values())
    assert total_responses == 9

    # POLARIS cost-cap'd after q-0 (cost=0.10 > cap 0.001)
    polaris_responses = [r.responses["polaris_v6"] for r in results.values()]
    capped = [r for r in polaris_responses if r.error and "cost_cap_reached" in r.error]
    assert len(capped) >= 2, f"expected ≥2 cost_cap_reached responses, got {len(capped)}"

    # Other systems still fully evaluated
    chatgpt_errors = [r.responses["chatgpt_5_5_pro_dr"].error for r in results.values()]
    assert all(e is None for e in chatgpt_errors), "chatgpt should not be cost-capped"


# ---- Match-or-beat verdict --------------------------------------------------

def test_match_or_beat_polaris_wins(runner):
    """3-way completeness required: include both ChatGPT and Gemini."""
    per_template = {
        "clinical": {
            "polaris_v6": {"factual_accuracy": 0.9, "citation_health": 0.9,
                           "refusal_calibration": 0.9, "sycophancy_resistance": 0.9},
            "chatgpt_5_5_pro_dr": {"factual_accuracy": 0.7, "citation_health": 0.7,
                                   "refusal_calibration": 0.7, "sycophancy_resistance": 0.7},
            "gemini_3_1_pro_dr": {"factual_accuracy": 0.6, "citation_health": 0.6,
                                  "refusal_calibration": 0.6, "sycophancy_resistance": 0.6},
        }
    }
    out = runner.compute_match_or_beat(per_template)
    assert out["per_template"]["clinical"]["polaris_wins"] is True
    assert out["per_template"]["clinical"]["state"] == "polaris_win"
    assert out["per_template"]["clinical"]["delta"] > 0
    assert out["win_count"] == 1


def test_match_or_beat_polaris_loses(runner):
    """3-way completeness required."""
    per_template = {
        "clinical": {
            "polaris_v6": {"factual_accuracy": 0.5, "citation_health": 0.5,
                           "refusal_calibration": 0.5, "sycophancy_resistance": 0.5},
            "chatgpt_5_5_pro_dr": {"factual_accuracy": 0.9, "citation_health": 0.9,
                                   "refusal_calibration": 0.9, "sycophancy_resistance": 0.9},
            "gemini_3_1_pro_dr": {"factual_accuracy": 0.9, "citation_health": 0.9,
                                  "refusal_calibration": 0.9, "sycophancy_resistance": 0.9},
        }
    }
    out = runner.compute_match_or_beat(per_template)
    assert out["per_template"]["clinical"]["polaris_wins"] is False
    assert out["per_template"]["clinical"]["state"] == "polaris_loss"


def test_match_or_beat_insufficient_data_dry_run_zeros(runner):
    """Both POLARIS and competitors at zero (dry-run) → DRY_RUN_NO_VERDICT (more specific)."""
    per_template = {
        "clinical": {
            "polaris_v6": {"factual_accuracy": 0.0, "citation_health": 0.0,
                           "refusal_calibration": 0.0, "sycophancy_resistance": 0.0},
            "chatgpt_5_5_pro_dr": {"factual_accuracy": 0.0, "citation_health": 0.0,
                                   "refusal_calibration": 0.0, "sycophancy_resistance": 0.0},
        }
    }
    out = runner.compute_match_or_beat(per_template)
    assert out["per_template"]["clinical"]["state"] == "insufficient_data"
    assert out["per_template"]["clinical"]["polaris_wins"] is False
    # In dry-run (LIVE_MODE=False default), verdict is DRY_RUN_NO_VERDICT
    assert out["verdict"] in ("DRY_RUN_NO_VERDICT", "INSUFFICIENT_DATA")


def test_match_or_beat_dry_run_blocks_approve(runner):
    """Even with apparent winning numbers in dry-run, verdict must NOT APPROVE without LIVE_MODE."""
    per_template = {tmpl: {
        "polaris_v6": {"factual_accuracy": 0.95, "citation_health": 0.95,
                       "refusal_calibration": 0.95, "sycophancy_resistance": 0.95},
        "chatgpt_5_5_pro_dr": {"factual_accuracy": 0.7, "citation_health": 0.7,
                               "refusal_calibration": 0.7, "sycophancy_resistance": 0.7},
        "gemini_3_1_pro_dr": {"factual_accuracy": 0.7, "citation_health": 0.7,
                              "refusal_calibration": 0.7, "sycophancy_resistance": 0.7},
    } for tmpl in ["clinical", "trade", "housing", "defense", "climate", "ai_sovereignty", "canada_us", "workforce"]}
    out = runner.compute_match_or_beat(per_template)
    # All 8 Carney templates, POLARIS wins big, but LIVE_MODE=False default
    assert out["verdict"] == "DRY_RUN_NO_VERDICT", f"got {out['verdict']}"


def test_match_or_beat_incomplete_carney_templates(runner, monkeypatch):
    """8 buckets that aren't the Carney 8 → INCOMPLETE_TEMPLATES."""
    monkeypatch.setattr(runner, "LIVE_MODE", True)
    per_template = {f"random_template_{i}": {
        "polaris_v6": {"factual_accuracy": 0.9, "citation_health": 0.9,
                       "refusal_calibration": 0.9, "sycophancy_resistance": 0.9},
        "chatgpt_5_5_pro_dr": {"factual_accuracy": 0.7, "citation_health": 0.7,
                               "refusal_calibration": 0.7, "sycophancy_resistance": 0.7},
        "gemini_3_1_pro_dr": {"factual_accuracy": 0.7, "citation_health": 0.7,
                              "refusal_calibration": 0.7, "sycophancy_resistance": 0.7},
    } for i in range(8)}
    out = runner.compute_match_or_beat(per_template)
    assert out["verdict"] == "INCOMPLETE_TEMPLATES"
    assert "missing_carney_templates" in out
    assert len(out["missing_carney_templates"]) == 8


def test_match_or_beat_approve_with_full_carney_set_and_live(runner, monkeypatch):
    """8 Carney templates, all comparable dims present, LIVE_MODE=True, ≥6 wins → APPROVE."""
    monkeypatch.setattr(runner, "LIVE_MODE", True)
    per_template = {tmpl: {
        "polaris_v6": {"factual_accuracy": 0.9, "citation_health": 0.9,
                       "refusal_calibration": 0.9, "sycophancy_resistance": 0.9},
        "chatgpt_5_5_pro_dr": {"factual_accuracy": 0.7, "citation_health": 0.7,
                               "refusal_calibration": 0.7, "sycophancy_resistance": 0.7},
        "gemini_3_1_pro_dr": {"factual_accuracy": 0.7, "citation_health": 0.7,
                              "refusal_calibration": 0.7, "sycophancy_resistance": 0.7},
    } for tmpl in ["clinical", "trade", "housing", "defense", "climate", "ai_sovereignty", "canada_us", "workforce"]}
    out = runner.compute_match_or_beat(per_template)
    assert out["verdict"] == "APPROVE", f"got {out['verdict']}: {out}"
    assert out["win_count"] == 8


def test_match_or_beat_competitor_must_have_all_dims(runner, monkeypatch):
    """Competitor missing some comparable dimensions → that competitor not eligible for comparison."""
    monkeypatch.setattr(runner, "LIVE_MODE", True)
    per_template = {tmpl: {
        "polaris_v6": {"factual_accuracy": 0.9, "citation_health": 0.9,
                       "refusal_calibration": 0.9, "sycophancy_resistance": 0.9},
        # ChatGPT missing sycophancy_resistance — should not count as comparable
        "chatgpt_5_5_pro_dr": {"factual_accuracy": 0.95, "citation_health": 0.95,
                               "refusal_calibration": 0.95},
        "gemini_3_1_pro_dr": {"factual_accuracy": 0.7, "citation_health": 0.7,
                              "refusal_calibration": 0.7, "sycophancy_resistance": 0.7},
    } for tmpl in ["clinical", "trade", "housing", "defense", "climate", "ai_sovereignty", "canada_us", "workforce"]}
    out = runner.compute_match_or_beat(per_template)
    # ChatGPT excluded; Gemini is the only competitor with full dims
    for tmpl_data in out["per_template"].values():
        assert "chatgpt_5_5_pro_dr" not in tmpl_data["competitors_with_data"]
        assert "gemini_3_1_pro_dr" in tmpl_data["competitors_with_data"]


# ---- NaN serialization -----------------------------------------------------

def test_nan_to_null_replaces_floats(runner):
    obj = {"a": float("nan"), "b": 1.5, "c": [float("nan"), 2.0], "d": {"e": float("nan")}}
    cleaned = runner._nan_to_null(obj)
    assert cleaned["a"] is None
    assert cleaned["b"] == 1.5
    assert cleaned["c"][0] is None
    assert cleaned["c"][1] == 2.0
    assert cleaned["d"]["e"] is None


def test_runner_output_has_no_bare_nan(runner, tmp_path, monkeypatch):
    """End-to-end runner output must not contain bare NaN tokens (non-standard JSON)."""
    bank = tmp_path / "qbank.json"
    bank.write_text(json.dumps([
        {"question_id": "q1", "template": "clinical", "text": "?", "difficulty": "routine"},
    ]))
    out_path = tmp_path / "results.json"
    old_argv = sys.argv
    sys.argv = ["api_benchmark_runner.py", "--questions", str(bank), "--results-out", str(out_path)]
    try:
        runner.main()
    finally:
        sys.argv = old_argv
    raw = out_path.read_text()
    # Strict-JSON consumers reject "NaN" / "Infinity" / "-Infinity" tokens
    assert "NaN" not in raw, "output contains non-standard NaN token"
    assert "Infinity" not in raw, "output contains non-standard Infinity token"
    # Parseable as strict JSON
    parsed = json.loads(raw)
    assert parsed["schema_version"] == "1.0.0"


def test_match_or_beat_insufficient_data_missing_polaris_dim(runner):
    """POLARIS missing one of the comparable dims → insufficient_data, not a win."""
    per_template = {
        "clinical": {
            # missing sycophancy_resistance
            "polaris_v6": {"factual_accuracy": 0.9, "citation_health": 0.9,
                           "refusal_calibration": 0.9},
            "chatgpt_5_5_pro_dr": {"factual_accuracy": 0.7, "citation_health": 0.7,
                                   "refusal_calibration": 0.7, "sycophancy_resistance": 0.7},
        }
    }
    out = runner.compute_match_or_beat(per_template)
    assert out["per_template"]["clinical"]["state"] == "insufficient_data"
    assert "sycophancy_resistance" in out["per_template"]["clinical"]["insufficient_data_reason"]


def test_match_or_beat_insufficient_data_no_competitor_data(runner):
    """No competitor has any comparable-dim data → insufficient."""
    per_template = {
        "clinical": {
            "polaris_v6": {"factual_accuracy": 0.9, "citation_health": 0.9,
                           "refusal_calibration": 0.9, "sycophancy_resistance": 0.9},
            # competitors entirely absent
        }
    }
    out = runner.compute_match_or_beat(per_template)
    assert out["per_template"]["clinical"]["state"] == "insufficient_data"
    # New 3-way completeness rule: missing competitors get reported by name
    reason = out["per_template"]["clinical"]["insufficient_data_reason"]
    assert "missing comparable data" in reason or "no competitor" in reason


# ---- Required-system enforcement -------------------------------------------

def test_run_benchmark_fails_loud_on_unknown_system(runner):
    qs = [runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="routine")]
    with pytest.raises(ValueError, match="unknown system"):
        runner.run_benchmark(qs, ["polaris_v6", "made_up_system"])


def test_run_benchmark_fails_loud_on_missing_required_system(runner):
    qs = [runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="routine")]
    with pytest.raises(ValueError, match="required system"):
        runner.run_benchmark(qs, ["polaris_v6"])  # missing chatgpt + gemini


def test_run_benchmark_subset_allowed_with_explicit_flag(runner, monkeypatch):
    monkeypatch.setenv("POLARIS_BENCHMARK_ALLOW_PARTIAL", "1")
    qs = [runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="?", difficulty="routine")]
    # Should not raise
    out = runner.run_benchmark(qs, ["polaris_v6"])
    assert "t" in out


# ---- Refusal calibration: over-refusal detection --------------------------

def test_refusal_calibration_detects_over_refusal_via_generic_marker(runner):
    """Question with NO expected_refusal_patterns + response that uses generic refusal language
    = over-refusal (incumbent failure mode); score 0."""
    q = runner.BenchmarkQuestion(question_id="t", template="clinical",
        text="What is the FDA-approved efficacy of tirzepatide?",
        difficulty="routine", expected_refusal_patterns=[])  # tractable Q, no refusal expected
    resp = runner.SystemResponse(system="chatgpt_5_5_pro_dr", question_id="t",
        response_text="I cannot provide medical advice.",
        citation_count=0, timestamp="t", cost_usd=0.0)
    s = runner.score_refusal_calibration(q, resp)
    assert s.score == 0.0
    assert "over_refusal" in s.rationale


# ---- End-to-end dry-run via CLI --------------------------------------------

def test_runner_dry_run_end_to_end(runner, tmp_path):
    """Execute the full main() flow (dry-run path) on a 2-question bank.

    Verifies: question loading, all 3 system adapters invoked, all 8
    dimensions scored, aggregate + per-template + match-or-beat emitted
    in output JSON.
    """
    bank = tmp_path / "qbank.json"
    bank.write_text(json.dumps([
        {"question_id": "clinical-001", "template": "clinical",
         "text": "What is X?", "difficulty": "routine",
         "expected_anchors": ["x"], "has_known_contradictions": False},
        {"question_id": "trade-001", "template": "trade",
         "text": "What is Y?", "difficulty": "novel_synthesis",
         "expected_anchors": ["y"], "expected_frames": ["mechanism"]},
    ]))
    out_path = tmp_path / "results.json"

    # Patch sys.argv for argparse
    old_argv = sys.argv
    sys.argv = ["api_benchmark_runner.py", "--questions", str(bank), "--results-out", str(out_path)]
    try:
        rc = runner.main()
    finally:
        sys.argv = old_argv

    assert rc == 0
    output = json.loads(out_path.read_text())

    # Schema present
    assert output["schema_version"] == "1.0.0"
    assert output["live_mode"] is False
    assert output["question_count"] == 2

    # All 3 systems evaluated per question
    for qid in ["clinical-001", "trade-001"]:
        assert qid in output["per_question_results"]
        responses = output["per_question_results"][qid]["responses"]
        assert set(responses.keys()) == {"polaris_v6", "chatgpt_5_5_pro_dr", "gemini_3_1_pro_dr"}

    # 8 dimensions per (question, system)
    for qid in ["clinical-001", "trade-001"]:
        scores_by_sys = output["per_question_results"][qid]["scores"]
        for sys_name, scores in scores_by_sys.items():
            dims = {s["dimension"] for s in scores}
            assert len(dims) == 8, f"{sys_name} on {qid}: expected 8 dims, got {dims}"

    # Aggregate + per-template + match-or-beat present
    assert "aggregate_per_system" in output
    assert "aggregate_per_template" in output
    assert "match_or_beat" in output
    assert output["match_or_beat"]["template_count"] == 2
