"""
B1 (b1b10 redesign) regression tests — SEMANTIC relevance scorer.

The bug: `_row_relevance` = len(overlap)/max(1,len(anchors)) — lexical
word-overlap divided by question length. A long research question mechanically
buries on-topic papers whose domain vocabulary doesn't lexically match the
question's words (the live 236/589 loss; drb_76 collapse documented at
`_row_relevance`).

The fix: embedding-cosine relevance (PG_RELEVANCE_SCORER=semantic_v2) reusing the
already-loaded embedder, plus REVERSING the credibility-redesign keep-all back to
a real RELEVANCE FILTER on the semantic score. Relevance FILTERS; credibility /
authority / retrieval_weight WEIGHT the sort (orthogonal axes).

ACCEPT criteria proven here (deterministic, stub embedder — no model load):
  1. A semantic on-topic paper the LEXICAL scorer dropped is now KEPT.
  2. An off-topic paper is dropped.
  3. Credibility/authority only WEIGHTS — a LOW-authority on-topic row is KEPT.
  4. Below-floor relevance drops are logged (drop ledger).
  5. Default (scorer OFF) selection is byte-identical to the prior behavior.
  6. Embedder unavailable => LOUD fallback to lexical (no silent keep-all).
"""
from __future__ import annotations

from dataclasses import dataclass

import pytest

import src.polaris_graph.retrieval.evidence_selector as es
from src.polaris_graph.retrieval.evidence_selector import (
    EvidenceSelection,
    select_evidence_for_generation,
)


@dataclass
class _FakeSource:
    url: str
    tier: str


# ── A deterministic STUB embedder: maps a fixed vocabulary to orthogonal unit
#    vectors so cosine similarity is fully controlled (no model load). It exposes
#    `encode(...)` (the interface `prefetch_offtopic_filter._similarity_scores`
#    uses) returning L2-normalized vectors. Texts are bag-of-keywords over a small
#    topic basis; the cosine of two texts = fraction of shared topic mass. ──────
class _StubEmbedder:
    # topic -> basis index. Three orthogonal topics.
    _BASIS = {
        "microbiome": 0,   # gut bacteria / fusobacterium / butyrate / colorectal
        "fed": 1,          # federal reserve / interest rate / inflation
        "sports": 2,       # boxing / gym / training
    }
    # keyword -> topic. This is the STUB's stand-in for semantic understanding:
    # the on-topic paper's domain vocabulary (fusobacterium, butyrate) AND the
    # question's DIFFERENT vocabulary (commensal, malignancy, intestine) BOTH map
    # to the same `microbiome` topic — modelling the cross-vocabulary similarity a
    # real embedder captures and the lexical scorer cannot. The lexical scorer sees
    # zero word overlap between question and paper; the (stub) embedder sees the
    # same topic.
    _KEYWORDS = {
        # on-topic paper vocabulary
        "fusobacterium": "microbiome",
        "butyrate": "microbiome",
        "microbiome": "microbiome",
        "colorectal": "microbiome",
        "gut": "microbiome",
        "bacteria": "microbiome",
        "tumorigenesis": "microbiome",
        # question vocabulary (semantically the SAME topic, lexically different)
        "commensal": "microbiome",
        "organisms": "microbiome",
        "malignancy": "microbiome",
        "intestine": "microbiome",
        "dietary": "microbiome",
        # fed topic
        "federal": "fed",
        "reserve": "fed",
        "interest": "fed",
        "inflation": "fed",
        "rate": "fed",
        # sports topic
        "boxing": "sports",
        "gym": "sports",
        "training": "sports",
    }

    def _vec(self, text: str):
        import numpy as np

        v = np.zeros(3, dtype="float32")
        toks = "".join(c.lower() if c.isalnum() else " " for c in text).split()
        for t in toks:
            topic = self._KEYWORDS.get(t)
            if topic is not None:
                v[self._BASIS[topic]] += 1.0
        n = float(np.linalg.norm(v))
        if n < 1e-9:
            return v  # zero vector -> 0 similarity (no embeddable topic)
        return v / n

    def encode(self, texts, normalize_embeddings: bool = True):
        import numpy as np

        if isinstance(texts, str):
            return self._vec(texts)
        return np.stack([self._vec(t) for t in texts])


@pytest.fixture(autouse=True)
def _reset_embedder_cache_and_env(monkeypatch):
    """Reset the module-level embedder cache + scrub B1 env between tests."""
    monkeypatch.setattr(es, "_SEMANTIC_EMBEDDER_CACHE", None, raising=False)
    for var in (
        "PG_RELEVANCE_SCORER",
        "PG_RELEVANCE_DROP_LEDGER",
        "PG_SWEEP_CREDIBILITY_REDESIGN",
        "PG_SELECT_SUBQUERY_FLOOR",
        "PG_RELEVANCE_PRESERVE_ANCHORS",
    ):
        monkeypatch.delenv(var, raising=False)
    yield
    monkeypatch.setattr(es, "_SEMANTIC_EMBEDDER_CACHE", None, raising=False)


def _install_stub_embedder(monkeypatch):
    """Force `_get_semantic_embedder` to return the deterministic stub."""
    monkeypatch.setattr(es, "_SEMANTIC_EMBEDDER_CACHE", _StubEmbedder(), raising=False)


# The research question's WORDS share almost NOTHING lexically with the on-topic
# paper's domain vocabulary — exactly the case the lexical scorer buries.
_QUESTION = (
    "What is the predominant mechanism by which commensal organisms "
    "influence the development and progression of malignancy in the "
    "large intestine, and how might dietary modulation mitigate it?"
)

_ON_TOPIC_QUOTE = (
    "Fusobacterium drives colorectal tumorigenesis while butyrate from gut "
    "bacteria in the microbiome is protective."
)
_OFF_TOPIC_QUOTE = (
    "The Federal Reserve raised the interest rate to combat inflation."
)


def _row(ev_id, url, tier, quote, authority=None):
    r = {
        "evidence_id": ev_id,
        "source_url": url,
        "statement": quote,
        "direct_quote": quote,
        "tier": tier,
    }
    if authority is not None:
        r["authority_score"] = authority
    return r


# ── 1 + 2 + 3: on-topic kept, off-topic dropped, low-authority on-topic kept ──

def test_semantic_keeps_ontopic_drops_offtopic_low_authority_kept(monkeypatch):
    monkeypatch.setenv("PG_RELEVANCE_SCORER", "semantic_v2")
    _install_stub_embedder(monkeypatch)

    rows = [
        # On-topic, HIGH authority.
        _row("ev_on_hi", "https://nature.com/on_hi", "T1", _ON_TOPIC_QUOTE, 0.95),
        # On-topic, LOW authority — must STILL be kept (credibility only weights).
        _row("ev_on_lo", "https://blog.example/on_lo", "T6", _ON_TOPIC_QUOTE, 0.05),
        # Off-topic — must be DROPPED by the relevance filter.
        _row("ev_off", "https://news.example/off", "T1", _OFF_TOPIC_QUOTE, 0.99),
    ]
    sources = [_FakeSource(url=r["source_url"], tier=r["tier"]) for r in rows]

    sel = select_evidence_for_generation(
        research_question=_QUESTION,
        protocol=None,
        classified_sources=sources,
        evidence_rows=rows,
        max_rows=999,
        relevance_floor=0.30,
    )
    kept_ids = {r["evidence_id"] for r in sel.selected_rows}

    # The on-topic paper (low lexical overlap with the question) IS kept.
    assert "ev_on_hi" in kept_ids
    # The LOW-authority on-topic row is ALSO kept — credibility weights, never drops.
    assert "ev_on_lo" in kept_ids
    # The off-topic paper is dropped by the relevance filter.
    assert "ev_off" not in kept_ids
    assert sel.dropped_count == 1
    # Strategy id flips so the manifest is auditable (the falsifiable check).
    assert sel.selection_strategy == "relevance_floor_semantic_v1"


# ── 1 (the headline): lexical scorer BURIES the on-topic paper, semantic RESCUES ─

def test_lexical_buries_what_semantic_rescues(monkeypatch):
    """Same pool, two scorers. Under the LEXICAL floor the on-topic paper (whose
    vocabulary doesn't lexically match the question) is dropped; under the SEMANTIC
    scorer it is kept. This is the 236/589 bug, made falsifiable."""
    rows = [
        _row("ev_on", "https://nature.com/on", "T1", _ON_TOPIC_QUOTE, 0.95),
    ]
    sources = [_FakeSource(url=rows[0]["source_url"], tier="T1")]

    # LEXICAL path (default scorer) — the on-topic paper is buried by the long
    # question's denominator (near-zero exact-word overlap).
    lexical = select_evidence_for_generation(
        research_question=_QUESTION,
        protocol=None,
        classified_sources=sources,
        evidence_rows=rows,
        max_rows=999,
        relevance_floor=0.30,
    )
    assert {r["evidence_id"] for r in lexical.selected_rows} == set()
    assert lexical.dropped_count == 1
    assert lexical.selection_strategy == "relevance_floor_v1"

    # SEMANTIC path — the SAME paper clears the floor.
    monkeypatch.setenv("PG_RELEVANCE_SCORER", "semantic_v2")
    _install_stub_embedder(monkeypatch)
    semantic = select_evidence_for_generation(
        research_question=_QUESTION,
        protocol=None,
        classified_sources=sources,
        evidence_rows=rows,
        max_rows=999,
        relevance_floor=0.30,
    )
    assert {r["evidence_id"] for r in semantic.selected_rows} == {"ev_on"}
    assert semantic.dropped_count == 0


# ── 4: below-floor drops are logged (drop ledger) ────────────────────────────

def test_drop_ledger_logs_below_floor(monkeypatch, caplog):
    monkeypatch.setenv("PG_RELEVANCE_SCORER", "semantic_v2")
    monkeypatch.setenv("PG_RELEVANCE_DROP_LEDGER", "1")
    _install_stub_embedder(monkeypatch)

    rows = [
        _row("ev_on", "https://nature.com/on", "T1", _ON_TOPIC_QUOTE, 0.9),
        _row("ev_off", "https://news.example/off", "T1", _OFF_TOPIC_QUOTE, 0.9),
    ]
    sources = [_FakeSource(url=r["source_url"], tier=r["tier"]) for r in rows]

    import logging

    with caplog.at_level(logging.INFO, logger=es._LOGGER.name):
        select_evidence_for_generation(
            research_question=_QUESTION,
            protocol=None,
            classified_sources=sources,
            evidence_rows=rows,
            max_rows=999,
            relevance_floor=0.30,
        )
    ledger_lines = [
        r.message for r in caplog.records
        if "relevance_drop_ledger" in r.message
    ]
    assert ledger_lines, "drop ledger must log the below-floor off-topic drop"
    assert any("news.example/off" in m for m in ledger_lines)
    # The kept on-topic url must NOT appear as a drop.
    assert not any("nature.com/on" in m for m in ledger_lines)


def test_drop_ledger_off_suppresses_log(monkeypatch, caplog):
    monkeypatch.setenv("PG_RELEVANCE_SCORER", "semantic_v2")
    monkeypatch.setenv("PG_RELEVANCE_DROP_LEDGER", "0")
    _install_stub_embedder(monkeypatch)

    rows = [_row("ev_off", "https://news.example/off", "T1", _OFF_TOPIC_QUOTE, 0.9)]
    sources = [_FakeSource(url=rows[0]["source_url"], tier="T1")]

    import logging

    with caplog.at_level(logging.INFO, logger=es._LOGGER.name):
        select_evidence_for_generation(
            research_question=_QUESTION,
            protocol=None,
            classified_sources=sources,
            evidence_rows=rows,
            max_rows=999,
            relevance_floor=0.30,
        )
    assert not any(
        "relevance_drop_ledger" in r.message for r in caplog.records
    )


# ── 5: default (scorer OFF) is byte-identical to the prior behavior ──────────

def test_default_off_is_lexical_byte_identical(monkeypatch):
    """With PG_RELEVANCE_SCORER unset, NO embedder loads and selection is exactly
    the legacy lexical floor filter (strategy id unchanged)."""
    # Sentinel: if the embedder were touched, this would blow up.
    def _boom():
        raise AssertionError("embedder must NOT load when scorer is OFF")

    monkeypatch.setattr(es, "_get_semantic_embedder", _boom, raising=True)

    rows = [
        _row("ev_a", "https://nature.com/a", "T1",
             "semaglutide obesity weight loss trial", 0.9),
        _row("ev_b", "https://news.example/b", "T1",
             "unrelated gardening tips", 0.9),
    ]
    sources = [_FakeSource(url=r["source_url"], tier=r["tier"]) for r in rows]

    sel = select_evidence_for_generation(
        research_question="semaglutide obesity weight loss",
        protocol=None,
        classified_sources=sources,
        evidence_rows=rows,
        max_rows=999,
        relevance_floor=0.30,
    )
    assert sel.selection_strategy == "relevance_floor_v1"
    # ev_a (lexical overlap with the short question) kept; ev_b dropped.
    kept = {r["evidence_id"] for r in sel.selected_rows}
    assert "ev_a" in kept
    assert "ev_b" not in kept


def test_credibility_redesign_keepall_unchanged_when_scorer_off(monkeypatch):
    """Under PG_SWEEP_CREDIBILITY_REDESIGN with the semantic scorer OFF, the
    keep-all over-correction is preserved byte-identically (NOT reversed)."""
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    monkeypatch.setattr(
        es, "_get_semantic_embedder",
        lambda: (_ for _ in ()).throw(AssertionError("no embedder when OFF")),
        raising=True,
    )

    rows = [
        _row("ev_a", "https://nature.com/a", "T1",
             "semaglutide obesity weight loss", 0.9),
        _row("ev_off", "https://news.example/off", "T1",
             "completely unrelated topic xyz", 0.9),
    ]
    sources = [_FakeSource(url=r["source_url"], tier=r["tier"]) for r in rows]

    sel = select_evidence_for_generation(
        research_question="semaglutide obesity weight loss",
        protocol=None,
        classified_sources=sources,
        evidence_rows=rows,
        max_rows=999,
        relevance_floor=0.30,
    )
    # keep-all: BOTH rows kept (credibility redesign without semantic = keep-all).
    assert len(sel.selected_rows) == 2
    assert sel.selection_strategy == "relevance_floor_v1"


# ── 6: embedder unavailable => LOUD fallback to lexical (no silent keep-all) ──

def test_embedder_unavailable_loud_fallback(monkeypatch, caplog):
    monkeypatch.setenv("PG_RELEVANCE_SCORER", "semantic_v2")
    # Force the embedder loader to report "unavailable".
    monkeypatch.setattr(es, "_get_semantic_embedder", lambda: None, raising=True)

    rows = [
        _row("ev_a", "https://nature.com/a", "T1",
             "semaglutide obesity weight loss", 0.9),
        _row("ev_off", "https://news.example/off", "T1",
             "completely unrelated topic xyz", 0.9),
    ]
    sources = [_FakeSource(url=r["source_url"], tier=r["tier"]) for r in rows]

    import logging

    with caplog.at_level(logging.WARNING, logger=es._LOGGER.name):
        sel = select_evidence_for_generation(
            research_question="semaglutide obesity weight loss",
            protocol=None,
            classified_sources=sources,
            evidence_rows=rows,
            max_rows=999,
            relevance_floor=0.30,
        )
    # LOUD: a warning must announce the fallback.
    assert any(
        "FELL BACK to the lexical scorer" in r.message
        for r in caplog.records
    ), "embedder-unavailable must LOUDLY fall back, not silently keep-all"
    # NOT a silent keep-all: the off-topic row is still FILTERED on the lexical
    # score (the filter is restored, just on the lexical score).
    kept = {r["evidence_id"] for r in sel.selected_rows}
    assert "ev_a" in kept
    assert "ev_off" not in kept
    # Strategy stays legacy (semantic did not actually drive the filter); the note
    # discloses the degrade.
    assert sel.selection_strategy == "relevance_floor_v1"
    assert any("REQUESTED but embedder unavailable" in n for n in sel.notes)


def test_embedder_unavailable_fallback_filters_even_under_redesign(monkeypatch):
    """Codex diff-gate P0 regression: PG_RELEVANCE_SCORER=semantic_v2 + embedder
    UNAVAILABLE + PG_SWEEP_CREDIBILITY_REDESIGN=1. The redesign keep-all branch
    must NOT swallow the fallback — the off-topic row must STILL be FILTERED on the
    lexical score (no silent keep-all). Before the fix this kept EVERYTHING."""
    monkeypatch.setenv("PG_RELEVANCE_SCORER", "semantic_v2")
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    monkeypatch.setattr(es, "_get_semantic_embedder", lambda: None, raising=True)

    rows = [
        _row("ev_a", "https://nature.com/a", "T1",
             "semaglutide obesity weight loss", 0.9),
        _row("ev_off", "https://news.example/off", "T1",
             "completely unrelated topic xyz", 0.9),
    ]
    sources = [_FakeSource(url=r["source_url"], tier=r["tier"]) for r in rows]

    sel = select_evidence_for_generation(
        research_question="semaglutide obesity weight loss",
        protocol=None,
        classified_sources=sources,
        evidence_rows=rows,
        max_rows=999,
        relevance_floor=0.30,
    )
    kept = {r["evidence_id"] for r in sel.selected_rows}
    # The relevant row is kept; the off-topic row is FILTERED (NOT keep-all).
    assert "ev_a" in kept
    assert "ev_off" not in kept, (
        "embedder-unavailable under credibility-redesign must FILTER on the "
        "lexical score, not silently keep-all"
    )
    assert any("REQUESTED but embedder unavailable" in n for n in sel.notes)


# ── Unit: the semantic scorer takes the per-anchor MAX in cosine space ───────

def test_semantic_score_takes_subquery_max(monkeypatch):
    """A row matching ONE focused sub-query (but not the broad question) must clear
    via the per-sub-query max — proving the facet logic lives in cosine space (no
    scale-mixing)."""
    _install_stub_embedder(monkeypatch)
    monkeypatch.setenv("PG_RELEVANCE_SCORER", "semantic_v2")

    rows = [_row("ev_on", "https://nature.com/on", "T1", _ON_TOPIC_QUOTE, 0.9)]
    scores = es._semantic_relevance_scores(
        # Broad question is about the Fed (off-topic for the row)...
        "Federal Reserve interest rate inflation policy",
        # ...but ONE sub-query is on-topic for the microbiome row.
        ["gut bacteria microbiome colorectal tumorigenesis"],
        rows,
    )
    assert scores is not None
    # The per-anchor MAX picks the on-topic sub-query, so the row scores high.
    assert scores[0] > 0.30


def test_semantic_scores_none_without_embedder(monkeypatch):
    """No embedder => None (the signal the caller uses to fall back loudly)."""
    monkeypatch.setattr(es, "_get_semantic_embedder", lambda: None, raising=True)
    rows = [_row("ev", "https://x/y", "T1", _ON_TOPIC_QUOTE)]
    assert es._semantic_relevance_scores(_QUESTION, None, rows) is None


# ── Optional: real-model proof (skipped if the model can't load) ─────────────

@pytest.mark.slow
def test_real_model_rescues_low_lexical_overlap_pair(monkeypatch):
    """ONE real-embedder proof on the Fusobacterium/butyrate case the code comment
    cites: an on-topic paper with NEAR-ZERO lexical overlap scores ABOVE a typical
    floor, while a Fed-rate paper scores below. Asserts ORDERING, not exact floats.
    Skips cleanly if the embedder is unavailable in this env."""
    monkeypatch.setattr(es, "_SEMANTIC_EMBEDDER_CACHE", None, raising=False)
    embedder = es._get_semantic_embedder()
    if embedder is None:
        pytest.skip("real embedder not available in this environment")

    rows = [
        _row("ev_on", "https://nature.com/on", "T1", _ON_TOPIC_QUOTE),
        _row("ev_off", "https://news.example/off", "T1", _OFF_TOPIC_QUOTE),
    ]
    scores = es._semantic_relevance_scores(_QUESTION, None, rows)
    assert scores is not None
    # On-topic clearly outscores off-topic; on-topic clears a conservative floor.
    assert scores[0] > scores[1]
    assert scores[0] >= 0.30
    assert scores[1] < 0.30
