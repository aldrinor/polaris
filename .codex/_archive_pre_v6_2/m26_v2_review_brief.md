M-26 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-26 v1 verdict: PARTIAL — 4 specific bugs.

1. TOCTOU race on approve_draft (clause snapshot before lock).
2. Direct _transition_draft bypasses all gates.
3. Cross-org existence leak in decide_clause.
4. Cross-org existence leak in _transition_draft.

All 4 integrated in v2 (commit 8b94079).

## What changed in v2

`contract_draft_store.py`:

- **Gate moved into transaction.** All gate checks (SOD,
  rationale, all-clauses-approved) now live INSIDE
  _transition_draft's BEGIN IMMEDIATE, gated on
  `to_state == APPROVED`. approve_draft is now a thin wrapper
  that just sanitizes the rationale and dispatches.

- **Direct-call bypass closed.** Because the gates are inside
  _transition_draft, a malicious caller invoking it directly
  (Python's _ prefix is convention only) cannot skip them. The
  SQL is in the same transaction as the status write — there's
  no path to APPROVED that doesn't pass through the gate.

- **TOCTOU race closed.** Clauses are re-read inside the lock,
  so a concurrent decide_clause(REJECTED) landing between snapshot
  and transition is caught — the transition fails with REJECTED.

- **Cross-org existence leak (both methods).** decide_clause and
  _transition_draft now use org-scoped lookups so unknown ID and
  cross-org both surface as "not accessible to this caller".

- **Docstring corrected.** ContractDraft no longer claims
  clause-add-time audit-IR validation that doesn't exist.

Tests added (6):
- test_direct_transition_draft_call_cannot_bypass_gate
- test_direct_transition_draft_blocks_self_approval
- test_direct_transition_draft_blocks_empty_rationale
- test_direct_transition_draft_blocks_rejected_clause (the exact
  TOCTOU repro you showed)
- test_cross_org_transition_draft_uniform_error
- test_cross_org_decide_clause_uniform_error

Tests updated: test_decide_clause_rejects_cross_org asserts the
unified "not accessible" wording.

Module: 37/37 contract_draft_store tests green; full Phase C:
419/419.

## Your job

Final verdict on M-26. GREEN / PARTIAL / DISAGREE.

If GREEN, M-26 v2 substrate locks. The renderer + LLM drafter
ship in v3 once the runner integration milestone lands.

## Output

Write to `outputs/codex_findings/m26_v2_review/findings.md`:

```markdown
# Codex re-review of M-26 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] gate checks inside BEGIN IMMEDIATE (TOCTOU closed)
- [x/no] direct _transition_draft bypass closed
- [x/no] cross-org access uniform error in both decide_clause and _transition_draft
- [x/no] docstring honest about back-link validation deferral

## Final word
GREEN to lock M-26 + proceed / PARTIAL with edits.
```

Be terse. Under 80 lines.
