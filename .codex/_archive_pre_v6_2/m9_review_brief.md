M-9 V30 sweep wired into JobRunner abstraction — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-8 GREEN-locked (4 review rounds). Now M-9: wires the existing V30
Phase-2 sweep (`scripts/run_full_scale_v30_phase2.py` →
`run_honest_sweep_r3.main_async`) into the M-8 JobRunner abstraction.

Subprocess approach, NOT in-process refactor — V30 is ~5000 lines of
asyncio orchestration; phase-by-phase refactoring is Phase C.

## What landed

`src/polaris_graph/audit_ir/v30_runner.py`:

- **V30JobRunner(JobRunner)**, template_id="v30_clinical"
- **V30RunnerConfig**: repo_root, sweep_script, out_root, python_bin,
  poll_interval_s, cancel_grace_s, extra_env
- **12 canonical phase milestones** mapped to progress_pct [5..100]:
  scope_gate→retrieval_started→retrieval_done→adequacy_gate→
  approval_gate→generation_started→strict_verify→evaluator_gate→
  v30_phase1→v30_phase2→qwen_judge→complete
- **Phase classification** via run_log.txt substring patterns; order
  matters (M-58 / V30 Phase 2 checked before "generation")
- **Subprocess**: stdout drained on background thread, polled at
  poll_interval_s
- **Cancel**: SIGTERM → 30s grace → kill
- **Pause**: NOT supported in Phase B (no clean mid-sweep pause point
  in V30). Documented as Phase C M-13 territory.
- **Artifact resolution**: glob out_root/<domain>/<slug>/manifest.json

`inspector_router.py`: `_ensure_runners_registered` now also calls
`make_default_v30_runner()`. Exception-tolerant.

`tests/polaris_graph/test_v30_runner.py`: 10 tests using a stub sweep
script that emits canonical phase markers. Tests cover phase
classification, progress monotonicity, completion, cancel-via-SIGTERM,
nonzero exit code, missing slug, missing script, default factory,
router registration.

Tests: 233 → 243.

## Your job

Code review for M-9. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **Subprocess approach correctness.** Phase B uses subprocess.Popen
   with stdout/stderr merged and a background drain thread. Is this
   robust on Windows (where SIGTERM is not real — `proc.terminate()`
   maps to TerminateProcess)? Are there any zombies / orphaned
   processes risk?

2. **Phase classification.** Order-dependent — `v30_phase2` patterns
   (M-58, "v30 phase 2") come BEFORE generic "generation" so the
   real V30 line "V30 Phase 2: M-58 slot-bound generation" classifies
   as v30_phase2 not generation_started. Is the pattern set complete
   for the actual run-14 log file? I haven't grep'd run-14
   run_log.txt to verify.

3. **Pause not supported.** I documented that pause raises Paused
   → worker marks paused → resume re-runs from scratch. The user-
   facing UX is "pause works but resume re-starts from beginning"
   for V30. Acceptable for Phase B, or should we explicitly raise
   in V30JobRunner.run() if the queue tries to pause it (so users
   see "pause unsupported for V30" instead of getting silently
   stuck)?

4. **Checkpoint frequency.** I checkpoint per-phase (12 times) and
   in the polling loop (every poll_interval_s=1.0). On a 2h25m
   sweep that's ~8700 checkpoint calls. Each writes to SQLite. Is
   this volume an issue, or fine?

5. **Artifact resolution.** I glob for `out_root/<domain>/<slug>/`
   and pick the most-recently-modified directory with manifest.json.
   For the canonical demo this is fine, but for a Phase B with
   multiple concurrent runs (slug="X", same template launched
   twice), this picks the most-recent and may be wrong. Should I
   require the runner to capture the run_id from sweep stdout and
   resolve via that instead?

6. **Test coverage.** 10 tests using a stub script. Does that cover
   enough? I deliberately don't test against the real V30 sweep
   ($0.0074 + 2h25m × N test runs is prohibitive). Is the stub
   approach acceptable, or should I add at least one E2E live-sweep
   test gated on a PG_RUN_LIVE=1 env var?

7. **Anything else you'd push back on.**

## Output

Write to `outputs/codex_findings/m9_review/findings.md`:

```markdown
# Codex review of M-9

## Verdict
GREEN / PARTIAL / DISAGREE

## Specific issues
File:line bugs / gaps.

## Pause-unsupported handling
Should V30JobRunner explicitly reject pause requests?

## Recommended changes
If PARTIAL.

## M-10 readiness
Is the runner registry ready for the curated template router?

## Final word
GREEN to lock M-9 / PARTIAL with edits / DISAGREE.
```

Be terse. Under 250 lines.
