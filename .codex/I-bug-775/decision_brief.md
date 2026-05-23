# Codex DECISION request — I-bug-775 (#815, URGENT): authoritative clinical sources fetch as stubs

You are the DECISION-MAKER (CHARTER §1). Decide the fix approach + priority +
guardrails + verification. Clinical-safety: this is the DOMINANT cause of
corpus_inadequate (the dominant benchmark abort, 5/13 vectors). Front-load all
real findings; I will execute your decision then bring you the diff to review.

## Problem
Authoritative clinical journals fetch as content-starved stubs (<200 chars →
skipped; <1000 → T7), so clinical corpus adequacy (T1≥3, T2≥2) is unmet. Verified
live: a fresh afib re-run STILL aborts corpus_inadequate (T1=0) with 8/20 sources
stubbed — incl JACC, AHA, ScienceDirect, a PMC article.

## The fetch layer is ALREADY sophisticated (src/tools/access_bypass.py, 2406 lines)
`fetch_with_bypass`: Unpaywall (M-23a, DOI→OA) → PDF detect+extract (docling/
PyMuPDF, FIX-GAP4) → concurrent Crawl4AI+Jina+Firecrawl, quality-scored
(`_score_content_quality`), per-backend 60s wall-clock (PG_BACKEND_FETCH_TIMEOUT).
So this is NOT a missing-feature; the stubs are in the LONG TAIL.

## Precise failure modes (from the afib re-run log — real evidence)
1. **Unpaywall "publisher OA landing" → doi.org/ LANDING page → stub.**
   `10.1111/eci.13803` → swapped to `doi.org/...` → crawl4ai 305 chars.
   `10.1097/AAP...` → 283 chars. The landing isn't full text; the swap made it
   no better than the paywalled original.
2. **Unpaywall PDF swap, but PDF extraction FAILS → fallback stub.**
   `jacc.org/doi/10.1016/j.jacasi.2023.08.007` → Unpaywall found
   `pmc.../PMC10715890/pdf/main.pdf` → swapped → but fetch returned **54 chars**
   (PDF extraction failed → fell back, content-starved).
3. **Direct PMC HTML extraction is INCONSISTENT.**
   `PMC12240022` → trafilatura → **25000** ✓ (works!).
   `PMC6490750` → jina timed out (60s) → crawl4ai → **111** ✗.
   Same host, opposite outcomes — scraping is flaky on PMC's JS-heavy pages.

## Key leverage observation
Most clinical OA — both Unpaywall results AND direct hits — resolve to **PMC
PMCIDs**. A structured **PMC-OA full-text API by PMCID** would be far more
reliable than scraping PMC HTML/PDF, and would fix BOTH failure-mode 2 (use the
API instead of the flaky PDF) AND mode 3 (API instead of HTML). Options:
- NCBI BioC: `https://www.ncbi.nlm.nih.gov/research/bionlp/RESTful/pmcoa.cgi/BioC_xml/<PMCID>/unicode`
- efetch: `https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pmc&id=<PMCID>&rettype=xml`
`NCBI_API_KEY` is already configured (`src/config/core.py:290`). (Note: the
efetch code in `src/agents/search_agent.py:1342-1370` is a PubMed-ABSTRACT
fetcher in legacy pipeline C — NOT wired into the active access_bypass path, and
it returns abstracts, not PMC full text.)

## Decide (one or combination)
- **A. PMC-OA-by-PMCID fetcher** wired into fetch_with_bypass: when a URL is (or
  Unpaywall resolves to) a pmc.ncbi PMCID, fetch full text via BioC/efetch
  db=pmc BEFORE/instead of scraping. Highest leverage (PMC is where OA lands).
  BioC vs efetch — which?
- **B. Prefer Unpaywall best_oa_location PDF/repository over "landing"**: don't
  swap to a doi.org landing (mode 1); only swap to a real PDF/PMC URL.
- **C. PDF-extraction robustness** (mode 2): why did the PMC PDF give 54 chars?
- **D. Accept genuinely-paywalled stubs** (AHA/JACC non-OA) as unfixable; don't
  lower the stub threshold (would launder junk).

## Hard constraints
- Full text ONLY — never lower the <200/<1000 stub thresholds to admit stubs
  (clinical-safety: a stub can't support a claim; #812's no-laundering guardrail).
- API content is genuine full text (not laundering).
- Respect NCBI rate limits (the legacy code backs off on 429).

## Return
1. Approach (A/B/C/D/combo)? If A: BioC or efetch, and where in fetch_with_bypass?
2. Priority order + the guardrail/invariant to test.
3. Verification (re-run which vectors, pass bar).
4. Anything mis-diagnosed?
Return a decision, not a menu.

## Files I have ALSO checked and they're clean
- `live_retriever.py`: `is_content_starved` (min 200 chars, L1046); skip at L1504.
- `tier_classifier.py`: T7_STUB at <1000 (Rule 1) — correct, not the bug.
- Unpaywall (`_try_unpaywall`) + `_extract_doi` (L2370, handles 10.x + doi.org/).
- `_extract_pdf_text` (FIX-GAP4 PDF path) — mode-2 failure is here.
- search_agent.py efetch = PubMed abstracts, legacy, not active path.
