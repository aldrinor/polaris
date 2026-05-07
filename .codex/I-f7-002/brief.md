# Codex Brief Review — I-f7-002 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review (separate Codex call) = code-matches-plan.

## Pre-flight

- **Context:** I-f7-002 — gap reason taxonomy frozen as enum. I-f7-001 introduced `FrameGap.reason: str` (free text). This Issue replaces it with a Literal enum: `paywalled | no_oa | source_tier_ineligible | language_unavailable | retracted_only | jurisdiction_outside | not_indexed | embargoed | other`.
- **Constraints:** Breaking schema change (`reason: str` → `reason: GapReason` Literal). I-f7-001 demo fixture has `reason: "no Cochrane review found"` which doesn't match any enum — must update demo + add backward-compat handling for the migration window OR accept that the Literal rejects "no Cochrane review found" and update the demo.
- **Done-when:** acceptance criteria 1-7 below.

## Plan

### Backend
1. `src/polaris_graph/generator2/verified_report.py`:
   - Add `GapReason` Literal: 9 values (`paywalled`, `no_oa`, `source_tier_ineligible`, `language_unavailable`, `retracted_only`, `jurisdiction_outside`, `not_indexed`, `embargoed`, `other`).
   - Change `FrameGap.reason: str` → `FrameGap.reason: GapReason`.
   - Add `FrameGap.reason_detail: str | None = None` (free-text supplement; max 500 chars). Allows the UI to show "{enum_label}: {detail}" e.g. "Paywalled: NEJM article behind subscription wall."

### Backend tests
2. `tests/polaris_graph/generator2/test_verified_report.py`: 4 new tests:
   - All 9 enum values accepted.
   - Bogus value rejected with ValidationError.
   - reason_detail optional + length-bounded.
   - Existing `FrameGap(entity_name="Pediatric", reason="no Cochrane review")` test from I-f7-001 must be updated to use enum + detail.

### Frontend
3. `web/lib/api.ts`: add `GapReason` Literal type + change `FrameGap.reason: GapReason` + add `reason_detail?: string | null` field.
4. `web/app/generation/components/frame_coverage_panel.tsx`:
   - Add `GAP_REASON_LABEL: Record<GapReason, string>` constant.
   - Render gap row as `<entity_name> — <GAP_REASON_LABEL[reason]>{reason_detail ? ": " + reason_detail : ""}`.
5. `web/app/sentence_hover_test/_demo.tsx`: change demo gap to `reason: "no_oa", reason_detail: "no open-access version of Cochrane review available"`.
6. `web/tests/e2e/frame_coverage_panel.spec.ts`: update assertion text to match new enum-driven label ("No OA").

## Risks for Codex Red-Team
1. **Breaking change:** I-f7-001's `reason: str` is replaced by Literal. Demo + existing test must be updated in same diff.
2. **Existing fixtures:** only the I-f7-001 demo + backend test reference FrameGap; both updated in this diff.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~80 LOC. Under 200.

## Acceptance criteria

1. `GapReason` Literal with exactly 9 enum values.
2. `FrameGap.reason: GapReason` (no longer free str).
3. `FrameGap.reason_detail: str | None` optional supplement.
4. 4 backend tests cover enum values + rejection + reason_detail + I-f7-001 test updated.
5. Frontend `GapReason` type + `GAP_REASON_LABEL` mapping.
6. Demo + Playwright updated to enum-driven labels.
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
