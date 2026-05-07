# Codex Brief Review — I-f8-005 (ITER 1 of 5)

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

- **Context:** I-f8-005 — guideline-vs-trial conflict is a distinct kind of disagreement: the trial result says X, but the practice guideline says Y (often because the guideline weighs other evidence too). Add `evidence_type: ContradictionEvidenceType` field on `ContradictionSide` so the pane can show "Source A (trial)" vs "Source B (guideline)" with explicit tags. Distinct conflict-type emerges naturally when sides differ in evidence_type.
- **Constraints:** Optional field with default "unspecified" to preserve back-compat.
- **Done-when:** acceptance criteria 1-7 below.

## Plan

### Backend
1. `src/polaris_graph/generator2/verified_report.py`:
   - Add `ContradictionEvidenceType` Literal: `trial | guideline | meta_analysis | observational | regulatory_label | expert_opinion | unspecified`.
   - Add `evidence_type: ContradictionEvidenceType = "unspecified"` field on `ContradictionSide`.
2. Tests: 2 new tests — default + all 7 values + bogus rejected.

### Frontend
3. `web/lib/api.ts`: add `ContradictionEvidenceType` type + optional `evidence_type?: ContradictionEvidenceType` on `ContradictionSide`.
4. `web/app/generation/components/contradiction_pane.tsx`: add `EVIDENCE_TYPE_LABEL` map; render evidence-type badge next to source_id on each side card. Skip rendering when type is "unspecified".
5. `web/app/sentence_hover_test/_demo.tsx`: APPEND sec_x:29 with sides where side 0 is `evidence_type="trial"` and side 1 is `evidence_type="guideline"`.
6. `web/tests/e2e/sentence_inspector_contradiction.spec.ts`: add 1 test — sec_x:29 pane shows trial/guideline tags.

## Risks for Codex Red-Team
1. **Optional + defaulted "unspecified":** existing fixtures unaffected. Pane skips badge for unspecified.
2. **Honest substrate:** generator does NOT yet populate evidence_type; demo only.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~80 LOC. Under 200.

## Acceptance criteria

1. `ContradictionEvidenceType` Literal with 7 values.
2. `evidence_type: ... = "unspecified"` field on ContradictionSide.
3. 2 backend tests.
4. Frontend renders evidence-type badge per side (skip "unspecified").
5. Demo + Playwright cover trial-vs-guideline case.
6. CHARTER §1 LOC cap respected (≤200 net).
7. Honest substrate framing in this brief.

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
