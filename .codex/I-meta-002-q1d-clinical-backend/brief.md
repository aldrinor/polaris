RULE NOW — emit the YAML verdict block FIRST. APPROVE this CONCRETE plan or REQUEST_CHANGES with specifics. Read AT MOST the cited regions. NO SPEND (free keyless API) — but it DOES hit the network.

HARD ITERATION CAP: 5. Iter 1 of 5. Front-load ALL findings; reserve P0/P1 for real execution risks.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex brief-gate (iter 1) — PR4 clinical retrieval backend: Europe PMC (#942-clinical). NO SPEND (free keyless); DOES hit network (fail-open).

Codex-verified depth gap (#941): `domain_backends.py:377` has NO clinical branch — the CLINICAL benchmark
domain (3 of 5 golden Qs) relies on generic Serper + keyless S2 only; no PubMed/Europe PMC/ClinicalTrials.gov.
This adds a keyless Europe PMC backend so the clinical search surface gains primary-literature breadth (the
benchmark must out-depth frontier DR on the clinical set). Lands on PR1 rerank + PR2 decomposition.

## GROUNDED FACTS (do not re-explore)
- `src/polaris_graph/retrieval/domain_backends.py`: existing backends (`arxiv_search` :127, `policy_targeted_serper`,
  `sec_edgar_search`) each take `(query, limit)` and return `list[SearchCandidate]`, fail-open. A shared
  `_http_get_json(url, params)` (:55) + `_http_get_text` exist (httpx, `HTTP_TIMEOUT`, follow_redirects).
  `SearchCandidate(url, title, snippet, source, metadata, query_origin)` from prefetch_offtopic_filter.
- `run_domain_backends(domain, research_question, amplified_queries)` (:331) dispatches per domain via a
  `_run(name, fn)` closure (dedups by URL, records `backends_used`/`per_backend_counts`); the `clinical`
  branch is a NO-OP comment (:377). Returns `DomainBackendResult`.
- `live_retriever.run_live_retrieval` already calls `run_domain_backends(domain=...)` and merges its
  candidates (these flow through the SAME fetch/tier/strict_verify chokepoint as Serper/S2 — no laundering).
- Workflow design (#941, Codex-verified): use Europe PMC (keyless, full-text-resolving) FIRST; PMC/DOI URLs
  only, NEVER `europepmc.org` landing pages; defer ClinicalTrials.gov (runtime 403) + openFDA/DailyMed
  (allowlist change) as NAMED fast-follows.

## CONCRETE PROPOSAL (APPROVE or correct)
A. **New `europe_pmc_search(query, limit=PG_DOMAIN_MAX_HITS) -> list[SearchCandidate]`** in
   domain_backends.py, matching the `arxiv_search` shape:
   - GET `https://www.ebi.ac.uk/europepmc/webservices/rest/search` with params
     `{"query": query, "format": "json", "resultType": "core", "pageSize": min(limit,25)}` via
     `_http_get_json`. Fail-open (None/exception → []).
   - For each `resultList.result[*]`, build a RESOLVABLE primary-literature URL, in priority order — and
     SKIP a result that yields none (never a europepmc.org landing page):
     1. `doi` → `https://doi.org/{doi}`
     2. else `pmcid` (e.g. "PMC123") → `https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/`
     3. else `pmid` → `https://pubmed.ncbi.nlm.nih.gov/{pmid}/`
   - `SearchCandidate(url=<resolved>, title=result["title"], snippet=result.get("abstractText","")[:300],
     source="europe_pmc", metadata={"doi": doi, "pmid": pmid, "pmcid": pmcid, "year": pubYear,
     "is_oa": isOpenAccess})`. (metadata mirrors the S2 candidate so downstream year/OA logic can read it.)
B. **Wire into the clinical branch** of `run_domain_backends`: `elif domain == "clinical":
   _run("europe_pmc", europe_pmc_search)`. Replaces the no-op comment. The `_run` closure already dedups by
   URL against existing candidates + records counts.
C. **Bounded / no-spend:** Europe PMC is FREE + KEYLESS (no API key, no cost). `PG_DOMAIN_MAX_HITS`
   (default 10) + the existing 3-amplified-query cap bound the call count. Add an env kill-switch
   `PG_CLINICAL_EUROPE_PMC` (default "1") so the backend can be disabled. `HTTP_TIMEOUT` applies; fail-open
   means a Europe PMC outage degrades to today's Serper+S2 (never breaks the run).
D. **Tests (offline, socket blocked):** inject a canned Europe PMC JSON response (monkeypatch
   `_http_get_json`): (1) a result with a `doi` → `https://doi.org/...` URL; (2) doi absent + `pmcid` →
   PMC URL; (3) only `pmid` → pubmed URL; (4) a result with NONE of doi/pmcid/pmid is SKIPPED (no
   europepmc.org landing URL ever emitted); (5) fail-open: `_http_get_json` returns None → []; (6)
   `run_domain_backends(domain="clinical")` now includes the europe_pmc backend in `backends_used`; (7)
   `PG_CLINICAL_EUROPE_PMC=0` disables it.

## Constraints / frozen
- NO SPEND (keyless). snake_case; explicit imports; no except:pass (fail-open = explicit try/except + log);
  ≤200 LOC. Untouched: strict_verify / D8 / runtime lock / the 5 PR-10 contracts / tier classifier /
  Serper+S2 path. Europe PMC candidates pass the SAME fetch/tier/strict_verify chokepoint (no laundering —
  a Europe PMC source counts as T1 only if the tier classifier confirms the fetched content).

## The real risks to rule on
1. Is DOI→PMC→PubMed the right URL priority, and is SKIPPING a result with no resolvable id correct
   (vs emitting a europepmc.org landing URL)? (Claim: skip — landing pages don't fetch as primary content.)
2. Europe PMC `query` syntax: passing the raw decomposed sub-query string is fine (free-text search), or
   should it be wrapped? (Claim: raw free-text is the documented default; confirm.)
3. Any dedup/merge issue when a Europe PMC DOI URL equals an S2 DOI URL for the same paper? (The `_run`
   closure dedups by URL; a `https://doi.org/{doi}` from both collapses — confirm that's the desired merge.)
4. Network/fail-open: a Europe PMC timeout/500 must degrade to Serper+S2, never break the run (confirm the
   try/except + None handling covers it).

APPROVE iff this adds a keyless Europe PMC clinical backend emitting only resolvable DOI/PMC/PubMed URLs,
wired into the clinical branch, fail-open + kill-switched, leaving strict_verify/D8/tier untouched, and is
test-proven offline.

---

## REVISED SPEC — Codex brief-gate iter-1 REQUEST_CHANGES adopted (binding for the build)
1. **URL priority is PMCID → DOI → PMID** (not DOI-first): PMC is the strongest keyless fetchable
   full-text path; a record with NONE of pmcid/doi/pmid is SKIPPED (never a europepmc.org landing URL).
2. **Dedup framing:** this PR does NOT claim `_run` dedups Europe PMC vs S2. Within-domain dedup is the
   `_run` closure; ACROSS backends the exact-URL collapse is at the live_retriever MERGE
   (`live_retriever.py:~1286-1291`, domain candidates appended only `if url not in seen_urls`, where
   seen_urls already holds Serper+S2 URLs). HONEST limitation: PMC-first means the same paper can appear
   as a PMC URL (Europe PMC) and a DOI URL (S2) — not collapsed; acceptable (fetch/tier/strict_verify
   handles it; worst case a benign re-fetch).
3. Raw Europe PMC query strings (httpx params handles encoding; free-text is the default). Fail-open +
   `PG_CLINICAL_EUROPE_PMC=0` kill-switch retained. (Codex diff-gate iter-1 P1 additionally moved the
   `_http_get_json` HTTP call INSIDE the fail-open try so a network exception returns [] not escapes.)
