# FX-09 §-1.1 audit — judge_error_rate denominator = actual judge calls (I-ready-017 #1114)

**Standard:** §-1.1 on the REAL held drb_72 `verification_details.json`.

## The bug (BUG-05)
`judge_error_rate` divided by ALL verifier-checked sentences, but the entailment
judge only runs on the subset that passes every mechanical strict_verify check
first — so the #1071 binding `abort_verifier_degraded` gate was diluted.

## Real held-run data (`verification_details.json`)
- OLD denominator (`judge_error_sentences_checked`) = **702** (kept 176 + dropped 526)
- `drop_reason_counts`: `no_provenance_token=281`, `no_integer_overlap_any_cited_span=155`,
  `no_content_word_overlap_any_cited_span=24`, `number_not_in_any_cited_span=3`,
  `entailment_failed=69`.
- The 281 `no_provenance_token` drops (and the other mechanical drops) NEVER reach the
  judge. `entailment_failed=69` ARE judge calls (judge ran, said "not entailed"). So the
  judge-eligible population is FAR below 702.
- Held run had `judge_error_count=0` → rate 0 either way (the bug wasn't *triggered*, but
  the dilution *structure* was present).

## Worst-case proof (the dilution that the fix removes)
A degraded judge with 30 errors:
- OLD: 30/702 = **0.043** < 0.10 cap → **SHIPS** (degraded judge masked) ❌
- NEW: ~30/245 = **0.122** > 0.10 cap → **ABORTS** (`abort_verifier_degraded` fires) ✅

## The fix
denominator = actual judge invocations this run = delta of the process-lifetime
`entailment_judge.get_judge_telemetry()['calls']` (snapshot at the run boundary,
never reset — reentrant). Numerator = `telemetry['judge_error']` delta (counts errors
even on KEPT sentences that failed open, which the reason-grep under-counts). The
kept+dropped count is retained as `verifier_sentences_checked` CONTEXT only
(`judge_error_sentences_checked` kept as a back-compat alias). Extracted a pure helper
`_judge_calls_and_errors_from_telemetry` for testability.

## Faithfulness-strengthening, not weakening
This makes the binding degraded-verifier abort FIRE when it should (un-dilutes the
gate). No grounding/strict_verify/4-role change. Telemetry-unavailable fallback keeps
the gate fail-functional (old reason-grep rate), never silently inert.

## Offline smoke
`pytest tests/polaris_graph/test_fx09_judge_error_rate_iready017.py` → **6 passed**
(N/245-not-N/702; real-telemetry delta via `_record_judge_outcome`; snapshot stability;
process-lifetime second-run-uses-only-its-delta; degraded-trip boundary 30/245>cap vs
30/702<cap; zero-calls no div-by-zero). Regression: `test_feature_firing_telemetry_iready005`
+ `test_manifest_contract` → 21 passed. `run_honest_sweep_r3.py` parses.

---

## iter-2 (Codex iter-1 RC: 1 P1 + 1 P2 → fixed)

**P1 (real, valid):** the v6 Dramatiq worker runs `asyncio.run(run_one_query(...))`
(`actors.py:206`) under `--threads 2`, so two overlapping runs share the process-global
`_JUDGE_TELEMETRY`. The iter-1 snapshot/delta would cross-contaminate — diluting a
degraded run below the abort OR false-aborting a clean one. **FIXED:** per-run counter
isolated via a `contextvars.ContextVar` (`_RUN_JUDGE_TELEMETRY` +
`begin_run_judge_telemetry()`), isolated per OS-thread AND per asyncio Task. The judge
ticks both the process-lifetime counter (health endpoint, unchanged) and the per-run
dict; `run_one_query` reads the per-run dict directly (no global delta). Sequential
calls in one context each rebind to a fresh dict (no reset needed).

**P2 (abort message):** **FIXED** — the `abort_verifier_degraded` summary now reports
`{judge_error_count}/{judge_calls} judge calls`, not the verifier-sentence denominator.

**Concurrency proof (the killer test):** `test_per_run_scope_isolates_concurrent_threads`
runs 2 threads through a `Barrier` (245 calls/30 err vs 100 calls/5 err) and asserts each
thread's per-run dict has ONLY its own counts. With the old process-global this would
cross-contaminate. PASS.

**Offline smoke:** 7 FX-09 tests (helper denominator; per-run scope counts only this
run; snapshot stability; second-run-scope-resets; degraded-trip; zero-calls; **thread
isolation**). Regression: `test_feature_firing_telemetry_iready005` +
`test_manifest_contract` → 28 passed total. Both modified files parse. (The 68
collection errors in scope/ + sovereignty/ are the pre-existing `No module named
'polaris_graph'` bare-import issue, unrelated to this change.)
