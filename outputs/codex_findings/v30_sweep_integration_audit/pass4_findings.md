# Codex V30 sweep integration audit — pass 4

**Verdict**: CONDITIONAL-blockers

## Scope narrow verification
Directionally correct: `scripts/run_honest_sweep_r3.py` no longer reads `report.md` or bibliography for V30, and `run_v30_post_generation(...)` now ignores deprecated legacy inputs. I also verified that `manifest.v30_warnings[]` survives merge and JSON serialization.

Not yet honest end-to-end: Phase-1 still writes `manifest["frame_coverage_report"]` ([v30_sweep_integration.py](</C:/POLARIS/src/polaris_graph/v30_sweep_integration.py:117>); [run_honest_sweep_r3.py](</C:/POLARIS/scripts/run_honest_sweep_r3.py:1645>)) while the warning/docstring say the field was renamed to `retrieval_coverage_report` ([v30_sweep_integration.py](</C:/POLARIS/src/polaris_graph/v30_sweep_integration.py:523>)). The appended disclosure prose also still overclaims: runtime output is `Frame coverage: all 15 contract-required entities populated with bound evidence.`

## Residual concerns
- Blocker: top-level surfaces can still be misread as report-coverage. The mandatory warning exists only in `manifest.v30_warnings[]`; `report.md` gets disclosure prose with no retrieval-only caveat. Put the same caveat into the Methods disclosure text, or rename that disclosure/header to retrieval coverage before live run.
- Blocker: `_synthesize_phase1_validation()` still treats every non-gap row as PASS and sets `bound_ev_id_present_in_prose=True` plus `observed_completion_count=1` for all such rows ([v30_sweep_integration.py](</C:/POLARIS/src/polaris_graph/v30_sweep_integration.py:561>)). I manually exercised a non-gap row with empty `direct_quote`; it still shipped `status=pass`. If M-56 ever emits degraded non-gap rows, Phase-1 can still false-pass retrieval.
- Blocker: the tests are not fully realigned. `test_clinical_tirzepatide_produces_coverage()` still injects legacy report/bibliography and asserts no retrieval-only warning ([test_v30_sweep_integration.py](</C:/POLARIS/tests/polaris_graph/test_v30_sweep_integration.py:258>)), but the current implementation always emits that warning; manual execution confirmed it.
- Concern: `_entity_cited_in_legacy()` as a stub is acceptable only because these three files no longer rely on it, but it does not fail loudly for stale callers; it silently returns `False` ([v30_sweep_integration.py](</C:/POLARIS/src/polaris_graph/v30_sweep_integration.py:629>)). Remove the dead heuristic body or raise a clearer deprecation error once external imports are gone.

## Next
Claude should make the surface honest before the Phase-1 live-run exercise:
1. Rename the manifest/report-facing terminology to retrieval coverage everywhere, including the appended disclosure prose.
2. Add a guard so empty or non-evidentiary non-gap rows do not PASS unless M-56 explicitly guarantees that invariant.
3. Realign the stale clinical-chain test to the new always-warn semantics.

Phase 2 via M-58 + M-59 is the right path for true report-coverage; the heuristic legacy cross-check should stay retired.
