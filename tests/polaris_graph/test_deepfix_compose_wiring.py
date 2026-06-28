"""I-deepfix-001 WIRER-COMPOSE — fail-loud behavioral tests for the five wired seams.

Each test flips the seam's flag ON and asserts the EFFECT APPEARS in real output (per §-1.4 FULLY-
WIRED gate): a chrome corroboration header is screened to a placeholder while the count survives
(B6a); a tier-authority prior joins so weight_mass goes non-zero (B9a); distinct DOIs never share one
origin cluster (B9b); same-origin mirror cites collapse to one citation + note (B9c); an unsupported
analyst-synthesis sentence gets a low-confidence marker while a supported one does not (B13); a
non-supporting repair marker is pruned only when the entailment judge confirms it (B17).

OFFLINE: no network / no model / no paid LLM. All judges are injected deterministic fakes.
"""
from __future__ import annotations

import importlib

import pytest


# ─────────────────────────────────────────────────────────────────────────────
# B6(a) — corroboration-aware chrome screen in sanitize_rendered_report
# ─────────────────────────────────────────────────────────────────────────────
def test_b6a_corroboration_header_chrome_screened_count_preserved(monkeypatch):
    monkeypatch.setenv("PG_CORROBORATION_SANITIZE", "1")
    monkeypatch.setenv("PG_RENDER_SEAM_SANITIZE", "1")
    monkeypatch.setenv("PG_RENDER_CHROME_SCREEN", "1")
    from src.polaris_graph.generator import weighted_enrichment as we
    importlib.reload(we)

    # A corroboration rollup whose FIRST basket header is page-furniture chrome (an ISSN/license
    # masthead scrape) and whose SECOND header is a real finding. Sub-bullets carry source locators.
    report = (
        "## Source corroboration (per claim)\n\n"
        "- **ISSN 2049-3630 Creative Commons Attribution 4.0 International License "
        "All rights reserved** — 3 verified independent source(s)\n"
        "  - SUPPORT: https://example.org/a (tier T1, weight 0.95)\n"
        "  - SUPPORT: https://example.com/b (tier T2, weight 0.85)\n"
        "- **GenAI adoption raised measured task throughput in the trial** — "
        "2 verified independent source(s)\n"
        "  - SUPPORT: https://example.net/c (tier T1, weight 0.95)\n"
    )
    clean, removed = we.sanitize_rendered_report(report)

    # The chrome claim string is withheld (placeholder), but its verified-source COUNT survives.
    assert "ISSN 2049-3630" not in clean
    assert "claim text withheld" in clean
    assert "3 verified independent source(s)" in clean  # count preserved (never dropped)
    # The two SUPPORT sub-bullets of the chrome basket are KEEP-ONLY (no source dropped).
    assert "https://example.org/a" in clean
    assert "https://example.com/b" in clean
    # The real finding header is untouched.
    assert "GenAI adoption raised measured task throughput in the trial" in clean
    assert removed >= 1


def test_b6a_kill_switch_off_is_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_CORROBORATION_SANITIZE", "0")
    monkeypatch.setenv("PG_RENDER_SEAM_SANITIZE", "1")
    from src.polaris_graph.generator import weighted_enrichment as we
    importlib.reload(we)
    report = (
        "## Source corroboration (per claim)\n\n"
        "- **ISSN 2049-3630 All rights reserved** — 3 verified independent source(s)\n"
        "  - SUPPORT: https://example.org/a (tier T1, weight 0.95)\n"
    )
    clean, _removed = we.sanitize_rendered_report(report)
    assert "ISSN 2049-3630 All rights reserved" in clean  # byte-preserved when the screen is OFF


# ─────────────────────────────────────────────────────────────────────────────
# B9(a) — tier-authority prior join => non-zero weight_mass; canary detects a wiring break
# ─────────────────────────────────────────────────────────────────────────────
def test_b9a_tier_prior_join_populates_authority_score(monkeypatch):
    monkeypatch.setenv("PG_CREDIBILITY_TIER_AUTHORITY_JOIN", "1")
    from src.polaris_graph.synthesis import credibility_pass as cp
    importlib.reload(cp)
    rows = [
        {"evidence_id": "ev_1", "tier": "T1", "direct_quote": "x"},   # no authority_score
        {"evidence_id": "ev_2", "tier": "T7", "direct_quote": "y"},
        {"evidence_id": "ev_3", "tier": "T2", "direct_quote": "z", "authority_score": 0.42},  # kept
    ]
    out = cp._join_tier_authority_prior(rows)
    by_eid = {r["evidence_id"]: r for r in out}
    assert by_eid["ev_1"]["authority_score"] == pytest.approx(0.95)  # T1 prior
    assert by_eid["ev_2"]["authority_score"] == pytest.approx(0.15)  # T7 prior
    assert by_eid["ev_3"]["authority_score"] == pytest.approx(0.42)  # real weight preserved
    assert by_eid["ev_1"]["authority_score_source"] == "tier_prior"
    # caller's rows never mutated
    assert "authority_score" not in rows[0]


def test_b9a_join_feeds_nonzero_weight_mass(monkeypatch):
    """The joined authority_score flows to weight_mass.aggregate_weight_mass => non-zero cluster_mass
    (the forensic weight_mass=0.0 defect is fixed)."""
    monkeypatch.setenv("PG_CREDIBILITY_TIER_AUTHORITY_JOIN", "1")
    from src.polaris_graph.synthesis import credibility_pass as cp
    from src.polaris_graph.synthesis.weight_mass import aggregate_weight_mass
    importlib.reload(cp)

    class _Claim:
        def __init__(self, ccid, eid):
            self.claim_cluster_id = ccid
            self.evidence_id = eid

    rows = [{"evidence_id": "ev_1", "tier": "T1", "direct_quote": "x"}]
    joined = cp._join_tier_authority_prior(rows)
    # singleton row is its own canonical origin (no origin_cluster_id => uncollapsed singleton)
    masses = aggregate_weight_mass([_Claim("c1", "ev_1")], joined, [])
    assert masses, "weight_mass produced no claims"
    assert masses[0].weight_mass > 0.0  # was 0.0 before the join; now the T1 prior (0.95)


def test_b9a_canary_raises_only_on_opt_in(monkeypatch):
    from src.polaris_graph.synthesis import credibility_pass as cp
    importlib.reload(cp)
    zero_rows = [{"evidence_id": "ev_1", "tier": "T1", "authority_score": 0.0}]
    # default: warns, never raises (fail-open rule)
    cp._emit_zero_authority_canary(zero_rows)  # no exception
    # opt-in: raises a fail-loud wiring-break
    monkeypatch.setenv("PG_REQUIRE_NONZERO_AUTHORITY", "1")
    with pytest.raises(cp.CredibilityPassError):
        cp._emit_zero_authority_canary(zero_rows)


# ─────────────────────────────────────────────────────────────────────────────
# B9(b) — distinct DOIs never join one origin cluster on body-cosine alone
# ─────────────────────────────────────────────────────────────────────────────
def test_b9b_distinct_dois_stay_independent_despite_near_dup_body():
    from src.polaris_graph.synthesis.independence_collapse import collapse_independent_origins
    gov = ("gov.uk",)
    # Two DIFFERENT works (distinct DOIs) on DIFFERENT hosts whose bodies are near-identical chrome
    # (would cross the 0.85 cosine and falsely collapse pre-B9b).
    chrome_body = (
        "Affiliation Department of Economics University of Somewhere ISSN 1234-5678 "
        "Creative Commons Attribution License Received 2024 Accepted 2024 Published 2024"
    )
    rows = [
        {"evidence_id": "ev_a", "source_url": "https://a.example/x", "direct_quote": chrome_body,
         "doi": "10.1000/aaa"},
        {"evidence_id": "ev_b", "source_url": "https://b.example/y", "direct_quote": chrome_body,
         "doi": "10.1000/bbb"},
    ]
    res = collapse_independent_origins(rows, gov_suffixes=gov)
    assert res.independent_origin_count == 2  # distinct DOIs => two distinct origins
    assert res.assignments[0].origin_cluster_id != res.assignments[1].origin_cluster_id


def test_b9b_same_doi_still_collapses():
    from src.polaris_graph.synthesis.independence_collapse import collapse_independent_origins
    gov = ("gov.uk",)
    body = "The agency announced quarterly emissions fell twelve percent after the new regulation."
    rows = [
        {"evidence_id": "ev_a", "source_url": "https://a.example/x", "direct_quote": body,
         "doi": "10.1000/same"},
        {"evidence_id": "ev_b", "source_url": "https://b.example/y", "direct_quote": body,
         "doi": "10.1000/same"},
    ]
    res = collapse_independent_origins(rows, gov_suffixes=gov)
    assert res.independent_origin_count == 1  # SAME doi + near-dup body => one origin


def test_b9b_same_doi_cross_mirror_collapses_to_one_origin():
    """B9(b)/(c) connector: arXiv + a PMC mirror of ONE paper (same DOI, DIFFERENT scholarly-mirror
    hosts, DIFFERENT bodies) MUST share one origin — overriding the mirror-allowlist skip — so the
    B9(c) mirror-cite collapse can actually fire on the canonical cross-mirror pair."""
    from src.polaris_graph.synthesis.independence_collapse import collapse_independent_origins
    gov = ("gov.uk",)
    rows = [
        {"evidence_id": "ev_037", "source_url": "https://arxiv.org/abs/2401.00001",
         "direct_quote": "preprint abstract text about GenAI employment effects",
         "doi": "10.1000/onepaper"},
        {"evidence_id": "ev_035", "source_url": "https://ncbi.nlm.nih.gov/pmc/articles/x",
         "direct_quote": "published version with a differently worded abstract",
         "doi": "10.1000/onepaper"},
    ]
    res = collapse_independent_origins(rows, gov_suffixes=gov)
    assert res.independent_origin_count == 1  # same DOI => one origin even across mirror hosts
    assert res.assignments[0].origin_cluster_id == res.assignments[1].origin_cluster_id


def test_b9b_distinct_doi_mirrors_stay_independent():
    """Guard the other side: two DIFFERENT papers each on a mirror host (distinct DOIs) stay two
    origins — the same-DOI union must not over-collapse distinct works."""
    from src.polaris_graph.synthesis.independence_collapse import collapse_independent_origins
    gov = ("gov.uk",)
    rows = [
        {"evidence_id": "ev_1", "source_url": "https://arxiv.org/abs/2401.00001",
         "direct_quote": "paper one", "doi": "10.1000/aaa"},
        {"evidence_id": "ev_2", "source_url": "https://ssrn.com/abstract=2",
         "direct_quote": "paper two", "doi": "10.1000/bbb"},
    ]
    res = collapse_independent_origins(rows, gov_suffixes=gov)
    assert res.independent_origin_count == 2


# ─────────────────────────────────────────────────────────────────────────────
# B9(c) — same-origin mirror cites collapse to one citation + note
# ─────────────────────────────────────────────────────────────────────────────
def test_b9c_mirror_cites_collapse(monkeypatch):
    monkeypatch.setenv("PG_MIRROR_CITE_COLLAPSE", "1")
    from src.polaris_graph.generator import provenance_generator as pg
    importlib.reload(pg)
    # nums 11 and 12 are two mirrors of ONE origin; 13 is a distinct origin.
    origin_by_num = {11: "origin::ev_037", 12: "origin::ev_037", 13: "origin::ev_099"}
    collapsed, n = pg.collapse_mirror_citation_numbers([11, 12, 13], origin_by_num)
    assert collapsed == [11, 13]   # the mirror (12) folded into 11; the distinct origin (13) kept
    assert n == 1


def test_b9c_distinct_origins_never_collapse(monkeypatch):
    monkeypatch.setenv("PG_MIRROR_CITE_COLLAPSE", "1")
    from src.polaris_graph.generator import provenance_generator as pg
    importlib.reload(pg)
    origin_by_num = {1: "origin::a", 2: "origin::b", 3: "origin::c"}
    collapsed, n = pg.collapse_mirror_citation_numbers([1, 2, 3], origin_by_num)
    assert collapsed == [1, 2, 3]  # all distinct origins => real §-1.3 multi-source preserved
    assert n == 0


def test_b9c_blank_origin_never_collapses(monkeypatch):
    monkeypatch.setenv("PG_MIRROR_CITE_COLLAPSE", "1")
    from src.polaris_graph.generator import provenance_generator as pg
    importlib.reload(pg)
    # blank/unknown origins must NEVER fold (under-collapse is the safe direction)
    collapsed, n = pg.collapse_mirror_citation_numbers([5, 6], {5: "", 6: ""})
    assert collapsed == [5, 6]
    assert n == 0


# ─────────────────────────────────────────────────────────────────────────────
# B13 — analyst-synthesis deviation check: KEEP-and-LABEL, never delete
# ─────────────────────────────────────────────────────────────────────────────
def test_b13_unsupported_sentence_labeled_supported_unchanged(monkeypatch):
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_DEVIATION_CHECK", "1")
    monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
    from src.polaris_graph.generator import analyst_synthesis_deviation_check as dc
    importlib.reload(dc)

    bibliography = [
        {"evidence_id": "ev_1", "title": "A", "url": "u1", "tier": "T1"},  # [1]
        {"evidence_id": "ev_2", "title": "B", "url": "u2", "tier": "T2"},  # [2]
    ]
    evidence_rows = [
        {"evidence_id": "ev_1", "direct_quote": "employment can grow with automation"},
        {"evidence_id": "ev_2", "direct_quote": "the study measured task completion times"},
    ]
    text = (
        "Employment can actually grow as GenAI adoption widens [1]. "
        "Hatte and Somers asserted genuine predictive validity for the metric [2]. "
        "This interpretation is offered without any cited source."
    )

    # Deterministic fake judge: the [1] sentence IS supported; the [2] sentence is NOT.
    def _fake_judge(claim: str, span: str) -> bool:
        return "employment" in span.lower() and "grow" in span.lower()

    labeled, tel = dc.screen_synthesis_against_baskets(
        text, bibliography, evidence_rows, judge_fn=_fake_judge,
    )
    # the supported [1] sentence is UNCHANGED (no marker)
    assert "Employment can actually grow as GenAI adoption widens [1]." in labeled
    # the unsupported [2] sentence is KEPT and LABELED low (never deleted)
    assert "predictive validity for the metric [2]" in labeled
    assert "[confidence: low" in labeled
    assert tel["synthesis_deviation_labeled_count"] == 1
    # the uncited sentence is KEPT and labeled no-source
    assert "[confidence: no-source-found" in labeled
    assert tel["synthesis_deviation_unresolved_count"] == 1
    # NEVER deletes: every original sentence's core text survives
    assert "without any cited source" in labeled


def test_b13_disabled_is_passthrough(monkeypatch):
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_DEVIATION_CHECK", "0")
    from src.polaris_graph.generator import analyst_synthesis_deviation_check as dc
    importlib.reload(dc)
    text = "Unsupported claim [1]."
    out, tel = dc.screen_synthesis_against_baskets(
        text, [{"evidence_id": "ev_1"}], [{"evidence_id": "ev_1", "direct_quote": "z"}],
        judge_fn=lambda c, s: False,
    )
    assert out == text  # byte-identical when off
    assert tel["synthesis_deviation_labeled_count"] == 0


def test_b13_judge_fault_fails_closed_low(monkeypatch):
    monkeypatch.setenv("PG_ANALYST_SYNTHESIS_DEVIATION_CHECK", "1")
    monkeypatch.setenv("PG_SWEEP_ANALYST_SYNTHESIS", "1")
    from src.polaris_graph.generator import analyst_synthesis_deviation_check as dc
    importlib.reload(dc)

    def _boom(claim: str, span: str) -> bool:
        raise RuntimeError("judge socket flap")

    bibliography = [{"evidence_id": "ev_1", "title": "A", "url": "u", "tier": "T1"}]
    rows = [{"evidence_id": "ev_1", "direct_quote": "some span text"}]
    labeled, tel = dc.screen_synthesis_against_baskets(
        "A grounded-looking claim [1].", bibliography, rows, judge_fn=_boom,
    )
    assert "[confidence: low" in labeled  # fail-closed to LOW (over-label = safe)
    assert tel["synthesis_deviation_labeled_count"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# B17 — sentence_repair marker prune: drop a non-supporting marker only when CONFIRMED
# ─────────────────────────────────────────────────────────────────────────────
def _fake_entailment_judge(supported_spans):
    """A fake _EntailmentJudge: judge(claim, span) -> (verdict, reason). A span in ``supported_spans``
    returns ENTAILED; anything else returns NEUTRAL (=> droppable)."""
    class _J:
        def judge(self, claim, span):
            for s in supported_spans:
                if s and s in span:
                    return ("ENTAILED", "")
            return ("NEUTRAL", "")
    return _J()


@pytest.mark.asyncio
async def test_b17_confirmed_subset_prune_accepted(monkeypatch):
    monkeypatch.setenv("PG_REPAIR_MARKER_PRUNE_ENABLED", "1")
    monkeypatch.setenv("PG_REPAIR_LOOP_ENABLED", "true")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    from src.polaris_graph.generator import sentence_repair as sr
    importlib.reload(sr)
    from src.polaris_graph.generator.provenance_generator import SentenceVerification, ProvenanceToken

    # Evidence pool: ev_a supports the claim; ev_b does NOT.
    pool = {
        "ev_a": {"direct_quote": "GenAI raised task throughput in the employment trial"},
        "ev_b": {"direct_quote": "unrelated text about rainfall in the alpine watershed"},
    }
    # A dropped multi-citation sentence citing BOTH ev_a (supporting) and ev_b (non-supporting).
    sentence = (
        "GenAI raised task throughput [#ev:ev_a:0-48][#ev:ev_b:0-50]"
    )
    toks = [
        ProvenanceToken(raw="[#ev:ev_a:0-48]", evidence_id="ev_a", start=0, end=48),
        ProvenanceToken(raw="[#ev:ev_b:0-50]", evidence_id="ev_b", start=0, end=50),
    ]
    sv = SentenceVerification(
        sentence=sentence, tokens=toks, is_verified=False,
        failure_reasons=["entailment_failed:ev_b"],
    )
    kept = [SentenceVerification(sentence="seed [#ev:ev_a:0-48][#ev:ev_b:0-50]",
                                 tokens=toks, is_verified=True)]

    # The repair model prunes ev_b (the non-supporting marker), keeping ev_a only.
    async def _fake_repair(*, dropped, evidence_pool, model, max_tokens, temperature):
        return "text", "GenAI raised task throughput [#ev:ev_a:0-48]", 1, 1

    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)

    new_kept, final_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=kept, dropped=[sv], evidence_pool=pool,
        marker_prune_judge=_fake_entailment_judge(
            supported_spans=["GenAI raised task throughput in the employment trial"]
        ),
    )
    # The confirmed prune was ACCEPTED (not a token_set_violation); ev_b was pruned.
    assert tel.markers_pruned == 1
    assert tel.token_set_violations == 0


@pytest.mark.asyncio
async def test_b17_unconfirmed_prune_rejected_fail_closed(monkeypatch):
    """If the judge says the dropped span IS supported (or errors), the prune is REJECTED — the model
    cannot prune a genuinely-supporting span to dodge repair (faithfulness STRENGTHENED, never relaxed)."""
    monkeypatch.setenv("PG_REPAIR_MARKER_PRUNE_ENABLED", "1")
    monkeypatch.setenv("PG_REPAIR_LOOP_ENABLED", "true")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    from src.polaris_graph.generator import sentence_repair as sr
    importlib.reload(sr)
    from src.polaris_graph.generator.provenance_generator import SentenceVerification, ProvenanceToken

    pool = {
        "ev_a": {"direct_quote": "GenAI raised task throughput in the employment trial"},
        "ev_b": {"direct_quote": "GenAI also improved retention across the cohort study"},
    }
    toks = [
        ProvenanceToken(raw="[#ev:ev_a:0-48]", evidence_id="ev_a", start=0, end=48),
        ProvenanceToken(raw="[#ev:ev_b:0-50]", evidence_id="ev_b", start=0, end=50),
    ]
    sv = SentenceVerification(
        sentence="GenAI raised task throughput [#ev:ev_a:0-48][#ev:ev_b:0-50]",
        tokens=toks, is_verified=False, failure_reasons=["entailment_failed:ev_b"],
    )
    kept = [SentenceVerification(sentence="seed [#ev:ev_a:0-48][#ev:ev_b:0-50]",
                                 tokens=toks, is_verified=True)]

    async def _fake_repair(*, dropped, evidence_pool, model, max_tokens, temperature):
        return "text", "GenAI raised task throughput [#ev:ev_a:0-48]", 1, 1

    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)

    # The judge says BOTH spans are supported -> the prune of ev_b is NOT confirmed -> REJECTED.
    new_kept, final_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=kept, dropped=[sv], evidence_pool=pool,
        marker_prune_judge=_fake_entailment_judge(supported_spans=["GenAI"]),
    )
    assert tel.markers_pruned == 0
    assert tel.token_set_violations == 1  # rejected as a violation, original drop kept
    assert sv in final_dropped


@pytest.mark.asyncio
async def test_b17_addition_always_rejected(monkeypatch):
    """Adding a NEW marker (not in the original) is always a violation, prune flag on or off."""
    monkeypatch.setenv("PG_REPAIR_MARKER_PRUNE_ENABLED", "1")
    monkeypatch.setenv("PG_REPAIR_LOOP_ENABLED", "true")
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    from src.polaris_graph.generator import sentence_repair as sr
    importlib.reload(sr)
    from src.polaris_graph.generator.provenance_generator import SentenceVerification, ProvenanceToken

    pool = {"ev_a": {"direct_quote": "GenAI raised task throughput in the employment trial"}}
    toks = [ProvenanceToken(raw="[#ev:ev_a:0-48]", evidence_id="ev_a", start=0, end=48)]
    sv = SentenceVerification(
        sentence="GenAI raised task throughput [#ev:ev_a:0-48]",
        tokens=toks, is_verified=False, failure_reasons=["entailment_failed:ev_a"],
    )
    kept = [SentenceVerification(sentence="seed [#ev:ev_a:0-48]", tokens=toks, is_verified=True)]

    async def _fake_repair(*, dropped, evidence_pool, model, max_tokens, temperature):
        # ADD a never-cited marker ev_z — must be rejected.
        return "text", "GenAI raised task throughput [#ev:ev_a:0-48][#ev:ev_z:0-10]", 1, 1

    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)
    new_kept, final_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=kept, dropped=[sv], evidence_pool=pool,
        marker_prune_judge=_fake_entailment_judge(supported_spans=[]),
    )
    assert tel.token_set_violations == 1
    assert tel.markers_pruned == 0
