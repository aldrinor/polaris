HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

RULE NOW — emit the YAML verdict block FIRST. Read ONLY the patch at
`.codex/I-meta-002-q1d-retrieval-trace/codex_diff.patch` (5 files, +241/-0, PURELY ADDITIVE). NO SPEND.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex diff-gate (iter 1) — PR8: per-call retrieval_trace.jsonl (#945)

Verify the diff implements the brief-gate-APPROVE'd plan (brief APPROVE iter 1) and changes NO retrieval/
verification behavior.

## What to verify
1. **pathB_capture.py**: new `_RETRIEVAL_TRACE` contextvar (init/`start_retrieval_trace` sets `[]`; reset
   nulls in `clear_pathB_capture`). Recorders `record_retrieval_query/kept/drop` are best-effort no-ops when
   the contextvar is None (mirror the existing `record_retrieval_attempt` idiom). `retrieval_trace_records()`
   accessor.
2. **live_retriever.py**: 3 lazy-import best-effort helpers `_trace_query/_trace_kept/_trace_drop`. Hooks:
   per-query at `_serper_search` (success + 2 attempted-error returns) + `_s2_bulk_search` (success + 2
   errors); per-kept at `evidence_rows.append` (`record kept(cand.url, cand.source)`); per-drop at
   `is_content_starved` skip (`content_starved`), fetch-fail (`fetch_failed`), prefetch off-topic filter
   (`offtopic`, via pre/post URL set diff), rerank non-selection (`rerank_not_selected`, via pre/post diff).
   **CRITICAL: confirm NONE of these change retrieval ranking, fetch, classification, is_content_starved,
   _build_provenance_quote, evidence_rows content, or any return value — they are additive observers only.**
3. **domain_backends.py**: per-query record at the policy serper return (best-effort).
4. **run_honest_sweep_r3.py**: `start_retrieval_trace()` once per query before retrieval + early empty
   materialize; `_flush_retrieval_trace()` (best-effort, never aborts) called right before the adequacy
   abort gate (line ~2031) so ALL exit paths (abort_corpus_inadequate, approval-denied, success) ship the
   full base+R-6+deepener trace. P2 lifecycle hygiene: fresh list per query (no stale-record leak).

## Evidence (verified by Claude main-thread, NO SPEND)
- 23 tests PASS: recorders no-op-when-not-started / accumulate / fresh-list-no-stale-leak / jsonl round-trip
  / clear resets; **`_serper_search` with a stubbed httpx returns the EXACT parsed candidates (hook does NOT
  alter the return) AND emits a query record**; trace helpers best-effort (never raise). Plus
  live_retriever_rerank + deepener_sweep_adapter no-regression.
- `py_compile` OK on all 4 source files. Patch is +241/-0 (purely additive).

## The real risks to rule on
1. Does ANY hook alter a retrieval return value / ranking / fetch / classification / evidence-row content?
   (Claim: no — every hook is an additive best-effort recorder; the §9.1 chokepoint is byte-for-byte
   unchanged. Verified by test_serper_hook_observational_only.)
2. Pre/post URL-set diff for offtopic + rerank drops — correct + cheap, no behavior change? (Claim: yes —
   it only READS candidate URLs before/after the existing transform.)
3. Flush lifecycle: fresh list per query, best-effort flush before the abort gate covers all exit paths, no
   stale-record leak into the next query? (P2 from brief gate — addressed by start_retrieval_trace fresh list.)
4. Best-effort `except Exception: pass` in the trace helpers — acceptable (mirrors the EXISTING
   record_retrieval_attempt idiom at the same call sites), not a new silent-failure pattern?

APPROVE iff the diff records per-query/per-kept/per-drop into run_dir `retrieval_trace.jsonl` via the existing
contextvar pattern, changes NO retrieval/verify behavior or return value, is NO-SPEND and offline-tested, and
leaves the §9.1 chokepoint untouched.
