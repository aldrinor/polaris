HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Output schema (return EXACTLY this, no prose verdict):
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

---

# Brief — I-cap-002 feature 3/4 (#1060): agentic search as URL-DISCOVERY in the benchmark path

## CHANGELOG vs iter 1 (your REQUEST_CHANGES, all addressed)
- **P1 (budget envelope not airtight w.r.t. content-reading/page-summary calls) — FIXED.** The benchmark
  agentic call now FORCES content reading OFF by toggling the import-cached module constant
  `searcher.PG_AGENTIC_CONTENT_READING_ENABLED = False` for the call (restored in `finally`, exactly the
  STORM `PG_STORM_ENABLED` toggle pattern). Confirmed: `searcher.py` imports it as a module constant (L73)
  and the page-summary block reads it as the module global (`if PG_AGENTIC_CONTENT_READING_ENABLED:` L1766).
  With it OFF, the ONLY LLM work in the loop is `_agentic_round_analysis` (≤ `PG_AGENTIC_MAX_ROUNDS` calls),
  so the envelope `PG_AGENTIC_MAX_ROUNDS × PG_AGENTIC_PER_ROUND_COST_USD` covers ALL bounded LLM work — the
  cap is airtight. Belt-and-suspenders: the loop runs in an isolated `copy_context()` and its real spend is
  discarded from the parent total (the envelope IS the parent's accounting), so even an unexpected call
  cannot breach `PG_MAX_COST_PER_RUN`. See §4.3 step 2.
- **P2 (discard the agentic result right after harvest) — FIXED.** Only `_urls = harvest_agentic_urls(...)`
  survives; the full result dict is `del`'d immediately so no notebook/summary field exists in scope near
  the merge. See §4.3 step 3.
- **P2 (merge dedup/renumber tests) — FIXED.** The dedup-by-URL + global evidence-id renumber core is
  extracted into a PURE helper `merge_seed_url_evidence(...)` in the harvester module and unit-tested for
  duplicate-URL rejection + id-renumber + no-inflation. See §4.2 + §8.

## 0. What this gate reviews
BRIEF gate (design correctness). Code does not exist yet. The single most important thing to red-team here
is the **faithfulness contract** (§4.1): the agentic loop must only DISCOVER URLs; agent-written summaries
must NEVER become evidence. Confirm the design cannot launder a summary into a `direct_quote`.

## 1. Context
Operator: "B then A". Wire the four Tier-B capabilities into the **benchmark (Pipeline A)**, then run the
1000-URL beat-both. POLARIS has TWO pipelines: A = benchmark (`run_gate_b` →
`run_honest_sweep_r3.run_one_query` → `live_retriever` → 4-role seam); B = web-UI LangGraph (`graph.py` +
`agents/`). The agentic loop (`agents/searcher.execute_agentic_search`) is consumed only by Pipeline B; it is
a NO-OP for the benchmark. Feature 1/4 STORM (PR #1061) and feature 2/4 depth-gate (PR #1062) are DONE
(Codex-approved). This is **feature 3/4 — the largest, highest-risk one**.

## 2. The capability today (Pipeline B only) + the faithfulness hazard
`execute_agentic_search(state, client)` (searcher.py L1591) runs a multi-round seed→search→reason loop:
each round generates follow-up queries from prior results, optionally READS page content into a
`research_notebook` of LLM **summaries** (`PG_AGENTIC_CONTENT_READING_ENABLED`,
`PG_AGENTIC_SUMMARY_MAX_TOKENS`), and converges on saturation/budget. It returns (L1885):
```
{ "web_results": [...], "academic_results": [...], "agentic_url_accumulator": [<=500 deduped urls],
  "agentic_research_notebook": [<summaries>], "agentic_search_rounds", "agentic_knowledge_gaps", ... }
```
**THE HAZARD:** `agentic_research_notebook` is LLM-written page summaries. POLARIS's core invariant is
verbatim-span faithfulness — every delivered sentence cites a `[#ev:id:start-end]` span that strict_verify
checks against fetched source text. If a notebook summary were turned into an evidence row's `direct_quote`,
it would be a model paraphrase masquerading as a source span — a fabrication that defeats the whole product.
So the benchmark wiring uses the agentic loop for **URL DISCOVERY ONLY**.

## 3. Goal of feature 3/4
Behind a default-OFF flag (Gate-B activates it), run the agentic loop to DISCOVER additional high-quality
URLs, then fetch those URLs **verbatim** through the SAME `run_live_retrieval(seed_urls=…, seed_only=True)`
chokepoint that the rest of the corpus goes through — so every discovered source earns its tier only from
fetched content and is strict_verify'd + 4-role-checked identically. The agentic notebook/summaries are
discarded. This directly serves the "search up to 1000 high-quality URLs" depth target by widening
discovery beyond the static Serper/S2 fan-out, without touching faithfulness.

## 4. Design (what the diff will implement)

### 4.1 Faithfulness contract (the core invariant — please verify this is airtight)
- The ONLY thing consumed from the agentic result is **URLs** (`agentic_url_accumulator`, plus the `url`
  field of `web_results`/`academic_results` as a fallback union). `agentic_research_notebook`,
  `agentic_knowledge_gaps`, and every summary/snippet field are IGNORED — never read, never written to any
  evidence row.
- Discovered URLs are fetched via `run_live_retrieval(seed_urls=urls, seed_only=True, …)` — the SAME
  fetch/tier/strict_verify path the deepener already uses (L2406-2468). A thin/abstract-only/denied page is
  DROPPED fail-closed exactly as today; no laundering.
- The merged evidence rows are the verbatim-fetched `direct_quote`s produced by `live_retriever`, identical
  in kind to the primary-retrieval rows. The 4-role seam + strict_verify run on them unchanged.

### 4.2 New harvester + merge module
`src/polaris_graph/retrieval/agentic_url_harvester.py` (stdlib + the existing `canonical_source_url`
helper; no network, no LLM, no new dependency):
```python
def harvest_agentic_urls(agentic_result: dict | None, cap: int = 200) -> list[str]:
    """Return ONLY discovered URLs from an execute_agentic_search() result — order-preserving,
    deduped (canonical_source_url), capped. Prefers 'agentic_url_accumulator'; falls back to the 'url'
    field of web_results+academic_results. NEVER reads agentic_research_notebook / summaries / snippets.
    cap<=0 -> []. Robust to missing keys."""

def merge_seed_url_evidence(staged_sources, staged_rows, new_sources, new_rows):
    """PURE merge core (P2.2): dedup new_sources by URL against staged_sources, append only accepted
    non-duplicate sources, and append only new_rows whose source URL was an ACCEPTED non-duplicate
    source — with a GLOBAL ev_### renumber from len(staged_rows) so ids never collide/inflate. Returns
    (merged_sources, merged_rows, accepted_source_count, accepted_row_count). No I/O. This is the
    deepener's accepted-source/renumber logic factored out so it is unit-testable (and a future PR can
    point the deepener at it too — noted as follow-up, not done here to keep blast radius small)."""
```
Both unit-tested. The benchmark block calls `merge_seed_url_evidence` for the source/row staging, then
recomputes `compute_tier_distribution` + completeness/adequacy over the staged corpus and commits on success
(the recompute stays inline because it closes over run-local objects).

### 4.3 Wire into `run_one_query` — mirror the deepener (the proven pattern)
Placed AFTER the primary retrieval (L2129) and AFTER the existing deepener block (so it is an additional,
independent URL source), behind `PG_AGENTIC_SEARCH_IN_BENCHMARK` (default OFF), reusing the **exact
STORM-style budget + isolation pattern** I already shipped (L2003-2070) and the **exact deepener atomic-merge
pattern** (L2445-2500+):
1. Build a minimal `ResearchState` the loop needs: `original_query`, `region`, `sub_queries`
   (the amplified/effective queries), `web_results: []`, `academic_results: []`.
2. **Force content reading OFF + airtight budget (P1 fix):** set `searcher.PG_AGENTIC_CONTENT_READING_ENABLED
   = False` for the call (toggle the import-cached module constant, restore the prior value in `finally`,
   STORM pattern) — the benchmark discards the notebook anyway, so paying for page summaries is pure waste,
   AND it removes the only un-enveloped LLM term. The remaining LLM work is `_agentic_round_analysis`
   (≤ `PG_AGENTIC_MAX_ROUNDS` calls), so BOOK a CONSERVATIVE envelope
   (`PG_AGENTIC_MAX_ROUNDS × PG_AGENTIC_PER_ROUND_COST_USD`, env-tunable) into `_RUN_COST_CTX` and ENFORCE
   the cap (`check_run_budget(0)`) BEFORE running; construct the client AFTER the precheck; run the loop in
   an isolated `copy_context()` task (real spend discarded from the parent — the envelope IS the parent's
   accounting); close the client in `finally`. Over-books, never under-enforces (LAW VI).
3. `_urls = harvest_agentic_urls(result, cap=PG_AGENTIC_BENCHMARK_URL_CAP)`; then `del result` immediately so
   no notebook/summary field is in scope near the merge (P2.1). Only `_urls` (a `list[str]`) survives.
4. If `_urls`: `agentic_retrieval = run_live_retrieval(research_question=q["question"], amplified_queries=[],
   protocol=protocol, fetch_cap=min(len(_urls), cap), enable_openalex_enrich=True,
   enable_prefetch_filter=False, seed_urls=_urls, seed_only=True)`.
5. **ATOMIC merge mirroring the deepener, via the pure helper:** call `merge_seed_url_evidence(...)` (§4.2)
   to stage deduped sources + renumbered rows, recompute `compute_tier_distribution` + completeness/adequacy
   over the staged corpus, and COMMIT to `retrieval`/`evidence_for_gen` only after every recompute succeeds.
   Any error → fail-open, post-primary corpus untouched.
6. Broad `except` logs `[agentic] … failed — proceeding without agentic URLs` and continues.

### 4.4 Gate-B activation (mirrors STORM/quantified/V30)
`run_gate_b_query`: `os.environ.setdefault("PG_AGENTIC_SEARCH_IN_BENCHMARK", "1")` so the paid benchmark
runs agentic discovery; `setdefault` keeps the operator override (LAW VI).

### 4.5 Invariants the diff MUST hold
1. **URL-discovery only** — no summary/notebook/snippet ever becomes an evidence row or `direct_quote`; the
   result dict is discarded right after URL harvest (only a `list[str]` survives).
2. **Same verify chokepoint** — discovered URLs go through `run_live_retrieval(seed_only=True)` +
   strict_verify + 4-role, identical to the deepener; thin/denied pages dropped fail-closed.
3. **Budget cap airtight** — content reading forced OFF (only `_agentic_round_analysis` LLM calls remain),
   conservative envelope booked + enforced BEFORE the loop, isolated context discards real spend; agentic
   LLM spend can never breach `PG_MAX_COST_PER_RUN`.
4. **Flag default OFF → byte-unchanged** legacy honest-sweep; Gate-B turns it ON.
5. **Fail-open** — any agentic/fetch/merge error leaves the primary corpus untouched; the run completes.
6. **Atomic merge** — pure-helper staging + recompute-then-commit, so a partial merge can't corrupt the
   corpus (deepener Codex-approved pattern).
7. **Client + flag lifecycle** — client built after the budget precheck, closed in `finally`;
   `PG_AGENTIC_CONTENT_READING_ENABLED` restored in `finally`.

## 5. Files I have ALSO checked
- `agents/searcher.py:1591` `execute_agentic_search` — return shape confirmed (L1885): `web_results`,
  `academic_results`, `agentic_url_accumulator` (clean deduped urls), `agentic_research_notebook`
  (summaries — IGNORED). Reads `state["original_query"|"region"|"sub_queries"]`.
- `retrieval/live_retriever.py:2158` `run_live_retrieval(..., seed_urls=…, seed_only=…)` — the verbatim
  seed-fetch path the deepener uses.
- `run_honest_sweep_r3.py` deepener L2406-2468 (URL-discovery → seed_only fetch → atomic staged merge →
  fail-open) is the merge template; gap-search L3139-3180 is the query-merge variant (not used here).
- STORM block L2003-2070 — the budget-envelope + isolated-context + fail-open + client-close template I reuse.
- `agents/planner.py` `PG_AGENTIC_SEED_QUERIES`; `state.py` agentic flags (MAX_ROUNDS/MAX_QUERIES/
  MAX_TIME_SECONDS/…) already exist and bound the loop internally.

## 6. Resolved design decisions (iter-1 open questions, now closed)
- **Merge reuse:** the dedup-by-URL + evidence-id-renumber CORE is now a pure tested helper
  `merge_seed_url_evidence` (shared-ready); the completeness/adequacy recompute stays inline (it closes over
  run-local objects). Deepener is NOT touched in this PR (a follow-up can repoint it). Low blast radius.
- **Placement:** AFTER the deepener — an independent additional URL source. (The deepener is borderline-gated
  and S2-only; agentic is a broader web/academic discoverer; keeping them separate fetches is clearer and
  each fails open independently.)
- **Content reading + budget:** RESOLVED — content reading is FORCED OFF for the benchmark agentic call, so
  the envelope `PG_AGENTIC_MAX_ROUNDS × PG_AGENTIC_PER_ROUND_COST_USD` covers all remaining LLM work; the cap
  is airtight (§4.3 step 2). No remaining open questions.

## 7. Acceptance (GREEN)
- New `agentic_url_harvester.py` (URLs-only, never touches notebook) + unit tests.
- `run_one_query` agentic block: flag-gated default OFF, budget-enveloped, isolated-context, fetch via
  `seed_only=True`, atomic merge mirroring the deepener, fail-open. Flag OFF → manifest/corpus byte-unchanged.
- `run_gate_b_query` activates `PG_AGENTIC_SEARCH_IN_BENCHMARK`; activation test asserts it == "1".
- No summary/notebook content can become evidence (test the harvester ignores notebook).
- ≤ ~200 LOC of net production change (mirror-merge may push this; flag if so).

## 8. Smoke plan (offline)
1. `pytest` the harvester unit tests: `harvest_agentic_urls` (URLs-only; notebook IGNORED even when present;
   cap; canonical dedup; missing-keys safe) + `merge_seed_url_evidence` (duplicate-URL rejection; only
   accepted-source rows appended; global ev_### renumber from the staged base; no row inflation).
2. Extend + run the benchmark-stack activation test (asserts `PG_AGENTIC_SEARCH_IN_BENCHMARK` == "1").
3. `py_compile` the touched files; import-smoke `searcher` + the harvester.
4. (Live agentic discovery needs network + spend — that is the Tier-A VM run, not this offline gate.)
