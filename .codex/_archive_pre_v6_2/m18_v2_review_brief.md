M-18 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-18 v1 verdict: PARTIAL with 4 specific edits.

1. Adequacy vocabulary mapping wrong (BLOCKER) — real V30 uses
   proceed/expand/abort, not pass/fail.
2. PG_REGRESSION_COST_SPIKE_RATIO not clamped to >= 1.0 (BLOCKER) —
   below-1.0 made cheaper runs trigger as cost spikes.
3. Contradiction severity escalation (RECOMMEND) — same
   (subject, predicate) low → high produced no alert.
4. Caller-supplied diff not validated (RECOMMEND) — mismatched
   diff would inject false alerts.

All 4 integrated in v2 (commit 5a97c99).

## What changed in v2

`regression_alerts.py`:
- `_check_adequacy`: passing set now includes `proceed`; failing
  set now includes `abort` and `expand`. Legacy pass/fail aliases
  retained.
- `_cost_spike_ratio()`: returns `max(1.0, raw)` so any user-
  supplied override below 1.0 is floored to 1.0 (no false-positive
  on cheaper runs).
- New `_check_contradiction_escalation(ir_a, ir_b)`: walks both
  IRs' contradictions, matches on (subject, predicate), alerts
  when severity rank increases. Severity ladder:
    -> high/critical/severe = HIGH
    -> medium/moderate = MEDIUM
  De-escalation does not alert (improvement, not regression).
  New `AlertCode.CONTRADICTION_SEVERITY_ESCALATION`.
- `detect_regressions(ir_a, ir_b, diff=...)` now validates a
  caller-supplied diff matches the IRs:
    diff.slug == ir_a.slug
    diff.a_run_id == ir_a.run_id
    diff.b_run_id == ir_b.run_id
  Mismatch raises ValueError.

Tests added (10 new):
- adequacy_proceed_to_abort_is_critical
- adequacy_proceed_to_expand_is_critical
- adequacy_legacy_pass_to_fail_still_works
- cost_spike_ratio_clamped_to_one (env override 0.5 must NOT
  alert on a cheaper run)
- contradiction_escalation_low_to_high_alerts (HIGH severity)
- contradiction_escalation_medium_to_low_does_not_alert (improvement)
- contradiction_escalation_low_to_medium_is_medium (MEDIUM)
- caller_supplied_diff_with_wrong_slug_raises
- caller_supplied_diff_with_wrong_run_ids_raises
- caller_supplied_correct_diff_does_not_recompute (sanity)

Module: 33/33 regression tests green; combined M-16/M-17/M-18 v2/
M-20/M-23: 199/199 green.

## Your job

Final verdict on M-18. GREEN / PARTIAL / DISAGREE.

If GREEN, M-18 v2 locks. Phase C continues to M-21 / M-19 / etc.

## Output

Write to `outputs/codex_findings/m18_v2_review/findings.md`:

```markdown
# Codex re-review of M-18 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] adequacy vocab covers proceed/expand/abort
- [x/no] cost-spike ratio clamped to >= 1.0
- [x/no] contradiction severity escalation detected
- [x/no] caller-supplied diff validated

## Final word
GREEN to lock M-18 + proceed / PARTIAL with edits.
```

Be terse. Under 80 lines.
