"""
BUG-M-202 regression tests: contradiction detector domain coverage.

Pre-fix, the predicate table was obesity/cardiometabolic-only. AF
anticoagulation queries with stroke/bleeding endpoints returned zero
numeric_claims even though the corpus contained clear numeric
contradictions.

Post-fix (deep-dive R7 minimum-viable), the predicate table is
expanded to cover AF anticoagulation, tech benchmarks, policy rates,
and DD financial metrics; domain parameter routes to the relevant set.
"""
from __future__ import annotations

from src.polaris_graph.retrieval.contradiction_detector import (
    _DOMAIN_PREDICATES,
    _EFFICACY_PREDICATES,
    _normalize_predicate,
    detect_contradictions,
    extract_numeric_claims,
)


def _ev(evid: str, quote: str, url: str = "http://x", tier: str = "T1") -> dict:
    return {
        "evidence_id": evid,
        "direct_quote": quote,
        "source_url": url,
        "tier": tier,
    }


# ─────────────────────────────────────────────────────────────────
# AF anticoagulation — the reproducer from real artifact
# ─────────────────────────────────────────────────────────────────

def test_m202_af_stroke_rate_predicate_recognized() -> None:
    """stroke rate, major bleeding, ICH all recognized as predicates."""
    assert _normalize_predicate(
        "Warfarin had a stroke rate of 1.6% per year.",
        domain="clinical",
    ) == "stroke rate"
    assert _normalize_predicate(
        "Apixaban major bleeding 2.1% annually.",
        domain="clinical",
    ) == "major bleeding"
    assert _normalize_predicate(
        "Intracranial hemorrhage 0.3% for DOAC vs 0.8% warfarin.",
        domain="clinical",
    ) == "intracranial hemorrhage"


def test_m202_af_stroke_rate_claims_extracted_with_domain() -> None:
    """AF reproducer: stroke endpoints now produce claims when the
    domain is passed. Full generic-numeric-mining per Codex §4 is
    tracked as followup (see docs/todo_list.md); this test verifies
    the minimum-viable fix closes the most common AF cases where the
    value-verb gate already matches."""
    evidence = [
        _ev("ev_af_1",
            "Apixaban reduced stroke rate by 1.27% per year versus warfarin."),
        _ev("ev_af_2",
            "Dabigatran 150mg reduced stroke rate by 1.11% per year versus warfarin."),
    ]
    claims = extract_numeric_claims(evidence, domain="clinical")
    # The "reduced ... by" verb pattern matches _VALUE_PHRASE_VERBS.
    predicates = {c.predicate for c in claims}
    assert "stroke rate" in predicates, (
        f"stroke rate should be in predicates, got {predicates}"
    )


def test_m202_metabolic_style_quote_with_af_endpoint() -> None:
    """A quote using the same verb structure as metabolic trials but
    with an AF endpoint should extract."""
    evidence = [
        _ev("ev_af_1",
            "Apixaban achieved a major bleeding rate of 2.1% annually."),
    ]
    claims = extract_numeric_claims(evidence, domain="clinical")
    # "achieved" matches _VALUE_PHRASE_VERBS
    predicates = {c.predicate for c in claims}
    assert "major bleeding" in predicates or any(
        "bleeding" in p for p in predicates
    )


# ─────────────────────────────────────────────────────────────────
# Tech / policy / DD domain predicates
# ─────────────────────────────────────────────────────────────────

def test_m202_tech_domain_predicates() -> None:
    """Tech endpoints (accuracy, f1, error rate, latency) are recognized
    when domain='tech'."""
    for pred, text in [
        ("accuracy", "BERT-large achieved accuracy of 91.2% on SQuAD."),
        ("f1 score", "Model reported f1 score 89.5 on the benchmark."),
        ("error rate", "LLaMA achieves error rate 8.3%."),
        ("latency", "Inference latency averaged 47ms per request."),
    ]:
        assert _normalize_predicate(text, domain="tech") == pred, (
            f"tech predicate {pred!r} not recognized in {text!r}"
        )


def test_m202_policy_domain_predicates() -> None:
    for pred, text in [
        ("compliance rate", "EU AI Act compliance rate reached 34%."),
        ("adoption rate", "Adoption rate among SMEs was 12%."),
    ]:
        assert _normalize_predicate(text, domain="policy") == pred


def test_m202_due_diligence_domain_predicates() -> None:
    for pred, text in [
        ("revenue growth", "Company reported revenue growth of 23% YoY."),
        ("ebitda margin", "EBITDA margin expanded to 18%."),
    ]:
        assert _normalize_predicate(text, domain="due_diligence") == pred


# ─────────────────────────────────────────────────────────────────
# Backward compatibility — metabolic still works without domain
# ─────────────────────────────────────────────────────────────────

def test_m202_metabolic_still_works_without_domain() -> None:
    """Pre-fix behavior preserved: weight loss without domain= kwarg."""
    quote = "Semaglutide produced mean weight loss of 14.9% at week 68."
    assert _normalize_predicate(quote) == "weight loss"
    assert _normalize_predicate(quote, domain="clinical") == "weight loss"


def test_m202_orchestrator_passes_domain_to_detector() -> None:
    """Source check: run_honest_sweep_r3 passes domain=q['domain']."""
    import inspect
    import scripts.run_honest_sweep_r3 as sweep
    source = inspect.getsource(sweep.run_one_query)
    assert "extract_numeric_claims(" in source
    # The call must pass domain= kwarg so the per-domain table is used.
    assert "domain=q[\"domain\"]" in source or "domain=q['domain']" in source, (
        "orchestrator must pass domain to extract_numeric_claims"
    )


def test_m202_domain_predicate_table_coverage() -> None:
    """Smoke: every scope_templates domain has at least some predicates."""
    for domain in ("clinical", "tech", "policy", "due_diligence"):
        assert domain in _DOMAIN_PREDICATES
        assert len(_DOMAIN_PREDICATES[domain]) > 0
