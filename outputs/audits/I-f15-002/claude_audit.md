# Claude architect audit — I-f15-002

**Issue:** embed extracted span text ≤500 chars (UTF-8 safe)
**Branch:** bot/I-f15-002
**Canonical-diff-sha256:** 85b29160ce9d3ff8d2b06ea6316ba1d5cf792902539bee038da25a592f26952f
**Brief verdict:** APPROVE iter 2 (0/0/0P1, 1 P2 bookkeeping)
**Diff verdict:** APPROVE iter 1 (0/0/0/0)

## Substrate honesty
- `src/polaris_graph/audit_bundle/` is the slice-004 module hosting bundle schema/builder/manifest substrate. `span_truncate.py` is a sibling helper, no cross-module coupling at this Issue.
- Stdlib `unicodedata.combining` only; no new dep.

## Algorithm correctness
- `cut = max_chars - 1`; output length = `cut + 1` ≤ `max_chars`. Verified by exact-500 assertions on ASCII and CJK truncation tests.
- Walk-back guards (a) combining mark on the next codepoint and (b) ZWJ join on either side of the cut. Tests cover Arabic combining, both ZWJ-cut directions, and a compound emoji where the natural cut lands inside the ZWJ sequence.
- Edge cases: `max_chars=0` → `""`; `max_chars=1` → `"…"`; `len(text) <= max_chars` → passthrough no ellipsis.
- All-combining-input degeneracy: walk-back drives `cut` to 0, output is just `"…"`. Cap holds.

## §9.4 compliance
- No mocks, no magic numbers (constants named), no `try: pass`, no `time.sleep`, no TODO/FIXME, no `pass` body.

## Sovereignty / external-egress
- Pure helper, no I/O, no network, no env var read. Zero sovereignty surface.

## Test integrity
- 11/11 PASS locally on Python 3.13.13.
- Hermetic: no fixtures, no env, no file IO.
- Includes constants-sanity test (`test_module_constants`) catching accidental rename.

## Out-of-scope follow-ups (named)
- I-f15-002b: integrate `truncate_span` into `bundle_builder` where extracted spans are embedded into the audit bundle.
- Full TR29 grapheme algorithm (regional indicators, variation selectors, hangul jamo, etc.) — post-Sep-6.

## CHARTER §1 LOC cap
- 127 net (33 src + 94 test). Under 200 by 73.

## Verdict
APPROVE on architect review. Ready to ship.
