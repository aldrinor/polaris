## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Issue + Acceptance

**GH#360 — I-bug-107: aggregate N BEAT-BOTH runs into mean ± stddev.**

Single BEAT-BOTH run has high sweep-to-sweep variance (LLM nondet). For benchmark publication, mean ± stddev across N runs is the correct framing.

**Scope decision:** this PR provides the AGGREGATOR, not sweep orchestration. Running N sweeps is user-budget-gated (~$0.10/sweep). The aggregator takes N pre-existing `outputs/m_live_2_beat_both/manifest.json` artifacts and produces the aggregate. Sweep-running orchestration is out of scope (separate user-decision concern).

**Acceptance:**
- New `scripts/aggregate_beat_both_runs.py` takes `--manifest` flag (repeatable) + `--output`.
- Output schema: `polaris_scores_aggregate.<dim>: {mean, stddev, min, max, values, n}` + `per_dimension_verdicts.<dim>: {polaris_mean, polaris_stddev, polaris_worst_case, chatgpt, gemini, verdict, robust}`. `robust=True` iff `(mean - stddev) > both competitor scores`.
- Tests cover: mean+stddev calc, output file written, <2 manifests rejected, robust verdict yes/no, summary flags high-variance dims (stddev > 10% of mean), missing-dimension handling.

## §2 — Proposed Change

| File | Δ |
|---|---|
| `scripts/aggregate_beat_both_runs.py` | NEW (+~210 lines) |
| `tests/scripts/test_aggregate_beat_both_runs.py` | NEW (+~115 lines) |
| `tests/scripts/__init__.py` | NEW (empty) |

Net: +~325 lines.

## §3 — Files clean

- `scripts/run_m_live_2_beat_both.py` UNCHANGED (existing single-run runner).
- `src/polaris_graph/audit_ir/beat_both_scoring.py` UNCHANGED.
- No production code touched. Pure aggregator + tests.

## §4 — Test Strategy

`pytest tests/scripts/test_aggregate_beat_both_runs.py -x -q` → 7 passed in 1.24s.

## §5 — Output Schema Bound

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
