# FX-17 (#1126) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
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
(vs FX-13 verified tip `5004b5a6`).

## Bug — confirmed §-1.1 on the REAL held trace
`_serper_search` did `min(num, 20)` SILENTLY (PG_SWEEP_MAX_SERPER=100 floored to a 20-item page) and
never paginated. Held drb_72 serper return_counts: **[10, 10, 10, 10, 10]** (uniform, single page; the
100 cap was inert + lying). Full §-1.1: `outputs/audits/I-ready-017/fx17_s11_audit.md`.

## Fix
1. **Visible clamp**: WARNING + clamp telemetry (`clamped/num_requested/per_page/page_max`) when
   `num > _SERPER_PAGE_MAX (20)`.
2. **Pagination**: new `_serper_fetch_page(query, per_page, page, headers)` helper (byte-identical
   payload when page==1 — no `page` key); `_serper_search` loops pages, dedups via `seen`, up to
   `PG_SERPER_TOTAL_PER_QUERY` (default = per_page → ONE page → byte-identical), bounded by
   `PG_SERPER_MAX_PAGES` (default 3), early-stop when a page returns < per_page. Aggregate trace adds
   `pages_fetched`/`total_budget`.
3. Query-variant count stays the env-tuned breadth knob (config; no code change).

## Evidence
- §-1.1 held trace: serper [10,10,10,10,10] — above.
- Offline smoke `test_fx17_serper_pagination_iready017.py` → 5 passed: default single page (no
  pagination); num=100 → WARNING + still single page on default; budget=40 → pages 1+2 accumulate +
  **dedup** (overlapping URL → 39 unique); short page → early-stop; `PG_SERPER_MAX_PAGES=2` cap
  respected over a budget of 200.
- Regression: `test_live_retriever_rerank` (8) + `test_retrieval_trace` (7) green.

## Decisions made (please confirm)
- **Default = one page (byte-identical):** `PG_SERPER_TOTAL_PER_QUERY` unset → total = per_page → 1
  page; page-1 payload has no `page` key (identical to the legacy request). The clamp WARNING still
  fires on the default path when num>20 (the intended honesty fix — it's a log, not a result change).
  Acceptable?
- **Bounds:** `PG_SERPER_MAX_PAGES` default 3 + total-URL budget + early-stop keep added Serper calls
  small. OK?

## Question
Is the pagination correct (dedup, early-stop, max-pages, byte-identical default) and the clamp now
honestly surfaced? Anything blocking APPROVE?
