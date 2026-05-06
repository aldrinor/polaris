M-9 v3 — final GREEN check.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-9 v2 verdict: STILL-PARTIAL on one race — the initial
`control.checkpoint(progress_pct=1.0)` at runner start was unguarded.
If `request_pause` landed between that checkpoint's record_progress
write and its flag check, raw `JobControl.Paused` escaped to the
worker, which marked the job 'paused' (not 'failed'). You saw
4/10 flake on the pause test.

## What changed in v3

Wrapped the initial checkpoint in the same Paused→RuntimeError
pattern as the loop checkpoints. Three layers + outer safety net
now uniformly convert Paused → RuntimeError:
- Initial checkpoint (newly guarded)
- Per-phase checkpoint
- Periodic checkpoint
- Outer safety net

Stability: 10/10 consecutive runs of
`test_pause_request_fails_loudly_for_v30_clinical` pass.
Full suite: 246/246.

## Your job

Final verdict on M-9. GREEN / STILL-PARTIAL / DISAGREE.

If GREEN, M-9 is locked and Phase B can proceed to M-10 (curated
template router with confidence gating).

## Output

Write to `outputs/codex_findings/m9_v3_review/findings.md`:

```markdown
# Codex final review of M-9 v3

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Initial-checkpoint race fix
- [x/no] Initial checkpoint guarded with Paused → RuntimeError

## Stability
10/10 acceptable for lock?

## Final word
GREEN to lock M-9 + proceed to M-10 / STILL-PARTIAL with edits.
```

Be terse. Under 60 lines.
