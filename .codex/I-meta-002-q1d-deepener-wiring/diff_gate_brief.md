RULE NOW — emit the YAML verdict block FIRST. Read the patch at `.codex/I-meta-002-q1d-deepener-wiring/codex_diff.patch` (5 files: 3 production + 2 test files now included inline). Do NOT explore beyond it. TOP SCRUTINY (feeds strict_verify). NOT unconditional no-spend (default OFF; when ON+triggered it spends, bounded).

RE-GATE on the FINAL ship patch. Prior iters (1-4) APPROVE'd the production code. Since then ONE additive change: the brief-gate required a regression test pinning the REAL 2-arg `deepen_evidence(client, state)` call shape — `test_run_deepener_sync_real_path_uses_2arg_signature_and_closes_client` (patches the real `evidence_deepener.deepen_evidence` + `OpenRouterClient`, calls `run_deepener_sync(state)` with no injected `deepen_fn`, asserts client constructed + passed arg1, state arg2, `client.close()` awaited). NO production-code change since iter-4 APPROVE. Confirm the patch still APPROVEs as the final shippable diff.

HARD ITERATION CAP: 5. Iter 5 of 5 (final). Front-load all findings; reserve P0/P1 for real execution risks.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex diff-gate (iter 1) — PR5 deepener wiring (#942-deepener). Verify the diff implements the brief-gate iter-1 required-changes (Option A confirmed).

## Iter-1 required-changes — verify each in the diff
1. **Exact Stop-RAG trigger:** `deepener_sweep_adapter.should_trigger_deepener` returns True iff
   `flag_on AND has_s2_key AND has_seed_evidence AND (adequacy_decision != "proceed" OR total_uncovered
   > 0)` — does NOT fire on a comfortably-adequate corpus (proceed + 0 uncovered). Wired with
   `PG_SWEEP_EVIDENCE_DEEPENER` default "0", `SEMANTIC_SCHOLAR_API_KEY` presence, `len(evidence_rows)>0`,
   and the post-R6 `adequacy.decision`/`completeness.total_uncovered` (adequacy values are Literal
   "proceed"/"expand"/"abort").
2. **Event-loop guard:** `run_deepener_sync` checks `asyncio.get_running_loop()`; no loop → `asyncio.run`;
   loop running → runs `asyncio.run(fn)` in an ISOLATED `ThreadPoolExecutor` thread (never raises
   RuntimeError mid-sweep). `deepen_fn` is injectable for offline fakes.
3. **Option A (seed_urls chokepoint):** the sweep feeds `discovered_urls(...)` into
   `run_live_retrieval(max_serper=0, max_s2=0, fetch_cap=min(len(urls), url_cap), seed_urls=urls)` — every
   deepened paper is fetched + `classify_source_tier` + `is_content_starved` + `_build_provenance_quote`
   through the SAME chokepoint; thin/abstract-only → dropped (no laundering). NO new evidence-row build.
4. **Merge = R-6 pattern:** dedup classified_sources by URL; renumber evidence_ids monotonically
   `ev_{base+i:03d}`; recompute `compute_tier_distribution` + `check_completeness` + `assess_corpus_adequacy`
   over the merged corpus. Logs discovered/seeded/accepted counts + deepener stats. Fail-open (any error
   leaves the post-R6 corpus untouched).

## Evidence (verified by Claude main-thread)
- 20 tests PASS: trigger predicate (flag/key/seed gates + borderline-only — proceed+0 → no, proceed+
  uncovered → yes, expand/abort → yes); build_deepener_state (drops blank-url rows); discovered_urls
  (dedup+cap); run_deepener_sync (no-loop path + inside-running-loop does NOT raise, isolated thread);
  no-laundering (is_content_starved drops thin deepened content). Plus the existing seed_urls chokepoint
  test (test_bug776_layer4_doi_seeds) + is_content_starved tests (test_r5_fix_d_content_starved) — the
  EXACT gate this fix reuses. `verify_lock --consistency` OK.
- LOC: +282/-2 net 280 — production executable ~100 (adapter ~50 + wiring ~50); rest is docstrings +
  ~110 test lines. Same shape as PR1 (256) / PR2 (270) which APPROVE'd; the cap's intent (bounded LOGIC
  blast radius) holds — confirm acceptable or direct a split (note: the brief covered module+wiring+tests
  as one atomic unit).
- Frozen/untouched: strict_verify / provenance_generator / D8 / runtime lock / the 5 PR-10 contracts / the
  verified core. The deepener feeds INPUT evidence ONLY through the existing chokepoint.

## Rule on
1. NO laundering: can a deepened paper EVER become an evidence row without passing is_content_starved +
   classify_source_tier over FETCHED content? (Must be NO — it only enters via seed_urls.)
2. Trigger correctness: does it ever fire on a comfortably-adequate corpus (proceed + 0 uncovered)? Ever
   stay always-on? (Must be NO / NO.)
3. Event-loop: any RuntimeError / deadlock path from `run_deepener_sync` in the sync sweep OR an async caller?
4. Spend bound: default OFF; when ON+triggered, is worst-case bounded (deepener caps+720s timeout, URL cap,
   `fetch_cap=min(len(urls),cap)`, `max_serper=0/max_s2=0`, PG_MAX_COST_PER_RUN still binds)? Note: the
   deepener pass still seeds the anchor `[research_question]` to serper/s2 with num=0 — is that a real cost?
5. Fail-open: a deepener/fetch error leaves the post-R6 corpus + adequacy untouched (try/except)?

APPROVE iff the trigger is exact + borderline-only, the event-loop guard never raises mid-sweep, every
deepened paper passes the existing chokepoint (no laundering), spend is bounded + default-OFF, and it's
test-proven offline.
