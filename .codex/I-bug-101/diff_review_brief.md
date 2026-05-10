## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

GH#355 I-bug-101. Brief APPROVE iter-1 (0 P0/P1, 2 P2 cosmetic — fixture-count typo fixed in this iter; truncation is a deliberate length cap acceptable per FPR contract).

Diff: 2 files, +~300 lines. FPR audit harness with --smoke / --golden / --live modes. 8 tests pass in 1.05s. Live 200-pair invocation user-budget-gated (out of scope per §2).

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
