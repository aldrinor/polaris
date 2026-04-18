# POLARIS honest-rebuild — Codex review round 4

Round 4 of max 12. You are the independent reviewer. Loop protocol:
`.codex/LOOP_PROTOCOL.md`. Verdict: `READY | NOT_READY | CONDITIONAL`.

## Output

Write findings to `outputs/codex_findings/round_4/findings.md` with
frontmatter:

```yaml
---
verdict: READY | NOT_READY | CONDITIONAL
blocker_count: <int>
medium_count: <int>
rationale: |
  <2-4 sentence justification with file:line>
---
```

## Prior rounds

- Round 1 findings+response: `outputs/codex_findings/round_1/`
- Round 2 findings+response: `outputs/codex_findings/round_2/`
- Round 3 findings+response: `outputs/codex_findings/round_3/`
- Commits:
  - Round 1: `724edf5` — B-1..B-5 initial fixes
  - Round 2: `9493326` — B-1 default=2, B-5 U+2066, homoglyph map
  - Round 3: `3a90b4f` — B-5 architectural rewrite (normalized view)
- Test state after round 3: 292 passed, 0 xfail, 0 fail

## Anti-circle-jerk rules

1. Read code at `3a90b4f`, not my summary.
2. If a fix is cosmetic, re-raise with `severity_reraised: true`.
3. `READY` requires zero blockers + ≤2 mediums with acceptable-risk
   rationale. Any silent failure mode disqualifies `READY`.

## Round 4 specific: verify round-3 architectural fix for B-5

Round 3 replaced the global-string-rewrite approach with a
normalized-view + index-projection approach. The core claim:
`sanitize_evidence_text()` now byte-preserves non-delimiter content
while still redacting delimiter lookalikes.

### Verify the architecture

Read `src/polaris_graph/generator/provenance_generator.py`:
- `_build_normalized_view(text)` around line 164-195 — should return
  `(normalized_str, list[int] orig_idx)`.
- `sanitize_evidence_text(text)` around line 198-260 — should do
  injection-directive redaction on raw text (pass 1), then build
  normalized view, run delimiter regexes on view, project matches
  back to original via `orig_idx`, redact original at those ranges.

Specifically probe:
- Does pass 1 (injection directives) mutate the text that pass 2
  operates on? If yes, do the `orig_idx` indices drift?
- What happens with OVERLAPPING delimiter matches in the normalized
  view? Does the merge-ranges code produce correct output?
- What happens when a delimiter spans a range where the normalized
  view is SHORTER than the original (invisible chars skipped)?
  Does `orig_idx[ne - 1] + 1` compute the correct `orig_end`?
- What happens with NFKC expansion (e.g., a ligature 'ﬁ' at original
  index 5 expands to 'f' + 'i' at normalized indices 10-11)? Does
  `orig_idx[10] == orig_idx[11] == 5` (both point to the same original
  char)?

### Verify coverage

- Build a list of every lowercase Latin letter in the keywords
  {evidence, end, pipeline, telemetry}: {a, c, d, e, i, l, m, n, o,
  p, r, t, v, y}. For each, confirm there's a Cyrillic OR Greek
  entry in `_CONFUSABLE_ASCII_MAP`. Is any missing?
- Does the category-Cf fallback in `_build_normalized_view` handle
  Unicode Cf chars we didn't enumerate? Test with U+00AD soft hyphen
  (known Cf).
- Can you construct a delimiter bypass using:
  - Latin Extended-A/B chars visually similar to ASCII (e.g., 'ĕ'
    U+0115 — Latin 'e' with breve)? Is that considered homoglyph?
  - Mathematical Alphanumeric Symbols U+1D400-U+1D7FF — full-width
    math script 'e' (U+1D486) looks like bold 'e'. NFKC normalizes
    these to ASCII — does our view catch them?

### Verify byte-preservation

Read `tests/polaris_graph/test_b5_delimiter_breakout.py:`
- `test_b5_legit_cyrillic_content_not_harmed` — asserts `out == text`.
- `test_b5_round3_legit_text_with_latin_end_preserved` — exact Codex
  round-3 reproducer.
- `test_b5_legit_math_alpha_preserved` — statistical notation.
- `test_b5_mixed_script_legit_preserved` — ASCII+Cyrillic+Greek mix.

Specifically probe:
- Construct a string where a legitimate Cyrillic word ENDS at the
  exact position where a Latin delimiter keyword would start. Does
  the sanitizer false-positive?
- A long legit Russian sentence (500+ chars) with no delimiters —
  is it byte-identical? Byte-by-byte compare.
- A multi-byte Unicode emoji inside legit text — does the emoji
  survive, or does NFKC expansion mess up the orig_idx map?

## Bonus attack surfaces (if time permits)

1. **Verifier batch behavior**: `verify_sentence_provenance()` when
   called on 1000+ sentences concurrently — any race / shared state?
2. **Tier classifier**: a bioRxiv preprint that has been
   peer-reviewed and subsequently moved to a T1 journal — does the
   classifier still return T4?
3. **Budget imputation edge case**: `_impute_cost_from_tokens()` when
   token counts are negative (corrupted API response)?
4. **Citation numbering across sections**: if two sections both
   cite ev_001, does `resolve_provenance_to_citations()` issue
   `[1]` in both, or `[1]` and `[2]`?

## Scope

Read-only: `src/polaris_graph/`, `scripts/run_honest_sweep_r3.py`,
`tests/polaris_graph/`, `outputs/codex_findings/round_1..3/`.

Writable: `outputs/codex_findings/round_4/` only.

## Authentication

OAuth. No API-key burn.

---

Start:

```
git diff 9493326 3a90b4f -- src/polaris_graph/generator/provenance_generator.py
git diff 9493326 3a90b4f -- tests/polaris_graph/test_b5_delimiter_breakout.py
```

Then probe the architecture. Grant `READY` only if you can't find a
silent-failure input after genuine probing.
