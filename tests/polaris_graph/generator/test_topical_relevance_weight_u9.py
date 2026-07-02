"""I-deepfix-001 (U9) — TOPICAL question-overlap ORDERING weight.

THE BUG: on the weighted-enrichment cited-breadth surface the ONLY per-row relevance
signal is ``selection_relevance`` — a per-passage SEMANTIC score. A topically-foreign
but semantically-fluent source (a logistics/supply-chain article in an AI-labor
question; an elder-abuse source in a PD-DBS question) can carry a HIGH
``selection_relevance`` and, being the PRIMARY sort key, WRRF-fuse to the TOP of the
cited findings — an off-topic source LEADS the report.

THE FIX (§-1.3 WEIGHT, never FILTER): a second TOPICAL signal — lexical overlap of the
source text against the research-question topic terms — scales the relevance sort key.
An off-topic row (near-zero question overlap) is DEMOTED in the order (toward the
floor) so it no longer top-fuses; an on-topic row keeps its full relevance key.
NOTHING is dropped — the returned set is identical, only the ORDER changes.

Pure offline unit test over the REAL basket dataclasses. No network, no model, no GPU.
The faithfulness engine (strict_verify / NLI / 4-role D8 / provenance) is untouched —
this suite only proves the ORDERING weight and its conservation + kill-switch.
"""

from __future__ import annotations

from src.polaris_graph.generator.weighted_enrichment import (
    _question_topic_terms,
    _topical_factor,
    _topical_overlap,
    diagnose_unbound_supports_selection,
    topical_relevance_weight_enabled,
)
from src.polaris_graph.synthesis.credibility_pass import (
    BasketMember,
    ClaimBasket,
    CredibilityAnalysis,
)

_QUESTION = "What is the impact of artificial intelligence on the labor workforce?"

# ev_on = ON-topic but LOWER selection_relevance; ev_off = OFF-topic (logistics) but
# HIGHER selection_relevance. Without a topical weight the semantic score alone puts
# the off-topic source FIRST (the bug). Both are above the 0.30 relevance floor, so the
# is_below_floor bucket is identical for both — the ordering is decided purely by the
# relevance key, which is exactly where the topical factor applies.
_POOL = {
    "ev_on": {
        "evidence_id": "ev_on",
        "selection_relevance": 0.50,
        "title": "Artificial intelligence and automation reshape the labor workforce",
        "statement": "Artificial intelligence adoption changes employment across the workforce.",
    },
    "ev_off": {
        "evidence_id": "ev_off",
        "selection_relevance": 0.90,
        "title": "Global logistics supply chain shipping and freight operations",
        "statement": "Warehouse trucking and freight forwarding optimize container shipping.",
    },
}


def _member(evidence_id: str) -> BasketMember:
    return BasketMember(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_tier="T2",
        origin_cluster_id=f"oc_{evidence_id}",
        credibility_weight=0.8,  # >= promotion W (0.10) => both promoted, no disclosed-only routing
        authority_score=0.8,
        span=(0, 20),
        direct_quote="a verified span of source text",
        span_verdict="SUPPORTS",
    )


def _basket(cluster_id: str, weight_mass: float, evidence_id: str) -> ClaimBasket:
    return ClaimBasket(
        claim_cluster_id=cluster_id,
        claim_text="claim text",
        subject="subject",
        predicate="predicate",
        supporting_members=[_member(evidence_id)],
        refuter_cluster_ids=(),
        weight_mass=weight_mass,
        total_clustered_origin_count=1,
        verified_support_origin_count=1,
        basket_verdict="full",
    )


def _analysis() -> CredibilityAnalysis:
    return CredibilityAnalysis(
        credibility_by_evidence={},
        origin_by_evidence={},
        claims=[],
        edges=[],
        weight_mass=[],
        # ev_off is put in the HIGHER-weight basket too, so nothing but the topical
        # factor could flip it below the on-topic source.
        baskets=[_basket("c_off", 0.9, "ev_off"), _basket("c_on", 0.5, "ev_on")],
        cluster_id_by_evidence={},
    )


# ── the helpers compute a real, monotone topical factor ──────────────────────────────


def test_question_topic_terms_extracts_content_words():
    terms = _question_topic_terms(_QUESTION)
    assert {"artificial", "intelligence", "labor", "workforce"} <= terms
    # stopwords are stripped
    assert "the" not in terms and "what" not in terms
    # a blank question yields NO terms => downstream factor 1.0 (byte-identical)
    assert _question_topic_terms("") == frozenset()
    assert _question_topic_terms("   ") == frozenset()


def test_topical_overlap_and_factor_monotone():
    terms = _question_topic_terms(_QUESTION)
    on_ov = _topical_overlap(_POOL["ev_on"], terms)
    off_ov = _topical_overlap(_POOL["ev_off"], terms)
    assert on_ov > off_ov
    assert off_ov == 0.0  # logistics text shares no topic term with the question
    # factor maps overlap->[floor,1.0]: on-topic keeps most weight, off-topic sinks to floor
    assert _topical_factor(on_ov, 0.25) > _topical_factor(off_ov, 0.25)
    assert _topical_factor(0.0, 0.25) == 0.25
    assert _topical_factor(1.0, 0.25) == 1.0
    # no question terms => keep-neutral 1.0 (byte-identical ordering)
    assert _topical_overlap(_POOL["ev_on"], frozenset()) == 1.0


# ── the ordering: off-topic no longer top-fuses, but is KEPT (never dropped) ──────────


def test_offtopic_source_demoted_below_ontopic_with_topical_weight():
    """WITH the topical weight (default ON) + a real research question, the ON-topic
    source leads and the higher-semantic-score OFF-topic source is demoted — but KEPT."""
    sel = diagnose_unbound_supports_selection(
        evidence_pool=_POOL,
        credibility_analysis=_analysis(),
        contract_plans=[],
        research_question=_QUESTION,
    )
    assert sel.reason == "ok"
    # on-topic leads; off-topic demoted to LAST — not top-fused any more.
    assert sel.ev_ids == ["ev_on", "ev_off"]
    # KEEP-ALL: the off-topic source is still present (a demotion, never a drop).
    assert set(sel.ev_ids) == {"ev_on", "ev_off"}


def test_legacy_order_byte_identical_without_question():
    """No research question => empty topic terms => factor 1.0 for every row => the
    legacy semantic-relevance-first ordering is byte-identical (off-topic top-fuses)."""
    sel = diagnose_unbound_supports_selection(
        evidence_pool=_POOL,
        credibility_analysis=_analysis(),
        contract_plans=[],
    )
    # higher selection_relevance (ev_off=0.90) sorts first under the legacy key.
    assert sel.ev_ids == ["ev_off", "ev_on"]


def test_kill_switch_off_restores_legacy_order(monkeypatch):
    """PG_TOPICAL_RELEVANCE_WEIGHT=0 => factor 1.0 for every row => legacy order even
    when a research question IS supplied (a clean, auditable disable path)."""
    monkeypatch.setenv("PG_TOPICAL_RELEVANCE_WEIGHT", "0")
    assert topical_relevance_weight_enabled() is False
    sel = diagnose_unbound_supports_selection(
        evidence_pool=_POOL,
        credibility_analysis=_analysis(),
        contract_plans=[],
        research_question=_QUESTION,
    )
    assert sel.ev_ids == ["ev_off", "ev_on"]
