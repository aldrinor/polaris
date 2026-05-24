# Claude architect audit — I-p2-052 (#851): Benchmark page S-audit

## Goal
Second cred-gated page (build-order step 5). /benchmark is the head-to-head scoreboard. Live it
401-redirects without a real reviewer JWT, and no benchmark run has been published, so the EMPTY
state is what renders today. Audited by rendering locally (seeded session + route-mocked
health/scoreboard fixture) to SEE every state. Fixture is visual-audit-only — never shipped.

## What looking-at-it found
1. The empty / error / loading states were bespoke amber/rose cards leaking INTERNAL dev language
   into a reviewer-facing demo: "POLARIS_BENCHMARK_RESULTS_DIR is not set in the live server's
   environment. Run scripts/run_benchmark.py first." For a gift to a PM's office, that is not
   top-tier — and it is the live-visible state. Replaced with the shared state-kit (EmptyState /
   ErrorState / LoadingState), reviewer-appropriate copy, design tokens only.
2. A LAW II honesty defect: the page intro asserted "POLARIS uniquely scores 1.0 on refusal
   correctness and auditability" — a specific benchmark NUMBER hardcoded in prose, decoupled from
   any data the page loads. Reframed to a capability claim ("built to be graded on them; every
   score below comes from the published scoreboard, not this page").
3. Raw Tailwind palette (text-emerald-700 / border-rose-500 / border-amber-500) instead of the
   design tokens. Moved to --verified / --destructive (via ErrorState) / EmptyState.
4. Mobile clipped the third peer column (the table compresses 4 columns at 390px). The head-to-head
   was incomplete on the live-visible mobile layout (Codex visual iter-1 P1). Fixed: below sm each
   dimension renders as a stacked, fully-labelled 3-system block; the dense table is retained sm+.

## Honest framing of the comparison (§-1.1 mindfulness)
This is a product benchmark feature, not a clinical-claim audit, so a head-to-head scoreboard is
legitimate — but it must not look rigged. The dimensions where POLARIS leads are its real
differentiators (sourcing tier mix, numeric grounding, provenance density); refusal correctness and
auditability are dimensions commercial products do not report (shown as POLARIS-only with a dash for
peers, NOT a fabricated peer 0); and the visual-audit fixture deliberately shows POLARIS LOSING
coverage completeness and latency to commercial products. No fabricated benchmark numbers are
shipped — the loaded view renders only what the real scoreboard endpoint returns.

## Preserved
The state machine, the real getBenchmarkHealth / getBenchmarkScoreboard fetches, all testids
(benchmark-page/-loading/-no-results-dir/-empty/-error/-loading-scoreboard/-list/-board/-tally/
agg-row-*/benchmark-link-*), and the e2e-asserted "BEAT-BOTH benchmark" H1.

## Dual Codex gate
- Brief APPROVE. Visual `-i` APPROVE iter-2 (desktop A / mobile A- / empty A- / error A- / list A).
  Code diff APPROVE.

## Honest verification state
LIVE-populated verification on polarisresearch.ca is DEFERRED — the page 401-redirects without the
real reviewer credential. States verified against a route-mocked fixture (visual audit only) + the
natural empty/error states. The empty state IS what renders live today, and it is verified.

## Constraints honored
Brand `#c8102e`; tokens only; logic/testids/H1 preserved; no fabricated SHIPPED data; no test
relaxation.

canonical-diff-sha256: 99ce63cb70476e222fa055330781f7502411b89293377e556c748631b5d6d47c
