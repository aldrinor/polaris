# Codex Brief Review — I-f9-002 (ITER 1 of 5)

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

- **Context:** I-f9-002 — clicking the I-f9-001 row badge opens a Sheet showing BOTH the generator's reading AND the evaluator's reading of the same evidence, with the cited sources from each side. Distinct from I-f8-002 ContradictionPane (which is multi-source disagreement). This pane is specifically generator-vs-evaluator (two-family disagreement on the SAME source(s)).
- **Constraints:** Add `EvaluatorDisagreement` schema to `ReportVerifiedSentence` to carry the evaluator's reading explicitly.
- **Done-when:** acceptance criteria 1-7 below.

## Plan

### Backend
1. `src/polaris_graph/generator2/verified_report.py`:
   - Add `EvaluatorDisagreement` BaseModel:
     - `generator_reading: str` (1..1000 chars) — what generator concluded.
     - `evaluator_reading: str` (1..1000 chars) — what evaluator concluded.
     - `cited_sources: list[str]` (min 1) — source_ids both reviewed.
     - `evaluator_model: str` (1..200 chars) — which model evaluated.
   - Add `evaluator_disagreement: EvaluatorDisagreement | None = None` field to `VerifiedSentence`.
   - Validator: when `evaluator_agrees=False`, `evaluator_disagreement` SHOULD be present (non-blocking warning via field doc, not enforced — keep validator scope tight).
2. Tests: 2 new tests — schema construction + cited_sources non-empty.

### Frontend
3. `web/lib/api.ts`: add `EvaluatorDisagreement` interface + `evaluator_disagreement?: EvaluatorDisagreement | null` on `ReportVerifiedSentence`.
4. `web/app/generation/components/evaluator_pane.tsx` (NEW): EvaluatorPane Sheet with:
   - Generator reading panel (data-testid=`evaluator-pane-generator-reading`).
   - Evaluator reading panel (data-testid=`evaluator-pane-evaluator-reading`).
   - Cited sources list (each: `evaluator-pane-source-{i}`).
   - Evaluator model badge (data-testid=`evaluator-pane-model`).
5. `web/app/generation/components/verified_report_view.tsx`: I-f9-001 row badge becomes a `<button>` with stopPropagation + Enter/Space handlers (mirror I-f8-002 pattern). On click, opens EvaluatorPane via root state.
6. `web/app/sentence_hover_test/_demo.tsx`: extend sec_x:11 with full `evaluator_disagreement` payload.
7. `web/tests/e2e/sentence_inspector_evaluator_flag.spec.ts`: extend with 1 click test → pane opens with both readings.

## Risks for Codex Red-Team
1. **Click propagation (Codex iter-1 P1 from I-f8-002):** badge becomes button; stopPropagation + onKeyDown for Enter/Space.
2. **Optional + null default:** existing fixtures unaffected.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~150 LOC. Under 200.

## Acceptance criteria

1. `EvaluatorDisagreement` Pydantic model added.
2. `evaluator_disagreement: ... | None = None` field on VerifiedSentence.
3. 2 backend tests.
4. EvaluatorPane Sheet with generator/evaluator readings + sources + model.
5. I-f9-001 badge becomes clickable button (with propagation guard) opening EvaluatorPane.
6. Demo + Playwright cover the click + pane content.
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
