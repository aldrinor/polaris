M-26 v13 — final re-review (lock cycle).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-26 v12 verdict: PARTIAL — direct SQL `UPDATE
contract_drafts SET status='approved', approved_by=<non-submitter>,
decision_rationale=<non-empty>, decided_at=<ts>, updated_at=<ts>`
on a row in `awaiting_approval` with all child clauses already
`approved` flipped status to APPROVED but wrote no
`contract_decision_log` row.

This is symmetric to v11's clause-decision audit-trail gap,
which v12 closed with `trg_log_clause_decision_change`.

Integrated in v13 (commit e1604a0). Per the prior advisor stop
criterion, this is the FINAL fix-and-relaunch round.

## What changed in v13

`contract_draft_store.py`:

  trg_log_draft_status_change (AFTER UPDATE OF status on
  contract_drafts): auto-writes contract_decision_log row
  whenever draft.status changes. Actor selection mirrors the
  legitimate flow:

```sql
CASE
    WHEN NEW.status = 'awaiting_approval' THEN NEW.submitter_user_id
    WHEN NEW.status = 'approved'          THEN NEW.approved_by
    WHEN NEW.status = 'rejected'          THEN NEW.rejected_by
    ELSE NEW.submitter_user_id
END
```

Manual log INSERTs removed from `_perform_submit`,
`_perform_approve`, `_perform_reject`. The trigger is the single
source of truth for status-transition log rows. `create_draft`'s
INSERT-time "created" log entry is independent (no UPDATE) and
stays.

Tests: 107/107 contract_draft_store green (was 102/102 in v12).
  - test_v13_direct_sql_draft_status_update_auto_logs
  - test_v13_legitimate_perform_{submit,approve,reject}_logs_exactly_once
  - test_v13_full_lifecycle_log_intact

## Threat-model boundary (final, applies regardless of verdict)

After 12 prior rounds the substrate exhaustively defends:

  IN SCOPE — direct-SQL DML on contract_drafts / contract_clauses:
    INSERT, UPDATE, DELETE, all parent-state combinations.

  OUT OF SCOPE:
    - DDL operations (DROP TRIGGER, ALTER TABLE)
    - Identity verification of decided_by / approved_by /
      rejected_by user IDs (M-15a's responsibility +
      anomaly detection on log entries)
    - File-system tampering of the .sqlite file
    - Transaction-isolation exploits

Cumulative defense (v13):

  contract_drafts:
    INSERT: trigger requires status='draft'
    UPDATE OF status: trigger validates closed transition table
      + SOD + all-clauses-approved
    UPDATE (any column): row-freeze when terminal
    AFTER UPDATE OF status: auto-log to contract_decision_log (v13)
    DELETE: blocked when terminal
    CHECK: status-vs-decision-fields invariants

  contract_clauses:
    INSERT: blocked once parent != 'draft'
    UPDATE: content-immutable; draft-id-locked when parent
      non-draft; terminal-parent total freeze; decision-
      metadata-drift block
    AFTER UPDATE: auto-log decision changes (v12)
    DELETE: blocked once parent != 'draft'
    CHECK: decision-vs-audit-fields invariants

## Your job

GREEN / PARTIAL / DISAGREE.

If GREEN — M-26 locks AND Phase C closes.

If PARTIAL with an in-scope DML finding — flag it, but per the
stop criterion, M-26 will lock with the finding documented as
known limitation.

If PARTIAL with out-of-scope finding — confirms the documented
threat-model boundary; M-26 locks.

## Output

Write to `outputs/codex_findings/m26_v13_review/findings.md`:

```markdown
# Codex re-review of M-26 v13

## Verdict
GREEN / PARTIAL / DISAGREE

## v12 fix integration
- [x/no] auto-log trigger on contract_drafts status changes
- [x/no] no duplicate log entries after manual INSERT removal

## Final word
GREEN to lock M-26 / PARTIAL with edits / [out-of-scope, lock with boundary]
```

Be terse. Under 60 lines.
