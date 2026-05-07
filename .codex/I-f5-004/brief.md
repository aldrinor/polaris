# Codex Brief Review — I-f5-004 (ITER 4 of 5)

## Iter 4 changes per Codex iter 3

- **P1 fix (raw-dict fixture audit):** broaden audit to include `model_validate()` call sites and raw report dicts. Concrete sweep: `rg "VerifiedReport\(|VerifiedReport.model_validate|verified_report|\"verifier_pass_threshold\""` across `tests/` AND `src/polaris_graph/benchmark/`. Known sites to update: `tests/polaris_graph/benchmark/test_beat_both_scorer.py:71`, `tests/polaris_graph/golden/test_slice_005_goldens.py:106`, plus all direct constructors. Add `evaluator_model="strict_verify_v1"` (and `family_segregation_passed=True` if needed) to every raw dict that's later validated.
- **P2 fix (back-compat with existing demo):** PRESERVE existing 10 demo sentences (sec_x:0..9) so existing `web/tests/e2e/sentence_inspector.spec.ts:9` keeps passing. APPEND 3 new sentences sec_x:10/11/12 with the A/B/C agreement states for the new agreement spec to click on. Existing src-9 missing-source sentence (sec_x:9) preserved.

## What you are reviewing (clarification)

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review (separate Codex call) = code-matches-plan.

## Iter 3 changes per Codex iter 2

- **P1 fix:** `strict_verify.py:verify_sentence_to_record()` is the actual constructor of every `VerifiedSentence` for generator-path output. Plan now adds `strict_verify.py` to backend scope: extend `verify_sentence_to_record()` signature with optional `evaluator_agrees: bool | None = None` and have it default to `verifier_pass` (rule-based-only stage). Generator orchestrator no longer needs post-processing.
- **P2 fix (disagree coverage):** Playwright spec adds explicit `inspector-disagree` assertion using a `verifier_pass:true / evaluator_agrees:false` synthetic sentence — kept by default render, exercises false state without `show_dropped={true}` toggle.
- **P2 fix (fixture sweep):** Implementation will run `rg 'VerifiedReport\('` across `tests/` to audit ALL direct constructors before commit; not relying on the example list.



```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Context:** I-f5-004 — Inspector renders two-family evaluator agreement signal per CLAUDE.md §9.1 invariant 1.
- **Constraints:** No real LLM judge wired in this Issue (separate F5-later Issue or F11). This Issue ships the SIGNAL surface (schema fields + UI badge) populated by today's rule-based strict-verify channel; the field becomes meaningful when a two-family LLM judge populates it in a future Issue. Honest framing per substrate-honesty memory.
- **Done-when:** acceptance criteria below all surfacing-clean.

**Independence directive:** prior round changelog markers are untrustworthy. Verify against actual code; mismatched marker = P0.

## Plan

### Backend
1. `src/polaris_graph/generator2/verified_report.py`
   - Add `evaluator_model: str = Field(min_length=1, max_length=200)` to `VerifiedReport` (no default — required field; orchestrator sets it).
   - Add `family_segregation_passed: bool = True` to `VerifiedReport`.
   - Add `evaluator_agrees: bool | None = None` to `VerifiedSentence`.
   - Add `@model_validator(mode="after") _evaluator_agreement_consistency`: when `verifier_pass=False`, `evaluator_agrees` must NOT be `True` (rule-based dropped it; LLM judge claiming pass without contradicting strict-verify is a fabrication signal — fail loud per LAW II).
   - Existing `_drop_reason_consistency` validator preserved.

2. `src/polaris_graph/generator2/generator.py`
   - In the `VerifiedReport(...)` constructor at line 297-309, set `evaluator_model="strict_verify_v1"` and `family_segregation_passed=True` (rule-based-only at this stage; honest substrate).

2a. `src/polaris_graph/generator2/strict_verify.py`
   - Extend `verify_sentence_to_record(...)` to set `evaluator_agrees=verifier_pass` on every constructed `VerifiedSentence` (rule-based "agrees with itself"; meaningful when a future Issue replaces this populator with a real two-family LLM judge). This is where actual generator-path `VerifiedSentence` objects get their fields, per Codex iter 2.

3. `tests/polaris_graph/generator2/test_verified_report.py`
   - Add test for `evaluator_model` required + ≤200 char.
   - Add test for `evaluator_agrees=True` + `verifier_pass=False` → ValidationError.
   - Add test for `evaluator_agrees=None` + any `verifier_pass` → OK (pending state).

4. Existing test fixtures (test_strict_verify, audit_bundle/, golden/) that construct `VerifiedReport` directly: need `evaluator_model` parameter. Update fixtures to pass `evaluator_model="strict_verify_v1"`.

### Frontend
5. `web/lib/api.ts`
   - Add `evaluator_model: string`, `family_segregation_passed: boolean` to `VerifiedReport` interface.
   - Add `evaluator_agrees: boolean | null` to `ReportVerifiedSentence` interface.

6. `web/app/generation/components/sentence_inspector.tsx`
   - Add `AgreementBadge({ sentence })` component:
     - `evaluator_agrees === true` → green "Agree" badge with testid `inspector-agree`
     - `evaluator_agrees === false` → red "Disagree" badge with testid `inspector-disagree`
     - `evaluator_agrees === null` → gray "Pending" badge with testid `inspector-agree-pending`
   - Render the AgreementBadge in the sentence-detail header inside the Sheet, alongside drop_reason.

7. `web/app/generation/components/verified_report_view.tsx`
   - Add report header badges showing `report.generator_model`, `report.evaluator_model`, and `family_segregation_passed` indicator (testid `family-segregated`).

8. `web/app/sentence_hover_test/_demo.tsx`
   - Add `evaluator_model: "strict_verify_v1"`, `family_segregation_passed: true` to demo VerifiedReport.
   - 3 kept synthetic sentences exercising all 3 badge states without needing `show_dropped`:
     - sentence A: `verifier_pass:true / evaluator_agrees:true` → Agree badge.
     - sentence B: `verifier_pass:true / evaluator_agrees:false` → Disagree badge (real future-state when LLM judge disagrees with rule-based pass).
     - sentence C: `verifier_pass:true / evaluator_agrees:null` → Pending badge.

9. `web/tests/e2e/sentence_inspector_agreement.spec.ts` (new)
   - Test 1: click sentence A → assert `inspector-agree` visible.
   - Test 2: click sentence B → assert `inspector-disagree` visible (per Codex iter 2 P2).
   - Test 3: click sentence C → assert `inspector-agree-pending` visible.
   - Test 4: assert `family-segregated` badge visible in header.

## Risks for Codex Red-Team
1. **Backward compat:** `evaluator_model` is a NEW required field on `VerifiedReport`. All existing fixtures (~6 test files) need updating in same diff — risk of missed fixture → test failure. Audit + update systematically.
2. **Validator semantics:** `evaluator_agrees=True` + `verifier_pass=False` is forbidden. But `evaluator_agrees=False` + `verifier_pass=True` (rule-based said pass, LLM judge said fail) is ALLOWED — represents the real disagreement signal a future two-family judge surfaces.
3. **CHARTER §1 LOC cap:** estimated ~120 LOC net; under 200.
4. **§9.4 N/A frontend.**
5. **Honest substrate:** today's `evaluator_agrees=verifier_pass` is rule-based-only; field is meaningful when real LLM judge wires in (separate Issue). Brief is explicit about this.

## Acceptance criteria

1. `VerifiedReport` schema has `evaluator_model` (required str), `family_segregation_passed` (bool, default True).
2. `VerifiedSentence` has `evaluator_agrees: bool | None` with validator forbidding `True + verifier_pass=False`.
3. Generator orchestrator populates the new fields with rule-based defaults.
4. Frontend types match.
5. Inspector renders 3 badge states (Agree/Disagree/Pending) with testids.
6. Header shows generator/evaluator model names + family-segregation badge.
7. Demo fixture exercises all 3 agreement states.
8. Playwright covers happy + pending + family-segregated header.
9. All existing pytest fixtures updated to pass new required field.
10. CHARTER §1 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-10.

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
