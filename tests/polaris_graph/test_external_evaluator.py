"""
Tests for Phase 5 external non-same-family evaluator.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.evaluator.external_evaluator import (
    EvaluatorOutput,
    run_external_evaluation,
    run_rule_checks,
)


_EVIDENCE_POOL = {
    "ev_step1": {
        "direct_quote": "Mean weight loss was 14.9% at week 68.",
        "source_url": "https://nejm.org/x",
        "tier": "T1",
    },
    "ev_step5": {
        "direct_quote": "Mean weight loss was 17.4% at week 104.",
        "source_url": "https://diabetesjournals.org/y",
        "tier": "T1",
    },
}


def _compliant_report() -> str:
    return (
        "# Semaglutide weight-loss report\n"
        "\n"
        "## Methods\n"
        "Retrieved on 2026-04-17 from PubMed, OpenAlex, and Semantic Scholar.\n"
        "The pre-registered protocol.json specifies inclusion of peer-reviewed\n"
        "RCTs and exclusion of scribd.com hosted documents. Sources were classified\n"
        "using the T1-T7 tier taxonomy. Sponsor funding was assessed.\n"
        "Generator model: deepseek/deepseek-v3.2-exp.\n"
        "Evaluator model: qwen/qwen3-8b.\n"
        "Prompt injection sanitization was applied to all evidence.\n"
        "\n"
        "## Results\n"
        "Actual tier distribution was T1=40%, T2=25%, T3=15%, T5=10%, T6=10%,\n"
        "within the expected ranges.\n"
        "Two weight loss results from the semaglutide program diverged: one RCT\n"
        "reported 14.9%[1] weight loss at 68 weeks and another reported 17.4%[2]\n"
        "at 104 weeks.\n"
    )


def _clinical_protocol() -> dict:
    return {
        "research_question": "Semaglutide weight loss",
        "expected_tier_distribution": [
            {"tier": "T1", "min_fraction": 0.30, "max_fraction": 0.60},
        ],
    }


def _contradiction_entry() -> dict:
    return {
        "subject": "semaglutide",
        "predicate": "weight loss",
        "claims": [
            {"evidence_id": "ev_step1", "value": 14.9, "unit": "%"},
            {"evidence_id": "ev_step5", "value": 17.4, "unit": "%"},
        ],
        "relative_difference": 0.168,
        "absolute_difference": 2.5,
        "severity": "medium",
    }


def test_fully_compliant_report_passes_most_checks() -> None:
    result = run_external_evaluation(
        report_text=_compliant_report(),
        protocol=_clinical_protocol(),
        tier_distribution_report={
            "tier_fractions": {"T1": 0.4},
            "tier_counts": {"T1": 4},
            "total_sources": 10,
        },
        contradictions=[_contradiction_entry()],
        evidence_pool=_EVIDENCE_POOL,
        enable_llm_judge=False,
    )
    assert isinstance(result, EvaluatorOutput)
    # Two different families
    assert result.generator_family != result.evaluator_family
    # Most checks should pass
    failed_names = [r.name for r in result.rule_checks if not r.passed]
    # Allow up to 2 minor failures (heuristics)
    assert len(failed_names) <= 2, f"Unexpected failures: {failed_names}"
    # Contradictions disclosed
    assert result.contradictions_disclosed >= 1


def test_report_missing_methods_fails_checks() -> None:
    bare_report = "Results: semaglutide works great. [1] Everyone should take it."
    result = run_external_evaluation(
        report_text=bare_report,
        protocol=_clinical_protocol(),
        tier_distribution_report=None,
        contradictions=[],
        evidence_pool=_EVIDENCE_POOL,
    )
    # Many checks should fail
    fail_count = result.rule_check_fail_count
    assert fail_count >= 6  # at least half should fail


def test_contradiction_missing_from_report_detected() -> None:
    # Report that doesn't mention the contradiction
    text = (
        "## Methods\n"
        "Retrieved 2026-04-17 using protocol.json. "
        "deepseek/deepseek-v3.2-exp generated. qwen/qwen3-8b evaluated. "
        "Included RCTs. Excluded blogs. Tiers T1-T7. Expected actual tier match.\n"
        "## Results\n"
        "The drug worked.\n"
    )
    result = run_external_evaluation(
        report_text=text,
        protocol=_clinical_protocol(),
        tier_distribution_report={"tier_fractions": {}},
        contradictions=[_contradiction_entry()],
        evidence_pool=_EVIDENCE_POOL,
    )
    assert len(result.contradictions_missing) == 1
    pt08 = next(r for r in result.rule_checks if r.item_id == "PT08")
    assert pt08.passed is False


def test_evaluator_output_is_json_serializable() -> None:
    import json
    result = run_external_evaluation(
        report_text=_compliant_report(),
        protocol=_clinical_protocol(),
        tier_distribution_report={"tier_fractions": {"T1": 0.4}},
        contradictions=[],
        evidence_pool=_EVIDENCE_POOL,
    )
    data = result.to_json_dict()
    # Should round-trip through JSON
    text = json.dumps(data, default=str)
    loaded = json.loads(text)
    assert loaded["generator_model"]
    assert "rule_checks" in loaded


def test_same_family_pair_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # Force both sides to be the same family
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setenv("PG_EVALUATOR_MODEL", "deepseek/deepseek-coder")
    # Reload the module so it picks up the env vars
    import importlib
    import src.polaris_graph.llm.openrouter_client as orc
    importlib.reload(orc)
    # Patch the evaluator's re-import
    with pytest.raises(RuntimeError) as excinfo:
        run_external_evaluation(
            report_text="dummy report",
            protocol={"expected_tier_distribution": []},
            tier_distribution_report={},
            contradictions=[],
            evidence_pool={},
        )
    assert "same" in str(excinfo.value).lower()
    # Restore defaults
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v3.2-exp")
    monkeypatch.setenv("PG_EVALUATOR_MODEL", "qwen/qwen3-8b")
    importlib.reload(orc)
