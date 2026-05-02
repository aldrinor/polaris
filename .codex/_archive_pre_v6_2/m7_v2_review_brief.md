M-7 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-7 v1 verdict: PARTIAL with 4 issues. All 4 integrated in v2.

## What changed

1. **Promo lexicon recalibrated** (15 → 35 patterns) + table+biblio
   stripping before scanning:
   - Run-14: exactly 1 hit ("superior" in narrative prose; the
     "superior" in the Trial Summary table row is excluded)
   - Gemini comparator: 54 hits (matches FINAL_PLAN's "1 vs 58"
     story within tolerance)
   - Added: massive, definitive(ly), decisive(ly), astonishing,
     gold-standard, landmark, dramatically, paradigm, transformative,
     robust, impressive(ly), etc.
   - Excluded: "significant" / "most" (legitimate clinical hedges)

2. **Per-section tier breakdown** — FINAL_PLAN-required, missing in v1.
   Derived from verified-sentence tokens.evidence_id → bibliography.tier.
   NOT from frame_coverage.provenance_class (would misrepresent mix).
   Rendered as a separate table after the band-comparison table.

3. **Band-marker clamping** (`_bandMarkerLeftPct`):
   - actual=0 → 0%, actual=1 → 99.5% (capped, marker stays inside)
   - actual outside [0,1] → clamped
   - bracket min/max also clamped

4. **Tests strengthened** to behavior-level:
   - Run-14 promo == 1 (exact, via Node + report.md read)
   - Gemini >= 50 (against state/compare_gemini_dr.txt)
   - Band marker edge cases (5 inputs)
   - Strip-tables-and-biblio
   - UNKNOWN residual row in DOM
   - Per-section breakdown in DOM
   - Headline card promo value == "1"

Tests: 166 → 173.

## Your job

Final verdict on M-7. GREEN / STILL-PARTIAL / DISAGREE.

Spot-check:
- All 4 fixes integrated?
- Promo calibration matches the FINAL_PLAN story?
- Per-section breakdown derivation method acceptable?
- Marker clamping correct for the edge cases?
- M-7 view ready for Phase A demo?

## Output

Write to `outputs/codex_findings/m7_v2_review/findings.md`:

```markdown
# Codex re-review of M-7 v2

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Fix integration
- [x/no] Promo lexicon + table-stripping recalibrated
- [x/no] Per-section breakdown rendered
- [x/no] Band marker clamping
- [x/no] Tests strengthened to behavior-level

## New issues
none / list

## Phase A completion
Are all 5 views (M-3..M-7) jointly aligned?

## Final word
GREEN to lock M-7 + Phase A complete / STILL-PARTIAL with edits.
```

Be terse. Under 100 lines.
