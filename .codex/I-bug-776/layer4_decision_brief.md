# Codex DECISION — I-bug-776 (#817) LAYER 4: inject anchored-trial DOIs as candidates

You are the DECISION-MAKER (CHARTER §1). You already decided b1 (per-slug
primary-trial anchors) and APPROVE'd the diff (PR #819). The combined
#812+#815+#817 afib re-run STILL aborts (T1=0) — layer 4. Decide the injection
mechanism + guardrails + verification.

## What we learned (verified)
- The M-35 expander emits SEARCH queries: `"ARISTOTLE" {question}` +
  `"ARISTOTLE" Granger NEJM apixaban warfarin atrial fibrillation {question}`.
  All 8 afib anchor queries FIRED (confirmed in the log).
- But NONE of ARISTOTLE/ROCKET-AF/RE-LY/ENGAGE-AF reached the final 20-source
  corpus. The question ("current clinical GUIDELINES for anticoagulation") is
  guidelines-dominated; SERPER/S2 rank guidelines/reviews, and the ~1000→20
  candidate cap fills with them before the 2011 NEJM primary.
- **The 4 trials ARE OA** (pipeline Unpaywall returns NEJM PDFs):
  ARISTOTLE 10.1056/NEJMoa1107039, ROCKET-AF 10.1056/NEJMoa1009638,
  RE-LY 10.1056/NEJMoa0905561, ENGAGE-AF-TIMI-48 10.1056/NEJMoa1310907.
  So a DIRECT fetch → Unpaywall OA PDF → (PDF extract / #815 BioC) → T1.

## Candidate-build seam (investigated)
`run_honest_sweep_r3.py` builds candidates from amplified queries → SERPER+S2
(`_serper_search`, `_s2_bulk_search`) → ~1000 pre-filter → top 20. The expander
output is a list of query STRINGS merged into the amplified set; there is no
direct-seed-URL path today.

## Mechanism options (decide)
- **(a) DOI-as-query:** extend M-35 to ALSO emit the exact DOI as a query when a
  per-anchor DOI is configured (e.g. `"10.1056/NEJMoa1107039"` or
  `doi.org/10.1056/NEJMoa1107039`). SERPER returns the doi.org/NEJM URL as a top
  hit → candidate → Unpaywall OA → T1. Pro: reuses the proven search→candidate→
  Unpaywall path; smallest change. Con: still depends on SERPER returning the DOI
  URL + surviving the 20-cap (though an exact-DOI query is far less ambiguous than
  "ARISTOTLE", so it should rank the primary).
- **(b) Direct-seed-URL injection:** add a seam so anchored-trial DOIs become
  DIRECT candidate URLs (`https://doi.org/{doi}`) bypassing search, guaranteed in
  the candidate pool (subject to fetch success). Pro: deterministic. Con: new
  code path in the candidate builder; must respect the same fetch/tier/stub gates.
- combo / something else.

## Constraints (clinical-safety)
- A DOI candidate counts as T1 ONLY if the fetched source is the primary trial
  (the tier classifier + adequacy gate are unchanged — no laundering).
- DOI must be the anchored trial's real DOI (verified): the config maps
  anchor->DOI; only configured DOIs are injected (slug-scoped, no global).
- Do not blow the candidate cap or starve other sources — these are ADDITIONAL
  high-value candidates, not replacements.

## Decide
1. Mechanism (a / b / combo)? Why, on reliability + minimal-blast-radius grounds?
2. Config schema (e.g. `per_query_primary_trial_dois: {slug: {ANCHOR: DOI}}`)?
3. Guardrails + the invariant to test.
4. Verification (re-run afib → T1>=3 with the 4 trials surfacing as T1).
5. Anything mis-diagnosed?
Return a decision, not a menu.
