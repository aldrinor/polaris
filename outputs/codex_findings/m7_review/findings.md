# Codex review of M-7

## Verdict
PARTIAL

## FINAL_PLAN compliance
Covered: the header-tier bar is already satisfied jointly by M-2, View 5 adds the large corpus bar, expected-vs-actual tier table, promo badge, material-deviation banner, and residual-tier handling.

Missing: FINAL_PLAN explicitly says `per-section breakdown`, and M-7 does not render one.

## Specific issues
- `scripts/static/inspector/inspector.js:1364-1371,1443-1495` promo calibration does not match the stated baseline. The scanner counts raw markdown matches, so run-14 hits `superior` twice (`report.md` prose + table row), not 1. Directly applying the shipped 15 regexes to `state/compare_gemini_dr.txt` yields 18 hits, not the claimed 58, so the badge is under-calibrated for the comparator it is supposed to distinguish.
- `scripts/static/inspector/inspector.js:1417-1555` FINAL_PLAN’s per-section tier breakdown is absent. `scripts/static/inspector/inspector.css:1462-1465` has an unused `.tier-mix-section-stats` hook, but no section-level render path exists.
- `scripts/static/inspector/inspector.js:1386-1391,1411` and `scripts/static/inspector/inspector.css:1446-1452` the band marker is not quite edge-correct: `actual=1` renders at `left:100%` with a 2px width and no centering/clipping, so it sits outside the right edge. Residual-row markers are also not clamped.
- `tests/polaris_graph/test_inspector_router.py:865-945` and `tests/polaris_graph/test_inspector_browser.py:400-437` only assert presence. They do not catch the current promo-count drift, do not assert the `UNKNOWN` residual row in live DOM, do not assert any per-section block, and do not exercise marker edge cases.

## Recommended changes
- For Phase A, derive the missing section breakdown from `verified_report.sections[*].sentences[*].tokens[*].evidence_id -> bibliography.tier`. Do not use `frame_coverage.provenance_class` as the proxy; run-14 would collapse to mostly/all T1 and misrepresent corpus mix. If you need true corpus-member section attribution, that is a Phase B IR addition.
- Make promo counting narrative-only: strip markdown tables/bibliography blocks before scanning, then extend the lexicon to the hype words actually used in the Gemini comparator (`massive`, `definitive/definitively`, `decisive/decisively`, `astonishing`, `gold standard`, `landmark`, `dramatically`, etc.).
- Add exact tests: run-14 promo count `== 1`, comparator baseline reproduction, `UNKNOWN` residual row present, and marker positions for `0`, `1`, and out-of-range inputs.

## Phase A completion
Views 1-4 still look aligned. View 5 is demoable, but Phase A is not fully aligned to FINAL_PLAN until the section breakdown lands and the promo badge is calibrated to the documented `1 vs 58` story.

## Final word
PARTIAL with targeted edits. I would not GREEN-lock M-7 yet.
