# Codex M-60 audit — pass 4

**Verdict**: APPROVED

## Pass-3 residual resolution
Verified. In `src/polaris_graph/generator/frame_manifest.py`, `_is_curator_actionable` is now a strict allowlist: only `(True, fail_min_fields)`, `(True, fail_missing_payload)`, and `(False, fail_min_fields)` return `True`.
Everything else returns `False`, so unknown future verdicts default to engineer routing. The stale routing docstring is also updated to match the allowlist and the non-gap `FAIL_MISSING_PAYLOAD` realignment.
The reviewed workspace copies of the two scoped files matched commit `9ddd568`.

## Fourth-round adversarial attempts
- `gap + PASS`: still a no-op. `_is_curator_actionable(True, "pass") == False`, and `test_gap_pass_not_routed_to_curator` keeps task emission at zero.
- `non-gap + FAIL_MIN_FIELDS`: still curator-routed, but the emitted task guidance is `EXTRACTION gap`, not `RETRIEVAL gap`. Locked by `test_min_fields_fail_task_has_extraction_guidance`.
- `non-gap + FAIL_MISSING_PAYLOAD`: engineer-routed. Locked by `test_nongap_missing_payload_not_routed_to_curator`.
- `gap + FAIL_MISSING_PAYLOAD`: still curator-routed. Locked by `test_gap_missing_payload_routed_to_curator`.
- Hypothetical new verdict: defaults to engineer. Because the predicate is pure set membership, any tuple not explicitly added returns `False`; a direct check with `brand_new_verdict` returned `False` for both gap and non-gap.
- Pipeline-fault interaction: still correct. `row is None` short-circuits into `_empty_coverage_entry(...)`, sets `provenance_class="pipeline_fault"`, `is_pipeline_fault=True`, and `human_completion_eligible=False`; `compose_human_completion_tasks` also defensively skips pipeline faults. Covered by the missing-row tests.
- `is_gap_row` derivation: correct for the listed row types because it is exactly `row.provenance_class == FRAME_GAP_UNRECOVERABLE`; `ABSTRACT_ONLY`, `OPEN_ACCESS`, and `METADATA_ONLY` stay non-gap, while `FRAME_GAP_UNRECOVERABLE` is the only gap case.
- Regression: scoped V30 suite passed `239/239` with `PYTHONPATH=src` over `test_m54_contract_schema.py` through `test_m60_frame_manifest.py`.

## Residual concerns
None in the reviewed scope.

## Next
Claude proceeds to M-61.
