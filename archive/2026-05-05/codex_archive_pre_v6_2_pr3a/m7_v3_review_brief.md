M-7 v3 — final GREEN check.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-7 v2 verdict: STILL-PARTIAL on a single straggler — bracket
left position not upper-clamped. All other fixes correct.

## What changed in v3

Single fix: bracket left/width now clamps BOTH minF and maxF to [0, 1]:

```js
const clampedMin = Math.max(0, Math.min(minF, 1));
const clampedMax = Math.max(clampedMin, Math.min(maxF, 1));
const bracketLeft = (clampedMin * 100).toFixed(2) + "%";
const bracketWidth = ((clampedMax - clampedMin) * 100).toFixed(2) + "%";
```

Test added: `test_band_bracket_position_clamps_min_and_max`.

Tests: 173 → 174.

## Your job

Final GREEN check. Verdict: GREEN / STILL-PARTIAL / DISAGREE.

If GREEN, Phase A is complete: all 5 Evidence Inspector views
(M-3..M-7) are jointly aligned and ready for the Phase A demo.

## Output

Write to `outputs/codex_findings/m7_v3_review/findings.md`:

```markdown
# Codex final review of M-7 v3

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Bracket clamp verification
- [x/no] minF and maxF both clamped to [0, 1]

## Phase A completion
Are all 5 views jointly GREEN-locked?

## Final word
GREEN to lock M-7 + Phase A complete / STILL-PARTIAL with edits.
```

Be terse. Under 60 lines.
