# Codex brief — I-p2-052 (#851): Benchmark page S-audit

HARD ITERATION CAP: 5. iter 1. Front-load findings; reserve P0/P1 for real risks. APPROVE iff the
plan is sound + doesn't break the contract.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Context
/benchmark (cred-gated) is the head-to-head scoreboard (POLARIS vs ChatGPT/Gemini DR on 7
dimensions). Live it 401-redirects without a real reviewer JWT, and no benchmark has been run, so
the EMPTY state is what renders live. Audited by rendering locally (seeded session + route-mocked
fixture — visual-audit-only, never shipped).

## Plan (assess-first — page already built)
1. FIX (S-bar + reviewer-appropriateness): empty/error/loading states leaked internal dev language
   ("POLARIS_BENCHMARK_RESULTS_DIR is not set … run scripts/run_benchmark.py") and used raw
   amber/rose palette. Replace with the shared state-kit + reviewer copy + design tokens.
2. FIX (honesty, LAW II): page intro asserted a hardcoded "POLARIS uniquely scores 1.0 …" number
   decoupled from data → capability claim.
3. POLISH: loaded view headline tally, brand POLARIS column, tabular-nums, --verified winners,
   dash + "POLARIS-only" for unreported peer dimensions, readable mobile (stacked, not clipped).
Preserve testids + the real fetches + the e2e-asserted "BEAT-BOTH benchmark" H1.

## Note
Already gated downstream: visual `-i` APPROVE iter-2 (desktop A / mobile A- / empty A- / error A- /
list A); code diff under review in parallel. This brief records acceptance for the artifact set.
