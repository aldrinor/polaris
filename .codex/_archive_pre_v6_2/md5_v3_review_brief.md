M-D5 phase 1 v3 review (commit 0e861a5).

**Skip git status.** Codex at gpt-5.4 + xhigh.

**Pytest**: `python -m pytest -q tests\polaris_graph\test_md5_scope_classifier.py`

## Context

R1 = GREEN with 2 LOW. v2 closed both.
R2 = PARTIAL — found Unicode Cf bypass: `"​"`,
`"﻿"`, etc. bypass `str.strip()` and reach the classifier.

v3 closes the bypass.

## What changed in v3

`src/polaris_graph/audit_ir/scope_classifier.py`:

1. New `_is_visually_empty(text)` function iterating char-by-char.
   Treats a string as empty when every char is one of:
     - `isspace()` True
     - `unicodedata.category(c) in ("Cf", "Cc", "Cn", "Co")`
   Cf = Format (ZWSP, ZWNJ, ZWJ, word joiner, BOM)
   Cc = Control codes
   Cn = Unassigned
   Co = Private Use

2. Empty-query short-circuit in `confidence_gated_match` now uses
   `_is_visually_empty(question)` instead of
   `not question or not question.strip()`.

`tests/polaris_graph/test_md5_scope_classifier.py` (29 passing):
  - test_unicode_format_character_query_short_circuits — 7
    inputs with Cf chars (zero-width space, ZWNJ, ZWJ, word
    joiner, BOM, mixed with whitespace) all bypass classifier.
  - test_visible_unicode_query_does_not_short_circuit —
    Japanese, accented Latin, Greek, em-dash, ティルゼパチド
    all reach the classifier.

`docs/md5_phase1_threat_model.md` boundary 7: updated with the
v3 details + curate list of categories.

## Your job

GREEN-LOCK or PARTIAL.

1. **Round-2 fix integration**:
   - [ ] Cf bypass closed (zero-width space query short-circuits)
   - [ ] visible Unicode (Japanese, accented Latin) NOT
     short-circuited
   - [ ] threat-model boundary 7 v3 wording matches code

2. **Stop criterion**: GREEN-lock if remaining findings are
   doc nits or follow-ups. PARTIAL only if you find:
     (a) Another bypass class not covered (e.g. Lo characters
         that render as nothing, surrogate halves, etc.)
     (b) `_is_visually_empty` over-strips legitimate content
         (false positive on real-content queries)
     (c) Test coverage hole

3. **Phase-2 readiness**: same as round 1.

## Output

`outputs/codex_findings/md5_v3_review/findings.md`:

```markdown
# Codex round 3 — M-D5 phase 1 v3 (commit 0e861a5)

## Verdict
GREEN

## Round-2 fix integration
- [x/no] Cf bypass closed
- [x/no] visible Unicode preserved
- [x/no] threat-model boundary 7 matches code

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D5 phase 1.
```

Be terse. Under 30 lines.
