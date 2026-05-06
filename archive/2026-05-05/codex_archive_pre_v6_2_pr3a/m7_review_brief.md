M-7 Evidence Inspector View 5 (Source Tier Mix) — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-1..M-6 GREEN-locked. Now M-7: View 5 (Source Tier Mix), the LAST
view in Phase A. Visualizes corpus tier distribution + expected-vs-
actual diagnostic + promotional-adjective calibration badge.

## What landed

Files:
- `scripts/static/inspector/inspector.js` (+~190 lines):
  renderTierMixView + countPromoAdjectives + renderTierBandRow +
  renderTierResidualRow + 15 promo-pattern regexes
- `scripts/static/inspector/inspector.css` (+~180 lines): tier-headline,
  tier-mix-bar-large, tier-mix-table, tier-mix-band-graphic,
  tier-mix-band-bracket, tier-mix-band-actual,
  tier-mix-promo-badge, tier-mix-row-residual, tier-mix-deviation-warning

Visual:
- 4 headline cards: corpus size, dominant tier, T1 share, promo
  adjective count + calibration badge
- Material-deviation banner if manifest.corpus.material_deviation=true
- Large tier bar (T1..T7+UNKNOWN, segments labeled inline if >= 5%)
- Expected-vs-actual band table with band-graphic visualization
  (bracket showing min..max, marker showing where actual falls)
- Residual rows for unexpected tiers

Promo-adjective calibration: 15 patterns scanned against report.md.
- 0-4 → well-calibrated (green)
- 5-14 → elevated (yellow)
- 15+ → promotional drift (red)
Run-14: 1 promo (well-calibrated) — matches FINAL_PLAN's claim of
1 vs Gemini's 58.

Tests: 155 → 166 (7 router + 4 browser).

## Your job

Code review for M-7. Verdict: GREEN / PARTIAL / DISAGREE.

Specifically:

1. **FINAL_PLAN compliance.** "Source Tier Mix": visual T1/T2/T3 bar
   at report header (already in M-2 strip), per-section tier
   breakdown, promo-adjective count badge. Does the view deliver
   all of these?

2. **Promo-adjective patterns.** 15 patterns (revolutionary,
   groundbreaking, unprecedented, breakthrough, world-class, etc.)
   on the canonical FINAL_PLAN.md V30 calibration list. Run-14 has
   1 hit; Gemini DR has 58. Are there obvious patterns I'm missing
   that V30 cares about? Or false positives I should worry about?

3. **Band-graphic correctness.** Each tier band renders min..max
   as a bracket overlay on a 0-100% axis, with the actual fraction
   as a 2px marker. Edge cases:
   - actual=0 → marker at left edge (correct?)
   - actual=1 → marker at right edge
   - actual outside 0..1 → clamped to 0..1 via Math.min/max
   - max_fraction == null falls through to 1, min_fraction == null to 0

4. **Per-section breakdown.** FINAL_PLAN says "Per-section tier
   breakdown". The current IR doesn't have per-section tier
   fractions — corpus is whole-corpus. Should I derive per-section
   stats from frame_coverage entries (one entry per slot, with
   section + provenance_class), or is this a Phase B add?

5. **Material-deviation banner.** Run-14 has
   material_deviation=true. Banner shows. Correct? Or should this
   be a more prominent action call (e.g., "review corpus_approval")?

6. **Residual tier handling.** UNKNOWN tier with 2.3% in run-14
   should appear as a residual row (UNKNOWN is not in the protocol's
   expected_tier_distribution). Verify.

7. **Test coverage.** 7 router + 4 browser. Anything important
   not covered?

8. **Anything else.**

## Output

Write to `outputs/codex_findings/m7_review/findings.md`:

```markdown
# Codex review of M-7

## Verdict
GREEN / PARTIAL / DISAGREE

## FINAL_PLAN compliance
What's covered / missing.

## Specific issues
File:line bugs.

## Recommended changes
If PARTIAL.

## Phase A completion
Are all 5 views jointly aligned and ready for Phase A demo?

## Final word
GREEN to lock M-7 / PARTIAL with edits.
```

Be terse. Under 300 lines.
