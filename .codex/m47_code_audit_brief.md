M-47 audit — fifth of 7 V28 bundle items.

## Commit

`6e85312` (bundled with M-44 pass-3 + M-45 pass-2).

## Plan reference

`outputs/audits/v27/fix_plan_v28.md` M-47 (pass-2). Your verbatim:

> "The validator extracts candidate quantitative fields from the
> cited clamp/PK evidence row's direct_quote or accepted refetched
> quote, normalizes units/patterns, and then checks that at least
> three of those same values/fields appear in the verified
> Mechanism section with the clamp/PK ev_id citation. Broad numeric
> counts in the section do not satisfy the rule."

## What changed

`src/polaris_graph/generator/multi_section_generator.py`:
- New "M-47 MECHANISM QUANTITATIVE-EXTRACTION RULE" section in
  SECTION_SYSTEM_PROMPT_TEMPLATE (placeholders only, passes M-32
  drug-scrub).
- `_M47_CLAMP_PK_TOKENS` (20-token vocabulary).
- `_m47_row_is_clamp_or_pk_paper(row)`: detects clamp/PK papers via
  title + statement + direct_quote substring match. Uses the same
  live-row-compatible accessor as M-48 pass-2.
- `_M47_VALUE_PATTERNS` (10-pattern regex list): M-value %,
  first/second-phase insulin %, insulin secretion rate, glucagon
  suppression %, half-life (hours|days), Tmax/Cmax, participant N,
  affinity ratio, clamp duration weeks.
- `_m47_extract_candidate_values(quote)`: runs patterns + dedups
  by (field_name, round(val, 2)).
- `_m47_prose_contains_value(text, ev_id, field, value, biblio)`:
  ±5% tolerance fuzzy match, unit normalization for half-life
  (days↔hours).
- `_m47_validate_mechanism_clamp_extraction()`: main validator.

In generate_multi_section_report: runs only on Mechanism section.
Populates `MultiSectionResult.m47_mechanism_clamp_diagnostic`.
Orchestrator persists `m47_mechanism_clamp_diagnostic.json`.

## Test coverage

`tests/polaris_graph/test_m47_mechanism_clamp_validator.py` — 24
tests:
- 5 clamp-paper detection (incl. live-row-statement-only schema)
- 7 value extraction (M-value, half-life, N, glucagon suppression,
  empty, no-fields, dedup)
- 6 prose matching (same sentence, different sentence, direct
  ev_id ref, ±5% within, ±5% outside, days↔hours equivalence)
- 4 integration (3-field pass, cite-without-extract fail,
  no-clamp no-op, broad-numeric-no-false-pass per your verbatim)
- 2 prompt-rule checks (rule present, no drug-name hard-codes)

276/276 regression across M-series.

## What to audit

1. **Evidence-linked contract**: does the validator extract from the
   CITED row's direct_quote (not the section's numbers)?
2. **Unit normalization**: half-life days↔hours works? Should we
   also normalize mg/dL↔mmol/L? (I can add if you want.)
3. **Broad-numeric false-pass prevention**: verified by
   `test_broad_numeric_tokens_do_not_false_pass`. Sufficient?
4. **Thresholds**: ≥3 matched fields matches your plan. Test
   `test_clamp_paper_with_3_matched_fields_passes` verifies.
5. **±5% tolerance**: reasonable per your plan language? Or do you
   want stricter ±2% / looser ±10%?
6. **Prompt-rule placement**: M-47 sits before M-42c sub-rule in
   SECTION_SYSTEM_PROMPT_TEMPLATE (both are Mechanism-specific
   rules, M-47 is the extraction requirement, M-42c is the length
   target). Acceptable ordering?

Write verdict to `outputs/codex_findings/m47_code_audit/findings.md`.
On READY/CONDITIONAL-no-blockers: Claude proceeds to M-50 (per-trial
subsection generator).
