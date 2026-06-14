# I-arch-004 — COMBINED dual-sourced chokepoint ledger (Claude static forensic × 9 Codex sessions)

**Status:** dual-sourced and converged. Claude's 74-finding static forensic (`chokepoint_ledger.md`) cross-checked by 9 independent Codex sessions (g1–g5 = targeted verification of Claude's claims; h1–h4 = blank-slate hunters). A 10th stream — the `drb72-deadrun-forensic` Workflow (run wf_91694fcf-778) — audits the **actual run data** (1622 llm_io captures + traces) and its data-visible findings will be folded into TIER-D below when it returns.

**Convergence headline:** of Claude's P0/P1 set, Codex **refuted 0** and **confirmed all**, correcting a few rationales (see notes). Codex surfaced ~20 genuinely NEW chokepoints invisible to the static framing. The dead run (`drb_72_ai_labor`, 3h20m, $6.74/$25, `error_unexpected`) is fully explained: it sailed through retrieval (740 src, 1428s) → weight (803 accepted) → consolidate (656→collapsed=0) → select (649/649, dropped 0) and **died composing the V30 narrative section** — the 600s smoke wall-clock killed the DeepSeek `generate()` mid-stream, twice, and `gather` without `return_exceptions` discarded all 3h20m.

Source tags: `CLD`=Claude static; `g1..g5`=Codex verify; `h1..h4`=Codex hunt. Multiple tags = independently corroborated.

---

## TIER A — P0 RUN-KILLERS (must land before ANY resume run)

### A1. Section gathers lack `return_exceptions=True` → one slow section kills the whole run
- **Where:** `multi_section_generator.py:5509` (contract), `:5550` (legacy), `:6432` (M-50 subsections)
- **Sources:** CLD + g1 + g5 + h1 + h2 + h3 + h4 (**unanimous, 7/7**)
- **Death proof:** `run_log.txt` traceback — `_run_section_with_wallclock:93` TimeoutError → out of `gather` at `:5509` → broad except → `error_unexpected`. Cost $6.74, 3h20m discarded.
- **g5 nuance (important):** `asyncio.gather` does NOT auto-cancel siblings on first exception — they orphan and keep running. So the fix must both (a) `return_exceptions=True` + gap-stub the failed section, AND (b) cleanly handle/await orphaned siblings.
- **Fix:** `gather(return_exceptions=True)`; map exceptions → gap-stub `SectionResult` (stub path ~321-347); **keep the `CredibilityPassError` fail-loud carve-out (:5856)** so faithfulness failures still abort. Continue to the faithfulness gates on the completed sections only.
- **env:** `n/a` (structural) — but pair with A2.

### A2. Section timeout + token budget sized off STALE 16384, not the real 64000
- **Where:** `run_honest_sweep_r3.py:6132` (runner default `PG_SECTION_MAX_TOKENS=16384` SHADOWS module `:220` default 64000); `openrouter_client.py:801` (`PG_GENERATOR_LLM_TIMEOUT_SECONDS=1800`); `multi_section_generator.py:68` (`PG_SECTION_WALLCLOCK_SECONDS`)
- **Sources:** g2 (novel) + g5 (novel) + h1 (novel) for the 16384 shadow — **this is the fix my I-arch-003 pass MISSED** (I set the module default but the runner default shadows it). CLD + g1 + g5 + h4 for the timeout.
- **Fix:** runner default → 64000 (or import the module constant); recompute `PG_SECTION_WALLCLOCK_SECONDS` and `PG_GENERATOR_LLM_TIMEOUT_SECONDS` off the REAL 64000-token budget at slow-band throughput (≈11000s wall / ≈6500s LLM, see `chokepoint_ledger.md §2`); add a **Gate-B preflight that FAILS LOUD** if any timeout/token knob resolves below the calculated floor (kills smoke-value inheritance forever).
- **env:** `PG_SECTION_MAX_TOKENS`, `PG_SECTION_WALLCLOCK_SECONDS`, `PG_GENERATOR_LLM_TIMEOUT_SECONDS`

### A3. No checkpoints + log opened mode `'w'` on a deterministic path → re-run overwrites prior artifacts
- **Where:** `run_honest_sweep_r3.py:2535/2683` (deterministic dir + `'w'` log), `:8837` (no resume), the 3 cancel-probe sites `:2817,5909,7106`
- **Sources:** CLD + g5 + h1 + h3 + h4 (h4 novel: the `'w'`-mode overwrite is a silent data-loss hazard)
- **Fix:** atomic DATA checkpoints — `corpus_snapshot` after retrieval (highest value; retrieval is 1428s), per-section + composed snapshots; `checkpoint.json` stage-pointer + resume flag; temp-file+atomic-replace for final artifacts. **HARD INVARIANT: checkpoints carry DATA, never VERDICTS — always re-run strict_verify/NLI/4-role/D8 on reload (no faithfulness bypass).**
- **env:** `PG_CHECKPOINT_ENABLED`, `PG_RESUME_RUN_DIR`

---

## TIER B — P1 FAITHFULNESS / CORRECTNESS (must land before beat-both; clinical-safety-critical)

### B1. Side-judges free-route on a RETIRED `evaluator` role key → unpinned GLM providers re-admitted into the faithfulness gates
- **Where:** `entailment_judge.py`, `semantic_conflict_detector.py`, `credibility_judge_caller.py`, `pathB_runner.py` — all call `get_role_provider('evaluator')`; the 4-role pin set is `generator/mirror/sentinel/judge`, so it returns **None** → no provider order, no ignore list, no `allow_fallbacks:false`.
- **Sources:** g3 (**novel P1, the single biggest find**)
- **Why lethal:** re-admits excluded/flaky GLM providers into strict_verify/NLI/conflict/credibility; judge_error fail-closed in strict_verify can then collapse verified-sentence coverage.
- **Fix:** map side-judge provider routing to **mirror** (GLM-5.1) with `allow_fallbacks:false`, `require_parameters:true`; or add an explicit `evaluator→mirror` alias.

### B2. Fail-open faithfulness holes Gate-B never closes
- **Where / Sources (h3 cluster, novel):**
  - `run_honest_sweep_r3.py:638` — `PG_BENCHMARK_STRICT_GATES` default-OFF and Gate-B doesn't set it → V30 contract faults fall back to legacy, success markable without completed D8, forced quantified can no-op silently.
  - `run_honest_sweep_r3.py:8271` / `nli_benchmark_annotator.py:147` (h1) — benchmark NLI is **advisory / fail-open** despite force-enable.
  - `semantic_conflict_detector.py:478` — judge error returns **neutral/0.0** (a real contradiction silently erased).
  - `run_honest_sweep_r3.py:7126` — qualitative conflict records never reach the evaluator PT08 contradiction gate (a high/medium clinical disagreement can be invisible).
  - `entailment_judge.py:180` — side-judge model from `PG_ENTAILMENT_MODEL` not forced to locked mirror.
- **Fix:** Gate-B slate sets `PG_BENCHMARK_STRICT_GATES=1`, binding NLI (`nli_status=ok` required when eligible sentences exist), fail-closed conflict above a tiny judge-error threshold, route qualitative conflicts into the evaluator gate, force `PG_ENTAILMENT_MODEL=z-ai/glm-5.1`; **preflight all of these as required.**

### B3. Verified-sentence count computed BEFORE citation-resolver drops → telemetry overstates faithfulness
- **Where:** `provenance_generator.py:2668-2700/2694`, `multi_section_generator.py:2915-2959` — `SectionResult.sentences_verified` = `report.total_kept` set before the resolver silently skips short/degenerate kept sentences.
- **Sources:** g4 + h3 (corroborated)
- **Fix:** return resolver drop counts/reasons; compute `sentences_verified`/`is_gap_stub` from the POST-resolve rendered sentences.

### B4. `reason()`/`generate_structured()` swap a generic 900/600s timeout in before the generator timeout can apply
- **Where:** `openrouter_client.py:2434,2541,3157,3362`
- **Sources:** g1 (novel P1)
- **Why:** DeepSeek-V4-Pro structured/reason calls without explicit timeout get capped by `PG_LLM_LONG/TIMEOUT` (live .env 900/600), far below the ~6500s generator budget.
- **Fix:** pass `timeout=None` through unchanged like `generate()`, OR select `GENERATOR_TIMEOUT_SECONDS` for `_REASONING_FIRST_MODELS` inside both helpers; add regression tests.

### B5. Force-on STORM / deepener timeouts strangle big reasoning calls
- **Where:** `storm_interviews.py:1344` (300s interview), `evidence_deepener.py:143-231` (120/240/720s)
- **Sources:** g1 (novel P1)
- **Fix:** size from generator timeout × rounds × per-interview call count; split LLM vs HTTP deepener timeouts; add to Gate-B slate + preflight floors.

### B6. Distill MAP/REDUCE prompts never receive the research_question
- **Where:** `evidence_distiller.py:207-377`, `multi_section_generator.py:2716-2746` (Gate-B force-enables `PG_SECTION_DISTILL`)
- **Sources:** g4 (novel P1)
- **Why:** the paid distill path decides on-topic from generic section_title/focus only → scoped population/comparator/jurisdiction constraints can be missed/over-included before strict_verify (which only sees local sentence faithfulness).
- **Fix:** thread `research_question` + mapped sub-query/facet text into `distill_section_evidence`/`_render_map_user`/`render_reduce_user`. **strict_verify unchanged.**

### B7. `PG_LIVE_MAX_EV_TO_GEN=20` silently feeds only 20 evidence rows into generation
- **Where:** `run_honest_sweep_r3.py:4758,4875`
- **Sources:** g5 (novel P1). *Nuance: g5 confirms Gate-B applies a full-capability floor, so this bites direct/bypass callers — but it's a real silent throttle and a fail-loud candidate.*
- **Fix:** raise default to the full extracted-corpus floor, or fail startup if below full-capability without an explicit downgrade token.

### B8. 4-role seam fixed 7200s outer timeout independent of claim count
- **Where:** `run_honest_sweep_r3.py:7551`
- **Sources:** h1 (novel P1)
- **Fix:** size timeout from claim count × workers × role-call p95, or replace with a progress-stall watchdog (`PG_FOUR_ROLE_STALL_SECONDS`).

---

## TIER C — P1 THROUGHPUT (why the run took 3h20m; reduces wall-time + timeout pressure)

- **C1. Global LLM semaphore = 5** (`openrouter_client.py:1595`, h2 novel) — ALL LLM work (sections, distill, verify, search, planning) queues behind one hidden cap. Fix: Gate-B sets cap + split concurrency by call class. `PG_MAX_CONCURRENT_LLM`.
- **C2. Sync `httpx` + `time.sleep` retries inside async** (`entailment_judge.py:189`, role_transport `:1077`, h2 novel) — blocks the event loop during backoff. Fix: AsyncClient / async backoff / governed pool.
- **C3. strict_verify serial** (`provenance_generator.py:2437`, h2 — the known 7/min class, still live) — bounded ordered pool, fail-closed per sentence, gates unchanged. `PG_STRICT_VERIFY_CONCURRENCY`.
- **C4. semantic-conflict NLI serial** (`semantic_conflict_detector.py:226`, h2). `PG_SWEEP_NLI_CONFLICT_CONCURRENCY`.
- **C5. retrieval goes serial AGAIN after parallel_fetch** — OpenAlex enrich/classify one-at-a-time over hundreds of candidates (`live_retriever.py:3268/3291/1236/1069`, h2+h1), and `corpus_truncated` only becomes telemetry → can feed a partial corpus to generation. Fix: parallelize enrich/classify; fail-closed/repair on truncation. `PG_OPENALEX_ENRICH_WORKERS`, `PG_CORPUS_TRUNCATION_POLICY`.
- **C6. serial discovery lanes** — STORM before base; deepener/agentic/STORM-seed serialized after base (`run_honest_sweep_r3.py:3355/3828`, `live_retriever.py:2824`, h1+h2). Fix: bounded parallel lanes, deterministic merge.
- **C7. `PG_DISTILL_MICROBATCH_SIZE` read but never exercised** → N+1 LLM burst per section (`evidence_distiller.py:1228/1241`, h2). Fix: real microbatching.

---

## TIER D — RUN-DATA-VISIBLE (COMPLETE: `drb72-deadrun-forensic` wf_91694fcf-778 — 6 Claude slices + Codex cross-audit APPROVE; 27 findings, 25 novel)
Both Claude (6 slices) and Codex (independent re-derivation) APPROVED. Codex corrections: "185 paywall journals" → ~162-169 (host-policy dependent); "80-98% reasoning/call" → range 33-100%. Substance + priorities unchanged.

### D-FAITHFULNESS (the §-1.1 core — clinical-safety-critical, NEW #1 priority)
- **D1. The D8 terminal Judge is a RUBBER STAMP** — Judge (qwen) returned `VERIFIED` on **69/69** claims; for the **12/12** claims where the Sentinel (minimax) said `unsupported`, the Judge OVERRODE every one, its reasoning calling the sentinel signal "a distractor"/"red herring"/"metadata." Root cause: the Judge receives only a compressed `grounded`/`ungrounded` token, NOT the Sentinel's atom-level "why." Claim_ids: 00-021,00-023,00-028,02-003,02-004,03-003,03-004,03-007,04-001,04-002,04-003,08-002. All 12 in `kept`, none `dropped`. **Fix:** pass the Sentinel's full atom-level output to the Judge; a document-level `unsupported` BLOCKS `VERIFIED` (fail-closed) unless the Judge span-grounds a rebuttal of each unsupported atom. **(P1, the primary clinical risk; NEW issue.)**
- **D2.** Claim 02-003 VERIFIED on a methodology misattribution — claim says researchers "implemented" a staggered design; cited span says they "study" it (observational). Verb-mismatch (implement/conduct vs study/observe) = qualitative-faithfulness gap. (P1)
- **D3.** Multi-citation claim 07-000 VERIFIED with one of two cited spans (ev_009) NOT supporting the 40% WEF figure — decorative co-citation riding on a strong span. Need per-citation span grounding. (P2)
- **D4.** frey_osborne grounded on the ORA repository **metadata/abstract page**, not the paper body (claims 01-002,03-003,04-001). Flag landing/metadata pages; abstract can't ground methods specifics. (P3, weight not drop.)

### D-DEATH / TOKEN (sharpen A1/A2 + new fixes)
- **D5. (P0, NEW fix "A4") Empty-completion reasoning-runaway** — call 268e2f24: 473.5s, `content=''`, 19797 chars reasoning stuck self-counting, `finish_reason=None`, billed $0, logged `status=ok`, then **silently skipped** at `contract_section_runner.py:710` (`if narr_text and narr_text.strip()`) after eating ~half the section budget. **Fix:** detect `content='' + finish_reason=None` → FAIL the call (raise/retry); reasoning-runaway guard; per-call stall timeout (~120-180s) << section wall.
- **D6. (P0) reasoning.max_tokens silently ignored by providers** — requested 1000 → served 5599 (5.6×); requested 6553 → 7997. Advisory field not honored. **Fix:** enforce client-side / pin a provider that honors it / **lower reasoning effort for contract_slot calls** (they need ≤3 sentences, not 8k reasoning tokens). Confirms I-arch-003 token-governance concern in DATA.
- **D7. (P1) Token caps not model-max** (Codex add) — deepseek 32768, entailment 2000, credibility 8000, Storm 409/819 → §9.1.8 violation, data-visible.
- **D8.** 600s wall architecturally incompatible (a clean 2-narrative section = 643s) — **A2's 9000s wall already fixes this**; per-section sizing (N_slots × per-call) is an A2 refinement.

### D-RETRIEVAL (§-1.3 weight-not-filter violations — belong under I-arch-001 #1245)
- **D9. (P0) 185 demanded journals fetched ONLY paywall stubs** — incl. the two flagship papers for THIS question (Acemoglu-Restrepo "Robots and Jobs" / "Automation and New Tasks"); academic.oup=34, uchicago=34, sciencedirect=25, doi.org=22; S2 success 15.8%. **Fix:** route paywalled publishers to Zyte FIRST + min-body-length fail-loud gate (the operator's Zyte key unlocks these).
- **D10. (P0) `status='ok'` masks stubs** — Zyte (1651×) + crawl4ai (1297×) returned ok on 304-374 char paywall bodies; `refetch_diagnostics.json=[]` (zero escalations despite 185 stubs). **Fix:** decouple fetch-success from content-success; record <1000-char body as `stub`/fail → trigger refetch ladder.
- **D11. (P1) §-1.3 HARD-DROP** — `content_starved=49` (44 reputable: Research Policy, Tech Forecasting, World Development) + `rerank_not_selected=539` (457 journal/DOI incl. REStat, Brookings). Log says "select dropped=0" — misleading; the real drops happened upstream. **Fix:** down-weight, don't drop; surface in the dropped count.
- **D12. (P1) R9 demotes canonical-DOI journals to T4** just because host=doi.org — JEP/JPE → T4 (50 sources); `weight_basis=tier_prior` for 803/803, so a tier bug IS a credibility bug. **Fix:** trust OpenAlex venue / resolve DOI to publisher host.
- **D13. (P2)** Duplicate refetch of dead paywall DOIs (mean 5.5 attempts/URL, worst 35×, single fetches 150-210s) — contributed to the section-gen wall pressure. Per-URL cap + negative cache.

### D-PROVIDER / COST
- **D14. (P1) Empty-content/null-usage streams logged `status=ok`** (the harness accepts blank 200s — both a generate AND a credibility_judge). Fail loud on `content==None + null usage`.
- **D15. (P2)** Side-judges free-route (`provider=None`, fanned across AtlasCloud/DeepInfra/Baidu/GMICloud) — **confirms g3's `evaluator`-role-key leak in DATA**; GMICloud blank-200 credibility_judge logged ok.
- **D16. (P2/P3 cost)** cost_ledger under-reports $0.30 (4.5%); `entailment_judge` = 47% of spend (full 11k-char span re-sent per call → trim to cited window); `credibility_judge` = 43% (verbose rationale → tighten schema).

### TIER-D → reshaped fix priority
After A1 (done) + A2 (in gate): **(1) D1 Judge rubber-stamp [faithfulness #1]**, (2) D5/D6 empty-completion + reasoning-effort [run-killer "A4"], (3) B-tier static faithfulness (B1 side-judge routing = D15, B2 fail-open = D14), (4) D9-D12 retrieval under I-arch-001 #1245, (5) the rest. The **minimal A1+A2 resume** still proves the pipeline completes; the **trustworthy** resume needs D1+D5+D14 at minimum.

---

## TIER E — P2/P3 HYGIENE + .env-ification (do alongside, not blocking)

- Run-health gate passes on `firing_status=fired` not delivered rows; deepener ungated (h1) → gate on attempted/fetched/merged rows. `PG_DISCOVERY_DELIVERY_GATE`.
- `PG_MAX_COST_PER_RUN` NOT a hard cap during parallel 4-role (spend reconciled after worker completion → overspend possible) (h4) → atomic budget reservation before each verifier call. **(spend-safety, treat as P1-ish.)**
- Corpus cache warmer writes empty 200s (`run_honest_sweep_r3.py:1887`, h4) → disable stub warming / never record empty-200 as valid. `PG_RETRIEVAL_CACHE_MODE`.
- Super-heavy preflight reruns per query (`run_gate_b.py:1330`, h4+h1) → cache by config/lock/API-key TTL.
- Final artifacts not atomic-write (`run_honest_sweep_r3.py:8397`, h4) → temp+fsync+replace.
- `research_planner` `DEFAULT_MAX_SUBQUERIES=40` bypasses Gate-B `PG_MAX_SUBQUERIES=15` (`research_planner.py:197`, h1). `PG_RESEARCH_PLANNER_MAX_SUBQUERIES`.
- Hardcoded side-call token literals: planner 2000, topic 1200, fact-dedup 2048, outline 2500, quantified 4000, audit 800 (g2+g5+h1) → `PG_*_MAX_TOKENS` each.
- 12/12/40 retrieval breadth + R-6 4q/5/5/15 defaults (g5; bites direct callers only) → promote Gate-B floors to governed defaults.
- Side-judge `max_tokens` 2000/8000 + not max-effort (g2+g3+h2+h3) → governed max + max effort reconciled to mirror cap (I-arch-003 max-budget rule).
- Stale Gemma comments on live faithfulness surfaces (g3 P3) → update to glm-5.1.
- `section_temperature=0.3`, resolver 3/15 heuristic, many bare 15/30/45/60/75s HTTP timeouts (g5+h2+h4) → `PG_*`.

---

## RESUME PATH (operator ask: resume the dead run from the middle)
The run had **no stage checkpoints**, but the VM retains `retrieval_cache.sqlite` + `authority_enrich.sqlite` (accelerators) and the full `drb_72_ai_labor` out-root. Honest resume = **land A1+A2 (+A3 corpus_snapshot), redeploy, re-run the SAME query with the SAME `--out-root`** → retrieval replays from cache (near-free), and only the section generation that died is re-paid, now with correct timeouts + crash isolation. A bespoke "start-from-middle temp pipeline" is more fragile than cache-reuse + fixed timeouts. **Resume is GATED behind A1+A2** (re-running with the broken 600s wall would just die again). Documented in `resume_plan.md` (next).

## DISCIPLINE
Every fix = its own Codex-gated brief+diff (§-1.2 / §3.0), §8.3.1 5-iter cap, faithfulness gates NEVER relaxed, all parameters .env-ified (operator directive: hardcoded params are lethal). Land order: A1 → A2 → A3 → B1 → B2 → B3 → (B4..B8, C1..C7, E) → resume run.
