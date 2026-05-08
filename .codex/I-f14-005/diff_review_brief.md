# Codex Diff Review — I-f14-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f14-005 — Cited recall
**Brief:** APPROVED iter 1 (zero P0/P1; 2 P2 noted: title with id+content acknowledged via title text; minimal new fixture page used per the more-direct option)
**Canonical-diff-sha256:** `07d0535b79da313380610a0749402e1cc74f39eb9c47e2684bb3f8c7db564c96`
**LOC:** 105 net (under CHARTER §3 200-cap)

## Files

```
web/app/generation/components/verified_report_view.tsx     +13   (prior-run-badge inline render)
web/app/sentence_hover_test/memory_cite/page.tsx           NEW +63 (minimal fixture page)
web/tests/e2e/cited_recall_badge.spec.ts                   NEW +29 (1 spec: badge on memory-cite, no badge on non-memory)
```

## What changed

### `verified_report_view.tsx`
- Inside SentenceItem, added inline render: when `!dropped && parsed_tokens.some(t => t.source_id.startsWith("ev_memory_"))`, render a purple chip `<span data-testid="prior-run-badge-{sentence_id}">from prior run</span>`.
- `title` attribute lists all matching `ev_memory_*` source_ids per Codex iter-1 P2 (so reviewer can see which memory-derived evidence id contributed).

### `memory_cite/page.tsx` (NEW fixture)
- Renders VerifiedReportView with a 2-sentence report:
  - Sentence 0: token `[#ev:ev_memory_abc123def456:0-90]` — should render badge.
  - Sentence 1: token `[#ev:src-1:0-60]` — should NOT render badge.
- Includes all required VerifiedReport fields (pipeline_verdict, generator_model, etc.) per schema.

### `cited_recall_badge.spec.ts`
- 1 test asserting both "rendered with id+title" (positive) and "not rendered for non-memory" (negative).

## Verification

- `npx tsc --noEmit`: exit 0.
- `npx eslint` on changed files: exit 0.
- `npx prettier --check`: exit 0.
- `npx next build`: succeeds; `/sentence_hover_test/memory_cite` static prerender included.
- `npx playwright test cited_recall_badge.spec.ts --project chromium`: 1/1 passing in 1.5s.

## Risks for Codex Red-Team

1. **Click-through to prior run deferred:** issue acceptance is "cite-in-current"; click-through is follow-up I-f14-005b.
2. **Title-text scope:** lists evidence_ids but not the underlying memory content (which would require pool-derived lookup). Acceptable for substrate-honest demo.
3. **§9.4 N/A frontend.**
4. **CHARTER §3 LOC cap:** 105 net. Under 200.

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
