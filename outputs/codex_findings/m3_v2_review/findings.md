# Codex re-review of M-3 v2

## Verdict
STILL-PARTIAL

## Fix integration check
- [x] Layout split-pane structure
- [x] Full cluster rendering
- [no] URL-stem resolver
- [x] URL protocol sanitization
- [x] Tier/severity enum validation
- [x] A11y attributes + focus management
- [x] Horizontal rule + adjacent tables

## New issues introduced
- `urlStem()` is too lossy: stripping query strings collapses distinct URLs such as `jomes.org/journal/download_pdf.php?doi=...` into one key. No false hit from the current bibliography, but the resolver can over-join.

## Final word
STILL-PARTIAL with edits. The layout, pane rendering, sanitization, enum validation, a11y, and markdown fixes are integrated correctly. The resolver only recovers `surpass_5_primary` in run-14; blank-URL `surpass_*` bibliography entries still cannot bridge to `ev_*` contradiction claims, so M-3 is not lock-ready yet.
