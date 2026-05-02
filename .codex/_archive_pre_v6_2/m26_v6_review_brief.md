M-26 v6 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-26 v5 verdict: PARTIAL — 1 remaining bypass.

`_transition_draft(... to_state=AWAITING_APPROVAL,
mark_decided=True, set_approver=True | set_rejecter=True)` still
wrote decision metadata onto a merely submitted draft. The
closed `(current, to_state)` table was sound, but the helper
permitted non-canonical audit fields on `DRAFT → AWAITING_APPROVAL`.

After 5 rounds where each round found a new (parameter, value)
bypass on the parameterized helper, v6 ships a structural
refactor (commit 33045fa).

## What changed in v6

`contract_draft_store.py`:

**The parameterized helper is GONE.** `_transition_draft(to_state,
from_states, mark_decided, set_approver, set_rejecter)` no longer
exists. The transition surface is now three hardcoded helpers,
one per legal edge:

  - `_perform_submit`  : DRAFT             → AWAITING_APPROVAL
  - `_perform_approve` : AWAITING_APPROVAL → APPROVED
  - `_perform_reject`  : AWAITING_APPROVAL → REJECTED

Each helper hardcodes its specific edge:
  - No `to_state` parameter — the helper name IS the target state.
  - No `from_states` parameter — the legal source state is
    enforced by `if current != ContractDraftStatus.X: raise`.
  - No `mark_decided` / `set_approver` / `set_rejecter` flags —
    each helper writes the canonical metadata pattern for its
    specific edge. `_perform_submit` only flips status (decision
    fields stay NULL). `_perform_approve` writes
    `approved_by + decided_at + decision_rationale, rejected_by=NULL`.
    `_perform_reject` writes the symmetric REJECTED pattern.

**DB-level CHECK constraints** on `contract_drafts` encode the
SOC2 audit-trail invariants:

```sql
CHECK (
    (status='draft'             AND approved_by IS NULL AND rejected_by IS NULL
        AND decision_rationale IS NULL AND decided_at IS NULL)
    OR
    (status='awaiting_approval' AND approved_by IS NULL AND rejected_by IS NULL
        AND decision_rationale IS NULL AND decided_at IS NULL)
    OR
    (status='approved'          AND approved_by IS NOT NULL AND rejected_by IS NULL
        AND decision_rationale IS NOT NULL AND decided_at IS NOT NULL)
    OR
    (status='rejected'          AND approved_by IS NULL AND rejected_by IS NOT NULL
        AND decision_rationale IS NOT NULL AND decided_at IS NOT NULL)
);
```

Even direct SQL UPDATEs that violate these patterns fail at the
SQL layer. The Python helpers + the DB constraints form
defense-in-depth: helpers maintain invariants during normal
operation, constraints catch any bug or future contributor who
bypasses the helpers.

The v5 bypass is closed at TWO layers:
  1. **Structural**: `_perform_submit` has no `mark_decided` /
     `set_approver` parameter to exploit.
  2. **DB layer**: even if someone hand-crafts an UPDATE setting
     `status='awaiting_approval', approved_by='bob', decided_at=N`,
     the CHECK fires with `IntegrityError`.

## Tests added

11 new direct-call tests covering each `_perform_*` helper:
- `_perform_submit`: requires clauses, blocked from non-DRAFT,
  blocked from terminal, doesn't write decision metadata,
  cross-org uniform error
- `_perform_approve`: blocks PENDING/REJECTED clauses, SOD,
  empty rationale, only-from-AWAITING, blocked from terminal,
  cross-org uniform, writes canonical metadata
- `_perform_reject`: requires rationale, only-from-AWAITING,
  blocked from terminal, cross-org uniform, writes canonical
  metadata

6 new DB CHECK constraint tests (direct SQL UPDATE attacks):
- approved with NULL approver → IntegrityError
- approved with rejected_by set → IntegrityError (mutual exclusion)
- rejected with NULL rejecter → IntegrityError
- draft with decision metadata → IntegrityError
- awaiting_approval with decision metadata → IntegrityError (the
  exact v5 bypass blocked at SQL)
- invalid status value → IntegrityError

1 dead-code test: `_transition_draft` no longer exists.

Module: 57/57 contract_draft_store tests green (was 46/46 in v5).
Full repo: 2543 passed; 19 failures are V30/V28 work pre-existing
(unrelated to Phase C).

## Your job

Final verdict on M-26. GREEN / PARTIAL / DISAGREE.

If GREEN, M-26 v6 substrate locks AND Phase C is fully locked.

If PARTIAL, name the specific bypass and the (operation,
state-or-data) tuple that produces an invalid invariant. The
parameter surface is gone; any remaining bypass would have to
be in:
  - one of the three `_perform_*` helpers' invariant logic
  - the public `decide_clause` / `add_clause` / `create_draft` paths
  - the DB CHECK constraint definitions (e.g. an unreachable
    OR-branch that allows an illegal pattern)

## Output

Write to `outputs/codex_findings/m26_v6_review/findings.md`:

```markdown
# Codex re-review of M-26 v6

## Verdict
GREEN / PARTIAL / DISAGREE

## v5 fix integration
- [x/no] _transition_draft removed
- [x/no] three concrete _perform_* helpers each hardcode one edge
- [x/no] DB CHECK constraints enforce status/decision-field invariants

## Final word
GREEN to lock M-26 + close Phase C / PARTIAL with edits.
```

Be terse. Under 60 lines.
