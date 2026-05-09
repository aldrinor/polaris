# Codex Diff Review — I-cj-003 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-cj-003 — Strict-verify Crown Jewel test. Brief APPROVE'd iter 1 (zero P0/P1/P2).
- **Diff under review:** `.codex/I-cj-003/codex_diff.patch` (canonical-diff-sha256 in trailer).
- **Files changed:**
  - NEW `tests/crown_jewels/test_cj_003_strict_verify.py` (~95 LOC, 7 tests)
  - MODIFY `docs/crown_jewels.md` (~1-row change)

## Acceptance criteria (from brief APPROVE iter 1)

1. ✅ 7 tests cover pass + 5 specific rejections + synthesis-claim escape hatch.
2. ✅ Registry doc row 3 updated.
3. ✅ All 7 tests pass locally.
4. ✅ ~95 LOC under 200 cap.

## Red-team checklist

1. **Mutation pattern** — each REJECT test mutates exactly one input element (token format, source_id, span bounds, decimal, content words) and asserts the SPECIFIC drop_reason. Five rejection paths × five distinct mutations.
2. **Pass test** — sentence "Aspirin reduced mortality by 12.5 percent [#ev:src-A:0-50]" matches span char 0-50 of fixture full_text "Aspirin reduced mortality by 12.5 percent in adults." → token valid, span in bounds, decimal "12.5" present in span, content overlap {aspirin, reduced, mortality, percent} ≥ 2.
3. **Synthesis-claim** — `is_synthesis_claim=True` + no tokens → passes (per I-f5-006).
4. **§9.4 hygiene** — clean.
5. **CHARTER §3 LOC cap** — under 200.

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
