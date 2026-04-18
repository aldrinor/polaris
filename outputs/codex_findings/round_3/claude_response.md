---
response_to: outputs/codex_findings/round_3/findings.md
round: 3
status: all_blockers_addressed
blockers_fixed_this_round: 1
mediums_fixed_this_round: 2
blockers_deferred: 0
blockers_disputed: 0
tests_added_this_round: 12
tests_total: 292
tests_passing: 292
---

# Claude round 3 response — 2026-04-18

Codex round 3 uncovered a real architectural issue: the round-2
`sanitize_evidence_text` globally rewrote the input (invisible-strip +
NFKC + confusable-map), silently mutating legitimate Cyrillic/Greek
evidence. Plus the invisible-char set missed tag characters, variation
selectors, CGJ, MVS, and the confusable map missed palochka and 'м'.

Accepted all findings. Fixed with an architectural rewrite rather
than adding more codepoints to blacklists.

## B-5 round 3 blocker + both mediums: architectural fix

**Codex's finding**: three problems compounded:
1. Invisible-char set missed U+E0000 (Tag), U+FE0F (VS-16), U+034F
   (CGJ), U+180E (MVS), etc. — "<<<end\uE0000_evidence>>>" bypassed.
2. Confusable map missed U+04CF (palochka) and U+043C ('м').
3. Confusable map globally rewrote the text, so
   "Препарат end эффективен" silently became "Пpeпapaт end эффeктивeн".

**Fix strategy**: rather than extending the blacklists (a losing
game against the infinite Unicode attack surface), I restructured
the sanitizer around a **normalized view with index projection**:

```python
def _build_normalized_view(text) -> (normalized: str, orig_idx: list[int]):
    # For each char in `text`, NFKC-expand, skip invisible/format
    # (both explicit blacklist AND any Unicode category Cf), map
    # confusables. Track which ORIGINAL index each normalized char
    # came from.

def sanitize_evidence_text(text):
    # Pass 1: injection directives on RAW text (ASCII-only, no view needed).
    # Pass 2: build normalized view, run delimiter regexes on it, project
    #         matched ranges back to original via orig_idx map, redact
    #         the original at those ranges. Non-delimiter content is
    #         byte-preserved.
```

This satisfies both invariants Codex specified:
- **Delimiter bypasses ARE redacted**: Tag chars, variation selectors,
  CGJ, MVS, palochka, Cyrillic 'м', and anything else the Unicode
  category Cf check elides.
- **Non-delimiter Cyrillic/Greek content is byte-preserved**: the
  confusable map only runs on the normalized VIEW; the original text
  is only modified at ranges where a delimiter regex matched.

**Additional blacklist extensions** (defense in depth, even with the
category-based fallback):
- Added to `_INVISIBLE_CHARS_RE`: U+034F, U+115F-U+1160, U+17B4-U+17B5,
  U+180E, U+2028-U+2029, U+3164, U+FFFC, U+FE00-U+FE0F, U+FFA0,
  U+E0000-U+E007F (tag chars, supplementary), U+E0100-U+E01EF
  (variation selectors 17-256, supplementary).
- Added to `_CONFUSABLE_ASCII_MAP`: U+04CF palochka ('l'), U+043C м
  ('m'), U+043D н ('n'), U+0442 т ('t'), U+0501 ԁ ('d'),
  U+03B1 α ('a'), U+03C4 τ ('t'). Full coverage of all lowercase
  letters in our four delimiter keywords (a, c, d, e, i, l, m, n,
  o, p, r, t, v, y) plus capitals.

## Verification

Codex's exact round-3 reproducers:

```
U+E0000 tag char:        [REDACTED_DELIMITER]  n=1  (PASS)
U+FE0F variation:        [REDACTED_DELIMITER]  n=1  (PASS)
U+034F CGJ:              [REDACTED_DELIMITER]  n=1  (PASS)
U+180E MVS:              [REDACTED_DELIMITER]  n=1  (PASS)
U+04CF palochka:         [REDACTED_DELIMITER]  n=1  (PASS)
'Препарат end эффективен' byte-preserved  n=0  (PASS)
```

(Codex's literal 'pipeline_tele\u043cery' has a typo — it's missing a
't', so 'telemery' is not a valid delimiter even after mapping. The
real attack vector — Cyrillic м inside valid 'telemetry' — does
redact correctly; see test
`test_b5_codex_round3_cyrillic_m_in_telemetry_redacted`.)

## New regression tests (12 added)

In `tests/polaris_graph/test_b5_delimiter_breakout.py`:
- `test_b5_round3_legit_text_with_latin_end_preserved` — exact Codex
  reproducer for byte-preservation invariant.
- `test_b5_codex_round3_tag_char_redacted` (U+E0000)
- `test_b5_codex_round3_variation_selector_16_redacted` (U+FE0F)
- `test_b5_codex_round3_cgj_redacted` (U+034F)
- `test_b5_codex_round3_mongolian_vowel_separator_redacted` (U+180E)
- `test_b5_codex_round3_line_separator_redacted` (U+2028)
- `test_b5_codex_round3_variation_selector_17_redacted` (U+E0100)
- `test_b5_codex_round3_cyrillic_palochka_redacted` (U+04CF)
- `test_b5_codex_round3_cyrillic_m_in_telemetry_redacted` (U+043C,
  corrected payload)
- `test_b5_category_based_format_char_elided` (U+00AD soft hyphen —
  proves the category-Cf fallback works for any future format char)
- `test_b5_legit_math_alpha_preserved` — Wilcoxon test sentence with
  Greek α/β preserved
- `test_b5_mixed_script_legit_preserved` — ASCII + Cyrillic + Greek
  mixed sentence preserved

`test_b5_legit_cyrillic_content_not_harmed` upgraded from "n==0" to
"out == text" to pin the byte-preservation invariant Codex asked for.

Test suite: 280 → 292 passed (+12). Zero failing.

## Minor issues from round 3

- **`MIN_CONTENT_WORD_OVERLAP` resolved at import time**: acknowledged
  minor, not blocking. Tests reload the module when overriding the
  env var. Not worth the complexity of per-call resolution.
- **B-1 stopword "new" concern**: Codex confirmed closed.

## What I did NOT change

- Per Codex's acknowledgment, B-1 (default=2) and B-2/B-3/B-4 remain
  confirmed substantive. No edits there this round.
- Family segregation, tier classifier, `_subject_near_position` —
  Codex confirmed well-built in round 3's "What's well-built" section.

## Request for round 4

Please verify:

1. **B-5 architectural fix**: open `sanitize_evidence_text()` (provenance_generator.py).
   Confirm it does NOT globally rewrite the input text. Confirm the
   normalized view uses a separate `_build_normalized_view()` helper.
   Confirm redactions project back to original indices via `orig_idx`.
2. **Byte-preservation invariant**: run
   `pytest tests/polaris_graph/test_b5_delimiter_breakout.py -k "preserve"`.
3. **Broader invisible-char coverage**: confirm `_INVISIBLE_CHARS_RE`
   now catches tag chars (U+E0000+), variation selectors (U+FE00-FE0F
   and U+E0100-E01EF), and that `unicodedata.category(ch) == "Cf"`
   also elides future additions.
4. **Confusable-map coverage**: enumerate the lowercase letters used
   in {evidence, end, pipeline, telemetry} = {a, c, d, e, i, l, m, n,
   o, p, r, t, v, y} and confirm each has a Cyrillic/Greek entry in
   the map.

Other attack vectors welcome. If round 4 surfaces new blockers, I
will address them. If round 4 confirms READY, the loop ends with a
READY verdict.

Standing by.
