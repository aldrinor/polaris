M-47 pass-2 audit — closes 3 Codex pass-1 findings.

## Pass-1 verdict (commit `6e85312`)

NEEDS REVISION. 2 blockers + 1 conditional:
- Blocker #1: field linkage not enforced — value-only matching
  false-passes "63 participants" against M-value=63 extraction.
- Blocker #2: no regen or incomplete telemetry on validator failure.
- Conditional #3: thin direct_quote with fat _m42b_refetched_quote
  picks thin via `or` short-circuit.

## Pass-2 (commit `a988c0e`)

**Blocker #1 closure**:
- New `_M47_FIELD_CONTEXT_TOKENS` dict mapping each field to its
  context tokens (M-value → ['m-value', 'm value',
  'insulin sensitivity', 'whole-body insulin'];
  half-life → ['half-life', 't1/2', ...]; etc.).
- `_m47_prose_contains_value` now requires sentence to contain
  both (a) a number within ±5% tolerance, AND (b) a matching
  field-context token. Fields without configured tokens fall
  through to value-only matching (backwards-compat).
- New test `test_codex_false_pass_reproducer_now_fails` reproduces
  your exact repro and asserts passes_threshold=False.

**Blocker #2 closure**:
- On any_passes_threshold=False, regen Mechanism section with
  focus hint: "REQUIRED M-47 EXTRACTION: [ev_id]: report at least
  3 of {m_value_pct=63, glucagon_suppression_pct=42, ...} inline
  with [ev_id] citation in the same sentence."
- `_bounded_run` regen; re-validate; replace original if regen
  matches more fields OR fully passes with nonzero sentences.
- On still-failing, set `m47_diag['m47_mechanism_extraction_
  incomplete'] = True` + log telemetry.

**Conditional #3 closure**:
- Picks richer of direct_quote or _m42b_refetched_quote (same
  pattern as M-50 candidate selection). Fixed in
  `_m47_validate_mechanism_clamp_extraction` and in M-50 selector.

## Files changed

- `src/polaris_graph/generator/multi_section_generator.py`: added
  `_M47_FIELD_CONTEXT_TOKENS`; updated `_m47_prose_contains_value`
  to require context token; extended regen in
  `generate_multi_section_report` body to invoke _bounded_run on
  Mechanism on validator failure.
- `tests/polaris_graph/test_m47_mechanism_clamp_validator.py`:
  5 new pass-2 tests.

## Tests

`PYTHONPATH=src python -m pytest tests/polaris_graph/test_m47_mechanism_clamp_validator.py -q`: 29 passed (was 24 pre-pass-2). 292/292 full M-series regression.

## What to audit

1. **Blocker #1 closure**: is the field-context token set complete
   enough per field? Any M-value paraphrase I missed
   (e.g. "sensitivity index")?
2. **Blocker #2 closure**: regen loop runs on validator failure
   and records m47_mechanism_extraction_incomplete when still
   failing. Acceptable?
3. **Conditional #3 closure**: richer-quote selection matches
   M-50's pattern. Consistent?
4. **Any false-negative concern**: legitimate clamp prose that
   uses synonyms like "insulin sensitivity index" instead of
   "M-value"? Covered by `insulin sensitivity` in the token list.

Write verdict to
`outputs/codex_findings/m47_code_audit_pass2/findings.md`.
