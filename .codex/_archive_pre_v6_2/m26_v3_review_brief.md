M-26 v3 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-26 v2 verdict: PARTIAL — 2 remaining bypasses.

1. Caller-supplied from_states could resurrect REJECTED → APPROVED.
2. Caller-supplied mark_decided/set_approver/set_rejecter could
   produce status='approved' with NULL approved_by, decided_at,
   rationale.

Both integrated in v3 (commit ea9eb0b).

## What changed in v3

`contract_draft_store.py`:

- For `to_state ∈ (APPROVED, REJECTED)`, v3 IGNORES caller-
  supplied `from_states` and forces the canonical
  `(AWAITING_APPROVAL,)`. Terminal-state resurrection is no
  longer reachable.

- For `to_state == APPROVED`: v3 forces `mark_decided=True,
  set_approver=True, set_rejecter=False` regardless of caller.
- For `to_state == REJECTED`: v3 forces `mark_decided=True,
  set_approver=False, set_rejecter=True` regardless of caller.

The result: a direct caller passing `from_states=(REJECTED,)`
or `mark_decided=False` on an APPROVED transition cannot bypass
the SOC2 audit-trail invariants. The bookkeeping is hardcoded
by `to_state`.

Tests added (3):
- test_direct_transition_cannot_resurrect_rejected_to_approved
- test_direct_transition_cannot_approve_with_mark_decided_false
  (the row IS populated despite caller's False)
- test_direct_transition_cannot_reject_without_bookkeeping
  (symmetric REJECTED case)

Module: 40/40 contract_draft_store tests green; full Phase C:
422/422.

## Your job

Final verdict on M-26. GREEN / PARTIAL / DISAGREE.

If GREEN, M-26 v3 substrate locks. The renderer + LLM drafter
ship in v4 once runner integration lands.

## Output

Write to `outputs/codex_findings/m26_v3_review/findings.md`:

```markdown
# Codex re-review of M-26 v3

## Verdict
GREEN / PARTIAL / DISAGREE

## v2 fix integration
- [x/no] from_states forced to (AWAITING_APPROVAL,) for terminal transitions
- [x/no] bookkeeping flags forced canonical for APPROVED/REJECTED

## Final word
GREEN to lock M-26 + proceed / PARTIAL with edits.
```

Be terse. Under 60 lines.
