# Codex Brief Review — I-f6-001 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 #1 fix (delay API):** `Tooltip.Root` does NOT accept `delay`. The harness wraps the tooltip in a `<Tooltip.Provider delay={300}>` to enforce debounce; per @base-ui/react/tooltip Provider API the `delay` prop is the supported entry point. Existing inspector call site already uses a Provider at the page root (or app root) — no behavioral change there.
- **P1 #2 fix (data path scope):** narrow scope. EvidenceContract `SourceSpan` does NOT carry `publication_date`. Inspector call site at `web/app/inspector/[runId]/page.tsx:341` will NOT thread the new prop in this Issue (data-path expansion would require backend EvidenceContract change — separate Issue). This Issue ships ONLY (a) the new optional `publishedDate?` prop, (b) tooltip rendering of it when supplied, (c) Provider `delay={300}` in the new harness route, (d) Playwright spec on the harness route. The existing inspector call site is left untouched.
- **P2 fix (debounce assertion):** Playwright now asserts (a) popup not present immediately after hover (within ~50ms) AND (b) popup appears within ~500ms — confirming the delay actually fires.

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

- **Context:** I-f6-001 — extend `web/components/ui/evidence-tooltip.tsx` so the hover-card includes (a) the cited quote (already present via `spanText`), (b) the source tier (already present), (c) **timestamp** (publication date — NEW), and (d) **debounced rendering** via Base UI `Tooltip.Provider` `delay` prop. Existing usage at `web/app/inspector/[runId]/page.tsx:341` and `web/tests/e2e/performance_hover.spec.ts` must keep passing.
- **Constraints:** Frontend-only. The polaris graph already has `publication_date` on `RetrievalSource` (used by I-f5-003 inspector trace). Extend the tooltip to render it.
- **Done-when:** acceptance criteria 1-6 below.

## Plan

### Frontend
1. `web/components/ui/evidence-tooltip.tsx`:
   - Add `publishedDate?: string | null` prop.
   - Render below the URL line as `Published: {publishedDate}` when present.
   - Component itself does NOT set delay (Tooltip.Root has no `delay` prop in this Base UI version). The harness route wraps the tooltip in `<EvidenceTooltipProvider delay={300}>` to apply the debounce; existing inspector call site is unaffected.
2. `web/app/inspector/[runId]/page.tsx`: NO change — EvidenceContract.SourceSpan lacks publication_date. Threading deferred to a separate Issue that expands EvidenceContract.
3. `web/components/ui/evidence-tooltip.tsx` testid: add `data-testid="evidence-tooltip-popup"` on the `Tooltip.Popup` for Playwright.
4. `web/tests/e2e/evidence_tooltip.spec.ts` (new):
   - Mount the inspector page (existing fixture) OR a small new harness route.
   - Hover a token; assert the popup appears with quote, tier, and (if provided) date text.

Given the inspector page is fixture-coupled, prefer harness route:
5. `web/app/sentence_hover_test/_demo_evidence_tooltip.tsx` (new): minimal harness rendering one `<EvidenceTooltipProvider><EvidenceTooltip publishedDate=... ... /></EvidenceTooltipProvider>` with known testid `evidence-tooltip-trigger`.
6. `web/app/sentence_hover_test/evidence_tooltip/page.tsx` (new): Next route mounting the harness.
7. Playwright spec asserts: (a) popup absent before hover, (b) popup absent immediately after hover (≤50ms — Codex iter-1 P2 debounce check), (c) popup visible within 500ms — confirming the 300ms Provider delay fires correctly. Asserts content: tier T1, Published: 2024-03-15, quote excerpt.

## Risks for Codex Red-Team
1. **Base UI Tooltip API:** `Tooltip.Root` accepts `delay` prop directly per @base-ui/react/tooltip API (see node_modules/@base-ui/react/tooltip docs).
2. **Existing tests:** `performance_hover.spec.ts` already exercises hover behavior — verify the new `delay={300}` doesn't break its timing.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~120 LOC. Under 200.

## Acceptance criteria

1. `EvidenceTooltip.publishedDate?: string | null` prop added.
2. Tooltip popup renders `Published: <date>` when prop present, omits when absent.
3. Harness route wraps tooltip in `<EvidenceTooltipProvider delay={300}>`; existing inspector call site untouched (Codex iter-1 P1 #1).
4. New `evidence-tooltip-popup` testid on Popup.
5. Harness route + Playwright spec assert popup content + debounce baseline.
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
