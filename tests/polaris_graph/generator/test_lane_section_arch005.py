"""I-arch-005 LANE-SECTION (#1257) — basket-render + budgets + section-resilience.

Covers the five LANE-SECTION fixes + B12-COMPLETION:

  * B2/B3 — the per-section / outline ROW caps are now char/token/basket BUDGETS by
    DEFAULT for every caller (not just the cert slate). No row cap binds on the default
    path; the legacy cap fires ONLY under the PG_GEN_ROW_CAPS escape hatch; the char-budget
    tail-drop is recorded in telemetry (not silently dropped).
  * B6/B8 — INLINE multi-citation basket render: a multi-source claim renders ALL its
    independently span-verified (SUPPORTS) basket members, never the advisory clustered
    count; a member with no verified span is NOT rendered inline; the OFF path is
    byte-identical.
  * B21 — section wall-clock default-ON: a hung section -> a visible gap stub (via the
    transient-failure isolation path), not a hung run.
  * B22 — a section that the cross-section dedup re-resolve emptied -> a VISIBLE gap stub,
    not a silent drop.
  * B12-COMPLETION — judge=None / gov-suffixes-missing under always-release ON does NOT
    raise the CredibilityPassError from the pre-try guard; it degrades + continues.

FAITHFULNESS (constraint 1): every basket-render assertion proves ONLY span-verified
(SUPPORTS) members render. No test relaxes strict_verify / NLI / 4-role / provenance.
"""
from __future__ import annotations

import asyncio

import pytest

import src.polaris_graph.generator.multi_section_generator as msg
from src.polaris_graph.generator.multi_section_generator import (
    SectionPlan,
    _budget_trim_ev_ids,
    _build_deterministic_fallback_outline,
    _build_reliability_header,
    _m44_inject_primaries_into_outline,
    _section_budgets_enabled,
    _section_wallclock_seconds,
)
from src.polaris_graph.generator.provenance_generator import (
    resolve_provenance_to_citations,
    resolve_provenance_to_citations_with_count,
    verify_sentence_provenance,
)
from src.polaris_graph.synthesis.credibility_pass import (
    BASKET_VERDICT_FULL,
    BASKET_VERDICT_PARTIAL,
    BasketMember,
    ClaimBasket,
)


# ─────────────────────────────────────────────────────────────────────────────
# B2/B3 — budgets are the DEFAULT; no row cap binds on the default path.
# ─────────────────────────────────────────────────────────────────────────────


def _short_pool(n: int) -> list[dict]:
    """n SHORT rows (small serialized length) so a generous char budget never trims."""
    return [
        {
            "evidence_id": f"ev_{i:03d}",
            "title": f"Trial {i} of intervention efficacy",
            "statement": f"Finding {i}: intervention reduced the outcome.",
            "direct_quote": f"Row {i}: intervention produced the outcome.",
            "tier": "T1",
        }
        for i in range(n)
    ]


def test_arch005_per_section_budget_default_no_row_cap(monkeypatch) -> None:
    """DEFAULT (no flag): the per-section ROW cap does NOT bind — all 40 round-robin rows
    per section flow through (vs the legacy 30-row clamp). Proves the budget path is the
    default for every caller, not just the cert slate."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    monkeypatch.delenv("PG_GEN_ROW_CAPS", raising=False)
    monkeypatch.delenv("PG_MAX_EV_PER_SECTION", raising=False)
    monkeypatch.delenv("PG_SECTION_EV_CHAR_BUDGET", raising=False)  # default ~120K chars

    assert _section_budgets_enabled() is True, "budgets must be the default"
    plans = _build_deterministic_fallback_outline(_short_pool(120), domain="clinical")
    assert plans, "fallback outline should build 3 sections from 120 rows"
    # 120 / 3 = 40 per section; the legacy cap would clamp to 30. Budget keeps all 40.
    assert all(len(p.ev_ids) == 40 for p in plans), (
        f"DEFAULT: every short row must flow through (no 30-row cap); got "
        f"{[len(p.ev_ids) for p in plans]}"
    )
    assert any(len(p.ev_ids) > 30 for p in plans), "at least one section exceeds the legacy 30"


def test_arch005_escape_hatch_restores_row_cap(monkeypatch) -> None:
    """PG_GEN_ROW_CAPS=1 restores the legacy 30-row clamp byte-for-byte (the regression
    escape hatch the cert preflight refuses)."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    monkeypatch.setenv("PG_GEN_ROW_CAPS", "1")
    monkeypatch.delenv("PG_MAX_EV_PER_SECTION", raising=False)

    assert _section_budgets_enabled() is False, "escape hatch must restore row caps"
    plans = _build_deterministic_fallback_outline(_short_pool(120), domain="clinical")
    assert all(len(p.ev_ids) == 30 for p in plans), (
        f"escape-hatch: every section clamps to 30; got {[len(p.ev_ids) for p in plans]}"
    )


def test_arch005_budget_trim_records_tail_drop_telemetry() -> None:
    """A binding char-budget trim records the tail-drop (count + chars + site) into the
    telemetry sink instead of dropping silently."""
    ev_ids = [f"ev_{i}" for i in range(10)]
    char_len_by_id = {e: 100 for e in ev_ids}  # 100 chars each
    sink: list[dict] = []
    # Budget admits ~3 rows (350 / 100 -> keep 3, 4th would exceed).
    kept = _budget_trim_ev_ids(
        ev_ids, char_len_by_id, 350, telemetry_sink=sink, site="unit_test_site",
    )
    assert len(kept) == 3, f"char budget should keep ~3 rows, got {len(kept)}"
    assert len(sink) == 1, "exactly one tail-drop record"
    rec = sink[0]
    assert rec["site"] == "unit_test_site"
    assert rec["reason"] == "char_budget_exceeded"
    assert rec["rows_in"] == 10
    assert rec["rows_kept"] == 3
    assert rec["rows_dropped"] == 7
    assert rec["chars_dropped"] == 700


def test_arch005_budget_trim_no_drop_no_telemetry() -> None:
    """When every row fits the budget, NOTHING is dropped and NO telemetry record is
    emitted (the budget is not a row cap; it only records a REAL drop)."""
    ev_ids = [f"ev_{i}" for i in range(5)]
    char_len_by_id = {e: 10 for e in ev_ids}
    sink: list[dict] = []
    kept = _budget_trim_ev_ids(ev_ids, char_len_by_id, 10_000, telemetry_sink=sink, site="s")
    assert kept == ev_ids, "all rows fit -> all kept"
    assert sink == [], "no drop -> no telemetry record"


# ─────────────────────────────────────────────────────────────────────────────
# B6/B8 — INLINE multi-citation basket render (the keystone).
# ─────────────────────────────────────────────────────────────────────────────


def _pool_three() -> dict:
    return {
        "ev_a": {
            "direct_quote": "Reported value was 14.9% here.",
            "statement": "A statement about the value.",
            "source_url": "https://a/",
            "tier": "T1",
        },
        "ev_b": {
            "direct_quote": "Confirmed value was 14.9% too.",
            "statement": "B statement about the value.",
            "source_url": "https://b/",
            "tier": "T2",
        },
        "ev_c": {
            "direct_quote": "A different unverified context line.",
            "statement": "C statement.",
            "source_url": "https://c/",
            "tier": "T5",
        },
    }


def _one_cited_sentence(pool: dict) -> list:
    """A single verified sentence that cites ONLY ev_a."""
    kept = [
        verify_sentence_provenance(
            "Reported value was 14.9% here [#ev:ev_a:0-29].", pool,
        ),
    ]
    assert all(sv.is_verified for sv in kept)
    return kept


def _basket_a_b_c_with_verdicts(
    *, b_verdict: str = "SUPPORTS", c_verdict: str = "UNSUPPORTED",
) -> ClaimBasket:
    """A 3-member basket on cluster 'c1': ev_a + ev_b SUPPORTS, ev_c per arg.
    verified_support_origin_count reflects the SUPPORTS members only."""
    members = [
        BasketMember(
            evidence_id="ev_a", source_url="https://a/", source_tier="T1",
            origin_cluster_id="o::ev_a", credibility_weight=0.9, authority_score=0.8,
            span=(0, 29), direct_quote="Reported value was 14.9% here.",
            span_verdict="SUPPORTS",
        ),
        BasketMember(
            evidence_id="ev_b", source_url="https://b/", source_tier="T2",
            origin_cluster_id="o::ev_b", credibility_weight=0.7, authority_score=0.6,
            span=(0, 29), direct_quote="Confirmed value was 14.9% too.",
            span_verdict=b_verdict,
        ),
        BasketMember(
            evidence_id="ev_c", source_url="https://c/", source_tier="T5",
            origin_cluster_id="o::ev_c", credibility_weight=0.3, authority_score=0.2,
            span=(0, 29), direct_quote="A different unverified context line.",
            span_verdict=c_verdict,
        ),
    ]
    verified = sum(1 for m in members if m.span_verdict == "SUPPORTS")
    return ClaimBasket(
        claim_cluster_id="c1",
        claim_text="Reported value was 14.9%.",
        subject="intervention", predicate="outcome",
        supporting_members=members,
        refuter_cluster_ids=(),
        weight_mass=1.9,
        total_clustered_origin_count=3,           # ADVISORY — must NEVER render
        verified_support_origin_count=verified,
        basket_verdict=BASKET_VERDICT_FULL if verified == 3 else BASKET_VERDICT_PARTIAL,
    )


def test_arch005_inline_renders_all_verified_basket_members() -> None:
    """A multi-source claim that the generator cited via ONE source (ev_a) renders ALL
    independently span-verified (SUPPORTS) members inline: ev_a AND ev_b. The unverified
    member ev_c is NOT rendered inline. The advisory clustered count (3) is never used."""
    pool = _pool_three()
    kept = _one_cited_sentence(pool)
    basket = _basket_a_b_c_with_verdicts(b_verdict="SUPPORTS", c_verdict="UNSUPPORTED")
    binding = {"ev_a": ["c1"], "ev_b": ["c1"], "ev_c": ["c1"]}

    text, biblio, emitted = resolve_provenance_to_citations_with_count(
        kept, pool, baskets=[basket], cluster_id_by_evidence=binding,
    )

    assert emitted == 1
    # The sentence cited only ev_a, but the basket corroborator ev_b (SUPPORTS) is rendered
    # inline too -> the bibliography carries BOTH ev_a and ev_b numbered.
    biblio_ids = {r["evidence_id"] for r in biblio}
    assert "ev_a" in biblio_ids
    assert "ev_b" in biblio_ids, "the SUPPORTS corroborator must render inline"
    # ev_c is UNSUPPORTED -> NOT rendered inline (faithfulness: only span-verified members).
    assert "ev_c" not in biblio_ids, "an UNSUPPORTED member must NOT render as inline support"
    # The rendered sentence carries TWO citation markers (ev_a + ev_b), not one and not three.
    n_markers = text.count("[1]") + text.count("[2]")
    assert "[1]" in text and "[2]" in text, f"expected two inline citations, got: {text!r}"
    assert "[3]" not in text, "the unverified clustered member must not get a 3rd marker"


def test_arch005_inline_off_path_byte_identical() -> None:
    """No basket args -> the inline render is byte-identical to the legacy single-citation
    render (one marker for the one cited source). Proves the OFF path is unchanged."""
    pool = _pool_three()
    kept = _one_cited_sentence(pool)

    text_off, biblio_off = resolve_provenance_to_citations(kept, pool)

    biblio_ids = {r["evidence_id"] for r in biblio_off}
    assert biblio_ids == {"ev_a"}, "OFF: only the one cited source is rendered"
    assert "[1]" in text_off and "[2]" not in text_off, "OFF: exactly one inline citation"
    assert set(biblio_off[0].keys()) == {"num", "evidence_id", "url", "tier", "statement"}


def test_arch005_inline_only_one_basket_arg_stays_legacy() -> None:
    """Both basket params required: one without the other must NOT half-render the inline
    corroborators (mirrors the bibliography param-presence gate)."""
    pool = _pool_three()
    kept = _one_cited_sentence(pool)
    basket = _basket_a_b_c_with_verdicts()

    # baskets present, no binding
    t1, b1, _ = resolve_provenance_to_citations_with_count(kept, pool, baskets=[basket])
    assert {r["evidence_id"] for r in b1} == {"ev_a"}, "no binding -> legacy single citation"
    # binding present, no baskets
    t2, b2, _ = resolve_provenance_to_citations_with_count(
        kept, pool, cluster_id_by_evidence={"ev_a": ["c1"]},
    )
    assert {r["evidence_id"] for r in b2} == {"ev_a"}, "no baskets -> legacy single citation"


def test_arch005_inline_never_renders_clustered_count() -> None:
    """When NO member is independently verified (all UNSUPPORTED except the cited one's
    own token), the inline render adds NO corroborators — the advisory clustered count is
    never materialized as inline support."""
    pool = _pool_three()
    kept = _one_cited_sentence(pool)
    # ev_b + ev_c both UNSUPPORTED; ev_a only carried by its own sentence token.
    basket = _basket_a_b_c_with_verdicts(b_verdict="UNSUPPORTED", c_verdict="UNSUPPORTED")
    # ev_a is NOT a SUPPORTS member here (its support comes from the sentence's own token),
    # so the SUPPORTS set for cluster c1 is empty -> no inline corroborator added.
    basket.supporting_members[0].span_verdict = "UNSUPPORTED"
    basket.verified_support_origin_count = 0
    binding = {"ev_a": ["c1"], "ev_b": ["c1"], "ev_c": ["c1"]}

    text, biblio, _ = resolve_provenance_to_citations_with_count(
        kept, pool, baskets=[basket], cluster_id_by_evidence=binding,
    )
    # Only ev_a (the sentence's own cited token) renders; no corroborator markers.
    assert {r["evidence_id"] for r in biblio} == {"ev_a"}
    assert "[2]" not in text, "no inline corroborator when no member is span-verified"


def test_arch005_inline_no_cross_claim_attribution_on_multi_cluster_token() -> None:
    """FAITHFULNESS (§-1.1 "citation appropriate for the claim"): a source that backs
    MULTIPLE distinct claims (1-to-many cluster_id_by_evidence) must NOT have one claim's
    verified corroborator rendered as support for a DIFFERENT claim's sentence.

    ev_a backs c1 ("value 14.9%", with corroborator ev_b SUPPORTS) AND c2 (a DIFFERENT
    claim, with a verified member ev_c). A sentence asserting c1 cites ev_a. The render must
    NOT pull ev_c (c2's verified member) onto the c1 sentence — the token is multi-cluster,
    so it cannot be attributed to ONE claim and gets NO corroborator expansion at all."""
    pool = _pool_three()
    kept = _one_cited_sentence(pool)  # cites ev_a only

    c1 = ClaimBasket(
        claim_cluster_id="c1", claim_text="Value was 14.9%.",
        subject="x", predicate="weight",
        supporting_members=[
            BasketMember(
                evidence_id="ev_a", source_url="https://a/", source_tier="T1",
                origin_cluster_id="o::ev_a", credibility_weight=0.9, authority_score=0.8,
                span=(0, 29), direct_quote="Reported value was 14.9% here.",
                span_verdict="SUPPORTS",
            ),
            BasketMember(
                evidence_id="ev_b", source_url="https://b/", source_tier="T2",
                origin_cluster_id="o::ev_b", credibility_weight=0.7, authority_score=0.6,
                span=(0, 29), direct_quote="Confirmed value was 14.9% too.",
                span_verdict="SUPPORTS",
            ),
        ],
        refuter_cluster_ids=(), weight_mass=1.6,
        total_clustered_origin_count=2, verified_support_origin_count=2,
        basket_verdict=BASKET_VERDICT_FULL,
    )
    c2 = ClaimBasket(
        claim_cluster_id="c2", claim_text="A DIFFERENT claim about side effects.",
        subject="x", predicate="nausea",
        supporting_members=[
            BasketMember(
                evidence_id="ev_c", source_url="https://c/", source_tier="T5",
                origin_cluster_id="o::ev_c", credibility_weight=0.3, authority_score=0.2,
                span=(0, 29), direct_quote="A different unverified context line.",
                span_verdict="SUPPORTS",  # verified — but for the OTHER claim
            ),
        ],
        refuter_cluster_ids=(), weight_mass=0.3,
        total_clustered_origin_count=1, verified_support_origin_count=1,
        basket_verdict=BASKET_VERDICT_FULL,
    )
    # ev_a backs BOTH c1 and c2 (1-to-many) — the sentence's token is AMBIGUOUS.
    binding = {"ev_a": ["c1", "c2"], "ev_b": ["c1"], "ev_c": ["c2"]}

    text, biblio, _ = resolve_provenance_to_citations_with_count(
        kept, pool, baskets=[c1, c2], cluster_id_by_evidence=binding,
    )

    biblio_ids = {r["evidence_id"] for r in biblio}
    # ev_c (c2's verified member) MUST NOT render as inline support for the c1 sentence.
    assert "ev_c" not in biblio_ids, (
        "cross-claim attribution: c2's verified member must NOT cite a c1 sentence"
    )
    # The multi-cluster token gets NO corroborator expansion at all (conservative); only
    # ev_a (its own cited token) renders.
    assert biblio_ids == {"ev_a"}, (
        f"a multi-cluster (ambiguous) token must not expand corroborators; got {biblio_ids}"
    )
    assert "[2]" not in text


def test_arch005_reliability_header_uses_verified_not_clustered() -> None:
    """The report-level reliability header counts corroboration by
    verified_support_origin_count (>=2 = corroborated), NEVER the clustered total."""
    corroborated = _basket_a_b_c_with_verdicts(b_verdict="SUPPORTS")  # 2 verified
    single = _basket_a_b_c_with_verdicts(b_verdict="UNSUPPORTED", c_verdict="UNSUPPORTED")
    single.claim_cluster_id = "c2"
    single.verified_support_origin_count = 1  # only ev_a verified

    class _Analysis:
        baskets = [corroborated, single]

    header = _build_reliability_header(_Analysis())
    assert header is not None
    assert header["claims_total"] == 2
    assert header["claims_multi_source_corroborated"] == 1  # the 2-verified basket
    assert header["claims_single_origin"] == 1
    assert header["corroboration_basis"] == "verified_support_origin_count"


def test_arch005_reliability_header_none_when_no_baskets() -> None:
    class _Empty:
        baskets = []

    assert _build_reliability_header(_Empty()) is None
    assert _build_reliability_header(None) is None


# ─────────────────────────────────────────────────────────────────────────────
# B21 — section wall-clock default-ON -> a hung section becomes a visible gap stub.
# ─────────────────────────────────────────────────────────────────────────────


def test_arch005_section_wallclock_default_on() -> None:
    """The per-section wall-clock is now default-ON (a generous default), so a caller that
    does NOT set the env still gets the hang protection (not the silent-hang-forever path)."""
    import os
    prev = os.environ.pop("PG_SECTION_WALLCLOCK_SECONDS", None)
    try:
        wall = _section_wallclock_seconds()
        assert wall > 0, "wall-clock must be default-ON (>0) so a hang cannot hang the run"
        # B24 (#1257): the default section wall (1800s) must clear the inner generator per-call
        # timeout (now right-sized to 600s by default) + headroom, so it fires only on a true hang.
        # Read the LIVE constant via the accessor (NOT the import-frozen module reference), so this
        # assertion is robust to a sibling test that mutated the global via set_generator_timeout_seconds.
        from src.polaris_graph.llm.openrouter_client import get_generator_timeout_seconds
        gen_timeout = get_generator_timeout_seconds()
        assert wall > gen_timeout, (
            f"wall ({wall}) must exceed the inner LLM timeout ({gen_timeout}) "
            f"so it fires only on a true hang, not a slow-but-legit section"
        )
    finally:
        if prev is not None:
            os.environ["PG_SECTION_WALLCLOCK_SECONDS"] = prev


def test_arch005_hung_section_becomes_gap_stub(monkeypatch) -> None:
    """A section whose runner WEDGES past the wall-clock raises a TimeoutError, which the
    isolation gather converts to a VISIBLE gap stub — NOT a hung run, NOT a sibling-cancel."""
    monkeypatch.setenv("PG_SECTION_WALLCLOCK_SECONDS", "1")  # 1s wall for a fast test

    class _Plan:
        title = "Hung Section"
        focus = "f"
        ev_ids = ["ev_a"]
        archetype = "Risk"

    async def _wedged_runner(plan):
        await asyncio.sleep(60)  # never returns within the 1s wall (x2)
        raise AssertionError("should have timed out")

    async def _drive():
        # _run_section_with_wallclock wraps + retries, then raises TimeoutError;
        # _gather_sections_isolated catches it -> gap stub.
        return await msg._gather_sections_isolated(
            [_Plan()],
            lambda p: msg._run_section_with_wallclock(_wedged_runner, p),
        )

    results = asyncio.run(_drive())
    assert len(results) == 1
    sr = results[0]
    assert sr.is_gap_stub is True, "a hung section must become a visible gap stub"
    assert sr.dropped_due_to_failure is False, "the gap stub must NOT be dropped at assembly"
    assert sr.verified_text, "the gap stub must carry a visible disclosure line"
    assert sr.sentences_verified == 0, "a gap stub carries zero verified sentences"


# ─────────────────────────────────────────────────────────────────────────────
# B22 — a section emptied by dedup re-resolve -> a VISIBLE gap stub, not a silent drop.
# (Unit-level: the gap-stub constants + the dropped_due_to_failure semantics that the
#  fix relies on. The full dedup path is exercised by the integration suite; here we
#  pin the invariant the fix establishes: zero-emission -> visible, not silently dropped.)
# ─────────────────────────────────────────────────────────────────────────────


def test_arch005_zero_emission_gap_stub_is_visible_not_dropped() -> None:
    """The B22 fix replaces `dropped_due_to_failure=True` (silent vanish at assembly) with
    a visible gap stub. Assert the gap-stub sentence is a real disclosure string and that
    the assembly filter (`if not sr.dropped_due_to_failure`) would KEEP a stub built the
    B22 way."""
    from src.polaris_graph.generator.multi_section_generator import (
        SectionResult,
        _GAP_STUB_SENTENCE,
    )

    # Build a SectionResult exactly as the B22 fix does on a zero-emission dedup re-resolve.
    sr = SectionResult(
        title="Emptied By Dedup", focus="f", ev_ids_assigned=["ev_a"],
        raw_draft="", rewritten_draft="",
        verified_text=_GAP_STUB_SENTENCE,
        biblio_slice=[],
        sentences_verified=0, sentences_dropped=3,
        regen_attempted=False, dropped_due_to_failure=False,
        is_gap_stub=True,
    )
    assert sr.is_gap_stub is True
    assert sr.dropped_due_to_failure is False, "B22: the emptied section must NOT be dropped"
    assert "curator-actionable gap" in sr.verified_text, "the stub must disclose the gap"
    # The assembly filter keeps non-dropped sections, so the stub is VISIBLE.
    keep = not sr.dropped_due_to_failure
    assert keep is True


# ─────────────────────────────────────────────────────────────────────────────
# B12-COMPLETION — judge=None under always-release ON does NOT raise from the pre-try
# guard; the credibility pass degrades + the report continues.
#
# The guard runs DEEP in generate_multi_section_report (after the LLM outline + section
# calls), so it cannot be exercised offline end-to-end. The decision logic is extracted
# into the pure `_credibility_guard_decision` helper (the inline site calls it verbatim) so
# the B12-COMPLETION behavior is directly + deterministically unit-tested. The
# source-level test below additionally pins that the inline guard is wired through the
# helper (so the unit test cannot drift from the production path).
# ─────────────────────────────────────────────────────────────────────────────


def test_iarch011_f2a_judge_none_with_gov_runs_priors_only() -> None:
    """I-arch-011 F2a (#1268): judge=None + gov_suffixes PRESENT + always-release ON -> "run"
    (was "degrade" under B12-COMPLETION). run_credibility_analysis(judge=None) builds the
    COMPLETE priors-only basket (ZERO scoring LLM calls, every source LABELED
    credibility_unscored); the old "degrade" threw that basket away -> the 794->9 cited-source
    collapse. A missing judge must RUN priors-only, not degrade. Faithfulness unchanged: priors
    weights are real; strict_verify / 4-role D8 / span-grounding stay the only binding gates."""
    assert msg._credibility_guard_decision(
        judge=None, gov_suffixes=("gov",), always_release=True,
    ) == "run"


def test_iarch011_f2a_gov_suffixes_missing_still_degrades() -> None:
    """MISSING gov_suffixes is a real wiring hole (the pass cannot classify gov sources) and is
    NOT the judge case: it KEEPS the B12-COMPLETION degrade under always-release, regardless of
    whether the judge is present. The F2a fix split the two conditions deliberately."""
    assert msg._credibility_guard_decision(
        judge=object(), gov_suffixes=None, always_release=True,
    ) == "degrade"
    assert msg._credibility_guard_decision(
        judge=object(), gov_suffixes=(), always_release=True,
    ) == "degrade"
    # gov-missing dominates even when the judge is ALSO missing (gov branch checked first).
    assert msg._credibility_guard_decision(
        judge=None, gov_suffixes=(), always_release=True,
    ) == "degrade"


def test_iarch011_f2a_judge_none_run_path_surfaces_disclosed_gap() -> None:
    """I-arch-011 Codex P1: the judge=None "run" path (priors-only) MUST surface the disclosed gap on
    the operator-visible ``credibility_disclosed_gap`` carrier — else priors-only weights ship without
    the LAW II disclosure (the old "degrade" path set it; F2a's "run" path must too). Pinned at source
    level (the set is deep in the async ``generate_multi_section_report``), mirroring the existing
    inline-guard wiring test."""
    import inspect

    src = inspect.getsource(msg.generate_multi_section_report)
    # the run path sets the named priors-only gap when the LLM credibility judge is None
    assert "_CREDIBILITY_PRIORS_ONLY_DISCLOSED_GAP" in src
    assert "credibility_pass_judge is None" in src
    # the named constant carries the priors_only token the manifest reader surfaces
    assert "priors_only" in msg._CREDIBILITY_PRIORS_ONLY_DISCLOSED_GAP
    # distinct from the pass-could-NOT-run degrade string (different condition, different text)
    assert (
        msg._CREDIBILITY_PRIORS_ONLY_DISCLOSED_GAP
        != msg._CREDIBILITY_NO_JUDGE_DISCLOSED_GAP
    )


def test_arch005_b12_judge_none_always_release_off_still_raises() -> None:
    """always-release OFF (legacy) keeps the hard fail-closed raise on judge=None —
    byte-identical to the pre-fix abort. Only the always-release-ON branch changed."""
    assert msg._credibility_guard_decision(
        judge=None, gov_suffixes=("gov",), always_release=False,
    ) == "raise"
    assert msg._credibility_guard_decision(
        judge=object(), gov_suffixes=None, always_release=False,
    ) == "raise"


def test_arch005_b12_judge_threaded_runs_normally() -> None:
    """When BOTH judge + gov_suffixes are threaded, the decision is "run" regardless of the
    always-release flag (the pass runs normally; faithfulness path unchanged)."""
    assert msg._credibility_guard_decision(
        judge=object(), gov_suffixes=("gov",), always_release=True,
    ) == "run"
    assert msg._credibility_guard_decision(
        judge=object(), gov_suffixes=("gov",), always_release=False,
    ) == "run"


def test_arch005_b12_inline_guard_wired_through_helper() -> None:
    """Pin that the inline credibility guard in generate_multi_section_report routes through
    `_credibility_guard_decision` (so the unit tests above cannot drift from production) AND
    that the guard now lives in the always-release-gated structure, not a pre-try raise."""
    import inspect

    src = inspect.getsource(msg.generate_multi_section_report)
    assert "_credibility_guard_decision(" in src, "inline guard must call the pure helper"
    # the raise is gated on the helper's "raise" decision (not an unconditional pre-try raise).
    assert 'if _cred_guard == "raise":' in src
    assert 'if _cred_guard == "degrade":' in src
    # the disclosed-gap is the NAMED constant (no inline magic string drift).
    assert "_CREDIBILITY_NO_JUDGE_DISCLOSED_GAP" in src


# ─────────────────────────────────────────────────────────────────────────────
# B-M44 — M-44 primary-trial injection must NOT silently COUNT-DROP a corroborating
# row on the DEFAULT path (§-1.3 BANNED filter-and-cap). The count-based swap is now
# gated behind the SAME PG_GEN_ROW_CAPS legacy escape hatch as the other B2/B3 caps.
# ─────────────────────────────────────────────────────────────────────────────


def _m44_full_section(n_rows: int) -> SectionPlan:
    """An 'efficacy'-titled section pre-loaded with n_rows non-primary ev_ids. 'efficacy' is
    a _M44_PRIMARY_ELIGIBLE_SECTION AND is in the _general anchor affinity set, so a _general
    anchor (e.g. SURPASS-2) fires injection non-vacuously (use_archetype=False / OFF path)."""
    return SectionPlan(
        title="efficacy",
        focus="glycemic efficacy of the intervention",
        ev_ids=[f"ev_{i:03d}" for i in range(n_rows)],
    )


def test_arch005_m44_default_path_no_count_drop(monkeypatch) -> None:
    """DEFAULT path (budgets enabled): a section already holding >= max_ev_per_section rows
    gets the primary PREPENDED with NO count-based eviction — the row list GROWS (the §-1.3
    weight-don't-filter contract). The injection actually FIRES (action='injected'), so the
    'no drop' assertion is non-vacuous (not an affinity skip)."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    monkeypatch.delenv("PG_GEN_ROW_CAPS", raising=False)
    assert _section_budgets_enabled() is True, "budgets must be the default"

    plan = _m44_full_section(40)  # at the Gate-B PG_MAX_EV_PER_SECTION=40 ceiling
    primary = "ev_PRIMARY_surpass2"
    plans, log = _m44_inject_primaries_into_outline(
        [plan],
        {"SURPASS-2": [primary]},
        max_ev_per_section=40,  # the Gate-B value; would trigger the legacy count-swap
        use_archetype=False,
    )
    out = plans[0]
    # The injection FIRED (non-vacuous): the action is 'injected', NOT a swap/skip.
    inj = [e for e in log if e["ev_id"] == primary]
    assert inj and inj[0]["action"] == "injected", (
        f"primary must be injected (not swapped/skipped) on the default path; got {inj}"
    )
    # NO count-based drop: the list GREW from 40 to 41, the primary is at the front, and
    # EVERY original corroborating row survives (none count-evicted).
    assert len(out.ev_ids) == 41, f"default path must keep all rows + the primary; got {len(out.ev_ids)}"
    assert out.ev_ids[0] == primary, "primary prepended for prompt salience"
    assert all(f"ev_{i:03d}" in out.ev_ids for i in range(40)), "no original row dropped"
    # No swap/drop telemetry was emitted on the default path.
    assert not any(e.get("drop_reason") for e in log), "default path must record NO count drop"


def test_arch005_m44_escape_hatch_restores_count_cap(monkeypatch) -> None:
    """ESCAPE HATCH (PG_GEN_ROW_CAPS=1): the legacy count-based swap is restored byte-for-byte
    — the last (lowest-priority) row is popped, the primary prepended, the list stays at the
    cap, and the count-evicted row is recorded in structured tail-drop telemetry."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    monkeypatch.setenv("PG_GEN_ROW_CAPS", "1")
    assert _section_budgets_enabled() is False, "escape hatch must restore row caps"

    plan = _m44_full_section(40)
    primary = "ev_PRIMARY_surpass2"
    plans, log = _m44_inject_primaries_into_outline(
        [plan],
        {"SURPASS-2": [primary]},
        max_ev_per_section=40,
        use_archetype=False,
    )
    out = plans[0]
    # The legacy swap FIRED: list stays at the 40-row cap, primary prepended, last row evicted.
    assert len(out.ev_ids) == 40, f"escape hatch must hold the count cap; got {len(out.ev_ids)}"
    assert out.ev_ids[0] == primary, "primary prepended"
    assert "ev_039" not in out.ev_ids, "the last (lowest-priority) row was count-evicted"
    swap = [e for e in log if e["ev_id"] == primary]
    assert swap and swap[0]["action"].startswith("swap_in_for_"), f"legacy swap action expected; got {swap}"
    # The count-evicted row is recorded in STRUCTURED telemetry (not silent, not only in the action string).
    assert swap[0].get("drop_reason") == "row_cap_swap"
    assert swap[0].get("dropped_ev_id") == "ev_039"


# ─────────────────────────────────────────────────────────────────────────────
# B24 — section timeout right-sizing: per-call generator timeout (600s default) sits
# UNDER the section wall-clock backstop (1800s default). The ORDERING is the invariant.
# ─────────────────────────────────────────────────────────────────────────────


def test_arch005_b24_generator_timeout_under_section_wall(monkeypatch) -> None:
    """B24 (#1257): the per-call generator LLM timeout (GENERATOR_TIMEOUT_SECONDS, default 600s)
    must be STRICTLY LESS than the section wall-clock backstop (_section_wallclock_seconds,
    default 1800s) so a hung inner call is killed by its own timeout BEFORE the outer section
    wall fires — the wall is the last-resort backstop, not the primary kill. Asserts the ACTUAL
    new default values, not just 'wall > timeout' in the abstract."""
    from src.polaris_graph.llm.openrouter_client import (
        GENERATOR_TIMEOUT_SECONDS,
        get_generator_timeout_seconds,
        set_generator_timeout_seconds,
    )

    # Pin the per-call default deterministically (the import-time module constant; restore the
    # LIVE global after to avoid leaking into ordering-sensitive siblings).
    monkeypatch.delenv("PG_GENERATOR_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("PG_SECTION_WALLCLOCK_SECONDS", raising=False)
    assert GENERATOR_TIMEOUT_SECONDS == 600, (
        f"B24: the per-call generator timeout MODULE default must be 600s; got {GENERATOR_TIMEOUT_SECONDS}"
    )
    assert int(msg.PG_SECTION_WALLCLOCK_SECONDS_DEFAULT) == 1800, (
        f"B24: the section wall MODULE default must be 1800s; got {msg.PG_SECTION_WALLCLOCK_SECONDS_DEFAULT}"
    )

    _orig = get_generator_timeout_seconds()
    try:
        set_generator_timeout_seconds(600)  # the right-sized per-call default
        per_call = get_generator_timeout_seconds()
        section_wall = _section_wallclock_seconds()
        assert per_call == 600, f"live per-call timeout must be 600s; got {per_call}"
        assert section_wall == 1800, f"section wall default must be 1800s; got {section_wall}"
        # The ORDERING invariant: per-call(600) < section-wall(1800).
        assert per_call < section_wall, (
            f"per-call generator timeout ({per_call}) must be STRICTLY LESS than the section "
            f"wall-clock backstop ({section_wall}) so the inner call dies first"
        )
    finally:
        set_generator_timeout_seconds(_orig)
