# Codex M-60 audit — pass 2

**Verdict**: CONDITIONAL-blockers

## Blocker — M-61 task payload
Partially resolved. `compose_human_completion_tasks()` now emits `required_fields`, `min_fields_for_completion`, `entity_type`, `failure_reason`, and `needs`, and the new list/int fields are JSON-safe in the reviewed paths.

Still open:
- No `ValidationVerdict` status is missing from `_compose_task_needs()`, but branch order makes some guidance wrong in practice.
- A `frame_gap_unrecoverable` row with `status="pass"` is still `human_completion_eligible=True`, so it is emitted as a task, but `_compose_task_needs()` returns `no action needed` because the `pass` branch wins before the retrieval-gap branch (`frame_manifest.py:266-269`, `353-403`, `413-423`).
- `fail_gap_no_language` on a real gap row also hits the earlier RETRIEVAL branch, so the later GAP-LANGUAGE branch is effectively dead for the normal case (`frame_manifest.py:415-445`). The current test suite codifies that behavior (`test_m60_frame_manifest.py:443-475`).
- `fail_unbound_citation` is emitted into `human_gap_tasks` even though its own `needs` string says engineer intervention is required and operator intervention is not (`frame_manifest.py:376-401`, `432-437`).

## Medium — pipeline-fault path
Resolution verified in the reviewed code.
- Missing-`FrameRow` entries are classified as `provenance_class="pipeline_fault"` with `is_pipeline_fault=True`, `human_completion_eligible=False`, and a pipeline-first `failure_reason` (`frame_manifest.py:203-225`, `496-547`).
- `compose_human_completion_tasks()` has two guards, so a pipeline fault cannot be human-routed through the normal path; even a forged entry with `human_completion_eligible=True` is dropped because `is_pipeline_fault` is checked again (`frame_manifest.py:377-382`).
- Aggregation and Methods disclosure keep `pipeline_fault_count` separate from `frame_gap_count` (`frame_manifest.py:277-289`, `293-350`).

## Nits
Resolution verified.
- The dead production `slot.is_partial` branch is gone; the only remaining `is_partial` reference in these two files is the outline fixture setup in the test file.
- `TestPartialOnlyDisclosure` now locks the partial-only and pipeline-fault disclosure shapes (`test_m60_frame_manifest.py:623-666`).

## New adversarial attempts
- Input: missing `FrameRow`. Behavior: entry becomes `pipeline_fault`, not `frame_gap_unrecoverable`; no human task emitted.
- Input: forged `pipeline_fault` entry with `human_completion_eligible=True`. Behavior: still dropped from tasks because `is_pipeline_fault` is checked defensively.
- Input: `frame_gap_unrecoverable` + `status="pass"`. Behavior: task is emitted with `needs: "no action needed"`; this is contradictory for an entry still marked human-completion-eligible.
- Input: `frame_gap_unrecoverable` + `status="fail_gap_no_language"`. Behavior: task is emitted and `needs` resolves to RETRIEVAL, not GAP-LANGUAGE, because provenance check shadows the status-specific branch.
- Input: `status="fail_unbound_citation"`. Behavior: task is emitted even though `needs` says engineer action, not curator action.
- Input: `status="fail_payload_mismatch"`. Behavior: falls through to generic VALIDATION guidance; serializes cleanly.

## Residual concerns
- The blocker is not fully closed until engineer-owned statuses are excluded from `human_gap_tasks`, or `_compose_task_needs()` / `human_completion_eligible` semantics are realigned so emitted tasks always correspond to actual curator work.
- Test coverage is still missing explicit assertions for the two bad routings above: pass+gap task generation and unbound-citation task suppression.
- Regression verified: scoped V30 suite collected 233 tests and passed 233/233 with `python -m pytest`; M-60 file passed 19/19.

## Next
Hold M-61. Fix task-routing / `needs` precedence for pass-gap, `fail_gap_no_language`, and `fail_unbound_citation`, add adversarial tests for those cases, then rerun the 233-test V30 slice.
