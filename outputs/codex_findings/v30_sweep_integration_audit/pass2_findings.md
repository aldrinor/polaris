# Codex V30 sweep integration audit — pass 2

**Verdict**: CONDITIONAL-blockers

## Blocker resolution
- Verified in code and direct in-process runs:
- Fully cited -> PASS (`pass=15`)
- Partially cited -> cited entity PASS, uncited entities `FAIL_UNBOUND_CITATION` (`pass=1`, `fail_unbound_citation=14`)
- No cross-check -> PASS plus `phase1_synth_retrieval_only` warning
- Gap -> `FAIL_MIN_FIELDS` plus curator task (`frame_gap_count=1`, `fail_min_fields=1`, `human_gap_tasks_json` length `1`)
- `_entity_cited_in_legacy()` does cover bibliography `doi`/`pmid`/`url_pattern`, plus report-text `doi`/`anchor`/`label_name`/`url_pattern`.
- Still open: the helper uses raw substring matching. Concrete false-pass remains: a shared domain like `accessdata.fda.gov` can mark multiple distinct FDA-label entities as cited, and DOI `10.1000/abc` matches unrelated text containing `10.1000/abcdef`. That can still overclaim PASS for uncited non-gap entities.

## Medium 1/2/3 resolutions
- Medium 1 verified: `scripts/run_honest_sweep_r3.py` gates on `PG_V30_ENABLED` before importing V30. When disabled, the only `manifest["v30_error"]` write is unreachable, and no other runner-side V30 manifest mutation path remains.
- Medium 2 verified: `append_disclosure_to_report()` returns `False` when `report.md` is missing and never creates the file. Direct helper run confirmed both missing-file and existing-file behavior.
- Medium 3 verified: `merge_v30_into_manifest()` matches runner expectations. Scoped coverage includes disabled, coverage merge, skipped_reason, error+warnings, plus the report append boundary helpers.

## Nit 1/2 resolutions
- Nit 1 verified: `compile_frame(...) is None` -> `skipped_reason="no_contract_for_slug"`; `FrameCompilerError` -> `skipped_reason="compile_frame_error"` with `error` preserved. The first case is covered in the test file; the second was verified by direct patched execution. There is still no dedicated pytest case for `FrameCompilerError`.
- Nit 2 verified: the completions comment is accurate. `tasks_equiv` is built from all contracted bindings, so the comment about accepting operator content for non-gap/partial rows matches the code.

## Adversarial attempts
- Disabled-path mutation: no remaining runner path found. Import and all `v30_*` manifest writes are inside the env gate.
- Legacy cross-check false-pass: still reproducible. Raw substring matching can validate the wrong entity via shared `url_pattern` domains or DOI superstrings.
- M-60 routing contradiction: not found in scoped behavior. `FAIL_UNBOUND_CITATION` stayed engineer-owned in direct execution (`human_gap_tasks_json == []` for the partial-citation case); gap rows still routed to curator.

## Residual concerns
- `_entity_cited_in_legacy()` needs tighter locator matching or a more entity-specific binding rule for URL-based regulatory artifacts before this can be considered safe for live coverage claims.
- There is no dedicated unit-test matrix for locator-boundary behavior, so the demonstrated false-pass cases are currently unguarded.
- `python -m pytest -q tests/polaris_graph/test_v30_sweep_integration.py` was blocked here by sandbox tempdir permissions for `tmp_path`; helper and phase-1-path verification was completed with direct in-process runs under workspace-local temp dirs.

## Next
Sweep integration is not yet ready for live-run exercise until the legacy citation helper tightens matching enough to remove the demonstrated false-pass path.
