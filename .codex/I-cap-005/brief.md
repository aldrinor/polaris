# I-cap-005 (#1068) — Full-capability benchmark keystone + kill every silent throttle/downgrade

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (return EXACTLY this)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context

The operator was furious: a prior benchmark run was SILENTLY throttled to ~40 fetched URLs (the operator
intended ~1000), STORM was wired-but-dead, the NLI annotation fail-opened, and these went undetected
because the tool tracker was itself off. The #1068 audit (your independent master list, `.codex/I-cap-005/
codex_audit.txt`) found the root causes. This PR is the **keystone subset** of that list: eliminate every
SILENT retrieval throttle and the fail-open NLI downgrade, and make a Gate-B run FAIL CLOSED if it is not at
full capability. The remaining #1068 items (per-feature manifest *status* stamping for STORM/agentic/depth,
`model_pin` effective_config, NLI `skipped_no_span`, rerank/backend status) are observability and are
captured as a follow-up Issue I-cap-006 — NOT in this PR.

## Root cause (verified, not hypothesised)

1. `run_gate_b_query` set the DEAD `PG_LIVE_*` names; the REAL knobs `run_one_query` reads at call-time are
   `PG_SWEEP_FETCH_CAP`/`PG_SWEEP_MAX_SERPER`/`PG_SWEEP_MAX_S2` (defaults 12/12/**40**). So the run used 40.
   Verified: `run_honest_sweep_r3.py:1771-1773`.
2. `from scripts.run_honest_sweep_r3 import run_one_query` happened BEFORE any slate, so import-time module
   constants (content cap / timeout / workers) never saw an override either.
3. STORM gated on `PG_STORM_ENABLED_IN_BENCHMARK` which Gate-B never set → dead. (`run_honest_sweep_r3.py:2003`)
4. The NLI judge fails open to `("ENTAILED", "judge_error: ...")` on API/parse error
   (`entailment_judge.py:259-261`); my annotator counted that as a genuine entailment → a degraded judge
   read as "NLI clean".
5. `state.py:217` read the typo'd env `PG_WEB_PER_ROUND`, so the documented `PG_AGENTIC_WEB_PER_ROUND` did
   nothing (agentic web breadth stuck at default 6).
6. R-6 completeness-expansion retrieval widths were HARDCODED `max_serper=5, max_s2=5, fetch_cap=15`
   (`run_honest_sweep_r3.py:2348-2350`) — a secondary throttle the slate could not lift.

## The fix (diff under review)

- **`scripts/dr_benchmark/run_gate_b.py`** — KEYSTONE:
  - `_FULL_CAPABILITY_BENCHMARK_SLATE` (correct `PG_SWEEP_*` names at 1000/100/100, `PG_STORM_ENABLED_IN_BENCHMARK=1`,
    `PG_ENABLE_TOOL_TRACKER=1`, `PG_SWEEP_EVIDENCE_DEEPENER=1`, import-time caps/timeouts/workers, evidence-extraction
    caps, `PG_MAX_COST_PER_RUN=25`, R-6 expand widths, `PG_AGENTIC_WEB_PER_ROUND=10`). Every value `setdefault`
    (LAW VI — operator override wins).
  - `apply_full_capability_benchmark_slate()` called BEFORE the `run_one_query` import (so import-time constants see it).
  - `preflight_full_capability()` called AFTER every flag is set, BEFORE any spend: raises `RuntimeError` if any
    effective `PG_SWEEP_*` is below its floor (500/50/50) or any required flag/tracker is off. Fail-closed.
- **`src/polaris_graph/retrieval/nli_benchmark_annotator.py`** — detect `reason.startswith("judge_error:")`:
  count as an error (NOT entailed), surface `judge_error_count` + `judge_errors[]`; `nli_status="error"` if EVERY
  call errored (scored==0). Added `sentences_scored`. Empty-pairs fast path carries the new keys.
- **`src/polaris_graph/state.py`** — read `PG_AGENTIC_WEB_PER_ROUND` first, legacy `PG_WEB_PER_ROUND` fallback.
- **`scripts/run_honest_sweep_r3.py`** — R-6 expansion widths now env-driven (`PG_R6_EXPAND_MAX_SERPER`/`_MAX_S2`/
  `_FETCH_CAP`, defaults preserve prior 5/5/15 for non-benchmark callers).
- **Tests**: `test_benchmark_stack_activation_meta007.py` now asserts STORM/tracker/deepener/`PG_SWEEP_*` are set
  by `run_gate_b_query` + a fail-closed preflight test; `test_nli_benchmark_annotator.py` adds judge_error +
  all-errors-→-status:error tests. 40 tests green (10 NLI + 30 Gate-B suites).

## Files I have ALSO checked and they're clean
- `run_honest_sweep_r3.py:1771-1773` — confirmed the slate's `PG_SWEEP_*` are read at CALL time inside
  `run_one_query`, so a setdefault before the call applies (no import-ordering issue for these three).
- `entailment_judge.py:356-363` — the existing telemetry helper already keys on `reason.startswith("judge_error:")`;
  my annotator now uses the same discriminator (consistent).
- `src/search/__init__.py` — the deleted `engines`/`fan_out_executor` imports are guarded (I-cap-004, committed);
  STORM + agentic search tools resolve. Not re-touched here.
- The slate is `setdefault`, so a non-benchmark caller / explicit operator env is never overridden (LAW VI).

## Acceptance criteria
1. A Gate-B run cannot reach a paid endpoint while silently throttled below the full-capability floor (preflight
   raises). 2. STORM/tracker/deepener are ON for the benchmark. 3. A degraded NLI judge surfaces as an error, never
   as "clean". 4. The typo + R-6 hardcodes no longer cap the run. 5. No non-benchmark caller behavior changes
   (all defaults preserved; slate is setdefault). 6. All edits LAW VI (env-driven), LAW II (fail loud, no silent
   downgrade).

Please review the committed diff (`.codex/I-cap-005/codex_diff.patch`) claim-by-claim against the above.
