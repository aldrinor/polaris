# Codex DIFF review — I-bug-776 (#817) anchors + LAYER-4 DOI injection. Iter 1 of 5.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

Canonical-diff-sha256 `e712e88ef2c017d6fe90ebca63ac80af465ad18138064759bbf2f4984ae64696`. This is the SAME #817 branch you APPROVE'd at the
anchor stage (PR #819), now PLUS layer-4 (your decision b: direct DOI injection).
70 prod lines across live_retriever + primary_trial_expander + run_honest_sweep_r3
+ clinical.yaml config + a new test. MERGE AUTHORIZED if mergeable + APPROVE iff
zero P0/P1. Clinical-safety CORE retrieval change — review carefully.

## What layer-4 adds (your decision b)
- live_retriever.run_live_retrieval: NEW `seed_urls: Optional[list[str]] = None`
  param. Seeds injected at the FRONT of `candidates` (with seen_urls dedup,
  source="primary_trial_doi"); the fetch_cap slice is bumped by the injected
  count (`candidates[:fetch_cap + _n_seed_injected]`) so seeds are ADDITIVE — a
  reserved front lane that does NOT evict search/guideline candidates. Seeds then
  flow through the SAME fetch / Unpaywall-OA / extraction / OpenAlex / tier /
  adequacy path — a seed counts as T1 ONLY if the tier classifier identifies the
  fetched content as a primary (no laundering). Backwards-compatible: seed_urls
  None/[] -> _n_seed_injected=0 -> cap unchanged -> zero behaviour change.
- primary_trial_expander.expand_primary_trial_dois(template, slug): reads
  `per_query_primary_trial_dois` ({ANCHOR: DOI}); validates DOIs (10.x/<suffix>,
  no whitespace/quote/backslash); returns `https://doi.org/{doi}`; slug-scoped;
  []-on-missing/malformed (backwards-compatible).
- run_honest_sweep_r3: passes seed_urls=expand_primary_trial_dois(_template, slug).
- clinical.yaml: afib DOIs (NEJMoa1107039/1009638/0905561/1310907 — OA-verified
  via Unpaywall; you fact-checked these against the NEJM article DOIs).

## Why (verified)
Layer-3 anchor SEARCH queries fired but the combined #812+#815+#817 afib run STILL
aborted T1=0 — none of the 4 trials reached the final 20 (guideline-dominated
SERPER/S2 ranking + the cap buried them). The 4 DOIs ARE OA (Unpaywall returns
NEJM PDFs). Direct injection bypasses the search-ranking problem.

## Guardrails honored (your decision)
- Slug-scoped (no global DOI injection); only configured anchors.
- Additive (cap bumped) — does not evict guidelines.
- Same gates; no tier/adequacy/threshold change; no laundering.
- Dedup by URL.

## Test evidence
- 56 retrieval/access regression tests green (seed_urls=None backwards-compat).
- 10 M-35 expander tests green. 5 new layer-4 tests: afib DOIs->doi.org URLs;
  negatives (unconfigured slug / no template / malformed) -> []; malformed-DOI
  rejection; _is_valid_doi; dedupe-order.
- expand_primary_trial_dois(afib) -> the 4 NEJM doi.org URLs.

## Review focus
1. The seed-injection + cap-bump correctness (any way a seed launders to T1 without
   passing the tier classifier? any eviction of guidelines? off-by-one in the cap?).
2. seed_urls backwards-compat (None path unchanged)?
3. DOI validation (any malformed DOI slipping to a bad URL)?
4. Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
