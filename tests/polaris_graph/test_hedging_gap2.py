"""
Regression tests for Gap-2 hedging / superlative attribution.
"""
from __future__ import annotations

from src.polaris_graph.generator.provenance_generator import (
    _detect_unhedged_superlative,
    verify_sentence_provenance,
)
from src.polaris_graph.evaluator.external_evaluator import run_rule_checks


# ─────────────────────────────────────────────────────────────────────────────
# Detector unit tests
# ─────────────────────────────────────────────────────────────────────────────


def test_gap2_unhedged_superlative_detected() -> None:
    sent = "Semaglutide produces the largest weight loss of any obesity medication."
    assert _detect_unhedged_superlative(sent) == "largest"


def test_gap2_hedged_via_source_verb_not_flagged() -> None:
    # "one review describes X as the largest" → hedged via "describes"
    sent = (
        "One review describes semaglutide as having the largest weight "
        "loss of any obesity medication to date."
    )
    assert _detect_unhedged_superlative(sent) is None


def test_gap2_hedged_via_reported_not_flagged() -> None:
    sent = (
        "Semaglutide is reported as the most effective anti-obesity "
        "drug in a recent meta-analysis."
    )
    assert _detect_unhedged_superlative(sent) is None


def test_gap2_bare_comparative_flagged() -> None:
    sent = "Tirzepatide is better than semaglutide for weight loss."
    assert _detect_unhedged_superlative(sent) == "better than"


def test_gap2_hedged_comparative_not_flagged() -> None:
    sent = (
        "A real-world analysis found that tirzepatide had lower "
        "cardiovascular event risk than semaglutide."
    )
    assert _detect_unhedged_superlative(sent) is None


def test_gap2_no_superlative_not_flagged() -> None:
    sent = "Semaglutide is FDA-approved for chronic weight management."
    assert _detect_unhedged_superlative(sent) is None


# ─────────────────────────────────────────────────────────────────────────────
# Integration: soft_warnings surface on SentenceVerification
# ─────────────────────────────────────────────────────────────────────────────


def test_gap2_soft_warning_does_not_drop_sentence() -> None:
    """Unhedged superlatives are a SOFT warning; the sentence still verifies
    if its numbers line up."""
    ev_pool = {
        # Span must cover both 14.9 AND content words (post-B-1).
        # "Weight loss was 14.9% at week 68." — span 0-26 covers it.
        "ev_a": {"direct_quote": "Weight loss was 14.9% at week 68."},
    }
    # Note: unhedged "largest", but a valid provenance token
    sentence = (
        "Semaglutide achieves the largest weight loss of 14.9% "
        "[#ev:ev_a:0-26]."
    )
    v = verify_sentence_provenance(sentence, ev_pool)
    assert v.is_verified is True  # not dropped
    assert any("unhedged_superlative" in w for w in v.soft_warnings)


def test_gap2_hedged_sentence_has_no_soft_warning() -> None:
    ev_pool = {
        # Span must cover both 14.9 AND content words (post-B-1).
        # "Weight loss was 14.9% at week 68." — span 0-26 covers it.
        "ev_a": {"direct_quote": "Weight loss was 14.9% at week 68."},
    }
    sentence = (
        "One trial reports weight loss of 14.9% [#ev:ev_a:0-26]."
    )
    v = verify_sentence_provenance(sentence, ev_pool)
    assert v.is_verified is True
    assert v.soft_warnings == []


# ─────────────────────────────────────────────────────────────────────────────
# PT13 rule-check
# ─────────────────────────────────────────────────────────────────────────────


def test_gap2_pt13_passes_when_hedged() -> None:
    report = (
        "# Semaglutide report\n\n"
        "One trial reports weight loss of 14.9% at 68 weeks.[1] "
        "A real-world analysis found lower cardiovascular risk with tirzepatide.[2]\n"
        "\n## Methods\n"
        "Retrieved 2026-04-18 from protocol.json. "
        "Generator: deepseek/deepseek-v3.2-exp. Evaluator: qwen/qwen3-8b. "
        "Inclusion / exclusion per template. Tiers T1-T7 used. "
        "Expected vs actual distribution reported. Sponsor review done. "
        "Prompt-injection sanitized.\n"
    )
    results, _, _ = run_rule_checks(
        report_text=report,
        protocol={},
        tier_distribution_report={"tier_fractions": {}},
        contradictions=[],
        evidence_pool={"ev_1": {}},
        generator_model="deepseek/deepseek-v3.2-exp",
        evaluator_model="qwen/qwen3-8b",
    )
    pt13 = next(r for r in results if r.item_id == "PT13")
    assert pt13.passed is True


def test_gap2_pt13_fails_when_multiple_unhedged() -> None:
    report = (
        "# Report\n\n"
        "Semaglutide produces the largest weight loss of any obesity drug.[1] "
        "Tirzepatide is better than semaglutide for weight loss.[2] "
        "Semaglutide is the most effective option for long-term outcomes.[3]\n"
        "\n## Methods\nRetrieved 2026-04-18.\n"
    )
    results, _, _ = run_rule_checks(
        report_text=report,
        protocol={},
        tier_distribution_report={"tier_fractions": {}},
        contradictions=[],
        evidence_pool={},
        generator_model="deepseek/deepseek-v3.2-exp",
        evaluator_model="qwen/qwen3-8b",
    )
    pt13 = next(r for r in results if r.item_id == "PT13")
    assert pt13.passed is False
    assert "unhedged" in pt13.details.lower() or len(pt13.details) > 0


def test_gap2_pt13_tolerates_one_unhedged() -> None:
    """Soft check: <=1 unhedged is acceptable (single lapse shouldn't fail
    the whole PRISMA checklist)."""
    report = (
        "# Report\n\n"
        "One trial reports 14.9% weight loss.[1] "
        "Semaglutide demonstrates the greatest efficacy among GLP-1 agonists.[2]\n"
        "\n## Methods\nRetrieved 2026-04-18.\n"
    )
    results, _, _ = run_rule_checks(
        report_text=report,
        protocol={},
        tier_distribution_report={"tier_fractions": {}},
        contradictions=[],
        evidence_pool={},
        generator_model="deepseek/deepseek-v3.2-exp",
        evaluator_model="qwen/qwen3-8b",
    )
    pt13 = next(r for r in results if r.item_id == "PT13")
    assert pt13.passed is True
