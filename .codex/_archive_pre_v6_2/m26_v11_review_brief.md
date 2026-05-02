M-26 v11 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-26 v10 verdict: PARTIAL — 3 bypasses on contract_clauses
during the AWAITING_APPROVAL window:

1. INSERT forged 'decision=approved' clause (with valid
   decided_by/decided_at) → approve_draft saw fully-approved
   clause set and approved.
2. DELETE rejected clause → rejection vanished.
3. UPDATE draft_id moves rejected clause to another non-terminal
   draft → same effect.

All three integrated in v11 (commit d22abf9).

## What changed in v11

`contract_draft_store.py`:

The clause-mutation freeze conditions are expanded from "parent
terminal" to "parent != 'draft'":

```sql
-- Was: status IN ('approved','rejected'); now: status != 'draft'
CREATE TRIGGER trg_freeze_clauses_after_submit_insert
BEFORE INSERT ON contract_clauses
WHEN EXISTS (
    SELECT 1 FROM contract_drafts
    WHERE draft_id = NEW.draft_id AND status != 'draft'
)
BEGIN RAISE(ABORT, 'cannot insert clauses once parent draft is submitted'); END;

CREATE TRIGGER trg_freeze_clauses_after_submit_delete
BEFORE DELETE ON contract_clauses
WHEN EXISTS (
    SELECT 1 FROM contract_drafts
    WHERE draft_id = OLD.draft_id AND status != 'draft'
)
BEGIN RAISE(ABORT, 'cannot delete clauses once parent draft is submitted'); END;

-- NEW: lock draft_id changes once parent is non-draft
CREATE TRIGGER trg_lock_clause_draft_id_after_submit
BEFORE UPDATE OF draft_id ON contract_clauses
WHEN OLD.draft_id != NEW.draft_id
     AND EXISTS (
         SELECT 1 FROM contract_drafts
         WHERE (draft_id = OLD.draft_id OR draft_id = NEW.draft_id)
           AND status != 'draft'
     )
BEGIN RAISE(ABORT, 'cannot move clauses to or from a submitted contract'); END;
```

The terminal-update trigger remains unchanged (still blocks all
UPDATEs on terminal-parent clauses). decide_clause's UPDATE only
touches decision metadata (not draft_id, not body), so it
continues to work during AWAITING_APPROVAL.

## Tests added (5)

- test_trigger_blocks_clause_insert_during_awaiting_approval
  (the v10 (a) repro: forged approved clause + approve_draft
  attempt fails)
- test_trigger_blocks_clause_delete_during_awaiting_approval
  (the v10 (b) repro: delete rejected clause + verify
  approve_draft still refuses)
- test_trigger_blocks_clause_move_during_awaiting_approval
  (the v10 (c) repro: move REJECTED clause off AWAITING parent
  to a separate DRAFT parent)
- test_trigger_blocks_clause_move_into_awaiting_approval
  (symmetric: inject clause from DRAFT parent into AWAITING
  parent)
- test_full_clause_protection_during_awaiting (end-to-end:
  all four mutation paths checked + decide_clause works)

Module: 96/96 contract_draft_store tests green (was 91/91 in v10).

## Cumulative defense surface (v11)

contract_drafts:
  INSERT: must start in 'draft' (trigger)
  UPDATE OF status: closed transition table + SOD +
    all-clauses-approved (trigger)
  UPDATE (any column): blocked when OLD.status terminal
    (row-freeze trigger)
  DELETE: blocked when OLD.status terminal (trigger)
  CHECK: status-vs-decision-fields (NOT NULL + length > 0)

contract_clauses:
  INSERT: blocked once parent != 'draft' (v11 trigger)
  UPDATE: content immutable (trigger); blocked when
    OLD or NEW parent terminal (terminal trigger);
    draft_id locked when OLD or NEW parent != 'draft' (v11 trigger)
  DELETE: blocked once parent != 'draft' (v11 trigger)
  CHECK: decision-vs-audit-fields (NOT NULL + length > 0)

The clause set attached to a non-DRAFT parent is now
**identity-frozen**: no INSERT, no DELETE, no draft_id changes.
Only decision metadata (decided_by, decided_at, decision_notes)
can change, and only during AWAITING_APPROVAL via decide_clause.
Once the parent goes terminal, even decision metadata is frozen.

## Your job

Final verdict on M-26. GREEN / PARTIAL / DISAGREE.

If GREEN, M-26 v11 substrate locks AND Phase C is fully locked.

If PARTIAL, name the specific bypass — it must reach an
invariant violation that survives all defense layers (Python
public API, hardcoded `_perform_*` helpers, DB CHECK,
DB triggers).

## Output

Write to `outputs/codex_findings/m26_v11_review/findings.md`:

```markdown
# Codex re-review of M-26 v11

## Verdict
GREEN / PARTIAL / DISAGREE

## v10 fix integration
- [x/no] clause INSERT blocked once parent draft is submitted
- [x/no] clause DELETE blocked once parent draft is submitted
- [x/no] clause draft_id move blocked once either parent is non-draft

## Final word
GREEN to lock M-26 + close Phase C / PARTIAL with edits.
```

Be terse. Under 60 lines.
