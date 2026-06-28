"""I-ready-017 Task 2a (#1204) — source-funnel telemetry persistence smoke.

ADDITIVE TELEMETRY ONLY. These tests assert the manifest gains the new
source-funnel keys (prefetch_offtopic, drop_reasons, extraction_yield,
kept_by_offtopic) and that they reflect counts ALREADY computed inside
``run_live_retrieval`` — without changing what gets discovered/filtered/
fetched/selected.

SPEND-FREE / NO NETWORK: the ``_retrieval_manifest_section`` writer is a PURE
mapping over a retrieval-result object, so it is exercised with the real
``LiveRetrievalResult`` dataclass plus plain-class stubs (NO unittest.mock per
CLAUDE.md §9.4). The behavior-unchanged assertion is structural: the writer
mirrors the result's funnel counts verbatim and never mutates the kept set.

Serialized per CLAUDE.md §8.4 (pure-python, no heavy ML).
"""
from __future__ import annotations

import importlib

from src.polaris_graph.retrieval.live_retriever import LiveRetrievalResult


def _section(retrieval):
    """Lazy-import the heavy sweep module and run the manifest-section writer."""
    sweep = importlib.import_module("scripts.run_honest_sweep_r3")
    return sweep._retrieval_manifest_section(retrieval)


# ── dataclass defaults: telemetry fields are HONESTLY absent/empty ──────────
def test_dataclass_defaults_are_honest():
    """A constructor that does not pass the new fields gets None / empty — never
    a faked count. Proves the additive fields cannot fabricate funnel data and
    that pre-#1204 constructors (test fixtures, etc.) stay valid."""
    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=[], total_candidates_pre_filter=0,
        candidates_kept_by_scope=0, candidates_kept_by_offtopic=0,
        candidates_fetched=0, candidates_failed_fetch=0,
    )
    assert r.prefetch_offtopic is None
    assert r.drop_reasons == {}


# ── prefetch_offtopic persists kept/rejected/threshold ──────────────────────
def test_prefetch_offtopic_persisted_with_raw_threshold():
    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=[{"evidence_id": "ev_000"}],
        total_candidates_pre_filter=2981, candidates_kept_by_scope=0,
        candidates_kept_by_offtopic=740, candidates_fetched=500,
        candidates_failed_fetch=10,
        prefetch_offtopic={"kept": 740, "rejected": 2241, "threshold": 0.3125},
        drop_reasons={
            "offtopic": 2241, "rerank_not_selected": 0,
            "fetch_failed": 10, "content_starved": 0,
        },
    )
    sec = _section(r)
    # the off-topic split is now persisted (was local 'notes' only)
    assert sec["prefetch_offtopic"] == {
        "kept": 740, "rejected": 2241, "threshold": 0.3125,
    }
    # raw float, NOT the rounded :.2f note string
    assert sec["prefetch_offtopic"]["threshold"] == 0.3125


# ── prefetch_offtopic is None when filter disabled / seed-only ──────────────
def test_prefetch_offtopic_none_when_filter_off():
    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=[], total_candidates_pre_filter=5,
        candidates_kept_by_scope=0, candidates_kept_by_offtopic=5,
        candidates_fetched=5, candidates_failed_fetch=0,
        prefetch_offtopic=None,  # seed-only / filter disabled
    )
    sec = _section(r)
    assert sec["prefetch_offtopic"] is None  # honest absence, never a 0-fake


# ── drop_reasons aggregate is persisted by reason ───────────────────────────
def test_drop_reasons_persisted_by_reason():
    drops = {
        "offtopic": 2241, "rerank_not_selected": 245,
        "fetch_failed": 10, "content_starved": 8,
    }
    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=[],
        total_candidates_pre_filter=2981, candidates_kept_by_scope=0,
        candidates_kept_by_offtopic=740, candidates_fetched=490,
        candidates_failed_fetch=10, drop_reasons=drops,
    )
    sec = _section(r)
    assert sec["drop_reasons"] == drops
    # the dominant pre-fetch loss is attributable to the off-topic stage
    assert sec["drop_reasons"]["offtopic"] == 2241


# ── extraction_yield pairs fetched -> extracted finding rows ────────────────
def test_extraction_yield_pairs_fetched_and_finding_rows():
    """The 2nd-biggest drop (fetched -> finding rows). finding_rows is the
    EXTRACTION-stage count frozen at retrieval return (extraction_finding_rows),
    which run_live_retrieval sets to len(evidence_rows) at return time."""
    rows = [{"evidence_id": f"ev_{i:03d}"} for i in range(55)]
    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=rows,
        total_candidates_pre_filter=2981, candidates_kept_by_scope=0,
        candidates_kept_by_offtopic=740, candidates_fetched=500,
        candidates_failed_fetch=10,
        extraction_finding_rows=len(rows),  # what run_live_retrieval sets at return
    )
    sec = _section(r)
    assert sec["extraction_yield"] == {"fetched": 500, "finding_rows": 55}


def test_extraction_yield_frozen_against_post_retrieval_mutation():
    """Codex diff-gate iter-1 P1: run_one_query MUTATES retrieval.evidence_rows
    AFTER run_live_retrieval returns (expansion/deepener/agentic lanes). The
    manifest's extraction-stage finding_rows MUST be the frozen return-time count
    (extraction_finding_rows), NOT len(evidence_rows) read at manifest-write time
    — else it reports the inflated post-expansion total, mislabelled as the
    extraction yield."""
    rows = [{"evidence_id": f"ev_{i:03d}"} for i in range(55)]
    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=rows,
        total_candidates_pre_filter=2981, candidates_kept_by_scope=0,
        candidates_kept_by_offtopic=740, candidates_fetched=500,
        candidates_failed_fetch=10,
        extraction_finding_rows=len(rows),  # frozen at return = 55
    )
    # Simulate the post-retrieval expansion lane (run_honest_sweep_r3.py:3585)
    # appending 20 more rows + the agentic lane reassigning the list.
    for i in range(20):
        r.evidence_rows.append({"evidence_id": f"exp_{i:03d}"})
    r.evidence_rows = list(r.evidence_rows)  # reassign, mirroring L3715/L3912
    assert len(r.evidence_rows) == 75  # the mutable list grew
    sec = _section(r)
    # finding_rows stays the EXTRACTION-stage 55, NOT the post-expansion 75.
    assert sec["extraction_yield"]["finding_rows"] == 55
    assert sec["extraction_yield"]["fetched"] == 500


# ── the pre-fetch funnel is explicit: 2981 -> offtopic -> cap -> 740 ────────
def test_prefetch_funnel_keys_all_present():
    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=[{"evidence_id": "ev_000"}],
        total_candidates_pre_filter=2981, candidates_kept_by_scope=0,
        candidates_kept_by_offtopic=740, candidates_fetched=500,
        candidates_failed_fetch=10,
    )
    sec = _section(r)
    # candidates_total -> (offtopic) kept_by_offtopic -> (cap) -> fetched
    assert sec["pre_filter"] == 2981
    assert "candidates_total" in sec
    assert sec["kept_by_offtopic"] == 740
    assert "extraction_yield" in sec
    assert "prefetch_offtopic" in sec
    assert "drop_reasons" in sec


# ── backward compatibility: pre-#1204 retrieval-like objects don't crash ────
def test_section_backward_compatible_with_old_object():
    """A stub WITHOUT the new attributes (pre-#1204 retrieval object) must still
    produce a valid section via the getattr defaults — never a KeyError."""

    class _OldRetr:
        total_candidates_pre_filter = 50
        candidates_fetched = 12
        candidates_failed_fetch = 0
        api_calls = {"fetch": 12}
        corpus_truncated = False
        candidates_total = 50
        candidates_processed = 12
        # NOTE: no prefetch_offtopic / drop_reasons / candidates_kept_by_offtopic
        # and no evidence_rows attribute

    sec = _section(_OldRetr())
    assert sec["prefetch_offtopic"] is None
    assert sec["drop_reasons"] == {}
    assert sec["kept_by_offtopic"] == 0
    assert sec["extraction_yield"] == {"fetched": 12, "finding_rows": 0}
    # I-deepfix-001 P1-4 (#1344): the getattr defaults keep the new wall/B4 fields
    # present + byte-identical OFF even on a pre-#1344 retrieval-like object.
    assert sec["retrieval_wall_hit"] is False
    assert sec["retrieval_queries_skipped"] == 0
    assert sec["retrieval_candidates_unclassified"] == 0
    assert sec["semantic_relevance_fell_back"] is False


# ── I-deepfix-001 P1-4: retrieval-wall + B4 fallback disclosure serialized ──────
def test_retrieval_wall_and_b4_fallback_serialized_in_manifest_section():
    """The retrieval-wall partial-handoff telemetry AND the B4 semantic->lexical
    fallback flag MUST be serialized by `_retrieval_manifest_section` (§-1.3 — the
    partial cutoff / degraded winner is disclosed in the manifest, never silent)."""
    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=[],
        total_candidates_pre_filter=900, candidates_kept_by_scope=3,
        candidates_kept_by_offtopic=400, candidates_fetched=120,
        candidates_failed_fetch=30,
        retrieval_wall_hit=True,
        retrieval_queries_skipped=7,
        retrieval_candidates_unclassified=55,
        semantic_relevance_fell_back=True,
    )
    sec = _section(r)
    assert sec["retrieval_wall_hit"] is True
    assert sec["retrieval_queries_skipped"] == 7
    assert sec["retrieval_candidates_unclassified"] == 55
    assert sec["semantic_relevance_fell_back"] is True


def test_retrieval_wall_off_path_byte_identical_false():
    """OFF path (wall never tripped, B4 gate off): the fields are present and falsey,
    so the disclosure is byte-identical to a pre-#1344 healthy run."""
    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=[],
        total_candidates_pre_filter=100, candidates_kept_by_scope=1,
        candidates_kept_by_offtopic=50, candidates_fetched=40,
        candidates_failed_fetch=2,
    )
    sec = _section(r)
    assert sec["retrieval_wall_hit"] is False
    assert sec["retrieval_queries_skipped"] == 0
    assert sec["retrieval_candidates_unclassified"] == 0
    assert sec["semantic_relevance_fell_back"] is False
