M-3 v4 — final GREEN check.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-3 v3 verdict was STILL-PARTIAL with two specific canonicalization
gaps. Both fixed in v4.

## What changed

1. **canonicalizeDoi(doi)** added. Strips publisher-suffix artefacts:
   - Trailing path segments: /pdf, /full, /abstract, /html, /epdf,
     /metrics, /references
   - Trailing extensions: .pdf, .html, .xml, .epub
   - Trailing slashes
   Iterates until stable. Tests verify Frontiers /pdf and Springer .pdf
   examples canonicalize correctly.

2. **stripUrlPrefix(url)** added. Detects pseudo-URL prefixes
   (oa_full_text:, url_pattern:, pdf:) via
   `/^[A-Za-z][A-Za-z0-9_]+:(https?:\/\/.+)$/` and returns the bare URL.

Both helpers wired into extractIdentifiers() and bibIdentifiers().

Tests: 101 → 108. 5 new Node-eval tests verify end-to-end behavior on
the exact examples you flagged (Frontiers /pdf, Springer .pdf,
oa_full_text:https:// prefix unwrapping).

## Your job

Final verdict on M-3. GREEN / STILL-PARTIAL / DISAGREE.

Quick spot-check:
- DOI canonicalization handles your examples correctly?
- URL-prefix stripping handles oa_full_text: + url_pattern: + pdf:
  prefixes?
- Any new issues introduced?
- M-4 ready?

## Output

Write to `outputs/codex_findings/m3_v4_review/findings.md`:

```markdown
# Codex final review of M-3 v4

## Verdict
GREEN / STILL-PARTIAL / DISAGREE

## Canonicalization fix verification
- [x/no] canonicalizeDoi handles flagged publisher suffixes
- [x/no] stripUrlPrefix handles oa_full_text: / url_pattern: / pdf:

## New issues
none / list

## Final word
GREEN to lock M-3 / STILL-PARTIAL with edits.
```

Be terse. Under 80 lines. This is final final sign-off.
