"""M-D2 stub keyword inductor tests (Phase D).

Verifies the rule-based keyword+ontology inductor:
  - InductorProtocol-conformant
  - High-confidence single match → accept curator contract
  - Low max-score → abstain
  - Low margin (top-2 tied) → abstain
  - Disqualifier keywords → abstain
  - End-to-end run on the M-D1.5 expanded validation set with the
    full M-D1 benchmark harness, capturing baseline metrics.

The metrics from the end-to-end test are ASSERTED (not just printed)
so a regression in either the inductor or the validation set
produces a test failure rather than silent drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.auto_induction import (
    InductorVerdict,
    load_validation_set,
    run_benchmark,
)
from src.polaris_graph.auto_induction.keyword_inductor import (
    KeywordInductor,
    KeywordInductorConfig,
    _SlugProfile,
)


SEED_VS_PATH = (
    Path(__file__).resolve().parents[2]
    / "config" / "auto_induction" / "validation_set.yaml"
)


# ---------------------------------------------------------------------------
# Unit tests on KeywordInductor.induce()
# ---------------------------------------------------------------------------


def test_clinical_query_routes_to_clinical_slug() -> None:
    inductor = KeywordInductor()
    v = inductor.induce(
        "What is tirzepatide efficacy for type 2 diabetes (T2DM)?"
    )
    assert v.decision == "accept"
    # Confidence is matches/total_keywords, ratio in [0,1]. Just
    # assert it's > 0; the accept decision is count-based not
    # confidence-based.
    assert v.confidence is not None and v.confidence > 0.0
    assert getattr(v.induced_contract, "slug", "") == "clinical_tirzepatide_t2dm"


def test_policy_query_routes_to_policy_slug() -> None:
    inductor = KeywordInductor()
    v = inductor.induce(
        "Medicare drug price negotiation under the Inflation Reduction Act and CMS rules"
    )
    assert v.decision == "accept"
    assert getattr(v.induced_contract, "slug", "") == "policy_medicare_drug_price"


def test_low_score_abstains() -> None:
    """Query with no profile keywords abstains (no anchor + no support)."""
    inductor = KeywordInductor()
    v = inductor.induce("What is the meaning of life?")
    assert v.decision == "abstain"
    # Could be "no anchor keyword matched" or "below floor"; either
    # path is correct abstention. Just check decision.


def test_low_margin_abstains() -> None:
    """If two slugs tie on hit count, margin floor triggers abstain."""
    # Construct an artificial config where two slugs share the same
    # anchor list (so margin is always 0). Use words actually present
    # in the test query so anchors fire.
    profiles = (
        _SlugProfile(slug="A", anchor_keywords=("foo", "bar")),
        _SlugProfile(slug="B", anchor_keywords=("foo", "bar")),
    )
    inductor = KeywordInductor(
        KeywordInductorConfig(profiles=profiles)
    )
    v = inductor.induce("foo bar in the context of stuff")
    assert v.decision == "abstain"
    assert "margin" in (v.abstain_reason or "")


def test_no_anchor_match_abstains() -> None:
    """Codex round-1 fix: even with multiple support-keyword hits,
    accept requires at least one anchor. 'type 2 diabetes treatments'
    matches support keywords but no anchor, so must abstain."""
    inductor = KeywordInductor()
    v = inductor.induce("type 2 diabetes treatments overview")
    assert v.decision == "abstain"
    assert "anchor" in (v.abstain_reason or "")


def test_disqualifier_blocks_accept() -> None:
    """Codex round-1 fix: disqualifier keyword forces abstain even
    if anchors + supports match. PBM rebates in employer plan should
    NOT route to Medicare drug-price contract."""
    inductor = KeywordInductor()
    v = inductor.induce(
        "How do PBM rebates affect employer-sponsored insurance premiums?"
    )
    assert v.decision == "abstain"


def test_word_boundary_prevents_double_count() -> None:
    """Codex round-1 fix: 'drug price' should NOT match inside
    'drug pricing'. Word boundary regex enforces this."""
    inductor = KeywordInductor()
    # Query has 'drug pricing' (1 support hit). Should not also count
    # 'drug price' (the singular form is NOT in the query as a
    # word-boundary match).
    v = inductor.induce(
        "What are antiviral drug pricing trends in hospital pharmacies?"
    )
    # No anchor, only one support → abstain.
    assert v.decision == "abstain"


def test_paraphrase_robustness() -> None:
    """Different surface forms of the same clinical question with
    >=2 matched keywords should all route to the same slug.

    Single-keyword queries (e.g. "tirzepatide clinical trial
    outcomes" with just "tirzepatide") intentionally abstain at
    the M-D2 stub level to avoid over-routing on weak signal —
    M-D2 LLM-augmented version is expected to handle thinner
    paraphrase via embedding similarity."""
    inductor = KeywordInductor()
    queries = [
        "Mounjaro and HbA1c reduction in diabetes",
        "T2DM glycemic control with semaglutide vs tirzepatide",
        "SURPASS-2 evidence on tirzepatide for diabetes management",
        "tirzepatide vs ozempic for HbA1c",
    ]
    for q in queries:
        v = inductor.induce(q)
        assert v.decision == "accept", f"expected accept for {q!r}, got {v}"
        assert (
            getattr(v.induced_contract, "slug", "") == "clinical_tirzepatide_t2dm"
        ), f"wrong slug for {q!r}"


def test_single_keyword_query_abstains_by_design() -> None:
    """Single-keyword queries fall below accept_count_floor=2 and
    abstain. Documents the M-D2-stub coverage limitation that
    M-D2 LLM-augmented is expected to fix."""
    inductor = KeywordInductor()
    v = inductor.induce("tirzepatide clinical trial outcomes")
    assert v.decision == "abstain"
    assert "below floor 2" in (v.abstain_reason or "")


# ---------------------------------------------------------------------------
# End-to-end benchmark on the M-D1.5 expanded validation set
# ---------------------------------------------------------------------------


def test_end_to_end_benchmark_baseline_on_expanded_set() -> None:
    """Run the M-D2 stub against the M-D1.5 expanded validation set.
    Captures baseline metrics. The inductor's design (route to
    curator contract on high-confidence match, abstain otherwise)
    means precision should be high (uses curator's own contract,
    so match_score=1.0) but operator-review-load may be high
    because the keyword set is conservative.

    Hard-coded acceptance bands reflect the M-D2 STUB capability,
    not the M-D1 final acceptance thresholds (which apply to M-D2
    LLM-augmented or later)."""
    s = load_validation_set(SEED_VS_PATH)
    inductor = KeywordInductor()
    result = run_benchmark(inductor, s, tau=0.8)
    m = result.metrics

    # Expansion sanity: confirm the expanded set actually grew.
    assert m.total_cases >= 30, f"validation set too small: {m.total_cases}"
    assert m.in_scope_total >= 10, f"too few in-scope cases: {m.in_scope_total}"
    assert m.abstain_should_abstain_total >= 15, (
        f"too few abstain-expected cases: "
        f"{m.abstain_should_abstain_total}"
    )

    # Baseline expectations for the M-D2 STUB:
    # - precision should be 1.0 because the inductor returns the
    #   curator's own contract (the routing decision is the only
    #   thing being measured; if it routes correctly the contract
    #   matches by definition).
    assert m.precision == pytest.approx(1.0), (
        f"M-D2 stub should hit precision 1.0 by construction "
        f"(routes to curator contract on accept). Got {m.precision}. "
        f"Silent disagreements: {m.in_scope_silent_disagreements}"
    )

    # - silent_disagreement_rate should be 0 (same reason).
    assert m.silent_disagreement_rate == pytest.approx(0.0)

    # - abstain_recall should be at least 0.95 (M-D1 floor).
    #   The keyword inductor should abstain on all 8 ambiguous +
    #   14 out_of_scope cases. With the conservative thresholds
    #   in KeywordInductorConfig, this should comfortably pass.
    assert m.abstain_recall >= 0.95, (
        f"abstain_recall below 0.95: {m.abstain_recall}. "
        f"Inductor wrongly accepted some abstain-expected cases."
    )

    # The M-D2 stub will likely FAIL the operator_review_load
    # ceiling (0.30) because the keyword inductor has narrow
    # coverage on in-scope queries (especially policy paraphrases
    # without exact matches). Document as KNOWN for M-D2 LLM
    # version to improve.
    # Don't assert on operator_review_load here — it's the metric
    # M-D2 LLM is expected to improve.


def test_end_to_end_baseline_metric_shape() -> None:
    """Check the shape of the case_results — every case in the set
    should produce one (case, verdict, comparison) triple."""
    s = load_validation_set(SEED_VS_PATH)
    inductor = KeywordInductor()
    result = run_benchmark(inductor, s, tau=0.8)
    assert len(result.case_results) == s.total
    # Every case_result triple has the right shape.
    for case, verdict, cmp in result.case_results:
        assert verdict.decision in ("accept", "abstain")
        if case.group == "in_scope" and verdict.decision == "accept":
            # Comparison should be present + match_score should be
            # 1.0 since we route to the curator's own contract.
            assert cmp is not None
            assert cmp.match_score == pytest.approx(1.0)
        else:
            # Abstain or non-in-scope accept: no comparison.
            assert cmp is None
