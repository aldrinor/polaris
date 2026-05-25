# I-ux-001c sub-PR 7 — claude_audit

## Scope
Visual-only marketing-auth chrome of `/runs/[runId]` (live run progress, SSE-driven). Brief APPROVED iter-1 (accept_remaining, 0 P0/P1, 6/6 PASS). Diff APPROVED iter-1 (accept_remaining, 0 P0/P1/P2, 6/6 PASS).

## Surface (header region only)
- NEW brand-red category eyebrow "LIVE RUN · POLARIS CLINICAL RESEARCH"
- PROMOTED "Run {runId}" eyebrow to brand-red (text-primary)
- Display-weight H1 with dynamic question content + loading/error fallback preserved

## Preserved verbatim
- getRun + subscribeToRun (SSE) + cancelRun + getBundle + downloadBundleAsJson
- TERMINAL_STATUSES gate on Cancel button
- Action row (Export-bundle + New-run buttons in same position)
- Metadata p (template/status/queued time)
- ErrorState handling
- FollowupPanel + RunProgress component (untouched sub-components)
- All existing testids: runs-runid-page + sub-component testids

## Test wiring
- v6 chrome cases ADDED to existing `runs_runid_g1_g8.spec.ts` (line 76+)
- web_ci.yml line 192 runs this file → tests will actually execute in CI
- Mocks BOTH `/api/v6/runs/{id}` (status fetch, 200 with stub data) AND `/api/v6/stream/{id}` (SSE, empty event-stream) — per brief iter-1 P2 fix

## Verdict
Ready for operator merge queue.
