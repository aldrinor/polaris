M-58 code audit pass 4 — verify pass-3 tightening.

**Skip git status.** Focus only on these two files.

## Context

Pass-3 verdict: CONDITIONAL-blockers. You caught the `5 M` vs
`5 m` case-normalization exploit. Commit `153c435` tightens:

  Pass-3 policy: whitespace-only normalization (no lowercase).
  Accepted:
    - value verbatim in source_span
    - whitespace-collapsed value in whitespace-collapsed source_span

  Rejected:
    - case drift (HbA1c vs hba1c, 5 M vs 5 m)
    - diacritic drift (Café vs cafe)
    - any direct_quote fallback (pass-2 fix)

## What to verify

Files (commit `153c435`):

1. `src/polaris_graph/generator/slot_fill.py` — `_value_supported_by_span`
   + `_normalize_for_span_check` + the inline comment rewrite.
2. `tests/polaris_graph/test_m58_slot_fill.py` — three new tests:
   `test_value_case_mismatch_raises`,
   `test_molarity_meter_case_raises`,
   `test_whitespace_only_normalization_still_accepted`.

Check:

1. **Pass-3 exploit closed**: span="5 M", value="5 m" now raises.
   Test `test_molarity_meter_case_raises` locks in the exact repro.
2. **Contract still covers legitimate normalization**:
   whitespace/tab variation still accepted via
   `test_whitespace_only_normalization_still_accepted`.
3. **Comment drift fixed**: inline comment near anti-fabrication
   check 2 now references the three-pass history and points to
   the docstring rather than describing the pass-1 fallback.
4. **Adversarial attempts**: try one more round. You previously
   surfaced real blockers at each pass. What else slips through
   the current policy? Examples:
   - Punctuation drift (comma vs no comma)
   - Unicode homoglyphs (Latin M vs Greek Μ)
   - Numeric representation (1,000 vs 1000)
   - Leading/trailing punctuation in value or span
   - Value substring matches wrong instance in span (if span
     contains the value multiple times with different semantics —
     but that's a narrow case)

5. **Regression**: 186/186 pass (was 184; +2 new tests, -0 lost
   — old `test_value_case_insensitive_normalization_accepted`
   was deleted since the accommodation was wrong).

## Output

Write to
`outputs/codex_findings/m58_code_audit/pass4_findings.md`.

Format:
```markdown
# Codex M-58 audit — pass 4

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Pass-3 exploit resolution
<verified / still open>

## New adversarial attempts
<list each input, whether parser caught it, and whether you
found a new hole>

## Residual concerns
<mediums/nits>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-59.
On CONDITIONAL-blockers: Claude iterates pass-5.
```

Keep under 80 lines. This is an adversarial pass — use the full
xhigh reasoning budget to find holes.
