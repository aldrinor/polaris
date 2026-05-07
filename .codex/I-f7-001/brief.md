# Codex Brief Review — I-f7-001 (ITER 1 of 5)

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

- **Context:** I-f7-001 — top-of-report frame coverage panel (above-the-fold). Surfaces "X of N entities covered" + lists gaps with reason. Acceptance per issue_breakdown.md: 14/15 entities → "1 gap: <name>, reason."
- **Constraints:** Heritage `frame_manifest.py` (M-60) exists in `polaris_graph/generator/` for the legacy V30 sweep. This Issue ships a NEW lightweight surface scoped to the v6.2 generator2/VerifiedReport pipeline — a per-report `frame_coverage` field consumed by the Inspector UI. Heritage M-60 stays untouched.
- **Done-when:** acceptance criteria 1-7 below.

## Plan

### Backend
1. `src/polaris_graph/generator2/verified_report.py`:
   - Add `FrameGap` BaseModel: `entity_name: str (min_length=1, max_length=200)`, `reason: str (min_length=1, max_length=500)`.
   - Add `FrameCoverage` BaseModel: `covered_entity_count: int (ge=0)`, `total_entity_count: int (ge=0)`, `gaps: list[FrameGap] = []`. Validator: `covered + len(gaps) <= total_entity_count`; `len(gaps) == total_entity_count - covered_entity_count`.
   - Add `frame_coverage: FrameCoverage | None = None` field to `VerifiedReport` (optional; existing fixtures stay valid).
2. Tests in `test_verified_report.py`: 3 new tests — minimal-no-gaps, with-gaps validator passes, count-mismatch rejected.

### Frontend
3. `web/lib/api.ts`: add `FrameGap` interface + `FrameCoverage` interface + optional `frame_coverage?: FrameCoverage | null` on `VerifiedReport`.
4. `web/app/generation/components/frame_coverage_panel.tsx` (NEW):
   - `FrameCoveragePanel({ coverage }: { coverage: FrameCoverage | null })`.
   - When `coverage === null`: render nothing (back-compat with reports that don't yet supply coverage).
   - When `coverage.gaps.length === 0`: render an emerald success Alert with `data-testid="frame-coverage-complete"` showing `covered/total entities covered`.
   - When `coverage.gaps.length > 0`: render an amber Alert with `data-testid="frame-coverage-gaps"` showing `covered/total entities covered`, then a list of gaps each with `data-testid="frame-coverage-gap-{idx}"` formatted as `{entity_name} — {reason}`.
   - Progress bar: simple inline `<div>` with width=`(covered/total)*100%`, testid `frame-coverage-progress`.
5. `web/app/generation/components/verified_report_view.tsx`: render `<FrameCoveragePanel coverage={report.frame_coverage ?? null} />` ABOVE the existing report Card (top-of-report).
6. `web/app/sentence_hover_test/_demo.tsx`: add `frame_coverage` to demo REPORT — 14 covered of 15, 1 gap (entity "Pediatric population", reason "no Cochrane review found").
7. `web/tests/e2e/frame_coverage_panel.spec.ts` (new):
   - Test 1: panel visible at top of `/sentence_hover_test`; `frame-coverage-gaps` testid present.
   - Test 2: gap entry visible with entity name "Pediatric population" + reason "no Cochrane review found".
   - Test 3: progress bar testid present.

## Risks for Codex Red-Team
1. **Schema validator exhaustiveness:** validator must reject when `covered + len(gaps) != total`. Allows total=0 + covered=0 + no gaps (degenerate empty case).
2. **Existing fixtures back-compat:** `frame_coverage` is optional with default None; no fixture sweep required.
3. **Frontend type:** `frame_coverage?: FrameCoverage | null`; defensive default behavior renders nothing.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~140 LOC (backend +30, types +12, panel +50, view +3, demo +15, test +30). Under 200.
6. **No new package dep.**

## Acceptance criteria

1. `FrameGap` + `FrameCoverage` Pydantic models added.
2. Validator rejects count mismatch (covered + gaps != total).
3. `VerifiedReport.frame_coverage: FrameCoverage | None = None` field added.
4. 3 backend tests cover model behavior.
5. Frontend `FrameCoveragePanel` renders 3 visual states (none / complete / gaps).
6. Demo fixture has 14/15 with one gap; Playwright spec covers panel + gap entry + progress.
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
