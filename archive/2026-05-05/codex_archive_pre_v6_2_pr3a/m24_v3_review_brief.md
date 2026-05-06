M-24 v3 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-24 v2 verdict: PARTIAL — bypass remains:
  OPEN -> close() -> reopen() -> resolve()
left a RESOLVED ticket with assigned_to=None.

Integrated in v3 (commit 77f4660).

## What changed in v3

`support_ticket_store.py`:
- New `require_assignee` flag on `_mutate`. When True, transition
  refuses if `assigned_to` is None.
- `resolve()` now passes `require_assignee=True` so a re-opened
  ticket without an assignee cannot reach RESOLVED.

Tests added: test_resolve_after_close_reopen_blocked_when_no_assignee
exercises the exact bypass chain Codex described.

Module: 27/27 support_ticket_store tests green.

## Your job

Final verdict on M-24. GREEN / PARTIAL / DISAGREE.

If GREEN, M-24 v3 locks.

## Output

Write to `outputs/codex_findings/m24_v3_review/findings.md`:

```markdown
# Codex re-review of M-24 v3

## Verdict
GREEN / PARTIAL / DISAGREE

## v2 fix integration
- [x/no] resolve() refuses RESOLVED when assigned_to is None
- [x/no] close → reopen → resolve bypass closed

## Final word
GREEN to lock M-24 + proceed / PARTIAL with edits.
```

Be terse. Under 60 lines.
