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


def test_pt12_ignores_bibliography_title_year_brackets() -> None:
    """BUG-M-5 (Codex pass 5 gating medium): PT12 must not treat a
    bracketed year in a bibliography entry title (e.g., "Best Guide on
    RAG Pipeline [2025]") as an out-of-range citation marker. Before
    the fix, the regex scanned the whole report and flagged `[2025]`
    as marker 2025 > evidence_pool size, causing a false-positive
    release abort."""
    report = (
        "# Research report: best practices for RAG\n"
        "\n"
        "Retrieval-augmented generation combines search with LLMs [1].\n"
        "Hybrid approaches are common [2].\n"
        "\n"
        "## Methods\n"
        "Retrieved on 2026-04-18 via Serper.\n"
        "Generator model: deepseek/deepseek-v3.2-exp.\n"
        "Evaluator model: qwen/qwen3-8b.\n"
        "\n"
        "## Bibliography\n"
        "[1] A Survey on RAG Architectures — https://arxiv.org/abs/x (tier T1)\n"
        "[2] Best Guide on RAG Pipeline, Use Cases & Diagrams [2025] "
        "— https://dextralabs.com/blog/rag (tier T4)\n"
    )
    ev_pool = {"ev_a": {"direct_quote": "a"}, "ev_b": {"direct_quote": "b"}}
    # evidence_pool size = 2, legitimate citation markers go up to [2]
    # The [2025] in the bibliography title must be excluded from the scan
    out = run_external_evaluation(
        report_text=report,
        protocol={"research_question": "best practices for RAG",
                  "expected_tier_distribution": []},
        tier_distribution_report={},
        contradictions=[],
        evidence_pool=ev_pool,
        enable_llm_judge=False,
    )
    pt12 = next(r for r in out.rule_checks if r.item_id == "PT12")
    assert pt12.passed, (
        f"PT12 should pass when only bibliography-title year brackets "
        f"exceed pool size. Got details: {pt12.details}"
    )


def test_pt13_exempts_title_and_question_inherited_superlatives() -> None:
    """BUG-M-6 (Codex pass 5 follow-up): PT13 must not count
    question-inherited superlatives toward its unhedged count. The
    research question literally contains 'best', the title echoes it,
    and the generator may echo it again in prose. None of those is a
    generator assertion."""
    report = (
        "# Research report: What are the current best practices for RAG?\n"
        "\n"
        "Hybrid retrieval is the best approach for most pipelines.\n"
        "Dense retrieval works well in many cases.\n"
        "\n"
        "## Methods\n"
        "Retrieved on 2026-04-18.\n"
    )
    out = run_external_evaluation(
        report_text=report,
        protocol={"research_question":
                  "What are the current best practices for RAG?",
                  "expected_tier_distribution": []},
        tier_distribution_report={},
        contradictions=[],
        evidence_pool={"ev_a": {"direct_quote": "a"}},
        enable_llm_judge=False,
    )
    pt13 = next(r for r in out.rule_checks if r.item_id == "PT13")
    assert pt13.passed, (
        f"PT13 should pass when 'best' is inherited from the research "
        f"question. Got details: {pt13.details}"
    )


def test_pt13_exemption_requires_lexical_echo_of_research_question() -> None:
    """BUG-M-6 refinement (Codex pass 6): an adversarial research
    question stuffed with superlatives must not globally suppress
    PT13 detection. The exemption requires the prose sentence to
    share >=2 content words with the research question (lexical
    echo), which rejects unrelated prose even if the superlative
    itself appears in the question."""
    # Adversarial question: every single-word superlative in the family
    adversarial_question = (
        "What is the best leading superior top unparalleled unmatched "
        "unprecedented largest highest greatest approach for drug X?"
    )
    # Prose sentences each use a different question-listed superlative
    # but do NOT share >=2 content words with the question (only the
    # superlative itself overlaps). Under the pre-refinement M-6, all
    # of these would have been exempted. Under the refinement, they
    # should all flag.
    report = (
        "# Research report: drug X study\n"
        "\n"
        "This method is unparalleled.\n"
        "Results were unmatched.\n"
        "The outcome is greatest.\n"
        "The effect is superior.\n"
        "\n"
        "## Methods\n"
        "Retrieved on 2026-04-18.\n"
    )
    out = run_external_evaluation(
        report_text=report,
        protocol={"research_question": adversarial_question,
                  "expected_tier_distribution": []},
        tier_distribution_report={},
        contradictions=[],
        evidence_pool={"ev_a": {"direct_quote": "a"}},
        enable_llm_judge=False,
    )
    pt13 = next(r for r in out.rule_checks if r.item_id == "PT13")
    assert not pt13.passed, (
        "Adversarial research_question must NOT globally suppress PT13. "
        f"Got: {pt13.details}"
    )
    # Details start with "<count> unhedged:" — confirm count is 4.
    assert pt13.details.startswith("4 unhedged"), (
        f"expected 4 unhedged; got: {pt13.details}"
    )


def test_pt13_exemption_handles_short_question_direct_answer_paraphrase() -> None:
    """BUG-M-6 second refinement (Codex pass 7): dynamic echo
    threshold must tolerate natural paraphrase when the question
    contains only ONE superlative. Codex case 1: short question
    "best RAG practices?" → direct answer "Hybrid retrieval with
    dense embeddings is the best approach". Content-word overlap
    with the question is only {best} (1) but the sentence is a
    legitimate direct answer, not an independent superlative claim.
    Under the hard ≥2 threshold this incorrectly flagged; under the
    dynamic threshold (≥1 when question has ≤1 superlative), it
    correctly exempts."""
    report = (
        "# Research report: best RAG practices?\n"
        "\n"
        "Hybrid retrieval with dense embeddings and learned sparse "
        "vectors is the best approach for most production deployments.\n"
        "\n"
        "## Methods\n"
        "Retrieved on 2026-04-19.\n"
    )
    out = run_external_evaluation(
        report_text=report,
        protocol={"research_question": "best RAG practices?",
                  "expected_tier_distribution": []},
        tier_distribution_report={},
        contradictions=[],
        evidence_pool={"ev_a": {"direct_quote": "a"}},
        enable_llm_judge=False,
    )
    pt13 = next(r for r in out.rule_checks if r.item_id == "PT13")
    assert pt13.passed, (
        f"Dynamic threshold should exempt single-superlative question "
        f"paraphrase. Got: {pt13.details}"
    )


def test_pt13_dynamic_threshold_still_blocks_adversarial_stuffing() -> None:
    """Dynamic threshold does NOT loosen the adversarial case: when
    the question has ≥2 superlatives, the ≥2 content-word requirement
    applies (strict)."""
    # Same adversarial question as the pass-6 test
    adversarial_question = (
        "What is the best leading superior top unparalleled unmatched "
        "unprecedented largest highest greatest approach for drug X?"
    )
    report = (
        "# Research report: drug X\n"
        "\n"
        "This method is unparalleled.\n"
        "Results were unmatched.\n"
        "\n"
        "## Methods\n"
        "Retrieved on 2026-04-19.\n"
    )
    out = run_external_evaluation(
        report_text=report,
        protocol={"research_question": adversarial_question,
                  "expected_tier_distribution": []},
        tier_distribution_report={},
        contradictions=[],
        evidence_pool={"ev_a": {"direct_quote": "a"}},
        enable_llm_judge=False,
    )
    pt13 = next(r for r in out.rule_checks if r.item_id == "PT13")
    assert not pt13.passed, (
        "Dynamic threshold must still block adversarial stuffing. "
        f"Got: {pt13.details}"
    )
    assert pt13.details.startswith("2 unhedged"), (
        f"expected 2 unhedged; got: {pt13.details}"
    )


def test_pt13_exemption_applies_when_prose_echoes_question() -> None:
    """Legitimate case: prose sentence shares >=2 content words with
    the research question (lexical echo), so the question-inherited
    superlative exemption applies."""
    report = (
        "# Research report: What are the best practices for RAG?\n"
        "\n"
        "The best practices for RAG include hybrid retrieval.\n"
        "Dense retrieval works well for many queries.\n"
        "\n"
        "## Methods\n"
        "Retrieved on 2026-04-18.\n"
    )
    # Question content words: {best, practices, rag}
    # Prose sentence 1 content words: {best, practices, rag, include,
    # hybrid, retrieval}; overlap = {best, practices, rag} = 3 >= 2
    # → exempted. Prose sentence 2 has no superlative.
    out = run_external_evaluation(
        report_text=report,
        protocol={"research_question": "What are the best practices for RAG?",
                  "expected_tier_distribution": []},
        tier_distribution_report={},
        contradictions=[],
        evidence_pool={"ev_a": {"direct_quote": "a"}},
        enable_llm_judge=False,
    )
    pt13 = next(r for r in out.rule_checks if r.item_id == "PT13")
    assert pt13.passed, (
        f"Legitimate lexical-echo prose must be exempted. Got: {pt13.details}"
    )


def test_pt13_still_flags_real_generator_superlatives() -> None:
    """Regression guard for M-6 — PT13 must still flag generator
    superlatives that do NOT appear in the research question."""
    report = (
        "# Research report: drug efficacy review\n"
        "\n"
        "This drug is unparalleled in its efficacy.\n"
        "It offers superior outcomes.\n"
        "It is the greatest treatment for this condition.\n"
        "\n"
        "## Methods\n"
        "Retrieved on 2026-04-18.\n"
    )
    out = run_external_evaluation(
        report_text=report,
        protocol={"research_question": "drug efficacy review",
                  "expected_tier_distribution": []},
        tier_distribution_report={},
        contradictions=[],
        evidence_pool={"ev_a": {"direct_quote": "a"}},
        enable_llm_judge=False,
    )
    pt13 = next(r for r in out.rule_checks if r.item_id == "PT13")
    assert not pt13.passed
    # 3 unhedged superlatives: 'unparalleled', 'superior', 'greatest'
    for term in ("unparalleled", "superior", "greatest"):
        assert term in pt13.details


def test_pt12_still_flags_real_out_of_range_citation_in_prose() -> None:
    """PT12's core contract still works when a citation marker in
    actual prose exceeds the evidence pool. Regression guard for the
    M-5 fix: we must not broaden PT12 into a no-op."""
    report = (
        "# Research report: drug X\n"
        "\n"
        "The drug works well [1][99].\n"  # [99] is out of range
        "\n"
        "## Methods\n"
        "Retrieved on 2026-04-18.\n"
        "\n"
        "## Bibliography\n"
        "[1] Trial A — https://nejm.org/a (tier T1)\n"
    )
    ev_pool = {"ev_a": {"direct_quote": "a"}}  # only 1 entry
    out = run_external_evaluation(
        report_text=report,
        protocol={"research_question": "drug X",
                  "expected_tier_distribution": []},
        tier_distribution_report={},
        contradictions=[],
        evidence_pool=ev_pool,
        enable_llm_judge=False,
    )
    pt12 = next(r for r in out.rule_checks if r.item_id == "PT12")
    assert not pt12.passed
    assert "99" in pt12.details


def test_same_family_pair_raises_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    # I-ready-018 (#1088): force both sides to the same family by monkeypatch.setattr on the LIVE
    # module globals (auto-restored) instead of setenv + importlib.reload(orc). reload() rebinds
    # openrouter_client.BudgetExceededError to a non-subclass class object and resets _RUN_COST_CTX,
    # poisoning the 4-role seam / fx01 / semantic-conflict budget tests later in the full sweep.
    # check_family_segregation reads PG_GENERATOR_MODEL / PG_EVALUATOR_MODEL as module globals at
    # call time (openrouter_client.py:627-628), so setattr is sufficient and reload-free.
    import src.polaris_graph.llm.openrouter_client as orc
    monkeypatch.setattr(orc, "PG_GENERATOR_MODEL", "deepseek/deepseek-chat")
    monkeypatch.setattr(orc, "PG_EVALUATOR_MODEL", "deepseek/deepseek-coder")
    with pytest.raises(RuntimeError) as excinfo:
        run_external_evaluation(
            report_text="dummy report",
            protocol={"expected_tier_distribution": []},
            tier_distribution_report={},
            contradictions=[],
            evidence_pool={},
        )
    assert "same" in str(excinfo.value).lower()
    # No manual restore + reload needed — monkeypatch.setattr auto-restores both globals.
