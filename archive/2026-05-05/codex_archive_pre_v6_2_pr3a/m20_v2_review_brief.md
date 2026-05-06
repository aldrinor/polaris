M-20 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-20 v1 verdict: PARTIAL with 3 specific edits.

1. Plural surface forms missing for drug-class abbreviations
   ("PD-1 inhibitors", "DOACs", "calcium channel blockers" etc.
   dropped to operator_review).
2. Exact-duplicate medical_keywords inflating weak matches (oncology
   listed outcome/outcomes/result/results twice; cardio listed
   outcome/outcomes/adult/adults twice).
3. test_real_catalog_has_no_unexpected_ties shape too weak (only
   checked rationale text, missed the verdict assertion).

All 3 integrated in v2 (commit 330a1fe).

## What changed in v2

`template_catalog.py`:
- Oncology drug_keywords: added pd-1 inhibitors, pd-l1 inhibitors,
  parp inhibitors, car-ts, car t cells, tyrosine kinase inhibitors,
  tkis, antibody-drug conjugates, adcs.
- Cardio drug_keywords: added angiotensin receptor blockers, calcium
  channel blockers, arbs (already had singular), doacs, noacs,
  direct oral anticoagulants, p2y12 inhibitors, pcsk9 inhibitors,
  arnis.
- Removed exact duplicates from oncology medical_keywords (last
  occurrence of outcome/outcomes/result/results) and cardio (last
  occurrence of outcome/outcomes; "adult"/"adults" appeared in two
  different sub-lists — kept the population list, removed the
  earlier copy).

`test_template_classifier.py`:
- 10 new parametrized tests covering plural forms (PD-1 inhibitors
  / PARP inhibitors / DOACs / ARBs / calcium channel blockers /
  beta blockers / statins / PCSK9 inhibitors / etc.) — each must
  surface the correct specialty template at top-1 ranking.
- New test_no_duplicate_keywords_within_template invariant —
  asserts no template has duplicate drug_keywords or
  medical_keywords. Catches future re-introduction.
- test_real_catalog_has_no_unexpected_ties tightened: now asserts
  verdict == ROUTED + correct template_id (not just absence of
  "multiple templates" rationale).

Module: 82/82 classifier tests green. M-16+M-17+M-20 combined:
129/129 green.

## Your job

Final verdict on M-20. GREEN / PARTIAL / DISAGREE.

If GREEN, M-20 v2 locks. Phase C continues (next: M-18 regression
alerts). Note: M-20 ships with 3 templates (clinical / oncology /
cardio); the FINAL_PLAN target of 50+ comes via subsequent
batches, each gated by `test_real_catalog_has_no_unexpected_ties`
and `test_no_duplicate_keywords_within_template`.

## Output

Write to `outputs/codex_findings/m20_v2_review/findings.md`:

```markdown
# Codex re-review of M-20 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] plural class forms route correctly
- [x/no] no duplicate keywords within any template
- [x/no] tie smoke test asserts verdict shape, not just rationale

## Final word
GREEN to lock M-20 + proceed to M-18 / PARTIAL with edits.
```

Be terse. Under 80 lines.
