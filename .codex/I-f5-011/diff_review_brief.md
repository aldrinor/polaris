# Codex Diff Review — I-f5-011 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only (do NOT spawn dev servers; sandbox blocks them).

**Issue:** I-f5-011 — F5 AI agent test (10 random sentences, <1s each, evidence present)
**Brief:** APPROVED iter 2
**Canonical-diff-sha256:** `aacd383e7035ab77a69b050d4348016a47e82816c641bc56d3819199e4fb4205`
**LOC:** 108 net (well under CHARTER §1 200-cap)

## Files

```
web/tests/e2e/sentence_inspector_ai_agent.spec.ts        NEW +108
```

## What changed

- Single Playwright spec — no production-code changes.
- xmur3 + sfc32 PRNG (public-domain, ~25 LOC) seeded with `"polaris-i-f5-011"` for deterministic shuffle.
- Loads `/sentence_hover_test/stress?n=200`; asserts 200 kept rows; picks 10 random indices.
- Per iteration: `page.evaluate` measures click → Sheet attach via `performance.now()` and MutationObserver; asserts <1000ms.
- After each Sheet open: asserts AT LEAST ONE evidence card present (`inspector-source-*` OR `inspector-paywalled-0` OR `inspector-synthesis-claim`).
- Per Codex iter-1 P1: Escape close + `await expect(...).toHaveCount(0)` to confirm full detach (Base UI 200ms transition) before next iteration.

## Verification
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Determinism:** PRNG seeded with literal string `"polaris-i-f5-011"`; same picks every run.
2. **Detach assertion (Codex iter-1 P1 fix):** explicit `toHaveCount(0)` between iterations.
3. **Evidence-card flexibility:** locator union of `^="inspector-source-"`, `inspector-paywalled-0`, `inspector-synthesis-claim` covers normal + adversarial cases without coupling to specific source IDs.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** 108 net. Comfortably under 200.
6. **No new package dep.**

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
