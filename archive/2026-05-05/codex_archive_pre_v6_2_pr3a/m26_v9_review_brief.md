M-26 v9 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-26 v8 verdict: PARTIAL — 2 remaining bypasses.

1. Clause UPDATE freeze checked NEW.draft_id only. Direct SQL
   `UPDATE contract_clauses SET draft_id = <non-terminal>` moved
   a clause OFF a terminal draft (NEW.draft_id wasn't terminal,
   trigger didn't fire).
2. contract_drafts had no terminal-row freeze for non-status
   updates. Direct SQL could mutate `title`,
   `counterparty_name`, `audit_run_id` on an APPROVED row;
   `assert_approved_for_send` still passed.

Both integrated in v9 (commit 08106bf).

## What changed in v9

`contract_draft_store.py`:

**Clause UPDATE freeze tightened.** WHEN clause now checks BOTH
OLD.draft_id and NEW.draft_id:

```sql
WHEN EXISTS (
    SELECT 1 FROM contract_drafts
    WHERE (draft_id = NEW.draft_id OR draft_id = OLD.draft_id)
      AND status IN ('approved', 'rejected')
)
```

Symmetric — clauses can neither leave nor join a terminal draft.

**Drafts row freeze added.** Two new triggers:

```sql
-- Block ANY mutation on terminal rows (covers non-status paths)
CREATE TRIGGER trg_freeze_drafts_on_terminal
BEFORE UPDATE ON contract_drafts
FOR EACH ROW
WHEN OLD.status IN ('approved', 'rejected')
BEGIN
    SELECT RAISE(ABORT, 'cannot modify a terminal contract draft (approved or rejected) — terminal rows are immutable');
END;

-- Block deletion of terminal rows (preserve SOC2 audit trail)
CREATE TRIGGER trg_freeze_drafts_delete_on_terminal
BEFORE DELETE ON contract_drafts
FOR EACH ROW
WHEN OLD.status IN ('approved', 'rejected')
BEGIN
    SELECT RAISE(ABORT, 'cannot delete a terminal contract draft (approved or rejected)');
END;
```

After a draft is APPROVED or REJECTED, the row is fully
immutable — no UPDATE, no DELETE — and so are all of its clauses
(no UPDATE, no DELETE, no INSERT). The complete audit-trail row
is frozen from review-time forward.

Tests added (5):
- test_trigger_blocks_clause_move_off_terminal_draft (the v8
  repro: UPDATE clause draft_id from terminal to non-terminal)
- test_trigger_blocks_clause_move_onto_terminal_draft
- test_trigger_blocks_terminal_draft_metadata_mutation
  (covers title, counterparty_name, audit_run_id)
- test_trigger_blocks_terminal_draft_metadata_mutation_rejected
- test_trigger_blocks_terminal_draft_delete

Module: 80/80 contract_draft_store tests green (was 75/75 in v8).

## Cumulative defense surface (v9)

Layer 1 (public API): sanitization + state-machine enforcement
Layer 2 (Python `_perform_*` helpers): hardcoded edges, no
  parameter surface (v6 structural refactor)
Layer 3 (DB CHECK): per-row field invariants (NOT NULL +
  length() > 0, mutual exclusion)
Layer 4 (DB triggers):
  - trg_validate_status_transition (state machine + SOD +
    all-clauses-approved at SQL)
  - trg_validate_status_on_insert (must start in 'draft')
  - trg_freeze_clauses_on_terminal_{update,delete,insert}
    (clauses immutable on terminal drafts; UPDATE checks both
    OLD and NEW draft_id)
  - trg_freeze_drafts_on_terminal (whole row immutable on
    terminal drafts)
  - trg_freeze_drafts_delete_on_terminal (no DELETE on terminal)

## Your job

Final verdict on M-26. GREEN / PARTIAL / DISAGREE.

The mutation surface on contract_drafts and contract_clauses is
now: nothing-that-changes-the-semantics-of-an-approved-row is
reachable. If Codex finds another bypass, it must be:
  - A path I haven't covered (e.g. a different table I forgot)
  - A logic error in one of the existing triggers
  - A deeper SQLite quirk (e.g. constraint priority, ATTACH
    DATABASE escapes, RECURSIVE triggers)

If GREEN, M-26 v9 substrate locks AND Phase C is fully locked.

## Output

Write to `outputs/codex_findings/m26_v9_review/findings.md`:

```markdown
# Codex re-review of M-26 v9

## Verdict
GREEN / PARTIAL / DISAGREE

## v8 fix integration
- [x/no] clause UPDATE freeze checks both OLD and NEW draft_id
- [x/no] terminal contract_drafts rows fully immutable (no UPDATE, no DELETE)

## Final word
GREEN to lock M-26 + close Phase C / PARTIAL with edits.
```

Be terse. Under 60 lines.
