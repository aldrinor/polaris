# Codex Brief Review — I-f5-005 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review (separate Codex call) = code-matches-plan. Do NOT mark criteria as "FAIL: not implemented" — that's diff-stage analysis.

## Pre-flight

- **Context:** I-f5-005 — Inspector multi-span support. A sentence may cite ONE source with multiple disjoint spans (e.g. `[#ev:src-1:0-50] [#ev:src-1:100-150]`) OR multiple sources each with their own span. Today's inspector (post I-f5-003) renders one SourceCard per token — so two tokens on the same source = two duplicated cards. Required UX: ONE card per source, with N highlighted spans rendered inside the card.
- **Constraints:** No backend change required (provenance_tokens list already supports N tokens). Honest substrate per CLAUDE.md §9.1: every span is verified independently by strict-verify; this Issue is purely a UI grouping change.
- **Done-when:** acceptance criteria 1-7 below.

**Independence directive:** prior round changelog markers are untrustworthy. Verify against actual code; mismatched marker = P0.

## Plan

### Frontend
1. `web/app/generation/components/sentence_inspector.tsx`
   - Refactor: group `ParsedToken[]` by `source_id` into a `Map<source_id, ParsedToken[]>` (preserve first-occurrence order).
   - `SourceCard` accepts `tokens: ParsedToken[]` instead of single `token: ParsedToken`. Renders the source URL + tier + retrieval trace once at the top, then iterates over `tokens` and renders one `<blockquote>` per span with testid `inspector-span-{i}-{j}` where `i` is source index and `j` is span index within that source.
   - Missing-source path (when source_id not in pool): one card per missing-source group with testid `inspector-source-missing-{i}` (per I-f5-003).
   - Existing testids `inspector-source-url-{i}` / `inspector-tier-{T}` / `inspector-trace-{i}` continue to refer to the per-source card (i = source group index, NOT raw token index). Existing I-f5-003 spec uses `inspector-span-0` (without the j); keep that compatible by using `inspector-span-{i}` when there's only one span in the group, OR by ALSO emitting the legacy `inspector-span-{i}` testid pointing at the first span. Choose: emit BOTH `inspector-span-{i}` (legacy, points to first span only) AND `inspector-span-{i}-{j}` (new) so the existing I-f5-003 spec keeps passing without modification.

2. `web/app/sentence_hover_test/_demo.tsx`
   - APPEND sentence sec_x:13 with TWO tokens to src-0 (e.g. `[#ev:src-0:0-30]` and `[#ev:src-0:60-90]`) to exercise multi-span same-source grouping.
   - APPEND sentence sec_x:14 with two tokens to TWO different sources (mixed: src-1 + src-2) to exercise multi-source rendering.

3. `web/tests/e2e/sentence_inspector_multispan.spec.ts` (new)
   - Test 1: click sec_x:13 → assert ONE source card (first match of `inspector-source-0` testid since src-0 is first-occurring) renders TWO blockquotes (`inspector-span-0-0` and `inspector-span-0-1`) both visible with their respective text content.
   - Test 2: click sec_x:14 → assert TWO source cards (`inspector-source-0` for src-1, `inspector-source-1` for src-2) each with one span (`inspector-span-0-0` and `inspector-span-1-0`).

## Risks for Codex Red-Team
1. **Test backward compatibility:** `web/tests/e2e/sentence_inspector_source.spec.ts` (I-f5-003) clicks `sec_x:5` and asserts `inspector-span-0`. The plan emits BOTH legacy `inspector-span-{i}` and new `inspector-span-{i}-{j}` testids on the first span of each source group, preserving back-compat. Verify the existing spec keeps passing.
2. **Span ordering:** within a source group, spans render in token-occurrence order in the sentence (left-to-right). NOT sorted by span_start.
3. **Map iteration order:** `Map<source_id, ...>` iterates in insertion order in V8/Spidermonkey/JSC. Honest, deterministic.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~110 LOC net (sentence_inspector refactor ~50, demo ~25, Playwright ~35). Under 200.
6. **No backend change, no fixture sweep, no schema migration.**

## Acceptance criteria

1. Tokens grouped by source_id; one SourceCard per source.
2. Each SourceCard shows source URL + tier + trace ONCE; N spans rendered as N blockquotes.
3. New testid scheme `inspector-span-{i}-{j}` where i = source index, j = span index within source.
4. Legacy `inspector-span-{i}` testid preserved (points to first span of source group i).
5. Demo fixture exercises multi-span same-source (sec_x:13) AND multi-source (sec_x:14).
6. Playwright spec covers both cases.
7. Existing I-f5-003 spec (`sentence_inspector_source.spec.ts`) keeps passing.

**Forced enumeration:** before verdict, write one line per criterion 1-7.

**Completeness check:** list files actually read (not just grep'd).

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
