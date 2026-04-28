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


def test_ira_clean_energy_query_abstains() -> None:
    """Codex round-2 fix: bare "Inflation Reduction Act" is too
    broad as an anchor — IRA covers clean energy, EVs, drug
    pricing. Demoted to support; only narrow 'ira drug price'
    style anchors qualify."""
    inductor = KeywordInductor()
    v = inductor.induce(
        "How does the Inflation Reduction Act (IRA) clean energy "
        "tax credit interact with state RPS mandates?"
    )
    # Should abstain — only support keyword "inflation reduction
    # act" + "ira" match, no anchor.
    assert v.decision == "abstain"


def test_ira_drug_price_anchored_query_accepts() -> None:
    """Counter-test for the IRA narrowing: a legitimate drug-pricing
    IRA query should still accept via the narrow anchor variant."""
    inductor = KeywordInductor()
    v = inductor.induce(
        "How does the IRA drug price negotiation timeline affect Part D drugs?"
    )
    assert v.decision == "accept"
    assert getattr(v.induced_contract, "slug", "") == "policy_medicare_drug_price"


def test_hospital_reimbursement_no_longer_disqualifies() -> None:
    """Codex round-2 fix: "hospital reimbursement" was too blunt
    as a disqualifier — it false-blocked legitimate Medicare
    drug-pricing queries that mention hospital administration
    of Part D drugs. Removed; narrower device-specific
    disqualifiers ("insulin pump", "DME") kept."""
    inductor = KeywordInductor()
    v = inductor.induce(
        "How will Medicare drug price negotiation affect hospital "
        "reimbursement for Part D oncology drugs?"
    )
    # Anchor "medicare drug price" + "drug price negotiation" both
    # match; topic IS drug pricing. Should accept.
    assert v.decision == "accept"
    assert getattr(v.induced_contract, "slug", "") == "policy_medicare_drug_price"


def test_insulin_pump_still_disqualifies() -> None:
    """Counter-test: device-specific disqualifiers must still fire
    on the original off-template adversarial."""
    inductor = KeywordInductor()
    v = inductor.induce(
        "CMS reimbursement rules for insulin pumps under Medicare Advantage"
    )
    assert v.decision == "abstain"


def test_round4_ira_provisions_without_drug_word_abstains() -> None:
    """Codex round-4 fix: round-3 added 'ira provisions',
    'ira negotiation' etc. as anchors, but those false-accepted
    on EV-tax-credit queries. Round-4 REVERTED those anchors;
    queries that mention IRA + Part D without the word "drug"
    now abstain by design — they're genuinely ambiguous (Part D
    has non-drug rules; IRA has clean-energy provisions).

    Operator must include "drug" / "drug pricing" / "drug price"
    explicitly to route to the Medicare drug-price contract."""
    inductor = KeywordInductor()
    # These ALL abstain in v5 by design (no drug word):
    abstain_queries = [
        "How will IRA provisions affect Part D formulary design?",
        "How do IRA provisions affect EV tax credits?",
        "How did IRA negotiation affect EV tax credits?",
    ]
    for q in abstain_queries:
        v = inductor.induce(q)
        assert v.decision == "abstain", f"expected abstain for {q!r}, got {v}"

    # These ACCEPT (drug word present):
    accept_queries = [
        "How will IRA drug price negotiation affect Part D formularies?",
        (
            "What is the Inflation Reduction Act drug pricing "
            "negotiation timeline for Medicare Part D?"
        ),
        "What does IRA drug price negotiation mean for Medicare?",
    ]
    for q in accept_queries:
        v = inductor.induce(q)
        assert v.decision == "accept", f"expected accept for {q!r}, got {v}"
        assert (
            getattr(v.induced_contract, "slug", "")
            == "policy_medicare_drug_price"
        )


def test_round4_commercial_plans_plural_disqualifies() -> None:
    """Codex round-4: 'commercial plan' was singular-only. Plural
    'commercial plans' now disqualifies."""
    inductor = KeywordInductor()
    v = inductor.induce(
        "How does Medicare drug price negotiation affect commercial plans?"
    )
    assert v.decision == "abstain"


def test_round4_insulin_pump_hyphenated_disqualifies() -> None:
    """Codex round-4: 'insulin pump' (space) didn't match
    'insulin-pump' (hyphen). Both forms disqualify now."""
    inductor = KeywordInductor()
    v = inductor.induce(
        "How does Medicare drug price negotiation affect "
        "insulin-pump supplies?"
    )
    assert v.decision == "abstain"
    # Plural-hyphenated:
    v2 = inductor.induce(
        "Medicare drug price negotiation impact on insulin-pumps "
        "for Part D enrollees"
    )
    assert v2.decision == "abstain"


def test_round3_insulin_pumps_plural_disqualifies() -> None:
    """Codex round-3 fix: 'insulin pump' (singular) didn't match
    'insulin pumps' (plural) under word-boundary regex. Added
    plural variant. With anchor-bearing query, this is the real
    regression test — anchors would otherwise force accept."""
    inductor = KeywordInductor()
    v = inductor.induce(
        "How will Medicare drug price negotiation affect "
        "insulin pumps under Part D?"
    )
    # Despite anchor "medicare drug price" + "drug price negotiation"
    # both matching, the disqualifier "insulin pumps" forces abstain.
    assert v.decision == "abstain"


def test_round3_dme_reimbursements_plural_disqualifies() -> None:
    """Plural variant of DME disqualifier."""
    inductor = KeywordInductor()
    v = inductor.induce(
        "How does Medicare drug price negotiation interact with "
        "DME reimbursements for Part D supplies?"
    )
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
