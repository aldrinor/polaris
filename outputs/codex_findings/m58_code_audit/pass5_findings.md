# Codex M-58 audit — pass 5

**Verdict**: CONDITIONAL-blockers

## Pass-4 exploit resolution
Verified in `src/polaris_graph/generator/slot_fill.py` (`_value_supported_by_span` at line 110, `_word_bounded_in` at line 171) and in the four pass-4 tests at `tests/polaris_graph/test_m58_slot_fill.py:450`, `:470`, `:488`, `:507`.

- `span="15 mg"` + `value="5 mg"` now raises.
- `span="1879"` + `value="879"` now raises.
- Legitimate cases still work:
  - `span="-0.47%"` + `value="-0.47%"` accepted in direct probe.
  - `span="N=1879"` + `value="1879"` accepted in `test_verbatim_from_equals_span_accepted`.

## Fifth-round adversarial attempts
- Unicode digit lookalike: `value="1879"`, `source_span="١٨٧٩"` raised. Good.
- Multi-line whitespace: `value="5 mg"`, `source_span="5\nmg"` accepted. Consistent with whitespace-collapse policy.
- Regex metacharacters: `value="C++"`, `source_span="C++"` accepted. `re.escape` is doing the right thing.
- Empty extracted value / empty `source_span`: both raised.
- NEW blocker: sign/symbol truncation still passes under the current `(?<!\w)needle(?!\w)` rule.
  - `value="0.47%"`, `source_span="-0.47%"` accepted.
  - `value="-0.47"`, `source_span="-0.47%"` accepted.
  - `value="Ca2"`, `source_span="Ca2+"` accepted.

This closes substring-inside-word exploits, but still permits substring-inside-symbol/token exploits. In clinical/scientific values, dropping `-`, `%`, or `+` changes meaning, so this remains a real anti-fabrication blocker.

## Policy clarity for future developers
Needs more.

- The `_value_supported_by_span` docstring is much better than earlier passes, but it overstates the current rule as the "Final policy" even though sign/symbol truncation is still open.
- Inline commentary in `parse_slot_fill_response` is stale: `src/polaris_graph/generator/slot_fill.py:425-434` still says "pass 1→3", "Final policy (pass-3)", and "three-pass history" after the pass-4 change.

## Residual concerns
- Regression target met: the five V30 files passed `190/190`.
- Pytest emitted one `.pytest_cache` access warning; no functional failure.
- No blocker found in the user-specified pass-4 exploit repros; the new blocker is specifically non-word sign/symbol truncation.

## Next
Claude iterates pass-6.

Fix should distinguish punctuation wrappers such as `(5 mg)` and `N=1879` from semantically attached signs/symbols such as `-0.47%` and `Ca2+`, then add regression tests for those cases before re-auditing M-58.

On CONDITIONAL-blockers: Claude iterates pass-6, or escalates to user for policy guidance if the residual is a design trade-off rather than a bug.
