# Codex Diff Review — I-f7-002 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only.

**Issue:** I-f7-002 — Gap reason taxonomy frozen as enum
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `ee67d4223717ba498325ef60aad81e2c811a80a5c2473bd2a51e3b9c3e816f0b`
**LOC:** 90 net (under CHARTER §1 200-cap)

## Files

```
src/polaris_graph/generator2/verified_report.py            +30 (GapReason Literal + reason field type + reason_detail)
tests/polaris_graph/generator2/test_verified_report.py     +44 (3 new tests + I-f7-001 test updated)
web/lib/api.ts                                             +13 (GapReason type + reason: GapReason + reason_detail)
web/app/generation/components/frame_coverage_panel.tsx     +14 (GAP_REASON_LABEL + render with detail)
web/app/sentence_hover_test/_demo.tsx                      +2/-1 (gap reason → enum)
web/tests/e2e/frame_coverage_panel.spec.ts                 +2/-1 (assertion text updated)
```

## What changed

### Backend
- `GapReason` Literal: 9 values exactly per issue_breakdown.md spec.
- `FrameGap.reason` switched from `str` → `GapReason`; bogus values now raise ValidationError.
- `FrameGap.reason_detail: str | None` optional supplement (max 500 chars).
- 3 new tests: 9-value enum acceptance, bogus rejection, reason_detail length-bound.
- I-f7-001's `test_frame_coverage_with_gaps_passes` updated to use enum + detail.
- 43 generator2/test_verified_report.py tests pass.

### Frontend
- `GapReason` Literal type + optional `reason_detail` on `FrameGap`.
- `GAP_REASON_LABEL: Record<GapReason, string>` mapping for UI display.
- Gap row renders as `<entity_name> — <Label>: <detail>` (detail elided when null).
- Demo + Playwright updated.

## Verification
- `PYTHONPATH=src pytest tests/polaris_graph/generator2/test_verified_report.py`: 43 passed.
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Breaking schema change:** I-f7-001's str-typed reason is replaced. Only consumers within this same diff (1 backend test + 1 demo + 1 spec); all updated.
2. **Honest substrate:** live generator still doesn't populate `frame_coverage` (per I-f7-001 scope-narrow); only demo path renders the panel.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** 90 net. Under 200.
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
