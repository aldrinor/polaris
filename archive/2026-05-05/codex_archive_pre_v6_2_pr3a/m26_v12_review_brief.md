M-26 v12 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-26 v11 verdict: PARTIAL — direct SQL UPDATE clause
decision fields bypassed decide_clause and left no audit log.

Integrated in v12 (commit 4f78987).

## What changed in v12

`contract_draft_store.py`:

  trg_log_clause_decision_change (AFTER UPDATE on contract_clauses):
    auto-writes a contract_decision_log row whenever decision
    changes. Direct SQL bypassing decide_clause now leaves a
    tamper-evident trail. decide_clause's manual log INSERT is
    removed; trigger is single source of truth.

  trg_block_decision_metadata_drift (BEFORE UPDATE on
    contract_clauses): blocks UPDATEs that change decided_by /
    decided_at / decision_notes WITHOUT changing decision.
    Attribution cannot drift without a re-decision event.

Tests: 102/102 contract_draft_store green (was 96/96 in v11).

## Threat-model boundary

After 11 review rounds, the cumulative defenses cover every
documented DML mutation path on contract_drafts and
contract_clauses. The remaining attack surface is:

  IN SCOPE for the SQL substrate:
  - Direct-SQL DML (INSERT/UPDATE/DELETE) on contract_drafts /
    contract_clauses by callers without DDL privileges.

  OUT OF SCOPE (other layers / modules):
  - DDL operations (DROP TRIGGER, ALTER TABLE, attach a fresh DB):
    require file-system + DB privileges. Not defendable from
    inside the schema; OS-level access control / encrypted
    filesystem is the right layer.
  - Identity verification of `decided_by` / `approved_by` user IDs:
    a forged actor string in those fields produces a tamper-
    evident log entry (v12 trigger), but the SQL layer cannot
    validate the user actually exists. M-15a (auth substrate) +
    anomaly detection on log entries handle this.
  - File-system tampering (corrupt/replace .sqlite file): OS
    layer.
  - Transaction-isolation exploits: SQLite's WAL + BEGIN
    IMMEDIATE handle this for in-process callers.

## Cumulative defense surface (v12)

contract_drafts:
  INSERT: must start in 'draft' (trigger)
  UPDATE OF status: closed transition table + SOD +
    all-clauses-approved (trigger)
  UPDATE (any column): row-freeze when terminal (trigger)
  DELETE: row-freeze when terminal (trigger)
  CHECK: status-vs-decision-fields invariant (NOT NULL +
    length > 0)

contract_clauses:
  INSERT: blocked once parent != 'draft' (trigger)
  UPDATE: content-immutable (trigger); draft-id-locked when
    parent non-draft (trigger); terminal-parent total freeze
    (trigger); decision-metadata-drift block (v12 trigger)
  AFTER UPDATE: auto-log decision changes (v12 trigger)
  DELETE: blocked once parent != 'draft' (trigger)
  CHECK: decision-vs-audit-fields (NOT NULL + length > 0)

## Your job

Final verdict on M-26. GREEN / PARTIAL / DISAGREE.

If GREEN, M-26 v12 substrate locks AND Phase C is fully locked.

If PARTIAL with an IN-SCOPE finding (DML on contract_drafts /
contract_clauses), name the specific (operation, table,
parameters, parent state) tuple.

If PARTIAL with an OUT-OF-SCOPE finding (DDL, adjacent-module
identity, file-system, etc.) — note that explicitly so we can
declare M-26 locked with the documented threat-model boundary.

## Output

Write to `outputs/codex_findings/m26_v12_review/findings.md`:

```markdown
# Codex re-review of M-26 v12

## Verdict
GREEN / PARTIAL / DISAGREE

## v11 fix integration
- [x/no] auto-log on clause decision change
- [x/no] decision-metadata drift blocked

## Final word
GREEN to lock M-26 / PARTIAL with edits / [out-of-scope, lock with boundary]
```

Be terse. Under 60 lines.
