# CORE API v3 — verified facts (for the implement agents)
- Auth: header `Authorization: Bearer <key>`; key in env CORE_API_KEY (.env, gitignored). LAW VI: NEVER hardcode.
- DOI search: GET https://api.core.ac.uk/v3/search/works?q=doi:"<doi>"&limit=3 -> JSON {totalHits, results:[work,...]}.
- work fields: doi (may be "https://doi.org/.." or bare; normalize+lowercase), fullText (extracted OA text, may be ""),
  downloadUrl (OA PDF link, may be null), title.
- CRITICAL: the DOI search is FUZZY. For 10.1257/jep.33.2.3 it returned a SPANISH paper (wrong). MUST validate
  returned work.doi (normalized) == queried doi (normalized), reject ALL non-exact matches. Else wrong-paper fabrication.
- Coverage is PARTIAL: paywalled econ papers often 0 hits or empty fullText. CORE is a LEGAL best-effort full-text
  source; on miss return empty so the caller falls back to the abstract.
- Sci-Hub to disable: src/tools/access_bypass.py:949 `if os.getenv("PG_SCIHUB_ENABLED","1")=="1": ... _try_scihub(...)`.
  Also frame_fetcher.py already rejects access_method 'scihub' (I-faith #1034). Now make PG_SCIHUB_ENABLED default '0'
  AND skip _try_scihub entirely (no outbound request to any sci-hub.* host).
