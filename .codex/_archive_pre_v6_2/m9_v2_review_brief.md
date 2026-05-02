M-9 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-9 v1 verdict: PARTIAL with 3 issues:
1. Phase patterns didn't match real V30 emission format
2. Artifact identity not per-job
3. Pause-unsupported should fail loud (not silently mark paused)

All 3 integrated in v2.

## What changed

1. **Patterns rewritten** to match the canonical bracketed tags from
   run-14 run_log.txt: `[scope]`, `[retrieval]`, `[corpus]`, `[adequacy]`,
   `[completeness]`, `[contradict]`, `[select]`, `[generation]`,
   `[V30-P2]`, `[evaluator]`, `[judge]`, `[eval_gate]`, `[V30]`,
   `[cost]`, `[status]`. 15 phase keys (was 12), reordered to actual
   emission order. New regression test
   `test_classify_phase_real_run14_log` loops the checked-in run-14
   log and asserts every canonical milestone is detected.

2. **Per-job artifact root**: `out_root/<job_id>/<domain>/<slug>/`
   instead of shared `out_root/<domain>/<slug>/`. Concurrent
   same-slug reruns no longer collide. New test
   `test_concurrent_same_slug_jobs_get_isolated_artifact_dirs`
   verifies job_id appears in every artifact path.

3. **Pause fails loud**: 3 conversion sites (per-phase except,
   periodic except, outer safety-net except) convert
   `JobControl.Paused` → `RuntimeError("Pause is not supported for
   template_id='v30_clinical'...")`. Worker maps to `mark_failed`.
   New test `test_pause_request_fails_loudly_for_v30_clinical`
   verifies status=='failed' (not 'paused') with the correct error
   message after request_pause mid-run.

Tests: 243 → 246. Stub sweep emits the canonical real markers.

## Your job

Final verdict on M-9. GREEN / STILL-PARTIAL / DISAGREE.

Quick verification:
- Phase patterns recognize the real run-14 log (regression test)?
- Per-job artifact root correctly isolates same-slug reruns?
- Pause request fails loud (status='failed', clear error message)?
- Anything else?

## Output

Write to `outputs/codex_findings/m9_v2_review/findings.md`:

```markdown
# Codex re-review of M-9 v2

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Fix integration
- [x/no] Patterns match real V30 emission
- [x/no] Per-job artifact root
- [x/no] Pause fails loud

## New issues
none / list

## Final word
GREEN to lock M-9 + proceed to M-10 / STILL-PARTIAL with edits.
```

Be terse. Under 100 lines.
