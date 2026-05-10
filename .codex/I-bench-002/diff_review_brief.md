## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

GH#195 I-bench-002. Brief iter-1 force-APPROVE'd. Both iter-1 P1 + P2 fixed:
- P1 (token-bearing artifact): added --verified-sentences flag + `_load_sentences_with_spans_from_jsonl` for canonical pre-resolution input. --report path retains for token-bearing artifacts with explicit docstring caveat.
- P1 (UNREACHABLE preservation): broken pointer state captured in `broken_pointers` field for both unknown source_id and out-of-bound span; sentence preserved in output stream.
- P2 (test coverage): 3 new regression tests (jsonl-load, unknown-source unreachable, oob-span unreachable).

12 tests pass.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
