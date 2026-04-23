# Codex M-60 audit

**Verdict**: CONDITIONAL-blockers

## Answers

1. Structured metadata (rev #4): `SlotCoverageEntry` includes all 7 required fields, and the extra `section` / `subsection_title` / `doi` / `pmid` / `provenance_class` echoes make the manifest itself strong. For M-60 manifest transport: yes. For M-61 handoff as implemented here: not fully, because the task payload still omits `required_fields` or any explicit missing-field list.
2. retrieval_attempt_log passthrough: Yes. Flattening each `RetrievalAttempt` to `source` / `url` / `attempt_index` / `http_status` / `outcome` preserves the retry chain and stays JSON-safe. That is the right manifest shape for this layer.
3. Methods disclosure (rev #5): Mostly yes. `compose_methods_disclosure()` is deterministic, count-driven, and contains no hardcoded trial/publication names. The caveat is that its gap line is still hardcoded as `Unretrievable (paywalled with no OA/abstract)`, so the wording is only accurate for true unretrievable rows, not the defensive missing-`FrameRow` path.
4. human_completion_eligible logic: For intended rows, yes. `is_gap_row or status != PASS` correctly captures retrieval failures and validation/extraction failures. The caveat is the defensive missing-`FrameRow` fallback is also marked eligible, which can route a pipeline-integrity fault into M-61 human work.
5. M-61 task composition: Not sufficient as a standalone operator handoff. The task dict carries identifiers, failure context, attempts, and artifacts, but not `required_fields` / missing-field detail, despite the docstring saying M-61 needs that. The generic `needs` string is also not failure-specific.
6. Partial-count semantics: Yes, as implemented: `partial_count` is non-gap rows with non-`PASS` verdicts, and `frame_gap_count` is retrieval failure. That taxonomy is coherent. Separately, `slot.is_partial` currently has no aggregate effect.
7. Aggregate by_status: Yes. Shipping `by_status[verdict] -> int` is a reasonable pre-aggregation for dashboards and gates.
8. Determinism: Yes. For this pure function, full `FrameCoverageReport` equality is a sufficient determinism assertion; it checks the complete recursive value tree for identical inputs.
9. JSON round-trip: No JSON-incompatible types are visible in the emitted manifest shape. `to_manifest_dict()` reduces entries to plain dict/list/scalar values, and the test proves round-trip serializability.
10. Defensive fallback preference: Current preference is not ideal. If `FrameRow` is missing, that diagnosis should dominate or be prepended, because it is a stronger root-cause signal than a generic validator reason. Letting validator text win can hide a pipeline-crossed-wires condition.
11. No surface-language leak: Yes. M-60 does not define the slot-gap prose template; it only emits structured coverage and the Methods disclosure. That is the right layering.
12. Entity-type-agnostic: Yes. There is no `entity_type` branching in M-60, and the statute / `dft_primary` test demonstrates that the implementation is type-agnostic.

## Findings

- Blocker: `compose_human_completion_tasks()` does not emit `required_fields` or equivalent missing-field detail, even though the function docstring says M-61 needs `doi/pmid/required_fields/failure_reason`. The actual task payload only includes IDs, identifiers, failure context, artifacts, attempt log, and a generic `needs` string, so operator handoff is underspecified for `FAIL_MIN_FIELDS` / citation-binding failures. References: `src/polaris_graph/generator/frame_manifest.py:302`, `src/polaris_graph/generator/frame_manifest.py:315`, `tests/polaris_graph/test_m60_frame_manifest.py:460`.
- Medium: The defensive missing-`FrameRow` path is classified as `frame_gap_unrecoverable`, marked `human_completion_eligible=True`, and allowed to inherit validator wording instead of surfacing the pipeline fault first. If this path fires, M-60 can misroute a pipeline-integrity problem into M-61 human completion and can also overstate the Methods disclosure as an unretrievable/paywalled gap. References: `src/polaris_graph/generator/frame_manifest.py:173`, `src/polaris_graph/generator/frame_manifest.py:286`, `src/polaris_graph/generator/frame_manifest.py:389`, `tests/polaris_graph/test_m60_frame_manifest.py:532`.
- Nit: `slot.is_partial` is read but has no behavioral effect because the branch only executes `partial_count += 0`. If the intended taxonomy is purely verdict-based, the dead branch should be removed or clarified; if outline partiality matters, it needs a real assertion and test. References: `src/polaris_graph/generator/frame_manifest.py:193`, `src/polaris_graph/generator/frame_manifest.py:205`.
- Nit: The test header claims explicit coverage for the partial-only Methods disclosure shape, but the suite only asserts all-pass and gaps-present cases. The partial-only branch exists in code but has no direct regression test. References: `tests/polaris_graph/test_m60_frame_manifest.py:19`, `tests/polaris_graph/test_m60_frame_manifest.py:414`, `tests/polaris_graph/test_m60_frame_manifest.py:421`.

## Next

Do not proceed to M-61 yet. First add field-level operator guidance to the M-61 task payload (`required_fields` or explicit missing fields), then re-run the scoped tests; after that, Claude can proceed to M-61 (hybrid human/licensed completion — Path B).
