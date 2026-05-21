# Codex DIFF review — I-ui-bug-001 (#725) completed-run render fix

HARD ITERATION CAP: 5. iter 1. P0/P1 for real execution risks only. APPROVE iff zero P0/P1. Final line MERGE AUTHORIZED if mergeable. web/ only, 1 file.

Canonical-diff-sha256: `9d4e3705e14591a7f5b99f01f352354f9157140c316f3bb4ffc2304eb9e8497c`. typecheck/build green. VISUALLY VERIFIED by re-screenshot (completed run: 4 cyan-check stages all "Completed.", no "connection lost" banner — qa_run_done.png).

## Bug (found by visual QA, missed by code review + the 5-iter #707 brief review)
Opening a COMPLETED run rendered as broken: "Live connection lost" + 4 stages "Not observed (stream lost)". A finished run has no live SSE to replay → #706 STREAM_LOST_GRACE emits synthetic run_complete{stream_lost} → it overrode run_store 'completed'.

## Fix (run_progress.tsx only)
- lifecycleCompleted = status?.status === "completed"; isSuccess includes it; isStreamLost = !lifecycleCompleted && stream_lost. → run_store status authoritative over the synthetic stream artifact.
- StageBody: state==="done" with no replayed event data → "Completed." (not active placeholders). Live-finished runs with data fall through to the real feed.

## Review focus
1. Is lifecycle-completed-authoritative correct, and does it correctly NOT mask a genuinely-still-running run whose stream dropped (stream_lost only when !lifecycleCompleted)?
2. Does the done-no-data → "Completed." guard preserve the live-run-with-data feed (falls through when data present)?
3. Any regression to the live-watch path (non-terminal stages still active/pending; success terminal still all-done)?
4. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
remaining_blockers_for_execution: [...]
```
