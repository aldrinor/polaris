## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1 — Diff under review

GH#359 I-bug-106. Brief APPROVE iter-1.

Diff: 2 files, +18/-3 lines. Synthesis prompt switches from `## subheadings` to `### subheadings` with explicit forbid `## headers`. New regression test asserts ### present + ## explicitly forbidden.

Tests: 29/29 pass on bot/I-bug-106 HEAD.

## §2 — Convergence

Trivial scope, single-line prompt change. Expected APPROVE iter 1.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
