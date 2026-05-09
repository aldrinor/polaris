# Claude architect audit — I-cj-001

## Scope vs brief
- `tests/crown_jewels/test_cj_001_two_family_segregation.py`: 5 tests covering all five required behaviors per Codex iter-2 APPROVE.
- `docs/crown_jewels.md`: registry table mapping I-cj-001 to test path + bound function; cj-002..007 marked "Pending".

## §9.4 hygiene
- No try/except: pass; no mock; no magic numbers; no sleep; no TODO/FIXME/XXX.

## CHARTER §3 LOC
- Test: 68 LOC. Doc: 13 LOC. Total ~83 under 200.

## Substrate-honest framing
- Module docstring + brief explicitly state this is a binding registry of an EXISTING invariant. The bound function `check_family_segregation` already raises per CLAUDE.md §9.1.1; this PR ships the unambiguously-named test surface so a future regression breaks `test_cj_001_*` rather than dispersing across the regression module.

## Acceptance criteria check
1. ✅ 5 tests pass locally.
2. ✅ Registry doc with table.
3. ✅ Override-bypass test demonstrates documented escape hatch.
4. ✅ LOC under cap.

## Test execution evidence
```
tests/crown_jewels/test_cj_001_two_family_segregation.py::test_cj_001_different_families_pass PASSED
tests/crown_jewels/test_cj_001_two_family_segregation.py::test_cj_001_same_family_raises PASSED
tests/crown_jewels/test_cj_001_two_family_segregation.py::test_cj_001_unknown_generator_without_override_raises PASSED
tests/crown_jewels/test_cj_001_two_family_segregation.py::test_cj_001_unknown_evaluator_without_override_raises PASSED
tests/crown_jewels/test_cj_001_two_family_segregation.py::test_cj_001_explicit_override_bypasses_unknown PASSED
5 passed in 1.23s
```

## Verdict
APPROVE.
