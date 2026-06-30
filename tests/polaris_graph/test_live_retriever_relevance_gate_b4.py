"""B4 (b1b10 redesign, I-arch-005 Phase-2/3): relevance-THRESHOLD + fetch-BUDGET
retrieval selection.

Unit tests for the `live_retriever` B4 lane:
  - `_relevance_gate_enabled` / `_relevance_gate_threshold` env knobs.
  - `_candidate_relevance_scores` (a THIN wrapper over B1's
    `evidence_selector._semantic_relevance_scores` — NO B4-private scoring loop,
    NO B4-private canary; the scorer contract cannot drift, Codex B4 iter-2 P1).
  - `_relevance_threshold_select` (topical gate + cost budget + unfetched tail).

NO real model load: B1's lazily-imported embedder + cosine primitive are
monkeypatched (§8.4 + parity with the existing `test_no_embedder_model_loaded`).
The acceptance deltas are made deterministic by injecting cosine scores.

Acceptance (PHASE2_3_LANE_SPECS.md LANE-RETRIEVAL):
  (a) a relevant LOW-TIER source is NOT dropped by the count cut — the B4 gate
      keeps it because gating is by TOPICAL relevance only, never credibility/tier.
  (b) the threshold+budget path keeps MORE on-topic sources than the old fixed-N
      cut on a long-question (drb_76-shape) fixture corpus.
  (c) the unfetched-but-relevant tail is RECORDED (count + score band).
  (d) faithfulness untouched — this lane only changes the pre-fetch candidate menu
      + an additive weight + telemetry; no faithfulness check lives here.
"""

from __future__ import annotations

import builtins

import pytest

import src.polaris_graph.retrieval.live_retriever as lr
from src.polaris_graph.retrieval.live_retriever import (
    RelevanceGateResult,
    _candidate_relevance_scores,
    _rerank_and_reserve,
    _relevance_gate_enabled,
    _relevance_gate_threshold,
    _relevance_threshold_select,
)
from src.polaris_graph.retrieval.prefetch_offtopic_filter import SearchCandidate

# A long, multi-part research question (the drb_76 shape): a row whose domain
# vocabulary does NOT lexically overlap these exact words scores near-zero on the
# lexical scorer (denominator = len(question tokens)).
_LONG_QUESTION = (
    "What is the predominant mechanism by which the gut microbiome can mitigate "
    "or retard colorectal tumorigenesis, and which dietary or pharmacological "
    "interventions plausibly alter that pathway in human populations?"
)


def _cand(url: str, *, title: str = "", snippet: str = "", source: str = "serper", origin: str = "") -> SearchCandidate:
    return SearchCandidate(url=url, title=title, snippet=snippet, source=source, query_origin=origin)


def _seed(url: str) -> SearchCandidate:
    return SearchCandidate(url=url, title="", snippet="", source="primary_trial_doi", query_origin="primary_trial_doi_seed")


class _FakeEmbedder:
    """Marker object so `_get_semantic_embedder` returns non-None. Never used for
    real encoding — `_similarity_scores` is monkeypatched to return injected scores."""


def _patch_semantic(monkeypatch, score_by_text: dict[str, float]):
    """Patch B1's lazily-imported embedder + cosine primitive so scoring is
    deterministic and NO real model loads. B4 now REUSES B1's
    `evidence_selector._semantic_relevance_scores`, which calls
    `evidence_selector._get_semantic_embedder` and (via that module)
    `prefetch_offtopic_filter._similarity_scores(embedder, anchor, row_texts)` —
    where `row_texts` are B1's `_row_embed_text` outputs (statement + direct_quote).

    The fake keys on the candidate's `snippet_text` (mapped onto `statement`). B1's
    `_row_embed_text` joins statement+direct_quote with a space, so the embed text
    carries a trailing space; the fake therefore looks up by `text.strip()` so the
    test score map stays keyed by the clean `snippet_text`. There is NO prepended
    self-similarity canary anymore (deleted in iter-3 — B1's `None` is the shared
    infra-failure signal, not a B4-private canary)."""
    import src.polaris_graph.retrieval.evidence_selector as es
    import src.polaris_graph.retrieval.prefetch_offtopic_filter as pf

    monkeypatch.setattr(es, "_get_semantic_embedder", lambda: _FakeEmbedder())

    _text_score = dict(score_by_text)

    def _fake_sims(embedder, anchor, texts):
        # B1 passes the row embed texts (statement[+direct_quote]); look up by the
        # stripped text so the trailing join-space does not break the match.
        return [_text_score.get((t or "").strip(), 0.0) for t in texts]

    monkeypatch.setattr(pf, "_similarity_scores", _fake_sims)
    return _text_score


# ── env knobs ────────────────────────────────────────────────────────────────
def test_gate_default_on(monkeypatch):
    """I-deepfix-001 B1 keystone (2026-06-28): the B4 pre-fetch relevance gate now
    defaults ON. Explicit off-values revert to the byte-identical legacy count-cut."""
    monkeypatch.delenv("PG_RETRIEVAL_RELEVANCE_GATE", raising=False)
    assert _relevance_gate_enabled() is True  # default ON now
    for v in ("0", "false", "no", "off", "", "disabled"):
        monkeypatch.setenv("PG_RETRIEVAL_RELEVANCE_GATE", v)
        assert _relevance_gate_enabled() is False
    for v in ("1", "true", "yes", "on", "ON", "True"):
        monkeypatch.setenv("PG_RETRIEVAL_RELEVANCE_GATE", v)
        assert _relevance_gate_enabled() is True


def test_threshold_is_b1_relevance_floor(monkeypatch):
    """P1.1: B4 reuses B1's `PG_RELEVANCE_FLOOR` (default 0.30) via B1's
    `parse_relevance_floor` — ONE floor, ONE relevance story across B1+B4. There
    is NO independent B4-private `PG_RETRIEVAL_RELEVANCE_THRESHOLD` 0.35 default."""
    monkeypatch.delenv("PG_RELEVANCE_FLOOR", raising=False)
    # Default is B1's _DEFAULT_RELEVANCE_FLOOR (0.30), NOT a B4-private 0.35.
    assert _relevance_gate_threshold() == pytest.approx(0.30)
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.5")
    assert _relevance_gate_threshold() == pytest.approx(0.5)


def test_threshold_fails_loud_on_garbage_floor(monkeypatch):
    """P1.1: a garbage / out-of-range `PG_RELEVANCE_FLOOR` FAILS LOUD via B1's
    `parse_relevance_floor` (raises ValueError) — identical to B1's behaviour, so
    a misconfigured floor can never silently pass an unbounded, off-topic pool.
    (`parse_relevance_floor` range is (0.0, 1.0], so 0.0 and >1.0 both raise.)"""
    for bad in ("-0.1", "1.5", "abc", "inf", "0", "0.0"):
        monkeypatch.setenv("PG_RELEVANCE_FLOOR", bad)
        with pytest.raises(ValueError):
            _relevance_gate_threshold()


# ── (a) a relevant LOW-TIER source is NOT dropped — gating is topical-only ─────
def test_low_tier_relevant_source_not_dropped_by_count_cut(monkeypatch):
    """P2.2 (Codex iter-1): the count cut must ACTUALLY BIND for this to prove the
    regression it claims. Two candidates, `fetch_cap=1` => the legacy lexical
    count-cut keeps exactly ONE and DROPS the other; B4 keeps BOTH on-topic
    survivors at the SAME cap (its fetch BUDGET drops one, but RECORDS it as the
    unfetched-relevant tail, not as a topical/credibility drop).

    The low-tier source's domain vocabulary ("butyrate Fusobacterium ...") has
    near-zero LEXICAL overlap with the long question's exact words, while the
    high-tier title shares "microbiome/colorectal/mechanism" — so the legacy
    lexical cut ranks the high-tier ABOVE it and, at cap=1, the legacy cut DROPS
    the low-tier on-topic source. B4 scores the low-tier 0.55 by COSINE (on-topic)
    so it clears the threshold and is kept on-topic, never gated out on tier."""
    high_tier = _cand("https://journal/a", title="microbiome colorectal mechanism", source="s2", origin="q1")
    low_tier = _cand("https://blog/b", title="butyrate Fusobacterium tumor patient story", source="serper", origin="q1")
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    _patch_semantic(monkeypatch, {
        high_tier.snippet_text: 0.80,
        low_tier.snippet_text: 0.55,  # on-topic by cosine, low overlap lexically
    })

    cap = 1  # BINDS on 2 candidates — the legacy count-cut must drop one.
    # First confirm the legacy lexical count-cut at this binding cap DROPS the
    # low-tier on-topic source (the regression B4 fixes).
    legacy_out = _rerank_and_reserve(
        [high_tier, low_tier], research_question=_LONG_QUESTION,
        fetch_cap=cap, n_seed_injected=0,
    )
    legacy_urls = {c.url for c in legacy_out}
    assert legacy_urls == {"https://journal/a"}      # low-tier on-topic CUT by count
    assert "https://blog/b" not in legacy_urls

    # B4 at the SAME cap keeps BOTH on-topic (one fetched, one in the recorded tail);
    # neither is gated out on topical relevance, and tier is never consulted.
    out, weights, gate = _relevance_threshold_select(
        [high_tier, low_tier], research_question=_LONG_QUESTION,
        sub_queries=[], fetch_cap=cap, n_seed_injected=0,
    )
    out_urls = {c.url for c in out}
    assert "https://journal/a" in out_urls           # highest-cosine fetched
    # The low-tier on-topic source is NOT off-topic-dropped — it clears the gate
    # and lands in the recorded unfetched-relevant tail (a COST bound, not a tier
    # or relevance drop). kept_on_topic counts BOTH; demoted (below-floor) is zero.
    assert gate.kept_on_topic == 2 and gate.demoted_below_floor == 0
    assert gate.fetched_budget == 1 and gate.unfetched_relevant_tail == 1
    # The fetched survivor carries its cosine forward as a weight.
    assert weights["https://journal/a"] == pytest.approx(0.80)


# ── (a') topical gate ignores tier even when budget fits ALL survivors ─────────
def test_low_tier_relevant_source_kept_when_budget_fits_all(monkeypatch):
    """Companion to the count-cut-binds case: with a budget large enough for ALL
    on-topic survivors, BOTH are fetched and BOTH carry a relevance weight — the
    gate consults ONLY cosine, never tier/credibility."""
    high_tier = _cand("https://journal/a", title="microbiome colorectal mechanism", source="s2", origin="q1")
    low_tier = _cand("https://blog/b", title="butyrate Fusobacterium tumor patient story", source="serper", origin="q1")
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    _patch_semantic(monkeypatch, {
        high_tier.snippet_text: 0.80,
        low_tier.snippet_text: 0.55,
    })
    out, weights, gate = _relevance_threshold_select(
        [high_tier, low_tier], research_question=_LONG_QUESTION,
        sub_queries=[], fetch_cap=10, n_seed_injected=0,
    )
    out_urls = {c.url for c in out}
    assert "https://blog/b" in out_urls and "https://journal/a" in out_urls
    assert weights["https://blog/b"] == pytest.approx(0.55)
    assert weights["https://journal/a"] == pytest.approx(0.80)
    assert gate.kept_on_topic == 2 and gate.demoted_below_floor == 0


# ── (b) threshold+budget keeps MORE on-topic than the old fixed-N count cut ─────
# AT THE SAME fetch_cap (the real production operating point — the caller hands
# BOTH paths the identical cap). The delta is the MECHANISM, not a bigger budget:
# the drb_76 inversion is decoys that lexically reuse the question's exact words
# (high lexical overlap, irrelevant) outranking on-topic domain-vocab sources
# (zero lexical overlap, on-topic). Verified offline: each decoy scores 0.471
# lexically vs 0.000 for each on-topic title against this question — so the legacy
# fixed-N cut fills the cap with decoys and keeps ZERO on-topic, while B4 (semantic
# cosine) keeps the on-topic and gates the decoys out, at the SAME cap.
def test_threshold_keeps_more_on_topic_than_fixed_n_at_equal_cap(monkeypatch):
    # On-topic: domain vocabulary ABSENT from the long question (lexical ~0).
    on = [
        _cand("https://on/0", title="butyrate short-chain fatty acid colonocyte Treg", origin="q1"),
        _cand("https://on/1", title="Fusobacterium nucleatum adenoma carcinoma sequence", origin="q1"),
        _cand("https://on/2", title="bile acid FXR signaling epithelium homeostasis", origin="q1"),
    ]
    # Off-topic DECOYS: reuse MANY of the question's exact content-words (high
    # lexical overlap) but are irrelevant — the legacy lexical scorer ranks these
    # ABOVE the on-topic sources and fills the cap with them.
    decoys = [
        _cand("https://decoy/0", title="dietary pharmacological interventions human populations pathway predominant mechanism", origin="q1"),
        _cand("https://decoy/1", title="predominant dietary mechanism interventions populations pathway human colorectal", origin="q1"),
        _cand("https://decoy/2", title="mechanism interventions populations pathway human dietary predominant retard", origin="q1"),
    ]
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    # Inject cosine: on-topic high, decoys low (the truth the lexical scorer misses).
    scores = {c.snippet_text: 0.60 for c in on}
    scores.update({c.snippet_text: 0.05 for c in decoys})
    _patch_semantic(monkeypatch, scores)

    cap = 3  # SAME cap for both paths — the production operating point.
    b4_out, _w, gate = _relevance_threshold_select(
        on + decoys, research_question=_LONG_QUESTION, sub_queries=[],
        fetch_cap=cap, n_seed_injected=0,
    )
    b4_kept_on = sum(1 for c in b4_out if c.url.startswith("https://on/"))
    assert b4_kept_on == 3                                   # all 3 on-topic kept
    # The decoys are DEMOTED (below floor) to the tail, not hard-dropped: at cap=3
    # the 3 above-floor on-topic sources FILL the budget, so the demoted decoys land
    # in the tail (fetched_to_fill=0). They are absent from the budget output because
    # the budget was full of higher-relevance sources — NOT because of a hard cut.
    assert all(not c.url.startswith("https://decoy/") for c in b4_out)  # decoys demoted past budget
    assert gate.demoted_below_floor == 3                     # 3 decoys below threshold (DEMOTED)
    assert gate.demoted_fetched_to_fill == 0                 # budget filled by above-floor
    assert gate.demoted_tail == 3                            # all 3 demoted to the cost tail

    # Legacy lexical fixed-N cut at the SAME cap fills with the higher-lexical
    # decoys and keeps strictly fewer on-topic (here ZERO).
    legacy_out = _rerank_and_reserve(
        on + decoys, research_question=_LONG_QUESTION, fetch_cap=cap, n_seed_injected=0,
    )
    legacy_kept_on = sum(1 for c in legacy_out if c.url.startswith("https://on/"))
    assert legacy_kept_on == 0                               # decoys monopolized the cap
    assert b4_kept_on > legacy_kept_on                       # B4 keeps MORE on-topic at EQUAL cap


# ── (c) the unfetched-but-relevant tail is RECORDED, not dropped-and-forgotten ──
def test_unfetched_relevant_tail_is_recorded(monkeypatch):
    """Four on-topic candidates, budget=2: two are fetched, the other two are the
    unfetched-but-relevant tail. The gate telemetry records the tail count + score
    band; the tail is NOT counted as off-topic (it is a COST drop, above threshold)."""
    cands = [
        _cand("https://c/0", title="aaa", origin="q1"),
        _cand("https://c/1", title="bbb", origin="q1"),
        _cand("https://c/2", title="ccc", origin="q1"),
        _cand("https://c/3", title="ddd", origin="q1"),
    ]
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    _patch_semantic(monkeypatch, {
        cands[0].snippet_text: 0.90,
        cands[1].snippet_text: 0.80,
        cands[2].snippet_text: 0.50,  # tail
        cands[3].snippet_text: 0.40,  # tail
    })
    out, weights, gate = _relevance_threshold_select(
        cands, research_question=_LONG_QUESTION, sub_queries=[],
        fetch_cap=2, n_seed_injected=0,
    )
    assert gate.kept_on_topic == 4            # all 4 above threshold
    assert gate.demoted_below_floor == 0      # none below floor (none demoted)
    assert gate.fetched_budget == 2           # budget bounds the fetch
    assert gate.unfetched_relevant_tail == 2  # the tail is RECORDED
    assert gate.tail_score_max == pytest.approx(0.50)
    assert gate.tail_score_min == pytest.approx(0.40)
    # Only the budget-fetched survivors carry a weight (top-2 by score).
    assert set(weights.keys()) == {"https://c/0", "https://c/1"}
    # The gate dict is JSON-serializable telemetry.
    d = gate.to_dict()
    assert d["unfetched_relevant_tail"] == 2 and d["scorer"] == "semantic_v2"


# ── seed lane preserved: seeds never scored, never dropped, prepended first ─────
def test_seeds_never_scored_or_dropped(monkeypatch):
    seeds = [_seed("https://doi.org/10.1056/seed1")]
    non = _cand("https://n/0", title="microbiome", origin="q1")
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    _patch_semantic(monkeypatch, {non.snippet_text: 0.7})
    out, weights, gate = _relevance_threshold_select(
        seeds + [non], research_question=_LONG_QUESTION, sub_queries=[],
        fetch_cap=5, n_seed_injected=1,
    )
    assert out[0].source == "primary_trial_doi"        # seed prepended first
    assert "https://doi.org/10.1056/seed1" in {c.url for c in out}
    assert gate.total_scored == 1                       # only the non-seed scored
    assert "https://doi.org/10.1056/seed1" not in weights  # seed carries no weight


# ── LOUD fallback: embedder unavailable -> (None, {}, None) so caller uses lexical ─
def test_embedder_unavailable_signals_lexical_fallback(monkeypatch):
    import src.polaris_graph.retrieval.evidence_selector as es
    monkeypatch.setattr(es, "_get_semantic_embedder", lambda: None)
    out, weights, gate = _relevance_threshold_select(
        [_cand("https://n/0", title="x", origin="q1")],
        research_question=_LONG_QUESTION, sub_queries=[], fetch_cap=5, n_seed_injected=0,
    )
    assert out is None and weights == {} and gate is None


def test_scorer_infra_failure_fails_open_to_lexical(monkeypatch):
    """I-deepfix-001 Codex wave-1 P0: a LOADED embedder whose `_similarity_scores`
    returns None (infra failure: no embed interface / zero-norm query / encode raise)
    must make B1's `_semantic_relevance_scores` return None so B4 falls back LOUDLY
    to the lexical cut — it must NOT mass-drop the corpus by treating the failure as
    all-zero below-threshold scores."""
    import src.polaris_graph.retrieval.evidence_selector as es
    import src.polaris_graph.retrieval.prefetch_offtopic_filter as pf
    monkeypatch.setattr(es, "_get_semantic_embedder", lambda: _FakeEmbedder())
    # Loaded embedder, but the shared scorer signals an infra failure (None).
    monkeypatch.setattr(pf, "_similarity_scores", lambda embedder, anchor, texts: None)
    out, weights, gate = _relevance_threshold_select(
        [_cand("https://n/0", title="x", origin="q1"),
         _cand("https://n/1", title="y", origin="q1")],
        research_question=_LONG_QUESTION, sub_queries=["facet"], fetch_cap=5,
        n_seed_injected=0,
    )
    # None signals the caller to run the legacy lexical cut (keep candidates),
    # never a (selected=[], all-dropped) hard cut on a scoring error.
    assert out is None and weights == {} and gate is None


def test_relevance_scores_none_when_no_anchors(monkeypatch):
    """Empty question AND no sub-queries -> B1's scorer returns None, so B4's thin
    wrapper returns None (fall back loudly), never a silent keep-all."""
    import src.polaris_graph.retrieval.evidence_selector as es
    monkeypatch.setattr(es, "_get_semantic_embedder", lambda: _FakeEmbedder())
    assert _candidate_relevance_scores("", [], [_cand("https://x", title="y")]) is None


# ── max-over-anchors: a candidate matching ONE sub-query facet clears the floor ─
def test_max_over_subquery_anchors(monkeypatch):
    """B1's `_semantic_relevance_scores` takes the per-row MAX cosine over
    {question} ∪ {sub-queries}; B4 inherits that behavior unchanged. The whole
    question scores low; sub-query 2 scores high -> max wins. No prepended canary —
    `_similarity_scores` is called with just the row embed texts."""
    import src.polaris_graph.retrieval.evidence_selector as es
    import src.polaris_graph.retrieval.prefetch_offtopic_filter as pf
    monkeypatch.setattr(es, "_get_semantic_embedder", lambda: _FakeEmbedder())
    cand = _cand("https://x", title="facet-two text")

    def _fake_sims(embedder, anchor, texts):
        # The whole question scores low; sub-query 2 scores high -> max wins.
        if anchor == _LONG_QUESTION:
            base = 0.10
        elif anchor == "facet two sub query":
            base = 0.72
        else:
            base = 0.0
        return [base for _ in texts]

    monkeypatch.setattr(pf, "_similarity_scores", _fake_sims)
    scores = _candidate_relevance_scores(
        _LONG_QUESTION, ["facet one sub query", "facet two sub query"], [cand],
    )
    assert scores == [pytest.approx(0.72)]  # max over anchors, not the low question score


# ── no model import on the B4 OFF path (parity with the legacy rerank test) ─────
def test_off_path_never_imports_embedder(monkeypatch):
    """With the gate OFF, `_rerank_and_reserve` runs and the semantic embedder is
    never imported (the heavy module-load guard). Mirrors the legacy
    test_no_embedder_model_loaded contract for the new lane."""
    real_import = builtins.__import__

    def _blocking_import(name, *args, **kwargs):
        if "sentence_transformers" in name or name == "torch":
            raise AssertionError(f"OFF path must not import a model: {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setenv("PG_RETRIEVAL_RELEVANCE_GATE", "0")
    assert _relevance_gate_enabled() is False
    monkeypatch.setattr(builtins, "__import__", _blocking_import)
    out = _rerank_and_reserve(
        [_cand("https://a", title="microbiome", origin="q1")],
        research_question=_LONG_QUESTION, fetch_cap=1, n_seed_injected=0,
    )
    assert len(out) == 1


# ── empty / zero-budget edges do not raise ──────────────────────────────────────
def test_edges_no_raise(monkeypatch):
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    # Only seeds present: no scoring, budget bounds the (empty) non-seeds.
    seeds = [_seed("https://doi.org/seed")]
    out, weights, gate = _relevance_threshold_select(
        seeds, research_question=_LONG_QUESTION, sub_queries=[], fetch_cap=0, n_seed_injected=1,
    )
    assert [c.url for c in out] == ["https://doi.org/seed"]
    assert gate.total_scored == 0
    # zero budget with non-seeds present (scorer patched): all become tail.
    cand = _cand("https://n/0", title="x", origin="q1")
    _patch_semantic(monkeypatch, {cand.snippet_text: 0.9})
    out2, w2, gate2 = _relevance_threshold_select(
        [cand], research_question=_LONG_QUESTION, sub_queries=[], fetch_cap=0, n_seed_injected=0,
    )
    assert out2 == []                       # budget 0 fetches nothing
    assert gate2.unfetched_relevant_tail == 1  # the on-topic candidate is the tail
    assert w2 == {}


# ── infra all-zero: handled by B1's scorer (no B4-private canary) ───────────────
def test_embedder_unavailable_via_b1_none_falls_back_loudly(monkeypatch):
    """B1's `_semantic_relevance_scores` returns None when the embedder is
    unavailable; B4's thin wrapper returns None on that and the selection path
    signals the LOUD lexical fallback `(None, {}, None)` — never a silent collapse.
    This is the shared infra-failure signal (B1's None), NOT a B4-private canary."""
    import src.polaris_graph.retrieval.evidence_selector as es
    monkeypatch.setattr(es, "_get_semantic_embedder", lambda: None)
    cands = [_cand(f"https://c/{i}", title=f"on-topic source {i}", origin="q1") for i in range(4)]
    assert _candidate_relevance_scores(_LONG_QUESTION, [], cands) is None
    out, weights, gate = _relevance_threshold_select(
        cands, research_question=_LONG_QUESTION, sub_queries=[],
        fetch_cap=10, n_seed_injected=0,
    )
    assert out is None and weights == {} and gate is None


def test_genuine_below_floor_is_demoted_not_dropped_fills_budget(monkeypatch):
    """§-1.3 DEMOTE-NOT-DROP (I-deepfix-001 D3, Codex iter-1 P1): a HEALTHY embedder
    scoring a candidate below the floor (cosine 0.0 for every anchor) now DEMOTES it,
    NOT drops it. With a budget large enough (fetch_cap=10 >> 1 candidate), the demoted
    below-floor candidate IS fetched-to-fill the budget — it is NEVER hard-dropped
    pre-fetch. Off-topic content with no overlap is caught by the downstream
    faithfulness engine (strict_verify), the ONLY sanctioned hard drop, not here.

    This is the CONVERSE of the old hard-drop test it replaces: the old code returned
    `out == []` (the below-floor source dropped before the budget). The fix makes the
    floor an ordering/disclosure boundary, so the source SURVIVES to the budget."""
    import src.polaris_graph.retrieval.evidence_selector as es
    import src.polaris_graph.retrieval.prefetch_offtopic_filter as pf
    monkeypatch.setattr(es, "_get_semantic_embedder", lambda: _FakeEmbedder())
    # Healthy embedder, candidate below floor (cosine 0.0 for every anchor).
    monkeypatch.setattr(pf, "_similarity_scores", lambda embedder, anchor, texts: [0.0 for _ in texts])
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    cands = [_cand("https://c/0", title="unrelated cooking recipe", origin="q1")]
    scores = _candidate_relevance_scores(_LONG_QUESTION, [], cands)
    assert scores == [pytest.approx(0.0)]           # real below-floor score, not None
    out, weights, gate = _relevance_threshold_select(
        cands, research_question=_LONG_QUESTION, sub_queries=[],
        fetch_cap=10, n_seed_injected=0,
    )
    out_urls = {c.url for c in out}
    assert "https://c/0" in out_urls                # DEMOTED, not dropped — fetched-to-fill
    assert gate is not None                         # NOT a fallback — a real verdict
    assert gate.kept_on_topic == 0                  # nothing above floor
    assert gate.demoted_below_floor == 1            # the below-floor source DEMOTED
    assert gate.demoted_fetched_to_fill == 1        # budget had room -> it IS fetched
    assert gate.demoted_tail == 0                   # none stranded in the tail
    assert gate.fetched_budget == 1
    assert weights["https://c/0"] == pytest.approx(0.0)  # carries its (low) weight forward


# ── empty-snippet contract: a text-less non-seed is DEMOTED, fetched-to-know ──────
def test_empty_snippet_nonseed_demoted_not_dropped(monkeypatch):
    """§-1.3 DEMOTE-NOT-DROP (I-deepfix-001 D3): a non-seed with EMPTY snippet_text has
    no text to embed, so B1's scorer scores it 0.0 — below the floor. The old code
    HARD-DROPPED it pre-fetch; the fix DEMOTES it (kept at the tail) and, with budget
    room (fetch_cap=10), FETCHES it ("fetch to know") instead of dropping it. The
    above-floor source still ranks FIRST (higher relevance); the empty-snippet row is
    demoted but SURVIVES. Seeds remain the floor-EXEMPT lane (split out pre-scoring,
    never scored) — see test_seeds_never_scored_or_dropped."""
    has_text = _cand("https://has/text", title="microbiome colorectal mechanism", origin="q1")
    no_text = _cand("https://no/text", title="", snippet="", source="serper", origin="q1")
    assert no_text.snippet_text == ""               # genuinely empty embed surface
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    # has_text scores 0.70 (above floor); no_text is not in the map => 0.0 (below floor).
    _patch_semantic(monkeypatch, {has_text.snippet_text: 0.70})
    out, weights, gate = _relevance_threshold_select(
        [has_text, no_text], research_question=_LONG_QUESTION, sub_queries=[],
        fetch_cap=10, n_seed_injected=0,
    )
    out_urls = {c.url for c in out}
    assert "https://has/text" in out_urls           # above-floor source kept (ranks first)
    assert "https://no/text" in out_urls            # text-less non-seed DEMOTED, fetched-to-know
    assert out[0].url == "https://has/text"          # above-floor ranks ahead of the demoted row
    assert gate.kept_on_topic == 1                  # the above-floor source
    assert gate.demoted_below_floor == 1            # the empty-snippet row is below floor (demoted)
    assert gate.demoted_fetched_to_fill == 1        # budget room -> the demoted row IS fetched
    assert gate.demoted_tail == 0


def test_empty_snippet_seed_is_kept_floor_exempt(monkeypatch):
    """Companion to the above: an empty-snippet SEED (primary-trial DOI lane) is the
    floor-EXEMPT analogue of B1's primary-trial anchor — split out pre-scoring, never
    dropped despite carrying no embeddable text. Proves the drop above hits only
    text-less NON-seeds, never the reserved seed lane."""
    seed = _seed("https://doi.org/10.1056/seed_empty")  # empty title+snippet
    assert seed.snippet_text == ""
    on = _cand("https://n/0", title="microbiome colorectal mechanism", origin="q1")
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    _patch_semantic(monkeypatch, {on.snippet_text: 0.70})
    out, weights, gate = _relevance_threshold_select(
        [seed, on], research_question=_LONG_QUESTION, sub_queries=[],
        fetch_cap=10, n_seed_injected=1,
    )
    out_urls = {c.url for c in out}
    assert "https://doi.org/10.1056/seed_empty" in out_urls  # seed kept (floor-exempt)
    assert "https://n/0" in out_urls
    assert gate.total_scored == 1                    # only the non-seed scored
    assert gate.demoted_below_floor == 0


# ── P2.1: INTEGRATED run_live_retrieval ON-path — weight + telemetry on rows ────
def _stub_fetch_ok(url, max_chars, **kwargs):
    """Long, on-topic full text so the candidate survives content-starvation and
    produces an evidence row."""
    body = (
        "The gut microbiome modulates colorectal tumorigenesis via butyrate and "
        "Fusobacterium nucleatum signalling in human cohorts. " * 12
    )
    return (body, True, "Microbiome Colorectal Mechanism", "html", "")


def test_integrated_run_live_retrieval_emits_weight_and_gate_telemetry(monkeypatch):
    """P2.1 (Codex iter-1): exercise the INTEGRATED `run_live_retrieval` ON-path
    (PG_RETRIEVAL_RELEVANCE_GATE=1), not just the helper. Assert that:
      - evidence rows receive `relevance_weight` (the carried-forward cosine), and
      - `LiveRetrievalResult.relevance_gate` telemetry is populated, and
      - the relevance-gate drop_reasons keys are emitted.
    NO network, NO model load: search/fetch backends + the embedder are stubbed."""
    import src.polaris_graph.retrieval.evidence_selector as es
    import src.polaris_graph.retrieval.prefetch_offtopic_filter as pf

    # Two on-topic non-seed serper hits; one off-topic that the gate must drop.
    on_url = "https://journal/on"
    tail_url = "https://journal/tail"
    off_url = "https://blog/off"

    def _stub_serper(q, num=10, api_calls=None):
        return [
            {"url": on_url, "title": "microbiome colorectal mechanism butyrate", "snippet": "on-topic"},
            {"url": tail_url, "title": "Fusobacterium adenoma carcinoma sequence", "snippet": "on-topic too"},
            {"url": off_url, "title": "local sports team championship recap", "snippet": "off-topic"},
        ]

    monkeypatch.setattr(lr, "_serper_search", _stub_serper)
    monkeypatch.setattr(lr, "_s2_bulk_search", lambda q, limit=20: [])
    monkeypatch.setattr(lr, "_fetch_content", _stub_fetch_ok)

    # Deterministic cosine: both on-topic high, the off-topic below floor. The
    # Keyed by the candidate `snippet_text` (= title + snippet). B1 maps that onto
    # the row `statement`; `_row_embed_text` appends a join space, so the fake looks
    # up by the stripped text. No prepended canary (deleted in iter-3).
    score_by_text = {
        "microbiome colorectal mechanism butyrate on-topic": 0.80,
        "Fusobacterium adenoma carcinoma sequence on-topic too": 0.50,
        "local sports team championship recap off-topic": 0.05,
    }
    monkeypatch.setattr(es, "_get_semantic_embedder", lambda: _FakeEmbedder())

    def _fake_sims(embedder, anchor, texts):
        return [score_by_text.get((t or "").strip(), 0.0) for t in texts]

    monkeypatch.setattr(pf, "_similarity_scores", _fake_sims)

    monkeypatch.setenv("PG_RETRIEVAL_RELEVANCE_GATE", "1")
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    # fetch_cap=1 so the BUDGET binds: top on-topic fetched, second on-topic is the
    # recorded unfetched-relevant tail; the off-topic is gated out below threshold.
    res = lr.run_live_retrieval(
        research_question=_LONG_QUESTION,
        fetch_cap=1,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
    )

    # (1) the relevance-gate telemetry is populated on the result.
    assert res.relevance_gate is not None
    assert res.relevance_gate["scorer"] == "semantic_v2"
    # §-1.3 DEMOTE-NOT-DROP: the off-topic (below-floor) source is DEMOTED, not dropped.
    # At cap=1 the highest-cosine above-floor source fills the budget, so the demoted
    # below-floor source lands in the cost tail (fetched_to_fill=0).
    assert res.relevance_gate["demoted_below_floor"] == 1     # the below-floor source DEMOTED
    assert res.relevance_gate["demoted_fetched_to_fill"] == 0 # budget filled by above-floor
    assert res.relevance_gate["demoted_tail"] == 1            # demoted to the cost tail
    assert res.relevance_gate["kept_on_topic"] == 2           # both above-floor
    assert res.relevance_gate["fetched_budget"] == 1          # cap=1 binds
    assert res.relevance_gate["unfetched_relevant_tail"] == 1 # 2nd above-floor recorded

    # (2) the fetched evidence row carries the carried-forward relevance_weight.
    fetched_rows = [r for r in res.evidence_rows if r["source_url"] == on_url]
    assert fetched_rows, "the highest-cosine on-topic source must produce a row"
    assert fetched_rows[0]["relevance_weight"] == pytest.approx(0.80)

    # (3) the relevance-gate drop_reasons keys are emitted on the result. The
    # below-floor source is now disclosed as a COST tail (relevance_below_floor_tail),
    # NOT as a hard-drop (the old offtopic_below_threshold drop reason is GONE).
    assert "offtopic_below_threshold" not in res.drop_reasons   # no hard pre-fetch drop
    assert res.drop_reasons.get("relevance_below_floor_tail") == 1
    assert res.drop_reasons.get("relevance_budget_tail") == 1


def test_integrated_below_floor_demoted_survives_to_budget_consumer_path(monkeypatch):
    """CONSUMER-PATH REGRESSION (I-deepfix-001 D3, Codex iter-1 P1 + iter-1 P2): the
    ACTUAL residual breadth hard-drop — the B4 relevance gate hard-dropping every
    below-floor candidate BEFORE the fetch budget — is GONE. Drives the INTEGRATED
    `run_live_retrieval` ON-path (PG_RETRIEVAL_RELEVANCE_GATE=1) with a budget LARGE
    enough for ALL candidates and proves a BELOW-FLOOR candidate:
      - SURVIVES the pre-fetch gate (is NOT hard-dropped), and
      - is actually FETCHED (produces an evidence row carrying its low relevance_weight),
        because the budget had room beyond the above-floor set, and
      - is DISCLOSED in the manifest as demoted-not-dropped (demoted_fetched_to_fill>=1),
        with the old `offtopic_below_threshold` hard-drop reason ABSENT.

    FAIL LOUD: if the below-floor candidate were hard-dropped before the budget (the
    old §-1.3-banned filter), it produces NO evidence row and (1) fails loudly. Distinct
    per-url fetch bodies avoid any content-dedup collapsing the assertion."""
    import src.polaris_graph.retrieval.evidence_selector as es
    import src.polaris_graph.retrieval.prefetch_offtopic_filter as pf

    on_url = "https://journal/on"            # above floor (0.80)
    mid_url = "https://journal/mid"          # above floor (0.50)
    below_url = "https://blog/below"         # BELOW floor (0.05) — the residual-drop victim

    def _stub_serper(q, num=10, api_calls=None):
        return [
            {"url": on_url, "title": "microbiome colorectal mechanism butyrate", "snippet": "on-topic"},
            {"url": mid_url, "title": "Fusobacterium adenoma carcinoma sequence", "snippet": "on-topic too"},
            {"url": below_url, "title": "local sports team championship recap", "snippet": "below floor"},
        ]

    def _stub_fetch_distinct(url, max_chars, **kwargs):
        # Distinct per-url on-topic body so each produces a row and dedup can't collapse
        # the below-floor row away (which would mask the regression for the wrong reason).
        body = (
            f"Source {url}: the gut microbiome modulates colorectal tumorigenesis via "
            "butyrate and Fusobacterium nucleatum signalling in human cohorts. " * 12
        )
        return (body, True, f"Title {url}", "html", "")

    monkeypatch.setattr(lr, "_serper_search", _stub_serper)
    monkeypatch.setattr(lr, "_s2_bulk_search", lambda q, limit=20: [])
    monkeypatch.setattr(lr, "_fetch_content", _stub_fetch_distinct)

    score_by_text = {
        "microbiome colorectal mechanism butyrate on-topic": 0.80,
        "Fusobacterium adenoma carcinoma sequence on-topic too": 0.50,
        "local sports team championship recap below floor": 0.05,  # below the 0.30 floor
    }
    monkeypatch.setattr(es, "_get_semantic_embedder", lambda: _FakeEmbedder())

    def _fake_sims(embedder, anchor, texts):
        return [score_by_text.get((t or "").strip(), 0.0) for t in texts]

    monkeypatch.setattr(pf, "_similarity_scores", _fake_sims)

    monkeypatch.setenv("PG_RETRIEVAL_RELEVANCE_GATE", "1")
    monkeypatch.setenv("PG_RELEVANCE_FLOOR", "0.30")
    # budget (5) >= candidate count (3): the below-floor candidate MUST be reached.
    res = lr.run_live_retrieval(
        research_question=_LONG_QUESTION,
        fetch_cap=5,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
    )

    # (1) FAIL-LOUD: the below-floor candidate SURVIVED to the fetch + produced a row.
    below_rows = [r for r in res.evidence_rows if r["source_url"] == below_url]
    assert below_rows, (
        "REGRESSION: the below-floor candidate was hard-dropped before the fetch "
        "budget (the §-1.3-banned pre-fetch filter) — it must be DEMOTED + fetched."
    )
    # it carries its low relevance weight forward (a WEIGHT, never a gate).
    assert below_rows[0]["relevance_weight"] == pytest.approx(0.05)

    # (2) the manifest discloses the demote-not-drop conversion + the fetched-to-fill.
    assert res.relevance_gate is not None
    assert res.relevance_gate["kept_on_topic"] == 2            # 2 above floor
    assert res.relevance_gate["demoted_below_floor"] == 1      # 1 below floor (DEMOTED, not dropped)
    assert res.relevance_gate["demoted_fetched_to_fill"] == 1  # budget reached it -> fetched
    assert res.relevance_gate["demoted_tail"] == 0             # nothing stranded in the tail
    assert res.relevance_gate["fetched_budget"] == 3           # all 3 fetched (budget had room)
    assert res.relevance_gate["unfetched_relevant_tail"] == 0

    # (3) NO hard pre-fetch drop reason; nothing left in the cost tail.
    assert "offtopic_below_threshold" not in res.drop_reasons
    assert res.drop_reasons.get("relevance_below_floor_tail", 0) == 0
    assert res.drop_reasons.get("relevance_budget_tail", 0) == 0


def test_integrated_off_path_emits_no_relevance_gate(monkeypatch):
    """Flag-OFF parity: with the gate explicitly OFF, `relevance_gate` is None and no
    evidence row carries a `relevance_weight` key (byte-identical legacy behaviour);
    the legacy `rerank_not_selected` reason is used, not the B4 reasons.
    I-deepfix-001 B1 flipped the DEFAULT to ON, so the OFF path is now reached via an
    explicit ``PG_RETRIEVAL_RELEVANCE_GATE=0``."""
    monkeypatch.setenv("PG_RETRIEVAL_RELEVANCE_GATE", "0")

    def _stub_serper(q, num=10, api_calls=None):
        return [{"url": "https://journal/on", "title": "microbiome colorectal mechanism", "snippet": "x"}]

    monkeypatch.setattr(lr, "_serper_search", _stub_serper)
    monkeypatch.setattr(lr, "_s2_bulk_search", lambda q, limit=20: [])
    monkeypatch.setattr(lr, "_fetch_content", _stub_fetch_ok)

    res = lr.run_live_retrieval(
        research_question=_LONG_QUESTION,
        fetch_cap=5,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
    )
    assert res.relevance_gate is None                         # OFF => None telemetry
    assert all("relevance_weight" not in r for r in res.evidence_rows)
    assert "offtopic_below_threshold" not in res.drop_reasons
    assert "relevance_budget_tail" not in res.drop_reasons
