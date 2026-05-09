# Codex Diff Review — I-cj-007 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-cj-007 — Delimiter sanitization Crown Jewel test (terminal in CJ track). Brief APPROVE'd iter 2 (Cyrillic homoglyph + decomposed-diacritic teeth added per Codex iter 1 P1).
- **Diff under review:** `.codex/I-cj-007/codex_diff.patch` (canonical-diff-sha256 in trailer).
- **Files changed:**
  - NEW `tests/crown_jewels/test_cj_007_delimiter_sanitization.py` (~80 LOC, 9 tests)
  - MODIFY `docs/crown_jewels.md` (~1-row change)

## Acceptance criteria (from brief APPROVE iter 2)

1. ✅ 9 tests cover clean / ASCII delimiter / end_evidence / invisible-char / fullwidth / Cyrillic homoglyph / decomposed diacritic / multilingual preserved / injection directive.
2. ✅ Registry doc row 7 updated to provenance_generator.py path.
3. ✅ All 9 tests pass locally.
4. ✅ ~80 LOC under 200.

## Red-team checklist

1. **Cross-script homoglyph tooth** — Cyrillic 'е' U+0435 in `<<<еvidence:...>>>` exercises `_CONFUSABLE_ASCII_MAP` independently of the NFKC fullwidth-bracket branch. A regression that drops cross-script confusable mapping breaks this test.
2. **NFKD decomposition tooth** — precomposed 'é' U+00E9 in `<<<énd_evidence>>>` decomposes to base 'e' + Mn combining acute (U+0301), which `_build_normalized_view` strips. A regression that switches NFKD→NFC (no compatibility) breaks this test.
3. **Multilingual byte-preservation tooth** — Cyrillic + Greek + Chinese clean text must not be globally rewritten. The round-3 architectural fix (build VIEW, not rewrite original) is what this pins.
4. **§9.4 hygiene** — clean.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
