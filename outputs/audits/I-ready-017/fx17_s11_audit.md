# FX-17 §-1.1 audit — Serper visible clamp + pagination (#1126)

**Standard:** §-1.1 over the REAL held drb_72 `run_artifacts/retrieval_trace.jsonl` per-backend search
rows (the per-query result counts are run-time OUTPUT; the live pagination lift needs a live run, so
the fix is proven by offline smoke + verified at RERUN).

## The bug, on the real artifact (line-by-line)
Per-backend Serper search `return_count` across the 5 effective queries (held drb_72):
- **`serper`: [10, 10, 10, 10, 10]** — uniformly 10/query. `PG_SWEEP_MAX_SERPER=100` was silently
  floored to a single 20-item page (`min(num, 20)`), and there was NO pagination, so the breadth cap
  was inert and SILENT (the 100 setting "lied"). (Compare: §-1.1 of FX-18 used the same trace.)

## The fix
1. **Visible clamp**: `_serper_search` logs a loud WARNING + records clamp telemetry
   (`clamped`, `num_requested`, `per_page`, `page_max`) when `num` exceeds the Serper page max (20).
2. **Pagination**: a new `_serper_fetch_page` helper fetches one page; `_serper_search` loops the
   `page` param accumulating + deduping URLs up to `PG_SERPER_TOTAL_PER_QUERY` (default = one page →
   byte-identical to the legacy single call), bounded by `PG_SERPER_MAX_PAGES` (default 3), with
   early-stop when a page returns fewer than `per_page` items. Aggregate trace records
   `pages_fetched` + `total_budget`.
3. Query-variant count remains the env-tuned breadth knob (config; no code change).

Byte-identical default: with `PG_SERPER_TOTAL_PER_QUERY` unset, `total = per_page` → one page; for
page 1 the payload carries no `page` key — identical to the legacy request. The benchmark slate
raises the budget (e.g. 60 → 3 pages).

## Offline smoke (proves the fix)
`pytest tests/polaris_graph/test_fx17_serper_pagination_iready017.py` → 5 passed:
- **default single page** (no `PG_SERPER_TOTAL_PER_QUERY`): num=10 → exactly one page fetched.
- **visible clamp**: num=100 → WARNING "exceeds the page max" emitted; still one page on default.
- **pagination accumulates + dedups**: budget=40 → pages 1+2, overlapping URL deduped (39 unique).
- **early-stop**: a page returning < per_page halts further pages.
- **max-pages cap**: budget=200 + `PG_SERPER_MAX_PAGES=2` → only 2 pages fetched.
- Regression: `test_live_retriever_rerank` (8) + `test_retrieval_trace` (7) green.

## Faithfulness check
Discovery-breadth only. No grounding / strict_verify / 4-role-decision change. Every additional URL
passes the SAME fetch/tier/strict_verify/4-role gates. Added Serper calls are bounded by
`PG_SERPER_MAX_PAGES` (small) + the total-URL budget + early-stop. Default byte-identical; the
clamp WARNING surfaces the previously-silent floor (an honesty fix, not a behavior change to results).
