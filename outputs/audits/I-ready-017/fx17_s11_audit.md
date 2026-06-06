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

## iter-2 — Codex iter-1 findings addressed
Codex iter-1 returned REQUEST_CHANGES on two real findings; both are now fixed.

**P1 — the fix was inert on the paid benchmark (slate not wired).** The Gate-B slate set
`PG_SWEEP_MAX_SERPER=100` but did NOT set `PG_SERPER_TOTAL_PER_QUERY`, so on the benchmark execution
path the run stayed single-page (~20/query) and the pagination lift never fired — the exact
"silent throttle reaches a paid run" class this campaign exists to kill. Fixed by:
- `_FULL_CAPABILITY_BENCHMARK_SLATE` now sets `PG_SERPER_TOTAL_PER_QUERY=60` + `PG_SERPER_MAX_PAGES=3`
  (`scripts/dr_benchmark/run_gate_b.py:419-420`).
- `_BENCHMARK_PREFLIGHT_FLOORS` now FAILS CLOSED if `PG_SERPER_TOTAL_PER_QUERY<40` or
  `PG_SERPER_MAX_PAGES<2` (`run_gate_b.py:509-510`) — an explicit operator override (or absence) that
  would leave the run single-page now aborts before any spend, with the same message class as the
  fetch/serper/s2 floors. Verified: absent key → `os.getenv(name,"0")` → 0 < 40 → RuntimeError.

**P2 — `api_calls['serper']` undercounted paginated breadth.** `run_live_retrieval` incremented
`api_calls['serper']` once per query regardless of pages fetched, so telemetry under-reported the real
Serper call volume on the benchmark. Fixed by threading `api_calls` into `_serper_search` and bumping
it once per HTTP page inside the page loop (`live_retriever.py` `_serper_search` + caller ~2411); the
redundant per-query `+= 1` at the call site is removed.

### iter-2 offline smoke (proves the iter-2 fixes)
`pytest tests/polaris_graph/test_fx17_serper_pagination_iready017.py` → 7 passed (5 original + 2 new):
- **api_calls counts each page**: budget=40, 2 pages → `api_calls['serper'] == 2` (not 1).
- **api_calls=None is safe**: default caller path (no kwarg) does not raise.
- Slate+preflight regression: `pytest tests/dr_benchmark/` → 291 passed (the new floors do not break
  any existing slate/preflight/CLI fixtures).
