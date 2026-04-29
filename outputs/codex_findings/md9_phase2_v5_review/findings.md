# Codex round 4 — M-D9 phase 2 v5 (commit 56b0a44)

## Verdict
PARTIAL

## Round-3 fix integration
- [x] whitespace-only stripped (verified — `"   "`, `"\t\n"` now treated as missing)
- [x] invisible-unicode rejected (Cf/Cc/Cn/Co/Cs)

## New findings
- [LOW] `_is_visually_empty_text` (`src/polaris_graph/audit_ir/beat_both_scoring.py:207`)
  is incomplete on the same `_is_frame_field_populated` boundary. Helper skips
  `isspace()` plus `Cf/Cc/Cn/Co/Cs` only at line 220, so invisible **Mn**
  (Mark Nonspacing) code points still count as populated. Verified that
  U+034F COMBINING GRAPHEME JOINER, U+FE0F VARIATION SELECTOR-16, and
  U+180B MONGOLIAN FREE VARIATION SELECTOR ONE all return not-empty,
  and a claim with `ci="͏"` still scores complete (`claim_frames == 1.0`).
  The new test at `tests/.../test_md9_phase2_beat_both.py:757` covers Cf
  examples only, so 52/52 passing does not close this remaining same-predicate
  leak.

  Assumption: standalone CGJ / variation selectors / Mongolian free variation
  selectors should be treated as non-content because they have no standalone
  visible rendering. If the intended boundary is narrower than "visually
  empty," the helper and docstring should say that explicitly.

  Verified separately: the round-3 whitespace finding is closed. `"   "` and
  `"\t\n"` are now treated as missing, and `python -m pytest -q
  tests\polaris_graph\test_md9_phase2_beat_both.py` passed all 52 tests on
  56b0a44.

## Final word
PARTIAL — same-predicate Unicode-emptiness convergence is not done yet;
do not lock the boundary.

## Audit-trail note
Round 4 ran twice:
1. First Codex session (019dd74b) hit Windows sandbox cutoff
   (CreateProcessWithLogonW failed: 267) mid-investigation.
2. A verdict-only follow-up brief (019dd74d) was launched against
   the diff alone (without re-reading files). It returned GREEN
   based on the diff text — but that brief did NOT have access to
   probe the specific Mn-bypass case Codex's full-investigation
   round eventually identified.
3. The actual full-investigation round (overwrote findings.md
   after the verdict-capture brief) returned PARTIAL with the
   above Mn finding.

Lesson: verdict-only briefs can miss findings that require
empirical probing. Use them only as a back-pocket fallback for
cutoff scenarios; if a full review eventually completes,
trust its findings over the verdict-capture brief's.
