# Codex iter 4 — Step 1 diff review (iter-3 continuing P1 #2 fix)

## §8.3.1 canonical cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 4 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker,
  classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by
  Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" —
  DON'T. Surface it now. The 5-cap means iter 6 doesn't exist;
  banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**Reminder: this is iter 4 of 5.** If iter 5 returns REQUEST_CHANGES on
P1 #2 again, the document is force-APPROVE'd per cap directive. Please
surface ALL remaining concerns now if there are any.

## What changed since iter 3

You returned `REQUEST_CHANGES` with one P1: `\s*` was too broad and
also missed zero-width separators. Your reproducer:

```
_normalize_unicode_minus("HbA1c at week 12\n–8.21 percent in patients.")
  -> "HbA1c at week 12 8.21 percent in patients."  # WRONG, real negative lost
```

You suggested replacing `\s*` with an explicit inline-gap class that
excludes line boundaries and includes zero-width separators. **I have
adopted essentially your proposed fix.**

## The fix (provenance_generator.py:487-521)

```python
_INLINE_RANGE_GAP = (
    # Codex iter-3 fix: bound to INLINE spacing only.
    # Horizontal whitespace (tab, space, NBSP, OGHAM SPACE, quad spaces
    # U+2000..U+200A, narrow no-break, medium math, ideographic space):
    r"[\t    -   　"
    # Zero-width format separators (U+200B..U+200F, U+2060..U+2064,
    # U+2066..U+2069, U+FEFF) that PDF/browser extraction inserts
    # between digit and dash; not matched by Python re \s.
    r"​-‏⁠-⁤⁦-⁩﻿"
    # Variation selectors 1-16 (BMP, U+FE00..U+FE0F):
    r"︀-️"
    r"]"
    # Supplementary-plane tag chars (U+E0000..U+E007F) and supplementary
    # variation selectors (U+E0100..U+E01EF) via alternation:
    r"|[\U000e0000-\U000e007f\U000e0100-\U000e01ef]"
)
_RANGE_DASH_BETWEEN_DIGITS = _re_normalize.compile(
    rf"(?<=\d)((?:{_INLINE_RANGE_GAP})*[–—‒]"
    rf"(?:{_INLINE_RANGE_GAP})*)(?=[−\-]?\d)"
)
```

Key properties:
- **Newlines/paragraph/line separators EXCLUDED** — `\n`, `\r`, `\v`,
  `\f`, U+2028 LINE SEP, U+2029 PARA SEP are NOT in the class, so the
  regex cannot bridge a previous-line digit to a next-line negative.
- **Zero-width separators INCLUDED** — U+200B..U+200F, U+2060..U+2064,
  U+2066..U+2069, U+FEFF, U+FE00..U+FE0F, U+E0000..U+E007F,
  U+E0100..U+E01EF. PDF extraction inserts these and `\s` misses them.
- **NBSP / em-quad / etc. INCLUDED** — clinical tables commonly use
  these instead of plain space.

## Adversarial test suite — 30+ assertions all PASS

`scripts/test_i_gen_005_iter2_adversarial.py` now covers:

### Iter 4 new tests (Codex iter-3 specific reproducers)

- `"HbA1c at week 12\n–8.21 percent in patients."` → decimals `{'-8.21'}` (negative PRESERVED) ✓
- `"HbA1c 8.12​–8.21 percent."` (ZWSP) → decimals `{'8.12', '8.21'}` ✓
- `"HbA1c 8.12  –8.21 percent."` (PARA SEP) → decimals include `-8.21` (NOT bridged) ✓
- `"HbA1c 8.12  –8.21 percent."` (LINE SEP) → decimals include `-8.21` (NOT bridged) ✓
- `"HbA1c 8.12\v–8.21 percent."` (VT) → decimals include `-8.21` ✓
- `"HbA1c 8.12\f–8.21 percent."` (FF) → decimals include `-8.21` ✓
- `"HbA1c 8.12 – 8.21 percent."` (NBSP) → decimals `{'8.12', '8.21'}` ✓

### Iter 3 tests still pass (no regression)

- `'8.12 –8.21'` → `{'8.12', '8.21'}` ✓
- `'8.12 — 8.21'` → `{'8.12', '8.21'}` ✓
- `'8.12– 8.21'` → `{'8.12', '8.21'}` ✓
- `'−7.5–−12.9'` → `{'-7.5', '-12.9'}` ✓
- `'8.12–8.21'` → `{'8.12', '8.21'}` ✓
- `'−1.44%'` → `{'-1.44'}` ✓ (real negative preserved)

### Iter 2 tests still pass

- TEST 1 (4 assertions): token-exact matching
- TEST 3: cancer-50% adversarial via full verifier (drops via content_word_overlap)
- TEST 4 (2 assertions): SURPASS grounded sentence (no regression)
- TEST 5: cluster placement

**Run yourself**:

```
PYTHONIOENCODING=utf-8 python scripts/test_i_gen_005_iter2_adversarial.py
```

### Direct repro of your iter-3 failing case

```
$ python -c "
from src.polaris_graph.generator.provenance_generator import _normalize_unicode_minus, _decimals_in, verify_sentence_provenance
s = 'HbA1c at week 12\n–8.21 percent in patients.'
print(repr(_normalize_unicode_minus(s)))
print(sorted(_decimals_in(s)))
sentence = f'HbA1c at week 12 was 8.21 percent in patients [#ev:ev1:0-{len(s)}].'
sv = verify_sentence_provenance(sentence, {'ev1': {'direct_quote': s, 'statement': 'HbA1c table'}})
print(len(s), sv.is_verified, sv.failure_reasons)
"
'HbA1c at week 12\n-8.21 percent in patients.'
['-8.21']
43 False ["number_not_in_any_cited_span:ev1:missing=['8.21']"]
```

The negative `-8.21` is now preserved, and the sentence claiming
positive `8.21` is correctly DROPPED via `number_not_in_any_cited_span`.

## P2 cluster placement

Your iter-3 P2: cluster placement still doesn't enumerate all valid
clusters per non-rarest token. **I have NOT touched cluster code in
iter 4.** Same reasoning as iter 3: P2/recall, not a smoke blocker.

If you flag this as continuing P1 in iter 4, I'll bump to actual
enumeration. Otherwise it goes as a follow-up Issue.

## Questions for you

1. Does the iter-4 inline-gap class fully close P1 #2 for every
   line/whitespace shape?
2. Are there OTHER zero-width / format-separator codepoints I'm
   missing that PDF/browser extraction emits?
3. Approval to run the smoke test now?
4. Any NEW findings in the iter-4 diff
   (`.codex/I-gen-005/codex_diff_iter4.patch`, 473 lines)?

## Files for you to read

1. `src/polaris_graph/generator/provenance_generator.py:487-521`
   (new `_INLINE_RANGE_GAP` + `_RANGE_DASH_BETWEEN_DIGITS`)
2. `scripts/test_i_gen_005_iter2_adversarial.py` (full test suite)
3. `.codex/I-gen-005/codex_diff_iter4.patch` (full diff)

## Output schema (verbatim, do not omit fields)

```yaml
verdict: APPROVE | REQUEST_CHANGES
diagnosis_alignment: TRUE | FALSE | PARTIAL
p0_or_p1_findings_on_iter4:
  - severity: P0 | P1
    location: <file:line>
    issue: |
      (specific bug or risk; quote code if applicable)
    proposed_fix: |
      (specific fix)
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
approval_to_run_smoke: YES | NO
if_no: |
  (must-fix items before smoke)
if_yes: ""
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

EMIT YAML ONLY. Push back hard if there are real blockers. If iter 5
will still find another whitespace variant, please surface that
specific codepoint NOW so it can be added in iter 5, not banked.
