You are auditing M-48 — first of 7 V28 bundle items. Narrow scope.
Plan APPROVED at outputs/codex_findings/v28_fix_plan_review_pass2/findings.md.

## Commit

`5e0b447` PL: M-48 — per-anchor variants + population-scope labels + preflight

## Plan references

`outputs/audits/v27/fix_plan_v28.md` M-48 (pass-2 revised):
- Per-anchor first-author + journal query variants (YOUR revision #7)
- SURMOUNT population-scope labels: SURMOUNT-2 direct; SURMOUNT-1/3/4
  indirect_for_t2d (YOUR verbatim requirement)
- Retrieval preflight script with per-anchor coverage assertion

## Files changed (this commit only)

- `config/scope_templates/clinical.yaml` — added
  `per_query_primary_trial_variants` + `per_query_trial_population_scope`
  for the clinical_tirzepatide_t2dm slug.
- `src/polaris_graph/retrieval/primary_trial_expander.py` — three new
  functions: `_extract_variants`, `get_trial_population_scope_for_slug`,
  `label_rows_with_population_scope`. `expand_primary_trial_queries`
  extended to emit anchor + variant per anchor.
- `scripts/run_honest_sweep_r3.py` — wires the population-scope
  labeler after retrieval.
- `scripts/v28_retrieval_preflight.py` — NEW retrieval-only preflight
  that asserts ≥1 primary per anchor, exits 1 on any failure.
- `tests/polaris_graph/test_m48_anchor_variants_and_scope.py` — NEW,
  20 tests.
- `tests/polaris_graph/test_m35_primary_trial_expander.py` — one
  stale assertion updated (cap 15 → cap*2=30 to accommodate variants).

## What to audit

Per your standard code-audit protocol:

1. **Variant schema**: does the YAML handle malformed variant values
   correctly? (Interior whitespace? Embedded quotes? Non-string types?)
2. **Query emission**: is the anchor cap applied to anchor count (not
   final query count) as the plan specified? Does the order match the
   plan (anchor-then-variant alternation)?
3. **Population-scope labeling**:
   - Does the title-match correctly label SURMOUNT-1/3/4 as indirect
     and SURMOUNT-2 as direct?
   - Does it handle rows with no anchor match (should leave alone)?
   - Any risk of over-tagging (e.g. SURMOUNT-11 title matching
     "SURMOUNT-1" substring)? [I accept this as a known limitation;
     no tirzepatide trials >9 exist; advise if you disagree.]
4. **Preflight script**: correct exit codes? Report schema useful?
5. **Backwards compatibility**: slugs without variants/scope section
   still work (tested in test_backwards_compatible_when_no_variants_section)?
6. **Integration with sweep script**: is the labeler wired at the
   right point (after initial retrieval, before evidence selection)?

## Test run

`PYTHONPATH=src python -m pytest tests/polaris_graph/test_m48_anchor_variants_and_scope.py tests/polaris_graph/test_m35_primary_trial_expander.py -q` — 148 passed (including 20 new).

## Output

Write your verdict to
`outputs/codex_findings/m48_code_audit/findings.md`. READY | CONDITIONAL
| BLOCKED per the established pattern (M-42e/a+b/c/d, M-43). On READY
or CONDITIONAL-no-blockers: Claude starts M-46 implementation.
