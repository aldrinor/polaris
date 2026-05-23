# Codex DIFF review — I-bug-775 (#815): PMC BioC full-text fetcher. Iter 1 of 5.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `ad89c0f5135cabba6841235c7827e8cdec7cb2a26a9e8c8e7f447b15b7bff5cb`. This implements YOUR decision (A+B+D). 2 files:
src/tools/access_bypass.py (+152 prod lines) + tests/polaris_graph/
test_bug775_pmc_bioc_fulltext.py (new). MERGE AUTHORIZED if mergeable + APPROVE
iff zero P0/P1. Clinical-safety core (fetch reliability of clinical evidence).

## What this implements (your A+B+D)
- **A**: `_extract_pmcid` + `_try_pmc_bioc_fulltext` (BioC_json/<PMCID>/unicode).
  Wired into `fetch_with_bypass` (1) after _resolve_academic_url, before
  Unpaywall/PDF/scrapers, when the URL carries a PMCID; (2) after an Unpaywall
  swap when the OA URL is a PMC URL. NCBI throttle: module Semaphore(1) +
  _NCBI_MIN_INTERVAL ~0.34s + 429 exponential backoff (3 attempts).
- Full-text guard `_parse_bioc_fulltext`: accept only if there is an explicit
  BioC body section (not in _BIOC_NON_BODY_SECTIONS = TITLE/ABSTRACT/REF/...) OR
  an article-sized passage set (>=5 passages AND >=3000 chars). Returns '' for
  error/garbage/abstract-only/refs-only. Caller requires >= _PMC_BIOC_MIN_FULLTEXT_CHARS (1000).
- **B**: `_try_unpaywall` no longer returns a publisher/doi.org LANDING (mode-1
  stub); returns only a direct PDF (existing) OR a PMCID-bearing PMC URL (scanned
  across oa_locations) so the caller's BioC path resolves it. Else None.
- **D**: no <200/<1000 threshold changes.

## Why safe (no laundering)
- Rule-1 stub (<1000 → T7) + is_content_starved (<200) UNCHANGED.
- BioC AccessResult(success=True) ONLY when _parse_bioc_fulltext returns body
  full text >= 1000 chars; non-OA / abstract-only / error → None → falls through
  to the existing cascade (which may still stub → T7, correct).

## Smoke + test evidence (claim-by-claim)
- LIVE: PMC10715890 (the JACC OA copy that PDF-extraction stubbed at 54 chars) →
  BioC **62647 chars**; PMC12240022 → 35338; PMC6490750 (NOT in OA subset) →
  None (correctly falls through — no laundering).
- 48 access_bypass regression tests green (m23/backend_timeout/teardown/wiring/m45).
- 7 new tests: _extract_pmcid (PMC URLs + None for non-PMC); _parse_bioc_fulltext
  rejects abstract-only / refs-only / garbage / error; accepts body-section +
  large-unsectioned; rejects tiny-unsectioned.

## Files I have ALSO checked and they're clean
- AccessResult shape (url/content/access_method/legal_alternative/success/metadata).
- aiohttp is the async client used throughout; json imported locally in the parser.
- _time_module alias (not `time`); _NO_BROTLI_HEADERS reused.
- The PMCID-first return is BEFORE the S2-landing skip? No — after it + after
  _resolve_academic_url, before Unpaywall. Verify ordering is correct.

## Review focus
1. Any P0/P1: NCBI rate-limit correctness (global last-request-time race under
   Semaphore(1)?), the full-text guard (could it accept a non-full-text doc, or
   reject genuine full text?), the Unpaywall B-change (could it now drop a
   legitimate OA full-text URL?).
2. Any laundering path (success=True on a stub)?
3. Anything mis-implemented vs your decision.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
