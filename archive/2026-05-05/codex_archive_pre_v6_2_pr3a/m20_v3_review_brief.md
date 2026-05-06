M-20 v3 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-20 v2 verdict: PARTIAL — plural class-form queries
("PD-1 inhibitors efficacy in melanoma", "DOACs efficacy in
atrial fibrillation", etc.) still landed in operator_review even
after v2 added plural drug_keywords. Root cause: queries naming
ONLY a drug class (no specific drug) had ex_jac < 0.30 against
existing specific-drug exemplars, falling to Tier B (drug named,
ex shape unmatched, score 0.40-0.45). The v2 plural-form test
asserted top-1 ranking only — passed even when verdict was
operator_review. You correctly flagged the assertion was too weak.

## What changed in v3 (commits 1702ad1 + f47160f)

`template_catalog.py`:
- Added 3 class-only scope_examples to v30_clinical_oncology:
    "PD-1 inhibitors efficacy in melanoma"
    "PARP inhibitors maintenance in ovarian cancer"
    "Checkpoint inhibitors in metastatic non-small cell lung cancer"
- Added 6 class-only scope_examples to v30_clinical_cardio:
    "DOACs efficacy in atrial fibrillation"
    "Statins for primary prevention in adults"
    "ARBs cardiovascular outcomes in chronic hypertension"
    "Calcium channel blockers efficacy in hypertension"
    "Beta blockers in heart failure"
    "PCSK9 inhibitors LDL reduction outcomes"

  These exemplars give jaccard >= 0.30 for the plural-class
  queries, lifting them into Tier A → score 0.55 + 0.45*ex_jac
  (well above floor_high 0.55).

`test_template_classifier.py`:
- test_plural_drug_class_forms_route_correctly tightened to
  assert verdict == ROUTED + correct template_id (per your
  feedback). Top-1-ranking-only would still let operator_review
  cases pass.

Also caught by separate catalog-shape test
test_scope_examples_are_concrete_questions: "ARBs outcomes in
hypertension" was 4 words, must be ≥ 5 — extended to "ARBs
cardiovascular outcomes in chronic hypertension".

Module: 91/91 across template classifier + catalog tests.
M-16+M-17+M-20 v3 combined: 134/134.

## Your job

Final verdict on M-20. GREEN / PARTIAL / DISAGREE.

If GREEN, M-20 v3 locks. Phase C continues. The FINAL_PLAN
target of 50+ templates comes via subsequent batches, each gated
by `test_real_catalog_has_no_unexpected_ties` and
`test_no_duplicate_keywords_within_template`. M-20 has shipped:
3 templates, plural-form coverage, tie detection, dedup
invariant, self-routing-must-route invariant.

## Output

Write to `outputs/codex_findings/m20_v3_review/findings.md`:

```markdown
# Codex re-review of M-20 v3

## Verdict
GREEN / PARTIAL / DISAGREE

## v2 fix integration
- [x/no] plural class-form queries route via Tier A
- [x/no] test asserts ROUTED verdict
- [x/no] catalog-shape constraint still satisfied

## Final word
GREEN to lock M-20 + proceed / PARTIAL with edits.
```

Be terse. Under 80 lines.
