M-23 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-23 v1 verdict: DISAGREE — 5 specific bugs.

1. prior_review_id existence leak (BLOCKER)
2. Multiple v2 siblings on same prior (no uniqueness)
3. Version-diff endpoint loaded by run_slug not run_id
4. Same-org non-assignee can decide
5. Zero-width / control-char notes accepted

All 5 integrated in v2 (commit a871d44).

## What changed in v2

`review_store.py`:
- enqueue() prior lookup is now scoped to org_id inside
  BEGIN IMMEDIATE; cross-org and unknown-id both surface
  "prior_review_id ... is not accessible to this caller".
- enqueue() rejects multiple siblings: SELECT for sibling under
  BEGIN IMMEDIATE; raises "already has a chained review" if one
  exists.
- approve()/reject()/request_changes() now pass assignee_only=True
  to _transition; raises if assigned_to != user_id.
- New `_sanitize_notes()` drops Unicode Cc/Cf categories + all
  whitespace; rejected/needs_changes with content-empty notes
  raises "requires non-empty notes with at least one printable
  content character".

`inspector_router.py`:
- Diff endpoint uses `find_run_by_id(prior.run_id)` /
  `find_run_by_id(item.run_id)` instead of `find_run_by_slug`,
  so the diff loads the correct two underlying audit runs.

Tests added (5):
- test_chain_unknown_prior_uniform_error_does_not_leak_existence
- test_chain_does_not_allow_multiple_v2_siblings
- test_assignee_only_decision_blocks_other_member
- test_assignee_only_blocks_reject_and_request_changes
- test_zero_width_only_notes_treated_as_empty_via_endpoint

Module: 36/36 review_store tests green.

## Your job

Final verdict on M-23. GREEN / PARTIAL / DISAGREE.

If GREEN, M-23 v2 locks. Phase C continues.

## Output

Write to `outputs/codex_findings/m23_v2_review/findings.md`:

```markdown
# Codex re-review of M-23 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] prior_review_id existence leak closed
- [x/no] single-child chain enforced
- [x/no] version-diff loads runs by run_id
- [x/no] assignee-only decision enforced
- [x/no] zero-width/control-char notes rejected

## Final word
GREEN to lock M-23 + proceed / PARTIAL with edits.
```

Be terse. Under 80 lines.
