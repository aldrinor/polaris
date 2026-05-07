# Codex Diff Review — I-f5-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**Issue:** I-f5-005 — Inspector multi-span support
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `8c692caac1b255283d3bcff712ec3002d09e6e98280f0c94c4699597555c14b5`
**LOC:** 93 net (under CHARTER §1 200-cap)

## Files

```
web/app/generation/components/sentence_inspector.tsx    EDIT (group-by-source refactor + SpanQuote split)
web/app/sentence_hover_test/_demo.tsx                   EDIT (sec_x:13 multi-span; sec_x:14 multi-source)
web/tests/e2e/sentence_inspector_source.spec.ts         EDIT (testid renamed inspector-span-0 -> inspector-span-0-0)
web/tests/e2e/sentence_inspector_multispan.spec.ts      NEW +42 (2 Playwright tests)
```

## What changed

### Refactor (sentence_inspector.tsx)
- Tokens grouped by `source_id` into `Map<string, ParsedToken[]>` preserving first-occurrence order. Iterated as `[source_id, group_tokens][]`.
- `SourceCard` now takes `tokens: ParsedToken[]` (was single `token`); renders source URL/tier/trace ONCE at top, then iterates over `tokens` rendering one `<SpanQuote>` per span.
- `SpanQuote` extracted as a separate component handling out-of-range guard + blockquote rendering. testid `inspector-span-{i}-{j}` where i = source group index, j = span index within group.
- Existing testids preserved: `inspector-source-{i}` / `inspector-source-url-{i}` / `inspector-tier-{T}` / `inspector-trace-{i}` / `inspector-source-missing-{i}` continue to refer to the per-source group card. Span testid changed from `inspector-span-{i}` to `inspector-span-{i}-{j}`.
- I-f5-003 spec (`sentence_inspector_source.spec.ts`) updated to match the new j=0 testid (`inspector-span-0-0`).

### Demo fixture (_demo.tsx)
- APPENDED sec_x:13: two tokens to src-0 (spans 0-30, 60-90) → multi-span same-source.
- APPENDED sec_x:14: one token to src-1 + one to src-2 → multi-source.
- Existing sentences sec_x:0..12 preserved unchanged.

### New Playwright spec (sentence_inspector_multispan.spec.ts)
- Test 1 (sec_x:13 same-source): exactly ONE source card; `inspector-source-1` has count 0; TWO blockquotes (`inspector-span-0-0`, `inspector-span-0-1`); URL/trace rendered ONCE.
- Test 2 (sec_x:14 multi-source): TWO source cards; each card has one span (`inspector-span-0-0`, `inspector-span-1-0`); `inspector-span-0-1` has count 0.

## Verification
- `npx tsc --noEmit` passes (web/), exit 0.
- I-f5-003 spec assertions updated for new testid scheme; agreement spec (I-f5-004) unaffected (uses sentence-text testids, not span testids).

## Risks for Codex Red-Team

1. **Testid scheme migration:** I-f5-003 used `inspector-span-{i}`; new scheme is `inspector-span-{i}-{j}`. Existing spec updated in same diff to assert `inspector-span-0-0`. Verify no other test references `inspector-span-N` (single index).
2. **Map iteration order:** `Map<source_id, ...>` insertion order preserved per ECMAScript spec. Test 2 asserts src-1 → idx 0, src-2 → idx 1 in token-occurrence order.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 93 net. Comfortably under 200.
5. **No backend change, no fixture sweep, no schema migration.**
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
