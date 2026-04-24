M-42a+b pass-2 audit. Pass-1 verdict: BLOCKED on 2 real
contract-violation defects. Pass-2 closes both.

## Pass-1 blockers (what you required)

1. **`statement` fallback in builder**: pre-pass-2 allowed
   `statement` as a fallback extraction source when direct_quote
   was thin. Contract says statement is disambiguation-only.

2. **LLM fallback receives generated prose**: pre-pass-2 fed
   `section_results[].verified_text` (generated report prose) to
   `_call_trial_summary_table`. Contract says LLM fallback must
   receive only primary-trial `direct_quote`s.

## Pass-2 changes

1. **`statement` branch removed**: `build_trial_summary_and_timeline_from_evidence`
   now enforces strict `direct_quote OR refetch OR skip` contract.
   Rows with thin direct_quote that cannot be refetched are
   `extraction_ineligible` and skipped — no statement fallback.

2. **LLM fallback rewired**: when deterministic builder returns
   empty, `generate_multi_section_report` now constructs
   `fallback_source` as concatenated primary-trial
   `direct_quote` strings (labeled with anchor names for clarity),
   NOT generated prose. When no primary-trial rows have a valid
   direct_quote, the LLM fallback is SKIPPED entirely and the
   table stays empty — honest about the evidence shortfall.

3. **Medium fix**: `_m42b_year_from_row` now checks the cached
   `_m42b_refetched_quote` attribute after URL and
   original direct_quote. Rows refetched during extraction can
   contribute their year to the timeline.

## New regression tests (2)

- `test_pass2_statement_fallback_REMOVED`: row with thin
  direct_quote + long statement + no refetch → builder produces
  NOTHING (statement must not be promoted). Pair of SURPASS-2/-3
  rows where SURPASS-2 has thin-quote + long-statement and
  SURPASS-3 has good quote → result is empty (since only 1
  qualifying row, below 2-row threshold).
- `test_pass2_year_from_refetched_quote`: row with URL/quote
  having no year + `_m42b_refetched_quote` containing "2021" →
  year returned as "2021".

## Files

```
src/polaris_graph/generator/multi_section_generator.py
  - build_trial_summary_and_timeline_from_evidence: statement
    branch removed; comment explains contract
  - _m42b_year_from_row: +refetched_quote check
  - generate_multi_section_report: LLM fallback receives
    primary-trial direct_quotes, skips if none available

tests/polaris_graph/test_m42ab_anaphoric_and_builder.py (+2 tests)
```

## What to verify

1. Is the statement branch fully removed? (grep for `statement`
   in the builder — should only appear in removed-branch comment)

2. Does the LLM fallback correctly extract direct_quote from
   primary-trial rows? Confirm it iterates anchors, matches via
   title.lower().contains(anchor.lower()), concatenates with
   anchor labels, skips rows with <100-char direct_quote.

3. Does the LLM fallback gracefully skip when no primary rows
   have usable direct_quote? (Table stays empty; logger info
   message emitted.)

4. Year extraction precedence: URL → original quote → refetched
   quote. Correct order?

5. All 24 tests pass (22 pass-1 + 2 pass-2). No regression on
   existing tests.

## What remains medium (not blocking)

- Primary-row filter is title + anchor only. M-42e upstream
  handles primary detection, so downstream re-check is belt-
  and-suspenders. Acceptable trade-off per pass-1 note.

## Deliverable

Write `outputs/codex_findings/m42ab_code_audit_pass2/findings.md`.
Final verdict READY | CONDITIONAL | BLOCKED. Confirm both pass-1
blockers closed.

Under 500 words.
