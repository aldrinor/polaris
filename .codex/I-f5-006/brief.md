# Codex Brief Review — I-f5-006 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix (frontend type):** make `is_synthesis_claim` OPTIONAL on `ReportVerifiedSentence` (`is_synthesis_claim?: boolean`). Badge renders only when truthy. Existing sec_x:0..14 demo literals stay valid without modification. Defensive default = "no badge."
- **P2 fix (schema invariant):** add validator: when `is_synthesis_claim=False` (or default) AND `verifier_pass=True` AND `provenance_tokens=[]`, raise — kept sentences must have either ≥1 provenance token OR `is_synthesis_claim=True`. Closes the schema gap that today's strict_verify catches at its own path but raw schema admitted.
- Validator additions to test_verified_report.py: 1 more test case for the `verifier_pass=True + provenance_tokens=[] + is_synthesis_claim=False` rejection.



```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review (separate Codex call) = code-matches-plan. Do NOT mark criteria as "FAIL: not implemented".

## Pre-flight

- **Context:** I-f5-006 — Inspector synthesis-claim badge. A "synthesis claim" is a kept sentence with NO direct provenance span (e.g., a discussion sentence summarizing across sources without quoting one). Today's strict_verify drops tokenless sentences with `drop_reason="no_provenance_token"`. This Issue introduces an opt-in synthesis category: when the generator marks a sentence `is_synthesis_claim=True`, strict_verify allows tokenless + kept; the Inspector renders a `synthesis-claim` badge.
- **Constraints:** No real LLM judge wired here. Synthesis-claim is a generator-supplied flag (today's fixed populator: False everywhere); future Issue may wire this into the prompt template to label synthesis sentences.
- **Done-when:** acceptance criteria 1-9 below.

**Independence directive:** prior round changelog markers are untrustworthy.

## Plan

### Backend (`src/polaris_graph/generator2/verified_report.py`)
1. Add `is_synthesis_claim: bool = False` to `VerifiedSentence` (default False for back-compat; existing fixtures unaffected).
2. Relax `_drop_reason_consistency` to ALSO allow: when `is_synthesis_claim=True`, `verifier_pass=True` is OK with `provenance_tokens=[]` and `drop_reason=None`. Validator additions:
   - If `is_synthesis_claim=True` AND `verifier_pass=False`: forbidden (synthesis claims either ship or are dropped before reaching this record).
   - If `is_synthesis_claim=True` AND `provenance_tokens` is non-empty: forbidden (synthesis claims have no provenance — that's the definition).
   - If `is_synthesis_claim=False` AND `verifier_pass=True` AND `provenance_tokens=[]`: forbidden (closes schema gap — kept sentences must have ≥1 provenance token OR be flagged as synthesis-claim).
3. Tests in `test_verified_report.py`: 4 new tests covering: allowed empty-tokens-with-synthesis-claim, forbidden synthesis-claim-with-tokens, forbidden synthesis-claim-with-pass-false, forbidden non-synthesis-pass-true-empty-tokens.

### Backend (`src/polaris_graph/generator2/strict_verify.py`)
4. `verify_sentence` currently returns `(False, "no_provenance_token")` when sentence has no tokens. Add an optional `is_synthesis_claim: bool = False` param: when True AND no tokens, return `(True, None)` without running token checks.
5. `verify_sentence_to_record` accepts the same param; when True AND no tokens, constructs `VerifiedSentence(verifier_pass=True, drop_reason=None, evaluator_agrees=True, is_synthesis_claim=True, provenance_tokens=[])`.
6. Tests in `test_strict_verify.py`: 2 new tests covering the synthesis-claim path.

### Frontend
7. `web/lib/api.ts`: add `is_synthesis_claim?: boolean` (OPTIONAL) to `ReportVerifiedSentence` interface. Defensive default behavior: undefined/false → no badge.
8. `web/app/generation/components/sentence_inspector.tsx`: when `sentence.is_synthesis_claim === true`, render a `synthesis-claim` badge with testid `inspector-synthesis-claim`. Render alongside drop_reason and AgreementBadge in the inspector header.
9. `web/app/sentence_hover_test/_demo.tsx`: APPEND sec_x:15 — a synthesis-claim sentence (`is_synthesis_claim: true`, `provenance_tokens: []`, `verifier_pass: true`, `drop_reason: null`).
10. `web/tests/e2e/sentence_inspector_synthesis.spec.ts` (new): click sec_x:15 → assert `inspector-synthesis-claim` visible.

## Risks for Codex Red-Team
1. **Schema validator interaction:** new validator must coexist with `_drop_reason_consistency` and `_evaluator_agreement_consistency`. All three live on VerifiedSentence and run in `mode="after"`. No conflicts because synthesis-claim path requires verifier_pass=True (which already requires drop_reason=None; consistent).
2. **Existing fixtures:** `is_synthesis_claim` defaults to False — no fixture changes required.
3. **Frontend type:** if a generation response from older backend lacks `is_synthesis_claim`, TypeScript treats it as `undefined`, which is falsy — badge does NOT render. Defensive default behavior is "no badge."
4. **§9.4 N/A frontend.**
5. **CHARTER §1 LOC cap:** estimated ~80 LOC net (backend +30, frontend +30, tests +20). Under 200.

## Acceptance criteria

1. `VerifiedSentence.is_synthesis_claim: bool = False` added to schema.
2. Validator forbids `is_synthesis_claim=True + verifier_pass=False`.
3. Validator forbids `is_synthesis_claim=True + provenance_tokens not empty`.
3a. Validator forbids `is_synthesis_claim=False + verifier_pass=True + provenance_tokens=[]` (closes schema gap).
4. `verify_sentence(..., is_synthesis_claim=True)` returns (True, None) for empty-tokens sentence.
5. `verify_sentence_to_record(..., is_synthesis_claim=True)` constructs valid VerifiedSentence.
6. Frontend `ReportVerifiedSentence` type includes `is_synthesis_claim?: boolean` (OPTIONAL; undefined/false → no badge; existing literals stay valid).
7. Inspector renders `inspector-synthesis-claim` badge when flag is True.
8. Demo fixture includes sec_x:15 synthesis-claim sentence.
9. Playwright covers the badge.

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
