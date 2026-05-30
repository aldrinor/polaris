# Claude architect audit — PR1 retrieval foundation (#943 cap + #951 rerank/reservation)

## What this fixes (pre-Q1 build step 1, Codex's verified order)
The launch sweep truncated candidates by ARRIVAL ORDER at a 20-source cap, and the prefetch relevance
filter was disabled — so the breadth of ~30 amplified queries was illusory (early queries saturated the
cap; later sub-queries' best hits were cut before fetch). This is Codex's required step-1 base: without
it, the query-decomposition fix (PR2) would still be truncated by arrival order.

## Design (both Codex gates APPROVE)
- **Cap raise (#943):** `PG_SWEEP_MAX_SERPER/MAX_S2` 8→12, `PG_SWEEP_FETCH_CAP` 20→40 (env-overridable,
  bounded by `PG_MAX_COST_PER_RUN`); fixed the wrong "per query" comment to "TOTAL after dedup".
- **Fetch-time rerank + reservation (#951):** new `_rerank_and_reserve` replaces the arrival-order slice.
  Pure-lexical relevance (`_lexical_relevance_score` via regex/stopword content-word overlap) — NO
  embedder, NO sentence-transformers/torch, NO loader/network on the ranking path (§8.4). Per-sub-query
  reservation: group non-seeds by `query_origin`, reserve ≤1 per origin (origins by best score), then fill
  by global score — the long full-paragraph query cannot monopolize the cap and no sub-query starves.
- **Seed protection (Codex brief-gate iter-1 P0):** primary-trial DOI seeds (empty title/snippet) are
  split out by `source == "primary_trial_doi"` and prepended AFTER ranking — never scored, never dropped,
  exactly additive as the I-bug-776 seed lane intends.
- **Fail-open:** any ranking error falls back to the prior `candidates[:fetch_cap + n_seed_injected]`.
- `SearchCandidate` gained `query_origin: str = ""` (additive, backward-compatible).

## Verification (offline, no spend)
- 7 new tests (`tests/polaris_graph/test_live_retriever_rerank.py`) PASS: seed retained despite empty text
  + higher-scoring non-seeds; model loader NOT invoked (blocks sentence_transformers/torch import, still
  runs); relevance prefers on-topic; reservation no-monopoly; fail-open preserves seeds; cap + edges.
- Regression PASS: prefetch_offtopic_filter (5), domain_backends_r6_gap2 (10), domain router (12),
  live_retriever_env_knobs (24), post_fetch_loop_timeout (5).
- Diff +142/-15 net 127 (≤200). strict_verify / provenance_generator / D8 / evidence_selector tier logic /
  runtime lock UNTOUCHED — this changes WHICH candidates are fetched, not how they're verified.

## Clinical-safety note
No change to the verification chokepoint. Seeds (primary-trial evidence the clinical questions need) are
unconditionally preserved. Lexical-only ranking is deterministic and fail-open.
