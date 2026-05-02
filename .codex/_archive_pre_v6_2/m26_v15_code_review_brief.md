M-26 v15 code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Post-lock doc audit found that `contract_decision_log` was not
actually append-only. v15 added two triggers to enforce it:

```sql
CREATE TRIGGER IF NOT EXISTS trg_decision_log_no_update
BEFORE UPDATE ON contract_decision_log FOR EACH ROW
BEGIN SELECT RAISE(ABORT, 'append-only ...'); END;

CREATE TRIGGER IF NOT EXISTS trg_decision_log_no_delete
BEFORE DELETE ON contract_decision_log FOR EACH ROW
BEGIN SELECT RAISE(ABORT, 'append-only ...'); END;
```

Plus 3 new tests (test_v15_*) at
`tests/polaris_graph/test_contract_draft_store.py`.

Commit: 77b132c. Module: 112/112 tests pass.

## Your job

GREEN / PARTIAL / DISAGREE on v15.

Same threat model as the v1-v14 substrate (DDL out of scope,
identity validation out of scope, file-system out of scope).
In-scope: direct-SQL DML attacks on `contract_decision_log`.

Specifically check:
1. Do the two triggers actually fire on every UPDATE / DELETE
   path including UPDATE of any single column, partial-row
   UPDATE, DELETE with subqueries, etc.?
2. Is `INSERT` the only mutation that should be allowed? Are
   there legitimate UPDATE/DELETE operations the code does
   anywhere that v15 now breaks?
3. Does the v15 test suite actually cover the new bypass class
   the original doc audit found?
4. Does v15 close any gap on the v14 substrate's claims, or
   create a new one?

## Output

Write to `outputs/codex_findings/m26_v15_review/findings.md`:

```markdown
# Codex re-review of M-26 v15

## Verdict
GREEN / PARTIAL / DISAGREE

## Findings
- [bypass on log-table mutation, if any]
- [legitimate path now broken, if any]
- [test coverage gap, if any]
- [gap created elsewhere, if any]

## Final word
GREEN to lock v15 / PARTIAL with edits / DISAGREE with [thesis].
```

Be terse. Under 60 lines.
