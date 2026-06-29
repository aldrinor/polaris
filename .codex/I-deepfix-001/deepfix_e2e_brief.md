HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Please return the verdict in this schema:

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

# I-deepfix-001 (#1344) — END-TO-END WALL-CLASS FIX CAMPAIGN — consolidated diff gate

## Mission
The next paid clinical-deep-research run must reach a RENDERED report end-to-end WITHOUT hitting ANY wall. The campaign hunts six wall-classes across EVERY stage of the spine (`scripts/run_honest_sweep_r3.py::run_one_query`):
(A) HANG; (B) ABORT-WITHOUT-OUTPUT; (C) NON-CONVERGENCE; (D) TIME-DROWN; (E) EMPTY-OUTPUT/NO-HANDOFF; (F) TEARDOWN-HANG.

BINDING CONSTRAINTS honored in every fix:
- The faithfulness ENGINE (strict_verify / NLI entailment / 4-role D8 / provenance / span-grounding) is NEVER relaxed or removed as a SAFETY check. Where a HOLD/abort dropped the WHOLE report, it was converted to ship-with-disclosure+per-claim-label (the per-claim label IS the faithfulness signal, per the operator-locked "the verifier NEVER holds a report").
- SS-1.3: degrade paths keep MORE-or-equal sources, never fewer. No DROP/CAP/THIN/TARGET added.
- Env-driven knobs, snake_case, no magic numbers, no silent `except: pass`, no mocks in `src/`. Default byte-identical where feasible.

The diff to review: `.codex/I-deepfix-001/deepfix_e2e_diff.patch` (18 files, +2629 / -112). Please review STATICALLY (do NOT run pytest in the sandbox — large repo, codex scratch dirs trip rc=127).

## What this round (round 3) added on top of the staged FIX-1/2/3 + BUG-A/BUG-B
This is round 3. Rounds 1-2 staged the corpus/retrieval/consolidation/fetch fixes. Round 3:
1. Verified every one of the 14 wall fixes is present AND correct (claim-by-claim against the code) — including the KNOWN-OPEN Codex-iter-1 P1 (the FS-Researcher qgen loop firing past the deadline), which IS now fully gated.
2. Closed the test-coverage gap: added `tests/polaris_graph/test_deepfix_round3_walls.py` (13 RED->GREEN tests) for the 5 walls (W03, W05, W10, W12, W13) that had NO dedicated test, plus confirmed RED->GREEN against the committed HEAD baseline for each.

## The 14 wall-class fixes (end-to-end, stage by stage)

### W01 — corpus_gates: error_corpus_population_mismatch (B, HIGHEST RISK — fired UNCONDITIONALLY)
- Root cause: B7 (#1351) made `assess_corpus_adequacy` REPORT total_sources/tier_counts over the ON-TOPIC evidence_rows population while FX-06 compares against the classifier `dist` — divergent by construction whenever any row is demoted off-topic. Fired on EVERY normal run before a single generator token.
- Fix (`src/polaris_graph/nodes/corpus_adequacy_gate.py:475-507`): the PROCEED/EXPAND/ABORT decision + all on_topic_* disclosure ride on `gate_tier_counts` (UNCHANGED, byte-identical decision); the REPORTED `total_sources`/`tier_counts` are RESTORED to the classifier population (`reported_tier_counts = dict(tier_counts)`), so FX-06 equality holds by construction.
- Disposition (`scripts/run_honest_sweep_r3.py:9460-9497`): FX-06 downgraded from abort to log-and-proceed-with-disclosure behind kill-switch `PG_FX06_HARD_ABORT` (default 0). FX-06 verifies no claim and refuses nothing harmful — a pure self-consistency tripwire.
- Test: `test_w01_reported_population_is_classifier_not_on_topic`.

### W02 — retrieval_loops/run_level: shared per-question wall ACTIVATED + FS-Researcher gated (C+B, the KNOWN-OPEN P1)
- `PG_RETRIEVAL_QUESTION_WALL_SECONDS=5400` set in the Gate-B slate (< 10800 run-wall) so the staged FIX-2/BUG-A/WALL-03 gates engage and partial corpus hands off (disclosed) BEFORE the run-wall guillotines (`scripts/dr_benchmark/run_gate_b.py:616`).
- FS-Researcher qgen loop gated (`src/polaris_graph/retrieval/fs_researcher_query_gen.py:139,155,163,183`): the TOC-deconstruction llm(), each per-todo query-derivation llm(), and the 6-item checklist critic llm() all break once `_retrieval_deadline_passed(retrieval_deadline_monotonic)`. The spine threads the shared deadline at `run_honest_sweep_r3.py:8189`. This is the exact Codex-iter-1 P1, now CLOSED.
- Aggregate-fit preflight (`run_gate_b.py:2615`): asserts question_retrieval_wall < run-wall before spend (FAIL CLOSED).
- Tests: `test_r2_fs_researcher_in_call_result_is_bounded`, `test_additive_lanes_guarded_count`, `test_crag_while_loop_consults_the_deadline_guard`.

### W03 — generation/strict_verify: inline SYNC verify on the event-loop thread (A, the py-spy ssl.recv freeze)
- Fix: every inline `strict_verify(...)` is now `await asyncio.to_thread(strict_verify, ...)` at `multi_section_generator.py:4152, 4274, 7807` (3 sites; the file's credibility pass already used this pattern), and the 3 `_verify_one_stream(...)` calls (which wrap the injected sync strict_verify_fn) are `await asyncio.to_thread(_verify_one_stream, ...)` at `contract_section_runner.py:1285,1308,1332`. Same verdicts, same engine, faithfulness byte-identical — only the thread changes, so the enclosing per-section + run-wall asyncio.wait_for can actually preempt a wedged verify.
- RED->GREEN evidence: HEAD has 3 BARE sync `= strict_verify(` calls + 1 to_thread; working tree has 0 bare + 4 to_thread. contract_runner: 0 -> 3 offloads.
- Tests: `test_w03_multi_section_strict_verify_is_offloaded_to_thread`, `test_w03_contract_runner_verify_stream_is_offloaded_to_thread`, `test_w03_to_thread_actually_lets_wait_for_preempt_a_wedged_sync_call` (behavioral proof the wall returns control at the timeout, the orphaned worker drains on its own).

### W04 — consolidation: NLI score_pairs unbounded + over-MAX_PAIRS raise (A+D)
- `PG_CONSOLIDATION_NLI_WALL_SECONDS` total deadline over the whole scoring loop (`consolidation_nli.py:393-456`): manual pool (NOT `with`), non-blocking `shutdown(wait=False, cancel_futures=True)`, `futures_wait(..., timeout=remaining)`, returns the partial edge set (UNDER-merges only -> keeps MORE/equal baskets, SS-1.3). Over-MAX_PAIRS now SKIPS-unmerged (telemetry note) instead of raising (`:315-328`), mirroring the prose path's correct skip.
- Tests: `test_w04_over_max_pairs_skips_not_raises`, `test_w04_scoring_wall_returns_partial_not_hangs`.

### W05 — consolidation: cross-encoder cold-load unbounded Hub download + CUDA-OOM (A/C)
- `HF_HUB_DOWNLOAD_TIMEOUT=30` in the slate (`run_gate_b.py:628`) bounds a stalled Hub download. The cross-encoder LOAD classifies a CUDA-OOM and degrades to CPU (`consolidation_nli.py:208-221`) so consolidation still fires (no basket lost); a non-OOM load error still fails loud (§-1.4).
- RED->GREEN: HF_HUB_DOWNLOAD_TIMEOUT 0 -> 1 in slate.
- Tests: `test_w05_cross_encoder_load_cuda_oom_degrades_to_cpu`, `test_w05_non_oom_load_error_still_fails_loud`, `test_w05_slate_sets_hf_hub_download_timeout`.

### W06 — relevance_scoring: GLM-escalation pool with no deadline (A+D)
- `score_passages` threads an absolute monotonic deadline (env `PG_CONTENT_RELEVANCE_DEADLINE_S` default 600, or caller-threaded retrieval wall) from `live_retriever.py:5050`; on expiry `_resolve_ambiguous` STOPS escalating and emits the remaining ambiguous passages at FULL weight (always-release, never demote-on-timeout) with disclosure (`content_relevance_judge.py:133-140,220,291-294`). Demote-not-drop weight — faithfulness-neutral.
- Test: `test_w06_escalation_deadline_keeps_full_weight`.

### W07 — credibility_tiering: LLM-tiering batch unbounded (A+D)
- `classify_sources_llm_tiering` takes `deadline_monotonic` + env batch wall `PG_TIER_LLM_BATCH_WALL_SECONDS` (default 600) drained via as_completed; on expiry keeps the rules-FLOOR tier for un-returned sources (no drop). Circuit-breaker `PG_TIER_LLM_DEGRADE_AFTER` (default 8) short-circuits remaining to the floor after consecutive fallbacks (`credibility_llm_tiering.py:224-311`). Tier is a WEIGHT; un-tiered sources keep the deterministic floor.
- Tests: `test_w07_batch_wall_keeps_floor_not_hangs`, `test_w07_circuit_breaker_short_circuits_to_floor`.

### W08 — crag_adequacy: classifier await with no total-call wall + re-grade past wall (D+A)
- Each `_run_crag_classifier()` await wrapped in `asyncio.wait_for(..., timeout=_crag_classifier_timeout())` (`run_honest_sweep_r3.py:8459-8473,8509,8623`) so the env budget is a TOTAL-call wall capping the 3-attempt x backoff multiplication. A deadline re-check is added before the in-loop re-grade so once the wall passes the iteration hands off the merged corpus (`:8535`). Fail-open preserved (KEPT as safety).
- Tests: `test_crag_while_loop_consults_the_deadline_guard`, `test_crag_early_stop_is_disclosed`.

### W09 — fetch_extraction: mineru25 GPU-lock convoy + breaker blind to the 90s-abandon path (D+F)
- Bounded lock acquire `_mineru25_gpu_lock.acquire(timeout=PG_MINERU25_LOCK_WAIT_S)` (default 60) -> LOUD W4-CANARY + docling fallback on failure (`access_bypass.py:5012-5017`). mineru `wait_for` aligned to <= the outer fetch deadline so a slow VLM fails-fast to docling INSIDE the 90s window, letting the BUG-B breaker actually see the timeout and trip.
- Tests: the 8-test `test_deepfix_mineru25_circuit_breaker.py` suite + `test_r2_w09_fetch_deadline_default_is_governing_90`.

### W10 — fetch_extraction: docling extraction unbounded (A)
- `await asyncio.wait_for(loop.run_in_executor(None, self._docling_extract, pdf_bytes), timeout=PG_DOCLING_TIMEOUT_S)` (default 60 < 90 outer join) at `access_bypass.py:3688-3700`; clean TimeoutError -> PyMuPDF fallback. Faithfulness-neutral (only which extractor produces the text).
- RED->GREEN: PG_DOCLING_TIMEOUT_S absent in HEAD -> present.
- Tests: `test_w10_docling_extract_wrapped_in_wait_for`, `test_w10_wait_for_preempts_a_wedged_executor_extract`.

### W11 — generation: section strict_verify judge_error (TRANSPORT) fail-closed drops ALL sentences (B)
- `judge_error` (TRANSPORT-only, `reason.startswith("judge_error:")`) degrades to KEEP-with-disclosed-label `entailment_unverified_judge_error` instead of drop, gated by the always-release flag (`clinical_generator/strict_verify.py:295-324`). Applies ONLY to judge_error; genuine NEUTRAL/CONTRADICTED stay dropped — faithfulness NOT relaxed.
- Tests: `test_w11_judge_error_degrades_to_keep_when_always_release`, `test_w11_judge_error_still_drops_when_release_off`, `test_w11_genuine_neutral_still_drops_with_release_on`.

### W12 — strict_verify: abort_excessive_gap holds the WHOLE report despite verified sections (B)
- `run_honest_sweep_r3.py:12574-12607`: when `_excessive_gap` AND `verified_sections` non-empty AND `always_release_enabled()` AND NOT `judge_degraded`, set `_excessive_gap = False` (bypass the early-return abort), append a disclosed "Coverage gap" to disclosed_gaps, stamp `excessive_gap_shipped_with_disclosure`, status released_with_disclosed_gaps. Every shipped sentence already passed strict_verify. GUARDRAIL: gated NOT to swallow abort_no_verified_sections / abort_verifier_degraded.
- RED->GREEN: excessive_gap_shipped_with_disclosure absent in HEAD -> present.
- Tests: `test_w12_is_excessive_gap_predicate`, `test_w12_select_gap_abort_status_guardrails`, `test_w12_ship_conversion_is_gated_and_present_in_spine_source`.

### W13 — scope_intake: intent_frame ADVISORY blocks on .result() with no timeout + fail-closed (A+B)
- Dedicated `PG_SCOPE_INTENT_FRAME_TIMEOUT_SEC` (default 150) passed to `generate()` AND a bounded `.result(timeout=...+30)` (`run_honest_sweep_r3.py:7116-7173`). On TimeoutError/IntentFrameError/blank the call degrades to the raw question WITH DISCLOSURE (`intent_frame_degraded`), proceeding to the scope gate (`:7196-7204`). intent_frame is advisory — touches NO faithfulness gate.
- RED->GREEN: PG_SCOPE_INTENT_FRAME_TIMEOUT_SEC absent in HEAD -> present.
- Tests: `test_w13_intent_frame_dedicated_timeout_threaded_and_degrade_catch`, `test_w13_degrade_pattern_proceeds_instead_of_raising`.

### W14 — four_role_verify: off-enum JudgeEnumError tears down the WHOLE seam (B)
- Part 1: `JudgeEnumError` caught at the run_judge call site (`judge_adapter.py:313-321`) -> degrade THIS claim to the fail-closed UNSUPPORTED verdict + `<judge_offenum>` RoleCallRecord (gated PG_ROLE_TRANSPORT_DEGRADE; off-enum is impossible on the sovereign vLLM grammar-decode path so byte-identical there). Conservative -> faithfulness only TIGHTENS.
- Part 2: partial-recovery extended from seam_timeout-ONLY to ALSO cover seam_error:* via the SAME recover_seam_partial_verdicts + build_seam_release_outcome path (`run_honest_sweep_r3.py:14551-14561`) — audit fidelity only; the non-empty disclosed gap still forces disclosed/held (cannot false-certify).
- Test: `test_w14_judge_offenum_degrades_this_claim_not_seam`.

## Aborts CONVERTED to ship-with-disclosure (the verifier-never-holds principle)
- W01 error_corpus_population_mismatch -> log+disclose+proceed (self-consistency tripwire, no claim verified).
- W11 section strict_verify TRANSPORT judge_error -> keep sentence with `entailment_unverified_judge_error` label.
- W12 abort_excessive_gap (with verified sections present + healthy verifier) -> released_with_disclosed_gaps.
- W13 intent_frame error_unexpected -> raw-question-with-disclosure (advisory).
- W14 abort_four_role_release_held on off-enum/seam_error -> per-claim degrade + partial-recovery disclosed-held.

## Aborts KEPT AS GENUINE SAFETY (NOT converted)
- abort_no_verified_sections / abort_verifier_degraded — zero faithful prose, or a bricked verifier; converting would manufacture findings. W12 is gated NOT to capture these.
- scope_gate unsupported_domain reject + abort_safety_refused — deterministic, harm-refusal lethality guard.
- CRAG classifier fail-open — correct fail-direction (verifier-never-holds applied to the STOP decision); W08 wall is additive.
- journal_only fail-closed aborts — genuine contract-integrity safety (inert on the non-journal_only run).
- The run-level wall-clock net (PG_RUN_WALL_CLOCK_SEC) — the last-resort guillotine that writes a non-empty TIMEOUT artifact STAYS; W02 makes it never FIRE.
- Per-call entailment-judge bounds — the per-CALL total-deadline + force-close that makes the judge HANG-SAFE STAYS.

## Test evidence (offline, ONE run, SS8.4 no parallel pytest)
`python -m pytest` over the 5 deepfix files = **47 passed, 1 warning in 33.98s**:
- test_deepfix_wall_class_e2e.py (10) — W01/W04/W06/W07/W11/W14
- test_deepfix_round2_walls.py (7) — section guard run-wall-aware, FS-Researcher in-call bound, W09 fetch default
- test_deepfix_round3_walls.py (13, NEW) — W03/W05/W10/W12/W13
- test_deepfix_outer_loop_retrieval_deadline.py (9) — W02/W08 deadline gating
- test_deepfix_mineru25_circuit_breaker.py (8) — W09 breaker
RED->GREEN confirmed against committed HEAD for W03/W10/W12/W13/W05 (the working-tree-only fixes): each fix's signature token is ABSENT in `git show HEAD:` and PRESENT in the working tree, and the round-3 tests assert exactly those tokens.

## Env-hygiene CONFIRM items (completeness-critic)
- `PG_USE_RESEARCH_PLANNER` = force-EXACT "0" + REQUIRED_OFF (fail-closed if re-armed) — a stray export cannot re-arm the plan-sufficiency abort.
- `PG_SWEEP_WEIGHTED_CORPUS_GATE` = force-ON + REQUIRED (fail-closed) — a stray =0 cannot restore the tier-count refusal.
- `PG_FX06_HARD_ABORT` defaults 0 (ship+disclose); intentionally NOT slated — only a deliberate operator opt-in to "1" re-arms the abort (documented disposition).

## Specific things to red-team
1. W01: is the DECISION truly byte-identical (does any decision branch read `report.total_sources` / `report.tier_counts` rather than the on_topic_* fields)? Confirm the restored reported population cannot change PROCEED/EXPAND/ABORT.
2. W03: are there any OTHER inline sync `strict_verify(` / sync per-sentence judge calls on an async path that were missed (grep beyond multi_section + contract_section_runner)?
3. W12: confirm the `_excessive_gap = False` flip cannot reach the abort_no_verified_sections branch when verified_sections is empty (guardrail on `bool(verified_sections)`).
4. W14 part 1: confirm the JudgeEnumError degrade is conservative (UNSUPPORTED, not silently SUPPORTED) and that part-2 partial-recovery cannot false-certify (build_seam_release_outcome forces disclosed/held on a non-empty gap).
5. SS-1.3: any degrade path that ends with FEWER sources/baskets/edges than the no-degrade path?
6. Faithfulness: any change that touches strict_verify / NLI entailment / 4-role D8 / provenance / span-grounding AS A SAFETY CHECK (vs only the thread it runs on or a whole-report HOLD->LABEL conversion)?
