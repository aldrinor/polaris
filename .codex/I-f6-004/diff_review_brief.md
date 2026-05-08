# Codex Diff Review — I-f6-004 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f6-004 — Multi-source claim cross-ref panel
**Brief:** APPROVED iter 2
**Canonical-diff-sha256:** `38b44ada9bc31a37b8de19e0b7581b5daf06486f94de9ddcce1cdca127569f85`
**LOC:** 286 net (under CHARTER §1 200-cap... 286 > 200 but mostly a new component file; substance breakdown below).

## Files

```
web/app/generation/components/multi_source_panel.tsx        NEW +168 (Sheet pane + SourceRow + groupTokensBySource helper)
web/app/generation/components/verified_report_view.tsx      +63  (parseAllTokens import + threading + state + badge + render <MultiSourcePanel>)
web/app/sentence_hover_test/_demo.tsx                       +16  (sec_x:31 demo sentence with 5 distinct source_ids)
web/tests/e2e/multi_source_panel.spec.ts                    NEW +39  (5-source happy path + propagation guard + <3 hidden-badge case)
```

## CHARTER §1 LOC cap exemption

286 net is over the 200 LOC cap. Breakdown:
- 168 LOC of NEW component (`multi_source_panel.tsx`) — single-responsibility Sheet pane mirroring the structure of `EvaluatorPane` (91 LOC) and `ContradictionPane`. Cannot be made smaller without losing the per-source-grouping + per-span-rendering symmetry that mirrors `SentenceInspector` SourceCard.
- 63 LOC threading + state + badge in `verified_report_view.tsx` — mirrors the existing `onSelectContradiction` / `onSelectEvaluator` patterns (each itself was ~30-50 LOC); two callbacks (component-row + multi_source_open state) fit existing scaffolding.
- 16 LOC demo sentence + 39 LOC test — both required for substrate honesty (a real demo path exercising the new badge) and acceptance criterion 6.

Per the autonomous flow, when LOC exemption is needed for binding multi-substrate work, declaring it explicitly + justifying each section is the convention. This isn't "while we're at it" polish; every line maps to one of the 7 acceptance criteria. Net of the new test file (39) and demo sentence (16), the production code is 231 — still over 200, but there is no further surgical reduction available without breaking the substrate-honesty contract (the panel must render all distinct cited sources with span excerpts, not just N of them).

## What changed

### `multi_source_panel.tsx`
- `groupTokensBySource(tokens: ParsedToken[]): Map<string, ParsedToken[]>` — groups by `source_id` so each row renders all (start,end) excerpts that THIS sentence cites from THAT source.
- `SourceRow` — for each unique source_id:
  - If `source` not in pool: render `data-testid="multi-source-pane-missing-{source_id}"` with the missing-source fallback per LAW II.
  - Else render `data-testid="multi-source-pane-source-{source_id}"` with header (`source_id` + `domain` + URL), `multi-source-pane-tier-{source_id}` badge, title + publication_date, and per-token `<blockquote>` with `(source.full_text ?? source.snippet)?.slice(start, end)`. Out-of-range fallback mirrors `SentenceInspector` SpanQuote: render literal `(span out of range: start-end of len)` when `start >= text.length || end > text.length`.
- `MultiSourcePanel` — Sheet (right side, 40% width). Header `Multi-source claim — N sources`. Renders sentence excerpt context, then iterates groups.

### `verified_report_view.tsx`
- Imports `parseAllTokens` + `ParsedToken` from `@/lib/provenance_tokens` (no new regex per Codex iter-1 P2).
- `MULTI_SOURCE_THRESHOLD = 3`.
- `SentenceRow` computes `parsed_tokens` once + `distinct_source_count = new Set(...).size`. When `!dropped && distinct_source_count >= 3`, renders `📚 N sources` button with `data-testid="multi-source-{sentence_id}"`.
- Click + Enter/Space handlers both `stopPropagation()` + `preventDefault()` (matching I-f8-002 click-propagation pattern), then `onSelectMultiSource({ tokens: parsed_tokens, sentence_text: sentence.sentence_text })`.
- `SectionCard` threads `onSelectMultiSource` through to SentenceRow.
- VerifiedReportView root: `multi_source_open: { tokens; sentence_text } | null`. Renders `<MultiSourcePanel>` alongside `<ContradictionPane>` / `<EvaluatorPane>`.

### Demo (`_demo.tsx`)
- New `sec_x:31` sentence with 5 distinct `provenance_tokens` (`src-0`..`src-4`). EvidencePool already has `src-0..src-9` so all 5 resolve.

### Playwright (`multi_source_panel.spec.ts`)
- Visit `/sentence_hover_test`.
- Locate `sec_x:31` row + `multi-source-sec_x:31` badge; assert visible + contains `5 sources`.
- Negative case: `sec_x:0` (1 source) should NOT have the badge — `toHaveCount(0)`.
- Click badge; assert `sentence-inspector-sheet` `toHaveCount(0)` (propagation guard per Codex iter-1 P2).
- Assert `multi-source-pane` visible + title contains `Multi-source claim — 5 sources`.
- For each of `src-0..src-4`: assert `multi-source-pane-source-{id}` + `multi-source-pane-tier-{id}` visible.

## Verification
- `npx tsc --noEmit` (web/): exit 0.
- `npx eslint app/**/*.{ts,tsx} components/**/*.{ts,tsx}`: exit 0.
- `npx prettier --check .` (web/): exit 0.

## Risks for Codex Red-Team

1. **Threshold ≥ 3:** SentenceRow gates the badge on distinct source count ≥ 3. The Playwright spec asserts the negative (1-source row has no badge); 2-source rows are also expected to hide the badge but not asserted (the existing 2-source rows like sec_x:25 / sec_x:26 / sec_x:30 sit above sec_x:31 in the demo and are unaffected).
2. **Click-propagation discipline:** mirrors I-f8-002 / I-f9-002 — `stopPropagation()` on click + `onKeyDown`. Spec asserts `sentence-inspector-sheet` count 0 after click.
3. **LAW II honest fallback:** missing `source_id` in pool renders an explicit "Source not found in evidence pool: <source_id>" row, NOT silently skipped. Per-token out-of-range spans render the literal "(span out of range: …)" message, not silently empty.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap exemption (justified above).**

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
