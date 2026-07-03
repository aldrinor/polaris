"""I-deepfix-001 P2 (#1344) — CITATION-PURITY directional-NLI co-support replay.

Owner: ``src/polaris_graph/generator/provenance_generator.py`` (the single corroborator
grounding chokepoint ``corroborator_grounds_sentence_via_basket`` + the own-token emit in
``resolve_provenance_to_citations_with_count``) and
``src/polaris_graph/synthesis/consolidation_nli.py`` (the new ``entails_directional`` primitive).

## What P2 does (design: ``.codex/I-deepfix-001/beatboth_master_fix_plan.md`` P2_citation_purity)

A corroborator [N] is attached to a sentence by CLUSTER membership once its span clears the
LEXICAL/NUMERIC overlap floor (``corroborator_span_grounds_sentence``). That floor can still
keep an OFF-TOPIC span that shares only GENERIC vocabulary with the claim (e.g. an "American
workers value manufacturing occupations" span glued onto a "displace fourteen percent" claim).
P2 STACKS a directional NLI co-support check BENEATH the floor — an AND, so it can ONLY tighten:
the cited SPAN (premise) must entail the CLAIM (hypothesis, ALCE/DeepTRACE direction). A span
that does not entail loses its INLINE [N]; the source STAYS as basket context in the
bibliography (§-1.3 WEIGHT/PURITY detach, never a source-type drop).

## Why this replay proves the effect (not just a flag)

The whole chain runs through the REAL ``resolve_provenance_to_citations_with_count`` over a real
basket + evidence_pool + kept-sentence. The cross-encoder is INJECTED (a deterministic
``entails_directional`` stub keyed on the span text — the true-corroborator span carries the
claim's load-bearing token, the off-topic span does not), so there is NO GPU / model download and
NO OpenRouter spend — the CI variant of the design's "deterministic mocked-entails variant for CI
+ GPU-real variant for the VM". The asserts are on the RENDERED output + bibliography, per the
I-wire-014 banked-replay-is-blind lesson (prove the [N] set changed in real output, not a counter
alone).

Fail-loud RED->GREEN: with ``PG_CITATION_NLI_PURITY=0`` the off-topic corroborator is KEPT inline
(the pre-fix legacy behaviour, and the byte-identical revert); with ``=1`` it is DETACHED while
the true corroborator + own token are kept and the detached source is retained as basket context.
"""
from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from src.polaris_graph.synthesis import consolidation_nli
from src.polaris_graph.generator import provenance_generator as pg
from src.polaris_graph.generator.provenance_generator import (
    ProvenanceToken,
    SentenceVerification,
    resolve_provenance_to_citations_with_count,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixture: one claim cluster c1 with an OWN-token source + two corroborators.
#   * ev_own  — the sentence's own cited source (grounds the claim).
#   * ev_true — an INDEPENDENT corroborator that reports the SAME displacement claim
#               (its span carries "displace" — lexical AND NLI both keep it).
#   * ev_off  — an OFF-TOPIC corroborator whose span shares GENERIC words with the claim
#               (american/workers/manufacturing/occupations) so the LEXICAL floor keeps it,
#               but it does NOT entail the "displace fourteen percent" claim (NLI detaches).
# The NLI verdict is the ONLY thing that separates ev_true from ev_off — so a detach on ev_off
# with ev_true kept proves the co-support gate, not the lexical floor.
# ─────────────────────────────────────────────────────────────────────────────

_CLAIM = "Automation could displace fourteen percent of American workers in manufacturing occupations."
_OWN_DQ = _CLAIM
_TRUE_DQ = "Researchers estimate automation may displace fourteen percent of workers within a decade."
_OFF_DQ = "American workers in manufacturing occupations report high job satisfaction and community pride."


def _member(eid: str, dq: str) -> SimpleNamespace:
    return SimpleNamespace(
        evidence_id=eid,
        source_url=f"https://example.org/{eid}",
        source_tier="T2",
        origin_cluster_id=f"o::{eid}",
        credibility_weight=0.8,
        authority_score=0.8,
        span_verdict="SUPPORTS",
        member_tier="SUPPORTS",
        direct_quote=dq,
    )


def _build_inputs():
    evidence_pool = {
        "ev_own": {
            "source_url": "https://example.org/ev_own", "tier": "T2",
            "statement": _OWN_DQ, "direct_quote": _OWN_DQ,
        },
        "ev_true": {
            "source_url": "https://example.org/ev_true", "tier": "T2",
            "statement": _TRUE_DQ, "direct_quote": _TRUE_DQ,
        },
        "ev_off": {
            "source_url": "https://example.org/ev_off", "tier": "T2",
            "statement": _OFF_DQ, "direct_quote": _OFF_DQ,
        },
    }
    basket = SimpleNamespace(
        claim_cluster_id="c1",
        claim_text=_CLAIM,
        subject="automation",
        predicate="displace",
        verified_support_origin_count=3,
        total_clustered_origin_count=3,
        weight_mass=2.4,
        basket_verdict="full",
        refuter_cluster_ids=(),
        supporting_members=[
            _member("ev_own", _OWN_DQ),
            _member("ev_true", _TRUE_DQ),
            _member("ev_off", _OFF_DQ),
        ],
    )
    cluster_id_by_evidence = {"ev_own": ["c1"], "ev_true": ["c1"], "ev_off": ["c1"]}
    sentence = f"{_CLAIM}[#ev:ev_own:0-{len(_OWN_DQ)}]"
    sv = SentenceVerification(
        sentence=sentence,
        tokens=[ProvenanceToken(evidence_id="ev_own", start=0, end=len(_OWN_DQ), raw="")],
        is_verified=True,
    )
    return [sv], evidence_pool, [basket], cluster_id_by_evidence


def _stub_entails(premise: str, hypothesis: str, **_kw):
    """Deterministic directional-NLI stub (no GPU): the span (premise) entails the claim iff it
    carries the load-bearing displacement token. The true-corroborator + own spans carry
    'displace'; the off-topic span does not."""
    return "displace" in (premise or "").lower()


def _num_for_eid(biblio, eid):
    for row in biblio:
        if row.get("evidence_id") == eid:
            return row.get("num")
    return None


def _eid_in_basket_context(biblio, eid) -> bool:
    """Is ``eid`` present as a basket-context member of ANY numbered bibliography row?
    (A P2-detached corroborator loses its own [N] but is RETAINED as basket context.)"""
    for row in biblio:
        for bsk in (row.get("baskets") or []):
            for m in (bsk.get("supporting_members") or []):
                if m.get("evidence_id") == eid:
                    return True
    return False


def test_entails_directional_forward_only():
    """The new consolidation_nli.entails_directional reads ONLY the forward logits and returns
    the three-state verdict (True / False / None), reusing the injected predict seam (no GPU)."""
    ent = lambda batch: [[0.1, 5.0, 0.2]]   # [contradiction, entailment, neutral] -> entailment
    con = lambda batch: [[5.0, 0.1, 0.2]]   # contradiction argmax
    neu = lambda batch: [[0.1, 0.2, 5.0]]   # neutral argmax
    assert consolidation_nli.entails_directional("span", "claim", predict_fn=ent) is True
    assert consolidation_nli.entails_directional("span", "claim", predict_fn=con) is False
    assert consolidation_nli.entails_directional("span", "claim", predict_fn=neu) is False
    # Empty text => UNAVAILABLE sentinel (None) so a caller keeps on lexical grounding.
    assert consolidation_nli.entails_directional("", "claim", predict_fn=ent) is None


def test_p2_offtopic_corroborator_detached_true_kept(monkeypatch):
    """PG_CITATION_NLI_PURITY=1: the off-topic corroborator [N] is DETACHED from inline support
    while the true corroborator + own token are KEPT, the detached source is RETAINED as basket
    context, and the sentence never goes cited->uncited."""
    monkeypatch.setenv("PG_CITATION_NLI_PURITY", "1")
    monkeypatch.setattr(consolidation_nli, "entails_directional", _stub_entails, raising=False)
    pg.reset_purity_telemetry()

    kept, pool, baskets, binding = _build_inputs()
    text, biblio, emitted = resolve_provenance_to_citations_with_count(
        kept, pool, baskets=baskets, cluster_id_by_evidence=binding,
    )

    n_own = _num_for_eid(biblio, "ev_own")
    n_true = _num_for_eid(biblio, "ev_true")
    n_off = _num_for_eid(biblio, "ev_off")

    # Own token + true corroborator render inline (non-vacuous: real multi-citation survives).
    assert n_own is not None and f"[{n_own}]" in text, f"own token must stay cited; text={text!r}"
    assert n_true is not None and f"[{n_true}]" in text, (
        f"the TRUE same-claim corroborator (span entails the claim) must be KEPT inline; "
        f"text={text!r} biblio={biblio!r}"
    )

    # The OFF-TOPIC corroborator's span does NOT entail the claim => its inline [N] is DETACHED.
    if n_off is not None:
        assert f"[{n_off}]" not in text, (
            f"FAITHFULNESS FAIL: the off-topic corroborator [{n_off}] (span does not entail the "
            f"claim) was rendered inline — the P2 NLI co-support gate did not detach it; "
            f"text={text!r}"
        )

    # ... but the detached source is RETAINED as basket context (§-1.3 WEIGHT/PURITY detach,
    # never a source drop).
    assert _eid_in_basket_context(biblio, "ev_off"), (
        "the P2-detached off-topic source must remain in the bibliography as basket context "
        "(purity detach keeps the source, only withholds its inline [N])"
    )

    # Sentence still cited (never cited->uncited) and the gate provably FIRED.
    assert emitted == 1
    tel = pg.get_purity_telemetry()
    assert tel["nli_detached"] >= 1, f"the NLI co-support gate never fired; telemetry={tel}"


def test_p2_off_flag_keeps_offtopic_corroborator(monkeypatch):
    """PG_CITATION_NLI_PURITY=0 reverts byte-identical: the off-topic corroborator (which clears
    the lexical floor) is KEPT inline exactly as the pre-fix legacy render — proving the ON-run
    detach above is caused by P2 and is non-vacuous, and that =0 is a clean revert."""
    monkeypatch.setenv("PG_CITATION_NLI_PURITY", "0")
    # Even with a stub present, the OFF flag must never consult it.
    monkeypatch.setattr(consolidation_nli, "entails_directional", _stub_entails, raising=False)
    pg.reset_purity_telemetry()

    kept, pool, baskets, binding = _build_inputs()
    text, biblio, _emitted = resolve_provenance_to_citations_with_count(
        kept, pool, baskets=baskets, cluster_id_by_evidence=binding,
    )

    n_off = _num_for_eid(biblio, "ev_off")
    assert n_off is not None and f"[{n_off}]" in text, (
        "with PG_CITATION_NLI_PURITY=0 the off-topic corroborator must render inline (the "
        f"lexical floor keeps it) — byte-identical legacy render; text={text!r}"
    )
    tel = pg.get_purity_telemetry()
    assert tel["nli_detached"] == 0, f"the NLI gate must not fire when OFF; telemetry={tel}"


def test_p2_own_token_withheld_on_out_of_bounds_span_but_kept_in_biblio(monkeypatch):
    """PG_CITATION_NLI_PURITY=1 own-token render-time re-assert: a token whose stored (start,end)
    is now OUT OF BOUNDS on the CURRENT direct_quote (the I-wire-014 truncation class) has its
    inline [N] WITHHELD (fail-closed), but the source STAYS in the bibliography and the
    min-retention guard keeps the sentence cited when it is the sentence's ONLY own token."""
    monkeypatch.setenv("PG_CITATION_NLI_PURITY", "1")
    monkeypatch.setattr(consolidation_nli, "entails_directional", _stub_entails, raising=False)
    pg.reset_purity_telemetry()

    # A truncated direct_quote: the token points at [0:len(_CLAIM)] but the current span is short.
    short_dq = "Automation could displace fourteen percent."
    pool = {
        "ev_trunc": {
            "source_url": "https://example.org/ev_trunc", "tier": "T2",
            "statement": _CLAIM, "direct_quote": short_dq,
        },
        "ev_good": {
            "source_url": "https://example.org/ev_good", "tier": "T2",
            "statement": _CLAIM, "direct_quote": _CLAIM,
        },
    }
    # Sentence A: ONLY the out-of-bounds token -> min-retention guard must KEEP it (never strand).
    sv_a = SentenceVerification(
        sentence=f"{_CLAIM}[#ev:ev_trunc:0-{len(_CLAIM)}]",
        tokens=[ProvenanceToken(evidence_id="ev_trunc", start=0, end=len(_CLAIM), raw="")],
        is_verified=True,
    )
    text_a, biblio_a, _ = resolve_provenance_to_citations_with_count(sv_a and [sv_a], pool)
    n_trunc = _num_for_eid(biblio_a, "ev_trunc")
    assert n_trunc is not None and f"[{n_trunc}]" in text_a, (
        "min-retention guard must keep the sole own token cited even though its span is out of "
        f"bounds (never cited->uncited); text={text_a!r}"
    )
    assert pg.get_purity_telemetry()["own_token_retention_kept"] >= 1

    # Sentence B: the out-of-bounds token PLUS a good in-bounds token -> the bad token's [N] is
    # WITHHELD (a passing token remains, so retention does not fire), source stays in biblio.
    pg.reset_purity_telemetry()
    sv_b = SentenceVerification(
        sentence=f"{_CLAIM}[#ev:ev_good:0-{len(_CLAIM)}][#ev:ev_trunc:0-{len(_CLAIM)}]",
        tokens=[
            ProvenanceToken(evidence_id="ev_good", start=0, end=len(_CLAIM), raw=""),
            ProvenanceToken(evidence_id="ev_trunc", start=0, end=len(_CLAIM), raw=""),
        ],
        is_verified=True,
    )
    text_b, biblio_b, _ = resolve_provenance_to_citations_with_count([sv_b], pool)
    n_good = _num_for_eid(biblio_b, "ev_good")
    n_trunc_b = _num_for_eid(biblio_b, "ev_trunc")
    assert n_good is not None and f"[{n_good}]" in text_b, "the in-bounds token must render inline"
    # The truncated token is withheld from inline support...
    if n_trunc_b is not None:
        assert f"[{n_trunc_b}]" not in text_b, (
            f"the out-of-bounds own token [{n_trunc_b}] must be withheld inline; text={text_b!r}"
        )
    # ... but its source is retained in the bibliography (fail-closed detach keeps the source).
    assert n_trunc_b is not None, "the withheld own-token source must still be numbered in biblio"
    assert pg.get_purity_telemetry()["withheld_own_token"] >= 1


# ─────────────────────────────────────────────────────────────────────────────
# Codex iter-1 P1 (blocker): Gate-B forces the V30 CONTRACT regroup
# (``contract_sentence_citation_nums``), NOT the flat resolver body. The render-time
# own-token bounds re-assert must ALSO fire there — otherwise a withheld bad own token
# (still registered in ev_to_num / biblio by the resolver) is REATTACHED into the shipped
# slot body and the purity fix is a no-op on the benchmark path. These tests exercise the
# contract helper DIRECTLY over a real ev_to_num, so RED (pre-fix) reattaches the bad [N].
# ─────────────────────────────────────────────────────────────────────────────

_SHORT_DQ = "Automation could displace fourteen percent."


def _contract_pool():
    # ev_trunc: direct_quote truncated BETWEEN verify and render (I-wire-014), so the stored
    # (0, len(_CLAIM)) is now OUT OF BOUNDS on the current span => own-token re-assert fails.
    # ev_good: current direct_quote still holds the full claim => re-assert passes.
    return {
        "ev_trunc": {
            "source_url": "https://example.org/ev_trunc", "tier": "T2",
            "statement": _CLAIM, "direct_quote": _SHORT_DQ,
        },
        "ev_good": {
            "source_url": "https://example.org/ev_good", "tier": "T2",
            "statement": _CLAIM, "direct_quote": _CLAIM,
        },
    }


def _contract_sv(sentence, tokens):
    # No relevance_demoted_eids / relevance_refuted_eids attrs => getattr default frozenset.
    return SimpleNamespace(sentence=sentence, tokens=tokens)


def _call_contract_nums(sv, ev_to_num, pool):
    from src.polaris_graph.generator.contract_section_runner import (
        contract_sentence_citation_nums,
    )
    # Empty basket index => the corroborator branch is inert; this isolates the OWN-token path.
    return contract_sentence_citation_nums(
        sv, sv.tokens, dict(ev_to_num),
        basket_supports_by_cluster={},
        cluster_id_by_evidence={},
        evidence_pool=pool,
        basket_by_cluster={},
    )


def test_p2_contract_path_withholds_out_of_bounds_own_token(monkeypatch):
    """PG_CITATION_NLI_PURITY=1 on the V30 CONTRACT regroup: an own token whose stored span is
    now OUT OF BOUNDS on the current direct_quote must NOT be reattached into the shipped slot
    body via ev_to_num — even though the resolver already numbered it — while a good in-bounds
    own token IS kept. This is the Codex iter-1 P1 blocker (Gate-B forces this path)."""
    monkeypatch.setenv("PG_CITATION_NLI_PURITY", "1")
    pool = _contract_pool()
    # The resolver already registered BOTH sources (incl. the withheld-bad one) in ev_to_num.
    ev_to_num = {"ev_good": 6, "ev_trunc": 5}

    sv_b = _contract_sv(
        f"{_CLAIM}[#ev:ev_good:0-{len(_CLAIM)}][#ev:ev_trunc:0-{len(_CLAIM)}]",
        [
            ProvenanceToken(evidence_id="ev_good", start=0, end=len(_CLAIM), raw=""),
            ProvenanceToken(evidence_id="ev_trunc", start=0, end=len(_CLAIM), raw=""),
        ],
    )
    nums_b = _call_contract_nums(sv_b, ev_to_num, pool)
    assert 6 in nums_b, f"the in-bounds own token [6] must stay cited; nums={nums_b}"
    assert 5 not in nums_b, (
        "FAITHFULNESS FAIL (Codex P1): the out-of-bounds own token [5] was REATTACHED into the "
        f"V30 contract body via ev_to_num — the render-time purity fix is a no-op on Gate-B; "
        f"nums={nums_b}"
    )


def test_p2_contract_path_min_retention_keeps_sole_own_token(monkeypatch):
    """PG_CITATION_NLI_PURITY=1: when the out-of-bounds token is the sentence's ONLY own token,
    the min-retention guard KEEPS it (never cited->uncited) on the contract path too."""
    monkeypatch.setenv("PG_CITATION_NLI_PURITY", "1")
    pool = _contract_pool()
    ev_to_num = {"ev_good": 6, "ev_trunc": 5}
    sv_a = _contract_sv(
        f"{_CLAIM}[#ev:ev_trunc:0-{len(_CLAIM)}]",
        [ProvenanceToken(evidence_id="ev_trunc", start=0, end=len(_CLAIM), raw="")],
    )
    nums_a = _call_contract_nums(sv_a, ev_to_num, pool)
    assert nums_a == [5], (
        f"min-retention must keep the sole own token cited (never cited->uncited); nums={nums_a}"
    )


def test_p2_contract_path_off_flag_reattaches_own_token(monkeypatch):
    """PG_CITATION_NLI_PURITY=0 reverts byte-identical on the CONTRACT path: BOTH own tokens
    (including the out-of-bounds one) reattach exactly as the legacy regroup — proving the ON
    withhold is caused by P2 and =0 is a clean revert (no cross-encoder / no bounds re-assert)."""
    monkeypatch.setenv("PG_CITATION_NLI_PURITY", "0")
    pool = _contract_pool()
    ev_to_num = {"ev_good": 6, "ev_trunc": 5}
    sv_b = _contract_sv(
        f"{_CLAIM}[#ev:ev_good:0-{len(_CLAIM)}][#ev:ev_trunc:0-{len(_CLAIM)}]",
        [
            ProvenanceToken(evidence_id="ev_good", start=0, end=len(_CLAIM), raw=""),
            ProvenanceToken(evidence_id="ev_trunc", start=0, end=len(_CLAIM), raw=""),
        ],
    )
    nums_b = _call_contract_nums(sv_b, ev_to_num, pool)
    assert 5 in nums_b and 6 in nums_b, (
        "with PG_CITATION_NLI_PURITY=0 both own tokens must reattach (byte-identical legacy "
        f"contract regroup); nums={nums_b}"
    )
