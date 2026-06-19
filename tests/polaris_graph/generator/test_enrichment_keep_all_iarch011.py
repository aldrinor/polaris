"""I-arch-011 (B18/B16, KEYSTONE breadth) — fail-loud behavioral test for the
weighted-enrichment WEIGHT-not-FILTER fix.

THE BUG (B18): weighted_enrichment.py re-imposed a HARD ``selection_relevance <
PG_RELEVANCE_FLOOR`` DROP on the unbound-SUPPORTS selection — the §-1.3-FORBIDDEN
FILTER-AND-CAP anti-pattern that the selector docstring (evidence_selector.py:
1944-1953) explicitly forbids. On a long 3-part research question the whole-question
denominator (B16) makes that 0.30 floor demand ~22 exact-word matches per source, so
729 of 746 isolated-span-verified unbound SUPPORTS scored below floor and were
DROPPED — the enrichment section appended NOTHING. The masking reason
(``all_supports_bound_or_pool_absent``) hid that the floor, not binding, was the
killer.

THE FIX (faithfulness-NEUTRAL):
  (a) REMOVE the hard floor drop — KEEP every SUPPORTS member, sort below-floor rows
      LAST (an ORDERING demotion, never an exclusion); ``below_floor_count`` is pure
      telemetry.
  (b) the empty-exit reason can no longer be "all below floor" (the floor never
      excludes); it reports the TRUE reason (no-supports / bound-or-pool-absent).
  (c) the relevance normalization is per-subquery and MONOTONIC-UP (max of the
      whole-question score and the best per-facet score) — the floor only ever OPENS,
      never tightens, under the credibility-redesign default.

These assertions FAIL on the pre-fix code (which dropped below-floor members and
mis-reported the reason / used the whole-question denominator) and PASS after.

FAITHFULNESS: enrichment surfaces the FULL ordered basket through the UNCHANGED
``strict_verify`` gate; nothing here relaxes a verify gate. Breadth comes from
keeping already-isolated-verified corroborators, not from loosening verification.
"""

from __future__ import annotations

from src.polaris_graph.generator.weighted_enrichment import (
    diagnose_unbound_supports_selection,
    select_unbound_supports_by_weight,
)
from src.polaris_graph.retrieval.evidence_selector import (
    _content_tokens,
    _row_relevance,
    _row_relevance_facet,
    _subquery_floor_enabled,
    _subquery_token_sets,
)
from src.polaris_graph.synthesis.credibility_pass import (
    BasketMember,
    ClaimBasket,
    CredibilityAnalysis,
)


def _member(evidence_id: str) -> BasketMember:
    return BasketMember(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_tier="T2",
        origin_cluster_id=f"oc_{evidence_id}",
        credibility_weight=0.8,
        authority_score=0.8,
        span=(0, 20),
        direct_quote="a verified span of source text",
        span_verdict="SUPPORTS",
    )


def _basket(cluster_id: str, weight_mass: float, members: list[BasketMember]) -> ClaimBasket:
    return ClaimBasket(
        claim_cluster_id=cluster_id,
        claim_text="claim text",
        subject="subject",
        predicate="predicate",
        supporting_members=members,
        refuter_cluster_ids=(),
        weight_mass=weight_mass,
        total_clustered_origin_count=len(members),
        verified_support_origin_count=len(members),
        basket_verdict="full",
    )


def _analysis(baskets: list[ClaimBasket]) -> CredibilityAnalysis:
    return CredibilityAnalysis(
        credibility_by_evidence={},
        origin_by_evidence={},
        claims=[],
        edges=[],
        weight_mass=[],
        baskets=baskets,
        cluster_id_by_evidence={},
    )


class _Plan:
    """Duck-typed contract plan with no bound evidence (so nothing is excluded as bound)."""

    title = "Efficacy"
    ev_ids: list[str] = []
    slots: tuple = ()


# ── (a) keep-all: ALL 10 below-floor SUPPORTS surface; 0 dropped by the floor ──


def test_ten_below_floor_supports_all_kept_zero_dropped_by_floor(monkeypatch):
    """B18 keystone: 10 SUPPORTS members whose source rows ALL score BELOW the floor
    (the long-question denominator pathology) surface in FULL — supports_kept == 10,
    0 dropped by the relevance floor. On the pre-fix code every one was DROPPED and
    the result was empty; this is the fail-loud guard for the 729/746 collapse."""
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    # 10 distinct sources, each PRESENT in the pool with a real but below-floor
    # relevance (0.05..0.14) — i.e. genuinely on-pool, low whole-question overlap.
    eids = [f"ev{i}" for i in range(1, 11)]
    pool = {
        eid: {"evidence_id": eid, "selection_relevance": 0.05 + 0.01 * i}
        for i, eid in enumerate(eids)
    }
    # Each member sits in its own basket with a descending weight_mass.
    baskets = [
        _basket(f"c{i}", weight_mass=1.0 - 0.05 * i, members=[_member(eid)])
        for i, eid in enumerate(eids)
    ]
    diag = diagnose_unbound_supports_selection(
        evidence_pool=pool,
        credibility_analysis=_analysis(baskets),
        contract_plans=[_Plan()],
    )
    supports_kept = len(diag.ev_ids)
    # KEEP-ALL: all 10 below-floor supports surface — the floor dropped NONE.
    assert supports_kept == 10, (
        f"floor drop regressed: {supports_kept} of 10 below-floor supports kept "
        "(pre-fix code dropped all 10 -> empty enrichment, the 729/746 collapse)"
    )
    assert set(diag.ev_ids) == set(eids)
    # below_floor_count is TELEMETRY (kept, not excluded): all 10 are below floor.
    assert diag.excluded_below_floor == 10
    assert diag.excluded_bound == 0
    assert diag.excluded_pool_absent == 0


# ── (a) ordering: below-floor rows sort LAST behind at/above-floor + missing rows ──


def test_below_floor_rows_sorted_last(monkeypatch):
    """Above-floor and missing-relevance rows sort BEFORE present-and-below-floor rows
    (the below-floor demotion), while ALL are kept."""
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    pool = {
        "ev_above": {"evidence_id": "ev_above", "selection_relevance": 0.90},
        "ev_missing": {"evidence_id": "ev_missing"},          # no relevance -> keep-neutral
        "ev_below_hi_w": {"evidence_id": "ev_below_hi_w", "selection_relevance": 0.10},
    }
    baskets = [
        _basket("c_above", 0.10, [_member("ev_above")]),       # above floor, LOW weight
        _basket("c_missing", 0.20, [_member("ev_missing")]),   # missing rel, mid weight
        _basket("c_below", 0.99, [_member("ev_below_hi_w")]),  # below floor, HIGH weight
    ]
    out = select_unbound_supports_by_weight(
        evidence_pool=pool,
        credibility_analysis=_analysis(baskets),
        contract_plans=[_Plan()],
    )
    # All three kept. The below-floor row sorts LAST despite its HIGH weight — proving
    # the floor demotes ORDER, never drops, and out-ranks weight for the below bucket.
    assert out == ["ev_above", "ev_missing", "ev_below_hi_w"]


# ── (b) masking reason: an all-below-floor pool is NOT an empty exit, and the empty ──
#        reason never claims a floor-exclusion that no longer happens. ──────────────


def test_reason_ok_when_below_floor_members_present(monkeypatch):
    """A pool where every member is below floor now yields reason='ok' with a full
    list (kept-all), NOT an 'all below floor' empty exit. The pre-fix code returned
    an empty list with the masking reason."""
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    pool = {f"ev{i}": {"evidence_id": f"ev{i}", "selection_relevance": 0.05} for i in range(1, 4)}
    baskets = [_basket("c1", 0.9, [_member(f"ev{i}") for i in range(1, 4)])]
    diag = diagnose_unbound_supports_selection(
        evidence_pool=pool,
        credibility_analysis=_analysis(baskets),
        contract_plans=[_Plan()],
    )
    assert diag.ev_ids  # non-empty -> the floor did not empty it
    assert diag.reason == "ok"


def test_empty_reason_is_true_cause_not_below_floor():
    """When the selection is genuinely empty, the reason reports the TRUE cause
    (no SUPPORTS member here) — the retired below-floor token is never used."""
    diag = diagnose_unbound_supports_selection(
        evidence_pool={},
        credibility_analysis=_analysis([_basket("c1", 0.9, [])]),  # basket with no members
        contract_plans=[_Plan()],
    )
    assert diag.ev_ids == []
    assert diag.reason == "no_supports_members"
    assert diag.reason != "all_candidates_below_relevance_floor"


# ── (c) B16: per-subquery monotonic-up relevance normalization ──────────────────────


# A long 3-part research question (the drb_76 denominator pathology in miniature):
# many distinct content tokens, so a row matching only one niche facet scores far
# below the 0.30 floor against the whole paragraph.
_LONG_QUESTION = (
    "Considering the predominant dietary choices that shape and influence the "
    "delicate equilibrium of the intestinal environment, what mechanisms might "
    "mitigate, retard, or otherwise modulate the downstream physiological "
    "consequences across multiple distinct organ systems and metabolic pathways?"
)
_FACET = "gut microbiota dysbiosis colorectal cancer tumorigenesis"
_TARGET_ROW = {
    "statement": (
        "Gut microbiota dysbiosis promotes colorectal cancer tumorigenesis "
        "through pathogenic bacteria and toxic metabolites."
    ),
    "direct_quote": "dysbiosis drives colorectal tumorigenesis",
}
_FLOOR = 0.30


def test_whole_question_denominator_buries_facet_row():
    """Precondition (the B16 bug): scored against the WHOLE long question, the niche
    on-topic row is UNDER the floor — today's denominator over-tightens."""
    q_toks = _content_tokens(_LONG_QUESTION)
    base = _row_relevance(_TARGET_ROW, q_toks, set())
    assert base < _FLOOR, f"fixture stale: base score {base} not below floor"


def test_subquery_facet_is_monotonic_up_and_clears_floor():
    """B16 fix: the per-subquery normalization is MONOTONIC-UP — max(whole_question,
    best_facet) — so the niche row's score RISES above the floor and is NEVER lower
    than the whole-question base. The floor only ever OPENS, never tightens."""
    q_toks = _content_tokens(_LONG_QUESTION)
    facet_sets = [_content_tokens(_FACET)]
    base = _row_relevance(_TARGET_ROW, q_toks, set())
    facet = _row_relevance_facet(_TARGET_ROW, q_toks, set(), facet_sets)
    # Monotonic-up: facet score never below the base.
    assert facet >= base
    # And it lifts the niche row above the floor (the throttle OPENS).
    assert facet >= _FLOOR


def test_subquery_floor_active_under_redesign_default(monkeypatch):
    """B16: under the credibility-redesign DEFAULT (PG_SWEEP_CREDIBILITY_REDESIGN
    unset/on) the per-subquery facet floor activates WITHOUT setting
    PG_SELECT_SUBQUERY_FLOOR — so the live keep-all path uses the monotonic-up
    denominator. An explicit OFF still forces the legacy whole-question denominator."""
    # Scrub the explicit flag; ensure the redesign default is ON.
    monkeypatch.delenv("PG_SELECT_SUBQUERY_FLOOR", raising=False)
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)  # defaults to "on"
    monkeypatch.delenv("PG_RELEVANCE_SCORER", raising=False)            # semantic OFF
    assert _subquery_floor_enabled() is True
    # The facet sets are then non-empty for a real sub-query (the lift can fire).
    assert _subquery_token_sets([_FACET]) == [_content_tokens(_FACET)]

    # Explicit OFF wins (audit/reversal) -> legacy whole-question denominator.
    monkeypatch.setenv("PG_SELECT_SUBQUERY_FLOOR", "0")
    assert _subquery_floor_enabled() is False
    assert _subquery_token_sets([_FACET]) == []

    # Explicit redesign OFF + flag unset + semantic OFF -> the bare default is OFF.
    monkeypatch.delenv("PG_SELECT_SUBQUERY_FLOOR", raising=False)
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    assert _subquery_floor_enabled() is False
