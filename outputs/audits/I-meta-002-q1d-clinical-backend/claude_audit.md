# Claude architect audit — PR4 Europe PMC clinical backend (#942-clinical)

## What this fixes (Codex-verified depth gap)
`domain_backends.py` had NO clinical branch — the clinical benchmark domain (3 of 5 golden Qs) relied on
generic Serper + keyless S2 only, no primary-literature backend. This adds a keyless Europe PMC backend so
the clinical search surface gains PubMed-indexed primary-literature breadth (the benchmark must out-depth
frontier DR on the clinical set). Lands on PR1 rerank (#959) + PR2 decomposition (#960).

## Design (both Codex gates APPROVE; diff iter 2)
- **`europe_pmc_search(query, limit)`** — KEYLESS, FREE (no API key, no cost). GET Europe PMC REST search
  (`resultType=core`, `pageSize=min(limit,25)`) via the shared `_http_get_json`. URL priority **PMCID →
  DOI → PMID** (Codex brief-gate: PMC is the strongest keyless fetchable full-text path): pmcid →
  `ncbi.nlm.nih.gov/pmc/articles/{pmcid}/`, else doi → `doi.org/{doi}`, else pmid →
  `pubmed.ncbi.nlm.nih.gov/{pmid}/`, else SKIP (never a europepmc.org landing page). `source="europe_pmc"`;
  metadata carries doi/pmid/pmcid/year/is_oa (mirrors the S2 candidate).
- **Fail-open** (Codex diff-gate iter-1 P1): the `try` wraps BOTH the `_http_get_json` HTTP call AND the
  parse — any network/helper/parse exception → log + `return []` (degrade to Serper+S2, never break the run).
- **Clinical dispatch** wired with kill-switch `PG_CLINICAL_EUROPE_PMC` (default on). CT.gov (runtime 403)
  + openFDA/DailyMed (allowlist change) named as fast-follows.
- **Dedup (honest):** within-domain dedup is the `_run` closure; across backends the exact-URL collapse is
  at the live_retriever merge (`live_retriever.py:~1286-1291`, `if url not in seen_urls`). Limitation:
  PMC-first means a paper can appear as a PMC URL (Europe PMC) + a DOI URL (S2) — not collapsed; acceptable
  (fetch/tier/strict_verify handle it; worst case a benign re-fetch). This PR does NOT over-claim `_run`.

## Verification (offline, no spend)
- 15 domain-backend tests PASS incl. 6 new: PMCID-first (even with doi+pmid), DOI-then-PMID fallback,
  skip-record-with-no-id (no europepmc.org URL), fail-open on None / bad-shape / EXCEPTION, clinical
  dispatch calls europe_pmc, kill-switch disables it. `verify_lock --consistency` OK.
- Frozen/untouched: strict_verify / D8 / runtime lock / the 5 PR-10 contracts / tier classifier / Serper+S2
  path. Europe PMC candidates pass the SAME fetch/tier/strict_verify chokepoint (no tier laundering — a
  source counts as T1 only if the classifier confirms the fetched content).

## Clinical-safety note
No-spend (keyless), fail-open (never breaks the clinical run), kill-switchable. Broadens evidence breadth
without weakening any verification gate; every Europe PMC source still earns its tier from fetched content.
