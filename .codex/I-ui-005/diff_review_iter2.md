# Codex DIFF review — I-ui-bug-001 (#725) iter 2

HARD CAP 5. iter 2. APPROVE iff zero P0/P1. MERGE AUTHORIZED if mergeable.
Canonical-diff-sha256: `133b074afaad1f1f49f7ea16dcef5bd6d17b1f71b5c92f2a44c3844e6e955db1`. typecheck/build green.

## iter-1 P1 FIXED (your finding): lifecycle 'completed' no longer = success. Now uses run_store pipeline_status (exposed on the backend RunStatusResponse; added to the frontend TS type). VERIFIED BY VISION:
- success run → 4 cyan-check stages "Completed." (qa_v_success)
- abort_scope_rejected run → 4 grey "Did not run." NOT green (qa_v_abort)

Logic: syntheticLoss (stream_lost/unavailable event) suppressed only when lifecycleCompleted; realEventStatus (a non-synthetic run_complete event) wins; else completed → pipeline_status (??'success'); isStreamLost = syntheticLoss && !lifecycleCompleted; isSuccess = success|completed|partial_*.

2 files: web/lib/api.ts (+pipeline_status type), run_progress.tsx (terminal derivation + done-no-data "Completed.").

## Review focus
1. Does pipeline_status now correctly gate success vs abort/error for completed runs (verified both)?
2. Does a genuinely-running run whose stream drops still show stream-loss degraded (syntheticLoss && !lifecycleCompleted)?
3. Live-finished real run_complete event still authoritative?
4. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
convergence_call: continue | accept_remaining
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
remaining_blockers_for_execution: []
```
