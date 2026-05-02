M-14 v4 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-14 v3 verdict: PARTIAL. One issue — smart-apostrophe
negation false-converged because `_expand_contractions()` only
matched ASCII `'`, not Unicode `'` (U+2019).

Integrated in v4 (commit 56b8c61).

## What changed in v4

`_expand_contractions(text)`:
- Normalize U+2018 (left smart) and U+2019 (right smart) to
  ASCII `'` BEFORE the contraction map runs.

Tests: 4 new parametrized cases.

M-14 module 52 → 56 green.

## Your job

Final verdict on M-14. GREEN / PARTIAL / DISAGREE.

If GREEN, M-14 is locked.

## Output

Write to `outputs/codex_findings/m14_v4_review/findings.md`:

```markdown
# Codex final review of M-14 v4

## Verdict
GREEN / PARTIAL / DISAGREE

## v3 fix
- [x/no] Smart apostrophes normalized before contraction map

## Final word
GREEN to lock M-14 / PARTIAL with edits.
```

Be terse. Under 40 lines.
