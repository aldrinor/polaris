"""I-deepfix-001 Wave-2 DEPTH (w2-D) behavioral tests — D1 / D2 / D3 / D4.

FAIL-LOUD + ISOLATED + OFFLINE ($0, no GPU, no network judge). Each test proves the EFFECT of its fix
in real composed / planned output, not a flag read:

  * D1 — WITHIN-BASKET QUALIFIER ELABORATION (`verified_compose.compose_qualifier_elaboration_units`
    + the `_compose_section_per_basket` wiring): the additive pass surfaces a basket member's OWN
    verbatim qualifier sentence (population/timeframe/etc.) the single-source headline dropped, each
    re-verified by the UNCHANGED `verify_sentence_provenance`; a non-qualifier corpus surfaces nothing;
    the whole thing is keep-all and default-OFF byte-identical.
  * D2 — VERIFIED CROSS-SOURCE ANALYTICAL COMPOSER
    (`cross_source_synthesis.compose_cross_source_analytical_units`): a two-basket shared-anchor pair
    composes ONE analytical sentence carrying TWO distinct `[#ev]` tokens; the connective is
    engine-LICENSED (neutral with no edge, conflict when a ContradictionEdge is injected); both atoms
    re-verify per clause.
  * D3 — FAIL-CLOSED ANALYST-SYNTHESIS PROMOTE GATE
    (`analyst_synthesis_deviation_check`): the PROMOTE mode is default-OFF (byte-identical) and requires
    BOTH the deviation-check gate AND the fine promote flag; the module's judge-fault path is fail-closed
    LOW (an ungrounded / errored sentence is NEVER promoted into the body).
  * D4 — FACET-CLUSTER THE ENRICHMENT BREADTH SURFACE
    (`weighted_enrichment.route_enrichment_members_by_facet` +
    `build_weighted_enrichment_plans_by_facet`): unbound-but-verified members are routed under the
    topical facet section their subject matches instead of one flat dump; keep-all is conserved
    (routed ∪ residual == input, no member dropped, none duplicated).

The faithfulness engine (strict_verify / NLI / 4-role / provenance / span-grounding) is NEVER relaxed by
any of these; the tests assert exactly that (verify still gates, keep-all holds, defaults byte-identical).
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

# Offline: no extra judge calls, no network entailment (mirrors the render-probe path).
os.environ["PG_VERIFICATION_MODE"] = "off"
os.environ.pop("PG_STRICT_VERIFY_ENTAILMENT", None)

import pytest  # noqa: E402

from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    verify_sentence_provenance,
)
from src.polaris_graph.synthesis.credibility_pass import (  # noqa: E402
    BasketMember,
    ClaimBasket,
)


# ── shared synthetic-corpus builders ──────────────────────────────────────────────────────────────
def _member(evid: str, quote: str, *, origin: str | None = None, weight: float = 5.0) -> BasketMember:
    return BasketMember(
        evidence_id=evid,
        source_url=f"https://example.org/{evid}",
        source_tier="T1",
        origin_cluster_id=origin or f"origin::{evid}",
        credibility_weight=weight,
        authority_score=weight,
        span=(0, len(quote)),
        direct_quote=quote,
        span_verdict="SUPPORTS",
        member_tier="T1",
    )


def _basket(cluster: str, subject: str, predicate: str, members: list[BasketMember]) -> ClaimBasket:
    return ClaimBasket(
        claim_cluster_id=cluster,
        claim_text=f"{subject} {predicate}".strip(),
        subject=subject,
        predicate=predicate,
        supporting_members=members,
        refuter_cluster_ids=(),
        weight_mass=10.0,
        total_clustered_origin_count=len(members),
        verified_support_origin_count=len(members),
        basket_verdict="SUPPORTED",
    )


def _pool(*members: BasketMember) -> dict:
    return {m.evidence_id: {"direct_quote": m.direct_quote, "statement": m.direct_quote}
            for m in members}


# ── D1 — within-basket qualifier elaboration ───────────────────────────────────────────────────────
_D1_QUOTE = (
    "Semaglutide reduced mean body weight by 15 percent in the trial. "
    "The study enrolled 1961 adults aged 18 years or older over a 68 week follow-up period."
)
_D1_HEADLINE = "Semaglutide reduced mean body weight by 15 percent in the trial."


def test_d1_qualifier_elaboration_surfaces_member_qualifier_sentence():
    """The qualifier sentence the single-source headline dropped is surfaced as an EXTRA verified
    [#ev] unit — and it re-passes the UNCHANGED verify_sentence_provenance."""
    from src.polaris_graph.generator.verified_compose import (
        compose_qualifier_elaboration_units,
        _sentence_carries_qualifier,
    )
    m = _member("D1A", _D1_QUOTE)
    basket = _basket("clD1", "semaglutide weight", "reduces", [m])
    pool = _pool(m)

    assert _sentence_carries_qualifier(
        "The study enrolled 1961 adults aged 18 years or older over a 68 week follow-up period."
    ), "the qualifier detector must fire on population/timeframe cues (enrolled/adults/aged/week)"

    units = compose_qualifier_elaboration_units(
        basket, pool, _D1_HEADLINE, verify_fn=verify_sentence_provenance,
    )
    assert units, "D1 must surface >=1 qualifier elaboration unit for a qualifier-carrying member"
    joined = " ".join(units).lower()
    assert "enrolled" in joined and "adults" in joined, (
        f"the surfaced unit must be the member's own qualifier sentence; got {units!r}"
    )
    # The surfaced unit carries its OWN provenance token and re-verifies (faithfulness untouched).
    for u in units:
        assert "[#ev:" in u, f"each elaboration unit must carry a provenance token; got {u!r}"
        res = verify_sentence_provenance(u, pool)
        assert bool(getattr(res, "is_verified", False)), (
            f"a surfaced elaboration unit MUST re-pass the unchanged strict_verify; failed on {u!r}"
        )
    # The headline sentence is NEVER re-surfaced (keep-all, no duplication of the headline).
    assert "15 percent" not in joined, "D1 must not re-state the headline sentence"


def test_d1_no_qualifier_sentence_surfaces_nothing():
    """A member with no qualifier-carrying non-headline sentence yields [] (the selection filter is a
    real filter, not a blanket dump)."""
    from src.polaris_graph.generator.verified_compose import compose_qualifier_elaboration_units
    quote = "Semaglutide reduced mean body weight by 15 percent in the trial."
    m = _member("D1B", quote)
    basket = _basket("clD1b", "semaglutide weight", "reduces", [m])
    units = compose_qualifier_elaboration_units(
        basket, _pool(m), quote, verify_fn=verify_sentence_provenance,
    )
    assert units == [], f"no extra qualifier sentence exists -> must surface nothing; got {units!r}"


def test_d1_wiring_default_off_is_byte_identical_and_on_adds_the_unit(monkeypatch):
    """EFFECT-IN-OUTPUT: `_compose_section_per_basket` output is byte-identical with the flag OFF, and
    with the flag ON it gains the qualifier elaboration unit — proving the pass is really wired in."""
    from src.polaris_graph.generator.verified_compose import (
        _compose_section_per_basket,
        build_short_member_sentence,
    )
    m = _member("D1C", _D1_QUOTE)
    basket = _basket("clD1c", "semaglutide weight", "reduces", [m])
    pool = _pool(m)

    def _writer(bk, pl):
        return build_short_member_sentence(bk, pl)

    monkeypatch.delenv("PG_QUALIFIER_ELABORATION", raising=False)  # default OFF
    off = _compose_section_per_basket(
        [basket], pool, writer_fn=_writer, verify_fn=verify_sentence_provenance,
    )
    monkeypatch.setenv("PG_QUALIFIER_ELABORATION", "1")  # ON
    on = _compose_section_per_basket(
        [basket], pool, writer_fn=_writer, verify_fn=verify_sentence_provenance,
    )
    off_txt = " ".join(off).lower()
    on_txt = " ".join(on).lower()
    assert "enrolled" not in off_txt, "OFF path must NOT surface the qualifier sentence (byte-identical)"
    assert "enrolled" in on_txt and "adults" in on_txt, (
        f"ON path must surface the qualifier elaboration unit; off={off!r} on={on!r}"
    )
    assert len(on) > len(off), "the ON pass is ADDITIVE (keep-all): it only adds units, never removes"


# ── D2 — verified cross-source analytical composer ──────────────────────────────────────────────────
_D2_QUOTE_A = "Automation displaced roughly 12 percent of clerical roles in the surveyed firms."
_D2_QUOTE_B = "Automation displaced about 9 percent of clerical roles across the manufacturing sector."


def _d2_section():
    ma = _member("D2A", _D2_QUOTE_A, origin="origin::A")
    mb = _member("D2B", _D2_QUOTE_B, origin="origin::B")
    a = _basket("clA", "automation clerical", "displaces", [ma])
    b = _basket("clB", "automation clerical", "displaces", [mb])
    return [a, b], _pool(ma, mb)


def _d2_writer(_basket, _pool):
    from src.polaris_graph.generator.verified_compose import build_short_member_sentence
    return build_short_member_sentence(_basket, _pool)


def test_d2_cross_source_unit_has_two_tokens_and_neutral_connective_by_default():
    from src.polaris_graph.generator.cross_source_synthesis import (
        compose_cross_source_analytical_units,
        LICENSED_CONNECTIVES,
        _distinct_ev_ids,
    )
    section, pool = _d2_section()
    units = compose_cross_source_analytical_units(
        section, pool, writer_fn=_d2_writer, verify_fn=verify_sentence_provenance,
    )
    assert units, "a shared-anchor distinct-cluster pair must compose >=1 analytical unit"
    u = units[0]
    assert len(_distinct_ev_ids(u)) >= 2, (
        f"a cross-source analytical sentence must cite >=2 distinct origins; got {u!r}"
    )
    # No relation engine fired -> the fail-closed NEUTRAL connective (never a fabricated relation).
    assert LICENSED_CONNECTIVES["neutral"] in u, (
        f"with no licensing edge the connective MUST be neutral juxtaposition; got {u!r}"
    )
    assert LICENSED_CONNECTIVES["conflict"] not in u and LICENSED_CONNECTIVES["agreement"] not in u


def test_d2_connective_is_engine_licensed_conflict_on_injected_edge():
    from src.polaris_graph.generator.cross_source_synthesis import (
        compose_cross_source_analytical_units,
        LICENSED_CONNECTIVES,
    )
    section, pool = _d2_section()

    class _Edge:
        claim_cluster_ids = ("clA", "clB")

    units = compose_cross_source_analytical_units(
        section, pool, writer_fn=_d2_writer, verify_fn=verify_sentence_provenance,
        edges=[_Edge()],
    )
    assert units, "the pair must still compose with an edge present"
    assert any(LICENSED_CONNECTIVES["conflict"] in u for u in units), (
        f"an injected ContradictionEdge MUST license the conflict connective; got {units!r}"
    )


def test_d2_both_atoms_reverify_per_clause():
    """The joined analytical sentence's provenance tokens each resolve + verify against the pool (the
    frozen engine still gates iff BOTH atoms pass)."""
    from src.polaris_graph.generator.cross_source_synthesis import (
        compose_cross_source_analytical_units,
    )
    section, pool = _d2_section()
    units = compose_cross_source_analytical_units(
        section, pool, writer_fn=_d2_writer, verify_fn=verify_sentence_provenance,
    )
    assert units
    res = verify_sentence_provenance(units[0], pool)
    assert bool(getattr(res, "is_verified", False)), (
        f"the composed cross-source sentence must re-pass strict_verify; got {units[0]!r}"
    )


# ── D3 — fail-closed analyst-synthesis promote gate ─────────────────────────────────────────────────
def test_d3_promote_gate_default_off_and_requires_both_flags(monkeypatch):
    """The PROMOTE mode is default-OFF (byte-identical) and turns on ONLY when the fine promote flag AND
    the deviation-check gate (fine + coarse analyst-layer flags) are ALL on — an ungrounded synthesis
    sentence can never sneak into the body via a single loose flag or when the analyst layer is off."""
    from src.polaris_graph.generator import analyst_synthesis_deviation_check as dc

    # 1. Default (promote flag unset) -> OFF, byte-identical, regardless of the deviation-check default.
    for k in ("PG_ANALYST_SYNTHESIS_DEVIATION_CHECK", "PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED",
              "PG_SWEEP_ANALYST_SYNTHESIS"):
        monkeypatch.delenv(k, raising=False)
    assert dc.promote_grounded_enabled() is False, "default-OFF: byte-identical"

    # 2. Promote flag ON but the coarse analyst-layer kill-switch OFF -> deviation check disabled ->
    #    promote STILL OFF (promote can never activate while the analyst/deviation layer is off).
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", "1")
    monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "0")
    assert dc.deviation_check_enabled() is False
    assert dc.promote_grounded_enabled() is False, (
        "promote requires the deviation-check gate; it must stay off when the analyst layer is off"
    )

    # 3. Both promote flag AND the deviation-check gate (fine + coarse) ON -> promote is ON.
    monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_DEVIATION_CHECK", "1")
    assert dc.deviation_check_enabled() is True
    assert dc.promote_grounded_enabled() is True, "the full enable path must turn promote ON"


def test_d3_deviation_check_module_is_fail_closed_low():
    """The deviation check maps any judge fault to fail-closed LOW (NOT supported): the source text
    must document + implement the fail-closed contract so an errored/ungrounded synthesis sentence is
    dropped from the body, never promoted."""
    import inspect
    from src.polaris_graph.generator import analyst_synthesis_deviation_check as dc

    src = inspect.getsource(dc)
    assert src.lower().count("fail-closed") >= 3, (
        "the deviation check must be explicitly fail-closed on judge faults (promote-only-if-grounded)"
    )
    assert hasattr(dc, "promote_grounded_enabled") and hasattr(dc, "deviation_check_enabled")


def _d3_fixture():
    """3-index bibliography + spans for the fail-closed behavioral test."""
    bibliography = [
        {"evidence_id": "ev1", "title": "A", "url": "u1", "tier": "T1"},  # [1]
        {"evidence_id": "ev2", "title": "B", "url": "u2", "tier": "T2"},  # [2]
        {"evidence_id": "ev3", "title": "C", "url": "u3", "tier": "T1"},  # [3]
    ]
    evidence_rows = [
        {"evidence_id": "ev1",
         "direct_quote": "Automation displaced 12 percent of clerical roles in the surveyed firms."},
        {"evidence_id": "ev2",
         "direct_quote": "The study measured task completion times for warehouse pickers."},
        {"evidence_id": "ev3",
         "direct_quote": "Automation displaced 9 percent of clerical roles nationwide."},
    ]
    return bibliography, evidence_rows


def test_d3_fail_closed_drops_ungrounded_synthesis_from_body(monkeypatch):
    """EFFECT-PROVING (RED on the pre-fix KEEP-and-LABEL impl): with the D3 fail-closed gate ON, an
    ungrounded / no-source / number-inventing synthesis sentence is DROPPED from the returned body,
    and ONLY a sentence that passes BOTH frozen-engine legs (deterministic span-grounding AND the
    judge) is promoted into the body. Proves the gate is the frozen engine, not a lone judge."""
    from src.polaris_graph.generator import analyst_synthesis_deviation_check as dc

    monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_DEVIATION_CHECK", "1")
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", "1")  # D3 fail-closed ON
    # Offline-deterministic frozen-engine re-pass: run strict_verify's MECHANICAL legs only (numeric /
    # content-overlap / percent-role), skipping the network NLI leg. Production runs the default
    # (enforce) so the real NLI leg also fires; here we prove the mechanical strict_verify gate.
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    assert dc.promote_grounded_enabled() is True

    bibliography, evidence_rows = _d3_fixture()
    text = (
        # (1) GROUNDED: numbers + words match the cited span, judge says supported -> PROMOTED.
        "Automation displaced 12 percent of clerical roles in the surveyed firms [1]. "
        # (2) JUDGE-UNSUPPORTED: cited span has no 'clerical' -> judge False -> DROPPED.
        "Warehouse throughput improved dramatically after the rollout [2]. "
        # (3) NUMBER-INVENTED: judge would say supported (span has 'clerical'), but the sentence's 47
        #     is NOT in the span -> the deterministic frozen-engine leg DROPS it (not a lone judge).
        "Automation displaced 47 percent of clerical roles nationwide [3]. "
        # (4) NO-SOURCE: no resolvable [N] marker at all -> DROPPED.
        "This interpretation is offered without any cited source."
    )

    # Deterministic judge: a span mentioning 'clerical' SUPPORTS its sentence; else NOT. This makes the
    # judge PASS sentence (3) so the ONLY reason (3) drops is the deterministic number-grounding leg.
    def _judge(claim: str, span: str) -> bool:
        return "clerical" in span.lower()

    body, tel = dc.screen_synthesis_against_baskets(
        text, bibliography, evidence_rows, judge_fn=_judge,
    )

    # The grounded sentence is PROMOTED into the body with a moderate-confidence marker.
    assert "Automation displaced 12 percent of clerical roles in the surveyed firms" in body
    assert "[confidence: moderate" in body
    assert tel["synthesis_deviation_promoted_count"] == 1

    # All three failing sentences are DROPPED from the scored body (fail-closed), never labeled-in.
    assert "Warehouse throughput" not in body, "judge-unsupported sentence must be dropped from body"
    assert "47 percent" not in body, "number-inventing sentence must be dropped by the span-grounding leg"
    assert "without any cited source" not in body, "no-source sentence must be dropped from body"
    assert "[confidence: low" not in body and "[confidence: no-source" not in body, (
        "fail-closed mode DROPS failing sentences; it must NOT keep-and-label them in the body"
    )
    assert tel["synthesis_deviation_dropped_count"] == 3
    assert tel["synthesis_deviation_labeled_count"] == 0
    assert tel["synthesis_deviation_unresolved_count"] == 0


def test_d3_promote_requires_real_frozen_engine_repass(monkeypatch):
    """EFFECT-PROVING (Codex iter-4 P0 + P1): a promoted synthesis sentence must clear the REAL frozen
    ``verify_sentence_provenance`` engine (a rebuilt ``[#ev:id:start-end]`` token per cited source), not
    just the cheap span-grounding pre-check + the Sentinel judge. This case is engineered so the cheap
    ``_span_grounds_sentence`` leg PASSES and the injected D8 judge PASSES, yet the REAL engine DROPS the
    sentence on a strict_verify leg (percent-role: a '30%' claim whose cited span carries only the bare
    integer '30', never a percent). If the D3 gate did NOT call verify_sentence_provenance (the pre-fix
    hole), this sentence would be PROMOTED — so this test is RED on the reverted fix. A genuinely
    percent-grounded control sentence IS promoted, proving the engine is not just rejecting everything."""
    from src.polaris_graph.generator import analyst_synthesis_deviation_check as dc

    monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_DEVIATION_CHECK", "1")
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", "1")  # D3 fail-closed ON
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")  # mechanical strict_verify legs only
    assert dc.promote_grounded_enabled() is True

    bibliography = [
        {"evidence_id": "ev1", "title": "A", "url": "u1", "tier": "T1"},  # [1] percent-role FAIL
        {"evidence_id": "ev2", "title": "B", "url": "u2", "tier": "T1"},  # [2] percent-grounded control
    ]
    evidence_rows = [
        # Span carries the bare integer '30' (twice) but NO percent — 'clerical' present so the judge
        # PASSES; the ONLY reason to drop the '30%' claim is the real strict_verify percent-role leg.
        {"evidence_id": "ev1",
         "direct_quote": "Adoption of clerical automation reached 30 in cohort 30 of the sample."},
        # Span states the percent honestly -> the real engine PROMOTES this control.
        {"evidence_id": "ev2",
         "direct_quote": "Adoption of clerical automation reached 30% across the surveyed firms."},
    ]

    text = (
        # (A) '30%' claim but the cited span has only bare '30' -> real engine drops (percent-role);
        #     cheap span-grounding + the judge both PASS, so only verify_sentence_provenance can catch it.
        "Adoption of clerical automation reached 30% of firms [1]. "
        # (B) '30%' claim whose cited span states 30% -> the real engine PROMOTES it.
        "Adoption of clerical automation reached 30% across the surveyed firms [2]."
    )

    def _judge(claim: str, span: str) -> bool:
        return "clerical" in span.lower()  # PASSES for both spans -> isolates the frozen-engine leg

    body, tel = dc.screen_synthesis_against_baskets(
        text, bibliography, evidence_rows, judge_fn=_judge,
    )

    # (A) is DROPPED by the REAL engine (percent-role), even though the judge + cheap span-ground pass.
    assert "reached 30% of firms" not in body, (
        "a '30%' claim whose cited span carries only bare '30' must be DROPPED by the real "
        "verify_sentence_provenance percent-role leg — the D3 gate must call the frozen engine"
    )
    # (B) the honestly percent-grounded control IS promoted -> the engine is not rejecting everything.
    assert "across the surveyed firms" in body
    assert "[confidence: moderate" in body
    assert tel["synthesis_deviation_promoted_count"] == 1
    assert tel["synthesis_deviation_dropped_count"] == 1


def test_d3_promote_off_is_keep_and_label_not_drop(monkeypatch):
    """CONTRAST / byte-identical guard: with the D3 gate OFF (promote flag unset), the SAME input is
    advisory KEEP-and-LABEL — the failing sentences are LABELED and RETAINED, nothing is dropped."""
    from src.polaris_graph.generator import analyst_synthesis_deviation_check as dc

    monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_DEVIATION_CHECK", "1")
    monkeypatch.delenv("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", raising=False)  # D3 OFF
    assert dc.promote_grounded_enabled() is False

    bibliography, evidence_rows = _d3_fixture()
    text = (
        "Warehouse throughput improved dramatically after the rollout [2]. "
        "This interpretation is offered without any cited source."
    )

    def _judge(claim: str, span: str) -> bool:
        return "clerical" in span.lower()

    body, tel = dc.screen_synthesis_against_baskets(
        text, bibliography, evidence_rows, judge_fn=_judge,
    )
    # Legacy advisory: BOTH sentences are RETAINED (never dropped), each LABELED.
    assert "Warehouse throughput" in body and "without any cited source" in body
    assert "[confidence: low" in body and "[confidence: no-source" in body
    assert tel["synthesis_deviation_dropped_count"] == 0


def test_d3_promote_rescreens_prelabeled_confidence_sentence(monkeypatch):
    """P1 (#1344) LABEL-BYPASS: in PROMOTE mode a sentence that ALREADY carries a ``[confidence:...]``
    marker does NOT get an idempotent free pass — it is re-screened on its BARE prose through BOTH
    frozen-engine legs. An ungrounded pre-labeled sentence is DROPPED (never survives as a hedged body
    claim); a grounded pre-labeled sentence is re-promoted with a FRESH moderate marker and the stale
    marker stripped (no double marker). RED on the pre-fix impl (which appended the pre-labeled sentence
    unchanged BEFORE the promote gate)."""
    from src.polaris_graph.generator import analyst_synthesis_deviation_check as dc

    monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_DEVIATION_CHECK", "1")
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", "1")  # D3 fail-closed ON
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")  # offline mechanical strict_verify only
    assert dc.promote_grounded_enabled() is True

    bibliography, evidence_rows = _d3_fixture()
    text = (
        # GROUNDED but pre-labeled low: must be RE-PROMOTED (marker refreshed), not passed through.
        "Automation displaced 12 percent of clerical roles in the surveyed firms [1] [confidence: low]. "
        # UNGROUNDED but pre-labeled low: must be DROPPED, not admitted as a hedged claim.
        "Warehouse throughput improved dramatically after the rollout [2] [confidence: low]."
    )

    def _judge(claim: str, span: str) -> bool:
        return "clerical" in span.lower()

    body, tel = dc.screen_synthesis_against_baskets(
        text, bibliography, evidence_rows, judge_fn=_judge,
    )

    # The ungrounded pre-labeled sentence is GONE from the body (the bypass is closed).
    assert "Warehouse throughput" not in body, (
        "a pre-labeled [confidence:] ungrounded sentence must NOT bypass the D3 promote gate"
    )
    # The grounded pre-labeled sentence survives, re-promoted to moderate, the stale marker stripped.
    assert "Automation displaced 12 percent of clerical roles in the surveyed firms" in body
    assert "[confidence: moderate" in body
    assert "[confidence: low" not in body, (
        "the stale pre-existing marker must be stripped and re-screened, never doubled or passed through"
    )
    assert tel["synthesis_deviation_promoted_count"] == 1
    assert tel["synthesis_deviation_dropped_count"] == 1


def test_d3_caller_fails_closed_on_screen_exception_under_promote(monkeypatch):
    """P0 (#1344) CALLER FAIL-OPEN: if the deviation SCREEN itself raises (wiring / import / checker
    fault), the synthesis was NEVER gated. Under PROMOTE mode the caller helper MUST fail CLOSED — DROP
    the whole synthesis block (return "") — never return the ungated text into the scored body. In
    legacy advisory mode it ships the text UNLABELED (prior behavior, additive check never aborts the
    report). RED on the pre-fix caller (which returned `cleaned` unconditionally on any screen
    exception)."""
    from src.polaris_graph.generator import analyst_synthesis as a_syn
    from src.polaris_graph.generator import analyst_synthesis_deviation_check as dc

    def _boom(*_a, **_k):
        raise RuntimeError("simulated deviation-screen wiring fault")

    # The helper does `from ...deviation_check import screen_synthesis_against_baskets` at call time, so
    # patching the module attribute makes the real screen raise (exercises the fail-closed except path).
    monkeypatch.setattr(dc, "screen_synthesis_against_baskets", _boom)

    bibliography, evidence_rows = _d3_fixture()
    ungated = "This ungrounded interpretation would ship straight into the scored body [2]."

    monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_DEVIATION_CHECK", "1")

    # PROMOTE ON -> fail CLOSED: the ungated synthesis is DROPPED to empty.
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", "1")
    out_promote = a_syn._apply_synthesis_deviation_screen(
        ungated, bibliography, evidence_rows, None,
    )
    assert out_promote == "", (
        "under promote mode a screen exception must DROP the ungated synthesis (fail-closed), "
        "never return the ungated body text"
    )
    assert a_syn._SYNTHESIS_TELEMETRY.get("synthesis_deviation_promote_failclosed_drop_count", 0) >= 1
    assert a_syn._SYNTHESIS_TELEMETRY.get("synthesis_deviation_check_error_count", 0) >= 1

    # PROMOTE OFF (legacy advisory) -> the additive check never aborts: text ships UNLABELED, not dropped.
    monkeypatch.delenv("PG_ANALYST_SYNTHESIS_PROMOTE_GROUNDED", raising=False)
    out_legacy = a_syn._apply_synthesis_deviation_screen(
        ungated, bibliography, evidence_rows, None,
    )
    assert out_legacy == ungated, (
        "legacy advisory mode must ship the text UNLABELED on a screen fault (prior additive behavior)"
    )


# ── D4 — facet-cluster the enrichment breadth surface ──────────────────────────────────────────────
def test_d4_routes_members_under_matching_facet_and_conserves_keep_all():
    from src.polaris_graph.generator.weighted_enrichment import (
        route_enrichment_members_by_facet,
    )
    facet_titles = [
        "Labor-Market Displacement Estimates",
        "Sectoral Productivity Effects",
        "Wage Inequality Evidence",
    ]
    text = {
        "e1": "Automation drove labor displacement across clerical roles",
        "e2": "Sectoral productivity rose with robotics adoption",
        "e3": "Wage inequality widened between skill tiers",
        "e4": "An unrelated note about supply-chain logistics weather",  # matches no facet
    }
    ids = ["e1", "e2", "e3", "e4"]
    routed, residual = route_enrichment_members_by_facet(
        ids, facet_titles, text_of=lambda e: text[e],
    )
    routed_map = dict(routed)
    assert "e1" in routed_map.get("Labor-Market Displacement Estimates", []), (
        f"e1 must route under the displacement facet; got {routed!r}"
    )
    assert "e2" in routed_map.get("Sectoral Productivity Effects", [])
    assert "e3" in routed_map.get("Wage Inequality Evidence", [])
    assert "e4" in residual, f"an unmatched member must land in residual (kept); got residual={residual!r}"

    # KEEP-ALL INVARIANT: routed ∪ residual == input, no drop, no duplicate.
    placed = [e for _t, members in routed for e in members] + list(residual)
    assert sorted(placed) == sorted(ids), (
        f"keep-all violated: input={ids} placed={placed}"
    )
    assert len(placed) == len(set(placed)), "a member must not be placed twice"


def test_d4_builds_per_facet_plans_plus_residual_and_conserves_ev_ids():
    from src.polaris_graph.generator.weighted_enrichment import (
        build_weighted_enrichment_plans_by_facet,
        _ENRICHMENT_FACET_TITLE_PREFIX,
        _ENRICHMENT_RESIDUAL_TITLE,
    )

    class _SP:
        def __init__(self, title, focus, ev_ids):
            self.title = title
            self.focus = focus
            self.ev_ids = list(ev_ids)

    facet_titles = ["Labor-Market Displacement Estimates", "Wage Inequality Evidence"]
    text = {
        "e1": "labor displacement in clerical roles",
        "e2": "wage inequality across tiers",
        "e3": "off-topic weather logistics note",
    }
    plans = build_weighted_enrichment_plans_by_facet(
        ["e1", "e2", "e3"], facet_titles,
        section_plan_cls=_SP, text_of=lambda e: text[e],
    )
    titles = [p.title for p in plans]
    assert any(t.startswith(_ENRICHMENT_FACET_TITLE_PREFIX) for t in titles), (
        f"D4 must emit per-facet routed section plans (not one flat dump); got {titles!r}"
    )
    assert _ENRICHMENT_RESIDUAL_TITLE in titles, "the residual block must exist for the off-topic member"
    # KEEP-ALL: the concatenation of all plan ev_ids equals the input (nothing dropped).
    all_ids = [e for p in plans for e in p.ev_ids]
    assert sorted(all_ids) == ["e1", "e2", "e3"], f"keep-all violated across plans; got {all_ids!r}"


def test_d4_default_off_falls_back_to_single_flat_plan():
    """With NO facet titles the builder returns a single flat plan titled the legacy enrichment title
    (byte-identical presentation to today)."""
    from src.polaris_graph.generator.weighted_enrichment import (
        build_weighted_enrichment_plans_by_facet,
        _ENRICHMENT_TITLE,
    )

    class _SP:
        def __init__(self, title, focus, ev_ids):
            self.title = title
            self.focus = focus
            self.ev_ids = list(ev_ids)

    plans = build_weighted_enrichment_plans_by_facet(
        ["e1", "e2"], [], section_plan_cls=_SP, text_of=lambda e: "anything",
    )
    assert len(plans) == 1 and plans[0].title == _ENRICHMENT_TITLE, (
        f"no facets -> single flat legacy plan (byte-identical); got {[p.title for p in plans]!r}"
    )
    assert sorted(plans[0].ev_ids) == ["e1", "e2"], "keep-all: all members in the flat plan"


# ── D2 — CALLER-WIRING integration (the gate, not the helper) ──────────────────────────────────────
def test_d2_cross_source_pass_is_wired_into_compose_section_per_basket(monkeypatch):
    """INTEGRATION EFFECT (Codex P1): drive the PRODUCTION seam
    `verified_compose._compose_section_per_basket` under `PG_CROSS_SOURCE_SYNTHESIS`. With the flag ON
    the section gains a cross-source analytical sentence (two distinct `[#ev]` tokens joined by the
    engine-licensed neutral connective); with the flag OFF the output is byte-identical (no analytical
    unit). If the caller wiring is reverted, this FAILS — the direct-helper unit test would not."""
    from src.polaris_graph.generator.verified_compose import _compose_section_per_basket
    from src.polaris_graph.generator.cross_source_synthesis import LICENSED_CONNECTIVES

    section, pool = _d2_section()

    monkeypatch.setenv("PG_CROSS_SOURCE_SYNTHESIS", "0")  # OFF (explicit kill-switch; default is now ON per cov C2)
    off = _compose_section_per_basket(
        section, pool, writer_fn=_d2_writer, verify_fn=verify_sentence_provenance,
    )
    monkeypatch.setenv("PG_CROSS_SOURCE_SYNTHESIS", "1")  # ON
    on = _compose_section_per_basket(
        section, pool, writer_fn=_d2_writer, verify_fn=verify_sentence_provenance,
    )

    neutral = LICENSED_CONNECTIVES["neutral"]
    off_has_analytical = any(neutral in u for u in off)
    on_has_analytical = any(neutral in u for u in on)
    assert not off_has_analytical, "OFF path must NOT emit a cross-source analytical unit (byte-identical)"
    assert on_has_analytical, (
        f"ON path must emit the wired cross-source analytical unit via the caller; off={off!r} on={on!r}"
    )
    assert len(on) > len(off), "the cross-source pass is ADDITIVE (keep-all): it only appends units"


def test_d2_conflict_connective_wired_through_caller_edges(monkeypatch):
    """INTEGRATION: a ContradictionEdge threaded into `_compose_section_per_basket(edges=...)` licenses
    the conflict connective on the wired analytical unit — proving `edges` is really passed through."""
    from src.polaris_graph.generator.verified_compose import _compose_section_per_basket
    from src.polaris_graph.generator.cross_source_synthesis import LICENSED_CONNECTIVES

    section, pool = _d2_section()

    class _Edge:
        claim_cluster_ids = ("clA", "clB")

    monkeypatch.setenv("PG_CROSS_SOURCE_SYNTHESIS", "1")
    on = _compose_section_per_basket(
        section, pool, writer_fn=_d2_writer, verify_fn=verify_sentence_provenance,
        edges=[_Edge()],
    )
    assert any(LICENSED_CONNECTIVES["conflict"] in u for u in on), (
        f"an injected ContradictionEdge must license the conflict connective through the caller; got {on!r}"
    )


# ── D4 — RENDER-GATE integration (routed plans must fire FIX-K) ─────────────────────────────────────
def test_d4_facet_and_residual_plans_are_recognized_by_the_fixk_render_gate():
    """INTEGRATION EFFECT (Fable P1 + Codex P1): every plan the facet builder emits — per-facet AND
    residual — must be recognized by `is_enrichment_section`, the exact gate `multi_section_generator`
    keys the FIX-K deterministic verified-span render on. On the pre-fix exact-title-only gate the
    facet-titled plans return False and silently collapse to the distill+LLM 590-in/0-cited path; this
    test FAILS there and PASSES once the gate matches the shared enrichment focus."""
    from src.polaris_graph.generator.weighted_enrichment import (
        build_weighted_enrichment_plans_by_facet,
        is_enrichment_section,
        _ENRICHMENT_FACET_TITLE_PREFIX,
        _ENRICHMENT_RESIDUAL_TITLE,
    )

    class _SP:
        def __init__(self, title, focus, ev_ids):
            self.title = title
            self.focus = focus
            self.ev_ids = list(ev_ids)

    facet_titles = ["Labor-Market Displacement Estimates", "Wage Inequality Evidence"]
    text = {
        "e1": "labor displacement in clerical roles",
        "e2": "wage inequality across tiers",
        "e3": "off-topic weather logistics note",  # -> residual
    }
    plans = build_weighted_enrichment_plans_by_facet(
        ["e1", "e2", "e3"], facet_titles,
        section_plan_cls=_SP, text_of=lambda e: text[e],
    )
    assert plans, "the builder must emit plans for a non-empty facet corpus"
    # EVERY routed plan (facet + residual) must fire FIX-K — otherwise the paid slate (facet-route ON
    # + verified-span render ON) drops the facet plans to the LLM collapse path.
    for p in plans:
        assert is_enrichment_section(p), (
            f"routed enrichment plan {p.title!r} must be recognized by the FIX-K render gate"
        )
    titles = [p.title for p in plans]
    assert any(t.startswith(_ENRICHMENT_FACET_TITLE_PREFIX) for t in titles)
    assert _ENRICHMENT_RESIDUAL_TITLE in titles


def test_d4_non_enrichment_section_is_not_touched_by_fixk_gate():
    """The FIX-K gate stays SCOPED: a normal body/contract section (no enrichment focus, ordinary
    title) is NEVER matched, so its render is byte-identical."""
    from src.polaris_graph.generator.weighted_enrichment import is_enrichment_section

    class _SP:
        def __init__(self, title, focus):
            self.title = title
            self.focus = focus

    assert not is_enrichment_section(_SP("Key Findings", "the report's key findings"))
    assert not is_enrichment_section(_SP("Background", ""))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
