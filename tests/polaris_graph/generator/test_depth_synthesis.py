"""I-wire-013 (#1327) — behavioral tests for the grounded DEPTH cross-source SYNTHESIS pass.

Proves the two faithfulness contracts of ``depth_synthesis.synthesize_cross_source_findings`` against
the REAL ``strict_verify`` engine (entailment leg disabled so the test is deterministic + offline —
the deterministic span + numeric-match + >=2 content-word legs are what the synthesis re-grounding
relies on):

1. GROUNDED: a synthesized cross-source sentence whose number traces to a cited span is KEPT, cites
   the report's existing ``[N]``, and surfaces through ``build_depth_layer``.
2. BACKSTOP: a synthesized sentence whose number is NOT in its cited span is DROPPED by strict_verify
   (drop-not-fallback) — proving zero new fabrication can ship even though the generator wrote it.

Plus the analytical_depth ATX regex broadening (key_findings counted on an inline ``## Key Findings``).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator import key_findings as kf
from src.polaris_graph.generator.analytical_depth import (
    evaluate_analytical_depth,
    split_report_into_sections,
)
from src.polaris_graph.generator.depth_synthesis import (
    bib_num_by_evidence_id,
    synthesize_cross_source_findings,
)
from src.polaris_graph.generator.provenance_generator import strict_verify
from src.polaris_graph.synthesis.credibility_pass import (
    MEMBER_TIER_ENTAILMENT_VERIFIED,
    BasketMember,
    ClaimBasket,
)

# Two corroborating sources carrying the SAME finding (mortality fell 25%), known spans.
_QUOTE_A = "Mortality fell by 25% across the pooled multinational cohorts."
_QUOTE_B = "A 25% reduction in mortality was observed across the pooled cohorts."


def _fixture_basket() -> tuple[ClaimBasket, dict]:
    """One high-corroboration basket (2 distinct-origin isolated-SUPPORTS members) + its pool."""
    evidence_pool = {
        "ev_a": {"source_url": "https://nejm.org/a", "tier": "T1", "direct_quote": _QUOTE_A},
        "ev_b": {"source_url": "https://lancet.com/b", "tier": "T1", "direct_quote": _QUOTE_B},
    }
    members = [
        BasketMember("ev_a", "https://nejm.org/a", "T1", "o1", 0.95, 0.9,
                     (0, len(_QUOTE_A)), _QUOTE_A, "SUPPORTS", MEMBER_TIER_ENTAILMENT_VERIFIED),
        BasketMember("ev_b", "https://lancet.com/b", "T1", "o2", 0.90, 0.85,
                     (0, len(_QUOTE_B)), _QUOTE_B, "SUPPORTS", MEMBER_TIER_ENTAILMENT_VERIFIED),
    ]
    basket = ClaimBasket(
        "c1", "Mortality fell by 25%", "mortality", "fell by 25%",
        members, (), 1.85, 2, 2, "full",
    )
    return basket, evidence_pool


# Report bibliography numbering the synthesized finding must re-use (NOT a fresh renumber).
_BIB_MAP = {"ev_a": 3, "ev_b": 4}

# A GROUNDED CROSS-SOURCE synthesized sentence: 25% is present in BOTH ev_a's and ev_b's spans, and the
# sentence cites BOTH canonical tokens. iter-2 (Codex P1): a cross-source finding must carry >=2 DISTINCT
# surviving sources, so the grounded fixture now cites two — each resolves to its own report [N] ([3]/[4]).
_GROUNDED = (
    f"Across two independent cohorts, mortality fell by 25% in the pooled analysis "
    f"[#ev:ev_a:0-{len(_QUOTE_A)}] [#ev:ev_b:0-{len(_QUOTE_B)}]."
)
# A SINGLE-SOURCE synthesized sentence: grounds cleanly (25% is in ev_a's span) but carries only ONE
# distinct surviving token -> the >=2-distinct-surviving gate DROPS it (not a genuine cross-source finding).
_SINGLE_SOURCE = (
    f"Mortality fell by 25% in the pooled analysis [#ev:ev_a:0-{len(_QUOTE_A)}]."
)
# An UNGROUNDED synthesized sentence: 99% is NOT in ev_b's span -> strict_verify must DROP it.
_UNGROUNDED = (
    f"The therapy eliminated disease in 99% of pooled participants [#ev:ev_b:0-{len(_QUOTE_B)}]."
)


@pytest.fixture(autouse=True)
def _deterministic_verify(monkeypatch):
    # Disable the entailment LLM leg so strict_verify is fully deterministic/offline; the span +
    # numeric-match + content-overlap legs (which the synthesis re-grounding relies on) still run.
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")


def test_grounded_cross_source_finding_emitted_and_cited(monkeypatch):
    # iter-3c FIXTURE #1: a basket with 2 DISTINCT surviving origins -> a CROSS_SOURCE finding emitted,
    # and the rendered depth layer scores key_findings > 0 on the REAL analytical_depth metric path.
    basket, evidence_pool = _fixture_basket()
    findings = synthesize_cross_source_findings(
        [basket], evidence_pool,
        synthesizer=lambda _b, _p: _GROUNDED,
        verify_fn=strict_verify,
        bib_num_by_evidence_id=_BIB_MAP,
    )
    assert len(findings) == 1, findings
    finding = findings[0]
    assert finding["tier"] == "cross_source", finding
    assert finding["label"] == "", finding  # cross-source carries NO single-source label
    sentence = finding["sentence"]
    # the synthesized [#ev:...] tokens resolved to the report's EXISTING citation numbers, not a renumber
    assert "[3]" in sentence
    # a cross-source finding carries >=2 DISTINCT surviving resolved sources -> [4] too
    assert "[4]" in sentence
    assert "[#ev:" not in sentence
    # every number in the finding traces to the cited span (25 is in BOTH quotes)
    assert "25%" in sentence
    assert "25" in _QUOTE_A and "25" in _QUOTE_B
    # key_findings > 0 via the REAL metric path (the "## Analytical synthesis" title trips the count)
    monkeypatch.setenv(kf._DEPTH_LAYER_ENV, "1")
    rendered = kf.build_depth_layer([], synthesized_findings=findings)
    assert "### Cross-source synthesis" in rendered
    depth = evaluate_analytical_depth(split_report_into_sections(rendered))
    assert depth["key_findings"] > 0, rendered


def test_ungrounded_synthesized_sentence_is_dropped_by_strict_verify():
    # The generator wrote BOTH a grounded and an ungrounded sentence; the backstop must keep the
    # grounded one and DROP the ungrounded one (its 99% is absent from the cited span).
    basket, evidence_pool = _fixture_basket()
    findings = synthesize_cross_source_findings(
        [basket], evidence_pool,
        synthesizer=lambda _b, _p: f"{_GROUNDED}\n{_UNGROUNDED}",
        verify_fn=strict_verify,
        bib_num_by_evidence_id=_BIB_MAP,
    )
    blob = "\n".join(f["sentence"] for f in findings)
    assert "99%" not in blob and "99" not in blob, f"fabricated 99% sentence survived: {findings!r}"
    # the grounded finding still ships (drop is per-sentence, not whole-basket)
    assert any("25%" in f["sentence"] for f in findings), findings


def test_single_origin_basket_emits_single_source_labeled_finding(monkeypatch):
    # iter-3c FIXTURE #2 (the FLIP of the iter-2 per-sentence drop): a >=2-member basket whose synthesis
    # re-grounds to ONE surviving origin is NO LONGER dropped — it is SURFACED as a single_source finding
    # with an explicit "(single source)" label (§-1.3 "don't drop, label weak weak").
    basket, evidence_pool = _fixture_basket()
    findings = synthesize_cross_source_findings(
        [basket], evidence_pool,
        synthesizer=lambda _b, _p: _SINGLE_SOURCE,
        verify_fn=strict_verify,
        bib_num_by_evidence_id=_BIB_MAP,
    )
    assert len(findings) == 1, findings
    finding = findings[0]
    assert finding["tier"] == "single_source", finding
    assert finding["label"] == "(single source)", finding
    assert "25%" in finding["sentence"] and "[3]" in finding["sentence"]
    assert "[#ev:" not in finding["sentence"]
    # it renders under the dedicated Single-source subhead with the (single source) label on the bullet
    monkeypatch.setenv(kf._DEPTH_LAYER_ENV, "1")
    rendered = kf.build_depth_layer([], synthesized_findings=findings)
    assert "### Single-source findings" in rendered
    assert "(single source)" in rendered


def test_ungrounded_only_basket_emits_nothing(monkeypatch):
    # iter-3c FIXTURE #3: a synthesized sentence with NO grounding span (99% absent from the cited span)
    # is DROPPED by the UNCHANGED strict_verify -> the basket emits NOTHING (drop-not-fallback). No
    # fabrication can ship even though the generator wrote it, and no empty subhead renders.
    basket, evidence_pool = _fixture_basket()
    findings = synthesize_cross_source_findings(
        [basket], evidence_pool,
        synthesizer=lambda _b, _p: _UNGROUNDED,
        verify_fn=strict_verify,
        bib_num_by_evidence_id=_BIB_MAP,
    )
    assert findings == [], findings
    monkeypatch.setenv(kf._DEPTH_LAYER_ENV, "1")
    rendered = kf.build_depth_layer([], synthesized_findings=findings)
    assert "Cross-source synthesis" not in rendered
    assert "Single-source findings" not in rendered


def test_partial_unresolved_token_drops_the_sentence():
    # iter-2 (Codex P1) test (c): two surviving tokens but only ONE resolves to a report [N]; the
    # unresolved (raw/unmatched) co-token would ship a dangling citation -> the WHOLE sentence DROPS.
    basket, evidence_pool = _fixture_basket()
    findings = synthesize_cross_source_findings(
        [basket], evidence_pool,
        synthesizer=lambda _b, _p: _GROUNDED,        # cites ev_a + ev_b
        verify_fn=strict_verify,
        bib_num_by_evidence_id={"ev_a": 3},          # ev_b unmapped -> unresolved -> drop whole sentence
    )
    assert findings == [], findings


def test_depth_model_resolves_via_central_lock(monkeypatch):
    # iter-2 (Codex P2-1) test (d): the depth generator model resolves via the SAME central runtime-lock
    # path the other composers use (PG_GENERATOR_MODEL == the lock generator slug), NOT a per-leg override.
    import src.polaris_graph.llm.openrouter_client as orc
    from src.polaris_graph.generator.depth_synthesis import _resolve_model

    assert _resolve_model() == orc.PG_GENERATOR_MODEL
    # the removed PG_DEPTH_SYNTHESIS_MODEL knob can no longer divert depth off the lock.
    monkeypatch.setenv("PG_DEPTH_SYNTHESIS_MODEL", "forbidden/off-lock-model")
    assert _resolve_model() == orc.PG_GENERATOR_MODEL


def test_below_corroboration_floor_basket_is_skipped():
    # A basket with a single SUPPORTS member is NOT a cross-source finding (definitional, not a filter).
    basket, evidence_pool = _fixture_basket()
    one_member = ClaimBasket(
        "c2", "x", "x", "y", [basket.supporting_members[0]], (), 1.0, 1, 1, "partial",
    )
    findings = synthesize_cross_source_findings(
        [one_member], evidence_pool,
        synthesizer=lambda _b, _p: _GROUNDED,
        verify_fn=strict_verify,
        bib_num_by_evidence_id=_BIB_MAP,
    )
    assert findings == []


def test_unmappable_citation_drops_the_sentence():
    # A kept sentence whose evidence_id is not in the report bibliography cannot ship a consistent [N].
    basket, evidence_pool = _fixture_basket()
    findings = synthesize_cross_source_findings(
        [basket], evidence_pool,
        synthesizer=lambda _b, _p: _GROUNDED,
        verify_fn=strict_verify,
        bib_num_by_evidence_id={"ev_z": 9},  # ev_a absent -> unmappable -> drop
    )
    assert findings == []


def test_build_depth_layer_renders_cross_source_block(monkeypatch):
    monkeypatch.setenv(kf._DEPTH_LAYER_ENV, "1")
    basket, evidence_pool = _fixture_basket()
    findings = synthesize_cross_source_findings(
        [basket], evidence_pool,
        synthesizer=lambda _b, _p: _GROUNDED,
        verify_fn=strict_verify,
        bib_num_by_evidence_id=_BIB_MAP,
    )
    out = kf.build_depth_layer([], synthesized_findings=findings)
    assert "## Analytical synthesis" in out
    assert "### Cross-source synthesis" in out
    assert "[3]" in out
    # HONEST provenance label: the cross-source bullets are generator-phrased + re-grounded, NOT
    # verbatim lifts — the sub-label must say so (§-1.1 misstated-provenance is lethal).
    assert "generator-phrased" in out and "re-passed strict_verify" in out
    # default-OFF master flag => byte-identical empty even with synthesized findings present
    monkeypatch.setenv(kf._DEPTH_LAYER_ENV, "0")
    assert kf.build_depth_layer([], synthesized_findings=findings) == ""


def test_bib_num_by_evidence_id_maps_report_numbers():
    bib = [
        {"num": 3, "evidence_id": "ev_a", "url": "https://nejm.org/a"},
        {"num": 4, "evidence_id": "ev_b"},
        {"evidence_id": "ev_c"},   # missing num -> skipped
        {"num": 5},                # missing evidence_id -> skipped
    ]
    out = bib_num_by_evidence_id(bib)
    assert out == {"ev_a": 3, "ev_b": 4}


def test_analytical_depth_counts_inline_atx_key_findings(monkeypatch):
    # I-wire-013 regex fix: an ATX "## Key Findings" header INSIDE a section's content is now counted
    # (default ON); the kill-switch restores the bold-only undercount.
    monkeypatch.delenv("PG_DEPTH_COUNT_ATX_KEY_FINDINGS", raising=False)
    section = [{"title": "Synthesis", "content": "## Key Findings\n\nMortality fell by 25%."}]
    assert evaluate_analytical_depth(section)["key_findings"] == 1
    monkeypatch.setenv("PG_DEPTH_COUNT_ATX_KEY_FINDINGS", "0")
    assert evaluate_analytical_depth(section)["key_findings"] == 0
