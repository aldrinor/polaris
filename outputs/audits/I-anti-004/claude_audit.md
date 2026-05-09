# Claude architect audit — I-anti-004

## Scope vs brief
- `src/polaris_v6/anti_sycophancy/nightly_eval.py`: matches brief code block. Pure-Python `_impl` + `@dramatiq.actor` wrapper. Coverage validation BEFORE scoring (same invariant as I-anti-003 gate).
- `tests/v6/anti_sycophancy/test_nightly_eval.py`: 5 tests covering pass/fail/missing/duplicate paths + actor delivery via stub broker (test 5 calls `.fn()` per Codex P2 iter-1 fix).

## §9.4 hygiene
- No try/except: pass, no mock in src, no magic numbers (DEFAULT_THRESHOLD module constant), no sleep, no TODO/FIXME/XXX.

## CHARTER §3 LOC
- `nightly_eval.py`: 78 LOC. Tests: ~55 LOC. Total ~135 under 200.

## Substrate-honest framing
- Module docstring + brief explicitly state real-LLM candidate generation is post-MVP (I-anti-005). The actor exercises scheduled-task mechanics + invariant-validation + structured-log pipeline against the existing fixture from I-anti-003.

## Acceptance criteria check
1. ✅ `run_nightly_anti_sycophancy_eval_impl` + actor exist.
2. ✅ Coverage validation + mean computation.
3. ✅ Structured log line (line 65-71).
4. ✅ Dict with N, mean_delta, threshold, verdict.
5. ✅ 5/5 tests pass.
6. ✅ LOC under cap.

## Test execution evidence
```
tests/v6/anti_sycophancy/test_nightly_eval.py::test_nightly_pass_on_clean_fixture PASSED
tests/v6/anti_sycophancy/test_nightly_eval.py::test_nightly_fail_on_drift_fixture PASSED
tests/v6/anti_sycophancy/test_nightly_eval.py::test_nightly_rejects_missing_paired_id PASSED
tests/v6/anti_sycophancy/test_nightly_eval.py::test_nightly_rejects_duplicate_paired_id PASSED
tests/v6/anti_sycophancy/test_nightly_eval.py::test_nightly_actor_delivers_via_stub_broker PASSED
5 passed in 1.20s
```

## Verdict
APPROVE — diff matches brief iter-1 APPROVE + P2 fix incorporated, all acceptance criteria met.
