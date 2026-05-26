# Codex iter 3 — atom_refusal_validator.py diff review

## §8.3.1 cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE'd per §8.3.1.
- If holding back a P1 — surface NOW; iter 6 doesn't exist.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Iter 2 verdict → addressed in iter 3

REQUEST_CHANGES with 1 novel P1 + 1 P2. Both fixed:

| # | severity | iter-2 finding | iter-3 fix |
|---|---|---|---|
| 1 | novel P1 | eligibility override masks outcome claims with baseline framing | tightened `_ELIGIBILITY_RANGE_RE` to specific criteria-frames only; added `_OUTCOME_VERB_WITH_NUMBER_RE` that prevents override when sentence has "reductions of N" / "decreased by N" etc. |
| 2 | P2 | comparator-arm `\w{3,}` matches benign prose like "than enough" | tightened `_COMPARATIVE_ARM_RE` to specific treatment-arm terms only: placebo/control/standard-care/drug-class/drug-names |

## Live verification on Codex's exact iter-2 repros

```
"Patients with baseline HbA1c of 8.6% had HbA1c reductions of 2.3 percentage points."
→ (True, 'trigger_A_number_plus_endpoint')    ✓ (was False, now correctly requires atom)

"This was more than enough evidence to proceed."
→ (False, None)    ✓ (was True, now correctly allowed as benign)

"More patients than expected completed follow-up."
→ (False, None)    ✓ (was True, now correctly allowed)

"Eligible patients had inclusion criteria of HbA1c between 7.0 and 10.0."
→ (False, None)    ✓ (regression: pure eligibility still allowed)

"Tirzepatide showed greater reduction than semaglutide."
→ (True, 'trigger_qualitative_comparative')    ✓ (regression: drug-arm comparative still required)
```

## Implementation

### `_OUTCOME_VERB_WITH_NUMBER_RE`

```python
_OUTCOME_VERB_WITH_NUMBER_RE = re.compile(
    r"\b(?:reduc(?:ed|tions?|ing)|"
    r"decreas(?:ed|es?|ing)|increas(?:ed|es?|ing)|"
    r"chang(?:ed|es?)|improv(?:ed|ements?|ing)|"
    r"lower(?:ed|ing)|rais(?:ed|ing)|"
    r"fell|rose|dropped)\s+"
    r"(?:by|of|from|to)?\s*[-−]?\d",
    re.IGNORECASE,
)
```

### Eligibility override (now triple-guarded)

```python
if (
    _ELIGIBILITY_RANGE_RE.search(s)
    and not has_qual_comparative
    and not _OUTCOME_VERB_WITH_NUMBER_RE.search(s)
):
    return False, None
```

### Tightened `_COMPARATIVE_ARM_RE`

```python
_COMPARATIVE_ARM_RE = re.compile(
    r"\b(?:than|versus|vs\.?|compared\s+(?:to|with))\s+"
    r"(?:"
    r"placebo|control(?:s|\s+arm)?|standard\s+care|usual\s+care|"
    r"active\s+comparator|background\s+therapy|sham|"
    r"glp[-\s]?1|sglt2|dpp[-\s]?4|insulin|metformin|sulfonylurea|"
    r"semaglutide|tirzepatide|dulaglutide|liraglutide|"
    r"empagliflozin|dapagliflozin|canagliflozin|ertugliflozin|"
    r"sitagliptin|linagliptin|saxagliptin|alogliptin|"
    r"warfarin|apixaban|rivaroxaban|dabigatran|edoxaban|"
    r"rosuvastatin|atorvastatin|simvastatin"
    r")\b",
    re.IGNORECASE,
)
```

## Tests (40/40 PASS — 92/92 combined)

4 NEW iter-3 regression tests:
- `test_iter3_p1_eligibility_override_does_not_mask_outcome_claim`
- `test_iter3_p2_comparator_arm_does_not_match_generic_words`
- `test_iter3_eligibility_pure_still_allowed` (regression check)
- `test_iter3_qualitative_drug_arm_still_requires_atom` (regression check)

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES

p1_eligibility_no_longer_masks_outcomes: YES | NO
  if_no: |
    (specific failure case)

p2_comparator_arm_no_false_positives: YES | NO
  if_no: |
    (specific benign sentence still over-requiring)

regression_pure_eligibility_still_allowed: YES | NO

regression_drug_arm_comparative_still_required: YES | NO

novel_p0: [...]
novel_p1: [...]
continuing_p0: [...]
continuing_p1: [...]
p2: [...]
p3: [...]

approval_to_proceed_to_step_3: YES | NO
  if_no: |
    (specific blocker before V4 Pro `_call_section` integration)

convergence_call: continue | accept_remaining
```

EMIT YAML ONLY. Diff at `.codex/I-gen-005-refusal/codex_diff_iter3.patch`.
