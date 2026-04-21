# M-30 code audit — pass 5

VERDICT: NOT_READY

## Blockers
- Residual false-PASS class remains for ALL-CAPS acronym subjects followed by common present-tense verbs outside `_PT11_VERB_INDICATORS`. The pass-5 logic at `src/polaris_graph/evaluator/external_evaluator.py:281` treats `ACRONYM + non-verb` as non-boundary, while `_looks_like_verb_form` only recognizes the explicit verb list plus `-ed`/`-ing` forms. Probes that should fail PT11 but currently pass:
  - `... 4.2%, 5.3%, 6.4%, 7.5%, 8.6%, and 9.7% in the U.S. FDA warns about endpoint drift.[1]`
  - `... 4.2%, 5.3%, 6.4%, 7.5%, 8.6%, and 9.7% in the U.S. CDC says surveillance changed.[1]`
  In both cases `[1]` cites the acronym-subject sentence, not the prior decimal sentence, but PT11 returns `passed=True`. This is the dangerous false-PASS class pass-5 is intended to close, just with present-tense verbs not included in the curated list.

## Mediums
- None.

## Lows / nits
- Full `tests/polaris_graph` could not be cleanly verified in this sandbox. With `PYTHONPATH=src`, 747 tests collected and 722 passed before 2 failures / 23 errors caused by temp-directory permission failures (`PermissionError` under `C:\Users\msn\AppData\Local\Temp` and `C:\POLARIS\codex_tmp_pytest`). The focused M-30 PT11 file passed: `40 passed`.

## Notes
- Required pass-4 probes now fail PT11 as intended:
  - `U.S. FDA approved the endpoint summary.[1]` -> FAIL, `6 numeric claims without adjacent citation marker`.
  - `U.S. CDC reported a separate finding.[1]` -> FAIL, `6 numeric claims without adjacent citation marker`.
- Pass-3 positive case still passes:
  - `U.S. FDA database across cohorts.[1]` -> PASS.
- Prior pass-1/pass-2 blockers still fail:
  - `Jan. A separate... [1]` -> FAIL.
  - `U.S. A separate... [1]` -> FAIL.
  - `et al. A separate... [1]` -> FAIL.
  - `etc. A separate... [1]` -> FAIL.
- Additional probes:
  - `U.K. NHS is responsible for health.[1]` -> FAIL.
  - `E.U. ECB announced rate cuts.[1]` -> FAIL.
  - `U.K. Biobank data across cohorts.[1]` -> PASS.
  - `U.S. FDA issues endpoint guidance.[1]` -> FAIL.
  - `U.S. CDC reports a separate finding.[1]` -> FAIL.
- Hard-coding check: `_PT11_VERB_INDICATORS` is general English vocabulary, not domain-specific, but it is too sparse for the claimed present-tense coverage. The remaining issue is not domain hard-coding; it is incomplete detection of ordinary present-tense verb forms.
