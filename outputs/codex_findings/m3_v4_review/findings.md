# Codex final review of M-3 v4

## Verdict
GREEN

## Canonicalization fix verification
- [x] canonicalizeDoi handles flagged publisher suffixes
- [x] stripUrlPrefix handles oa_full_text: / url_pattern: / pdf:

## New issues
none

## Final word
GREEN to lock M-3. Spot-check passed for Frontiers `/pdf`, Springer `.pdf`, and `oa_full_text:` / `url_pattern:` / `pdf:` prefix unwrapping. Targeted tests passed: `tests/polaris_graph/test_inspector_markdown.py` 13/13 and `tests/polaris_graph/test_inspector_router.py` 23/23.
