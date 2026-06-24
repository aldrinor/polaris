HARD ITERATION CAP: 5 per document. This is iter 4 of 5.



## ITER-3 RESOLUTION — verify (iter-3 confirmed iter-2 P1 fixed, raised 2 NEW P1)
- **P1 anchor re-run (generated query dropped):** FIXED. _iter_per_query_retrieve now passes the
  ORIGINAL question as run_live_retrieval `research_question` (scope context only) and the
  IterResearch-GENERATED query via `amplified_queries=[query]` with `anchor_seed=False` — the
  gap-round single-query pattern (~line 9036). The generated query is the SOLE fired query; no 35x
  anchor re-run.
- **P1 worker cost-context + client lifecycle:** FIXED by mirroring the proven _planner_llm wrapper
  (~line 6005): copy_context() for READ visibility, capture worker _RUN_COST_CTX in finally (even on
  raise), write the cost DELTA back to the parent _RUN_COST_CTX, and `await client.close()` in finally.
  So IterResearch policy spend now merges into parent/manifest cost + the runaway budget guard.

## ITER-2 RESOLUTION — verify (iter-2 confirmed the 3 iter-1 P1s fixed, raised 1 NEW P1)
- **NEW P1 (client reused across asyncio.run loops):** FIXED. `_iter_llm` now constructs a FRESH
  OpenRouterClient INSIDE the worker per call, so its httpx.AsyncClient lives and dies within the
  same asyncio.run() loop — no cross-loop reuse, round 2+ is safe. Client __init__ is network-free
  (cheap per-round). The 2 iter-2 P2s (extra source-funnel telemetry merge; duplicate-query round
  cost) are accepted v1 debt / follow-ups, not fixed here.

## ITER-1 RESOLUTIONS — verify each (iter-1 returned REQUEST_CHANGES: 3 P1)
- **P1 asyncio.run crash:** `_iter_llm` now runs the async generate in a WORKER THREAD
  (ThreadPoolExecutor max_workers=1 -> asyncio.run in a thread with no running loop), so it is safe
  inside the already-async run_one_query. No asyncio.run on the sweep loop.
- **P1 evidence-id collision:** `merge_retrieval_results` now RENUMBERS every merged evidence row to
  a globally-unique `ev_NNN` (copies the row first, reassigns evidence_id by running index) — verified
  by smoke: two results both starting at ev_000 merge to ev_000/ev_001/ev_002 (unique).
- **P1 dropped contract fields:** merge now carries `journal_metadata_sidecar` (dict-merged across
  rounds), `corpus_truncated` (OR-propagated), and candidates_total/processed — verified by smoke.
- **P2 seed_urls:** the layer-4 DOI seed is now passed on the FIRST IterResearch query only (not None).
- **P2 max_tokens:** raised to PG_QGEN_ITERRESEARCH_MAX_TOKENS (default 8192) per token governance.
Smoke (all green): py_compile x2; merge ev-id renumber unique; corpus_truncated OR; sidecar merge;
flag default OFF.

- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution risks; classify minor issues P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

FRONTIER-TECH MANDATE: IterResearch = Tongyi DeepResearch (arXiv 2510.24701 / 2511.07327), the
I-qgen-001 (#1291) bake-off winner on DRB-II info_recall coverage.

# Diff review — I-qgen-002 (#1292): wire IterResearch adaptive query-gen into the production sweep

STATIC code review. Do NOT run pytest. Read `.codex/I-qgen-002/codex_diff.patch` (2 files, ~276 lines):
1. `src/polaris_graph/retrieval/iterresearch_query_gen.py` (NEW) — the IterResearch workspace-
   reconstruction loop: each round the GLM-5.2 policy sees ONLY (question, evolving report, last
   obs), emits a rewritten REPORT (overwritten = strategic forgetting) + the next QUERY (or STOP);
   that one query is retrieved via an INJECTED per_query_retrieve; per-round LiveRetrievalResults
   are MERGED (dedup evidence by source_url, dedup sources by url, sum api_calls). Injectable llm +
   retrieve + result_factory (no live_retriever import at module load; unit-testable on stubs).
2. `scripts/run_honest_sweep_r3.py` (MODIFIED, ~+55 lines at the retrieval call site) — flag-gated
   branch: when `PG_QGEN_ITERRESEARCH=1`, run the IterResearch loop where each query calls the SAME
   `run_live_retrieval` (single query, amplified_queries=[]); else the EXISTING run_live_retrieval
   call runs UNCHANGED.

## Design intent
- FLAG-GATED, DEFAULT OFF => byte-identical to the current template-facet path (verify the else
  branch is character-identical to the original call).
- FAITHFULNESS UNTOUCHED: only query SELECTION changes; every query still flows through the
  unchanged run_live_retrieval (scope gate, tier classify, fetch, provenance), and strict_verify /
  NLI / 4-role / provenance are not touched. Confirm this holds.
- Downstream contract preserved: the merged result is a real LiveRetrievalResult, so consolidation
  -> generation -> verify -> render see the same shape.

## What to check (your call — Codex is the gate)
- BYTE-IDENTICAL OFF: when PG_QGEN_ITERRESEARCH is unset, is behaviour exactly as before (the else
  branch identical to the pre-change call)? Any path where the flag-off case differs?
- MERGE CORRECTNESS: does merge_retrieval_results correctly dedup evidence_rows by source_url and
  classified_sources by url, sum api_calls, and produce a valid LiveRetrievalResult that downstream
  consumes the same way? Any field downstream needs that the merge drops or miscomputes (e.g.
  journal_metadata_sidecar, fetch_success_rate, corpus_truncated, prefetch_offtopic)?
- LOOP CORRECTNESS: strategic-forgetting (report overwrite), STOP handling, duplicate-query skip,
  max_rounds cap. Could the loop spin or never terminate?
- RESOURCE/PERF: the ON path calls run_live_retrieval once PER query (up to 35) instead of once
  total — is that an acceptable cost shape, and is asyncio.run(per call) on the injected llm safe
  here (single-threaded sweep, not the ThreadPool that deadlocked in #1291)?
- SEED/DOMAIN: the ON path passes seed_urls=None (vs _retrieval_seed_urls off-mode). Is dropping the
  layer-4 DOI seed in IterResearch mode acceptable for v1, or a correctness gap to flag?
- FAITHFULNESS: confirm nothing in either file touches/relaxes a faithfulness gate.
- Any NEW P0/P1 that makes the production path unsafe even with the flag.

## Output schema (this exact schema; loose prose rejected)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
