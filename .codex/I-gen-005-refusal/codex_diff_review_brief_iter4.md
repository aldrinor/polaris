# Codex iter 4 — atom_refusal_validator.py diff review

## §8.3.1 cap (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE per §8.3.1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**Iter 4 of 5. One iteration remains.**

## Iter 3 verdict → iter 4 response

REQUEST_CHANGES with continuing P1 (eligibility override masks outcomes
with non-narrow verb forms like "had HbA1c of N") + novel P1 (comparator
drug list missing exenatide).

### Iter-4 design decision: drop eligibility override entirely

Two iterations of regex tightening (iter-2, iter-3) couldn't reliably
distinguish:
- "Patients meeting inclusion criteria had HbA1c of 6.8%" (outcome — must require)
- "Eligible adults had baseline HbA1c between 7.0 and 10.0" (eligibility — could allow)

The right answer is structural: drop the override. Per CLAUDE.md §-1.1
clinical-safety principle:
- false negative (over-refuse benign eligibility) → recoverable
  (V4 Pro emits refusal block; awkward but safe)
- false positive (mask real outcome) → lethal

`requires_atom_citation` no longer has any eligibility override; any
quantitative claim requires atom citation. The eligibility regex
constants are kept in the file with a docstring noting the iter-4
decision; not called.

### Comparator drug list fix

`_build_comparative_arm_re()` now imports `_DRUG_RE.pattern` from
atom_extractor and embeds the full drug-name alternation. Any drug
name the extractor recognizes (including exenatide which wasn't in
my iter-3 hardcoded list) is auto-recognized as a comparator arm.

## Live verification on iter-3 repros

```
"Patients meeting inclusion criteria had HbA1c of 6.8% at 40 weeks."
→ (True, 'trigger_A_number_plus_endpoint')    ✓ now requires (was False)

"Tirzepatide showed greater reduction than exenatide."
→ (True, 'trigger_qualitative_comparative')    ✓ now requires (was False)

"This was more than enough evidence to proceed."
→ (False, None)    ✓ still benign (regression check)

"More patients than expected completed follow-up."
→ (False, None)    ✓ still benign (regression check)
```

## Tests (42/42 PASS — 94/94 combined)

Three prior eligibility tests updated to reflect new "require atom"
behavior. Two new iter-4 regression tests:
- `test_iter4_codex_repro_outcome_with_criteria_still_required`
- `test_iter4_comparator_arm_uses_full_drug_regex`

## Trade-off acknowledgment

Eligibility-frame sentences with endpoint+number now go through Trigger
A and require atom citation. If V4 Pro can't find a supporting atom
(because the sentence is actually eligibility framing not an outcome
claim), it emits a refusal block: "Insufficient verified atom-level
evidence about HbA1c..." This reads awkwardly for a benign eligibility
sentence but is the SAFE default.

To mitigate the awkwardness, V4 Pro's system prompt (Step 3 — not in
this diff) will be instructed to recognize eligibility-frame sentences
and write them as pure design prose without endpoint+number framing
where possible.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES

p1_outcome_with_criteria_now_requires_atom: YES | NO
p1_comparator_drug_list_complete: YES | NO

trade_off_acceptable: YES | NO
  if_no: |
    (concern about over-refusal cost)

novel_p0: [...]
novel_p1: [...]
continuing_p0: [...]
continuing_p1: [...]
p2: [...]
p3: [...]

approval_to_proceed_to_step_3: YES | NO

iter4_cap_consideration: APPROVE_THIS | CONTINUE_TO_ITER_5
  reasoning: |

convergence_call: continue | accept_remaining
```

EMIT YAML ONLY. Diff at `.codex/I-gen-005-refusal/codex_diff_iter4.patch`.
