# Codex Diff Review — I-cj-004 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-cj-004 — Zero-verified abort Crown Jewel test. Brief APPROVE'd iter 1 (zero P0/P1/P2).
- **Diff under review:** `.codex/I-cj-004/codex_diff.patch` (canonical-diff-sha256 in trailer).
- **Files changed:**
  - NEW `tests/crown_jewels/test_cj_004_zero_verified_abort.py` (~95 LOC, 4 tests)
  - MODIFY `docs/crown_jewels.md` (~1-row change)

## Acceptance criteria (from brief APPROVE iter 1)

1. ✅ 4 tests cover abort+dropped+empty+kept-raises + success+only-dropped-raises.
2. ✅ Registry doc row 4 updated.
3. ✅ All 4 tests pass locally.
4. ✅ ~95 LOC under 200.

## Red-team checklist

1. **Pydantic v2 ValidationError wrapping** — both raise tests use `pytest.raises(ValidationError)` and `match=` regex on the inner ValueError message; this is the documented v2 behavior.
2. **Substrate-honest** — pure schema-validation pinning.
3. **Both teeth tested** — abort+kept raises (one tooth) AND success+all-dropped raises (symmetric tooth).
4. **§9.4 hygiene** — clean.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
