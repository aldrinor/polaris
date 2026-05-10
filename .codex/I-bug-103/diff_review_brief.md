## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1 — Diff under review

GH#357 I-bug-103. Brief APPROVE iter-1.

Diff: 1 file added, +63 lines, 0 deletions. Pure markdown documentation of the failed retrieval-expansion experiment.

## §2 — Files clean

- `src/polaris_graph/retrieval/live_retriever.py` UNCHANGED
- No tests touched
- No imports added anywhere
- Diff is one new markdown file in `docs/experiments/`

## §3 — Convergence

Documentation-only PR. Expected APPROVE iter 1.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
