M-58 code audit pass 3 — verify anti-fabrication tightening.

**Skip git status.** Focus only on these two files.

## Context

Pass-2 verdict: CONDITIONAL-blockers. Same-quote misbinding
exploit (`span="5 mg"` + `value="10 mg"`) was still accepted by
the pass-1 fallback. Commit `0b1c97f` tightens the policy:

  Old policy (pass-1):
    - value ∈ source_span  OR
    - value ∈ direct_quote AND ≥1 token overlap with source_span

  New policy (pass-2 tightening):
    - value ∈ source_span  OR
    - normalize(value) ∈ normalize(source_span)
      where normalize = whitespace-collapse + lowercase

The direct_quote fallback is DROPPED.

## What to verify

Files (commit `0b1c97f`):

1. `src/polaris_graph/generator/slot_fill.py` —
   `_value_supported_by_span` and `_normalize_for_span_check`.
2. `tests/polaris_graph/test_m58_slot_fill.py` —
   `test_value_misbound_to_wrong_span_raises` (pass-2 regression
   case), `test_value_case_insensitive_normalization_accepted`,
   `test_value_whitespace_normalization_accepted`.

Check:

1. **Pass-2 exploit closed**: `span="5 mg"` + `value="10 mg"` with
   a direct_quote containing BOTH phrases now raises
   SlotFillParseError. Regression test locks this in.
2. **Legitimate normalization still accepted**: span="N=1879"
   value="1879" passes (normalized substring match). span="HbA1c"
   value="hba1c" passes (case normalization).
3. **New exploit attempts**: find an adversarial input that the
   new policy still accepts but shouldn't. Examples you might
   try:
   - span="H" with value="h" (normalized single-char match)
   - span with non-ASCII characters + value with ASCII normalization
   - span with newlines / tabs + value with spaces
   - span="" (empty) — currently returns False; verify no crash
   - unicode characters that normalize differently under casefold()
     vs lower()
   If you find a new exploit, that's a new blocker.

4. **Regression**: 184/184 pass (was 182; +2 new tests).

## Output

Write to
`outputs/codex_findings/m58_code_audit/pass3_findings.md`.

Format:
```markdown
# Codex M-58 audit — pass 3

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Pass-2 exploit resolution
<verified / still open>

## New exploit attempts
<list any you tried, whether the parser caught them, and whether
you found a new hole>

## Residual concerns
<mediums/nits>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-59.
```

Keep under 80 lines. Full xhigh reasoning budget — be adversarial.
