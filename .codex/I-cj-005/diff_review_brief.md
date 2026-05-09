# Codex Diff Review — I-cj-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-cj-005 — Corpus approval rubber-stamp resistance Crown Jewel test. Brief APPROVE'd iter 2 (P1 rubber-stamp branch ordering corrected; test pins user-observable rejection invariant, not branch identity).
- **Diff under review:** `.codex/I-cj-005/codex_diff.patch` (canonical-diff-sha256 in trailer).
- **Files changed:**
  - NEW `tests/crown_jewels/test_cj_005_corpus_approval.py` (~75 LOC, 5 tests)
  - MODIFY `docs/crown_jewels.md` (~1-row change)

## Acceptance criteria (from brief APPROVE iter 2)

1. ✅ 5 tests cover no-deviation pass + 3 rejection paths + substantive-note pass.
2. ✅ Registry doc row 5 updated to correct corpus_approval_gate.py path.
3. ✅ All 5 tests pass locally.
4. ✅ ~75 LOC under 200.

## Red-team checklist

1. **Outcome-pinning** — test 4 asserts rejection without binding to which specific branch fires (length-check or trivial-set check). User-observable invariant per CLAUDE.md §9.1.5 is "rubber-stamp note + material deviation → rejected"; that is what the test pins.
2. **Substrate-honest** — pure dataclass+function pinning.
3. **§9.4 hygiene** — clean.
4. **CHARTER §3 LOC cap** — under 200.

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
