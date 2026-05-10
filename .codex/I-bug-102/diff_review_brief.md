## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

GH#356 I-bug-102. Brief APPROVE iter-1.

Diff: 2 files. entailment_judge.py adds explicit off-mode contract docstring (no judge instantiation, no httpx, no network). New test file: 3 tests asserting __init__ never runs in off-mode (mocked + verified telemetry stays zero + no API key needed).

65 tests pass. P2 cosmetics (lazy-import wording + verify_sentence framing) addressed in this iter.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
