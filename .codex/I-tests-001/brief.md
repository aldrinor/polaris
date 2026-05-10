## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Issue + Acceptance

**GH#364 — I-tests-001: 10 pre-existing failing tests triage.**

Acceptance: `docs/tests/i_tests_001_triage.md` with per-test classification + per-class fix plan.

## §2 — Findings

Empirical run on `polaris` HEAD (2026-05-10): **65 collection errors**, NOT 10 as issue body said. ALL 65 share single root cause: `ModuleNotFoundError: No module named 'polaris_graph'` — caused by mixed import-prefix conventions (`from polaris_graph.X` vs `from src.polaris_graph.X`).

Per-test classification:
- Real-bug count: **0**
- Stale-test count: **0**
- Flaky-test count: **0**
- Configuration-issue count: **65**

Single fix: add tests/conftest.py that prepends both `src/` and repo root to sys.path. Out-of-scope for THIS PR (separate risk surface around full-suite regression after sys.path change).

## §3 — Files clean

- No production code touched.
- Pure documentation.

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
