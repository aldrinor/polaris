# FX-15b §-1.1 audit — host-class junk filter + seed-safe semantic prefetch (I-ready-017 #1119)

**Standard:** §-1.1 precision audit of `_is_low_content_host_or_page` over the REAL held drb_72
`outputs/audits/I-ready-017/run_artifacts/retrieval_trace.jsonl` — every one of the 41 agentic
rows (the FX-15a-mislabeled `backend=='primary_trial_doi'` set) classified keep-vs-drop, then each
verdict checked against the actual URL.

## Result on the real artifact
- 41 agentic rows → filter **DROPS 13, KEEPS 28**.
- **Genuine false drops (a real primary article wrongly dropped): 0.**
- The one URL my loose audit heuristic flagged — `academic.oup.com/ooec/article/3/Supplement_1/i906/7708121`
  — is a **conference SUPPLEMENT abstract** (`/Supplement_1/`, page `i906`), correctly caught by the
  reused `tier_classifier._detect_conference_abstract` (`/supplement_` URL rule). It is NOT a full
  primary article; the tier classifier already treats supplement abstracts as low-tier, so dropping
  it pre-fetch is consistent (a CORRECT drop).

### DROPPED (13) — all genuine nav / SERP / conference / supplement (line-by-line)
- `/issues/381` (journal TOC), `/forum/232/...` (discussion), `/toc/jpe/2020/128/6`, `/toc/jpe/current`
  (table-of-contents listings)
- `/conference/2009/...`, `/conference/2019/...`, `/conference/2023/program/...`,
  `/conference/2025/program/...` (×2) (conference programs)
- `/journals/search-results?...per-page=21` (×2), `/search/index?jelcode=b1...page=504` (SERP listings)
- `oup.com/ooec/article/3/Supplement_1/i906/...` (conference supplement abstract)

### KEPT (28) — every real source preserved
Real journal articles (`aeaweb.org/articles?id=10.1257/...`, `pubs.aeaweb.org/doi/...`,
`journals.uchicago.edu/doi/...`, `academic.oup.com/qje/article/...`, `science.org/doi/...`,
`wiley.com/doi/...`) AND real working-paper PDFs (`nber.org/system/files/working_papers/w22252.pdf`,
`economics.mit.edu/sites/default/files/publications/...`, `oxfordmartin.ox.ac.uk/publications/the-future-of-employment`
= Frey-Osborne) AND real abstract pages (`ideas.repec.org/a/...`, `stlouisfed.org/publications/...`,
`itif.org/publications/...`). **Not one real article dropped.**

### Recall gap (deferred to downstream — not a precision issue)
3 atypical citation-stub / news pages survive the STRUCTURAL floor:
`aeaweb.org/news/cnn-...`, `scirp.org/reference/referencespapers?referenceid=...`,
`socqa.syr.edu/bibcite/reference/7202`. These are caught downstream by the tier classifier +
`is_content_starved` + (now seed-safe) semantic filter. `/news/` is deliberately NOT in the reject
set (a news URL CAN be a legitimate citation in some domains — precision over recall).

## The fix
1. **Structural filter** `_is_low_content_host_or_page(url, title='')` (live_retriever) — rejects
   `/search`, `/browse`, `/conference`, `/annual-meeting`, `/issues/`, `/forum/`, `/toc/`,
   `search-results`, `per-page=`, and `_detect_conference_abstract`. Precision-first; never a real
   article. Applied to `_ag_urls` on the agentic lane (`run_honest_sweep_r3.py`), flag-gated
   `PG_AGENTIC_HOST_FILTER` (default on); `urls_selectable` telemetry added.
2. **Seed-safe Step-3** — the semantic prefetch filter now EXCLUDES injected seeds
   (`_SEED_SOURCE_LABELS`) before `filter_search_results`, so enabling `enable_prefetch_filter=True`
   on the agentic lane can no longer drop the URL-only (empty-snippet) seeds as ~0-similarity
   off-topic. `enable_prefetch_filter=True` flipped on the agentic call (inert for the URL-only
   seed_only set; the structural filter is the real defense there).

## Offline smoke (proves the fix)
`pytest tests/polaris_graph/test_fx15b_host_filter_iready017.py` → 4 passed:
- structural reject of 12 nav/SERP/conference/TOC shapes;
- **precision gate**: 6 real articles (aeaweb/pubs/arxiv/nber/doi.org) — ZERO dropped;
- empty-URL kept;
- **seed-exclusion repro**: with `enable_prefetch_filter=True` + a reject-ALL embedder stub, the
  empty-snippet agentic seed STILL survives (excluded from the off-topic filter) and produces an
  evidence row — pre-fix it would have been dropped.
- Regression: FX-15a (6) + `test_live_retriever_rerank` (8) + `test_bug776_layer4_doi_seeds` (5) +
  `test_retrieval_trace` (7) + `test_plan_sufficiency_phase3` (26) all pass.

## Faithfulness check
Quality/precision fix. The structural floor drops ONLY nav/SERP/conference/supplement listing pages
(0 real articles dropped on the real artifact); the seed-exclusion PREVENTS a latent catastrophic
drop of the entire agentic seed lane. No grounding / strict_verify / 4-role-decision change.
Flag-gated + reversible.
