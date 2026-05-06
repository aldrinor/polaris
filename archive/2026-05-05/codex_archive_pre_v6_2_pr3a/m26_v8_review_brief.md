M-26 v8 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-26 v7 verdict: PARTIAL — 1 remaining bypass.

Direct SQL could `INSERT` a new clause with
`draft_id=<approved draft>, decision='pending'`. v7 froze
terminal-draft clause UPDATE and DELETE but not INSERT. The
row landed, `list_clauses` showed the new pending clause, and
`assert_approved_for_send` still passed because it only checked
`draft.status == 'approved'`.

Integrated in v8 (commit fe44702).

## What changed in v8

`contract_draft_store.py`:

Symmetric BEFORE INSERT trigger on contract_clauses:

```sql
CREATE TRIGGER IF NOT EXISTS trg_freeze_clauses_on_terminal_insert
BEFORE INSERT ON contract_clauses
FOR EACH ROW
WHEN EXISTS (
    SELECT 1 FROM contract_drafts
    WHERE draft_id = NEW.draft_id
      AND status IN ('approved', 'rejected')
)
BEGIN
    SELECT RAISE(ABORT, 'cannot insert clauses on a terminal draft (approved or rejected)');
END;
```

Terminal drafts now have NO mutable clause surface: no UPDATE,
no DELETE, no INSERT. The full set of v7+v8 freeze triggers:

  - trg_freeze_clauses_on_terminal_update
  - trg_freeze_clauses_on_terminal_delete
  - trg_freeze_clauses_on_terminal_insert  ← NEW

Tests added (2):
- test_trigger_blocks_clause_insert_on_terminal_draft_approved
  (the exact v7 repro: approve a draft, then INSERT a clause)
- test_trigger_blocks_clause_insert_on_terminal_draft_rejected
  (symmetric for REJECTED)

Module: 75/75 contract_draft_store tests green (was 73/73 in v7).

## Note

This is the 8th iteration. The cumulative defense surface:

  Layer 1 (Python public API): sanitization + state-machine
    enforcement
  Layer 2 (Python helpers `_perform_*`): hardcoded edges, no
    parameter surface (v6 structural refactor)
  Layer 3 (DB CHECK): per-row field invariants (NOT NULL +
    length() > 0)
  Layer 4 (DB triggers): cross-row invariants — closed
    transition table, all-clauses-approved, SOD,
    insert-must-start-in-draft, terminal-clause-freeze
    (UPDATE + DELETE + INSERT)

Any bypass in v8 would have to survive all four layers. The
SQL trigger surface covers every mutation path on contract_drafts
and contract_clauses; if Codex finds another, the (operation,
table, status) tuple needs to be one I haven't covered.

## Your job

Final verdict on M-26. GREEN / PARTIAL / DISAGREE.

If GREEN, M-26 v8 substrate locks AND Phase C is fully locked.

## Output

Write to `outputs/codex_findings/m26_v8_review/findings.md`:

```markdown
# Codex re-review of M-26 v8

## Verdict
GREEN / PARTIAL / DISAGREE

## v7 fix integration
- [x/no] BEFORE INSERT trigger blocks clause INSERT on terminal draft

## Final word
GREEN to lock M-26 + close Phase C / PARTIAL with edits.
```

Be terse. Under 60 lines.
