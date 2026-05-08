# Codex Brief Review — I-f6-004 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix (EvidencePool contract):** `RetrievalSource` exposes `source_id` (NOT `evidence_id`), `publication_date` (NOT `published_date`), `full_text` / `snippet` (NOT `span_text`). Panel data contract revised: pass **`ParsedToken[]`** (already exported from `web/lib/provenance_tokens.ts`) into `MultiSourcePanel`, then group by `source_id` so each row can show all (start,end) excerpts cited by THAT sentence. Render `source.source_id`, `source.publication_date`, and `(source.full_text ?? source.snippet)?.slice(start, end)` (with same out-of-range fallback as `SentenceInspector`: render literal "[span out of range]" if start≥len or end>len).
- **P2 fix (no extra regex):** SentenceRow uses `parseAllTokens(sentence.provenance_tokens)` from `web/lib/provenance_tokens.ts`; no new regex.
- **P2 fix (null-pool):** when `pool === null` OR a `source_id` is not found in `pool.sources`, render the missing-source fallback row ("Source not found in evidence pool: <source_id>"); panel still mounts and lists each requested source_id.
- **P2 fix (e2e propagation):** Playwright spec adds `await expect(page.getByTestId("sentence-inspector-sheet")).toHaveCount(0)` after clicking the badge, mirroring the I-f8-002 contradiction propagation guard.

## Original brief (iter 1)

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

- **Issue:** I-f6-004 — Multi-source claim cross-ref panel.
- **Acceptance criteria from `state/polaris_restart/issue_breakdown.md`:**
  - `count "5 sources" → click → panel with all 5`
  - `Playwright cross-ref`
- **Substrate:** `VerifiedSentence.provenance_tokens: list[str]` already encodes citations. Each token is `[#ev:<source_id>:<start>-<end>]`. The set of distinct `source_id` values across a sentence's tokens is the multi-source count.
- **Display threshold:** the issue's title example is "5 sources." I'll show the badge when distinct `source_id` count ≥ 3 (rationale: 2 sources is the contradiction-detection floor already surfaced by I-f8-001 "⚠ N sources disagree"; a "multi-source corroboration" surface should kick in at 3 to be informative, not noisy on every 2-cite sentence). Clicking opens a panel with **all** distinct sources, not just the first 3 — count is the gate, panel content is exhaustive.
- **Scope:** test-and-component-only. No backend/schema change. Reuses `EvidencePool` already plumbed for `pool` prop.

## Plan

### Frontend

1. New component `web/app/generation/components/multi_source_panel.tsx`:
   - Props: `open: boolean`, `onOpenChange(open: boolean)`, `tokens: ParsedToken[]`, `pool: EvidencePool | null`, `sentence_text: string` (for context header).
   - Renders `<Sheet>` (right side, ~40% width to match `EvaluatorPane` and `ContradictionPane`).
   - Header: "Multi-source claim — N sources" (N = distinct `source_id` count from tokens).
   - Body: group `tokens` by `source_id`. For each unique source_id:
     - Look up `pool?.sources.find(s => s.source_id === source_id)`.
     - If found: render row with `source.source_id` (display id), `source.tier` badge (T1/T2/T3 with existing tone classes), truncated `source.url`, `source.publication_date` if present, and per-(start,end) span excerpts via `(source.full_text ?? source.snippet)?.slice(start, end)` (mirror `SentenceInspector` out-of-range fallback: literal "[span out of range]" if `start >= text.length || end > text.length`).
     - If `pool === null` OR source not found: render "Source not found in evidence pool: <source_id>" (honest fallback per LAW II — no silent default).
   - testids: `multi-source-pane-title`, `multi-source-pane-source-{source_id}`, `multi-source-pane-tier-{source_id}`, `multi-source-pane-missing-{source_id}` (for the fallback row).

2. `web/app/generation/components/verified_report_view.tsx`:
   - Add `multi_source_open` state at root: `{ tokens: ParsedToken[]; sentence_text: string } | null`.
   - Thread `onSelectMultiSource(payload)` callback through SectionCard → SentenceRow (same pattern as `onSelectContradiction` / `onSelectEvaluator` from I-f8-002 / I-f9-002).
   - In SentenceRow:
     - Use `parseAllTokens(sentence.provenance_tokens)` from `web/lib/provenance_tokens.ts` (no new regex).
     - Compute `distinct_source_count = new Set(tokens.map(t => t.source_id)).size`.
     - When `!dropped && distinct_source_count >= 3`, render an inline button:
       - `data-testid={"multi-source-${sentence_id}"}`
       - Label: `📚 ${distinct_source_count} sources`
       - `onClick` with `stopPropagation` and `onSelectMultiSource({ tokens, sentence_text: sentence.sentence_text })`.
       - `onKeyDown` Enter/Space with `stopPropagation` + `preventDefault` + same call (per I-f8-002 click-propagation pattern).
       - Class: blue accent (rose=evaluator, amber=contradiction; corroboration is neutral-positive so blue distinguishes it).
   - Render `<MultiSourcePanel>` at root alongside `<ContradictionPane>` / `<EvaluatorPane>`.

### Demo data

3. `web/app/sentence_hover_test/_demo.tsx`:
   - Add or modify ONE existing demo sentence to have 5 distinct provenance source_ids matching pool sources. Confirm the corresponding 5 sources exist in the demo `EvidencePool`. (Alternative: add a new section with one such sentence — keep it small.)

### Playwright

4. `web/tests/e2e/multi_source_panel.spec.ts` (new):
   - Visit `/sentence_hover_test` (existing demo route from prior F5/F8 issues).
   - Find the multi-source sentence by its data-testid `multi-source-{sentence_id}`.
   - Assert badge text contains "5 sources".
   - Click it; assert pane visible with title containing "Multi-source claim — 5 sources".
   - **Propagation guard:** assert `getByTestId("sentence-inspector-sheet").toHaveCount(0)` (badge click must NOT also open SentenceInspector).
   - Assert all 5 source rows present via `multi-source-pane-source-{source_id}` selectors.
   - Assert each row has a tier badge.

## Risks for Codex Red-Team

1. **Threshold ≥ 3:** the issue spec example says "5 sources" — pick a threshold that surfaces the badge for 3+, not 2+, to avoid duplicating I-f8-001's "⚠ N sources disagree" badge that already fires at 2+ for contradictions.
2. **Click-propagation discipline:** matches the I-f8-002 pattern (stopPropagation on click + onKeyDown). Without it, clicking the badge opens BOTH the multi-source panel AND the SentenceInspector.
3. **Honest fallback:** if a `source_id` from a provenance token isn't found in `pool.sources`, render "Source not found" — DO NOT silently skip per LAW II (no silent fallbacks).
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~120 LOC component change + ~40 LOC spec + ~30 LOC demo addition = ~190. Under 200.

## Acceptance criteria

1. New `MultiSourcePanel` component renders all distinct cited sources (not just 3).
2. SentenceRow inline badge appears when distinct `source_id` count ≥ 3, hidden otherwise.
3. Badge click opens panel; click propagation does NOT also open SentenceInspector.
4. Panel rows show evidence_id + tier + url + published_date + span_text (when available).
5. Honest fallback: missing source_id renders "Source not found in evidence pool."
6. Playwright spec covers the 5-source path.
7. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-7.

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
