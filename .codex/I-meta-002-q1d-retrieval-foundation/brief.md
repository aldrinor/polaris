RULE NOW — emit the YAML verdict block FIRST. APPROVE this CONCRETE plan or REQUEST_CHANGES with specifics. Read AT MOST the cited code regions. NO SPEND / NO unconditional new model load.

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

# Codex brief-gate (iter 1) — PR1 retrieval foundation: raise fetch cap (#943) + fetch-time relevance rerank + per-sub-query reservation (#951 q1d-b). Codex's verified step-1. NO SPEND.

Pre-Q1 build, depth-first. Codex gap-verify (#950) p0: "step 1 = fetch-cap + fetch-time rerank/
per-subquery reservation together, not cap-alone; otherwise decomposition (PR2) is still truncated by
arrival order." This PR builds that base. The 5 golden Qs must out-depth frontier DR WITHOUT weakening
strict_verify or D8.

## GROUNDED FACTS (Codex-confirmed in #950 gap-verify; do not re-explore)
- `src/polaris_graph/retrieval/live_retriever.py`: candidates appended in query/source ARRIVAL order
  (Serper+S2 ~:1241-1271, domain backends ~:1276-1291); deduped by canonical URL (~:1217-1271); the union
  size is `total_pre_filter` (~:1307); then **truncated by arrival order**: `candidates =
  candidates[:fetch_cap + _n_seed_injected]` (~:1324). The prefetch embedding off-topic filter defaults
  OFF (`enable_prefetch_filter=False` ~:1173) and the sweep passes `False` (`run_honest_sweep_r3.py:1664`).
  `run_live_retrieval` seeds queries starting with `[research_question]` (~:1200).
- `scripts/run_honest_sweep_r3.py:1591-1593`: launch defaults `PG_SWEEP_MAX_SERPER=8`, `PG_SWEEP_MAX_S2=8`,
  `PG_SWEEP_FETCH_CAP=20`. The cap comment (~:1587) says "per query" — WRONG; the docstring (~:1185) "Hard
  cap on total URLs" is correct (a doc bug).
- `src/polaris_graph/retrieval/evidence_selector.py`: ranks only the ALREADY-fetched survivors by tier +
  lexical Jaccard (~:653-658,:751-756,:1089-1091) — not pre-fetch relevance.
- Invariant 9.1.6: `PG_MAX_COST_PER_RUN` is the hard budget ceiling; counts are NOT a quality signal (§-1.1).

## CONCRETE PROPOSAL (APPROVE or correct)
A. **Raise the cap, bounded (#943).** Defaults `PG_SWEEP_FETCH_CAP=20→40`, `PG_SWEEP_MAX_SERPER=8→12`,
   `PG_SWEEP_MAX_S2=8→12` (all env-overridable, unchanged mechanism). Fix the wrong "per query" comment to
   "total URLs fetched after dedup." The real cost ceiling remains `PG_MAX_COST_PER_RUN` (unchanged). Raise
   is additive: more candidates fetched, no behavior change to verification.
B. **Fetch-time relevance rerank BEFORE the `[:fetch_cap]` slice.** New pure helper in live_retriever (e.g.
   `_rank_candidates_by_relevance(candidates, question, query_origin, fetch_cap)`):
   1. Score each candidate by relevance of its `(title + snippet)` to the research question. PRIMARY:
      cosine on the ALREADY-LOADED pooled embedder IF one is present in this path (no new model load);
      FALLBACK (no embedder available — keep it no-model so §8.4 RAM discipline holds): a deterministic
      lexical relevance score (content-word overlap / BM25-lite) over title+snippet. Fail-open: on any
      error, preserve current arrival order (never raise).
   2. **Per-sub-query round-robin reservation:** tag each candidate with the query that surfaced it
      (`query_origin`), then fill the cap round-robin across sub-queries by descending relevance, so no
      single query (esp. the long full-paragraph query) monopolizes the cap and every sub-query gets ≥k
      slots if it has candidates. Dedup preserved.
   3. Return the top `fetch_cap` by this policy. This REPLACES the arrival-order `candidates[:fetch_cap]`.
C. **Tag query origin.** Where candidates are appended per query (~:1241-1291), record which query produced
   each candidate (a parallel list or a field) so (B.2) can reserve per sub-query. Minimal structural add.
D. **Tests (offline, socket blocked):** (1) arrival-order truncation no longer drops a high-relevance
   late-query candidate that a low-relevance early-query candidate displaced; (2) round-robin reservation
   gives each of N sub-queries ≥1 slot when each has candidates (no monopolization); (3) fail-open: a
   broken scorer falls back to arrival order without raising; (4) cap raise respected + env-overridable;
   (5) dedup still holds. Use fixture candidate lists; NO network.

## Constraints / frozen
- NO SPEND. NO new model download/load in the autonomous path (§8.4): the rerank MUST reuse an
  already-loaded embedder OR use the no-model lexical fallback — never trigger a sentence-transformer/CUDA
  load just for ranking. Confirm which embedder (if any) is already live in run_live_retrieval; if NONE,
  ship the lexical fallback as primary.
- Untouched: strict_verify / provenance_generator, the D8 gate, evidence_selector's tier logic, runtime
  lock (not promoted), the 5 PR-10 contracts. Verification semantics unchanged — this only changes WHICH
  candidates get fetched, not how they're verified.
- snake_case; explicit imports; no except:pass (fail-open here = explicit try/except that logs + returns
  arrival order); ≤200 LOC.

## The real risks to rule on
1. Is reusing an already-loaded embedder safe (no lazy load on first call)? If run_live_retrieval has NO
   live embedder, is the lexical fallback the right PRIMARY to honor §8.4 (no model load for ranking)?
2. Does per-sub-query reservation risk STARVING the high-value full-paragraph/anchor query? Propose the
   reservation policy (e.g. reserve ≥k per sub-query but fill the remainder by global relevance).
3. Any path where reranking could drop a source that a downstream gate (jurisdictional T3 floor,
   primary-trial seed injection `_n_seed_injected`) REQUIRES? Must preserve seed-injected + floor sources.
4. Cap raise 20→40: latency/cost within `PG_MAX_COST_PER_RUN`? Confirm the cap is bounded by budget.

APPROVE iff this lands the rerank+reservation+cap base no-spend, no-model-load (or lexical-fallback),
preserves seed/floor sources, leaves strict_verify/D8 untouched, and is test-proven.

---

## REVISED SPEC — Codex brief-gate iter-1 REQUEST_CHANGES adopted (binding for the build)
1. **Seed protection (P0):** apply rerank ONLY to non-seed candidates. `seed_candidates =
   candidates[:_n_seed_injected]`; rank/select non-seeds to `fetch_cap`; final =
   `seed_candidates + selected_non_seeds`. Seeds (empty title/snippet primary-trial DOIs) are NEVER
   ranked/dropped — the additive seed lane is preserved exactly as today.
2. **Lexical-first by default:** no already-instantiated embedder is present in `run_live_retrieval`
   (the only embedding path is the DISABLED prefetch filter). Use a deterministic lexical relevance
   score (content-word overlap, stable) as PRIMARY. Use cosine ONLY if an already-materialized embedder
   object is directly passed/present — NEVER call a loader/getter/import that can init
   sentence-transformers/CUDA (§8.4).
3. **Reservation algorithm (exact):** group non-seeds by `query_origin`; sort each group by
   `(-score, original_index)`; take at most ONE reserved item per origin while capacity remains; then
   fill all remaining slots by global `(-score, original_index)`. If #origins > cap, pick reserved
   origins by best candidate score. (Anchor/full-paragraph query is not starved.)
4. **query_origin buckets:** assign for the anchor query, each amplified query, AND domain-backend
   candidates, with a stable fallback bucket for any candidate lacking an origin.
5. **Tests (offline, socket blocked):** (a) a seed with empty title/snippet is RETAINED despite many
   higher-scoring non-seed candidates; (b) the model loader is NOT invoked (assert no
   sentence-transformer/embedder init); (c) reservation does not let one origin monopolize the cap;
   (d) fail-open returns arrival order for non-seeds while preserving seeds; (e) cap raise respected +
   env-overridable; (f) dedup holds. (g) sweep comment fixed to "total URLs after dedup".
