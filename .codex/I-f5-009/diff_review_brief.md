# Codex Diff Review — I-f5-009 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only (do NOT spawn dev servers/browsers; sandbox blocks them).

**Issue:** I-f5-009 — Every assertion gated-and-clickable
**Brief:** APPROVED iter 1
**Canonical-diff-sha256:** `d1bb66c945e91770d7201d192a7aac5d6918b5035e13d4a1d4ec0b3ae6d0011b`
**LOC:** 161 net (under CHARTER §1 200-cap)

## Files

```
src/polaris_graph/generator2/verified_report.py          +21 (AssertionSurface Literal + field)
tests/polaris_graph/generator2/test_verified_report.py   +33 (3 new tests)
web/lib/api.ts                                            +9 (AssertionSurface type + ?: field)
web/app/generation/components/verified_report_view.tsx   +44 (legend + per-row badge with prose-default coercion)
web/app/sentence_hover_test/_demo.tsx                    +18 (5 new sec_x:18..22 with non-prose surfaces)
web/tests/e2e/sentence_inspector_surfaces.spec.ts        NEW +35 (legend + 5 surface tests)
```

## What changed

### Backend
- `AssertionSurface` Literal: 6 values (prose / table / summary_bullet / limitation / caption / heading).
- `VerifiedSentence.assertion_surface: AssertionSurface = "prose"` — back-compat default for all existing fixtures.
- 3 new schema tests: default == prose, all 6 values accepted, bogus value rejected.
- 36 generator2/test_verified_report.py tests pass.

### Frontend
- `web/lib/api.ts`: `AssertionSurface` type + optional `assertion_surface?: AssertionSurface`.
- `verified_report_view.tsx`:
  - Per Codex iter-1 P2: explicit `surface = sentence.assertion_surface ?? "prose"` coercion before deciding to render badge. No badge for prose; badge for the other 5 surfaces.
  - Surface badges (`surface-badge-{type}`) prepend the sentence text in the row.
  - Report-header `assertion-surface-legend` lists all 6 surface labels.
- `_demo.tsx`: APPENDED 5 sentences (sec_x:18..22) with non-prose surfaces. Existing sec_x:0..17 preserved.
- 6 Playwright tests: legend visible + 5 per-surface clickability/badge.

## Verification
- `PYTHONPATH=src pytest tests/polaris_graph/generator2/test_verified_report.py`: 36 passed.
- `npx tsc --noEmit` (web/): exit 0.

## Risks for Codex Red-Team

1. **Coercion at render site:** `?? "prose"` defensive default normalizes `undefined` to "prose" so legacy rows never get a non-prose badge (Codex iter-1 P2 fix).
2. **Demo append-only:** existing sec_x:0..17 preserved; multispan/agreement/synthesis/retracted-stale/sec_x:5 specs all keep passing.
3. **Surface field optional in TS:** undefined coerces to "prose" at render; no badge — same behavior as if backend never sent the field.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** 161 net. Under 200.
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
