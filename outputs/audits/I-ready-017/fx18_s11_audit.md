# FX-18 §-1.1 audit — S2 short-keyword lane + wire OpenAlex (#1122)

**Standard:** §-1.1 on the REAL held drb_72 `run_artifacts/retrieval_trace.jsonl` per-backend search
rows (run-time OUTPUT, so the starvation is confirmed on the real artifact; the live result-count
lift needs a live run, so the fix is proven by offline smoke + verified at RERUN).

## The bug, on the real artifact (line-by-line)
Per-backend search `return_count` across the 5 effective queries:
- **`semantic_scholar` (S2): 5 calls → return_counts = [0, 0, 0, 0, 4]** — 4/5 NL queries returned
  ZERO; total = 4 candidates. S2 is a KEYWORD index; the sweep fed it the 40-70-word NL queries.
- `serper`: 5 calls → [10,10,10,10,10] = 50 (healthy).
- **`openalex_search`: NOT present** — the NL-friendly OpenAlex backend (`domain_backends.openalex_search`,
  already built + fail-open) was never wired into the sweep search lane.

So the academic discovery lane was starved: S2 contributed ~4 sources and OpenAlex contributed 0.

## The fix (discovery-breadth; faithfulness-SAFE)
1. **S2 short-keyword** — the per-query S2 call now sends `distill_keywords(q)` (a short,
   stopword-filtered, deduped, ≤8-term content phrase; reuses `query_decomposer._content_tokens`)
   instead of the NL `q`. Flag-gated `PG_S2_KEYWORD_DISTILL` (default on); an empty distillation
   falls back to the NL query (never an empty search). The candidate `query_origin` stays the NL `q`
   so the per-sub-query rerank reservation + plan-sufficiency are unchanged.
2. **Wire OpenAlex** — `openalex_search(q)` runs as a PARALLEL academic backend in the per-query loop
   (ADD/union, not replace S2 — Codex Q8), union+deduped via the shared `seen_urls`; candidates carry
   `source="openalex_search"`, default `query_origin=q`. Flag-gated `PG_OPENALEX_SEARCH` (default on);
   fail-open (a backend fault adds 0 hits).

Every new source passes the SAME fetch / tier / strict_verify / 4-role gates as any other — this only
widens DISCOVERY, never the grounding/verification bar.

## Offline smoke (proves the fix)
`pytest tests/polaris_graph/test_fx18_s2_keyword_openalex_iready017.py` → 3 passed:
- `distill_keywords`: 33-word NL → ≤8 content terms, stopwords dropped, deduped, strictly shorter;
  all-stopword question → `''` (caller falls back to the NL query).
- integration (mocked serper/s2/openalex/fetch): **S2 receives the DISTILLED keyword phrase** (not the
  NL query); **OpenAlex's new URL is merged** (`source="openalex_search"`); a URL OpenAlex shares with
  serper is **deduped** (present once, kept as the serper row).
- Regression: query_decomposer (14) + FX-15a (6) + FX-15b (5) + live_retriever_rerank (8) +
  retrieval_trace (7) + research_planner phase1 — 68 passed.

## Faithfulness check
Discovery-breadth only. No grounding / strict_verify / 4-role-decision change. Keyword distillation
risk (over-generalization) is bounded — it keeps the SAME leading content words (drops only
stopwords + caps length) and the downstream (now seed-safe, FX-15b) semantic prefetch + tier
classifier still filter. OpenAlex is fail-open + flag-gated. Both knobs reversible.
