## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Diff under review

GH#360 I-bug-107. Brief iter-1 REQUEST_CHANGES with 1 P1 + 1 P2; both fixed in this diff.

| Fix | Description |
|---|---|
| P1 (strict inequality) | `robust = worst_case > chatgpt_val and worst_case > gemini_val` (no tolerance). Regression test `test_robust_strict_inequality_no_tolerance` verifies near-margin case (mean=101, stddev=0.7, competitors=100/99) → robust=True. |
| P2 (missing competitor dim) | Explicit INCOMPLETE verdict + chatgpt/gemini=None when competitor manifest lacks the dimension; never fabricate 0.0. Regression test `test_incomplete_verdict_when_competitor_dimension_missing` verifies. |

Net diff: scripts/aggregate_beat_both_runs.py +~210 (with iter-1 fixes); tests/scripts/test_aggregate_beat_both_runs.py +~190 (9 tests). Tests: **9/9 pass in 1.40s**.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
