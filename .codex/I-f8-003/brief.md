# Codex Brief Review — I-f8-003 (ITER 1 of 5)

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

## Pre-thrusters

- **Context:** I-f8-003 — adversarial: SAME source asserts "X is safe" in one paragraph and "X is dangerous" in another. The contradiction signal must flag this even though there's only ONE source. Today's `ContradictionSignal.disagreeing_source_count: int (ge=2)` rejects single-source-self-contradiction; we need to distinguish:
  - **Multi-source contradiction (I-f8-001/002):** ≥2 distinct sources disagree.
  - **Self-contradiction (I-f8-003):** 1 source contradicts itself across spans/paragraphs.
- **Constraints:** Add `kind: ContradictionKind` discriminator. When `kind="self_contradiction"`, allow disagreeing_source_count=1 BUT sides MUST have ≥2 entries from the same source_id.
- **Done-when:** acceptance criteria 1-7 below.

## Plan

### Backend
1. `src/polaris_graph/generator2/verified_report.py`:
   - Add `ContradictionKind` Literal: `"multi_source"` (default) | `"self_contradiction"`.
   - Add `kind: ContradictionKind = "multi_source"` field to `ContradictionSignal`.
   - Update `disagreeing_source_count` constraint: `ge=1` (was `ge=2`), but reinforce via validator:
     - `kind="multi_source"` → `disagreeing_source_count >= 2`.
     - `kind="self_contradiction"` → `disagreeing_source_count == 1` AND sides MUST have ≥2 entries with the same source_id.
2. Tests in `test_verified_report.py`: 4 new tests:
   - Default kind="multi_source" preserved.
   - Self-contradiction with count=1 + 2 same-source sides accepted.
   - Self-contradiction with count!=1 rejected.
   - Self-contradiction with sides referencing different source_ids rejected.

### Frontend
3. `web/lib/api.ts`: add `ContradictionKind` type + `kind?: ContradictionKind` (optional with default "multi_source") on `ContradictionSignal`.
4. `web/app/generation/components/verified_report_view.tsx`: badge text differs by kind:
   - "multi_source": ⚠ {N} sources disagree (existing).
   - "self_contradiction": ⚠ Source self-contradicts ({N} spans).
   Add `kind` reading defensive default to "multi_source".
5. `web/app/generation/components/contradiction_pane.tsx`: pane title differs by kind ("Self-contradiction:" vs "Contradiction:").
6. `web/app/sentence_hover_test/_demo.tsx`: APPEND sec_x:27 with `kind: "self_contradiction"`, count=1, 2 sides both src-0 with opposing claim_excerpts.
7. `web/tests/e2e/sentence_inspector_contradiction.spec.ts`: add 1 test — sec_x:27 row shows "Source self-contradicts" badge text; click → pane title contains "Self-contradiction".

## Risks for Codex Red-Team
1. **Schema validator change:** `disagreeing_source_count` lower bound relaxed from 2 to 1. Now `kind` discriminator enforces the correct bound per kind.
2. **Existing fixtures:** I-f8-001 + I-f8-002 demos use multi_source with count≥2 — unaffected.
3. **§9.4 N/A frontend.**
4. **CHARTER §1 LOC cap:** estimated ~140 LOC. Under 200.

## Acceptance criteria

1. `ContradictionKind` Literal added with 2 values.
2. `kind: ContradictionKind = "multi_source"` field added.
3. Validator: multi_source requires count≥2; self_contradiction requires count==1 AND sides≥2 same source_id.
4. 4 backend tests cover default + self-contradiction valid + invalid count + invalid same-source.
5. Frontend badge text + pane title differ by kind.
6. Demo + Playwright cover self-contradiction case.
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
