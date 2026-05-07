# Codex Diff Review — I-f6-002 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only.

**Issue:** I-f6-002 — Edge-aware tooltip positioning
**Brief:** APPROVED iter 2
**Canonical-diff-sha256:** `79c6ca6e48e843093b80641239f07b38a670e879a0e77b69506d70f75261b844`
**LOC:** 106 net (under CHARTER §1 200-cap)

## Files

```
web/components/ui/evidence-tooltip.tsx                          +9 (side prop with "top" default)
web/app/sentence_hover_test/_demo_evidence_tooltip_edges.tsx    NEW +52 (3-trigger edge harness)
web/app/sentence_hover_test/evidence_tooltip_edges/page.tsx     NEW +5 (Next route)
web/tests/e2e/evidence_tooltip_edges.spec.ts                    NEW +41 (3 edge-bounded viewport tests)
```

## What changed

### Component
- `EvidenceTooltipProps.side?: "top"|"right"|"bottom"|"left"` (default `"top"`).
- Pass `side={side}` to `<Tooltip.Positioner>`.
- Existing inspector + I-f6-001 harness pass no `side` and continue defaulting to top — no behavior change.

### Harness
- 3 absolute-positioned triggers near top, bottom, right edges of full-viewport container. Each requests a side that would CLIP if Base UI didn't auto-flip (top trigger requests side="top", bottom trigger requests side="bottom", right requests side="right").
- Provider `delay={0}` so tests run fast (focus is on positioning, not debounce).

### Playwright
- For each scenario: hover trigger, wait for popup visible (1000ms), capture popup `getBoundingClientRect()` via `page.evaluate`, assert `left/top >= 0 AND right/bottom <= viewport`.
- Test queries last popup in DOM (in case multiple tooltips are concurrent during transitions).

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- No backend changes; existing I-f6-001 + inspector untouched.

## Risks for Codex Red-Team

1. **Base UI flip+shift default:** verified via local types in iter-1 brief review. Tooltip.Positioner uses Floating UI middleware with flip+shift on by default.
2. **Optional prop default:** existing call sites unaffected.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 106 net. Under 200.
5. **No new package dep.**

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
