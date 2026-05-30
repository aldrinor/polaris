RULE NOW — emit the YAML verdict block FIRST. Read the patch at `.codex/I-meta-002-q1d-clinical-backend/codex_diff.patch` (2 files, +138/-2). Do NOT explore beyond it. NO SPEND (keyless API).

HARD ITERATION CAP: 5. Iter 1 of 5. Front-load all findings; reserve P0/P1 for real execution risks.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex diff-gate (iter 1) — PR4 Europe PMC clinical backend (#942-clinical). Verify the diff implements the brief-gate-required changes. NO SPEND (keyless); DOES hit network (fail-open).

The brief-gate (REQUEST_CHANGES) required: PMCID→DOI→PMID URL priority; don't claim `_run` dedups vs S2.
This diff implements them. Verify + no regression.

## What the diff implements (verify against the patch)
1. **`europe_pmc_search(query, limit)`** in `domain_backends.py` — keyless GET to
   `https://www.ebi.ac.uk/europepmc/webservices/rest/search` (`format=json, resultType=core, pageSize=min(limit,25)`)
   via the existing `_http_get_json`. Fail-open (None/`{}`/exception → []). For each result, URL priority
   **PMCID → DOI → PMID** (Codex brief-gate fix): `pmcid` → `https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/`,
   else `doi` → `https://doi.org/{doi}`, else `pmid` → `https://pubmed.ncbi.nlm.nih.gov/{pmid}/`, else SKIP
   (never a europepmc.org landing page). `source="europe_pmc"`, metadata carries doi/pmid/pmcid/year/is_oa.
2. **Clinical dispatch** — `run_domain_backends` clinical branch now `_run("europe_pmc", europe_pmc_search)`
   behind a kill-switch `PG_CLINICAL_EUROPE_PMC` (default "1"). CT.gov + openFDA noted as fast-follows.

## Dedup (Codex brief-gate point — confirmed, NOT claimed via `_run`)
- WITHIN domain backends, `run_domain_backends._run` dedups by URL against already-collected domain
  candidates (existing `test_r6_dispatcher_dedupes_across_backends`).
- ACROSS backends (Europe PMC vs Serper/S2), the EXACT-URL collapse happens at the live_retriever MERGE:
  `live_retriever.py:~1286-1291` appends domain candidates only `if url not in seen_urls`, where `seen_urls`
  already contains every Serper+S2 URL — so a Europe PMC `https://doi.org/{doi}` equal to an S2 DOI URL
  collapses. HONEST LIMITATION: with PMC-first, the SAME paper can appear as a PMC URL (Europe PMC) and a
  DOI URL (S2) — different URLs, NOT collapsed; that is acceptable (the fetch/tier/strict_verify chokepoint
  handles it; worst case a benign re-fetch). This PR does NOT claim `_run` solves cross-backend dedup.

## Evidence (verified by Claude main-thread)
- 15 domain-backend tests PASS incl. 6 new: PMCID-first (even with doi+pmid), DOI-then-PMID fallback,
  skip-record-with-no-id (no europepmc.org URL ever), fail-open on None/bad-shape, clinical dispatch calls
  europe_pmc, kill-switch disables it. Plus 46 across domain/rerank/env-knobs PASS; `verify_lock` OK.
- Diff +138/-2 net 136 (≤200). Frozen/untouched: strict_verify / D8 / runtime lock / 5 PR-10 contracts /
  tier classifier / Serper+S2 path. Europe PMC candidates pass the SAME fetch/tier/strict_verify chokepoint
  (no tier laundering — counts as T1 only if the classifier confirms fetched content).

## Rule on
1. Is PMCID→DOI→PMID correct + is SKIP (not a landing URL) right for a record with no resolvable id?
2. Is fail-open robust (None body, non-dict `resultList`, missing keys all → [] / skip, never raise)?
3. No-spend confirmed (keyless)? `pageSize`/`PG_DOMAIN_MAX_HITS` + 3-amplified cap bound call count?
4. The dedup framing above — is it accurate (not over-claiming)? Any real dup risk that hurts the run?

APPROVE iff the Europe PMC backend is keyless/fail-open/kill-switched, emits only resolvable
DOI/PMC/PubMed URLs with PMC-first priority, leaves strict_verify/D8/tier untouched, and is test-proven.
