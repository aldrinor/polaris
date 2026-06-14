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

## TIER D — RUN-DATA-VISIBLE (pending: `drb72-deadrun-forensic` Workflow wf_91694fcf-778)
*To be filled from the 6-slice Claude forensic + Codex cross-audit of the actual run data: death mechanics, ~25 length-capped llm_io truncations, faithfulness-leak hunt over 276 D8 role calls, retrieval quality (S2 15.8%, 7 empty-extract 200s), provider-lock conformance (served_model per role), cost breakdown of $6.74.*

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
