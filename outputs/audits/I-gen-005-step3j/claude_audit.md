# I-gen-005 Step 3j — Claude architect audit

## Diff scope

`src/polaris_graph/generator/atom_refusal_validator.py`:
- Adds `_TRIAL_DESIGN_FRAME_RE` (methodology marker pattern)
- Adds `_ENDPOINT_NAMES_ALT` (mirrored from `_ENDPOINT_VOCAB_RE` per Codex review)
- Adds `_TIMEPOINT_ALT` + `_TIMEPOINT_PREP_ALT` (broad time-clause coverage)
- Adds `_ENDPOINT_RESULT_ATTRIBUTION_RE` (6-branch independent trigger: a-f)
- Expands `_OUTCOME_VERB_WITH_NUMBER_RE` with active outcome verbs + article carve-out
- Wires both into `requires_atom_citation`:
  - result-attribution check fires FIRST (independent trigger; cannot be masked by trial-design exemption)
  - existing narrative-category exemption preserved
  - NEW trial-design exemption (allows pure methodology framing without atom citation)
  - existing Trigger A / qual-comparative / Trigger B preserved

`tests/polaris_graph/test_atom_refusal_validator.py`: 31 new test_step3j_* tests
spanning the design APPROVE + 4 iters of diff-review P1 fixes.

## Codex iteration trajectory

- Design review: iter 1 → iter 4 APPROVE_DESIGN (3 iters of P1 fixes on regex completeness)
- Diff review: iter 1 → iter 5 (cap-hit). Iter 5 P1 fixed in iter-5 patch + force-APPROVE marker per §8.3.1.

## Correctness rationale

1. **Trial-design exemption can only ALLOW when result-attribution is ABSENT.** Branches a-f of `_ENDPOINT_RESULT_ATTRIBUTION_RE` fire as independent trigger BEFORE the trial-design exemption check, so any sentence asserting an outcome value (copular, value-at-timepoint, reverse-order, passive/incidence, verb-endpoint-of-NUMBER) refuses regardless of methodology framing.

2. **Step 3b iter-3 safety floor preserved.** Codex verified the historical repro "Patients with baseline HbA1c of 8.6% had HbA1c reductions of 2.3 percentage points" still refuses (outcome verb + number guard fires).

3. **Decimal handling.** All 4 numeric branches use `\d+(?:\.\d+)?` so the `[^.]` advance in branch (d) doesn't snag on the decimal in `-2.30`.

4. **Endpoint vocab parity.** `_ENDPOINT_NAMES_ALT` mirrors `_ENDPOINT_VOCAB_RE` per Codex iter-2 design + iter-1/2 diff fixes (added pancreatitis, hazard ratio, injection-site reactions, noninferiority, superiority, urinary albumin, hypoglycaemic events, etc.).

5. **Timepoint phrasing.** `_TIMEPOINT_PREP_ALT` covers at/after/by/at-the-end-of/over/through(out)/during/within/in with optional article. `_TIMEPOINT_ALT` covers `40 weeks`, `week 40`, and `40-week` hyphenated.

6. **Article/modifier carve-out.** Branch (f) and `_OUTCOME_VERB_WITH_NUMBER_RE` permit article/modifier (a/an/the/mean/median/baseline/average/change in) between verb and endpoint, up to 3 modifiers ("led to a change in HbA1c of -2.30").

## §-1.1 claim-by-claim audit table (excerpt)

| Sentence | Verdict | Trigger |
|---|---|---|
| s009 efficacy repro (methodology) | ALLOW | exemption |
| "primary endpoint of change in HbA1c was -2.30" | REFUSE | (a) |
| "mean HbA1c at 40 weeks was 6.2%" | REFUSE | (b) |
| "HbA1c at week 40 was 6.2%" | REFUSE | (b) |
| "change from baseline was -2.30 at 40 weeks" | REFUSE | (d) |
| "nausea was reported in 22%" | REFUSE | (e) |
| "86% achieved HbA1c reduction" | REFUSE | (e) |
| "tirzepatide achieved HbA1c of 6.2% at 40 weeks" | REFUSE | (f) |
| "treatment led to a change in HbA1c of -2.30" | REFUSE | (f) |
| "produced -2.30 reduction" | REFUSE | outcome verb |
| Step 3b iter-3 historical repro | REFUSE | outcome verb (safety floor) |
| "phase 3 trial showed reduced more than" | REFUSE | qual-comparative |
| "(mean baseline HbA1c 8.28%, mean weight 93.7 kg)" in design-frame sentence | ALLOW | exemption (no result-attribution) |

## Test result

`tests/polaris_graph/test_atom_refusal_validator.py` + `test_provenance_generator.py` + `test_claim_atom_extractor.py`: **149/149 PASS**

## Risks / known limitations

- Step 3j touches refusal-mode logic. Real V4 Pro smoke verification (Step 4 of operator's plan) will confirm calibration. Without that, the impact on refusal_rate is theoretical.
- The result-attribution regex is complex (6 branches). Future maintenance requires re-running this test suite + adding new test cases when V4 Pro emits novel phrasings.
- No follow-up Issue required after the iter-5 fix.

## Verdict

Step 3j is ready to merge. Per the operator's plan, next steps are Step 3k (atom_extractor safety vocab expansion) → re-run smoke → submit new gaps.json to Codex for §-1.1 audit.
