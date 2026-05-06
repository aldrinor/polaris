M-23 v1 — first review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-23 ships the human review queue + version diff for completed
audit runs. Per FINAL_PLAN Phase C deliverable #8:

  Human review queue with annotation + approval + version diff
  for each run.

This is the workflow surface a customer-facing operator uses to
gate audit-bundle delivery. A run passing M-17 (citation health,
green) and M-18 (no critical regressions) is still not "shipped"
until a human reviewer signs off via M-23.

## What changed in v1 (commit ed44e0f)

New module: `src/polaris_graph/audit_ir/review_store.py`

State machine:

    PENDING --claim()--> IN_REVIEW --approve()--> APPROVED
                                  --reject()--> REJECTED
                                  --request_changes()--> NEEDS_CHANGES

Terminal states cannot transition. Re-review is a NEW ReviewItem
at version=N+1 with `prior_review_id` set to the prior. Chain
rules:
  - prior must be NEEDS_CHANGES (not APPROVED / REJECTED)
  - prior + new must share org_id (no cross-tenant chaining)
  - prior + new must share run_slug

Cross-tenant isolation: get/list/transitions all org-scoped.
Transition methods raise `ReviewStateError` on cross-org write
attempts. The endpoint dep `require_review_*` returns 403 with
"caller does not belong to the target org" rather than 404, so
existence is not leaked.

Storage: SQLite-backed, per-call connections, WAL mode, foreign
keys, BEGIN IMMEDIATE on transitions. Audit log table
`review_transitions` is append-only — every state change writes
one row with from_status / to_status / actor_user_id / notes /
created_at.

Auth middleware: `_lookup_review_org(review_id)` does a direct
DB peek bypassing the org filter (used by the dep factory to
distinguish 404-unknown from 403-cross-org). Three new role
deps: `require_review_viewer`, `require_review_member`,
`require_review_admin`.

Endpoints (all gated):
  POST  /api/inspector/reviews                    — enqueue (member+)
  GET   /api/inspector/reviews                    — list, org-scoped
  GET   /api/inspector/reviews/{id}               — single (viewer+)
  POST  /api/inspector/reviews/{id}/claim         — pending→in_review
  POST  /api/inspector/reviews/{id}/decision      — in_review→terminal
  GET   /api/inspector/reviews/{id}/transitions   — audit log
  GET   /api/inspector/reviews/{id}/diff          — vs prior version

Decision endpoint requires non-empty notes for `rejected` /
`needs_changes`. `approved` may have empty notes (operator can
sign off without prose) — but is recommended in practice.

Diff endpoint reuses M-16's diff_runs against the prior review's
underlying audit run, returning a `{prior_review, current_review,
diff}` payload.

Tests (32):
  - 16 review_store unit tests (lifecycle, state machine, cross-
    tenant isolation, version chain, audit log, status filtering)
  - 10 endpoint integration tests (authz, cross-org returns 403,
    lifecycle, decision validation, transitions visibility,
    diff-no-prior 400)

Combined suite: 199/199 (M-16/M-17/M-18 v2/M-20/M-23).

## Your job

Verdict on M-23 v1. GREEN / PARTIAL / DISAGREE.

I'm asking you to look for:

1. **Cross-tenant isolation bypasses.** Can a caller from org_b
   list / read / claim / decide / chain to / view diffs of an
   org_a review? The dominant Phase C failure mode.
2. **State-machine bypasses.** Can a reviewer skip claim and
   directly approve? Can a NEEDS_CHANGES item be re-claimed
   instead of via re-enqueue? Can two reviewers race to claim?
3. **Re-review chain bypasses.** Can a re-review chain across
   two different runs (different run_slug)? Can the prior_review
   chain produce a cycle? Can multiple v2 reviews chain to the
   same v1 prior?
4. **Approval audit log integrity.** The transitions table is
   append-only — any way to lose a transition? Any way to write
   a transition that contradicts the current status field?
5. **Decision validation gaps.** Can a reject / needs_changes
   slip through with empty notes via creative edge cases (all
   whitespace, control characters)?
6. **Diff endpoint correctness.** Does the version diff correctly
   reuse M-16 even when the runs have different ir_schema_versions?
7. **Anything else worth flagging before M-23 locks.**

If GREEN, M-23 locks. Phase C continues to M-21 (workspace memory)
or M-19 (SOC2).

## Output

Write to `outputs/codex_findings/m23_review/findings.md`:

```markdown
# Codex review of M-23 v1

## Verdict
GREEN / PARTIAL / DISAGREE

## Cross-tenant isolation
- [list bypass attempts and results]

## State machine bypasses
- [list any]

## Re-review chain
- [list any chain bypasses]

## Audit log
- [defensible / list issues]

## Decision validation
- [defensible / list issues]

## Final word
GREEN to lock M-23 + proceed / PARTIAL with edits.
```

Be terse. Under 100 lines.
