# Codex Brief Review — I-f8-002 (ITER 1 of 5)

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

- **Context:** I-f8-002 — clicking the contradiction badge opens a Sheet showing ALL sides of the disagreement. Each side carries: source_id, source_tier, sample_size (from the underlying study, optional), hedge_language string (e.g. "high confidence", "moderate confidence"), and PT08 flag (Primary Trial 0/8 dimensional flag — used by V32 contradiction-aware hedging per heritage).
- **Constraints:** Schema breaking-extension on `ContradictionSignal` — adds `sides: list[ContradictionSide]`. Existing demo sec_x:26 needs a `sides` array.
- **Done-when:** acceptance criteria 1-7 below.

## Plan

### Backend
1. `src/polaris_graph/generator2/verified_report.py`:
   - Add `ContradictionSide` BaseModel:
     - `source_id: str (min_length=1, max_length=200)`
     - `source_tier: Literal["T1", "T2", "T3"]`
     - `sample_size: int | None = None` (≥0 when present)
     - `hedge_language: str (min_length=1, max_length=200)` (e.g. "high confidence", "moderate confidence", "low confidence")
     - `pt08_flag: str | None = None` (PT08 dimensional flag string when applicable; max 50 chars)
     - `claim_excerpt: str (min_length=1, max_length=500)` — the actual disagreeing claim wording from this side
   - Add `sides: list[ContradictionSide] = []` field to `ContradictionSignal`.
   - Add validator: `len(sides) == disagreeing_source_count` (when sides non-empty).
2. Tests in `test_verified_report.py`: 3 new tests:
   - ContradictionSide minimal construction.
   - ContradictionSignal with 3 sides matching count=3.
   - count/sides length mismatch rejected.
   - Existing test `test_verified_sentence_with_contradiction_signal` must be updated to include sides.

### Frontend
3. `web/lib/api.ts`: add `ContradictionSide` interface; extend `ContradictionSignal` with `sides: ContradictionSide[]`.
4. `web/app/generation/components/contradiction_pane.tsx` (NEW):
   - `ContradictionPane({ open, signal, onOpenChange })`
   - Renders Sheet (right side, 40% width) with title "Contradiction: N sources disagree".
   - Lists each side as a card with:
     - Source ID + tier badge.
     - Sample size (if present).
     - Hedge language badge.
     - PT08 flag badge (if present).
     - Claim excerpt blockquote.
   - Each side has testid `contradiction-side-{idx}` with sub-testids for source/tier/hedge/sample/pt08/claim.
5. `web/app/generation/components/verified_report_view.tsx`: contradiction badge now becomes clickable; opens the ContradictionPane. Local state `selected_contradiction: { signal, sentence_id } | null`.
6. `web/app/sentence_hover_test/_demo.tsx`: update sec_x:26's contradiction to include 3 `sides` (T1 + T2 + T1 with different hedges/sample sizes/excerpts).
7. `web/tests/e2e/sentence_inspector_contradiction.spec.ts`: extend with 1 new test — click badge → pane visible + 3 `contradiction-side-*` cards.

## Risks for Codex Red-Team
1. **Schema breaking change on existing test:** I-f8-001's `test_verified_sentence_with_contradiction_signal` must add sides matching count.
2. **Sides validator subtlety:** allow `sides: []` (back-compat for I-f8-001-only callers) OR require non-empty AND len-matching when present. Choose: ALLOW empty (back-compat) but REJECT non-empty mismatch (per criteria 2).
3. **Honest substrate:** generator does NOT populate sides; demo path only. Future Issue (F8-003+) wires real conflict-detector output.
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~180 LOC. Right at the 200 cap; LOC exemption candidate if needed.

## Acceptance criteria

1. `ContradictionSide` Pydantic model added (6 fields with constraints).
2. `ContradictionSignal.sides: list[ContradictionSide] = []` added.
3. Validator: `sides` non-empty → `len(sides) == disagreeing_source_count`.
4. 3 new backend tests + I-f8-001 test updated.
5. Frontend `ContradictionPane` Sheet renders all sides with sub-testids.
6. Demo + Playwright extended; click badge opens pane with 3 sides.
7. CHARTER §1 LOC cap (≤200 net OR exemption with justification).

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
