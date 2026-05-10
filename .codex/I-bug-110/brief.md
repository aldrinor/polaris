## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Issue + Acceptance

**GH#362 — I-bug-110: synthesis [N] scrub telemetry counters.**

Acceptance: add `synthesis_n_scrub_count` (cumulative across process lifetime) and `n_scrub_runs` (number of synthesis calls that needed any scrub). Pattern mirrors `_JUDGE_TELEMETRY` from `polaris_graph.llm.entailment_judge`.

## §2 — Proposed change

| File | Δ |
|---|---|
| `src/polaris_graph/generator/analyst_synthesis.py` | +~40: `_SYNTHESIS_TELEMETRY` dict + `get_synthesis_telemetry()` snapshot + `reset_synthesis_telemetry()` zero-in-place; `_scrub_invalid_n_markers` increments counters when scrubbed > 0 |
| `tests/polaris_graph/test_synthesis_telemetry.py` | NEW (+~95): 8 tests covering clean-text-no-increment, single+multi marker counts, runs counter increments per call, snapshot independence, reset preserves dict identity |

Net: +~135 lines. Tests: 37 pass (8 new + 29 existing analyst_synthesis tests).

## §3 — Files clean

- `_scrub_invalid_n_markers` call site at `analyst_synthesis.py:287` UNCHANGED — caller still throws away scrub count via `_, _ = ...`. Telemetry is module-level so caller doesn't need wiring.
- No production code path changes. Pure observability addition.

## §4 — Test verification

`pytest tests/polaris_graph/test_synthesis_telemetry.py tests/polaris_graph/test_analyst_synthesis.py -x -q` → 37 passed in 3.35s.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Expected APPROVE iter 1.
