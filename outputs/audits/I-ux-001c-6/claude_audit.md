# I-ux-001c sub-PR 6 — claude_audit

## Scope
Visual-only marketing-auth chrome of `/dashboard`. Brief APPROVED iter-5 (5-cap converged, 0 P0/P1/P2). Diff APPROVED iter-1 (accept_remaining, 0 P0/P1, 6/6 checks PASS).

## Iter trail
- Brief iter-1: REQUEST_CHANGES (mock URL pattern wrong)
- Brief iter-2: stale (Edit didn't land)
- Brief iter-3: REQUEST_CHANGES (test file dead in CI per web_ci.yml enumeration)
- Brief iter-4: REQUEST_CHANGES (subtitle "signed bundle" overclaims; GPG path pending)
- Brief iter-5: APPROVE (5-cap converged)
- Diff iter-1: APPROVE

## Surface (header chrome only)
- Brand-red eyebrow "RUNS · POLARIS CLINICAL RESEARCH"
- Display H1 "Your recent runs."
- Honest subtitle: "Open one to replay the proof, claim by claim — every brief carries its own audit bundle."
- Start-new-research CTA preserved in same row position

## Preserved verbatim
- listCompletedRuns + LoadingState + ErrorState + EmptyState
- All run-row rendering + verdict pills + inspector deep-links
- formatWhen + locale-deterministic date rendering
- All existing testids: dashboard-page, dashboard-start-run, runs-list, run-row-*

## Test wiring
- v6 chrome cases ADDED to existing `dashboard_g1_g8.spec.ts` (line 49+)
- web_ci.yml line 185 runs this file → tests will actually execute in CI
- Mock targets `**/api/v6/runs**` matching listCompletedRuns URL

## Follow-ups filed
- #892 — other sub-PRs (2-5) have standalone v6 specs that may be CI-dead; fold or update web_ci.yml

## Verdict
Ready for operator merge queue.
