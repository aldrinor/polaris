# Claude architect audit — PR8: per-call retrieval_trace.jsonl (#945)

**Issue:** #945 (q1c-4, operator's §-1.1 line-by-line / full-run-log requirement). **Branch:**
`bot/I-meta-002-q1d-retrieval-trace`. **Both Codex gates APPROVE iter-1** (brief + diff, zero P0/P1/P2).
**NO SPEND** — purely additive observability, 23 offline tests.

## What this adds and why

Codex-verified gap (#941): `pathB_capture.record_retrieval_attempt(backend)` stored only the backend NAME
in a set (a presence flag); the individual Serper / S2 / OpenAlex calls, their queries, returned URLs,
kept-source backends, and per-drop reasons were never recorded — so the retrieval half of a run could not be
audited line-by-line. This mirrors the generator's `reasoning_trace.jsonl` for the search/fetch half, giving
the operator the "full log during the run, alphabet-level" record they require.

## Design — purely observational, via the existing contextvar pattern

A new `_RETRIEVAL_TRACE` contextvar in `pathB_capture.py` (fresh list per query via `start_retrieval_trace()`,
nulled by `clear_pathB_capture()`), with best-effort recorders `record_retrieval_query/kept/drop` that no-op
when not started — exactly the idiom of the existing `record_retrieval_attempt`. Lazy-import best-effort
helpers `_trace_query/_trace_kept/_trace_drop` in `live_retriever.py`. **Every hook is an additive observer;
the §9.1 retrieval/strict_verify chokepoint — ranking, fetch, `classify_source_tier`, `is_content_starved`,
`_build_provenance_quote`, evidence-row content, and every return value — is byte-for-byte unchanged**
(verified by `test_serper_hook_observational_only`, which asserts `_serper_search` returns the exact parsed
candidates AND emits a query record).

## What is captured (the §-1.1 retrieval audit contract)

- **Per query:** backend, query text, return count, returned URLs — at `_serper_search`, `_s2_bulk_search`
  (success + attempted-error paths), and the `domain_backends` policy serper.
- **Per kept source:** URL + originating backend — at the `evidence_rows.append` keep point (`cand.source`).
- **Per drop:** URL + reason — `content_starved` (is_content_starved skip), `fetch_failed` (fetch failure),
  `offtopic` (prefetch off-topic filter, via pre/post URL-set diff), `rerank_not_selected` (rerank
  reservation, via pre/post diff).

## Lifecycle hygiene (Codex brief-gate P2)

`start_retrieval_trace()` creates a FRESH list per query (no prior query's records leak into a later
run_dir). An empty `retrieval_trace.jsonl` is materialized early (so a run that aborts before retrieval still
ships the file). `_flush_retrieval_trace()` is best-effort (a write error never aborts the run) and fires
right before the adequacy abort gate — after all retrieval (base + R-6 + deepener) — so EVERY exit path
(abort_corpus_inadequate, approval-denied, success) ships the full trace.

## Tests (23 pass, NO SPEND)

`test_retrieval_trace.py` (7): no-op-when-not-started, accumulate, fresh-list-no-stale-leak, jsonl
round-trip, clear resets, serper-hook-observational-only (return value unchanged + record emitted),
trace-helpers-best-effort. Plus live_retriever_rerank + deepener_sweep_adapter no-regression (16).
`py_compile` OK. Patch is +241/-0 (purely additive).

## Verdict

Records per-query / per-kept / per-drop into a run_dir `retrieval_trace.jsonl` via the existing contextvar
pattern, changes NO retrieval/verify behavior or return value, is NO-SPEND and offline-tested, leaves the
§9.1 chokepoint untouched. Both gates APPROVE iter-1. Ready to queue for operator merge (Option A — no spend).
