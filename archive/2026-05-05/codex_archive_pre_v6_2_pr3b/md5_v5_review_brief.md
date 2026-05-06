# Codex review — M-D5 phase 1 v5 (commit a39a024)

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md5_scope_classifier.py`
- Skip `outputs/codex_*` and `.codex_tmp/` in `rg`
- DO NOT run Python verification scripts that print Unicode —
  the Windows sandbox uses cp1252 and chokes on chars like
  U+034F. Read the diff and tests directly.

## Scope
M-D5 phase 1 was locked at v4 (commit 13a4c21) with
`_is_visually_empty` skipping only Cf/Cc/Cn/Co/Cs.

M-D9 phase 2 v7 (commit f96af56) just asymptote-stopped on
the SAME predicate after Codex round-5 found that:
  - Mn/Mc/Me (combining marks) bypassed v6
  - Hangul fillers U+115F/U+1160/U+3164/U+FFA0 (Lo) bypassed v6+

M-D9 phase 2 v7 documented the boundary: skip set
`{isspace()} ∪ {Cf,Cc,Cn,Co,Cs,Mn,Mc,Me} ∪ {U+115F,U+1160,U+3164,U+FFA0}`
exhaustively covers Unicode Default_Ignorable_Code_Point per
UCD DerivedCoreProperties.

v5 of M-D5 phase 1 applies the same extension to
`scope_classifier._is_visually_empty` to align.

## What to verify

**Diff scope** (commit a39a024):
- `src/polaris_graph/audit_ir/scope_classifier.py` — added
  `_VISUALLY_EMPTY_CODEPOINTS = frozenset({U+115F, U+1160,
  U+3164, U+FFA0})` and extended skip set in
  `_is_visually_empty`. Docstring updated to reference v7
  boundary.
- `tests/polaris_graph/test_md5_scope_classifier.py` — added
  `test_combining_marks_and_hangul_fillers_short_circuit` (10
  visually-empty inputs cover all 8 categories + mixed) and
  `test_combining_marks_with_base_char_do_not_short_circuit`
  (4 base+combining inputs that MUST reach the classifier).
- `docs/md5_phase1_threat_model.md` v4→v5 with cross-reference
  to M-D9 phase 2 v7 boundary.

**Tests pass locally**: 32/32 (was 30, +2).

## Verdict checklist (no Python execution required)

- [Y/N] Skip set in v5 matches the M-D9 phase 2 v7 boundary
  (Cf/Cc/Cn/Co/Cs + Mn/Mc/Me + 4 Hangul fillers)?
- [Y/N] Non-regression on base+combining sequences (`"a̧"`,
  `"한"`, etc.) — loop exits on first non-skip char?
- [Y/N] Any divergence from M-D9 phase 2 v7's pattern that
  could create asymmetric behavior across milestones?
- [Y/N] Any finding on a DIFFERENT predicate within
  scope_classifier.py (`_read_threshold_from_env`, the gate
  decision logic, RoutingResult contract)?

## Output format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Alignment with M-D9 phase 2 v7
- [x/ ] Skip set matches
- [x/ ] Non-regression preserved

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
