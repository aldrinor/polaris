"""I-arch-007 ITEM 2 (#1264) BREADTH — negative-control unit test for weighted_enrichment.

Design BREADTH_FIX_DESIGN.md §4 + the advisor's mandatory negative control: prove the §-1.3
WEIGHT-AND-CONSOLIDATE selection surfaces MORE distinct verified sources (breadth UP) while
relaxing NOTHING (faithfulness identical). "Breadth up" alone would pass even if a gate were
relaxed; the load-bearing assertions are the EXCLUSIONS:

  * only isolated-verified ``span_verdict == "SUPPORTS"`` members are offered (UNSUPPORTED never
    surfaces) — the basket-faithfulness guard;
  * a member already bound to a contract entity is excluded (no double-render of the 5);
  * a member absent from ``evidence_pool`` is excluded — it has no real row to attribute to, so
    surfacing it would be a FABRICATED citation;
  * relevance-to-question FIRST, then ``weight_mass`` ORDERS — the FULL surviving list is returned
    (no cap / target / top-N): breadth EMERGES, never forced;
  * a member whose source row is PRESENT-and-below ``PG_RELEVANCE_FLOOR`` is EXCLUDED (the operator
    #1264 relevance gate — no off-topic verified-but-peripheral findings) reusing the EXISTING floor;
  * a member whose source row carries NO usable relevance score FALLS BACK to keep (pool membership
    already implies the retrieval floor passed) — a missing score never SILENTLY excludes;
  * ``credibility_analysis is None`` (always-release degrade / flag OFF) => ``[]`` => the render is
    byte-identical to the pre-fix path;
  * the master flag defaults OFF.

Pure unit test over the REAL basket dataclasses; no network, no model spend. The downstream
strict_verify drop of a fabricated/numeric-mismatch DRAFT is the UNCHANGED ``_run_section`` gate
(covered by the existing strict_verify suite) — this module only proves the SELECTION offers no
unverifiable candidate.
"""

from __future__ import annotations

from types import SimpleNamespace

from src.polaris_graph.generator.multi_section_generator import SectionPlan
from src.polaris_graph.generator.weighted_enrichment import (
    breadth_enrichment_enabled,
    build_weighted_enrichment_plan,
    contract_bound_evidence_ids,
    select_unbound_supports_by_weight,
)
from src.polaris_graph.synthesis.credibility_pass import (
    BasketMember,
    ClaimBasket,
    CredibilityAnalysis,
)

# A fixed in-memory evidence_pool: ev1..ev8 resolve; anything else does NOT.
_POOL = {f"ev{i}": {"evidence_id": f"ev{i}"} for i in range(1, 9)}


def _member(evidence_id: str, span_verdict: str) -> BasketMember:
    return BasketMember(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_tier="T2",
        origin_cluster_id=f"oc_{evidence_id}",
        credibility_weight=0.8,
        authority_score=0.8,
        span=(0, 20),
        direct_quote="a verified span of source text",
        span_verdict=span_verdict,
    )


def _basket(cluster_id: str, weight_mass: float, members: list[BasketMember]) -> ClaimBasket:
    n_supports = sum(1 for m in members if m.span_verdict == "SUPPORTS")
    return ClaimBasket(
        claim_cluster_id=cluster_id,
        claim_text="claim text",
        subject="subject",
        predicate="predicate",
        supporting_members=members,
        refuter_cluster_ids=(),
        weight_mass=weight_mass,
        total_clustered_origin_count=len(members),
        verified_support_origin_count=n_supports,
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


def _contract_plan(ev_ids, slot_entity_id_groups):
    """Duck-typed to what contract_bound_evidence_ids reads (.ev_ids + .slots[].entity_ids)."""
    return SimpleNamespace(
        title="Efficacy",
        ev_ids=list(ev_ids),
        slots=tuple(SimpleNamespace(entity_ids=list(g)) for g in slot_entity_id_groups),
    )


def test_supports_surface_unsupported_excluded():
    """Breadth UP for SUPPORTS; the UNSUPPORTED member NEVER surfaces (basket-faithfulness)."""
    baskets = [
        _basket("c1", 0.9, [_member("ev1", "SUPPORTS"), _member("ev3", "UNSUPPORTED")]),
        _basket("c2", 0.5, [_member("ev2", "SUPPORTS")]),
    ]
    out = select_unbound_supports_by_weight(
        evidence_pool=_POOL,
        credibility_analysis=_analysis(baskets),
        contract_plans=[_contract_plan([], [])],
    )
    assert out == ["ev1", "ev2"]  # weight desc; ev3 (UNSUPPORTED) excluded


def test_contract_bound_member_excluded():
    """A member already inside the contract render universe is NOT re-surfaced."""
    baskets = [_basket("c1", 0.9, [_member("ev1", "SUPPORTS"), _member("ev2", "SUPPORTS")])]
    plan = _contract_plan(ev_ids=["ev1"], slot_entity_id_groups=[["ev2"]])  # both bound
    assert contract_bound_evidence_ids([plan]) == {"ev1", "ev2"}
    out = select_unbound_supports_by_weight(
        evidence_pool=_POOL,
        credibility_analysis=_analysis(baskets),
        contract_plans=[plan],
    )
    assert out == []  # nothing UNBOUND remains


def test_pool_absent_member_excluded_no_fabricated_citation():
    """A SUPPORTS member with no resolvable evidence_pool row is excluded (no fabricated cite)."""
    baskets = [_basket("c1", 0.9, [_member("ev1", "SUPPORTS"), _member("PHANTOM", "SUPPORTS")])]
    out = select_unbound_supports_by_weight(
        evidence_pool=_POOL,
        credibility_analysis=_analysis(baskets),
        contract_plans=[_contract_plan([], [])],
    )
    assert out == ["ev1"]  # PHANTOM absent from pool -> excluded


def test_full_list_no_cap_ordered_by_weight():
    """The FULL ordered list is returned — no cap / target / top-N; weight_mass orders only."""
    baskets = [
        _basket("c1", 0.2, [_member("ev1", "SUPPORTS")]),
        _basket("c2", 0.9, [_member("ev2", "SUPPORTS")]),
        _basket("c3", 0.5, [_member("ev3", "SUPPORTS"), _member("ev4", "SUPPORTS")]),
    ]
    out = select_unbound_supports_by_weight(
        evidence_pool=_POOL,
        credibility_analysis=_analysis(baskets),
        contract_plans=[_contract_plan([], [])],
    )
    # weight desc (c2=0.9, c3=0.5, c1=0.2); within c3 deterministic eid tiebreak; ALL four kept.
    assert out == ["ev2", "ev3", "ev4", "ev1"]


def test_none_analysis_is_byte_identical_empty():
    """Degrade path (credibility_analysis is None) => [] => byte-identical legacy render."""
    assert select_unbound_supports_by_weight(
        evidence_pool=_POOL, credibility_analysis=None, contract_plans=[_contract_plan([], [])],
    ) == []


def test_empty_baskets_returns_empty():
    assert select_unbound_supports_by_weight(
        evidence_pool=_POOL, credibility_analysis=_analysis([]), contract_plans=[_contract_plan([], [])],
    ) == []


def test_build_plan_none_on_empty_legacy_title_on_nonempty():
    """None on empty ev_ids (byte-identical); a NON-contract title routes to legacy field-agnostic."""
    assert build_weighted_enrichment_plan([], section_plan_cls=SectionPlan) is None
    plan = build_weighted_enrichment_plan(["ev1", "ev2"], section_plan_cls=SectionPlan)
    assert plan is not None
    assert plan.ev_ids == ["ev1", "ev2"]
    assert plan.title == "Corroborated Weighted Findings"  # non-contract -> is_contract_section False


def test_master_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("PG_BREADTH_ENRICHMENT_ENABLED", raising=False)
    assert breadth_enrichment_enabled() is False
    monkeypatch.setenv("PG_BREADTH_ENRICHMENT_ENABLED", "1")
    assert breadth_enrichment_enabled() is True
    monkeypatch.setenv("PG_BREADTH_ENRICHMENT_ENABLED", "0")
    assert breadth_enrichment_enabled() is False


# ── I-arch-007 #1264 relevance gate (operator: no off-topic verified-but-peripheral findings) ──
# Relevance lives on the evidence_pool ROW (`selection_relevance`, the score the retrieval gate
# stamps at evidence_selector.py:2128), NOT on the BasketMember. These tests build a relevance-
# bearing pool locally (never mutating the shared `_POOL`) and pin PG_RELEVANCE_FLOOR for
# determinism. The floor + its (0.0, 1.0] validation come from the EXISTING `parse_relevance_floor`.


def _pool_with_relevance(scores: dict[str, float]) -> dict[str, dict]:
    """A fresh evidence_pool whose rows carry `selection_relevance` (the topicality sidecar)."""
    return {
        eid: {"evidence_id": eid, "selection_relevance": score}
        for eid, score in scores.items()
    }


def test_below_floor_source_excluded(monkeypatch):
    """A SUPPORTS member whose source row scores BELOW PG_RELEVANCE_FLOOR is NOT surfaced."""
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    pool = _pool_with_relevance({"ev1": 0.80, "ev2": 0.05})  # ev2 below the 0.30 floor
    baskets = [_basket("c1", 0.9, [_member("ev1", "SUPPORTS"), _member("ev2", "SUPPORTS")])]
    out = select_unbound_supports_by_weight(
        evidence_pool=pool,
        credibility_analysis=_analysis(baskets),
        contract_plans=[_contract_plan([], [])],
    )
    assert out == ["ev1"]  # ev2 is on-pool but genuinely off-topic -> gated out


def test_at_floor_kept_inclusive(monkeypatch):
    """The gate mirrors retrieval's `>=`: a row exactly AT the floor is KEPT, not dropped."""
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    pool = _pool_with_relevance({"ev1": 0.30})  # exactly at the floor
    baskets = [_basket("c1", 0.9, [_member("ev1", "SUPPORTS")])]
    out = select_unbound_supports_by_weight(
        evidence_pool=pool,
        credibility_analysis=_analysis(baskets),
        contract_plans=[_contract_plan([], [])],
    )
    assert out == ["ev1"]


def test_relevance_outranks_weight_in_ordering(monkeypatch):
    """Ordering is relevance FIRST: a high-relevance/low-weight row sorts before a
    low-relevance/high-weight row (proves relevance is primary, not just a tiebreak on weight)."""
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    pool = _pool_with_relevance({"ev1": 0.90, "ev2": 0.40})
    baskets = [
        _basket("c_low_weight", 0.10, [_member("ev1", "SUPPORTS")]),   # high relevance, LOW weight
        _basket("c_high_weight", 0.95, [_member("ev2", "SUPPORTS")]),  # low relevance, HIGH weight
    ]
    out = select_unbound_supports_by_weight(
        evidence_pool=pool,
        credibility_analysis=_analysis(baskets),
        contract_plans=[_contract_plan([], [])],
    )
    assert out == ["ev1", "ev2"]  # relevance desc beats weight desc


def test_missing_relevance_score_kept_fallback(monkeypatch):
    """A SUPPORTS member whose source row carries NO usable relevance score FALLS BACK to keep
    (pool membership implies the retrieval floor already passed) — never a silent exclusion."""
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    # ev1 has a real low-but-passing score; ev2 has NO `selection_relevance`; ev3 carries garbage.
    pool = {
        "ev1": {"evidence_id": "ev1", "selection_relevance": 0.50},
        "ev2": {"evidence_id": "ev2"},  # no relevance sidecar -> fallback keep
        "ev3": {"evidence_id": "ev3", "selection_relevance": "not-a-float"},  # unparseable -> keep
    }
    baskets = [
        _basket("c1", 0.7, [_member("ev1", "SUPPORTS")]),
        _basket("c2", 0.9, [_member("ev2", "SUPPORTS")]),
        _basket("c3", 0.5, [_member("ev3", "SUPPORTS")]),
    ]
    out = select_unbound_supports_by_weight(
        evidence_pool=pool,
        credibility_analysis=_analysis(baskets),
        contract_plans=[_contract_plan([], [])],
    )
    # All three kept. ev1 (relevance 0.50) sorts first; ev2/ev3 (sentinel 0.0 relevance) follow,
    # ordered by weight desc: ev2 (0.9) before ev3 (0.5).
    assert out == ["ev1", "ev2", "ev3"]


def test_missing_relevance_pool_reproduces_weight_desc_order(monkeypatch):
    """When NO row carries a relevance score (the shared _POOL shape), the result is today's pure
    weight-desc order — the constant sentinel ties on relevance, leaving weight in control."""
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    baskets = [
        _basket("c1", 0.2, [_member("ev1", "SUPPORTS")]),
        _basket("c2", 0.9, [_member("ev2", "SUPPORTS")]),
        _basket("c3", 0.5, [_member("ev3", "SUPPORTS"), _member("ev4", "SUPPORTS")]),
    ]
    out = select_unbound_supports_by_weight(
        evidence_pool=_POOL,  # no `selection_relevance` on any row
        credibility_analysis=_analysis(baskets),
        contract_plans=[_contract_plan([], [])],
    )
    assert out == ["ev2", "ev3", "ev4", "ev1"]  # identical to test_full_list_no_cap_ordered_by_weight
