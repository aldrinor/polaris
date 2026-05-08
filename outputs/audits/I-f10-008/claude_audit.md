# Claude architect audit — I-f10-008

**Issue:** F10 walkthrough: tirzepatide vs semaglutide
**Branch:** bot/I-f10-008
**Canonical-diff-sha256:** de10e135e1182f84348c71442e85f7f2a2d228c78387bea016920f8c86ae473f
**Brief verdict:** APPROVE iter 2 (port + N=5 wording + clinical-question disclaimer P2 fixes applied)
**Diff verdict:** APPROVE iter 1 (0/0/0/0, accept_remaining)

## Substrate honesty
- Documentation-only deliverable per the issue's LOC 0 spec.
- Honest framing per LAW II + CLAUDE.md §9.4: walkthrough explicitly states "the clinical question itself is NOT answered by live evidence today" and clarifies the demo routes show housing-starts data and SELECT-trial-style cardiovascular data, not pharmaceutical efficacy.
- All cross-referenced PR commits exist on polaris (bad6d9e, a3f1f50, 6fb1b37, bbe8dbc, 599bbe0, 54fc31a, 617605e).
- Port 3000 corrected per Codex iter-1 P1 (web/package.json `"dev": "next dev"` defaults to 3000; 3738 is Playwright e2e port only).
- N=5 wording corrected to "5 entities × 2 metrics = 10 entity-metric data rows" per Codex iter-2 P2.
- "What's NOT yet wired" section explicitly captures the deferred work (live LLM auto-table, production evidence_id resolution, OS-level isolation).

## §9.4 N/A documentation.

## CHARTER §1 LOC cap
- N/A — documentation only per issue's LOC estimate of 0.

## Verdict
APPROVE.
