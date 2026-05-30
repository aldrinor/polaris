# Clinical retrieval backend — design (part of #942 depth fix)

Area: clinical domain backend for the SHIPPING path
(run_honest_sweep_r3 -> live_retriever.run_live_retrieval ->
domain_backends.run_domain_backends).

## Verified facts (empirical + primary-source, 2026-05-29)

Integration point: `domain_backends.run_domain_backends` has NO clinical
branch (domain_backends.py:377-378 is only a comment). live_retriever.py:1276
already calls it with `domain="clinical"` for the benchmark questions
(run_honest_sweep_r3.py:1665 passes `domain=q["domain"]`).

Pipeline consumes evidence text ONLY from `_fetch_content(cand.url, ...)`
(live_retriever.py:1367, 1449-1459). `SearchCandidate.metadata` is NOT
read as evidence text. => a backend MUST emit a fetchable full-text URL;
carried inline text is invisible to strict_verify.

tier_classifier T7 traps: Rule 1 (<1000 chars => T7 stub), Rule 6
(abstract-only domains). Allowlisted clinical evidence hosts confirmed:
ncbi.nlm.nih.gov/pmc (T2), fda.gov + accessdata.fda.gov (T1),
clinicaltrials.gov (T3). NOT allowlisted: europepmc.org, dailymed.nlm.nih.gov.

Empirical fetch (this network, 2026-05-29):
- PMC full text (ncbi.nlm.nih.gov/pmc/articles/PMCxxx/): 200, 180KB -> T2. PASS.
- Europe PMC search (ebi.ac.uk/.../rest/search, keyless): 200, returns
  per-result pmid + pmcid + doi + fullTextUrlList. PASS.
- ClinicalTrials.gov SPA AND v2 API: 403 with both POLARIS-UA and browser-UA
  (Akamai bot block on this runtime). DEFER.
- openFDA label JSON (api.fda.gov): 200, full label text inline, but
  api.fda.gov is JSON not an allowlisted evidence page.
- accessdata.fda.gov DAF overview (?ApplNo=217806): 200, 63KB, allowlisted T1,
  but approval-history/navigation page (label text in linked PDFs).
- DailyMed (dailymed.nlm.nih.gov ?setid=...): 200, 706KB full SPL label
  (indications+contraindications+dosage+warnings), NOT allowlisted.

## Decision

Ship ONE verified backend this PR: **Europe PMC** (keyless, full-text,
indexes PubMed/NICE; resolve each hit to an allowlisted PMC full-text URL
or doi.org link). Defer openFDA (needs a tier_classifier DailyMed-allowlist
change = separate review surface + LOC) and ClinicalTrials.gov (403-blocked
at runtime) to Codex-reviewed fast-follow issues. NCBI E-utilities
(esearch+efetch) is an optional NCBI_API_KEY-gated supplement, kept behind a
default-off flag to honor the 200-LOC cap.

Cochrane: no clean free API; surfaces via Europe PMC indexing +
cochranelibrary.com URLs (already T1 in clinical_source_registry) — no
phantom Cochrane fetcher.

## clinical_retrieval/ reconciliation

`src/polaris_graph/clinical_retrieval/` is designed-but-unwired (its
process_retrieval has a sentinel _default_fetch_fn that raises; not imported
by run_honest_sweep_r3). The executing path is live_retriever+domain_backends.
This PR targets the executing path. The new `europe_pmc_search()` can later
double as the long-promised "PR 7" FetchHttpFn adapter for clinical_retrieval/
(thin SearchCandidate->FetchResult wrapper) — noted, not built here.
