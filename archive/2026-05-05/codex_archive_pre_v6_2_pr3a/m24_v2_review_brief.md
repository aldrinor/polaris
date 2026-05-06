M-24 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-24 v1 verdict: PARTIAL — resolve() allowed
OPEN -> RESOLVED, bypassing assign() and leaving assigned_to=None.

Integrated in v2 (commit d3a9e09).

## What changed in v2

`support_ticket_store.py`:
- resolve() now requires IN_PROGRESS only (was OPEN | IN_PROGRESS).
  The lifecycle is OPEN → assign() → IN_PROGRESS → resolve().
  Operators wanting to close-without-assigning use close()
  instead, which still allows OPEN as a from-state (for won't-fix
  / duplicate scenarios).

Tests added: test_resolve_from_open_is_blocked.

Tests updated: test_reopen_clears_resolved_at now goes through
assign() before resolve() (the natural lifecycle path).

Module: 26/26 support_ticket_store tests green.

## Your job

Final verdict on M-24. GREEN / PARTIAL / DISAGREE.

The "optional follow-up: normalize cross-org mutator errors if
you want zero existence leak at the store layer" you noted in v1
was not addressed — it's a documented consistency gap, not a
bypass. Acceptable as deferred?

If GREEN, M-24 v2 locks.

## Output

Write to `outputs/codex_findings/m24_v2_review/findings.md`:

```markdown
# Codex re-review of M-24 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] resolve() requires IN_PROGRESS (no OPEN bypass)

## Final word
GREEN to lock M-24 + proceed / PARTIAL with edits.
```

Be terse. Under 60 lines.
