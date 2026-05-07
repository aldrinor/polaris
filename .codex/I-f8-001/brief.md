# Codex Brief Review — I-f8-001 (ITER 1 of 5)

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

- **Context:** I-f8-001 — when a sentence has a contradiction signal (≥2 sources disagree on the cited claim), render an inline `⚠ N sources disagree` badge on that sentence row. Subsequent F8 issues build on this surface (I-f8-002 side pane with all sides, I-f8-003 adversarial cases, etc.).
- **Constraints:** Today's verified_report.py has no contradiction signal — it's a generator-supplied annotation that future Issues populate. This Issue ships the SCHEMA + UI surface; honest substrate per CLAUDE.md §9.4 (no silent overclaim).
- **Done-when:** acceptance criteria 1-7 below.

## Plan

### Backend
1. `src/polaris_graph/generator2/verified_report.py`:
   - Add `ContradictionSignal` BaseModel: `disagreeing_source_count: int (ge=2, le=20)`, `summary: str (min_length=1, max_length=500)`.
   - Add `contradiction: ContradictionSignal | None = None` field to `VerifiedSentence`.
2. Tests in `test_verified_report.py`: 3 new tests:
   - Default None.
   - With signal, count=2, summary present.
   - count=1 rejected (need ≥2 to be a "disagreement").

### Frontend
3. `web/lib/api.ts`: add `ContradictionSignal` interface + optional `contradiction?: ContradictionSignal | null` on `ReportVerifiedSentence`.
4. `web/app/generation/components/verified_report_view.tsx`: in `SentenceRow`, when `sentence.contradiction != null`, render a `⚠ N sources disagree` inline badge with testid `inspector-contradiction-{i}` (where i is the sentence index in section). Tooltip = the summary.
5. `web/app/sentence_hover_test/_demo.tsx`: APPEND sec_x:26 with `contradiction: { disagreeing_source_count: 3, summary: "Three Cochrane reviews disagree on dose-response curve" }`.
6. `web/tests/e2e/sentence_inspector_contradiction.spec.ts` (new):
   - Test 1: sec_x:26 row shows `inspector-contradiction-26` badge with text containing "3 sources disagree".
   - Test 2: sec_x:5 (normal) shows NO contradiction badge.

## Risks for Codex Red-Team
1. **Schema field optional + default None:** existing fixtures untouched.
2. **Frontend type `?: ... | null`:** undefined coerces to null, no badge.
3. **Honest substrate:** today's generator does NOT populate contradiction; demo is the only render path. Future Issue (I-f8-002+) wires real detection.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~100 LOC. Under 200.
6. **Testid collision:** sentence rows already have a generic `kept-sentence` testid. The contradiction badge gets a uniquely-indexed testid `inspector-contradiction-{section_id}-{idx}` or `inspector-contradiction-{idx}` scoped to its parent row — choose: use the index inside the section (matches multispan testid convention).

## Acceptance criteria

1. `ContradictionSignal` Pydantic model added (count ≥2 ≤20, summary length-bounded).
2. `VerifiedSentence.contradiction: ContradictionSignal | None = None`.
3. 3 backend tests cover model + count-rejection.
4. Frontend type + optional `contradiction?: ContradictionSignal | null`.
5. Inline badge `inspector-contradiction-{idx}` renders when present; absent otherwise.
6. Demo + Playwright cover positive + negative cases.
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
