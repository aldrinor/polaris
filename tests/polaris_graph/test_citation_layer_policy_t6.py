"""I-deepfix-001 Wave-3 T6 — fail-loud behavioral tests for the two-layer citation RENDER policy.

These tests prove the EFFECT on a REAL verified basket built from the production ``ClaimBasket`` /
``BasketMember`` dataclasses (no mocks): the policy TYPES every distinct-origin SUPPORTS member into
the inline body layer (Layer 1) or the per-claim corroboration line (Layer 2), keeps ALL of them
cited (DNA CONSOLIDATE), drops nothing, never double-cites a same-origin duplicate, and never cites
an UNSUPPORTED member (faithfulness untouched). The body/appendix/demote boundary is asserted as the
single source of truth T5 + F1 consume.

RED->GREEN: with the two-layer policy ON, a 5-distinct-origin basket renders all 5 sources cited
(thoroughness 5/5); with the kill-switch OFF it collapses to the legacy single-``[N]`` (1/5). The
multi-citation assertion FAILS under the legacy path, so it is a genuine behavioral proof, not a
flag-check tautology."""
from __future__ import annotations

import pytest

from src.polaris_graph.synthesis.credibility_pass import BasketMember, ClaimBasket
from src.polaris_graph.generator.citation_layer_policy import (
    RenderDestination,
    classify_render_block,
    is_audit_appendix_block,
    split_basket_citation_layers,
)

_TWO_LAYER_ENV = "PG_CITATION_TWO_LAYER_POLICY"
_LAYER1_MAX_ENV = "PG_CITATION_LAYER1_MAX"
_APPENDIX_KINDS_ENV = "PG_CITATION_APPENDIX_KINDS"


def _member(evidence_id: str, origin: str, weight: float, verdict: str = "SUPPORTS") -> BasketMember:
    """A real ``BasketMember`` with an isolated span verdict — the exact object the render reads."""
    return BasketMember(
        evidence_id=evidence_id,
        source_url=f"https://example.org/{evidence_id}",
        source_tier="T2",
        origin_cluster_id=origin,
        credibility_weight=weight,
        authority_score=weight,
        span=(0, 20),
        direct_quote=f"{evidence_id} verified span text about the claim.",
        span_verdict=verdict,
    )


def _basket(members: list[BasketMember]) -> ClaimBasket:
    """A real multi-source ``ClaimBasket`` carrying the members (keep-all: none dropped)."""
    return ClaimBasket(
        claim_cluster_id="cc-1",
        claim_text="AI adoption rose sharply among knowledge workers.",
        subject="AI adoption",
        predicate="rose sharply",
        supporting_members=members,
        refuter_cluster_ids=(),
        weight_mass=1.0,
        total_clustered_origin_count=len(members),
        verified_support_origin_count=len(members),
        basket_verdict="full",
    )


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Default: policy ON, layer1_max=1 — the shipped production defaults."""
    monkeypatch.delenv(_TWO_LAYER_ENV, raising=False)
    monkeypatch.delenv(_LAYER1_MAX_ENV, raising=False)
    monkeypatch.delenv(_APPENDIX_KINDS_ENV, raising=False)
    yield


# ── the two typed citation layers ────────────────────────────────────────────────────────────────


def test_multi_origin_basket_cites_every_distinct_origin_keep_all():
    """The headline DNA effect: a 5-distinct-origin SUPPORTS basket cites ALL 5 (thoroughness 5/5),
    split as 1 inline (Layer 1) + 4 corroboration (Layer 2). Nothing dropped."""
    members = [
        _member("e1", "o1", 0.90),
        _member("e2", "o2", 0.80),
        _member("e3", "o3", 0.70),
        _member("e4", "o4", 0.60),
        _member("e5", "o5", 0.50),
    ]
    layers = split_basket_citation_layers(_basket(members))

    # Layer 1 is the single top-weight load-bearing representative (natural single-[N]).
    assert layers.layer1_ev_ids == ["e1"], "Layer 1 must be the single top-weight representative"
    # Layer 2 keeps every OTHER distinct-origin corroborator (keep-all, DNA CONSOLIDATE).
    assert set(layers.layer2_ev_ids) == {"e2", "e3", "e4", "e5"}
    # The FULL cited set = all 5 distinct origins. This is the RED->GREEN behavioral proof: the legacy
    # single-[N] path would cite exactly ONE. Nothing dropped.
    assert set(layers.cited_ev_ids) == {"e1", "e2", "e3", "e4", "e5"}
    assert len(layers.cited_ev_ids) == 5


def test_layers_partition_the_distinct_origin_support_set():
    """HARD INVARIANT: Layer1 and Layer2 PARTITION the distinct-origin SUPPORTS set (union == whole,
    intersection == empty) — the policy never drops, never double-counts."""
    members = [_member(f"e{i}", f"o{i}", 1.0 - i * 0.1) for i in range(4)]
    layers = split_basket_citation_layers(_basket(members))

    l1 = set(layers.layer1_ev_ids)
    l2 = set(layers.layer2_ev_ids)
    assert l1 & l2 == set(), "Layer 1 and Layer 2 must not overlap (no source cited twice)"
    assert l1 | l2 == {"e0", "e1", "e2", "e3"}, "union must equal the full distinct-origin SUPPORTS set"


def test_same_origin_duplicate_never_double_cited():
    """A same-origin duplicate member NEVER renders as a second citation (Codex gate P1)."""
    members = [
        _member("e1", "o1", 0.90),
        _member("e2", "o2", 0.80),
        _member("e1_dup", "o1", 0.85),  # SAME origin as e1 — a duplicate, not a distinct corroborator
    ]
    layers = split_basket_citation_layers(_basket(members))

    cited = layers.cited_ev_ids
    # Exactly the two DISTINCT origins are cited; the same-origin duplicate is collapsed out.
    assert set(cited) == {"e1", "e2"}
    assert "e1_dup" not in cited, "same-origin duplicate must not render as a corroboration citation"


def test_unsupported_member_never_cited_faithfulness_untouched():
    """FAITHFULNESS: an UNSUPPORTED member is NEVER promoted into a citation — only genuinely-
    supporting sources are cited (keeps DeepTRACE #7 accuracy high)."""
    members = [
        _member("e1", "o1", 0.90, verdict="SUPPORTS"),
        _member("e2", "o2", 0.80, verdict="SUPPORTS"),
        _member("bad", "o3", 0.95, verdict="UNSUPPORTED"),  # high weight but NOT verified support
    ]
    layers = split_basket_citation_layers(_basket(members))

    assert "bad" not in layers.cited_ev_ids, "an UNSUPPORTED member must never be cited"
    assert set(layers.cited_ev_ids) == {"e1", "e2"}


def test_load_bearing_ev_id_becomes_layer1():
    """When the composer supplies the ev_id it actually grounded the clause on, THAT source leads
    Layer 1 (not merely the top-weight one); the rest keep-all in Layer 2."""
    members = [
        _member("e1", "o1", 0.90),
        _member("e2", "o2", 0.80),
        _member("e3", "o3", 0.70),
    ]
    # e2 grounded the body clause even though e1 has higher weight.
    layers = split_basket_citation_layers(_basket(members), load_bearing_ev_ids=["e2"])

    assert layers.layer1_ev_ids == ["e2"]
    assert set(layers.layer2_ev_ids) == {"e1", "e3"}
    assert set(layers.cited_ev_ids) == {"e1", "e2", "e3"}  # still keep-all


def test_licensed_cross_source_two_inline_citations(monkeypatch):
    """D2: a licensed cross-source analytical sentence carries up to 2 inline Layer-1 citations
    (``PG_CITATION_LAYER1_MAX=2``); everything else keeps-all in Layer 2."""
    monkeypatch.setenv(_LAYER1_MAX_ENV, "2")
    members = [
        _member("e1", "o1", 0.90),
        _member("e2", "o2", 0.80),
        _member("e3", "o3", 0.70),
        _member("e4", "o4", 0.60),
    ]
    layers = split_basket_citation_layers(_basket(members), load_bearing_ev_ids=["e1", "e2"])

    assert set(layers.layer1_ev_ids) == {"e1", "e2"}
    assert len(layers.layer1_ev_ids) == 2
    assert set(layers.layer2_ev_ids) == {"e3", "e4"}
    assert set(layers.cited_ev_ids) == {"e1", "e2", "e3", "e4"}  # partition total, nothing dropped


def test_overflow_load_bearing_falls_to_layer2_not_dropped(monkeypatch):
    """If more load-bearing ev_ids are supplied than the Layer-1 cap allows, the overflow does NOT
    vanish — it renders in Layer 2 (still cited). The partition invariant always holds."""
    monkeypatch.setenv(_LAYER1_MAX_ENV, "1")
    members = [
        _member("e1", "o1", 0.90),
        _member("e2", "o2", 0.80),
        _member("e3", "o3", 0.70),
    ]
    layers = split_basket_citation_layers(_basket(members), load_bearing_ev_ids=["e1", "e2"])

    assert len(layers.layer1_ev_ids) == 1
    assert "e2" in layers.layer2_ev_ids, "overflow load-bearing member must fall to Layer 2, not drop"
    assert set(layers.cited_ev_ids) == {"e1", "e2", "e3"}


def test_kill_switch_off_collapses_to_single_citation(monkeypatch):
    """RED path: with the policy OFF the render is the LEGACY single-[N] (1 inline, empty corroboration).
    This is the behavioral contrast that makes the multi-citation assertions above meaningful."""
    monkeypatch.setenv(_TWO_LAYER_ENV, "0")
    members = [_member(f"e{i}", f"o{i}", 1.0 - i * 0.1) for i in range(5)]
    layers = split_basket_citation_layers(_basket(members))

    assert layers.enabled is False
    assert layers.layer1_ev_ids == ["e0"]
    assert layers.layer2_ev_ids == [], "legacy path renders NO corroboration line"
    assert len(layers.cited_ev_ids) == 1  # 1/5 — the pre-fix thoroughness the T6 fix raises to 5/5


def test_single_source_basket_has_no_corroboration_line():
    """A genuine single-source basket cites exactly one source and has an empty Layer 2 (no invented
    corroboration)."""
    layers = split_basket_citation_layers(_basket([_member("e1", "o1", 0.9)]))
    assert layers.layer1_ev_ids == ["e1"]
    assert layers.layer2_ev_ids == []


def test_empty_basket_cites_nothing():
    """A basket with no SUPPORTS members cites nothing (never invents a citation)."""
    layers = split_basket_citation_layers(_basket([_member("bad", "o1", 0.9, verdict="UNSUPPORTED")]))
    assert layers.cited_ev_ids == []


# ── the supports_members overload (the production render path, dict members) ───────────────────────


def _dict_member(evidence_id, origin, weight):
    """A plain-dict SUPPORTS member — the exact shape ``_basket_corroboration_block`` iterates."""
    return {
        "evidence_id": evidence_id,
        "origin_cluster_id": origin,
        "credibility_weight": weight,
        "authority_score": weight,
        "source_url": f"https://example.org/{evidence_id}",
        "span_verdict": "SUPPORTS",
        "member_tier": "ENTAILMENT_VERIFIED",
    }


def test_supports_members_overload_types_dict_members_keep_all():
    """The named function's ``supports_members`` overload (the production render path) accepts DICT
    members, dedupes to one-per-origin (top weight kept), and keeps all distinct origins cited."""
    members = [
        _dict_member("e1", "o1", 0.90),
        _dict_member("e2", "o2", 0.80),
        _dict_member("e3", "o3", 0.70),
    ]
    layers = split_basket_citation_layers(supports_members=members)
    assert layers.layer1_ev_ids == ["e1"], "top-weight dict member leads Layer 1"
    assert set(layers.layer2_ev_ids) == {"e2", "e3"}
    assert set(layers.cited_ev_ids) == {"e1", "e2", "e3"}


def test_supports_members_overload_collapses_same_origin_mirror():
    """The render-path defect the T6 wiring fixes: two dict members sharing ONE origin (different
    evidence_ids) are collapsed to a single citation — the mirror is never double-cited."""
    members = [
        _dict_member("evA", "oc_same", 0.90),
        _dict_member("evA_mirror", "oc_same", 0.50),  # same origin, lower weight -> collapsed out
        _dict_member("evB", "oc_b", 0.70),
    ]
    layers = split_basket_citation_layers(supports_members=members)
    assert set(layers.cited_ev_ids) == {"evA", "evB"}, "same-origin mirror collapses; top weight kept"
    assert "evA_mirror" not in layers.cited_ev_ids


# ── the body / appendix / demote render boundary (single source of truth for T5 + F1) ──────────────


@pytest.mark.parametrize("kind", [
    "reliability_header",
    "corroborated_weighted_findings",
    "weight_basis",
    "count_reconciliation",
    "credibility_ledger",
    "source_corroboration_rollup",
    "disclosure",
    "bibliography_audit",
    "methods",
])
def test_audit_machinery_routes_to_appendix(kind):
    """T5: every audit/disclosure/weight MACHINERY block relocates to the typed appendix (kept +
    disclosed, out of the scored body)."""
    assert classify_render_block(kind) is RenderDestination.APPENDIX
    assert is_audit_appendix_block(kind) is True


@pytest.mark.parametrize("kind", [
    "section_prose",
    "key_findings",
    "abstract",
    "conclusion",
    "residual_coverage",
    "claim",
    "corroboration_line",
])
def test_relevant_claims_stay_in_body(kind):
    """F1: relevant on-topic verified claims — including residual-coverage sentences and the Layer-2
    corroboration line — stay in the DeepTRACE-scored body."""
    assert classify_render_block(kind) is RenderDestination.BODY
    assert is_audit_appendix_block(kind) is False


def test_off_topic_residual_routes_to_demote_disclose():
    """F3: a confirmed-off-topic residual basket routes to the demote-and-disclose tail (kept +
    disclosed, never in the scored body)."""
    assert classify_render_block("off_topic_residual") is RenderDestination.DEMOTE_DISCLOSE


def test_unknown_kind_fails_open_to_body():
    """An unrecognized block kind renders in the body (a real claim must never be silently hidden;
    only NAMED audit machinery is relocated)."""
    assert classify_render_block("some_new_block") is RenderDestination.BODY


def test_appendix_kinds_env_override_forces_appendix(monkeypatch):
    """LAW VI: ``PG_CITATION_APPENDIX_KINDS`` additively forces extra kinds into the appendix."""
    monkeypatch.setenv(_APPENDIX_KINDS_ENV, "experimental_sidebar, notes")
    assert classify_render_block("experimental_sidebar") is RenderDestination.APPENDIX
    assert classify_render_block("notes") is RenderDestination.APPENDIX
    # A normal body kind is unaffected.
    assert classify_render_block("section_prose") is RenderDestination.BODY
