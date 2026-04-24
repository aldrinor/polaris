M-58 code audit pass 2 — verify blocker + medium fix.

**Skip git status.** Focus only on the two files below.

## Context

Pass-1 verdict: CONDITIONAL-blockers. One blocker + one medium
fixed in commit `9bcedb3`:

- Blocker: parse_slot_fill_response didn't verify `value in source_span`.
  Fix: new `_value_supported_by_span` helper; parser raises when
  extracted `value` is not traceable to the span or to direct_quote
  with token overlap.
- Medium: compose_gap_payload silently accepted non-gap rows.
  Fix: raises ValueError for non-gap provenance (symmetric with
  build_slot_fill_prompt's guard).
- Nit: gap prose template noted as stopgap owned by M-60.

## What to verify

Files (commit `9bcedb3`):

1. `src/polaris_graph/generator/slot_fill.py`
2. `tests/polaris_graph/test_m58_slot_fill.py`

Check:

1. **Blocker resolution** —
   - `_value_supported_by_span(value, source_span, direct_quote)`
     logic: accept when value ∈ source_span, OR when value ∈
     direct_quote AND ≥1 token overlap with source_span.
   - parse_slot_fill_response raises SlotFillParseError with
     "anti-fabrication check 2" on fabricated value.
   - Test `test_fabricated_value_with_real_span_raises`:
     value="1880" + span="N=1879" raises.
   - Test `test_value_whitespace_normalization_accepted`:
     value="1879" + span="N=1879" passes.
   Does this close the fabrication hole? Any edge case that
   slips through (e.g. tokens of length 1, punctuation-only
   overlap, language-specific character handling)?

2. **Medium resolution** —
   - compose_gap_payload raises ValueError when provenance_class
     != FRAME_GAP_UNRECOVERABLE.
   - Three new tests: non_gap (ABSTRACT_ONLY), open_access,
     metadata_only all raise.
   Sufficient?

3. **Regression check** — M-54 54 + M-55 41 + M-56 35 + M-57 20
   + M-58 32 = 182/182 pass (was 177; +5 tests).

## Output

Write to
`outputs/codex_findings/m58_code_audit/pass2_findings.md`.

Format:
```markdown
# Codex M-58 audit — pass 2

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Blocker 1 — value-not-supported-by-span
<resolution verified / still open>

## Medium — compose_gap_payload symmetry
<resolution verified / still open>

## Residual concerns (if any)
<mediums/nits/new items>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-59
(slot-completion validator).
```

Keep under 80 lines. Pass-2 scope is narrow — verify the two
fixes. Use your full xhigh reasoning budget to find edge cases.
