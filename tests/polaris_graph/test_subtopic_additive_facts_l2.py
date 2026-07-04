"""I-deepfix-001 #1344 (Item 11) — L2 ADDITIVE DISTINCT-FACT surfacing.

L2 sub-topic decomposition used to surface a basket's extra distinct facts ONLY as a per-basket
FALLBACK (``build_verified_span_draft_multi``) — it fired only when the abstractive winner's prose
FAILED strict_verify. On the SUCCESS path those extra facts never rendered. ``compose_distinct_fact_units``
makes L2 ADDITIVE: after the headline is kept, it surfaces the DISTINCT numeric facts a basket already
grounds that the abstractive paraphrase DROPPED (absolute counts, currency, dates, multipliers — the
bare integers the writer's numeric-completeness gate does NOT force into the paraphrase). Each surfaced
fact is a VERBATIM span slice re-verified by the UNCHANGED strict_verify, ADDITIVE to (never replacing)
the headline.

FAITHFULNESS: every surfaced sentence must PASS the REAL ``verify_sentence_provenance`` and land within
the basket's own member regions — the test uses the real engine, never a stub, for the forced positives.

NO DUPLICATION (the operator's hard constraint): a unit is surfaced ONLY when it carries a number
(comma-normalized) absent from the composed headline. A fact whose numbers are all already in the
headline is skipped. Any comma-normalization collision can only cause a SKIP (under-emit), never a
false surface.

RED/GREEN: default-OFF (PG_SUBTOPIC_ADDITIVE_FACTS=0) is byte-identical (the missing fact does NOT
render); default-ON surfaces it. Offline logic tests only — no LLM, no network.
"""
import re

from types import SimpleNamespace

from src.polaris_graph.generator.provenance_generator import (
    verify_sentence_provenance,
)
from src.polaris_graph.generator.verified_compose import (
    _canon_number,
    _compose_section_per_basket,
    _subtopic_additive_facts_enabled,
    build_short_member_sentence,
    compose_distinct_fact_units,
)
from src.polaris_graph.synthesis.credibility_pass import (
    MEMBER_TIER_ENTAILMENT_VERIFIED,
)

# ── fixture builders (mirror test_companion_figure_and_degraded_disclosure_wave3) ──────────────


def _member(eid, quote, *, span_verdict="SUPPORTS", weight=0.9):
    return SimpleNamespace(
        evidence_id=eid,
        direct_quote=quote,
        span_verdict=span_verdict,
        member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
        entailment_judge_unavailable=False,
        credibility_weight=weight,
        origin_cluster_id=eid,
        source_url="https://example.org/" + eid,
        source_tier="T1",
        authority_score=weight,
        span=(0, len(quote)),
    )


def _basket(members, *, subject="the workforce estimate", claim_text="AI workforce impact"):
    return SimpleNamespace(
        supporting_members=members,
        subject=subject,
        claim_text=claim_text,
        predicate="",
        claim_cluster_id="cluster_1",
        refuter_cluster_ids=(),
        weight_mass=1.0,
        total_clustered_origin_count=len(members),
        verified_support_origin_count=len(members),
        basket_verdict="full",
    )


def _pool(*members):
    return {m.evidence_id: {"direct_quote": m.direct_quote} for m in members}


def _short_writer(evidence_pool):
    """The DEFAULT deterministic short writer (first sentence of the strongest member) — the same
    writer_fn the non-abstractive production path uses. It keeps ONLY the first sentence, dropping the
    later distinct facts — exactly the M<N gap the additive pass fills."""
    return lambda b, _p: build_short_member_sentence(b, evidence_pool)


# The M<N shape: sentence 1 states a substantive percent (1.8%); sentence 2 states DISTINCT facts —
# an absolute count (400,000) and a date (2030) — that a one-sentence headline drops. Both verbatim
# inside ONE member's span.
_TWO_FACT_QUOTE = (
    "Sector output rose 1.8% last year. "
    "AI is projected to displace 400,000 manufacturing workers by 2030."
)


# ── forced positive: RED (OFF) / GREEN (ON) via the real section producer ──────────────────────


def test_additive_surfaces_dropped_distinct_fact_red_green(monkeypatch):
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "0")  # isolate the additive pass
    member = _member("ev_ndl", _TWO_FACT_QUOTE)
    basket = _basket([member])
    pool = _pool(member)

    # GREEN: the additive pass ON surfaces the dropped 400,000/2030 fact ADDITIVE to the headline.
    monkeypatch.setenv("PG_SUBTOPIC_ADDITIVE_FACTS", "1")
    on = _compose_section_per_basket(
        [basket], pool, writer_fn=_short_writer(pool), verify_fn=verify_sentence_provenance,
    )
    assert len(on) == 2, on
    headline, extra = on[0], on[1]
    assert "1.8%" in headline and "400,000" not in headline
    assert "400,000" in extra
    # ADDITIVE: the headline is untouched; the extra fact is appended, never replacing it.
    # The surfaced unit re-passes the REAL strict_verify (faithful by construction — right offsets).
    res = verify_sentence_provenance(extra, pool)
    assert res.is_verified, (extra, getattr(res, "failure_reasons", None))

    # RED: the additive pass OFF is byte-identical — the dropped fact does NOT render.
    monkeypatch.setenv("PG_SUBTOPIC_ADDITIVE_FACTS", "0")
    off = _compose_section_per_basket(
        [basket], pool, writer_fn=_short_writer(pool), verify_fn=verify_sentence_provenance,
    )
    assert len(off) == 1, off
    assert off[0] == on[0]  # the headline is identical ON vs OFF


# ── producer-level: the ABSTRACTIVE success-path scenario (paraphrase headline drops the count) ──


def test_producer_surfaces_fact_dropped_by_abstractive_paraphrase(monkeypatch):
    monkeypatch.setenv("PG_SUBTOPIC_ADDITIVE_FACTS", "1")
    member = _member("ev_ndl", _TWO_FACT_QUOTE)
    basket = _basket([member])
    pool = _pool(member)
    # Simulate the abstractive winner: ONE paraphrase per member carrying the whole-quote token; it
    # keeps the SUBSTANTIVE numeric (1.8%, forced by the writer completeness gate) but DROPS the bare
    # integer facts (400,000 / 2030) the gate does not require.
    paraphrase = f"Sector output climbed by 1.8% over the prior year [#ev:ev_ndl:0-{len(_TWO_FACT_QUOTE)}]."

    units = compose_distinct_fact_units(
        basket, pool, paraphrase, verify_fn=verify_sentence_provenance,
    )
    assert len(units) == 1, units
    extra = units[0]
    # VERBATIM slice — the source's own words, NO connective / lead-in / aggregate predicate.
    assert extra.split(" [#ev:")[0] == "AI is projected to displace 400,000 manufacturing workers by 2030"
    # The token indexes a real "400,000" occurrence in the quote (true-offset guarantee).
    m = re.search(r"\[#ev:ev_ndl:(\d+)-(\d+)\]", extra)
    assert m, extra
    s, e = int(m.group(1)), int(m.group(2))
    assert "400,000" in _TWO_FACT_QUOTE[s:e]
    # Re-passes the REAL strict_verify against the pool.
    assert verify_sentence_provenance(extra, pool).is_verified


# ── no-duplication guarantees ──────────────────────────────────────────────────────────────────


def test_no_duplication_when_headline_already_covers_the_number(monkeypatch):
    monkeypatch.setenv("PG_SUBTOPIC_ADDITIVE_FACTS", "1")
    member = _member("ev_ndl", _TWO_FACT_QUOTE)
    basket = _basket([member])
    pool = _pool(member)
    # A headline that ALREADY states BOTH the 400,000 count and the 2030 date -> nothing to add.
    headline_both = (
        "Output rose 1.8% and AI may displace 400,000 workers by 2030 "
        f"[#ev:ev_ndl:0-{len(_TWO_FACT_QUOTE)}]."
    )
    units = compose_distinct_fact_units(
        basket, pool, headline_both, verify_fn=verify_sentence_provenance,
    )
    assert units == []


def test_no_duplication_comma_normalized_number(monkeypatch):
    # "400000" in the headline and "400,000" in the span are the SAME figure -> not surfaced.
    monkeypatch.setenv("PG_SUBTOPIC_ADDITIVE_FACTS", "1")
    member = _member("ev_ndl", _TWO_FACT_QUOTE)
    basket = _basket([member])
    pool = _pool(member)
    # Headline carries BOTH numbers of both sentences (1.8 and the count as an un-separated 400000):
    # only the comma-normalization decides whether the 400,000 span sentence looks novel. It must not.
    headline_nocomma = (
        "Output rose 1.8% and AI may displace 400000 workers by 2030 "
        f"[#ev:ev_ndl:0-{len(_TWO_FACT_QUOTE)}]."
    )
    units = compose_distinct_fact_units(
        basket, pool, headline_nocomma, verify_fn=verify_sentence_provenance,
    )
    assert units == []
    assert _canon_number("400,000") == _canon_number("400000") == "400000"


# ── faithfulness negative controls ──────────────────────────────────────────────────────────────


def test_verify_failure_drops_the_unit():
    member = _member("ev_ndl", _TWO_FACT_QUOTE)
    basket = _basket([member])
    pool = _pool(member)
    headline = "Sector output rose 1.8% last year [#ev:ev_ndl:0-33]."

    def _always_fail(sentence, _pool):
        return SimpleNamespace(sentence=sentence, is_verified=False)

    units = compose_distinct_fact_units(basket, pool, headline, verify_fn=_always_fail)
    assert units == []


def test_never_invents_a_figure_absent_from_every_span(monkeypatch):
    # The 400,000 appears ONLY in the (fabricated) headline, NEVER in a member span: the pass scans
    # real direct_quotes and can only ever emit a member's own sentence, so it surfaces nothing.
    monkeypatch.setenv("PG_SUBTOPIC_ADDITIVE_FACTS", "1")
    member = _member("ev_x", "Sector output rose 1.8% last year.")
    basket = _basket([member])
    pool = _pool(member)
    fabricated = "Output rose 1.8%; some claim 400,000 jobs lost [#ev:ev_x:0-20]."
    units = compose_distinct_fact_units(basket, pool, fabricated, verify_fn=verify_sentence_provenance)
    assert units == []


def test_qualitative_only_fact_is_not_surfaced(monkeypatch):
    # Numeric-anchored scope (honest boundary): a distinct fact carrying NO new number is NOT surfaced
    # by this pass (under-emit is the safe direction — never a duplicate). The qualifier-elaboration
    # pass handles the qualitative case separately.
    monkeypatch.setenv("PG_SUBTOPIC_ADDITIVE_FACTS", "1")
    quote = "Output rose 1.8% last year. The reforms were widely criticised by unions."
    member = _member("ev_q", quote)
    basket = _basket([member])
    pool = _pool(member)
    headline = f"Output rose 1.8% last year [#ev:ev_q:0-30]."
    units = compose_distinct_fact_units(basket, pool, headline, verify_fn=verify_sentence_provenance)
    assert units == []


# ── byte-identical OFF ──────────────────────────────────────────────────────────────────────────


def test_off_is_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "0")
    member = _member("ev_ndl", _TWO_FACT_QUOTE)
    basket = _basket([member])
    pool = _pool(member)

    monkeypatch.setenv("PG_SUBTOPIC_ADDITIVE_FACTS", "1")
    on = _compose_section_per_basket(
        [basket], pool, writer_fn=_short_writer(pool), verify_fn=verify_sentence_provenance,
    )
    monkeypatch.setenv("PG_SUBTOPIC_ADDITIVE_FACTS", "0")
    off = _compose_section_per_basket(
        [basket], pool, writer_fn=_short_writer(pool), verify_fn=verify_sentence_provenance,
    )
    assert not _subtopic_additive_facts_enabled()
    assert len(off) == 1 and len(on) == 2
    assert off[0] == on[0]


def test_default_off_and_explicit_on(monkeypatch):
    # DEFAULT-OFF (LAW VI): unset or blank stays OFF (a new content-surfacing pass is never silently
    # on); only an explicit 1/true/on/yes turns it ON.
    monkeypatch.delenv("PG_SUBTOPIC_ADDITIVE_FACTS", raising=False)
    assert not _subtopic_additive_facts_enabled()
    monkeypatch.setenv("PG_SUBTOPIC_ADDITIVE_FACTS", "")
    assert not _subtopic_additive_facts_enabled()
    monkeypatch.setenv("PG_SUBTOPIC_ADDITIVE_FACTS", "1")
    assert _subtopic_additive_facts_enabled()
