# Codex iter 2 — atom_refusal_validator.py diff review

## §8.3.1 cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Iter 1 verdict (your call)

REQUEST_CHANGES, 1 P1 + 4 P2s + 1 P3:

| # | severity | iter-1 finding | iter-2 fix |
|---|---|---|---|
| 1 | P1 | qualitative comparative false negatives (3 repros) | expanded qual regex + safety endpoints + comparator-arm fallback |
| 2 | P2 | eligibility-range over-refused | `_ELIGIBILITY_RANGE_RE` override before Trigger A |
| 3 | P2 | SOFT substring match (12.30 matched 2.30) | numeric-token-boundary equality via `_NUMBER_RE` set semantics |
| 4 | P2 | refused records missing detected_values | populated detected_values in `_build_refusal_record` |
| 5 | P2 | other SOFT followups (endpoint/entity/timepoint mismatch + partial coverage) | deferred to follow-up Issue per your acceptance |
| 6 | P3 | empty test assertions | added explicit assert not requires |

## Live verification of all 3 iter-1 P1 repros

```python
requires_atom_citation("Adverse events were more common with tirzepatide than placebo.")
→ (True, 'trigger_qualitative_comparative')    ✓

requires_atom_citation("Nausea was higher with tirzepatide than placebo.")
→ (True, 'trigger_qualitative_comparative')    ✓ (nausea now in endpoint vocab + qual regex catches "higher with")

requires_atom_citation("Tirzepatide showed greater reduction than semaglutide.")
→ (True, 'trigger_qualitative_comparative')    ✓ (no endpoint vocab term but comparator-arm "than semaglutide" signal fires)
```

## Iter-2 implementation details

### Expanded `_QUAL_COMPARATIVE_RE`

Added:
- `more(?:\s+\w+){0,4}\s+than` — "more common with X than Y", "more events than"
- `fewer(?:\s+\w+){0,4}\s+than` — symmetric
- `more\s+(?:effective|common|frequent)` — bare patterns
- `less\s+(?:effective|common|frequent)` — symmetric

### New `_COMPARATIVE_ARM_RE`

```python
_COMPARATIVE_ARM_RE = re.compile(
    r"\b(?:than|versus|vs\.?|compared\s+(?:to|with))\s+"
    r"(?:placebo|control|standard\s+care|usual\s+care|\w{3,})\b",
    re.IGNORECASE,
)
```

In `requires_atom_citation`:
```python
if has_qual_comparative and (has_endpoint or has_comparator_arm):
    return True, "trigger_qualitative_comparative"
```

Catches "Tirzepatide showed greater reduction than semaglutide" — qual_comparative fires on "greater reduction than", comparator_arm fires on "than semaglutide", no endpoint vocab needed.

### Safety endpoint vocab additions

```
nausea | vomiting | diarrh(o)?ea | constipation | abdominal pain | injection-site reaction
```

### Eligibility-range override

```python
_ELIGIBILITY_RANGE_RE = re.compile(
    r"\b(?:inclusion\s+criter|exclusion\s+criter|eligibility|"
    r"eligible\s+patients|eligible\s+adults|"
    r"baseline\s+(?:hba1c|weight|bmi)|"
    r"required\s+(?:hba1c|weight))\b",
    re.IGNORECASE,
)
```

Override fires BEFORE Trigger A:
```python
if _ELIGIBILITY_RANGE_RE.search(s) and not has_qual_comparative:
    return False, None
```

"Eligible patients had inclusion criteria of HbA1c between 7.0 and 10.0" → False ✓
(But "Eligible patients showed greater reduction than..." would still require — qual_comparative override.)

### SOFT layer numeric-token-boundary match

```python
detected_values = _NUMBER_RE.findall(sentence)
detected_value_set = set(detected_values)
for aid in cited_atoms:
    atom = catalog[aid]
    atom_val_normalized = atom.value.replace("−", "-")
    atom_val_unsigned = atom_val_normalized.lstrip("-")
    sentence_unsigned = {v.lstrip("-") for v in detected_value_set}
    if atom_val_unsigned and atom_val_unsigned not in sentence_unsigned:
        soft_notes.append(f"atom={aid} value={atom.value!r} not in sentence numeric tokens")
```

"12.30" extracts as token "12.30". atom_003 value "2.30" (unsigned). "2.30" ∉ {"12.30"} → SOFT_MISMATCH ✓

### detected_values on refusal records

Added to `_build_refusal_record`:
```python
detected_values = _NUMBER_RE.findall(sentence)
return GapRecord(..., detected_values=detected_values, ...)
```

## Tests (36/36 PASS — 88/88 combined with atom_extractor)

6 NEW iter-2 regression tests for the exact iter-1 repros:
- `test_iter2_p1_qualitative_comparative_safety_requires_atom`
- `test_iter2_p1_qualitative_higher_with_drug_requires_atom`
- `test_iter2_p1_qualitative_greater_reduction_than_requires_atom`
- `test_iter2_p2_eligibility_range_allowed`
- `test_iter2_p2_soft_value_word_boundary_match`
- `test_iter2_p2_refused_record_includes_detected_values`

Also added missing asserts on the two P3-flagged tests.

## Deferred to P2 follow-up Issue (per your accept_remaining)

You explicitly said:
> "Endpoint/entity/timepoint/comparator mismatch and multi-number partial coverage remain P2 follow-ups."

I did NOT add those soft checks in iter-2. They'll be a post-cap follow-up Issue (filed after the I-gen-005 PR #905 merges).

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES

p1_qualitative_comparative_false_negatives_fixed: YES | NO | PARTIAL
  if_not_yes: |
    (specific failure mode + repro)

p2_eligibility_range_allowed: YES | NO | PARTIAL

p2_soft_value_token_boundary_correct: YES | NO

p2_refused_records_include_detected_values: YES | NO

p3_test_assertions_added: YES | NO

new_qual_regex_no_false_positives: YES | NO
  if_no: |
    (which benign sentence is now over-requiring atom)

comparator_arm_signal_robust: YES | NO
  edge_cases_remaining: |
    (e.g. "than usual" without drug, "compared to baseline")

eligibility_override_no_under_refusal: YES | NO
  if_no: |
    (case where eligibility frame mask outcome claim)

novel_p0: [...]
novel_p1: [...]
continuing_p0: [...]
continuing_p1: [...]
p2: [...]
p3: [...]

approval_to_proceed_to_step_3: YES | NO

convergence_call: continue | accept_remaining
```

EMIT YAML ONLY. Diff is at `.codex/I-gen-005-refusal/codex_diff_iter2.patch` (278 lines).
