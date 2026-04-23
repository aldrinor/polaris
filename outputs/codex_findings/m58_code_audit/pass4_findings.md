# Codex M-58 audit — pass 4

**Verdict**: CONDITIONAL-blockers

## Pass-3 exploit resolution
Verified in `src/polaris_graph/generator/slot_fill.py:109-152,378-388` and `tests/polaris_graph/test_m58_slot_fill.py:392-445`.
- `span="5 M", value="5 m"` now raises; `test_molarity_meter_case_raises` locks in the exact repro and passed.
- Whitespace-only normalization still works; `test_whitespace_only_normalization_still_accepted` passed with `span="5\tmg"` and `value="5 mg"`.
- Comment drift is fixed: the anti-fabrication check-2 comment now summarizes the pass-1→3 history and points to the `_value_supported_by_span` docstring instead of restating the pass-1 fallback.

## New adversarial attempts
- `span="1,000 mg", value="1000 mg"`: parser raised. No new hole.
- `span="5 M", value="5 Μ"` (Greek Mu homoglyph): parser raised. No new hole.
- `span="HbA1c reduction", value="(HbA1c reduction"`: parser raised. No new hole.
- `span="(5 mg)", value="5 mg"`: parser accepted. Not a hole under the stated contract; the value is still verbatim inside the cited span.
- `span="15 mg", value="5 mg"`: parser accepted. New hole.
- `span="1879", value="879"`: parser accepted. Same hole class.

## Residual concerns
- `_value_supported_by_span` still uses raw containment (`value in source_span` and normalized containment). That closes case/diacritic/whitespace drift, but it still accepts internal substrings without token or numeric boundaries.
- Result: truncated numeric values can piggyback on larger numbers/units inside the same span. This is a real anti-fabrication gap, not just a prompt-quality issue.
- Narrow residual only: if the same exact string appears multiple times inside one long `source_span` with different semantics, the parser still cannot disambiguate which mention the field meant. That is not new in pass-3.
- Regression is only partially verified here: `python -m pytest tests/polaris_graph/test_m58_slot_fill.py -q` passed `36/36`, but `python -m pytest -q` aborted during unrelated collection with 11 external import/permission errors, so the claimed `186/186` could not be substantiated in this workspace.

## Next

On CONDITIONAL-blockers: Claude iterates pass-5.
