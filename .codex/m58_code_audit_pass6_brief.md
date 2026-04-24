M-58 code audit pass 6 — verify structural fix.

**Skip git status.** Focus only on these two files.

## Context

Pass-5 surfaced sign/ionic-state truncation (span='-0.47%' +
value='0.47%'; span='Ca2+' + value='Ca2'). Rather than another
regex tweak, commit `d10d9c7` makes a structural change:

  Old: value is a substring of source_span with some boundary rule.
  New: value MUST equal source_span (modulo whitespace collapse).

This collapses the distinction. No substring-containment exposure
remains. The prompt is updated to tell the LLM: "value and
source_span must be IDENTICAL strings copied verbatim from
direct_quote".

## What to verify

Files (commit `d10d9c7`):

1. `src/polaris_graph/generator/slot_fill.py` — `_value_matches_span`
   + `_whitespace_collapse`. `_word_bounded_in` and
   `_normalize_for_span_check` DELETED.
2. `tests/polaris_graph/test_m58_slot_fill.py` — 44 tests total
   (was 40; +4 new for pass-5 structural change, some old tests
   flipped from "accepted legitimate drift" to "raises").

Check:

1. **Structural fix**: is `value == source_span OR
   whitespace_collapse(value) == whitespace_collapse(source_span)`
   the right rule? Does it close all five previous exploits?
2. **Prompt-parser alignment**: the new prompt tells the LLM
   "value and source_span MUST be IDENTICAL strings (modulo
   whitespace collapse)". Does that match what the parser
   enforces?
3. **Sixth-round adversarial attempts**: try to break the equality
   rule. Ideas:
   - Unicode normalization forms (NFC vs NFD — 'é' as single
     codepoint vs 'e' + combining acute)
   - Invisible characters (zero-width space, non-breaking space)
     between matching visible characters
   - Leading/trailing whitespace only on one side (handled by
     whitespace_collapse)
   - Multi-line span vs single-line value
   - Any exploit where value == source_span but the value still
     doesn't mean what it seems
4. **Prompt quality**: is the new "rule 7" (quote-same-form-for-
   both) sufficient guidance for a real LLM, or could it still
   emit value != span naturally?
5. **Regression**: 194/194 pass (was 190; +4 new tests).

## Output

Write to
`outputs/codex_findings/m58_code_audit/pass6_findings.md`.

Format:
```markdown
# Codex M-58 audit — pass 6

**Verdict**: APPROVED | CONDITIONAL-no-blockers | CONDITIONAL-blockers | REJECT

## Structural fix verification
<five-pass exploits all closed? yes/no with detail>

## Prompt-parser alignment
<contract matches what parser enforces?>

## Sixth-round adversarial attempts
<list each input, parser behavior>

## Residual concerns
<anything>

## Next

On APPROVED / CONDITIONAL-no-blockers: Claude proceeds to M-59.
```

Keep under 80 lines. This should be the converging pass. If you
find no NEW exploit (only previously known or clearly out-of-
scope issues like LLM prompt adherence), mark APPROVED.
