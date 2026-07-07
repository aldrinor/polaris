# MASTER LIVENESS LEDGER — the anti-dark gate for the paid VM run (I-deepfix-001 #1344)

**Operator fear this document kills (2026-07-07):** "you complete 8 waves, run on the VM, FORGET to monitor
that all 8 fired, let it run dark, then say 'we fucked up again' and rebuild — wasting another night."

**HARD RULE:** the paid VM run is NOT "success" and I do NOT declare any benchmark result until EVERY row
below shows FIRED with a real realized-effect count in the ACTUAL run log. No exceptions. No "assume it fired."

## Three structural protections (do not depend on me remembering)

1. **Fail-loud activation canary — ARMED.** `PG_ACTIVATION_CANARY="1"` + `PG_LOG_LEVEL="INFO"` are on the
   official slate. `assert_activation_markers_fired()` (run_gate_b.py) raises `RuntimeError` (overall_rc=1)
   if any ON flag's `[activation]` marker is ABSENT, its honesty booleans unhealthy, or a degrade/fail-open
   marker present. So a DARK flag CRASHES the run — it cannot silently ship a bad report.
2. **Preflight PROVEN table BEFORE spend.** A small real run fills the `preflight FIRED?` column below. I do
   NOT launch the big paid run until every row is FIRED. (Offline unit tests are NOT preflight.)
3. **Live monitor during the run.** Arm a Monitor on the run log for the expected `[activation]` markers +
   the canary result, so a missing/failed marker wakes me instantly — not dependent on 5-min polling memory.

## The ledger — every wave flag (fill FIRED counts from the REAL run log, never assume)

| Wave | Flag | Expected [activation] marker | canary spec | preflight FIRED? | RUN FIRED? |
|---|---|---|---|---|---|
| 1 | PG_WORKFORCE_T3_TARGETING | `[activation] workforce_t3_targeting: promoted= checked=` (realized) | ✅ **spec ADDED (77ea5fed)** — Wave-9; whitelist default-OFF | ⬜ | ⬜ |
| 1 | PG_DEBATE_CON_BASKET_CONSOLIDATION | `[activation] debate_con_basket_consolidation: consolidated=` (realized len-delta; degrade `unavailable_failopen`) | ✅ **spec ADDED (77ea5fed)** — Wave-9; flag_default_on=True (default-ON producer) | ⬜ | ⬜ |
| 1 | PG_A1_BASKET_FALLBACK | (conditional contract/clinical seam — no marker) | ❌ **DEFERRED (Wave-9b)** — conditional seam: a per-call spec would false-fail a released run; needs guaranteed-once run-summary emit (FF3 pattern) | ⬜ | ⬜ |
| 1 | PG_RENDER_CHROME_SCREEN | (conditional KF/Abstract/Conclusion render seam — no marker) | ❌ **DEFERRED (Wave-9b)** — conditional seam false-fail hazard | ⬜ | ⬜ |
| 1 | PG_DEPTH_DECHROME_MEMBERS | (only when depth baskets exist — no marker) | ❌ **DEFERRED (Wave-9b)** — conditional seam false-fail hazard | ⬜ | ⬜ |
| 2 | PG_POST_FETCH_ENRICH_PARALLEL | `[activation] post_fetch_enrich_parallel: batched= enriched=` (realized) | ✅ **spec ADDED (77ea5fed)** — Wave-9; whitelist default-OFF | ⬜ | ⬜ |
| 2 | PG_WALL_CLASSIFY_RESCUE | `[activation] wall_classify_rescue: armed enrich_parallel=` (pre-existing marker) | ✅ **spec REGISTERED (77ea5fed)** — Wave-9 register-only; whitelist default-OFF | ⬜ | ⬜ |

> **ANTI-DARK GAP (found + 4/7 CLOSED 2026-07-07, Wave-9 77ea5fed):** the 7 Wave-1/2 flags above are all quad-pinned FORCE-ON
> but originally had ZERO `_ActivationMarkerSpec`, so `assert_activation_markers_fired` did NOT cover them. Wave-9 instrumented
> 4 (realized-effect marker + fail-loud spec, dual-gate APPROVE). 3 remain BLIND — DEFERRED to Wave-9b because their seams are
> CONDITIONAL (skipped for some report shapes): a per-call spec would MARKER-ABSENT-FALSE-FAIL a legitimate released run, so
> they need a guaranteed-once run-summary emit at the Gate-B per-report chokepoint (the FF3/summary_table lifecycle pattern).
> Waves 3-4 (below) + 6b/6c/7 have specs. So the automated canary now covers ALL force-ON flags EXCEPT these 3 conditional-seam
> flags, which the operator must weigh (accept the manual ledger read for them, or authorize the Wave-9b lifecycle instrumentation).
| 3 | PG_QGEN_PARALLEL_QUERIES | `[activation] qgen_parallel_fanout: ... issued=` (numeric>=2) | wave3 | ⬜ | ⬜ |
| 3 | PG_OPENALEX_DATE_FILTER | `[activation] openalex_date_filter:` | wave3 | ⬜ | ⬜ |
| 3 | PG_LANDMARK_EXPANDER | `[activation] landmark_study_expansion: expanded_queries=` (ran-ok; NOT unavailable_failopen) | wave3 | ⬜ | ⬜ |
| 4 | PG_OPENALEX_MATCH_VALIDATE | `[activation] openalex_match_validate: checked= rejected=` | yes | ⬜ | ⬜ |
| 4 | PG_RESOLVE_PUBDATE_FROM_HTML | `[activation] pubdate_html_resolve: resolved= unresolved=` | yes | ⬜ | ⬜ |
| 5 | ~~FF2-TRUNC-v2~~ RETIRED (e55637b3) | — (unsound lexical leg removed; no marker, not on slate) | n/a | ➖ | ➖ |
| 5 | FF3-TRUNC-SEM (PG_FF3_TRUNC_SEM) | `[activation] ff3_trunc_sem: reached=(True\|False) screened= detected= repaired= dropped=` (degrade: `unavailable_failopen`) | yes | ⬜ | ⬜ |
| 6 | PG_RENDER_SUMMARY_TABLE (Wave-6a vocab + Wave-6b canary) | `[activation] summary_table: reached=(True\|False) rows= cols=` (degrade: `unavailable_failopen`) | **DONE (1f3d2ced)** — fail-loud _ActivationMarkerSpec added with flag_default_on=True (matches default-ON producer); dark render crashes (overall_rc=1), honest rows=0 passes, NO count>0 gate | ⬜ | ⬜ |
| 6c | PG_STANCE_DIVERSIFY_SEEDS (a09fe434) | `[activation] stance_diversify_seeds: issued=` (realized post-budget count; degrade: `unavailable_failopen`) | DONE — quad-pinned (slate 1716 / preflight 2045 / force-on 2339 / allowlist 3749) + fail-loud spec 3305-3323; additive fail-open, default-OFF byte-identical, marker realized-count | ⬜ | ⬜ |
| 7 | PG_CROSS_SECTION_REPETITION_GUARD (f9173615) | `[activation] cross_section_repetition_guard: consolidated=` (realized count; degrade: `unavailable_failopen`) | DONE — activated built-but-dark module (committed + wired caller multi_section_generator.py:10251 after engine, before remap); quad-pinned + fail-loud spec (WAVE3 tuple); render-only consolidate-not-drop, fail-conservative, default-OFF byte-identical | ⬜ | ⬜ |
| 6 | (table + 14-study coverage flag[s]) | TBD@build | TBD | ⬜ | ⬜ |
| 7 | PG_CONTENT_SHELL_REFETCH | `[activation] content_shell_refetch:` | TBD@build | ⬜ | ⬜ |
| 7 | PG_CROSS_SOURCE_THREAD_CONSOLIDATION | `[activation] cross_source_body:` | check | ⬜ | ⬜ |
| 7 | PG_CROSS_SECTION_REPETITION_GUARD | cross-section repetition-guard marker | TBD@build | ⬜ | ⬜ |

(Update the exact marker strings + canary-spec column as each wave commits; add Wave-6 rows at build.
Every row's RUN FIRED? must be a real count read from the run log before declaring the run good.)

## Run-day procedure (bound to this ledger)
1. Deploy committed HEAD to the VM. Confirm the slate sets PG_ACTIVATION_CANARY=1 + PG_LOG_LEVEL=INFO.
2. Small preflight run → grep the log for each row's marker → fill `preflight FIRED?`. ANY dark row → fix
   BEFORE the paid run (do not spend). Rebuild that flag's wiring, re-preflight.
3. Only when ALL preflight rows FIRED → launch the paid drb_72 run. Arm a Monitor on the run log markers.
4. During the run: forensic 5-min line-by-line read; the canary fail-louds on any dark flag.
5. After the run: fill `RUN FIRED?` from the log for every row. If the canary raised OR any row is dark →
   the run is NOT a success; do NOT score-as-final; fix + resume-from-closest-checkpoint. Only an all-FIRED,
   canary-green run gets scored + benchmarked vs GPT/Gemini.

## RUN-DAY DEPLOYMENT STATE (2026-07-07, autonomous)

- **Judge = kimi-k2.6 CONFIRMED for the paid run.** No swap needed: the benchmark path resolves the D8 Judge
  via `benchmark_verifier_lineup()` → `_BENCHMARK_LINEUP_DEFAULT_SLUG["judge"] = "moonshotai/kimi-k2.6"`
  (I-judge-kimi, 2026-06-29). The lock's `PG_JUDGE_MODEL=qwen` is the sovereign/non-benchmark default kept
  only so verify_lock + canonical-pin don't HARD-STOP; run_gate_b.py:202/433 engages the benchmark lineup, so
  the paid drb_72 run uses kimi across its 21 OpenRouter providers → no 429 → the per-claim D8 seam completes.
- **Branch pushed.** origin/bot/I-wire-001-integration = 74b91141 (15 commits incl Waves 4-9). Repo is public.
- **Box = vast 43674874 (box 2), ssh6.vast.ai:34874, 2×A100-80GB.** Chosen over box 1 (43580988, ssh9:20988)
  for more disk (127 GB free). Both were blank idle 2×A100s. Box 1 kept as a spare. Offline: 43762228.
- **Deployed:** /workspace/POLARIS @ HEAD 74b9114; `.env` (OpenRouter key set) + `launch_run.sh` staged.
  Base image: Python 3.11, CUDA 12.4, torch 2.5.1+cu124, 2 GPUs, ~1.3 TB RAM.
- **Setup in progress (agent):** install POLARIS deps + transformers + sentence-transformers + vllm + mineru
  2.5.4; start `mineru-vllm-server` on card1:30000; prove 1 real PDF extracts >500 chars.
- **launch_run.sh** loads .env → sets mineru vlm-http-client backend (:30000) → sources a100_complete_env.sh
  (2-card device split) → polaris_verify_device_pins(+_clinical) fail-loud → curl-checks the mineru server →
  `run_gate_b.py "$@"`. Preflight: `--only drb_72_ai_labor --smoke-scale --out-root outputs/preflight_smoke`.
