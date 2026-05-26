# Codex iter 3 — Step 1 diff review (iter-2 continuing P1 #2 fix)

## §8.3.1 canonical cap directive (verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
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

## What changed since iter 2

You returned `REQUEST_CHANGES` with one continuing P1: the range-dash
regex required a digit IMMEDIATELY left of the dash, so `8.12 –8.21`
(whitespace before dash) still produced fake negative `-8.21`. You
even ran `verify_sentence_provenance` live and showed it was passing
a sentence claiming `-8.21` against a positive-range evidence.

**Status: FIXED.**

### The fix (provenance_generator.py:488-496)

Adopted essentially your suggested regex form, slightly tightened:

```python
_RANGE_DASH_BETWEEN_DIGITS = _re_normalize.compile(
    r"(?<=\d)(\s*[–—‒]\s*)(?=[−\-]?\d)"
)
```

- Lookbehind: digit on the LEFT (anywhere, requiring a numeric token to
  the immediate-or-near left).
- Match: optional whitespace + en/em/figure dash + optional whitespace.
- Lookahead: optional minus (ASCII `-` OR U+2212) then digit on the
  RIGHT. The lookahead covers ranges of negatives like `−7.5–−12.9`
  where the dash sits between a digit and a U+2212 minus.
- Replacement: a single space — eliminates the dash entirely without
  preserving stray whitespace that could confuse downstream regexes.

### Reproduced your exact failing test

```
NORMALIZED: 'HbA1c 95% CI was 8.12 8.21 percent at week 12 in patients.'
DECIMALS: ['8.12', '8.21']
IS_VERIFIED: False  REASONS: ["number_not_in_any_cited_span:ev1:missing=['-8.21']"]
```

The sentence claiming `-8.21` is now correctly DROPPED because the
evidence has only positive `8.21` after normalization.

## Adversarial test suite (run locally, all 21 assertions pass)

`scripts/test_i_gen_005_iter2_adversarial.py` — 21 assertions across
5 test groups. **Run yourself**:

```
PYTHONIOENCODING=utf-8 python scripts/test_i_gen_005_iter2_adversarial.py
```

### Iter 3 new test cases (whitespace variants)

- `'8.12 –8.21'` (left-ws only) → `'8.12  8.21'`, decimals `{8.12, 8.21}` ✓
- `'8.12 — 8.21'` (both-ws em-dash) → `'8.12  8.21'`, decimals `{8.12, 8.21}` ✓
- `'8.12– 8.21'` (right-ws only) → `'8.12  8.21'`, decimals `{8.12, 8.21}` ✓
- `'−7.5–−12.9'` (range of negatives) → `'-7.5 -12.9'`, decimals `{-7.5, -12.9}` ✓
- `'—Tirzepatide 15 mg—'` (narrative em-dash) → `'-Tirzepatide 15 mg-'` ✓
- Codex's exact failing string: `'HbA1c 95% CI was 8.12 –8.21 percent at week 12 in patients.'` → decimals `{8.12, 8.21}` ✓

All iter-2 P1 #1 (token-exact), P1 #3 (localized entailment), and
P2 (cluster placement) tests still pass — no regressions.

## P2 cluster placement (your iter 2 P2)

You flagged that the cluster-based placement still doesn't enumerate
all valid clusters and noted it's "P2/recall, not a smoke blocker."

**I have NOT changed cluster code in iter 3.** Rationale: per your
own iter-2 advice, this is recall, not safety. Bumping recall before
measuring smoke is premature — the smoke gives me the actual
distribution of which sentences need cluster-shape help. I'll capture
this as a follow-up Issue (or a Step-2 task) regardless of iter-3
verdict.

## min_content_overlap_recommendation

You said KEEP_2. Implementation kept at 2. Confirmed.

## Questions for you

1. Does the iter-3 regex `(?<=\d)(\s*[–—‒]\s*)(?=[−\-]?\d)` fully
   close P1 #2, or is there another whitespace shape I'm missing?
2. Approval to run the smoke test now (Step 1 P1 fixes complete)?
3. Any NEW findings in the iter-3 diff (`.codex/I-gen-005/codex_diff_iter3.patch`, 447 lines)?

## Files for you to read

1. `src/polaris_graph/generator/provenance_generator.py:487-528`
   (new range-dash regex + `_normalize_unicode_minus`)
2. `scripts/test_i_gen_005_iter2_adversarial.py:131-217` (iter 3 tests)
3. `.codex/I-gen-005/codex_diff_iter3.patch` (full diff)

## Output schema (verbatim, do not omit fields)

```yaml
verdict: APPROVE | REQUEST_CHANGES
diagnosis_alignment: TRUE | FALSE | PARTIAL
p0_or_p1_findings_on_iter3:
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

EMIT YAML ONLY. Operator directive: "Pls keep this iteration until
Codex approve." Push back hard if there are real blockers; don't
manufacture findings to extend the cycle.
