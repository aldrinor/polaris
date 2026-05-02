M-26 v10 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-26 v9 verdict: PARTIAL — 2 remaining bypasses on
contract_clauses during AWAITING_APPROVAL.

1. Direct SQL `UPDATE contract_clauses SET decision='approved'`
   left no decided_by/decided_at audit trail. DB didn't bind
   non-PENDING decisions to review attribution.
2. An already-approved clause's body/title/evidence_ids could be
   rewritten via direct SQL between submit and final approval —
   the shipped contract differed from what the reviewer signed
   off on.

Both integrated in v10 (commit 4444488).

## What changed in v10

`contract_draft_store.py`:

**CHECK constraint on contract_clauses** binds decision values to
their canonical audit-trail metadata:

```sql
CHECK (
    (decision = 'pending'
        AND decided_by IS NULL AND decision_notes IS NULL
        AND decided_at IS NULL)
    OR
    (decision = 'approved'
        AND decided_by IS NOT NULL AND length(decided_by) > 0
        AND decided_at IS NOT NULL)
    OR
    (decision = 'rejected'
        AND decided_by IS NOT NULL AND length(decided_by) > 0
        AND decided_at IS NOT NULL
        AND decision_notes IS NOT NULL AND length(decision_notes) > 0)
)
```

**`trg_clause_content_immutable`** (BEFORE UPDATE on
contract_clauses): clause content is immutable from INSERT-time
onward.

```sql
WHEN NEW.title != OLD.title
     OR NEW.body != OLD.body
     OR NEW.evidence_ids_json != OLD.evidence_ids_json
     OR NEW.claim_ids_json != OLD.claim_ids_json
BEGIN
    SELECT RAISE(ABORT, 'clause title/body/evidence are immutable after creation — only decision metadata may change via decide_clause');
END;
```

There is no public "edit clause body" API — `add_clause` is the
only path that writes content, and `decide_clause` only updates
decision metadata. The trigger matches this contract.

The single-statement combined attack (UPDATE flips decision AND
rewrites body in the same SQL statement) is also blocked — the
trigger fires on body change regardless of OLD.decision.

Tests added (11):
- 5 clause CHECK tests:
  - approved without decided_by → CHECK fails
  - approved with empty-string decided_by → CHECK fails
  - approved without decided_at → CHECK fails
  - rejected without decision_notes → CHECK fails
  - pending with decision metadata → CHECK fails
- 5 immutability tests:
  - body rewrite after creation (pre-decision)
  - body rewrite after decide_clause(APPROVED) (the v9 repro)
  - title rewrite
  - evidence_ids_json + claim_ids_json rewrite
  - combined single-UPDATE: flip decision + rewrite body
- 1 sanity test: legitimate decide_clause flow still works

Module: 91/91 contract_draft_store tests green (was 80/80 in v9).

## Cumulative defense surface (v10)

The mutation surface is now exhaustively constrained:

  contract_drafts:
    - INSERT: must start in 'draft' (trigger)
    - UPDATE OF status: closed transition table + SOD +
        all-clauses-approved (trigger)
    - UPDATE (any column): blocked when OLD.status terminal
        (row-freeze trigger)
    - DELETE: blocked when OLD.status terminal (trigger)
    - Per-row CHECK: status-vs-decision-fields invariant
        (NOT NULL + length > 0)

  contract_clauses:
    - INSERT: blocked on terminal parent draft (trigger)
    - UPDATE: clause content immutable (trigger); blocked when
        OLD.draft_id or NEW.draft_id is terminal (trigger)
    - DELETE: blocked on terminal parent draft (trigger)
    - Per-row CHECK: decision-vs-audit-fields invariant
        (NEW v10)

## Your job

Final verdict on M-26. GREEN / PARTIAL / DISAGREE.

Every documented mutation path on both tables now has an
invariant binding it. If Codex finds another bypass, it must
involve:
  - A path I still haven't considered (different table, ATTACH
    DATABASE, raw VFS, etc.)
  - A trigger logic error (e.g. WHEN clause that misses an edge)
  - A CHECK that has an unreachable OR-branch admitting an
    illegal pattern

If GREEN, M-26 v10 substrate locks AND Phase C is fully locked.

## Output

Write to `outputs/codex_findings/m26_v10_review/findings.md`:

```markdown
# Codex re-review of M-26 v10

## Verdict
GREEN / PARTIAL / DISAGREE

## v9 fix integration
- [x/no] CHECK binds clause decision to decided_by + decided_at + notes
- [x/no] clause body/title/evidence are immutable after INSERT

## Final word
GREEN to lock M-26 + close Phase C / PARTIAL with edits.
```

Be terse. Under 60 lines.
