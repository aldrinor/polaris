# Codex M-58 audit — pass 2

**Verdict**: CONDITIONAL-blockers

## Blocker 1 — value-not-supported-by-span
Partially resolved, not fully closed.

- Verified `_value_supported_by_span` exists in `src/polaris_graph/generator/slot_fill.py:109` and `parse_slot_fill_response` raises `SlotFillParseError` with `anti-fabrication check 2 failed` in `src/polaris_graph/generator/slot_fill.py:374`.
- Verified `test_fabricated_value_with_real_span_raises` and `test_value_whitespace_normalization_accepted` exist in `tests/polaris_graph/test_m58_slot_fill.py:354` and `:376`; `python -m pytest tests/polaris_graph/test_m58_slot_fill.py -q` reports `32 passed`.
- The original hole `value="1880"` + `source_span="N=1879"` is closed.
- Remaining blocker: the fallback `value in direct_quote AND >=1 token overlap with source_span` is too permissive. Runtime repro on current code: `direct_quote="Dose 5 mg daily, escalated to 10 mg after 4 weeks."`, `source_span="5 mg"`, `value="10 mg"` returns `True`, and `parse_slot_fill_response` accepts it. A real value elsewhere in the quote can still be misbound to the wrong span if it shares a generic token like `mg`.
- Edge cases: 1-character tokens are conservatively rejected in the fallback; punctuation and Unicode normalization can create false negatives. Those are secondary. The open issue is the same-quote misbinding false positive above.

## Medium — compose_gap_payload symmetry
Resolution verified.

- `compose_gap_payload` now raises `ValueError` for any provenance other than `FRAME_GAP_UNRECOVERABLE` in `src/polaris_graph/generator/slot_fill.py:416`.
- Verified new tests `test_non_gap_row_raises`, `test_open_access_row_raises`, and `test_metadata_only_row_raises` in `tests/polaris_graph/test_m58_slot_fill.py:419`, `:428`, and `:433`; they pass.
- This is sufficient for the stated routing bug.

## Residual concerns (if any)
- Regression slice verified: `python -m pytest tests/polaris_graph/test_m54_contract_schema.py tests/polaris_graph/test_m55_frame_compiler.py tests/polaris_graph/test_m56_frame_fetcher.py tests/polaris_graph/test_m57_contract_outline.py tests/polaris_graph/test_m58_slot_fill.py -q` reports `182 passed`.
- The blocker remains until anti-fabrication check 2 requires stronger span support than one shared token. Reasonable fixes: normalized containment against `source_span`, or all significant value tokens present in `source_span` after stricter normalization.

## Next
Hold M-59. Tighten anti-fabrication check 2 and add a regression test for misbound same-quote values such as `source_span="5 mg"` with `value="10 mg"`.
