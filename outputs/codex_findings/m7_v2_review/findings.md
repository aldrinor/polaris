# Codex re-review of M-7 v2

## Verdict
STILL-PARTIAL

## Fix integration
- [x] Promo lexicon + table-stripping recalibrated (`run-14=1`, Gemini comparator=`53`; acceptable against FINAL_PLAN's `1 vs 58` story)
- [x] Per-section breakdown rendered (derivation from verified-sentence `tokens.evidence_id -> bibliography.tier` is acceptable for Phase A)
- [no] Band marker clamping (`_bandMarkerLeftPct` is correct, but the expected-band bracket is not fully clamped)
- [x] Tests strengthened to behavior-level (targeted Node/router checks passed; browser DOM tests exist but were skipped locally because Chromium is unavailable)

## New issues
- `scripts/static/inspector/inspector.js:1447-1448` does not fully clamp the expected-band bracket as claimed: `bracketLeft` uses `Math.max(0, minF)` but not an upper clamp, so malformed `min_fraction > 1` renders `left:150%`. The marker fix is real; the bracket fix is incomplete and untested.

## Phase A completion
Not fully. M-3, M-4, M-5, and M-6 remain GREEN, and M-7 is demo-ready on the canonical run, but all 5 views are not jointly GREEN until the bracket-clamp straggler is closed.

## Final word
STILL-PARTIAL with one edit: clamp bracket left to `[0,1]` and add a direct test, then lock M-7 + Phase A complete.
