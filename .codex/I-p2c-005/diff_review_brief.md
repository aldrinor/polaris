# Codex Diff Review — I-p2c-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-p2c-005 — Mobile end-to-end
**Brief:** APPROVED iter 1 (zero P0/P1)
**Canonical-diff-sha256:** `18429ffd7c5229cf8cf571959bbacddd52cea934d7ea85b8f58adaa3f816ce27`
**LOC:** 52 net (well under CHARTER §3 200-cap)

## Files

```
web/tests/e2e/p2c_005_mobile.spec.ts   NEW +52  (mobile F1→F5 chain + F5 tap-to-show)
```

## What changed

- `test.use({ viewport: 375×667, hasTouch: true, isMobile: true, userAgent: devices["iPhone 13"].userAgent })`.
- Single test walks F1..F5: intake / disambiguation / upload / sse / evidence-tooltip.
- F5 calls `trigger.tap()` and waits for `evidence-tooltip-popup` testid (mobile tap-to-show per I-f6-003).
- Final assertion: completed counter equals `["F1","F2","F3","F4","F5"]`.

## Verification

- `npx tsc --noEmit`: exit 0.
- `npx eslint`: exit 0.
- `npx prettier --check`: exit 0.
- `npx playwright test p2c_005_mobile.spec.ts --project chromium`: 1/1 passing in 1.8s.

## Risks for Codex Red-Team

1. **Mobile tap fallback:** uses `locator.tap()` which dispatches touch events. Verifies the I-f6-003 mobile fallback path.
2. **§9.4 N/A frontend.**
3. **CHARTER §3 LOC cap:** 52 net.

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
