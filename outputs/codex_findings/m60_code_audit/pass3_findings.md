# Codex M-60 audit — pass 3

**Verdict**: CONDITIONAL-no-blockers

## Pass-2 bugs closed
Verified in `src/polaris_graph/generator/frame_manifest.py:410-496` and locked by `tests/polaris_graph/test_m60_frame_manifest.py:445-545`.
- `fail_unbound_citation` + non-gap row: no task emitted.
- `fail_gap_no_language` + gap row: no task emitted.
- gap + `PASS`: no task emitted.
- `fail_payload_mismatch`: no task emitted on either gap or non-gap rows.
- `TestHumanCompletionTasks` now has explicit tests for all four cases.

## Curator-actionable cases still work
Verified.
- gap + `fail_min_fields`: emits one curator task with `needs` starting `RETRIEVAL gap` (`tests/...:445-479`).
- non-gap + `fail_min_fields`: emits one curator task with `needs` starting `EXTRACTION gap` (`tests/...:547-560`).
- Regression: scoped V30 suite passed `237/237` with `PYTHONPATH=src python -m pytest -q tests/polaris_graph/test_m54_contract_schema.py tests/polaris_graph/test_m55_frame_compiler.py tests/polaris_graph/test_m56_frame_fetcher.py tests/polaris_graph/test_m57_contract_outline.py tests/polaris_graph/test_m58_slot_fill.py tests/polaris_graph/test_m59_slot_validator.py tests/polaris_graph/test_m60_frame_manifest.py`.

## Third-round adversarial attempts
- `gap + FAIL_MISSING_PAYLOAD`: emits one curator task; `needs` is `RETRIEVAL gap`. I agree with this. Gap provenance means the curator can actually resolve it by supplying licensed content.
- `non-gap + FAIL_MISSING_PAYLOAD`: still emits one curator task, but `needs` becomes `ROUTING CHECK: ...`. That is loud and useful, but it is still the one remaining path where a likely M-58/M-61 engineer-side failure can enter the curator stream.
- `is_pipeline_fault=True`: no task emitted even when status is `fail_missing_payload`; `TestMissingFrameRowDefensive` locks this down at `tests/polaris_graph/test_m60_frame_manifest.py:621-690`.
- The `_compose_task_needs()` catch-all is a reasonable belt-and-suspenders diagnostic. It prevents silent drift between the predicate and task composer, but it does not by itself keep the curator queue pure.

## Residual concerns
- `_is_curator_actionable()` is not fully "strict": it ignores `is_gap_row` and defaults any non-`PASS`, non-engineer status to `True` (`src/polaris_graph/generator/frame_manifest.py:460-496`). Safe for today's verdict set, but future statuses would route to curator by default.
- The helper docstring is internally inconsistent: it lists `fail_payload_mismatch` as both curator-actionable and engineer-owned (`src/polaris_graph/generator/frame_manifest.py:471-474` vs `:479-482`). Behavior is correct; the comment is stale.

## Next
Claude proceeds to M-61.
