# Codex re-review of M-3 v3

## Verdict
STILL-PARTIAL

## Identifier resolver assessment
- The core plumbing is correct. `extractIdentifiers()` + `bibIdentifiers()` + `clustersByIdentifier` are wired the right way, and `bibIdentifiers()` now correctly pulls `doi`, `pmid`, `retrieval_attempt_log[].url`, and `bib.url` from `ir.frame_coverage.entries`.
- `urlStem()` preserving query strings fixes the v2 over-join concern.
- The remaining problem is canonicalization quality, not architecture.
- DOI regex gap: `\b10\.\d{4,9}/[^\s?#&]+` overcaptures publisher suffixes in real run-14 URLs, e.g. Frontiers `...10.3389/fphar.2022.998816/pdf` and Springer `...10.1007/s13300-023-01470-w.pdf`. Those become non-canonical DOI keys and can miss real matches.
- Retrieval-log gap: `bibIdentifiers()` feeds raw `retrieval_attempt_log[].url` values into `extractIdentifiers()`, but some are pseudo-URLs like `oa_full_text:https://...` and `url_pattern:https://...`. Those prefixes survive normalization, so URL-based bridging from frame coverage is incomplete when `bib.url` is blank.
- Focused verification passed: `python -m pytest tests/polaris_graph/test_inspector_router.py -q` -> 21 passed.

## Run-14 bridge reality
- Acceptable for Phase A. The shipped run-14 artifact really is mostly a disjoint-set problem, not a UI-plumbing problem.
- In the canonical demo, the entity-anchored trial entries mostly have DOI/PMID in `frame_coverage`, but the contradiction corpus mostly cites different papers.
- Actual outcome remains sparse: among the entity-anchored trial entries, only `surpass_5_primary` currently bridges, and that bridge is by exact JAMA PDF URL, not DOI/PMID.
- I would not require IR-load-time synthesis before Phase A. That is a later enhancement if you want denser cross-namespace drilldown, not a blocker to an honest run-14 demo.

## New issues
- DOI extraction is not fully canonical on publisher URLs with suffixes like `/pdf`, `.pdf`, and likely `/full`.
- Retrieval-log URL prefixes (`oa_full_text:`, `url_pattern:`) are not stripped before identifier extraction.

## Final word
STILL-PARTIAL with small edits. The scope call for run-14 is honest and acceptable, but I would fix DOI canonicalization and retrieval-log prefix stripping before locking M-3 and moving on to M-4.
