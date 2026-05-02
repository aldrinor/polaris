M-26 v5 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-26 v4 verdict: PARTIAL — 2 remaining bypasses.

1. AWAITING_APPROVAL → DRAFT was reachable (rewind submitted).
2. DRAFT → AWAITING_APPROVAL with zero clauses bypassed
   submit_for_approval's check.

Both integrated in v5 (commit d3a8fe6).

## What changed in v5

`contract_draft_store.py`:

- New `_VALID_DRAFT_TRANSITIONS` frozenset is the closed
  state-machine transition table:
    (DRAFT,             AWAITING_APPROVAL),
    (AWAITING_APPROVAL, APPROVED),
    (AWAITING_APPROVAL, REJECTED).
  Any (current, to_state) pair NOT in this set raises inside
  _transition_draft's BEGIN IMMEDIATE.
- Clause-count check moved inside the lock for AWAITING_APPROVAL
  transitions. Direct callers cannot submit empty drafts.

Tests added (3):
- test_direct_transition_cannot_revert_awaiting_to_draft
- test_direct_transition_cannot_skip_approval_queue (DRAFT →
  APPROVED)
- test_direct_transition_submit_requires_clauses

Module: 46/46 contract_draft_store tests green; full Phase C: 428/428.

## Note

This is the 5th iteration. Each round you've found a new
(parameter, value) bypass through the _transition_draft helper.
The pattern suggests the surface itself is the problem. If v5
returns PARTIAL, my next round will be a structural refactor —
replacing _transition_draft(to_state, from_states, mark_decided,
set_approver, set_rejecter) with three concrete helpers
(_perform_submit, _perform_approve, _perform_reject) plus DB
CHECK constraints for audit-trail invariants. That eliminates
the parameter surface entirely.

But for v5 specifically: GREEN if all v1..v4 fixes integrate
correctly + the closed transition table is sound.

## Output

Write to `outputs/codex_findings/m26_v5_review/findings.md`:

```markdown
# Codex re-review of M-26 v5

## Verdict
GREEN / PARTIAL / DISAGREE

## v4 fix integration
- [x/no] AWAITING_APPROVAL → DRAFT blocked by transition table
- [x/no] empty draft cannot be submitted (clause-count inside lock)

## Final word
GREEN to lock M-26 + close Phase C / PARTIAL with edits.
```

Be terse. Under 60 lines.
