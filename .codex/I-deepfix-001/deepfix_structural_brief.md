HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# DIFF GATE — I-deepfix-001 (#1344) consolidated STRUCTURAL fix set (3 fixes)

## TASK
Static review of the staged diff at `.codex/I-deepfix-001/deepfix_structural_diff.patch` (READ that file). DO NOT run pytest — static review only. You may read source files in C:/POLARIS for context. Verdict APPROVE iff the 3 fixes are surgical, faithfulness-neutral, §-1.3-safe, default-byte-identical where applicable, and free of NOVEL/continuing P0 + P1.

These three fixes target the runtime mid-flight failure modes a static gate + at-rest preflight kept passing over (the relaunch forensic + midflight review). All three are PRE-GENERATION retrieval/consolidation safety — none touches the faithfulness engine.

## THE 3 FIXES (files: `src/polaris_graph/retrieval/scope_query_validator.py`, `scripts/run_honest_sweep_r3.py`, `src/polaris_graph/synthesis/consolidation_nli.py`)

### FIX-1 (KEYSTONE) — scope-validator anti-empty-round (KEEP-BEST-N)
**Root cause (relaunch forensic P1-8):** `validate_amplified_queries` could drop a whole snowball / CRAG-corrective sub-query set to "0 unique candidates". An empty kept-set fires NO search => no new sources merge => the CRAG adequacy grader re-grades the unchanged corpus not-sufficient => the corrective loop burns its budget WITHOUT widening the corpus — retrieval never converges. A validator that HARD-DROPS to empty is itself the §-1.3 "filter, not weight" anti-pattern.
**Fix:** KEEP-BEST-N. When the scope-floor loop leaves the kept-set EMPTY AND there are below-floor (non-directive, non-empty) candidates, keep the top-N by scope similarity (a WEIGHT — the most on-intent survivors) so the round still fires. Env knob `PG_SCOPE_KEEP_BEST_N` (default 1; `0` => legacy drop-to-empty, byte-identical).
- The function SIGNATURE is UNCHANGED (env-driven only) — the 3 other callers (research_planner, run_gate_b, live_retriever) are byte-identical-safe.
- Fires ONLY when kept would be empty; when an always-kept anchor or any passing query already makes kept non-empty, it NO-OPs => byte-identical.
- The B3 directive/injection screen runs BEFORE the floor, so an injected directive is NEVER a keep-best-N survivor; empty-after-tokenization queries are never survivors.
- §-1.3 keep-and-proceed: adds on-intent queries the floor would have stranded; drops no source; touches no strict_verify/NLI/4-role/span gate.

### FIX-2 — SHARED per-question retrieval wall-deadline
**Root cause (relaunch forensic P0-1/P1-9 + midflight #8 = 57-min retrieval grind):** `run_live_retrieval` already ACCEPTS `retrieval_deadline_monotonic` and hands off the partial corpus with disclosure on expiry — but `run_one_query` never passed a SHARED instant, so EACH retrieval lane (initial / IterResearch-or-FS / CRAG loop-back / R-6 expansion / deepener / agentic / STORM / saturation-gap) anchored its OWN fresh `PG_RETRIEVAL_WALL_SECONDS` (30 min) wall. Each lane reset the clock; the run ground tens of minutes.
**Fix:** new pure helper `_per_question_retrieval_deadline()` reads `PG_RETRIEVAL_QUESTION_WALL_SECONDS` and returns ONE absolute `time.monotonic()` instant (or `None` when unset/garbage/non-positive => the proven per-invocation default, byte-identical). `run_one_query` anchors it ONCE (at the retrieval-phase start, right after `t0`) and threads it into all 8 `run_live_retrieval(...)` call sites via `retrieval_deadline_monotonic=...`.
- The `run_live_retrieval` wall machinery + partial-fetch handoff is UNCHANGED (already gated + tested by `test_live_retriever_retrieval_wall.py`); this is purely the caller-side SHARING.
- §-1.3: only the per-lane CLOCK RESET is stopped; the existing wall hands off the partial corpus with disclosure (no breadth cap, no source drop). `None` default => byte-identical.

### FIX-3 — W10 consolidation-NLI cross-encoder OOM-DEGRADE
**Root cause (relaunch forensic GPU co-residence):** the consolidation cross-encoder (`consolidation_nli._load_model`) loaded on CUDA by default with NO device control and NO OOM handling. On the crammed 2-GPU split (W6 embedder + W5 reranker + W10 NLI co-resident on cuda:0) a CUDA OOM during load/predict RAISES — propagating through `_apply_consolidation_nli` -> `dedup_by_finding` and killing the CONSOLIDATION step (a §-1.3 WEIGHT, not a faithfulness gate).
**Fix:** DEGRADE instead of die.
- `PG_CONSOLIDATION_NLI_DEVICE` knob places the cross-encoder (default unset => NO device kwarg => byte-identical library auto-placement).
- On a CUDA OOM during the model LOAD, retry the load on CPU (degrade) — the winner still FIRES (it logs the load + scores on CPU), so the §-1.4 firing canary is satisfied and NO basket is lost.
- On a CUDA OOM during PREDICT, rebuild the model on CPU and re-score; the CPU model is swapped in for all remaining chunks (no per-chunk thrash). The bidirectional-entailment argmax is device-invariant, so the merged baskets are identical.
- A NON-OOM error (missing checkpoint, tokenizer mismatch) still FAILS LOUD (`_is_cuda_oom` classifier) — only a genuine CUDA OOM degrades.
- §-1.3: keeps MORE baskets (consolidation runs to completion on CPU instead of dying), never fewer; merges literal clusters exactly as before; touches no strict_verify/NLI-entailment-verifier/4-role/span gate.

## FAITHFULNESS / §-1.3 NON-NEGOTIABLES (confirm each holds)
1. FAITHFULNESS ENGINE UNTOUCHED — strict_verify / NLI entailment verifier / 4-role D8 / provenance / span-grounding are not imported or altered by any of the 3 fixes. (The W10 NLI here is the CONSOLIDATION cross-encoder = a corroboration WEIGHT, NOT the faithfulness NLI verifier `nli_verifier._load_faithlens`.)
2. §-1.3 NO-DROP / WEIGHT-NOT-FILTER — FIX-1 keep-best-N ADDS on-intent queries (never drops a source); FIX-2 only stops the clock RESET (the existing wall hands off with disclosure, no cap/drop); FIX-3 keeps MORE baskets (degrade-not-die). NONE adds a hard DROP/CAP/THIN/TARGET.
3. DEFAULT BYTE-IDENTICAL where feasible — FIX-1 `PG_SCOPE_KEEP_BEST_N=0`; FIX-2 `PG_RETRIEVAL_QUESTION_WALL_SECONDS` unset; FIX-3 `PG_CONSOLIDATION_NLI_DEVICE` unset + no CUDA OOM. snake_case, env-driven (LAW VI), no silent `except: pass`, no mocks in src/.

## REVIEW FOCUS (find any REAL residual violation)
1. FIX-1: confirm keep-best-N fires ONLY on an empty kept-set; the directive screen + empty-after-tokenization guards still gate survivors; the rescued queries are correctly moved from `dropped` to `kept` (no double-count); determinism (sim DESC, stable tie-break). Confirm the unchanged SIGNATURE keeps the 3 other callers byte-identical.
2. FIX-2: confirm the deadline is anchored ONCE and threaded into ALL retrieval lanes in `run_one_query` (8 call sites); confirm `None` default is byte-identical; confirm the garbage/non-positive guard mirrors `_env_float` finiteness.
3. FIX-3: confirm `_is_cuda_oom` classifies ONLY genuine CUDA OOM (typed `OutOfMemoryError` + 'out of memory'+'cuda'/'gpu' message) and a non-OOM error still raises; confirm the predict-OOM degrade swaps the CPU model in for ALL remaining chunks (thread-safe under `_MODEL_LOCK`); confirm the load-OOM degrade does not infinite-loop (already-CPU device re-raises). Confirm the basket merge result is unchanged by the degrade (same edges).
4. NO NEW BUGS from the surgical edits (closure capture of `_question_retrieval_deadline`; the `_MODEL_DEVICE` global lifecycle; the `_predict_holder`/`_degraded` mutable closure under the bounded thread pool).

## TEST EVIDENCE (offline, no GPU/network — RED->GREEN per fix)
- FIX-1 `tests/polaris_graph/test_deepfix_crag_gap_scope_keystone.py` — 7 tests: legacy drop-to-empty (RED baseline), keep-best-N rescues the empty round, default-ON, does-not-rescue-injected-directives, skips-empty-after-tokenization, no-op when a query already passes, no-op when anchor already kept. 7/7 GREEN.
- FIX-2 `tests/polaris_graph/test_deepfix_shared_retrieval_deadline.py` — 10 tests: helper None when unset / absolute instant when set / garbage->None (param), + static wiring assertions (every `run_live_retrieval` call site in `run_one_query` carries `retrieval_deadline_monotonic=`, anchored exactly once). 10/10 GREEN.
- FIX-3 `tests/polaris_graph/test_deepfix_consolidation_nli_oom_degrade.py` — 6 tests: device knob unset (no kwarg) / set (placed); load CUDA-OOM degrades to CPU / non-OOM load raises; predict CUDA-OOM degrades + completes with identical edges / non-OOM predict raises. 6/6 GREEN.
- Regression suites (one run at a time, §8.4): `test_scope_query_validator.py` 9/9, `test_live_retriever_retrieval_wall.py` 5/5, `test_fact_dedup.py` + `test_credibility_pass_wall_deadline.py` 54/54, `test_finding_dedup_phase5.py` + `test_winner_firing_gate_ideepfix001.py` + `test_deepfix_reranker_nli_device_knob.py` + `test_capped_finding_dedup_iready004.py` 71/71, `test_live_retriever_env_knobs.py` + relevance-gate + weight-not-filter + crag-fire 66/66. Consolidated touched-file run = 70 passed. No regressions.

## Files I ALSO checked and they're clean (§-1.2 adjacent scan)
- `validate_amplified_queries` callers: `research_planner.py`, `live_retriever.py`, `run_gate_b.py` — signature UNCHANGED (keep-best-N is env-driven), so all byte-identical-safe.
- `retrieval_deadline_monotonic` consumers: `live_retriever.run_live_retrieval` (unchanged) + the new `run_honest_sweep_r3.py` caller wiring only.
- `consolidation_nli` consumers: `fact_dedup.py`, `finding_dedup.py`, `nli_benchmark_annotator.py` — call `group_clusters`/`score_pairs` whose public contract is unchanged (same edges; degrade is internal).

## Output schema (REQUIRED — last `verdict:` line authoritative)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
Static review only — do NOT run code. Verdict APPROVE iff the 3 fixes are correct, surgical, faithfulness-neutral, §-1.3-safe with zero P0/P1.
