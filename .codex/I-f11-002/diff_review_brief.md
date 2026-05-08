# Codex Diff Review — I-f11-002 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f11-002 — Append-to-existing-report rendering
**Brief:** APPROVED iter 1 (zero P0/P1; 1 P2 incorporated: separator wrapper with caption + hr, not bare hr)
**Canonical-diff-sha256:** `4aa2c39d0cd9098e3b84520b834cec441c1df3cdd6de0bfd227e3458a5c32067`
**LOC:** 108 net (under CHARTER §3 200-cap)

## Files

```
web/app/generation/components/follow_up_append_view.tsx       NEW +35  (FollowUpAppendView component)
web/app/sentence_hover_test/follow_up_append/page.tsx         NEW +61  (fixture page)
web/tests/e2e/follow_up_append.spec.ts                        NEW +12  (1 e2e test)
```

## What changed

- `FollowUpAppendView({ original, appended })` renders `<VerifiedReportView>` + separator (`<hr>` + caption + `<hr>` wrapped in `<div data-testid="follow-up-separator">`) + `<VerifiedReportView>`.
- `<p data-testid="follow-up-separator-caption">Follow-up appended below</p>`.
- Fixture page uses a small `_report` helper to build minimal valid `VerifiedReport` instances.
- Spec: `getByTestId("verified-report-view").toHaveCount(2)` + `follow-up-separator` visible + caption text.

## Verification

- `npx tsc --noEmit`: exit 0.
- `npx eslint`: exit 0.
- `npx prettier --check`: exit 0.
- `npx next build`: succeeds; `/sentence_hover_test/follow_up_append` static prerender included.
- `npx playwright test follow_up_append.spec.ts --project chromium`: 1/1 passing in 1.5s.

## Risks for Codex Red-Team

1. **Production wiring deferred:** I-f11-002b will wire `/runs/{run_id}/followup/{follow_up_id}` route and graph_v4 producing `appended` from `FollowUpAgent.compose`.
2. **§9.4 N/A frontend.**
3. **CHARTER §3 LOC cap:** 108 net.

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
