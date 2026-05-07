# Codex Brief Review — I-f6-002 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix:** EvidenceTooltip currently hard-codes `<Tooltip.Positioner side="top">`. Add an optional `side?: "top" | "right" | "bottom" | "left"` prop (default `"top"`, preserving existing behavior) so the harness can request bottom/right scenarios. Existing inspector + I-f6-001 harness pass no `side` and continue defaulting to top.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review = code-matches-plan.

## Pre-flight

- **Context:** I-f6-002 — when the EvidenceTooltip is near a viewport edge, the popup must reposition to remain visible. Base UI's `Tooltip.Positioner` already uses Floating UI under the hood (per @base-ui/react/tooltip docs at `web/node_modules/@base-ui/react/tooltip/positioner/TooltipPositioner.d.ts`); the existing component sets `side="top"` which can clip when the trigger is near the top of the viewport. Verify edge-aware behavior + add Playwright coverage for 3 viewport-edge scenarios.
- **Constraints:** Frontend-only. Reuse the I-f6-001 harness pattern; expose 3 trigger positions (top, bottom, right edges) so Playwright can hover each and assert the popup stays in viewport.
- **Done-when:** acceptance criteria 1-6 below.

## Plan

### Frontend
1. `web/components/ui/evidence-tooltip.tsx`:
   - Add optional `side?: "top" | "right" | "bottom" | "left"` prop (default `"top"`).
   - Pass through to `<Tooltip.Positioner side={side}>` so the harness can deliberately request bottom/right scenarios.
   - Existing callers pass no `side` and continue defaulting to top — no behavior change.
   - Base UI Tooltip.Positioner default flip+shift on collision is what we rely on (verified against local types).
2. `web/app/sentence_hover_test/_demo_evidence_tooltip_edges.tsx` (new): harness with 3 triggers placed at:
   - `near-top`: trigger near the top edge of the viewport — popup with `side="top"` request should flip to bottom.
   - `near-bottom`: near bottom — popup with `side="bottom"` should flip to top.
   - `near-right`: near right edge — popup with `side="right"` should flip to left.
3. `web/app/sentence_hover_test/evidence_tooltip_edges/page.tsx` (new): Next route mounting the harness.
4. `web/tests/e2e/evidence_tooltip_edges.spec.ts` (new): for each of the 3 edge scenarios:
   - Hover the trigger.
   - Wait for popup visible.
   - Capture popup bounding box via `page.evaluate(() => element.getBoundingClientRect())`.
   - Assert `box.left >= 0`, `box.top >= 0`, `box.right <= viewport.width`, `box.bottom <= viewport.height` — i.e., popup fully inside viewport.

## Risks for Codex Red-Team
1. **Base UI default collision behavior:** Floating UI flip+shift is Base UI's default for Positioner; verify by reading `web/node_modules/@base-ui/react/tooltip/positioner/TooltipPositioner.d.ts` to confirm.
2. **Viewport assumptions:** Playwright config viewport is 1440x900 (per `playwright.config.ts`). Edge positions chosen relative to that.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~110 LOC. Under 200.

## Acceptance criteria

1. New harness with 3 edge-positioned triggers (top/bottom/right).
2. Each trigger uses a deliberately-clipping `side` request to force a flip.
3. Playwright spec hovers each, asserts popup fully inside viewport.
4. Component changes: add optional `side?` prop with `"top"` default; pass through to Positioner. Rely on Base UI default flip+shift collision behavior.
5. Existing inspector + I-f6-001 harness routes UNTOUCHED.
6. CHARTER §1 LOC cap respected (≤200 net).

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
