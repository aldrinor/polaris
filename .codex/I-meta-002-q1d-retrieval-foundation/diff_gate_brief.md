RULE NOW — emit the YAML verdict block FIRST. Read the patch at
`.codex/I-meta-002-q1d-retrieval-foundation/codex_diff.patch` (4 files, +142/-15). Do NOT explore beyond it.

HARD ITERATION CAP: 5. Iter 1 of 5. Front-load all findings; reserve P0/P1 for real execution risks.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex diff-gate (iter 1) — PR1 retrieval foundation (#943 cap + #951 rerank/reservation). Verify the diff implements the brief-gate iter-1 required-changes. NO SPEND.

The brief-gate (`.codex/I-meta-002-q1d-retrieval-foundation/brief.md`) returned REQUEST_CHANGES with 5
required-changes; this diff implements them. Verify each was honored AND no regression/leak introduced.

## Required-changes to verify in the diff
1. **Seed protection (P0):** rerank applies ONLY to non-seeds; seeds (`source == "primary_trial_doi"`,
   empty title/snippet) are split out and PREPENDED after ranking — never ranked/dropped.
   `_rerank_and_reserve` in `live_retriever.py`: `seeds = [c ... source == "primary_trial_doi"]`;
   `non_seeds = [...]`; returns `seeds + selected_non_seeds`. Confirm seeds can never be dropped.
2. **Lexical-first, no model load (§8.4):** scoring is `_lexical_relevance_score` via
   `_rerank_content_tokens` (regex + stopword set) — NO embedder, NO sentence-transformers/torch import,
   NO loader/getter. Confirm nothing in the ranking path can trigger a model load.
3. **Reservation algorithm:** group non-seeds by `query_origin`; sort each group by `(-score, index)`;
   Phase-1 reserve ≤1 per origin (origins ranked by best candidate score) bounded by capacity; Phase-2
   fill remaining by global `(-score, index)`. Confirm the long full-paragraph/anchor query is not
   starved AND no origin monopolizes.
4. **query_origin buckets:** assigned for anchor+amplified (`query_origin=q` on serper/s2 appends),
   domain-backend (`"domain_backend"` fallback), seeds (`"primary_trial_doi_seed"`), with `"_unlabeled"`
   fallback in the grouper. `SearchCandidate` gained `query_origin: str = ""` (additive, backward-compat).
5. **Cap raise + comment fix:** `run_honest_sweep_r3.py` defaults `8/8/20 → 12/12/40` (env-overridable),
   comment fixed from "per query" to "TOTAL after dedup". Cost still bounded by `PG_MAX_COST_PER_RUN`.

## Evidence (verified by Claude main-thread)
- New tests `tests/polaris_graph/test_live_retriever_rerank.py` (7) PASS: seed retained despite empty
  text + higher-scoring non-seeds; model loader NOT invoked (blocks sentence_transformers/torch import,
  still runs); relevance prefers on-topic; reservation no-monopoly (all 3 origins represented at cap=3);
  fail-open → arrival order with seeds preserved; cap respected + edge cases; lexical scorer edges.
- Regression PASS: test_prefetch_offtopic_filter (5), test_domain_backends_r6_gap2 (10),
  test_m_int_5_domain_router_integration (12), test_live_retriever_env_knobs (24),
  test_post_fetch_loop_timeout (5). SearchCandidate field is additive (positional construction unchanged).
- Diff +142/-15 net 127 (≤200). strict_verify / provenance_generator / D8 / evidence_selector tier logic
  / runtime lock UNTOUCHED — only WHICH candidates get fetched changes, not how they're verified.

## Rule on
1. Can a primary-trial DOI seed EVER be dropped by the rerank? (Must be NO.)
2. Any path where ranking triggers a model load / network call? (Must be NO.)
3. Does the reservation ever return MORE than `fetch_cap` non-seeds, or starve the anchor query?
4. Selected non-seeds are emitted in original arrival order (stable corpus) — any ordering bug vs the
   `selected_idx` set?
5. Fail-open: does the `except` truly preserve the prior behavior `candidates[:fetch_cap + n_seed]`?

APPROVE iff the 5 required-changes are correctly implemented, seeds are unconditionally preserved, no
model-load/network on the ranking path, strict_verify/D8 untouched, and it's test-proven.
