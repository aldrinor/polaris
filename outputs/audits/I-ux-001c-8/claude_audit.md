# I-ux-001c sub-PR 8 — claude_audit

## Scope
Visual-only marketing-auth chrome of `/compare` (run-vs-run comparison). UNIQUE this sub-PR: established the first CI-wired e2e for /compare. Brief APPROVED iter-1 clean. Diff APPROVED iter-1 clean.

## Surface (header chrome only)
- Brand-red eyebrow "COMPARE · POLARIS CLINICAL RESEARCH"
- Display H1 "Compare two runs side-by-side."
- Tightened subtitle locked verbatim

## Preserved verbatim
- compareRuns + listCompletedRuns API calls
- ReportComparison rendering + run-picker UI
- ErrorState + LoadingState + EmptyState
- All existing testids: compare-page, comparison-result

## NEW CI surface
- web/tests/e2e/compare_g1_g8.spec.ts (5 tests: G1+G6, G2, nav-parity, G8, v6 chrome)
- .github/workflows/web_ci.yml block enumerating the new spec (after runs_runid_g1_g8 block)
- Mocks `**/api/v6/runs**` to avoid auth-gated race

## Verdict
Ready for operator merge queue.
