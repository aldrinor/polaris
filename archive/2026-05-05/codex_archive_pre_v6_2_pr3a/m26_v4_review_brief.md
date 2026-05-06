M-26 v4 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-26 v3 verdict: PARTIAL — 2 remaining bypasses.

1. Direct `to_state=AWAITING_APPROVAL, from_states=(REJECTED,)`
   could revive a terminal REJECTED draft.
2. Direct `to_state=REJECTED, rationale=None` produced
   status=rejected with decision_rationale=NULL.

Both integrated in v4 (commit 3f1524d).

## What changed in v4

`contract_draft_store.py`:

- **Terminal states truly terminal.** When to_state is NOT
  terminal (i.e. NOT APPROVED/REJECTED), v4 strips
  {APPROVED, REJECTED} from the caller's from_states. If
  nothing remains, raises "cannot transition out of a terminal
  state." A direct caller cannot revive REJECTED back to
  AWAITING_APPROVAL or APPROVED back to DRAFT.

- **REJECTED requires rationale inside _transition_draft.**
  Symmetric to the APPROVED rationale check. A direct
  _transition_draft(to_state=REJECTED, rationale=None) call
  raises "rejection rationale must be non-empty" — the public
  reject_draft check is now mirrored at the lock level.

Tests added (3):
- test_direct_transition_cannot_revive_rejected_to_awaiting
- test_direct_transition_cannot_revive_approved_to_draft (symmetric)
- test_direct_transition_reject_requires_rationale (None +
  whitespace-only both rejected)

Module: 43/43 contract_draft_store tests green; full Phase C: 425/425.

## Your job

Final verdict on M-26. GREEN / PARTIAL / DISAGREE.

If GREEN, M-26 v4 substrate locks AND Phase C is fully locked.
The renderer + LLM drafter ship in v5 once runner integration
lands.

## Output

Write to `outputs/codex_findings/m26_v4_review/findings.md`:

```markdown
# Codex re-review of M-26 v4

## Verdict
GREEN / PARTIAL / DISAGREE

## v3 fix integration
- [x/no] terminal states cannot be revived
- [x/no] REJECTED requires rationale inside _transition_draft

## Final word
GREEN to lock M-26 + close Phase C / PARTIAL with edits.
```

Be terse. Under 60 lines.
