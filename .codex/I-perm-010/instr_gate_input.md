# Codex diff-gate — Task 2a (#1204): source-funnel telemetry persistence

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. Same quality bar regardless of iteration.
- Don't pick bone from egg: reserve P0/P1 for real execution risks; cosmetic -> P3/P2.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What this change does
ADDITIVE source-funnel telemetry ONLY. Persists counts ALREADY computed inside
run_live_retrieval so the ~90% pre-fetch source loss is measurable on a fresh run.
GOAL: zero change to what is discovered/filtered/fetched/selected; manifest gains keys only.

## Claude's own line-by-line review (VERIFY these, do not re-discover):
1. live_retriever.py: 2 additive fields on LiveRetrievalResult (prefetch_offtopic: dict|None=None,
   drop_reasons: dict=field(default_factory=dict)); 'field' and 'Any' confirmed imported (lines 34,36).
2. A 'drop_reasons[reason] += 1' was added beside EACH of the 4 _trace_drop call sites; grep confirms
   exactly 4 _trace_drop sites (offtopic/rerank_not_selected/fetch_failed/content_starved) and all 4
   are counted -> no missed site -> no silent undercount.
3. prefetch_offtopic built from the existing filt.total_kept/total_rejected/threshold_used (raw float).
4. run_honest_sweep_r3._retrieval_manifest_section persists kept_by_offtopic (=getattr
   candidates_kept_by_offtopic, a REAL existing field line 135, populated line 3517), prefetch_offtopic,
   drop_reasons, extraction_yield{fetched=candidates_fetched (real, line136/3518), finding_rows=
   len(evidence_rows) (real, line132/3514)}. All getattr names resolve to real fields (verified).
5. Tests: 7 telemetry + 14 manifest-contract + 39 live_retriever regression = 60 green. No mock (§9.4).

## RED-TEAM CHECKLIST (please verify against the diff below):
(a) Is retrieval BEHAVIOR byte-identical? (no change to filter/cap/threshold/ordering/what-is-fetched
    -or-selected — every added line is a field default, a counter init, a += beside an existing
    _trace_drop, or a dict built from already-computed values.)
(b) Are the new manifest counts REAL (sourced from actually-computed attrs; honest None/empty when
    absent; never a fabricated count)?
(c) Any faithfulness-gate (strict_verify/4-role/D8) touch? (should be NONE.)
(d) Is the test meaningful (asserts keys populate from real values AND honest-absence)?

Emit the §8.3.9 schema; final line EXACTLY 'verdict: APPROVE' or 'verdict: REQUEST_CHANGES'.

## DIFF (tracked files)
```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index ac733cef..304b306e 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -1111,6 +1111,37 @@ def _retrieval_manifest_section(retrieval) -> dict:
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
+        # EXTRACTED from fetched content (len(evidence_rows)) — the honest
+        # extraction-stage count that is ALWAYS available. This deliberately
+        # differs from finding_dedup.raw_row_count, which is a POST-selection,
+        # dedup-gated count (PG_USE_FINDING_DEDUP defaults OFF, so it is absent
+        # on most runs); len(evidence_rows) keeps this key populated every run.
+        "extraction_yield": {
+            "fetched": getattr(retrieval, "candidates_fetched", 0),
+            "finding_rows": len(getattr(retrieval, "evidence_rows", []) or []),
+        },
     }
 
 
diff --git a/src/polaris_graph/retrieval/live_retriever.py b/src/polaris_graph/retrieval/live_retriever.py
index 8e3cc297..02d42320 100644
--- a/src/polaris_graph/retrieval/live_retriever.py
+++ b/src/polaris_graph/retrieval/live_retriever.py
@@ -158,6 +158,21 @@ class LiveRetrievalResult:
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
 
 
 # ─────────────────────────────────────────────────────────────────────────────
@@ -2715,6 +2730,21 @@ def run_live_retrieval(
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
@@ -2976,10 +3006,19 @@ def run_live_retrieval(
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
 
@@ -2999,6 +3038,7 @@ def run_live_retrieval(
     )
     for _dropped_url in _pre_rerank_urls - {c.url for c in candidates}:
         _trace_drop(_dropped_url, "rerank_not_selected")
+        drop_reasons["rerank_not_selected"] += 1
 
     classified_sources: list[CorpusSource] = []
     evidence_rows: list[dict[str, Any]] = []
@@ -3282,6 +3322,7 @@ def run_live_retrieval(
         if not ok:
             failed_fetch += 1
             _trace_drop(cand.url, "fetch_failed")
+            drop_reasons["fetch_failed"] += 1
         else:
             fetched += 1
 
@@ -3434,6 +3475,7 @@ def run_live_retrieval(
                     "for %r (len=%d)", cand.url, len(content),
                 )
                 _trace_drop(cand.url, "content_starved")
+                drop_reasons["content_starved"] += 1
             else:
                 direct_quote = _build_provenance_quote(
                     content, head_chars=1500, window_chars=500,
@@ -3485,4 +3527,7 @@ def run_live_retrieval(
         parallel_completion_rate=_parallel_completion_rate,
         fetch_workers=_fetch_workers,
         distinct_hosts=_distinct_hosts,
+        # I-ready-017 Task 2a (#1204): additive source-funnel telemetry.
+        prefetch_offtopic=prefetch_offtopic,
+        drop_reasons=drop_reasons,
     )
```

## NEW TEST FILE (untracked): tests/polaris_graph/retrieval/test_source_funnel_telemetry.py
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
    """The 2nd-biggest drop (fetched -> finding rows). finding_rows is the count
    of evidence rows EXTRACTED from fetched content == len(evidence_rows)."""
    rows = [{"evidence_id": f"ev_{i:03d}"} for i in range(55)]
    r = LiveRetrievalResult(
        classified_sources=[], evidence_rows=rows,
        total_candidates_pre_filter=2981, candidates_kept_by_scope=0,
        candidates_kept_by_offtopic=740, candidates_fetched=500,
        candidates_failed_fetch=10,
    )
    sec = _section(r)
    assert sec["extraction_yield"] == {"fetched": 500, "finding_rows": 55}


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
