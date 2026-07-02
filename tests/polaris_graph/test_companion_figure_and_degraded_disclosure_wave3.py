"""I-deepfix-001 Wave-3 (#1344) — COMPANION-FIGURE COMPOSE (PART 1) + DEGRADED-VERIFY
HONEST DISCLOSURE (PART 2 ARM B).

PART 1 — the composed headline states ONE percent while the SAME SUPPORTS member's own
verified span carries a materially-different SAME-KIND companion percent the headline
OMITS (the drb_72 one-sidedness). ``compose_companion_figure_units`` surfaces it as a
VERBATIM slice of that member's direct_quote, tagged with the member's REAL global offsets,
re-verified by the UNCHANGED strict_verify. The gate is byte-for-byte the primacy advisory
gate (shared measure-stem + ``_PRIMACY_MIN_ABS_GAP_PCT`` + ``_PRIMACY_MIN_RATIO``), so the
surfaced companion and the advisory label always agree. Default-ON; OFF => byte-identical.

PART 2 ARM B — a basket with NO ENTAILMENT_VERIFIED span but >=1 DETERMINISTIC_ONLY member
(the entailment judge 429'd / timed out this run) must disclose "verification incomplete: N
source(s) deterministically ground this claim but entailment verification was unavailable"
instead of the misleading bare "insufficient verified evidence" gap. Only the LABEL changes;
no DETERMINISTIC_ONLY prose is ever promoted into verified text. Default-ON; OFF =>
byte-identical (the bare gap for both causes).

Each behavior gets: a FORCED-POSITIVE (the fix acts), faithfulness NEGATIVE-CONTROLS (legit
cases untouched / never-fabricate), and a byte-identical-OFF assertion.

Offline logic tests only — the drb_72 fresh-run confirmation (do the 46%/47% companions sit
inside the SUPPORTS members' direct_quotes of the SAME basket?) is a fresh-run acceptance
item, not a build blocker (see the design OPEN_QUESTIONS + open_items).
"""
from types import SimpleNamespace

from src.polaris_graph.generator.contract_section_runner import (
    _is_gap_disclosure_sentence,
)
from src.polaris_graph.generator.provenance_generator import (
    verify_sentence_provenance,
)
from src.polaris_graph.generator.multi_section_generator import (
    _repair_untokened_draft,
)
from src.polaris_graph.generator.verified_compose import (
    _compose_one_basket,
    _compose_section_per_basket,
    _deterministic_only_member_count,
    _judge_unavailable_member_count,
    _no_verified_span_disclosure,
    build_short_member_sentence,
    compose_companion_figure_units,
    partition_composed_disclosures,
    render_degraded_disclosures,
)
from src.polaris_graph.synthesis.credibility_pass import (
    MEMBER_TIER_DETERMINISTIC_ONLY,
    MEMBER_TIER_ENTAILMENT_VERIFIED,
    MEMBER_TIER_UNVERIFIED,
)

# ── fixture builders ─────────────────────────────────────────────────────────


def _member(
    eid,
    quote,
    *,
    span_verdict="SUPPORTS",
    member_tier=MEMBER_TIER_ENTAILMENT_VERIFIED,
    weight=0.9,
    judge_unavailable=False,
):
    return SimpleNamespace(
        evidence_id=eid,
        direct_quote=quote,
        span_verdict=span_verdict,
        member_tier=member_tier,
        # I-deepfix-001 Wave-3 P1b (#1344): the durable judge-outage signal the ARM-B disclosure gates on.
        entailment_judge_unavailable=judge_unavailable,
        credibility_weight=weight,
        origin_cluster_id=eid,
        source_url="https://example.org/" + eid,
        source_tier="T1",
        authority_score=weight,
        span=(0, len(quote)),
    )


def _basket(members, *, subject="the exposure estimate", claim_text="AI job exposure"):
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
    """The DEFAULT deterministic short writer (first sentence of the strongest member) — the
    same writer_fn the non-abstractive production path uses. Drops the later same-kind figures,
    exactly the one-sidedness PART 1 repairs."""
    return lambda b, _p: build_short_member_sentence(b, evidence_pool)


# The drb_72 one-sidedness shape: headline 1.8%, companion 46%, SAME kind (both "exposed"),
# MATERIALLY different (gap 44.2pp, ratio 25x) — both verbatim inside ONE member's span.
_TWO_FIGURE_QUOTE = (
    "AI could expose 1.8% of jobs to automation. "
    "Just over 46% of tasks could be exposed."
)


# ── PART 1: forced-positive ──────────────────────────────────────────────────


def test_part1_forced_positive_surfaces_omitted_companion_percent(monkeypatch):
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "1")
    member = _member("ev_eloundou", _TWO_FIGURE_QUOTE)
    basket = _basket([member])
    pool = _pool(member)

    out = _compose_section_per_basket(
        [basket], pool,
        writer_fn=_short_writer(pool), verify_fn=verify_sentence_provenance,
    )

    # BOTH the 1.8% headline AND a 46% companion are rendered (was: 1.8% only).
    assert len(out) == 2, out
    headline, companion = out[0], out[1]
    assert "1.8%" in headline and "46%" not in headline
    assert "46%" in companion
    # The companion carries a valid [#ev:eid:s-e] token that INDEXES the 46% sentence.
    assert "[#ev:ev_eloundou:" in companion
    # ROUND-TRIP: the surfaced companion re-passes the REAL strict_verify against the pool
    # (proves the offsets are correct — faithful by construction, never a wrong-offset fabrication).
    res = verify_sentence_provenance(companion, pool)
    assert res.is_verified, (companion, getattr(res, "failure_reasons", None))


def test_part1_producer_returns_verbatim_companion_only(monkeypatch):
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "1")
    member = _member("ev_eloundou", _TWO_FIGURE_QUOTE)
    basket = _basket([member])
    pool = _pool(member)
    headline = build_short_member_sentence(basket, pool)  # the 1.8% headline only

    units = compose_companion_figure_units(
        basket, pool, headline, verify_fn=verify_sentence_provenance,
    )
    assert len(units) == 1
    companion = units[0]
    # VERBATIM slice — the source's own words, NO connective / lead-in / aggregate predicate.
    assert companion.split(" [#ev:")[0] == "Just over 46% of tasks could be exposed"


# ── PART 1: faithfulness negative controls ───────────────────────────────────


def test_part1_never_invents_a_figure_absent_from_every_span(monkeypatch):
    # (i) the 46% appears ONLY in the (hypothetical) composed prose, NEVER in a member span:
    # the pass scans real direct_quotes, so it can surface nothing to invent.
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "1")
    member = _member("ev_x", "AI could expose 1.8% of jobs to automation.")
    basket = _basket([member])
    pool = _pool(member)
    # A composed headline that (fabricated) mentions 46% — the producer must not echo it, because
    # no member span carries 46%.
    fabricated_headline = "AI could expose 1.8% of jobs; some claim 46% of tasks [#ev:ev_x:0-20]."
    units = compose_companion_figure_units(
        basket, pool, fabricated_headline, verify_fn=verify_sentence_provenance,
    )
    assert units == []


def test_part1_verify_failure_drops_the_companion(monkeypatch):
    # (ii) a companion that qualifies on the primacy gate is STILL dropped if strict_verify fails —
    # the fix can only ADD a strict_verify-PASSED span, never bypass the engine.
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "1")
    member = _member("ev_eloundou", _TWO_FIGURE_QUOTE)
    basket = _basket([member])
    pool = _pool(member)
    headline = build_short_member_sentence(basket, pool)

    def _always_fail(sentence, _pool):
        return SimpleNamespace(sentence=sentence, is_verified=False)

    units = compose_companion_figure_units(
        basket, pool, headline, verify_fn=_always_fail,
    )
    assert units == []


def test_part1_different_measure_kind_not_surfaced(monkeypatch):
    # (iii) a companion percent that shares NO measure-context stem with the headline is not a
    # same-kind companion -> not surfaced.
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "1")
    quote = "GDP grew 1.8% last year. Regional inflation reached 46% overall."
    member = _member("ev_macro", quote)
    basket = _basket([member])
    pool = _pool(member)
    headline = build_short_member_sentence(basket, pool)  # "GDP grew 1.8% last year"
    units = compose_companion_figure_units(
        basket, pool, headline, verify_fn=verify_sentence_provenance,
    )
    assert units == []


def test_part1_rounding_neighbour_not_surfaced(monkeypatch):
    # (iv) a same-kind percent within the material-gap floor (rounding neighbour) is not surfaced.
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "1")
    quote = "Exposure was 1.8% of jobs. A later estimate put it at 1.9% of jobs."
    member = _member("ev_round", quote)
    basket = _basket([member])
    pool = _pool(member)
    headline = build_short_member_sentence(basket, pool)  # "Exposure was 1.8% of jobs"
    units = compose_companion_figure_units(
        basket, pool, headline, verify_fn=verify_sentence_provenance,
    )
    assert units == []


def test_part1_figure_already_in_headline_skipped(monkeypatch):
    # (v) a companion figure the headline ALREADY presents is not re-surfaced.
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "1")
    quote = "AI exposes 1.8% of jobs. Nearly 46% of tasks are affected."
    member = _member("ev_dup", quote)
    basket = _basket([member])
    pool = _pool(member)
    # The headline already carries BOTH figures (1.8 and 46) -> nothing to surface.
    headline_both = "AI exposes 1.8% of jobs and 46% of tasks are affected [#ev:ev_dup:0-18]."
    units = compose_companion_figure_units(
        basket, pool, headline_both, verify_fn=verify_sentence_provenance,
    )
    assert units == []


# ── PART 1: byte-identical OFF ───────────────────────────────────────────────


def test_part1_off_is_byte_identical(monkeypatch):
    member = _member("ev_eloundou", _TWO_FIGURE_QUOTE)
    basket = _basket([member])
    pool = _pool(member)

    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "1")
    on = _compose_section_per_basket(
        [basket], pool,
        writer_fn=_short_writer(pool), verify_fn=verify_sentence_provenance,
    )
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "0")
    off = _compose_section_per_basket(
        [basket], pool,
        writer_fn=_short_writer(pool), verify_fn=verify_sentence_provenance,
    )
    # OFF drops the companion entirely and is byte-identical to the legacy headline-only output.
    assert len(off) == 1
    assert len(on) == 2
    assert off[0] == on[0]  # the headline is untouched by the pass


# ── PART 2 ARM B: forced-positive ────────────────────────────────────────────


def _degraded_basket():
    """A basket whose members DETERMINISTICALLY ground the claim but are NOT entailment-verified because
    the judge was DURABLY UNAVAILABLE this run (span_verdict != SUPPORTS, member_tier ==
    DETERMINISTIC_ONLY, entailment_judge_unavailable == True) — the judge-outage shape (Codex P1b)."""
    members = [
        _member(
            "ev_a", "Trial A reported a 12% absolute risk reduction.",
            span_verdict="UNSUPPORTED", member_tier=MEMBER_TIER_DETERMINISTIC_ONLY,
            judge_unavailable=True,
        ),
        _member(
            "ev_b", "Registry B found a comparable effect.",
            span_verdict="UNSUPPORTED", member_tier=MEMBER_TIER_DETERMINISTIC_ONLY,
            judge_unavailable=True,
        ),
    ]
    return _basket(members, subject="the absolute risk reduction")


def test_part2_armb_degraded_disclosure_forced_positive(monkeypatch):
    monkeypatch.setenv("PG_DEGRADED_VERIFY_DISCLOSURE", "1")
    basket = _degraded_basket()
    pool = _pool(*basket.supporting_members)

    # Both members are DETERMINISTIC_ONLY *and* judge-unavailable — ARM B fires on the DURABLE
    # judge-outage count (Codex P1b), not on DETERMINISTIC_ONLY alone.
    assert _deterministic_only_member_count(basket) == 2
    assert _judge_unavailable_member_count(basket) == 2

    out = _compose_one_basket(
        basket, pool,
        writer_fn=lambda _b, _p: "", verify_fn=verify_sentence_provenance,
    )
    # The DISTINCT degraded label, NOT the bare insufficient-evidence gap.
    assert out.startswith("[verification incomplete: 2 source(s) deterministically ground")
    assert "entailment verification was unavailable this run" in out
    assert "the absolute risk reduction" in out
    # NEVER promotes DETERMINISTIC_ONLY member prose into verified text.
    assert "12% absolute risk reduction" not in out
    assert "Registry B" not in out


def test_part2_armb_off_is_byte_identical(monkeypatch):
    basket = _degraded_basket()
    pool = _pool(*basket.supporting_members)
    monkeypatch.setenv("PG_DEGRADED_VERIFY_DISCLOSURE", "0")
    out = _compose_one_basket(
        basket, pool,
        writer_fn=lambda _b, _p: "", verify_fn=verify_sentence_provenance,
    )
    # OFF => the bare legacy insufficient-evidence gap (byte-identical).
    assert out == "[insufficient verified evidence to compose a sentence for: the absolute risk reduction]"


def test_part2_genuine_gap_is_not_the_degraded_label(monkeypatch):
    # A real evidence gap (members UNVERIFIED — own span lacks the claim) still gets the bare
    # honest gap, NOT the degraded judge-outage label.
    monkeypatch.setenv("PG_DEGRADED_VERIFY_DISCLOSURE", "1")
    members = [
        _member(
            "ev_c", "Unrelated background text.",
            span_verdict="UNSUPPORTED", member_tier=MEMBER_TIER_UNVERIFIED,
        ),
    ]
    basket = _basket(members, subject="the missing figure")
    pool = _pool(*members)
    assert _deterministic_only_member_count(basket) == 0
    out = _no_verified_span_disclosure(basket)
    assert out.startswith("[insufficient verified evidence")
    assert "verification incomplete" not in out


def test_part2_gap_predicate_recognizes_degraded_label(monkeypatch):
    # The frame-coverage honesty override must treat the degraded label as a disclosure
    # placeholder (not substantive prose), and the legacy gap marker still matches.
    monkeypatch.setenv("PG_DEGRADED_VERIFY_DISCLOSURE", "1")
    degraded = _no_verified_span_disclosure(_degraded_basket())
    assert _is_gap_disclosure_sentence(degraded)
    assert _is_gap_disclosure_sentence("Baseline HbA1c: not extractable from available primary content")
    # Substantive verified prose is NOT a gap disclosure.
    assert not _is_gap_disclosure_sentence("Tirzepatide reduced HbA1c by 2.1% [#ev:ev_x:0-40].")


# ── PART 2 ARM B: Codex P1b — clean NEUTRAL/CONTRADICTED is NOT a judge outage ────────────────


def test_part2_p1b_clean_non_entailment_is_not_degraded_label(monkeypatch):
    """Codex Wave-3 P1b: a member that is DETERMINISTIC_ONLY because the judge RAN and returned
    NEUTRAL/CONTRADICTED (entailment_judge_unavailable == False) is a GENUINE gap — it must NOT be
    disclosed as 'entailment verification was unavailable'. Only a DURABLE judge outage may."""
    monkeypatch.setenv("PG_DEGRADED_VERIFY_DISCLOSURE", "1")
    members = [
        _member(
            "ev_a", "Trial A reported a 12% absolute risk reduction.",
            span_verdict="UNSUPPORTED", member_tier=MEMBER_TIER_DETERMINISTIC_ONLY,
            judge_unavailable=False,  # judge RAN, returned NEUTRAL/CONTRADICTED — a clean non-entailment
        ),
        _member(
            "ev_b", "Registry B found a comparable effect.",
            span_verdict="UNSUPPORTED", member_tier=MEMBER_TIER_DETERMINISTIC_ONLY,
            judge_unavailable=False,
        ),
    ]
    basket = _basket(members, subject="the absolute risk reduction")
    # DETERMINISTIC_ONLY count is 2, but the JUDGE-UNAVAILABLE count is 0 — the label gates on the latter.
    assert _deterministic_only_member_count(basket) == 2
    assert _judge_unavailable_member_count(basket) == 0
    out = _no_verified_span_disclosure(basket)
    assert out.startswith("[insufficient verified evidence")
    assert "verification incomplete" not in out
    assert "was unavailable this run" not in out


def test_part2_p1b_mixed_counts_only_the_judge_unavailable_members(monkeypatch):
    """When a basket mixes a judge-outage member with a clean-NEUTRAL member, the degraded label counts
    ONLY the durably-unavailable one (honest count)."""
    monkeypatch.setenv("PG_DEGRADED_VERIFY_DISCLOSURE", "1")
    members = [
        _member(
            "ev_a", "Trial A reported a 12% absolute risk reduction.",
            span_verdict="UNSUPPORTED", member_tier=MEMBER_TIER_DETERMINISTIC_ONLY,
            judge_unavailable=True,   # the judge errored/timed out on this one
        ),
        _member(
            "ev_b", "Registry B found a comparable effect.",
            span_verdict="UNSUPPORTED", member_tier=MEMBER_TIER_DETERMINISTIC_ONLY,
            judge_unavailable=False,  # clean NEUTRAL/CONTRADICTED — a genuine gap
        ),
    ]
    basket = _basket(members, subject="the absolute risk reduction")
    assert _judge_unavailable_member_count(basket) == 1
    out = _no_verified_span_disclosure(basket)
    assert out.startswith("[verification incomplete: 1 source(s) deterministically ground")


# ── PART 2 ARM B: Codex P1a — production-path carrier (reaches verified_text, not rebound/dropped) ──


def _supports_two_figure_basket():
    """A real SUPPORTS basket that composes verified prose (so a mixed section has a rebind target)."""
    member = _member("ev_real", _TWO_FIGURE_QUOTE)
    return _basket([member], subject="AI job exposure", claim_text="AI job exposure")


def test_part2_p1a_production_path_label_reaches_body_not_rebound_or_dropped(monkeypatch):
    """Codex Wave-3 P1a: exercise the REAL production helpers end-to-end. A section with a real SUPPORTS
    basket + a judge-outage degraded basket must (1) surface verified prose for the real basket, (2) HOLD
    the degraded label OUT of the strict_verify-bound draft (so _repair_untokened_draft can't rebind it
    and strict_verify can't drop it no_provenance_token), and (3) RENDER the degraded label back onto the
    section body."""
    monkeypatch.setenv("PG_DEGRADED_VERIFY_DISCLOSURE", "1")
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "0")  # isolate ARM B from PART 1
    real = _supports_two_figure_basket()
    degraded = _degraded_basket()
    section = [real, degraded]
    pool = _pool(real.supporting_members[0], *degraded.supporting_members)

    composed = _compose_section_per_basket(
        section, pool,
        writer_fn=_short_writer(pool), verify_fn=verify_sentence_provenance,
    )
    # The degraded basket emits the DISTINCT label; the real basket emits verified prose.
    assert any("[verification incomplete:" in c for c in composed), composed

    # (1) PARTITION holds the degraded label ASIDE — it is NOT in the strict_verify-bound real units.
    real_units, disclosures = partition_composed_disclosures(composed)
    assert any("[verification incomplete:" in d for d in disclosures)
    assert all("[verification incomplete:" not in u for u in real_units)
    # The real verified prose survives in the real units.
    assert any("1.8%" in u for u in real_units)

    # (2) _repair_untokened_draft over the real units NEVER reintroduces (rebinds) the degraded label.
    raw = "\n".join(u for u in real_units if u and u.strip())
    repaired = _repair_untokened_draft(
        raw, section, pool,
        writer_fn=lambda _b, _p: build_short_member_sentence(_b, pool),
        verify_fn=verify_sentence_provenance,
    )
    assert "[verification incomplete:" not in repaired

    # (3) RENDER the held-aside disclosure back onto the section body (post strict_verify), reaching
    # verified_text — never verified prose, never rebound, never dropped.
    body = render_degraded_disclosures("Verified prose about 1.8% exposure.", disclosures)
    assert "[verification incomplete: 2 source(s) deterministically ground" in body
    assert "Verified prose about 1.8% exposure." in body
    # An all-degraded section (empty body) renders the DISTINCT disclosure as the whole body.
    body_only = render_degraded_disclosures("", disclosures)
    assert body_only.startswith("[verification incomplete: 2 source(s) deterministically ground")


def test_part2_p1a_repair_never_rebinds_degraded_label_to_supports_basket(monkeypatch):
    """Codex Wave-3 P1a (the exact failure mode): feed the degraded label DIRECTLY to the repair pass
    WITH a real SUPPORTS basket in scope (a valid rebind target with overlapping content words). The
    label must be returned UNCHANGED — never laundered into that basket's verified clause."""
    monkeypatch.setenv("PG_DEGRADED_VERIFY_DISCLOSURE", "1")
    monkeypatch.setenv("PG_NO_TOKEN_SENTENCE_REPAIR", "1")
    # A SUPPORTS basket whose claim words overlap the degraded label ("risk", "reduction", "source").
    supports_member = _member(
        "ev_supp", "The absolute risk reduction reached 12% in the pooled analysis.",
    )
    supports_basket = _basket([supports_member], subject="the absolute risk reduction")
    degraded = _degraded_basket()
    pool = _pool(supports_member, *degraded.supporting_members)
    label = _no_verified_span_disclosure(degraded)
    assert label.startswith("[verification incomplete:")

    repaired = _repair_untokened_draft(
        label, [supports_basket, degraded], pool,
        writer_fn=lambda _b, _p: build_short_member_sentence(_b, pool),
        verify_fn=verify_sentence_provenance,
    )
    # UNCHANGED: the honest disclosure was NOT rebound to the SUPPORTS basket's verified clause.
    assert repaired.strip() == label.strip()
    assert "[#ev:" not in repaired  # never given a fabricated provenance token


def test_part2_p1a_partition_off_is_byte_identical(monkeypatch):
    """When ARM B is OFF, no degraded label is ever produced, so the partition returns the composed
    units UNCHANGED (byte-identical) with an empty disclosures list."""
    monkeypatch.setenv("PG_DEGRADED_VERIFY_DISCLOSURE", "0")
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "0")
    real = _supports_two_figure_basket()
    degraded = _degraded_basket()
    pool = _pool(real.supporting_members[0], *degraded.supporting_members)
    composed = _compose_section_per_basket(
        [real, degraded], pool,
        writer_fn=_short_writer(pool), verify_fn=verify_sentence_provenance,
    )
    real_units, disclosures = partition_composed_disclosures(composed)
    assert disclosures == []
    assert real_units == composed  # every unit passes through unchanged
    # And no degraded label exists at all (bare insufficient-evidence gap is suppressed upstream).
    assert all("[verification incomplete:" not in c for c in composed)


# ── PART 1: Codex P2 — repeated identical sentence gets its TRUE iterated offset ──────────────


def test_part1_p2_repeated_sentence_uses_true_iterated_offset(monkeypatch):
    """Codex Wave-3 P2: when a member's direct_quote repeats an identical percent-bearing sentence, the
    companion producer must capture the SECOND occurrence's real offset (running cursor), not always the
    first. The surfaced companion's [#ev:...] token must resolve to the true offset and re-pass
    strict_verify."""
    monkeypatch.setenv("PG_COMPANION_FIGURE_COMPOSE", "1")
    # Headline states 1.8%; the SAME 46% companion sentence appears TWICE, verbatim identical.
    quote = (
        "AI could expose 1.8% of jobs to automation. "
        "Just over 46% of tasks could be exposed. "
        "Just over 46% of tasks could be exposed."
    )
    member = _member("ev_rep", quote)
    basket = _basket([member])
    pool = _pool(member)
    headline = build_short_member_sentence(basket, pool)  # the 1.8% headline

    units = compose_companion_figure_units(
        basket, pool, headline, verify_fn=verify_sentence_provenance,
    )
    # Exactly one companion is surfaced (the repeated figure is not double-surfaced), and it re-passes
    # the REAL strict_verify against its cited offset (proving the offset is correct, first OR second).
    assert len(units) == 1, units
    companion = units[0]
    assert "46%" in companion
    res = verify_sentence_provenance(companion, pool)
    assert res.is_verified, (companion, getattr(res, "failure_reasons", None))
    # The cited token's offsets index a real "46%" occurrence in the quote (true-offset guarantee).
    import re as _re
    m = _re.search(r"\[#ev:ev_rep:(\d+)-(\d+)\]", companion)
    assert m, companion
    s, e = int(m.group(1)), int(m.group(2))
    assert "46%" in quote[s:e]
