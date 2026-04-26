# Codex review of M-5

## Verdict
PARTIAL

## FINAL_PLAN compliance
Run-14 mostly matches the plan: 15 entries render, each row shows a declared status, and the summary bar is correct for this payload (`14 pass / 0 partial / 1 gap / 0 pipeline_fault` = ~93% green, ~7% red). The V30 `phase1_retrieval_coverage_only` warning is surfaced verbatim.

Not fully at the "literal antidote to silent omissions" bar yet: the view still hides `slot_id`, which is the canonical contract-slot key in IR. So the manifest is visibly per-entity, not explicitly per-slot.

## Specific issues
1. `scripts/static/inspector/inspector.js:776-783`, `827-887`; `scripts/static/inspector/inspector.css:916-944`
`classifyCoverageStatus()` hard-maps every `fail_min_fields` row to `gap`. Backend semantics do not guarantee that. `fail_min_fields` can be a true `partial` on non-gap rows (`tests/polaris_graph/test_m60_frame_manifest.py:322-334`). That creates a future mismatch where the summary bar can show `partial`, but the row still renders red as a gap.

2. `scripts/static/inspector/inspector.js:833-858`
`slot_id` is not rendered anywhere. For a view whose contract is "status for every contract slot," hiding the slot key is a real omission and makes Phase-B cross-view linking harder than it needs to be.

3. `scripts/static/inspector/inspector.js:866-878`; `scripts/static/inspector/inspector.css:991-1005`
`required_fields` and `available_artifacts` render as two visually identical unlabeled chip rows. Only `aria-label` differs. Sighted operators cannot reliably tell "what the contract required" from "what retrieval produced."

## Recommended changes
If keeping M-5 open:

- Render row severity from aggregate semantics, not raw status alone. At minimum, distinguish `fail_min_fields + provenance_class=frame_gap_unrecoverable` from `fail_min_fields + non-gap row`, and add a targeted render test for the partial case.
- Surface `slot_id` in the row meta now, and include it in `polaris:resolve-gap`. Phase A can keep `entity_id`, but Phase B should at least emit `{entity_id, slot_id, status, section, subsection_title}` or the full entry payload.
- Add visible labels and/or distinct chip styling for `required_fields` vs `available_artifacts`.

## M-6 readiness
Mostly yes. The IR shape is good and the render pattern is reusable for Methods + Provenance. I would fix the status-semantics mismatch and surface `slot_id` before calling the Inspector pattern fully stable across wider manifests.

## Final word
PARTIAL with edits.
