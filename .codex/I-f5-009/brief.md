# Codex Brief Review — I-f5-009 (ITER 1 of 5)

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

- **Context:** I-f5-009 — every assertion in a verified report must be gated-and-clickable OR explicitly marked ungated. Six assertion-bearing surfaces per Carney plan §F: prose sentences (already covered I-f5-001..007), tables, summary bullets, limitations, captions, headings. Each must either route through the Inspector via the same click affordance OR carry a visible `ungated` badge with a reason.
- **Constraints:** Today's verified_report renders only prose sentences (kept-sentence rows). Tables/bullets/captions/headings/limitations don't yet have a render path because the generator doesn't emit those surfaces. This Issue ships the SCHEMA and UI surfaces; today's data path produces all-prose; future Issues wire generator emission of the other types.
- **Done-when:** acceptance criteria 1-9 below.

## Plan

### Backend
1. `src/polaris_graph/generator2/verified_report.py`: add `AssertionSurface` Literal type:
   ```python
   AssertionSurface = Literal["prose", "table", "summary_bullet", "limitation", "caption", "heading"]
   ```
   Add `assertion_surface: AssertionSurface = "prose"` field to `VerifiedSentence` (default "prose" for back-compat with existing fixtures).
2. Tests in `test_verified_report.py`: 1 new test covering default + each enum value rejection of bogus value.

### Frontend
3. `web/lib/api.ts`: add `AssertionSurface` type and `assertion_surface?: AssertionSurface` (OPTIONAL with defensive default "prose") to `ReportVerifiedSentence`.
4. `web/app/generation/components/verified_report_view.tsx`:
   - For each kept sentence with `assertion_surface !== "prose"` (or undefined), render same clickable row but with a surface-type badge (`data-testid="surface-badge-{surface}"`) prefix. All surfaces are gated-and-clickable equally — the click affordance is universal.
   - Add a top-of-section legend testid `assertion-surface-legend` listing the 6 surface types as a small caption.
5. `web/app/sentence_hover_test/_demo.tsx`: APPEND 5 new sentences sec_x:18..22 with assertion_surface = "table", "summary_bullet", "limitation", "caption", "heading" respectively (each with a valid token). All clickable, all routed through Inspector.
6. `web/tests/e2e/sentence_inspector_surfaces.spec.ts` (new):
   - Test 1: legend visible on the page.
   - Tests 2-6 (one per non-prose surface): click sec_x:18..22 → assert Inspector opens AND `surface-badge-{type}` visible on the row.

## Risks for Codex Red-Team
1. **Schema default back-compat:** `assertion_surface = "prose"` default keeps all existing fixtures (~17 sites from I-f5-004) valid without any change. No fixture sweep required.
2. **Future generator wiring:** today's generator emits no non-prose sentences. The schema field is the surface; future Issues populate it (e.g., when a table-summary cell becomes a verified assertion).
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~150 LOC (backend +20, types +5, view +30, demo +50, tests +50). Under 200.
5. **No new package dep.**

## Acceptance criteria

1. `AssertionSurface` Literal type added (6 values).
2. `VerifiedSentence.assertion_surface` field defaults to "prose"; bogus value rejected by Pydantic Literal.
3. 1 new backend test.
4. Frontend `ReportVerifiedSentence` includes `assertion_surface?: AssertionSurface`.
5. Inspector row renders `surface-badge-{type}` when surface is non-prose.
6. Section header includes `assertion-surface-legend` listing all 6 surfaces.
7. Demo fixture has sec_x:18..22 each with one non-prose surface.
8. Playwright spec covers legend + 5 surface clicks; each opens Inspector.
9. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-9.

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
