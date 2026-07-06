"""I-deepfix-001 COV-DECHROME-BASKETS (#1344) — coverage-forensic root fix.

The coverage forensic traced the depth pre-pass 3->0 collapse (and the death of the one anchored
cross-source pair) to CHROME basket member spans: a member whose claim-local ``direct_quote`` is page
furniture (cookie/consent banner, author byline, ToC dot-leader, dead-fetch shell) still arrived at the
cross-source synthesizer as an isolated-``SUPPORTS`` member — credibility_pass kept it (correctly, §-1.3
no-drop) but only held it out of the strengthening COUNT, never out of ``supporting_members``. The
cross-source eligibility gate then COUNTED the chrome member toward the ``>=2 distinct origins`` floor and
the synthesizer built its consolidation prompt / span-join on the chrome span, collapsing the basket.

RED (the exact defect): a basket whose second "origin" is a cookie-banner span is COUNTED toward
cross-source eligibility and drafted.
GREEN (the fix): the chrome member is held OUT of the corroboration set BEFORE eligibility, the basket's
REAL members are retained, and each hold-out is logged LOUD per-basket.

FAITHFULNESS: untouched (strict_verify / NLI / D8 / provenance / span-grounding). §-1.3: page furniture
is not a corroborating source, so holding it out of a count is not a DROP of a real source — the source
stays in ``supporting_members`` + disclosure. LAW VI: default-ON kill-switch ``PG_DEPTH_DECHROME_MEMBERS``.
"""
from __future__ import annotations

import logging

import pytest

from src.polaris_graph.generator.depth_synthesis import (
    _dechrome_distinct_origin_supports,
    _distinct_origin_supports,
    synthesize_cross_source_findings,
)
from src.polaris_graph.synthesis.credibility_pass import (
    MEMBER_TIER_ENTAILMENT_VERIFIED,
    BasketMember,
    ClaimBasket,
)

# Two REAL corroborating spans (same finding) + one CHROME span (a cookie-consent banner). The chrome
# string trips the shared render-seam predicate ``is_render_chrome_or_unrenderable`` (verified live).
_REAL_A = "Generative AI raised call-center worker productivity by 14 percent in a field experiment."
_REAL_B = "A controlled trial found AI assistance increased worker output by 14 percent."
_CHROME = "We use cookies to enhance your browsing experience on our site."


def _member(eid: str, origin: str, quote: str, *, weight: float, span_is_chrome: bool = False) -> BasketMember:
    return BasketMember(
        eid, f"https://example.org/{eid}", "T1", origin, weight, 0.9,
        (0, len(quote)), quote, "SUPPORTS", MEMBER_TIER_ENTAILMENT_VERIFIED,
        span_is_chrome=span_is_chrome,
    )


def _basket(members: list[BasketMember]) -> ClaimBasket:
    return ClaimBasket(
        "c1", "AI raised worker productivity by 14 percent", "AI", "raised productivity by 14 percent",
        members, (), 2.0, len(members), 0, "partial",
    )


def _two_real_one_chrome() -> ClaimBasket:
    return _basket([
        _member("ev_a", "o1", _REAL_A, weight=0.95),
        _member("ev_chrome", "o2", _CHROME, weight=0.90),  # page furniture (cookie banner)
        _member("ev_b", "o3", _REAL_B, weight=0.85),
    ])


def test_red_legacy_selection_counts_chrome_member() -> None:
    """RED: the pre-fix member selection (``_distinct_origin_supports``) INCLUDES the chrome member —
    it is counted toward cross-source corroboration exactly as the forensic found."""
    basket = _two_real_one_chrome()
    legacy = _distinct_origin_supports(basket)
    quotes = {m.direct_quote for m in legacy}
    assert _CHROME in quotes  # the defect: page furniture counted as a corroborating origin
    assert len(legacy) == 3


def test_green_dechrome_holds_out_chrome_keeps_real(caplog: pytest.LogCaptureFixture) -> None:
    """GREEN: the chrome member is held out; the two REAL members are retained; the drop is logged LOUD."""
    basket = _two_real_one_chrome()
    with caplog.at_level(logging.INFO, logger="src.polaris_graph.generator.depth_synthesis"):
        kept = _dechrome_distinct_origin_supports(basket)
    kept_quotes = {m.direct_quote for m in kept}
    assert _CHROME not in kept_quotes  # chrome held out of the corroboration set
    assert kept_quotes == {_REAL_A, _REAL_B}  # real members RETAINED (§-1.3 no-drop of real sources)
    assert {m.evidence_id for m in kept} == {"ev_a", "ev_b"}
    # loud per-basket disclosure (the forensic flagged these were SILENT)
    assert any(
        "dropped from corroboration" in r.message and "chrome" in r.message and "ev_chrome" in r.message
        for r in caplog.records
    )


def test_green_dechrome_reads_durable_flag() -> None:
    """The DURABLE ``span_is_chrome`` flag credibility_pass stamps at basket build is honored even when
    the member's ``direct_quote`` text alone would not trip the re-screen."""
    basket = _basket([
        _member("ev_a", "o1", _REAL_A, weight=0.95),
        _member("ev_flagged", "o2", "A perfectly ordinary sentence about workers.", weight=0.9,
                span_is_chrome=True),  # flagged chrome at basket build (dead-fetch shell etc.)
        _member("ev_b", "o3", _REAL_B, weight=0.85),
    ])
    kept = _dechrome_distinct_origin_supports(basket)
    assert {m.evidence_id for m in kept} == {"ev_a", "ev_b"}


def test_kill_switch_off_is_byte_identical_legacy(monkeypatch: pytest.MonkeyPatch) -> None:
    """LAW VI: ``PG_DEPTH_DECHROME_MEMBERS=0`` => the dechrome is a no-op (legacy selection, chrome kept)."""
    monkeypatch.setenv("PG_DEPTH_DECHROME_MEMBERS", "0")
    basket = _two_real_one_chrome()
    assert _dechrome_distinct_origin_supports(basket) == _distinct_origin_supports(basket)


def test_behavioral_chrome_not_counted_toward_eligibility(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end at the eligibility seam: a basket with ONE real origin + ONE chrome origin.

    RED (kill-switch OFF = legacy): the chrome member is counted -> the basket clears the ``>=2`` floor
    -> the synthesizer is invoked (the basket is drafted).
    GREEN (default ON): the chrome member is held out -> only ONE real origin remains -> the basket is
    below the floor -> the synthesizer is NEVER invoked (no chrome-contaminated draft).
    """
    # isolate the eligibility effect from the FIX-1 span-join fallback
    monkeypatch.setenv("PG_DEPTH_SYNTHESIS_SPANJOIN_FALLBACK", "0")
    basket = _basket([
        _member("ev_a", "o1", _REAL_A, weight=0.95),
        _member("ev_chrome", "o2", _CHROME, weight=0.90),
    ])
    pool = {
        "ev_a": {"source_url": "https://example.org/ev_a", "tier": "T1", "direct_quote": _REAL_A},
        "ev_chrome": {"source_url": "https://example.org/ev_chrome", "tier": "T1", "direct_quote": _CHROME},
    }

    calls: list = []

    class _EmptyReport:
        kept_sentences: list = []

    def _fake_synth(b, p):
        calls.append(b)
        return f"AI raised worker productivity by 14 percent [#ev:ev_a:0-{len(_REAL_A)}]."

    def _fake_verify(_draft, _scoped):
        return _EmptyReport()

    # RED — legacy: chrome counted, basket eligible, synthesizer drafted it
    monkeypatch.setenv("PG_DEPTH_DECHROME_MEMBERS", "0")
    calls.clear()
    synthesize_cross_source_findings(
        [basket], pool, synthesizer=_fake_synth, verify_fn=_fake_verify,
    )
    assert len(calls) == 1

    # GREEN — default ON: chrome held out, basket below the >=2 floor, synthesizer never called
    monkeypatch.delenv("PG_DEPTH_DECHROME_MEMBERS", raising=False)
    calls.clear()
    out = synthesize_cross_source_findings(
        [basket], pool, synthesizer=_fake_synth, verify_fn=_fake_verify,
    )
    assert calls == []
    assert out == []
