"""I-deepfix-006-compose C2 — offline behavioral tests for single-source synthesis.

Proves that when C1 (entailment verify) AND PG_SYNTH_SINGLE_SOURCE are both on, a basket with ONE
distinct-origin SUPPORTS member is SYNTHESIZED and labeled ``(single source)`` — never dropped — while
with the flag OFF the DEFINITIONAL >=2 eligibility floor holds (the single-member basket is dropped).
Deterministic + offline: a fake synthesizer + the entailment judge stubbed (no GPU / network).
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator.depth_synthesis import synthesize_cross_source_findings
from src.polaris_graph.generator.provenance_generator import strict_verify
from src.polaris_graph.synthesis.credibility_pass import (
    MEMBER_TIER_ENTAILMENT_VERIFIED,
    BasketMember,
    ClaimBasket,
)

_QUOTE = "Mortality fell by 25% across the pooled multinational cohorts."


def _single_member_basket() -> tuple[ClaimBasket, dict, dict]:
    evidence_pool = {"ev_a": {"source_url": "https://nejm.org/a", "tier": "T1", "direct_quote": _QUOTE}}
    members = [
        BasketMember("ev_a", "https://nejm.org/a", "T1", "o1", 0.95, 0.9,
                     (0, len(_QUOTE)), _QUOTE, "SUPPORTS", MEMBER_TIER_ENTAILMENT_VERIFIED),
    ]
    basket = ClaimBasket(
        "c1", "Mortality fell by 25%", "mortality", "fell by 25%",
        members, (), 0.95, 1, 1, "full",
    )
    bib_map = {"ev_a": 3}
    return basket, evidence_pool, bib_map


# A verbatim-grounded single-source sentence (strict_verify keeps it on its own; entailment leg is inert).
_SINGLE = f"Mortality fell by 25% across the pooled multinational cohorts [#ev:ev_a:0-{len(_QUOTE)}]."


@pytest.fixture(autouse=True)
def _offline_entailment(monkeypatch):
    # Stub the entailment judge so the C1 union wrap (auto-applied by synthesize_cross_source_findings)
    # never loads the cross-encoder; strict_verify keeps the verbatim sentence regardless.
    monkeypatch.setattr(
        "src.polaris_graph.synthesis.consolidation_nli.entails_directional",
        lambda _p, _h, **_k: True,
    )
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")


def test_single_source_basket_synthesized_and_labeled(monkeypatch):
    monkeypatch.setenv("PG_SYNTH_ENTAILMENT_VERIFY", "1")  # C1 on
    monkeypatch.setenv("PG_SYNTH_SINGLE_SOURCE", "1")      # C2 on
    basket, evidence_pool, bib_map = _single_member_basket()
    findings = synthesize_cross_source_findings(
        [basket], evidence_pool,
        synthesizer=lambda _b, _p: _SINGLE,
        verify_fn=strict_verify,
        bib_num_by_evidence_id=bib_map,
    )
    assert len(findings) == 1, findings
    finding = findings[0]
    assert finding["tier"] == "single_source", finding
    assert finding["label"] == "(single source)", finding
    assert "[3]" in finding["sentence"]
    assert "[#ev:" not in finding["sentence"]


def test_single_source_dropped_when_flag_off(monkeypatch):
    # PG_SYNTH_SINGLE_SOURCE OFF => the DEFINITIONAL >=2 eligibility floor holds; the 1-member basket
    # is not a candidate and is dropped (byte-identical to pre-C2).
    monkeypatch.setenv("PG_SYNTH_ENTAILMENT_VERIFY", "1")
    monkeypatch.setenv("PG_SYNTH_SINGLE_SOURCE", "0")
    basket, evidence_pool, bib_map = _single_member_basket()
    findings = synthesize_cross_source_findings(
        [basket], evidence_pool,
        synthesizer=lambda _b, _p: _SINGLE,
        verify_fn=strict_verify,
        bib_num_by_evidence_id=bib_map,
    )
    assert findings == []


def test_single_source_requires_c1(monkeypatch):
    # C2 fires ONLY when C1 is also on. C1 OFF => single-source not active => the 1-member basket drops.
    monkeypatch.setenv("PG_SYNTH_ENTAILMENT_VERIFY", "0")
    monkeypatch.setenv("PG_SYNTH_SINGLE_SOURCE", "1")
    basket, evidence_pool, bib_map = _single_member_basket()
    findings = synthesize_cross_source_findings(
        [basket], evidence_pool,
        synthesizer=lambda _b, _p: _SINGLE,
        verify_fn=strict_verify,
        bib_num_by_evidence_id=bib_map,
    )
    assert findings == []
