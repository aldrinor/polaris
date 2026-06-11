# Codex diff-gate iter 2 — Task 2a (#1204): source-funnel telemetry

HARD ITERATION CAP: 5 per document. This is iter 2 of 5. Front-load ALL findings.
Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## iter-1 verdict was REQUEST_CHANGES on ONE P1 — now FIXED:
P1 (iter1): extraction_yield.finding_rows read len(retrieval.evidence_rows) at manifest-write
time, but run_one_query MUTATES evidence_rows after run_live_retrieval returns (expansion append
L3585, deepener/agentic reassign L3715/L3912) -> reported the post-expansion total, not the
extraction yield.
FIX: added an immutable int field 'extraction_finding_rows' to LiveRetrievalResult, set ONCE at
the run_live_retrieval RETURN to len(evidence_rows) (frozen before any downstream mutation);
_retrieval_manifest_section now reads that frozen snapshot, NOT len(retrieval.evidence_rows).
Added regression test test_extraction_yield_frozen_against_post_retrieval_mutation: mutates
evidence_rows to 75 post-construction, asserts finding_rows stays the frozen 55.

## Verify: (a) the frozen snapshot is captured at return BEFORE any mutation; (b) the manifest
reads the frozen field not the mutable list; (c) the regression test actually exercises the
mutation path; (d) still additive-only / behavior-neutral / no faithfulness-gate touch; (e) no
NEW issue introduced by the fix. Tests: 43 green (8 telemetry incl. the new regression + 14
manifest-contract + 6 corpus-truncation + 8 rerank + 7 retrieval-trace).

Emit the §8.3.9 schema; final line EXACTLY 'verdict: APPROVE' or 'verdict: REQUEST_CHANGES'.

## FULL DIFF (tracked files, iter 2)
```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index ac733cef..dffbbd71 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -1111,6 +1111,39 @@ def _retrieval_manifest_section(retrieval) -> dict:
         ),
         "fetch_workers": getattr(retrieval, "fetch_workers", None),
         "distinct_hosts": getattr(retrieval, "distinct_hosts", None),
+        # I-ready-017 Task 2a (#1204): ADDITIVE source-funnel telemetry. These
+        # persist counts already computed inside run_live_retrieval so the
+        # ~90% pre-fetch source loss is MEASURABLE on a fresh run. Pure
+        # read-only mirroring — retrieval behavior is byte-identical.
+        #
+        # kept_by_offtopic makes the pre-fetch funnel explicit: with pre_filter
+        # and candidates_total already emitted above, the
+        #   candidates_total -> (off-topic filter) -> kept_by_offtopic -> (cap) -> ...
+        # split is now visible. The field already existed on
+        # LiveRetrievalResult; it was simply never written to the manifest.
+        "kept_by_offtopic": getattr(
+            retrieval, "candidates_kept_by_offtopic", 0,
+        ),
+        # The off-topic filter's kept/rejected/threshold (the dominant ~90%
+        # drop). None when the filter is disabled or only seeds are present —
+        # honestly absent rather than a faked count.
+        "prefetch_offtopic": getattr(retrieval, "prefetch_offtopic", None),
+        # Per-reason drop aggregate (offtopic / rerank_not_selected /
+        # fetch_failed / content_starved) so each stage's loss is attributable.
+        "drop_reasons": getattr(retrieval, "drop_reasons", {}),
+        # The fetched -> finding-row extraction stage (the 2nd-biggest drop,
+        # previously uncounted). finding_rows is the number of evidence rows
+        # EXTRACTED from fetched content at retrieval RETURN time. Codex diff-gate
+        # iter-1 P1: read the FROZEN `extraction_finding_rows` snapshot, NOT
+        # len(retrieval.evidence_rows) — run_one_query mutates evidence_rows after
+        # run_live_retrieval returns (expansion/deepener/agentic lanes), so a
+        # manifest-time len() would report the post-expansion total, not the
+        # extraction yield this key names. finding_dedup.raw_row_count is a
+        # separate POST-selection dedup-gated count (absent when dedup is OFF).
+        "extraction_yield": {
+            "fetched": getattr(retrieval, "candidates_fetched", 0),
+            "finding_rows": getattr(retrieval, "extraction_finding_rows", 0),
+        },
     }
 
 
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index 8e3cc297..1daf9b2f 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -158,6 +158,29 @@ class LiveRetrievalResult:
     parallel_completion_rate: float | None = None
     fetch_workers: int | None = None
     distinct_hosts: int | None = None
+    # I-ready-017 Task 2a (#1204): ADDITIVE source-funnel telemetry (read-only).
+    # Persists existing-but-unsaved retrieval counts so the ~90% pre-fetch
+    # source loss is MEASURABLE on a fresh run. NONE of these change what is
+    # discovered/filtered/fetched/selected — they only mirror locals already
+    # computed inside run_live_retrieval.
+    #   prefetch_offtopic: the off-topic filter's kept/rejected/threshold. None
+    #     when the filter is disabled or only seeds are present (seed_only) —
+    #     honestly absent, never a faked count.
+    #   drop_reasons: per-reason aggregate of the in-run _trace_drop calls
+    #     (offtopic / rerank_not_selected / fetch_failed / content_starved). The
+    #     four statically-known reasons are pre-seeded to 0 so the schema is
+    #     stable; counts derive locally (not from the pathB trace contextvar,
+    #     which is empty on a normal sweep).
+    prefetch_offtopic: dict[str, Any] | None = None
+    drop_reasons: dict[str, int] = field(default_factory=dict)
+    #   extraction_finding_rows: the EXTRACTION-stage finding-row count captured
+    #     at run_live_retrieval RETURN time (== len(evidence_rows) here), frozen
+    #     as an int. Codex diff-gate iter-1 P1: run_one_query MUTATES
+    #     retrieval.evidence_rows AFTER this returns (expansion append, deepener/
+    #     agentic reassign), so reading len(evidence_rows) at manifest-write time
+    #     reports the POST-expansion total, not the extraction yield. This frozen
+    #     int is the stable fetched->finding extraction count.
+    extraction_finding_rows: int = 0
 
 
 # ─────────────────────────────────────────────────────────────────────────────
@@ -2715,6 +2738,21 @@ def run_live_retrieval(
     """
     api_calls: dict[str, int] = {"serper": 0, "s2": 0, "openalex": 0, "fetch": 0}
     notes: list[str] = []
+    # I-ready-017 Task 2a (#1204): ADDITIVE source-funnel telemetry. Local
+    # aggregate of every _trace_drop call by reason, mirrored onto the result so
+    # the per-stage source loss is persisted (not just the pathB trace, which is
+    # empty on a normal sweep). Pre-seed the four statically-known reasons to 0
+    # so the manifest schema is stable; incrementing beside each _trace_drop
+    # leaves _trace_drop itself byte-identical (no behavior change).
+    drop_reasons: dict[str, int] = {
+        "offtopic": 0,
+        "rerank_not_selected": 0,
+        "fetch_failed": 0,
+        "content_starved": 0,
+    }
+    # Populated inside the Step-3 off-topic block; stays None when the filter is
+    # disabled or only seeds are present (honest absence, never a faked count).
+    prefetch_offtopic: dict[str, Any] | None = None
 
     # ── Step 0: UP-FRONT plan validation (I-meta-005 Phase 2, P2-note-1) ──
     # A malformed frame (bad evidence_need / bad jurisdiction SHAPE) must FAIL
@@ -2976,10 +3014,19 @@ def run_live_retrieval(
             candidates = _seed_cands + filt.kept
             for _dropped_url in _pre_offtopic_urls - {c.url for c in filt.kept}:
                 _trace_drop(_dropped_url, "offtopic")
+                drop_reasons["offtopic"] += 1
             notes.append(
                 f"prefetch_offtopic: {filt.total_kept} kept / "
                 f"{filt.total_rejected} rejected (threshold={filt.threshold_used:.2f})"
             )
+            # I-ready-017 Task 2a (#1204): persist the off-topic split. Store the
+            # raw threshold float (not the :.2f note string) so the manifest
+            # carries the unrounded value used in the filter decision.
+            prefetch_offtopic = {
+                "kept": filt.total_kept,
+                "rejected": filt.total_rejected,
+                "threshold": filt.threshold_used,
+            }
         # else: only seeds present (e.g. seed_only mode) — nothing to off-topic filter.
     kept_by_offtopic = len(candidates)
 
@@ -2999,6 +3046,7 @@ def run_live_retrieval(
     )
     for _dropped_url in _pre_rerank_urls - {c.url for c in candidates}:
         _trace_drop(_dropped_url, "rerank_not_selected")
+        drop_reasons["rerank_not_selected"] += 1
 
     classified_sources: list[CorpusSource] = []
     evidence_rows: list[dict[str, Any]] = []
@@ -3282,6 +3330,7 @@ def run_live_retrieval(
         if not ok:
             failed_fetch += 1
             _trace_drop(cand.url, "fetch_failed")
+            drop_reasons["fetch_failed"] += 1
         else:
             fetched += 1
 
@@ -3434,6 +3483,7 @@ def run_live_retrieval(
                     "for %r (len=%d)", cand.url, len(content),
                 )
                 _trace_drop(cand.url, "content_starved")
+                drop_reasons["content_starved"] += 1
             else:
                 direct_quote = _build_provenance_quote(
                     content, head_chars=1500, window_chars=500,
@@ -3485,4 +3535,11 @@ def run_live_retrieval(
         parallel_completion_rate=_parallel_completion_rate,
         fetch_workers=_fetch_workers,
         distinct_hosts=_distinct_hosts,
+        # I-ready-017 Task 2a (#1204): additive source-funnel telemetry.
+        prefetch_offtopic=prefetch_offtopic,
+        drop_reasons=drop_reasons,
+        # Codex diff-gate iter-1 P1: freeze the extraction-stage count HERE (at
+        # return), before run_one_query mutates evidence_rows via the expansion/
+        # deepener/agentic lanes.
+        extraction_finding_rows=len(evidence_rows),
     )
```

## TEST FILE (untracked): tests/polaris_graph/retrieval/test_source_funnel_telemetry.py
```python
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
```
