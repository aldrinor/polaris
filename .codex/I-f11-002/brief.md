# Codex Brief Review — I-f11-002 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f11-002 — Append-to-existing-report rendering. Scope: UI appends below original with separator. Acceptance: Playwright; clear separator visible. LOC estimate 110.
- **Substrate today:** existing `VerifiedReportView` renders a single report. No follow-up append surface.
- **Honest framing per CLAUDE.md §9.4:** ship a small `FollowUpAppendView` component that takes `original: VerifiedReport` and `appended: VerifiedReport` props and renders both with a labeled separator between them. New `/sentence_hover_test/follow_up_append` fixture page; Playwright spec asserts both reports + separator visible. Production wiring (graph_v4 producing `appended` from FollowUpAgent.compose, page route at `/runs/{run_id}/followup/{follow_up_id}`) is I-f11-002b.

## Plan

### `web/app/generation/components/follow_up_append_view.tsx` (NEW)

1. Component `FollowUpAppendView({ original, appended }: { original: VerifiedReport; appended: VerifiedReport })`.
2. Render `<VerifiedReportView report={original} />`, then `<hr data-testid="follow-up-separator" />` with caption "Follow-up appended below", then `<VerifiedReportView report={appended} />`.
3. Caption explicitly says "Follow-up appended". Substrate-honest about what this UI is.

### `web/app/sentence_hover_test/follow_up_append/page.tsx` (NEW fixture)

4. Use minimal VerifiedReport for both — original has 1 sentence, appended has 1 sentence (different content).

### `web/tests/e2e/follow_up_append.spec.ts` (NEW)

5. Visit `/sentence_hover_test/follow_up_append`.
6. Assert 2 `verified-report-view` elements visible (one per report).
7. Assert `follow-up-separator` visible with text "Follow-up appended below".

## Risks for Codex Red-Team

1. **Existing test fixtures:** reuse pattern from `memory_cite/page.tsx` (I-f14-005).
2. **§9.4 N/A frontend.**
3. **CHARTER §3 LOC cap:** estimated component ~25, fixture page ~70, spec ~20 = ~115. Tight; will trim if over.

## Acceptance criteria

1. New `web/app/generation/components/follow_up_append_view.tsx`.
2. New `web/app/sentence_hover_test/follow_up_append/page.tsx` fixture.
3. New `web/tests/e2e/follow_up_append.spec.ts`: asserts 2 reports + separator.
4. CHARTER §3 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-4.
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
