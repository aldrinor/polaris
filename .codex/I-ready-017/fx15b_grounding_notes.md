# FX-15b grounding notes (#1119) — host-class junk filter + seed-safe semantic prefetch

Depends on FX-15a (#1118, DONE). Author NEXT wake with fresh context (faithfulness-adjacent precision).

## Code anchors (verified this wake)
- Agentic caller: `scripts/run_honest_sweep_r3.py:2907` `if _ag_urls:` → `:2909-2923`
  `run_live_retrieval(... enable_prefetch_filter=False, seed_urls=_ag_urls, seed_only=True,
  seed_source='agentic_seed', seed_query_origin='agentic_seed')`. Merge at `:2928`
  `merge_seed_url_evidence(...)`.
- `_ag_urls` is `list[str]` from `harvest_agentic_urls(_ag_result, cap=_ag_url_cap)` — URL-only, NO
  title/snippet.
- `_agentic_telemetry = make_feature_telemetry("agentic_search", urls_discovered=0, ...)` at
  `run_honest_sweep_r3.py:1604`; updated at `:2880-2882` (`fired`/`urls_discovered`/`firing_status`).
  ADD `urls_selectable` (post-structural-filter count).
- Conference detector to REUSE: `src/polaris_graph/retrieval/tier_classifier.py:789`
  `_detect_conference_abstract(title: str, url: str = "") -> bool` (keywords, numbered-abstract
  prefixes, day-letter IDs, `/Supplement_`, `/abstract/`). Import-safe? verify no cycle
  (tier_classifier ↔ live_retriever).
- Semantic filter: `src/polaris_graph/retrieval/prefetch_offtopic_filter.py:152`
  `filter_search_results(candidates, research_question, threshold=None) -> FilterResult`. Scores on
  `.snippet_text`; FAIL-OPEN on empty anchor / embedder error.
- **Step-3 application (THE landmine): `live_retriever.py:2438-2444`** —
  `if enable_prefetch_filter and candidates: filt = filter_search_results(candidates, ...)`.
  Runs on ALL candidates INCLUDING injected empty-snippet seeds. Empty snippet → ~0 similarity →
  REJECTED. So enabling prefetch on the seed_only agentic call WITHOUT seed-exclusion drops every
  agentic seed. MUST exclude seeds (split on `_SEED_SOURCE_LABELS` at `:2100`, filter non-seeds,
  re-prepend seeds — mirror `_rerank_and_reserve` at `:2131-2132`).
- Seed-split SET already exists: `_SEED_SOURCE_LABELS = {primary_trial_doi, agentic_seed,
  deepener_seed}` (live_retriever.py:2100, from FX-15a).

## Design (3 parts)
1. **`_is_low_content_host_or_page(url, title='')`** pure helper in live_retriever.py.
   REJECT: paths `/search`, `/browse`, `/conference`, `/annual-meeting`, `/issue/`; SERP query
   strings (`search-results`, `?...page=`); `_detect_conference_abstract(title, url)`.
   KEEP (precision — assert in tests): `aeaweb.org/articles?id=10.1257/...`,
   `pubs.aeaweb.org/doi/10.1257/...`, arxiv `/abs/...`. Conservative: when unsure, KEEP.
2. **Apply on agentic lane**: filter `_ag_urls` (drop low-content) before `run_live_retrieval`;
   add `urls_selectable` to `_agentic_telemetry`. Flag-gate `PG_AGENTIC_HOST_FILTER` (default-on
   in benchmark slate; reversible).
3. **Seed-safe Step-3**: split seeds out of `filter_search_results` (filter non-seeds only,
   re-prepend seeds), then pass `enable_prefetch_filter=True` on the agentic call.

## Smoke (offline)
- precision fixture for `_is_low_content_host_or_page` (reject/keep table; ZERO real article dropped).
- Step-3 seed-exclusion: empty-snippet seed candidate survives `enable_prefetch_filter=True`
  (monkeypatch `filter_search_results` or stub embedder; assert seed kept).
- agentic merge integration: mixed `_ag_urls` → nav/conf/SERP absent, `urls_selectable < urls_discovered`.

## §-1.1
On the held drb_72 `retrieval_trace.jsonl` (kept rows = the 41 aeaweb): classify each as
low-content (reject) vs real article (keep); assert the filter would drop ONLY the nav/conf/SERP
ones and KEEP the `articles?id=` / `pubs.aeaweb.org/doi/` ones.

## Faithfulness note
Dropping junk is quality-positive ONLY if precision is perfect (no real article dropped). The
structural filter must be conservative; the semantic-filter seed-exclusion must never drop a seed.
Flag-gate so it is reversible. No grounding/strict_verify/4-role change.

## Diff base for the gate: FX-15a verified tip `83e7ebfd` (or current branch HEAD).
