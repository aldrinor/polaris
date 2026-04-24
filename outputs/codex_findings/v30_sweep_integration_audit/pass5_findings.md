# Codex V30 sweep integration audit — pass 5

**Verdict**: APPROVED

## Pass-4 blockers resolved
- Blocker 1 verified in `src/polaris_graph/v30_sweep_integration.py`: `methods_disclosure_text` now starts with `PHASE-1 RETRIEVAL COVERAGE ...`, explicitly says it does not claim the legacy generator cited each entity in the verified report, points to Phase 2, and `append_disclosure_to_report(...)` uses `## V30 Phase-1 Retrieval Coverage Disclosure`.
- Blocker 2 verified in `src/polaris_graph/v30_sweep_integration.py`: `_row_has_retrieval_evidence(row)` now matches the requested guard. Direct exercise confirmed `quote -> True`, `oa_only -> True`, `empty/no_oa -> False`, `None -> False`, `HUMAN_CURATED -> True`.
- Blocker 3 verified in `tests/polaris_graph/test_v30_sweep_integration.py`: happy-path assertions now require the standing `phase1_retrieval_coverage_only` warning and the Phase-1 disclosure preamble. The file contains 20 `test_` cases, including the two degraded-row additions.

## Fifth-round adversarial attempts
- Manifest/report overclaim surface: no blocker found in the audited code. The report surface is now explicitly Phase-1 retrieval-only before the inherited M-60 prose is appended.
- False-pass probe on degraded rows: no blocker found. A non-gap row with empty `direct_quote` and no `oa_pdf_url` now falls to `FAIL_MIN_FIELDS`; a direct manual run produced `pass_count=0` and `fail_min_fields=15`.
- Edge case `HUMAN_CURATED` + empty `direct_quote`: `_row_has_retrieval_evidence` would still return `True` because human-curated rows short-circuit. Given the stated M-61 parse invariant rejecting empty quotes, this is an invariant dependency, not a live blocker.

## Residual concerns
- `frame_coverage_report` remains the runtime/manifest key, while `_synthesize_phase1_validation(...)` comments and warning text still mention `retrieval_coverage_report`. That is a documentation inconsistency, not a behavior bug, but it is the main remaining place a maintainer could get confused.
- Focused `pytest` execution in this sandbox was blocked by temp-dir permission errors; the requested behaviors were verified by direct code inspection plus direct Python execution of the happy path, degraded-row guard, and disclosure append path.

## Next
Sweep integration ready for Phase-1 live-run. Task #28 can proceed to live run.
