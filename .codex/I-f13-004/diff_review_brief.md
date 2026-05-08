# Codex Diff Review — I-f13-004 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f13-004 — F13 adversarial: source retraction during replay
**Brief:** APPROVED iter 2 (P1 fix: pin default-B; P2 fixes: pass_rate=0.83 to avoid double alert; attribution scope = newly retracted only)
**Canonical-diff-sha256:** `eb557dce0182cfd4f12d411600bb053dacf732926e78e968a0995bfc3821b681`
**LOC:** 84 net (under CHARTER §1 200-cap)

## Files

```
web/lib/pin_replay_demo.ts                       +14  (PinSnapshot.retracted_source_ids; 2026-05-15 entry; 2026-04-30 retracted)
web/lib/pin_regression.ts                        +27 -2 (getRetractionContext + attribution wiring)
web/app/pin_replay/page.tsx                      +13 -1 (pin default-B; render attribution span)
web/tests/e2e/pin_retraction_handled.spec.ts     NEW +29 (adversarial selectOption A=2026-04-30 → B=2026-05-15)
```

## What changed

### `pin_replay_demo.ts`
- `PinSnapshot.retracted_source_ids?: string[]` (optional).
- 2026-04-30 gains `retracted_source_ids: ["demo-clin-002"]`.
- New `2026-05-15` entry: pass_rate=0.83 (drop 2pp, under threshold), verified_sentence_count=17 (drop 6, over threshold), retracted=["demo-clin-002","demo-clin-005"].

### `pin_regression.ts`
- `RegressionAlert` gains `attributed_to_retraction?: string[]`.
- New `RetractionContext { newly_retracted: string[] }`.
- New `getRetractionContext(a, b)` — returns IDs in `b.retracted_source_ids` not in `a.retracted_source_ids`. Defensive `?? []`.
- `detectRegressions` computes retraction context once; merges `attributed_to_retraction` into sentence-count alert when newly_retracted.length > 0. Pass-rate alert never gets attribution (scope choice).

### `page.tsx`
- Line 77: `useState(PIN_DATES[PIN_DATES.length - 1])` → `useState("2026-04-30")` — pin default-B explicitly so adding 2026-05-15 doesn't shift initial state.
- Alert `<li>` now renders an inline `<span data-testid="regression-retraction-attribution">(attributed to retraction of: <ids>)</span>` when alert has `attributed_to_retraction`.

### `pin_retraction_handled.spec.ts`
- selectOption A=2026-04-30, B=2026-05-15.
- Asserts `regression-alert` visible.
- Asserts `regression-alert-verified_sentence_count` visible.
- Asserts `regression-alert-pass_rate` has count 0 (NOT visible — 2pp under threshold).
- Asserts `regression-retraction-attribution` contains "demo-clin-005".
- Asserts attribution does NOT contain "demo-clin-002" (carried over from A; brief criterion-6 negative assertion per Codex iter-2 P2).

## Verification

- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/pin_replay/page.tsx lib/pin_regression.ts lib/pin_replay_demo.ts tests/e2e/pin_retraction_handled.spec.ts`: exit 0.
- `npx prettier --check` on changed files: exit 0.
- `npx next build`: succeeds; `/pin_replay` static prerender unchanged.
- `npx playwright test` (chromium, against `next start -p 3738`): all 4 specs (existing 3 + new 1) pass in 3.3s.

## Risks for Codex Red-Team

1. **Default-B pinning:** explicit string "2026-04-30" hard-coded in page.tsx; will go stale if registry semantics change. Acceptable for demo substrate (post-Carney production reads from server).
2. **Pass-rate-only alert single-attribution:** intentional scope; pass-rate retraction-attribution is a follow-up if needed.
3. **Optional field semantics:** `retracted_source_ids` undefined treated as empty; first 3 pin entries (2026-01-15, 2026-03-01, 2026-04-30 originally) require zero migration. 2026-04-30 explicitly populated for demo continuity.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** 84 net. Under 200.

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
