# FX-17 (#1126) diff-gate — ITER 2 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
P2 discovery-breadth — faithfulness-SAFE (adds candidates; all pass the same fetch/tier/strict_verify/
4-role gates). Default byte-identical (single page). Diff: `.codex/I-ready-017/fx17_codex_diff.patch`
(vs FX-13 verified tip `5004b5a6`, 3 files: live_retriever.py + run_gate_b.py + the smoke test).

## What iter-1 found (both fixed in this diff)
You returned REQUEST_CHANGES with two findings. Both are addressed:

**P1 (iter-1) — the pagination fix was inert on the paid benchmark.** The Gate-B slate set
`PG_SWEEP_MAX_SERPER=100` but never set `PG_SERPER_TOTAL_PER_QUERY`, so the benchmark execution path
stayed single-page (~20/query) — the fix only worked under manual env. **Now fixed:**
- `scripts/dr_benchmark/run_gate_b.py:419-420` — `_FULL_CAPABILITY_BENCHMARK_SLATE` sets
  `PG_SERPER_TOTAL_PER_QUERY=60` + `PG_SERPER_MAX_PAGES=3`.
- `run_gate_b.py:509-510` — `_BENCHMARK_PREFLIGHT_FLOORS` adds `PG_SERPER_TOTAL_PER_QUERY:40` +
  `PG_SERPER_MAX_PAGES:2`. The preflight (`preflight_full_capability`, ~655) FAILS CLOSED if the
  effective value is below the floor; for these two keys there is NO default in `_defaults`, so an
  absent key reads `"0"` → 0 < 40 → RuntimeError before any spend. An explicit operator
  `PG_SERPER_TOTAL_PER_QUERY=10` also aborts. This matches the fetch/serper/s2 floor pattern.

**P2 (iter-1) — `api_calls['serper']` undercounted paginated breadth.** `run_live_retrieval`
incremented `api_calls['serper']` once per query regardless of pages. **Now fixed:**
- `_serper_search` takes `api_calls: dict[str,int] | None = None` and bumps
  `api_calls['serper'] += 1` once per `_serper_fetch_page` call inside the page loop (counts every
  HTTP page request, including a failed one — a real call was made).
- The caller (`live_retriever.py` ~2411) now passes `api_calls=api_calls`; the redundant
  per-query `api_calls["serper"] += 1` is DELETED.

## The original bug (unchanged from iter-1, for context)
`_serper_search` did `min(num, 20)` SILENTLY and never paginated. Held drb_72 serper return_counts:
**[10, 10, 10, 10, 10]** (single page; the 100 cap was inert + lying). §-1.1:
`outputs/audits/I-ready-017/fx17_s11_audit.md`.

## Fix summary (full)
1. **Visible clamp**: WARNING + clamp telemetry when `num > _SERPER_PAGE_MAX (20)`.
2. **Pagination**: `_serper_fetch_page(query, per_page, page, headers)` (byte-identical payload when
   page==1 — no `page` key); `_serper_search` loops pages, dedups via `seen`, up to
   `PG_SERPER_TOTAL_PER_QUERY` (default = per_page → ONE page → byte-identical), bounded by
   `PG_SERPER_MAX_PAGES` (default 3), early-stop when a page returns < per_page.
3. **Slate + preflight wiring** (iter-2 P1 fix) — above.
4. **Per-page api_calls counting** (iter-2 P2 fix) — above.

## Evidence
- §-1.1 held trace: serper [10,10,10,10,10] (the inert cap).
- Offline smoke `test_fx17_serper_pagination_iready017.py` → **7 passed** (5 original + 2 new):
  default single page; num=100 → WARNING + still single page on default; budget=40 → pages 1+2
  accumulate + dedup (39 unique); short page → early-stop; `PG_SERPER_MAX_PAGES=2` cap respected;
  **api_calls counts each page (==2, not 1)**; **api_calls=None back-compat (no raise)**.
- Slate/preflight regression: `pytest tests/dr_benchmark/` → **291 passed** (new floors break nothing).

## Faithfulness check
Discovery-breadth only. No grounding / strict_verify / 4-role change. Every additional URL passes the
SAME downstream gates. Added Serper calls bounded by `PG_SERPER_MAX_PAGES` + total-URL budget +
early-stop. Default byte-identical; the clamp WARNING surfaces the previously-silent floor (honesty,
not a result change).

## Question
Are the two iter-1 findings fully resolved (slate+preflight activation fail-closed; api_calls counted
per page) and is the pagination still correct (dedup, early-stop, max-pages, byte-identical default)?
Anything blocking APPROVE?
