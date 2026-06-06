# FX-15b §-1.1 audit — host-class junk filter + seed-safe semantic prefetch (I-ready-017 #1119)

**Standard:** §-1.1 precision audit of `_is_low_content_host_or_page` over the REAL held drb_72
`retrieval_trace.jsonl`, **cross-referenced against `run_artifacts/evidence_pool.json`** (Codex
iter-1 P1 demanded the empirical check: does a dropped URL actually produce evidence?).

## Codex iter-1 P1 (fixed)
iter-1's blanket `/conference` reject FALSE-DROPPED real papers:
`/conference/2025/program/paper/S7SHZQ4n` (50,000 chars) and `/S25ktKkD` (30,440 chars) fetched as
REAL papers (`evidence_pool.json`). The junk `/conference/2023/program/paper/8A8RRTQY` has the
IDENTICAL URL shape — so a URL pattern CANNOT distinguish real-vs-junk conference papers. iter-2
narrows the filter to drop ONLY pure-nav pages and lets the POST-fetch tier classifier +
content-starvation check decide conference papers / supplement abstracts.

## iter-2 result on the real artifact (evidence_pool cross-reference)
- 41 agentic rows → **DROP 7, KEEP 34**.
- **Genuine false drops (dropped but produced real evidence): 0.**
- All 7 DROPPED have **0 evidence** in evidence_pool: `/issues/381`, `/forum/232`,
  `/journals/search-results?...per-page=21` (×2), `/search/index?jelcode=b1...page=504`,
  `/toc/jpe/2020/128/6`, `/toc/jpe/current`. Pure SERP / TOC / discussion listings.
- The 2 real evidence-bearing conference papers (S7SHZQ4n 50k, S25ktKkD 30k) are now **KEPT**.

## The fix (precision-corrected)
1. **Structural filter** `_is_low_content_host_or_page(url, title='')` (live_retriever) now rejects
   ONLY pages that cannot carry a paper's content: `/search`, `/browse`, `/issues/`, `/forum/`,
   `/toc/`, and SERP query strings (`search-results`, `per-page=`). **DELIBERATELY EXCLUDED**
   (they CAN bear evidence → post-fetch tiering, not pre-fetch drop): `/conference/.../program/paper/`,
   `/annual-meeting/.../paper/`, conference SUPPLEMENT abstracts (`_detect_conference_abstract`
   removed from the pre-fetch path). Applied to `_ag_urls` on the agentic lane, flag-gated
   `PG_AGENTIC_HOST_FILTER` (default on); `urls_selectable` telemetry added.
2. **Seed-safe Step-3** — the semantic prefetch filter now EXCLUDES injected seeds
   (`_SEED_SOURCE_LABELS`) before `filter_search_results`, so `enable_prefetch_filter=True` on the
   agentic lane can no longer drop the URL-only (empty-snippet) seeds as ~0-similarity off-topic.

## Offline smoke (proves the fix)
`pytest tests/polaris_graph/test_fx15b_host_filter_iready017.py` → 5 passed:
- structural reject of 9 pure nav/SERP/TOC shapes;
- **precision gate** — 11 KEEP URLs incl. the held conference papers (S7SHZQ4n, S25ktKkD), the
  same-shape junk 8A8RRTQY, the OUP supplement, real working-paper PDFs/DOIs — ZERO dropped;
- **Codex iter-1 P1 regression** — the exact held URLs that fetched real evidence asserted KEPT;
- empty-URL kept;
- **seed-exclusion repro** — with `enable_prefetch_filter=True` + a reject-ALL embedder stub, the
  empty-snippet agentic seed STILL survives and produces an evidence row.
- Regression: FX-15a (6) + `test_live_retriever_rerank` (8) + `test_retrieval_trace` (7) +
  `test_plan_sufficiency_phase3` (26) all pass.

## Faithfulness check
Quality/precision fix, now empirically precision-verified: on the real artifact the structural
floor drops ONLY 0-evidence pure-nav pages and keeps every evidence-bearing page (incl. the two
conference papers iter-1 wrongly dropped). The seed-exclusion PREVENTS a latent catastrophic drop
of the entire agentic seed lane. No grounding / strict_verify / 4-role-decision change.
Flag-gated + reversible.
