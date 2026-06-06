# FX-09 (#1114) diff-gate — ITER 2 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Your iter-1 findings → fixed (the delta in iter-2)

- **P1 (real, valid)**: the v6 Dramatiq worker runs `asyncio.run(run_one_query(...))`
  (`src/polaris_v6/queue/actors.py:206`) under `--threads 2`, so two overlapping runs
  shared the process-global `_JUDGE_TELEMETRY`; my iter-1 snapshot/delta would
  cross-contaminate (dilute a degraded run OR false-abort a clean one). **FIXED:**
  per-run counter isolated via `contextvars.ContextVar` (`_RUN_JUDGE_TELEMETRY` +
  `begin_run_judge_telemetry()` in `entailment_judge.py`) — isolated per OS-thread AND
  per asyncio Task. `_record_judge_outcome` ticks BOTH the process-lifetime counter
  (health endpoint, unchanged) and the per-run dict. `run_one_query` calls
  `begin_run_judge_telemetry()` at the run boundary and reads the per-run dict directly
  (no process-global delta). Sequential calls in one context each rebind to a fresh
  dict (no reset needed for correctness).
- **P2 (abort message)**: **FIXED** — the `abort_verifier_degraded` summary now reports
  `{judge_error_count}/{judge_calls} judge calls`, not the verifier-sentence denominator.

## Evidence (offline; no spend) — diff `.codex/I-ready-017/fx09_codex_diff.patch` (vs FX-08 tip `c0d71881`)

- **Concurrency proof (killer test):** `test_per_run_scope_isolates_concurrent_threads`
  — 2 threads through a `threading.Barrier` (A: 245 calls/30 err; B: 100 calls/5 err);
  asserts each thread's per-run dict has ONLY its own counts. With the old
  process-global this cross-contaminates. PASS.
- 7 FX-09 tests pass (helper denominator; per-run scope counts only this run; snapshot
  stability; second-run-scope-resets; degraded-trip 30/245>cap vs 30/702<cap; zero-calls
  guard; **thread isolation**). Regression `test_feature_firing_telemetry_iready005` +
  `test_manifest_contract` → 28 passed. Both modified files parse.
- §-1.1 (iter-1, still valid): real held `verification_details.json` denominator was 702
  (281 no_provenance drops never reach the judge); worst-case 30/702=0.043 ships vs
  ~30/245=0.122 aborts.

## Faithfulness check
Strengthens the binding degraded-verifier abort AND removes a concurrency hazard that
could have diluted/false-fired it. The process-lifetime counter (health endpoint) is
unchanged. No grounding / strict_verify / 4-role change.

## Note
The 68 pytest collection errors in `tests/polaris_graph/scope/` + `sovereignty/` are the
pre-existing `No module named 'polaris_graph'` bare-import issue (PYTHONPATH), unrelated
to this change (my code uses the `src.`-prefixed import path).

## Question
Is the per-run telemetry now correctly isolated for the concurrent v6 worker path (no
cross-contamination), faithfulness-strengthening, with the abort message fixed? Anything
blocking?
