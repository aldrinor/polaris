# Codex Brief Review — I-f5-011 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix (Sheet close assertion):** between iterations, after `page.keyboard.press('Escape')`, AWAIT `expect(page.getByTestId('sentence-inspector-sheet')).toHaveCount(0)` to ensure the Base UI Sheet (200ms transition) fully detaches before the next click + MutationObserver. Otherwise iter 2 observes the stale mounted Sheet and asserts on previous-iteration evidence.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review (separate Codex call) = code-matches-plan.

## Pre-flight

- **Context:** I-f5-011 — final F5 acceptance test. An "AI agent" (programmatic test harness) navigates 10 RANDOM sentences from a stress report. For each: click → assert Inspector opens within 1000ms AND surfaces at least one evidence card (provenance source rendered) OR the appropriate adversarial badge (paywalled / out-of-range / synthesis-claim).
- **Constraints:** Builds on I-f5-008 stress harness. The "AI agent" is a Playwright loop — random sentence picker + per-iteration timing + assertion of evidence presence. No real LLM agent in scope; the name "AI agent" is plan-§F terminology.
- **Done-when:** acceptance criteria 1-6 below.

## Plan

### Frontend test only
1. `web/tests/e2e/sentence_inspector_ai_agent.spec.ts` (new):
   - Navigate to `/sentence_hover_test/stress?n=200`.
   - Wait for `verified-report-view` and assert `kept-sentence` count == 200.
   - Run a fixed-seed shuffle to pick 10 sentence indices in [0, 200) deterministically (seed = "polaris-i-f5-011" hashed into a small PRNG).
   - For each picked index i:
     - Capture `t0 = performance.now()` inside `page.evaluate`.
     - Click `[data-sentence-id="sec_stress:i"]`.
     - Wait via MutationObserver for `[data-testid="sentence-inspector-sheet"]`.
     - Capture `t1 = performance.now()`.
     - Assert `t1 - t0 < 1000`.
     - Inside the Sheet, assert AT LEAST ONE evidence-card-shaped surface is present: ANY of `inspector-source-{j}` (j ≥ 0) OR `inspector-source-missing-{j}` OR `inspector-paywalled-{j}` OR `inspector-synthesis-claim`. (Each kept sentence in the stress harness cites src-{i mod 50}, so `inspector-source-0` should always be present — the multi-id tolerance is defense against future demo changes.)
     - Close the Sheet via Escape key, then `await expect(page.getByTestId('sentence-inspector-sheet')).toHaveCount(0)` to confirm full detach before the next iteration (Codex iter-1 P1).
2. Use a small PRNG inline (xmur3 + sfc32 from public-domain hash literature; ~15 lines) to keep the test deterministic without a dep.

### Stress harness extension (small)
3. `web/app/sentence_hover_test/_demo_stress.tsx`: no behavior change needed. Already produces N kept sentences each with one provenance token in I-f5-008.

## Risks for Codex Red-Team
1. **Determinism via PRNG:** seeded shuffle prevents flaky test ordering. PRNG is xmur3 (stringHash) + sfc32 (state); both pure JS, no deps.
2. **Latency at random indices in 200-sentence list:** I-f5-008 already verified <1000ms at n=200 for first sentence; rendering all 200 rows happens once at navigation, click → Sheet only depends on per-sentence work.
3. **Escape-key close:** Sheet's onOpenChange wires to ESC via @base-ui/react Dialog default behavior. Verify by reading the Sheet component.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~80 LOC test file. Under 200.
6. **No new package dep.**

## Acceptance criteria

1. Test file exists at the named path.
2. Test loads `/sentence_hover_test/stress?n=200` and asserts 200 kept sentences.
3. Test picks 10 deterministic random indices (seed-fixed PRNG).
4. For each: time-to-Sheet asserted <1000ms via `performance.now()`.
5. For each: at least one evidence-card-shaped testid present in the Sheet.
6. Test closes the Sheet between iterations.

**Forced enumeration:** before verdict, write one line per criterion 1-6.

**Completeness check:** list files actually read.

## Output schema

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
