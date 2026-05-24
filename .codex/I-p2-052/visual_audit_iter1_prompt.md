# Codex VISUAL audit — I-p2-052 (#851) Benchmark (head-to-head), A++/S bar — iter 1 of 5

You have VISION. Audit /benchmark (cred-gated). It fetches the benchmark health + scoreboard
endpoints; these screenshots are rendered LOCALLY with a seeded client session + a Playwright
route-mocked FIXTURE (visual-audit only — fixture never shipped; page keeps fetching real data).
Front-load all; don't pick bone from egg; APPROVE iff zero P0/P1.

## What changed (assess-first rebuild — page was already built)
- States were dev-language amber/rose cards leaking internal env-var + script names
  ("POLARIS_BENCHMARK_RESULTS_DIR is not set… run scripts/run_benchmark.py"). Replaced with the
  shared state-kit (EmptyState / ErrorState / LoadingState), reviewer-appropriate copy, design
  tokens only (no raw emerald/rose/amber palette).
- Loaded view: headline tally ("58 of 84 … won by POLARIS", brand --verified), brand-emphasized
  POLARIS column, tabular-nums, winner cells = --verified green, a dash (—) for unreported peer
  dimensions + a "POLARIS-only" tag on refusal/auditability, and a legend.
- HONESTY: the fixture is deliberately NOT a clean sweep — POLARIS leads sourcing/grounding/
  provenance, is alone on refusal+auditability, and LOSES coverage + latency to commercial
  products (green on their cells). page.tsx intro had a hardcoded "POLARIS uniquely scores 1.0…"
  number decoupled from data → reframed to a capability claim ("built to be graded on them; every
  score below comes from the published scoreboard, not this page").

## Attached
1. bench_loaded_desktop  2. bench_loaded_mobile  3. bench_empty_desktop
4. bench_error_desktop   5. bench_list_desktop

## Locked / do NOT flag
- Brand #c8102e. "BEAT-BOTH benchmark" H1 is a required e2e-asserted string — keep it. Fixture is
  visual-audit-only. LIVE-populated verification DEFERRED (real JWT needed; 401-redirects without
  it) — the EMPTY state is the live-visible state, so weight it. The footer naming
  scripts/run_benchmark.py is a deliberate reproducibility/transparency claim (re-runnable).

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { loaded_desktop: "", loaded_mobile: "", empty: "", error: "", list: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff a confident A-tier, credible, HONEST scoreboard (no fabricated-looking sweep; clean
tokenized states), zero P0/P1.
