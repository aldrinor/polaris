# Claude architect audit — I-bug-775 (#815) PMC BioC full-text fetcher

## Root cause (verified live, afib re-run log + access_bypass code)
The dominant corpus_inadequate cause is the FETCH layer, not classification. The
fetch path is already sophisticated (Unpaywall → PDF extract → concurrent
crawl4ai/jina/firecrawl), but stubs in the long tail: (1) Unpaywall "publisher OA
landing" → doi.org landing → 280-400-char stub; (2) Unpaywall PDF swap but PDF
extraction fails (jacc→PMC PDF→54 chars); (3) PMC HTML scraping inconsistent
(PMC12240022→25000 ✓, PMC6490750→111 ✗). Authoritative clinical sources
(JACC/AHA/PMC) stub → T7 → T1=0 → corpus_inadequate.

## Decision provenance (Codex = decision-maker)
`.codex/I-bug-775/decision_verdict.txt`: Codex decided A+B+D (BioC by PMCID +
tighten Unpaywall + no threshold change), with BioC/E-Utilities doc citations.

## Implementation (line-by-line self-audit)
- A: `_extract_pmcid` + `_try_pmc_bioc_fulltext` (BioC_json/<PMCID>/unicode),
  wired into `fetch_with_bypass` PMCID-first (before Unpaywall/PDF/scrapers) +
  after Unpaywall PMC swaps. NCBI throttle: Semaphore(1) + ~0.34s min-interval +
  429 exp backoff. Full-text guard `_parse_bioc_fulltext`: body section OR
  article-sized passage set; rejects abstract-only/refs-only/error.
- B: `_try_unpaywall` returns only direct PDF or a PMCID-bearing PMC URL; never a
  publisher/doi.org landing (mode-1 fix).
- D: no <200/<1000 threshold changes.

## §-1.1 / no-laundering verification
- BioC AccessResult(success=True) ONLY for body full text ≥1000 chars; non-OA /
  abstract-only / error → None → falls through (may still T7, correct).
- Rule-1 stub + is_content_starved UNCHANGED.

## Evidence
- LIVE smoke: PMC10715890 (JACC, was 54-char PDF stub) → BioC 62647 chars;
  PMC12240022 → 35338; PMC6490750 (non-OA) → None (correct fall-through).
- 48 access regression tests + 10 new #815 tests green.
- Codex diff review: APPROVE iter-1 (zero P0/P1, MERGE AUTHORIZED), one
  non-blocking P2 (mocked Unpaywall regression) — ADDRESSED (3 added tests).

## Verdict
Code-correctness: APPROVE (Codex iter-1). **Remaining gate (LAW II empirical):**
live afib re-run must confirm corpus adequacy improves (more authoritative
sources fetch full-text via BioC → higher T1/T2). Running. Pairs with #812
(classification). NOT merged by Claude — queued for operator.
