M-8 v4 — final GREEN check.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-8 v3 verdict: STILL-PARTIAL on one remaining flake —
`test_cancel_paused_job_via_endpoint_terminates_directly` used the
auto-start enqueue endpoint, which raced with manual `claim_pending()`.

## What changed in v4

Refactored that test to use direct `queue.enqueue()` + tmp_path /
`_set_job_*_for_tests` setup, matching the same deterministic pattern
applied to other Codex-flagged router tests in v3.

Stability: 10/10 consecutive runs, 0 failures.
Full Phase A + M-8 v4 suite: 233/233 tests pass.

## Your job

Final GREEN check. Verdict: GREEN / STILL-PARTIAL / DISAGREE.

If GREEN, M-8 is locked and Phase B can proceed to M-9 (V30 wiring
into the JobRunner abstraction).

## Output

Write to `outputs/codex_findings/m8_v4_review/findings.md`:

```markdown
# Codex final review of M-8 v4

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Final flake fix
- [x/no] test_cancel_paused_job_via_endpoint_terminates_directly de-raced

## Stability
10/10 acceptable for lock?

## Final word
GREEN to lock M-8 + proceed to M-9 / STILL-PARTIAL with edits.
```

Be terse. Under 60 lines.
