M-26 v7 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-26 v6 verdict: PARTIAL — 3 remaining bypasses.

1. `_perform_approve` / `_perform_reject` re-checked rationale
   with `.strip()` instead of `_sanitize_notes(...)`. Repro:
   `rationale="​"` (zero-width space) → APPROVED with
   content-empty `decision_rationale`.
2. DB CHECK only enforced `IS NOT NULL` — direct SQL could write
   `status='approved', approved_by='', decision_rationale=''`.
3. Direct SQL could write canonical APPROVED metadata onto a
   draft with PENDING clauses; `assert_approved_for_send` then
   passed on an unreviewed draft.

All three integrated in v7 (commit 3a1c69b).

## What changed in v7

`contract_draft_store.py`:

**Helpers** route rationale through `_sanitize_notes`:

```python
sanitized_rationale = _sanitize_notes(rationale)
if sanitized_rationale is None:
    raise ContractDraftStateError("approval rationale must be non-empty (LAW II ...)")
rationale = sanitized_rationale
```

`_sanitize_notes` strips Unicode Cc/Cf categories + whitespace.
Zero-width spaces, ZWNJ, ZWJ, mixed Cf+space inputs all return
None.

**CHECK** now requires `length() > 0` for all NOT-NULL string
fields:

```sql
(status='approved'
  AND approved_by IS NOT NULL AND length(approved_by) > 0
  AND rejected_by IS NULL
  AND decision_rationale IS NOT NULL AND length(decision_rationale) > 0
  AND decided_at IS NOT NULL)
```

(Symmetric for REJECTED with rejected_by.)

**Triggers** encode the cross-row invariants the CHECK cannot:

- `trg_validate_status_transition` (BEFORE UPDATE OF status):
  encodes the closed transition table at SQL layer + the all-
  clauses-approved invariant + SOD. Edges:
    `draft → awaiting_approval` (requires ≥1 clause)
    `awaiting_approval → approved` (all clauses approved + SOD)
    `awaiting_approval → rejected`
  Any other (OLD.status, NEW.status) pair raises ABORT.
  Any transition INTO 'draft' is forbidden.

- `trg_validate_status_on_insert` (BEFORE INSERT): new rows
  must start in 'draft'.

- `trg_freeze_clauses_on_terminal_update` /
  `trg_freeze_clauses_on_terminal_delete` (BEFORE
  UPDATE/DELETE on contract_clauses): clauses are immutable
  once the parent draft reaches APPROVED or REJECTED. No
  retroactive flips.

The v6 bypass "direct SQL writes APPROVED with PENDING clauses"
is now blocked at the trigger layer; `assert_approved_for_send`
then sees the row never landed in APPROVED state (defense in
depth).

## Tests added (16)

- 3 helper-level zero-width-space / Cf-only rationale tests
- 2 CHECK length-check tests (empty-string approver/rationale/rejecter)
- 10 trigger tests:
  - approved-with-PENDING blocked (the exact v6 bypass)
  - approved-with-REJECTED-clause blocked
  - DRAFT → APPROVED skip blocked
  - AWAITING_APPROVAL → DRAFT (rewind) blocked
  - REJECTED → AWAITING_APPROVAL revival blocked
  - SOD via SQL (approved_by = submitter_user_id) blocked
  - Empty-draft submit via SQL blocked
  - INSERT non-draft status blocked
  - Clause UPDATE on terminal draft blocked
  - Clause DELETE on terminal draft blocked

Module: 73/73 contract_draft_store green (was 57/57 in v6).

## Your job

Final verdict on M-26. GREEN / PARTIAL / DISAGREE.

The bypass surface is now defended at three layers:
  1. Public methods sanitize rationale before dispatch
  2. Direct callers reaching `_perform_*` re-sanitize rationale
     and check state precondition
  3. SQL layer (CHECK + triggers) blocks any direct-DB attack

If GREEN, M-26 v7 substrate locks AND Phase C is fully locked.

If PARTIAL, name the specific bypass — it must reach an invariant
violation that survives all three layers.

## Output

Write to `outputs/codex_findings/m26_v7_review/findings.md`:

```markdown
# Codex re-review of M-26 v7

## Verdict
GREEN / PARTIAL / DISAGREE

## v6 fix integration
- [x/no] helpers use _sanitize_notes (zero-width-space rationale rejected)
- [x/no] CHECK enforces length() > 0 on string audit fields
- [x/no] trigger blocks direct SQL APPROVED with PENDING clauses

## Final word
GREEN to lock M-26 + close Phase C / PARTIAL with edits.
```

Be terse. Under 60 lines.
