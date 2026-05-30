HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution risks; non-blockers are P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

RULE NOW — emit the YAML verdict block FIRST. APPROVE this CONCRETE plan or REQUEST_CHANGES with specifics.
Additive observability for the operator's §-1.1 line-by-line / "full log during the run" requirement.
PURELY OBSERVATIONAL — the §9.1 retrieval/strict_verify chokepoint is READ, never altered. NO SPEND offline.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex brief-gate (iter 1) — PR8: per-call retrieval_trace.jsonl (#945)

Codex-verified gap (#941): `pathB_capture.record_retrieval_attempt(backend)` stores only the backend NAME
in a set (presence flag); the 41 Serper + 41 S2 + 19 OpenAlex individual calls, their queries, returned
URLs, kept-source backends, and per-drop reasons are NOT recorded — so the retrieval half cannot be audited
line-by-line. Mirror the generator's `reasoning_trace.jsonl` for the search/fetch half.

## GROUNDED FACTS (verified; do not re-explore)
- `pathB_capture.py`: contextvar pattern — `_RETRIEVAL: ContextVar[set|None]` (`:37`); init sets `_SINK.set([])`
  + `_RETRIEVAL.set(set())` (`:52-53`); reset nulls both (`:58-60`); `record_retrieval_attempt(backend)`
  (`:142`) is best-effort (no-op when contextvar is None). This is the pattern to extend.
- Per-query data is LOCAL at the backend functions: `_serper_search(query, num)` builds `out=[{url,title,
  snippet,source}]` and `return out` (live_retriever.py:85-122); `_s2_bulk_search(query, limit)` similar
  (:125+); `domain_backends.py:180` serper. `record_retrieval_attempt` already fires at :95 / :130 / :180.
- The fetch loop (live_retriever.py ~1651-1691) is the keep/drop chokepoint: `classify_source_tier` →
  `classified_sources.append` (always) → `if content: if is_content_starved(content): SKIP (drop, :1674)
  else evidence_rows.append({...,"source": cand.source}) (KEEP, :1683)`. `cand.source` is the originating
  backend. Other drop sites: fetch-failure (`candidates_failed_fetch`), off-topic prefetch filter
  (`kept_by_offtopic`), rerank non-reservation (`_rerank_and_reserve`).
- The generator flushes `reasoning_trace.jsonl` via `_reasoning_collector.flush(run_dir)` at
  run_honest_sweep_r3.py:1342 — the mirror flush point for `retrieval_trace.jsonl`.

## CONCRETE PROPOSAL (additive, observational, contextvar pattern)
1. **Extend `pathB_capture.py`**: add `_RETRIEVAL_TRACE: ContextVar[list|None]` (init `[]` / reset `None`
   alongside `_RETRIEVAL`). New best-effort recorders (no-op when contextvar None, like existing ones):
   - `record_retrieval_query(backend, query, urls)` → append `{"kind":"query","backend","query","return_count":len(urls),"urls"}`.
   - `record_retrieval_kept(url, backend)` → append `{"kind":"kept","url","backend"}`.
   - `record_retrieval_drop(url, reason)` → append `{"kind":"drop","url","reason"}`.
   - `retrieval_trace_records() -> list[dict]` accessor.
   - A `start_retrieval_trace()` (sets `_RETRIEVAL_TRACE.set([])`) so the sweep guarantees capture
     regardless of the pathB sink gate.
2. **Hooks (each a one-line lazy try/except, mirroring record_retrieval_attempt — NO logic change):**
   - `_serper_search` (before `return out`): `record_retrieval_query("serper", query, [o["url"] for o in out])`.
   - `_s2_bulk_search` (before its return): `record_retrieval_query("semantic_scholar", query, [urls])`.
   - `domain_backends.py` serper backend: same per-query record.
   - fetch loop KEEP (`evidence_rows.append`, :1683): `record_retrieval_kept(cand.url, cand.source)`.
   - fetch loop DROP (`is_content_starved` skip, :1674): `record_retrieval_drop(cand.url, "content_starved")`.
   - fetch-failure drop: `record_retrieval_drop(url, "fetch_failed")`.
   - off-topic prefetch filter drop: `record_retrieval_drop(url, "offtopic")`.
   - rerank non-reserved drop: `record_retrieval_drop(url, "rerank_not_selected")`.
3. **Flush in `run_honest_sweep_r3.py`**: `start_retrieval_trace()` before retrieval in run_one_query;
   write `run_dir/retrieval_trace.jsonl` (one JSON object per line, mirroring reasoning_trace) from
   `retrieval_trace_records()` near the reasoning_trace flush. Best-effort; a trace-write error never
   aborts the run.
4. Tests: recorders accumulate query/kept/drop records; no-op when contextvar not started; jsonl round-trips
   (one object/line); the hooks don't change retrieval return values (call `_serper_search` with a stubbed
   httpx → assert `out` unchanged AND a query record emitted). NO network.

## Constraints / frozen
snake_case; explicit imports; no except:pass (best-effort hooks use `except Exception: pass` ONLY mirroring
the EXISTING record_retrieval_attempt idiom at live_retriever:96 — same lazy-import guard, not a new silent-
failure pattern). UNTOUCHED: strict_verify, classify_source_tier, is_content_starved, _build_provenance_quote,
evidence_rows content, the §9.1 chokepoint behavior — this PR only OBSERVES. ≤200 LOC.

## The real risks to rule on
1. Is the contextvar-list pattern (vs a reasoning_trace-style Collector class) the right choice for
   consistency + lightness? (Claim: yes — mirrors the existing `_RETRIEVAL` set + `record_retrieval_attempt`.)
2. Do the hooks alter ANY retrieval behavior / return value? (Claim: no — each is an additive best-effort
   recorder; the chokepoint logic is byte-for-byte unchanged.)
3. Is the drop-reason set complete enough for line-by-line audit (content_starved / fetch_failed / offtopic /
   rerank_not_selected)? Any drop path missed?
4. Flush placement: per-query run_dir/retrieval_trace.jsonl, best-effort, never aborts the run — correct?

APPROVE iff this records per-query (backend/query/count/urls) + per-kept (url/backend) + per-drop (url/reason)
into a run_dir `retrieval_trace.jsonl` via the existing contextvar pattern, changes NO retrieval/verify
behavior, is NO-SPEND and testable offline, and leaves the §9.1 chokepoint untouched.
