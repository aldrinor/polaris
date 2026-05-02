M-14 v3 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-14 v2 verdict: PARTIAL with 3 issues:
1. Contraction-style negation ("isn't approved") false-converged
   because tokenizer split the apostrophe into fragments before
   negation guard saw "not".
2. Flattening scrubber was exact-substring; "approved worldwide",
   "approved globally", "internationally approved", "consensus
   across jurisdictions", "unanimously approved" all bypassed.
3. Numeric guard treated "1,000 mg" vs "1000 mg" as divergence
   because the regex saw {"1","000"} vs {"1000"}.

All 3 integrated in v3 (commit a6cf3d4).

## What changed in v3

`_expand_contractions(text)`:
- Runs BEFORE `_tokens()`. 31 English contractions normalized to
  expanded form (isn't → is not, cant → can not, won't → will
  not, etc.). Both apostrophe and apostrophe-less forms covered.
- Word-boundary regex respects `\b` for non-apostrophe forms;
  apostrophe-aware match for "'t" suffixes.

`_NEGATION_TOKENS` extended:
- Added "refused", "revoked", "negative" (refusal verbs that flip
  meaning without containing "not").

`_FLATTENING_TRIGGERS` rewritten as 14 trigger words/phrases
matched via regex `\b(?:t1|t2|...)\b` with re.IGNORECASE:
- worldwide, globally, internationally, international consensus,
  global consensus, consensus across jurisdictions, unanimous,
  unanimously, all regulators, all jurisdictions, every
  jurisdiction, every regulator, regulators worldwide, regulators
  globally.
- Both adjective ("unanimous") and adverb ("unanimously") forms
  listed because `\b` requires explicit inflection coverage.

`_NUMERIC_RE` extended:
- New pattern: `\b\d{1,3}(?:,\d{3})+(?:\.\d+)?\b|\b\d+(?:\.\d+)?\b`
- Captures thousands-separator-style numbers like "1,000".
- `_extract_numeric_tokens` strips commas so "1,000" and "1000"
  canonicalize to the same token.

Tests: 18 new.
- 8 contraction parametrized cases (isn't, aren't, can't, won't,
  doesn't, didn't, isnt, cannot).
- 8 flattening variant parametrized cases (approved worldwide,
  approved globally, internationally approved, consensus across
  jurisdictions, global consensus, unanimously approved, every
  jurisdiction, every regulator).
- Thousands-separator parity ("1,000 mg" vs "1000 mg" →
  convergence).
- Thousands-separator real mismatch ("1,000 mg" vs "2,000 mg" →
  divergence — sanity).

M-14 module 34 → 52 green.

## Your job

Final verdict on M-14. GREEN / PARTIAL / DISAGREE.

If GREEN, M-14 is locked and Phase C proceeds to M-15a.

## Output

Write to `outputs/codex_findings/m14_v3_review/findings.md`:

```markdown
# Codex final review of M-14 v3

## Verdict
GREEN / PARTIAL / DISAGREE

## v2 fix integration
- [x/no] Contraction expansion before tokenization
- [x/no] Flattening regex catches morphological variants
- [x/no] Thousands-separator numeric parity

## Final word
GREEN to lock M-14 + proceed to M-15a / PARTIAL with edits.
```

Be terse. Under 80 lines.
