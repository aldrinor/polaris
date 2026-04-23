# Codex M-58 audit — pass 3

**Verdict**: CONDITIONAL-blockers

## Pass-2 exploit resolution
Verified.
`_value_supported_by_span` in `src/polaris_graph/generator/slot_fill.py:109-143` no longer uses `direct_quote`; support is now limited to:
- verbatim `value in source_span`, or
- `normalize(value) in normalize(source_span)` via `_normalize_for_span_check`.
The named regression `test_value_misbound_to_wrong_span_raises` is present at `tests/polaris_graph/test_m58_slot_fill.py:410` and passes.
Adversarial repro `span="5 mg"`, `value="10 mg"`, direct quote containing both phrases now raises `SlotFillParseError`.

Legitimate normalization is still intact:
- `span="N=1879"`, `value="1879"` accepted.
- `span="HbA1c"`, `value="hba1c"` accepted.
Both named tests are present and pass.

## New exploit attempts
Tried:
- `span="5 mg"`, `value="10 mg"` with both phrases in `direct_quote`: rejected. Closed.
- `span="10\tmg"`, `value="10 mg"`: accepted. Looks intentional whitespace normalization, not a new hole by itself.
- `span=""`, `value="10 mg"`: rejected before support check; no crash.
- `span="Café"`, `value="cafe"`: rejected.
- `span="Straße"`, `value="strasse"`: rejected.
- `span="H"`, `value="h"`: accepted.
- `span="İ"`, `value="i"`: accepted.
- `span="5 M"`, `value="5 m"`: accepted. New blocker.

Why blocker:
Lowercasing in `_normalize_for_span_check` conflates case-sensitive scientific tokens. `5 M` and `5 m` are not the same value/unit, but the parser accepts the drift and would let prose render the wrong quantity as "supported". This is the same root cause as the single-character acceptance, but `M` vs `m` is a concrete semantic inversion, not a cosmetic mismatch.

## Residual concerns
- Comment drift in `parse_slot_fill_response` around `src/polaris_graph/generator/slot_fill.py:378-385`: the inline comment still describes the old pass-1 `direct_quote + token overlap` fallback even though the implementation now calls the tighter span-only rule. Not a behavioral bug, but misleading during future audits.
- I could not verify the claimed `184/184` gate from this workspace. What I could verify:
  - `python -m pytest -q tests/polaris_graph/test_m58_slot_fill.py` -> `34 passed`
  - broader repo / Polaris suites are already red for unrelated failures and temp-path permission errors, so there is no clean local signal for `184/184`.

## Next
Block on M-59 until case-normalization is narrowed or removed for case-sensitive spans; then add a regression such as `span="5 M"` + `value="5 m"` -> `SlotFillParseError`.
