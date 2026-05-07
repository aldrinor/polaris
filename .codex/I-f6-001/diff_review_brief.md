# Codex Diff Review — I-f6-001 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f6-001 — Hover-card with debounced rendering
**Brief:** APPROVED iter 2
**Canonical-diff-sha256:** `5090c4a49973e973e0b51d4e8cf4462325ba7c7ec559b7d824ff50fd48595996`
**LOC:** 91 net (under CHARTER §1 200-cap)

## Files

```
web/components/ui/evidence-tooltip.tsx                       +18 (publishedDate prop, render row, Popup testid)
web/app/sentence_hover_test/_demo_evidence_tooltip.tsx       NEW +33 (harness with EvidenceTooltipProvider delay={300})
web/app/sentence_hover_test/evidence_tooltip/page.tsx        NEW +5 (Next route)
web/tests/e2e/evidence_tooltip.spec.ts                       NEW +29 (debounce + content assertions)
```

## What changed

### Component
- `EvidenceTooltip.publishedDate?: string | null` prop added. Renders `Published: <date>` line between URL and quote when present.
- `evidence-tooltip-popup` testid on `Tooltip.Popup`.
- `evidence-tooltip-published` testid on the date line for explicit assertion.
- Existing inspector call site at `web/app/inspector/[runId]/page.tsx:341` UNTOUCHED (Codex iter-1 P1 #2 — EvidenceContract.SourceSpan lacks publication_date; data-path expansion deferred to a separate Issue).

### Harness
- `_demo_evidence_tooltip.tsx`: minimal `<EvidenceTooltipProvider delay={300}>` wrapper around one `<EvidenceTooltip>` with all 4 fields populated. Trigger has `data-testid="evidence-tooltip-trigger"`.
- `/sentence_hover_test/evidence_tooltip` route mounts the harness.

### Playwright
- Test asserts: (a) popup absent before hover, (b) popup absent ~50ms after hover (debounce baseline per Codex iter-1 P2), (c) popup visible within 500ms (300ms Provider delay + buffer), (d) content includes `tier T1`, `Published: 2024-03-15`, `randomized trial enrolled 1247 adults` excerpt.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- No backend changes; existing `performance_hover.spec.ts` and `inspector/[runId]` call site untouched.

## Risks for Codex Red-Team

1. **Existing Tooltip.Provider:** other call sites that wrap their own EvidenceTooltip in a Provider continue to work; the harness's local Provider only affects the harness route.
2. **Optional prop:** `publishedDate` defaults to undefined; existing inspector callers unaffected.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 91 net. Under 200.
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
