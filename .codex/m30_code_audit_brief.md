You are auditing M-30 (PT11 abbreviation-aware sentence boundary) as a
code review BEFORE V20 full-scale sweep runs. This is a code audit,
not a DR content audit.

## Context

V19 aborted with `release_allowed=False`, eval_gate reason
`rule_pt11_uncited_numeric_claims`. 4 of 43 decimals flagged uncited.

Root cause (diagnosed): PT11 regex treated `vs. ` as a sentence
boundary. The V19 Safety section wrote:

  "including diarrhea (10.7% vs. 4.8%), nausea (8.1% vs. 2.7%),
   and vomiting (5.7% vs. 1.2%).[7]"

The `[7]` citation at the true sentence end covered all 4 decimals,
but PT11's lookahead stopped at the first `. ` pattern — which in this
text is `vs. `. Zero underlying quality defect; the checker has a
false-positive on English abbreviation orthography.

## Fix

Commit `6056855` (`PL: M-30 — PT11 abbreviation-aware sentence
boundary`).

Two new module-level helpers in
`src/polaris_graph/evaluator/external_evaluator.py`:

- `_is_abbreviation_period(text, pos)` — walks back from a `.` to the
  token, matches against a generalizable English abbreviation list
  (`vs`, `etc`, `Fig`, `No`, `Dr`, `Inc`, months, `e.g`, `i.e`, `et
  al`, etc.). Returns True if the period is an abbreviation terminator
  (NOT a sentence boundary).
- `_next_real_sentence_end(text)` / `_prev_real_sentence_end(text)` —
  first/last real sentence terminator in `text`, skipping abbreviation-
  period false positives.

PT11 now uses these in both lookahead and lookback windows.

Regression test: `tests/polaris_graph/test_m30_pt11_abbreviation_boundary.py`
covers the V19 pattern plus genuinely-uncited-decimal counter-test
(fix must not over-relax).

Tests: 707 → 724 (+17 M-30). Suite green.

## Your task

Review the change for:

1. **Correctness**. Does `_is_abbreviation_period` correctly identify
   abbreviations in representative English prose? Are there edge cases
   it would incorrectly flag as abbreviation (false-negative sentence
   boundaries)? Are there abbreviations it misses that would still
   bite PT11?

2. **Generalization**. The abbreviation list is English-language
   generalizable (no POLARIS-specific, no tirzepatide-specific, no
   clinical-specific terms). Is that assertion correct? Does the list
   include any domain-leak terms that should be removed?

3. **Risk**. Could the new helpers break existing PT11 behavior on
   reports that previously passed? (Existing external_evaluator tests
   must still pass.)

4. **Test coverage**. Are the regression and counter-test adequate?
   Any edge cases that should be added before V20 runs?

5. **Hard-coding check**. The user mandate (2026-04-20) forbids
   narrow, domain-specific hard-codes. Is the abbreviation list a
   legitimate generalizable English orthography concept, or does it
   sneak in hidden domain bias? (Example litmus: does it include any
   abbreviation that only makes sense for clinical trials or for
   tirzepatide? If yes → flag as blocker.)

## Files to review

- `src/polaris_graph/evaluator/external_evaluator.py` lines 60-156
  (new helpers + abbreviation list).
- `src/polaris_graph/evaluator/external_evaluator.py` lines 295-345
  (PT11 loop using the new helpers).
- `tests/polaris_graph/test_m30_pt11_abbreviation_boundary.py` (full
  file).

## Verdict format

Write `outputs/codex_findings/m30_code_audit/findings.md` with:

```
# M-30 code audit findings

VERDICT: READY | NOT_READY

## Blockers (fix before V20)
- none  OR  - <list>

## Mediums (should fix, not blocking)
- none  OR  - <list>

## Lows / nits
- <list>

## Notes
<any other observations>
```

If VERDICT is READY, V20 sweep launches next.
If NOT_READY, Claude fixes the blockers and re-audits.

## Scope

Audit ONLY the M-30 diff. Do NOT audit M-28, M-29, or the pre-existing
PT11 logic. Do NOT audit the V19 outline-decode failure — that's
tracked separately as task #8 (M-31).
