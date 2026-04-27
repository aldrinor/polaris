# Test Failure Triage — 2026-04-27 Snapshot

**Suite**: `tests/polaris_graph/`
**Commit**: ef27d58 (M-26 threat model doc)
**Result**: 2614 collected → 2595 passed, 19 failed, 3 skipped, 3 collection errors

This document categorizes the 19 failing tests into actionable buckets so a future contributor (or wake-up agent) can pick them off without re-discovering the landscape.

---

## Bucket 1 — Test pollution (likely 9 tests)

**Symptom**: tests pass when run individually, fail when run as part of the full suite.

**Files**: `test_m36_trial_summary_table.py`

**Tests** (9):
- `TestCallOrchestration::test_empty_prose_returns_empty_no_llm_call`
- `TestCallOrchestration::test_empty_bibliography_returns_empty_no_llm_call`
- `TestCallOrchestration::test_bibliography_without_num_field_returns_empty`
- `TestCallOrchestration::test_llm_returns_no_trials_named_empty`
- `TestCallOrchestration::test_llm_returns_valid_table`
- `TestCallOrchestration::test_llm_returns_table_with_out_of_range_citations_dropped`
- `TestCallOrchestration::test_llm_failure_returns_empty`
- `TestCallOrchestration::test_llm_returns_junk_returns_empty`
- `TestDisableKnob::test_max_tokens_zero_suppresses_call`

**Reproducible verification**:
```
$ pytest tests/polaris_graph/test_m36_trial_summary_table.py::TestCallOrchestration::test_llm_returns_valid_table
1 passed in 2.70s            ← passes alone

$ pytest tests/polaris_graph/   (full suite)
9 fail                         ← polluted by an earlier test
```

**Likely cause**: an upstream test mutates module-level state (probably an OpenRouter client mock, a global env var, or an `asyncio` event-loop binding — the `DeprecationWarning: There is no current event loop` hint in the trace points at the latter). The `TestCallOrchestration` class assumes a clean event loop; another test leaves one in a bad state.

**Effort to fix**: ~1-2 hours. Bisect the suite to identify the polluting test, then add a `pytest` fixture that resets the loop or mocks per-test instead of module-level. Standard test-isolation hygiene.

**Priority**: Medium. The tests pass when run alone, so they aren't masking real M-36 bugs. But the suite is noisy in CI and that erodes trust.

---

## Bucket 2 — Genuine V28 regressions awaiting V30 fix (8 tests)

**Symptom**: V28 produced lower citation counts than the V27 baseline; preservation tests assert V27 floors.

**Files**: `test_m42_preservation.py`, `test_m49_v28_preservation.py`

**Tests** (8):
- `test_m42_preservation::TestJurisdictionPreservation::test_nice_count_at_or_above_v25_baseline`
- `test_m49_v28_preservation::TestV27PreservationFloors::test_fda_count_preserved` (V28: 4 < V27: 7)
- `test_m49_v28_preservation::TestV27PreservationFloors::test_hc_count_preserved`
- `test_m49_v28_preservation::TestM44PrimaryCitations::test_pivotal_trial_coverage`
- `test_m49_v28_preservation::TestM44PrimaryCitations::test_surpass_cvot_mentioned`
- `test_m49_v28_preservation::TestM44PrimaryCitations::test_surpass_2_primary_etd_present`
- `test_m49_v28_preservation::TestM47MechanismExtraction::test_m47_clamp_validator_passes`
- (1 more in M-49 family per the run output)

**Reproducible verification**:
```
test_fda_count_preserved
> assert fda >= V27_BASELINES["fda_count"]
> AssertionError: V28 FDA 4 < V27 baseline 7
```

**Likely cause**: This is the documented V28 regression that motivated V30 (per `outputs/audits/v29/true_root_cause_cross_review.md`). V28 + V29 landed `3 BB + 0 BO + 4 LB` cross-reviewed — identical regressions. V30 Report Contract Architecture (M-54..M-62) is the structural fix.

**Effort to fix**: NOT a quick win. These tests are red BY DESIGN until V30 ships end-to-end. They serve as the regression floor V30 must restore.

**Priority**: Wait. These flip green when V30 ships. Don't try to "fix" them by lowering the floor — that defeats their purpose.

---

## Bucket 3 — V30-pipeline-state assertions (2 tests)

**Symptom**: tests assert invariants on V30 pipeline output that V30 hasn't yet produced.

**Files**: `test_m201_evidence_selection.py`, `test_m207_invariant_coverage.py`, `test_manifest_contract.py`

**Tests** (3):
- `test_m201_evidence_selection::test_m201_selection_pool_smaller_than_max_keeps_everything`
- `test_m207_invariant_coverage::test_m207_every_manifest_write_includes_status_key`
- `test_manifest_contract::test_manifest_contract_all_manifest_writes_have_status`

**Likely cause**: The last two are duplicate enforcement of "every manifest write must include `status` key." The V30 manifest emission (M-60 — pending) is the right place to enforce this. M-201 is upstream evidence-selection invariants.

**Effort to fix**: 1-3 days. These can be addressed independent of V30 if someone wants to harden the manifest-emission code paths. But the cleaner path is to defer until M-60 lands.

**Priority**: Low-medium. They're noisy but not blocking.

---

## Bucket 4 — Pre-existing V30/V28 import errors (3 collection errors, NOT in the 19 above)

These don't run at all; they fail at collection:
- `test_m25_trial_name_match.py` — uses `from polaris_graph.X import Y` instead of `from src.polaris_graph.X import Y`
- `test_m28_regulatory_expander.py` — same
- `test_m29_jurisdictional_precision.py` — same

**Effort to fix**: 5 minutes. Sed the imports. But the modules they reference are V30-era and may have been renamed since these tests were written, so verify each test's referenced symbols still exist before changing the import path.

**Priority**: Low. They're pre-existing and excluded from the regression check via `--ignore=`.

---

## Recommended action plan

**Right now** (no V30 dependency):
- Bucket 1 (M-36 test pollution, 9 tests, ~1-2h): bisect + fix the polluting test fixture
- Bucket 4 (3 collection errors, 5min): rewrite the imports if the V30 modules they reference still exist

**Next V30 sprint**:
- Bucket 3 (3 tests): land them as part of M-60 manifest emission completion
- Bucket 2 (8 tests): they self-clear when V30 reaches BEAT-BOTH

**Never** (don't touch):
- Don't lower the V27 baselines in Bucket 2 to make them pass — that erases the regression floor.
- Don't `xfail` Bucket 2 — the failing assertions are the test authors signaling "V30 must restore this."

---

## Appendix — bucket totals

| Bucket | Count | Action |
|---|---:|---|
| 1. M-36 test pollution | 9 | Fix now |
| 2. V28 regressions (V30 fixes) | 8 | Wait for V30 |
| 3. V30 manifest invariants | 2-3 | Land with M-60 |
| 4. Collection-time import errors | 3 | Fix now or skip permanently |
| **Total in suite** | **19 fail + 3 collect-error** | |
